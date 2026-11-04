"""Signaling client: socket, sender/receiver threads, handshake, calls.

Architecture mirrors the native pipeline (bao-cao.md §1, §6;
bao-cao-transport.md §4):
    app -> send_message -> XOR params -> plain frame -> transport
    encrypt (plain / GCM / Prov / CBC fallback) -> socket
    socket -> FrameReader -> transport decrypt -> Req deserialize
    (checksum) -> state machine + on_message callback + inbound queue

What this client does NOT do (all flagged, none faked):
- It does not authenticate a mobile session. The caller must supply
  a connected socket path: talk_host/talk_port (+ optional HTTP
  CONNECT proxy, as observed in the pcap). Mobile socket auth is a
  separate work item (U5 in the reports).
- It does not know the real handshake frame contents: the 0xa1/0xa3
  plaintext frames take explicit opcode/params from the caller, and
  the first Prov message content (U4) is a caller-supplied argument.
- It does not know field semantics of 401 (which field carries the
  thread id). make_call maps thread_id to the first string field of
  a mode-1 401 and logs that mapping as UNCONFIRMED.
- Keys/session values are constructor-injected only, never stored
  in files, logs, or this source tree.
"""

import logging
import queue
import socket
import threading

from zalo_call.errors import (
    ChecksumError,
    DecryptError,
    FrameError,
    ZaloCallError,
)
from zalo_call.keyset import KeySet
from zalo_call.req import MSG_TYPE_VOIP, Message
from zalo_call.signaling import (
    CallStateMachine,
    Opcode,
    build_401_mode1,
    build_402,
    build_409,
    build_425,
    build_432,
    build_440_441,
)
from zalo_call.transport import (
    FrameReader,
    cbc_fallback_encrypt,
    decrypt_wire_frame,
    encode_plain_frame,
    encode_wire,
    gcm_encrypt,
    prov_encrypt,
)
from zalo_call.xor_params import HANDSHAKE_SUBCMDS, should_xor, xor_params

logger = logging.getLogger(__name__)

DEFAULT_INNER_TYPE = 2


class ClientConfig:
    """Connection configuration. All session/key material is injected."""

    def __init__(
        self,
        talk_host: str,
        talk_port: int,
        keyset: KeySet | None = None,
        src_id: int = 0,
        src_type: int = 0,
        version: int = 2,
        proxy_host: str | None = None,
        proxy_port: int | None = None,
        connect_timeout: float = 15.0,
        socket_timeout: float = 30.0,
        cbc_cipher=None,
        prov_map_kdf=None,
        ecdh_kdf=None,
    ) -> None:
        self.talk_host = talk_host
        self.talk_port = talk_port
        self.keyset = keyset or KeySet()
        self.src_id = src_id
        self.src_type = src_type
        self.version = version
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.connect_timeout = connect_timeout
        self.socket_timeout = socket_timeout
        self.cbc_cipher = cbc_cipher
        self.prov_map_kdf = prov_map_kdf
        self.ecdh_kdf = ecdh_kdf


