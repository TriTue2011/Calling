"""SRTP thuan Python doi chieu voi @softtynet/zca-js 2.3.13.

Vector trong tests/fixtures/srtp_zca_js_2_3_13.json duoc SINH bang chinh
`ZaloSrtpSession.protectRtp` cua thu vien do (script sinh: tests/fixtures/
srtp_vectors.mjs). Test nay khong chung minh "chay duoc voi Zalo that" — no
chung minh ban Python tao ra DUNG tung byte ma thu vien tham chieu tao ra,
ke ca luc seq quay vong 65535 -> 0 (ROC tang).
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import srtp_pure  # noqa: E402
from zalo_pc_app.srtp_pure import SrtpError, SrtpSession  # noqa: E402

with open(os.path.join(os.path.dirname(__file__), "fixtures",
                       "srtp_zca_js_2_3_13.json"), encoding="utf-8") as _f:
    VEC = json.load(_f)

import base64  # noqa: E402

KEY = base64.b64decode(VEC["key_b64"])
SUITES = {"AES_CM_128_HMAC_SHA1_80": "aes_cm_128_hmac_sha1_80",
          "AES_CM_128_HMAC_SHA1_32": "aes_cm_128_hmac_sha1_32"}


def test_protect_matches_reference_byte_for_byte():
    for ref_suite, suite in SUITES.items():
        s = SrtpSession(KEY, suite)
        for i, pkt in enumerate(VEC["suites"][ref_suite]):
            got = s.protect(bytes.fromhex(pkt["rtp"])).hex()
            assert got == pkt["srtp"], (suite, i)


def test_unprotect_reads_reference_packets():
    for ref_suite, suite in SUITES.items():
        s = SrtpSession(KEY, suite)
        for i, pkt in enumerate(VEC["suites"][ref_suite]):
            got = s.unprotect(bytes.fromhex(pkt["srtp"])).hex()
            assert got == pkt["rtp"], (suite, i)


def test_roc_rolls_over_with_sequence_wrap():
    # Chuoi vector: seq 65530..65535 roi 0..3 (ROC tang tu 0 len 1). Phia nhan
    # phai tu doan ROC dung, neu khong goi seq=0 se khong xac thuc duoc.
    pk = VEC["suites"]["AES_CM_128_HMAC_SHA1_80"]
    assert [p["rtp"][4:8] for p in pk[4:8]] == ["fffe", "ffff", "0000", "0001"]
    s = SrtpSession(KEY, "aes_cm_128_hmac_sha1_80")
    for p in pk:
        assert s.unprotect(bytes.fromhex(p["srtp"])) == bytes.fromhex(p["rtp"])
    # ROC that su da tang: cung seq=0 nhung ROC 0 se cho ban ma khac.
    fresh = SrtpSession(KEY, "aes_cm_128_hmac_sha1_80")
    zero_roc0 = fresh.protect(bytes.fromhex(pk[6]["rtp"])).hex()
    assert zero_roc0 != pk[6]["srtp"]


def test_roundtrip_two_sessions_same_key():
    a = SrtpSession(KEY)
    b = SrtpSession(KEY)
    for n in (0, 1, 15, 16, 17, 160, 640):
        rtp = bytes.fromhex(VEC["suites"]["AES_CM_128_HMAC_SHA1_80"][0]["rtp"])[:20] \
            + bytes((i * 3) & 0xFF for i in range(n))
        assert b.unprotect(a.protect(rtp)) == rtp


def test_tamper_and_wrong_key_rejected():
    pkt = bytes.fromhex(VEC["suites"]["AES_CM_128_HMAC_SHA1_80"][0]["srtp"])
    flipped = bytearray(pkt)
    flipped[25] ^= 0x01
    try:
        SrtpSession(KEY).unprotect(bytes(flipped))
    except SrtpError:
        pass
    else:
        raise AssertionError("goi bi sua phai bi tu choi")
    other = bytes((b ^ 0xFF) for b in KEY)
    try:
        SrtpSession(other).unprotect(pkt)
    except SrtpError:
        pass
    else:
        raise AssertionError("sai khoa phai bi tu choi")


def test_bad_inputs():
    for bad in (KEY[:29], KEY + b"\x00"):
        try:
            SrtpSession(bad)
        except ValueError:
            continue
        raise AssertionError("do dai khoa sai phai bi tu choi")
    try:
        SrtpSession(KEY, "aes_gcm_128_16_auth")
    except ValueError:
        pass
    else:
        raise AssertionError("suite GCM chua ho tro phai bao loi ro")
    try:
        SrtpSession(KEY).protect(b"\x90\x70")
    except SrtpError:
        pass
    else:
        raise AssertionError("goi qua ngan phai bi tu choi")


def test_new_master_key_is_40_char_base64_of_30_bytes():
    k = srtp_pure.new_master_key_b64()
    assert len(k) == 40
    assert len(base64.b64decode(k)) == 30
    assert k != srtp_pure.new_master_key_b64()


def test_session_key_is_first_30_ascii_chars_of_sessid():
    sess = "TQbwP5z1Y3Pqd6rJPqc9E7UU7Mu6JPrk" + "x" * 100   # dang sessId (gia)
    assert srtp_pure.key_from_session(sess) == sess[:30].encode("ascii")
    assert srtp_pure.key_from_session(sess.encode()) == sess[:30].encode()
    # Thieu / sai kieu / khong phai ASCII -> None (khong doan, khong cat ngan).
    for bad in (None, "", "ngan", "a" * 29, 123, "é" * 40):
        assert srtp_pure.key_from_session(bad) is None, bad


def test_session_key_roundtrips_plain_12_byte_rtp():
    # Dien thoai that gui RTP tran 12 byte (0x80) + tai ma hoa + the 10 byte;
    # SrtpSession phai ma hoa/giai ma dung goi kieu do voi khoa tu sessId.
    import struct
    sess = "Ab-_" * 38                                      # 152 ky tu
    key = srtp_pure.key_from_session(sess)
    rtp = bytes([0x80, 0x70]) + struct.pack(">HII", 5553, 1504637829,
                                            0x0C646DE5) + b"\x48" + bytes(range(7))
    a, b = SrtpSession(key), SrtpSession(key)
    wire = a.protect(rtp)
    assert len(wire) == len(rtp) + 10 and wire[:12] == rtp[:12]
    assert wire[12:-10] != rtp[12:]                          # that su da ma hoa
    assert b.unprotect(wire) == rtp
    other = srtp_pure.key_from_session("Zz" + sess[2:])
    try:
        SrtpSession(other).unprotect(wire)
    except SrtpError:
        pass
    else:
        raise AssertionError("sai khoa phai bi tu choi")


def test_openssl_keystream_matches_pure_python():
    # Dong khoa OpenSSL phai KHAC KHONG so voi ban thuan Python (gom ca khi bo dem
    # tran byte thap: iv ket thuc bang ff ff).
    if srtp_pure._LIBCRYPTO is None:
        return
    import os as _os
    for key in (bytes(range(16)), _os.urandom(16)):
        for iv in (bytes(16), bytes(14) + b"\xff\xfe", _os.urandom(16),
                   b"\xff" * 16):
            for n in (1, 15, 16, 17, 100, 1400):
                a = srtp_pure._aes_ctr_openssl(key, iv, n)
                b = srtp_pure._aes_ctr_pure(key, iv, n)
                assert a == b, (key.hex(), iv.hex(), n)


def test_protect_1k_packet_is_fast_with_openssl():
    if srtp_pure._LIBCRYPTO is None:
        return
    import struct as _st
    import time as _t
    s = SrtpSession(KEY)
    pkt = bytes([0x90, 0x62]) + _st.pack(">HII", 1, 0, 7) + bytes(8) + bytes(1070)
    t0 = _t.perf_counter()
    for i in range(50):
        s.protect(pkt[:2] + _st.pack(">H", i) + pkt[4:])
    per = (_t.perf_counter() - t0) / 50
    assert per < 0.005, "SRTP 1 KB mat %.1f ms/goi" % (per * 1000)   # ban thuan ~25-40 ms


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL SRTP TESTS PASSED")
