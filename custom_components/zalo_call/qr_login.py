"""Đăng nhập Zalo bằng mã QR từ Home Assistant (thuần Python, không phụ thuộc HA để kiểm thử riêng).

App Zalo Call có hai kiểu đăng nhập: «web» (Qua Web) và «pc» (Zalo PC). Mỗi kiểu có QR riêng. Tích hợp chỉ điều khiển app qua
POST /api/qr/new {client}, GET /api/qr/status và POST /api/zalo/logout; ảnh QR do app trả dạng data:image/png;base64."""
from __future__ import annotations

import base64
import binascii
from typing import Any

CLIENTS = ("web", "pc")
CLIENT_LABEL = {"web": "Web (Qua Web)", "pc": "PC (Zalo PC)"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DATA_URL_PREFIX = "data:image/png;base64,"
STATE_TEXT = {
    "idle": "Chưa đăng nhập — bấm «Đăng nhập bằng QR»",
    "waiting": "Đang chờ quét mã QR bằng ứng dụng Zalo trên điện thoại",
    "scanned": "Đã quét — hãy bấm xác nhận trên điện thoại",
    "done": "Đã đăng nhập",
    "expired": "Mã QR đã hết hạn — bấm «Đăng nhập bằng QR» để lấy mã mới",
    "rate_limited": "Zalo giới hạn số lần lấy mã — chờ một lúc rồi thử lại",
    "rejected": "Điện thoại đã từ chối đăng nhập",
    "error": "Lỗi khi đăng nhập",
}


def normalize_client(value: Any) -> str | None:
    """"web" | "pc" (không phân biệt hoa thường, bỏ khoảng trắng); trống → None (giữ kiểu hiện tại của app); giá trị lạ → ValueError."""
    if value is None or str(value).strip() == "":
        return None
    v = str(value).strip().lower()
    if v not in CLIENTS:
        raise ValueError("Kiểu đăng nhập chỉ gồm: %s" % ", ".join(CLIENTS))
    return v


def png_from_data_url(url: Any) -> bytes | None:
    """Giải mã ảnh QR (data:image/png;base64,…) thành byte PNG; None nếu không có hoặc không phải PNG hợp lệ."""
    if not isinstance(url, str) or not url.startswith(DATA_URL_PREFIX):
        return None
    try:
        raw = base64.b64decode(url[len(DATA_URL_PREFIX):], validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw if raw.startswith(PNG_SIGNATURE) else None


def attributes(status: dict[str, Any] | None) -> dict[str, Any]:
    """Thuộc tính hiển thị của thực thể QR (tiếng Việt, không chứa ảnh/khóa)."""
    st = status if isinstance(status, dict) else {}
    state = str(st.get("state") or "idle")
    out: dict[str, Any] = {"trang_thai": state, "mo_ta": STATE_TEXT.get(state, state)}
    client = st.get("client")
    if client in CLIENTS:
        out["kieu_dang_nhap"] = client
        out["kieu_dang_nhap_ten"] = CLIENT_LABEL[client]
    if st.get("countdown"):
        out["het_han_sau_giay"] = st["countdown"]
    if st.get("uid"):
        out["uid"] = str(st["uid"])
    if st.get("error"):
        out["loi"] = str(st["error"])[:200]
    if st.get("warning"):
        out["canh_bao"] = str(st["warning"])[:200]
    return out


# ---- trạng thái Zalo tổng hợp (đã đăng nhập / chưa / đang chờ quét…) và nút nào còn hợp lệ ----
LOGIN_STATES = ("logged_in", "logged_out", "waiting_qr", "scanned", "expired", "error")
LOGIN_STATE_TEXT = {"logged_in": "Đã đăng nhập", "logged_out": "Chưa đăng nhập", "waiting_qr": "Đang chờ quét mã QR", "scanned": "Đã quét, chờ xác nhận trên điện thoại",
                    "expired": "Mã QR hết hạn", "error": "Đăng nhập lỗi"}
_QR_TO_STATE = {"waiting": "waiting_qr", "scanned": "scanned", "expired": "expired", "rate_limited": "error", "rejected": "error", "error": "error"}


def logged_in(coordinator_data: Any) -> bool | None:
    """Đã đăng nhập Zalo? True/False theo /api/status; None = chưa biết (chưa có dữ liệu, app không trả lời) — khi đó KHÔNG làm mờ thực thể nào."""
    st = (coordinator_data or {}).get("status") if isinstance(coordinator_data, dict) else None
    if not isinstance(st, dict) or "login" not in st:
        return None
    return bool(st.get("login"))


def login_state(is_logged_in: bool | None, qr: dict[str, Any] | None = None) -> str | None:
    """Mã trạng thái tổng hợp (LOGIN_STATES) hoặc None khi chưa biết. Đã đăng nhập thì luôn «logged_in»; chưa thì theo trạng thái QR (không có QR = logged_out)."""
    if is_logged_in is None:
        return None
    if is_logged_in:
        return "logged_in"
    state = str((qr or {}).get("state") or "")
    if state == "done":                       # QR «xong» còn sót từ lần đăng nhập trước, mà phiên đã mất: chưa đăng nhập
        return "logged_out"
    return _QR_TO_STATE.get(state, "logged_out")


def login_actions(is_logged_in: bool | None) -> dict[str, bool]:
    """Nút nào còn hợp lệ: đã đăng nhập thì chỉ «Đăng xuất» (đăng nhập QR và ảnh QR mờ đi); chưa đăng nhập thì chỉ đăng nhập QR (đăng xuất mờ đi);
    chưa biết thì cả hai cùng sáng để không chặn người dùng."""
    if is_logged_in is None:
        return {"login": True, "logout": True}
    return {"login": not is_logged_in, "logout": bool(is_logged_in)}
