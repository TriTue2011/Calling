"""Tests for real SRTP via libsrtp2 (ctypes).

All vectors are self-generated (test keys, test RTP packets);
nothing here touches a Zalo server or a real account. If libsrtp2
is absent the tests skip (the Dockerfile installs libsrtp2-1).
"""

import struct

import pytest

try:
    from zalo_call.errors import SrtpError
    from zalo_call.srtp import SrtpSession

    _HAS_SRTP = True
except Exception:  # noqa: BLE001
    _HAS_SRTP = False

pytestmark = pytest.mark.skipif(
    not _HAS_SRTP, reason="libsrtp2 not importable on this machine"
)

RTP_HDR = struct.pack(">BBHII", 0x80, 111, 7, 960, 12345)
PAYLOAD = b"opus-payload-1234"
PACKET = RTP_HDR + PAYLOAD


def _session(suite, keylen):
    return SrtpSession(bytes(range(keylen)), suite=suite)


@pytest.mark.parametrize(
    "suite,keylen",
    [
        ("aes_cm_128_hmac_sha1_80", 30),
        ("aes_cm_128_hmac_sha1_32", 30),
        ("aes_gcm_128_16_auth", 28),
        ("aes_gcm_256_16_auth", 44),
    ],
)
def test_roundtrip(suite, keylen):
    with _session(suite, keylen) as sess:
        protected = sess.protect(PACKET)
        assert protected != PACKET
        assert sess.unprotect(protected) == PACKET


@pytest.mark.parametrize(
    "suite,keylen",
    [
        ("aes_cm_128_hmac_sha1_80", 30),
        ("aes_gcm_256_16_auth", 44),
    ],
)
def test_tamper_rejected(suite, keylen):
    # Tamper on a FRESH session so the failure is auth, not replay.
    with _session(suite, keylen) as tx:
        protected = tx.protect(PACKET)
    bad = bytearray(protected)
    bad[15] ^= 0xFF  # inside the payload
    with _session(suite, keylen) as rx:
        with pytest.raises(SrtpError):
            rx.unprotect(bytes(bad))


@pytest.mark.parametrize(
    "suite,keylen",
    [
        ("aes_cm_128_hmac_sha1_80", 30),
        ("aes_gcm_256_16_auth", 44),
    ],
)
def test_replay_rejected(suite, keylen):
    with _session(suite, keylen) as sess:
        protected = sess.protect(PACKET)
        assert sess.unprotect(protected) == PACKET
        with pytest.raises(SrtpError):
            sess.unprotect(protected)


def test_wrong_key_length_rejected():
    with pytest.raises(SrtpError):
        SrtpSession(bytes(29), suite="aes_cm_128_hmac_sha1_80")


def test_unknown_suite_rejected():
    with pytest.raises(SrtpError):
        SrtpSession(bytes(30), suite="no-such-suite")


def test_short_packet_rejected():
    with _session("aes_cm_128_hmac_sha1_80", 30) as sess:
        with pytest.raises(SrtpError):
            sess.protect(b"\x80\x6f\x00")


def test_context_manager_closes():
    sess = _session("aes_cm_128_hmac_sha1_80", 30)
    with sess:
        assert sess.protect(PACKET)
    assert sess._tx is None
