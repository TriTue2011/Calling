"""Prov (ECDH) key derivation — what is known, what is not.

Evidence status (bao-cao-transport.md §2.4, §7 S2/U4):
- ProvV21 uses X25519 ECDH (32-byte keys, server pubkey decoded
  via curve_decode_point) and then AES-GCM-256 "with the shared
  secret derived from ECDH". The disassembly does NOT isolate a
  KDF step (no HKDF/SHA call pinned between the ECDH exchange
  and the AESGCM256Encrypt call).
- An X25519 shared secret is exactly 32 bytes, and AES-GCM-256
  takes exactly a 32-byte key. The LITERAL reading of the
  evidence is therefore that the shared secret is used directly
  as the GCM key, with no derivation step. That reading is
  implemented here as identity_kdf — but it is a HYPOTHESIS,
  explicitly UNCONFIRMED: a hash/KDF step may exist that the
  disassembly did not isolate, and only a real handshake (with
  known keys) can confirm or refute it. Callers that need a
  different derivation must inject their own ecdh_kdf; the hook
  in transport.prov_encrypt stays the override point.
- SEPARATE UNKNOWN (do not conflate): the receive path derives
  its GCM key from a (s1, s2) string pair in the Prov key-set
  map (ZaloCache+0xd60). Those are STRINGS, not a 32-byte
  secret, so no formula is proposed for them at all — the
  prov_map_kdf hook in transport.decrypt_wire_frame must be
  supplied by the caller, and it raises until then.
- Also unknown: the first Prov message's content (U4: frame size
  known, Req 23 + params 147, opcode/params unknown) and the
  second Prov trailing field B's identity (S2: A is hypothesized
  to be the sender's public-key material; B is unpinned).

Nothing in this module fabricates a formula. The identity
hypothesis is labeled as such wherever it is used.
"""

from zalo_call.errors import DecryptError


def identity_kdf(shared_secret: bytes) -> bytes:
    """HYPOTHESIS (UNCONFIRMED): use the ECDH shared secret directly
    as the 32-byte AES-GCM-256 key.

    Basis: X25519 shared secret is 32 bytes; AES-GCM-256 needs a
    32-byte key; the disassembly shows AESGCM256Encrypt "with the
    shared secret derived from ECDH" and no isolated KDF step.
    If a real handshake later shows a KDF step exists, replace
    this function via the ecdh_kdf hook — do NOT silently keep
    using it.
    """
    if len(shared_secret) != 32:
        raise DecryptError(
            f"ECDH shared secret must be 32 bytes, got {len(shared_secret)}"
        )
    return shared_secret
