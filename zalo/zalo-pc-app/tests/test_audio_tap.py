"""Hai nguoi nghe cung mot cuoc goi (loa R1 + AI) khong duoc chia khung nhau: tap = ban sao rieng.
Va nguon tep cua /api/call/say khong duoc LAP (mac dinh nguon tep lap mai)."""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import audio_tx, call_audio, pc_media  # noqa: E402


class _T:
    state = "started"

    def set_pcm_callback(self, cb):
        self.cb = cb

    def stop(self):
        pass


def test_tap_gets_every_frame_and_does_not_steal_from_speaker():
    t = _T()
    eng = pc_media.PcMediaEngine(t, queue_size=500).start()
    tap = eng.add_tap()
    frames = [bytes([i % 256]) * 640 for i in range(80)]
    for f in frames:
        t.cb(f)
    got_tap = [tap.get_nowait() for _ in range(tap.qsize())]
    got_speaker = []
    while True:
        f = eng.read_frame(timeout=0)
        if f is None:
            break
        got_speaker.append(f)
    assert got_tap == frames and got_speaker == frames          # moi ben du ca 80 khung
    eng.remove_tap(tap)
    t.cb(frames[0])
    assert tap.qsize() == 0                                     # go tap roi thi khong nhan nua


def test_slow_tap_drops_but_never_blocks_the_receive_path():
    t = _T()
    eng = pc_media.PcMediaEngine(t, queue_size=500).start()
    tap = eng.add_tap(maxsize=3)
    for i in range(50):
        t.cb(b"\x01" * 640)
    assert tap.qsize() == 3 and eng.status()["received_frames"] == 50


def test_stream_out_reads_from_given_source_not_engine_queue():
    t = _T()
    eng = pc_media.PcMediaEngine(t, queue_size=500).start()
    tap = eng.add_tap()
    for i in range(5):
        t.cb(bytes([i + 1]) * 640)
    out, state = [], {"n": 0}

    def write(chunk):
        out.append(chunk)

    def live():
        state["n"] += 1
        return state["n"] <= 5

    import queue as _q

    def read():
        try:
            return tap.get_nowait()
        except _q.Empty:
            return None
    call_audio.stream_out(eng, write, live, sleep=lambda s: None, clock=lambda: 0.0, read=read, depth=tap.qsize)
    assert out[0][:4] == b"RIFF" and [c[0] for c in out[1:]] == [1, 2, 3, 4, 5]
    assert eng.queue_depth() == 5                               # hang doi chinh cua loa khong bi dung toi


def test_file_source_args_loop_only_when_asked():
    loop = audio_tx.build_ffmpeg_args("/tmp/x.mp3")
    once = audio_tx.build_ffmpeg_args("/tmp/x.mp3", loop=False)
    assert "-stream_loop" in loop and "-stream_loop" not in once and "-re" in once


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("ALL AUDIO-TAP TESTS PASSED")
