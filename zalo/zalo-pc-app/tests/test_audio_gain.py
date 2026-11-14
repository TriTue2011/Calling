"""Tang/giam am luong MIC va LOA giua cuoc goi bang phan mem (14/11/2026).
Run: python3 tests/test_audio_gain.py"""
import io
import json
import os
import struct
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
tmp = tempfile.mkdtemp(prefix="zalo-pc-gain-test-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_PORT"] = "0"
os.environ["ZALO_PC_APP_USER"] = "nguoi-dung-test"
os.environ["ZALO_PC_APP_PASSWORD"] = "mat-khau-test-123"
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)

from zalo_pc_app import audio_gain, audio_rx, audio_tx, media_endpoints  # noqa: E402
from zalo_pc_app import server as sv  # noqa: E402


def pcm(*samples):
    return struct.pack("<%dh" % len(samples), *samples)


def unpcm(b):
    return list(struct.unpack("<%dh" % (len(b) // 2), b))


def test_apply_gain_pure():
    f = pcm(1000, -1000, 20000, -20000)
    assert audio_gain.apply_gain(f, 100) is f                                   # 100% = đúng đối tượng cũ, không tốn tính toán
    assert unpcm(audio_gain.apply_gain(f, 50)) == [500, -500, 10000, -10000]
    assert unpcm(audio_gain.apply_gain(f, 200)) == [2000, -2000, 32767, -32768]    # tăng quá thì xén, không tràn số
    assert audio_gain.apply_gain(f, 0) == bytes(len(f))                         # 0% = im lặng
    assert audio_gain.apply_gain(f + b"\x07", 50)[-1:] == b"\x07"               # byte lẻ giữ nguyên
    assert audio_gain.apply_gain(b"", 50) == b""
    assert audio_gain.clamp_percent(-5) == 0 and audio_gain.clamp_percent(999) == 300 and audio_gain.clamp_percent("120") == 120
    for bad in ("abc", None, True):
        try:
            audio_gain.clamp_percent(bad)
        except ValueError:
            continue
        raise AssertionError("phải từ chối %r" % (bad,))


class _Stdin:
    def __init__(self):
        self.data, self.closed = [], False

    def write(self, b):
        self.data.append(b)

    def close(self):
        self.closed = True


class _SinkProc:
    def __init__(self):
        self.stdin = _Stdin()

    def poll(self):
        return 0 if self.stdin.closed else None

    def kill(self):
        self.stdin.closed = True


class _Engine:
    def __init__(self, frames):
        self.frames = list(frames)

    def read_frame(self, timeout=0):
        return self.frames.pop(0) if self.frames else None

    def queue_depth(self):
        return len(self.frames)


def test_sink_applies_gain_after_the_echo_guard_measured_the_original():
    loud = pcm(*([3000] * 320))
    guard = audio_rx.EchoGuard()
    proc = _SinkProc()
    sink = audio_rx.AudioSink(_Engine([loud, loud]), "http://h/i?k=1", guard=guard, popen=lambda *a, **k: proc, sleep=lambda s: None)
    sink.gain = 50
    sink.start()
    deadline = time.time() + 3
    while sink.frames < 2 and time.time() < deadline:
        time.sleep(0.01)
    sink.stop()
    assert unpcm(proc.stdin.data[0])[0] == 1500, proc.stdin.data[:1]          # loa nhận bản đã giảm 50%
    assert guard.levels and sum(guard.levels) >= 1                              # chống vọng vẫn đo trên tiếng gốc 3000 (không lệch theo nút)
    assert sink.status()["gain"] == 50


def test_mic_sender_applies_gain_but_gated_frames_stay_silent():
    src = pcm(*([2000] * 320)) * 4

    class P:
        def __init__(self):
            self.stdout = io.BytesIO(src)

        def poll(self):
            return 0

        def kill(self):
            pass
    sent = []
    s = audio_tx.AudioSender(sent.append, popen=lambda *a, **k: P(), sleep=lambda x: None)
    s.gain = 150
    s.start()
    time.sleep(0.4)
    s.stop()
    assert sent and all(unpcm(f)[0] == 3000 for f in sent), unpcm(sent[0])[:2]
    assert s.status()["gain"] == 150
    sent2, blocked = [], [True]
    s2 = audio_tx.AudioSender(sent2.append, popen=lambda *a, **k: P(), sleep=lambda x: None, gate=lambda: blocked[0])
    s2.gain = 300
    s2.start()
    time.sleep(0.4)
    s2.stop()
    assert sent2 and all(f == bytes(640) for f in sent2)                        # đang chặn vọng: vẫn im lặng dù tăng


def test_rule_gain_from_ha_is_the_default_and_the_buttons_win():
    sv._CALL_DEVICES.pop("91", None)
    sv.CALL_GAIN.pop("91", None)
    sv._remember_call_devices(91, {"mic_url": "test", "mic_gain": 150, "speaker_gain": "220"})
    assert sv._gain_of(91, "mic") == 150 and sv._gain_of(91, "speaker") == 220      # quy tắc HA đặt sẵn mức khởi đầu
    assert sv._set_gain(91, "mic", step=-10) == 140                                   # nút −/+ tính từ mức của quy tắc
    assert sv._gain_of(91, "mic") == 140 and sv._gain_of(91, "speaker") == 220
    sv._remember_call_devices(92, {"mic_url": "test", "mic_gain": "abc", "speaker_gain": 0})
    assert sv._gain_of(92, "mic") == 100 and sv._gain_of(92, "speaker") == 100        # rác/0 = giữ nguyên
    assert sv._devices_for_call(92).get("mic_url") == "test"
    for cid in (91, 92):
        sv._CALL_DEVICES.pop(str(cid), None)
        sv.CALL_GAIN.pop(str(cid), None)


BASE = ""
_COOKIE = ""


def api(method, path, body=None):
    global _COOKIE
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if _COOKIE:
        req.add_header("Cookie", _COOKIE)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            sc = resp.headers.get("Set-Cookie") or ""
            if sc.startswith("zalo_pc_app="):
                _COOKIE = sc.split(";", 1)[0]
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class _Transport:
    def send_pcm(self, p):
        pass

    def send_video_frame(self, au, key):
        return True


class _MicProc:
    def __init__(self):
        self.stdout = io.BytesIO(b"")

    def poll(self):
        return 0

    def kill(self):
        pass


def test_api_gain_step_level_validation_persistence_and_cleanup():
    global BASE
    state = sv.AppState(tmp)
    sv.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    assert api("POST", "/api/app/login", {"username": "nguoi-dung-test", "password": "mat-khau-test-123"})[0] == 200
    state.session = {"zpw_sek": "x", "zpw_enk": "k", "device_id": "d", "uid": "1"}
    assert api("POST", "/api/call/media", {"action": "gain", "target": "mic", "step": 10})[1]["error"] == "no_live_call"
    state.calls.record_start(88, "Peer", "20001", "user")
    state.calls.record_answered(88, "test")
    media_endpoints.ENDPOINTS.active[88] = {"transport": _Transport()}
    real = sv.audio_tx_mod.AudioSender
    sv.audio_tx_mod.AudioSender = lambda f, source="test", fmt="auto", gate=None, **kw: real(f, source=source, fmt=fmt, gate=gate, popen=lambda *a, **k: _MicProc(), **kw)
    import shutil
    real_which = shutil.which
    shutil.which = lambda name: "/usr/bin/" + name
    try:
        st, b = api("POST", "/api/call/media", {"action": "status"})
        assert b["gain"] == {"mic": 100, "speaker": 100}, b
        st, b = api("POST", "/api/call/media", {"action": "gain", "target": "mic", "step": -10})
        assert st == 200 and b["gain"]["mic"] == 90 and b["gain"]["speaker"] == 100, b
        st, b = api("POST", "/api/call/media", {"action": "gain", "target": "speaker", "level": 250})
        assert b["gain"]["speaker"] == 250, b
        st, b = api("POST", "/api/call/media", {"action": "gain", "target": "speaker", "step": 100})
        assert b["gain"]["speaker"] == 300, "phải chặn trần 300%"
        st, b = api("POST", "/api/call/media", {"action": "gain", "target": "mic", "level": 5})
        st, b = api("POST", "/api/call/media", {"action": "gain", "target": "mic", "step": -10})
        assert b["gain"]["mic"] == 0, "phải chặn sàn 0%"
        for bad in ({"target": "video", "step": 10}, {"target": "mic"}, {"target": "mic", "step": "abc"}, {"target": "mic", "level": "x"}):
            st, b = api("POST", "/api/call/media", dict(bad, action="gain"))
            assert st == 400 and b["ok"] is False, (bad, st, b)
        # mic chạy: áp ngay vào bộ gửi; tắt rồi mở lại vẫn giữ mức đã chỉnh
        api("POST", "/api/call/media", {"action": "gain", "target": "mic", "level": 70})
        st, b = api("POST", "/api/call/media", {"action": "start", "target": "mic", "source": "test"})
        assert b["ok"] and b["mic"]["gain"] == 70, b
        api("POST", "/api/call/media", {"action": "gain", "target": "mic", "step": 10})
        assert sv.AUDIO_SENDERS["88"].gain == 80
        api("POST", "/api/call/media", {"action": "stop", "target": "mic"})
        st, b = api("POST", "/api/call/media", {"action": "start", "target": "mic", "source": "test"})
        assert b["mic"]["gain"] == 80, "mở lại mic phải giữ mức đã chỉnh"
        snap = state.calls.snapshot()
        assert snap["active"] is not None and sv._gain_of(88, "mic") == 80 and sv._gain_of(88, "speaker") == 300
        api("POST", "/api/call/media", {"action": "stop", "target": "both"})
        # cuối cuộc gọi: hàm dọn thật xóa mức đã chỉnh (cuộc sau cùng số không thừa hưởng)
        assert "88" in sv.CALL_GAIN
        sv._cleanup_call_media({"call_id": 88, "thread_id": "20001", "status": "answered"})
        assert "88" not in sv.CALL_GAIN and sv._gain_of(88, "mic") == 100
    finally:
        shutil.which = real_which
        sv.audio_tx_mod.AudioSender = real
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
    print("ALL AUDIO GAIN TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
