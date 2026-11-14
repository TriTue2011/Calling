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
