"""SRTP protect/unprotect via the system libsrtp2 library (ctypes).

This is REAL SRTP, not a stub: packets are protected with the
libsrtp2 C library (Debian package libsrtp2-1, present on both
amd64 and arm64 bookworm), using the standard RTP packet format
(12-byte header + payload). The binding was verified empirically
against libsrtp2 2.5.0: the srtp_policy_t layout (128 bytes) and
the ssrc type enum (specific=1, any_inbound=2, any_outbound=3)
were taken from /usr/include/srtp2/srtp.h, and round-trips were
tested for every suite below (tampered packets fail auth, replayed
packets fail replay protection).

Supported suites (key material = master key || master salt):
    aes_cm_128_hmac_sha1_80  AES-CM-128 + HMAC-SHA1, 10-byte tag
                             (via srtp_crypto_policy_set_rtp_default;
                             libsrtp2 does NOT export a dedicated
                             ..._128_hmac_sha1_80 setter).
                             Key material: 30 bytes (16 key + 14 salt).
    aes_cm_128_hmac_sha1_32  AES-CM-128 + HMAC-SHA1, 4-byte tag.
                             Key material: 30 bytes.
    aes_gcm_128_16_auth      AES-GCM-128, 16-byte tag.
                             Key material: 28 bytes (16 key + 12 salt).
    aes_gcm_256_16_auth      AES-GCM-256, 16-byte tag.
                             Key material: 44 bytes (32 key + 12 salt).

Key material is injected by the caller (from call setup) and is
never generated, stored, or logged here.

INTEGRATION GAP (read before wiring this into the media path):
SrtpSession protects STANDARD RTP packets. Whether the Zalo relay
payload (the 9-byte ZRTP relay header + opaque bytes, see audio.py)
embeds a full RTP packet or applies SRTP-style crypto with
non-RTP framing is NOT pinned in the disassembly/pcap reports —
the relay payload is opaque there. So this module proves the SRTP
primitive works, but the relay-payload <-> RTP mapping is still a
TODO that needs a real call (or further libzrtc analysis) to close.
AudioPipeline.protect/unprotect currently receive raw Opus
packets; do NOT feed those directly into SrtpSession until the
mapping is known — an RTP header must be built first.
"""

import ctypes
import ctypes.util
import threading

from zalo_call.errors import SrtpError, SrtpUnavailable

_LIB_NAMES = ("libsrtp2.so.1", "libsrtp2.so")
_ERR_NAMES = {
    0: "ok",
    1: "fail",
    2: "bad_param",
    3: "alloc_fail",
    4: "dealloc_fail",
    5: "init_fail",
    6: "terminus",
    7: "auth_fail",
    8: "cipher_fail",
    9: "replay_fail",
    10: "replay_old",
    11: "algo_fail",
    12: "no_such_op",
    13: "no_ctx",
    14: "cant_check",
    15: "key_expired",
}

# srtp_ssrc_type_t (srtp.h): undefined=0, specific=1,
# any_inbound=2 (unprotect), any_outbound=3 (protect).
_SSRC_ANY_INBOUND = 2
_SSRC_ANY_OUTBOUND = 3

# Suite table: name -> (policy setter symbol, key material length).
# The AES-CM-128-HMAC-SHA1-80 suite has no dedicated setter symbol
# in libsrtp2; srtp_crypto_policy_set_rtp_default sets exactly that
# suite (verified: cipher_key_len=30, auth_tag_len=10 after the call).
_SUITES = {
    "aes_cm_128_hmac_sha1_80": ("srtp_crypto_policy_set_rtp_default", 30),
    "aes_cm_128_hmac_sha1_32": (
        "srtp_crypto_policy_set_aes_cm_128_hmac_sha1_32",
        30,
    ),
    "aes_gcm_128_16_auth": ("srtp_crypto_policy_set_aes_gcm_128_16_auth", 28),
    "aes_gcm_256_16_auth": ("srtp_crypto_policy_set_aes_gcm_256_16_auth", 44),
}

_TRAILER_ROOM = 64  # headroom for auth tag / SRTP trailer on protect


class _CryptoPolicy(ctypes.Structure):
    _fields_ = [
        ("cipher_type", ctypes.c_int),
        ("cipher_key_len", ctypes.c_int),
        ("auth_type", ctypes.c_int),
        ("auth_key_len", ctypes.c_int),
        ("auth_tag_len", ctypes.c_int),
        ("sec_serv", ctypes.c_int),
    ]


class _Ssrc(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("value", ctypes.c_uint32)]


class _Policy(ctypes.Structure):
    # Exact libsrtp 2.5.0 srtp_policy_t layout (srtp.h); ctypes
    # computes the padding (128 bytes total). The extra fields
    # (keys, num_master_keys, deprecated_ekt, enc_xtn_hdr*) are
    # left NULL/0, which is the single-master-key configuration.
    _fields_ = [
        ("ssrc", _Ssrc),
        ("rtp", _CryptoPolicy),
        ("rtcp", _CryptoPolicy),
        ("key", ctypes.c_void_p),
        ("keys", ctypes.c_void_p),
        ("num_master_keys", ctypes.c_ulong),
        ("deprecated_ekt", ctypes.c_void_p),
        ("window_size", ctypes.c_ulong),
        ("allow_repeat_tx", ctypes.c_int),
        ("enc_xtn_hdr", ctypes.c_void_p),
        ("enc_xtn_hdr_count", ctypes.c_int),
        ("next", ctypes.c_void_p),
    ]


_lib = None
_lib_lock = threading.Lock()


