"""ParamCipher / signkey / session-AES unit tests."""

import base64
import hashlib
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app.crypto import (  # noqa: E402
    ParamCipher, make_device_id, md5_hex, session_aes_decrypt,
    session_aes_encrypt, signkey)


def test_signkey_construction():
    params = {"b": "2", "a": "1", "type": "embed", "client_version": 695}
    # Independent recomputation: MD5(salt + name + values sorted by key).
    blob = "zsecure" + "reqqr" + "1" + "2" + "695" + "embed"
    assert signkey("reqqr", params) == hashlib.md5(blob.encode()).hexdigest()


def test_param_cipher_roundtrip_and_shape():
    cipher = ParamCipher("embed", "device-123", 1762345678901,
                         "TEST_PARAM_KEY_32_CHARS_LONG_XXX")
    assert len(cipher.zcid) == 64  # AES hex, upper
    assert cipher.zcid == cipher.zcid.upper()
    assert 6 <= len(cipher.zcid_ext) <= 12
    assert len(cipher.enk) == 32
    enc, enk = cipher.encrypt({"imei": "device-123", "self_g": 0})
    assert enk == cipher.enk
    assert set(enc.keys()) == {"zcid", "zcid_ext", "enc_ver", "params"}
    assert enc["enc_ver"] == "v2"
    back = ParamCipher.decrypt_response(enk, enc["params"])
    assert '"imei": "device-123"' in back or '"imei":"device-123"' in back


def test_enk_derivation_matches_spec():
    # Recompute enk from zcid/zcid_ext by hand (spec steps).
    cipher = ParamCipher("embed", "device-123", 1762345678901,
                         "TEST_PARAM_KEY_32_CHARS_LONG_XXX")
    md5_ext = hashlib.md5(cipher.zcid_ext.encode()).hexdigest().upper()
    even_md5 = [c for i, c in enumerate(md5_ext) if i % 2 == 0]
    even_z = [c for i, c in enumerate(cipher.zcid) if i % 2 == 0]
    odd_z = [c for i, c in enumerate(cipher.zcid) if i % 2 == 1]
    # JS: odd.reverse().slice(0,12) — reverse whole odd array, then 12.
    expect = ("".join(even_md5[:8]) + "".join(even_z[:12])
              + "".join(odd_z[::-1][:12]))
    assert cipher.enk == expect


def test_session_aes_roundtrip():
    key = base64.b64encode(b"S" * 32).decode()
    text = '{"calleeId":"42","callId":"c1"}'
    enc = session_aes_encrypt(key, text)
    assert session_aes_decrypt(key, enc) == text


def test_device_id_shape():
    did = make_device_id()
    uid, md5part = did.rsplit("-", 1)
    assert len(md5part) == 32
    assert md5_hex("zalo-pc-qr/1.0") == md5part


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CRYPTO TESTS PASSED")
