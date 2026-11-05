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
"""

import json
import urllib.parse

from . import protocol
from .crypto import session_aes_encrypt

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
    """Best-effort: pull [{id, name, avatar}] out of common shapes."""
    rows = []
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("friends", "groups", "items", "list", "data"):
            val = data.get(key)
            if isinstance(val, list):
                items = val
                break
    for it in items:
        if not isinstance(it, dict):
            continue
        uid = (it.get("userId") or it.get("id") or it.get("uid") or "")
        name = (it.get("displayName") or it.get("name")
                or it.get("dName") or "")
        avatar = it.get("avatar", "")
        if uid or name:
            rows.append({"id": str(uid), "name": name, "avatar": avatar})
    return rows


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
        return payload.get("data")

    def friends(self, init=False):
        """getfriends. init=True on the first load only (real client sends
        init=1 as a query param on its first friends request)."""
        body = protocol.friends_params(self.device_id)
        extra = {"init": 1} if init else None
        url = _url_with_params(protocol.PROFILE_DOMAIN, FRIENDS_PATH,
                               body, self.zpw_enk, extra)
        data = self._get(url)
        return {"rows": _extract_rows(data), "raw": data}

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
            rows.extend(_extract_rows(data))
            total = data.get("total", total)
            if not data.get("hasMore"):
                break
            if total is not None and len(rows) >= total:
                break
            page += 1
        return {"rows": rows,
                "raw": {"groups": rows, "total": total,
                        "hasMore": False}}
