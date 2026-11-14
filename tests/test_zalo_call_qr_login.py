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
