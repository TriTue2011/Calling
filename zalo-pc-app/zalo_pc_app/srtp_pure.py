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

Khoa: 30 byte = 16 byte khoa chu + 14 byte muoi. Dien thoai that dung
`key_from_session` (30 ky tu dau cua sessId, do 09/11/2026); zca-js thi cho
ben goi tu sinh (30 byte ngau nhien, base64 40 ky tu) gui trong
extendData.srtpKey cua tin hieu 416 — che do "key", khong thay may that
chap nhan. Hai chieu dung chung mot khoa chu.

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


def key_from_session(session):
    """Khoa chu SRTP cua cuoc goi = 30 KY TU DAU cua `sessId` (chuoi base64url
    server cap o phan hoi 11300), dung nguyen ky tu ASCII lam byte.

    Do 09/11/2026 tren cuoc goi that toi dien thoai Android: ca 8 goi nhan duoc
    xac thuc HMAC-SHA1-80 dung va giai ma ra Opus 16 kHz 20 ms (TOC 0x48) voi
    khoa nay; khong co khoa nao khac xuat hien trong 11300 / su kien tra loi /
    su kien cuoc goi den. Hai chieu dung chung khoa. Tra None khi `session`
    khong phai chuoi ASCII du 30 ky tu."""
    if isinstance(session, (bytes, bytearray)):
        session = bytes(session).decode("ascii", "ignore")
    if not isinstance(session, str) or len(session) < KEY_MATERIAL_LEN \
            or not session.isascii():
        return None
    return session[:KEY_MATERIAL_LEN].encode("ascii")


def _load_libcrypto():
    """OpenSSL (libcrypto) qua ctypes de tao dong khoa AES-CTR nhanh. Python
    chuan da keo theo libcrypto (hashlib/ssl dung no) nen khong them goi nao.
    Tra None neu khong nap duoc — khi do dung ban thuan Python (cham: ~25 ms
    moi goi 1 KB, du de hinh video lam nghen am thanh)."""
    try:
        import ctypes
        import ctypes.util
        lib = ctypes.CDLL(ctypes.util.find_library("crypto")
                          or "libcrypto.so.3")
        vp, ci = ctypes.c_void_p, ctypes.c_int
        lib.EVP_CIPHER_CTX_new.restype = vp
        lib.EVP_CIPHER_CTX_free.argtypes = [vp]
        lib.EVP_aes_128_ctr.restype = vp
        lib.EVP_EncryptInit_ex.argtypes = [vp, vp, vp, ctypes.c_char_p,
                                           ctypes.c_char_p]
        lib.EVP_EncryptInit_ex.restype = ci
        lib.EVP_EncryptUpdate.argtypes = [vp, ctypes.c_char_p,
                                          ctypes.POINTER(ci),
                                          ctypes.c_char_p, ci]
        lib.EVP_EncryptUpdate.restype = ci
        return lib
    except (OSError, AttributeError):
        return None


_LIBCRYPTO = _load_libcrypto()


def _aes_ctr_openssl(key, iv16, length):
    import ctypes
    lib = _LIBCRYPTO
    ctx = lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise SrtpError("EVP_CIPHER_CTX_new that bai")
    try:
        if lib.EVP_EncryptInit_ex(ctx, lib.EVP_aes_128_ctr(), None,
                                  bytes(key), bytes(iv16)) != 1:
            raise SrtpError("EVP_EncryptInit_ex that bai")
        out = ctypes.create_string_buffer(length + 16)
        outl = ctypes.c_int(0)
        if lib.EVP_EncryptUpdate(ctx, out, ctypes.byref(outl),
                                 bytes(length), length) != 1:
            raise SrtpError("EVP_EncryptUpdate that bai")
        return out.raw[:length]
    finally:
        lib.EVP_CIPHER_CTX_free(ctx)


def _aes_ctr_pure(key, iv16, length):
    """Dong khoa AES-CTR `length` byte; bo dem la so nguyen 128 bit tang dan."""
    counter = int.from_bytes(iv16, "big")
    out = bytearray()
    while len(out) < length:
        out += aes_pure.encrypt_block(key, (counter & ((1 << 128) - 1))
                                      .to_bytes(16, "big"))
        counter += 1
    return bytes(out[:length])


def _aes_ctr(key, iv16, length):
    if length <= 0:
        return b""
    if _LIBCRYPTO is not None:
        return _aes_ctr_openssl(key, iv16, length)
    return _aes_ctr_pure(key, iv16, length)


def _xor(a, b):
    n = len(a)
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(n, "big")


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
        enc = _xor(rtp[header:], stream)
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
        dec = _xor(body[header:], stream)
        return body[:header] + dec
