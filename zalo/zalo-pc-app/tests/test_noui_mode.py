"""Bản KHÔNG giao diện: đường UI trả «không có giao diện», API vẫn chạy; bản có UI không đổi (14/11/2026).
Run: python3 tests/test_noui_mode.py"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
tmp = tempfile.mkdtemp(prefix="zalo-pc-noui-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_PORT"] = "0"
os.environ["ZALO_PC_APP_USER"] = "nguoi-dung-test"
os.environ["ZALO_PC_APP_PASSWORD"] = "mat-khau-test-123"
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)
from zalo_pc_app import server as sv  # noqa: E402


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def get(base, path, cookie=""):
    req = urllib.request.Request(base + path)
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=10) as r:
            return r.status, r.headers.get("Content-Type") or "", r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type") or "", e.read().decode("utf-8", "replace")


def test_ui_enabled_rules():
    with tempfile.TemporaryDirectory() as d:
        assert sv._ui_enabled({}, d) is False                                   # không có static/zalo/index.html (image :noui xóa thư mục static) → không UI
        os.makedirs(os.path.join(d, "zalo"))
        open(os.path.join(d, "zalo", "index.html"), "w").write("<html>")
        assert sv._ui_enabled({}, d) is True and sv._ui_enabled({"ZALO_PC_UI": ""}, d) is True       # biến rỗng (compose) = mặc định
        for off in ("0", "false", "No", "OFF", " 0 "):
            assert sv._ui_enabled({"ZALO_PC_UI": off}, d) is False, off         # tắt UI trên bản có giao diện
        assert sv._ui_enabled({"ZALO_PC_UI": "1"}, d) is True
    assert sv.UI_ENABLED is True                                                   # cây mã nguồn này có WebUI


def test_noui_routes_and_api_still_works():
    st = sv.AppState(tmp)
    sv.STATE = st
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    saved = sv.UI_ENABLED
    try:
        sv.UI_ENABLED = True                                                       # bản có UI: như cũ
        s, ct, body = get(base, "/login")
        assert s == 200 and "text/html" in ct, (s, ct)
        sv.UI_ENABLED = False                                                      # bản KHÔNG UI
        s, ct, body = get(base, "/")
        info = json.loads(body)
        assert s == 200 and info["ui"] is False and info["status"] == "/api/app/status" and "get_app_settings" in info["message"], (s, body)
        for path in ("/login", "/classic", "/call", "/app.js", "/style.css", "/ui/app.css", "/ui/app.js", "/ui/call.js", "/fonts/x.woff2"):
            s, ct, body = get(base, path)
            assert s == 404 and json.loads(body) == {"error": "khong_co_giao_dien", "ui": False}, (path, s, body)      # không đọc tệp tĩnh nào
        s, _, body = get(base, "/api/app/status")                                  # API công khai vẫn sống (cũng là healthcheck)
        assert s == 200 and json.loads(body)["logged_in"] is False
        req = urllib.request.Request(base + "/api/app/login", method="POST", data=json.dumps({"username": "nguoi-dung-test", "password": "mat-khau-test-123"}).encode())
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as r:
            cookie = r.headers.get("Set-Cookie").split(";", 1)[0]                  # đăng nhập app qua API (curl) vẫn chạy
        s, _, body = get(base, "/api/app/status", cookie)
        assert json.loads(body)["logged_in"] is True
        s, _, body = get(base, "/api/status", cookie)
        assert s == 200 and json.loads(body)["ui"] is False                        # /api/status báo không có UI
        sv.UI_ENABLED = True
        s, _, body = get(base, "/api/status", cookie)
        assert json.loads(body)["ui"] is True
    finally:
        sv.UI_ENABLED = saved
        httpd.shutdown()


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
    print("ALL NOUI MODE TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
