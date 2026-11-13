"""Mã PIN riêng tư: đơn vị (PrivacyGate) + đầu-cuối qua HTTP (chặn mặc định, danh sách cho phép, giới hạn đoán sai, tự khoá).
Chạy: python3 tests/test_privacy_gate.py"""
import http.client
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

TEST_USER, TEST_PASSWORD, PIN = "nguoi-dung-test", "mat-khau-test-123", "4821"
tmp = tempfile.mkdtemp(prefix="zalo-pc-privacy-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_APP_USER"] = TEST_USER
os.environ["ZALO_PC_APP_PASSWORD"] = TEST_PASSWORD
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)
for k in ("ZALO_PC_APP_PIN", "ZALO_PC_APP_PIN_HASH", "ZALO_PC_APP_PIN_MINUTES"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import privacy  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def test_from_env_disabled_by_default_and_validates_format():
    assert privacy.PrivacyGate.from_env({}).enabled is False
    assert privacy.PrivacyGate.from_env({"ZALO_PC_APP_PIN": PIN}).enabled is True
    for bad in ({"ZALO_PC_APP_PIN": "123"}, {"ZALO_PC_APP_PIN": "x" * 33}, {"ZALO_PC_APP_PIN_HASH": "sha256:abc"}):
        try:
            privacy.PrivacyGate.from_env(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)                                              # cấu hình sai: nổ lúc khởi động, không âm thầm tắt
    from zalo_pc_app import app_auth
    assert privacy.PrivacyGate.from_env({"ZALO_PC_APP_PIN_HASH": app_auth.hash_password(PIN)}).enabled is True
    g = privacy.PrivacyGate.from_env({"ZALO_PC_APP_PIN": PIN})
    assert g.status("tok") == {"enabled": True, "unlocked": False, "seconds_left": 0}
    assert privacy.PrivacyGate.from_env({}).status("tok")["unlocked"] is True        # tắt: coi như luôn mở (WebUI không hiện khoá)


def test_unlock_lock_idle_timeout_and_brute_force_limit():
    clock = Clock()
    g = privacy.PrivacyGate.from_env({"ZALO_PC_APP_PIN": PIN, "ZALO_PC_APP_PIN_MINUTES": "2"})
    g._clock = clock
    assert g.is_unlocked("tok") is False
    assert g.unlock("tok", "0000", "1.1.1.1") == (False, "sai_pin")
    assert g.unlock("tok", None, "1.1.1.1") == (False, "sai_pin") and g.unlock("", PIN, "1.1.1.1") == (False, "sai_pin")
    assert g.unlock("tok", PIN, "1.1.1.1") == (True, "")
    assert g.is_unlocked("tok") and not g.is_unlocked("tok-khac")                    # mở khoá theo TỪNG phiên
    clock.t += 100
    assert g.is_unlocked("tok")                                                      # dùng thì được gia hạn (đang là +100/120 s)
    clock.t += 100
    assert g.is_unlocked("tok")                                                      # nhờ gia hạn lần trước nên vẫn còn
    clock.t += 121
    assert not g.is_unlocked("tok")                                                  # quá 2 phút KHÔNG dùng: tự khoá lại
    assert g.unlock("tok", PIN, "2.2.2.2")[0] and g.lock("tok") and not g.is_unlocked("tok") and not g.lock("tok")
    for _ in range(5):
        assert g.unlock("tok", "sai", "9.9.9.9")[1] == "sai_pin"
    assert g.unlock("tok", PIN, "9.9.9.9") == (False, "qua_nhieu_lan_sai")            # đúng PIN cũng bị từ chối khi đang bị khoá địa chỉ
    assert g.unlock("tok", PIN, "8.8.8.8")[0]                                          # địa chỉ khác không bị ảnh hưởng


def test_allowed_paths_are_a_short_whitelist_and_cannot_be_bypassed_with_dots():
    ok = ("/", "/login", "/ui/app.js", "/ui/app.css", "/api/status", "/api/calls", "/api/app/status", "/api/privacy/unlock")
    bad = ("/api/conversations", "/api/thread/1/history", "/api/events", "/api/svc/getMessages", "/api/file/download", "/api/inbox/summary", "/api/logout",
           "/api/contacts", "/classic", "/api/status/../conversations", "//api/conversations", "/ui/../api/conversations", "/api/call/say")
    for p in ok:
        assert privacy.PrivacyGate.allowed(p), p
    for p in bad:
        assert not privacy.PrivacyGate.allowed(p), p


class Client:
    def __init__(self, port):
        self.port, self.cookie = port, ""

    def req(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        headers = {"Content-Type": "application/json"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        resp = conn.getresponse()
        raw, sc = resp.read(), resp.getheader("Set-Cookie") or ""
        conn.close()
        try:
            parsed = json.loads(raw.decode())
        except Exception:
            parsed = None
        return resp.status, parsed, sc

    def login(self):
        status, _b, sc = self.req("POST", "/api/app/login", {"username": TEST_USER, "password": TEST_PASSWORD})
        assert status == 200 and sc
        self.cookie = sc.split(";", 1)[0]


def _serve(state):
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def test_http_locked_session_gets_423_on_content_routes_but_whitelist_works():
    state = app_server.AppState(tmp)
    state.privacy = privacy.PrivacyGate.from_env({"ZALO_PC_APP_PIN": PIN})
    httpd, port = _serve(state)
    try:
        c = Client(port)
        assert c.req("GET", "/api/privacy/status")[0] == 401                         # chưa đăng nhập app: 401, không lộ gì
        c.login()
        s, b, _ = c.req("GET", "/api/privacy/status")
        assert s == 200 and b == {"enabled": True, "unlocked": False, "seconds_left": 0}, (s, b)
        for method, path in (("GET", "/api/conversations"), ("GET", "/api/contacts"), ("GET", "/api/inbox/summary"), ("GET", "/api/events"),
                             ("GET", "/api/thread/123/history?type=user"), ("GET", "/api/file/list"), ("GET", "/api/svc/catalog"),
                             ("POST", "/api/svc/getMessages"), ("POST", "/api/thread/123/send"), ("POST", "/api/logout"), ("POST", "/api/call/request")):
            s, b, _ = c.req(method, path, {})
            assert s == 423 and b == {"error": "privacy_locked"}, (method, path, s, b)
        for path in ("/api/status", "/api/calls", "/api/app/status"):
            s, b, _ = c.req("GET", path)
            assert s != 423 and b != {"error": "privacy_locked"}, (path, s)             # danh sách cho phép KHÔNG bị khoá (401 do Zalo chưa đăng nhập trong test là chuyện khác)
        s, _b, _ = c.req("POST", "/api/privacy/unlock", {"pin": "0000"})
        assert s == 401
        s, b, _ = c.req("POST", "/api/privacy/unlock", {"pin": PIN})
        assert s == 200 and b["unlocked"] is True and b["seconds_left"] > 0, (s, b)
        s, _b, _ = c.req("GET", "/api/conversations")
        assert s != 423, s                                                             # đã mở khoá: không còn bị chặn (401 do Zalo chưa đăng nhập trong test là chuyện khác)
        other = Client(port)
        other.login()                                                                  # phiên app KHÁC vẫn đang khoá
        assert other.req("GET", "/api/conversations")[0] == 423
        s, b, _ = c.req("POST", "/api/privacy/lock", {})
        assert s == 200 and b["unlocked"] is False
        assert c.req("GET", "/api/conversations")[0] == 423                             # khoá lại bằng tay
    finally:
        httpd.shutdown()


def test_http_without_pin_nothing_changes_and_privacy_routes_report_disabled():
    state = app_server.AppState(tmp)
    assert state.privacy.enabled is False
    httpd, port = _serve(state)
    try:
        c = Client(port)
        c.login()
        s, b, _ = c.req("GET", "/api/privacy/status")
        assert s == 200 and b["enabled"] is False and b["unlocked"] is True, (s, b)
        for path in ("/api/conversations", "/api/contacts", "/api/inbox/summary"):
            assert c.req("GET", path)[0] != 423, path                                  # tắt PIN: không bao giờ 423
        s, b, _ = c.req("POST", "/api/privacy/unlock", {"pin": PIN})
        assert s == 400 and b == {"error": "chua_bat"}
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL PRIVACY-GATE TESTS PASSED")
