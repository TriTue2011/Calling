"""Loa truc tiep (A-law 8 kHz POST toi bo dam) va chong vong (mic nin khi loa phat)."""

import math
import os
import shutil
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import audio_rx, audio_tx, call_audio  # noqa: E402


def tone(amp, n=320):
    return b"".join(struct.pack("<h", int(amp * math.sin(2 * math.pi * 440 * i / 16000)))
                    for i in range(n))


class FakeEngine:
    def __init__(self, frames):
        self.frames = list(frames)

    def read_frame(self, timeout=0):
        return self.frames.pop(0) if self.frames else None

    def queue_depth(self):
        return len(self.frames)


class _Stdin:
    def __init__(self):
        self.data, self.closed = [], False

    def write(self, b):
        self.data.append(b)

    def close(self):
        self.closed = True


class _Proc:
    def __init__(self):
        self.stdin = _Stdin()

    def poll(self):
        return 0 if self.stdin.closed else None

    def kill(self):
        self.stdin.closed = True


def test_ffmpeg_args_alaw_post_low_latency():
    a = audio_rx.build_ffmpeg_args("http://ha:8123/api/r1_speaker/intercom/E?k=K")
    assert a[a.index("-i") + 1] == "-" and "-nostdin" not in a              # doc tu stdin
    assert a[a.index("-c:a") + 1] == "pcm_alaw" and a[a.index("-ar", a.index("-c:a") - 4) + 1] == "8000"
    assert a[a.index("-method") + 1] == "POST" and a[a.index("-chunked_post") + 1] == "1"
    assert "nobuffer" in a and a[-1] == "http://ha:8123/api/r1_speaker/intercom/E?k=K"
    assert a.index("-probesize") < a.index("-i")


def test_ffmpeg_args_duplex_posts_raw_pcm16_16k():
    url = "http://ha:8123/api/r1_speaker/duplex/E?k=K"
    assert audio_rx.is_duplex_url(url)
    assert not audio_rx.is_duplex_url("http://ha:8123/api/r1_speaker/intercom/E?k=K")
    assert not audio_rx.is_duplex_url("") and not audio_rx.is_duplex_url(None)
    a = audio_rx.build_ffmpeg_args(url)
    assert a[a.index("-c:a") + 1] == "pcm_s16le" and "pcm_alaw" not in a
    assert a[a.index("-f", a.index("-c:a")) + 1] == "s16le"
    assert a[a.index("-ar", a.index("-c:a") - 4) + 1] == "16000"          # khong ha xuong 8 kHz
    assert a[a.index("-method") + 1] == "POST" and a[-1] == url


def test_stream_out_header_optional():
    for header in (True, False):
        out = []
        n = [0]

        def live():
            n[0] += 1
            return n[0] <= 3
        call_audio.stream_out(FakeEngine([tone(1000)]), out.append, live,
                              sleep=lambda s: None, header=header)
        assert (out[0][:4] == b"RIFF") == header
        assert len(out) == 3 + (1 if header else 0) and len(out[-1]) == 640     # dung 640 B/khung


def test_echo_guard_blocks_mic_only_while_far_voice_plays():
    now = [100.0]
    g = audio_rx.EchoGuard(threshold=180, hold=0.5, clock=lambda: now[0])
    assert g.blocked() is False
    g.note_far(bytes(640))                         # im lang: khong chan
    g.note_far(tone(60))                           # nho hon nguong
    assert g.blocked() is False
    g.note_far(tone(3000))                         # tieng that
    assert g.blocked() is True and g.suppressed == 1
    now[0] += 0.4
    assert g.blocked() is True                     # van trong thoi gian giu (duoi vong phong)
    now[0] += 0.2
    assert g.blocked() is False                    # het giu: mic gui lai
    assert audio_rx.frame_rms(tone(3000)) > 2000 and audio_rx.frame_rms(b"") == 0.0


def test_sink_writes_frames_in_order_and_feeds_guard():
    frames = [tone(3000), bytes(640), tone(2500)]
    guard = audio_rx.EchoGuard()
    proc = _Proc()
    sink = audio_rx.AudioSink(FakeEngine(frames), "http://h/i?k=1", guard=guard,
                              popen=lambda *a, **k: proc, sleep=lambda s: None)
    sink.start()
    deadline = time.time() + 3
    while sink.frames < 3 and time.time() < deadline:
        time.sleep(0.01)
    sink.stop()
    assert proc.stdin.data[:3] == frames and sink.errors == 0
    st = sink.status()
    assert st["echo_guard"] is True and "http" not in str(st)                  # khong lo URL
    assert proc.stdin.closed


def test_mic_sender_gated_by_guard_sends_silence_frames_not_gaps_and_never_the_real_audio():
    sent, blocked = [], [False]
    frames = b"".join(bytes([i]) * 640 for i in range(1, 9))

    class P:
        def __init__(self):
            import io
            self.stdout = io.BytesIO(frames)

        def poll(self):
            return 0

        def kill(self):
            pass

    s = audio_tx.AudioSender(sent.append, popen=lambda *a, **k: P(), sleep=lambda x: None,
                             gate=lambda: blocked[0])
    blocked[0] = True                              # loa dang phat: tieng mic bi chan nhung luong khung van lien tuc (khung im lang)
    s.start()
    time.sleep(0.4)
    assert sent and all(f == bytes(640) for f in sent), sent[:2]      # toan khung im lang, khong lot tieng that
    assert s.status()["gated"] >= 1
    s.stop()


def test_real_ffmpeg_posts_alaw_to_local_server():
    """Chay ffmpeg THAT (neu co) POST luong A-law toi may chu cuc bo kieu bo dam."""
    if shutil.which("ffmpeg") is None:
        print("SKIP: khong co ffmpeg")
        return
    got = {"n": 0, "chunks": 0, "path": ""}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got["path"] = self.path
            if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                while True:
                    size = int(self.rfile.readline().strip() or b"0", 16)
                    if size == 0:
                        break
                    got["n"] += len(self.rfile.read(size))
                    got["chunks"] += 1
                    self.rfile.readline()
            try:                                   # ffmpeg da bi tat: khong co ai nhan phan hoi
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    frames = [tone(3000)] * 100                      # 2 giay tieng
    engine = FakeEngine(frames)
    sink = audio_rx.AudioSink(engine, "http://127.0.0.1:%d/api/x/intercom/E?k=K" % srv.server_address[1])
    sink.start()
    time.sleep(2.6)
    sink.stop()
    srv.shutdown()
    assert got["path"].endswith("/intercom/E?k=K"), got
    # 2 s A-law 8 kHz = 16000 byte; chap nhan lech nho (bo dem ffmpeg / khung im lang them vao).
    assert 12000 <= got["n"] <= 24000 and got["chunks"] > 5, got


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL AUDIO RX TESTS PASSED")
