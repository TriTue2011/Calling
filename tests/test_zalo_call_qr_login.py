"""Đăng nhập/đăng xuất Zalo bằng QR từ Home Assistant (14/11/2026): logic QR thuần, lớp API gọi đúng route app, và dây nối dịch vụ/nút/thực thể.
Chạy được không cần Home Assistant. Run: python3 tests/test_zalo_call_qr_login.py"""
import asyncio
import base64
import importlib.util
import os
import sys
import types

CC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_components", "zalo_call")


def load(name):
    spec = importlib.util.spec_from_file_location("zc_" + name, os.path.join(CC, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["zc_" + name] = m
    spec.loader.exec_module(m)
    return m


qr = load("qr_login")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def url(raw):
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def test_normalize_client_accepts_web_pc_blank_and_rejects_others():
    assert qr.normalize_client("web") == "web" and qr.normalize_client(" PC ") == "pc"
    assert qr.normalize_client(None) is None and qr.normalize_client("") is None and qr.normalize_client("  ") is None
    for bad in ("mobile", "android", "zalo", "webb"):
        try:
            qr.normalize_client(bad)
        except ValueError:
            continue
        raise AssertionError("phải từ chối %r" % bad)


def test_png_from_data_url_decodes_only_real_png():
    assert qr.png_from_data_url(url(PNG)) == PNG
    assert qr.png_from_data_url(url(b"GIF89a....")) is None                      # không phải PNG
    assert qr.png_from_data_url("data:image/png;base64,@@@không-phải-base64") is None
    assert qr.png_from_data_url("data:image/jpeg;base64," + base64.b64encode(PNG).decode()) is None
    assert qr.png_from_data_url(None) is None and qr.png_from_data_url("") is None and qr.png_from_data_url(123) is None


def test_attributes_describe_every_state_in_vietnamese_and_leak_no_image():
    for st in ("idle", "waiting", "scanned", "done", "expired", "rate_limited", "rejected", "error"):
        a = qr.attributes({"state": st})
        assert a["trang_thai"] == st and a["mo_ta"] == qr.STATE_TEXT[st] and a["mo_ta"] != st, a
    a = qr.attributes({"state": "waiting", "client": "pc", "countdown": 90, "qr_image": url(PNG), "uid": 5, "error": "x" * 500, "warning": "w"})
    assert a["kieu_dang_nhap"] == "pc" and a["kieu_dang_nhap_ten"] == "PC (Zalo PC)" and a["het_han_sau_giay"] == 90 and a["uid"] == "5", a
    assert len(a["loi"]) == 200 and a["canh_bao"] == "w"
    assert "qr_image" not in a and "base64" not in str(a)                          # ảnh không nằm trong thuộc tính (nặng, và là bí mật phiên)
    assert qr.attributes(None)["trang_thai"] == "idle" and qr.attributes({"state": "la-hoac"})["mo_ta"] == "la-hoac"
    assert "kieu_dang_nhap" not in qr.attributes({"state": "idle", "client": "android"})


class _Resp:
    def __init__(self, data, status=200):
        self._d, self.status = data, status

    async def json(self, content_type=None):
        return self._d

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Session:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append((method, url.split("//", 1)[-1].split("/", 1)[-1], kw.get("json")))
        return _Resp({"ok": True, "state": "waiting"})


def test_api_client_calls_the_right_app_routes():
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        print("SKIP: không có aiohttp")
        return
    api = load("api")
    s = _Session()
    c = api.ZaloCallApi(s, "http://app:8090/", "u", "p")

    async def run():
        await c.qr_new("web")
        await c.qr_new("pc")
        await c.qr_new()
        await c.qr_new("")
        await c.qr_status()
        await c.zalo_logout()
    asyncio.run(run())
    assert s.calls == [("POST", "api/qr/new", {"client": "web"}), ("POST", "api/qr/new", {"client": "pc"}),
                       ("POST", "api/qr/new", {}), ("POST", "api/qr/new", {}),
                       ("GET", "api/qr/status", None), ("POST", "api/zalo/logout", {})], s.calls          # không client = {} (giữ kiểu hiện tại)


def test_wiring_services_buttons_image_platform_and_docs():
    sv = open(os.path.join(CC, "services.py"), encoding="utf-8").read()
    assert 'DOMAIN, "login_qr", login_qr' in sv and 'DOMAIN, "logout", logout_zalo' in sv
    assert 'vol.Optional("type"): vol.In(list(qr_login.CLIENTS))' in sv and "qr_login.normalize_client(call.data.get(\"type\"))" in sv
    bt = open(os.path.join(CC, "button.py"), encoding="utf-8").read()
    for k in ('"login_web"', '"login_pc"', '"logout"'):
        assert k in bt, k
    assert 'api.qr_new(self._key.split("_", 1)[1])' in bt and "api.zalo_logout()" in bt
    assert '"image"]' in open(os.path.join(CC, "__init__.py"), encoding="utf-8").read()
    im = open(os.path.join(CC, "image.py"), encoding="utf-8").read()
    assert "class ZaloQrImage(ZaloCallEntity, ImageEntity)" in im and "qr_login.png_from_data_url" in im and "_attr_image_last_updated" in im
    y = open(os.path.join(CC, "services.yaml"), encoding="utf-8").read()
    assert "\nlogin_qr:\n" in y and "\nlogout:\n" in y and "value: web" in y and "value: pc" in y


def test_logged_in_from_coordinator_data_unknown_when_missing():
    assert qr.logged_in({"status": {"login": True}}) is True
    assert qr.logged_in({"status": {"login": False}}) is False
    for unknown in (None, {}, {"status": {}}, {"status": None}, {"calls": {}}, "x"):
        assert qr.logged_in(unknown) is None, unknown                                   # chưa có dữ liệu / app không trả lời: CHƯA BIẾT (không làm mờ gì)


def test_login_state_combines_session_and_qr_progress():
    assert qr.login_state(None, {"state": "waiting"}) is None
    assert qr.login_state(True, None) == "logged_in" and qr.login_state(True, {"state": "waiting"}) == "logged_in"      # đã đăng nhập thì luôn là đã đăng nhập
    assert qr.login_state(False, None) == "logged_out" and qr.login_state(False, {"state": "idle"}) == "logged_out"
    assert qr.login_state(False, {"state": "waiting"}) == "waiting_qr" and qr.login_state(False, {"state": "scanned"}) == "scanned"
    assert qr.login_state(False, {"state": "expired"}) == "expired"
    for bad in ("rate_limited", "rejected", "error"):
        assert qr.login_state(False, {"state": bad}) == "error", bad
    assert qr.login_state(False, {"state": "done"}) == "logged_out"                      # QR «xong» sót từ lần trước mà phiên đã mất: chưa đăng nhập
    assert qr.login_state(False, {"state": "la-hoac"}) == "logged_out"
    for code in qr.LOGIN_STATES:
        assert qr.LOGIN_STATE_TEXT[code]                                                 # mỗi trạng thái có lời mô tả tiếng Việt


def test_login_actions_dim_the_buttons_that_do_not_apply():
    assert qr.login_actions(True) == {"login": False, "logout": True}                    # đã đăng nhập: ẩn (mờ) đăng nhập, chỉ còn đăng xuất
    assert qr.login_actions(False) == {"login": True, "logout": False}                   # chưa đăng nhập: ẩn (mờ) đăng xuất, chỉ còn đăng nhập
    assert qr.login_actions(None) == {"login": True, "logout": True}                     # chưa biết: cả hai sáng, không chặn người dùng


def test_wiring_availability_status_sensor_and_service_guard():
    bt = open(os.path.join(CC, "button.py"), encoding="utf-8").read()
    assert "def available(self) -> bool:" in bt and "qr_login.login_actions(qr_login.logged_in(self._rt.coordinator.data))" in bt
    assert 'self._key in ("login_web", "login_pc", "logout")' in bt and "coordinator.async_add_listener(self.async_write_ha_state)" in bt
    im = open(os.path.join(CC, "image.py"), encoding="utf-8").read()
    assert 'qr_login.login_actions(qr_login.logged_in(self._rt.coordinator.data))["login"]' in im
    se = open(os.path.join(CC, "sensor.py"), encoding="utf-8").read()
    assert "class ZaloLoginStateSensor" in se and "qr_login.login_state(" in se and "list(qr_login.LOGIN_STATES)" in se and "ZaloLoginStateSensor(coordinator, entry)" in se
    sv = open(os.path.join(CC, "services.py"), encoding="utf-8").read()
    assert 'qr_login.logged_in(rt.coordinator.data) is True and not call.data.get("force")' in sv and 'vol.Optional("force", default=False): cv.boolean' in sv
    init = open(os.path.join(CC, "__init__.py"), encoding="utf-8").read()
    assert 'data["qr"] = await self.api.qr_status()' in init and 'not status.get("login")' in init            # chỉ hỏi QR khi chưa đăng nhập
    y = open(os.path.join(CC, "services.yaml"), encoding="utf-8").read()
    assert "Đăng nhập lại dù đang đăng nhập" in y


def test_coordinator_stays_alive_when_zalo_is_logged_out():
    """Số đo thật: chưa đăng nhập Zalo thì /api/calls trả 401; trước đây cả bộ cập nhật hỏng và mọi cảm biến «không khả dụng» (không báo được «chưa đăng nhập»)."""
    import ast
    src = open(os.path.join(CC, "__init__.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(n for c in tree.body if isinstance(c, ast.ClassDef) and c.name == "ZaloCallCoordinator" for n in c.body if getattr(n, "name", "") == "_async_update_data")
    class ZaloCallError(Exception):
        pass
    class ZaloCallAuthError(ZaloCallError):
        pass
    class UpdateFailed(Exception):
        pass
    class ConfigEntryAuthFailed(Exception):
        pass
    ns = {"ZaloCallError": ZaloCallError, "ZaloCallAuthError": ZaloCallAuthError, "UpdateFailed": UpdateFailed, "ConfigEntryAuthFailed": ConfigEntryAuthFailed}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "x", "exec"), ns)
    upd = ns["_async_update_data"]

    class Policy:
        def __init__(self):
            self.calls = []

        def poll(self, ok):
            self.calls.append(ok)
            return ok

    class Api:
        def __init__(self, status, calls_exc=None):
            self.st, self.calls_exc, self.fetched = status, calls_exc, []

        async def status(self):
            if isinstance(self.st, Exception):
                raise self.st
            return self.st

        async def calls(self):
            self.fetched.append("calls")
            if self.calls_exc:
                raise self.calls_exc
            return {"active": None, "calls": [{"call_id": 1}]}

        async def qr_status(self):
            self.fetched.append("qr")
            return {"state": "waiting"}

    def run(status, **kw):
        async def _push():
            return None
        me = types.SimpleNamespace(api=Api(status, **kw), bridge=types.SimpleNamespace(policy=Policy(), async_push_defaults=_push), hass=types.SimpleNamespace(async_create_task=lambda c: c.close()))
        try:
            return me, asyncio.run(upd(me)), None
        except Exception as e:  # noqa: BLE001
            return me, None, e
    me, data, err = run({"login": True})
    assert err is None and data["calls"]["calls"] == [{"call_id": 1}] and "qr" not in data and me.api.fetched == ["calls"], (data, err, me.api.fetched)     # đã đăng nhập: như cũ
    me, data, err = run({"login": False}, calls_exc=ZaloCallError("chua_dang_nhap"))
    assert err is None, err                                                                                       # chưa đăng nhập: KHÔNG hỏng dù /api/calls sẽ trả 401
    assert data["status"]["login"] is False and data["calls"] == {"active": None, "calls": []} and data["qr"] == {"state": "waiting"}, data
    assert me.api.fetched == ["qr"] and me.bridge.policy.calls == [False], (me.api.fetched, me.bridge.policy.calls)    # không gọi /api/calls; cầu nối «chưa sẵn sàng» để đẩy lại mặc định khi đăng nhập xong
    me, data, err = run(ZaloCallError("mạng đứt"))
    assert isinstance(err, UpdateFailed) and me.bridge.policy.calls == [False]                                   # app không trả lời vẫn là lỗi thật
    me, data, err = run(ZaloCallAuthError("sai mật khẩu app"))
    assert isinstance(err, ConfigEntryAuthFailed)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, str(e)[:300])
    print("ALL QR LOGIN TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
