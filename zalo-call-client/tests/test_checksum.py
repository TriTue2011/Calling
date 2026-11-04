"""Checksum tests with LITERAL hand-computed vectors.

Vector 1: needAck=1, msgType=1, seqId=100, srcId=200, srcType=3,
opcode=401, subCmd=0.
  sum = 1+1+100+200+3+401+0 = 706 = 0x2c2
  checksum = 0x2c2 XOR 0x6ce7daa0 = 0x6ce7d862
Vector 2 (signed-halfword opcode): opcode wire u16 = 0xFF9C -> -100,
needAck=0, msgType=1, seqId=1, srcId=0, srcType=0, subCmd=0.
  sum = -98 -> 0xFFFFFF9E
  checksum = 0xFFFFFF9E XOR 0x6ce7daa0 = 0x9318253E
"""

import pytest

from zalo_call.errors import ChecksumError
from zalo_call.req import Message, compute_checksum


def test_checksum_vector_1():
    assert compute_checksum(1, 1, 100, 200, 3, 401, 0) == 0x6CE7D862


def test_checksum_vector_2_signed_halfword():
    assert compute_checksum(0, 1, 1, 0, 0, 0xFF9C, 0) == 0x9318253E


def test_req_round_trip_keeps_fields_and_checksum():
    msg = Message(
        version=2,
        need_ack=1,
        msg_type=1,
        seq_id=100,
        src_id=200,
        src_type=3,
        opcode=401,
        sub_cmd=0,
        params=b"\x01\x02",
    )
    raw = msg.build()
    assert raw[4] == 2  # version byte
    assert raw[9] == 1  # needAck
    assert raw[10] == 1  # msgType
    parsed = Message.parse(raw)
    assert parsed.seq_id == 100
    assert parsed.src_id == 200
    assert parsed.opcode == 401
    assert parsed.params == b"\x01\x02"


def test_tampered_checksum_rejected():
    msg = Message(
        version=2,
        need_ack=0,
        msg_type=1,
        seq_id=1,
        src_id=0,
        src_type=0,
        opcode=402,
        sub_cmd=0,
        params=b"zz",
    )
    raw = bytearray(msg.build())
    raw[6] ^= 0xFF  # corrupt a checksum byte
    with pytest.raises(ChecksumError):
        Message.parse(bytes(raw))


def test_tampered_data_size_rejected():
    msg = Message(
        version=2,
        need_ack=0,
        msg_type=1,
        seq_id=1,
        src_id=0,
        src_type=0,
        opcode=402,
        sub_cmd=0,
        params=b"zz",
    )
    raw = bytearray(msg.build())
    raw[0] ^= 0xFF  # corrupt dataSize low byte
    with pytest.raises(Exception):
        Message.parse(bytes(raw))
