"""Error types for the Zalo call client."""


class ZaloCallError(Exception):
    """Base error for all client failures."""


class ChecksumError(ZaloCallError):
    """Raised when a message header checksum does not verify."""


class FrameError(ZaloCallError):
    """Raised on malformed frames (bad length, truncation, absurd size)."""


class DecryptError(ZaloCallError):
    """Raised when no transport scheme can decrypt a frame."""


class HandshakeError(ZaloCallError):
    """Raised when the signaling handshake fails or times out."""


class OpusUnavailable(ZaloCallError):
    """Raised when libopus cannot be loaded for the audio codec."""


class SrtpUnavailable(ZaloCallError):
    """Raised when SRTP protect/unprotect is attempted.

    SRTP is NOT implemented in this release (see audio.SrtpSession):
    there is no libsrtp on the build machine, and the SRTP keying
    material comes from the media handshake, which is not yet done.
    This error is intentional — media must not pretend to work.
    """
