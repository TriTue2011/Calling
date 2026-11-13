"""Gửi NHIỀU ẢNH một lúc thành một album (13/11/2026) — đúng cách zalo_bot cũ (zca-js sendMessage {attachments:[…]}).

zca-js gửi mỗi ảnh là một tin riêng nhưng cả nhóm mang CHUNG `groupLayoutId`, `isGroupLayout: 1`, `idInGroup` (0..N-1) và `totalItemInGroup` (N);
Zalo dựa vào đó vẽ thành một album. GIF/HEIC/tệp khác không vào album (zca-js gửi rời). Module thuần (không nhập homeassistant) để kiểm thử được.
"""
from __future__ import annotations

import os
from typing import Sequence

ALBUM_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_MIME_OK = ("image/jpeg", "image/png", "image/webp")


def is_album_photo(filename: str, mime: str = "") -> bool:
    """Ảnh vào được album: jpg/jpeg/png/webp theo đuôi (không đuôi thì theo MIME) — khớp chat.is_photo_file của app."""
    ext = os.path.splitext(str(filename or ""))[1].lower()
    if ext:
        return ext in ALBUM_EXTS
    return str(mime or "").strip().lower() in _MIME_OK


def album_plan(items: Sequence[tuple[str, str]], layout_id: int | str) -> list[dict | None]:
    """items = [(tên tệp, mime)] theo thứ tự gửi -> mỗi phần tử: None (gửi rời) hoặc 4 trường album. Chỉ gộp khi có từ 2 ảnh trở lên."""
    idx = [i for i, (name, mime) in enumerate(items) if is_album_photo(name, mime)]
    plan: list[dict | None] = [None] * len(items)
    if len(idx) >= 2:
        for k, i in enumerate(idx):
            plan[i] = {"groupLayoutId": str(layout_id), "totalItemInGroup": str(len(idx)), "isGroupLayout": "1", "idInGroup": str(k)}
    return plan
