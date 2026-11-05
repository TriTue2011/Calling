"""Transport layer: framing + encryption schemes.

Wire frame (confirmed on real pcap, bao-cao.md §5, bao-cao-transport.md §2):
    [u32 L, little-endian][u8 wire_type][payload]
    L = number of bytes AFTER the u32 field; total frame = L + 4.

    wire_type = inner_type + 2 * scheme
        scheme 0 (plaintext): wire <= 2, wire_type IS the inner type,
                              payload = message bytes directly.
        scheme 1 (AES-GCM-256): wire 3..4, wire_type = inner + 2,
                              payload = [cipher][16-byte tag][12-byte nonce]
                              (nonce = last 12 bytes of payload).
        scheme 2 (ProvV21, ECDH + GCM): wire >= 5, wire_type = inner + 4,
                              payload = [cipher][tag][nonce][A 32][B 32].

    Observed inner types: 1 (server-side only), 2 (normal messages),
    4 (prov handshake). Because wire = inner + 2*scheme, GCM encoding
    is only unambiguous for inner 1..2 (wire 3..4) and Prov encoding
    for inner 2..4 (wire 6..8); the encoders enforce this.

    GCM encrypts only the message (the 5-byte plain prefix
    [u32][u8 inner] is NOT encrypted). GCM decrypt failure with the
    current key and wire <= 4 retries with the old key (native
    "RE-DECRYPT WITH OLD" path).

    Prov: ECDH via X25519 (32-byte public keys — the curve is inferred
    from the 32-byte server pubkey, NOT absolutely confirmed). The
    shared-secret -> GCM-key derivation has NO isolated KDF step in
    the disassembly (bao-cao-transport.md §2.4: AESGCM256Encrypt
    "with the shared secret derived from ECDH"); see
    prov_kdf.identity_kdf for the literal-reading hypothesis
    (shared secret used directly as the 32-byte key), which is
    UNCONFIRMED and replaceable via the ecdh_kdf hook. The
    identities of the trailing 32-byte fields A/B are likewise
    partly unconfirmed (bao-cao-transport.md S2): A is
    HYPOTHESIZED to be the sender's public-key material (so the
    server can derive the same shared secret) — in the ECDH path,
    a defaults to the ephemeral client public key; B's identity is
    unpinned, so the caller must supply it explicitly. This module
    never fabricates B.

    CBCXor+MD5 fallback: the exact CBCXor construction is NOT
    documented either. This module implements the frame LAYOUT
    ([cipher][16-byte MD5], MD5 over plain-prefix + cipher) with a
    pluggable length-preserving cipher hook (default: raise).
    On decode, wire inner+2 frames are tried as GCM first, then as
    CBC fallback when a cipher hook is configured — an interpretation,
    flagged as such, because the reports do not pin a distinct
    wire_type for CBC frames. Static-analysis note (not a proven
    construction): the pcap XOR-identical trace (§2.6 — cipher
    differs exactly where plaintext differs) is characteristic of
    a STREAM cipher, not CBC (which would avalanche after the
    first differing block), so the unknown key schedule is most
    plausibly a repeating-key XOR stream; the key schedule itself
    is unknown and no candidate is implemented here.
"""

import hashlib
import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from zalo_call.errors import DecryptError, FrameError

MAX_FRAME_BYTES = 16 * 1024 * 1024
GCM_TAG_LEN = 16
GCM_NONCE_LEN = 12
PROV_AB_LEN = 32


def encode_wire(wire_type: int, payload: bytes) -> bytes:
    """Encode one wire frame: [u32 L][u8 wire_type][payload]."""
    return struct.pack("<I", 1 + len(payload)) + struct.pack(
        "<B", wire_type & 0xFF
    ) + payload


def encode_plain_frame(inner_type: int, message: bytes) -> bytes:
    """Plaintext frame. (Identical layout to encode_wire: for scheme 0
    the wire type IS the inner type and the payload IS the message.)"""
    return encode_wire(inner_type, message)


