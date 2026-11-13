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
SESSIONS_FILENAME = "app_sessions.json"   # phien WebUI con song qua khoi dong lai (chi luu BAM SHA-256 cua token, 0600)


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


def _load_verifier_record(data_dir):
    """{"password_hash", "source", "env_hash"} hoac None. source: "env" (tu bien
    moi truong) | "ui" (doi qua WebUI); env_hash = PBKDF2 cua mat khau trong env tai
    thoi diem do (de biet env co bi doi ve sau khong)."""
    try:
        with open(_verifier_path(data_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    stored = data.get("password_hash", "") if isinstance(data, dict) else ""
    if not (isinstance(stored, str) and stored.startswith("$pbkdf2-sha256$")):
        return None
    env_hash = data.get("env_hash")
    return {"password_hash": stored,
            "source": "ui" if data.get("source") == "ui" else "env",
            "env_hash": env_hash if isinstance(env_hash, str)
            and env_hash.startswith("$pbkdf2-sha256$") else ""}


def _load_verifier_file(data_dir):
    rec = _load_verifier_record(data_dir)
    return rec["password_hash"] if rec else None


def _save_verifier_file(data_dir, stored, source="env", env_hash=""):
    os.makedirs(data_dir, exist_ok=True)
    tmp = _verifier_path(data_dir) + ".tmp"
    rec = {"password_hash": stored, "source": source}
    if env_hash:
        rec["env_hash"] = env_hash
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rec, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, _verifier_path(data_dir))
    try:
        os.chmod(_verifier_path(data_dir), 0o600)
    except OSError:
        pass


MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 256


def _token_key(token):
    """Khoa luu phien: SHA-256 cua token. Token goc chi nam trong cookie cua trinh duyet, khong bao gio ghi ra dia."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _atomic_write_private(path, text):
    """Ghi tep quyen 0600 theo kieu ghi-tam-roi-doi-ten, de khong bao gio de lai tep ghi do."""
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


class PasswordChangeError(Exception):
    """Doi mat khau that bai; `code` la ma loi cho API."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class AppAuth:
    """Mot tai khoan app + cac phien dang nhap (token, trong bo nho)."""

    def __init__(self, username, password_hash, session_hours=None,
                 data_dir=None, env_hash="", managed_by_env_hash=False):
        self.username = username
        self.password_hash = password_hash
        self._data_dir = data_dir
        self._env_hash = env_hash                 # PBKDF2 cua mat khau trong env (neu co)
        # ZALO_PC_APP_PASSWORD_HASH la nguon duy nhat: khong cho doi qua WebUI.
        self.managed_by_env_hash = managed_by_env_hash
        self.session_hours = (DEFAULT_SESSION_HOURS if session_hours is None
                              else session_hours)
        self._sessions = {}  # sha256(token) -> (username, expires_at)
        import threading
        self._lock = threading.Lock()
        self._load_sessions()

    # -- phien ben (qua khoi dong lai) --------------------------------------
    def _fingerprint(self):
        """Dau van tay mat khau hien tai: doi mat khau thi moi phien da luu mat hieu luc."""
        return hashlib.sha256(self.password_hash.encode("utf-8")).hexdigest()[:16]

    def _sessions_path(self):
        return os.path.join(self._data_dir, SESSIONS_FILENAME) if self._data_dir else ""

    def _load_sessions(self):
        path = self._sessions_path()
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or data.get("fp") != self._fingerprint():
                return                                   # mat khau da doi (hoac tep la): bo het
            now = time.time()
            for key, val in (data.get("sessions") or {}).items():
                if isinstance(key, str) and isinstance(val, list) and len(val) == 2 \
                        and isinstance(val[0], str) and isinstance(val[1], (int, float)) and val[1] > now:
                    self._sessions[key] = (val[0], float(val[1]))
        except (OSError, ValueError):
            self._sessions.clear()                       # tep hong: nhu chua co phien, khong lam server chet

    def _save_sessions(self):
        """Goi KHI DANG GIU self._lock. Loi ghi tep khong lam hong dang nhap (phien van song trong bo nho)."""
        path = self._sessions_path()
        if not path:
            return
        try:
            _atomic_write_private(path, json.dumps(
                {"fp": self._fingerprint(), "sessions": {k: [u, e] for k, (u, e) in self._sessions.items()}}))
        except OSError:
            pass

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
            stored, env_hash = password_hash, ""
        elif password:
            rec = _load_verifier_record(data_dir)
            if rec and rec["source"] == "ui" and rec["env_hash"] \
                    and verify_password(password, rec["env_hash"]):
                # Da doi qua WebUI va bien moi truong KHONG doi tu do: giu mat
                # khau moi (khong ghi de bang mat khau cu trong env).
                stored, env_hash = rec["password_hash"], rec["env_hash"]
            elif rec and verify_password(password, rec["password_hash"]):
                stored = rec["password_hash"]    # mat khau khong doi: giu salt/hash cu
                env_hash = rec["env_hash"] or hash_password(password)
                if rec["source"] != "env" or not rec["env_hash"]:
                    _save_verifier_file(data_dir, stored, "env", env_hash)
            else:
                # Lan dau, hoac env doi sang mat khau khac: salt moi, ghi de file.
                stored = hash_password(password)
                env_hash = stored
                _save_verifier_file(data_dir, stored, "env", env_hash)
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
        return cls(username, stored, session_hours=hours, data_dir=data_dir,
                   env_hash=env_hash, managed_by_env_hash=bool(password_hash))

    # -- doi mat khau -----------------------------------------------------
    def change_password(self, old_password, new_password, keep_token=None):
        """Doi mat khau (WebUI): kiem mat khau cu, luu hash moi (0600), thu hoi
        MOI phien khac (giu keep_token). Nem PasswordChangeError(code):
        managed_by_env | sai_mat_khau_cu | mat_khau_qua_ngan | mat_khau_qua_dai |
        mat_khau_trung."""
        if self.managed_by_env_hash:
            raise PasswordChangeError("managed_by_env")
        if not isinstance(old_password, str) \
                or not verify_password(old_password, self.password_hash):
            raise PasswordChangeError("sai_mat_khau_cu")
        if not isinstance(new_password, str) or len(new_password) < MIN_PASSWORD_LEN:
            raise PasswordChangeError("mat_khau_qua_ngan")
        if len(new_password) > MAX_PASSWORD_LEN:
            raise PasswordChangeError("mat_khau_qua_dai")
        if new_password == old_password:
            raise PasswordChangeError("mat_khau_trung")
        new_hash = hash_password(new_password)
        with self._lock:
            if self._data_dir:
                _save_verifier_file(self._data_dir, new_hash, "ui", self._env_hash)
            self.password_hash = new_hash
        return self.revoke_all(keep_token=keep_token)

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
            self._sessions[_token_key(token)] = (username, expires)
            self._save_sessions()
        return token, expires

    def validate_token(self, token):
        """Tra ve username neu token con han, khong thi None."""
        if not token:
            return None
        key = _token_key(token)
        with self._lock:
            entry = self._sessions.get(key)
            if entry is None:
                return None
            username, expires = entry
            if time.time() > expires:
                del self._sessions[key]
                self._save_sessions()
                return None
            return username

    def revoke_token(self, token):
        if not token:
            return False
        with self._lock:
            removed = self._sessions.pop(_token_key(token), None) is not None
            if removed:
                self._save_sessions()
            return removed

    def session_count(self):
        with self._lock:
            return len(self._sessions)

    def revoke_all(self, keep_token=None):
        """Thu hoi moi phien (tru keep_token neu co). Tra so phien da xoa."""
        keep = _token_key(keep_token) if keep_token else None
        with self._lock:
            drop = [t for t in self._sessions if t != keep]
            for t in drop:
                del self._sessions[t]
            self._save_sessions()
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
