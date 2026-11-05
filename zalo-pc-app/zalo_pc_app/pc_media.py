"""PC media adapter: Opus 16 kHz + SRTP hooks + engine for the seam.

This module wires `Udp4200Transport` (see `udp_transport.py`,
agent A) to the `MediaEngineSeam` contract in `engine_seam.py`
(`.start()` / `.stop()` / `.pcm_out_frames()` / `.send_pcm(bytes)`
/ `.status()`, PCM 16 kHz mono 16-bit LE, 20 ms frames = 640 bytes).

Why this file exists instead of reusing `zalo-call-client`:
  * `zalo_call/audio.py` is built for the MOBILE path: Opus at
    48 kHz (`FRAME_BYTES` 1920, timestamp +960/frame) and a
    9-byte `MediaPacket` header. The PC wire format is 16 kHz
    (timestamp +320/frame, 20-byte RTP header) — reusing the
    mobile `AudioPipeline`/`MediaPacket` would send wrong
    timestamps and a wrong header. The transport owns RTP
    seq/timestamp itself; this module only supplies the
    `encode_frame` / `decode_frame` hooks (Opus 16 kHz) and the
    `protect_rtp` / `unprotect_rtp` hooks (SRTP) that the
    transport calls.
  * `zalo_call/srtp.py` (`SrtpSession`, libsrtp2 via ctypes) is
    NOT vendored into the app image: the app PC Dockerfile is
    stdlib-only and its CI context (`./zalo-pc-app`) copies only
    `zalo_pc_app/` (packaging decision (b) — see the final
    report). `make_srtp_hooks` therefore imports `zalo_call.srtp`
    LAZILY and raises a clear error when libsrtp2 / the package
    is absent; the transport still starts for the handshake
    without hooks, and media stays unwired until the hooks are
    injected. Nothing here imports libopus/libsrtp2 at module
    load time.

SRTP key (read before wiring a real call):
  The key comes from response 11300 `zrtc_config.srtpKey` — a
  STRING whose format and length are UNCONFIRMED (disassembly:
  `srtpKey` is a plain string field of `zrtc_config`, no length
  limit in the parser). LIVE 2026-11-06: the real 11300
  `zrtc_config` carries NO `srtpKey` at all, so a real call
  currently has no key to wire — signaling proceeds
  handshake-only (`media_endpoints` reports srtp "not-wired")
  and the key source is still OPEN (it may live inside the
  115-byte token, in `settings`/`msg`, or be issued separately
  by the server). `media_hooks_for_call` converts it
  best-effort: raw `bytes` are used as-is; a `str` is tried as
  base64url first, then as UTF-8 — and the result MUST match the
  suite's exact key-material length (30 bytes for
  `aes_cm_128_hmac_sha1_80`), otherwise it raises naming the
  expected length. If the real `srtpKey` turns out to be some
  other encoding, this conversion — not the transport — is where
  it gets fixed. The key VALUE is never logged.
"""

import ctypes
import ctypes.util
import queue
import threading

FRAME_SAMPLES = 320            # 20 ms @ 16 kHz mono
FRAME_BYTES = FRAME_SAMPLES * 2  # PCM16 mono LE: 640 bytes/frame
SAMPLE_RATE = 16000
CHANNELS = 1
OPUS_APPLICATION_VOIP = 2048

# Key-material lengths per libsrtp2 suite (see zalo_call/srtp.py).
_SUITE_KEY_LEN = {
    "aes_cm_128_hmac_sha1_80": 30,
    "aes_cm_128_hmac_sha1_32": 30,
    "aes_gcm_128_16_auth": 28,
    "aes_gcm_256_16_auth": 44,
}


class OpusUnavailable(Exception):
    """libopus is not loadable in this environment."""


class SrtpUnavailable(Exception):
    """libsrtp2 / zalo_call.srtp is not available in this build."""


# ------------------------------------------------------------------ Opus 16k

def _load_libopus():
    name = ctypes.util.find_library("opus") or "libopus.so.0"
    try:
        return ctypes.CDLL(name)
    except OSError as exc:
        raise OpusUnavailable(
            "libopus not found (%s): %s — on Debian install "
            "libopus0; the app PC image does not bundle it yet "
            "(packaging decision (b))" % (name, exc)) from exc


