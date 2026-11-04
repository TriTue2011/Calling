"""Đăng nhập qua web UI nội bộ — P1: TDLib thật, chỉ qua /ui/api/*.

Luồng (KHÔNG có endpoint đăng nhập nào dưới /api/* của HA):
  nhập số → tạo login_id → nhập mã OTP → (nếu server yêu cầu) 2FA →
  tạo session TDLib bền -> xác minh getMe -> status online.
  QR tùy chọn: tạo login_id QR -> quét -> xác nhận.

``client_factory`` là hàm ``(phone, session_dir) -> client`` (client thật
là ``TdlibClient``; test dùng fake cùng interface). Khi factory là None
(gateway chạy mock_mode, chưa cấu hình TDLib), giữ hành vi khung P0:
mã đúng định dạng 5-6 chữ số được chấp nhận để tạo session khung —
đường này chỉ tồn tại khi chưa bật engine thật, và route trả ``mock:
True`` để phân biệt rõ.

Chống flood: mã sai (sai định dạng HOẶC server từ chối) tính là 1 lần
thử; 3 lần sai → khóa login_id đó 15 phút; log chỉ đếm lần thử,
KHÔNG ghi mã/OTP/2FA (dùng logger đã redact + mask_peer cho số).
FLOOD_WAIT từ Telegram -> 429 FLOOD_WAIT kèm retry_after_seconds lấy
thẳng từ server, không tự bịa.
"""

import logging
import time
import uuid

from .errors import bad_request, flood_wait, login_locked
from .redact import mask_peer
from .store import AccountStore
from .tdclient import TelegramError

logger = logging.getLogger("telegram_gateway")

LOCK_AFTER_FAILURES = 3
LOCK_SECONDS = 15 * 60


