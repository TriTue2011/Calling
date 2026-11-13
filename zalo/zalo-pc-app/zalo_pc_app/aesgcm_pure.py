"""AES-GCM thuần Python (giải mã/mã hoá), IV độ dài BẤT KỲ (Zalo dùng IV 16 byte, không phải 12), AAD tuỳ ý, thẻ 16 byte.

Dùng cho dữ liệu sự kiện WebSocket (encrypt = 2 hoặc 3): container không có thư viện `cryptography`. Chậm hơn bản C nhiều nhưng mỗi sự kiện chỉ vài KB.
Tái dùng các hàm vòng của aes_pure (khoá chỉ mở rộng MỘT lần cho mỗi lần gọi). Đã đối chiếu với NIST GCM test case 3-6 và với `cryptography`
trên khoá/IV/AAD ngẫu nhiên (xem tests/test_aesgcm_pure.py).
"""
from __future__ import annotations

import hmac

from . import aes_pure as _A

TAG_LEN = 16
_R = 0xE1 << 120


def _enc_block(sched, block):
    w, nr = sched
    state = list(block)
    _A._add_round_key(state, w, 0)
    for rnd in range(1, nr):
        _A._sub_bytes(state, _A._SBOX)
        _A._shift_rows(state)
        _A._mix_columns(state)
        _A._add_round_key(state, w, rnd)
    _A._sub_bytes(state, _A._SBOX)
    _A._shift_rows(state)
    _A._add_round_key(state, w, nr)
    return bytes(state)


def _gf_mult(x, y):
    z, v = 0, y
    for i in range(127, -1, -1):
        if (x >> i) & 1:
            z ^= v
        v = ((v >> 1) ^ _R) if (v & 1) else (v >> 1)
    return z


def _pad16(b):
    return b + b"\x00" * ((-len(b)) % 16)


def _ghash(h, data):
    """GHASH trên dữ liệu ĐÃ độn bội số 16 byte."""
    y = 0
    for i in range(0, len(data), 16):
        y = _gf_mult(y ^ int.from_bytes(data[i:i + 16], "big"), h)
    return y


def _j0(sched, h, iv):
    if len(iv) == 12:
        return iv + b"\x00\x00\x00\x01"
    block = _pad16(iv) + b"\x00" * 8 + (len(iv) * 8).to_bytes(8, "big")
    return _ghash(h, block).to_bytes(16, "big")


def _ctr_xor(sched, j0, data):
    prefix, ctr = j0[:12], int.from_bytes(j0[12:], "big")
    out = bytearray(len(data))
    for n, off in enumerate(range(0, len(data), 16)):
        ks = _enc_block(sched, prefix + ((ctr + 1 + n) & 0xFFFFFFFF).to_bytes(4, "big"))
        chunk = data[off:off + 16]
        for i, byte in enumerate(chunk):
            out[off + i] = byte ^ ks[i]
    return bytes(out)


def _tag(sched, h, j0, aad, ciphertext):
    lens = (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(8, "big")
    s = _ghash(h, _pad16(aad) + _pad16(ciphertext) + lens)
    ek = int.from_bytes(_enc_block(sched, j0), "big")
    return (s ^ ek).to_bytes(16, "big")


def _setup(key, iv):
    if len(key) not in (16, 24, 32):
        raise ValueError("khoa AES phai 16/24/32 byte")
    if not iv:
        raise ValueError("IV rong")
    sched = _A._expand_key(key)
    h = int.from_bytes(_enc_block(sched, b"\x00" * 16), "big")
    return sched, h, _j0(sched, h, iv)


def encrypt(key, iv, aad, plaintext):
    """-> ciphertext || tag (16 byte)."""
    sched, h, j0 = _setup(key, iv)
    ct = _ctr_xor(sched, j0, plaintext)
    return ct + _tag(sched, h, j0, aad, ct)


def decrypt(key, iv, aad, data):
    """data = ciphertext || tag. Sai thẻ (dữ liệu bị sửa / sai khoá) thì ném ValueError, KHÔNG trả bản giải mã."""
    if len(data) < TAG_LEN:
        raise ValueError("du lieu ngan hon the xac thuc")
    sched, h, j0 = _setup(key, iv)
    ct, tag = data[:-TAG_LEN], data[-TAG_LEN:]
    if not hmac.compare_digest(_tag(sched, h, j0, aad, ct), tag):
        raise ValueError("sai the xac thuc GCM")
    return _ctr_xor(sched, j0, ct)
