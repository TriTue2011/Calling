"""Zalo PC wire protocol: endpoints, request builders, response parsers.

Evidence: Zalo PC 26.11.10 renderer bundle (see bao-cao.md).
All requests are HTTPS GET unless noted. Post-login calls carry
`params=<session-AES base64 JSON>`; login calls carry either the
ParamCipher envelope or plaintext params + signkey (see crypto.py).

Common query params on every API call:
    zpw_ver=<apiVersion> & zpw_type=<apiType>
Defaults for this build: apiVersion=695, apiType=30 (an INTEGER, not
the string "embed" — see the note on API_TYPE below; the old
"embed" value is why groups failed twice with 602, §7d in bao-cao.md).

Group list (addon path, §7i in bao-cao.md): the addon (zca-js)
lists groups in two steps — GET {group}/api/group/getlg/v4 (no
body, no pagination) returns {version, gridVerMap: {groupId:
version}}, then POST {group}/api/group/getmg-v2 with
{gridVerMap: {groupId: 0}} returns {gridInfoMap} with the names,
avatars and topMember lists. Both endpoints exist in the PC
client's own command table too (codes 12027/12028). The old
getlg/v3 list path was the PC client's list path, NOT the addon's;
per the user's "lấy y nguyên" direction the app now follows the
addon path only — v3 is not kept as a fallback.
"""

import json
import os
import threading
import time
import urllib.parse

AUTH_DOMAIN = "https://wpa.zalo.me"
CHAT_DOMAIN = "https://chat-wpa.zalo.me"
VOICECALL_DOMAIN = "https://voicecall-wpa.zalo.me"
CONVERS_DOMAIN = "https://convers-wpa.api.zalo.me"
# Cài đặt tự xoá (getConvers/updateConvers) của phiên kiểu web nằm ở máy chủ này; `convers-wpa.api.zalo.me` trả 404/405 (đo 13/11).
CONVERS_WEB_DOMAIN = "https://tt-convers-wpa.chat.zalo.me"
PROFILE_DOMAIN = "https://profile-wpa.zalo.me"
GROUP_DOMAIN = "https://group-wpa.zalo.me"
# Cac domain con lai trong bang lenh (SERVICE-MAP.md §1): chi
# hard-code trong bundle — REACTION va QUICK_MESSAGE KHONG co o
# day, chung chi co trong services map server tra ve luc login
# (xem services._domain_for — khong hard-code).
FRIEND_DOMAIN = "https://friend-wpa.zalo.me"
ALIAS_DOMAIN = "https://alias-wpa.api.zalo.me"
LABEL_DOMAIN = "https://label-wpa.api.zalo.me"
BOARD_DOMAIN = "https://groupboard-wpa.api.zalo.me"
STICKER_DOMAIN = "https://sticker-wpa.zalo.me"
FILE_DOMAIN = "https://files-wpa.zalo.me"

def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# Mặc định 695/30 (giá trị của bundle web). Zalo PC 26.11.10 THẬT dùng zpw_type=24 và zpw_ver=693 (nhật ký mạng Chromium
# 13/11/2026: 138 yêu cầu). Điện thoại có thể đối xử bên khai type 30 như Zalo Web (không cho chuyển video, camera «tắt»):
# thử ZALO_PC_API_TYPE=24 ZALO_PC_API_VERSION=693 (CHƯA đo thật trên cuộc gọi).
API_VERSION = _env_int("ZALO_PC_API_VERSION", 695)
# apiType is a NUMBER. Bundle evidence (compact-app-pc bundle,
# Zalo PC 26.11.10):
#   config literal: apiVersion:695,
#                   apiType:"embed"===__ZaBUNDLENAME__?31:30
#   __ZaBUNDLENAME__ for this bundle is "compact-app-pc" — proven by
#   the startup guard `if(!("compact-app-pc"===__ZaBUNDLENAME__))
#   return;` before "Starting compact application".
#   "embed" === "compact-app-pc" is false, so apiType = 30.
#   Common params are built as
#   re={zpw_ver:r.default.apiVersion, zpw_type:r.default.apiType},
#   i.e. zpw_ver=695 & zpw_type=30 on every post-login call
#   (friends, groups, voicecall) and in the login envelope
#   (encryptParam: n.type=r.default.apiType).
#   The getServerInfo response carries no top-level type /
#   client_version (probe 2026-11-05: error_code 0, no such keys),
#   so nothing overrides these defaults.
# The 2026-11-05 fixes read this ternary as apiType="embed" and sent
# zpw_type=embed. Friends (profile-wpa) accepted it, but group-wpa
# validates zpw_type strictly and answered 602 "zpw_type bị thiếu
# hoặc không đúng" — twice, for both getlg v1 and getlg/v3. Sending
# the correct numeric 30 is the fix.
API_TYPE = _env_int("ZALO_PC_API_TYPE", 30)
LANGUAGE = "vi"

