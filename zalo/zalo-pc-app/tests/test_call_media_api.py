"""API thiet bi mac dinh + dieu khien mic/hinh + chuyen thoai -> video (server that)."""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
tmp = tempfile.mkdtemp(prefix="zalo-pc-media-test-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_PORT"] = "0"
os.environ["ZALO_PC_APP_USER"] = "nguoi-dung-test"
os.environ["ZALO_PC_APP_PASSWORD"] = "mat-khau-test-123"
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)

from zalo_pc_app import media_endpoints  # noqa: E402
from zalo_pc_app import server as sv  # noqa: E402

_COOKIE = ""
BASE = ""


def api(method, path, body=None, login=True):
    global _COOKIE
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if _COOKIE and login:
        req.add_header("Cookie", _COOKIE)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            sc = resp.headers.get("Set-Cookie") or ""
            if sc.startswith("zalo_pc_app="):
                _COOKIE = sc.split(";", 1)[0]
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class _Proc:
    def __init__(self):
        import io
        self.stdout = io.BytesIO(b"")

    def poll(self):
        return 0

    def kill(self):
        pass


class _Transport:
    def __init__(self):
        self.pcm, self.frames = [], []

    def send_pcm(self, p):
        self.pcm.append(p)

    def send_video_frame(self, au, key):
        self.frames.append((len(au), key))
        return True


