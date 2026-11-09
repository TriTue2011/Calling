"""Dang nhap app (cong ngoai) cho Zalo PC app.

Mot tai khoan duy nhat, dat qua bien moi truong luc deploy — KHONG co
mat khau mac dinh trong repo, KHONG hardcode user/mat khau trong code:

  ZALO_PC_APP_USER             ten dang nhap (bat buoc)
  ZALO_PC_APP_PASSWORD         mat khau dang plain text (dat 1 trong 2
                               bien mat khau; uu tien HASH neu ca 2 co)
  ZALO_PC_APP_PASSWORD_HASH    hash da tinh san, dang
                               $pbkdf2-sha256$<iterations>$<salt_b64>$<hash_b64>
                               (tinh bang: python3 -m zalo_pc_app.app_auth)

Mat khau luu dang hash PBKDF2-HMAC-SHA256 (210.000 vong, salt 16 byte,
hash 32 byte). Neu dung ZALO_PC_APP_PASSWORD: salt + hash duoc luu
vao <data>/app_auth.json (mode 0600, cung thu muc data voi
session.json); khi doi mat khau qua env, file nay duoc ghi de bang
salt/hash moi. Neu dung ZALO_PC_APP_PASSWORD_HASH: dung thang hash
do, khong ghi file.

Thieu ca hai bien mat khau (hoac thieu user) -> MissingAppCredentials;
server (main) tu choi khoi dong, khong bao gio tu chay khong mat khau.

Phien dang nhap app: token ngau nhien (secrets.token_urlsafe), luu
phia server (chi trong bo nho — mat khi restart container), han 8 gio
mac dinh (doi qua ZALO_PC_APP_SESSION_HOURS). Cookie HttpOnly,
SameSite=Lax, Path=/; Secure chi khi ZALO_PC_APP_COOKIE_SECURE=1
(dat sau reverse proxy HTTPS).
"""

import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import time

ITERATIONS = 210000
SALT_BYTES = 16
HASH_BYTES = 32
DEFAULT_SESSION_HOURS = 8.0
COOKIE_NAME = "zalo_pc_app"
VERIFIER_FILENAME = "app_auth.json"

# H3 — chong brute-force o /api/app/login (chi trong bo nho tien
# trinh, restart la het — day la muc chong do co ban, KHONG phai WAF):
# sau MAX_FAILED_LOGINS lan sai lien tiep tu cung IP, IP do bi khoa
# tam LOCKOUT_SECONDS giay. Nguong 5 de 1-2 lan go sai cua user that
# khong bi khoa nham; dang nhap dung reset bo dem va khong bi cham
# (khong sleep/delay tren duong dung). Dem theo IP vi chi co 1 tai
# khoan dung chung — dem theo username thi ke do van do duoc.
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 300  # 5 phut
# Bo nho cu (IP khong con khoa, khong sai them) duoc don sau thoi
# gian nay de dict khong phinh vo han.
FAILED_ENTRY_TTL_SECONDS = 3600


class MissingAppCredentials(Exception):
    """Thieu bien moi truong tai khoan app (xem module docstring)."""


def hash_password(password, salt=None, iterations=ITERATIONS):
    """Tra ve chuoi hash $pbkdf2-sha256$<iter>$<salt_b64>$<hash_b64>."""
    if salt is None:
        salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                             iterations)
    return "$pbkdf2-sha256$%d$%s$%s" % (
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"))


def verify_password(password, stored):
    """So sanh mat khau voi chuoi hash (constant-time). Sai dinh dang
    -> False, khong bao gio raise."""
    try:
        if not isinstance(stored, str):
            return False
        parts = stored.split("$")
        # ['', 'pbkdf2-sha256', iter, salt_b64, hash_b64]
        if len(parts) != 5 or parts[1] != "pbkdf2-sha256":
            return False
        iterations = int(parts[2])
        salt = base64.b64decode(parts[3])
        expected = base64.b64decode(parts[4])
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 salt, iterations)
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError, base64.binascii.Error):
        return False


def _verifier_path(data_dir):
    return os.path.join(data_dir, VERIFIER_FILENAME)


def _load_verifier_file(data_dir):
    try:
        with open(_verifier_path(data_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
        stored = data.get("password_hash", "")
        if isinstance(stored, str) and stored.startswith("$pbkdf2-sha256$"):
            return stored
    except (OSError, ValueError):
        pass
    return None


def _save_verifier_file(data_dir, stored):
    os.makedirs(data_dir, exist_ok=True)
    tmp = _verifier_path(data_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"password_hash": stored}, f)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, _verifier_path(data_dir))
    try:
        os.chmod(_verifier_path(data_dir), 0o600)
    except OSError:
        pass


