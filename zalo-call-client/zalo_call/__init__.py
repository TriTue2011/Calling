"""Zalo call signaling client — pure-Python implementation of the
wire format reverse-engineered from Zalo Android 26.10.02 (static
analysis only, see README.md for sources and status).

This package contains NO credentials, keys, tokens, sessions, or
account identifiers. All key/session material must be injected at
runtime by the caller (see keyset.KeySet); nothing is hardcoded.
"""

from zalo_call.errors import (
    ChecksumError,
    DecryptError,
    FrameError,
    HandshakeError,
    OpusUnavailable,
    SrtpUnavailable,
    ZaloCallError,
)

__version__ = "0.1.0"

__all__ = [
    "ChecksumError",
    "DecryptError",
    "FrameError",
    "HandshakeError",
    "OpusUnavailable",
    "SrtpUnavailable",
    "ZaloCallError",
    "__version__",
]
