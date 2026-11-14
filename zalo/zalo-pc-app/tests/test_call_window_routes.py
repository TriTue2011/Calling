"""Trang /call (cửa sổ cuộc gọi tách rời): cần đăng nhập app; CSS công khai như app.css; JS cần đăng nhập (14/11/2026).
Run: python3 tests/test_call_window_routes.py"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
tmp = tempfile.mkdtemp(prefix="zalo-pc-callwin-")
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
            return r.status, r.headers.get("Content-Type"), r.read().decode("utf-8", "replace"), r.headers.get("Location")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read().decode("utf-8", "replace"), e.headers.get("Location")


def test_call_window_routes_and_static_files():
    st = sv.AppState(tmp)
    sv.STATE = st
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        s, _, _, loc = get(base, "/call")
        assert s in (301, 302, 303) and loc == "/login", (s, loc)                              # chưa đăng nhập app: về /login
        s, ct, body, _ = get(base, "/ui/call.css")
        assert s == 200 and "text/css" in ct and ".cw-panel" in body and "@media (min-aspect-ratio" in body                      # CSS công khai như app.css, có luật xếp lại theo cỡ cửa sổ
        s, _, _, _ = get(base, "/ui/call.js")
        assert s == 401, s                                                                     # JS cần đăng nhập
        req = urllib.request.Request(base + "/api/app/login", method="POST", data=json.dumps({"username": "nguoi-dung-test", "password": "mat-khau-test-123"}).encode())
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as r:
            cookie = r.headers.get("Set-Cookie").split(";", 1)[0]
        s, ct, body, _ = get(base, "/call", cookie)
        assert s == 200 and "text/html" in ct and 'id="cw-vbox"' in body and "/ui/call.js" in body and "/ui/call.css" in body, (s, ct)
        assert 'name="referrer" content="no-referrer"' in body                                  # kho video Zalo từ chối khi có Referer
        s, ct, body, _ = get(base, "/ui/call.js", cookie)
        assert s == 200 and "javascript" in ct and "api/call/video/snapshot" in body and "__CALL_TEST_HOOK__" in body, (s, ct)
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    try:
        test_call_window_routes_and_static_files()
        print("PASS test_call_window_routes_and_static_files")
        print("ALL CALL WINDOW ROUTE TESTS PASSED")
    except Exception as e:  # noqa: BLE001
        print("FAIL", type(e).__name__, str(e)[:400])
        sys.exit(1)