def test_endpoints():
    global BASE
    state = sv.AppState(tmp)
    sv.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    # Chua dang nhap app -> 401 o ca ba route.
    for m, p in (("GET", "/api/settings/devices"), ("POST", "/api/settings/devices"),
                 ("POST", "/api/call/media"), ("POST", "/api/call/upgrade_video")):
        assert api(m, p, {} if m == "POST" else None, login=False)[0] == 401, p
    assert api("POST", "/api/app/login", {"username": "nguoi-dung-test",
                                          "password": "mat-khau-test-123"})[0] == 200
    # Co dang nhap app nhung chua dang nhap Zalo -> van chua_dang_nhap.
    assert api("GET", "/api/settings/devices")[1].get("error") == "chua_dang_nhap"
    state.session = {"zpw_sek": "x", "zpw_enk": "k", "device_id": "d", "uid": "1"}

    # Cai dat mac dinh: ghi, doc ban da che, tu choi gia tri xau.
    st, b = api("POST", "/api/settings/devices", {
        "camera_url": "rtsp://u:pw@10.0.0.5:8554/cam-sub", "mic_url": "test",
        "video": {"fps": 10}})
    assert st == 200 and b["devices"]["camera_url"] == "rtsp://u:***@10.0.0.5:8554/cam-sub", b
    assert "pw" not in json.dumps(api("GET", "/api/settings/devices")[1])
    st, b = api("POST", "/api/settings/devices", {"mic_url": "ftp://x"})
    assert st == 400 and b["ok"] is False

    # Khong co cuoc goi dang song.
    assert api("POST", "/api/call/media", {"action": "start"})[1]["error"] == "no_live_call"

    # Dung mot cuoc goi da nghe may voi transport gia.
    state.calls.record_start(77, "Peer", "20001", "user")
    state.calls.record_answered(77, "test")
    tr = _Transport()
    media_endpoints.ENDPOINTS.active[77] = {"transport": tr}
    real = sv.audio_tx_mod.AudioSender
    sv.audio_tx_mod.AudioSender = lambda f, source="test", fmt="auto", gate=None: real(
        f, source=source, fmt=fmt, gate=gate, popen=lambda *a, **k: _Proc())
    real_v = sv.video_tx_mod.VideoSender
    sv.video_tx_mod.VideoSender = lambda f, **kw: real_v(
        f, popen=lambda *a, **k: _Proc(), **kw)
    sent = []
    sv._send_a2v_async = lambda cid, thread, status: sent.append(("a2v", cid, thread, status))
    sv._send_camera_state_async = lambda cid, thread, on: sent.append(("cam", cid, thread, on))
    sv.ffmpeg_ok = True
    import shutil
    real_which = shutil.which
    shutil.which = lambda name: "/usr/bin/" + name       # khong can ffmpeg that
    try:
        st, b = api("POST", "/api/call/media", {"target": "mic", "source": "test"})
        assert b["ok"] is True and b["mic"]["alive"] in (True, False) and b["video"] is None, b
        assert api("POST", "/api/call/media", {"action": "status"})[1]["mic"] is not None
        # Mac dinh: target both -> mic_url "test" + camera_url tu cai dat.
        st, b = api("POST", "/api/call/media", {"target": "both"})
        assert b["ok"] and b["video"] is not None, b
        assert ("cam", 77, "20001", True) in sent
        # Dung het.
        st, b = api("POST", "/api/call/media", {"action": "stop", "target": "both"})
        assert b["video"] is None and b["mic"] is None
        assert ("cam", 77, "20001", False) in sent
        # Chuyen thoai -> video: xin 12056 status 1 va bat hinh (camera_url mac dinh).
        sent.clear()
        st, b = api("POST", "/api/call/upgrade_video", {})
        assert b["ok"] and b["video"] is not None, b
        assert ("a2v", 77, "20001", 1) in sent and ("cam", 77, "20001", True) in sent, sent
        # Dien thoai xin len video (status 1): dong y status 2 va phat camera mac dinh.
        sv._stop_video(77)
        sent.clear()
        state._on_video_request({
            "call_id": 77, "act": "audio_to_video", "data": {"params": {"status": 1}}})
        assert ("a2v", 77, "20001", 2) in sent and ("cam", 77, "20001", True) in sent, sent
        # Co do tre: chua lam gi truoc han, den han thi dong y + phat; cuoc goi het truoc han thi bo qua.
        sv._stop_video(77)
        sent.clear()
        api("POST", "/api/settings/devices", {"auto_video_delay": 1})
        state._on_video_request({"call_id": 77, "act": "audio_to_video",
                                 "data": {"params": {"status": 1}}})
        assert sent == [] and "77" not in sv.VIDEO_SENDERS                  # chua toi han
        time.sleep(1.5)
        assert ("a2v", 77, "20001", 2) in sent and ("cam", 77, "20001", True) in sent, sent
        sv._stop_video(77)
        sent.clear()
        state._on_video_request({"call_id": 77, "act": "audio_to_video",
                                 "data": {"params": {"status": 1}}})
        state.calls.record_end(77, "peer_ended")                           # ket thuc truoc han
        time.sleep(1.5)
        assert sent == [] and "77" not in sv.VIDEO_SENDERS, sent
        state.calls.record_start(77, "Peer", "20001", "user")              # dung lai cuoc goi cho phan sau
        state.calls.record_answered(77, "test")
        api("POST", "/api/settings/devices", {"auto_video_delay": 0})
        # Tat auto_video_on_request thi khong tu phat.
        sv._stop_video(77)
        sent.clear()
        api("POST", "/api/settings/devices", {"auto_video_on_request": False})
        state._on_video_request({
            "call_id": 77, "act": "audio_to_video", "data": {"params": {"status": 1}}})
        assert sent == [] and "77" not in sv.VIDEO_SENDERS
        # Cuoc goi chua nghe may khong duoc chuyen video.
        state.calls.record_start(78, "P2", "20002", "user")
        media_endpoints.ENDPOINTS.active[78] = {"transport": tr}
        st, b = api("POST", "/api/call/upgrade_video", {"call_id": 78})
        assert b["error"] == "chua_nghe_may", b
        assert api("POST", "/api/call/media", {"action": "xoa"})[0] == 400
    finally:
        shutil.which = real_which
        sv.audio_tx_mod.AudioSender = real
        sv.video_tx_mod.VideoSender = real_v
        sv._stop_video(77)
        sv._stop_mic(77)
        media_endpoints.ENDPOINTS.active.pop(77, None)
        media_endpoints.ENDPOINTS.active.pop(78, None)
        httpd.shutdown()


