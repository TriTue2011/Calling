"""Tests for the Prov KDF hypothesis + Prov A-default behavior.

The identity KDF is a HYPOTHESIS (UNCONFIRMED), not a proven
formula: these tests pin the module's stated behavior, not the
correctness of the hypothesis against a real handshake.
"""

import pytest

from zalo_call.errors import DecryptError, FrameError
from zalo_call.prov_kdf import identity_kdf
from zalo_call.transport import prov_decrypt, prov_encrypt


def test_identity_kdf_returns_secret_unchanged():
    secret = bytes(range(32))
    assert identity_kdf(secret) == secret


def test_identity_kdf_rejects_non_32_byte():
    with pytest.raises(DecryptError):
        identity_kdf(bytes(31))


def test_ecdh_path_defaults_a_to_client_pubkey():
    # Server pubkey: any 32 bytes (X25519 public key format).
    server_pub = bytes(range(32))
    b_field = bytes([0xAB] * 32)
    frame, client_pub = prov_encrypt(
        4,
        b"hello-prov",
        b=b_field,
        server_pubkey=server_pub,
        ecdh_kdf=identity_kdf,
    )
    assert client_pub is not None and len(client_pub) == 32
    # Frame layout: [len u32][inner][wire][gcm...][A][B]; A is the
    # last-but-one 32-byte field and must equal the client pubkey.
    assert frame[-64:-32] == client_pub
    assert frame[-32:] == b_field
    # The frame decrypts with the shared secret: recompute it from
    # the client pubkey + a fresh server private key is not possible
    # here (the server private key is ephemeral-internal), so this
    # test only pins layout + A default, not the KDF hypothesis.


def test_ecdh_path_requires_b():
    with pytest.raises(FrameError):
        prov_encrypt(
            4,
            b"x",
            server_pubkey=bytes(32),
            ecdh_kdf=identity_kdf,
        )


def test_gcm_key_path_still_requires_a_and_b():
    with pytest.raises(FrameError):
        prov_encrypt(4, b"x", b=bytes(32), gcm_key=bytes(32))
    with pytest.raises(FrameError):
        prov_encrypt(4, b"x", a=bytes(32), gcm_key=bytes(32))


def test_gcm_key_path_roundtrip_unchanged():
    key = bytes(range(32))
    a, b = bytes([1] * 32), bytes([2] * 32)
    frame, _ = prov_encrypt(4, b"msg", a, b, gcm_key=key)
    inner, plain, a2, b2 = prov_decrypt(key, 8, frame[5:])
    assert inner == 4 and plain == b"msg" and a2 == a and b2 == b
