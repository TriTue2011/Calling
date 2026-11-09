"""Req/Comm/Ret build + parse tests.

Header sizes follow the msg_type byte (req.py): VoIP=1 -> 23,
Comm=2 -> 36, Ret=3 -> 27.
"""

from zalo_call.req import (
    HEADER_COMM,
    HEADER_REQ,
    HEADER_RET,
    Message,
)


def test_req_header_size_and_datasize():
    msg = Message(
        version=2, need_ack=0, msg_type=1, seq_id=1, src_id=0,
        src_type=0, opcode=401, sub_cmd=0, params=b"12345",
    )
    raw = msg.build()
    assert msg.header_size == HEADER_REQ == 23
    assert len(raw) == 23 + 5
    assert int.from_bytes(raw[:4], "little") == 23 + 5


def test_comm_header_size():
    msg = Message(
        version=2, need_ack=0, msg_type=2, seq_id=1, src_id=0,
        src_type=0, opcode=401, sub_cmd=0, params=b"",
        ret_code=0, comm_byte=0, comm_u64=0,
    )
    raw = msg.build()
    assert msg.header_size == HEADER_COMM == 36
    assert len(raw) == 36


def test_ret_header_size():
    msg = Message(
        version=2, need_ack=0, msg_type=3, seq_id=1, src_id=0,
        src_type=0, opcode=401, sub_cmd=0, params=b"",
        ret_code=0,
    )
    raw = msg.build()
    assert msg.header_size == HEADER_RET == 27
    assert len(raw) == 27


def test_round_trip_preserves_all_fields():
    msg = Message(
        version=2, need_ack=1, msg_type=1, seq_id=777, src_id=888,
        src_type=2, opcode=409, sub_cmd=5, params=b"\xde\xad\xbe\xef",
    )
    parsed = Message.parse(msg.build())
    assert parsed.version == 2
    assert parsed.need_ack == 1
    assert parsed.msg_type == 1
    assert parsed.seq_id == 777
    assert parsed.src_id == 888
    assert parsed.src_type == 2
    assert parsed.opcode == 409
    assert parsed.sub_cmd == 5
    assert parsed.params == b"\xde\xad\xbe\xef"
