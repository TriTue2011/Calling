"""Hình điện thoại gửi H.265/HEVC (log thật 14/11: gói đầu «1c80 00000001 4001» = VPS) — phải ghép, nhận biết và đưa đúng loại cho ffmpeg.
Run: python3 tests/test_hevc_rx.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import h264_rx as rx  # noqa: E402
from zalo_pc_app.calls import video as vid  # noqa: E402

S4 = b"\x00\x00\x00\x01"
VPS, SPS, PPS = b"\x40\x01\x0c\x01", b"\x42\x01\x01\x01", b"\x44\x01\xc1\x72"
IDR, TRAIL = b"\x26\x01\xaf\x08" + b"\x11" * 20, b"\x02\x01\xd0\x10" + b"\x22" * 10


def key_frame_two_packets():
    raw = S4 + VPS + S4 + SPS + S4 + PPS + S4 + IDR
    return [(b"\x1c\x80" + raw[:30], False), (b"\x1c\x40" + raw[30:], True)]       # kiểu Zalo: «1c 80» đầu, «1c 40» cuối


def test_detect_codec_h265_vs_h264():
    assert rx.detect_codec(S4 + VPS) == "h265" and rx.detect_codec(S4 + SPS) == "h265"
    assert rx.detect_codec(b"\x00\x00\x01" + IDR) == "h265"
    assert rx.detect_codec(S4 + b"\x67\x42\x00\x1f") == "h264" and rx.detect_codec(S4 + b"\x41\x9a") == "h264" and rx.detect_codec(S4 + b"\x65\x88") == "h264"
    assert rx.detect_codec(b"") is None and rx.detect_codec(b"\x40") is None


def test_hevc_frames_are_assembled_key_detected_and_params_cached():
    d, seq, out = rx.H264Depacketizer(), 100, []
    # P-frame trước khi có khung khoá: bỏ (đang chờ khung khoá)
    assert d.push(S4 + TRAIL, True, seq) is None and d.need_key
    for pl, mk in key_frame_two_packets():
        seq += 1
        r = d.push(pl, mk, seq)
        if r:
            out.append(r)
    assert len(out) == 1 and out[0][1] is True and d.codec == "h265" and not d.need_key, (out, d.codec)
    assert out[0][0] == S4 + VPS + S4 + SPS + S4 + PPS + S4 + IDR                  # đủ VPS/SPS/PPS + lát cắt IDR, đúng thứ tự
    seq += 1
    r = d.push(S4 + TRAIL, True, seq)                                                # khung P sau khung khoá: phát bình thường
    assert r and r[1] is False and r[0] == S4 + TRAIL
    seq += 1
    r = d.push(S4 + IDR, True, seq)                                                  # khung khoá thiếu tập thông số: tự thêm VPS/SPS/PPS đã nhớ
    assert r and r[1] is True and r[0].startswith(S4 + VPS + S4 + SPS + S4 + PPS), r
    assert d.stats["key"] == 2 and d.stats["frames"] == 3


def test_hevc_packet_loss_waits_for_next_key_like_h264():
    d = rx.H264Depacketizer()
    pk = key_frame_two_packets()
    d.push(pk[0][0], pk[0][1], 1)
    d.push(pk[1][0], pk[1][1], 3)                                                    # mất gói số 2: bỏ khung
    assert d.stats["dropped"] >= 1 and d.need_key
    assert d.push(S4 + TRAIL, True, 4) is None                                       # P-frame khi chờ khung khoá: bỏ


def test_ffmpeg_command_input_format_follows_codec_and_output_untouched():
    h265 = vid._ffmpeg_cmd(vid.VIDEO_VIEW_FFMPEG, "h265")
    i = h265.index("-i")
    assert h265[i - 2:i] == ["-f", "hevc"], h265
    assert h265[h265.index("-f", i) + 1] == "mpjpeg"                                 # đầu ra không đổi
    h264 = vid._ffmpeg_cmd(vid.VIDEO_VIEW_FFMPEG, "h264")
    assert h264 == vid.VIDEO_VIEW_FFMPEG and h264[h264.index("-i") - 1] == "h264"
    snap = vid._ffmpeg_cmd(vid.VIDEO_SNAP_FFMPEG, "h265")
    assert snap[snap.index("-i") - 1] == "hevc" and snap[snap.index("-c:v") + 1] == "mjpeg"


def test_peek_codec_reads_first_frame_and_gives_it_back():
    import queue
    q = queue.Queue()
    q.put((S4 + VPS + S4 + IDR, True))
    codec, first = vid._peek_codec(q, object(), timeout=0.2)
    assert codec == "h265" and first[1] is True and first[0].startswith(S4 + VPS)
    q2 = queue.Queue()
    codec, first = vid._peek_codec(q2, type("T", (), {"_h264": type("D", (), {"codec": "h265"})()})(), timeout=0.05)
    assert codec == "h265" and first is None                                         # chưa có khung: dùng loại đã nhận biết (nếu có)
    assert vid._peek_codec(queue.Queue(), object(), timeout=0.05) == ("h264", None)


def test_deep_shape_never_leaks_values():
    from zalo_pc_app.calls import outgoing
    d = {"hostCall": 1, "params": {"servers": [{"rtcpaddr": "10.9.8.7:4200"}], "token": "BiMat123", "x": {"a": {"b": {"c": 1}}}}, "partnerIds": ["u1", "u2"]}
    shape = outgoing.deep_shape(d)
    assert "10.9.8.7" not in shape and "BiMat123" not in shape and "u1" not in shape, shape
    assert "servers: list(1) of dict(1)" in shape and "token: str(8)" in shape and "partnerIds: list(2) of str(2)" in shape, shape


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
    print("ALL HEVC RX TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