class ZaloCallClient:
    """TCP signaling client for Zalo voice calls (caller side)."""

    def __init__(
        self,
        config: ClientConfig,
        on_message=None,
    ) -> None:
        self.config = config
        self.on_message = on_message
        self.state = CallStateMachine()
        self.inbound: queue.Queue = queue.Queue()
        self._sock: socket.socket | None = None
        self._send_lock = threading.Lock()
        self._seq_lock = threading.Lock()
        self._seq = 0
        self._reader_thread: threading.Thread | None = None
        self._running = False
        self._pending_tts: str | None = None

    # ------------------------------------------------------------ seq

    def next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    # ------------------------------------------------------------ connect

    def connect(self) -> None:
        """Open the TCP socket (optionally via HTTP CONNECT proxy)."""
        cfg = self.config
        if cfg.proxy_host and cfg.proxy_port:
            sock = socket.create_connection(
                (cfg.proxy_host, cfg.proxy_port), timeout=cfg.connect_timeout
            )
            req = (
                f"CONNECT {cfg.talk_host}:{cfg.talk_port} HTTP/1.1\r\n"
                f"Host: {cfg.talk_host}:{cfg.talk_port}\r\n\r\n"
            ).encode("ascii")
            sock.sendall(req)
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ZaloCallError("proxy closed CONNECT handshake")
                buf += chunk
            if b" 200 " not in buf.split(b"\r\n", 1)[0]:
                raise ZaloCallError(f"proxy CONNECT failed: {buf[:100]!r}")
        else:
            sock = socket.create_connection(
                (cfg.talk_host, cfg.talk_port), timeout=cfg.connect_timeout
            )
        sock.settimeout(cfg.socket_timeout)
        self._sock = sock
        self._running = True
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="zalo-call-reader", daemon=True
        )
        self._reader_thread.start()

    def close(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # ------------------------------------------------------------ send path

    def _build_wire(
        self, message: Message, scheme: str, inner_type: int
    ) -> bytes:
        """Apply XOR params, wrap in a plain frame, encrypt per scheme."""
        cfg = self.config
        params = message.params
        if should_xor(message.version, message.sub_cmd):
            total = message.header_size + len(params)
            params = xor_params(
                params,
                cfg.keyset.xor_key,
                total,
                cfg.keyset.e2e_src_id,
            )
        wire_msg = Message(
            version=message.version,
            need_ack=message.need_ack,
            msg_type=message.msg_type,
            seq_id=message.seq_id,
            src_id=message.src_id,
            src_type=message.src_type,
            opcode=message.opcode,
            sub_cmd=message.sub_cmd,
            params=params,
            ret_code=message.ret_code,
            comm_byte=message.comm_byte,
            comm_u64=message.comm_u64,
        )
        raw = wire_msg.build()
        if scheme == "plain":
            return encode_plain_frame(inner_type, raw)
        if scheme == "gcm":
            return gcm_encrypt(cfg.keyset.require_transport_key(), inner_type, raw)
        if scheme == "cbc":
            return cbc_fallback_encrypt(inner_type, raw, cfg.cbc_cipher)
        raise ValueError(f"unknown scheme {scheme!r} (use plain/gcm/cbc)")

    def send_message(
        self,
        message: Message,
        scheme: str = "gcm",
        inner_type: int = DEFAULT_INNER_TYPE,
    ) -> None:
        if self._sock is None:
            raise ZaloCallError("not connected")
        wire = self._build_wire(message, scheme, inner_type)
        with self._send_lock:
            self._sock.sendall(wire)

    def _new_message(
        self, opcode: int, params: bytes, sub_cmd: int = 0, need_ack: int = 0
    ) -> Message:
        cfg = self.config
        return Message(
            version=cfg.version,
            need_ack=need_ack,
            msg_type=MSG_TYPE_VOIP,
            seq_id=self.next_seq(),
            src_id=cfg.src_id,
            src_type=cfg.src_type,
            opcode=opcode,
            sub_cmd=sub_cmd,
            params=params,
        )

    # ------------------------------------------------------------ handshake

    def send_handshake_frame(
        self, sub_cmd: int, opcode: int = 0, params: bytes = b""
    ) -> Message:
        """One plaintext handshake frame (sub_cmd 0xa1/0xa3).

        The opcode/params of real handshake frames are UNCONFIRMED
        (U4 in the reports); the caller supplies them explicitly.
        These frames always travel plaintext (no XOR, wire <= 2).
        """
        if sub_cmd not in HANDSHAKE_SUBCMDS:
            raise ValueError(f"not a handshake sub_cmd: 0x{sub_cmd:02x}")
        msg = self._new_message(opcode, params, sub_cmd=sub_cmd)
        self.send_message(msg, scheme="plain", inner_type=2)
        logger.warning(
            "handshake frame sub_cmd=0x%02x opcode=%d sent with "
            "caller-supplied content (UNCONFIRMED against a real server)",
            sub_cmd,
            opcode,
        )
        return msg

    def perform_handshake(self) -> list[Message]:
        """Send the 0xa1 then 0xa3 plaintext frames, in order."""
        sent = [
            self.send_handshake_frame(0xA1),
            self.send_handshake_frame(0xA3),
        ]
        return sent

    def send_prov_handshake(
        self,
        message: Message,
        a: bytes,
        b: bytes,
        server_pubkey: bytes | None = None,
        gcm_key: bytes | None = None,
    ) -> tuple[bytes, bytes | None]:
        """Send one Prov (ECDH+GCM) handshake frame, inner type 4.

        The first Prov message's content (U4) is caller-supplied via
        `message`. a/b are the trailing 32-byte fields (identities
        UNCONFIRMED — caller supplies them). Returns
        (wire_bytes, client_pubkey_or_None).
        """
        if self._sock is None:
            raise ZaloCallError("not connected")
        raw = message.build()
        wire, pubkey = prov_encrypt(
            4,
            raw,
            a,
            b,
            gcm_key=gcm_key,
            server_pubkey=server_pubkey,
            ecdh_kdf=self.config.ecdh_kdf,
        )
        with self._send_lock:
            self._sock.sendall(wire)
        return wire, pubkey

    # ------------------------------------------------------------ calls

    def make_call(
        self, thread_id: str, tts_text: str | None = None, sub_cmd: int = 0
    ) -> tuple[int, Message]:
        """Start an outgoing call to a thread (alert flow).

        TODO (UNCONFIRMED field mapping): thread_id is placed in the
        first string field of a mode-1 401. Which 401 field really
        carries the thread id must be confirmed against a real
        handshake; until then this mapping is a documented guess.
        Likewise, whether the Java packet field h (returned by the
        401 builder) equals the wire subCmd byte is UNCONFIRMED, so
        sub_cmd is left at its default unless the caller passes one.
        tts_text is stored for the audio pipeline (played when the
        call becomes ACTIVE); it is NOT a signaling param.
        """
        logger.warning(
            "make_call thread_id mapping to 401/str2 is UNCONFIRMED "
            "(needs a real handshake to verify)"
        )
        params, _h_byte = build_401_mode1(str2=thread_id)
        msg = self._new_message(Opcode.REQUEST_CALL, params, sub_cmd=sub_cmd)
        self.send_message(msg, scheme="gcm")
        self.state.sent(Opcode.REQUEST_CALL)
        self._pending_tts = tts_text
        return msg.seq_id, msg

    def send_pre_call(self, i1: int = 0, i2: int = 0) -> Message:
        msg = self._new_message(Opcode.PRE_CALL, build_425(i1, i2))
        self.send_message(msg, scheme="gcm")
        return msg

    def answer_call(
        self,
        i1: int = 0,
        b: int = 0,
        i2: int = 0,
        strings: tuple[str, str, str, str, str] = ("", "", "", "", ""),
    ) -> Message:
        msg = self._new_message(Opcode.REQUEST_ANSWER, build_402(i1, b, i2, strings))
        self.send_message(msg, scheme="gcm")
        return msg

    def end_call(self) -> Message:
        msg = self._new_message(Opcode.END_CALL, build_409())
        self.send_message(msg, scheme="gcm")
        self.state.sent(Opcode.END_CALL)
        return msg

    def send_core_data(
        self, i1: int = 0, i2: int = 0, i3: int = 0, s: str = ""
    ) -> Message:
        msg = self._new_message(Opcode.CORE_DATA, build_432(i1, i2, i3, s))
        self.send_message(msg, scheme="gcm")
        return msg

    def request_new_server(
        self, i1: int = 0, i2: int = 0, i3: int = 0, s: str = ""
    ) -> Message:
        msg = self._new_message(
            Opcode.CALLER_NEW_SERVER, build_440_441(i1, i2, i3, s)
        )
        self.send_message(msg, scheme="gcm")
        return msg

    # ------------------------------------------------------------ receive path

    def _handle_frame(self, wire_type: int, payload: bytes) -> None:
        cfg = self.config
        try:
            if wire_type >= 5:
                # Auth path only: Prov key-set name = peer host:port.
                # Normal-path Prov frames (empty name) are dropped
                # inside decrypt_wire_frame, faithful to the original.
                inner, raw = decrypt_wire_frame(
                    cfg.keyset,
                    wire_type,
                    payload,
                    keyset_name=f"{cfg.talk_host}:{cfg.talk_port}",
                    prov_map_kdf=cfg.prov_map_kdf,
                )
            else:
                inner, raw = decrypt_wire_frame(
                    cfg.keyset,
                    wire_type,
                    payload,
                    keyset_name="",
                    cbc_cipher=cfg.cbc_cipher,
                )
        except (DecryptError, FrameError) as exc:
            logger.warning("dropping undecryptable frame: %s", exc)
            return
        try:
            message = Message.parse(raw)
        except (ChecksumError, FrameError) as exc:
            logger.warning("dropping unparsable message: %s", exc)
            return
        # Reverse the XOR params layer for the application layer.
        if should_xor(message.version, message.sub_cmd):
            total = message.header_size + len(message.params)
            message.params = xor_params(
                message.params,
                cfg.keyset.xor_key,
                total,
                cfg.keyset.e2e_src_id,
            )
        event = self.state.received(message)
        self.inbound.put((message, event))
        if self.on_message is not None:
            try:
                self.on_message(message, event)
            except Exception:  # never kill the reader thread on callbacks
                logger.exception("on_message callback failed")

    def _reader_loop(self) -> None:
        assert self._sock is not None
        reader = FrameReader()
        while self._running:
            try:
                chunk = self._sock.recv(65536)
            except (OSError, socket.timeout):
                break
            if not chunk:
                break
            try:
                frames = reader.feed(chunk)
            except FrameError as exc:
                logger.warning("frame reader error: %s", exc)
                break
            for wire_type, payload in frames:
                self._handle_frame(wire_type, payload)
        self._running = False
