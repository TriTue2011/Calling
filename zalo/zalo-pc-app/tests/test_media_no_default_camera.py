"""Không còn camera mặc định: nút Camera/«nâng lên video» không tự gửi «hình thử» (vạch màu) sang điện thoại nữa (14/11/2026).
Số đo thật: điện thoại hiện đúng vạch màu testsrc có đồng hồ 00:00:36 khi bấm Camera trên WebUI mà chưa có camera nào.
Run: python3 tests/test_media_no_default_camera.py"""
import io
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
tmp = tempfile.mkdtemp(prefix="zalo-pc-nocam-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_PORT"] = "0"
os.environ["ZALO_PC_APP_USER"] = "nguoi-dung-test"
os.environ["ZALO_PC_APP_PASSWORD"] = "mat-khau-test-123"
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)
from zalo_pc_app import media_endpoints  # noqa: E402
from zalo_pc_app import server as sv  # noqa: E402

BASE, _COOKIE = "", ""


def api(path, body):
    global _COOKIE
    req = urllib.request.Request(BASE + path, method="POST", data=json.dumps(body).encode())
    req.add_header("Content-Type", "application/json")
    if _COOKIE:
        req.add_header("Cookie", _COOKIE)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            sc = r.headers.get("Set-Cookie") or ""
            if sc.startswith("zalo_pc_app="):
                _COOKIE = sc.split(";", 1)[0]
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class Tr:
    def send_pcm(self, p): pass
    def send_video_frame(self, au, key): return True


class Proc:
    def __init__(self): self.stdout = io.BytesIO(b"")
    def poll(self): return 0
    def kill(self): pass


def test_no_camera_means_error_not_a_test_pattern():
    global BASE
    st = sv.AppState(tmp)
    sv.STATE = st
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    assert api("/api/app/login", {"username": "nguoi-dung-test", "password": "mat-khau-test-123"})[0] == 200
    st.session = {"zpw_sek": "x", "zpw_enk": "k", "device_id": "d", "uid": "1"}
    st.calls.record_start(66, "Peer", "20001", "user")
    st.calls.record_answered(66, "test")
    media_endpoints.ENDPOINTS.active[66] = {"transport": Tr()}
    started = []
    real = sv.video_tx_mod.VideoSender
    sv.video_tx_mod.VideoSender = lambda f, source="test", **kw: (started.append(source), real(f, source=source, popen=lambda *a, **k: Proc(), **kw))[1]
    sv._send_a2v_async = lambda *a: None
    sv.video_calls._send_camera_state_async = lambda *a: None
    sv.ffmpeg_ok = True
    import shutil
    rw = shutil.which
    shutil.which = lambda n: "/usr/bin/" + n
    try:
        assert st.devices.get()["camera_url"] == ""                                    # không có camera mặc định
        s, b = api("/api/call/media", {"action": "start", "target": "video"})
        assert b["ok"] is False and b["error"] == "chua_co_camera" and started == [], (b, started)     # trước đây: tự gửi «test»
        s, b = api("/api/call/video", {"action": "start"})
        assert b["ok"] is False and b["error"] == "chua_co_camera" and started == [], (b, started)
        s, b = api("/api/call/upgrade_video", {})
        assert b["ok"] is False and b["error"] == "chua_co_camera" and started == [], (b, started)
        s, b = api("/api/call/media", {"action": "start", "target": "both"})
        assert b["ok"] is True and b["video"] is None and started == [], (b, started)    # «cả hai» không camera: chỉ mic/loa nếu có, KHÔNG bật hình thử
        s, b = api("/api/call/media", {"action": "start", "target": "video", "camera_url": "rtsp://cam.local/s"})
        assert b["ok"] is True and started == ["rtsp://cam.local/s"], (b, started)       # có camera thật: chạy bình thường
        api("/api/call/media", {"action": "stop", "target": "video"})
        s, b = api("/api/call/media", {"action": "start", "target": "video", "source": "test"})
        assert b["ok"] is True and started[-1] == "test", (b, started)                    # «test» chỉ chạy khi được gọi tường minh (kiểm thử)
    finally:
        shutil.which = rw
        sv.video_tx_mod.VideoSender = real
        httpd.shutdown()


if __name__ == "__main__":
    try:
        test_no_camera_means_error_not_a_test_pattern()
        print("PASS test_no_camera_means_error_not_a_test_pattern")
        print("ALL NO DEFAULT CAMERA TESTS PASSED")
    except Exception as e:  # noqa: BLE001
        print("FAIL", type(e).__name__, str(e)[:400])
        sys.exit(1)
