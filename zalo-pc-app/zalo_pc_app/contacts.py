"""Post-login data fetchers for the main UI (contacts / threads).

Endpoints (PC client, auth/profile/group/convers domains):
  friends: GET {auth}/api/social/friend/getfriends (code 11137)
  groups:  GET {group}/api/group/getlg/v3           (code 11161,
           paginated: page/count, hasMore/total — the plain v1
           /api/group/getlg has no live caller and the real server
           rejects it with 602, see bao-cao.md 7c)
  convers: GET {convers}/api/conv/...               (list endpoint,
           exact path parameters are a phase-2 detail; the client
           sends the standard common params + session-AES params)

All take the standard common params plus params=<session-AES JSON>.
Response parsing here is deliberately loose (best-effort id/name
extraction): the server's list shapes vary, and the UI only needs
id + display name + avatar to render rows. Anything unparsed is still
returned raw under "raw" for the UI to inspect.

Real response shapes (bundle compact-app-pc, see _extract_rows):
  friends: data is a BARE ARRAY of profile items
    {userId, displayName|zaloName, avatar};
  groups:  data is {groups: [...raw {groupId, name, avt, ...}...],
    hasMore, total}.

Post-login responses are a TWO-LAYER envelope (bundle kCOK unwrap):
outer {error_code: 0, data: "<AES base64 string>"} — the data field
is ciphertext, NOT the payload. Decrypt it with the session key
(zpw_enk) and JSON-parse the inner {error_code, data}; the inner
data is the real payload above. Contacts._get decodes this via
crypto.decode_postlogin_data. Returning payload["data"] directly was
the 0/0 bug of 2026-11-05: a string parses as "no items" for both
endpoints while the outer error_code stays 0, so the UI showed empty
tabs with no error — exactly what the live server did (60 friends /
6 groups on the phone, 0/0 in our app).

Diagnostic logging: friends()/groups() print one shape-only line
per endpoint to stdout (see describe_shape) — types, lengths and
key names only, never personal values — so a redeploy's log shows
what the server really returned.
"""

import json
import urllib.parse

from . import protocol
from .crypto import decode_postlogin_data, session_aes_encrypt

FRIENDS_PATH = "/api/social/friend/getfriends"
GROUPS_PATH = "/api/group/getlg/v3"


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
    """Best-effort: pull [{id, name, avatar}] out of the REAL shapes.

    Real shapes (Zalo PC bundle compact-app-pc, verified 2026-11-05
    from the client's own parsing code — NOT from the old mock, which
    returned pre-formatted items and hid these gaps):
      friends (getfriends): data is a BARE ARRAY of profile items
        {userId, displayName|zaloName, avatar}. The client's
        FriendListManager checks Array.isArray(data) after unwrapping
        the envelope; the contacts UI resolves a name as
        getDName(userId) || displayName || zaloName, and
        reformatConversationFromFriend also accepts snake_case
        (uid / zalo_name / display_name).
      groups (getlg/v3): data is {groups: [...], hasMore, total};
        each item is a RAW group object {groupId, name, avt, fullAvt,
        creatorId, ...}. The client's _preFormatItemGroup maps
        groupId -> userId ("group"+groupId), name -> displayName,
        avt -> avatar, fullAvt -> bgavatar. Our rows keep the RAW
        groupId as id (the voicecall API takes the raw group id;
        the "group" prefix is only a client-store convention).
    Defensive fallbacks (not bundle-confirmed, harmless): a "rows"
    container key, and an item nested under "profile".
    """
    rows = []
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("friends", "groups", "items", "list", "data", "rows"):
            val = data.get(key)
            if isinstance(val, list):
                items = val
                break
    for it in items:
        if not isinstance(it, dict):
            continue
        if isinstance(it.get("profile"), dict):
            it = it["profile"]
        uid = (it.get("userId") or it.get("groupId") or it.get("id")
               or it.get("uid") or "")
        name = (it.get("displayName") or it.get("dName")
                or it.get("zaloName") or it.get("name")
                or it.get("display_name") or it.get("zalo_name") or "")
        avatar = (it.get("avatar") or it.get("avt")
                  or it.get("fullAvt") or "")
        if uid or name:
            rows.append({"id": str(uid), "name": name, "avatar": avatar})
    return rows


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
        for key in ("groups", "friends", "items", "list", "data", "rows"):
            val = data.get(key)
            if isinstance(val, list):
                first_keys = sorted({k for it in val[:1]
                                     if isinstance(it, dict) for k in it})
                parts.append("%s len=%d first_item_keys=%s"
                             % (key, len(val), first_keys))
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
    def __init__(self, http_get, device_id, zpw_enk):
        self.http_get = http_get
        self.device_id = device_id
        self.zpw_enk = zpw_enk

    def _get(self, url):
        status, payload = self.http_get(url, timeout=30)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("contacts: network status=%s" % status)
        if payload.get("error_code") != 0:
            raise RuntimeError("contacts: error_code=%s %s" % (
                payload.get("error_code"), payload.get("error_message", "")))
        # Two-layer envelope (bundle kCOK unwrap): the outer data
        # field is an AES-encrypted STRING. Returning it directly
        # made _extract_rows see "no items" for every endpoint.
        return decode_postlogin_data(payload, self.zpw_enk)

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

    def groups(self, count=100):
        """getlg/v3, paginated exactly like the real client: page 1, 2,
        ... while the server says hasMore and fewer than total rows
        were collected (cap 100 pages, mirroring the client's loop
        guard `++page >= 100 || !hasMore || collected >= total`)."""
        rows, total, page = [], None, 1
        while page <= 100:
            url = _url_with_params(
                protocol.GROUP_DOMAIN, GROUPS_PATH,
                protocol.groups_params(page=page, count=count,
                                       device_id=self.device_id),
                self.zpw_enk)
            data = self._get(url)
            if not isinstance(data, dict):
                data = {}
            page_rows = _extract_rows(data)
            rows.extend(page_rows)
            _log_shape("groups page=%d" % page, data, len(rows))
            total = data.get("total", total)
            if not data.get("hasMore"):
                break
            if total is not None and len(rows) >= total:
                break
            page += 1
        return {"rows": rows,
                "raw": {"groups": rows, "total": total,
                        "hasMore": False}}
