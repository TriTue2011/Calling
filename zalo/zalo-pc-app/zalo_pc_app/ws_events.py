"""Khung và giải mã sự kiện của kênh WebSocket Zalo (hàm thuần, không mạng).

Khung nhị phân: 4 byte đầu [phiên bản u8][cmd u16 little-endian][subCmd u8] rồi JSON UTF-8 {"data": "...", "encrypt": 0..3}. Nguồn: thư viện mã nguồn mở
zca-js (listen.ts, utils.decodeEventData) và chuỗi trong app iOS «GiaNô» (wss://ws1-msg.chat.zalo.me, cmd/sub/enc/err).
  encrypt 0  data là JSON thường
  encrypt 1  base64 -> nén zlib
  encrypt 2  base64 (đã urlencode) -> AES-GCM (IV = 16 byte đầu, AAD = 16 byte kế, phần còn lại = bản mã + thẻ 16 byte; khoá = `key` do máy chủ gửi ở
             khung cmd 1 sub 1) -> nén zlib
  encrypt 3  như 2 nhưng KHÔNG nén
Dữ liệu sau giải mã có hình dạng giống dữ liệu long-poll (msgs, groupMsgs, controls, reacts...) nên dùng lại đúng các hàm tách của hai bộ poll.
"""
from __future__ import annotations

import base64
import json
import struct
import urllib.parse
import zlib

from . import aesgcm_pure

HEADER = struct.Struct("<BHB")

CMD_HELLO = (1, 1)                 # (cmd, subCmd): máy chủ gửi khoá phiên {"key": "<base64>"}
CMD_DUPLICATE = 3000               # có kết nối khác của tài khoản này: máy chủ sẽ đóng kết nối này
SYNC_CMDS = (501, 551, 521)        # tin nhắn 1-1 (msgs), tin trang, tin nhóm (groupMsgs) -> SyncPoller
CTRL_CMDS = (601, 612)             # điều khiển (cuộc gọi, nhóm, tệp...) và cảm xúc -> CtrlPoller


def encode_frame(version, cmd, sub, data):
    """Khung gửi đi (ví dụ ping: version 1, cmd 2, sub 1, data {"eventId": ms})."""
    return HEADER.pack(version, cmd, sub) + json.dumps(data, separators=(",", ":")).encode("utf-8")


def parse_frame(raw):
    """-> (version, cmd, sub, parsed_json_or_None). Nén/đóng gói sai thì parsed là None; chưa đủ 4 byte thì ValueError."""
    raw = bytes(raw)
    if len(raw) < HEADER.size:
        raise ValueError("khung ngan hon 4 byte")
    version, cmd, sub = HEADER.unpack(raw[:HEADER.size])
    body = raw[HEADER.size:]
    if not body:
        return version, cmd, sub, None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return version, cmd, sub, None
    return version, cmd, sub, parsed if isinstance(parsed, dict) else None


def _b64(text):
    text = text.strip()
    return base64.b64decode(text + "=" * (-len(text) % 4))


def _inflate(raw):
    for wbits in (47, -zlib.MAX_WBITS):                 # zlib/gzip tự nhận, rồi deflate trần
        try:
            return zlib.decompress(raw, wbits)
        except zlib.error:
            continue
    raise ValueError("khong giai nen duoc")


def decode_event(parsed, cipher_key_b64=None):
    """{"data": str, "encrypt": 0..3} -> đối tượng JSON đã giải mã (thường có khoá "data"). Ném ValueError khi sai khuôn dạng / thiếu khoá / sai thẻ GCM."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("data"), str):
        raise ValueError("thieu data dang chuoi")
    enc = parsed.get("encrypt")
    if not isinstance(enc, int) or isinstance(enc, bool) or not 0 <= enc <= 3:
        raise ValueError("encrypt khong hop le")
    text = parsed["data"]
    if enc == 0:
        return json.loads(text)
    try:
        raw = _b64(text if enc == 1 else urllib.parse.unquote(text))
    except ValueError as exc:
        raise ValueError("base64 sai") from exc
    if enc != 1:
        if not cipher_key_b64 or len(raw) < 48:
            raise ValueError("thieu khoa hoac du lieu qua ngan")
        raw = aesgcm_pure.decrypt(_b64(cipher_key_b64), raw[:16], raw[16:32], raw[32:])
    if enc != 3:
        raw = _inflate(raw)
    return json.loads(raw.decode("utf-8"))


def event_payload(decoded):
    """Phần dữ liệu để đưa cho bộ poll: decoded["data"] nếu là dict, ngược lại {}."""
    if isinstance(decoded, dict) and isinstance(decoded.get("data"), dict):
        return decoded["data"]
    return {}


def route(cmd):
    """Sự kiện cmd đi về bộ poll nào: "sync" | "ctrl" | None (chỉ đếm)."""
    if cmd in SYNC_CMDS:
        return "sync"
    if cmd in CTRL_CMDS:
        return "ctrl"
    return None


def build_ping():
    import time
    return encode_frame(1, 2, 1, {"eventId": int(time.time() * 1000)})


def encode_event_for_tests(data_obj, cipher_key_b64=None, enc=2):
    """Dựng một khung `parsed` đúng như máy chủ (dùng trong test): data_obj -> JSON -> nén/mã hoá theo `enc`."""
    import os
    text = json.dumps(data_obj, separators=(",", ":")).encode("utf-8")
    if enc == 0:
        return {"data": text.decode("utf-8"), "encrypt": 0}
    if enc != 3:
        text = zlib.compress(text)
    if enc in (2, 3):
        iv, aad = os.urandom(16), os.urandom(16)
        text = iv + aad + aesgcm_pure.encrypt(_b64(cipher_key_b64), iv, aad, text)
    b64 = base64.b64encode(text).decode("ascii")
    return {"data": urllib.parse.quote(b64, safe="") if enc in (2, 3) else b64, "encrypt": enc}
