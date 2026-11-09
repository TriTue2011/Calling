"""SRTP AES_CM_128_HMAC_SHA1_80/32 thuan Python (RFC 3711).

Chi dung thu vien chuan + `aes_pure` (image app la stdlib-only, khong co
libsrtp2). Cung giao dien voi `zalo_call.srtp.SrtpSession` ma
`pc_media.make_srtp_hooks` dung: `protect(rtp) -> srtp`,
`unprotect(srtp) -> rtp`, ca hai nhan/tra GOI TRON gom header RTP
(`RTP_HEADER_LEN` = 20 byte voi goi PC: 12 byte co dinh + phan mo rong
BEDE 1 tu = 8 byte; do dai that duoc tinh tu bit X/CC cua header nen khong
phu thuoc con so 20).

Nguon doi chieu: `@softtynet/zca-js` 2.3.13, `ZaloSrtpSession.js`
(`deriveSrtpSessionKey`, `buildSrtpCtrIv`, `protectRtp`, `unprotectRtp`).
Test doi chieu bang vector chay tu chinh thu vien do: tests/test_srtp_pure.py.

Khoa: 30 byte = 16 byte khoa chu + 14 byte muoi. Zalo: BEN GOI tu sinh
(30 byte ngau nhien, base64 40 ky tu) va gui trong extendData.srtpKey
cua tin hieu 416 (11301); hai chieu dung chung mot khoa chu.

Gioi han co y: khong chong phat lai (replay), khong SRTCP (extendData gui
srtcp=0), khong suite GCM. Khoa khong bao gio duoc ghi log.
"""

import hashlib
import hmac
import os
import struct

from . import aes_pure

KEY_MATERIAL_LEN = 30          # 16 khoa chu + 14 muoi
_TAG_LEN = {"aes_cm_128_hmac_sha1_80": 10, "aes_cm_128_hmac_sha1_32": 4}


class SrtpError(ValueError):
    """Goi SRTP/RTP khong hop le hoac xac thuc that bai."""


def new_master_key_b64():
    """Khoa chu moi cho BEN GOI: 30 byte ngau nhien -> base64 chuan (40 ky tu)."""
    import base64
    return base64.b64encode(os.urandom(KEY_MATERIAL_LEN)).decode("ascii")


def _aes_ctr(key, iv16, length):
    """Dong khoa AES-CTR `length` byte; bo dem la so nguyen 128 bit tang dan."""
    counter = int.from_bytes(iv16, "big")
    out = bytearray()
    while len(out) < length:
        out += aes_pure.encrypt_block(key, (counter & ((1 << 128) - 1))
                                      .to_bytes(16, "big"))
        counter += 1
    return bytes(out[:length])


def derive_session_key(master_key, master_salt, label, length):
    """RFC 3711 4.3.1 voi key_derivation_rate = 0 (khop ban cua zca-js)."""
    iv = bytearray(16)
    iv[:14] = master_salt[:14]
    iv[7] ^= label & 0xFF
    return _aes_ctr(master_key, bytes(iv), length)


def _ctr_iv(session_salt, ssrc, roc, seq):
    iv = bytearray(16)
    iv[:14] = session_salt[:14]
    for i, b in enumerate(struct.pack(">I", ssrc & 0xFFFFFFFF)):
        iv[4 + i] ^= b
    for i, b in enumerate(struct.pack(">I", roc & 0xFFFFFFFF)):
        iv[8 + i] ^= b
    iv[12] ^= (seq >> 8) & 0xFF
    iv[13] ^= seq & 0xFF
    return bytes(iv)


def _split_rtp(packet):
    """(do_dai_header, seq, ssrc) cua mot goi RTP; SrtpError neu hong."""
    if len(packet) < 12:
        raise SrtpError("goi RTP qua ngan: %d byte" % len(packet))
    first = packet[0]
    if first >> 6 != 2:
        raise SrtpError("khong phai RTP version 2")
    header = 12 + 4 * (first & 0x0F)
    if first & 0x10:                                   # co phan mo rong
        if len(packet) < header + 4:
            raise SrtpError("goi RTP ngan hon header mo rong")
        (ext_words,) = struct.unpack_from(">H", packet, header + 2)
        header += 4 + 4 * ext_words
    if len(packet) < header:
        raise SrtpError("goi RTP ngan hon header (%d < %d)"
                        % (len(packet), header))
    (seq,) = struct.unpack_from(">H", packet, 2)
    (ssrc,) = struct.unpack_from(">I", packet, 8)
    return header, seq, ssrc


