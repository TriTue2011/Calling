"""Post-login data fetchers for the main UI (contacts / threads).

Endpoints (PC client, auth/profile/group/convers domains):
  friends: GET {profile}/api/social/friend/getfriends (code 11137)
  groups:  ADDON PATH (§7i in bao-cao.md), two steps, same as
           zca-js getAllGroups + getGroupInfo:
           1. GET {group}/api/group/getlg/v4 (code 12027, no body,
              no pagination) -> {version, gridVerMap: {groupId:
              version}} — a version map, NOT a named list;
           2. POST {group}/api/group/getmg-v2 (code 12028, form
              body params=<AES {gridVerMap: "{groupId: 0}"}>) ->
              {removedsGroup, unchangedsGroup, gridInfoMap:
              {groupId: {groupId, name, avt, fullAvt, creatorId,
              topMember: [{id, ...}], totalMember, type, ...}}}.
           The old getlg/v3 list path was the PC client's list path,
           not the addon's; per the user's "lấy y nguyên" direction
           the app follows the addon path ONLY. Both endpoints exist
           in the PC client's own command table (12027/12028), so
           the PC session can call them with the same auth.
  convers: GET {convers}/api/conv/...               (list endpoint,
           exact path parameters are a phase-2 detail; the client
           sends the standard common params + session-AES params)

All take the standard common params; calls with a body add
params=<session-AES JSON> (GET query for friends, POST form body
for getmg-v2; v4 has no body at all).
Response parsing here is deliberately loose (best-effort id/name
extraction): the server's list shapes vary, and the UI only needs
id + display name + avatar to render rows. Anything unparsed is still
returned raw under "raw" for the UI to inspect.

Real response shapes:
  friends: data is a BARE ARRAY of profile items
    {userId, displayName|zaloName, avatar} (bundle compact-app-pc,
    FriendListManager checks Array.isArray(data) after unwrapping);
  groups:  data is {version, gridVerMap} (v4) then {gridInfoMap}
    (getmg-v2); each group info is {groupId, name, avt, fullAvt,
    creatorId, topMember: [{id, ...}], totalMember, ...} (bundle
    _preFormatData: displayName=name, avatar=avt, bgavatar=fullAvt).

Post-login responses are a TWO-LAYER envelope (bundle kCOK unwrap):
outer {error_code: 0, data: "<AES base64 string>"} — the data field
is ciphertext, NOT the payload. Decrypt it with the session key
(zpw_enk) and JSON-parse the inner {error_code, data}; the inner
data is the real payload above. Contacts._get/_post decode this via
crypto.decode_postlogin_data. Returning payload["data"] directly was
the 0/0 bug of 2026-11-05: a string parses as "no items" for both
endpoints while the outer error_code stays 0, so the UI showed empty
tabs with no error — exactly what the live server did (the account
has friends and groups for real, the app showed 0/0).

Diagnostic logging: friends()/groups() print shape-only lines to
stdout (see describe_shape) — types, lengths and key names only,
never personal values — so a redeploy's log shows what the server
really returned.
"""

import json
import urllib.parse

from . import protocol
from .crypto import decode_postlogin_data, session_aes_encrypt

FRIENDS_PATH = "/api/social/friend/getfriends"
GROUPS_V4_PATH = protocol.GROUPS_V4_PATH
GROUP_INFO_MULTI_PATH = protocol.GROUP_INFO_MULTI_PATH


def _url_with_params(base, path, body, zpw_enk, extra_query=None):
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    enc = session_aes_encrypt(zpw_enk, raw)
    params = protocol.common_params()
    if extra_query:
        params.update(extra_query)
    qs = urllib.parse.urlencode(params)
    # encodeURIComponent parity: quote() with safe="" encodes '/' as %2F
    # (the default safe="/" left raw '/' in the base64 value, unlike the
    # real client — one of the wire-format deviations behind the 602).
    return "%s%s?%s&params=%s" % (
        base, path, qs, urllib.parse.quote(enc, safe=""))


