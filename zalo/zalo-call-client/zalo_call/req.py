"""MessageBinReq / Comm / Ret — wire format (little-endian).

Confirmed from libznetwork.so disassembly (bao-cao.md §2–3,
bao-cao-transport.md §6). All three types share the same 23-byte
prefix; they differ only in the tail:

    wire[0..3]   u32 dataSize  = header_size + len(params)
    wire[4]      u8  version   (wire version byte; NOT the dex field f=3,
                 which is a separate Java-layer constant)
    wire[5..8]   u32 checksum  (see below)
    wire[9]      u8  needAck
    wire[10]     u8  msgType   (1 = VoIP)
    wire[11..14] u32 seqId
    wire[15..18] u32 srcId
    wire[19]     u8  srcType
    wire[20..21] u16 opcode    (field g of dex RequestPacket)
    wire[22]     u8  subCmd    (0xa1/0xa3 = plaintext handshake)
    wire[23..]   params        (Req) / tail + params (Comm/Ret)

    Req tail:  none                        (header 23, params at 23)
    Ret tail:  u32 at [0x17]               (header 27, params at 27)
    Comm tail: u32 at [0x17], u8 at [0x1b], u64 at [0x1c]
                                           (header 36, params at 36)

Checksum (Req, confirmed both directions):
    sum = needAck + msgType + seqId + srcId + srcType
          + opcode (as SIGNED halfword) + subCmd     (mod 2**32)
    checksum = sum XOR 0x6CE7DAA0

NOTE on Comm/Ret checksums: the native Comm checksum adds four more
struct fields whose wire offsets are NOT fully mapped yet. This
module therefore builds Comm/Ret with the same base formula and
flags it: Comm/Ret messages produced here may fail the server's
checksum check. VoIP (Req) is the path that matters for calling
and is exact.
"""

import struct

from zalo_call.errors import ChecksumError, FrameError

CHECKSUM_XOR = 0x6CE7DAA0

MSG_TYPE_VOIP = 1
MSG_TYPE_COMM = 2
MSG_TYPE_RET = 3

HEADER_REQ = 23
HEADER_RET = 27
HEADER_COMM = 36

HEADER_SIZE = {
    MSG_TYPE_VOIP: HEADER_REQ,
    MSG_TYPE_COMM: HEADER_COMM,
    MSG_TYPE_RET: HEADER_RET,
}


