"""Mã PIN riêng tư cho WebUI (học từ ZaloCRM «Privacy PIN»): đã đăng nhập app vẫn phải nhập PIN mới đọc được tin nhắn.

Bật bằng biến môi trường lúc deploy (KHÔNG có PIN mặc định; thiếu cả hai biến = tính năng TẮT, hành vi cũ):
  ZALO_PC_APP_PIN_HASH   hash $pbkdf2-sha256$... (tính bằng: python3 -m zalo_pc_app.privacy)
  ZALO_PC_APP_PIN        PIN dạng chữ (4-32 ký tự), băm trong bộ nhớ lúc khởi động
  ZALO_PC_APP_PIN_MINUTES  tự khoá lại sau ngần này phút KHÔNG dùng (mặc định 10)

Cách chặn: MẶC ĐỊNH CHẶN. Phiên chưa mở khoá chỉ gọi được danh sách cho phép (ALLOWED_PREFIXES: trạng thái, danh sách cuộc gọi, đăng nhập/đăng xuất app,
các đường PIN, trang chính và /ui/); mọi đường còn lại (lịch sử, cập nhật, danh sách hội thoại, SSE, tải tệp, cổng /api/svc, ...) trả 423 «privacy_locked». Chặn ở MỘT chỗ
(server._require_app_login) nên không có đường nào bị sót vì quên che. Trạng thái mở khoá chỉ nằm trong bộ nhớ: khởi động lại là khoá lại.
"""
from __future__ import annotations

import getpass
import time

from . import app_auth

MIN_PIN_LEN = 4
MAX_PIN_LEN = 32
DEFAULT_MINUTES = 10.0
# Đường vẫn dùng được khi đang khoá (không trả nội dung tin nhắn): trang chính và tài nguyên giao diện (để hiện ô nhập PIN), trạng thái, danh sách
# cuộc gọi, đăng nhập/đăng xuất app, các đường PIN. /api/logout (đăng xuất Zalo) KHÔNG nằm đây: phải mở khoá mới được.
ALLOWED_EXACT = ("/", "/login")
ALLOWED_PREFIXES = ("/api/status", "/api/calls", "/api/app/", "/api/privacy/", "/ui/")


class PrivacyGate:
    def __init__(self, pin_hash="", minutes=DEFAULT_MINUTES, clock=time.time, limiter=None):
        self._hash = pin_hash or ""
        self._ttl = max(1.0, float(minutes)) * 60.0
        self._clock = clock
        self._unlocked = {}                 # sha256(token) -> hết hạn (giây)
        self.limiter = limiter or app_auth.LoginLimiter(max_fails=5, window=900)

    @classmethod
    def from_env(cls, env=None):
        import os
        env = os.environ if env is None else env
        try:
            minutes = float(env.get("ZALO_PC_APP_PIN_MINUTES") or DEFAULT_MINUTES)
            if minutes <= 0:
                raise ValueError
        except ValueError:
            minutes = DEFAULT_MINUTES
        pin_hash = (env.get("ZALO_PC_APP_PIN_HASH") or "").strip()
        if pin_hash:
            if not pin_hash.startswith("$pbkdf2-sha256$"):
                raise ValueError("ZALO_PC_APP_PIN_HASH sai dinh dang (can $pbkdf2-sha256$...): tinh bang python3 -m zalo_pc_app.privacy")
            return cls(pin_hash, minutes)
        pin = env.get("ZALO_PC_APP_PIN") or ""
        if pin:
            if not (MIN_PIN_LEN <= len(pin) <= MAX_PIN_LEN):
                raise ValueError("ZALO_PC_APP_PIN phai dai %d-%d ky tu" % (MIN_PIN_LEN, MAX_PIN_LEN))
            return cls(app_auth.hash_password(pin), minutes)
        return cls("", minutes)

    @property
    def enabled(self):
        return bool(self._hash)

    @staticmethod
    def allowed(path):
        if ".." in path or "//" in path:                 # không để đường dẫn «lách» qua tiền tố được phép
            return False
        return path in ALLOWED_EXACT or path.startswith(ALLOWED_PREFIXES)

    def _key(self, token):
        return app_auth._token_key(token) if token else ""

    def is_unlocked(self, token):
        """True nếu đã mở khoá và chưa hết hạn; mỗi lần dùng được gia hạn (khoá theo thời gian KHÔNG dùng)."""
        key = self._key(token)
        if not key:
            return False
        now = self._clock()
        exp = self._unlocked.get(key)
        if exp is None or now > exp:
            self._unlocked.pop(key, None)
            return False
        self._unlocked[key] = now + self._ttl
        return True

    def unlock(self, token, pin, ip=""):
        """Trả (ok, lý do): lý do là "" | "sai_pin" | "qua_nhieu_lan_sai" | "chua_bat". Sai quá 5 lần/15 phút từ một địa chỉ thì khoá địa chỉ đó."""
        if not self.enabled:
            return False, "chua_bat"
        key = self._key(token)
        if not key:
            return False, "sai_pin"
        if self.limiter.blocked(ip):
            return False, "qua_nhieu_lan_sai"
        if isinstance(pin, str) and app_auth.verify_password(pin, self._hash):
            self.limiter.reset(ip)
            self._unlocked[key] = self._clock() + self._ttl
            return True, ""
        self.limiter.fail(ip)
        return False, "sai_pin"

    def lock(self, token):
        return self._unlocked.pop(self._key(token), None) is not None

    def status(self, token):
        """Cho WebUI: {enabled, unlocked, seconds_left}. KHÔNG gia hạn hạn dùng."""
        if not self.enabled:
            return {"enabled": False, "unlocked": True, "seconds_left": 0}
        exp = self._unlocked.get(self._key(token))
        left = int(exp - self._clock()) if exp else 0
        return {"enabled": True, "unlocked": left > 0, "seconds_left": max(0, left)}


class PrivacyLocked(Exception):
    """Ném từ server._require_app_login khi PIN đang bật mà phiên chưa mở khoá; Handler đổi thành HTTP 423."""


if __name__ == "__main__":
    pin = getpass.getpass("PIN rieng tu: ")
    if pin != getpass.getpass("Nhap lai PIN: "):
        raise SystemExit("Hai lan nhap khong khop.")
    if not (MIN_PIN_LEN <= len(pin) <= MAX_PIN_LEN):
        raise SystemExit("PIN phai dai %d-%d ky tu." % (MIN_PIN_LEN, MAX_PIN_LEN))
    print("Dat bien moi truong nay luc deploy (chi hash, khong phai PIN):")
    print("ZALO_PC_APP_PIN_HASH=" + app_auth.hash_password(pin))
