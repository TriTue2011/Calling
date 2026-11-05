"""Zalo PC-style app service: QR login + session + signaling + UI.

Run:  python3 -m zalo_pc_app.server
Env:  ZALO_PC_DATA_DIR  (default ./data)
      ZALO_PC_PORT      (default 8080)
      ZALO_PC_HOST      (default 127.0.0.1)
      ZALO_PC_PARAM_CIPHER_KEY (optional; without it, login params go
        plaintext + signkey — accepted only if the server has param
        encryption disabled)
"""

from . import contacts as contacts_mod
from . import engine_seam, media_endpoints, protocol, qr_login
from . import session as session_mod
from . import signaling as signaling_mod
from .crypto import make_device_id

# App version marker: returned by GET /api/status and shown in the UI
# footer, so a deploy can be verified against the pushed code ("is the
# server really running the new image?"). Bump the tag on every fix
# that changes behaviour; the Docker build may override it with the
# exact commit sha via env ZALO_PC_VERSION (see Dockerfile).
VERSION = "2026-11-05-call-11301"

__all__ = ["protocol", "qr_login", "session_mod", "signaling_mod",
           "contacts_mod", "engine_seam", "media_endpoints",
           "make_device_id", "VERSION"]
