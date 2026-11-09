"""Media layer: abstract audio I/O, Opus codec (ctypes libopus), media packets.

Status, stated honestly (bao-cao.md §7, pcap report):
- Media rides a ZRTP relay over UDP port 4200, 20 ms frames at
  48 kHz, header type 03 (uplink) / 04 (downlink). The packet
  header is implemented here (MediaPacket); the relay payload
  format (whether it embeds a full RTP packet) is NOT pinned —
  see srtp.py's integration-gap note before wiring SRTP into
  the relay path.
- Opus encode/decode is REAL: it binds libopus.so (x86-64, v1.4)
  via ctypes — no opuslib needed. If libopus is absent, OpusCodec
  raises OpusUnavailable (a clear error, not a silent stub).
- SRTP protect/unprotect is REAL (libsrtp2 via ctypes, see
  srtp.SrtpSession): AES-CM-128-HMAC-SHA1-80 and AES-GCM
  128/256 suites, standard RTP packets. Keys are injected from
  call setup, never generated here.
- Mic/speaker are ABSTRACT interfaces. File/Silent/Null/stream
  implementations are provided; a real device mic/speaker or a
  TTS source is injected by the outer layer (TtsSource wraps a
  caller-supplied synthesize(text) -> PCM-bytes callable).
  Stream sources/sinks take any binary stream (pipe, stdin/stdout,
  socket file object) so HA/R1 can feed audio in and out — the
  container is deliberately NOT assumed to have /dev/snd (on the
  server, mic/speaker live at HA/R1, not in the container).
"""

import ctypes
import ctypes.util
import logging
import struct
import threading
import time
from abc import ABC, abstractmethod

from zalo_call.errors import OpusUnavailable, SrtpUnavailable, ZaloCallError
from zalo_call.srtp import SrtpSession  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)

SAMPLE_RATE = 48000
CHANNELS = 1
FRAME_SAMPLES = 960  # 20 ms @ 48 kHz
FRAME_BYTES = FRAME_SAMPLES * 2  # PCM16 mono
OPUS_APPLICATION_VOIP = 2048


# ------------------------------------------------------------------ audio I/O

class MicSource(ABC):
    """Produces one 20 ms PCM16 mono frame per read_frame() call."""

    @abstractmethod
    def read_frame(self) -> bytes:
        """Return exactly FRAME_BYTES of PCM, or b'' at end-of-stream."""


class SpeakerSink(ABC):
    """Consumes one 20 ms PCM16 mono frame per write_frame() call."""

    @abstractmethod
    def write_frame(self, pcm: bytes) -> None:
        pass


class FileMicSource(MicSource):
    """Reads raw PCM16 mono 48 kHz from a file (loops if loop=True)."""

    def __init__(self, path: str, loop: bool = False) -> None:
        self._f = open(path, "rb")
        self._loop = loop

    def read_frame(self) -> bytes:
        data = self._f.read(FRAME_BYTES)
        if len(data) < FRAME_BYTES:
            if self._loop and data:
                self._f.seek(0)
                data += self._f.read(FRAME_BYTES - len(data))
            else:
                return b""
        return data


class FileSpeakerSink(SpeakerSink):
    """Appends raw PCM16 mono 48 kHz to a file."""

    def __init__(self, path: str) -> None:
        self._f = open(path, "wb")

    def write_frame(self, pcm: bytes) -> None:
        self._f.write(pcm)


class SilentMicSource(MicSource):
    """Endless silence (useful for hold / no-mic paths)."""

    def read_frame(self) -> bytes:
        return b"\x00" * FRAME_BYTES


class StreamMicSource(MicSource):
    """Reads raw PCM16 mono 48 kHz frames from any binary stream.

    The stream may be a pipe, sys.stdin.buffer, or a socket file
    object — this is how HA/R1 feed live audio into the container
    without the container owning /dev/snd. Short reads are
    buffered until a full frame is available; a trailing partial
    frame at EOF is dropped (padding it would inject fake audio).
    """

    def __init__(self, stream) -> None:
        self._stream = stream
        self._buf = bytearray()

    def read_frame(self) -> bytes:
        while len(self._buf) < FRAME_BYTES:
            chunk = self._stream.read(FRAME_BYTES - len(self._buf))
            if not chunk:
                return b""
            self._buf += chunk
        frame = bytes(self._buf[:FRAME_BYTES])
        del self._buf[:FRAME_BYTES]
        return frame


