"""Phủ service addon (96 services) lên app Zalo kiểu PC.

Nguồn duy nhất cho endpoint PC: bao-cao-doi-chieu-addon.md Bảng 1 +
Bảng 3 (bundle client PC thật Zalo PC 26.11.10, bảng lệnh 231 mục).
Quy tắc trung thực của module này:

* Mọi thao tác đều đi qua cùng một đường dây post-login như
  contacts/signaling: common params zpw_ver=695 & zpw_type=30 +
  params=<AES-JSON bằng khóa phiên zpw_enk, AES-CBC IV 0, base64>,
  response envelope HAI LỚP (decode_postlogin_data). Không có
  endpoint nào ở đây được bịa: path + mã lệnh lấy từ bảng lệnh;
  chỗ nào audit ghi "chưa lần hết body" thì body dùng các tham số
  của chính service addon đó (msg_id, thread_id, ...) và entry
  trong CATALOG đánh dấu body_unverified=True — integrator / đợt
  lần tiếp theo phải xác minh body thật trước khi coi là xong.
* Service nào KHÔNG có đường PC trong bảng lệnh (reaction, ghim,
  ẩn hội thoại + PIN, lưu trữ, kết bạn/chặn/biệt danh, poll, tin
  nhắn nhanh) thì KHÔNG có nút bấm: CATALOG ghi status
  "unsupported" + lý do, server trả 409, UI chỉ hiện trạng thái.
* Service chỉ thuộc máy chủ zalobot (webhook, proxy, đa tài khoản)
  ghi status "zalobot" — phiên web, không phải của app PC.
* Gửi tin (text/file/ảnh/video/link/card/voice) có đường PC nhưng
  thuộc KHUNG CHAT — agent chat làm song song; ở đây chỉ ghi
  status "chat" trỏ tới đó, không viết lại đường gửi.

Route server (móc duy nhất, xem server.py): 
  GET  /api/svc/catalog      -> CATALOG (không cần đăng nhập)
  POST /api/svc/<action>     -> dispatch(); yêu cầu phiên Zalo
    (server._require_login). ĐĂNG NHẬP APP (user/mật khẩu) do
    agent đăng nhập làm song song — chưa có trong bản này; khi
    có, integrator bọc thêm auth app quanh /api/svc/* (xem
    AUTH_NOTE dưới); hiện tại route chỉ được bảo vệ bằng phiên
    Zalo, giống /api/contacts và /api/call/*.

Thread = (threadId, type): type "user" (1-1, threadId = userId),
type "group" (threadId = groupId thô). Các op 1-1 dùng toid, các
op nhóm dùng grid — đúng như bundle (sendZText, sendSticker...).
"""

import json
import time
import urllib.parse

from . import protocol
from .crypto import decode_postlogin_data, session_aes_encrypt

AUTH_NOTE = (
    "Route /api/svc/* hiện chỉ kiểm tra phiên Zalo "
    "(server._require_login). Đăng nhập app (user/mật khẩu) chưa "
    "có trong bản này — integrator phải bọc thêm auth app khi "
    "agent đăng nhập xong, giống các route /api/* khác."
)

# Nhóm hiển thị trên UI (theo cách gộp Bảng 1 của báo cáo đối chiếu).
GROUPS = [
    ("tin_nhan", "Tác động tin nhắn"),
    ("nhom", "Quản lý nhóm"),
    ("hoi_thoai", "Hội thoại / trạng thái"),
    ("ho_so", "Hồ sơ / người dùng"),
    ("sticker", "Sticker"),
    ("nhac", "Nhắc hẹn / bảng tin"),
    ("nhan", "Nhãn / đang gõ"),
    ("khac", "Tài khoản / hệ thống"),
]


class UnsupportedService(Exception):
    """Service có trong CATALOG nhưng không gọi được từ app PC."""

    def __init__(self, service, status, reason):
        super().__init__("%s: %s" % (service, reason))
        self.service = service
        self.status = status
        self.reason = reason


class UnknownAction(Exception):
    pass