class FrameReader:
    """Incremental wire-frame parser for a byte stream (socket)."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        """Consume bytes, return all complete (wire_type, payload) frames."""
        self._buf += data
        frames: list[tuple[int, bytes]] = []
        while True:
            if len(self._buf) < 5:
                break
            (length,) = struct.unpack_from("<I", self._buf, 0)
            if length < 1:
                raise FrameError(f"wire frame length {length} < 1")
            if length > MAX_FRAME_BYTES:
                raise FrameError(f"wire frame length {length} exceeds cap")
            total = 4 + length
            if len(self._buf) < total:
                break
            wire_type = self._buf[4]
            payload = bytes(self._buf[5:total])
            del self._buf[:total]
            frames.append((wire_type, payload))
        return frames


def _aesgcm(key: bytes) -> AESGCM:
    if len(key) != 32:
        raise DecryptError(f"AES-GCM-256 needs a 32-byte key, got {len(key)}")
    return AESGCM(key)


def gcm_encrypt(
    key: bytes, inner_type: int, message: bytes, nonce: bytes | None = None
) -> bytes:
    """Build a GCM wire frame. inner_type must be 1 or 2 (wire 3..4)."""
    if inner_type not in (1, 2):
        raise FrameError(f"GCM inner_type must be 1 or 2, got {inner_type}")
    if nonce is None:
        nonce = os.urandom(GCM_NONCE_LEN)
    if len(nonce) != GCM_NONCE_LEN:
        raise FrameError("GCM nonce must be 12 bytes")
    cipher_and_tag = _aesgcm(key).encrypt(nonce, message, None)
    cipher, tag = cipher_and_tag[:-GCM_TAG_LEN], cipher_and_tag[-GCM_TAG_LEN:]
    return encode_wire(inner_type + 2, cipher + tag + nonce)


def _gcm_decrypt_payload(key: bytes, payload: bytes) -> bytes:
    if len(payload) < GCM_TAG_LEN + GCM_NONCE_LEN:
        raise DecryptError("GCM payload too short for tag+nonce")
    cipher = payload[: -GCM_TAG_LEN - GCM_NONCE_LEN]
    tag = payload[-GCM_TAG_LEN - GCM_NONCE_LEN : -GCM_NONCE_LEN]
    nonce = payload[-GCM_NONCE_LEN:]
    try:
        return _aesgcm(key).decrypt(nonce, cipher + tag, None)
    except InvalidTag as exc:
        raise DecryptError("GCM authentication failed") from exc


def gcm_decrypt(
    key: bytes, wire_type: int, payload: bytes
) -> tuple[int, bytes]:
    """Decrypt a GCM wire frame -> (inner_type, message)."""
    return wire_type - 2, _gcm_decrypt_payload(key, payload)


def gcm_decrypt_with_retry(
    current_key: bytes, old_key: bytes | None, wire_type: int, payload: bytes
) -> tuple[int, bytes]:
    """Try the current key, then the old key (native retry path,
    only for wire <= 4)."""
    try:
        return gcm_decrypt(current_key, wire_type, payload)
    except DecryptError:
        if old_key is not None and wire_type <= 4:
            return gcm_decrypt(old_key, wire_type, payload)
        raise


def prov_encrypt(
    inner_type: int,
    message: bytes,
    a: bytes | None = None,
    b: bytes | None = None,
    gcm_key: bytes | None = None,
    server_pubkey: bytes | None = None,
    ecdh_kdf=None,
    nonce: bytes | None = None,
) -> tuple[bytes, bytes | None]:
    """Build a Prov wire frame.

    Returns (wire_frame, client_pubkey_or_None). Either pass gcm_key
    directly (tests / known-key paths; then a and b are both
    required) or server_pubkey + ecdh_kdf (real ECDH path:
    ephemeral X25519 keypair, shared secret -> ecdh_kdf(shared) ->
    32-byte GCM key). In the ECDH path, a defaults to the
    ephemeral client public key (HYPOTHESIS S2: A = sender
    public-key material); b must always be supplied explicitly
    (its identity is unpinned). For a recommended ecdh_kdf see
    prov_kdf.identity_kdf (hypothesis, UNCONFIRMED).
    """
    if inner_type not in (2, 4):
        raise FrameError(f"Prov inner_type must be 2 or 4, got {inner_type}")
    if b is None or len(b) != PROV_AB_LEN:
        raise FrameError("Prov B field must be exactly 32 bytes")
    client_pubkey = None
    if gcm_key is None:
        if server_pubkey is None or ecdh_kdf is None:
            raise DecryptError(
                "Prov encryption needs gcm_key, or server_pubkey + "
                "ecdh_kdf (see prov_kdf.identity_kdf for the "
                "unconfirmed hypothesis; the KDF is not documented "
                "in the disassembly reports)"
            )
        if len(server_pubkey) != 32:
            raise FrameError("Prov server pubkey must be 32 bytes")
        ephemeral = X25519PrivateKey.generate()
        shared = ephemeral.exchange(
            X25519PublicKey.from_public_bytes(server_pubkey)
        )
        gcm_key = ecdh_kdf(shared)
        client_pubkey = ephemeral.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )
        if len(gcm_key) != 32:
            raise DecryptError("ecdh_kdf must return a 32-byte GCM key")
        if a is None:
            # HYPOTHESIS S2: A = sender public-key material.
            a = client_pubkey
    if a is None or len(a) != PROV_AB_LEN:
        raise FrameError("Prov A field must be exactly 32 bytes")
    if nonce is None:
        nonce = os.urandom(GCM_NONCE_LEN)
    cipher_and_tag = _aesgcm(gcm_key).encrypt(nonce, message, None)
    cipher, tag = cipher_and_tag[:-GCM_TAG_LEN], cipher_and_tag[-GCM_TAG_LEN:]
    payload = cipher + tag + nonce + a + b
    return encode_wire(inner_type + 4, payload), client_pubkey


def prov_parse_payload(payload: bytes) -> dict:
    """Split a Prov payload into its fields (no decryption)."""
    min_len = GCM_TAG_LEN + GCM_NONCE_LEN + 2 * PROV_AB_LEN
    if len(payload) < min_len:
        raise FrameError("Prov payload too short")
    return {
        "cipher": payload[: -GCM_TAG_LEN - GCM_NONCE_LEN - 2 * PROV_AB_LEN],
        "tag": payload[
            -GCM_TAG_LEN - GCM_NONCE_LEN - 2 * PROV_AB_LEN :
            -GCM_NONCE_LEN - 2 * PROV_AB_LEN
        ],
        "nonce": payload[-GCM_NONCE_LEN - 2 * PROV_AB_LEN : -2 * PROV_AB_LEN],
        "a": payload[-2 * PROV_AB_LEN : -PROV_AB_LEN],
        "b": payload[-PROV_AB_LEN:],
    }


def prov_decrypt(
    gcm_key: bytes, wire_type: int, payload: bytes
) -> tuple[int, bytes, bytes, bytes]:
    """Decrypt a Prov wire frame with a known GCM key.

    Returns (inner_type, message, a, b).
    """
    parts = prov_parse_payload(payload)
    try:
        message = _aesgcm(gcm_key).decrypt(
            parts["nonce"], parts["cipher"] + parts["tag"], None
        )
    except InvalidTag as exc:
        raise DecryptError("Prov GCM authentication failed") from exc
    return wire_type - 4, message, parts["a"], parts["b"]


def _cbc_plain_prefix(inner_type: int, message_len: int) -> bytes:
    return struct.pack("<I", 1 + message_len) + struct.pack(
        "<B", inner_type & 0xFF
    )


def cbc_fallback_encrypt(
    inner_type: int, message: bytes, cipher_fn
) -> bytes:
    """Build a CBCXor+MD5 fallback wire frame.

    cipher_fn must be a length-preserving involution (XOR stream
    cipher). The MD5 covers plain_prefix + cipher (interpretation:
    the reports say "MD5 on header + cipher"; the exact header
    bytes are TODO — this uses the plain-frame prefix).
    The wire type reuses the GCM slot (inner + 2); see module docstring.
    """
    if cipher_fn is None:
        raise DecryptError(
            "CBCXor cipher construction is TODO: not documented in "
            "the disassembly reports (only the frame layout + MD5 "
            "placement are known)"
        )
    cipher = cipher_fn(message)
    if len(cipher) != len(message):
        raise FrameError("CBC fallback cipher_fn must preserve length")
    digest = hashlib.md5(_cbc_plain_prefix(inner_type, len(message)) + cipher)
    return encode_wire(inner_type + 2, cipher + digest.digest())


def cbc_fallback_decrypt(
    inner_type: int, payload: bytes, cipher_fn
) -> bytes:
    """Verify MD5 and decrypt a CBC fallback payload."""
    if cipher_fn is None:
        raise DecryptError("CBCXor cipher construction is TODO")
    if len(payload) < 16:
        raise DecryptError("CBC fallback payload too short for MD5")
    cipher, digest = payload[:-16], payload[-16:]
    message = cipher_fn(cipher)
    expected = hashlib.md5(
        _cbc_plain_prefix(inner_type, len(message)) + cipher
    ).digest()
    if expected != digest:
        raise DecryptError("CBC fallback MD5 mismatch")
    return message


def decrypt_wire_frame(
    keyset,
    wire_type: int,
    payload: bytes,
    keyset_name: str = "",
    cbc_cipher=None,
    prov_map_kdf=None,
) -> tuple[int, bytes]:
    """Decrypt one wire frame -> (inner_type, message).

    keyset_name is the Prov key-set name: "" on the normal receive
    path (Prov frames are dropped there, faithful to the original),
    "host:port" on the auth path (bao-cao-gap.md §4).
    """
    if wire_type <= 2:
        return wire_type, payload
    if wire_type >= 5:
        inner = wire_type - 4
        if not keyset_name:
            raise DecryptError(
                "Prov frame on normal path dropped (empty key-set "
                "name, faithful to ReceiveFullResponse)"
            )
        pair = (keyset.prov_map or {}).get(keyset_name)
        if pair is None:
            raise DecryptError(f"no Prov key-set for name {keyset_name!r}")
        if prov_map_kdf is None:
            raise DecryptError(
                "Prov key-set -> GCM key derivation is TODO: not "
                "documented in the disassembly reports"
            )
        gcm_key = prov_map_kdf(pair[0], pair[1])
        _, message, _, _ = prov_decrypt(gcm_key, wire_type, payload)
        return inner, message
    # wire 3..4: GCM, then CBC fallback, then fail.
    inner = wire_type - 2
    try:
        current = keyset.require_transport_key()
    except ValueError as exc:
        raise DecryptError(str(exc)) from exc
    try:
        return gcm_decrypt_with_retry(
            current, keyset.old_transport_key, wire_type, payload
        )
    except DecryptError:
        if cbc_cipher is not None:
            return inner, cbc_fallback_decrypt(inner, payload, cbc_cipher)
        raise
