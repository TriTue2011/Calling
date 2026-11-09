"""Handshake + state machine tests."""

import pytest

from zalo_call.errors import DecryptError
from zalo_call.keyset import KeySet
from zalo_call.req import Message
from zalo_call.signaling import CallStateMachine, Opcode
from zalo_call.transport import (
    decrypt_wire_frame,
    encode_plain_frame,
    prov_decrypt,
    prov_encrypt,
    prov_parse_payload,
)
from zalo_call.xor_params import should_xor


def _msg(opcode, params=b"", sub_cmd=0):
    return Message(
        version=2, need_ack=0, msg_type=1, seq_id=1, src_id=0,
        src_type=0, opcode=opcode, sub_cmd=sub_cmd, params=params,
    )


def test_handshake_frames_are_plaintext_wire_le_2():
    for sub_cmd in (0xA1, 0xA3):
        assert should_xor(2, sub_cmd) is False
        frame = encode_plain_frame(2, _msg(0, b"", sub_cmd).build())
        assert frame[4] == 2  # wire <= 2
        inner, raw = decrypt_wire_frame(KeySet(), 2, frame[5:])
        assert inner == 2
        parsed = Message.parse(raw)
        assert parsed.sub_cmd == sub_cmd


def test_prov_layout_round_trip_with_explicit_ab():
    key = bytes(range(32))
    a = bytes([0x11] * 32)
    b = bytes([0x22] * 32)
    message = _msg(401, b"prov-payload").build()
    frame, _pub = prov_encrypt(4, message, a, b, gcm_key=key)
    assert frame[4] == 8  # inner 4 + 4
    parts = prov_parse_payload(frame[5:])
    assert parts["a"] == a
    assert parts["b"] == b
    inner, plain, a2, b2 = prov_decrypt(key, 8, frame[5:])
    assert inner == 4 and plain == message and a2 == a and b2 == b


def test_prov_requires_explicit_ab():
    key = bytes(range(32))
    with pytest.raises(Exception):
        prov_encrypt(4, b"x", bytes(31), bytes(32), gcm_key=key)


def test_prov_dropped_on_empty_keyset_name():
    key = bytes(range(32))
    frame, _ = prov_encrypt(4, b"x", bytes(32), bytes(32), gcm_key=key)
    with pytest.raises(DecryptError):
        decrypt_wire_frame(KeySet(), 8, frame[5:], keyset_name="")


def test_state_machine_full_call_flow():
    sm = CallStateMachine()
    assert sm.state == "idle"
    sm.sent(Opcode.REQUEST_CALL)
    assert sm.state == "dialing"
    sm.received(_msg(Opcode.RINGING, b"\x00" * 20))
    assert sm.state == "ringing"
    sm.received(_msg(Opcode.REQUEST_ANSWER, b"\x00" * 30))
    assert sm.state == "active"
    sm.received(_msg(Opcode.END_CALL, b"\x00" * 30))
    assert sm.state == "ended"


def test_state_machine_cancel_and_unknown_opcode():
    sm = CallStateMachine()
    sm.sent(Opcode.REQUEST_CALL)
    sm.received(_msg(Opcode.CANCEL, b""))
    assert sm.state == "ended"
    event = sm.received(_msg(9999, b""))
    assert event[0] == "unknown" and event[1] == 9999
    # Unknown opcodes never crash the machine.
    assert sm.state == "ended"