# API codes (QoS/logging ids the client sends alongside each call).
CODE_REQQQR = 11133
CODE_GET_SERVER_INFO = 11323
CODE_GET_LOGIN_INFO = 11134
CODE_LOGOUT = 11135
CODE_GET_FRIENDS = 11137
CODE_GET_GROUPS_V4 = 12027
CODE_GET_INFO_MULTI_GROUP = 12028
CODE_SETTING_ME = 12113

# Voicecall path -> code (internal signal code = code - 10900-ish mapping
# used by the native bridge: 401=requestcall, 416=request, 407=ringring,
# 402=answer, 408=answerack, 405=cancel, 409=endcall, 411/412/413/414=hold).
VOICECALL = {
    "requestcall": 11300,
    "request": 11301,
    "ringring": 11302,
    "answer": 11303,
    "answerack": 11304,
    "cancel": 11305,
    "endcall": 11306,
    "holdreq": 11307,
    "holdresp": 11308,
    "unholdreq": 11309,
    "unholdresp": 11310,
}

# Group voicecall uses SEPARATE endpoints + codes (native bridge
# dispatch: case 12433 -> requestCallGroup, 12434 -> sendRequestCall
# Group, ...; command table maps 12433 -> /api/voicecall/group/
# requestcall). A group call is NOT a 1-1 requestcall with a group id
# as calleeId: the endpoint, the body shape and the identifier are
# all different. The target is identified by threadID, exactly like
# the addon (zca-js ThreadType: User=0, Group=1; HA sendMessage
# passes threadId + type): 1-1 threadId = userId, group threadId =
# groupId (raw, no "group" prefix).
VOICECALL_GROUP = {
    "requestcall": 12433,
    "request": 12434,
    "adduser": 12435,
    "answer": 12436,
    "cancel": 12437,
    "endcall": 12438,
    "ringring": 12439,
}

# Call-type values carried by `typeRequest` in requestcall (11300)
# and group/requestcall (12433). Bundle evidence (compact-app-pc,
# Zalo PC 26.11.10, renderer class wZ — the call helper):
#   makeCall(e, t=isVideo, n=isGroup, ...):
#       o = n ? (t ? 6 : 5) : (t ? 3 : 1)
#   i.e. 1-1 audio=1, 1-1 video=3, group audio=5, group video=6.
#   The renderer sends the native engine
#       {type:"request", command:"makeCall",
#        data:{partner, type:o, groupInfo}}
#   and the engine's signal 401 carries that value back as `type`
#   (native bridge dispatch: case 401 -> requestCall(n.calleeId,
#   n.callId, n.codec, n.type)), which the renderer forwards as
#   `typeRequest` in the requestCall body. The UI's DO_CALL action
#   dispatches makeCall(false, conversation) — audio — so a 1-1
#   audio call is typeRequest=1, a group audio call is 5. There is
#   NO 0 anywhere in this vocabulary: the pre-fix code sent
#   typeRequest=0, which the server answered with inner 114
#   "Tham số không hợp lệ" on a real 1-1 call (2026-11-05 17:31).
#   This app only places audio calls, so the server derives 1/5
#   from the thread type (video 3/6 is documented here, not sent).
# Chuoi codec tren day la MANG JSON (khong phai ten tran "opus"). Mau that
# bat tu cuoc goi den cua client Zalo chinh thuc ngay 09/11/2026: 11300
# khai danh sach codec cua may goi, 11301 khai codec da chon, deu la
# chuoi JSON nay; server moi chuyen tiep cho may nhan (params.codec) va
# may nhan chi do chuong khi doc duoc. App chi giai ma duoc opus 16 kHz
# mono (audioSampleRate 16000), nen chi khai dung codec do.
DEFAULT_CODEC = ('[{"dynamicFptime":0,"frmPtime":20,'
                 '"name":"opus/16000/1","payload":112}]')