def _extract_rows(data):
    """Best-effort: pull [{id, name, avatar}] out of the REAL friends
    shape (getfriends returns a bare array of profile items
    {userId, displayName|zaloName, avatar}; the client's
    FriendListManager checks Array.isArray(data) after unwrapping
    the envelope; the contacts UI resolves a name as
    getDName(userId) || displayName || zaloName, and
    reformatConversationFromFriend also accepts snake_case
    (uid / zalo_name / display_name)).
    Defensive fallbacks (harmless): a "rows" container key, and an
    item nested under "profile". Groups are NOT parsed here — they
    come from gridInfoMap via _group_row (addon path, see groups()).
    """
    rows = []
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("friends", "items", "list", "data", "rows"):
            val = data.get(key)
            if isinstance(val, list):
                items = val
                break
    for it in items:
        if not isinstance(it, dict):
            continue
        if isinstance(it.get("profile"), dict):
            it = it["profile"]
        uid = (it.get("userId") or it.get("id") or it.get("uid") or "")
        name = (it.get("displayName") or it.get("dName")
                or it.get("zaloName") or it.get("name")
                or it.get("display_name") or it.get("zalo_name") or "")
        avatar = (it.get("avatar") or it.get("avt")
                  or it.get("fullAvt") or "")
        if uid or name:
            rows.append({"id": str(uid), "name": name, "avatar": avatar})
    return rows


def _group_row(group_id, info):
    """One group row from a gridInfoMap item (getmg-v2): the bundle's
    _preFormatData maps name -> displayName, avt -> avatar,
    fullAvt -> bgavatar; topMember is the member list (each member
    an object with id). `members` feeds the group call's `partners`
    (who to ring); topMember may be PARTIAL when hasMoreMember is
    set — the full member list via getgi/v2 is the follow-up if a
    large group's call misses members."""
    if not isinstance(info, dict):
        info = {}
    name = (info.get("name") or info.get("groupName")
            or info.get("title") or info.get("displayName") or "")
    avatar = (info.get("avt") or info.get("avatar")
              or info.get("fullAvt") or "")
    members = []
    for m in info.get("topMember") or []:
        if isinstance(m, dict):
            mid = m.get("id") or m.get("userId") or m.get("uid")
            if mid:
                members.append(str(mid))
        elif isinstance(m, str):
            members.append(m)
    return {"id": str(group_id), "name": name, "avatar": avatar,
            "members": members}


def describe_shape(data):
    """Shape-only description of a response payload: value TYPES,
    lengths, and KEY NAMES only. Never includes names, ids, phone
    numbers, message content, or any other personal VALUE — only
    keys and counts — so the line is safe to paste into a log or a
    chat message for diagnosis. Examples:
      list len=60 first_item_keys=['avatar', 'displayName', 'userId']
      dict keys=['groups', 'hasMore', 'total'] groups len=6
        first_item_keys=['avt', 'creatorId', 'groupId', 'name']
        total=6 hasMore=False
    """
    if data is None:
        return "null"
    if isinstance(data, list):
        first_keys = sorted({k for it in data[:1]
                             if isinstance(it, dict) for k in it})
        return "list len=%d first_item_keys=%s" % (len(data), first_keys)
    if isinstance(data, dict):
        parts = ["dict keys=%s" % sorted(data.keys())]
        for key in ("groups", "friends", "items", "list", "data", "rows",
                    "gridVerMap", "gridInfoMap"):
            val = data.get(key)
            if isinstance(val, list):
                first_keys = sorted({k for it in val[:1]
                                     if isinstance(it, dict) for k in it})
                parts.append("%s len=%d first_item_keys=%s"
                             % (key, len(val), first_keys))
                break
            if isinstance(val, dict):
                # Map keyed by id (gridVerMap: {id: version string};
                # gridInfoMap: {id: group info dict}).
                first_val = next(iter(val.values()), None)
                if isinstance(first_val, dict):
                    parts.append("%s len=%d first_item_keys=%s"
                                 % (key, len(val), sorted(first_val.keys())))
                else:
                    parts.append("%s len=%d" % (key, len(val)))
                break
        if isinstance(data.get("total"), int):
            parts.append("total=%d" % data["total"])
        if isinstance(data.get("hasMore"), bool):
            parts.append("hasMore=%s" % data["hasMore"])
        return " ".join(parts)
    return type(data).__name__


