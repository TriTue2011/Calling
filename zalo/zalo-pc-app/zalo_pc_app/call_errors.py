"""Phân loại lỗi cuộc gọi đi theo KIỂU NGOẠI LỆ và mã lỗi có cấu trúc (không dò chữ trong thông báo).

Trước đây call_log chỉ nhận chuỗi tự do (str(exc)) nên WebUI hiện nguyên văn kỹ thuật. Mỗi lỗi giờ có một `error_kind` thuộc tập đóng KINDS;
chuỗi gốc vẫn được giữ ở `detail` để chẩn đoán. Cuộc gọi ĐẾN cũng dùng chung tên gọi (xem END_REASON ở WebUI).
"""
from __future__ import annotations

import socket

KINDS = ("already_answered", "server_rejected", "timeout", "network", "unknown")

# inner error_code của Zalo khi bước nghe máy (11303) tới sau khi điện thoại đã tự xác nhận / cuộc gọi đã được nghe ở nơi khác.
INNER_ALREADY_ANSWERED = -101


def inner_code(exc):
    """error_code số nguyên mà ServerRejectedError mang trong `.inner` (gói lỗi của Zalo); None nếu không có."""
    inner = getattr(exc, "inner", None)
    if isinstance(inner, dict):
        code = inner.get("error_code")
        if isinstance(code, int) and not isinstance(code, bool):
            return code
    return None


def classify(exc):
    """Trả về một giá trị trong KINDS. Thứ tự: máy chủ Zalo từ chối (kể cả mã đã-nghe-rồi) → hết giờ → lỗi mạng → không rõ."""
    from .signaling import ServerRejectedError          # nhập muộn: tránh vòng nhập khi test nạp module riêng
    if isinstance(exc, ServerRejectedError):
        return "already_answered" if inner_code(exc) == INNER_ALREADY_ANSWERED else "server_rejected"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(exc, OSError):                         # ConnectionError, URLError, ... đều là OSError
        return "network"
    return "unknown"
