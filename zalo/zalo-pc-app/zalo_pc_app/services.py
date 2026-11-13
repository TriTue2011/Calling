"""Phu service addon (96 services) len app Zalo kieu PC.

Nguon duy nhat cho endpoint PC: SERVICE-MAP.md (audit bundle
client PC that Zalo PC 26.11.10, 416 ma lenh) — thay the bao cao
doi chieu cu (bang lenh 231 muc). Quy tac trung thuc cua module
nay:

* Moi thao tac deu di qua cung mot duong day post-login nhu
  contacts/signaling: common params zpw_ver=695 & zpw_type=30 +
  params=<AES-JSON bang khoa phien zpw_enk, AES-CBC IV 0, base64>,
  response envelope HAI LOP (decode_postlogin_data). Khong co
  endpoint nao o day duoc bia: path + ma lenh + body lay tu
  SERVICE-MAP.md (trich truc tiep tu ham static trong bundle).
* Service nao body chua lan het thi CATALOG danh dau
  body_unverified=True — UI canh bao, integrator / dot lan tiep
  theo phai xac minh body that truoc khi coi la xong. Truong nao
  chua biet gia tri thi KHONG gui (khong doan gia tri).
* Service chi thuoc may chu zalobot (webhook, proxy, da tai
  khoan, QR web) ghi status "zalobot" — phien web, khong phai
  cua app PC; server tra 409, UI chi hien trang thai.
* Gui tin (text/file/anh/voice/link) co duong PC nhung thuoc
  KHUNG CHAT — chat.py lam; o day chi ghi status "chat" tro toi
  do, khong viet lai duong gui. Ngoai le: sticker, typing, seen,
  quote, forward, undo, delete — la op trong OPS vi chung la
  tac dong len tin da co, khong phai khung gui.
* REACTION va QUICK_MESSAGE: domain KHONG hard-code — chi co
  trong services map server tra ve luc login (config
  zpw_service_map_new, luu o session["service_map"]). Services
  resolve qua map, log domain resolve duoc (xem _domain_for);
  neu map chua co thi tu choi ro rang, khong doan domain.

Route server (moc duy nhat, xem server.py):
  GET  /api/svc/catalog      -> CATALOG (khong can dang nhap)
  POST /api/svc/<action>     -> dispatch(); yeu cau phien Zalo
    (server._require_login). Upload file (doi avatar nhom/tai
    khoan) gui multipart field "file" — xem handle_svc.

Thread = (threadId, type): type "user" (1-1, threadId = userId),
type "group" (threadId = groupId tho). Cac op 1-1 dung toid, cac
op nhom dung grid — dung nhu bundle (sendZText, sendSticker...).
"""

import json
import logging
import time
import urllib.parse
from datetime import datetime, timezone

from . import protocol
from .chat import build_multipart
from .crypto import decode_postlogin_data, session_aes_encrypt

log = logging.getLogger(__name__)

# Nhom hien thi tren UI (theo cach gop Bang 1 cua bao cao doi chieu).
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

# --- Hang so lay tu bundle (SERVICE-MAP.md + lan them 2026-11-05) ---
LANGUAGE = protocol.LANGUAGE  # "vi" — clientLang trong cac body.
AVATAR_SIZE = protocol.AVATAR_SIZE  # 160.

# Loai topic tren board (module "1pet" trong bundle: TEXT_TOPIC=0,
# LINK_TOPIC=1, MSG_TOPIC=2, POLL_TOPIC=3, REMINDER_TOPIC=4).
TOPIC_TEXT = 0
# Mau mac dinh cua topic moi (bundle: color:-16777216).
TOPIC_COLOR_DEFAULT = -16777216
# Emoji mac dinh: nhac hen dung dong ho; ghi chu thuong de trong.
TOPIC_EMOJI_REMINDER = "⏰"
TOPIC_EMOJI_NOTE = ""

# Tat thong bao (module "1pet": SET_MUTE=1, UNSET_MUTE=3).
MUTE_ACTION_SET = 1
MUTE_ACTION_UNSET = 3

# Reaction: chi co "like" la map chac chan tu bundle —
# default_reaction:{rType:3, rIcon:"/-strong"} + thumb
# iconlike_*.png. Cac icon khac (heart/haha/wow/cry/angry) chi
# co cap (rType, rIcon) trong config server (reactionMsgInfo) ma
# khong co ten HA di kem — KHONG doan map; caller phai truyen
# r_icon/r_type truc tiep (xem _b_reaction). Cac cap da thay trong
# bundle (de dot lan sau doi chieu voi config server):
#   2:":-(( " 3:"/-strong" 4:"/-weak" 5:"/-heart" 7:":') "
#   8:":-* " 20:":-h" 32:":o" 65:"/-break" 66:"/-shit" 120:"/-rose"
# Bang day du (ten -> (rType, rIcon)) lay tu zca-js 2.1.2: dist/apis/addReaction.js (rType) + dist/models/Reaction.js (rIcon),
# trich bang script, khong go tay. Cac cap da thay trong bundle PC (ghi chu tren) KHOP voi bang nay. Chi "like" da thu live
# tren app nay; con lai theo thu vien (cung endpoint 12410/12411) — chua thu live.
REACTION_ICONS = {
    'haha': (0, ':>'),
    'like': (3, '/-strong'),
    'heart': (5, '/-heart'),
    'wow': (32, ':o'),
    'cry': (2, ':-(('),
    'angry': (20, ':-h'),
    'kiss': (8, ':-*'),
    'tears_of_joy': (7, ":')"),
    'shit': (66, '/-shit'),
    'rose': (120, '/-rose'),
    'broken_heart': (65, '/-break'),
    'dislike': (4, '/-weak'),
    'love': (29, ';xx'),
    'confused': (51, ';-/'),
    'wink': (45, ';-)'),
    'fade': (121, '/-fade'),
    'sun': (67, '/-li'),
    'birthday': (126, '/-bd'),
    'bomb': (127, '/-bome'),
    'ok': (68, '/-ok'),
    'peace': (69, '/-v'),
    'thanks': (70, '/-thanks'),
    'punch': (71, '/-punch'),
    'share': (72, '/-share'),
    'pray': (73, '_()_'),
    'no': (131, '/-no'),
    'bad': (132, '/-bad'),
    'love_you': (133, '/-loveu'),
    'sad': (1, '--b'),
    'very_sad': (16, ':(('),
    'cool': (21, 'x-)'),
    'nerd': (22, '8-)'),
    'big_smile': (23, ';-d'),
    'sunglasses': (26, 'b-)'),
    'neutral': (30, ':--|'),
    'sad_face': (35, 'p-('),
    'bye': (36, ':-bye'),
    'sleepy': (38, '|-)'),
    'wipe': (39, ':wipe'),
    'dig': (42, ':-dig'),
    'anguish': (44, '&-('),
    'handclap': (46, ':handclap'),
    'angry_face': (47, '>-|'),
    'f_chair': (48, ':-f'),
    'l_chair': (49, ':-l'),
    'r_chair': (50, ':-r'),
    'silent': (52, ';-x'),
    'surprise': (53, ':-o'),
    'embarrassed': (54, ';-s'),
    'afraid': (60, ';-a'),
    'sad2': (61, ':-<'),
    'big_laugh': (62, ':))'),
    'rich': (63, '$-)'),
    'beer': (99, '/-beer'),
}
# Loai tin mac dinh khi react (module "1pet": MSG_TEXT=1) — gia
# dinh tin duoc react la tin text; truyen msg_type neu khac.
REACTION_MSG_TYPE_TEXT = 1


class UnsupportedService(Exception):
    """Service có trong CATALOG nhưng không gọi được từ app PC."""

    def __init__(self, service, status, reason):
        super().__init__("%s: %s" % (service, reason))
        self.service = service
        self.status = status
        self.reason = reason


class UnknownAction(Exception):
    pass


class ServiceError(RuntimeError):
    """Loi server Zalo tra ve trong envelope (inner error_code).

    Subclass cua RuntimeError nen code cu bat RuntimeError van
    dung; .code de caller phan biet ma loi (vd. 212 = chua co
    danh sach ghim tren server — set_pinned xu ly rieng)."""

    def __init__(self, where, code, message=""):
        super().__init__("svc %s: error_code=%s %s"
                         % (where, code, message))
        self.where = where
        self.code = code
        self.message = message