def test_speaker_sink_and_echo_guard_endpoints():
    global BASE
    state = sv.AppState(tempfile.mkdtemp(prefix="zalo-pc-spk-"))
    sv.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    global _COOKIE
    _COOKIE = ""
    state.auth = sv.app_auth.AppAuth.from_env(state.data_dir, {
        "ZALO_PC_APP_USER": "nguoi-dung-test", "ZALO_PC_APP_PASSWORD": "mat-khau-test-123"})
    assert api("POST", "/api/app/login", {"username": "nguoi-dung-test",
                                          "password": "mat-khau-test-123"})[0] == 200
    state.session = {"zpw_sek": "x", "zpw_enk": "k", "device_id": "d", "uid": "1"}
    state.calls.record_start(88, "Peer", "20001", "user")
    state.calls.record_answered(88, "test")
    tr = _Transport()
    media_endpoints.ENDPOINTS.active[88] = {"transport": tr}

    class Eng:
        call_info = {"call_id": 88}

        def read_frame(self, timeout=0):
            return None

        def queue_depth(self):
            return 0
    sv.engine_seam.SEAM.engine = Eng()
    procs = []

    class P:
        def __init__(self):
            import io
            self.stdin = type("S", (), {"write": lambda s, b: None, "close": lambda s: None})()
            procs.append(self)

        def poll(self):
            return None

        def kill(self):
            pass
    real_sink, real_mic = sv.audio_rx_mod.AudioSink, sv.audio_tx_mod.AudioSender
    sv.audio_rx_mod.AudioSink = lambda e, u, guard=None: real_sink(
        e, u, guard=guard, popen=lambda *a, **k: P(), sleep=lambda s: None)
    sv.audio_tx_mod.AudioSender = lambda f, source="test", fmt="auto", gate=None: real_mic(
        f, source=source, fmt=fmt, gate=gate, popen=lambda *a, **k: _Proc())
    import shutil
    real_which = shutil.which
    shutil.which = lambda n: "/usr/bin/" + n
    try:
        # Chua co speaker_url: bat tay thieu -> loi ro; URL xau bi tu choi.
        assert api("POST", "/api/call/media", {"target": "speaker"})[1]["error"] == "chua_co_speaker_url"
        assert "http" in api("POST", "/api/call/media", {"target": "speaker", "speaker_url": "rtsp://x"})[1]["error"]
        # Cai dat mac dinh co chong vong -> mic va loa dung chung MOT guard, mic co cong chan.
        api("POST", "/api/settings/devices", {"speaker_url": "http://ha:8123/api/r1_speaker/intercom/E?k=S",
                                              "echo_guard": True, "mic_url": "test"})
        st, b = api("POST", "/api/call/media", {"target": "both"})
        assert b["ok"] and b["speaker"]["alive"] and b["speaker"]["echo_guard"] is True, b
        assert sv.ECHO_GUARDS["88"] is sv.SPEAKER_SINKS["88"]._guard
        assert sv.AUDIO_SENDERS["88"]._gate == sv.ECHO_GUARDS["88"].blocked
        st, b = api("GET", "/api/calls")
        media = [c for c in b["calls"] if c["call_id"] == "88" or str(c["call_id"]) == "88"][0].get("media") or {}
        assert media.get("speaker") and "http" not in json.dumps(media["speaker"]), media
        # Dung rieng loa.
        st, b = api("POST", "/api/call/media", {"action": "stop", "target": "speaker"})
        assert b["speaker"] is None and b["mic"] is not None
        # Ghi de theo cuoc goi: tat loa va chong vong cho rieng cuoc nay.
        sv._stop_mic(88); sv._stop_speaker(88); sv.ECHO_GUARDS.pop("88", None)
        sv._remember_call_devices(88, {"speaker_url": "off", "echo_guard": "false"})
        assert sv._devices_for_call(88)["speaker_url"] == "" and sv._devices_for_call(88)["echo_guard"] is False
        sv._CALL_DEVICES.pop("88", None)
        # Dong cuoc goi: don sach loa, guard, mic.
        api("POST", "/api/call/media", {"target": "both"})
        sv._cleanup_call_media({"call_id": 88})
        assert "88" not in sv.SPEAKER_SINKS and "88" not in sv.ECHO_GUARDS and "88" not in sv.AUDIO_SENDERS
    finally:
        shutil.which = real_which
        sv.audio_rx_mod.AudioSink, sv.audio_tx_mod.AudioSender = real_sink, real_mic
        sv.engine_seam.SEAM.engine = None
        media_endpoints.ENDPOINTS.active.pop(88, None)
        httpd.shutdown()


