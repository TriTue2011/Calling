"""Tương thích tên trường với zalo_bot cũ (13/11/2026).

Automation viết cho `zalo_bot` dùng tên trường khác (`image_path`, `video_path_or_url`, `thumbnail_url`, `group_id`, `thread_ids`, `uid_from`…).
Đổi tên TRƯỚC khi kiểm trường bắt buộc, để dời automation chỉ cần đổi tên miền dịch vụ. Khoá nào dịch vụ không có thì vẫn bị bỏ qua, nhưng
nay có cảnh báo (trước đây bị bỏ lặng lẽ: `ttl`, `quote`, `thumbnail_url` biến mất không dấu vết). Module thuần, không nhập homeassistant.
"""
from __future__ import annotations

from typing import Any, Collection, Mapping

GLOBAL_ALIASES = {
    "file_path_or_url": "file", "image_path": "file", "video_path_or_url": "file", "voice_path": "file", "avatar_source": "file",
    "image_paths": "files",
    "thumbnail_url": "thumbnail",
    "group_id": "thread_id",
}
PER_SERVICE = {
    "forward_message": {"thread_ids": "dest_thread_ids"},
    "create_group": {"members": "member_ids"},
    "delete_message": {"uid_from": "owner_id"},
}
# zalo_bot chọn tài khoản bằng các khoá này; ở đây mỗi tích hợp là một tài khoản (chọn bằng entry_id) nên bỏ qua, không cảnh báo.
IGNORED = frozenset({"account_selection", "own_id"})


def rename_aliases(service: str, data: Any, fields: Collection[str] = ()) -> Any:
    """Bản sao `data` với khoá cũ của zalo_bot đổi sang tên của zalo_call. Khoá đích đã có thì giữ nó và bỏ khoá cũ.
    Không đổi khi khoá cũ chính là một trường của dịch vụ, hoặc khi dịch vụ không có trường đích (trừ thread_id)."""
    if not isinstance(data, Mapping):
        return data
    table = {**GLOBAL_ALIASES, **PER_SERVICE.get(service, {})}
    out = dict(data)
    for old, new in table.items():
        if old not in out or old in fields:
            continue
        if new not in fields and new != "thread_id":
            continue
        value = out.pop(old)
        out.setdefault(new, value)
    return out


def unknown_keys(data: Mapping, fields: Collection[str]) -> list[str]:
    """Các khoá trong `data` mà dịch vụ không dùng (để cảnh báo)."""
    skip = set(fields) | IGNORED | {"entry_id", "thread_id", "type"}
    return sorted(str(k) for k in data if k not in skip)
