"""Giải cột BinNet của lịch sử Zalo trên điện thoại (ChatContent.BinNet) để lấy lại ĐƯỜNG DẪN ảnh / tệp.

Cấu trúc quan sát được trên 5830 dòng ảnh/tệp thật (13/11/2026), mọi số nguyên là 4 byte big-endian:
  [0..12)  đầu: số mục, độ dài, 0x2c
  [12..24) 4, 0, 0x2e
  [24..28) độ dài JSON tham số (width, height, fileSize, fileExt, checksum, ...)
  [28..)   JSON tham số, rồi các chuỗi có tiền tố 1 byte độ dài: URL (ảnh: ảnh gốc rồi ảnh thu nhỏ; tệp: một URL), JSON nguồn, ảnh thu nhỏ base64, tên người gửi.
Ảnh và tệp tải được qua HTTPS công khai; video hết hạn (404). Hàm này KHÔNG bao giờ ném lỗi: không giải được thì trả rỗng.
"""
from __future__ import annotations

import json
import re
import struct

_URL = re.compile(rb"https?://")
_URL_CHARS = re.compile(rb"[\x21-\x7e]+")


def decode(blob):
    """-> {"params": dict, "urls": [str, ...]} (theo thứ tự xuất hiện)."""
    out = {"params": {}, "urls": []}
    try:
        b = bytes(blob)
    except (TypeError, ValueError):
        return out
    if len(b) < 29:
        return out
    try:
        jl = struct.unpack(">I", b[24:28])[0]
        if 0 < jl <= len(b) - 28 and b[28:29] == b"{":
            params = json.loads(b[28:28 + jl].decode("utf-8", "replace"))
            if isinstance(params, dict):
                out["params"] = params
    except (struct.error, ValueError):
        pass
    for m in _URL.finditer(b):
        pos = m.start()
        length = b[pos - 1] if pos else 0
        chunk = b[pos:pos + length] if length else b""
        if chunk.startswith(b"http") and _URL_CHARS.fullmatch(chunk):
            url = chunk                                   # có tiền tố độ dài khớp: chính xác
        else:
            mm = _URL_CHARS.match(b, pos)
            url = mm.group() if mm else b""
        text = url.decode("ascii", "replace")
        if text and text not in out["urls"]:
            out["urls"].append(text)
    return out
