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

    def __init__(self, username, password_hash, session_hours=None):
        self.username = username
        self.password_hash = password_hash
        self.session_hours = (DEFAULT_SESSION_HOURS if session_hours is None
                              else session_hours)
        self._sessions = {}  # token -> (username, expires_at)
        import threading
        self._lock = threading.Lock()

    # -- khoi tao tu env -------------------------------------------------
    @classmethod
    def from_env(cls, data_dir, env=None):
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
        return cls(username, stored, session_hours=hours)

    # -- dang nhap --------------------------------------------------------
    def verify(self, username, password):
        """Dung/sai chung mot ket qua False — khong lo user co ton tai
        hay khong. So sanh constant-time ca user lan hash."""
        if not isinstance(username, str) or not isinstance(password, str):
            return False
        user_ok = hmac.compare_digest(username, self.username)
        pass_ok = verify_password(password, self.password_hash)
        return user_ok and pass_ok

    def create_session(self, username):
        token = secrets.token_urlsafe(32)
        expires = time.time() + self.session_hours * 3600
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
            if time.time() > expires:
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

    def revoke_all(self, keep_token=None):
        """Thu hoi moi phien (tru keep_token neu co). Tra so phien da xoa."""
        with self._lock:
            drop = [t for t in self._sessions if t != keep_token]
            for t in drop:
                del self._sessions[t]
            return len(drop)


class LoginLimiter:
    """Chan do mat khau: sai qua `max_fails` lan trong `window` giay tu
    cung mot dia chi thi khoa dia chi do den het cua so. Trong bo nho."""

    def __init__(self, max_fails=5, window=900):
        self.max_fails = max_fails
        self.window = window
        self._fails = {}
        import threading
        self._lock = threading.Lock()

    def _prune(self, ip, now):
        self._fails[ip] = [t for t in self._fails.get(ip, []) if now - t < self.window]

    def blocked(self, ip, now=None):
        now = time.time() if now is None else now
        with self._lock:
            self._prune(ip, now)
            return len(self._fails[ip]) >= self.max_fails

    def fail(self, ip, now=None):
        now = time.time() if now is None else now
        with self._lock:
            self._prune(ip, now)
            self._fails[ip].append(now)

    def reset(self, ip):
        with self._lock:
            self._fails.pop(ip, None)

    def blocked_count(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            for ip in list(self._fails):
                self._prune(ip, now)
            return sum(1 for v in self._fails.values() if len(v) >= self.max_fails)


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