def test_duplex_speaker_opens_before_mic_and_is_not_restarted():
    global BASE, _COOKIE
    state = sv.AppState(tempfile.mkdtemp(prefix="zalo-pc-dup-"))
    sv.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    _COOKIE = ""
    state.auth = sv.app_auth.AppAuth.from_env(state.data_dir, {
        "ZALO_PC_APP_USER": "nguoi-dung-test", "ZALO_PC_APP_PASSWORD": "mat-khau-test-123"})
    api("POST", "/api/app/login", {"username": "nguoi-dung-test", "password": "mat-khau-test-123"})
    state.session = {"zpw_sek": "x", "zpw_enk": "k", "device_id": "d", "uid": "1"}
    state.calls.record_start(89, "Peer", "20002", "user")
    state.calls.record_answered(89, "test")
    media_endpoints.ENDPOINTS.active[89] = {"transport": _Transport()}

    class Eng:
        call_info = {"call_id": 89}

        def read_frame(self, timeout=0):
            return None

        def queue_depth(self):
            return 0
    sv.engine_seam.SEAM.engine = Eng()
    order, args_seen = [], []

    class P:
        def __init__(self):
            self.stdin = type("S", (), {"write": lambda s, b: None, "close": lambda s: None})()

        def poll(self):
            return None

        def kill(self):
            pass

    def make_sink(e, u, guard=None):
        order.append("sink")
        return real_sink(e, u, guard=guard, popen=lambda a, **k: (args_seen.append(a), P())[1],
                         sleep=lambda s: None)

    def make_mic(f, source="test", fmt="auto", gate=None):
        order.append("mic")
        return real_mic(f, source=source, fmt=fmt, gate=gate, popen=lambda *a, **k: _Proc())
    real_sink, real_mic = sv.audio_rx_mod.AudioSink, sv.audio_tx_mod.AudioSender
    sv.audio_rx_mod.AudioSink, sv.audio_tx_mod.AudioSender = make_sink, make_mic
    real_settle, sv.audio_rx_mod.DUPLEX_SETTLE_SECONDS = sv.audio_rx_mod.DUPLEX_SETTLE_SECONDS, 0
    import shutil
    real_which = shutil.which
    shutil.which = lambda n: "/usr/bin/" + n
    try:
        duplex = "http://ha:8123/api/r1_speaker/duplex/E?k=S"
        api("POST", "/api/settings/devices", {"speaker_url": duplex, "echo_guard": False, "mic_url": "test"})
        # Mo MIC truoc (nhu khi nghe may): phien song cong phai duoc mo truoc mic.
        sv._start_mic(89, "test")
        assert order == ["sink", "mic"], order
        first = sv.SPEAKER_SINKS["89"]
        assert any("pcm_s16le" in a for a in args_seen), "phai gui PCM tho, khong phai A-law"
        # Goi lai loa cung dich (auto media / API) khong dong POST dang mo.
        assert sv._start_speaker(89, duplex) is first and order == ["sink", "mic"]
        sv._start_mic(89, "test")                       # doi mic: khong mo lai phien song cong
        assert order == ["sink", "mic", "mic"] and sv.SPEAKER_SINKS["89"] is first
        # Loa khac dich (cua bo dam) thi thay the.
        other = sv._start_speaker(89, "http://ha:8123/api/r1_speaker/intercom/E?k=S")
        assert other is not first
    finally:
        shutil.which = real_which
        sv.audio_rx_mod.AudioSink, sv.audio_tx_mod.AudioSender = real_sink, real_mic
        sv.audio_rx_mod.DUPLEX_SETTLE_SECONDS = real_settle
        sv._stop_mic(89); sv._stop_speaker(89)
        sv.engine_seam.SEAM.engine = None
        media_endpoints.ENDPOINTS.active.pop(89, None)
        httpd.shutdown()


def test_per_call_override_is_validated_and_cleaned():
    sv._CALL_DEVICES.clear()
    out = sv._remember_call_devices(5, {"mic_url": "http://h/x", "camera_url": "rm -rf",
                                        "mic_format": "s16le16k", "junk": 1})
    assert out == {"mic_url": "http://h/x", "mic_format": "s16le16k"}
    assert sv._CALL_DEVICES["5"] == out
    assert sv._remember_call_devices(6, {"mic_format": "mp3"}) == {}
    assert "6" not in sv._CALL_DEVICES
    # "off" tat thiet bi cho rieng cuoc nay (ghi de mac dinh bang chuoi rong).
    assert sv._remember_call_devices(7, {"mic_url": "off", "camera_url": "OFF"}) == {
        "mic_url": "", "camera_url": ""}
    assert sv._devices_for_call(7)["mic_url"] == "" and sv._devices_for_call(7)["camera_url"] == ""


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CALL MEDIA API TESTS PASSED")
