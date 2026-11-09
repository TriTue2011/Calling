"""Framing tests: wire frame arithmetic + FrameReader round-trips."""

import pytest

from zalo_call.errors import FrameError
from zalo_call.transport import FrameReader, encode_plain_frame, encode_wire


def test_plain_frame_layout():
    frame = encode_plain_frame(2, b"abc")
    # L = 1 + 3 = 4, total = 8
    assert frame[:4] == (4).to_bytes(4, "little")
    assert frame[4] == 2
    assert frame[5:] == b"abc"
    assert len(frame) == 8


def test_wire_frame_length_arithmetic():
    for payload_len in (0, 1, 100, 4096):
        frame = encode_wire(7, b"x" * payload_len)
        length = int.from_bytes(frame[:4], "little")
        assert length == 1 + payload_len
        assert len(frame) == 4 + length


def test_frame_reader_round_trip_and_split():
    reader = FrameReader()
    f1 = encode_wire(2, b"hello")
    f2 = encode_wire(3, b"world!")
    combined = f1 + f2
    # Feed byte-by-byte: the first frame completes mid-stream, the
    # second only at the very last byte.
    seen = []
    for byte in combined[:-1]:
        seen.extend(reader.feed(bytes([byte])))
    assert seen == [(2, b"hello")]
    seen.extend(reader.feed(combined[-1:]))
    assert seen == [(2, b"hello"), (3, b"world!")]


def test_frame_reader_rejects_zero_length():
    reader = FrameReader()
    with pytest.raises(FrameError):
        reader.feed((0).to_bytes(4, "little") + b"\x02")


def test_frame_reader_rejects_oversize():
    reader = FrameReader()
    with pytest.raises(FrameError):
        reader.feed((17 * 1024 * 1024).to_bytes(4, "little") + b"\x02")