def _csv(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [s.strip() for s in str(value).split(",") if s.strip()]


def _client_id():
    return str(int(time.time() * 1000))


def _need(params, key, service):
    v = params.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        raise ValueError("%s: thiếu tham số bắt buộc %s" % (service, key))
    return v


def _thread(params, service):
    tid = _need(params, "thread_id", service)
    ttype = (params.get("type") or "user").lower()
    if ttype not in ("user", "group"):
        raise ValueError("%s: type phải là user hoặc group" % service)
    return str(tid), ttype


def _toid_or_grid(tid, ttype, extra=None):
    """Địa chỉ đích theo kiểu thread: 1-1 -> toid, nhóm -> grid."""
    body = dict(extra or {})
    if ttype == "group":
        body["grid"] = tid
    else:
        body["toid"] = tid
    return body


# ------------------------------------------------------------------ body
# Mỗi builder nhận (params UI, thread_id, thread_type) -> body JSON
# gửi trong params AES. Body nào audit chưa lần hết thì ghi rõ trong
# CATALOG (body_unverified=True) — dùng tham số addon, chưa xác
# minh thật, KHÔNG được coi là "đã đúng với client PC thật".

def _b_undo(p, tid, tt):
    return _toid_or_grid(tid, tt, {
        "msgId": _need(p, "msg_id", "undo_message"),
        "cliMsgId": p.get("cli_msg_id", ""),
        "imei": p["_imei"]})


def _b_delete_msg(p, tid, tt):
    return _toid_or_grid(tid, tt, {
        "msgId": _need(p, "msg_id", "delete_message"),
        "cliMsgId": p.get("cli_msg_id", ""),
        "uidFrom": p.get("uid_from", ""),
        "imei": p["_imei"]})


def _b_forward(p, tid, tt):
    dest = _csv(_need(p, "dest_thread_ids", "forward_message"))
    return _toid_or_grid(tid, tt, {
        "msgId": _need(p, "msg_id", "forward_message"),
        "threadIds": dest, "imei": p["_imei"]})


def _b_quote(p, tid, tt):
    return _toid_or_grid(tid, tt, {
        "msgId": _need(p, "msg_id", "quote_message"),
        "message": _need(p, "text", "quote_message"),
        "clientId": _client_id(), "imei": p["_imei"]})


def _b_seen(p, tid, tt):
    # Body đã biết (Bảng 3 dòng 14): {msg_ids:[...], seen:bool}.
    return _toid_or_grid(tid, tt, {
        "msg_ids": _csv(_need(p, "msg_ids", "mark_seen")),
        "seen": True, "imei": p["_imei"]})


def _b_parse_link(p, tid, tt):
    return {"link": _need(p, "link", "parse_link"), "imei": p["_imei"]}


def _b_important(p, tid, tt):
    # Body đã biết (Bảng 3 dòng 19): {limit, uid}.
    if tt != "user":
        raise UnsupportedService(
            "fetch_important", "unsupported",
            "Tin nhắn quan trọng chỉ lần được cho hội thoại 1-1 "
            "(fetchImportant lấy theo uid); nhóm chưa có đường PC.")
    return {"limit": 50, "uid": tid, "imei": p["_imei"]}


def _b_history_group(p, tid, tt):
    # Body đã biết (Bảng 3 dòng 2): {grid, count}.
    if tt != "group":
        raise UnsupportedService(
            "get_group_chat_history", "unsupported",
            "Lịch sử 1-1 không có endpoint HTTPS trong bundle "
            "(chỉ đọc DB local + pull_mobile_msg); chỉ nhóm có "
            "/api/group/history.")
    try:
        count = int(p.get("count") or 50)
    except ValueError:
        count = 50
    return {"grid": tid, "count": max(1, min(count, 1000))}


def _b_typing(p, tid, tt):
    # Body đã biết (Bảng 3 dòng 13).
    if tt == "group":
        return {"grid": tid, "imei": p["_imei"]}
    return {"toid": tid, "destType": "USER", "imei": p["_imei"]}


def _b_sticker(p, tid, tt):
    # Body đã biết (Bảng 3 dòng 7).
    return _toid_or_grid(tid, tt, {
        "stickerId": _need(p, "sticker_id", "send_sticker"),
        "cateId": p.get("cate_id", ""),
        "type": p.get("type_") or p.get("sticker_type") or "",
        "clientId": _client_id(), "imei": p["_imei"]})


def _b_create_group(p, tid, tt):
    return {"name": _need(p, "name", "create_group"),
            "members": _csv(p.get("member_ids")),
            "imei": p["_imei"]}


def _b_group_info(p, tid, tt):
    # /api/group/getgi/v2 (11162): thông tin + thành viên một nhóm.
    return {"grid": tid, "imei": p["_imei"]}


def _b_add_member(p, tid, tt):
    return {"grid": tid, "members": _csv(
        _need(p, "member_id", "add_user_to_group")), "imei": p["_imei"]}


def _b_remove_member(p, tid, tt):
    return {"grid": tid, "memberIds": _csv(
        _need(p, "member_id", "remove_user_from_group")),
        "imei": p["_imei"]}


def _b_group_name(p, tid, tt):
    return {"grid": tid, "name": _need(p, "name", "change_group_name"),
            "imei": p["_imei"]}


def _b_group_avatar(p, tid, tt):
    # upavatar (11195) ở client thật là upload file; ở đây nhận
    # avatar_url, body chưa xác minh — xem CATALOG.
    return {"grid": tid, "avatarUrl": _need(
        p, "avatar_url", "change_group_avatar"), "imei": p["_imei"]}


def _b_deputy(p, tid, tt, service):
    return {"grid": tid,
            "memberId": _need(p, "member_id", service),
            "imei": p["_imei"]}


def _b_group_only(p, tid, tt, service):
    if tt != "group":
        raise UnsupportedService(service, "unsupported",
                                 "Thao tác này chỉ áp dụng cho nhóm.")
    return {"grid": tid, "imei": p["_imei"]}


def _b_group_link(p, tid, tt):
    return _b_group_only(p, tid, tt, "get_group_link")


def _b_join_group(p, tid, tt):
    return {"link": _need(p, "link", "join_group"), "imei": p["_imei"]}


def _b_leave_group(p, tid, tt):
    silent = str(p.get("silent", "")).lower() in ("1", "true", "yes")
    return {"grid": tid, "silent": silent, "imei": p["_imei"]}


def _b_note_create(p, tid, tt):
    return {"grid": tid, "title": _need(p, "title", "create_note_group"),
            "pinAct": True, "imei": p["_imei"]}


def _b_note_edit(p, tid, tt):
    return {"grid": tid,
            "topicId": _need(p, "topic_id", "edit_note_group"),
            "title": _need(p, "title", "edit_note_group"),
            "imei": p["_imei"]}


def _b_board_list(p, tid, tt):
    return {"grid": tid, "imei": p["_imei"]}


def _b_unread(p, tid, tt, service):
    return {"threadId": tid, "type": 1 if tt == "group" else 0,
            "imei": p["_imei"]}


def _b_delete_chat(p, tid, tt):
    return _toid_or_grid(tid, tt, {"imei": p["_imei"]})


def _b_auto_delete(p, tid, tt):
    ttl = _need(p, "ttl", "update_auto_delete_chat")
    return {"threadId": tid, "type": 1 if tt == "group" else 0,
            "ttl": int(ttl), "imei": p["_imei"]}


def _b_mute(p, tid, tt):
    # Mức PROFILE (audit Bảng 1 nhóm D): chưa rõ có mức thread
    # không — body chỉ mang duration, xem CATALOG.
    dur = _need(p, "duration", "set_mute")
    return {"duration": int(dur), "imei": p["_imei"]}


def _b_user_info(p, tid, tt):
    return {"userId": _need(p, "user_id", "get_user_info"),
            "imei": p["_imei"]}


def _b_find_user(p, tid, tt):
    return {"phone": _need(p, "phone", "find_user"), "imei": p["_imei"]}


def _b_last_online(p, tid, tt):
    return {"userId": _need(p, "user_id", "last_online"),
            "imei": p["_imei"]}


def _b_update_profile(p, tid, tt):
    body = {"imei": p["_imei"]}
    if p.get("name"):
        body["name"] = p["name"]
    if p.get("dob"):
        body["dob"] = p["dob"]
    if p.get("gender") in ("0", "1"):
        body["gender"] = int(p["gender"])
    if not any(k in body for k in ("name", "dob", "gender")):
        raise ValueError("update_profile: cần ít nhất name, dob "
                         "hoặc gender")
    return body


def _b_update_settings(p, tid, tt):
    return {"settingType": _need(p, "setting_type", "update_settings"),
            "status": int(_need(p, "status", "update_settings")),
            "imei": p["_imei"]}


def _b_change_avatar(p, tid, tt):
    # /api/social/profile/avatar-url (audit §G): nhận URL ảnh.
    return {"avatarUrl": _need(p, "avatar_url", "change_account_avatar"),
            "imei": p["_imei"]}


def _b_avatar_list(p, tid, tt):
    try:
        count = int(p.get("count") or 20)
    except ValueError:
        count = 20
    try:
        page = int(p.get("page") or 1)
    except ValueError:
        page = 1
    return {"count": count, "page": page, "imei": p["_imei"]}


def _b_sticker_list(p, tid, tt):
    return {"imei": p["_imei"]}


def _b_sticker_detail(p, tid, tt):
    return {"cateId": _need(p, "sticker_album", "get_stickers_detail"),
            "imei": p["_imei"]}


def _b_reminder_create(p, tid, tt):
    # 1-1: /api/board/oneone/create (audit §F đã nêu tên). Nhóm:
    # không thấy endpoint tạo nhắc hẹn nhóm trong bảng lệnh —
    # không bịa path, trả "chưa hỗ trợ" cho nhóm.
    if tt != "user":
        raise UnsupportedService(
            "create_reminder", "unsupported",
            "Tạo nhắc hẹn nhóm chưa có endpoint trong bảng lệnh "
            "231 mục (chỉ có đường 1-1 /api/board/oneone/create); "
            "cần lần thêm, không bịa path.")
    return {"toid": tid,
            "title": _need(p, "title", "create_reminder"),
            "content": p.get("content", ""),
            "remindTime": _need(p, "remind_time", "create_reminder"),
            "imei": p["_imei"]}


def _b_reminder_remove(p, tid, tt):
    if tt != "user":
        raise UnsupportedService(
            "remove_reminder", "unsupported",
            "Xóa nhắc hẹn nhóm chưa có endpoint trong bảng lệnh "
            "(chỉ có đường 1-1 /api/board/oneone/remove).")
    return {"toid": tid,
            "reminderId": _need(p, "reminder_id", "remove_reminder"),
            "imei": p["_imei"]}


def _b_reminder_edit(p, tid, tt):
    if tt == "user":
        return {"toid": tid,
                "topicId": _need(p, "topic_id", "edit_reminder"),
                "title": _need(p, "title", "edit_reminder"),
                "imei": p["_imei"]}
    return {"grid": tid,
            "topicId": _need(p, "topic_id", "edit_reminder"),
            "title": _need(p, "title", "edit_reminder"),
            "imei": p["_imei"]}


def _b_reminder_get(p, tid, tt):
    # /api/board/topic/getReminder (audit §F, đường nhóm đã nêu).
    return {"grid": tid,
            "reminderId": _need(p, "reminder_id", "get_reminder"),
            "imei": p["_imei"]}


def _b_reminder_list(p, tid, tt):
    if tt == "user":
        return {"toid": tid, "imei": p["_imei"]}
    return {"grid": tid, "imei": p["_imei"]}


def _b_reminder_responses(p, tid, tt):
    return {"grid": tid,
            "reminderId": _need(p, "reminder_id",
                                "get_reminder_responses"),
            "imei": p["_imei"]}


def _b_labels(p, tid, tt):
    return {"imei": p["_imei"]}


def _b_label_update(p, tid, tt):
    return {"threadId": tid, "type": 1 if tt == "group" else 0,
            "labelIds": _csv(_need(p, "label_ids", "update_label")),
            "imei": p["_imei"]}


# ------------------------------------------------------------------ OPS
# action -> spec. domain: "chat" | "group" | "profile" | "convers".
# method: GET (params trong query) hay POST (params trong form body).
# thread: "both" | "user" | "group" | "none" (không cần thread).
# body_unverified: True = path + mã có trong bundle nhưng body chưa
#   được lần hết trong audit — dùng tham số addon, cần xác minh thật.

def _op(addon_no, addon, group, label, desc, domain, path, code,
        method, thread, fields, body_fn, body_unverified=True,
        danger=False):
    return {"addon_no": addon_no, "addon": addon, "group": group,
            "label": label, "desc": desc, "domain": domain,
            "path": path, "code": code, "method": method,
            "thread": thread, "fields": fields,
            "body_fn": body_fn, "body_unverified": body_unverified,
            "danger": danger, "status": "supported"}


F_MSG = [{"key": "msg_id", "label": "ID tin nhắn", "required": True}]
F_MSG_CLI = F_MSG + [{"key": "cli_msg_id", "label": "Client ID tin nhắn"}]

OPS = {
    # --- Tác động tin nhắn (nhóm E + liên quan) ---
    "undo_message": _op(
        28, "undo_message", "tin_nhan", "Thu hồi tin nhắn",
        "Thu hồi tin đã gửi (1-1: /api/message/undo 11281; "
        "nhóm: /api/group/undomsg 11192).",
        None, None, None, "POST", "both", F_MSG_CLI, _b_undo),
    "delete_message": _op(
        68, "delete_message", "tin_nhan", "Xóa tin nhắn",
        "Xóa tin chỉ ở phía mình (1-1: 11779; nhóm: 11834).",
        None, None, None, "POST", "both",
        F_MSG_CLI + [{"key": "uid_from", "label": "UID người gửi"}],
        _b_delete_msg),
    "forward_message": _op(
        69, "forward_message", "tin_nhan", "Chuyển tiếp tin nhắn",
        "Chuyển tiếp tới nhiều thread (1-1: 11199; nhóm: 11818).",
        None, None, None, "POST", "both",
        F_MSG + [{"key": "dest_thread_ids",
                  "label": "Thread đích (cách nhau bằng dấu phẩy)",
                  "required": True}],
        _b_forward),
    "quote_message": _op(
        None, "(quote — trong send_message)", "tin_nhan",
        "Trích dẫn tin nhắn",
        "Không có service riêng trong 96; trích dẫn nằm trong "
        "send_message (1-1: /api/message/quote 11771; nhóm: "
        "/api/group/quote 11197).",
        None, None, None, "POST", "both",
        F_MSG + [{"key": "text", "label": "Nội dung trích dẫn",
                  "required": True}],
        _b_quote),
    "mark_seen": _op(
        None, "(seen/delivered — ngoài 96)", "tin_nhan",
        "Đánh dấu đã xem / đã nhận",
        "1-1: /api/message/seen 11150, delivered 11153; nhóm: "
        "/api/group/seen 11167, delivered 11166. Body đã biết "
        "{msg_ids, seen}.",
        None, None, None, "POST", "both",
        [{"key": "msg_ids", "label": "ID tin nhắn (cách nhau bằng "
          "dấu phẩy)", "required": True}],
        _b_seen, body_unverified=False),
    "parse_link": _op(
        70, "parse_link", "tin_nhan", "Phân tích link lấy preview",
        "/api/message/parselink (11285).",
        "chat", "/api/message/parselink", 11285, "POST", "none",
        [{"key": "link", "label": "Link", "required": True}],
        _b_parse_link),
    "fetch_important": _op(
        None, "(tin quan trọng — ngoài 96)", "tin_nhan",
        "Xem tin nhắn quan trọng",
        "/api/message/fetchImportant (12114), body đã biết "
        "{limit, uid}. Chỉ hội thoại 1-1.",
        "chat", "/api/message/fetchImportant", 12114, "GET", "user",
        [], _b_important, body_unverified=False),
    "send_typing_event": _op(
        95, "send_typing_event", "nhan", "Gửi trạng thái đang gõ",
        "1-1: /api/message/typing 11144 {toid, destType, imei}; "
        "nhóm: /api/group/typing 11196 {grid, imei}. Body đã biết.",
        None, None, None, "POST", "both", [], _b_typing,
        body_unverified=False),
    "get_group_chat_history": _op(
        41, "get_group_chat_history", "tin_nhan", "Xem lịch sử nhóm",
        "GET /api/group/history (11240) {grid, count}. Chỉ nhóm — "
        "lịch sử 1-1 không có endpoint HTTPS (DB local + sync).",
        "group", "/api/group/history", 11240, "GET", "group",
        [{"key": "count", "label": "Số tin (tối đa 1000)"}],
        _b_history_group, body_unverified=False),
    # --- Quản lý nhóm (nhóm C) ---
    "create_group": _op(
        9, "create_group", "nhom", "Tạo nhóm mới",
        "/api/group/create (11185) / create/v2 (12443).",
        "group", "/api/group/create", 11185, "POST", "none",
        [{"key": "name", "label": "Tên nhóm", "required": True},
         {"key": "member_ids",
          "label": "Thành viên (userId, cách nhau bằng dấu phẩy)"}],
        _b_create_group),
    "get_group_info": _op(
        10, "get_group_info", "nhom", "Xem thông tin nhóm",
        "/api/group/getgi/v2 (11162) — thông tin + thành viên "
        "một nhóm (đường getmg-v2 đã dùng cho danh bạ).",
        "group", "/api/group/getgi/v2", 11162, "GET", "group", [],
        _b_group_info),
    "add_user_to_group": _op(
        11, "add_user_to_group", "nhom", "Mời thành viên vào nhóm",
        "/api/group/invite (11186) / invite/v2 (12444).",
        "group", "/api/group/invite", 11186, "POST", "group",
        [{"key": "member_id", "label": "UserId (cách nhau bằng dấu "
          "phẩy)", "required": True}],
        _b_add_member),
    "remove_user_from_group": _op(
        12, "remove_user_from_group", "nhom", "Đuổi thành viên",
        "/api/group/kickout (11187) / kickout/multi (12606).",
        "group", "/api/group/kickout", 11187, "POST", "group",
        [{"key": "member_id", "label": "UserId (cách nhau bằng dấu "
          "phẩy)", "required": True}],
        _b_remove_member, danger=True),
    "change_group_name": _op(
        31, "change_group_name", "nhom", "Đổi tên nhóm",
        "/api/group/updateinfo (11188).",
        "group", "/api/group/updateinfo", 11188, "POST", "group",
        [{"key": "name", "label": "Tên mới", "required": True}],
        _b_group_name),
    "change_group_avatar": _op(
        32, "change_group_avatar", "nhom", "Đổi ảnh đại diện nhóm",
        "/api/group/upavatar (11195). Client thật upload file; "
        "ở đây nhận URL ảnh, body chưa xác minh.",
        "group", "/api/group/upavatar", 11195, "POST", "group",
        [{"key": "avatar_url", "label": "URL ảnh đại diện",
          "required": True}],
        _b_group_avatar),
    "add_group_deputy": _op(
        42, "add_group_deputy", "nhom", "Thêm phó nhóm",
        "/api/group/admins/add (11814).",
        "group", "/api/group/admins/add", 11814, "POST", "group",
        [{"key": "member_id", "label": "UserId", "required": True}],
        lambda p, t, tt: _b_deputy(p, t, tt, "add_group_deputy")),
    "remove_group_deputy": _op(
        43, "remove_group_deputy", "nhom", "Xóa phó nhóm",
        "/api/group/admins/remove (11815).",
        "group", "/api/group/admins/remove", 11815, "POST", "group",
        [{"key": "member_id", "label": "UserId", "required": True}],
        lambda p, t, tt: _b_deputy(p, t, tt, "remove_group_deputy")),
    "change_group_owner": _op(
        44, "change_group_owner", "nhom", "Chuyển quyền sở hữu nhóm",
        "/api/group/change-owner (10063).",
        "group", "/api/group/change-owner", 10063, "POST", "group",
        [{"key": "member_id", "label": "UserId chủ mới",
          "required": True}],
        lambda p, t, tt: _b_deputy(p, t, tt, "change_group_owner"),
        danger=True),
    "disperse_group": _op(
        45, "disperse_group", "nhom", "Giải tán nhóm",
        "/api/group/disperse (11832). Không hoàn tác được.",
        "group", "/api/group/disperse", 11832, "POST", "group", [],
        lambda p, t, tt: _b_group_only(p, t, tt, "disperse_group"),
        danger=True),
    "enable_group_link": _op(
        46, "enable_group_link", "nhom", "Bật link tham gia nhóm",
        "/api/group/link/new (11822).",
        "group", "/api/group/link/new", 11822, "POST", "group", [],
        lambda p, t, tt: _b_group_only(p, t, tt, "enable_group_link")),
    "disable_group_link": _op(
        47, "disable_group_link", "nhom", "Tắt link tham gia nhóm",
        "/api/group/link/disable (11823).",
        "group", "/api/group/link/disable", 11823, "POST", "group",
        [], lambda p, t, tt: _b_group_only(p, t, tt,
                                           "disable_group_link")),
    "get_group_link": _op(
        None, "(link nhóm — ngoài 96)", "nhom", "Xem link nhóm",
        "/api/group/link/detail (11821).",
        "group", "/api/group/link/detail", 11821, "GET", "group", [],
        _b_group_link),
    "join_group": _op(
        48, "join_group", "nhom", "Tham gia nhóm bằng link",
        "/api/group/link/join (11825).",
        "group", "/api/group/link/join", 11825, "POST", "none",
        [{"key": "link", "label": "Link mời", "required": True}],
        _b_join_group),
    "leave_group": _op(
        49, "leave_group", "nhom", "Rời nhóm",
        "/api/group/leave (11189).",
        "group", "/api/group/leave", 11189, "POST", "group",
        [{"key": "silent", "label": "Rời lặng lẽ (true/false)"}],
        _b_leave_group, danger=True),
    "create_note_group": _op(
        76, "create_note_group", "nhom", "Tạo ghi chú trong nhóm",
        "/api/board/topic/create.",
        "group", "/api/board/topic/create", None, "POST", "group",
        [{"key": "title", "label": "Tiêu đề ghi chú",
          "required": True}],
        _b_note_create),
    "edit_note_group": _op(
        77, "edit_note_group", "nhom", "Sửa ghi chú trong nhóm",
        "/api/board/topic/update.",
        "group", "/api/board/topic/update", None, "POST", "group",
        [{"key": "topic_id", "label": "ID ghi chú",
          "required": True},
         {"key": "title", "label": "Tiêu đề mới", "required": True}],
        _b_note_edit),
    "get_list_board": _op(
        78, "get_list_board", "nhom", "Xem bảng tin của nhóm",
        "/api/board/list.",
        "group", "/api/board/list", None, "GET", "group", [],
        _b_board_list),
    # --- Hội thoại / trạng thái (nhóm D) ---
    "get_unread_mark": _op(
        54, "get_unread_mark", "hoi_thoai", "Xem hội thoại chưa đọc",
        "/api/conv/getUnreadMark (12011).",
        "convers", "/api/conv/getUnreadMark", 12011, "GET", "none",
        [], lambda p, t, tt: {"imei": p["_imei"]}),
    "add_unread_mark": _op(
        55, "add_unread_mark", "hoi_thoai",
        "Đánh dấu hội thoại chưa đọc",
        "/api/conv/addUnreadMark (12013).",
        "convers", "/api/conv/addUnreadMark", 12013, "POST", "both",
        [], lambda p, t, tt: _b_unread(p, t, tt, "add_unread_mark")),
    "remove_unread_mark": _op(
        56, "remove_unread_mark", "hoi_thoai",
        "Bỏ đánh dấu chưa đọc",
        "/api/conv/removeUnreadMark (12014).",
        "convers", "/api/conv/removeUnreadMark", 12014, "POST",
        "both", [],
        lambda p, t, tt: _b_unread(p, t, tt, "remove_unread_mark")),
    "delete_chat": _op(
        57, "delete_chat", "hoi_thoai", "Xóa hội thoại",
        "1-1: /api/message/deleteconver (11778); nhóm: "
        "/api/group/deleteconver (11835).",
        None, None, None, "POST", "both", [], _b_delete_chat,
        danger=True),
    "get_auto_delete_chat": _op(
        59, "get_auto_delete_chat", "hoi_thoai",
        "Xem hội thoại đang tự xóa",
        "/api/conv/autodelete/getConvers (12022).",
        "convers", "/api/conv/autodelete/getConvers", 12022, "GET",
        "none", [], lambda p, t, tt: {"imei": p["_imei"]}),
    "update_auto_delete_chat": _op(
        60, "update_auto_delete_chat", "hoi_thoai",
        "Bật/tắt tự xóa tin nhắn",
        "/api/conv/autodelete/updateConvers (12023).",
        "convers", "/api/conv/autodelete/updateConvers", 12023,
        "POST", "both",
        [{"key": "ttl", "label": "TTL (0=tắt, 86400000=1 ngày, "
          "604800000=7 ngày)", "required": True}],
        _b_auto_delete),
    "get_mute": _op(
        65, "get_mute", "hoi_thoai", "Xem danh sách tắt thông báo",
        "/api/social/profile/getmute (mức tài khoản; chưa rõ có "
        "mức từng thread không).",
        "profile", "/api/social/profile/getmute", None, "GET", "none",
        [], lambda p, t, tt: {"imei": p["_imei"]}),
    "set_mute": _op(
        52, "set_mute", "hoi_thoai", "Tắt thông báo",
        "/api/social/profile/setmute (mức tài khoản; chưa rõ có "
        "mức từng thread không).",
        "profile", "/api/social/profile/setmute", None, "POST", "both",
        [{"key": "duration", "label": "Thời lượng giây "
          "(3600/14400/-1=vĩnh viễn/0=bật lại)", "required": True}],
        _b_mute),
    # --- Hồ sơ / người dùng (nhóm B + G) ---
    "find_user": _op(
        6, "find_user", "ho_so", "Tìm người dùng theo SĐT",
        "/api/social/friend/phonebook/v2 (body chưa lần hết).",
        "profile", "/api/social/friend/phonebook/v2", None, "GET",
        "none",
        [{"key": "phone", "label": "Số điện thoại", "required": True}],
        _b_find_user),
    "get_user_info": _op(
        7, "get_user_info", "ho_so", "Xem thông tin người dùng",
        "/api/social/friend/getprofiles/v2.",
        "profile", "/api/social/friend/getprofiles/v2", None, "GET",
        "none",
        [{"key": "user_id", "label": "UserId", "required": True}],
        _b_user_info),
    "last_online": _op(
        94, "last_online", "ho_so", "Xem hoạt động cuối",
        "/api/social/profile/lastOnline.",
        "profile", "/api/social/profile/lastOnline", None, "GET",
        "none",
        [{"key": "user_id", "label": "UserId", "required": True}],
        _b_last_online),
    "update_profile": _op(
        50, "update_profile", "ho_so", "Cập nhật thông tin cá nhân",
        "/api/social/profile/update.",
        "profile", "/api/social/profile/update", None, "POST", "none",
        [{"key": "name", "label": "Tên hiển thị"},
         {"key": "dob", "label": "Ngày sinh (yyyy-mm-dd)"},
         {"key": "gender", "label": "Giới tính (0=Nam, 1=Nữ)"}],
        _b_update_profile),
    "update_settings": _op(
        51, "update_settings", "ho_so", "Cập nhật cài đặt riêng tư",
        "/api/setting/update.",
        "profile", "/api/setting/update", None, "POST", "none",
        [{"key": "setting_type",
          "label": "Loại (online_status/seen_status/receive_message/"
          "phone_search)", "required": True},
         {"key": "status", "label": "Trạng thái (1=bật, 0=tắt)",
          "required": True}],
        _b_update_settings),
    "change_account_avatar": _op(
        92, "change_account_avatar", "ho_so", "Đổi ảnh đại diện",
        "/api/social/profile/avatar-url (nhận URL ảnh).",
        "profile", "/api/social/profile/avatar-url", None, "POST",
        "none",
        [{"key": "avatar_url", "label": "URL ảnh", "required": True}],
        _b_change_avatar),
    "get_avatar_list": _op(
        93, "get_avatar_list", "ho_so", "Xem ảnh đại diện đã dùng",
        "/api/social/avatar-list.",
        "profile", "/api/social/avatar-list", None, "GET", "none",
        [{"key": "count", "label": "Số lượng"},
         {"key": "page", "label": "Trang"}],
        _b_avatar_list),
    # --- Sticker (nhóm H) ---
    "send_sticker": _op(
        27, "send_sticker", "sticker", "Gửi sticker",
        "1-1: /api/message/sticker (11154) {stickerId, cateId, "
        "type, clientId, imei, toid}; nhóm: /api/group/sticker "
        "(11165). Body đã biết.",
        None, None, None, "POST", "both",
        [{"key": "sticker_id", "label": "Sticker ID",
          "required": True},
         {"key": "cate_id", "label": "Cate ID"},
         {"key": "sticker_type", "label": "Type"}],
        _b_sticker, body_unverified=False),
    "get_stickers": _op(
        73, "get_stickers", "sticker", "Xem danh mục sticker",
        "/api/message/sticker/category/list (+ /v2).",
        "chat", "/api/message/sticker/category/list", None, "GET",
        "none", [], _b_sticker_list),
    "get_stickers_detail": _op(
        74, "get_stickers_detail", "sticker", "Xem chi tiết bộ sticker",
        "/api/message/sticker/category/list theo cateId.",
        "chat", "/api/message/sticker/category/list", None, "GET",
        "none",
        [{"key": "sticker_album", "label": "Album/Cate ID",
          "required": True}],
        _b_sticker_detail),
    # --- Nhắc hẹn / bảng tin (nhóm F) ---
    "create_reminder": _op(
        29, "create_reminder", "nhac", "Tạo nhắc hẹn",
        "1-1: /api/board/oneone/create. Nhóm: chưa có endpoint "
        "trong bảng lệnh — không bịa path.",
        None, None, None, "POST", "both",
        [{"key": "title", "label": "Tiêu đề", "required": True},
         {"key": "content", "label": "Nội dung"},
         {"key": "remind_time", "label": "Thời gian nhắc",
          "required": True}],
        _b_reminder_create),
    "remove_reminder": _op(
        30, "remove_reminder", "nhac", "Xóa nhắc hẹn",
        "1-1: /api/board/oneone/remove. Nhóm: chưa có endpoint.",
        None, None, None, "POST", "both",
        [{"key": "reminder_id", "label": "ID nhắc hẹn",
          "required": True}],
        _b_reminder_remove),
    "edit_reminder": _op(
        82, "edit_reminder", "nhac", "Sửa nhắc hẹn",
        "1-1: /api/board/oneone/update; nhóm: "
        "/api/board/topic/updateEventResponse.",
        None, None, None, "POST", "both",
        [{"key": "topic_id", "label": "ID nhắc hẹn",
          "required": True},
         {"key": "title", "label": "Tiêu đề mới", "required": True}],
        _b_reminder_edit),
    "get_reminder": _op(
        83, "get_reminder", "nhac", "Xem chi tiết nhắc hẹn",
        "/api/board/topic/getReminder.",
        "group", "/api/board/topic/getReminder", None, "GET", "group",
        [{"key": "reminder_id", "label": "ID nhắc hẹn",
          "required": True}],
        _b_reminder_get),
    "get_list_reminder": _op(
        84, "get_list_reminder", "nhac", "Xem danh sách nhắc hẹn",
        "1-1: /api/board/oneone/list; nhóm: "
        "/api/board/listReminder.",
        None, None, None, "GET", "both", [], _b_reminder_list),
    "get_reminder_responses": _op(
        85, "get_reminder_responses", "nhac", "Xem phản hồi nhắc hẹn",
        "/api/board/topic/listResponseEvent.",
        "group", "/api/board/topic/listResponseEvent", None, "GET",
        "group",
        [{"key": "reminder_id", "label": "ID nhắc hẹn",
          "required": True}],
        _b_reminder_responses),
    # --- Nhãn (nhóm I) ---
    "get_labels": _op(
        90, "get_labels", "nhan", "Xem danh sách nhãn",
        "/api/convlabel/get.",
        "convers", "/api/convlabel/get", None, "GET", "none", [],
        _b_labels),
    "update_label": _op(
        None, "(gắn nhãn — ngoài 96)", "nhan", "Gắn nhãn cho hội thoại",
        "/api/convlabel/update (12160).",
        "convers", "/api/convlabel/update", 12160, "POST", "both",
        [{"key": "label_ids", "label": "ID nhãn (cách nhau bằng dấu "
          "phẩy)", "required": True}],
        _b_label_update),
}

# Đường dây 1-1/nhóm cho các op có 2 endpoint (path/code khác nhau
# theo thread). Key: action -> (domain_1_1, path_1_1, code_1_1,
#                                 domain_nhom, path_nhom, code_nhom)
_SPLIT = {
    "undo_message": ("chat", "/api/message/undo", 11281,
                     "group", "/api/group/undomsg", 11192),
    "delete_message": ("chat", "/api/message/delete", 11779,
                       "group", "/api/group/deletemsg", 11834),
    "forward_message": ("chat", "/api/message/forward", 11199,
                        "group", "/api/group/forward", 11818),
    "quote_message": ("chat", "/api/message/quote", 11771,
                      "group", "/api/group/quote", 11197),
    "mark_seen": ("chat", "/api/message/seen", 11150,
                  "group", "/api/group/seen", 11167),
    "send_typing_event": ("chat", "/api/message/typing", 11144,
                          "group", "/api/group/typing", 11196),
    "send_sticker": ("chat", "/api/message/sticker", 11154,
                     "group", "/api/group/sticker", 11165),
    "delete_chat": ("chat", "/api/message/deleteconver", 11778,
                    "group", "/api/group/deleteconver", 11835),
    "create_reminder": ("chat", "/api/board/oneone/create", None,
                        "group", None, None),
    "remove_reminder": ("chat", "/api/board/oneone/remove", None,
                        "group", None, None),
    "edit_reminder": ("chat", "/api/board/oneone/update", None,
                      "group", "/api/board/topic/updateEventResponse",
                      None),
    "get_list_reminder": ("chat", "/api/board/oneone/list", None,
                          "group", "/api/board/listReminder", None),
}

_DOMAINS = {
    "chat": lambda: protocol.CHAT_DOMAIN,
    "group": lambda: protocol.GROUP_DOMAIN,
    "profile": lambda: protocol.PROFILE_DOMAIN,
    "convers": lambda: protocol.CONVERS_DOMAIN,
}


def _resolve(action, spec, ttype):
    """(domain, path, code) cho action + kiểu thread."""
    if action in _SPLIT:
        d1, p1, c1, d2, p2, c2 = _SPLIT[action]
        if ttype == "group":
            if p2 is None:
                return None, None, None
            return d2, p2, c2
        return d1, p1, c1
    return spec["domain"], spec["path"], spec["code"]


# ---------------------------------------------------------------- catalog
# Các service KHÔNG thao tác được: status + lý do ngắn, không nút bấm.
#  "chat"    — có đường PC nhưng thuộc khung chat (agent chat làm).
#  "zalobot" — chỉ thuộc máy chủ zalobot, phiên web (không phải app PC).
#  "view"    — đã xem được trên UI danh bạ hôm nay.
#  "unsupported" — chưa có đường PC trong bảng lệnh 231 mục.

_NOT_SUPPORTED = [
    # (addon_no, addon, group, status, reason)
    (1, "send_message", "tin_nhan", "chat",
     "Gửi text thuộc khung chat — agent chat làm (đường PC: "
     "1-1 /api/message/sms 11151, nhóm /api/group/sendmsg 11163)."),
    (2, "send_file", "tin_nhan", "chat",
     "Đính kèm file thuộc khung chat (1-1 sharefile_full 11146, "
     "nhóm 11191)."),
    (3, "send_image", "tin_nhan", "chat",
     "Gửi ảnh thuộc khung chat (upload 12651/12652 rồi send "
     "11152/11164)."),
    (13, "send_image_to_user", "tin_nhan", "chat",
     "Gửi ảnh thuộc khung chat (như send_image, đích 1-1)."),
    (14, "send_images_to_user", "tin_nhan", "chat",
     "Gửi nhiều ảnh thuộc khung chat (như send_image, đích 1-1)."),
    (15, "send_image_to_group", "tin_nhan", "chat",
     "Gửi ảnh thuộc khung chat (như send_image, đích nhóm)."),
    (16, "send_images_to_group", "tin_nhan", "chat",
     "Gửi nhiều ảnh thuộc khung chat (như send_image, đích nhóm)."),
    (33, "send_voice", "tin_nhan", "chat",
     "Gửi tin nhắn thoại thuộc khung chat (voicemp3 11148 / "
     "sendmp3 11169) — không phải gọi điện."),
    (71, "send_card", "tin_nhan", "chat",
     "Gửi danh thiếp thuộc khung chat (1-1 contact 11774, nhóm "
     "11827; body chưa lần hết)."),
    (72, "send_link", "tin_nhan", "chat",
     "Gửi link thuộc khung chat (1-1 link 11286, nhóm sendlink "
     "11193; body chưa lần hết)."),
    (75, "send_video", "tin_nhan", "chat",
     "Gửi video thuộc khung chat (upload 12058/12061 + thumb; "
     "bước send chưa lần hết)."),
    (4, "get_logged_accounts", "khac", "zalobot",
     "Đa tài khoản chỉ có trên máy chủ zalobot (phiên web). "
     "App PC đơn tài khoản — tài khoản hiện tại xem ở /api/status."),
    (5, "get_account_details", "khac", "zalobot",
     "Chi tiết tài khoản theo account_selection — chỉ có trên "
     "máy chủ zalobot (phiên web)."),
    (17, "get_account_webhooks", "khac", "zalobot",
     "Webhook thuộc máy chủ zalobot (phiên web). Trang cài đặt "
     "webhook do agent riêng làm — không làm lại ở đây."),
    (18, "get_account_webhook", "khac", "zalobot",
     "Webhook thuộc máy chủ zalobot (phiên web)."),
    (19, "set_account_webhook", "khac", "zalobot",
     "Webhook thuộc máy chủ zalobot (phiên web)."),
    (20, "delete_account_webhook", "khac", "zalobot",
     "Webhook thuộc máy chủ zalobot (phiên web)."),
    (21, "get_proxies", "khac", "zalobot",
     "Proxy chỉ có trên máy chủ zalobot (docker cũ); app PC "
     "không có proxy."),
    (22, "add_proxy", "khac", "zalobot",
     "Proxy chỉ có trên máy chủ zalobot; app PC không có proxy."),
    (23, "remove_proxy", "khac", "zalobot",
     "Proxy chỉ có trên máy chủ zalobot; app PC không có proxy."),
    (96, "get_login_qr", "khac", "zalobot",
     "QR này là QR kiểu WEB của máy chủ zalobot — khác loại với "
     "QR kiểu PC app đang dùng (đăng nhập QR PC đã có sẵn)."),
    (34, "get_all_friends", "ho_so", "view",
     "Đã xem được: danh bạ Bạn bè (60 bạn, đúng thật)."),
    (40, "get_all_groups", "ho_so", "view",
     "Đã xem được: danh bạ Nhóm (6 nhóm, đúng thật)."),
    (8, "send_friend_request", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint kết bạn trong bảng "
     "lệnh 231 mục — cần lần thêm, không bịa endpoint."),
    (24, "accept_friend_request", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint chấp nhận kết bạn "
     "trong bảng lệnh."),
    (25, "block_user", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint chặn người dùng "
     "trong bảng lệnh."),
    (26, "unblock_user", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint bỏ chặn trong bảng "
     "lệnh."),
    (35, "get_sent_friend_requests", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint liệt kê lời mời đã "
     "gửi trong bảng lệnh."),
    (36, "undo_friend_request", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint thu hồi lời mời "
     "trong bảng lệnh."),
    (37, "remove_friend", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint hủy kết bạn trong "
     "bảng lệnh."),
    (38, "change_friend_alias", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint đổi biệt danh trong "
     "bảng lệnh."),
    (39, "remove_friend_alias", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint xóa biệt danh trong "
     "bảng lệnh."),
    (91, "block_view_feed", "ho_so", "unsupported",
     "Chưa có đường PC: không thấy endpoint chặn xem nhật ký "
     "trong bảng lệnh."),
    (53, "set_pinned_conversation", "hoi_thoai", "unsupported",
     "Chưa có đường PC: không thấy endpoint ghim/bỏ ghim hội "
     "thoại trong bảng lệnh 231 mục."),
    (58, "get_archived_chat_list", "hoi_thoai", "unsupported",
     "Chưa có đường PC: không thấy endpoint lưu trữ hội thoại "
     "trong bảng lệnh."),
    (61, "get_hidden_conversations", "hoi_thoai", "unsupported",
     "Chưa có đường PC: không thấy endpoint hội thoại ẩn trong "
     "bảng lệnh."),
    (62, "set_hidden_conversations", "hoi_thoai", "unsupported",
     "Chưa có đường PC: không thấy endpoint ẩn/bỏ ẩn hội thoại "
     "trong bảng lệnh."),
    (63, "update_hidden_convers_pin", "hoi_thoai", "unsupported",
     "Chưa có đường PC: không thấy endpoint đặt PIN hội thoại "
     "ẩn trong bảng lệnh."),
    (64, "reset_hidden_convers_pin", "hoi_thoai", "unsupported",
     "Chưa có đường PC: không thấy endpoint gỡ PIN hội thoại "
     "ẩn trong bảng lệnh."),
    (66, "get_pin_conversations", "hoi_thoai", "unsupported",
     "Chưa có đường PC: không thấy endpoint liệt kê hội thoại "
     "đã ghim trong bảng lệnh."),
    (67, "add_reaction", "tin_nhan", "unsupported",
     "Chưa có đường PC: bảng lệnh chỉ có /api/react/gLastSn "
     "(lấy reaction gần nhất), không có endpoint GỬI reaction."),
    (79, "create_poll", "nhom", "unsupported",
     "Chưa có đường PC: bundle có /api/board/... cho topic, "
     "không thấy endpoint poll riêng trong bảng lệnh."),
    (80, "get_poll_detail", "nhom", "unsupported",
     "Chưa có đường PC: không thấy endpoint chi tiết poll "
     "trong bảng lệnh."),
    (81, "lock_poll", "nhom", "unsupported",
     "Chưa có đường PC: không thấy endpoint khóa poll trong "
     "bảng lệnh."),
    (86, "add_quick_message", "nhac", "unsupported",
     "Chưa có đường PC: không thấy endpoint tin nhắn nhanh "
     "trong bảng lệnh 231 mục."),
    (87, "get_quick_message", "nhac", "unsupported",
     "Chưa có đường PC: không thấy endpoint tin nhắn nhanh "
     "trong bảng lệnh."),
    (88, "remove_quick_message", "nhac", "unsupported",
     "Chưa có đường PC: không thấy endpoint tin nhắn nhanh "
     "trong bảng lệnh."),
    (89, "update_quick_message", "nhac", "unsupported",
     "Chưa có đường PC: không thấy endpoint tin nhắn nhanh "
     "trong bảng lệnh."),
]


# ------------------------------------------------------------------ addon
# PIVOT 2026-11-05 (addon-embedded): /api/svc/* di qua sidecar zalobot
# (zca-js) khi AppState co addon client; khong co client thi giu nguyen
# duong PC cu (Services.dispatch). Bang nay dich tham so UI (snake_case,
# theo catalog fields) sang body sidecar (camelCase, API-MAP §4.8) —
# SAO CHEP builder cua HA integration (chat/group/user/misc/reminder/
# quickmsg/sticker_features.py), khong tu suy dien shape. Quy tac:
#  * `type` gui dang SO (0/1) — API-MAP §4.1/§11: so dung duoc o moi
#    handler; chuoi "group" bi sendMessageByAccount truyen tho.
#  * Chi nhung op dich duoc TRUNG THUC moi co mat o day. Op nao body
#    sidecar mo ho tu code (API-MAP §12 muc 1: update_label, forward
#    (params), delete_chat (lastMessage), get_group_link (can link
#    that, UI khong co)) GIU NGUYEN duong PC — khong doan.
#  * 11 op khung chat (send_message/send_file/send_image/.../send_
#    video) KHONG co o day: chung di qua khung chat (server thread
#    routes), catalog giu status "chat".
#  * 4 muc zalobot khong co route API (get_proxies/add_proxy/
#    remove_proxy — chi co UI route /proxies; get_login_qr — QR qua
#    POST /zalo-login, API-MAP §8/§12 muc 3-4) KHONG co o day va giu
#    status "zalobot" trong catalog.
#
# Spec: route = hau to route sidecar (bo "ByAccount", client.svc them
# lai); thread: "both" -> threadId+type, "group" -> groupId,
# "user" -> threadId+type, "none" -> khong thread; map: {field sidecar:
# ui_key | ("csv", ui_key) | ("bool", ui_key) | ("int", ui_key)};
# options: {field trong options: spec} (long vao "options");
# special: builder rieng (dest/payload) — xem _addon_special_body.

def _aop(route, thread, mapping=None, options=None, fields=None,
         special=None):
    return {"route": route, "thread": thread, "map": mapping or {},
            "options": options or {}, "fields": fields or [],
            "special": special}


_F_USER_ID = [{"key": "user_id", "label": "UserId", "required": True}]
_F_MSG_ID = [{"key": "msg_id", "label": "ID tin nhắn", "required": True}]
_F_MEMBER_ID = [{"key": "member_id", "label": "UserId",
                 "required": True}]

ADDON_OPS = {
    # --- 25 op "khong co duong PC" — nay chay qua sidecar ---
    "send_friend_request": _aop(
        "sendFriendRequest", "none",
        {"userId": "user_id", "message": "message"},
        fields=_F_USER_ID + [{"key": "message", "label": "Lời nhắn"}]),
    "accept_friend_request": _aop(
        "acceptFriendRequest", "none", {"userId": "user_id"},
        fields=_F_USER_ID),
    "block_user": _aop("blockUser", "none", {"userId": "user_id"},
                       fields=_F_USER_ID),
    "unblock_user": _aop("unblockUser", "none", {"userId": "user_id"},
                         fields=_F_USER_ID),
    "block_view_feed": _aop(
        "blockViewFeed", "none",
        {"isBlockFeed": ("bool", "is_block_feed"), "userId": "user_id"},
        fields=_F_USER_ID + [{"key": "is_block_feed",
                              "label": "Chặn xem nhật ký (true/false)",
                              "required": True}]),
    "change_friend_alias": _aop(
        "changeFriendAlias", "none",
        {"alias": "alias", "friendId": "friend_id"},
        fields=[{"key": "friend_id", "label": "UserId",
                 "required": True},
                {"key": "alias", "label": "Biệt danh",
                 "required": True}]),
    "remove_friend_alias": _aop(
        "removeFriendAlias", "none", {"friendId": "friend_id"},
        fields=[{"key": "friend_id", "label": "UserId",
                 "required": True}]),
    "remove_friend": _aop(
        "removeFriend", "none", {"friendId": "friend_id"},
        fields=[{"key": "friend_id", "label": "UserId",
                 "required": True}]),
    "undo_friend_request": _aop(
        "undoFriendRequest", "none", {"friendId": "friend_id"},
        fields=[{"key": "friend_id", "label": "UserId",
                 "required": True}]),
    "get_sent_friend_requests": _aop("getSentFriendRequest", "none"),
    "get_alias_list": _aop(
        "getAliasList", "none",
        {"count": ("int", "count"), "page": ("int", "page")},
        fields=[{"key": "count", "label": "Số lượng"},
                {"key": "page", "label": "Trang"}]),
    "get_friend_recommendations": _aop(
        "getFriendRecommendations", "none"),
    "set_pinned_conversation": _aop(
        "setPinnedConversations", "both",
        {"pinned": ("bool", "pinned")},
        fields=[{"key": "pinned", "label": "Ghim (true/false)",
                 "required": True}]),
    "get_archived_chat_list": _aop("getArchivedChatList", "none"),
    "get_hidden_conversations": _aop("getHiddenConversations", "none"),
    "set_hidden_conversations": _aop(
        "setHiddenConversations", "both",
        {"hidden": ("bool", "hidden")},
        fields=[{"key": "hidden", "label": "Ẩn (true/false)",
                 "required": True}]),
    "update_hidden_convers_pin": _aop(
        "updateHiddenConversPin", "none", {"pin": "pin"},
        fields=[{"key": "pin", "label": "PIN", "required": True}]),
    "reset_hidden_convers_pin": _aop("resetHiddenConversPin", "none"),
    "get_pin_conversations": _aop("getPinConversations", "none"),
    "add_reaction": _aop(
        "addReaction", "both", special="reaction",
        fields=_F_MSG_ID + [
            {"key": "cli_msg_id", "label": "Client ID tin nhắn"},
            {"key": "icon", "label": "Icon (vd. like/heart)",
             "required": True}]),
    "create_poll": _aop(
        "createPoll", "group",
        options={"question": "question",
                 "options": ("csv", "options"),
                 "allowMultiChoices": ("bool", "allow_multi_choices")},
        fields=[{"key": "question", "label": "Câu hỏi",
                 "required": True},
                {"key": "options",
                 "label": "Lựa chọn (cách nhau bằng dấu phẩy)",
                 "required": True},
                {"key": "allow_multi_choices",
                 "label": "Cho chọn nhiều (true/false)"}]),
    "get_poll_detail": _aop(
        "getPollDetail", "none", {"pollId": "poll_id"},
        fields=[{"key": "poll_id", "label": "ID bình chọn",
                 "required": True}]),
    "lock_poll": _aop(
        "lockPoll", "none", {"pollId": "poll_id"},
        fields=[{"key": "poll_id", "label": "ID bình chọn",
                 "required": True}]),
    "add_quick_message": _aop(
        "addQuickMessage", "none", special="quick_add",
        fields=[{"key": "keyword", "label": "Từ khóa",
                 "required": True},
                {"key": "title", "label": "Tiêu đề",
                 "required": True}]),
    "get_quick_message": _aop("getQuickMessageList", "none"),
    "remove_quick_message": _aop(
        "removeQuickMessage", "none",
        {"itemIds": ("csv_int", "item_ids")},
        fields=[{"key": "item_ids",
                 "label": "ID tin nhắn nhanh (cách nhau bằng dấu phẩy)",
                 "required": True}]),
    "update_quick_message": _aop(
        "updateQuickMessage", "none", special="quick_update",
        fields=[{"key": "item_id", "label": "ID tin nhắn nhanh",
                 "required": True},
                {"key": "keyword", "label": "Từ khóa",
                 "required": True},
                {"key": "title", "label": "Tiêu đề",
                 "required": True}]),
    # --- 6 muc zalobot-web co route API (accounts + webhooks) ---
    "get_logged_accounts": _aop(None, "none", special="accounts"),
    "get_account_details": _aop(None, "none", special="account"),
    "get_account_webhooks": _aop(None, "none",
                                 special="webhooks_all"),
    "get_account_webhook": _aop(
        None, "none", special="webhook_one",
        fields=[{"key": "own_id", "label": "OwnId (để trống = tài "
                 "khoản hiện tại)"}]),
    "set_account_webhook": _aop(
        None, "none", special="webhook_set",
        fields=[{"key": "own_id", "label": "OwnId (để trống = tài "
                 "khoản hiện tại)"},
                {"key": "message_webhook_url",
                 "label": "URL webhook tin nhắn"},
                {"key": "group_event_webhook_url",
                 "label": "URL webhook sự kiện nhóm"},
                {"key": "reaction_webhook_url",
                 "label": "URL webhook reaction"}]),
    "delete_account_webhook": _aop(
        None, "none", special="webhook_delete",
        fields=[{"key": "own_id", "label": "OwnId (để trống = tài "
                 "khoản hiện tại)"}]),
    # --- Op PC cu, dich thang qua sidecar khi co client ---
    "undo_message": _aop("undo", "both", special="undo",
                         fields=F_MSG_CLI),
    "delete_message": _aop(
        "deleteMessage", "both", special="delete",
        fields=F_MSG_CLI + [{"key": "uid_from",
                             "label": "UID người gửi"}]),
    "mark_seen": _aop("sendSeenEvent", "both", special="seen",
                      fields=[{"key": "msg_ids",
                               "label": "ID tin nhắn (cách nhau bằng "
                               "dấu phẩy)", "required": True}]),
    "parse_link": _aop(
        "parseLink", "none", {"link": "link"},
        fields=[{"key": "link", "label": "Link", "required": True}]),
    "send_typing_event": _aop("sendTypingEvent", "both",
                              special="typing"),
    "send_sticker": _aop(
        "sendSticker", "both", special="sticker",
        fields=[{"key": "sticker_id", "label": "Sticker ID",
                 "required": True},
                {"key": "cate_id", "label": "Cate ID"},
                {"key": "sticker_type", "label": "Type"}]),
    "get_group_chat_history": _aop(
        "getGroupChatHistory", "group", special="group_history",
        fields=[{"key": "count", "label": "Số tin (tối đa 1000)"}]),
    "create_group": _aop(
        "createGroup", "none",
        {"members": ("csv", "member_ids"), "name": "name",
         "avatarPath": "avatar_path"},
        fields=[{"key": "name", "label": "Tên nhóm",
                 "required": True},
                {"key": "member_ids",
                 "label": "Thành viên (userId, cách nhau bằng dấu "
                 "phẩy)"}]),
    "get_group_info": _aop("getGroupInfo", "group",
                           special="group_info"),
    "add_user_to_group": _aop(
        "addUserToGroup", "group",
        {"memberId": ("csv", "member_id")},
        fields=[{"key": "member_id",
                 "label": "UserId (cách nhau bằng dấu phẩy)",
                 "required": True}]),
    "remove_user_from_group": _aop(
        "removeUserFromGroup", "group",
        {"memberId": ("csv", "member_id")},
        fields=[{"key": "member_id",
                 "label": "UserId (cách nhau bằng dấu phẩy)",
                 "required": True}]),
    "change_group_name": _aop(
        "changeGroupName", "group", {"name": "name"},
        fields=[{"key": "name", "label": "Tên mới",
                 "required": True}]),
    "change_group_avatar": _aop(
        "changeGroupAvatar", "group", {"avatarSource": "avatar_url"},
        fields=[{"key": "avatar_url", "label": "URL ảnh đại diện",
                 "required": True}]),
    "add_group_deputy": _aop(
        "addGroupDeputy", "group", {"memberId": "member_id"},
        fields=_F_MEMBER_ID),
    "remove_group_deputy": _aop(
        "removeGroupDeputy", "group", {"memberId": "member_id"},
        fields=_F_MEMBER_ID),
    "change_group_owner": _aop(
        "changeGroupOwner", "group", {"memberId": "member_id"},
        fields=[{"key": "member_id", "label": "UserId chủ mới",
                 "required": True}]),
    "disperse_group": _aop("disperseGroup", "group"),
    "enable_group_link": _aop("enableGroupLink", "group"),
    "disable_group_link": _aop("disableGroupLink", "group"),
    "join_group": _aop(
        "joinGroup", "none", {"link": "link"},
        fields=[{"key": "link", "label": "Link mời",
                 "required": True}]),
    "leave_group": _aop("leaveGroup", "group"),
    "create_note_group": _aop(
        "createNote", "group",
        options={"title": "title", "pinAct": ("bool", "pin_act")},
        fields=[{"key": "title", "label": "Tiêu đề ghi chú",
                 "required": True}]),
    "edit_note_group": _aop(
        "editNote", "group",
        options={"topicId": "topic_id", "title": "title"},
        fields=[{"key": "topic_id", "label": "ID ghi chú",
                 "required": True},
                {"key": "title", "label": "Tiêu đề mới",
                 "required": True}]),
    "get_list_board": _aop("getListBoard", "group"),
    "get_unread_mark": _aop("getUnreadMark", "none"),
    "add_unread_mark": _aop("addUnreadMark", "both"),
    "remove_unread_mark": _aop("removeUnreadMark", "both"),
    "get_auto_delete_chat": _aop("getAutoDeleteChat", "none"),
    "update_auto_delete_chat": _aop(
        "updateAutoDeleteChat", "both", {"ttl": "ttl"},
        fields=[{"key": "ttl",
                 "label": "TTL (0=tắt, 86400000=1 ngày, "
                 "604800000=7 ngày)", "required": True}]),
    "get_mute": _aop("getMute", "none"),
    "set_mute": _aop("setMute", "both", special="mute",
                     fields=[{"key": "duration",
                              "label": "Thời lượng giây (3600/14400/"
                              "-1=vĩnh viễn/0=bật lại)",
                              "required": True}]),
    "find_user": _aop(
        "findUser", "none", {"phone": "phone"},
        fields=[{"key": "phone", "label": "Số điện thoại",
                 "required": True}]),
    "get_user_info": _aop(
        "getUserInfo", "none", {"userId": "user_id"},
        fields=[{"key": "user_id", "label": "UserId",
                 "required": True}]),
    "last_online": _aop(
        "lastOnline", "none", {"uid": "user_id"},
        fields=[{"key": "user_id", "label": "UserId",
                 "required": True}]),
    "update_profile": _aop(
        "updateProfile", "none",
        {"name": "name", "dob": "dob", "gender": "gender"},
        fields=[{"key": "name", "label": "Tên hiển thị"},
                {"key": "dob", "label": "Ngày sinh (yyyy-mm-dd)"},
                {"key": "gender", "label": "Giới tính (0=Nam, 1=Nữ)"}]),
    "update_settings": _aop(
        "updateSettings", "none",
        {"type": "setting_type", "status": ("int", "status")},
        fields=[{"key": "setting_type",
                 "label": "Loại (online_status/seen_status/"
                 "receive_message/phone_search)", "required": True},
                {"key": "status",
                 "label": "Trạng thái (1=bật, 0=tắt)",
                 "required": True}]),
    "change_account_avatar": _aop(
        "changeAccountAvatar", "none", {"avatarSource": "avatar_url"},
        fields=[{"key": "avatar_url", "label": "URL ảnh",
                 "required": True}]),
    "get_avatar_list": _aop(
        "getAvatarList", "none",
        {"count": ("int", "count"), "page": ("int", "page")},
        fields=[{"key": "count", "label": "Số lượng"},
                {"key": "page", "label": "Trang"}]),
    "get_stickers": _aop("getStickers", "none",
                         {"query": "query"}),
    "get_stickers_detail": _aop(
        "getStickersDetail", "none", {"stickerAlbum": "sticker_album"},
        fields=[{"key": "sticker_album", "label": "Album/Cate ID",
                 "required": True}]),
    "create_reminder": _aop(
        "createReminder", "both",
        options={"title": "title", "content": "content",
                 "remindTime": "remind_time"},
        fields=[{"key": "title", "label": "Tiêu đề",
                 "required": True},
                {"key": "content", "label": "Nội dung"},
                {"key": "remind_time", "label": "Thời gian nhắc",
                 "required": True}]),
    "remove_reminder": _aop(
        "removeReminder", "both", {"reminderId": "reminder_id"},
        fields=[{"key": "reminder_id", "label": "ID nhắc hẹn",
                 "required": True}]),
    "edit_reminder": _aop(
        "editReminder", "both",
        options={"topicId": "topic_id", "title": "title"},
        fields=[{"key": "topic_id", "label": "ID nhắc hẹn",
                 "required": True},
                {"key": "title", "label": "Tiêu đề mới",
                 "required": True}]),
    "get_reminder": _aop(
        "getReminder", "none", {"reminderId": "reminder_id"},
        fields=[{"key": "reminder_id", "label": "ID nhắc hẹn",
                 "required": True}]),
    "get_list_reminder": _aop("getListReminder", "both"),
    "get_reminder_responses": _aop(
        "getReminderResponses", "none", {"reminderId": "reminder_id"},
        fields=[{"key": "reminder_id", "label": "ID nhắc hẹn",
                 "required": True}]),
    "get_labels": _aop("getLabels", "none"),
}


def _addon_type_number(ttype):
    return 1 if ttype == "group" else 0


def _addon_map_value(spec, params, action):
    """Giai 1 spec trong ADDON_OPS map/options: "ui_key" lay thang,
    ("csv", k) tach chuoi phay, ("csv_int", k) tach + int, ("bool", k)
    ep boolean, ("int", k) ep int. Thieu tham so bat buoc -> ValueError
    (handle_svc doi thanh 400)."""
    if isinstance(spec, tuple):
        kind, key = spec
        raw = params.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        if kind == "csv":
            return _csv(raw)
        if kind == "csv_int":
            out = []
            for part in _csv(raw):
                try:
                    out.append(int(part))
                except ValueError:
                    out.append(part)
            return out
        if kind == "bool":
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in ("1", "true", "yes")
        if kind == "int":
            return int(raw)
        raise ValueError("%s: kieu map khong biet %r" % (action, kind))
    return params.get(spec)


def _addon_special_body(special, params, tid, ttype, action):
    """Body rieng cho nhung op co shape dac biet (sao chep builder
    HA — xem ghi chu o dau bang ADDON_OPS). Tra ve dict body (chua
    accountSelection — client.svc tu them)."""
    num = _addon_type_number(ttype)
    if special == "undo":
        # HA misc_features undo: payload {msgId, cliMsgId} — Zalo
        # can ca hai; khong co cli_msg_id thi dung lai msg_id.
        return {"payload": {
            "msgId": _need(params, "msg_id", action),
            "cliMsgId": params.get("cli_msg_id")
            or params.get("msg_id")},
            "threadId": tid, "type": num}
    if special == "delete":
        return {"dest": {
            "threadId": tid, "type": num,
            "data": {"msgId": _need(params, "msg_id", action),
                     "cliMsgId": params.get("cli_msg_id", ""),
                     "uidFrom": params.get("uid_from", "")}},
            "onlyMe": True}
    if special == "reaction":
        return {"icon": _need(params, "icon", action),
                "dest": {"threadId": tid, "type": num,
                         "data": {"msgId": _need(params, "msg_id",
                                                 action),
                                  "cliMsgId": params.get("cli_msg_id",
                                                         "")}}}
    if special == "seen":
        ids = _csv(_need(params, "msg_ids", action))
        return {"messages": [{"msgId": m} for m in ids],
                "type": num}
    if special == "typing":
        # Sidecar chi nhan threadId (API-MAP §4.6: luon User).
        return {"threadId": tid}
    if special == "sticker":
        return {"sticker": {
            "id": int(_need(params, "sticker_id", action)),
            "cateId": params.get("cate_id", ""),
            "type": params.get("type_")
            or params.get("sticker_type") or ""},
            "threadId": tid, "type": num}
    if special == "group_history":
        try:
            count = int(params.get("count") or 50)
        except ValueError:
            count = 50
        return {"groupId": tid, "count": max(1, min(count, 1000))}
    if special == "group_info":
        return {"groupId": [tid]}
    if special == "mute":
        # HA misc_features set_mute: params {action, duration} +
        # threadId + type. Sidecar handler doc lai {params,
        # threadID, type} (API-MAP §4.8 — chu D hoa) nen gui ca hai
        # khoa threadId/threadID de khong phu thuoc vao ten nao dung.
        duration = int(_need(params, "duration", action))
        return {"params": {"action": "mute" if duration > 0
                           else "unmute",
                           "duration": duration},
                "threadId": tid, "threadID": tid, "type": num}
    if special == "quick_add":
        title = _need(params, "title", action)
        return {"addPayload": {
            "keyword": _need(params, "keyword", action),
            "title": title,
            "message": {"title": title, "params": ""}}}
    if special == "quick_update":
        title = _need(params, "title", action)
        return {"itemId": _need(params, "item_id", action),
                "updatePayload": {
                    "keyword": _need(params, "keyword", action),
                    "title": title,
                    "message": {"title": title, "params": ""}}}
    raise ValueError("%s: special khong biet %r" % (action, special))


def dispatch_via_addon(client, action, params):
    """Chay mot op qua sidecar (client.svc). Tra data verbatim tu
    sidecar. Raises: UnknownAction, UnsupportedService, ValueError
    (thieu tham so), AddonUnreachable/AddonAuthError/AddonError
    (tu addon_client — handle_svc doi thanh 502)."""
    from . import addon_client as _ac
    spec = ADDON_OPS.get(action)
    if spec is None:
        raise UnknownAction("svc: khong co thao tac addon %s" % action)
    params = dict(params or {})
    special = spec["special"]
    if special in ("accounts", "account", "webhooks_all",
                   "webhook_one", "webhook_set", "webhook_delete"):
        own_id = (params.get("own_id") or params.get("ownId") or "")
        if special == "accounts":
            return client.accounts()
        if special == "account":
            return client.account_details(
                own_id or client.resolve_account())
        if special == "webhooks_all":
            return client.webhooks_get()
        if special == "webhook_one":
            return client.webhooks_get_account(
                own_id or client.resolve_account())
        if special == "webhook_set":
            urls = {}
            for key in ("messageWebhookUrl",
                        "groupEventWebhookUrl", "reactionWebhookUrl"):
                if params.get(key):
                    urls[key] = params[key]
                elif params.get(_WEBHOOK_UI_KEY.get(key, "")):
                    urls[key] = params[_WEBHOOK_UI_KEY[key]]
            return client.webhooks_set(
                own_id or client.resolve_account(), urls)
        return client.webhooks_delete(
            own_id or client.resolve_account())
    thread_needed = spec["thread"]
    if thread_needed == "none":
        tid, ttype = "", "user"
    else:
        tid, ttype = _thread(params, action)
        if thread_needed == "group" and ttype != "group":
            raise UnsupportedService(
                action, "unsupported",
                "Thao tac nay chi ap dung cho nhom — hay chon "
                "mot nhom.")
        if thread_needed == "user" and ttype != "user":
            raise UnsupportedService(
                action, "unsupported",
                "Thao tac nay chi ap dung cho hoi thoai 1-1.")
    if special is not None:
        body = _addon_special_body(special, params, tid, ttype, action)
    else:
        body = {}
        if thread_needed == "group":
            body["groupId"] = tid
        elif thread_needed != "none":
            body["threadId"] = tid
            body["type"] = _addon_type_number(ttype)
        for side_key, map_spec in spec["map"].items():
            value = _addon_map_value(map_spec, params, action)
            if value is not None:
                body[side_key] = value
        if spec["options"]:
            options = {}
            for opt_key, map_spec in spec["options"].items():
                value = _addon_map_value(map_spec, params, action)
                if value is not None:
                    options[opt_key] = value
            if options:
                body["options"] = options
    if spec["route"] is None:
        raise UnknownAction("svc: khong co route addon %s" % action)
    return client.svc(spec["route"], body)


# UI key -> sidecar webhook key (cho set_account_webhook).
_WEBHOOK_UI_KEY = {
    "messageWebhookUrl": "message_webhook_url",
    "groupEventWebhookUrl": "group_event_webhook_url",
    "reactionWebhookUrl": "reaction_webhook_url",
}


def build_catalog():
    """Toàn bộ 96 service addon + các op ngoài 96 (quote, seen,
    fetchImportant, link nhóm, gắn nhãn): mỗi entry có status để
    UI vẽ nút bấm hoặc trạng thái 'Chưa hỗ trợ' — không nút giả."""
    entries = []
    for action, spec in OPS.items():
        entries.append({
            "action": action,
            "addon": spec["addon"],
            "addon_no": spec["addon_no"],
            "group": spec["group"],
            "label": spec["label"],
            "desc": spec["desc"],
            "status": "supported",
            "fields": spec["fields"],
            "thread": spec["thread"],
            "danger": spec["danger"],
            "body_unverified": spec["body_unverified"],
            "pc": _pc_label(action, spec),
            "reason": "",
        })
    for no, addon, group, status, reason in _NOT_SUPPORTED:
        # PIVOT addon-embedded: op nao sidecar co route (ADDON_OPS)
        # thi bo co "Chua ho tro" — status "supported", action = ten
        # addon de /api/svc/<addon> goi duoc, fields lay tu bang
        # dich. 4 muc khong co route API (get_proxies/add_proxy/
        # remove_proxy/get_login_qr, API-MAP §12 muc 3-4) giu nguyen
        # status "zalobot". 11 op khung chat giu "chat".
        if addon in ADDON_OPS:
            spec = ADDON_OPS[addon]
            entries.append({
                "action": addon,
                "addon": addon,
                "addon_no": no,
                "group": group,
                "label": addon,
                "desc": "",
                "status": "supported",
                "fields": spec["fields"],
                "thread": spec["thread"],
                "danger": False,
                "body_unverified": False,
                "pc": None,
                "reason": "Chay qua sidecar addon (zca-js).",
            })
            continue
        entries.append({
            "action": None,
            "addon": addon,
            "addon_no": no,
            "group": group,
            "label": addon,
            "desc": "",
            "status": status,
            "fields": [],
            "thread": "both",
            "danger": False,
            "body_unverified": False,
            "pc": None,
            "reason": reason,
        })
    entries.sort(key=lambda e: (e["addon_no"] is None,
                                e["addon_no"] or 0))
    counts = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    counts["total_96"] = sum(
        1 for e in entries if e["addon_no"] is not None)
    return {"services": entries, "counts": counts,
            "groups": [{"id": g, "label": label}
                       for g, label in GROUPS]}


def _pc_label(action, spec):
    if action in _SPLIT:
        d1, p1, c1, d2, p2, c2 = _SPLIT[action]
        parts = []
        if p1:
            parts.append("1-1 %s%s" % (p1, " (%s)" % c1 if c1 else ""))
        if p2:
            parts.append("nhóm %s%s" % (p2, " (%s)" % c2 if c2 else ""))
        return "; ".join(parts) if parts else None
    if spec["path"]:
        return "%s%s" % (spec["path"],
                         " (%s)" % spec["code"] if spec["code"] else "")
    return None


CATALOG = build_catalog()


def catalog_public():
    return CATALOG


# ------------------------------------------------------------------ client
class Services:
    """Client gọi endpoint PC cho các op trong OPS (giống
    Signaling/Contacts: cùng transport, cùng envelope hai lớp).
    Không đụng signaling.py hay body requestcall."""

    def __init__(self, http_get, http_post, device_id, zpw_enk):
        self.http_get = http_get
        self.http_post = http_post
        self.device_id = device_id
        self.zpw_enk = zpw_enk

    def _aes(self, raw_json):
        return session_aes_encrypt(self.zpw_enk, raw_json)

    def _unwrap(self, status, payload, where):
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("svc %s: network status=%s"
                               % (where, status))
        if payload.get("error_code") != 0:
            raise RuntimeError("svc %s: error_code=%s %s" % (
                where, payload.get("error_code"),
                payload.get("error_message", "")))
        return decode_postlogin_data(payload, self.zpw_enk)

    def _url(self, domain, path, body):
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        enc = self._aes(raw)
        qs = urllib.parse.urlencode(protocol.common_params())
        return "%s%s?%s&params=%s" % (
            domain, path, qs, urllib.parse.quote(enc, safe=""))

    def _get(self, domain, path, body):
        url = self._url(domain, path, body)
        status, payload = self.http_get(url, timeout=30)
        return self._unwrap(status, payload, "GET %s" % path)

    def _post(self, domain, path, body):
        url = "%s%s?%s" % (domain, path, urllib.parse.urlencode(
            protocol.common_params()))
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        form = "params=" + urllib.parse.quote(self._aes(raw), safe="")
        if self.http_post is None:
            raise RuntimeError("svc: POST transport missing for %s"
                               % path)
        status, payload = self.http_post(url, form, timeout=30)
        return self._unwrap(status, payload, "POST %s" % path)

    def dispatch(self, action, params):
        """Chạy một op: trả về data đã giải mã từ envelope hai lớp.
        Raises: UnknownAction, UnsupportedService, ValueError
        (thiếu tham số), RuntimeError (lỗi mạng/server Zalo)."""
        spec = OPS.get(action)
        if spec is None:
            entry = next((e for e in CATALOG["services"]
                          if e["addon"] == action), None)
            if entry is not None:
                raise UnsupportedService(
                    action, entry["status"], entry["reason"])
            raise UnknownAction("svc: không có thao tác %s" % action)
        params = dict(params or {})
        params["_imei"] = self.device_id
        thread_needed = spec["thread"]
        if thread_needed == "none":
            tid, ttype = "", "user"
        else:
            tid, ttype = _thread(params, action)
            if thread_needed == "group" and ttype != "group":
                raise UnsupportedService(
                    action, "unsupported",
                    "Thao tác này chỉ áp dụng cho nhóm — hãy chọn "
                    "một nhóm.")
            if thread_needed == "user" and ttype != "user":
                raise UnsupportedService(
                    action, "unsupported",
                    "Thao tác này chỉ áp dụng cho hội thoại 1-1.")
        body = spec["body_fn"](params, tid, ttype)
        domain_key, path, _code = _resolve(action, spec, ttype)
        if path is None:
            raise UnsupportedService(
                action, "unsupported",
                "Thao tác này chưa có endpoint cho nhóm — cần lần "
                "thêm, không bịa path.")
        domain = _DOMAINS[domain_key]()
        if spec["method"] == "GET":
            return self._get(domain, path, body)
        return self._post(domain, path, body)


def handle_svc(state, action, body):
    """Móc duy nhất từ server.py do_POST /api/svc/<action>.
    `state` là AppState (đã qua _require_login ở server).
    Trả (http_status, json_obj).
    PIVOT addon-embedded: khi AppState co addon client va action co
    trong ADDON_OPS thi chay qua sidecar truoc; khong co client (hoac
    action khong dich duoc trung thuc — forward/quote/fetchImportant/
    get_group_link/delete_chat/update_label) thi giu nguyen duong PC
    cu. Sidecar chet -> 502 "addon_unavailable", khong bia du lieu."""
    from . import addon_client as _ac
    from . import server as _server_mod  # tránh import vòng lúc load
    client = None
    getter = getattr(state, "addon_client", None)
    if callable(getter):
        try:
            client = getter()
        except Exception:
            client = None
    if client is not None and action in ADDON_OPS:
        try:
            data = dispatch_via_addon(client, action, body or {})
        except UnknownAction as e:
            return 404, {"error": str(e)}
        except UnsupportedService as e:
            return 409, {"error": e.reason, "service": e.service,
                         "status": e.status}
        except ValueError as e:
            return 400, {"error": str(e)}
        except _ac.AddonUnreachable as e:
            return 502, {"error": "addon_unavailable: %s" % e}
        except _ac.AddonAuthError as e:
            return 502, {"error": "addon_unavailable: %s" % e}
        except _ac.AddonError as e:
            return 502, {"error": str(e)}
        except Exception as e:  # noqa: BLE001 - loi khac -> 502
            return 502, {"error": str(e)}
        return 200, {"ok": True, "action": action, "data": data}
    if client is None and action in ADDON_OPS and action not in OPS:
        # Op chi chay duoc qua sidecar, ma sidecar khong co (chua
        # cau hinh mat khau admin / chua chay): 502 chu khong phai
        # 409 — PC khong co duong nao cho op nay, nen khong duoc bao
        # "khong ho tro" nhu the op khong ton tai.
        return 502, {"error": "addon_unavailable: sidecar chua duoc "
                     "cau hinh hoac chua chay"}
    sess = state.session
    transport = _server_mod.make_transport(sess["zpw_sek"])
    svc = Services(transport, transport.http_post,
                   sess["device_id"], sess["zpw_enk"])
    try:
        data = svc.dispatch(action, body or {})
    except UnknownAction as e:
        return 404, {"error": str(e)}
    except UnsupportedService as e:
        return 409, {"error": e.reason, "service": e.service,
                     "status": e.status}
    except ValueError as e:
        return 400, {"error": str(e)}
    except Exception as e:  # noqa: BLE001 - lỗi Zalo/mạng -> 502
        return 502, {"error": str(e)}
    return 200, {"ok": True, "action": action, "data": data}