def _signed_halfword(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value


def compute_checksum(
    need_ack: int,
    msg_type: int,
    seq_id: int,
    src_id: int,
    src_type: int,
    opcode: int,
    sub_cmd: int,
) -> int:
    """Req header checksum (see module docstring)."""
    total = (
        (need_ack & 0xFF)
        + (msg_type & 0xFF)
        + (seq_id & 0xFFFFFFFF)
        + (src_id & 0xFFFFFFFF)
        + (src_type & 0xFF)
        + _signed_halfword(opcode)
        + (sub_cmd & 0xFF)
    )
    return (total & 0xFFFFFFFF) ^ CHECKSUM_XOR


class Message:
    """One signaling message at wire level."""

    def __init__(
        self,
        version: int = 2,
        need_ack: int = 0,
        msg_type: int = MSG_TYPE_VOIP,
        seq_id: int = 0,
        src_id: int = 0,
        src_type: int = 0,
        opcode: int = 0,
        sub_cmd: int = 0,
        params: bytes = b"",
        ret_code: int | None = None,
        comm_byte: int | None = None,
        comm_u64: int | None = None,
    ) -> None:
        self.version = version
        self.need_ack = need_ack
        self.msg_type = msg_type
        self.seq_id = seq_id
        self.src_id = src_id
        self.src_type = src_type
        self.opcode = opcode
        self.sub_cmd = sub_cmd
        self.params = params
        self.ret_code = ret_code
        self.comm_byte = comm_byte
        self.comm_u64 = comm_u64

    @property
    def header_size(self) -> int:
        try:
            return HEADER_SIZE[self.msg_type]
        except KeyError as exc:
            raise FrameError(f"unsupported msg_type {self.msg_type}") from exc

    def checksum(self) -> int:
        return compute_checksum(
            self.need_ack,
            self.msg_type,
            self.seq_id,
            self.src_id,
            self.src_type,
            self.opcode,
            self.sub_cmd,
        )

    def build(self) -> bytes:
        """Serialize to wire bytes (checksum computed)."""
        header_size = self.header_size
        buf = bytearray()
        buf += struct.pack("<I", header_size + len(self.params))
        buf += struct.pack("<B", self.version & 0xFF)
        buf += struct.pack("<I", self.checksum())
        buf += struct.pack("<B", self.need_ack & 0xFF)
        buf += struct.pack("<B", self.msg_type & 0xFF)
        buf += struct.pack("<I", self.seq_id & 0xFFFFFFFF)
        buf += struct.pack("<I", self.src_id & 0xFFFFFFFF)
        buf += struct.pack("<B", self.src_type & 0xFF)
        buf += struct.pack("<H", self.opcode & 0xFFFF)
        buf += struct.pack("<B", self.sub_cmd & 0xFF)
        if self.msg_type == MSG_TYPE_RET:
            buf += struct.pack("<I", (self.ret_code or 0) & 0xFFFFFFFF)
        elif self.msg_type == MSG_TYPE_COMM:
            buf += struct.pack("<I", (self.ret_code or 0) & 0xFFFFFFFF)
            buf += struct.pack("<B", (self.comm_byte or 0) & 0xFF)
            buf += struct.pack("<Q", (self.comm_u64 or 0) & 0xFFFFFFFFFFFFFFFF)
        assert len(buf) == header_size, (len(buf), header_size)
        buf += self.params
        return bytes(buf)

    @classmethod
    def parse(cls, data: bytes) -> "Message":
        """Parse wire bytes; verifies dataSize and checksum exactly.

        The native deserializer rejects on length mismatch or bad
        checksum — this mirrors that strictness.
        """
        if len(data) < HEADER_REQ:
            raise FrameError(f"message too short: {len(data)} bytes")
        (data_size,) = struct.unpack_from("<I", data, 0)
        if data_size != len(data):
            raise FrameError(
                f"dataSize mismatch: header says {data_size}, got {len(data)}"
            )
        version = data[4]
        (wire_checksum,) = struct.unpack_from("<I", data, 5)
        need_ack = data[9]
        msg_type = data[10]
        (seq_id,) = struct.unpack_from("<I", data, 11)
        (src_id,) = struct.unpack_from("<I", data, 15)
        src_type = data[19]
        (opcode,) = struct.unpack_from("<H", data, 20)
        sub_cmd = data[22]
        try:
            header_size = HEADER_SIZE[msg_type]
        except KeyError as exc:
            raise FrameError(f"unsupported msg_type {msg_type}") from exc
        expected = compute_checksum(
            need_ack, msg_type, seq_id, src_id, src_type, opcode, sub_cmd
        )
        if expected != wire_checksum:
            raise ChecksumError(
                f"checksum mismatch: wire 0x{wire_checksum:08x}, "
                f"computed 0x{expected:08x}"
            )
        ret_code = comm_byte = comm_u64 = None
        if msg_type == MSG_TYPE_RET:
            (ret_code,) = struct.unpack_from("<I", data, 23)
        elif msg_type == MSG_TYPE_COMM:
            (ret_code,) = struct.unpack_from("<I", data, 23)
            comm_byte = data[27]
            (comm_u64,) = struct.unpack_from("<Q", data, 28)
        return cls(
            version=version,
            need_ack=need_ack,
            msg_type=msg_type,
            seq_id=seq_id,
            src_id=src_id,
            src_type=src_type,
            opcode=opcode,
            sub_cmd=sub_cmd,
            params=bytes(data[header_size:]),
            ret_code=ret_code,
            comm_byte=comm_byte,
            comm_u64=comm_u64,
        )
