"""Runtime key material for the signaling client.

All values are injected by the caller at runtime (from a real
session). NOTHING here contains real key values, and no default
is a usable key: operations that need a missing key raise instead
of silently using a placeholder.

Sources (from the disassembly reports):
- k1 = CoreUtility.p, k2 = CoreUtility.q, taken from a server JSON
  payload (bao-cao-gap.md §2). updateKeySet stores k1 verbatim and
  Base64-decodes k2 into the current transport key, rotating the
  previous current key into the "old" slot (bao-cao-transport.md §3).
- XOR params key: working hypothesis (UNVERIFIED at runtime) is
  that it equals k1 (bao-cao-transport.md S4). The client keeps it
  as a separate field so the hypothesis can be replaced without
  touching the transport code.
- Prov key-set map: name -> (s1, s2) pairs (ZaloCache+0xd60).
  The auth-path name is the peer address "host:port"
  (bao-cao-gap.md §4); the normal receive path uses the empty
  name, which drops Prov frames (faithful to the original).
"""

import base64
import binascii


class KeySet:
    """Holds the session keys for one signaling connection."""

    def __init__(
        self,
        k1: str | None = None,
        k2: str | None = None,
        transport_key: bytes | None = None,
        old_transport_key: bytes | None = None,
        xor_key: bytes | None = None,
        e2e_src_id: int = 0,
        prov_map: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self.k1 = k1
        self.k2 = k2
        # If only k2 is given, derive the transport key exactly like
        # updateKeySet does: Base64-decode k2.
        if transport_key is None and k2 is not None:
            try:
                transport_key = base64.b64decode(k2, validate=False)
            except binascii.Error:
                transport_key = None
        self.transport_key = transport_key
        self.old_transport_key = old_transport_key
        # Working hypothesis: XOR key == k1 (UNVERIFIED at runtime).
        if xor_key is None and k1 is not None:
            xor_key = k1.encode("utf-8")
        self.xor_key = xor_key
        self.e2e_src_id = e2e_src_id
        self.prov_map: dict[str, tuple[str, str]] = dict(prov_map or {})

    def require_transport_key(self) -> bytes:
        if not self.transport_key:
            raise ValueError(
                "no transport key: inject KeySet(k2=...) or "
                "KeySet(transport_key=...) from a real session"
            )
        return self.transport_key

    def rotate_transport_key(self, new_key: bytes) -> None:
        """Mirror the native key rotation: old = current; current = new."""
        self.old_transport_key = self.transport_key
        self.transport_key = new_key

    def update_key_set(self, k1: str, k2: str) -> None:
        """Mirror native updateKeySet(k1, k2)."""
        self.k1 = k1
        self.k2 = k2
        new_key = base64.b64decode(k2, validate=False)
        self.rotate_transport_key(new_key)
        if self.xor_key is None:
            self.xor_key = k1.encode("utf-8")
