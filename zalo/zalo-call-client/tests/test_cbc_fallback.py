"""CBCXor+MD5 fallback tests.

The test cipher is a repeating-key XOR (length-preserving involution).
It stands in for the undocumented real CBCXor construction; these
tests verify the FRAME LAYOUT (cipher + MD5 position, plain-prefix
MD5 input) and the GCM-then-CBC decode order, not the real cipher.
"""

from zalo_call.keyset import KeySet
from zalo_call.transport import (
    cbc_fallback_decrypt,
    cbc_fallback_encrypt,
    decrypt_wire_frame,
    gcm_encrypt,
)


def _xor_cipher(key: bytes):
    def fn(data: bytes) -> bytes:
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

    return fn


def test_cbc_layout_round_trip():
    cipher = _xor_cipher(b"testkey")
    frame = cbc_fallback_encrypt(2, b"hello cbc", cipher)
    assert frame[4] == 4  # inner 2 + 2 (GCM slot, documented)
    payload = frame[5:]
    # Last 16 bytes are the MD5; the rest is the cipher.
    assert len(payload) == len(b"hello cbc") + 16
    plain = cbc_fallback_decrypt(2, payload, cipher)
    assert plain == b"hello cbc"


def test_cbc_md5_mismatch_rejected():
    cipher = _xor_cipher(b"testkey")
    frame = bytearray(cbc_fallback_encrypt(2, b"hello", cipher))
    frame[-1] ^= 0xFF  # corrupt MD5
    try:
        cbc_fallback_decrypt(2, bytes(frame[5:]), cipher)
    except Exception as exc:
        assert "MD5" in str(exc)
    else:
        raise AssertionError("expected MD5 mismatch")


def test_decode_tries_gcm_then_cbc():
    key = bytes(range(32))
    cipher = _xor_cipher(b"testkey")
    ks = KeySet(transport_key=key)
    # A GCM frame decodes via GCM.
    gcm_frame = gcm_encrypt(key, 2, b"via gcm")
    inner, plain = decrypt_wire_frame(
        ks, 4, gcm_frame[5:], cbc_cipher=cipher
    )
    assert (inner, plain) == (2, b"via gcm")
    # A CBC frame (same wire slot) falls through to CBC.
    cbc_frame = cbc_fallback_encrypt(2, b"via cbc", cipher)
    inner, plain = decrypt_wire_frame(
        ks, 4, cbc_frame[5:], cbc_cipher=cipher
    )
    assert (inner, plain) == (2, b"via cbc")