def _csv(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [s.strip() for s in str(value).split(",") if s.strip()]


def _client_id():
    """clientId dang JSON NUMBER epoch-ms tang don dieu (NMlV.next()
    — xem protocol.new_client_id)."""
    return protocol.new_client_id()


def _need(params, key, service):
    v = params.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        raise ValueError("%s: thiếu tham số bắt buộc %s" % (service, key))
    return v


def _bool_param(params, key, default=False):
    v = params.get(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("1", "true", "yes", "on")


def _int_param(params, key, default=None, service=""):
    v = params.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError("%s: %s phải là số nguyên" % (service, key))


def _cli_int(value, service=""):
    """cliMsgId ve so nguyen (clientId la JSON number). Chuoi so
    -> int; so -> nguyen; khac -> ValueError (khong doan)."""
    if isinstance(value, bool):
        raise ValueError("%s: cli_msg_id không hợp lệ" % service)
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    raise ValueError("%s: cli_msg_id phải là số (%r)" % (service, value))


def _parse_remind_ms(value, service):
    """remind_time -> epoch MILLISECONDS (startTime cua topic).
    Nhan: so ms (>=1e12), so giay (epoch s), chuoi so tuong tu,
    chuoi ISO-8601 (vd. 2026-11-06T10:00:00+07:00, date-only
    2026-11-06 = 00:00 dia phuong). Khac -> ValueError."""
    if isinstance(value, bool):
        raise ValueError("%s: remind_time không hợp lệ" % service)
    if isinstance(value, (int, float)):
        n = int(value)
    else:
        s = str(value).strip()
        if not s:
            raise ValueError("%s: remind_time rỗng" % service)
        if s.lstrip("-").isdigit():
            n = int(s)
        else:
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(
                    "%s: remind_time không parse được (%r) — dùng "
                    "ISO-8601 hoặc epoch" % (service, value))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
    if n >= 10 ** 12:
        return n
    if n >= 10 ** 9:
        return n * 1000
    raise ValueError("%s: remind_time epoch quá nhỏ (%r)"
                     % (service, value))


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
# gửi trong params AES. Body nào SERVICE-MAP.md chưa lần hết thì
# CATALOG đánh dấu body_unverified=True — dùng tham số addon, chưa
# xác minh thật, KHÔNG được coi là "đã đúng với client PC thật".
# Trường nào chưa biết giá trị thì KHÔNG gửi (không đoán).

def _b_undo(p, tid, tt):
    # 1-1: {msgId, toid, clientId:number, cliMsgIdUndo} (KHONG imei);
    # nhom: {msgId, grid, clientId, visibility:0, cliMsgIdUndo, imei}.
    body = {"msgId": _need(p, "msg_id", "undo_message"),
            "clientId": _client_id()}
    if p.get("cli_msg_id") not in (None, ""):
        body["cliMsgIdUndo"] = _cli_int(p["cli_msg_id"],
                                       "undo_message")
    if tt == "group":
        body.update({"grid": tid, "visibility": 0,
                     "imei": p["_imei"]})
    else:
        body["toid"] = tid
    return body


def _b_delete_msg(p, tid, tt):
    # {toid|grid, cliMsgId, msgs:[{cliMsgId, globalMsgId, ownerId, destId}], onlyMe:0|1, imei}. Zalo web gửi `msgs` là danh sách ĐỐI TƯỢNG: với
    # [msgId] trơn Zalo trả 114 «Tham số không hợp lệ» (cả onlyMe=0 lẫn 1), với đối tượng trả status 0 (đo 13/11). ownerId = người GỬI tin
    # (mặc định: chính phiên này, tức tin của ta). onlyMe=0 chỉ xoá phía mình — bên kia vẫn giữ tin (đo 13/11), muốn mất cả hai bên phải thu hồi.
    msg_id = str(_need(p, "msg_id", "delete_message"))
    cli_id = str(_need(p, "cli_msg_id", "delete_message"))
    owner = str(p.get("owner_id") or p.get("_uid") or "")
    if not owner:
        raise ValueError("delete_message: thieu owner_id (nguoi gui tin) va phien khong co uid")
    return _toid_or_grid(tid, tt, {
        "cliMsgId": str(int(time.time() * 1000)),
        "msgs": [{"cliMsgId": cli_id, "globalMsgId": msg_id, "ownerId": owner, "destId": str(tid)}],
        "onlyMe": 1 if _bool_param(p, "only_me", True) else 0,
        "imei": p["_imei"]})


def _b_forward(p, tid, tt):
    # Khung da xac minh: {toId|grid, imei}. Phan transform theo
    # loai tin (msgType, msgs/totalIds, file/photo) CHUA lan —
    # dispatch goi _forward_message (lap theo tung dich) thay vi
    # dung builder nay truc tiep; chi giu de mo ta body 1 dich.
    dest = _csv(_need(p, "dest_thread_ids", "forward_message"))[0]
    dtype = (p.get("type") or "user").lower()
    if dtype == "group":
        return {"grid": dest, "imei": p["_imei"]}
    return {"toId": dest, "imei": p["_imei"]}


def _b_quote(p, tid, tt):
    # 1-1 POST /api/message/quote 11771; nhom POST /api/group/quote
    # 11197 (SERVICE-MAP.md §3.1).
    body = {
        "message": _need(p, "text", "quote_message"),
        "clientId": _client_id(),
        "qmsgOwner": _need(p, "qmsg_owner", "quote_message"),
        "qmsgId": _need(p, "msg_id", "quote_message"),
        "qmsgCliId": _cli_int(p.get("qmsg_cli_id") or 0,
                              "quote_message"),
        "qmsgType": _int_param(p, "qmsg_type", 1, "quote_message"),
        "qmsgTs": _int_param(p, "qmsg_ts", 0, "quote_message"),
        "qmsg": p.get("qmsg", ""),
    }
    if tt == "group":
        body.update({"grid": tid, "language": LANGUAGE,
                     "visibility": 0})
    else:
        body.update({"toid": tid, "imei": p["_imei"]})
        if p.get("ttl") not in (None, ""):
            body["qmsgTTL"] = int(p["ttl"])
    return body


def _b_seen(p, tid, tt):
    # Body 1-1 CHUA trich truc tiep (SERVICE-MAP.md §6: chi co
    # delivered 1-1 {msg_ids, seen}); giu body cua audit cu, danh
    # dau body_unverified=True.
    ids = [int(i) if i.isdigit() else i for i in _csv(_need(p, "msg_ids", "mark_seen"))]
    if tt == "group":
        return {"msg_ids": ids, "grid": tid}
    return {"msg_ids": ids, "senderId": tid}


def _b_parse_link(p, tid, tt):
    # {link, version:1, imei}; domain FILE (files-wpa).
    return {"link": _need(p, "link", "parse_link"), "version": 1,
            "imei": p["_imei"]}


def _b_important(p, tid, tt):
    # {limit:50, uid, newestId|lastId} (SERVICE-MAP.md §6).
    if tt != "user":
        raise UnsupportedService(
            "fetch_important", "unsupported",
            "Tin nhắn quan trọng chỉ lần được cho hội thoại 1-1 "
            "(fetchImportant lấy theo uid); nhóm chưa có đường PC.")
    body = {"limit": 50, "uid": tid}
    if p.get("newest_id"):
        body["newestId"] = p["newest_id"]
    if p.get("last_id"):
        body["lastId"] = p["last_id"]
    return body


def _b_history_group(p, tid, tt):
    # {grid, count} (11240).
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
    # 1-1: {toid, destType:"USER", imei}; nhom: {grid, imei}.
    if tt == "group":
        return {"grid": tid, "imei": p["_imei"]}
    return {"toid": tid, "destType": "USER", "imei": p["_imei"]}


def _b_sticker(p, tid, tt):
    # {stickerId, cateId, type, clientId:number, imei, toid|grid}
    # + buildParams (ttl).
    return _toid_or_grid(tid, tt, {
        "stickerId": _need(p, "sticker_id", "send_sticker"),
        "cateId": p.get("cate_id", ""),
        "type": p.get("type_") or p.get("sticker_type") or "",
        "clientId": _client_id(), "imei": p["_imei"], "ttl": 0})


# --- Ban be (SERVICE-MAP.md §2.1) ---
def _b_friend_request(p, tid, tt):
    return {"toid": _need(p, "user_id", "send_friend_request"),
            "msg": p.get("message", ""), "reqsrc": -1,
            "imei": p["_imei"], "language": LANGUAGE}


def _b_friend_accept(p, tid, tt):
    return {"fid": _need(p, "user_id", "accept_friend_request"),
            "language": LANGUAGE}


def _b_friend_reject(p, tid, tt):
    # POST /api/friend/reject 11428 (bundle SERVICE-MAP §2.1 +
    # zca-js rejectFriendRequest): {fid} — KHONG imei, KHONG
    # language (khac accept: {fid, language}).
    return {"fid": _need(p, "user_id", "reject_friend_request")}


def _b_friend_block(p, tid, tt):
    return {"fid": _need(p, "user_id", "block_user"),
            "imei": p["_imei"]}


def _b_friend_unblock(p, tid, tt):
    return {"fid": _need(p, "user_id", "unblock_user"),
            "imei": p["_imei"]}


def _b_sent_requests(p, tid, tt):
    return {"imei": p["_imei"]}


def _b_undo_request(p, tid, tt):
    return {"fid": _need(p, "friend_id", "undo_friend_request")}


def _b_remove_friend(p, tid, tt):
    return {"fid": _need(p, "friend_id", "remove_friend"),
            "imei": p["_imei"]}


def _b_alias_update(p, tid, tt):
    return {"friendId": _need(p, "friend_id", "change_friend_alias"),
            "alias": _need(p, "alias", "change_friend_alias"),
            "imei": p["_imei"]}


def _b_alias_remove(p, tid, tt):
    return {"friendId": _need(p, "friend_id", "remove_friend_alias")}


def _b_block_feed(p, tid, tt):
    return {"fid": _need(p, "user_id", "block_view_feed"),
            "isBlockFeed": 1 if _bool_param(p, "is_block_feed") else 0,
            "imei": p["_imei"]}


# --- Nhom ---
def _b_create_group(p, tid, tt):
    # v1 GET /api/group/create 11185: {clientId, gname, members,
    # nameChanged} (suggestionId chua biet gia tri — khong gui).
    return {"clientId": _client_id(),
            "gname": _need(p, "name", "create_group"),
            "members": _csv(p.get("member_ids")),
            "nameChanged": 1}


def _b_group_info(p, tid, tt):
    # POST /api/group/getmg 12604 (da lan het — static getGroupInfos
    # mac dinh mpage=1, mcount=50; avatar_size=160).
    return {"grids": [tid], "avatar_size": AVATAR_SIZE,
            "member_avatar_size": AVATAR_SIZE, "mpage": 1,
            "mcount": 50, "imei": p["_imei"]}


def _b_add_member(p, tid, tt):
    # v1 POST /api/group/invite 11186: {grid, members} (KHONG imei).
    return {"grid": tid, "members": _csv(
        _need(p, "member_id", "add_user_to_group"))}


def _b_remove_member(p, tid, tt):
    return {"grid": tid, "members": _csv(
        _need(p, "member_id", "remove_user_from_group")),
        "imei": p["_imei"]}


def _b_group_name(p, tid, tt):
    return {"grid": tid, "gname": _need(p, "name", "change_group_name"),
            "imei": p["_imei"]}


def _b_group_avatar(p, tid, tt):
    # POST files-wpa /api/group/upavatar 11195: UPLOAD FILE
    # (multipart fileContent), khong phai URL. params: {grid,
    # clientId, originWidth, originHeight, imei} (avatarSize chua
    # biet gia tri — khong gui). File lay tu params["_file"].
    if not p.get("_file"):
        raise ValueError("change_group_avatar: thiếu file ảnh "
                         "(multipart field 'file')")
    try:
        width = int(p.get("width") or 0)
        height = int(p.get("height") or 0)
    except ValueError:
        width, height = 0, 0
    return {"grid": tid, "clientId": _client_id(),
            "originWidth": width, "originHeight": height,
            "imei": p["_imei"]}


def _b_deputy(p, tid, tt, service):
    # GET /api/group/admins/add|remove: {grid, members:[], imei}.
    return {"grid": tid,
            "members": [_need(p, "member_id", service)],
            "imei": p["_imei"]}


def _b_change_owner(p, tid, tt):
    # POST /api/group/change-owner 10063.
    return {"grid": tid,
            "newAdminId": _need(p, "member_id", "change_group_owner"),
            "imei": p["_imei"], "language": LANGUAGE}


def _b_group_only(p, tid, tt, service):
    if tt != "group":
        raise UnsupportedService(service, "unsupported",
                                 "Thao tác này chỉ áp dụng cho nhóm.")
    return {"grid": tid, "imei": p["_imei"]}


def _b_join_group(p, tid, tt):
    # GET /api/group/link/join 11825: {link, clientLang}.
    return {"link": _need(p, "link", "join_group"),
            "clientLang": LANGUAGE}


def _b_leave_group(p, tid, tt):
    # POST /api/group/leave 11189: {grids:[], imei, silent:0|1,
    # language}.
    return {"grids": [tid], "imei": p["_imei"],
            "silent": 1 if _bool_param(p, "silent") else 0,
            "language": LANGUAGE}


# --- Ghim / an / luu tru (SERVICE-MAP.md §2.2) ---
def _b_pin_list(p, tid, tt):
    return {"imei": p["_imei"]}


def _b_archived_list(p, tid, tt):
    # GET /api/archivedchat/list 12076: {version, imei}; version la
    # so version dong bo, lan dau = 0 (quy uoc nhu cac version
    # dong bo khac: pinconvers, quickmessage).
    return {"version": 0, "imei": p["_imei"]}


def _b_hidden_list(p, tid, tt):
    return {"imei": p["_imei"]}


def _b_hidden_set(p, tid, tt):
    # POST /api/hiddenconvers/add-remove 10049: {del_threads,
    # add_threads (JSON-string), imei}.
    hidden = _bool_param(p, "hidden", True)
    return {"del_threads": json.dumps([] if hidden else [tid]),
            "add_threads": json.dumps([tid] if hidden else []),
            "imei": p["_imei"]}


def _b_hidden_pin(p, tid, tt):
    return {"new_pin": _need(p, "pin", "update_hidden_convers_pin"),
            "imei": p["_imei"]}


# --- Poll (SERVICE-MAP.md §2.4) ---
def _b_poll_create(p, tid, tt):
    # POST /api/poll/create 12080 (src chua biet gia tri — khong
    # gui; allow_add_new_option/is_anonymous theo UI mac dinh).
    return {"group_id": tid,
            "question": _need(p, "question", "create_poll"),
            "options": _csv(_need(p, "options", "create_poll")),
            "expired_time": _int_param(p, "expired_time", 0, "create_poll"),
            "pinAct": False,
            "allow_multi_choices": _bool_param(
                p, "allow_multi_choices"),
            "allow_add_new_option": _bool_param(
                p, "allow_add_new_option", True),
            "is_hide_vote_preview": _bool_param(
                p, "hide_vote_preview"),
            "is_anonymous": _bool_param(p, "is_anonymous"),
            "poll_type": 0, "src": 1,
            "imei": p["_imei"]}


def _b_poll_detail(p, tid, tt):
    return {"poll_id": _need(p, "poll_id", "get_poll_detail"),
            "imei": p["_imei"]}


def _b_poll_lock(p, tid, tt):
    return {"poll_id": _need(p, "poll_id", "lock_poll"),
            "imei": p["_imei"]}


def _b_poll_vote(p, tid, tt):
    # GET /api/poll/vote 12084 (bundle SERVICE-MAP §2.4 +
    # zca-js votePoll): {poll_id, option_ids, imei}. option_ids
    # la list (UI: CSV; alias option_id cho 1 lua chon).
    # zca-js: unvote = option_ids rong — op nay chi bo phieu nen
    # yeu cau it nhat 1 lua chon. poll_id/option_ids giu nguyen
    # dang chuoi nhu create_poll/get_poll_detail (khong ep int).
    raw = p.get("option_ids")
    if raw in (None, ""):
        raw = p.get("option_id")
    option_ids = _csv(raw)
    if not option_ids:
        raise ValueError("vote_poll: thiếu tham số bắt buộc "
                         "option_ids")
    return {"poll_id": _need(p, "poll_id", "vote_poll"),
            "option_ids": option_ids,
            "imei": p["_imei"]}


# --- Tin nhan nhanh (SERVICE-MAP.md §2.5) ---
def _b_qm_add(p, tid, tt):
    # GET /api/quickmessage/create 12029 (media/type chua biet
    # kieu/gia tri — khong gui).
    return {"keyword": _need(p, "keyword", "add_quick_message"),
            "message": _need(p, "title", "add_quick_message"),
            "imei": p["_imei"]}


def _b_qm_list(p, tid, tt):
    return {"version": 0, "lang": 0, "imei": p["_imei"]}


def _b_qm_delete(p, tid, tt):
    return {"itemIds": _csv(_need(p, "item_ids",
                                  "remove_quick_message"))}


def _b_qm_update(p, tid, tt):
    # GET /api/quickmessage/update 12026 (KHONG imei; media/type
    # chua biet — khong gui).
    return {"itemId": _need(p, "item_id", "update_quick_message"),
            "keyword": p.get("keyword", ""),
            "message": p.get("title", "")}


# --- Reaction (SERVICE-MAP.md §2.3) ---
def _b_reaction(p, tid, tt):
    # POST REACTION /api/message/reaction 12410 /
    # /api/group/reaction 12411. react_list item: {message:
    # JSON-str({rMsg:[{gMsgID, cMsgID, msgType}], rIcon, rType,
    # source:6}), clientId: number (cliMsgId cua tin duoc react)}.
    icon = (p.get("icon") or "").strip()
    if icon in REACTION_ICONS:
        r_type, r_icon = REACTION_ICONS[icon]
    else:
        r_icon = p.get("r_icon")
        r_type = p.get("r_type")
        if not r_icon or r_type in (None, ""):
            raise ValueError(
                "add_reaction: icon %r không có trong bảng (%s); "
                "hoặc truyền r_icon + r_type trực tiếp"
                % (icon, ", ".join(sorted(REACTION_ICONS))))
        try:
            r_type = int(r_type)
        except (TypeError, ValueError):
            raise ValueError("add_reaction: r_type phải là số")
    cli_id = _cli_int(_need(p, "cli_msg_id", "add_reaction"),
                      "add_reaction")
    msg_type = _int_param(p, "msg_type", REACTION_MSG_TYPE_TEXT,
                          "add_reaction")
    item_msg = {"rMsg": [{"gMsgID": _need(p, "msg_id", "add_reaction"),
                          "cMsgID": cli_id, "msgType": msg_type}],
                "rIcon": r_icon, "rType": r_type, "source": 6}
    react = {"message": json.dumps(item_msg, separators=(",", ":"),
                                   ensure_ascii=False),
             "clientId": cli_id}
    if tt == "group":
        return {"grid": tid, "react_list": [react],
                "imei": p["_imei"]}
    return {"toid": tid, "react_list": [react]}


# --- Hoi thoai / trang thai ---
def _b_unread_add(p, tid, tt):
    # POST /api/conv/addUnreadMark 12013: {param: JSON-str({convsGroup, convsUser, imei})}; moi muc la DOI TUONG {id, cliMsgId, fromUid:"0",
    # ts} (zca-js addUnreadMark; ban cu gui chuoi id tro nen khong khop dang Zalo PC).
    now = int(time.time() * 1000)
    entry = {"id": tid, "cliMsgId": str(now), "fromUid": "0", "ts": now}
    inner = {"convsGroup": [entry] if tt == "group" else [],
             "convsUser": [] if tt == "group" else [entry],
             "imei": p["_imei"]}
    return {"param": json.dumps(inner, separators=(",", ":"),
                                ensure_ascii=False)}


def _b_unread_remove(p, tid, tt):
    # POST /api/conv/removeUnreadMark 12014: {param: JSON-str({convsGroup, convsUser, convsGroupData, convsUserData})} — bundle
    # `removeMarkAsUnread(e,t,n,a)`; *Data la [{id, ts}] (zca-js removeUnreadMark). Ban cu thieu hai truong *Data.
    now = int(time.time() * 1000)
    group = tt == "group"
    inner = {"convsGroup": [tid] if group else [],
             "convsUser": [] if group else [tid],
             "convsGroupData": [{"id": tid, "ts": now}] if group else [],
             "convsUserData": [] if group else [{"id": tid, "ts": now}]}
    return {"param": json.dumps(inner, separators=(",", ":"),
                                ensure_ascii=False)}


def _b_delete_chat(p, tid, tt):
    # POST deleteconver 11778/11835: {toid|grid, cliMsgId?,
    # conver?, onlyMe:1, imei}. cliMsgId/conver lay tu tin cuoi
    # hoi thoai — neu caller biet thi truyen (cli_msg_id, conver),
    # khong thi bo qua (khong doan).
    body = _toid_or_grid(tid, tt, {"onlyMe": 1, "imei": p["_imei"]})
    if p.get("cli_msg_id") not in (None, ""):
        body["cliMsgId"] = _cli_int(p["cli_msg_id"], "delete_chat")
    if p.get("conver"):
        body["conver"] = p["conver"]
    return body


def _b_auto_delete(p, tid, tt):
    # POST /api/conv/autodelete/updateConvers 12023: {threadId,
    # isGroup:bool, ttl, clientLang} — params trong QUERY URL,
    # KHONG co form body (method POST_QUERY).
    ttl = _need(p, "ttl", "update_auto_delete_chat")
    # isGroup phải là SỐ 0/1: gửi true/false -> Zalo trả 114 (đo 13/11). Zalo chỉ nhận ttl 0 / 1 / 7 / 14 / 30 ngày (1 giờ chỉ zBusiness).
    return {"threadId": tid, "isGroup": 1 if tt == "group" else 0,
            "ttl": int(ttl), "clientLang": LANGUAGE}


def _b_mute(p, tid, tt):
    # POST /api/social/profile/setmute 11288 (da lan het tu bundle:
    # setMuteConversation): {toid, duration, action, startTime,
    # muteType, imei}. action: SET_MUTE=1 / UNSET_MUTE=3;
    # muteType: 1 = 1-1, 2 = nhom; startTime = unix hien tai;
    # duration mac dinh -1 (tat vinh vien), 0 = bat lai.
    dur = _int_param(p, "duration", -1, "set_mute")
    if dur is None:
        dur = -1
    return {"toid": tid, "duration": dur,
            "action": MUTE_ACTION_UNSET if dur == 0
            else MUTE_ACTION_SET,
            "startTime": int(time.time()),
            "muteType": 2 if tt == "group" else 1,
            "imei": p["_imei"]}


def _b_user_info(p, tid, tt):
    # POST /api/social/friend/getprofiles/v2: bundle `getFriendProfilev2` + zca-js getUserInfo — {phonebook_version, friend_pversion_map:
    # ["<id>_0", ...], avatar_size, language, show_online_status, imei}. Ban cu gui GET {userId, imei} — khong dung dang Zalo.
    ids = _csv(_need(p, "user_id", "get_user_info"))
    return {"phonebook_version": 0,
            "friend_pversion_map": [i if "_" in i else "%s_0" % i for i in ids],
            "avatar_size": AVATAR_SIZE, "language": LANGUAGE,
            "show_online_status": 1, "imei": p["_imei"]}


def _b_find_user(p, tid, tt):
    # GET friend-wpa /api/friend/profile/get 11420.
    return {"phone": _need(p, "phone", "find_user"),
            "avatar_size": 240, "language": LANGUAGE,
            "imei": p["_imei"]}


def _b_last_online(p, tid, tt):
    # GET /api/social/profile/lastOnline 12090 (conv_type chua
    # biet gia tri — khong gui).
    return {"uid": _need(p, "user_id", "last_online"),
            "conv_type": 1, "imei": p["_imei"]}


def _b_update_profile(p, tid, tt):
    # POST /api/social/profile/update 12075: fields cu the chua
    # lan — giu body cua audit cu, danh dau unverified.
    # zca-js updateProfile (profile la CHUOI JSON, kem biz + language; khong imei); ban cu gui name/dob/gender o cap ngoai cung.
    profile = {}
    if p.get("name"):
        profile["name"] = p["name"]
    if p.get("dob"):
        profile["dob"] = p["dob"]
    if str(p.get("gender")) in ("0", "1"):
        profile["gender"] = int(p["gender"])
    if not profile:
        raise ValueError("update_profile: cần ít nhất name, dob "
                         "hoặc gender")
    return {"profile": json.dumps(profile, separators=(",", ":"), ensure_ascii=False),
            "biz": "{}", "language": LANGUAGE}


def _b_update_settings(p, tid, tt):
    # GET wpa.zalo.me /api/setting/update 12033: object truyen
    # thang, key that chua lan — giu body cua audit cu, danh dau
    # unverified.
    # Bundle `setSettings(e)` + zca-js updateSettings: body la {<ten cai dat>: gia tri}, vd {"show_online_status": 1}. Ban cu gui
    # {settingType, status, imei} (ten khoa gia) nen Zalo khong doi cai dat nao.
    key = str(_need(p, "setting_type", "update_settings")).strip()
    if not key.replace("_", "").isalnum():
        raise ValueError("update_settings: setting_type không hợp lệ")
    return {key: _int_param({"status": _need(p, "status", "update_settings")}, "status", None, "update_settings")}


def _b_change_avatar(p, tid, tt):
    # POST files-wpa /api/profile/upavatar 11819: UPLOAD FILE
    # (multipart fileContent). params: {clientId, language}
    # (avatarSize/metaData chua biet gia tri — khong gui).
    if not p.get("_file"):
        raise ValueError("change_account_avatar: thiếu file ảnh "
                         "(multipart field 'file')")
    return {"clientId": _client_id(), "language": LANGUAGE}


def _b_avatar_list(p, tid, tt):
    # GET /api/social/avatar-list 12451: body chua lan — giu body
    # cua audit cu, danh dau unverified.
    try:
        count = int(p.get("count") or 20)
    except ValueError:
        count = 20
    try:
        page = int(p.get("page") or 1)
    except ValueError:
        page = 1
    return {"page": page, "albumId": "0", "count": count, "imei": p["_imei"]}


def _b_sticker_list(p, tid, tt):
    # GET sticker-wpa /api/message/sticker/category/list 11155:
    # params AES cua chuoi rong "" (khong body). Tra ve str rong —
    # _url/_post gui raw, khong json.dumps.
    return ""


def _b_sticker_detail(p, tid, tt):
    # GET sticker-wpa /api/message/sticker/category/detail 11156:
    # {cid} (album = cate id).
    return {"cid": _need(p, "sticker_album", "get_stickers_detail")}


# --- Nhac hen / bang tin (board) ---
def _topic_params(p):
    """params (topicInfo) cua topic: {title, content?}."""
    params = {"title": p.get("title", "")}
    if p.get("content"):
        params["content"] = p["content"]
    return params


def _reminder_objectdata_1_1(p, tid, for_update=False):
    """objectData cho nhac hen 1-1 (createOneOneGroupTopic /
    updateOneOneGroupTopic): {toUid, type:TEXT_TOPIC, color, emoji,
    startTime, duration:-1, params, needPin, repeat, creatorUid}
    (+ reminderId khi update). src chua biet gia tri — khong gui.
    startTime: ms; mac dinh -1 (update khi khong truyen
    remind_time — giu nguyen gio cu la viec cua UI, khong doan)."""
    if p.get("remind_time") not in (None, ""):
        start = _parse_remind_ms(p["remind_time"], "edit_reminder"
                                 if for_update else "create_reminder")
    elif for_update:
        start = -1
    else:
        start = _parse_remind_ms(
            _need(p, "remind_time", "create_reminder"),
            "create_reminder")
    obj = {"toUid": tid, "type": TOPIC_TEXT,
           "color": TOPIC_COLOR_DEFAULT,
           "emoji": TOPIC_EMOJI_REMINDER, "startTime": start,
           "duration": -1, "params": _topic_params(p),
           "needPin": False, "repeat": 0,
           "creatorUid": p.get("_uid", "")}
    if for_update:
        obj["reminderId"] = _need(p, "topic_id", "edit_reminder")
    else:
        obj["src"] = 1                      # zca-js createReminder; update khong co src (bundle updateOneOneGroupTopic)
    return obj


def _b_reminder_create(p, tid, tt):
    if tt == "user":
        # POST board /api/board/oneone/create 12429:
        # {objectData: JSON-str, imei}.
        return {"objectData": json.dumps(
            _reminder_objectdata_1_1(p, tid), separators=(",", ":"),
            ensure_ascii=False), "imei": p["_imei"]}
    # Nhom: cung qua /api/board/topic/create 12141 (da lan:
    # createGroupTopicv2) — {grid, type, color, emoji, startTime,
    # duration, params: JSON-str, needPin, repeat, imei}.
    start = _parse_remind_ms(
        _need(p, "remind_time", "create_reminder"), "create_reminder")
    return {"grid": tid, "type": TOPIC_TEXT,
            "color": TOPIC_COLOR_DEFAULT,
            "emoji": TOPIC_EMOJI_REMINDER, "startTime": start,
            "duration": -1,
            "params": json.dumps(_topic_params(p),
                                 separators=(",", ":"),
                                 ensure_ascii=False),
            "needPin": False, "repeat": 0, "src": 1,
            "imei": p["_imei"]}


def _b_reminder_remove(p, tid, tt):
    if tt == "user":
        # POST board /api/board/oneone/remove 12431: {uid,
        # reminderId} (KHONG imei).
        return {"uid": tid,
                "reminderId": _need(p, "reminder_id",
                                    "remove_reminder")}
    # Nhom: POST board /api/board/topic/remove 12143 (da lan:
    # removeGroupTopicv2): {grid, topicId, imei}.
    return {"grid": tid,
            "topicId": _need(p, "reminder_id", "remove_reminder"),
            "imei": p["_imei"]}


def _b_reminder_edit(p, tid, tt):
    if tt == "user":
        # POST board /api/board/oneone/update 12430:
        # {objectData: JSON-str} (KHONG imei).
        return {"objectData": json.dumps(
            _reminder_objectdata_1_1(p, tid, for_update=True),
            separators=(",", ":"), ensure_ascii=False)}
    # Nhom: POST board /api/board/topic/update 12142 — bundle `updateGroupTopicv2` (nhanh cu) + zca-js editReminder: {grid, type, color, emoji,
    # startTime, duration, params: JSON-str, needPin, topicId, repeat, imei}. Ban cu goi /topic/updateEventResponse (12087) la «tra loi su kien»
    # (RSVP) — khong sua nhac hen nao.
    start = -1
    if p.get("remind_time") not in (None, ""):
        start = _parse_remind_ms(p["remind_time"], "edit_reminder")
    return {"grid": tid, "type": TOPIC_TEXT,
            "color": TOPIC_COLOR_DEFAULT,
            "emoji": TOPIC_EMOJI_REMINDER, "startTime": start,
            "duration": -1,
            "params": json.dumps(_topic_params(p), separators=(",", ":"), ensure_ascii=False),
            "needPin": False,
            "topicId": _need(p, "topic_id", "edit_reminder"),
            "repeat": 0, "imei": p["_imei"]}


def _b_reminder_get(p, tid, tt):
    # GET board /api/board/topic/getReminder 12088:
    # {eventId, imei}.
    return {"eventId": _need(p, "reminder_id", "get_reminder"),
            "imei": p["_imei"]}


def _board_list_objectdata(p, tid, tt):
    """objectData cho list board: chi gui key nao da biet gia tri
    (uid/group_id + phan trang neu caller truyen); cac key khac
    client that gui undefined thi JSON.stringify bo qua."""
    inner = {"group_id": tid} if tt == "group" else {"uid": tid}
    # Mac dinh nhu zca-js getListReminder: board_type 1 (nhac hen), page 1, count 20, last_id 0, last_type 0.
    inner.update({"board_type": 1, "page": 1, "count": 20, "last_id": 0, "last_type": 0})
    for key in ("board_type", "page", "count", "last_id",
                "last_type"):
        if p.get(key) not in (None, ""):
            try:
                inner[key] = int(p[key])
            except (TypeError, ValueError):
                inner[key] = p[key]
    return json.dumps(inner, separators=(",", ":"),
                      ensure_ascii=False)


def _b_reminder_list(p, tid, tt):
    if tt == "user":
        # GET board /api/board/oneone/list 12432:
        # {objectData} (KHONG imei).
        return {"objectData": _board_list_objectdata(p, tid, tt)}
    # GET board /api/board/listReminder 12425:
    # {objectData, imei}.
    return {"objectData": _board_list_objectdata(p, tid, tt),
            "imei": p["_imei"]}


def _b_reminder_responses(p, tid, tt):
    # GET board /api/board/topic/listResponseEvent 12086:
    # {eventId} (KHONG imei).
    return {"eventId": _need(p, "reminder_id",
                             "get_reminder_responses")}


def _b_note_create(p, tid, tt):
    # POST board /api/board/topic/create 12141 (da lan:
    # createGroupTopicv2): {grid, type:TEXT_TOPIC, color, emoji:"",
    # startTime:-1, duration:-1, params: JSON-str({title}),
    # needPin, repeat:0, imei} (src chua biet — khong gui).
    return {"grid": tid, "type": TOPIC_TEXT,
            "color": TOPIC_COLOR_DEFAULT,
            "emoji": TOPIC_EMOJI_NOTE, "startTime": -1,
            "duration": -1,
            "params": json.dumps(
                {"title": _need(p, "title", "create_note_group")},
                separators=(",", ":"), ensure_ascii=False),
            "needPin": _bool_param(p, "pin_act"),
            "repeat": 0, "src": 1, "imei": p["_imei"]}


def _b_note_edit(p, tid, tt):
    # POST board /api/board/topic/update 12142 (da lan:
    # updateGroupTopicv2): nhu create + topicId; needPin chi gui
    # khi caller truyen pin_act (khong doan trang thai ghim cu).
    body = {"grid": tid, "type": TOPIC_TEXT,
            "color": TOPIC_COLOR_DEFAULT,
            "emoji": TOPIC_EMOJI_NOTE, "startTime": -1,
            "duration": -1,
            "params": json.dumps(
                {"title": _need(p, "title", "edit_note_group")},
                separators=(",", ":"), ensure_ascii=False),
            "topicId": _need(p, "topic_id", "edit_note_group"),
            "repeat": 0, "imei": p["_imei"]}
    if p.get("pin_act") not in (None, ""):
        body["needPin"] = _bool_param(p, "pin_act")
    return body


def _b_board_list(p, tid, tt):
    # GET board /api/board/list 12140: {group_id, imei} (+ phan
    # trang neu caller truyen; board_type/last_* chua biet — chi
    # gui khi co).
    # Mac dinh nhu zca-js getListBoard: board_type 0, page 1, count 20, last_id 0, last_type 0 (bundle listBoard gui du 5 khoa).
    body = {"group_id": tid, "board_type": 0, "page": 1, "count": 20, "last_id": 0, "last_type": 0, "imei": p["_imei"]}
    for key in ("board_type", "page", "count", "last_id",
                "last_type"):
        if p.get(key) not in (None, ""):
            try:
                body[key] = int(p[key])
            except (TypeError, ValueError):
                body[key] = p[key]
    return body


def _b_labels(p, tid, tt):
    return {"imei": p["_imei"]}


def _b_keepalive(p, tid, tt):
    # GET chat /keepalive (11770) — zca-js auth/keepAlive: chi gui
    # {imei}, params AES nhu moi GET post-login khac.
    return {"imei": p["_imei"]}


def _b_label_update(p, tid, tt):
    # POST /api/convlabel/update 12160: {labelData: JSON-str(danh sach nhan), version, imei} — bundle `updateConversationLabel(e,t)` +
    # zca-js updateLabels. labelData la TOAN BO danh sach nhan (id, text, color, emoji, conversations...) lay tu get_labels; version la so
    # phien ban cua danh sach do. Ban cu gui {threadId, type, labelIds} — khong phai dang Zalo.
    raw = _need(p, "label_data", "update_label")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise ValueError("update_label: label_data phải là JSON danh sách nhãn")
    if not isinstance(raw, list):
        raise ValueError("update_label: label_data phải là danh sách nhãn (lấy từ get_labels)")
    version = _int_param({"version": _need(p, "version", "update_label")}, "version", None, "update_label")
    return {"labelData": json.dumps(raw, separators=(",", ":"), ensure_ascii=False),
            "version": version, "imei": p["_imei"]}

# ------------------------------------------------------------------ OPS
# action -> spec. domain: "chat" | "group" | "profile" | "convers"
#   | "friend" | "alias" | "label" | "board" | "sticker" | "file"
#   | "auth" | "reaction" | "quick_message" (2 cai cuoi resolve
#   qua services map — xem _domain_for, KHONG hard-code).
# method: GET (params trong query) | POST (params trong form body)
#   | POST_QUERY (POST, params trong query URL — #60)
#   | POST_MULTIPART (POST multipart fileContent — avatar).
# thread: "both" | "user" | "group" | "none" (không cần thread).
# body_unverified: True = path + mã có trong bundle nhưng body
#   chưa được lần hết trong audit — dùng tham số addon, cần xác
#   minh thật. no_params: True = GET không gửi params (chi co
#   common params — reset PIN).

def _op(addon_no, addon, group, label, desc, domain, path, code,
        method, thread, fields, body_fn, body_unverified=True,
        danger=False, no_params=False):
    return {"addon_no": addon_no, "addon": addon, "group": group,
            "label": label, "desc": desc, "domain": domain,
            "path": path, "code": code, "method": method,
            "thread": thread, "fields": fields,
            "body_fn": body_fn, "body_unverified": body_unverified,
            "danger": danger, "status": "supported",
            "no_params": no_params}


def _b_pin_set(p, tid, tt):
    # Body cho POST /api/pinconvers/update — version + danh sach
    # da tinh san o dispatch (GET list truoc), xem _set_pinned.
    return {"version": p["_pin_version"],
            "conversations": p["_pin_conversations"]}


F_MSG = [{"key": "msg_id", "label": "ID tin nhắn", "required": True}]
F_MSG_CLI = F_MSG + [{"key": "cli_msg_id", "label": "Client ID tin nhắn"}]

OPS = {
    # --- Tác động tin nhắn (nhóm E + liên quan) ---
    "undo_message": _op(
        28, "undo_message", "tin_nhan", "Thu hồi tin nhắn",
        "Thu hồi tin đã gửi (1-1: /api/message/undo 11281; "
        "nhóm: /api/group/undomsg 11192). clientId NUMBER, "
        "cliMsgIdUndo; nhóm thêm visibility=0, imei.",
        None, None, None, "POST", "both", F_MSG_CLI, _b_undo,
        body_unverified=False),
    "delete_message": _op(
        68, "delete_message", "tin_nhan", "Xóa tin nhắn",
        "Xóa tin chỉ ở phía mình (1-1: 11779; nhóm: 11834). "
        "Body {toid|grid, msgs:[msgId], onlyMe, imei}.",
        None, None, None, "POST", "both",
        F_MSG_CLI + [{"key": "owner_id",
                      "label": "Mã người gửi tin (bỏ trống = tin của chính tài khoản; xoá tin người khác trong nhóm thì điền)"},
                     {"key": "only_me",
                      "label": "Chỉ xóa phía mình (true/false)"}],
        _b_delete_msg, body_unverified=False),
    "forward_message": _op(
        69, "forward_message", "tin_nhan", "Chuyển tiếp tin nhắn",
        "Chuyển tiếp NỘI DUNG CHỮ tới nhiều thread bằng mforward (1-1: "
        "/api/message/mforward 12440; nhóm: /api/group/mforward 12442, "
        "domain file) — bundle Zalo PC + zca-js. Ảnh/file chưa hỗ trợ.",
        None, None, None, "POST", "none",
        [{"key": "message", "label": "Nội dung chữ cần chuyển tiếp",
          "required": True},
         {"key": "ttl", "label": "TTL (ms, 0 = không tự xóa)"},
         {"key": "dest_thread_ids",
          "label": "Thread đích (cách nhau bằng dấu phẩy)",
          "required": True},
         {"key": "type", "label": "Loại thread đích (user/group)"}],
        _b_forward, body_unverified=False),
    "quote_message": _op(
        None, "(quote — trong send_message)", "tin_nhan",
        "Trích dẫn tin nhắn",
        "Không có service riêng trong 96; trích dẫn nằm trong "
        "send_message (1-1: /api/message/quote 11771; nhóm: "
        "/api/group/quote 11197).",
        None, None, None, "POST", "both",
        F_MSG + [{"key": "text", "label": "Nội dung trích dẫn",
                  "required": True},
                 {"key": "qmsg_owner", "label": "UID người gửi tin "
                  "gốc", "required": True},
                 {"key": "qmsg_cli_id", "label": "Client ID tin gốc"},
                 {"key": "qmsg_type", "label": "Loại tin gốc"},
                 {"key": "qmsg_ts", "label": "Timestamp tin gốc"},
                 {"key": "qmsg", "label": "Nội dung tin gốc"},
                 {"key": "ttl", "label": "TTL (1-1)"}],
        _b_quote, body_unverified=False),
    "mark_seen": _op(
        None, "(seen/delivered — ngoài 96)", "tin_nhan",
        "Đánh dấu đã xem / đã nhận",
        "1-1: /api/message/seen 11150 {msg_ids:[số], senderId}; nhóm: "
        "/api/group/seen 11167 {msg_ids, grid} — bundle sendSeen / "
        "sendGroupSeen. Dịch vụ HA mark_seen đi đường seenv2 (tin gốc "
        "từ kho) và chỉ rơi về bản này khi không có tin gốc.",
        None, None, None, "POST", "both",
        [{"key": "msg_ids", "label": "ID tin nhắn (cách nhau bằng "
          "dấu phẩy)", "required": True}],
        _b_seen, body_unverified=False),
    "parse_link": _op(
        70, "parse_link", "tin_nhan", "Phân tích link lấy preview",
        "GET files-wpa /api/message/parselink (11285) "
        "{link, version:1, imei}.",
        "file", "/api/message/parselink", 11285, "GET", "none",
        [{"key": "link", "label": "Link", "required": True}],
        _b_parse_link, body_unverified=False),
    "fetch_important": _op(
        None, "(tin quan trọng — ngoài 96)", "tin_nhan",
        "Xem tin nhắn quan trọng",
        "/api/message/fetchImportant (12114), body {limit, uid}. "
        "Chỉ hội thoại 1-1.",
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
    "add_reaction": _op(
        67, "add_reaction", "tin_nhan", "Thả reaction",
        "POST REACTION /api/message/reaction (12410) / "
        "/api/group/reaction (12411). Domain lay tu services map "
        "luc login (khong hard-code). Chi map 'like' da xac minh "
        "(rType 3, rIcon '/-strong'); icon khac truyen r_icon + "
        "r_type truc tiep.",
        None, None, None, "POST", "both",
        [{"key": "icon", "label": "Icon (like/heart/haha/...)",
          "required": True},
         {"key": "msg_id", "label": "ID tin nhắn", "required": True},
         {"key": "cli_msg_id", "label": "Client ID tin nhắn",
          "required": True},
         {"key": "r_icon", "label": "rIcon (khi icon chưa map)"},
         {"key": "r_type", "label": "rType (khi icon chưa map)"},
         {"key": "msg_type", "label": "Loại tin (mặc định 1=text)"}],
        _b_reaction),
    # --- Bạn bè (nhóm B, SERVICE-MAP §2.1) ---
    "send_friend_request": _op(
        8, "send_friend_request", "ho_so", "Gửi lời mời kết bạn",
        "POST friend-wpa /api/friend/sendreq (11424) {toid, msg, "
        "reqsrc:-1, imei, language}.",
        "friend", "/api/friend/sendreq", 11424, "POST", "none",
        [{"key": "user_id", "label": "UserId", "required": True},
         {"key": "message", "label": "Lời nhắn"}],
        _b_friend_request, body_unverified=False),
    "accept_friend_request": _op(
        24, "accept_friend_request", "ho_so", "Chấp nhận kết bạn",
        "POST friend-wpa /api/friend/accept (11427) {fid, "
        "language} (KHÔNG imei).",
        "friend", "/api/friend/accept", 11427, "POST", "none",
        [{"key": "user_id", "label": "UserId", "required": True}],
        _b_friend_accept, body_unverified=False),
    "reject_friend_request": _op(
        None, "(từ chối kết bạn — ngoài 96)", "ho_so",
        "Từ chối lời mời kết bạn",
        "POST friend-wpa /api/friend/reject (11428) {fid} "
        "(KHÔNG imei, KHÔNG language) — bundle SERVICE-MAP §2.1 "
        "+ zca-js rejectFriendRequest.",
        "friend", "/api/friend/reject", 11428, "POST", "none",
        [{"key": "user_id", "label": "UserId", "required": True}],
        _b_friend_reject, body_unverified=False),
    "block_user": _op(
        25, "block_user", "ho_so", "Chặn người dùng",
        "POST friend-wpa /api/friend/block (11422) {fid, imei}.",
        "friend", "/api/friend/block", 11422, "POST", "none",
        [{"key": "user_id", "label": "UserId", "required": True}],
        _b_friend_block, body_unverified=False),
    "unblock_user": _op(
        26, "unblock_user", "ho_so", "Bỏ chặn người dùng",
        "POST friend-wpa /api/friend/unblock (11433) {fid, imei}.",
        "friend", "/api/friend/unblock", 11433, "POST", "none",
        [{"key": "user_id", "label": "UserId", "required": True}],
        _b_friend_unblock, body_unverified=False),
    "get_sent_friend_requests": _op(
        35, "get_sent_friend_requests", "ho_so",
        "Xem lời mời kết bạn đã gửi",
        "GET friend-wpa /api/friend/requested/list (12203) {imei}.",
        "friend", "/api/friend/requested/list", 12203, "GET", "none",
        [], _b_sent_requests, body_unverified=False),
    "undo_friend_request": _op(
        36, "undo_friend_request", "ho_so", "Thu hồi lời mời kết bạn",
        "POST friend-wpa /api/friend/undo (11441) {fid} "
        "(KHÔNG imei).",
        "friend", "/api/friend/undo", 11441, "POST", "none",
        [{"key": "friend_id", "label": "UserId", "required": True}],
        _b_undo_request, body_unverified=False),
    "remove_friend": _op(
        37, "remove_friend", "ho_so", "Hủy kết bạn",
        "POST friend-wpa /api/friend/remove (11423) {fid, imei}.",
        "friend", "/api/friend/remove", 11423, "POST", "none",
        [{"key": "friend_id", "label": "UserId", "required": True}],
        _b_remove_friend, body_unverified=False, danger=True),
    "change_friend_alias": _op(
        38, "change_friend_alias", "ho_so", "Đổi biệt danh",
        "GET alias-wpa /api/alias/update (12201) {friendId, "
        "alias, imei}.",
        "alias", "/api/alias/update", 12201, "GET", "none",
        [{"key": "friend_id", "label": "UserId", "required": True},
         {"key": "alias", "label": "Biệt danh mới",
          "required": True}],
        _b_alias_update, body_unverified=False),
    "remove_friend_alias": _op(
        39, "remove_friend_alias", "ho_so", "Xóa biệt danh",
        "GET alias-wpa /api/alias/remove (12202) {friendId} "
        "(KHÔNG imei).",
        "alias", "/api/alias/remove", 12202, "GET", "none",
        [{"key": "friend_id", "label": "UserId", "required": True}],
        _b_alias_remove, body_unverified=False),
    "block_view_feed": _op(
        91, "block_view_feed", "ho_so", "Chặn xem nhật ký",
        "POST friend-wpa /api/friend/feed/block (12204) {fid, "
        "isBlockFeed:1|0, imei}.",
        "friend", "/api/friend/feed/block", 12204, "POST", "none",
        [{"key": "user_id", "label": "UserId", "required": True},
         {"key": "is_block_feed", "label": "Chặn (true/false)",
          "required": True}],
        _b_block_feed, body_unverified=False),
    # --- Quản lý nhóm (nhóm C) ---
    "create_group": _op(
        9, "create_group", "nhom", "Tạo nhóm mới",
        "GET group-wpa /api/group/create (11185) {clientId, gname, "
        "members, nameChanged} — đúng nhánh cũ `createGroup` của bundle "
        "(suggestionId bỏ trống như bundle khi không có).",
        "group", "/api/group/create", 11185, "GET", "none",
        [{"key": "name", "label": "Tên nhóm", "required": True},
         {"key": "member_ids",
          "label": "Thành viên (userId, cách nhau bằng dấu phẩy)"}],
        _b_create_group, body_unverified=False),
    "get_group_info": _op(
        10, "get_group_info", "nhom", "Xem thông tin nhóm",
        "POST group-wpa /api/group/getmg (12604) {grids, "
        "avatar_size:160, member_avatar_size:160, mpage:1, "
        "mcount:50, imei}.",
        "group", "/api/group/getmg", 12604, "POST", "group", [],
        _b_group_info, body_unverified=False),
    "add_user_to_group": _op(
        11, "add_user_to_group", "nhom", "Mời thành viên vào nhóm",
        "POST /api/group/invite (11186) {grid, members} "
        "(KHÔNG imei).",
        "group", "/api/group/invite", 11186, "POST", "group",
        [{"key": "member_id", "label": "UserId (cách nhau bằng dấu "
          "phẩy)", "required": True}],
        _b_add_member, body_unverified=False),
    "remove_user_from_group": _op(
        12, "remove_user_from_group", "nhom", "Đuổi thành viên",
        "POST /api/group/kickout (11187) {grid, members, imei}.",
        "group", "/api/group/kickout", 11187, "POST", "group",
        [{"key": "member_id", "label": "UserId (cách nhau bằng dấu "
          "phẩy)", "required": True}],
        _b_remove_member, body_unverified=False, danger=True),
    "change_group_name": _op(
        31, "change_group_name", "nhom", "Đổi tên nhóm",
        "POST /api/group/updateinfo (11188) {grid, gname, imei}.",
        "group", "/api/group/updateinfo", 11188, "POST", "group",
        [{"key": "name", "label": "Tên mới", "required": True}],
        _b_group_name, body_unverified=False),
    "change_group_avatar": _op(
        32, "change_group_avatar", "nhom", "Đổi ảnh đại diện nhóm",
        "POST files-wpa /api/group/upavatar (11195). Client thật "
        "UPLOAD FILE (multipart field 'file'); params {grid, "
        "clientId, originWidth, originHeight, imei} (avatarSize "
        "chưa biết — không gửi).",
        "file", "/api/group/upavatar", 11195, "POST_MULTIPART",
        "group",
        [{"key": "file", "label": "Ảnh đại diện (upload file)",
          "required": True},
         {"key": "width", "label": "Chiều rộng ảnh"},
         {"key": "height", "label": "Chiều cao ảnh"}],
        _b_group_avatar),
    "add_group_deputy": _op(
        42, "add_group_deputy", "nhom", "Thêm phó nhóm",
        "GET /api/group/admins/add (11814) {grid, members:[], "
        "imei}.",
        "group", "/api/group/admins/add", 11814, "GET", "group",
        [{"key": "member_id", "label": "UserId", "required": True}],
        lambda p, t, tt: _b_deputy(p, t, tt, "add_group_deputy"),
        body_unverified=False),
    "remove_group_deputy": _op(
        43, "remove_group_deputy", "nhom", "Xóa phó nhóm",
        "GET /api/group/admins/remove (11815) {grid, members:[], "
        "imei}.",
        "group", "/api/group/admins/remove", 11815, "GET", "group",
        [{"key": "member_id", "label": "UserId", "required": True}],
        lambda p, t, tt: _b_deputy(p, t, tt, "remove_group_deputy"),
        body_unverified=False),
    "change_group_owner": _op(
        44, "change_group_owner", "nhom", "Chuyển quyền sở hữu nhóm",
        "POST /api/group/change-owner (10063) {grid, newAdminId, "
        "imei, language}.",
        "group", "/api/group/change-owner", 10063, "POST", "group",
        [{"key": "member_id", "label": "UserId chủ mới",
          "required": True}],
        _b_change_owner, body_unverified=False, danger=True),
    "disperse_group": _op(
        45, "disperse_group", "nhom", "Giải tán nhóm",
        "POST /api/group/disperse (11832) {imei, grid}. Không hoàn "
        "tác được.",
        "group", "/api/group/disperse", 11832, "POST", "group", [],
        lambda p, t, tt: _b_group_only(p, t, tt, "disperse_group"),
        body_unverified=False, danger=True),
    "enable_group_link": _op(
        46, "enable_group_link", "nhom", "Bật link tham gia nhóm",
        "GET /api/group/link/new (11822) {grid, imei}.",
        "group", "/api/group/link/new", 11822, "GET", "group", [],
        lambda p, t, tt: _b_group_only(p, t, tt,
                                       "enable_group_link"),
        body_unverified=False),
    "disable_group_link": _op(
        47, "disable_group_link", "nhom", "Tắt link tham gia nhóm",
        "GET /api/group/link/disable (11823) {grid}.",
        "group", "/api/group/link/disable", 11823, "GET", "group", [],
        lambda p, t, tt: _b_group_only(p, t, tt,
                                       "disable_group_link"),
        body_unverified=False),
    "get_group_link": _op(
        None, "(link nhóm — ngoài 96)", "nhom", "Xem link nhóm",
        "GET /api/group/link/detail (11821) {grid, imei} — bundle "
        "getGroupLinkDetail + zca-js.",
        "group", "/api/group/link/detail", 11821, "GET", "group", [],
        lambda p, t, tt: _b_group_only(p, t, tt, "get_group_link"),
        body_unverified=False),
    "join_group": _op(
        48, "join_group", "nhom", "Tham gia nhóm bằng link",
        "GET /api/group/link/join (11825) {link, clientLang}.",
        "group", "/api/group/link/join", 11825, "GET", "none",
        [{"key": "link", "label": "Link mời", "required": True}],
        _b_join_group, body_unverified=False),
    "leave_group": _op(
        49, "leave_group", "nhom", "Rời nhóm",
        "POST /api/group/leave (11189) {grids:[], imei, "
        "silent:0|1, language}.",
        "group", "/api/group/leave", 11189, "POST", "group",
        [{"key": "silent", "label": "Rời lặng lẽ (true/false)"}],
        _b_leave_group, body_unverified=False, danger=True),
    "create_note_group": _op(
        76, "create_note_group", "nhom", "Tạo ghi chú trong nhóm",
        "POST board /api/board/topic/create (12141) {grid, "
        "type:0, color, emoji, startTime:-1, duration:-1, params, "
        "needPin, repeat:0, src:1, imei} — bundle + zca-js.",
        "board", "/api/board/topic/create", 12141, "POST", "group",
        [{"key": "title", "label": "Tiêu đề ghi chú",
          "required": True},
         {"key": "pin_act", "label": "Ghim (true/false)"}],
        _b_note_create, body_unverified=False),
    "edit_note_group": _op(
        77, "edit_note_group", "nhom", "Sửa ghi chú trong nhóm",
        "POST board /api/board/topic/update (12142) — như create "
        "+ topicId; needPin chỉ gửi khi có pin_act.",
        "board", "/api/board/topic/update", 12142, "POST", "group",
        [{"key": "topic_id", "label": "ID ghi chú",
          "required": True},
         {"key": "title", "label": "Tiêu đề mới", "required": True},
         {"key": "pin_act", "label": "Ghim (true/false)"}],
        _b_note_edit, body_unverified=False),
    "get_list_board": _op(
        78, "get_list_board", "nhom", "Xem bảng tin của nhóm",
        "GET board /api/board/list (12140) {group_id, board_type:0, "
        "page:1, count:20, last_id:0, last_type:0, imei} — bundle "
        "listBoard + zca-js getListBoard.",
        "board", "/api/board/list", 12140, "GET", "group", [],
        _b_board_list, body_unverified=False),
    # --- Hội thoại / trạng thái (nhóm D) ---
    "set_pinned_conversation": _op(
        53, "set_pinned_conversation", "hoi_thoai",
        "Ghim/bỏ ghim hội thoại",
        "POST convers-wpa /api/pinconvers/update (12121) "
        "{version, conversations:[id 'u'/'g']}. Đọc trước GET "
        "/api/pinconvers/list (12120) lấy version + danh sách "
        "hiện tại rồi mới POST.",
        "convers", "/api/pinconvers/update", 12121, "POST", "both",
        [{"key": "pinned", "label": "Ghim (true/false)",
          "required": True}],
        _b_pin_set, body_unverified=False),
    "get_pin_conversations": _op(
        66, "get_pin_conversations", "hoi_thoai",
        "Xem hội thoại đã ghim",
        "GET convers-wpa /api/pinconvers/list (12120) {imei} -> "
        "{version, conversations}.",
        "convers", "/api/pinconvers/list", 12120, "GET", "none", [],
        _b_pin_list, body_unverified=False),
    "get_archived_chat_list": _op(
        58, "get_archived_chat_list", "hoi_thoai",
        "Xem hội thoại đã lưu trữ",
        "GET label-wpa /api/archivedchat/list (12076) {version:0, "
        "imei}.",
        "label", "/api/archivedchat/list", 12076, "GET", "none", [],
        _b_archived_list, body_unverified=False),
    "get_hidden_conversations": _op(
        61, "get_hidden_conversations", "hoi_thoai",
        "Xem hội thoại ẩn",
        "GET convers-wpa /api/hiddenconvers/get-all (10048) "
        "{imei}.",
        "convers", "/api/hiddenconvers/get-all", 10048, "GET",
        "none", [], _b_hidden_list, body_unverified=False),
    "set_hidden_conversations": _op(
        62, "set_hidden_conversations", "hoi_thoai",
        "Ẩn/bỏ ẩn hội thoại",
        "POST convers-wpa /api/hiddenconvers/add-remove (10049) "
        "{del_threads, add_threads (JSON-string), imei}.",
        "convers", "/api/hiddenconvers/add-remove", 10049, "POST",
        "both",
        [{"key": "hidden", "label": "Ẩn (true/false)",
          "required": True}],
        _b_hidden_set, body_unverified=False),
    "update_hidden_convers_pin": _op(
        63, "update_hidden_convers_pin", "hoi_thoai",
        "Đặt PIN hội thoại ẩn",
        "GET convers-wpa /api/hiddenconvers/update-pin (10050) "
        "{new_pin, imei}.",
        "convers", "/api/hiddenconvers/update-pin", 10050, "GET",
        "none",
        [{"key": "pin", "label": "PIN mới", "required": True}],
        _b_hidden_pin, body_unverified=False),
    "reset_hidden_convers_pin": _op(
        64, "reset_hidden_convers_pin", "hoi_thoai",
        "Gỡ PIN hội thoại ẩn",
        "GET convers-wpa /api/hiddenconvers/reset (10051) — "
        "KHÔNG gửi params (chỉ common params).",
        "convers", "/api/hiddenconvers/reset", 10051, "GET", "none",
        [], lambda p, t, tt: None, body_unverified=False,
        no_params=True),
    "get_unread_mark": _op(
        54, "get_unread_mark", "hoi_thoai", "Xem hội thoại chưa đọc",
        "GET convers-wpa /api/conv/getUnreadMark (12011) {} "
        "(params rỗng).",
        "convers", "/api/conv/getUnreadMark", 12011, "GET", "none",
        [], lambda p, t, tt: {}, body_unverified=False),
    "add_unread_mark": _op(
        55, "add_unread_mark", "hoi_thoai",
        "Đánh dấu hội thoại chưa đọc",
        "POST convers-wpa /api/conv/addUnreadMark (12013) {param: "
        "JSON-str({convsGroup, convsUser, imei})}.",
        "convers", "/api/conv/addUnreadMark", 12013, "POST", "both",
        [], _b_unread_add, body_unverified=False),
    "remove_unread_mark": _op(
        56, "remove_unread_mark", "hoi_thoai",
        "Bỏ đánh dấu chưa đọc",
        "POST convers-wpa /api/conv/removeUnreadMark (12014) "
        "{param: JSON-str({convsGroup, convsUser, convsGroupData, "
        "convsUserData})} — *Data là [{id, ts}] (bundle + zca-js).",
        "convers", "/api/conv/removeUnreadMark", 12014, "POST",
        "both", [], _b_unread_remove, body_unverified=False),
    "delete_chat": _op(
        57, "delete_chat", "hoi_thoai", "Xóa hội thoại",
        "1-1: /api/message/deleteconver (11778); nhóm: "
        "/api/group/deleteconver (11835). {toid|grid, onlyMe:1, "
        "imei} + cliMsgId/conver nếu caller biết (lấy từ tin "
        "cuối hội thoại).",
        None, None, None, "POST", "both",
        [{"key": "cli_msg_id", "label": "Client ID tin cuối"},
         {"key": "conver", "label": "Conver của tin cuối"}],
        _b_delete_chat, danger=True),
    "get_auto_delete_chat": _op(
        59, "get_auto_delete_chat", "hoi_thoai",
        "Xem hội thoại đang tự xóa",
        "GET convers-wpa /api/conv/autodelete/getConvers (12022) "
        "{} (params rỗng).",
        "convers_web", "/api/conv/autodelete/getConvers", 12022, "GET",
        "none", [], lambda p, t, tt: {}, body_unverified=False),
    "update_auto_delete_chat": _op(
        60, "update_auto_delete_chat", "hoi_thoai",
        "Bật/tắt tự xóa tin nhắn",
        "POST convers-wpa /api/conv/autodelete/updateConvers "
        "(12023) {threadId, isGroup:bool, ttl, clientLang} — "
        "params trong QUERY URL, không có form body.",
        "convers_web", "/api/conv/autodelete/updateConvers", 12023,
        "POST_QUERY", "both",
        [{"key": "ttl", "label": "TTL (0=tắt, 86400000=1 ngày, "
          "604800000=7 ngày)", "required": True}],
        _b_auto_delete, body_unverified=False),
    "get_mute": _op(
        65, "get_mute", "hoi_thoai", "Xem danh sách tắt thông báo",
        "GET profile-wpa /api/social/profile/getmute (11280) "
        "{imei}.",
        "profile", "/api/social/profile/getmute", 11280, "GET",
        "none", [], lambda p, t, tt: {"imei": p["_imei"]},
        body_unverified=False),
    "set_mute": _op(
        52, "set_mute", "hoi_thoai", "Tắt thông báo",
        "POST profile-wpa /api/social/profile/setmute (11288) "
        "{toid, duration, action:1=tắt/3=bật lại, startTime, "
        "muteType:1=1-1/2=nhóm, imei}.",
        "profile", "/api/social/profile/setmute", 11288, "POST",
        "both",
        [{"key": "duration", "label": "Thời lượng giây "
          "(3600/14400/-1=vĩnh viễn/0=bật lại)", "required": True}],
        _b_mute, body_unverified=False),
    # --- Hồ sơ / người dùng (nhóm B + G) ---
    "find_user": _op(
        6, "find_user", "ho_so", "Tìm người dùng theo SĐT",
        "GET friend-wpa /api/friend/profile/get (11420) {phone, "
        "avatar_size:240, language, imei}.",
        "friend", "/api/friend/profile/get", 11420, "GET", "none",
        [{"key": "phone", "label": "Số điện thoại", "required": True}],
        _b_find_user, body_unverified=False),
    "get_user_info": _op(
        7, "get_user_info", "ho_so", "Xem thông tin người dùng",
        "POST profile-wpa /api/social/friend/getprofiles/v2 "
        "(11140) {phonebook_version, friend_pversion_map, "
        "avatar_size, language, show_online_status, imei} — bundle "
        "getFriendProfilev2 + zca-js getUserInfo.",
        "profile", "/api/social/friend/getprofiles/v2", 11140,
        "POST", "none",
        [{"key": "user_id", "label": "UserId (nhiều id cách nhau bằng dấu phẩy)", "required": True}],
        _b_user_info, body_unverified=False),
    "last_online": _op(
        94, "last_online", "ho_so", "Xem hoạt động cuối",
        "GET profile-wpa /api/social/profile/lastOnline (12090) "
        "{uid, conv_type:1, imei} — bundle getOnlinStatus + zca-js.",
        "profile", "/api/social/profile/lastOnline", 12090, "GET",
        "none",
        [{"key": "user_id", "label": "UserId", "required": True}],
        _b_last_online, body_unverified=False),
    "update_profile": _op(
        50, "update_profile", "ho_so", "Cập nhật thông tin cá nhân",
        "POST profile-wpa /api/social/profile/update (12075) "
        "{profile: JSON-str({name, dob, gender}), biz, language} — "
        "zca-js updateProfile.",
        "profile", "/api/social/profile/update", 12075, "POST",
        "none",
        [{"key": "name", "label": "Tên hiển thị"},
         {"key": "dob", "label": "Ngày sinh (yyyy-mm-dd)"},
         {"key": "gender", "label": "Giới tính (0=Nam, 1=Nữ)"}],
        _b_update_profile, body_unverified=False),
    "update_settings": _op(
        51, "update_settings", "ho_so", "Cập nhật cài đặt riêng tư",
        "GET wpa.zalo.me /api/setting/update (12033) — body "
        "{<setting_type>: status}; các loại đã biết (zca-js): "
        "view_birthday, show_online_status, display_seen_status, "
        "receive_message, accept_stranger_call, add_friend_via_phone, "
        "add_friend_via_qr, add_friend_via_group, "
        "add_friend_via_contact, display_on_recommend_friend, "
        "archivedChatStatus, quickMessageStatus.",
        "auth", "/api/setting/update", 12033, "GET", "none",
        [{"key": "setting_type",
          "label": "Tên cài đặt (vd show_online_status, "
          "display_seen_status, receive_message...)", "required": True},
         {"key": "status", "label": "Giá trị (1=bật, 0=tắt)",
          "required": True}],
        _b_update_settings, body_unverified=False),
    "get_settings": _op(
        None, "(đọc cài đặt riêng tư — ngoài 96)", "ho_so", "Xem cài đặt riêng tư",
        "GET /api/setting/me (12113) — bundle `getSettings()`: CHỈ tham số chung, không params. Đo trên Zalo thật 12/11/2026: trả 14 cài đặt "
        "(add_friend_via_contact/group/qr/phone, display_on_recommend_friend, display_seen_status, show_online_status, receive_message, "
        "accept_stranger_call, setting_show_stranger_msg_directly, view_birthday, quick_message_status, archived_chat_status, "
        "setting_2FA_status). Đọc xong sửa bằng update_settings.",
        "auth", "/api/setting/me", 12113, "GET", "none",
        [], lambda p, t, tt: None, body_unverified=False,
        no_params=True),
    "change_account_avatar": _op(
        92, "change_account_avatar", "ho_so", "Đổi ảnh đại diện",
        "POST files-wpa /api/profile/upavatar (11819). Client thật "
        "UPLOAD FILE (multipart field 'file'); params {clientId, "
        "language} (avatarSize/metaData chưa biết — không gửi).",
        "file", "/api/profile/upavatar", 11819, "POST_MULTIPART",
        "none",
        [{"key": "file", "label": "Ảnh đại diện (upload file)",
          "required": True}],
        _b_change_avatar),
    "get_avatar_list": _op(
        93, "get_avatar_list", "ho_so", "Xem ảnh đại diện đã dùng",
        "GET profile-wpa /api/social/avatar-list (12451) {page, "
        "albumId:\"0\", count, imei} — zca-js getAvatarList.",
        "profile", "/api/social/avatar-list", 12451, "GET", "none",
        [{"key": "count", "label": "Số lượng"},
         {"key": "page", "label": "Trang"}],
        _b_avatar_list, body_unverified=False),
    # --- Sticker (nhóm H) ---
    "send_sticker": _op(
        27, "send_sticker", "sticker", "Gửi sticker",
        "1-1: /api/message/sticker (11154) {stickerId, cateId, "
        "type, clientId, imei, toid}; nhóm: /api/group/sticker "
        "(11165). Body đã biết (+ ttl).",
        None, None, None, "POST", "both",
        [{"key": "sticker_id", "label": "Sticker ID",
          "required": True},
         {"key": "cate_id", "label": "Cate ID"},
         {"key": "sticker_type", "label": "Type"}],
        _b_sticker, body_unverified=False),
    "get_stickers": _op(
        73, "get_stickers", "sticker", "Xem danh mục sticker",
        "GET sticker-wpa /api/message/sticker/category/list "
        "(11155) — params AES của chuỗi rỗng.",
        "sticker", "/api/message/sticker/category/list", 11155,
        "GET", "none", [], _b_sticker_list, body_unverified=False),
    "get_stickers_detail": _op(
        74, "get_stickers_detail", "sticker", "Xem chi tiết bộ sticker",
        "GET sticker-wpa /api/message/sticker/category/detail "
        "(11156) {cid}.",
        "sticker", "/api/message/sticker/category/detail", 11156,
        "GET", "none",
        [{"key": "sticker_album", "label": "Album/Cate ID",
          "required": True}],
        _b_sticker_detail, body_unverified=False),
    # --- Nhắc hẹn / bảng tin (nhóm F) ---
    "create_reminder": _op(
        29, "create_reminder", "nhac", "Tạo nhắc hẹn",
        "1-1: POST board /api/board/oneone/create (12429) "
        "{objectData, imei}; nhóm: POST board "
        "/api/board/topic/create (12141). objectData {toUid/grid, "
        "type:0, color, emoji, startTime, duration:-1, params, "
        "needPin, repeat, creatorUid, src:1} — bundle + zca-js.",
        None, None, None, "POST", "both",
        [{"key": "title", "label": "Tiêu đề", "required": True},
         {"key": "content", "label": "Nội dung"},
         {"key": "remind_time", "label": "Thời gian nhắc "
          "(ISO-8601 hoặc epoch)", "required": True}],
        _b_reminder_create, body_unverified=False),
    "remove_reminder": _op(
        30, "remove_reminder", "nhac", "Xóa nhắc hẹn",
        "1-1: POST board /api/board/oneone/remove (12431) {uid, "
        "reminderId}; nhóm: POST board /api/board/topic/remove "
        "(12143) {grid, topicId, imei}.",
        None, None, None, "POST", "both",
        [{"key": "reminder_id", "label": "ID nhắc hẹn",
          "required": True}],
        _b_reminder_remove, body_unverified=False),
    "edit_reminder": _op(
        82, "edit_reminder", "nhac", "Sửa nhắc hẹn",
        "1-1: POST board /api/board/oneone/update (12430) "
        "{objectData}; nhóm: POST board /api/board/topic/update "
        "(12142) {grid, type, color, emoji, startTime, duration, "
        "params, needPin, topicId, repeat, imei} — bundle "
        "updateGroupTopicv2 + zca-js editReminder.",
        None, None, None, "POST", "both",
        [{"key": "topic_id", "label": "ID nhắc hẹn",
          "required": True},
         {"key": "title", "label": "Tiêu đề mới", "required": True},
         {"key": "remind_time", "label": "Thời gian nhắc mới"}],
        _b_reminder_edit, body_unverified=False),
    "get_reminder": _op(
        83, "get_reminder", "nhac", "Xem chi tiết nhắc hẹn",
        "GET board /api/board/topic/getReminder (12088) {eventId, "
        "imei}.",
        "board", "/api/board/topic/getReminder", 12088, "GET",
        "none",
        [{"key": "reminder_id", "label": "ID nhắc hẹn",
          "required": True}],
        _b_reminder_get, body_unverified=False),
    "get_list_reminder": _op(
        84, "get_list_reminder", "nhac", "Xem danh sách nhắc hẹn",
        "1-1: GET board /api/board/oneone/list (12432); nhóm: GET "
        "board /api/board/listReminder (12425). objectData "
        "JSON-str({uid|group_id, board_type:1, page, count, last_id, "
        "last_type}) — zca-js getListReminder.",
        None, None, None, "GET", "both", [], _b_reminder_list,
        body_unverified=False),
    "get_reminder_responses": _op(
        85, "get_reminder_responses", "nhac", "Xem phản hồi nhắc hẹn",
        "GET board /api/board/topic/listResponseEvent (12086) "
        "{eventId} (KHÔNG imei).",
        "board", "/api/board/topic/listResponseEvent", 12086, "GET",
        "none",
        [{"key": "reminder_id", "label": "ID nhắc hẹn",
          "required": True}],
        _b_reminder_responses, body_unverified=False),
    # --- Poll (nhóm, SERVICE-MAP §2.4) ---
    "create_poll": _op(
        79, "create_poll", "nhom", "Tạo bình chọn",
        "POST group-wpa /api/poll/create (12080) {group_id, "
        "question, options, expired_time, pinAct:false, "
        "allow_multi_choices, allow_add_new_option, "
        "is_hide_vote_preview, is_anonymous, poll_type:0, src:1, "
        "imei} — theo bundle Zalo PC + zca-js createPoll.",
        "group", "/api/poll/create", 12080, "POST", "group",
        [{"key": "question", "label": "Câu hỏi", "required": True},
         {"key": "options", "label": "Lựa chọn (cách nhau bằng dấu "
          "phẩy)", "required": True},
         {"key": "allow_multi_choices",
          "label": "Cho chọn nhiều (true/false)"},
         {"key": "allow_add_new_option",
          "label": "Cho thêm lựa chọn mới (mặc định true)"},
         {"key": "is_anonymous", "label": "Bình chọn ẩn danh (true/false)"},
         {"key": "hide_vote_preview",
          "label": "Ẩn kết quả khi chưa bình chọn (true/false)"},
         {"key": "expired_time",
          "label": "Hạn chót (ms epoch, 0 = không hết hạn)"}],
        _b_poll_create, body_unverified=False),
    "get_poll_detail": _op(
        80, "get_poll_detail", "nhom", "Xem chi tiết bình chọn",
        "GET group-wpa /api/poll/detail (12081) {poll_id, imei}.",
        "group", "/api/poll/detail", 12081, "GET", "group",
        [{"key": "poll_id", "label": "ID bình chọn",
          "required": True}],
        _b_poll_detail, body_unverified=False),
    "lock_poll": _op(
        81, "lock_poll", "nhom", "Khóa bình chọn",
        "POST group-wpa /api/poll/end (12089) {poll_id, imei}.",
        "group", "/api/poll/end", 12089, "POST", "group",
        [{"key": "poll_id", "label": "ID bình chọn",
          "required": True}],
        _b_poll_lock, body_unverified=False),
    "vote_poll": _op(
        None, "(bỏ phiếu — ngoài 96)", "nhom", "Bỏ phiếu bình chọn",
        "GET group-wpa /api/poll/vote (12084) {poll_id, "
        "option_ids, imei} — bundle SERVICE-MAP §2.4 + zca-js "
        "votePoll (pollId, optionId); unvote = option_ids rỗng "
        "(op này chỉ bỏ phiếu: cần ít nhất 1 lựa chọn).",
        "group", "/api/poll/vote", 12084, "GET", "group",
        [{"key": "poll_id", "label": "ID bình chọn",
          "required": True},
         {"key": "option_ids",
          "label": "ID lựa chọn (cách nhau bằng dấu phẩy)",
          "required": True}],
        _b_poll_vote, body_unverified=False),
    # --- Tin nhắn nhanh (nhóm, SERVICE-MAP §2.5) ---
    "add_quick_message": _op(
        86, "add_quick_message", "nhac", "Thêm tin nhắn nhanh",
        "GET QUICK_MESSAGE /api/quickmessage/create (12029) "
        "{keyword, message, imei} (media/type tùy chọn, bundle "
        "createQuickReplyItem). Domain lấy từ services map lúc login.",
        "quick_message", "/api/quickmessage/create", 12029, "GET",
        "none",
        [{"key": "keyword", "label": "Từ khóa", "required": True},
         {"key": "title", "label": "Nội dung", "required": True}],
        _b_qm_add, body_unverified=False),
    "get_quick_message": _op(
        87, "get_quick_message", "nhac", "Xem tin nhắn nhanh",
        "GET QUICK_MESSAGE /api/quickmessage/list (12025) "
        "{version:0, lang:0, imei}.",
        "quick_message", "/api/quickmessage/list", 12025, "GET",
        "none", [], _b_qm_list, body_unverified=False),
    "remove_quick_message": _op(
        88, "remove_quick_message", "nhac", "Xóa tin nhắn nhanh",
        "GET QUICK_MESSAGE /api/quickmessage/delete (12032) "
        "{itemIds:[...]}.",
        "quick_message", "/api/quickmessage/delete", 12032, "GET",
        "none",
        [{"key": "item_ids", "label": "ID (cách nhau bằng dấu phẩy)",
          "required": True}],
        _b_qm_delete, body_unverified=False),
    "update_quick_message": _op(
        89, "update_quick_message", "nhac", "Sửa tin nhắn nhanh",
        "GET QUICK_MESSAGE /api/quickmessage/update (12026) "
        "{itemId, keyword, message} (KHÔNG imei; media/type tùy "
        "chọn, bundle updateQuickReplyItem).",
        "quick_message", "/api/quickmessage/update", 12026, "GET",
        "none",
        [{"key": "item_id", "label": "ID", "required": True},
         {"key": "keyword", "label": "Từ khóa"},
         {"key": "title", "label": "Nội dung"}],
        _b_qm_update, body_unverified=False),
    # --- Nhãn (nhóm I) ---
    "get_labels": _op(
        90, "get_labels", "nhan", "Xem danh sách nhãn",
        "GET label-wpa /api/convlabel/get (12161) {imei}.",
        "label", "/api/convlabel/get", 12161, "GET", "none", [],
        _b_labels, body_unverified=False),
    "update_label": _op(
        None, "(gắn nhãn — ngoài 96)", "nhan", "Gắn nhãn cho hội thoại",
        "POST label-wpa /api/convlabel/update (12160) "
        "{labelData, version, imei}: gửi TOÀN BỘ danh sách nhãn đã sửa "
        "(lấy từ get_labels) cùng version của nó.",
        "label", "/api/convlabel/update", 12160, "POST", "none",
        [{"key": "label_data", "label": "Danh sách nhãn (JSON) đã sửa, "
          "lấy từ get_labels", "required": True},
         {"key": "version", "label": "Version của danh sách nhãn",
          "required": True}],
        _b_label_update, body_unverified=False),
    # --- Kiem chung phien (ngoai 96; loi H5 + I1) ---
    # zca-js auth/keepAlive (src/apis/auth/keepAlive.ts): GET
    # {zpwServiceMap.chat[0]}/keepalive, params AES {imei}, lenh
    # 11770, tra ve envelope hai lop (config_vesion). Domain "chat"
    # o day resolve ve protocol.CHAT_DOMAIN nhu cac op chat khac.
    "keepAlive": _op(
        None, "keepAlive", "khac", "Kiểm tra phiên còn sống",
        "GET chat /keepalive (11770) {imei} — hoi Zalo xem phien "
        "con song khong (zca-js auth/keepAlive). App dung de phat "
        "hien phien bi da (600/401/403) thay vi chi kiem "
        "session.json con zpw_sek.",
        "chat", "/keepalive", 11770, "GET", "none", [],
        _b_keepalive, body_unverified=False),
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
    "create_reminder": ("board", "/api/board/oneone/create", 12429,
                        "board", "/api/board/topic/create", 12141),
    "remove_reminder": ("board", "/api/board/oneone/remove", 12431,
                        "board", "/api/board/topic/remove", 12143),
    "edit_reminder": ("board", "/api/board/oneone/update", 12430,
                      "board", "/api/board/topic/update", 12142),
    "get_list_reminder": ("board", "/api/board/oneone/list", 12432,
                          "board", "/api/board/listReminder", 12425),
    "add_reaction": ("reaction", "/api/message/reaction", 12410,
                     "reaction", "/api/group/reaction", 12411),
}

_DOMAINS = {
    "chat": lambda: protocol.CHAT_DOMAIN,
    "group": lambda: protocol.GROUP_DOMAIN,
    "profile": lambda: protocol.PROFILE_DOMAIN,
    "convers": lambda: protocol.CONVERS_DOMAIN,
    "convers_web": lambda: protocol.CONVERS_WEB_DOMAIN,
    "friend": lambda: protocol.FRIEND_DOMAIN,
    "alias": lambda: protocol.ALIAS_DOMAIN,
    "label": lambda: protocol.LABEL_DOMAIN,
    "board": lambda: protocol.BOARD_DOMAIN,
    "sticker": lambda: protocol.STICKER_DOMAIN,
    "file": lambda: protocol.FILE_DOMAIN,
    "auth": lambda: protocol.AUTH_DOMAIN,
}

# Domain chi co trong services map (khong hard-code — xem module
# docstring). Key trong map: "reaction" / "quick_message" (enum
# domainType trong bundle); gia tri la URL day du hoac list URL
# (v3 map: lay phan tu dau).
_SERVICES_MAP_DOMAINS = ("reaction", "quick_message")
# Domain DU PHONG khi service_map cua phien PC (config zpw_service_map_new) khong co khoa do. Chi co bang chung moi duoc them:
# reaction -> zca-js (addReaction.js dung zpw_service_map_v3.reaction[0] cua phien web) VA thu that tren phien PC 11/11/2026
# (POST add_reaction «like» tra msgIds, phan ung hien tren tin that). quick_message chua co bang chung -> van tu choi.
_DOMAIN_FALLBACKS = {"reaction": "https://reaction.chat.zalo.me"}


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
# Genuine gap (SERVICE-MAP.md §5): 4, 5, 17–20, 21–23 (9 service)
# + 96 (QR web — QR PC đã native trong app).

_NOT_SUPPORTED = [
    # (addon_no, addon, group, status, reason)
    (1, "send_message", "tin_nhan", "chat",
     "Gửi text thuộc khung chat — chat.py làm (đường PC: "
     "1-1 /api/message/sms 11151, nhóm /api/group/sendmsg 11163, "
     "clientId NUMBER + ttl)."),
    (2, "send_file", "tin_nhan", "chat",
     "Đính kèm file thuộc khung chat (đường hai bước asyncfile: "
     "upload 11776/13000 + asyncfile/msg 11777/13001; "
     "sharefile_full 11146/11191 là đường chết, Zalo trả 405)."),
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
     "Gửi tin nhắn thoại thuộc khung chat (upload chunked "
     "12060/12063 + asyncfile/msg) — không phải gọi điện."),
    (71, "send_card", "tin_nhan", "chat",
     "Gửi danh thiếp thuộc khung chat: đường card user thường "
     "CHƯA lần riêng (chỉ có biến thể OA forwardContactOA "
     "11774/11827) — chưa implement, không bịa body."),
    (72, "send_link", "tin_nhan", "chat",
     "Gửi link thuộc khung chat (1-1 link 11286, nhóm sendlink "
     "11193) — chat.py send_link đã implement."),
    (75, "send_video", "tin_nhan", "chat",
     "Gửi video thuộc khung chat: chỉ có bước upload "
     "(12058/12061 + thumb); bước send sau upload CHƯA lần hết "
     "— chưa implement, không bịa endpoint."),
    (4, "get_logged_accounts", "khac", "zalobot",
     "Đa tài khoản chỉ có trên máy chủ zalobot (phiên web). "
     "App PC đơn tài khoản — tài khoản hiện tại xem ở /api/status."),
    (5, "get_account_details", "khac", "zalobot",
     "Chi tiết tài khoản theo account_selection — chỉ có trên "
     "máy chủ zalobot (phiên web). Gần nhất trên PC: "
     "/api/social/profile/me-v2 (chưa lần body)."),
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
     "QR kiểu PC app đang dùng (đăng nhập QR PC đã có sẵn: "
     "reqqr 11133 → getLoginInfo 11134)."),
    (34, "get_all_friends", "ho_so", "view",
     "Đã xem được: danh bạ Bạn bè (60 bạn, đúng thật)."),
    (40, "get_all_groups", "ho_so", "view",
     "Đã xem được: danh bạ Nhóm (6 nhóm, đúng thật)."),
]


def build_catalog():
    """Toàn bộ 96 service addon + các op ngoài 96 (quote, seen,
    fetchImportant, group link detail, label update, vote poll,
    reject friend request): mỗi entry có
    status để UI vẽ nút bấm hoặc trạng thái 'Chưa hỗ trợ' — không
    nút giả."""
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
    from . import zca_api
    from . import rich_text
    out = dict(CATALOG)
    out["zca"] = zca_api.catalog()
    # Bang chon cho giao dien (cung nguon voi dich vu HA): emoji, bieu tuong cam xuc, kieu chu mac dinh/auto.
    out["ui"] = {"emoji": dict(rich_text.EMOJI), "reactions": sorted(REACTION_ICONS),
                 "style": {"size": list(rich_text.STYLE_SIZE), "color": list(rich_text.STYLE_COLOR), "toggle": list(rich_text.STYLE_TOGGLE),
                           "auto_color": list(rich_text.STYLE_AUTO_COLOR)}}
    return out

# ------------------------------------------------------------------ client
class Services:
    """Client gọi endpoint PC cho các op trong OPS (giống
    Signaling/Contacts: cùng transport, cùng envelope hai lớp).
    Không đụng signaling.py hay body requestcall."""

    def __init__(self, http_get, http_post, device_id, zpw_enk,
                 service_map=None, http_post_multipart=None):
        self.http_get = http_get
        self.http_post = http_post
        self.device_id = device_id
        self.zpw_enk = zpw_enk
        # Services map server tra ve luc login (config
        # zpw_service_map_new) — chi dung de resolve REACTION /
        # QUICK_MESSAGE, khong hard-code domain (xem _domain_for).
        self.service_map = service_map or {}
        self.uid = ""                      # uid của phiên (server gán): mặc định ownerId cho tin của ta
        if http_post_multipart is None:
            http_post_multipart = getattr(
                http_get, "http_post_multipart", None)
        self.http_post_multipart = http_post_multipart
        self._logged_domains = set()

    def _domain_for(self, action, domain_key):
        """URL goc cho mot domain key. REACTION / QUICK_MESSAGE
        resolve qua services map (log domain resolve duoc, chi log
        host — khong log params/gia tri); map thieu thi dung
        _DOMAIN_FALLBACKS neu co bang chung (reaction), con lai tu
        choi ro rang thay vi doan domain."""
        if domain_key in _SERVICES_MAP_DOMAINS:
            raw = (self.service_map or {}).get(domain_key)
            if isinstance(raw, list):
                raw = raw[0] if raw else None
            if (not raw or not isinstance(raw, str)) \
                    and domain_key in _DOMAIN_FALLBACKS:
                raw = _DOMAIN_FALLBACKS[domain_key]
            if not raw or not isinstance(raw, str):
                raise UnsupportedService(
                    action, "unsupported",
                    "Domain %s chưa có trong services map do server "
                    "trả về lúc đăng nhập (config "
                    "zpw_service_map_new) — không đoán domain; "
                    "cần đăng nhập lại để lấy map." % domain_key)
            url = raw.strip()
            if "://" not in url:
                url = "https://" + url
            url = url.rstrip("/")
            host = urllib.parse.urlparse(url).netloc or url
            key = (domain_key, host)
            if key not in self._logged_domains:
                self._logged_domains.add(key)
                log.info("svc domain %s resolved to %s",
                         domain_key, host)
            return url
        return _DOMAINS[domain_key]()

    def _aes(self, raw_json):
        return session_aes_encrypt(self.zpw_enk, raw_json)

    def _unwrap(self, status, payload, where):
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("svc %s: network status=%s"
                               % (where, status))
        if payload.get("error_code") != 0:
            raise ServiceError(
                where, payload.get("error_code"),
                payload.get("error_message", ""))
        try:
            return decode_postlogin_data(payload, self.zpw_enk)
        except RuntimeError as e:
            # Loi inner (vd. 212): doi sang ServiceError de caller
            # phan biet ma loi; van la RuntimeError nen code cu bat
            # RuntimeError khong doi.
            import re as _re
            m = _re.search(r"inner error_code=(\d+)", str(e))
            if m:
                raise ServiceError(where, int(m.group(1)), str(e))
            raise

    def _encode_body(self, body):
        """params value: dict -> JSON; str -> raw (vd. "" cua
        get_stickers — params AES cua chuoi rong, khong phai
        JSON '""')."""
        if isinstance(body, str):
            return body
        return json.dumps(body, separators=(",", ":"), ensure_ascii=False)

    def _url(self, domain, path, body, no_params=False):
        qs = urllib.parse.urlencode(protocol.common_params())
        if no_params:
            return "%s%s?%s" % (domain, path, qs)
        enc = self._aes(self._encode_body(body))
        return "%s%s?%s&params=%s" % (
            domain, path, qs, urllib.parse.quote(enc, safe=""))

    def _get(self, domain, path, body, no_params=False):
        url = self._url(domain, path, body, no_params=no_params)
        status, payload = self.http_get(url, timeout=30)
        return self._unwrap(status, payload, "GET %s" % path)

    def _post(self, domain, path, body):
        url = "%s%s?%s" % (domain, path, urllib.parse.urlencode(
            protocol.common_params()))
        form = "params=" + urllib.parse.quote(
            self._aes(self._encode_body(body)), safe="")
        if self.http_post is None:
            raise RuntimeError("svc: POST transport missing for %s"
                               % path)
        status, payload = self.http_post(url, form, timeout=30)
        return self._unwrap(status, payload, "POST %s" % path)

    def _post_query(self, domain, path, body):
        """POST nhung params nam trong QUERY URL, khong co form
        body (update_auto_delete_chat 12023 — bundle _post(i, null,
        null, 12023))."""
        url = self._url(domain, path, body)
        if self.http_post is None:
            raise RuntimeError("svc: POST transport missing for %s"
                               % path)
        status, payload = self.http_post(url, "", timeout=30)
        return self._unwrap(status, payload, "POST %s" % path)

    def _post_multipart(self, domain, path, body, filename, mime,
                        data):
        """POST multipart fileContent (doi avatar): params AES o
        query, file o FormData — giong chat.send_file."""
        if self.http_post_multipart is None:
            raise RuntimeError(
                "svc: multipart transport missing for %s" % path)
        url = self._url(domain, path, body)
        payload_bytes, ctype = build_multipart(
            {}, [("fileContent", filename, mime, data)])
        status, payload = self.http_post_multipart(
            url, payload_bytes, ctype, timeout=60)
        return self._unwrap(status, payload, "POST %s" % path)

    # -- cac op can nhieu buoc ---------------------------------------
    def _set_pinned(self, params, tid, ttype):
        """set_pinned_conversation: doc GET /api/pinconvers/list
        lay version + danh sach hien tai (id co prefix 'u'/'g'),
        tinh danh sach moi, cat vao params de body_fn gui POST
        update. Loi 212 = server chua co danh sach ghim -> bat dau
        tu rong, version 0 (theo PinDataManager trong bundle)."""
        if params.get("pinned") is None:
            raise ValueError("set_pinned_conversation: thiếu tham "
                             "số bắt buộc pinned")
        pinned = _bool_param(params, "pinned", True)
        domain = self._domain_for("set_pinned_conversation",
                                  "convers")
        try:
            data = self._get(domain, "/api/pinconvers/list",
                             {"imei": self.device_id})
        except ServiceError as e:
            if e.code == 212:
                data = {"version": 0, "conversations": []}
            else:
                raise
        version, convs = 0, []
        if isinstance(data, dict):
            version = data.get("version") or 0
            convs = data.get("conversations") or []
        elif isinstance(data, list):
            convs = data
        try:
            version = int(version)
        except (TypeError, ValueError):
            version = 0
        mine = ("g" if ttype == "group" else "u") + tid
        new_list = [c for c in convs if c != "m1"]
        if pinned:
            if mine not in new_list:
                new_list.append(mine)
        else:
            new_list = [c for c in new_list if c != mine]
        params["_pin_version"] = version
        params["_pin_conversations"] = new_list

    def _forward_message(self, params):
        """forward_message: chuyen tiep NOI DUNG CHU toi nhieu thread bang mforward (bundle `forwardMultiMessage` 12440/12442 + zca-js
        forwardMessage), domain FILE. Body: user {toIds:[{clientId,toUid,ttl}], imei, ttl, msgType:"1", totalIds, msgInfo:JSON({message}),
        decorLog}; nhom {grids:[{clientId,grid,ttl}], ttl, msgType, totalIds, msgInfo, decorLog}. Ban cu chi gui khung {toId|grid, imei}
        (khong co noi dung) toi endpoint don nen khong chuyen duoc gi. Anh/file can transform theo loai tin — chua ho tro."""
        dests = _csv(_need(params, "dest_thread_ids", "forward_message"))
        dtype = (params.get("type") or "user").lower()
        if dtype not in ("user", "group"):
            raise ValueError("forward_message: type phải là user hoặc group")
        message = str(_need(params, "message", "forward_message")).strip()
        if not message:
            raise ValueError("forward_message: message (nội dung chữ cần chuyển tiếp) không được rỗng")
        ttl = _int_param(params, "ttl", 0, "forward_message")
        client_id = str(int(time.time() * 1000))
        msg_info = {"message": message}
        if params.get("reference"):                      # {id, ts, fwLvl} cua tin goc: Zalo hien nhan «Da chuyen tiep»
            ref = params["reference"]
            msg_info["reference"] = json.dumps({"type": 3, "data": json.dumps(ref, separators=(",", ":"))}, separators=(",", ":"))
        decor = None
        if params.get("reference"):
            ref = params["reference"]
            leg = {"st": 1, "ts": ref.get("ts"), "id": ref.get("id")}
            decor = {"fw": {"pmsg": dict(leg), "rmsg": dict(leg), "fwLvl": ref.get("fwLvl")}}
        common = {"ttl": ttl, "msgType": "1", "totalIds": len(dests),
                  "msgInfo": json.dumps(msg_info, separators=(",", ":"), ensure_ascii=False),
                  "decorLog": json.dumps(decor, separators=(",", ":"))}
        if dtype == "group":
            body = dict({"grids": [{"clientId": client_id, "grid": d, "ttl": ttl} for d in dests]}, **common)
            path = "/api/group/mforward"
        else:
            body = dict({"toIds": [{"clientId": client_id, "toUid": d, "ttl": ttl} for d in dests], "imei": self.device_id}, **common)
            path = "/api/message/mforward"
        domain = self._domain_for("forward_message", "file")
        return {"results": [self._post(domain, path, body)]}

    def dispatch(self, action, params, files=None):
        """Chạy một op: trả về data đã giải mã từ envelope hai lớp.
        Raises: UnknownAction, UnsupportedService, ValueError
        (thiếu tham số), RuntimeError (lỗi mạng/server Zalo).
        files: {"file": (filename, mime, bytes)} cho cac op upload
        (multipart) — lay tu HTTP multipart hoac truyen truc tiep
        o test."""
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
        if self.uid:
            params["_uid"] = self.uid
        if files and "file" in files:
            params["_file"] = files["file"]
        if action == "forward_message":
            return self._forward_message(params)
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
        if action == "set_pinned_conversation":
            self._set_pinned(params, tid, ttype)
        body = spec["body_fn"](params, tid, ttype)
        domain_key, path, _code = _resolve(action, spec, ttype)
        if path is None:
            raise UnsupportedService(
                action, "unsupported",
                "Thao tác này chưa có endpoint cho nhóm — cần lần "
                "thêm, không bịa path.")
        domain = self._domain_for(action, domain_key)
        method = spec["method"]
        if method == "GET":
            return self._get(domain, path, body,
                             no_params=spec.get("no_params", False))
        if method == "POST":
            return self._post(domain, path, body)
        if method == "POST_QUERY":
            return self._post_query(domain, path, body)
        if method == "POST_MULTIPART":
            filename, mime, data = params["_file"]
            return self._post_multipart(domain, path, body, filename,
                                        mime, data)
        raise RuntimeError("svc: method lạ %s" % method)


def make_services(state):
    """(Services, ctx) cho phien Zalo hien tai — dung chung cho handle_svc va cac
    tinh nang giao dien (nhan dan...)."""
    from . import server as _server_mod
    sess = state.session
    transport = _server_mod.make_transport(sess["zpw_sek"])
    svc = Services(transport, transport.http_post,
                   sess["device_id"], sess["zpw_enk"],
                   service_map=sess.get("service_map") or {},
                   http_post_multipart=transport.http_post_multipart)
    return svc, {"imei": sess.get("device_id", ""), "uid": sess.get("uid", "")}


def handle_svc(state, action, body, files=None):
    """Móc duy nhất từ server.py do_POST /api/svc/<action>.
    `state` là AppState (đã qua _require_login ở server).
    Trả (http_status, json_obj)."""
    from . import server as _server_mod  # tránh import vòng lúc load
    sess = state.session
    transport = _server_mod.make_transport(sess["zpw_sek"])
    svc = Services(transport, transport.http_post,
                   sess["device_id"], sess["zpw_enk"],
                   service_map=sess.get("service_map") or {},
                   http_post_multipart=transport.http_post_multipart)
    params = dict(body or {})
    params["_uid"] = sess.get("uid", "")
    if action == "mark_seen":
        # «Da xem» di cung duong v2 nhu WebUI (tin goc lay tu kho tin); body cu cua op nay chua duoc xac minh (SERVICE-MAP §6).
        try:
            from . import chat as _chat_mod
            tid, ttype = _thread(params, action)
            chat = _chat_mod.Chat(transport, sess["device_id"], sess["zpw_enk"])
            data = chat.mark_seen(ttype, tid, _csv(params.get("msg_ids")), store=getattr(state, "message_store", None),
                                  own_uid=sess.get("uid", ""))
        except ValueError as e:
            return 400, {"error": str(e)}
        except Exception as e:  # noqa: BLE001 - loi Zalo/mang -> 502
            return 502, {"error": str(e)}
        return 200, {"ok": True, "action": action, "data": data}
    try:
        data = svc.dispatch(action, params, files=files)
    except UnknownAction as e:
        from . import zca_api
        if zca_api.registry().get(action) is None:
            return 404, {"error": str(e)}
        try:
            ctx = {"imei": sess.get("device_id", ""), "uid": sess.get("uid", "")}
            data = zca_api.ZcaApi(svc, ctx).call(action, params)
        except zca_api.ZcaManual as m:
            return 409, {"error": m.reason, "service": m.name,
                         "status": "manual"}
        except zca_api.ZcaError as m:
            return 400, {"error": str(m)}
        except ValueError as m:
            return 400, {"error": str(m)}
        except Exception as m:  # noqa: BLE001 - loi Zalo/mang -> 502
            return 502, {"error": str(m)}
        return 200, {"ok": True, "action": action, "data": data,
                     "source": "zca", "unverified": True}
    except UnsupportedService as e:
        return 409, {"error": e.reason, "service": e.service,
                     "status": e.status}
    except ValueError as e:
        return 400, {"error": str(e)}
    except Exception as e:  # noqa: BLE001 - lỗi Zalo/mạng -> 502
        return 502, {"error": str(e)}
    return 200, {"ok": True, "action": action, "data": data}
