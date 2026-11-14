"""Ghi chẩn đoán vọng (audio_dump) + công cụ phân tích echo_analyze (14/11/2026). Chạy: python3 tests/test_audio_dump.py"""
import glob
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from zalo_pc_app import audio_dump  # noqa: E402
import echo_analyze  # noqa: E402

FRAME = bytes(range(256)) * 2 + bytes(128)      # 640 byte


def fresh():
    audio_dump._DUMP = audio_dump._Dump()
    return audio_dump._DUMP


def test_off_by_default_writes_nothing():
    os.environ.pop("ZALO_PC_AUDIO_DUMP_SECONDS", None)
    d = tempfile.mkdtemp()
    dump = fresh()
    dump.record(0, FRAME, now=1.0, directory=d)
    assert glob.glob(d + "/*") == [] and dump._fh is None


def test_records_both_streams_caps_per_call_and_keeps_five_files():
    os.environ["ZALO_PC_AUDIO_DUMP_SECONDS"] = "2"
    try:
        d = tempfile.mkdtemp()
        dump = fresh()
        t = 100.0
        while t < 110.0:                                     # 10 s liên tục nhưng hạn mức 2 s → chỉ ~2 s được ghi
            dump.record(0, FRAME, now=t, directory=d)
            dump.record(1, FRAME[::-1], now=t + 0.001, directory=d)
            t += 0.02
        dump._close()
        files = glob.glob(d + "/echo-*.bin")
        assert len(files) == 1, files
        n = os.path.getsize(files[0]) // (9 + 640)
        assert 190 <= n <= 210, n                            # 2 s × 50 khung × 2 luồng = 200 bản ghi
        far, near = echo_analyze.load(files[0])
        assert far.size == near.size and far.size >= 16000 * 1.9
        # im > 5 s = cuộc mới → tệp mới; giữ tối đa 5 tệp
        for i in range(8):
            t = 500.0 + i * 100
            dump.record(0, FRAME, now=t, directory=d)
            dump.record(1, FRAME, now=t + 0.02, directory=d)
            dump._fh and dump._fh.flush()
            os.utime(dump.path, None)
            import time as _t
            _t.sleep(1.05)                                   # tên tệp theo giây: tránh trùng tên
        dump._close()
        assert len(glob.glob(d + "/echo-*.bin")) <= audio_dump.KEEP_FILES
    finally:
        os.environ.pop("ZALO_PC_AUDIO_DUMP_SECONDS", None)


def _speechlike(n, seed):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n).astype(np.float32)
    env = np.repeat(rng.random(n // 4000 + 1).astype(np.float32) > 0.4, 4000)[:n] * 3000.0      # đoạn có / không có tiếng
    return np.convolve(x, np.ones(4) / 4, mode="same") * env


def test_analyzer_finds_delay_and_echo_fraction():
    n = 16000 * 12
    far = _speechlike(n, 1)
    delay = 4000                                              # 250 ms
    room = np.zeros(300, np.float32); room[0], room[40], room[150] = 0.5, 0.25, 0.1
    echo = np.zeros(n, np.float32); echo[delay:] = np.convolve(far, room)[:n - delay]
    rng = np.random.default_rng(2)
    quiet = echo + 20 * rng.standard_normal(n).astype(np.float32)                 # chỉ có vọng + nhiễu nền
    k, conf, rows = echo_analyze.analyze(far, quiet)
    assert abs(k - delay) <= 40 and conf >= 8, (k, conf)
    assert rows and np.mean([r[3] for r in rows]) > 0.8, "mic toàn vọng phải cho tỷ lệ vọng cao"
    clean = (200 * rng.standard_normal(n)).astype(np.float32)                       # mic KHÔNG có vọng (bộ khử làm sạch / chỉ tiếng nhà)
    k2, conf2, rows2 = echo_analyze.analyze(far, clean)
    assert rows2 and np.mean([r[3] for r in rows2]) < 0.1, "mic không có vọng phải cho tỷ lệ thấp: %s" % np.mean([r[3] for r in rows2])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("ALL AUDIO DUMP TESTS PASSED")
