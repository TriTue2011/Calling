"""Đo độ rộng/độ cao ảnh từ chính byte của tệp (14/11/2026), không cần thư viện ngoài.

Vì sao: Zalo chọn bố cục album theo tỉ lệ `width`/`height` trong tin ảnh. Nơi gọi không khai (dịch vụ Home Assistant gửi tệp thô) thì
tin mang 0x0 và Zalo xếp ô vuông cắt, khác hẳn ảnh `zalo_bot` (2 ảnh + 1 ảnh lớn khung ngang). WebUI tự đo trong trình duyệt nên không lỗi.
Hỗ trợ JPEG (kể cả EXIF xoay 90°: trình duyệt hiển thị đã xoay nên kích thước khai phải đã xoay), PNG, GIF, WebP (VP8/VP8L/VP8X).
Định dạng lạ hoặc tệp hỏng -> (0, 0): đo hỏng không được chặn việc gửi.
"""

import struct

_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg(b):
    i, n, orient = 2, len(b), 1
    while i + 4 <= n:
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        seg = struct.unpack(">H", b[i + 2:i + 4])[0]
        if m == 0xE1 and b[i + 4:i + 10] == b"Exif\0\0":
            orient = _exif_orientation(b[i + 10:i + 2 + seg])
        if m in _SOF and i + 9 <= n:
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return (h, w) if orient in (5, 6, 7, 8) else (w, h)
        if m == 0xDA:
            break
        i += 2 + seg
    return 0, 0


def _exif_orientation(t):
    try:
        e = "<" if t[:2] == b"II" else ">"
        off = struct.unpack(e + "I", t[4:8])[0]
        cnt = struct.unpack(e + "H", t[off:off + 2])[0]
        for k in range(cnt):
            p = off + 2 + 12 * k
            if struct.unpack(e + "H", t[p:p + 2])[0] == 0x0112:
                return struct.unpack(e + "H", t[p + 8:p + 10])[0]
    except struct.error:
        pass
    return 1


def _png(b):
    return struct.unpack(">II", b[16:24]) if len(b) >= 24 else (0, 0)


def _gif(b):
    return struct.unpack("<HH", b[6:10]) if len(b) >= 10 else (0, 0)


def _webp(b):
    k = b[12:16]
    if k == b"VP8 " and len(b) >= 30:
        w, h = struct.unpack("<HH", b[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if k == b"VP8L" and len(b) >= 25:
        v = struct.unpack("<I", b[21:25])[0]
        return (v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1
    if k == b"VP8X" and len(b) >= 30:
        return int.from_bytes(b[24:27], "little") + 1, int.from_bytes(b[27:30], "little") + 1
    return 0, 0


def image_size(data):
    """-> (width, height) theo điểm ảnh sau khi xoay hiển thị; (0, 0) khi không đọc được. Không bao giờ ném lỗi."""
    b = bytes(data[:262144]) if data else b""
    try:
        if b[:2] == b"\xff\xd8":
            w, h = _jpeg(b)
        elif b[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = _png(b)
        elif b[:6] in (b"GIF87a", b"GIF89a"):
            w, h = _gif(b)
        elif b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            w, h = _webp(b)
        else:
            return 0, 0
    except (struct.error, IndexError):
        return 0, 0
    return (int(w), int(h)) if w > 0 and h > 0 else (0, 0)
