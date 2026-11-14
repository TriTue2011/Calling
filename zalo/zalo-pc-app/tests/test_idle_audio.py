"""Không có mic: vẫn gửi tiếng IM LẶNG để luồng RTP liên tục (14/11/2026).
Số đo thật: mọi cuộc gọi không có mic đều rtp_tx=0 và máy tính báo «Kết nối của BenBap không ổn định»; cuộc gọi có mic gửi >1000 gói.
Run: python3 tests/test_idle_audio.py"""
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
tmp = tempfile.mkdtemp(prefix="zalo-pc-idle-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_PORT"] = "0"
os.environ["ZALO_PC_APP_USER"] = "nguoi-dung-test"
os.environ["ZALO_PC_APP_PASSWORD"] = "mat-khau-test-123"
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)
from zalo_pc_app import audio_tx, media_endpoints  # noqa: E402
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
    def poll(self): return None
    def kill(self): pass


def test_silence_source_and_idle_flag():
    args = audio_tx.build_ffmpeg_args("silence")
    assert "anullsrc=r=16000:cl=mono" in args and "-re" in args and args[-1] == "pipe:1", args
    s = audio_tx.AudioSender(lambda f: None, source="silence", popen=lambda *a, **k: Proc())
    assert s.idle is True and s.status()["idle"] is True
    real = audio_tx.AudioSender(lambda f: None, source="test", popen=lambda *a, **k: Proc())
    assert real.idle is False and real.status()["idle"] is False


def test_idle_audio_keeps_stream_alive_is_not_reported_as_mic_and_real_mic_replaces_it():
    global BASE
    st = sv.AppState(tmp)
    sv.STATE = st
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    assert api("/api/app/login", {"username": "nguoi-dung-test", "password": "mat-khau-test-123"})[0] == 200
    st.session = {"zpw_sek": "x", "zpw_enk": "k", "device_id": "d", "uid": "1"}
    st.calls.record_start(77, "Peer", "20001", "user")
    st.calls.record_answered(77, "test")
    media_endpoints.ENDPOINTS.active[77] = {"transport": Tr()}
    realcls = sv.audio_tx_mod.AudioSender
    sv.audio_tx_mod.AudioSender = lambda f, source="test", fmt="auto", gate=None, **kw: realcls(f, source=source, fmt=fmt, gate=gate, popen=lambda *a, **k: Proc(), **kw)
    import shutil
    rw = shutil.which
    shutil.which = lambda n: "/usr/bin/" + n
    try:
        s = sv._start_idle_audio(77)
        assert s is not None and s.idle and sv.AUDIO_SENDERS["77"] is s                      # đang gửi tiếng im lặng
        assert sv._start_idle_audio(77) is s                                                  # gọi lại không tạo thêm
        assert sv.mic_status(77) is None                                                      # nhưng KHÔNG tính là mic đang bật
        assert api("/api/call/media", {"action": "status"})[1]["mic"] is None
        assert st.calls.snapshot()["calls"][0].get("media", {}).get("mic", None) is None
        # mic thật bật -> thay bộ gửi im lặng
        s2 = sv._start_mic(77, "test")
        assert sv.AUDIO_SENDERS["77"] is s2 and not s2.idle and sv.mic_status(77) is not None
        # tắt mic từ WebUI/API -> trả mic None nhưng luồng tiếng vẫn được giữ bằng im lặng
        b = api("/api/call/media", {"action": "stop", "target": "mic"})[1]
        assert b["ok"] and b["mic"] is None, b
        assert sv.AUDIO_SENDERS["77"].idle is True                                           # luồng không bị đứt sau khi tắt mic
        b = api("/api/call/media", {"action": "stop", "target": "both"})[1]
        assert b["mic"] is None and sv.AUDIO_SENDERS["77"].idle is True
        # hết cuộc gọi: dọn sạch (không để bộ gửi im lặng sống tiếp)
        sv._cleanup_call_media({"call_id": 77, "thread_id": "20001", "status": "answered"})
        assert "77" not in sv.AUDIO_SENDERS
        # không có transport (chưa nối/đã hết): không tạo gì
        assert sv._start_idle_audio(999) is None and "999" not in sv.AUDIO_SENDERS
    finally:
        shutil.which = rw
        sv.audio_tx_mod.AudioSender = realcls
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
    print("ALL IDLE AUDIO TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
