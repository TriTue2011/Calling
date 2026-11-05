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
from . import engine_seam, protocol, qr_login, session as session_mod
from . import signaling as signaling_mod
from .crypto import make_device_id

__all__ = ["protocol", "qr_login", "session_mod", "signaling_mod",
           "contacts_mod", "engine_seam", "make_device_id"]
