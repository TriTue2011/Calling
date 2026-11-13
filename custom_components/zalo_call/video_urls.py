"""Đổi đường dẫn tệp trong HA thành địa chỉ công khai để Zalo tải video (13/11/2026).

Zalo gửi video thật bằng ĐỊA CHỈ (zca-js sendVideo / zalo_bot cũ): máy chủ Zalo tự tải về rồi lưu lại. Nên tệp nằm trong HA phải có một địa chỉ
mà internet mở được. Hai nơi tệp thường nằm:
  /config/www/<đường>   -> {gốc}/local/<đường>               (HA phục vụ công khai, không cần đăng nhập)
  thư mục media <id>    -> {gốc}/media/<id>/<đường>?authSig=… (cần chữ ký có hạn, do HA ký)
Module thuần (không nhập homeassistant) để kiểm thử được ngoài HA.
"""
from __future__ import annotations

import os
import urllib.parse
from typing import Callable, Mapping


def _inside(path: str, root: str) -> str | None:
    """Phần đường dẫn tương đối của `path` trong `root`, hoặc None nếu nằm ngoài (chặn ../)."""
    path, root = os.path.normpath(path), os.path.normpath(root)
    try:
        if os.path.commonpath([path, root]) != root or path == root:
            return None
    except ValueError:
        return None
    return os.path.relpath(path, root).replace(os.sep, "/")


def local_to_public(path: str, *, www_dir: str, media_dirs: Mapping[str, str], base_url: str,
                    sign: Callable[[str], str]) -> str | None:
    """Địa chỉ công khai của tệp cục bộ, hoặc None nếu không ánh xạ được (ngoài www và các thư mục media)."""
    base = (base_url or "").rstrip("/")
    if not base:
        return None
    rel = _inside(path, www_dir)
    if rel is not None:
        return "%s/local/%s" % (base, urllib.parse.quote(rel))
    for media_id, root in (media_dirs or {}).items():
        rel = _inside(path, root)
        if rel is not None:
            url_path = "/media/%s/%s" % (urllib.parse.quote(str(media_id)), urllib.parse.quote(rel))
            return base + sign(url_path)
    return None


def sibling_thumb_candidates(video_path: str) -> list[str]:
    """Các tên ảnh bìa có thể có cạnh video: <tên>_thumb.jpg (bản thiết kế camera tạo sẵn), <tên không _video>_thumb.jpg, <tên>.jpg."""
    root, _ext = os.path.splitext(video_path)
    out = []
    if root.endswith("_video"):
        out.append(root[: -len("_video")] + "_thumb.jpg")
    out += [root + "_thumb.jpg", root + ".jpg", root + ".jpeg", root + ".png"]
    return list(dict.fromkeys(out))
