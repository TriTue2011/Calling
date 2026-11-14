"""Đọc/ghi MỌI cài đặt của app Zalo Call từ Home Assistant (thuần Python, không phụ thuộc HA để kiểm thử riêng).

Mục đích: sau này có thể chạy app KHÔNG có WebUI (máy cấu hình yếu) mà vẫn cấu hình được toàn bộ từ HA. App giữ mọi cài đặt sau cổng đăng nhập
của nó; module này chỉ gom/che bí mật/kiểm tra mục hợp lệ. Mật khẩu app là BĂM trong app nên KHÔNG đọc ngược được: HA chỉ biết mật khẩu nó đang dùng để đăng nhập."""
from __future__ import annotations

import re
from typing import Any

# mục cài đặt đọc/ghi được qua dịch vụ (mỗi mục ứng với một route của app)
READ_SECTIONS = ("app", "webhooks", "devices", "retention", "proxy", "security", "history_sync")
WRITE_SECTIONS = ("webhooks", "devices", "retention", "proxy", "security")
MASK = "***"
_SECRET_QUERY = re.compile(r"([?&](?:k|key|token|secret|password)=)[^&\s\"']+", re.I)
_CREDS = re.compile(r"(://[^/\s:@]+:)[^@/\s]*@")
_WEBHOOK_ID = re.compile(r"(/api/webhook/)[^/?#\s]+")


def mask_url(url: Any) -> str:
    """Che bí mật trong địa chỉ: mật khẩu dạng user:pw@host, tham số ?k=/token=…, và mã webhook của HA (/api/webhook/<mã>)."""
    s = str(url or "")
    s = _CREDS.sub(r"\1" + MASK + "@", s)
    s = _SECRET_QUERY.sub(r"\1" + MASK, s)
    return _WEBHOOK_ID.sub(r"\1" + MASK, s)


def mask_webhooks(cfg: Any, reveal: bool = False) -> dict[str, Any]:
    """Cấu hình webhook của app: địa chỉ (có mã bí mật) bị che trừ khi reveal=True. Các cờ bật/tắt giữ nguyên."""
    if not isinstance(cfg, dict):
        return {}
    return {k: (v if reveal or not k.endswith("_url") else mask_url(v)) for k, v in cfg.items()}


def mask_connection(url: str, username: str, password: str, reveal: bool = False) -> dict[str, Any]:
    """Thông tin HA đang dùng để nói chuyện với app. Mật khẩu chỉ hiện khi reveal=True (mật khẩu app là băm nên không có cách nào khác để biết)."""
    return {"url": mask_url(url), "username": username, "password": password if reveal else (MASK if password else ""), "password_revealed": bool(reveal)}


def build_snapshot(raw: dict[str, Any], connection: dict[str, Any], reveal: bool = False) -> dict[str, Any]:
    """Gộp các mục đã đọc từ app thành một dict. Mục nào app không trả lời thì ghi {"error": ...} thay vì làm hỏng cả bản đọc."""
    out: dict[str, Any] = {"connection": connection}
    for section, data in raw.items():
        if isinstance(data, Exception):
            out[section] = {"error": str(data)[:200]}
        elif section == "webhooks":
            out[section] = mask_webhooks(data, reveal)
        elif section == "proxy" and not reveal:
            out[section] = _mask_proxy(data)
        else:
            out[section] = data
    return out


def _mask_proxy(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: (mask_url(v) if k in ("url", "active_url") else _mask_proxy(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask_proxy(x) for x in data]
    return data


def normalize_sections(value: Any) -> list[str]:
    """Danh sách mục cần đọc: trống = tất cả; mục lạ → ValueError (nêu rõ mục hợp lệ)."""
    if value in (None, "", []):
        return list(READ_SECTIONS)
    items = [value] if isinstance(value, str) else list(value)
    bad = [x for x in items if x not in READ_SECTIONS]
    if bad:
        raise ValueError("Mục không hợp lệ: %s. Chỉ gồm: %s" % (", ".join(map(str, bad)), ", ".join(READ_SECTIONS)))
    return list(dict.fromkeys(items))


def check_write(section: Any, values: Any) -> tuple[str, dict[str, Any]]:
    """Kiểm tra yêu cầu ghi: mục hợp lệ và `values` là dict không rỗng. (App tự kiểm giá trị từng khóa và trả lỗi rõ ràng.)"""
    if section not in WRITE_SECTIONS:
        raise ValueError("Mục ghi chỉ gồm: %s" % ", ".join(WRITE_SECTIONS))
    if not isinstance(values, dict) or not values:
        raise ValueError("«values» phải là một đối tượng (dict) không rỗng")
    return str(section), dict(values)


def check_password_change(old: Any, new: Any) -> tuple[str, str]:
    """Đổi mật khẩu app: cả hai là chuỗi không rỗng và mới khác cũ. (Độ dài/độ mạnh do app quyết định và báo lỗi.)"""
    o, n = str(old or ""), str(new or "")
    if not o or not n:
        raise ValueError("Cần cả mật khẩu cũ và mật khẩu mới")
    if o == n:
        raise ValueError("Mật khẩu mới phải khác mật khẩu cũ")
    return o, n


PASSWORD_ERRORS = {
    "sai_mat_khau_cu": "Mật khẩu cũ không đúng",
    "managed_by_env": "Mật khẩu app đang được đặt bằng biến môi trường (ZALO_PC_APP_PASSWORD_HASH) nên không đổi được từ đây — hãy đổi biến đó rồi khởi động lại app",
    "qua_nhieu_lan_sai": "Nhập sai quá nhiều lần, app khóa tạm — thử lại sau 15 phút",
    "app_chua_cau_hinh": "App chưa cấu hình tài khoản đăng nhập",
}


def password_error_text(error: Any) -> str:
    """Lời báo tiếng Việt cho mã lỗi đổi mật khẩu của app; mã lạ thì giữ nguyên mã để còn tra cứu."""
    code = str(error or "")
    return PASSWORD_ERRORS.get(code, "Không đổi được mật khẩu app: %s" % (code or "lỗi không rõ"))