# Codec video client that khai trong extendData.video.codec cua cuoc
# goi video (mau that 09/11/2026): h264 payload 97.
VIDEO_CODEC = [{"name": "h264", "payload": 97}]
CALL_TYPE_AUDIO_1_1 = 1
CALL_TYPE_VIDEO_1_1 = 3
CALL_TYPE_AUDIO_GROUP = 5
CALL_TYPE_VIDEO_GROUP = 6
CALL_TYPES_1_1 = (CALL_TYPE_AUDIO_1_1, CALL_TYPE_VIDEO_1_1)
CALL_TYPES_GROUP = (CALL_TYPE_AUDIO_GROUP, CALL_TYPE_VIDEO_GROUP)


def common_params(api_version=API_VERSION, api_type=API_TYPE):
    return {"zpw_ver": api_version, "zpw_type": api_type}


def build_url(base, path, params):
    qs = urllib.parse.urlencode(params)
    return "%s%s?%s" % (base, path, qs)


def unix_now():
    return int(time.time())


# ---------------------------------------------------------------- clientId
# clientId cua moi tin gui: JSON NUMBER, epoch-ms tang don dieu
# (SERVICE-MAP.md §3.1, module NMlV trong bundle: next() tra ve
# Date.now(), neu trung thi +1). Code cu gui string ("ms-hex6" o
# chat.py, str(ms) o services.py) — sai kieu JSON, la nghi pham
# so 1 cua loi 114 (cung ho voi lesson callId 114). Generator
# dung chung cho moi lan gui trong phien (text/file/anh/voice/
# sticker/quote/reaction), giong client that; thread-safe vi
# server chay ThreadingHTTPServer.
_CLIENT_ID_LOCK = threading.Lock()
_LAST_CLIENT_ID = 0


def new_client_id():
    """So nguyen epoch-ms tang don dieu, dung lam clientId."""
    global _LAST_CLIENT_ID
    with _CLIENT_ID_LOCK:
        now = int(time.time() * 1000)
        if now <= _LAST_CLIENT_ID:
            now = _LAST_CLIENT_ID + 1
        _LAST_CLIENT_ID = now
        return now


# ---------------------------------------------------------------- QR login
def reqqr_params(device_id, computer_name, logged_uids, language=LANGUAGE,
                 self_g=0, qr_form=0):
    """Plain (pre-encryption) reqqr parameters."""
    return {
        "language": language,
        "client_time": unix_now(),
        "imei": device_id,
        "computer_name": computer_name,
        "logged_uids": logged_uids,
        "self_g": self_g,
        "qr_form": qr_form,
    }


def parse_qr_data(data):
    """reqqr response `data` -> QR record (Qe parser in the client)."""
    data = data or {}
    return {
        "base64_qr": data.get("base64_qr", ""),
        "chk_wait_scan": data.get("chk_wait_scan", ""),
        "chk_wait_cfirm": data.get("chk_wait_cfirm", ""),
        "qr_retry": data.get("qr_retry", 0),
        "qr_timeout": data.get("qr_timeout", 0),
        "token_id": data.get("token_id", ""),
        "ntk": data.get("ntk", ""),
        "qr_cnt": data.get("qr_cnt", ""),
        "uid": data.get("uid", ""),
        "master_id": data.get("master_id", ""),
        "regen_qr": data.get("regen_qr", 0),
    }


def parse_scan_event(data):
    """chk_wait_scan event payload (je parser in the client)."""
    data = data or {}
    link = data.get("link_data") or {}
    return {
        "avatar": data.get("avatar", ""),
        "display_name": data.get("display_name", ""),
        "enc_link_data": link.get("enc_link_data", ""),
        "enc_link_hmac": link.get("enc_link_hmac", ""),
    }


def parse_confirm(data):
    """chk_wait_cfirm payload: the session grant."""
    data = data or {}
    return {
        "uid": data.get("uid", ""),
        "dkey": data.get("dkey", ""),
        "phonenum": (data.get("profile") or {}).get("phonenum", ""),
        "need_sync_msg": data.get("needSyncMsg", False),
        "cptch_cert": data.get("cptch_cert", ""),
        "zpw_sek": data.get("zpw_sek", ""),
        "zpw_kt": data.get("zpw_kt", ""),
        "devices": data.get("devices", []),
    }


