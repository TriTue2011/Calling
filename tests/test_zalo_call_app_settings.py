"""Đọc/ghi mọi cài đặt của app + đổi mật khẩu app + gửi thử webhook từ HA (14/11/2026) — để sau này chạy bản KHÔNG WebUI mà vẫn cấu hình từ HA.
Chạy được không cần Home Assistant. Run: python3 tests/test_zalo_call_app_settings.py"""
import ast
import asyncio
import importlib.util
import os
import sys
import types

CC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_components", "zalo_call")


def load(name):
    spec = importlib.util.spec_from_file_location("zc2_" + name, os.path.join(CC, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["zc2_" + name] = m
    spec.loader.exec_module(m)
    return m


A = load("app_settings")


def test_mask_url_hides_password_query_secret_and_webhook_id():
    assert A.mask_url("http://u:Bi%40Mat@10.0.0.5:8554/cam") == "http://u:***@10.0.0.5:8554/cam"
    assert A.mask_url("http://ha:8123/api/r1_speaker/intercom/E1?k=KHOA123&x=1") == "http://ha:8123/api/r1_speaker/intercom/E1?k=***&x=1"
    assert A.mask_url("http://ha:8123/api/webhook/4a39560d994b7ed99096") == "http://ha:8123/api/webhook/***"
    assert A.mask_url("https://x/y?token=abc&secret=zzz") == "https://x/y?token=***&secret=***"
    assert A.mask_url("") == "" and A.mask_url(None) == "" and A.mask_url("http://host/plain") == "http://host/plain"


def test_mask_webhooks_masks_only_urls_unless_revealed():
    cfg = {"message_webhook_url": "http://ha/api/webhook/SECRET", "message_enabled": True, "call_webhook_url": "", "n": 3}
    m = A.mask_webhooks(cfg)
    assert m["message_webhook_url"] == "http://ha/api/webhook/***" and m["message_enabled"] is True and m["n"] == 3 and m["call_webhook_url"] == ""
    assert A.mask_webhooks(cfg, reveal=True)["message_webhook_url"].endswith("SECRET")
    assert A.mask_webhooks(None) == {} and A.mask_webhooks("x") == {}


def test_connection_never_shows_password_by_default():
    c = A.mask_connection("http://app:8090", "admin", "MatKhau!", False)
    assert c["password"] == "***" and "MatKhau" not in str(c) and c["password_revealed"] is False and c["username"] == "admin"
    assert A.mask_connection("http://app:8090", "admin", "MatKhau!", True)["password"] == "MatKhau!"
    assert A.mask_connection("http://app", "u", "", False)["password"] == ""


def test_snapshot_keeps_going_when_one_section_fails_and_masks_the_rest():
    raw = {"webhooks": {"message_webhook_url": "http://ha/api/webhook/S"}, "retention": RuntimeError("chua_dang_nhap"),
           "proxy": {"items": [{"url": "http://a:pw@h:8080", "name": "p"}], "active_url": "http://a:pw@h:8080"}, "devices": {"ok": True}}
    snap = A.build_snapshot(raw, {"url": "x"}, False)
    assert snap["webhooks"]["message_webhook_url"].endswith("***") and snap["retention"] == {"error": "chua_dang_nhap"}
    assert snap["proxy"]["items"][0]["url"] == "http://a:***@h:8080" and snap["proxy"]["active_url"] == "http://a:***@h:8080" and snap["devices"] == {"ok": True} and snap["connection"] == {"url": "x"}
    assert A.build_snapshot({"proxy": raw["proxy"]}, {}, True)["proxy"]["active_url"] == "http://a:pw@h:8080"      # reveal: giữ nguyên


def test_sections_and_write_validation():
    assert A.normalize_sections(None) == list(A.READ_SECTIONS) and A.normalize_sections([]) == list(A.READ_SECTIONS)
    assert A.normalize_sections("webhooks") == ["webhooks"] and A.normalize_sections(["proxy", "app", "proxy"]) == ["proxy", "app"]
    for bad in (["webhooks", "mat_khau"], "xyz"):
        try:
            A.normalize_sections(bad)
        except ValueError as e:
            assert "Chỉ gồm" in str(e)
            continue
        raise AssertionError(bad)
    assert A.check_write("webhooks", {"a": 1}) == ("webhooks", {"a": 1})
    for sec, val in (("app", {"a": 1}), ("history_sync", {"a": 1}), ("webhooks", {}), ("webhooks", None), ("webhooks", [1]), (None, {"a": 1})):
        try:
            A.check_write(sec, val)
        except ValueError:
            continue
        raise AssertionError((sec, val))
    assert A.check_password_change("cu", "moi") == ("cu", "moi")
    for o, n in (("", "x"), ("x", ""), ("x", "x"), (None, None)):
        try:
            A.check_password_change(o, n)
        except ValueError:
            continue
        raise AssertionError((o, n))
    assert "Mật khẩu cũ" in A.password_error_text("sai_mat_khau_cu") and "ZALO_PC_APP_PASSWORD_HASH" in A.password_error_text("managed_by_env")
    assert "ky_la" in A.password_error_text("ky_la") and "lỗi không rõ" in A.password_error_text(None)


class _Resp:
    def __init__(self, d, status=200):
        self._d, self.status = d, status

    async def json(self, content_type=None):
        return self._d

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Session:
    def __init__(self, status=200, data=None):
        self.calls, self._st, self._d = [], status, data if data is not None else {"ok": True}

    def request(self, method, url, **kw):
        self.calls.append((method, url.split("//", 1)[-1].split("/", 1)[-1], kw.get("json")))
        return _Resp(self._d, self._st)


def test_api_client_routes_for_settings_and_password():
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        print("SKIP: không có aiohttp")
        return
    api_mod = load("api")
    s = _Session()
    c = api_mod.ZaloCallApi(s, "http://app:8090", "u", "p")

    async def run():
        await c.app_status(); await c.retention_get(); await c.retention_set({"keep_days": 30}); await c.proxy_get(); await c.proxy_action({"action": "add", "url": "http://p"})
        await c.security_get(); await c.security_action({"action": "revoke_others"}); await c.history_sync_status(); await c.webhook_test("message")
        await c.change_app_password("cu", "moi")
    asyncio.run(run())
    assert s.calls == [("GET", "api/app/status", None), ("GET", "api/retention", None), ("POST", "api/retention", {"keep_days": 30}), ("GET", "api/proxy", None),
                       ("POST", "api/proxy", {"action": "add", "url": "http://p"}), ("GET", "api/security", None), ("POST", "api/security", {"action": "revoke_others"}),
                       ("GET", "api/history-sync/status", None), ("POST", "api/webhooks/test", {"kind": "message"}),
                       ("POST", "api/app/password", {"old_password": "cu", "new_password": "moi"})], s.calls
    assert c._pw == "moi"                                                                                     # đổi thành công: phiên dùng mật khẩu mới
    bad = _Session(403, {"ok": False, "error": "sai_mat_khau_cu"})
    c2 = api_mod.ZaloCallApi(bad, "http://app:8090", "u", "p")
    try:
        asyncio.run(c2.change_app_password("sai", "moi"))
    except api_mod.ZaloCallError as e:
        assert str(e) == "sai_mat_khau_cu" and e.status == 403
    else:
        raise AssertionError("phải lỗi")
    assert c2._pw == "p"                                                                                     # đổi THẤT BẠI: giữ mật khẩu cũ


def _services():
    """Nạp NGUYÊN VĂN các hàm dịch vụ lồng trong async_register_services (với bản giả của HA) để kiểm hành vi thật."""
    tree = ast.parse(open(os.path.join(CC, "services.py"), encoding="utf-8").read())
    outer = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_register_services")
    want = {"_entry_and_api", "get_app_settings", "set_app_settings", "set_app_password", "test_webhook"}
    fns = [n for n in outer.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in want]
    assert {f.name for f in fns} == want, [f.name for f in fns]

    class ZaloCallError(Exception):
        pass

    class VErr(Exception):
        pass

    class HErr(Exception):
        pass
    rt_api = types.SimpleNamespace()
    ns = {"app_settings": A, "ZaloCallError": ZaloCallError, "ServiceValidationError": VErr, "HomeAssistantError": HErr, "DOMAIN": "zalo_call", "Any": object, "ServiceCall": object}
    entries = {}
    hass = types.SimpleNamespace(data={"zalo_call": {"e1": types.SimpleNamespace(api=rt_api, defaults=types.SimpleNamespace(get=lambda k: {"auto_mic": True, "ha_url": "http://ha"}.get(k)))}},
                                 config_entries=types.SimpleNamespace(async_get_entry=lambda eid: entries.get(eid), async_update_entry=lambda e, data=None: entries.__setitem__("updated", data)))
    ns["hass"] = hass
    exec(compile(ast.Module(body=fns, type_ignores=[]), "services_sub", "exec"), ns)
    entries["e1"] = types.SimpleNamespace(data={"url": "http://app:8090", "username": "admin", "password": "MatKhauHA"})
    return ns, rt_api, entries, ZaloCallError, VErr, HErr


class _Call:
    def __init__(self, **d):
        self.data = d


def test_get_app_settings_service_masks_secrets_and_tolerates_a_failing_section():
    ns, api, entries, ZErr, VErr, HErr = _services()

    async def ok(v):
        return v

    def f(v):
        async def g():
            if isinstance(v, Exception):
                raise v
            return v
        return g
    api.app_status = f({"logged_in": True, "username": "admin", "can_change_password": True})
    api.get_webhooks = f({"message_webhook_url": "http://ha/api/webhook/SECRET", "message_enabled": True})
    api.devices_get = f({"ok": True, "devices": {"camera_url": "rtsp://u:***@h/s"}})
    api.retention_get = f(ZErr("chua_dang_nhap"))
    api.proxy_get = f({"items": []})
    api.security_get = f({"sessions": 1})
    api.history_sync_status = f({"state": "idle"})
    res = asyncio.run(ns["get_app_settings"](_Call()))
    assert set(res) >= {"connection", "app", "webhooks", "devices", "retention", "proxy", "security", "history_sync", "ha"}, set(res)
    assert res["webhooks"]["message_webhook_url"] == "http://ha/api/webhook/***" and res["connection"]["password"] == "***" and "MatKhauHA" not in str(res)
    assert res["retention"] == {"error": "chua_dang_nhap"} and res["app"]["logged_in"] is True and res["ha"]["auto_mic"] is True
    rv = asyncio.run(ns["get_app_settings"](_Call(sections=["webhooks"], reveal_secrets=True)))
    assert set(rv) == {"connection", "webhooks", "ha"} and rv["webhooks"]["message_webhook_url"].endswith("SECRET") and rv["connection"]["password"] == "MatKhauHA", rv
    try:
        asyncio.run(ns["get_app_settings"](_Call(sections=["mat_khau"])))
    except VErr:
        pass
    else:
        raise AssertionError("mục lạ phải bị từ chối")
    try:
        asyncio.run(ns["get_app_settings"](_Call(entry_id="khong-co")))
    except VErr:
        pass
    else:
        raise AssertionError("không có tích hợp phải báo lỗi")


def test_set_app_settings_service_routes_each_section_and_masks_results():
    ns, api, entries, ZErr, VErr, HErr = _services()
    sent = []

    def rec(name, ret):
        async def g(v):
            sent.append((name, v))
            if isinstance(ret, Exception):
                raise ret
            return ret
        return g
    api.set_webhooks = rec("webhooks", {"ok": True, "config": {"message_webhook_url": "http://ha/api/webhook/SECRET", "message_enabled": True}})
    api.devices_set = rec("devices", {"ok": True})
    api.retention_set = rec("retention", {"ok": True})
    api.proxy_action = rec("proxy", {"items": [{"url": "http://a:pw@h:1"}], "active_url": ""})
    api.security_action = rec("security", {"ok": True, "revoked": 2})
    r = asyncio.run(ns["set_app_settings"](_Call(section="webhooks", values={"message_enabled": True})))
    assert r["ok"] and r["section"] == "webhooks" and r["result"]["config"]["message_webhook_url"].endswith("***"), r         # phản hồi không lộ mã webhook
    asyncio.run(ns["set_app_settings"](_Call(section="devices", values={"echo_guard": True})))
    asyncio.run(ns["set_app_settings"](_Call(section="retention", values={"keep_days": 30})))
    r = asyncio.run(ns["set_app_settings"](_Call(section="proxy", values={"action": "add", "url": "http://a:pw@h:1"})))
    assert r["result"]["items"][0]["url"] == "http://a:***@h:1", r
    r = asyncio.run(ns["set_app_settings"](_Call(section="security", values={"action": "revoke_others"})))
    assert r["result"]["revoked"] == 2
    assert [s[0] for s in sent] == ["webhooks", "devices", "retention", "proxy", "security"] and sent[0][1] == {"message_enabled": True}, sent
    for sec, val in (("app", {"a": 1}), ("webhooks", {}), ("webhooks", None)):
        try:
            asyncio.run(ns["set_app_settings"](_Call(section=sec, values=val)))
        except VErr:
            continue
        raise AssertionError((sec, val))
    api.set_webhooks = rec("webhooks", ZErr("khong hop le: url"))
    try:
        asyncio.run(ns["set_app_settings"](_Call(section="webhooks", values={"x": 1})))
    except HErr as e:
        assert "khong hop le" in str(e)
    else:
        raise AssertionError("lỗi của app phải thành lỗi HA rõ ràng")


def test_set_app_password_updates_ha_entry_only_on_success_and_explains_errors():
    ns, api, entries, ZErr, VErr, HErr = _services()

    async def ok(old, new):
        assert (old, new) == ("cu", "moi")
        return {"ok": True, "other_sessions_revoked": 3}
    api.change_app_password = ok
    r = asyncio.run(ns["set_app_password"](_Call(old_password="cu", new_password="moi")))
    assert r == {"ok": True, "other_sessions_revoked": 3}
    assert entries["updated"] == {"url": "http://app:8090", "username": "admin", "password": "moi"}, entries.get("updated")     # HA nhớ mật khẩu mới
    entries.pop("updated")

    async def fail(old, new):
        raise ZErr("sai_mat_khau_cu")
    api.change_app_password = fail
    try:
        asyncio.run(ns["set_app_password"](_Call(old_password="sai", new_password="moi")))
    except HErr as e:
        assert "Mật khẩu cũ không đúng" in str(e)
    else:
        raise AssertionError("phải lỗi")
    assert "updated" not in entries                                                                          # đổi thất bại: KHÔNG ghi mật khẩu mới vào HA
    for o, n in (("x", "x"), ("", "y")):
        try:
            asyncio.run(ns["set_app_password"](_Call(old_password=o, new_password=n)))
        except VErr:
            continue
        raise AssertionError((o, n))


def test_test_webhook_service_and_wiring():
    ns, api, entries, ZErr, VErr, HErr = _services()

    async def wt(kind):
        return {"ok": True, "kind": kind, "status": 200}
    api.webhook_test = wt
    assert asyncio.run(ns["test_webhook"](_Call(kind="call")))["result"]["kind"] == "call"
    sv = open(os.path.join(CC, "services.py"), encoding="utf-8").read()
    for name in ("get_app_settings", "set_app_settings", "set_app_password", "test_webhook"):
        assert 'DOMAIN, "%s", %s' % (name, name) in sv, name
    assert 'vol.Required("values"): dict' in sv and 'vol.In(list(app_settings.WRITE_SECTIONS))' in sv
    y = open(os.path.join(CC, "services.yaml"), encoding="utf-8").read()
    for name in ("get_app_settings", "set_app_settings", "set_app_password", "test_webhook"):
        assert "\n%s:\n" % name in y, name
    assert "type: password" in y


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
    print("ALL APP SETTINGS TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
