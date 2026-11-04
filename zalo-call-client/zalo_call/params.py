"""Params encoding for VoIP signaling messages.

Encoding rules (confirmed from dex analysis, giai-ma-packet.md §3):
- integers: little-endian (g4 = 4 bytes, h2 = 2 bytes)
- strings: UTF-8 bytes, length prefix = number of UTF-8 BYTES
  (not characters), usually 2-byte LE; one exception (401 mode 2,
  first string) uses a raw 1-byte length
- blobs: 2-byte LE length prefix + raw bytes
"""

import struct

from zalo_call.errors import FrameError


def u8(value: int) -> bytes:
    return struct.pack("<B", value & 0xFF)


def u16le(value: int) -> bytes:
    return struct.pack("<H", value & 0xFFFF)


def u32le(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def u64le(value: int) -> bytes:
    return struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF)


def str2(value: str) -> bytes:
    """UTF-8 string with 2-byte LE length prefix."""
    raw = value.encode("utf-8")
    return u16le(len(raw)) + raw


def str1(value: str) -> bytes:
    """UTF-8 string with raw 1-byte length prefix (401 mode 2 only)."""
    raw = value.encode("utf-8")
    if len(raw) > 0xFF:
        raise FrameError("str1 field longer than 255 bytes")
    return u8(len(raw)) + raw


def blob2(data: bytes) -> bytes:
    """Raw bytes with 2-byte LE length prefix."""
    return u16le(len(data)) + data


class ParamsWriter:
    """Builds a params byte string in field order."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def byte(self, value: int) -> "ParamsWriter":
        self._buf += u8(value)
        return self

    def raw(self, data: bytes) -> "ParamsWriter":
        self._buf += data
        return self

    def i32(self, value: int) -> "ParamsWriter":
        self._buf += u32le(value)
        return self

    def i16(self, value: int) -> "ParamsWriter":
        self._buf += u16le(value)
        return self

    def string(self, value: str) -> "ParamsWriter":
        self._buf += str2(value)
        return self

    def string1(self, value: str) -> "ParamsWriter":
        self._buf += str1(value)
        return self

    def blob(self, data: bytes) -> "ParamsWriter":
        self._buf += blob2(data)
        return self

    def build(self) -> bytes:
        return bytes(self._buf)


class ParamsReader:
    """Reads params fields in order; raises FrameError on truncation."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._off = 0

    def _take(self, n: int) -> bytes:
        if self._off + n > len(self._data):
            raise FrameError(
                f"params truncated: need {n} bytes at offset {self._off}, "
                f"have {len(self._data) - self._off}"
            )
        chunk = self._data[self._off : self._off + n]
        self._off += n
        return chunk

    def byte(self) -> int:
        return self._take(1)[0]

    def raw(self, n: int) -> bytes:
        return self._take(n)

    def i32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def i16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def string(self) -> str:
        n = self.i16()
        return self._take(n).decode("utf-8")

    def string1(self) -> str:
        n = self.byte()
        return self._take(n).decode("utf-8")

    def blob(self) -> bytes:
        n = self.i16()
        return self._take(n)

    @property
    def remaining(self) -> int:
        return len(self._data) - self._off

    @property
    def offset(self) -> int:
        return self._off
