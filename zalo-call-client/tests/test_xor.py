"""Params XOR layer tests.

Hand vector: key=b"AB", e2e_src_id=0x01020304, total_len=10,
data=00 01 02 03.
  b_le = 04 03 02 01 ; a_le = 0A 00 00 00
  tmp1 = [0x41^0x04, 0x42^0x03] = [0x45, 0x41]
  tmp2 = [0x45^0x0A, 0x41^0x00] = [0x4F, 0x41]
  out  = [0x00^0x4F, 0x01^0x41, 0x02^0x4F, 0x03^0x41]
       = 4F 40 4D 42
"""

from zalo_call.xor_params import should_xor, xor_params


def test_xor_hand_vector():
    out = xor_params(bytes([0, 1, 2, 3]), b"AB", 10, 0x01020304)
    assert out == bytes.fromhex("4f404d42")


def test_xor_is_involution():
    data = bytes(range(64))
    once = xor_params(data, b"secret-key", 100, 12345)
    twice = xor_params(once, b"secret-key", 100, 12345)
    assert twice == data


def test_xor_empty_key_is_identity():
    assert xor_params(b"abc", b"", 10, 0) == b"abc"
    assert xor_params(b"abc", None, 10, 0) == b"abc"


def test_xor_gating():
    assert should_xor(2, 0) is True
    assert should_xor(2, 0xA1) is False
    assert should_xor(2, 0xA3) is False
    assert should_xor(1, 0) is False
    assert should_xor(3, 0) is False