class LoginManager:
    def __init__(self, store: AccountStore, clients: dict | None = None,
                 client_factory=None):
        self.store = store
        # phone -> client TDLib đã đăng nhập (dùng cho gửi/gọi thật)
        self.clients: dict = clients if clients is not None else {}
        self.client_factory = client_factory
        # login_id -> {phone, failures, locked_until, stage, client, qr_link}
        self._pending: dict[str, dict] = {}

    # -- helpers ---------------------------------------------------------
    def _fail(self, entry: dict, now: float):
        entry["failures"] += 1
        logger.info("login attempt failed count=%d (so dien thoai da che)",
                    entry["failures"])
        if entry["failures"] >= LOCK_AFTER_FAILURES:
            entry["locked_until"] = now + LOCK_SECONDS
            raise login_locked()
        raise bad_request("Mã không đúng.")

    def _get_pending(self, login_id: str) -> dict:
        entry = self._pending.get(login_id)
        if entry is None:
            raise bad_request("login_id không tồn tại hoặc đã hết hạn.")
        if time.time() < entry["locked_until"]:
            raise login_locked()
        return entry

    def _finish(self, login_id: str, entry: dict, display_name: str = ""):
        """Đăng ký tài khoản online + client, xóa pending."""
        phone = entry["phone"]
        acc = self.store.create_session(phone, display_name,
                                        status="online")
        client = entry.get("client")
        if client is not None:
            self.clients[phone] = client
        del self._pending[login_id]
        logger.info("login ok account=%s", mask_peer(phone))
        return acc

    # -- bắt đầu -----------------------------------------------------------
    def start(self, phone: str) -> str:
        if not phone or len(phone.strip()) < 6:
            raise bad_request("Số điện thoại không hợp lệ.")
        phone = phone.strip()
        login_id = uuid.uuid4().hex
        entry = {"phone": phone, "failures": 0, "locked_until": 0.0,
                 "stage": "code", "client": None, "qr_link": ""}
        self._pending[login_id] = entry
        if self.client_factory is None:
            return login_id  # khung mock: mã kiểm ở submit_code
        sdir = self.store.ensure_session_dir(phone)
        client = self.client_factory(phone, sdir)
        entry["client"] = client
        try:
            client.open()
            client.set_phone(phone)
        except TelegramError as exc:
            if exc.flood_wait_seconds is not None:
                del self._pending[login_id]
                raise flood_wait(exc.flood_wait_seconds)
            del self._pending[login_id]
            raise bad_request(f"Telegram từ chối số điện thoại: "
                              f"{exc.message or exc.code}")
        return login_id

    def start_qr(self, phone: str) -> tuple[str, str]:
        """Bắt đầu đăng nhập bằng QR. Trả (login_id, qr_link).

        Không có factory (mock) -> raise 400: QR chỉ có ở đường thật.
        """
        if self.client_factory is None:
            raise bad_request("Đăng nhập QR cần engine TDLib thật.")
        if not phone or len(phone.strip()) < 6:
            raise bad_request("Số điện thoại không hợp lệ.")
        phone = phone.strip()
        login_id = uuid.uuid4().hex
        entry = {"phone": phone, "failures": 0, "locked_until": 0.0,
                 "stage": "qr", "client": None, "qr_link": ""}
        self._pending[login_id] = entry
        sdir = self.store.ensure_session_dir(phone)
        client = self.client_factory(phone, sdir)
        entry["client"] = client
        try:
            client.open()
            link = client.request_qr()
        except TelegramError as exc:
            if exc.flood_wait_seconds is not None:
                del self._pending[login_id]
                raise flood_wait(exc.flood_wait_seconds)
            del self._pending[login_id]
            raise bad_request(f"Telegram từ chối yêu cầu QR: "
                              f"{exc.message or exc.code}")
        entry["qr_link"] = link
        return login_id, link

    def status(self, login_id: str) -> dict:
        entry = self._get_pending(login_id)
        return {"login_id": login_id, "stage": entry["stage"],
                "phone": mask_peer(entry["phone"]),
                "qr_link": entry["qr_link"] if entry["stage"] == "qr" else ""}

    # -- xác minh -----------------------------------------------------------
    def submit_code(self, login_id: str, code: str):
        """Trả Account khi xong, hoặc dict {'needs_password': True}.

        Đường mock (không factory): giữ đúng hành vi P0 — mã đúng định
        dạng 5-6 chữ số -> session khung (route trả mock=True).
        """
        entry = self._get_pending(login_id)
        now = time.time()
        if self.client_factory is None:
            if not code or not code.isdigit() or not (5 <= len(code) <= 6):
                self._fail(entry, now)
            phone = entry["phone"]
            acc = self.store.create_session(phone)
            del self._pending[login_id]
            return acc
        # Đường thật: sai định dạng vẫn tính 1 lần thử (đỡ đốt OTP).
        if not code or not code.isdigit() or not (5 <= len(code) <= 6):
            self._fail(entry, now)
        client = entry["client"]
        try:
            result = client.check_code(code)
        except TelegramError as exc:
            if exc.flood_wait_seconds is not None:
                raise flood_wait(exc.flood_wait_seconds)
            self._fail(entry, now)
        if result == "password":
            entry["stage"] = "password"
            return {"needs_password": True, "stage": "password"}
        if result == "ok":
            name = ""
            try:
                me = client.get_me()
                name = (me.get("first_name", "") + " " +
                        me.get("last_name", "")).strip()
            except Exception:
                name = ""
            return self._finish(login_id, entry, name)
        raise bad_request(f"Trạng thái đăng nhập chưa xong: {result}")

    def submit_password(self, login_id: str, password: str):
        """Xác minh 2FA. Trả Account khi xong."""
        entry = self._get_pending(login_id)
        if entry["stage"] != "password":
            raise bad_request("Phiên này không ở bước mật khẩu 2FA.")
        if self.client_factory is None:
            raise bad_request("Đường 2FA cần engine TDLib thật.")
        now = time.time()
        if not password:
            self._fail(entry, now)
        client = entry["client"]
        try:
            result = client.check_password(password)
        except TelegramError as exc:
            if exc.flood_wait_seconds is not None:
                raise flood_wait(exc.flood_wait_seconds)
            self._fail(entry, now)
        if result == "ok":
            name = ""
            try:
                me = client.get_me()
                name = (me.get("first_name", "") + " " +
                        me.get("last_name", "")).strip()
            except Exception:
                name = ""
            return self._finish(login_id, entry, name)
        raise bad_request(f"Trạng thái đăng nhập chưa xong: {result}")

    def confirm_qr(self, login_id: str):
        """Kiểm tra QR đã quét xong chưa; xong -> Account."""
        entry = self._get_pending(login_id)
        if entry["stage"] != "qr":
            raise bad_request("Phiên này không ở bước QR.")
        client = entry["client"]
        if client is None or not client.is_authorized():
            raise bad_request("QR chưa được quét hoặc chưa xác nhận.")
        name = ""
        try:
            me = client.get_me()
            name = (me.get("first_name", "") + " " +
                    me.get("last_name", "")).strip()
        except Exception:
            name = ""
        return self._finish(login_id, entry, name)

    def pending_count(self) -> int:
        return len(self._pending)
