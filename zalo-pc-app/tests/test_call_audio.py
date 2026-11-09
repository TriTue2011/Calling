"""Cau noi am thanh cuoc goi (call_audio.py + route trong server.py).

Thiet bi bat ky (loa/mic HA...) lay am thanh ben kia qua GET .../out/<token>
va dua mic vao qua POST .../in/<call_id>; ca hai chi chay khi co engine media
gan dung cuoc goi do. Test dung engine GIA — khong goi Zalo that.
"""

import http.client
import json
import os
import struct
import sys
import tempfile
import threading

TEST_USER = "nguoi-dung-test"
TEST_PASSWORD = "mat-khau-test-123"
tmp = tempfile.mkdtemp(prefix="zalo-pc-app-audio-test-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_APP_USER"] = TEST_USER
os.environ["ZALO_PC_APP_PASSWORD"] = TEST_PASSWORD
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import call_audio  # noqa: E402
from zalo_pc_app import ctrl_poll  # noqa: E402
from zalo_pc_app import engine_seam  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import webhooks  # noqa: E402

KEY = "A" * 40


def test_find_srtp_key_in_incoming_event_shapes():
    f = ctrl_poll.find_srtp_key
    assert f({"extendData": {"srtpKey": KEY}}) == KEY
    assert f({"params": json.dumps({"extendData": json.dumps(
        {"srtpMode": 1, "srtpKey": KEY})})}) == KEY          # long JSON chuoi
    assert f({"callSetting": {"zrtcConfig": {"enc": {"key": KEY}}}}) == KEY
    assert f({"data": [{"x": 1}, {"masterKey": KEY}]}) == KEY
    # Khong doan: thieu, ngan, sai kieu, qua sau.
    assert f({"extendData": {"srtpMode": 1}}) is None
    assert f({"srtpKey": "ngan"}) is None
    assert f({"srtpKey": 123}) is None
    assert f("khong phai json") is None and f(None) is None
    deep = cur = {}
    for _ in range(12):
        cur["x"] = {}
        cur = cur["x"]
    cur["srtpKey"] = KEY
    assert f(deep) is None


def test_webhook_ended_event_carries_end_reason_without_zalo_error_text():
    ev = webhooks.build_call_event(
        {"call_id": 5, "thread_id": "9", "peer": "A", "type": "user",
         "status": "ended", "started_at": 1, "ended_at": 9,
         "detail": "peer_declined; zalo_cancel: loi mang"}, "uid")
    assert ev["end_reason"] == "peer_declined", ev
    assert "zalo_cancel" not in json.dumps(ev)
    sent = webhooks.build_call_event(
        {"call_id": 5, "status": "sent", "detail": "x"}, "uid")
    assert "end_reason" not in sent


def test_call_audio_helpers():
    h = call_audio.wav_header()
    assert len(h) == 44 and h[:4] == b"RIFF" and h[8:16] == b"WAVEfmt "
    _fmt, ch, rate, byte_rate, block, bits = struct.unpack_from(
        "<HHIIHH", h, 20)
    assert (ch, rate, byte_rate, block, bits) == (1, 16000, 32000, 2, 16)
    frames, rest = call_audio.split_frames(bytes(1000))
    assert len(frames) == 1 and len(frames[0]) == 640 and rest == 360
    t = call_audio.CallAudioTokens()
    a, b = t.token_for(1), t.token_for(2)
    assert a != b and t.token_for(1) == a and t.call_for(a) == "1"
    assert len(a) >= 30
    t.drop(1)
    assert t.call_for(a) is None and t.call_for(b) == "2"


class _Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, d):
        self.t += d


class _QueueEngine:
    def __init__(self, frames):
        self.q = list(frames)

    def queue_depth(self):
        return len(self.q)

    def read_frame(self, timeout=1.0):
        return self.q.pop(0) if self.q else None


def test_stream_out_is_paced_to_the_clock_not_to_frame_arrival():
    # Khung den khong deu (cu 3 nhip thi co 1 khung): van phai dung 50 khung/s
    # (32000 byte/s) — ghi nhanh hon thi thiet bi phat bi dap va do tre tang.
    clk = _Clock()
    eng = _QueueEngine([])
    out = []
    n = {"i": 0}

    def write(b):
        out.append(b)
        n["i"] += 1
        if n["i"] % 3 == 0:
            eng.q.append(bytes([n["i"] % 250 + 1]) * 640)

    call_audio.stream_out(eng, write, lambda: clk.t < 1.0, clk.now, clk.sleep)
    total = sum(len(b) for b in out)
    assert abs(total - (44 + 32000)) <= 1280, total          # 1 s = 32000 +- 2 khung
    assert out[0][:4] == b"RIFF"
    assert any(b != call_audio.SILENCE for b in out[1:])      # khung that co di qua


