"""Chính sách TRẢ LỜI tin nhắn nhóm bằng AI (giống tính năng của zalo_bot: tài khoản phụ nhắn vào nhóm thì nhận được câu trả lời).

Không phụ thuộc Home Assistant nên test được riêng. Các trường nằm trong quy tắc (set_rule):
  reply_trigger  Từ khóa gọi trong NHÓM, ví dụ "@Bot" (không phân biệt hoa thường). Để trống = trả lời mọi tin của nhóm (hành vi cũ).
  reply_senders  Chỉ những người này mới được gọi trong NHÓM: mã Zalo cách nhau dấu phẩy/dấu cách/xuống dòng. Để trống = mọi thành viên.
                 So khớp cả mã dài 19 chữ số (sender_id) lẫn mã số ngắn (uid_from), nên dán loại nào cũng được.
  reply_quote    Trả lời kèm TRÍCH DẪN tin gốc (cần tin chữ có đủ message_id, cli_msg_id, uid_from).
  reply_prefix   Chữ gắn đầu câu trả lời, ví dụ "Bot-Hass: ".
Tin 1-1 không bị từ khóa/giới hạn người gửi chặn (người nhắn riêng đã là người được chọn); trích dẫn và tiền tố áp cho cả hai.
"""
from __future__ import annotations

import re
from typing import Any


def is_group(thread_type: Any) -> bool:
    return str(thread_type).lower() in ("1", "group")


def parse_ids(value: Any) -> list[str]:
    """Danh sách mã từ chuỗi (dấu phẩy/cách/xuống dòng) hoặc list; bỏ trống và trùng."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else re.split(r"[\s,;]+", str(value))
    out: list[str] = []
    for it in items:
        s = str(it).strip()
        if s and s not in out:
            out.append(s)
    return out


def evaluate(rule: dict, event: dict) -> tuple[bool, str]:
    """(được trả lời không, nội dung đưa cho AI). Nội dung đã bỏ từ khóa gọi (nếu có); bỏ xong rỗng thì giữ nguyên."""
    text = str(event.get("content") or "").strip()
    if not text:
        return False, ""
    if not is_group(event.get("thread_type")):
        return True, text
    senders = parse_ids(rule.get("reply_senders"))
    if senders and not ({str(event.get("sender_id") or ""), str(event.get("uid_from") or "")} & set(senders)):
        return False, text
    trigger = str(rule.get("reply_trigger") or "").strip()
    if not trigger:
        return True, text
    if trigger.lower() not in text.lower():
        return False, text
    cleaned = re.sub(r"@?" + re.escape(trigger.lstrip("@")), "", text, count=1, flags=re.IGNORECASE).strip(" \t\n,:;")
    return True, cleaned or text


def apply_prefix(rule: dict, text: str) -> str:
    prefix = str(rule.get("reply_prefix") or "").strip()            # quy tắc đã cắt khoảng trắng cuối: luôn tự thêm đúng MỘT dấu cách
    return prefix + " " + text if prefix else text


def quote_payload(rule: dict, event: dict, thread_type: str, thread_id: str, text: str) -> dict | None:
    """Thân dịch vụ quote_message của app, hoặc None nếu không trích dẫn được (tắt, hay thiếu mã tin gốc / không phải tin chữ)."""
    if not rule.get("reply_quote"):
        return None
    msg_id, cli_id, owner = (str(event.get(k) or "").strip() for k in ("message_id", "cli_msg_id", "uid_from"))
    if not (msg_id and cli_id and owner) or str(event.get("kind") or "text") != "text":
        return None
    try:
        ts = int(float(event.get("msg_ts") or 0))
    except (TypeError, ValueError):
        ts = 0
    original = str(event.get("original_content") if event.get("original_content") is not None else event.get("content") or "")
    return {"thread_id": str(thread_id), "type": "group" if thread_type == "group" else "user", "text": text, "msg_id": msg_id,
            "qmsg_owner": owner, "qmsg_cli_id": cli_id, "qmsg_type": 1, "qmsg_ts": ts, "qmsg": original}
