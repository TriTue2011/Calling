"""Client TDLib thật cho gateway (P1) — báo hiệu + gửi tin qua MTProto.

Luồng TDLib (đã đối chiếu td_api.tl qua T0-B):
  setTdlibParameters (THAM SỐ PHẲNG, không lồng ``parameters``; khóa mã hóa DB
  local từ file ``khoa`` đi trong ``database_encryption_key``, base64) ->
  authorizationStateWaitPhoneNumber -> setAuthenticationPhoneNumber ->
  checkAuthenticationCode -> (nếu server yêu cầu) checkAuthenticationPassword
  -> authorizationStateReady. QR là đường thay thế: requestQrCodeAuthentication
  -> update authorizationStateWaitQrCode (mang link) -> Ready khi quét xong.

Binding tdjson nhận BYTES, không nhận str: mọi request đều JSON-encode
sang bytes trước khi gửi (caveat T0-B). Transport được inject để test
dùng fake mà không cần tdjson thật: transport cần ``create_client_id``,
``send(client_id, data: bytes)``, ``receive(timeout) -> bytes | None``
và ``execute(data: bytes)``.

FLOOD_WAIT: lỗi TDLib dạng ``{"@type": "error", "code": 429, "message":
"FLOOD_WAIT_123"}`` — số giây lấy thẳng từ message, gateway không tự bịa
(``parse_flood_wait``). Lỗi khác mang code/message nguyên vẹn để route
bọc thành mã lỗi REST đúng (400/429/503...).

LƯU Ý CHƯA KIỂM CHỨNG LIVE (T1): code này viết theo td_api.tl +
chữ ký tdjson/ntgcalls đã kiểm ở T0/T0-B, chưa chạy với tài khoản thật.
Cuộc gọi thật tài khoản phụ ↔ tài khoản test (T1) mới chốt được hành vi
runtime (đặc biệt ``config``/``custom_parameters`` từ server thật).
"""

import base64
import json
import logging
import os
import re
import time
import uuid

logger = logging.getLogger("telegram_gateway")

_FLOOD_RE = re.compile(r"FLOOD_WAIT_(\d+)")


def parse_flood_wait(message: str) -> int | None:
    """Trả số giây FLOOD_WAIT từ message Telegram, None nếu không phải."""
    if not message:
        return None
    m = _FLOOD_RE.search(message)
    return int(m.group(1)) if m else None