class StreamSpeakerSink(SpeakerSink):
    """Writes raw PCM16 mono 48 kHz frames to any binary stream.

    Each frame is flushed immediately so pipes/sockets deliver
    audio with no extra buffering delay.
    """

    def __init__(self, stream) -> None:
        self._stream = stream

    def write_frame(self, pcm: bytes) -> None:
        self._stream.write(pcm)
        flush = getattr(self._stream, "flush", None)
        if flush is not None:
            flush()


class NullSpeakerSink(SpeakerSink):
    """Discards audio."""

    def write_frame(self, pcm: bytes) -> None:
        pass


class TtsSource(MicSource):
    """Mic source backed by an outer TTS synthesizer.

    synthesize(text) -> bytes must return raw PCM16 mono 48 kHz;
    the last partial frame is zero-padded. The synthesizer itself
    is NOT part of this package.
    """

    def __init__(self, text: str, synthesize) -> None:
        pcm = synthesize(text)
        self._frames = [
            pcm[i : i + FRAME_BYTES] for i in range(0, len(pcm), FRAME_BYTES)
        ]
        if self._frames and len(self._frames[-1]) < FRAME_BYTES:
            self._frames[-1] = self._frames[-1].ljust(FRAME_BYTES, b"\x00")
        self._idx = 0

    def read_frame(self) -> bytes:
        if self._idx >= len(self._frames):
            return b""
        frame = self._frames[self._idx]
        self._idx += 1
        return frame


# ------------------------------------------------------------------ Opus codec

class OpusError(ZaloCallError):
    pass


def _load_libopus():
    name = ctypes.util.find_library("opus") or "libopus.so.0"
    try:
        return ctypes.CDLL(name)
    except OSError as exc:
        raise OpusUnavailable(f"libopus not found ({name}): {exc}") from exc


class OpusCodec:
    """Opus encoder + decoder via ctypes libopus (VOIP, 48 kHz, mono)."""

    def __init__(self) -> None:
        self._lib = _load_libopus()
        lib = self._lib
        lib.opus_encoder_create.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.opus_encoder_create.restype = ctypes.c_void_p
        lib.opus_encode.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int16),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int,
        ]
        lib.opus_encode.restype = ctypes.c_int
        lib.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
        lib.opus_decoder_create.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.opus_decoder_create.restype = ctypes.c_void_p
        lib.opus_decode.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int16),
            ctypes.c_int,
            ctypes.c_int,
        ]
        lib.opus_decode.restype = ctypes.c_int
        lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
        err = ctypes.c_int(0)
        self._enc = lib.opus_encoder_create(
            SAMPLE_RATE, CHANNELS, OPUS_APPLICATION_VOIP, ctypes.byref(err)
        )
        if not self._enc or err.value != 0:
            raise OpusError(f"opus_encoder_create failed: {err.value}")
        self._dec = lib.opus_decoder_create(
            SAMPLE_RATE, CHANNELS, ctypes.byref(err)
        )
        if not self._dec or err.value != 0:
            raise OpusError(f"opus_decoder_create failed: {err.value}")

    def encode(self, pcm: bytes) -> bytes:
        if len(pcm) != FRAME_BYTES:
            raise OpusError(f"encode needs {FRAME_BYTES} bytes, got {len(pcm)}")
        in_buf = (ctypes.c_int16 * FRAME_SAMPLES).from_buffer_copy(pcm)
        out_buf = (ctypes.c_ubyte * 4000)()
        n = self._lib.opus_encode(
            self._enc, in_buf, FRAME_SAMPLES, out_buf, 4000
        )
        if n < 0:
            raise OpusError(f"opus_encode failed: {n}")
        return bytes(out_buf[:n])

    def decode(self, packet: bytes) -> bytes:
        in_buf = (ctypes.c_ubyte * len(packet)).from_buffer_copy(packet)
        out_buf = (ctypes.c_int16 * FRAME_SAMPLES)()
        n = self._lib.opus_decode(
            self._dec, in_buf, len(packet), out_buf, FRAME_SAMPLES, 0
        )
        if n < 0:
            raise OpusError(f"opus_decode failed: {n}")
        return bytes(out_buf)[: n * 2]

    def close(self) -> None:
        if getattr(self, "_enc", None):
            self._lib.opus_encoder_destroy(self._enc)
            self._enc = None
        if getattr(self, "_dec", None):
            self._lib.opus_decoder_destroy(self._dec)
            self._dec = None


# ------------------------------------------------------------------ SRTP

