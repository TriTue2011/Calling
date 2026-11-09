"""Phat hinh len cuoc goi: tach khung H.264, dong goi theo kieu dien thoai, gui."""

import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-auth")

from zalo_pc_app import udp_transport as ut  # noqa: E402
from zalo_pc_app import video_tx  # noqa: E402

SC4 = b"\x00\x00\x00\x01"
AUD = SC4 + b"\x09\xf0"
SPS = SC4 + b"\x67\x42\x00\x1f\xac"
PPS = SC4 + b"\x68\xce\x3c\x80"
IDR = SC4 + b"\x65" + b"\x88" * 40
P = SC4 + b"\x41" + b"\x9a" * 20


def test_splitter_cuts_on_aud_and_holds_last_frame():
    key = AUD + SPS + PPS + IDR
    stream = key + AUD + P + AUD + P + AUD
    sp = video_tx.AccessUnitSplitter()
    got = []
    for i in range(0, len(stream), 7):               # nhieu manh nho
        got += sp.feed(stream[i:i + 7])
    assert got == [key, AUD + P, AUD + P], [len(g) for g in got]
    assert video_tx.is_key_frame(got[0]) and not video_tx.is_key_frame(got[1])
    # Khung cuoi chua co AUD ke tiep thi chua ra.
    assert sp.feed(b"") == []


def test_splitter_handles_three_byte_start_codes_and_leading_junk():
    a = b"\x00\x00\x01\x09\xf0\x00\x00\x01\x41\x01\x02"
    sp = video_tx.AccessUnitSplitter()
    got = sp.feed(b"\xff\xee" + a + a + a)
    assert got == [a, a], got


def test_packetize_small_and_fragmented_like_the_phone():
    small = bytes(range(200))
    assert ut.packetize_video_frame(small) == [small]
    big = bytes(i % 251 for i in range(2500))
    parts = ut.packetize_video_frame(big)
    assert [p[:2] for p in parts] == [b"\x1c\x80", b"\x1c\x00", b"\x1c\x40"]
    assert all(len(p) == 2 + 1068 for p in parts[:2]) and len(parts[2]) == 2 + 364
    assert b"".join(p[2:] for p in parts) == big
    assert len(ut.packetize_video_frame(b"x" * 1068)) == 1       # vua khit


def test_build_ffmpeg_args_per_source():
    t = video_tx.build_ffmpeg_args("test", 640, 360, 15, 300)
    assert "lavfi" in t and "-re" in t and "libx264" in t
    assert "aud=1:repeat-headers=1" in t and t[-1] == "pipe:1"
    r = video_tx.build_ffmpeg_args("rtsp://h/x", 640, 360, 15, 300)
    assert r[r.index("-rtsp_transport") + 1] == "tcp" and "-re" not in r
    f = video_tx.build_ffmpeg_args("/tmp/a.mp4")
    assert "-stream_loop" in f
    assert t[t.index("-g") + 1] == "15"


class _FakeProc:
    def __init__(self, data):
        import io
        self.stdout = io.BytesIO(data)

    def poll(self):
        return 0

    def kill(self):
        pass


def test_sender_feeds_frames_and_counts_skips():
    key = AUD + SPS + PPS + IDR
    stream = AUD + P + key + AUD + P + AUD + P + AUD     # P dau bi bo (chua co khoa)
    calls = []

    def send(au, k):
        calls.append((len(au), k))
        return bool(calls and (k or any(c[1] for c in calls[:-1])))
    sender = video_tx.VideoSender(send, popen=lambda *a, **k: _FakeProc(stream))
    sender.start()
    sender._thread.join(timeout=3)
    st = sender.status()
    assert st["frames"] == 3 and st["keys"] == 1 and st["skipped_before_key"] == 1, st
    assert st["alive"] is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VIDEO TX TESTS PASSED")
