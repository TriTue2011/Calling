"""Offline client test over a socketpair (no network, no accounts).

The client speaks GCM with a TEST key; the peer side decrypts with
the same key, verifying the full send/receive stack: framing,
GCM, Req build/parse, checksum, state machine, inbound queue.
"""

import socket
import threading
import time

import pytest

from zalo_call.client import ClientConfig, ZaloCallClient
from zalo_call.keyset import KeySet
from zalo_call.req import Message
from zalo_call.signaling import Opcode, build_402, build_407, build_409
from zalo_call.transport import FrameReader, gcm_decrypt, gcm_encrypt

TEST_KEY = bytes(range(32))


def _wire_client(peer_sock):
    cfg = ClientConfig(
        talk_host="127.0.0.1",
        talk_port=1,
        keyset=KeySet(transport_key=TEST_KEY),
        # Offline socketpair test, not a real call: the secret
        # guard is covered separately in test_call_guards.py.
        require_secrets=False,
    )
    client = ZaloCallClient(cfg)
    client._sock = peer_sock
    client._sock.settimeout(5)
    client._running = True
    client._reader_thread = threading.Thread(
        target=client._reader_loop, daemon=True
    )
    client._reader_thread.start()
    return client


def _read_one_frame(sock, timeout=5):
    sock.settimeout(timeout)
    reader = FrameReader()
    buf = b""
    while True:
        frames = reader.feed(sock.recv(65536))
        if frames:
            return frames[0]
        time.sleep(0.01)


def _wait_state(client, state, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.state.state == state:
            return True
        time.sleep(0.02)
    return False


def test_client_sends_401_over_socketpair():
    a, b = socket.socketpair()
    client = _wire_client(a)
    try:
        seq, msg = client.make_call(thread_id="thread-123")
        wire_type, payload = _read_one_frame(b)
        assert wire_type == 4  # GCM, inner 2
        inner, raw = gcm_decrypt(TEST_KEY, wire_type, payload)
        assert inner == 2
        parsed = Message.parse(raw)
        assert parsed.opcode == Opcode.REQUEST_CALL
        assert parsed.seq_id == seq
        # mode-1 401 params: b1(1) b1(4) g4 g4 h2+str2 ...
        assert parsed.params[0] == 1 and parsed.params[1] == 4
        assert b"thread-123" in parsed.params
    finally:
        client.close()
        b.close()


def test_client_receives_407_402_409_flow():
    a, b = socket.socketpair()
    client = _wire_client(a)
    try:

        def send_peer(opcode, params):
            msg = Message(
                version=2, need_ack=0, msg_type=1, seq_id=9, src_id=0,
                src_type=0, opcode=opcode, sub_cmd=0, params=params,
            )
            b.sendall(gcm_encrypt(TEST_KEY, 2, msg.build()))

        send_peer(Opcode.RINGING, build_407(1, 2, 3, 4, "ring"))
        assert _wait_state(client, "ringing")
        send_peer(Opcode.REQUEST_ANSWER, build_402(1, 0, 2, ("a", "b", "c", "d", "e")))
        assert _wait_state(client, "active")
        send_peer(Opcode.END_CALL, build_409(1, 0, 2, "x", "y", "z", 3))
        assert _wait_state(client, "ended")
        # Inbound queue got all three messages in order.
        opcodes = []
        while not client.inbound.empty():
            message, _event = client.inbound.get_nowait()
            opcodes.append(message.opcode)
        assert opcodes == [407, 402, 409]
    finally:
        client.close()
        b.close()


def test_client_handshake_frame_is_plaintext():
    a, b = socket.socketpair()
    client = _wire_client(a)
    try:
        client.send_handshake_frame(0xA1)
        wire_type, payload = _read_one_frame(b)
        assert wire_type == 2  # plaintext, wire <= 2
        parsed = Message.parse(payload)
        assert parsed.sub_cmd == 0xA1
    finally:
        client.close()
        b.close()
