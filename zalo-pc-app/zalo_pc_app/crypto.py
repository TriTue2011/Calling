"""Crypto for the Zalo PC protocol, reimplemented from the observed
client behaviour (see bao-cao.md for the evidence trail).

Three independent pieces — do not confuse them:

1. ParamCipher — encrypts the *login* API parameters (reqqr, ...).
   Per-request key derived from (zcid, zcid_ext):
     zcid      = AES-256-CBC(key=PARAM_CIPHER_KEY, iv=0,
                             "apiType,deviceId,firstLaunchTimeMs") as UPPER hex
     zcid_ext  = random 6..12 chars (sent in the clear)
     enk       = even(MD5(zcid_ext).hex.upper)[0:8]
                 + even(zcid)[0:12]
                 + reversed(odd(zcid))[0:12]          (32 chars)
     params    = AES-256-CBC(key=enk, iv=0, json) as base64
   PARAM_CIPHER_KEY is a fixed key embedded in the distributed PC app.
   It is NEVER stored in this repo: the deployer supplies it at runtime
   (env ZALO_PC_PARAM_CIPHER_KEY or the session config file). Without it,
   the client falls back to plaintext params + signkey, which the server
   accepts only when param encryption is disabled server-side.

2. signkey — request signature for login APIs:
     signkey = MD5(fixed_salt + api_name + concat(values of params
                   sorted by key, no separator))
   The salt is a short fixed protocol constant of the PC client. It is
   a protocol constant (same for every client, like the endpoint URLs),
   not an account credential; it is kept as a named constant below.

3. Session AES — encrypts *post-login* API parameters (voicecall,
   friends, groups, conversations, ...):
     params = AES-CBC(key=base64decode(zpw_enk), iv=0, json) as base64
   zpw_enk is delivered per session by getLoginInfo after QR login,
   so no embedded key is needed here at all.

4. Post-login RESPONSE envelope — TWO layers (bundle compact-app-pc,
   response handler module kCOK, offset ~16575942; decodeAES /
   getSecretKey / setDecryptKey in the crypto util, offsets
   ~20698147/~20698975; config secretKey:"zpw_enk" at ~8055993;
   getLoginInfo stores it as decryptKey from zpw_enk, ~11816399):
     outer: {error_code: 0, data: "<AES base64 string>"}
     inner: AES-decrypt data with the session key (same AES-CBC,
       zero IV, PKCS7 as the request params) -> JSON
       {error_code, data} -> the inner data is the real payload
       (friends: bare array; groups: {groups, hasMore, total}).
   The outer `data` field is an ENCRYPTED STRING, never the payload
   itself. Code that returns payload["data"] directly reads
   ciphertext as data (and silently gets zero rows, because a string
   parses as "no items"). decode_postlogin_data() below implements
   the client's unwrap exactly.
"""

import hashlib
import json
import random
import string
import uuid

from .aes_pure import ZERO_IV, cbc_decrypt, cbc_encrypt

# Fixed protocol salt used by the PC client's signkey construction.
# Protocol constant, not an account secret (see module docstring).
SIGN_SALT = "zsecure"


def md5_hex(text):
    if isinstance(text, str):
        text = text.encode("utf-8")
    return hashlib.md5(text).hexdigest()


def signkey(api_name, params):
    """MD5(salt + api_name + values in sorted-key order, no separator)."""
    keys = sorted(params.keys())
    blob = SIGN_SALT + api_name + "".join(str(params[k]) for k in keys)
    return md5_hex(blob)


def _split_even_odd(s):
    even = [c for i, c in enumerate(s) if i % 2 == 0]
    odd = [c for i, c in enumerate(s) if i % 2 == 1]
    return even, odd


def _random_zcid_ext(rng=None):
    rng = rng or random
    n = rng.randint(6, 12)
    return "".join(rng.choice(string.hexdigits.lower()) for _ in range(n))


