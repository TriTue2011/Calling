"""Zalo PC wire protocol: endpoints, request builders, response parsers.

Evidence: Zalo PC 26.11.10 renderer bundle (see bao-cao.md).
All requests are HTTPS GET unless noted. Post-login calls carry
`params=<session-AES base64 JSON>`; login calls carry either the
ParamCipher envelope or plaintext params + signkey (see crypto.py).

Common query params on every API call:
    zpw_ver=<apiVersion> & zpw_type=<apiType>
Defaults for this build: apiVersion=695, apiType="embed".
"""

import json
import time
import urllib.parse

AUTH_DOMAIN = "https://wpa.zalo.me"
VOICECALL_DOMAIN = "https://voicecall-wpa.zalo.me"
CONVERS_DOMAIN = "https://convers-wpa.api.zalo.me"
PROFILE_DOMAIN = "https://profile-wpa.zalo.me"
GROUP_DOMAIN = "https://group-wpa.zalo.me"

API_VERSION = 695
API_TYPE = "embed"
LANGUAGE = "vi"

# API codes (QoS/logging ids the client sends alongside each call).
CODE_REQQQR = 11133
CODE_GET_SERVER_INFO = 11323
CODE_GET_LOGIN_INFO = 11134
CODE_LOGOUT = 11135
CODE_GET_FRIENDS = 11137
CODE_GET_GROUPS = 11161
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


def common_params(api_version=API_VERSION, api_type=API_TYPE):
    return {"zpw_ver": api_version, "zpw_type": api_type}


def build_url(base, path, params):
    qs = urllib.parse.urlencode(params)
    return "%s%s?%s" % (base, path, qs)


def unix_now():
    return int(time.time())


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
    return {"calleeId": callee_id, "callId": call_id,
            "codec": codec if codec is not None else "[]",
            "typeRequest": type_request, "imei": device_id}


def vc_request(callee_id, rtcp_address, rtp_address, codec, session,
               call_id, device_id, extend_data=None):
    body = {"calleeId": callee_id, "rtcpAddress": rtcp_address,
            "rtpAddress": rtp_address, "codec": codec, "session": session,
            "callId": call_id, "imei": device_id}
    if extend_data:
        body["extendData"] = extend_data
        body["subCommand"] = 3
    return body


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


def groups_params(page=1, count=100, device_id=""):
    """Body of getlg/v3, exactly as the real PC client sends it.

    Bundle getGroupListV3(page, count=100): {page, count,
    avatar_size:160, member_avatar_size:160, imei} to
    /api/group/getlg/v3 (command table: 11161 -> getlg/v3). Every live
    caller (_fetchAllGroups, the fetch-by-page helper,
    callFetchGroupListByPage) uses V3, paginated. The plain
    getGroupList() v1 (/api/group/getlg, {avatar_size,
    member_avatar_size}, no imei) has no live caller for the main
    list, and the real server rejects it with 602 — that was the
    remaining groups bug after 8397d18 (friends passed, groups 602).
    """
    return {"page": page, "count": count, "avatar_size": AVATAR_SIZE,
            "member_avatar_size": AVATAR_SIZE, "imei": device_id}