def logininfo_params(device_id, computer_name, language=LANGUAGE):
    """Plain (pre-envelope) getLoginInfo parameters, exactly as the PC
    client sends them (API class getLoginInfo in the renderer bundle):
    imei, computer_name, language, ts in milliseconds. The caller wraps
    these in the login envelope (type/client_version/signkey, encrypted
    when a param cipher key is configured) — getLoginInfo is a *login*
    API, so it does NOT use the post-login zpw_ver/zpw_type params."""
    return {
        "imei": device_id,
        "computer_name": computer_name,
        "language": language,
        "ts": int(time.time() * 1000),
    }


# ---------------------------------------------------------------- voicecall
def voicecall_url(path, extra_common=None):
    params = common_params()
    if extra_common:
        params.update(extra_common)
    return "%s/api/voicecall/%s?%s" % (
        VOICECALL_DOMAIN, path, urllib.parse.urlencode(params))


def voicecall_params(path, body, session_aes):
    """Full voicecall GET url: common params + params=<AES JSON>."""
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    enc = session_aes(raw)
    # encodeURIComponent parity: quote() with safe="" encodes '/' as %2F
    # (the default safe="/" left raw '/' in the base64 value, unlike the
    # real client). Same fix as contacts._url_with_params.
    return voicecall_url(path) + "&params=" + urllib.parse.quote(enc, safe="")


def vc_requestcall(callee_id, call_id, codec, type_request, device_id):
    """Body of requestcall (code 11300), exactly as the PC client
    sends it (bundle class wZ: static requestCall(e,t,n,a) ->
    {calleeId:e, callId:t, codec:n ?? "[]", typeRequest:a,
    imei:getZaloClientID()}):
    - calleeId: the callee's userId as a STRING. (The JS renderer
      must carry it as a string: real threadIds are 19-digit and
      exceed the JS safe-integer range 2**53, so a JSON number
      would lose precision. The native engine receives the partner
      id as a JS string from makeCall data.partner[].id.)
    - callId: a JSON NUMBER in uint32 range. Native evidence:
      ZaloCall.exe `_initCallConfig ... callId = %u` (also
      `userId = %u`, `partnerId = %u`) — the engine stores callId
      as a uint32, and the renderer stringifies the native signal
      object, so the wire value is a number. The pre-fix code sent
      a 13-digit STRING (Date.now() millis) — wrong type AND out
      of uint32 range. This app sends epoch seconds (fits uint32;
      see server._normalize_call_id).
    - codec: "[]" is the client's own documented fallback (n ??
      "[]") when the native engine supplies no codec list, so it
      is kept — the engine normally supplies its real list. The
      real list format IS now known (zca-js ZRTPPacketCodec.ts:279
      DEFAULT_ZALO_AUDIO_CODEC, softtyos v2.3.13 — bao cao
      outbox/zca-js-tong-hop.md §4.4/§7.2): the JSON list string
      '[{"dynamicFptime":0,"frmPtime":20,"name":"opus/16000/1",
      "payload":112}]'. The app sends that list (see
      media_endpoints.DEFAULT_ZALO_AUDIO_CODEC, used by server.py
      step 1 and for_call step 2); "[]" survives only as the
      factory fallback when no codec is supplied at all, matching
      zca-js requestVoiceCall (options.codec ?? "[]").
    - typeRequest: 1 for a 1-1 AUDIO call (3 video) — never 0.
      The pre-fix 0 is the primary 114 suspect (§7k)."""
    return {"calleeId": callee_id, "callId": call_id,
            "codec": codec if codec is not None else DEFAULT_CODEC,
            "typeRequest": type_request, "imei": device_id}


def vc_requestcall_group(group_id, call_id,
                         type_request=CALL_TYPE_AUDIO_GROUP, data=None,
                         partners=None):
    """Body of group/requestcall (code 12433), exactly as the PC
    client sends it: {groupId, callId, typeRequest, data, partners}
    to /api/voicecall/group/requestcall. NOTE: no imei field (unlike
    the 1-1 requestcall). groupId is the RAW group id = the threadId
    of the group thread (addon/zca-js ThreadType Group=1). `partners`
    is the member userIds to ring; it comes from the group's
    topMember list, loaded via getmg-v2 when the contacts were
    fetched (see contacts.groups). topMember may be partial
    (hasMoreMember) — the full member list via getgi/v2 is the
    follow-up if a large group's call misses members.
    typeRequest is 5 for a group AUDIO call (6 video) — the makeCall
    enum (see CALL_TYPE_* above); the pre-fix 0 was invalid here
    too, same 114 as the 1-1 path. callId is a JSON number in
    uint32 range, same as vc_requestcall (native `%u`)."""
    return {"groupId": group_id, "callId": call_id,
            "typeRequest": type_request, "data": data,
            "partners": partners if partners is not None else []}


