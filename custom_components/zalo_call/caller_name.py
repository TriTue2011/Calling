"""Tên người gọi để ĐỌC ra loa: tên trong quy tắc → tên đã lưu trong danh bạ Zalo (tra theo thread_id) → tên Zalo trong sự kiện → «người lạ»/«một người».
Không bao giờ đọc một dãy số thuần (mã Zalo): sự kiện cuộc gọi đến thường có caller_name rỗng nên `peer` chính là mã số."""
from __future__ import annotations

from typing import Any


def find_contact_name(contacts: Any, thread_id: Any) -> str:
    """Tên đã lưu của thread_id trong dữ liệu danh bạ của app ({friends: {rows: [{id, name}]}, groups: ...}); rỗng nếu không có."""
    tid = str(thread_id or "").strip()
    if not tid or not isinstance(contacts, dict):
        return ""
    for part in ("friends", "groups"):
        block = contacts.get(part)
        for row in (block.get("rows") if isinstance(block, dict) else None) or []:
            if isinstance(row, dict) and str(row.get("id") or "") == tid and str(row.get("name") or "").strip():
                return str(row["name"]).strip()
    return ""


def spoken_name(rule: dict[str, Any], payload: dict[str, Any]) -> str:
    """Tên để đọc. `payload["contact_name"]` là tên danh bạ đã tra sẵn (xem find_contact_name)."""
    for cand in (rule.get("name"), payload.get("contact_name"), payload.get("peer")):
        name = str(cand or "").strip()
        if name and not name.isdigit():
            return name
    return "người lạ" if payload.get("contact_status") == "stranger" else "một người"