class TelegramError(RuntimeError):
    """Lỗi trả về từ Telegram (qua TDLib), giữ nguyên code/message."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def flood_wait_seconds(self) -> int | None:
        return parse_flood_wait(self.message) if self.code == 429 else None


def tdjson_bytes(obj: dict) -> bytes:
    """JSON-encode một request TDLib sang bytes (binding chỉ nhận bytes)."""
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class _RealTdjsonTransport:
    """Transport thật quanh wheel tdjson 1.8.69 (lazy import)."""

    def create_client_id(self) -> int:
        import tdjson
        return tdjson.td_create_client_id()

    def send(self, client_id: int, data: bytes) -> None:
        import tdjson
        tdjson.td_send(client_id, data)

    def receive(self, timeout: float):
        import tdjson
        return tdjson.td_receive(timeout)

    def execute(self, data: bytes):
        import tdjson
        return tdjson.td_execute(data)


class TdlibClient:
    """Một client TDLib cho một tài khoản (đồng bộ, dùng td_receive).

    ``on_update`` nhận mọi update TDLib (updateCall,
    updateNewCallSignalingData, updateNewMessage...) để glue/event
    đăng ký. Các update đến trong lúc chờ response được đệm và phát
    lại qua ``on_update`` ngay khi nhận.
    """

    def __init__(self, session_dir: str, api_id: int, api_hash: str,
                 transport=None, on_update=None):
        self.session_dir = session_dir
        self.files_dir = os.path.join(session_dir, "files")
        self.key_path = os.path.join(session_dir, "khoa")
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self._transport = transport or _RealTdjsonTransport()
        self.on_update = on_update
        self.client_id: int | None = None
        self._buffered_updates: list[dict] = []
        self.qr_link: str = ""
        self._auth_state: str = ""

    # -- vòng đời ------------------------------------------------------
    def open(self) -> None:
        """Tạo client + setTdlibParameters (kèm khóa DB local)."""
        if self.client_id is not None:
            return
        os.makedirs(self.files_dir, exist_ok=True)
        try:
            os.chmod(self.files_dir, 0o700)
        except OSError:
            pass
        self.client_id = self._transport.create_client_id()
        try:        # TDLib mặc định ghi log rất dài ra stdout: chỉ giữ lỗi
            self._transport.execute(tdjson_bytes(
                {"@type": "setLogVerbosityLevel", "new_verbosity_level": 1}))
        except Exception:
            pass
        # TDLib >= 1.8.6: setTdlibParameters nhận trường PHẲNG; bọc trong "parameters" thì
        # api_id bị đọc là 0 -> "Valid api_id must be provided". Khóa DB là bytes -> base64.
        self.call({
            "@type": "setTdlibParameters",
            "use_test_dc": False,
            "database_directory": self.files_dir,
            "files_directory": self.files_dir,
            "database_encryption_key": base64.b64encode(self._read_key()).decode("ascii"),
            "use_file_database": True,
            "use_chat_info_database": True,
            "use_message_database": True,
            "use_secret_chats": False,
            "api_id": self.api_id,
            "api_hash": self.api_hash,
            "system_language_code": "en",
            "device_model": "telegram-gateway",
            "system_version": "Linux",
            "application_version": "0.1.0",
        })
        # Client ở WaitPhoneNumber / WaitCode / Ready tùy session cũ còn hạn hay không;
        # trạng thái đọc qua getAuthorizationState.
        self._auth_state = self.authorization_state()

    def _read_key(self) -> bytes:
        try:
            with open(self.key_path, encoding="utf-8") as fh:
                raw = fh.read().strip()
        except OSError:
            raw = ""
        if raw:
            try:
                return bytes.fromhex(raw)
            except ValueError:
                return raw.encode("utf-8")
        return b""

    def close(self) -> None:
        if self.client_id is None:
            return
        try:
            self.call({"@type": "close"})
        except Exception:
            pass
        self.client_id = None

    # -- request/response ----------------------------------------------
    def call(self, request: dict, timeout: float = 30) -> dict:
        """Gửi một request, chờ response cùng @extra; update được đệm."""
        if self.client_id is None:
            raise RuntimeError("Client TDLib chưa mở (gọi open() trước).")
        extra = uuid.uuid4().hex
        req = dict(request)
        req["@extra"] = extra
        self._transport.send(self.client_id, tdjson_bytes(req))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self._transport.receive(max(0.0, deadline - time.time()))
            if raw is None:
                continue
            try:
                obj = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if obj.get("@extra") == extra:
                if obj.get("@type") == "error":
                    raise TelegramError(int(obj.get("code", 400)),
                                        str(obj.get("message", "")))
                return obj
            self._dispatch_update(obj)
        raise TimeoutError(f"TDLib không trả lời request {request.get('@type')}")

    def _dispatch_update(self, obj: dict) -> None:
        self._buffered_updates.append(obj)
        if obj.get("@type") == "updateAuthorizationState":
            state = obj.get("authorization_state", {})
            self._auth_state = state.get("@type", "")
            if self._auth_state == "authorizationStateWaitQrCode":
                self.qr_link = state.get("link", "") or self.qr_link
        if self.on_update is not None:
            try:
                self.on_update(obj)
            except Exception:
                logger.exception("on_update lỗi (đã nuốt, không sập client)")

    def _wait_auth_state(self, wanted: set, timeout: float = 30) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for upd in list(self._buffered_updates):
                if upd.get("@type") == "updateAuthorizationState":
                    st = upd.get("authorization_state", {}).get("@type", "")
                    if st in wanted:
                        return st
            try:
                self.call({"@type": "getAuthorizationState"}, timeout=5)
            except Exception:
                pass
            if self._auth_state in wanted:
                return self._auth_state
            time.sleep(0.2)
        return self._auth_state

    def authorization_state(self) -> str:
        try:
            resp = self.call({"@type": "getAuthorizationState"}, timeout=10)
            state = resp.get("@type", "")
            if state.startswith("authorizationState"):
                return state
            # Một số binding trả state lồng trong trường authorization_state.
            inner = resp.get("authorization_state", {})
            return inner.get("@type", state)
        except Exception:
            return self._auth_state

    def is_authorized(self) -> bool:
        return self.authorization_state() == "authorizationStateReady"

    # -- đăng nhập --------------------------------------------------------
    def set_phone(self, phone: str) -> None:
        """Gửi số điện thoại -> server gửi mã OTP (raise TelegramError)."""
        self.call({"@type": "setAuthenticationPhoneNumber",
                   "phone_number": phone})

    def check_code(self, code: str) -> str:
        """Xác minh OTP. Trả 'ok' | 'password' (cần 2FA) | tên state khác."""
        self.call({"@type": "checkAuthenticationCode", "code": code})
        state = self.authorization_state()
        if state == "authorizationStateReady":
            return "ok"
        if state == "authorizationStateWaitPassword":
            return "password"
        return state

    def check_password(self, password: str) -> str:
        """Xác minh mật khẩu 2FA. Trả 'ok' hoặc tên state khác."""
        self.call({"@type": "checkAuthenticationPassword",
                   "password": password})
        state = self.authorization_state()
        return "ok" if state == "authorizationStateReady" else state

    def request_qr(self, timeout: float = 10) -> str:
        """Xin QR đăng nhập; trả link QR (rỗng nếu update chưa tới kịp)."""
        self.call({"@type": "requestQrCodeAuthentication",
                   "other_user_ids": []})
        deadline = time.time() + timeout
        while time.time() < deadline and not self.qr_link:
            try:
                self.call({"@type": "getAuthorizationState"}, timeout=2)
            except Exception:
                pass
            time.sleep(0.2)
        return self.qr_link

    def get_me(self) -> dict:
        return self.call({"@type": "getMe"})

    # -- chat / gửi tin ---------------------------------------------------
    def resolve_chat_id(self, peer: str) -> int:
        """peer: user_id số, hoặc username (@... hoặc tên trần)."""
        peer = peer.strip()
        if peer.lstrip("+").isdigit():
            # Số điện thoại thuần không phải user_id TDLib; thử coi là
            # user_id số trước (đường test), nếu sai server trả lỗi rõ.
            user_id = int(peer.lstrip("+"))
            resp = self.call({"@type": "createPrivateChat",
                              "user_id": user_id, "force": False})
            return int(resp["id"])
        username = peer[1:] if peer.startswith("@") else peer
        resp = self.call({"@type": "searchPublicChat",
                          "username": username})
        return int(resp["id"])

    def send_message(self, peer: str, text: str) -> int:
        chat_id = self.resolve_chat_id(peer)
        resp = self.call({
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageText",
                "text": {"@type": "formattedText", "text": text,
                         "entities": []},
                "link_preview_options": {"@type": "linkPreviewOptions",
                                         "is_disabled": True},
            },
        })
        return int(resp["id"])

    def send_media(self, peer: str, file_path: str, caption: str = "") -> int:
        """Gửi file làm document (P1: đường media thật; ảnh/video riêng
        theo mime là việc P4 tinh chỉnh, không đổi API này)."""
        chat_id = self.resolve_chat_id(peer)
        resp = self.call({
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageDocument",
                "document": {"@type": "inputFileLocal", "path": file_path},
                "caption": {"@type": "formattedText", "text": caption,
                            "entities": []},
            },
        })
        return int(resp["id"])

    def send_voice(self, peer: str, audio_path: str,
                   duration: int = 0) -> int:
        """Gửi voice note (file ogg/opus; duration 0 = để server tự tính)."""
        chat_id = self.resolve_chat_id(peer)
        resp = self.call({
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageVoiceNote",
                "voice_note": {"@type": "inputFileLocal",
                               "path": audio_path},
                "duration": int(duration),
                "waveform": "",
                "caption": {"@type": "formattedText", "text": "",
                            "entities": []},
            },
        })
        return int(resp["id"])

    # -- gọi (báo hiệu; media qua glue ở engine.py) ------------------------
    def create_call(self, user_id: int, protocol: dict) -> int:
        resp = self.call({"@type": "createCall", "user_id": int(user_id),
                          "protocol": protocol, "is_video": False})
        # createCall trả CallId (int32): response JSON là số trần, hoặc
        # dict bọc call_id tùy binding — chấp nhận cả hai.
        if isinstance(resp, dict):
            return int(resp.get("call_id", resp.get("id", 0)))
        return int(resp)

    def accept_call(self, call_id: int, protocol: dict) -> None:
        self.call({"@type": "acceptCall", "call_id": int(call_id),
                   "protocol": protocol})

    def discard_call(self, call_id: int, reason: str = "hangup") -> None:
        self.call({"@type": "discardCall", "call_id": int(call_id),
                   "is_disconnected": False, "duration": 0,
                   "is_video": False, "connection_id": 0})

    def send_signaling_data(self, call_id: int, data: bytes) -> None:
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("signaling data phải là bytes (binding tdjson).")
        # Trường bytes trong JSON TDLib là chuỗi base64 (bằng chứng T0-B:
        # probe gửi data="AAAA" được parse thành bytes [3] {00 00 00}).
        # Request tổng vẫn JSON-encode sang bytes ở tầng transport.
        import base64
        self.call({"@type": "sendCallSignalingData",
                   "call_id": int(call_id),
                   "data": base64.b64encode(bytes(data)).decode("ascii")})
