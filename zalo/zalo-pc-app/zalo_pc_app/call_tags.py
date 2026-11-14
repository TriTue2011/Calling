"""Nhãn cho mỗi dòng nhật ký cuộc gọi (14/11/2026): `[in|out/voice|video/login=web|pc/call=web|pc|mobile]`.

Lý do: ba trục (hướng gọi đến/đi, thoại/video, kiểu đăng nhập web/pc) làm lỗi khó khoanh — mỗi dòng nhật ký tự mang nhãn nên `docker logs | grep "/video/"`
hay `grep "in/voice/login=pc"` lọc đúng nhóm. Nhãn nằm CUỐI dòng (đầu dòng `[call] <việc> call_id=…` giữ nguyên: dung_lai.sh và các bộ lọc cũ dựa vào đó).
"""
import re

_CALL_ID = re.compile(r"call_id=(\d+)")
VIDEO_TYPES = ("video", "video_group")


def media_of(entry):
    return "video" if str((entry or {}).get("type") or "") in VIDEO_TYPES else "voice"


def direction_of(entry):
    return "out" if (entry or {}).get("direction") == "out" else "in"


def tag(entry, login, call_client):
    """-> «in/voice/login=pc/call=pc» (hướng/thoại-hay-video/kiểu đăng nhập/kiểu khai của đường gọi)."""
    return "%s/%s/login=%s/call=%s" % (direction_of(entry), media_of(entry), login, call_client)


def suffix(msg, find_entry, login, call_client):
    """Phần nối vào cuối dòng nhật ký (rỗng nếu dòng không nêu call_id hoặc chưa có bản ghi). find_entry(call_id) -> dict | None. Không bao giờ ném lỗi."""
    try:
        m = _CALL_ID.search(str(msg))
        if not m:
            return ""
        entry = find_entry(m.group(1))
        return "" if not entry else " [%s]" % tag(entry, login, call_client)
    except Exception:  # noqa: BLE001 - nhật ký không được làm hỏng cuộc gọi
        return ""
