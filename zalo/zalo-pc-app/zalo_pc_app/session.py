"""Persistent session store.

One JSON file, mode 0600, inside the mounted volume directory.
It holds everything a restart needs to resume without re-scanning:

  device_id   client-generated device id (UUID-MD5 shape, stable)
  computer    hostname sent as computer_name
  uid/dkey    account id + device key from the QR confirm
  phonenum    profile phone number (display only)
  zpw_sek     session cookie (sent with post-login API calls)
  zpw_kt      refresh token for session renewal
  zpw_enk     per-session AES key for post-login params (getLoginInfo)
  service_map domain overrides from getLoginInfo config (may be empty)
  ws_endpoint sync/control WebSocket endpoint from getLoginInfo config
  poll_msg_urls  long-poll tin den (99100) URL list = config
                 zpw_chts_new (server tra ve o getLoginInfo); rong
                 khi phien cu chua co (can refresh getLoginInfo)
  poll_ctl_urls  long-poll dieu khien (99101) URL list = config
                 zpw_ctrs_new (chua dung o dot nay)
  poll_msg_timeout / poll_ctl_timeout  config zpw_conf lp_* (giay,
                 mac dinh 30)
  trusted_device flags (self_g / qr_format_trust_device / logo_qr)
  login_type  "qr" for QR logins
  status      see STATUS_* below

No other file in this project ever contains a session secret, and the
store file itself is gitignored (see .gitignore).
"""

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

STATUS_NO_SESSION = "chua_dang_nhap"
STATUS_QR_WAITING = "cho_quet"
STATUS_QR_SCANNED = "da_quet_cho_xac_nhan"
STATUS_QR_EXPIRED = "qr_het_han"
STATUS_QR_REJECTED = "bi_tu_choi"
STATUS_LOGGED_IN = "da_dang_nhap"
STATUS_RATE_LIMITED = "gioi_han_tao_qr"


class SessionStore:
    def __init__(self, path):
        self.path = path

    def exists(self):
        return os.path.exists(self.path)

    def load(self):
        """Doc session tu dia.

        Tra None khi khong co phien dung duoc — gom ca truong hop
        file hong (H4): JSON khong parse duoc hoac noi dung khong
        phai dict thi file duoc doi ten thanh session.json.corrupt
        (giu lai de doi chieu, KHONG xoa) roi tra None, de server
        khoi dong voi phien trong thay vi chet voi JSONDecodeError
        truoc ca main(). File khong ton tai van raise
        FileNotFoundError nhu truoc; server bao ve bang exists().
        """
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise
        except ValueError as e:
            return self._quarantine_corrupt("JSON hong: %s" % e)
        if not isinstance(data, dict):
            return self._quarantine_corrupt(
                "noi dung khong phai dict (kieu %s)"
                % type(data).__name__)
        return data

    def _quarantine_corrupt(self, reason):
        """Doi ten file session hong sang session.json.corrupt roi
        tra None. Neu doi ten that bai (vd quyen ghi) thi van tra
        None de server khoi dong duoc; lan khoi dong sau se thu
        doi ten lai."""
        corrupt_path = self.path + ".corrupt"
        try:
            os.replace(self.path, corrupt_path)
            renamed = corrupt_path
        except OSError as e:
            renamed = "khong doi ten duoc (%s)" % e
        msg = ("session.json hong (%s), da doi ten thanh %s, khoi "
               "dong voi phien trong — quet lai QR"
               % (reason, renamed))
        logger.warning(msg)
        print(msg, file=sys.stderr, flush=True)
        return None

    def save(self, data):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def clear(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


def new_session(device_id, computer):
    return {
        "device_id": device_id,
        "computer": computer,
        "uid": "",
        "dkey": "",
        "phonenum": "",
        "zpw_sek": "",
        "zpw_kt": "",
        "zpw_enk": "",
        "service_map": {},
        "ws_endpoint": "",
        "poll_msg_urls": [],
        "poll_ctl_urls": [],
        "poll_msg_timeout": 30,
        "poll_ctl_timeout": 30,
        "trusted_device": {"self_g": False,
                           "qr_format_trust_device": False,
                           "logo_qr": True},
        "login_type": "qr",
        "status": STATUS_NO_SESSION,
    }
