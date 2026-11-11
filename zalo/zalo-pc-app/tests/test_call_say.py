"""POST /api/call/say: phat am thanh (TTS cua HA) len cuoc goi DANG NOI qua duong mic.
Mock/offline hoan toan; AudioSender duoc thay bang ban ghi nguon (khong can ffmpeg)."""
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from test_call_11301 import _api, FAKE_TOKEN  # noqa: E402
from test_call_incoming_zca import CALL_ID_IN, INCOMING_EVENT, _parsed_event, _wait_active, _wait_steps  # noqa: E402
from test_call_ringing import _run  # noqa: E402
from test_media_provider import REAL_SHAPE_SERVERS  # noqa: E402
from zalo_pc_app import server as sv  # noqa: E402


def _post_file(base, name, data, call_id=None):
    boundary = "----sayb"
    parts = []
    if call_id is not None:
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"call_id\"\r\n\r\n%s\r\n" % (boundary, call_id)).encode())
    if data is not None:
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: audio/mpeg\r\n\r\n"
                      % (boundary, name)).encode() + data + b"\r\n")
    parts.append(("--%s--\r\n" % boundary).encode())
    req = urllib.request.Request(base + "/api/call/say", method="POST", data=b"".join(parts),
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            import json
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        import json
        return e.code, json.loads(e.read().decode())


class _Rec:
    made = []

    def __init__(self, send, source="test", fmt="auto", gate=None, **kw):
        self.source, self.alive, self.gate = source, True, gate
        _Rec.made.append(self)

    def start(self):
        pass

    def stop(self):
        self.alive = False

    def status(self):
        return {"alive": self.alive}


def test_say_plays_file_on_answered_call_and_validates():
    mock = MockZalo().start()
    mock.requestcall_data = {"servers": REAL_SHAPE_SERVERS, "sessId": "s", "srtpKey": "k", "token": FAKE_TOKEN}
    real = sv.audio_tx_mod.AudioSender
    sv.audio_tx_mod.AudioSender = _Rec

    def check(base, mock, endpoints):
        # chua co cuoc goi nao nghe may -> tu choi, khong tao nguon
        st, b = _post_file(base, "a.mp3", b"ID3fake")
        assert b["ok"] is False and b["error"] == "chua_nghe_may", b
        sv.STATE._on_ctrl_call_event(_parsed_event(dict(INCOMING_EVENT)))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        _wait_steps(mock, CALL_ID_IN, ["ringring"])
        assert _api(base, "POST", "/api/call/answer", {"call_id": CALL_ID_IN})[1]["ok"] is True
        # thieu tep -> 400
        st, b = _post_file(base, "a.mp3", None)
        assert st == 400 and b["error"] == "thieu_file", (st, b)
        # Chong vong dang BAT va loa vua phat tieng lon: TTS KHONG duoc bi gate (neu bi gate: nghe giat cuc)
        assert _api(base, "POST", "/api/settings/devices", {"echo_guard": True})[1]["ok"]
        guard = sv._guard_for_call(CALL_ID_IN)
        assert guard is not None
        guard.note_far(b"\xff\x7f" * 320)
        assert guard.blocked() is True
        # co tep -> ghi vao <data>/say va phat qua mic
        st, b = _post_file(base, "tts.mp3", b"ID3-tts-bytes", call_id=CALL_ID_IN)
        assert st == 200 and b["ok"] is True and b["call_id"] == CALL_ID_IN and b["bytes"] == 13, (st, b)
        assert _Rec.made[-1].gate is None, "TTS bi gate chong vong -> mat khung, nghe giat cuc"
        src = _Rec.made[-1].source
        assert os.path.dirname(src) == os.path.join(sv.STATE.data_dir, "say") and src.endswith(".mp3"), src
        assert open(src, "rb").read() == b"ID3-tts-bytes"
        # duoi la khong an toan -> .bin (khong de ten tep nguoi dung vao duong dan)
        st, b = _post_file(base, "../../x;rm", b"zz")
        assert b["ok"] is True and _Rec.made[-1].source.endswith(".bin") and ".." not in os.path.basename(_Rec.made[-1].source)
        # qua lon -> 413
        old = sv.SAY_MAX_BYTES
        sv.SAY_MAX_BYTES = 5
        try:
            st, b = _post_file(base, "big.mp3", b"123456789")
            assert st == 413, (st, b)
        finally:
            sv.SAY_MAX_BYTES = old

    try:
        _run(mock, check)
    finally:
        sv.audio_tx_mod.AudioSender = real


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("ALL CALL-SAY TESTS PASSED")