def test_stream_out_drops_oldest_when_backlog_builds_up():
    clk = _Clock()
    eng = _QueueEngine([bytes([i]) * 640 for i in range(1, 31)])   # ton 30 khung
    out = []
    call_audio.stream_out(eng, out.append, lambda: len(out) < 3,
                          clk.now, clk.sleep)
    # Giu 5 khung moi nhat (26..30), bo 25 khung cu -> khung dau phat la so 26.
    assert out[1] == bytes([26]) * 640, out[1][:1]


class FakeEngine:
    def __init__(self, call_id):
        self.call_info = {"call_id": call_id}
        self.sent = []
        self.out = [bytes([i]) * 640 for i in range(1, 4)]
        self.fail = False

    def read_frame(self, timeout=1.0):
        return self.out.pop(0) if self.out else None

    def send_pcm(self, pcm):
        if self.fail:
            raise RuntimeError("chua chon relay")
        self.sent.append(pcm)


def _http(port, method, path, body=None, cookie="", ctype="application/json"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    headers = {"Content-Type": ctype}
    if cookie:
        headers["Cookie"] = cookie
    conn.request(method, path, body, headers)
    resp = conn.getresponse()
    return conn, resp


def test_http_routes():
    from http.server import ThreadingHTTPServer
    state = app_server.AppState(tmp)
    assert state.auth is not None, state.auth_error
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # Dang nhap de lay cookie.
        conn, resp = _http(port, "POST", "/api/app/login", json.dumps(
            {"username": TEST_USER, "password": TEST_PASSWORD}).encode())
        cookie = resp.getheader("Set-Cookie").split(";", 1)[0]
        resp.read(); conn.close()

        # --- ra: token sai / chua co media
        conn, resp = _http(port, "GET", "/api/call/audio/out/khong-co")
        assert resp.status == 404, resp.status
        resp.read(); conn.close()
        token = state.audio_tokens.token_for(77)
        engine_seam.SEAM.engine = None
        conn, resp = _http(port, "GET", "/api/call/audio/out/" + token)
        assert resp.status == 409, resp.status
        resp.read(); conn.close()

        # --- ra: dung token + engine dung cuoc goi, KHONG can cookie
        eng = FakeEngine(77)
        engine_seam.SEAM.engine = eng
        conn, resp = _http(port, "GET", "/api/call/audio/out/" + token)
        assert resp.status == 200, resp.status
        assert resp.getheader("Content-Type") == "audio/wav"
        assert resp.getheader("Cache-Control") == "no-store"
        data = resp.read(44 + 640 * 3)
        conn.close()
        assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
        assert data[44:44 + 640] == b"\x01" * 640 and \
            data[44 + 1280:44 + 1920] == b"\x03" * 640
        # engine cua cuoc goi KHAC thi khong phat.
        engine_seam.SEAM.engine = FakeEngine(99)
        conn, resp = _http(port, "GET", "/api/call/audio/out/" + token)
        assert resp.status == 409, resp.status
        resp.read(); conn.close()

        # --- vao (mic): can cookie, can engine dung cuoc goi, cat 640 byte
        engine_seam.SEAM.engine = eng
        pcm = bytes(range(256)) * 4            # 1024 byte = 1 khung + 384 le
        conn, resp = _http(port, "POST", "/api/call/audio/in/77", pcm,
                           ctype="application/octet-stream")
        assert resp.status == 401, resp.status          # khong cookie
        resp.read(); conn.close()
        conn, resp = _http(port, "POST", "/api/call/audio/in/77", pcm,
                           cookie=cookie, ctype="application/octet-stream")
        body = json.loads(resp.read()); conn.close()
        assert resp.status == 200 and body == {
            "ok": True, "frames": 1, "errors": 0, "last_error": ""}, body
        assert eng.sent == [pcm[:640]], len(eng.sent)
        eng.fail = True
        conn, resp = _http(port, "POST", "/api/call/audio/in/77", pcm,
                           cookie=cookie, ctype="application/octet-stream")
        body = json.loads(resp.read()); conn.close()
        assert body["ok"] is False and body["errors"] == 1 \
            and "relay" in body["last_error"], body
        conn, resp = _http(port, "POST", "/api/call/audio/in/55", pcm,
                           cookie=cookie, ctype="application/octet-stream")
        assert resp.status == 409, resp.status             # khong phai cuoc goi nay
        resp.read(); conn.close()
        big = bytes(call_audio.MAX_IN_BYTES + 640)
        conn, resp = _http(port, "POST", "/api/call/audio/in/77", big,
                           cookie=cookie, ctype="application/octet-stream")
        assert resp.status == 413, resp.status
        resp.read(); conn.close()

        # --- ket thuc cuoc goi: token het hieu luc
        state.audio_tokens.drop(77)
        conn, resp = _http(port, "GET", "/api/call/audio/out/" + token)
        assert resp.status == 404, resp.status
        resp.read(); conn.close()
    finally:
        engine_seam.SEAM.engine = None
        httpd.shutdown()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CALL AUDIO TESTS PASSED")