class Opus16kCodec:
    """Opus encoder + decoder at 16 kHz mono via ctypes libopus.

    Same binding shape as `zalo_call.audio.OpusCodec`, but at the
    PC sample rate (16000 Hz, 320-sample frames). Created lazily:
    constructing one loads libopus and raises `OpusUnavailable`
    with a clear message when it is absent, instead of failing
    at import time.
    """

    def __init__(self):
        self._lib = _load_libopus()
        lib = self._lib
        lib.opus_encoder_create.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int)]
        lib.opus_encoder_create.restype = ctypes.c_void_p
        lib.opus_encode.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16),
            ctypes.c_int, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
        lib.opus_encode.restype = ctypes.c_int
        lib.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
        lib.opus_decoder_create.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        lib.opus_decoder_create.restype = ctypes.c_void_p
        lib.opus_decode.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int, ctypes.POINTER(ctypes.c_int16),
            ctypes.c_int, ctypes.c_int]
        lib.opus_decode.restype = ctypes.c_int
        lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
        err = ctypes.c_int(0)
        self._enc = lib.opus_encoder_create(
            SAMPLE_RATE, CHANNELS, OPUS_APPLICATION_VOIP,
            ctypes.byref(err))
        if not self._enc or err.value != 0:
            raise OpusUnavailable(
                "opus_encoder_create failed: %d" % err.value)
        self._dec = lib.opus_decoder_create(
            SAMPLE_RATE, CHANNELS, ctypes.byref(err))
        if not self._dec or err.value != 0:
            raise OpusUnavailable(
                "opus_decoder_create failed: %d" % err.value)

    def encode(self, pcm):
        """One 640-byte PCM frame -> Opus packet bytes."""
        if len(pcm) != FRAME_BYTES:
            raise ValueError(
                "opus encode needs one %d-byte frame, got %d"
                % (FRAME_BYTES, len(pcm)))
        in_buf = (ctypes.c_int16 * FRAME_SAMPLES).from_buffer_copy(pcm)
        out_buf = (ctypes.c_ubyte * 4000)()
        n = self._lib.opus_encode(self._enc, in_buf, FRAME_SAMPLES,
                                  out_buf, 4000)
        if n < 0:
            raise OpusUnavailable("opus_encode failed: %d" % n)
        return bytes(out_buf[:n])

    def decode(self, packet):
        """One Opus packet -> one 640-byte PCM frame (zero-padded
        when the decoder returns fewer than 320 samples, e.g. PLC
        edge; truncated if more — a 20 ms frame at 16 kHz)."""
        if not packet:
            return b"\x00" * FRAME_BYTES
        in_buf = (ctypes.c_ubyte * len(packet)).from_buffer_copy(packet)
        out_buf = (ctypes.c_int16 * FRAME_SAMPLES)()
        n = self._lib.opus_decode(self._dec, in_buf, len(packet),
                                  out_buf, FRAME_SAMPLES, 0)
        if n < 0:
            raise OpusUnavailable("opus_decode failed: %d" % n)
        pcm = bytes(out_buf)[:n * 2]
        if len(pcm) < FRAME_BYTES:
            pcm = pcm.ljust(FRAME_BYTES, b"\x00")
        return pcm

    def close(self):
        if getattr(self, "_enc", None):
            self._lib.opus_encoder_destroy(self._enc)
            self._enc = None
        if getattr(self, "_dec", None):
            self._lib.opus_decoder_destroy(self._dec)
            self._dec = None


# ------------------------------------------------------------------ SRTP hooks

