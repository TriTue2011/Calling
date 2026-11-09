"""Opus codec round-trip (skipped when libopus is absent)."""

import pytest

from zalo_call.audio import FRAME_BYTES, OpusCodec
from zalo_call.errors import OpusUnavailable


def test_opus_round_trip():
    try:
        codec = OpusCodec()
    except OpusUnavailable:
        pytest.skip("libopus not present")
    try:
        # A 20 ms sine-ish PCM frame.
        import math
        import struct

        pcm = b"".join(
            struct.pack("<h", int(8000 * math.sin(2 * math.pi * i / 48)))
            for i in range(960)
        )
        assert len(pcm) == FRAME_BYTES
        packet = codec.encode(pcm)
        assert 0 < len(packet) < FRAME_BYTES
        decoded = codec.decode(packet)
        assert len(decoded) == FRAME_BYTES
    finally:
        codec.close()
