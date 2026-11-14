"""Ghi khung hình thật đầu cuộc gọi để chẩn đoán (tắt được; giữ vài tệp; không bao giờ làm hỏng luồng nhận) (14/11/2026).
Run: python3 tests/test_video_dump.py"""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
tmp = tempfile.mkdtemp(prefix="zalo-dump-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
from zalo_pc_app import udp_transport as ut  # noqa: E402

dump = ut.Udp4200Transport._dump_video_frame


def records(path):
    data, out, i = open(path, "rb").read(), [], 0
    while i < len(data):
        n = int.from_bytes(data[i:i + 4], "big")
        out.append((data[i + 4] == 1, data[i + 5:i + 5 + n]))
        i += 5 + n
    return out


def test_dump_writes_first_frames_then_stops_and_closes():
    global tmp
    tmp = tempfile.mkdtemp(prefix="zalo-dump1-")                      # thư mục riêng cho test này (các test độc lập nhau)
    os.environ["ZALO_PC_DATA_DIR"] = tmp
    ut.VIDEO_DUMP_FRAMES = 3
    me = types.SimpleNamespace()
    for n, (key, fr) in enumerate([(True, b"\x00\x00\x00\x01\x67aa"), (False, b"\x00\x00\x00\x01\x41bb"), (False, b"\x00\x00\x00\x01\x41cc"), (False, b"\x00\x00\x00\x01\x41dd")], 1):
        dump(me, fr, key, n)
    files = sorted(os.listdir(os.path.join(tmp, "diag")))
    assert len(files) == 1, files
    rec = records(os.path.join(tmp, "diag", files[0]))
    assert [k for k, _ in rec] == [True, False, False] and rec[0][1].endswith(b"aa") and rec[2][1].endswith(b"cc"), rec      # đúng 3 khung đầu, có cờ khoá
    assert me._video_dump is None                                                                                          # quá giới hạn: đóng tệp


def test_dump_off_keeps_at_most_three_files_and_never_raises():
    ut.VIDEO_DUMP_FRAMES = 0
    me = types.SimpleNamespace()
    folder = os.path.join(tmp, "diag")
    before = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    dump(me, b"\x00\x00\x00\x01\x67", True, 1)
    assert (sorted(os.listdir(folder)) if os.path.isdir(folder) else []) == before                                         # tắt (0): không tạo tệp mới
    ut.VIDEO_DUMP_FRAMES = 2
    import time as _t
    for i in range(5):
        me2 = types.SimpleNamespace()
        dump(me2, b"\x00\x00\x00\x01\x67", True, 1)
        me2._video_dump.close()
        _t.sleep(1.05)                                                                                                   # tên tệp theo giây
    assert len(os.listdir(os.path.join(tmp, "diag"))) <= 3, os.listdir(os.path.join(tmp, "diag"))                          # xoay vòng: giữ ≤ 3 tệp
    os.environ["ZALO_PC_DATA_DIR"] = "/proc/khong-ghi-duoc"                                                               # thư mục không ghi được: nuốt lỗi
    me3 = types.SimpleNamespace()
    dump(me3, b"x", True, 1)
    assert me3._video_dump is None
    os.environ["ZALO_PC_DATA_DIR"] = tmp


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
    print("ALL VIDEO DUMP TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