def vc_request(callee_id, rtcp_address, rtp_address, codec, session,
               call_id, device_id, extend_data=None):
    body = {"calleeId": callee_id, "rtcpAddress": rtcp_address,
            "rtpAddress": rtp_address, "codec": codec, "session": session,
            "callId": call_id, "imei": device_id}
    if extend_data:
        body["extendData"] = extend_data
        body["subCommand"] = 3
    return body


def vc_request_group(callee_id, call_id, call_type, data, session,
                     partners, group_id):
    """Body of group/request (code 12434), exactly as the PC client
    sends it (bundle class wZ: static sendRequestCallGroup(e,t,n,a,i,
    r,o) -> {calleeId:e, callId:t, callType:n, data:a, session:i,
    partners:r, groupId:o} to /api/voicecall/group/request):
    - calleeId: the group's id. CHUA XAC MINH TU BUNDLE — the engine
      signal (handleSendSignal case 12434) carries calleeId as a
      separate field from groupId, but its VALUE is not visible in
      the renderer excerpt; the group itself is the callee of a
      group call, so groupId is the most plausible value. The live
      test will confirm (a wrong calleeId should draw an inner
      error like 114 did for requestcall).
    - callType: 5 for group AUDIO (6 video), same enum as
      requestcall.
    - session / data / partners: the media-session material from
      the native engine (see media_endpoints.py); partners is the
      member userIds to ring. No imei field (unlike the 1-1
      request) and no extendData/subCommand pair — the group
      variant carries no such fields in the bundle."""
    return {"calleeId": callee_id, "callId": call_id,
            "callType": call_type, "data": data, "session": session,
            "partners": partners if partners is not None else [],
            "groupId": group_id}


def vc_ringring(caller_id, call_id, device_id):
    return {"callerId": caller_id, "callId": call_id, "status": 0,
            "imei": device_id}


def vc_answer(caller_id, call_id, status, codec, rtcp_address, rtp_address,
              session_id, extend_data=None):
    body = {"callerId": caller_id, "callId": call_id, "status": status,
            "codec": codec or "", "rtcpAddress": rtcp_address,
            "rtpAddress": rtp_address, "session_id": session_id}
    if extend_data:
        body["extendData"] = extend_data
        body["subCommand"] = 3
    return body


def vc_answerack(callee_id, call_id, device_id):
    return {"calleeId": callee_id, "callId": call_id, "status": 0,
            "imei": device_id}


def vc_cancel(caller_id, call_id, call_type, device_id):
    return {"callerId": caller_id, "callId": call_id, "callType": call_type,
            "status": 0, "imei": device_id}


def vc_endcall(uid_to, call_id, device_id):
    return {"uidTo": uid_to, "callId": call_id, "status": 3,
            "imei": device_id}


def vc_logendcall(call_id, partner_id, status, logdata, duration, role, device_id):
    """Body of logendcall (11311, signal 406): ghi ket qua cuoc goi cho lich su chat. Giong het sendLogEndCall cua Zalo PC 26.11.10:
    {call_id, partner_id, status, logdata, duration, role, imei}; status 50 da noi may, 103 nguoi goi huy / het gio, 160 tu choi;
    role true = ta la ben goi; logdata la chuoi JSON thong ke."""
    return {"call_id": call_id, "partner_id": str(partner_id), "status": status, "logdata": logdata,
            "duration": duration, "role": bool(role), "imei": device_id}


def vc_endcall_group(callee_id, call_id, call_type, host_call, data,
                     partners):
    """Body of group/endcall (code 12438), exactly as the PC client
    sends it (bundle class wZ: static sendEndCallGroup(e,t,n,a,i,r)
    -> {calleeId:e, callId:t, callType:n, hostCall:a, data:i,
    partners:r}; native bridge case 12438 destructures the same
    fields from the engine signal). No imei, no uidTo. hostCall is
    the engine signal's flag for whether this side hosts the call —
    the bundle only gives the field NAME, not the value's meaning;
    for an outgoing call this side is the host, so the app sends
    True (UNCONFIRMED — if the real server rejects it, the end is
    still local best-effort and the error is logged, §7m)."""
    return {"calleeId": callee_id, "callId": call_id,
            "callType": call_type, "hostCall": host_call,
            "data": data,
            "partners": partners if partners is not None else []}


