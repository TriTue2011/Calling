import struct, sys
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import udp_transport as ut

def hdr(pt, rc, words): return struct.pack(">BBH", 0x80 | rc, pt, words)
OURS = 365685311
# SR (200) rc=1: header+ssrc(4)+sender info(20) = 28 byte, + 1 block 24 byte => 52 byte = 13 words -> length field 12
sr = hdr(200, 1, 12) + struct.pack(">I", 207908325) + b"\0" * 20 + struct.pack(">IIIIII", OURS, (3 << 24) | 7, 5000, 11, 0, 0)
pli = hdr(206, 1, 2) + struct.pack(">II", 207908325, OURS)
fir = hdr(206, 4, 4) + struct.pack(">II", 207908325, 0) + struct.pack(">I", OURS) + b"\0" * 4
nack = hdr(205, 1, 3) + struct.pack(">IIHH", 207908325, OURS, 100, 0)
remb = hdr(206, 15, 5) + struct.pack(">II", 207908325, 0) + b"REMB" + b"\0" * 8
twcc = hdr(205, 15, 3) + struct.pack(">IIHH", 207908325, OURS, 1, 1)
fb = ut.parse_video_rtcp_feedback(sr + pli + fir + nack + remb + twcc)
assert fb["pli"] == 1 and fb["fir"] == 1 and fb["nack"] == 1 and fb["remb"] == 1 and fb["twcc"] == 1, fb
assert len(fb["blocks"]) == 1, fb
b = fb["blocks"][0]
assert b["ssrc"] == OURS and b["fraction"] == 3 and b["cum_lost"] == 7 and b["ext_high"] == 5000 and b["jitter"] == 11, b
# RR (201) rc=1 : 8 byte + 24 = 32 byte = 8 words -> 7
rr = hdr(201, 1, 7) + struct.pack(">I", 207908325) + struct.pack(">IIIIII", OURS, 0, 9, 4, 0, 0)
assert ut.parse_video_rtcp_feedback(rr)["blocks"][0]["ext_high"] == 9
# cụt / rác không được ném lỗi
assert ut.parse_video_rtcp_feedback(b"")["blocks"] == []
assert ut.parse_video_rtcp_feedback(sr[:30])["blocks"] == []
assert ut.parse_video_rtcp_feedback(b"\x80\xc8\xff\xff" + b"\0" * 8)["pli"] == 0
print("PASSED")
