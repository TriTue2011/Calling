"""Media packet header tests (seq wrap, timestamp +960)."""

import pytest

from zalo_call.audio import MEDIA_DOWNLINK, MEDIA_UPLINK, MediaPacket
from zalo_call.errors import ZaloCallError


def test_media_packet_round_trip():
    pkt = MediaPacket(MEDIA_UPLINK, 0x01, 0xAB, 7, 123456, b"payload")
    parsed = MediaPacket.parse(pkt.build())
    assert parsed.packet_type == MEDIA_UPLINK
    assert parsed.flag == 0x01
    assert parsed.call_byte == 0xAB
    assert parsed.seq == 7
    assert parsed.timestamp == 123456
    assert parsed.payload == b"payload"


def test_media_packet_seq_wraps_at_256():
    pkt = MediaPacket(MEDIA_DOWNLINK, 0, 0, 300, 0, b"")
    assert pkt.seq == 44  # 300 mod 256


def test_media_packet_timestamp_steps():
    packets = [
        MediaPacket(MEDIA_UPLINK, 0, 0, i, i * 960, b"") for i in range(5)
    ]
    timestamps = [p.timestamp for p in packets]
    assert timestamps == [0, 960, 1920, 2880, 3840]


def test_media_packet_bad_magic_rejected():
    data = bytes([0x03, 0x91, 0, 0, 0]) + (0).to_bytes(4, "big")
    with pytest.raises(ZaloCallError):
        MediaPacket.parse(data)
