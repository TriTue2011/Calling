"""Tests for stream audio I/O (pipe/stdin/stdout/socket path).

No /dev/snd is assumed: streams are plain binary file objects
(io.BytesIO here; a pipe or socket file object in production).
"""

import io

from zalo_call.audio import (
    FRAME_BYTES,
    StreamMicSource,
    StreamSpeakerSink,
)


def test_stream_mic_reads_full_frames():
    data = bytes(range(256)) * (FRAME_BYTES * 2 // 256 + 1)
    data = data[: FRAME_BYTES * 2]
    src = StreamMicSource(io.BytesIO(data))
    assert src.read_frame() == data[:FRAME_BYTES]
    assert src.read_frame() == data[FRAME_BYTES:]
    assert src.read_frame() == b""  # EOF


def test_stream_mic_buffers_short_reads():
    # A stream that dribbles bytes must still yield full frames.
    class Dribble(io.RawIOBase):
        def __init__(self, data):
            self._data = data
            self._pos = 0

        def readable(self):
            return True

        def read(self, n=-1):
            if self._pos >= len(self._data):
                return b""
            chunk = self._data[self._pos : self._pos + 7]
            self._pos += len(chunk)
            return chunk

    data = b"\x55" * FRAME_BYTES
    src = StreamMicSource(Dribble(data))
    assert src.read_frame() == data


def test_stream_mic_drops_trailing_partial_frame():
    src = StreamMicSource(io.BytesIO(b"\x01" * (FRAME_BYTES + 100)))
    assert src.read_frame() == b"\x01" * FRAME_BYTES
    assert src.read_frame() == b""  # partial trailing frame dropped


def test_stream_speaker_writes_and_flushes():
    buf = io.BytesIO()
    sink = StreamSpeakerSink(buf)
    frame = b"\x02" * FRAME_BYTES
    sink.write_frame(frame)
    assert buf.getvalue() == frame


def test_stream_roundtrip_mic_to_speaker():
    data = bytes([0x10, 0x20]) * (FRAME_BYTES // 2)
    src = StreamMicSource(io.BytesIO(data))
    out = io.BytesIO()
    sink = StreamSpeakerSink(out)
    frame = src.read_frame()
    assert frame == data
    sink.write_frame(frame)
    assert out.getvalue() == data