def _log_shape(tag, raw, rows):
    print("[contacts-shape] %s raw=%s rows=%d"
          % (tag, describe_shape(raw), rows), flush=True)


class Contacts:
    def __init__(self, http_get, device_id, zpw_enk, http_post=None):
        # http_get: (url, timeout) -> (status, json dict); http_post:
        # (url, form_body, timeout) -> (status, json dict) for the
        # getmg-v2 POST. Both come from server.make_transport.
        self.http_get = http_get
        self.http_post = http_post
        self.device_id = device_id
        self.zpw_enk = zpw_enk

    def _unwrap(self, status, payload, where):
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("contacts: %s network status=%s"
                               % (where, status))
        if payload.get("error_code") != 0:
            raise RuntimeError("contacts: %s error_code=%s %s" % (
                where, payload.get("error_code"),
                payload.get("error_message", "")))
        # Two-layer envelope (bundle kCOK unwrap): the outer data
        # field is an AES-encrypted STRING. Returning it directly
        # made _extract_rows see "no items" for every endpoint.
        return decode_postlogin_data(payload, self.zpw_enk)

    def _get(self, url):
        status, payload = self.http_get(url, timeout=30)
        return self._unwrap(status, payload, "GET %s" % url.split("?")[0])

    def _post(self, url, form):
        if self.http_post is None:
            raise RuntimeError("contacts: POST transport missing for %s"
                               % url.split("?")[0])
        status, payload = self.http_post(url, form, timeout=30)
        return self._unwrap(status, payload, "POST %s" % url.split("?")[0])

    def friends(self, init=False):
        """getfriends. init=True on the first load only (real client sends
        init=1 as a query param on its first friends request)."""
        body = protocol.friends_params(self.device_id)
        extra = {"init": 1} if init else None
        url = _url_with_params(protocol.PROFILE_DOMAIN, FRIENDS_PATH,
                               body, self.zpw_enk, extra)
        data = self._get(url)
        rows = _extract_rows(data)
        _log_shape("friends", data, len(rows))
        return {"rows": rows, "raw": data}

    def groups(self):
        """Addon path (zca-js getAllGroups + getGroupInfo), two steps:
        1. GET getlg/v4 (no body, no pagination) -> {version,
           gridVerMap: {groupId: version}} — the SET of groups;
        2. POST getmg-v2 with {gridVerMap: {groupId: 0}} ->
           {removedsGroup, unchangedsGroup, gridInfoMap} — names,
           avatars and topMember lists for those ids.
        No getmg-v2 call when the map is empty (an account with no
        groups returns zero rows, not an error). Rows keep the RAW
        groupId as id (the voicecall API takes the raw group id; the
        "group" prefix is only a client-store convention) and carry
        `members` (topMember userIds) for the group call's partners.
        """
        data = self._get(protocol.groups_v4_url())
        if not isinstance(data, dict):
            data = {}
        grid_ver = data.get("gridVerMap") or {}
        if not isinstance(grid_ver, dict):
            grid_ver = {}
        _log_shape("groups v4", data, len(grid_ver))
        if not grid_ver:
            return {"rows": [], "raw": data}
        ver_map = {str(gid): 0 for gid in grid_ver}
        body = protocol.group_info_multi_params(ver_map)
        form = protocol.group_info_multi_form(
            body, lambda raw: session_aes_encrypt(self.zpw_enk, raw))
        info = self._post(protocol.group_info_multi_url(), form)
        if not isinstance(info, dict):
            info = {}
        grid_info = info.get("gridInfoMap") or {}
        if not isinstance(grid_info, dict):
            grid_info = {}
        _log_shape("groups info", info, len(grid_info))
        rows = [_group_row(gid, grid_info.get(str(gid)))
                for gid in grid_ver]
        return {"rows": rows, "raw": info}
