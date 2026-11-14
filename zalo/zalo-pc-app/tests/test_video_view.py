"""GET /api/call/video/view: hình điện thoại (khung H.264 từ transport) -> ffmpeg -> MJPEG cho trình duyệt; dọn sạch khi ngắt."""
import json
import os
import queue
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import server as S  # noqa: E402


class FakeTransport:
    def __init__(self):
        self.q = queue.Queue()
        self.removed = 0
        self.q.put((b"\x00\x00\x00\x01\x67annexb", True))

    def add_video_tap(self, maxsize=90):
        return self.q

    def remove_video_tap(self, q):
        self.removed += 1


class FakeProc:
    def __init__(self, chunks):
        self.chunks, self.written, self.killed = list(chunks), [], False
        outer = self

        class In:
            def write(self, b): outer.written.append(bytes(b))
            def close(self): pass
        class Out:
            def read(self, n):
                return outer.chunks.pop(0) if outer.chunks else b""
        self.stdin, self.stdout = In(), Out()

    def poll(self): return 0 if self.killed else None
    def kill(self): self.killed = True
    def wait(self, timeout=None): return 0


def _serve():
    tmp = tempfile.mkdtemp(prefix="zalo-view-")
    os.environ["ZALO_PC_DATA_DIR"] = tmp
    S.STATE = S.AppState(tmp)
    S.STATE.session = {"uid": "1", "zpw_sek": "x", "status": "da_dang_nhap", "client": "web"}      # đã đăng nhập Zalo
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=8) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()


LOGS = []


def _patched(transport, proc, which="/usr/bin/ffmpeg"):
    LOGS.clear()
    S._log_call = LOGS.append
    saved = (S._transport_for_call, S.subprocess.Popen, S.shutil.which, S.STATE.require_login if hasattr(S.STATE, "require_login") else None)
    S._transport_for_call = lambda cid: transport
    S.subprocess.Popen = lambda *a, **k: proc
    S.shutil.which = lambda n: which
    return saved


def _restore(saved):
    S._transport_for_call, S.subprocess.Popen, S.shutil.which = saved[0], saved[1], saved[2]


def test_streams_mjpeg_from_ffmpeg_and_cleans_up():
    httpd, base = _serve()
    tr, proc = FakeTransport(), FakeProc([b"--frame\r\nJPEGA", b"JPEGB\r\n"])
    saved = _patched(tr, proc)
    try:
        st, ct, body = _get(base, "/api/call/video/view?call_id=111")
        assert st == 200 and ct == "multipart/x-mixed-replace;boundary=frame", (st, ct)
        assert body == b"--frame\r\nJPEGAJPEGB\r\n"
        assert tr.removed == 1 and proc.killed is True                     # dọn người xem + ffmpeg
        assert S.VIDEO_VIEW_COUNT[0] == 0
        assert proc.written and proc.written[0].startswith(b"\x00\x00\x00\x01")   # khung khoá đã được bơm vào ffmpeg
        assert any("video-view start call_id=111" in l for l in LOGS), LOGS
        end = [l for l in LOGS if "video-view end call_id=111" in l]
        assert end and "khung_vao=1" in end[0] and "khung_khoa=1" in end[0] and "anh_ra=1" in end[0] and "byte_ra=21" in end[0], end   # nhật ký đo từng chặng
    finally:
        _restore(saved)
        httpd.shutdown()


def test_errors_no_transport_no_ffmpeg_and_too_many_viewers():
    httpd, base = _serve()
    try:
        saved = _patched(None, FakeProc([]))
        try:
            assert _get(base, "/api/call/video/view?call_id=111")[0] == 409
        finally:
            _restore(saved)
        saved = _patched(FakeTransport(), FakeProc([]), which=None)
        try:
            assert _get(base, "/api/call/video/view?call_id=111")[0] == 503
        finally:
            _restore(saved)
        saved = _patched(FakeTransport(), FakeProc([b"x"]))
        S.VIDEO_VIEW_COUNT[0] = S.VIDEO_VIEWERS_MAX
        try:
            assert _get(base, "/api/call/video/view?call_id=111")[0] == 429
        finally:
            S.VIDEO_VIEW_COUNT[0] = 0
            _restore(saved)
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VIDEO VIEW TESTS PASSED")