def _load_libsrtp():
    global _lib
    with _lib_lock:
        if _lib is not None:
            return _lib
        last_exc = None
        for name in _LIB_NAMES:
            try:
                _lib = ctypes.CDLL(name)
                break
            except OSError as exc:
                last_exc = exc
        if _lib is None:
            raise SrtpUnavailable(
                f"libsrtp2 not found (tried {_LIB_NAMES}): {last_exc}. "
                "On Debian bookworm install package libsrtp2-1."
            )
        lib = _lib
        lib.srtp_init.restype = ctypes.c_int
        lib.srtp_init.argtypes = []
        lib.srtp_create.restype = ctypes.c_int
        lib.srtp_create.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(_Policy),
        ]
        lib.srtp_protect.restype = ctypes.c_int
        lib.srtp_protect.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.srtp_unprotect.restype = ctypes.c_int
        lib.srtp_unprotect.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.srtp_dealloc.restype = ctypes.c_int
        lib.srtp_dealloc.argtypes = [ctypes.c_void_p]
        rc = lib.srtp_init()
        if rc != 0:
            raise SrtpError(f"srtp_init failed: {_ERR_NAMES.get(rc, rc)}")
        return _lib


def _check(rc: int, op: str) -> None:
    if rc != 0:
        raise SrtpError(f"srtp {op} failed: {_ERR_NAMES.get(rc, rc)}")


class SrtpSession:
    """Bidirectional SRTP session (libsrtp2) for one key/suite.

    Two underlying libsrtp sessions are held: a transmit session
    (ssrc_any_outbound) for protect() and a receive session
    (ssrc_any_inbound) for unprotect(). Both use the same key
    material, mirroring a call leg whose two directions share one
    master key; if a real call setup yields per-direction keys,
    construct one SrtpSession per direction instead.

    Keys are injected, never generated here. protect() takes a
    complete RTP packet (>= 12-byte header) and returns the
    protected packet (payload encrypted + auth tag appended).
    """

    def __init__(
        self,
        key_material: bytes,
        suite: str = "aes_cm_128_hmac_sha1_80",
        window_size: int = 128,
    ) -> None:
        if suite not in _SUITES:
            raise SrtpError(
                f"unknown SRTP suite {suite!r} (known: {sorted(_SUITES)})"
            )
        setter_name, key_len = _SUITES[suite]
        if len(key_material) != key_len:
            raise SrtpError(
                f"suite {suite} needs {key_len} bytes of key material, "
                f"got {len(key_material)}"
            )
        lib = _load_libsrtp()
        self._lib = lib
        self.suite = suite
        self._key_buf = ctypes.create_string_buffer(key_material)
        self._tx = self._create_session(
            lib, setter_name, _SSRC_ANY_OUTBOUND, window_size
        )
        try:
            self._rx = self._create_session(
                lib, setter_name, _SSRC_ANY_INBOUND, window_size
            )
        except Exception:
            lib.srtp_dealloc(self._tx)
            self._tx = None
            raise

    def _create_session(self, lib, setter_name, ssrc_type, window_size):
        try:
            setter = getattr(lib, setter_name)
        except AttributeError as exc:
            raise SrtpUnavailable(
                f"libsrtp2 lacks policy setter {setter_name}: {exc}"
            ) from exc
        setter.argtypes = [ctypes.POINTER(_CryptoPolicy)]
        setter.restype = None
        pol = _Policy()
        setter(ctypes.byref(pol.rtp))
        setter(ctypes.byref(pol.rtcp))
        pol.ssrc.type = ssrc_type
        pol.ssrc.value = 0
        pol.key = ctypes.cast(self._key_buf, ctypes.c_void_p)
        pol.window_size = window_size
        sess = ctypes.c_void_p()
        rc = lib.srtp_create(ctypes.byref(sess), ctypes.byref(pol))
        _check(rc, "create")
        return sess

    def protect(self, rtp_packet: bytes) -> bytes:
        """Protect one RTP packet (encrypt + authenticate)."""
        if len(rtp_packet) < 12:
            raise SrtpError("RTP packet too short (< 12-byte header)")
        buf = ctypes.create_string_buffer(
            rtp_packet + b"\x00" * _TRAILER_ROOM,
            len(rtp_packet) + _TRAILER_ROOM,
        )
        length = ctypes.c_int(len(rtp_packet))
        rc = self._lib.srtp_protect(self._tx, buf, ctypes.byref(length))
        _check(rc, "protect")
        return buf.raw[: length.value]

    def unprotect(self, protected: bytes) -> bytes:
        """Verify + decrypt one protected RTP packet.

        Raises SrtpError on auth failure (tampered packet) or
        replay failure (same packet unprotected twice on this
        session) — both are real libsrtp behaviors, not stubs.
        """
        if len(protected) < 12:
            raise SrtpError("protected packet too short (< 12-byte header)")
        buf = ctypes.create_string_buffer(
            protected + b"\x00" * _TRAILER_ROOM,
            len(protected) + _TRAILER_ROOM,
        )
        length = ctypes.c_int(len(protected))
        rc = self._lib.srtp_unprotect(self._rx, buf, ctypes.byref(length))
        _check(rc, "unprotect")
        return buf.raw[: length.value]

    def close(self) -> None:
        lib = getattr(self, "_lib", None)
        if lib is None:
            return
        for sess in (getattr(self, "_tx", None), getattr(self, "_rx", None)):
            if sess:
                lib.srtp_dealloc(sess)
        self._tx = None
        self._rx = None
        self._lib = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
