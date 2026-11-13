"""AES-GCM thuần Python: vector NIST + đối chiếu với `cryptography` (nếu máy có) + kiểm sửa dữ liệu. Chạy: python3 tests/test_aesgcm_pure.py"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import aesgcm_pure as G  # noqa: E402

H = bytes.fromhex
K = H("feffe9928665731c6d6a8f9467308308")
P64 = H("d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b391aafd255")
AAD = H("feedfacedeadbeeffeedfacedeadbeefabaddad2")


def test_nist_gcm_vectors_with_12_byte_8_byte_and_60_byte_iv():
    # Test case 3 (IV 12 byte, không AAD)
    iv = H("cafebabefacedbaddecaf888")
    out = G.encrypt(K, iv, b"", P64)
    assert out[:-16] == H("42831ec2217774244b7221b784d0d49ce3aa212f2c02a4e035c17e2329aca12e21d514b25466931c7d8f6a5aac84aa051ba30b396a0aac973d58e091473f5985")
    assert out[-16:] == H("4d5c2af327cd64a62cf35abd2ba6fab4")
    # Test case 4 (có AAD, plaintext 60 byte)
    out4 = G.encrypt(K, iv, AAD, P64[:60])
    assert out4[-16:] == H("5bc94fbc3221a5db94fae95ae7121a47")
    assert G.decrypt(K, iv, AAD, out4) == P64[:60]
    # Test case 5 (IV 8 byte)
    out5 = G.encrypt(K, H("cafebabefacedbad"), AAD, P64[:60])
    assert out5[:-16][:16] == H("61353b4c2806934a777ff51fa22a4755")
    assert out5[-16:] == H("3612d2e79e3b0785561be14aaca2fccb")
    # Test case 6 (IV 60 byte)
    iv6 = H("9313225df88406e555909c5aff5269aa6a7a9538534f7da1e4c303d2a318a728c3c0c95156809539fcf0e2429a6b525416aedbf5a0de6a57a637b39b")
    out6 = G.encrypt(K, iv6, AAD, P64[:60])
    assert out6[-16:] == H("619cc5aefffe0bfa462af43c1699d050")
    assert G.decrypt(K, iv6, AAD, out6) == P64[:60]


def test_zalo_style_16_byte_iv_roundtrip_and_tamper_detection():
    rnd = random.Random(7)
    for klen in (16, 32):
        key, iv, aad = bytes(rnd.getrandbits(8) for _ in range(klen)), bytes(rnd.getrandbits(8) for _ in range(16)), bytes(rnd.getrandbits(8) for _ in range(16))
        for n in (0, 1, 15, 16, 17, 100, 1000):
            pt = bytes(rnd.getrandbits(8) for _ in range(n))
            ct = G.encrypt(key, iv, aad, pt)
            assert len(ct) == n + 16 and G.decrypt(key, iv, aad, ct) == pt
        bad = bytearray(ct)
        bad[0] ^= 1
        for tampered, a in ((bytes(bad), aad), (ct, aad[:-1] + b"\x00"), (ct[:-1] + bytes([ct[-1] ^ 1]), aad)):
            try:
                G.decrypt(key, iv, a, tampered)
            except ValueError:
                pass
            else:
                raise AssertionError("phai tu choi du lieu bi sua")
    for bad_args in ((b"x" * 5, b"i" * 16, b"", b"d" * 20), (K, b"", b"", b"d" * 20), (K, b"i" * 16, b"", b"ngan")):
        try:
            G.decrypt(*bad_args)
        except ValueError:
            pass
        else:
            raise AssertionError(bad_args)


def test_matches_cryptography_library_when_available():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        print("  (bo qua: may khong co thu vien cryptography)")
        return
    rnd = random.Random(11)
    for _ in range(40):
        key = bytes(rnd.getrandbits(8) for _ in range(rnd.choice((16, 24, 32))))
        iv = bytes(rnd.getrandbits(8) for _ in range(rnd.choice((12, 16, 8, 24))))
        aad = bytes(rnd.getrandbits(8) for _ in range(rnd.randint(0, 40)))
        pt = bytes(rnd.getrandbits(8) for _ in range(rnd.randint(0, 300)))
        ref = AESGCM(key).encrypt(iv, pt, aad)
        assert G.encrypt(key, iv, aad, pt) == ref
        assert G.decrypt(key, iv, aad, ref) == pt


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL AESGCM TESTS PASSED")