def _call_id_number(call_id):
    """callId la SO JSON (uint32) trong goi bao hieu, nhu engine that (`callId = %u`). Cuoc goi DEN mang ma dang chuoi chu so -> doi lai thanh so:
    gui chuoi "1346292903" thi Zalo van tra err 0 nhung dien thoai khong khop duoc ma cuoc goi va giu «BenBap dang tat camera» (12/11 21:52,
    cuoc goi di dung so thi hinh len)."""
    if isinstance(call_id, str) and call_id.strip().isdigit():
        return int(call_id.strip())
    return call_id


def vc_conf(callee_id, call_id, cam=-1, mic=-1):
    """Body of voicecall/conf (code 12006, `sendOnOffMicCam`): trang thai camera
    / mic cua ta cho dien thoai. cam: 1 bat, 0 tat, -1 giu nguyen; mic: 1 =
    TAT tieng (co mute), 0 = bo mute, -1 giu nguyen (zcall-native `_micState`).
    Khong co thi dien thoai coi camera cua ta la TAT va khong ve hinh du ta
    dang gui (do 10/11: «BenBap dang tat camera»)."""
    return {"calleeId": str(callee_id), "callId": _call_id_number(call_id),
            "isOnCam": cam, "isOnMic": mic, "data": ""}


def vc_a2v(uid_to, call_id, status=1):
    """Body of voicecall/requestaudio2video (code 12056): chuyen cuoc goi THOAI dang
    dien ra sang VIDEO. status 1 = xin bat video, 2 = dong y loi xin cua ben kia
    (fork zca-js `requestAudioToVideoCall`)."""
    return {"uidTo": str(uid_to), "callId": _call_id_number(call_id), "status": status}


def vc_hold(to_id):
    return {"toId": to_id}


# ---------------------------------------------------------------- post-login data
# Avatar size the real PC client asks for in friends/groups lists
# (bundle: getFriendsList/getGroupList send avatar_size: 160, i.e. se=160).
AVATAR_SIZE = 160


def friends_params(device_id):
    """Body of getfriends, exactly as the real PC client sends it.

    Bundle: {incInvalid:1, page:1, count:20000, avatar_size:160,
    actiontime:0, imei} (+ init=1 as a QUERY param on the first load).
    """
    return {"incInvalid": 1, "page": 1, "count": 20000,
            "avatar_size": AVATAR_SIZE, "actiontime": 0, "imei": device_id}


# ---------------------------------------------------------------- groups (addon path)
# zca-js getAllGroups: GET {group_poll}/api/group/getlg/v4 — no
# body, no pagination, just the common params. The PC command table
# maps code 12027 to the same path (domainType GROUP).
GROUPS_V4_PATH = "/api/group/getlg/v4"
# zca-js getGroupInfo / PC getInfoMultiGroup (code 12028): POST
# {group}/api/group/getmg-v2, form body params=<AES JSON> with
# {gridVerMap: "<JSON string of {groupId: 0}>"} — the map value is a
# JSON STRING, not a nested object (both clients do
# gridVerMap: JSON.stringify(map)).
GROUP_INFO_MULTI_PATH = "/api/group/getmg-v2"


def groups_v4_url():
    """GET url for getlg/v4: common params only, no params value."""
    return build_url(GROUP_DOMAIN, GROUPS_V4_PATH, common_params())


def group_info_multi_params(grid_ver_map):
    return {"gridVerMap": json.dumps(grid_ver_map,
                                     separators=(",", ":"))}


def group_info_multi_url():
    """POST url for getmg-v2: common params only; the encrypted
    params go in the form body (see group_info_multi_form)."""
    return build_url(GROUP_DOMAIN, GROUP_INFO_MULTI_PATH, common_params())


def group_info_multi_form(body, session_aes):
    """Form body for getmg-v2: params=<AES JSON>, fully percent-
    encoded (encodeURIComponent parity, same as voicecall_params)."""
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    enc = session_aes(raw)
    return "params=" + urllib.parse.quote(enc, safe="")
