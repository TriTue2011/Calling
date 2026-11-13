"""Ghép RTP H.264 chuẩn (NAL đơn, STAP-A, FU-A) thành khung Annex-B; mất gói thì bỏ khung."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import h264_rx as H  # noqa: E402

SPS = bytes([0x67, 0x42, 0x00, 0x1F, 0xAA])
PPS = bytes([0x68, 0xCE, 0x3C, 0x80])
IDR = bytes([0x65]) + bytes(range(1, 30))
P = bytes([0x41]) + bytes(range(50, 70))


def fu_a(nal, size):
    body = nal[1:]
    out, i = [], 0
    while i < len(body):
        chunk = body[i:i + size]
        s = 0x80 if i == 0 else 0
        e = 0x40 if i + size >= len(body) else 0
        out.append(bytes([(nal[0] & 0xE0) | 28, s | e | (nal[0] & 0x1F)]) + chunk)
        i += size
    return out


def test_single_nal_and_stap_a_and_fu_a_make_annexb_frame():
    d = H.H264Depacketizer()
    seq = 100
    stap = bytes([24]) + len(SPS).to_bytes(2, "big") + SPS + len(PPS).to_bytes(2, "big") + PPS
    assert d.push(stap, False, seq) is None
    parts = fu_a(IDR, 8)
    out = None
    for k, p in enumerate(parts):
        seq += 1
        out = d.push(p, k == len(parts) - 1, seq)
    assert out is not None
    annexb, key = out
    assert key is True
    assert annexb == H.START + SPS + H.START + PPS + H.START + IDR
    seq += 1
    f2 = d.push(P, True, seq)                                # NAL đơn = khung P
    assert f2 == (H.START + P, False)
    assert d.stats["frames"] == 2 and d.stats["key"] == 1


def test_packet_loss_drops_frame_and_waits_for_next_keyframe():
    d = H.H264Depacketizer()
    seq = 1
    for k, p in enumerate(fu_a(IDR, 8)):                     # khoá đầu: OK
        out = d.push(p, False, seq) if False else d.push(p, k == len(fu_a(IDR, 8)) - 1, seq)
        seq += 1
    assert out is not None
    parts = fu_a(bytes([0x41]) + bytes(range(80)), 10)       # khung P nhiều mảnh, MẤT mảnh giữa
    seq += 1
    outs = []
    for k, p in enumerate(parts):
        if k == 2:
            seq += 1                                         # mất 1 gói
        outs.append(d.push(p, k == len(parts) - 1, seq))
        seq += 1
    assert all(o is None for o in outs), "khung mất gói không được phát"
    assert d.stats["dropped"] == 1
    p2 = d.push(P, True, seq)                                # khung P kế: bỏ vì chưa có khoá mới
    assert p2 is None
    seq += 1
    k2 = d.push(IDR, True, seq)                              # khoá mới: phát lại
    assert k2 is not None and k2[1] is True


def test_key_frame_without_sps_pps_gets_cached_ones_prepended():
    d = H.H264Depacketizer()
    d.push(SPS, False, 1)
    d.push(PPS, False, 2)
    d.push(IDR, True, 3)                                     # khung khoá có SPS/PPS cùng khung
    out = d.push(IDR, True, 4)                               # khung khoá chỉ có IDR
    assert out[0] == H.START + SPS + H.START + PPS + H.START + IDR


def test_rtp_payload_skips_header_extension_and_padding():
    hdr = bytes([0x90, 98, 0, 1, 0, 0, 0, 1, 0, 0, 0, 2])     # V2, X=1
    ext = bytes([0xBE, 0xDE, 0x00, 0x01, 0x51, 0x01, 0x22, 0x00])
    assert H.rtp_payload(hdr + ext + b"\x41abc") == b"\x41abc"
    assert H.rtp_payload(b"\x80\x62") is None
    padded = bytes([0xA0, 98, 0, 1, 0, 0, 0, 1, 0, 0, 0, 2]) + b"\x41abc" + b"\x00\x00\x03"
    assert H.rtp_payload(padded) == b"\x41abc"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL H264 RX TESTS PASSED")