class SrtpSession:
    """Mot phien SRTP hai chieu dung chung mot khoa chu (nhu zca-js)."""

    def __init__(self, master_key, suite="aes_cm_128_hmac_sha1_80"):
        if suite not in _TAG_LEN:
            raise ValueError("suite %r khong ho tro (co: %s)"
                             % (suite, sorted(_TAG_LEN)))
        material = bytes(master_key)
        if len(material) != KEY_MATERIAL_LEN:
            raise ValueError("khoa SRTP can %d byte, nhan %d"
                             % (KEY_MATERIAL_LEN, len(material)))
        self.suite = suite
        self._tag_len = _TAG_LEN[suite]
        key, salt = material[:16], material[16:30]
        self._key = derive_session_key(key, salt, 0x00, 16)
        self._auth = derive_session_key(key, salt, 0x01, 20)
        self._salt = derive_session_key(key, salt, 0x02, 14)
        # Ben gui: ROC tang khi seq quay vong (giong zca-js).
        self._send_roc = 0
        self._send_last = None
        # Ben nhan: s_l + ROC theo RFC 3711 Phu luc A.
        self._recv_roc = 0
        self._recv_s_l = None

    # -- gui -------------------------------------------------------------
    def protect(self, rtp):
        header, seq, ssrc = _split_rtp(rtp)
        if self._send_last is not None and seq < self._send_last \
                and self._send_last - seq > 0x8000:
            self._send_roc = (self._send_roc + 1) & 0xFFFFFFFF
        self._send_last = seq
        roc = self._send_roc
        stream = _aes_ctr(self._key, _ctr_iv(self._salt, ssrc, roc, seq),
                          len(rtp) - header)
        enc = bytes(a ^ b for a, b in zip(rtp[header:], stream))
        head = bytes(rtp[:header])
        tag = hmac.new(self._auth, head + enc + struct.pack(">I", roc),
                       hashlib.sha1).digest()[:self._tag_len]
        return head + enc + tag

    # -- nhan ------------------------------------------------------------
    def _guess_roc(self, seq):
        if self._recv_s_l is None:
            return self._recv_roc
        s_l, roc = self._recv_s_l, self._recv_roc
        if s_l < 0x8000:
            if seq - s_l > 0x8000:
                return (roc - 1) & 0xFFFFFFFF
            return roc
        if s_l - 0x8000 > seq:
            return (roc + 1) & 0xFFFFFFFF
        return roc

    def unprotect(self, srtp):
        if len(srtp) < 12 + self._tag_len:
            raise SrtpError("goi SRTP qua ngan: %d byte" % len(srtp))
        body = bytes(srtp[:len(srtp) - self._tag_len])
        got = bytes(srtp[len(srtp) - self._tag_len:])
        header, seq, ssrc = _split_rtp(body)
        roc = self._guess_roc(seq)
        want = hmac.new(self._auth, body + struct.pack(">I", roc),
                        hashlib.sha1).digest()[:self._tag_len]
        if not hmac.compare_digest(got, want):
            raise SrtpError("xac thuc SRTP that bai")
        # Chi cap nhat trang thai SAU khi xac thuc thanh cong.
        if self._recv_s_l is None or roc > self._recv_roc \
                or (roc == self._recv_roc and seq > self._recv_s_l):
            self._recv_roc, self._recv_s_l = roc, seq
        stream = _aes_ctr(self._key, _ctr_iv(self._salt, ssrc, roc, seq),
                          len(body) - header)
        dec = bytes(a ^ b for a, b in zip(body[header:], stream))
        return body[:header] + dec
