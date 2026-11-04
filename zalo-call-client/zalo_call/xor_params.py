"""XOR layer on message params (bao-cao.md §4).

Applies only when version == 2 and subCmd not in {0xa1, 0xa3}
(the two handshake subCmds travel in plaintext).

Native construction (ZaloDataUtils::doEncryptData):
    tmp1[j] = key[j] ^ b_le[j % 4]          (b = E2E srcId int)
    tmp2[j] = tmp1[j] ^ a_le[j % 4]         (a = total message length)
    out[i]  = data[i] ^ tmp2[i % len(key)]
where key is the session XOR string (ZaloDataUtils+0x28), and
b_le / a_le are the 4-byte little-endian forms of b / a.

XOR is an involution: applying it twice restores the original.
An empty/None key means "copy unchanged" (the native NULL-key path).
"""

import struct

HANDSHAKE_SUBCMDS = (0xA1, 0xA3)


def should_xor(version: int, sub_cmd: int) -> bool:
    """True when the native code XORs params for this message."""
    return version == 2 and sub_cmd not in HANDSHAKE_SUBCMDS


def _xor_with_key(data: bytes, key: bytes) -> bytes:
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def xor_params(
    params: bytes,
    key: bytes | None,
    total_length: int,
    e2e_src_id: int,
) -> bytes:
    """Apply (or reverse — same operation) the params XOR layer.

    total_length is the full message length (header + params),
    e2e_src_id is the ZaloCache+0x6bc int (E2E source id).
    """
    if not key:
        return params
    b_le = struct.pack("<i", e2e_src_id)
    a_le = struct.pack("<i", total_length)
    tmp1 = _xor_with_key(key, b_le)
    tmp2 = _xor_with_key(tmp1, a_le)
    return _xor_with_key(params, tmp2)
