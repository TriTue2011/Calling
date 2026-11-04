"""GCM transport tests (test keys only, never real keys)."""

import pytest

from zalo_call.errors import DecryptError
from zalo_call.transport import (
    gcm_decrypt,
    gcm_decrypt_with_retry,
    gcm_encrypt,
)

KEY = bytes(range(32))
OLD_KEY = bytes([0xAA] * 32)


def test_gcm_round_trip():
    frame = gcm_encrypt(KEY, 2, b"hello world")
    wire_type = frame[4]
    assert wire_type == 4  # inner 2 + 2
    inner, plain = gcm_decrypt(KEY, wire_type, frame[5:])
    assert inner == 2
    assert plain == b"hello world"


def test_gcm_wire_type_formula():
    assert gcm_encrypt(KEY, 1, b"x")[4] == 3
    assert gcm_encrypt(KEY, 2, b"x")[4] == 4


def test_gcm_wrong_key_fails():
    frame = gcm_encrypt(KEY, 2, b"secret")
    with pytest.raises(DecryptError):
        gcm_decrypt(bytes([0x55] * 32), frame[4], frame[5:])


def test_gcm_old_key_retry():
    frame = gcm_encrypt(OLD_KEY, 2, b"legacy")
    inner, plain = gcm_decrypt_with_retry(KEY, OLD_KEY, frame[4], frame[5:])
    assert inner == 2
    assert plain == b"legacy"


def test_gcm_old_key_retry_not_applied_above_wire_4():
    frame = gcm_encrypt(OLD_KEY, 2, b"legacy")
    with pytest.raises(DecryptError):
        gcm_decrypt_with_retry(KEY, OLD_KEY, 5, frame[5:])