class AppAuth:
    """Mot tai khoan app + cac phien dang nhap (token, trong bo nho)."""

    def __init__(self, username, password_hash, session_hours=None,
                 time_fn=None):
        self.username = username
        self.password_hash = password_hash
        self.session_hours = (DEFAULT_SESSION_HOURS if session_hours is None
                              else session_hours)
        # time_fn: chi de test chich dong ho gia (mac dinh time.time).
        self._now = time_fn or time.time
        self._sessions = {}  # token -> (username, expires_at)
        # H3: lan sai theo IP — chi trong bo nho, restart la het.
        # ip -> {"count": int, "locked_until": float, "last_at": float}
        self._failed = {}
        import threading
        self._lock = threading.Lock()

    # -- khoi tao tu env -------------------------------------------------
    @classmethod
    def from_env(cls, data_dir, env=None, time_fn=None):
        env = os.environ if env is None else env
        username = (env.get("ZALO_PC_APP_USER") or "").strip()
        password = env.get("ZALO_PC_APP_PASSWORD") or ""
        password_hash = env.get("ZALO_PC_APP_PASSWORD_HASH") or ""
        if not username:
            raise MissingAppCredentials(
                "Thieu ten dang nhap app: dat bien moi truong "
                "ZALO_PC_APP_USER luc deploy (khong co tai khoan mac dinh).")
        if password_hash:
            if not password_hash.startswith("$pbkdf2-sha256$"):
                raise MissingAppCredentials(
                    "ZALO_PC_APP_PASSWORD_HASH sai dinh dang (can "
                    "$pbkdf2-sha256$<iterations>$<salt_b64>$<hash_b64>); "
                    "tinh lai bang: python3 -m zalo_pc_app.app_auth")
            stored = password_hash
        elif password:
            stored = _load_verifier_file(data_dir)
            if stored is not None and verify_password(password, stored):
                pass  # mat khau khong doi: giu nguyen salt/hash cu
            else:
                # Lan dau hoac da doi mat khau: salt moi, ghi de file.
                stored = hash_password(password)
                _save_verifier_file(data_dir, stored)
        else:
            raise MissingAppCredentials(
                "Thieu mat khau app: dat ZALO_PC_APP_PASSWORD hoac "
                "ZALO_PC_APP_PASSWORD_HASH luc deploy (khong co mat "
                "khau mac dinh; server se khong khoi dong).")
        try:
            hours = float(env.get("ZALO_PC_APP_SESSION_HOURS") or
                          DEFAULT_SESSION_HOURS)
            if hours <= 0:
                raise ValueError
        except ValueError:
            raise MissingAppCredentials(
                "ZALO_PC_APP_SESSION_HOURS phai la so > 0 (gio).")
        return cls(username, stored, session_hours=hours, time_fn=time_fn)

    # -- dang nhap --------------------------------------------------------
    def verify(self, username, password):
        """Dung/sai chung mot ket qua False — khong lo user co ton tai
        hay khong. So sanh constant-time ca user lan hash."""
        if not isinstance(username, str) or not isinstance(password, str):
            return False
        user_ok = hmac.compare_digest(username, self.username)
        pass_ok = verify_password(password, self.password_hash)
        return user_ok and pass_ok

    # -- H3: chong brute-force theo IP (bo nho, restart la het) --------
    def _prune_failed(self, now):
        """Don muc het han: khoa da het + khong sai them qua TTL.
        Goi khi da giu self._lock."""
        for ip in list(self._failed):
            entry = self._failed[ip]
            if entry["locked_until"] and now >= entry["locked_until"]:
                del self._failed[ip]
            elif now - entry["last_at"] > FAILED_ENTRY_TTL_SECONDS:
                del self._failed[ip]

    @staticmethod
    def _norm_ip(ip):
        ip = (ip or "").strip()
        return ip if ip else "unknown"

    def is_locked(self, ip, now=None):
        """True neu IP dang trong thoi gian khoa tam."""
        return self.lock_remaining(ip, now=now) > 0

    def lock_remaining(self, ip, now=None):
        """So giay con lai cua khoa tam (0 neu khong bi khoa).
        Het khoa thi bo dem cua IP cung reset (don o _prune_failed)."""
        now = self._now() if now is None else now
        ip = self._norm_ip(ip)
        with self._lock:
            self._prune_failed(now)
            entry = self._failed.get(ip)
            if not entry or not entry["locked_until"]:
                return 0
            remaining = entry["locked_until"] - now
            return int(remaining) + (1 if remaining % 1 else 0)

    def failed_count(self, ip, now=None):
        """So lan sai lien tiep hien tai cua IP (0 neu chua sai /
        da reset / het khoa)."""
        now = self._now() if now is None else now
        ip = self._norm_ip(ip)
        with self._lock:
            self._prune_failed(now)
            entry = self._failed.get(ip)
            return entry["count"] if entry else 0

    def record_failed_login(self, ip, now=None):
        """Ghi 1 lan sai tu IP; du nguong thi khoa tam 5 phut.
        Log IP + so lan + thoi gian (KHONG log mat khau da thu).
        Tra ve so lan sai lien tiep sau lan nay."""
        now = self._now() if now is None else now
        ip = self._norm_ip(ip)
        with self._lock:
            self._prune_failed(now)
            entry = self._failed.get(ip)
            if entry is None:
                entry = {"count": 0, "locked_until": 0, "last_at": now}
                self._failed[ip] = entry
            entry["count"] += 1
            entry["last_at"] = now
            if entry["count"] >= MAX_FAILED_LOGINS and not entry["locked_until"]:
                entry["locked_until"] = now + LOCKOUT_SECONDS
                print("[app-login] sai lien tiep %d lan tu ip=%s -> "
                      "khoa tam %d giay" % (entry["count"], ip,
                                            LOCKOUT_SECONDS), flush=True)
            else:
                print("[app-login] sai mat khau ip=%s lan=%d" % (
                    ip, entry["count"]), flush=True)
            return entry["count"]

    def record_successful_login(self, ip):
        """Dang nhap dung: reset bo dem cua IP do."""
        ip = self._norm_ip(ip)
        with self._lock:
            self._failed.pop(ip, None)

    def create_session(self, username):
        token = secrets.token_urlsafe(32)
        expires = self._now() + self.session_hours * 3600
        with self._lock:
            self._sessions[token] = (username, expires)
        return token, expires

    def validate_token(self, token):
        """Tra ve username neu token con han, khong thi None."""
        if not token:
            return None
        with self._lock:
            entry = self._sessions.get(token)
            if entry is None:
                return None
            username, expires = entry
            if self._now() > expires:
                del self._sessions[token]
                return None
            return username

    def revoke_token(self, token):
        if not token:
            return False
        with self._lock:
            return self._sessions.pop(token, None) is not None

    def session_count(self):
        with self._lock:
            return len(self._sessions)


