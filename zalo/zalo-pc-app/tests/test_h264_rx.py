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


# ---- Kiểu đóng gói của ZALO (zcall-native packetizeFrame; app cũng gửi hình lên điện thoại bằng đúng kiểu này) ----
def _zalo_annexb(*nals):
    return b"".join(b"\x00\x00\x00\x01" + n for n in nals)


def _push_all(d, payloads, seq, marker_last=True):
    out = None
    for i, pl in enumerate(payloads):
        out = d.push(pl, marker_last and i == len(payloads) - 1, seq)
        seq = (seq + 1) & 0xFFFF
    return out, seq


def test_zalo_style_key_frame_split_with_1c_80_00_40_headers():
    """Khung khoá lớn (SPS+PPS+IDR ~3 KB) cắt mảnh «1c 80 / 1c 00 / 1c 40» như điện thoại: ghép lại đúng, là khung khoá, đủ SPS/PPS."""
    from zalo_pc_app.udp_transport import packetize_video_frame
    idr = bytes([0x65]) + bytes((i * 7) % 251 for i in range(1, 3000))
    frame = _zalo_annexb(SPS, PPS, idr)
    chunks = packetize_video_frame(frame, 1068)
    assert len(chunks) == 3 and chunks[0][:2] == b"\x1c\x80" and chunks[1][:2] == b"\x1c\x00" and chunks[2][:2] == b"\x1c\x40"
    d = H.H264Depacketizer()
    out, seq = _push_all(d, chunks, 500)
    assert out is not None and out[1] is True
    assert H.split_annexb(out[0]) == [SPS, PPS, idr]


def test_zalo_style_small_frames_sent_whole_as_annexb():
    """Khung vừa một gói gửi NGUYÊN dạng Annex-B (không NAL RFC): P-frame nhỏ sau khung khoá ra đúng, không khoá."""
    d = H.H264Depacketizer()
    key, seq = _push_all(d, [_zalo_annexb(SPS, PPS, IDR)], 10)
    assert key is not None and key[1] is True and H.split_annexb(key[0]) == [SPS, PPS, IDR]
    p, seq = _push_all(d, [_zalo_annexb(P)], seq)
    assert p is not None and p[1] is False and H.split_annexb(p[0]) == [P]


def test_zalo_style_lost_middle_chunk_drops_frame_and_waits_for_next_key():
    from zalo_pc_app.udp_transport import packetize_video_frame
    big = bytes([0x65]) + bytes(range(256)) * 12
    chunks = packetize_video_frame(_zalo_annexb(SPS, PPS, big), 1068)
    d = H.H264Depacketizer()
    d.push(chunks[0], False, 1)
    out = None
    for pl, sq in ((chunks[2], 3),):            # mất gói giữa (seq 2)
        out = d.push(pl, True, sq)
    assert out is None and d.stats["dropped"] == 1
    p, _ = _push_all(d, [_zalo_annexb(P)], 4)   # chưa có khung khoá mới: bỏ
    assert p is None
    key, _ = _push_all(d, [_zalo_annexb(SPS, PPS, IDR)], 5)
    assert key is not None and key[1] is True


def test_rfc6184_fu_a_still_works_next_to_zalo_style():
    d = H.H264Depacketizer()
    seq = 900
    _, seq = _push_all(d, [bytes([24]) + len(SPS).to_bytes(2, "big") + SPS + len(PPS).to_bytes(2, "big") + PPS], seq, marker_last=False)
    out, seq = _push_all(d, fu_a(IDR, 10), seq)
    assert out is not None and out[1] is True


# ---- Xếp lại gói lệch thứ tự + xin khung khoá (14/11/2026: cuộc video thật chỉ ghép được ~10% khung, bỏ 302) ----
def test_reorder_buffer_in_order_swap_late_duplicate_and_wraparound():
    r = H.ReorderBuffer()
    got = []
    for seq in (10, 11, 13, 12, 14):                       # 13 đến trước 12
        got += [q for q, _ in r.push(seq, "p%d" % seq)]
    assert got == [10, 11, 12, 13, 14], got
    assert r.push(12, "trùng") == [] and r.late == 1       # muộn/trùng: bỏ
    r2 = H.ReorderBuffer()
    out = []
    for seq in (65534, 65535, 1, 0, 2):                    # vòng seq 16 bit, 0 đến sau 1
        out += [q for q, _ in r2.push(seq, seq)]
    assert out == [65534, 65535, 0, 1, 2], out


def test_reorder_buffer_gives_up_on_a_lost_packet_after_max_hold():
    r = H.ReorderBuffer(max_hold=4)
    out = [q for q, _ in r.push(100, 0)]
    for seq in range(102, 108):                            # 101 mất hẳn
        out += [q for q, _ in r.push(seq, 0)]
    assert out[0] == 100 and out[1] == 102 and out[-1] == 107 and r.lost == 1, (out, r.lost)


def test_depacketizer_recovers_all_frames_when_packets_arrive_swapped():
    from zalo_pc_app.udp_transport import packetize_video_frame
    big = bytes([0x65]) + bytes((i * 3) % 251 for i in range(1, 2600))
    frames = [_zalo_annexb(SPS, PPS, big), _zalo_annexb(P), _zalo_annexb(P)]
    pkts = []                                              # (seq, payload, marker)
    seq = 7
    for f in frames:
        ch = packetize_video_frame(f, 1068)
        for i, c in enumerate(ch):
            pkts.append((seq, c, i == len(ch) - 1))
            seq += 1
    swapped = list(pkts)
    swapped[1], swapped[2] = swapped[2], swapped[1]       # đảo hai gói giữa khung khoá
    r, d, keys = H.ReorderBuffer(), H.H264Depacketizer(), 0
    n = 0
    for sq, pl, mk in swapped:
        for q, (p2, m2) in r.push(sq, (pl, mk)):
            o = d.push(p2, m2, q)
            if o is not None:
                n += 1
                keys += 1 if o[1] else 0
    assert n == 3 and keys == 1 and d.stats["dropped"] == 0, (n, keys, d.stats)
    assert d.need_key is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL H264 RX TESTS PASSED")
