"""AES correctness: FIPS-197 block vectors + openssl cross-check."""

import subprocess
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app.aes_pure import (  # noqa: E402
    ZERO_IV, cbc_decrypt, cbc_encrypt, decrypt_block, encrypt_block)


def test_fips197_aes128():
    key = bytes(range(16))
    pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    assert encrypt_block(key, pt).hex() == "69c4e0d86a7b0430d8cdb78070b4c55a"
    assert decrypt_block(key, bytes.fromhex(
        "69c4e0d86a7b0430d8cdb78070b4c55a")) == pt


def test_fips197_aes256():
    key = bytes(range(32))
    pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    assert encrypt_block(key, pt).hex() == "8ea2b7ca516745bfeafc49904b496089"
    assert decrypt_block(key, bytes.fromhex(
        "8ea2b7ca516745bfeafc49904b496089")) == pt


def _openssl(args, data):
    p = subprocess.run(["openssl"] + args, input=data,
                       capture_output=True, timeout=30)
    assert p.returncode == 0, p.stderr.decode()
    return p.stdout


def test_cbc_interop_with_openssl():
    key = bytes(range(32))
    msg = b'{"calleeId":"123","callId":"abc"}'
    mine = cbc_encrypt(key, ZERO_IV, msg)
    # openssl must decrypt what my code produced
    theirs = _openssl(["enc", "-aes-256-cbc", "-d",
                       "-K", key.hex(), "-iv", "00" * 16], mine)
    assert theirs == msg
    # and my code must decrypt what openssl produced
    enc = _openssl(["enc", "-aes-256-cbc",
                    "-K", key.hex(), "-iv", "00" * 16], msg)
    assert cbc_decrypt(key, ZERO_IV, enc) == msg


def test_cbc_roundtrip_edge_lengths():
    key = b"K" * 32
    for n in (0, 1, 15, 16, 17, 100):
        msg = bytes((i % 251 for i in range(n)))
        assert cbc_decrypt(key, ZERO_IV, cbc_encrypt(key, ZERO_IV, msg)) == msg


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL AES TESTS PASSED")