def _srtp_key_to_material(srtp_key, suite):
    """Convert a `zrtc_config.srtpKey` value to exact key material.

    `bytes` are used as-is. A `str` is tried as base64url (the
    token's encoding — UNCONFIRMED for the key) and then as
    UTF-8. The result must be exactly the suite's key-material
    length, else ValueError naming the expected length. NOTHING
    is guessed beyond that: a key that fits no suite length is
    rejected loudly instead of being truncated or padded.
    """
    need = _SUITE_KEY_LEN[suite]
    if isinstance(srtp_key, (bytes, bytearray)):
        raw = bytes(srtp_key)
    elif isinstance(srtp_key, str):
        import base64
        import binascii
        raw = None
        try:
            padded = srtp_key + "=" * (-len(srtp_key) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            if len(decoded) == need:
                raw = decoded
        except (binascii.Error, ValueError, UnicodeEncodeError):
            raw = None
        if raw is None:
            raw = srtp_key.encode("utf-8")
    else:
        raise ValueError(
            "srtp_key: must be bytes or str, got %r" % type(srtp_key))
    if len(raw) != need:
        raise ValueError(
            "srtp_key: %d bytes of key material, suite %s needs %d "
            "(srtpKey format from zrtc_config is UNCONFIRMED; "
            "neither truncation nor padding is applied)"
            % (len(raw), suite, need))
    return raw


def make_srtp_hooks(srtp_key, suite="aes_cm_128_hmac_sha1_80"):
    """Build (protect_rtp, unprotect_rtp) from an SRTP key.

    The hooks take/return COMPLETE RTP packets including the
    20-byte header — exactly the contract `TransportConfig`
    expects. Requires `zalo_call.srtp.SrtpSession` (libsrtp2);
    raises `SrtpUnavailable` with a clear message when it is
    absent, and ValueError when the key does not fit the suite.
    """
    if suite not in _SUITE_KEY_LEN:
        raise ValueError("unknown SRTP suite %r (known: %s)"
                         % (suite, sorted(_SUITE_KEY_LEN)))
    material = _srtp_key_to_material(srtp_key, suite)
    try:
        from zalo_call.srtp import SrtpSession
    except ImportError as exc:
        raise SrtpUnavailable(
            "zalo_call.srtp (libsrtp2) is not available in this "
            "build: %s — the app PC image is stdlib-only "
            "(packaging decision (b)); SRTP hooks must be injected "
            "from a build that bundles libsrtp2-1" % exc) from exc
    session = SrtpSession(material, suite=suite)
    return session.protect, session.unprotect


def media_hooks_for_call(srtp_key, suite="aes_cm_128_hmac_sha1_80",
                         codec=None):
    """Build all four media hooks for one call's TransportConfig.

    Returns {"protect_rtp", "unprotect_rtp", "encode_frame",
    "decode_frame"} — Opus 16 kHz (`codec` or a fresh
    `Opus16kCodec`) + SRTP (`make_srtp_hooks`). Raises
    `OpusUnavailable` / `SrtpUnavailable` / ValueError with a
    clear message when a piece is missing; the caller
    (`server.py`) treats that as "handshake-only" and never lets
    it break signaling.
    """
    codec = codec or Opus16kCodec()
    protect, unprotect = make_srtp_hooks(srtp_key, suite=suite)
    return {"protect_rtp": protect, "unprotect_rtp": unprotect,
            "encode_frame": codec.encode,
            "decode_frame": codec.decode}


# ------------------------------------------------------------------ engine

class PcMediaEngine:
    """Media engine for one started transport (seam contract).

    The transport (already started by `MediaEndpoints.for_call`,
    with its Opus/SRTP hooks baked into its config) owns RTP
    seq/timestamp, the relay/P2P switch and the jitter buffer.
    This class only adapts it to the seam: `send_pcm` forwards
    640-byte PCM frames to `transport.send_pcm`, and the
    transport's PCM callback feeds `pcm_out_frames()` — PCM
    16 kHz mono 16-bit LE, the format HA/R1 consume.

    `attach(call_info)` returns self (seam contract). `start()`
    registers the PCM callback (and starts the transport if it
    is still idle, e.g. in tests). `stop()` is idempotent.
    """

    def __init__(self, transport, queue_size=50):
        self.transport = transport
        self._queue = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._started = False
        self._dropped = 0
        self._received = 0
        self._sent = 0
        self.call_info = None

    def attach(self, call_info):
        self.call_info = call_info
        return self

    def start(self):
        if not self._started:
            self.transport.set_pcm_callback(self._on_pcm)
            if getattr(self.transport, "state", None) == "idle":
                self.transport.start()
            self._started = True
        return self

    def stop(self):
        self._stop.set()
        try:
            self.transport.stop()
        except Exception:  # noqa: BLE001 - stop is best-effort
            pass
        return self

    def send_pcm(self, pcm):
        """Push microphone PCM into the call (640 bytes / 20 ms
        frame; longer buffers must be split by the caller).
        Raises the transport's error when media cannot be sent
        (no relay selected yet, no SRTP hook, wrong frame size).
        """
        self.transport.send_pcm(pcm)
        self._sent += 1

    def pcm_out_frames(self):
        """Generator of received PCM frames (640 bytes each) until
        `stop()` is called. Silent while no frames arrive."""
        while not self._stop.is_set():
            try:
                yield self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

    def read_frame(self, timeout=1.0):
        """One received PCM frame, or None on timeout/stop."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def status(self):
        try:
            transport_status = self.transport.status()
        except Exception as exc:  # noqa: BLE001 - status never raises
            transport_status = {"error": str(exc)}
        return {"attached": True, "started": self._started,
                "queued": self._queue.qsize(),
                "received_frames": self._received,
                "sent_frames": self._sent,
                "dropped_frames": self._dropped,
                "transport": transport_status}

    def _on_pcm(self, frame):
        self._received += 1
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            self._dropped += 1