# The real implementation lives in srtp.py (libsrtp2 via ctypes)
# and is re-exported here so existing imports keep working:
#   from zalo_call.audio import SrtpSession
# NOTE: SrtpSession protects STANDARD RTP packets. Whether the
# ZRTP relay payload embeds a full RTP packet is still UNCONFIRMED
# (see srtp.py's integration-gap note); do NOT feed raw Opus
# packets from AudioPipeline into SrtpSession until the
# relay-payload <-> RTP mapping is known.


# ------------------------------------------------------------------ media packets

MEDIA_UPLINK = 0x03
MEDIA_DOWNLINK = 0x04
MEDIA_HEADER_LEN = 9  # type, 0x90, flag, call_byte, seq, ts BE u32


class MediaPacket:
    """ZRTP relay media packet (header only; payload is opaque SRTP).

    Layout (pcap report): [type][0x90][flag][call_byte][seq 1 byte]
    [timestamp 4 bytes big-endian][payload]. Timestamps advance
    +960 per 20 ms frame; seq wraps at 256.
    """

    def __init__(
        self,
        packet_type: int,
        flag: int,
        call_byte: int,
        seq: int,
        timestamp: int,
        payload: bytes,
    ) -> None:
        self.packet_type = packet_type
        self.flag = flag
        self.call_byte = call_byte
        self.seq = seq & 0xFF
        self.timestamp = timestamp & 0xFFFFFFFF
        self.payload = payload

    def build(self) -> bytes:
        return struct.pack(
            "<BBBBB",
            self.packet_type,
            0x90,
            self.flag,
            self.call_byte,
            self.seq,
        ) + struct.pack(">I", self.timestamp) + self.payload

    @classmethod
    def parse(cls, data: bytes) -> "MediaPacket":
        if len(data) < MEDIA_HEADER_LEN:
            raise ZaloCallError("media packet too short")
        ptype, magic, flag, call_byte, seq = struct.unpack_from("<BBBBB", data, 0)
        if magic != 0x90:
            raise ZaloCallError(f"media packet magic 0x{magic:02x} != 0x90")
        (timestamp,) = struct.unpack_from(">I", data, 5)
        return cls(ptype, flag, call_byte, seq, timestamp, data[9:])


# ------------------------------------------------------------------ pipeline

class AudioPipeline:
    """Mic -> Opus encode -> protect -> network send, and the reverse.

    protect/unprotect are injectable callables (bytes -> bytes).
    By default they raise SrtpUnavailable (no session wired in);
    a real call wires SrtpSession.protect/unprotect here — but
    only once the relay-payload <-> RTP mapping is known (see
    srtp.py). Tests pass identity functions explicitly labeled
    test-only.
    """

    def __init__(
        self,
        mic: MicSource,
        speaker: SpeakerSink,
        codec: OpusCodec,
        send_packet,
        protect=None,
        unprotect=None,
    ) -> None:
        self.mic = mic
        self.speaker = speaker
        self.codec = codec
        self.send_packet = send_packet
        self.protect = protect if protect is not None else self._stub_protect
        self.unprotect = (
            unprotect if unprotect is not None else self._stub_unprotect
        )
        self._seq = 0
        self._timestamp = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _stub_protect(data: bytes) -> bytes:
        raise SrtpUnavailable("no SRTP session wired into the pipeline")

    @staticmethod
    def _stub_unprotect(data: bytes) -> bytes:
        raise SrtpUnavailable("no SRTP session wired into the pipeline")

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._mic_loop, name="zalo-audio-mic", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _mic_loop(self) -> None:
        while not self._stop.is_set():
            start = time.monotonic()
            frame = self.mic.read_frame()
            if not frame:
                break
            packet = self.codec.encode(frame)
            protected = self.protect(packet)
            self.send_packet(protected)
            self._seq = (self._seq + 1) & 0xFF
            self._timestamp = (self._timestamp + FRAME_SAMPLES) & 0xFFFFFFFF
            elapsed = time.monotonic() - start
            if elapsed < 0.020:
                time.sleep(0.020 - elapsed)

    def deliver_network_packet(self, data: bytes) -> None:
        """One received (protected) Opus packet -> decode -> speaker."""
        packet = self.unprotect(data)
        pcm = self.codec.decode(packet)
        if len(pcm) == FRAME_BYTES:
            self.speaker.write_frame(pcm)
        elif pcm:
            # Partial decode (PLC edge): pad to a full frame.
            self.speaker.write_frame(pcm.ljust(FRAME_BYTES, b"\x00"))