def cookie_header(token, max_age_seconds):
    """Set-Cookie cho phien app: HttpOnly + SameSite=Lax; Secure chi
    khi chay sau HTTPS (ZALO_PC_APP_COOKIE_SECURE=1)."""
    parts = ["%s=%s" % (COOKIE_NAME, token),
             "HttpOnly", "Path=/", "SameSite=Lax",
             "Max-Age=%d" % int(max_age_seconds)]
    if os.environ.get("ZALO_PC_APP_COOKIE_SECURE") == "1":
        parts.append("Secure")
    return "; ".join(parts)


def clear_cookie_header():
    parts = ["%s=" % COOKIE_NAME, "HttpOnly", "Path=/", "SameSite=Lax",
             "Max-Age=0"]
    if os.environ.get("ZALO_PC_APP_COOKIE_SECURE") == "1":
        parts.append("Secure")
    return "; ".join(parts)


if __name__ == "__main__":
    # Tien ich tinh hash de dat vao ZALO_PC_APP_PASSWORD_HASH.
    # Mat khau doc qua getpass (khong luu vao shell history, khong in ra).
    pw = getpass.getpass("Mat khau app: ")
    pw2 = getpass.getpass("Nhap lai mat khau app: ")
    if pw != pw2:
        print("Hai lan nhap khong khop.")
        raise SystemExit(1)
    if not pw:
        print("Mat khau khong duoc de trong.")
        raise SystemExit(1)
    print("Dat bien moi truong nay luc deploy (chi hash, khong phai mat khau):")
    print("ZALO_PC_APP_PASSWORD_HASH=" + hash_password(pw))