class ParamCipher:
    """One-shot cipher for a single login-API request."""

    def __init__(self, api_type, device_id, first_launch_ms, param_cipher_key,
                 rng=None):
        self.api_type = api_type
        self.device_id = device_id
        self.first_launch_ms = first_launch_ms
        self.key = param_cipher_key
        if isinstance(self.key, str):
            self.key = self.key.encode("utf-8")
        plain = "%s,%s,%s" % (api_type, device_id, first_launch_ms)
        self.zcid = cbc_encrypt(self.key, ZERO_IV,
                                plain.encode("utf-8")).hex().upper()
        self.zcid_ext = _random_zcid_ext(rng)
        self.enk = self._derive_enk()

    def _derive_enk(self):
        md5_ext = md5_hex(self.zcid_ext).upper()
        even_md5, _ = _split_even_odd(md5_ext)
        even_zcid, odd_zcid = _split_even_odd(self.zcid)
        # JS: i.reverse().slice(0,12) — reverse the WHOLE odd array,
        # then take the first 12 (= last 12 odd chars, reversed).
        return ("".join(even_md5[:8])
                + "".join(even_zcid[:12])
                + "".join(odd_zcid[::-1][:12]))

    def encrypted_params(self):
        return {"zcid": self.zcid, "zcid_ext": self.zcid_ext,
                "enc_ver": "v2"}

    def encrypt(self, params_obj):
        """Return (encrypted_params_dict_with_params, enk)."""
        raw = json.dumps(params_obj, separators=(",", ":"),
                         ensure_ascii=False)
        enc = cbc_encrypt(self.enk.encode("utf-8"), ZERO_IV,
                          raw.encode("utf-8"))
        import base64
        out = self.encrypted_params()
        out["params"] = base64.b64encode(enc).decode("ascii")
        return out, self.enk

    @staticmethod
    def decrypt_response(enk, data_b64):
        """Decrypt a response `data` field (base64) with the request enk."""
        import base64
        raw = base64.b64decode(data_b64)
        return cbc_decrypt(enk.encode("utf-8"), ZERO_IV, raw).decode("utf-8")


def session_aes_encrypt(zpw_enk_b64, json_text):
    """Post-login params encryption: AES-CBC, zero IV, base64 output."""
    import base64
    key = base64.b64decode(zpw_enk_b64)
    ct = cbc_encrypt(key, ZERO_IV, json_text.encode("utf-8"))
    return base64.b64encode(ct).decode("ascii")


def session_aes_decrypt(zpw_enk_b64, data_b64):
    import base64
    key = base64.b64decode(zpw_enk_b64)
    raw = base64.b64decode(data_b64)
    return cbc_decrypt(key, ZERO_IV, raw).decode("utf-8")


def decode_postlogin_data(payload, zpw_enk_b64):
    """Decode the two-layer post-login response envelope (client
    unwrap in bundle module kCOK): outer {error_code: 0, data} where
    data is an AES-256-CBC base64 STRING encrypted with the session
    key; decrypt it (zero IV, PKCS7) and JSON-parse the inner
    {error_code, data}, returning the inner data. An inner
    error_code != 0 raises. A plain dict/list data is returned as-is
    (defensive: some responses may already be decoded); a missing
    data field resolves to None, like the client's `else t()`."""
    data = payload.get("data")
    if isinstance(data, str):
        if not data:
            return None
        try:
            inner = json.loads(session_aes_decrypt(zpw_enk_b64, data))
        except Exception as exc:
            raise RuntimeError("response decrypt failed: %s" % exc)
        if isinstance(inner, dict):
            if inner.get("error_code") not in (0, None):
                raise RuntimeError("response inner error_code=%s %s" % (
                    inner.get("error_code"),
                    inner.get("error_message", "")))
            return inner.get("data")
        return inner
    return data


def make_device_id(app_ua="zalo-pc-qr/1.0"):
    """Client-generated device id, same shape as the PC client:
    UUID + '-' + MD5(user-agent). Persist it in the session file."""
    return "%s-%s" % (str(uuid.uuid4()), md5_hex(app_ua))
