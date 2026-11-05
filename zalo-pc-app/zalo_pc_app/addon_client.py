"""Loopback client for the embedded zalobot sidecar (Node, zca-js).

Contract: ~/workspace/zalo-addon-api-map/API-MAP.md (authoritative;
135 route registrations in routes/api.js, NOT 132 — do not assert
132 anywhere). Base http://127.0.0.1:3000, 60 s timeout, stdlib-only
(urllib + http.cookiejar, no `requests`).

Auth (API-MAP §1): POST /api/login {username, password} (admin env
ZALO_SERVER_ADMIN_USERNAME, default "admin" /
ZALO_SERVER_ADMIN_PASSWORD — same env the sidecar reads; the
password is NEVER hardcoded here). The session cookie is
`zalo-server.sid`, HttpOnly, 30-day TTL, rolling, FileStore, with
session-ID regeneration on login — the 30 days is the SERVER cookie
TTL. The client's own re-login clock is 6 h, client-side only (copied
from the HA integration's ZaloServerSession, server_session.py):
login lazily, remember the login time, re-login on 401 once and
retry the identical request once; a second consecutive 401 is a
hard failure. A 429 from /api/login means the IP is locked out for
up to 15 min — back off, do not retry in a tight loop.

Account resolution (API-MAP §2): GET /api/accounts (poll — this is
also how QR-login completion is detected; there is no server-side
QR TTL). Prefer ownId == the PC session uid, else the first
account; env ZALOBOT_ACCOUNT overrides. A "account not found"
error from the server clears the cached resolution and re-resolves
once. IDs are strings end-to-end; `type` is sent NUMERIC (0/1 —
API-MAP §4.1/§11: numeric works everywhere; the sendMessage
handler passes a string "group" through raw, so never send it).

Media (API-MAP §4.3): imagePath/fileUrl/videoUrl/voiceUrl are
treated by the sidecar as URLs it downloads over HTTP/HTTPS
(utils/download.js rejects anything else, including file:// URLs
and bare paths). The Python app therefore serves a staged upload
over loopback HTTP (see LocalMediaServer below) and passes that
URL; the staged file is deleted after the send.

clientId (API-MAP §4.2, the send-114 lesson): zca-js always derives
clientId from Date.now() (number for text, string for attachments).
This client NEVER sends its own clientId.

Errors: AddonUnreachable (loopback cannot be reached), AddonAuthError
(login failed / locked out), AddonError (the server answered
success=false — the server's message is surfaced, never invented).
No secret value, no user ID, phone number or message content is
ever logged — only route names, HTTP statuses, counts and lengths.

The client is injectable: pass `transport=` (an object with
request(method, path, body) -> (status, dict)) or a different
`base_url` so tests can use a fake sidecar.
"""

import http.cookiejar
import json
import os
import random
import string
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_BASE_URL = "http://127.0.0.1:3000"
DEFAULT_TIMEOUT = 60
AUTH_TTL_SECONDS = 6 * 60 * 60  # client-side only (HA pattern); the
# server cookie itself is 30-day rolling (API-MAP §1.2).
STATUS_TIMEOUT_SECONDS = 5  # /api/status probe must never hang the page

# The server's "account not found" text (API-MAP §2). Matched
# substring-only; the value that follows it (an ID) is never logged.
ACCOUNT_NOT_FOUND = "Không tìm thấy tài khoản"


class AddonUnreachable(Exception):
    """The loopback sidecar cannot be reached (route name + network
    error only — never the URL, which could carry an address)."""


class AddonAuthError(Exception):
    """Admin login failed (wrong credentials, or the per-IP login
    lockout: 10 failures / 15 min -> 429, API-MAP §1.2)."""


class AddonError(Exception):
    """The sidecar answered success=false (or an unexpected shape):
    the server's message is carried verbatim for the UI."""


class UrllibTransport:
    """Default transport: urllib + a cookie jar holding the
    `zalo-server.sid` session cookie. request() returns
    (http_status, parsed_json_dict)."""

    def __init__(self, base_url, timeout=DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar))

    def request(self, method, path, body=None, timeout=None):
        url = self.base_url + path
        data = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, method=method, data=data)
        for key, value in headers.items():
            req.add_header(key, value)
        try:
            with self._opener.open(
                    req, timeout=timeout or self.timeout) as resp:
                return resp.status, _parse_json(resp.read())
        except urllib.error.HTTPError as e:
            try:
                payload = _parse_json(e.read())
            except Exception:
                payload = {}
            return e.code, payload
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise AddonUnreachable(
                "%s %s: %s" % (method, path, type(e).__name__))


def _parse_json(raw):
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _thread_type_number(thread_type):
    """'user'/'group' (or 0/1) -> 0/1. Numeric type works on every
    sidecar handler (API-MAP §4.1); a string is NOT passed through."""
    if thread_type in (1, "1", "group"):
        return 1
    if thread_type in (0, "0", "user", None, ""):
        return 0
    raise ValueError("type phai la user|group (0|1), nhan %r"
                     % (thread_type,))


class AddonClient:
    """Python client for the embedded zalobot sidecar."""

    def __init__(self, base_url=None, username=None, password=None,
                 account=None, pc_uid=None, transport=None,
                 timeout=DEFAULT_TIMEOUT):
        self.base_url = (base_url or os.environ.get(
            "ZALOBOT_BASE_URL", "") or DEFAULT_BASE_URL).rstrip("/")
        self.username = (username if username is not None
                         else os.environ.get(
                             "ZALO_SERVER_ADMIN_USERNAME", "admin"))
        self.password = (password if password is not None
                         else os.environ.get(
                             "ZALO_SERVER_ADMIN_PASSWORD", ""))
        # Explicit account override (env ZALOBOT_ACCOUNT, API-MAP §2).
        self.account_override = (account if account is not None
                                 else os.environ.get("ZALOBOT_ACCOUNT",
                                                     ""))
        self.pc_uid = pc_uid or ""
        self.timeout = timeout
        self.transport = transport or UrllibTransport(
            self.base_url, timeout=timeout)
        self._auth_lock = threading.Lock()
        self._authenticated_at = 0.0
        self._account = None  # resolved ownId (string), cached

    # -- auth ------------------------------------------------------------
    def _auth_fresh(self):
        return bool(self._authenticated_at) and (
            time.monotonic() - self._authenticated_at < AUTH_TTL_SECONDS)

    def login(self):
        """POST /api/login. Raises AddonAuthError on any failure
        (including the 429 lockout — the caller must back off, not
        retry in a loop)."""
        if not self.password:
            raise AddonAuthError(
                "addon login: chua dat ZALO_SERVER_ADMIN_PASSWORD")
        with self._auth_lock:
            status, payload = self.transport.request(
                "POST", "/api/login",
                {"username": self.username, "password": self.password},
                timeout=10)
            if status == 429:
                raise AddonAuthError(
                    "addon login: qua nhieu lan sai, bi khoa tam thoi "
                    "(429) — cho roi thu lai")
            if status != 200 or payload.get("success") is not True:
                self._authenticated_at = 0.0
                raise AddonAuthError(
                    "addon login that bai (HTTP %s): %s"
                    % (status, payload.get("message")
                       or payload.get("error") or "khong ro ly do"))
            self._authenticated_at = time.monotonic()
            return payload

    def _ensure_auth(self):
        if not self._auth_fresh():
            self.login()

    # -- low-level call --------------------------------------------------
    def _call(self, method, path, body=None, auth=True, timeout=None):
        """One call with the HA 401 dance: login lazily, then on 401
        force a re-login and retry the identical request ONCE; a
        second 401 is fatal. Connection problems become
        AddonUnreachable (route + error type only)."""
        if auth:
            self._ensure_auth()
        status, payload = self.transport.request(
            method, path, body, timeout=timeout)
        if auth and status == 401:
            self._authenticated_at = 0.0
            self.login()
            status, payload = self.transport.request(
                method, path, body, timeout=timeout)
        return status, payload

    @staticmethod
    def _unwrap(status, payload, route, full=False):
        """Standard envelope (API-MAP §conventions): success=true +
        data on success; validation failure is 400 {error} (some
        handlers use {success:false, error}); zca-js failure is 500
        {success:false, error}. The `error` key is the constant.
        Returns the `data` field (or the whole payload when the
        handler has no `data`, e.g. /api/health)."""
        if status == 401:
            raise AddonAuthError(
                "addon %s: chua dang nhap (401 sau khi dang nhap lai)"
                % route)
        if status == 429:
            raise AddonError("addon %s: bi gioi han (429)" % route)
        if not isinstance(payload, dict):
            raise AddonError("addon %s: phan hoi khong doc duoc "
                             "(HTTP %s)" % (route, status))
        if payload.get("success") is False or "error" in payload:
            raise AddonError("addon %s: %s"
                             % (route, payload.get("error")
                                or payload.get("message")
                                or "loi khong ro"))
        if status >= 400:
            raise AddonError("addon %s: HTTP %s" % (route, status))
        if full:
            return payload
        if "data" in payload:
            return payload["data"]
        return payload

    def _get(self, path, auth=True, timeout=None, full=False):
        status, payload = self._call("GET", path, None, auth=auth,
                                     timeout=timeout)
        return self._unwrap(status, payload, "GET %s" % path,
                            full=full)

    def _post(self, path, body=None, auth=True, timeout=None,
              full=False):
        status, payload = self._call("POST", path, body or {}, auth=auth,
                                     timeout=timeout)
        return self._unwrap(status, payload, "POST %s" % path,
                            full=full)

    def _post_with_account(self, path, body=None, full=False):
        """*ByAccount call: adds accountSelection, and on the
        server's 'account not found' error re-resolves the account
        once and retries (API-MAP §2)."""
        body = dict(body or {})
        body["accountSelection"] = self._resolve_account()
        try:
            return self._post(path, body, full=full)
        except AddonError as e:
            if ACCOUNT_NOT_FOUND not in str(e):
                raise
            self._account = None
            body["accountSelection"] = self._resolve_account()
            return self._post(path, body, full=full)

    # -- health / accounts ------------------------------------------------
    def health(self, timeout=None):
        """GET /api/health — public, no auth, no Zalo contact
        (API-MAP §8.2): {success, status, uptime, accounts}."""
        status, payload = self._call("GET", "/api/health", None,
                                     auth=False, timeout=timeout)
        if status != 200 or not isinstance(payload, dict):
            raise AddonUnreachable(
                "GET /api/health: HTTP %s" % status)
        return payload

    def accounts(self, timeout=None):
        """GET /api/accounts (admin session): [{ownId, phoneNumber,
        proxy, displayName, isOnline}] + total. Returns the list."""
        data = self._get("/api/accounts", timeout=timeout)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data") or data.get("accounts") or []
        return []

    def account_details(self, own_id):
        """GET /api/accounts/:ownId — live fetchAccountInfo()."""
        return self._get("/api/accounts/%s"
                         % urllib.parse.quote(str(own_id), safe=""))

    def _resolve_account(self):
        """ownId to use for accountSelection: env override, else
        ownId == PC session uid, else the first account (API-MAP
        §2). Raises AddonError when no account is logged in."""
        if self._account:
            return self._account
        if self.account_override:
            self._account = str(self.account_override)
            return self._account
        found = self.accounts()
        if not found:
            raise AddonError(
                "addon: chua co tai khoan Zalo nao dang nhap o sidecar "
                "(quet QR o :3000/zalo-login bang tai khoan phu)")
        pc_uid = self.pc_uid or ""
        chosen = None
        if pc_uid:
            for acc in found:
                if isinstance(acc, dict) and str(
                        acc.get("ownId", "")) == str(pc_uid):
                    chosen = acc
                    break
        if chosen is None:
            chosen = found[0]
        self._account = str(chosen.get("ownId", ""))
        if not self._account:
            raise AddonError("addon: tai khoan sidecar khong co ownId")
        return self._account

    def resolve_account(self):
        """Public alias for _resolve_account (server webhook sync)."""
        return self._resolve_account()

    def set_pc_uid(self, pc_uid):
        """The PC session uid changed (new login): prefer the
        matching sidecar account next time. Only re-resolves when
        the uid actually changed."""
        if pc_uid and pc_uid != self.pc_uid:
            self.pc_uid = pc_uid
            if not self.account_override:
                self._account = None

    def status(self):
        """Best-effort addon status for /api/status — NEVER raises:
        {ok, logged_in, accounts:[{ownId, phoneNumber}]}.
        logged_in comes from GET /api/accounts (poll, API-MAP §8:
        there is no server-side QR TTL, so the account list IS the
        login signal); ok also requires /api/health to answer.
        Counts only are logged, never IDs or phone numbers."""
        try:
            healthy = self.health(timeout=STATUS_TIMEOUT_SECONDS)
            ok = bool(healthy.get("success", True))
        except Exception:
            return {"ok": False, "logged_in": False, "accounts": []}
        try:
            found = self.accounts(timeout=STATUS_TIMEOUT_SECONDS)
        except Exception:
            return {"ok": ok, "logged_in": False, "accounts": []}
        accounts = [{"ownId": str(a.get("ownId", "")),
                     "phoneNumber": str(a.get("phoneNumber", ""))}
                    for a in found if isinstance(a, dict)]
        return {"ok": ok, "logged_in": bool(accounts),
                "accounts": accounts}

    # -- contacts ----------------------------------------------------------
    def friends(self, count=None, page=None):
        """POST /api/getAllFriendsByAccount -> User[] verbatim
        (zca-js defaults count=20000 page=1 when omitted; the HA
        integration sends neither — API-MAP §3/§12 item 5)."""
        body = {}
        if count is not None:
            body["count"] = count
        if page is not None:
            body["page"] = page
        return self._post_with_account("/api/getAllFriendsByAccount",
                                       body)

    def groups(self):
        """POST /api/getAllGroupsByAccount -> {version, gridVerMap}
        (IDs + versions only — step 1 of the two-step group flow,
        API-MAP §3)."""
        return self._post_with_account("/api/getAllGroupsByAccount", {})

    def group_info(self, group_ids):
        """POST /api/getGroupInfoByAccount {groupId: [...] or str} ->
        {removedsGroup, unchangedsGroup, gridInfoMap} (step 2)."""
        if isinstance(group_ids, str):
            group_ids = [group_ids]
        return self._post_with_account("/api/getGroupInfoByAccount",
                                       {"groupId": list(group_ids)})

    def find_user(self, phone):
        return self._post_with_account("/api/findUserByAccount",
                                       {"phone": phone})

    def get_user_info(self, user_id):
        return self._post_with_account("/api/getUserInfoByAccount",
                                       {"userId": user_id})

    # -- send ---------------------------------------------------------------
    def send_message(self, thread_id, thread_type, message,
                     quote=None, ttl=None):
        """POST /api/sendMessageByAccount. `message` is a plain
        string or a MessageContent object; quote is merged by the
        server. No clientId is ever sent (zca-js generates it from
        Date.now(), API-MAP §4.2). Returns data verbatim:
        {message:{msgId:number}|null, attachment:[...]} plus the
        server's messageTtl auto-undo record (or null)."""
        body = {"message": message, "threadId": str(thread_id),
                "type": _thread_type_number(thread_type)}
        if quote is not None:
            body["quote"] = quote
        if ttl is not None:
            body["ttl"] = ttl
        return self._post_with_account("/api/sendMessageByAccount",
                                       body)

    def send_image(self, thread_id, thread_type, image_url,
                   message="", ttl=None):
        """POST /api/sendImageByAccount {imagePath (a URL the
        sidecar downloads, 25 MB cap, magic-byte checked),
        threadId, type, message (caption), ttl}."""
        body = {"imagePath": image_url, "threadId": str(thread_id),
                "type": _thread_type_number(thread_type),
                "message": message or ""}
        if ttl is not None:
            body["ttl"] = ttl
        return self._post_with_account("/api/sendImageByAccount", body)

    def send_images(self, thread_id, thread_type, image_urls,
                    caption="", ttl=None):
        """POST /api/sendImagesToUser/GroupByAccount (batched album;
        per-request caps 24 images / 100 MB, GIF rejected — API-MAP
        §4.4)."""
        route = ("/api/sendImagesToGroupByAccount"
                 if _thread_type_number(thread_type) == 1
                 else "/api/sendImagesToUserByAccount")
        body = {"imagePaths": list(image_urls),
                "threadId": str(thread_id)}
        if caption:
            body["caption"] = caption
        if ttl is not None:
            body["ttl"] = ttl
        return self._post_with_account(route, body)

    def send_file(self, thread_id, thread_type, file_url,
                  message="", ttl=None):
        """POST /api/sendFileByAccount {fileUrl (a URL the sidecar
        downloads, 150 MB cap), threadId, type, message, ttl}.
        NOTE (API-MAP §12 item 7): the sidecar's own error path can
        surface a secondary error when the download itself fails —
        that is the server's bug, surfaced here, not copied."""
        body = {"fileUrl": file_url, "threadId": str(thread_id),
                "type": _thread_type_number(thread_type),
                "message": message or ""}
        if ttl is not None:
            body["ttl"] = ttl
        return self._post_with_account("/api/sendFileByAccount", body)

    def send_video(self, thread_id, thread_type, video_url,
                   thumbnail_url=None, duration=None):
        """POST /api/sendVideoByAccount {options:{videoUrl,
        thumbnailUrl?, duration?}, threadId, type}. The sidecar
        downloads the video, measures duration, uploads it and a
        (mandatory) thumbnail, then sends (API-MAP §4.5)."""
        options = {"videoUrl": video_url}
        if thumbnail_url:
            options["thumbnailUrl"] = thumbnail_url
        if duration is not None:
            options["duration"] = duration
        return self._post_with_account(
            "/api/sendVideoByAccount",
            {"options": options, "threadId": str(thread_id),
             "type": _thread_type_number(thread_type)})

    def send_voice(self, thread_id, thread_type, voice_url, ttl=None):
        """POST /api/sendVoiceByAccount {options:{voiceUrl, ttl?},
        threadId, type}. Non-Zalo URLs are downloaded, converted
        with ffmpeg to AAC-LC 16 kHz mono and uploaded first, so the
        recipient gets a playable voice bubble, not a file
        (API-MAP §4.5)."""
        options = {"voiceUrl": voice_url}
        if ttl is not None:
            options["ttl"] = ttl
        return self._post_with_account(
            "/api/sendVoiceByAccount",
            {"options": options, "threadId": str(thread_id),
             "type": _thread_type_number(thread_type)})

    def send_sticker(self, thread_id, thread_type, sticker):
        """POST /api/sendStickerByAccount {sticker:{id:number,...},
        threadId, type}."""
        return self._post_with_account(
            "/api/sendStickerByAccount",
            {"sticker": sticker, "threadId": str(thread_id),
             "type": _thread_type_number(thread_type)})

    def send_card(self, thread_id, thread_type, options):
        """POST /api/sendCardByAccount {options, threadId, type}.
        The inner `options` shape is zca-js-defined (API-MAP §12
        item 1 — ambiguous from code alone); pass through verbatim
        and surface the server's error."""
        return self._post_with_account(
            "/api/sendCardByAccount",
            {"options": options, "threadId": str(thread_id),
             "type": _thread_type_number(thread_type)})

    def send_link(self, thread_id, thread_type, options):
        """POST /api/sendLinkByAccount — same pass-through caveat
        as send_card."""
        return self._post_with_account(
            "/api/sendLinkByAccount",
            {"options": options, "threadId": str(thread_id),
             "type": _thread_type_number(thread_type)})

    # -- history ------------------------------------------------------------
    def group_history_full(self, group_id, count=50):
        """Same call as group_history, but returns the FULL server
        envelope (data + groupId/groupName/source/requested/
        returned/fromCache) instead of only `data`."""
        return self._post_with_account(
            "/api/getGroupChatHistoryByAccount",
            {"groupId": str(group_id), "count": int(count)}, full=True)

    def group_history(self, group_id, count=50):
        """POST /api/getGroupChatHistoryByAccount {groupId, count
        1..1000}. Returns the server envelope verbatim: {data:
        {groupMsgs, more, ...}, groupId, groupName, source,
        requested, returned, fromCache, ...}. There is NO 1-1
        history endpoint (API-MAP §6)."""
        return self._post_with_account(
            "/api/getGroupChatHistoryByAccount",
            {"groupId": str(group_id), "count": int(count)})

    # -- typing / seen / delivered -------------------------------------------
    def typing(self, thread_id):
        """POST /api/sendTypingEventByAccount {threadId}. NOTE
        (API-MAP §4.6): the sidecar hard-codes ThreadType.User +
        DestType.User — there is NO way to send a group typing
        event through this route. The call is still made (a 1-1
        typing event is correct; a group one is best-effort and
        the server's behaviour is surfaced, not invented)."""
        return self._post_with_account(
            "/api/sendTypingEventByAccount",
            {"threadId": str(thread_id)})

    def seen(self, thread_id, thread_type, msg_ids):
        """POST /api/sendSeenEventByAccount {messages, type}.
        zca-js wants full SendSeenEventMessageParams objects
        ({msgId, cliMsgId, uidFrom, idTo, msgType, st, at, cmd,
        ts}); the app only knows message IDs, so each ID is sent
        as {msgId} — the honest best-effort (API-MAP §12 item 1:
        the full shape needs a live check). The server's error, if
        any, is surfaced, not hidden."""
        messages = [{"msgId": str(m)} for m in (msg_ids or [])]
        return self._post_with_account(
            "/api/sendSeenEventByAccount",
            {"messages": messages,
             "type": _thread_type_number(thread_type)})

    def delivered(self, thread_id, thread_type, msg_ids, is_seen=True):
        """POST /api/sendDeliveredEventByAccount {isSeen, messages,
        type} — `type` is passed raw by the sidecar (API-MAP §4.6),
        so numeric is sent."""
        messages = [{"msgId": str(m)} for m in (msg_ids or [])]
        return self._post_with_account(
            "/api/sendDeliveredEventByAccount",
            {"isSeen": bool(is_seen), "messages": messages,
             "type": _thread_type_number(thread_type)})

    # -- generic service op ---------------------------------------------------
    def svc(self, op, params):
        """Generic *ByAccount op: POST /api/<op>ByAccount with the
        given params + accountSelection. `op` is the route suffix
        (e.g. "sendMessage", "getGroupInfo"); a trailing
        "ByAccount" is tolerated. Special non-ByAccount ops:
        get_logged_accounts -> GET /api/accounts,
        get_account_details -> GET /api/accounts/:ownId,
        get_all_friends / get_all_groups / get_group_chat_history
        -> their dedicated methods. Returns data verbatim."""
        if op == "get_logged_accounts":
            return self.accounts()
        if op == "get_account_details":
            own_id = (params or {}).get("ownId") or self._resolve_account()
            return self.account_details(own_id)
        if op == "get_all_friends":
            return self.friends()
        if op == "get_all_groups":
            return self.groups()
        if op == "get_group_chat_history":
            params = params or {}
            return self.group_history(params.get("groupId", ""),
                                      params.get("count", 50))
        route = op[:-len("ByAccount")] if op.endswith("ByAccount") else op
        return self._post_with_account("/api/%sByAccount" % route,
                                       dict(params or {}))

    # -- webhooks ---------------------------------------------------------------
    def webhooks_get(self):
        """GET /api/account-webhooks (admin session only; the API
        key does NOT work here — API-MAP §10.5): the whole
        webhook-config file."""
        return self._get("/api/account-webhooks")

    def webhooks_get_account(self, own_id):
        """GET /api/account-webhook/:ownId -> {ownId,
        messageWebhookUrl, groupEventWebhookUrl,
        reactionWebhookUrl} (missing keys fall back to "")."""
        return self._get("/api/account-webhook/%s"
                         % urllib.parse.quote(str(own_id), safe=""))

    def webhooks_set(self, own_id, urls):
        """POST /api/account-webhook {ownId, messageWebhookUrl?,
        groupEventWebhookUrl?, reactionWebhookUrl?} — only the
        keys present are updated."""
        body = {"ownId": str(own_id)}
        for key in ("messageWebhookUrl", "groupEventWebhookUrl",
                    "reactionWebhookUrl"):
            if key in (urls or {}):
                body[key] = urls[key]
        return self._post("/api/account-webhook", body)

    def webhooks_delete(self, own_id):
        """DELETE /api/account-webhook/:ownId — removes the
        per-account block (the default still applies)."""
        status, payload = self._call(
            "DELETE", "/api/account-webhook/%s"
            % urllib.parse.quote(str(own_id), safe=""), None)
        return self._unwrap(status, payload,
                            "DELETE /api/account-webhook")


def make_client(pc_uid=None, **kwargs):
    """Build an AddonClient from the environment (admin env + base
    URL), with the PC session uid for account preference. Returns
    None when no admin password is configured — the caller then
    keeps the legacy PC-direct behaviour (no sidecar calls are
    attempted at all)."""
    password = os.environ.get("ZALO_SERVER_ADMIN_PASSWORD", "")
    if not password and "password" not in kwargs:
        return None
    return AddonClient(pc_uid=pc_uid, **kwargs)


# ----------------------------------------------------------------------
# LocalMediaServer: loopback-only file server for staged uploads.
#
# WHY: the sidecar downloads media over HTTP/HTTPS only
# (utils/download.js rejects file:// URLs and bare paths), so a
# staged upload in /data/tmp cannot be handed over as a path. The
# app serves the file on 127.0.0.1 (ephemeral port, random token
# per file) and passes that URL to the sidecar; the file is deleted
# right after the send. The server binds loopback ONLY, serves only
# files explicitly published (token-checked), and never lists
# directories. No secret, ID or content is logged — only the token
# length and byte count.
# ----------------------------------------------------------------------

def _random_token():
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(32))


class LocalMediaServer:
    """One loopback HTTP server for staged upload files."""

    def __init__(self, directory):
        self.directory = os.path.abspath(directory)
        self._tokens = {}  # token -> (filename, abspath)
        self._lock = threading.Lock()
        self._httpd = None
        self._thread = None

    def _ensure_started(self):
        with self._lock:
            if self._httpd is not None:
                return
            server = self

            class _Handler(BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"

                def log_message(self, *args):
                    pass

                def do_GET(self):
                    parts = [p for p in
                             urllib.parse.urlparse(self.path).path
                             .split("/") if p]
                    if len(parts) != 2:
                        return self._deny()
                    token, filename = parts
                    with server._lock:
                        entry = server._tokens.get(token)
                    if entry is None or entry[0] != filename:
                        return self._deny()
                    try:
                        with open(entry[1], "rb") as f:
                            data = f.read()
                    except OSError:
                        return self._deny()
                    self.send_response(200)
                    self.send_header("Content-Type",
                                     "application/octet-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)

                def _deny(self):
                    body = b"not found"
                    self.send_response(404)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            self._httpd = ThreadingHTTPServer(
                ("127.0.0.1", 0), _Handler)
            self._thread = threading.Thread(
                target=self._httpd.serve_forever, daemon=True)
            self._thread.start()

    def publish(self, path):
        """Register a file under the server; returns
        (url, token). The file must already exist inside the
        server directory."""
        abspath = os.path.abspath(path)
        if (os.path.commonpath([abspath, self.directory])
                != self.directory):
            raise ValueError("media file outside staging directory")
        if not os.path.isfile(abspath):
            raise ValueError("media file missing")
        self._ensure_started()
        token = _random_token()
        with self._lock:
            self._tokens[token] = (os.path.basename(abspath), abspath)
            port = self._httpd.server_address[1]
        url = ("http://127.0.0.1:%d/%s/%s"
               % (port, token, urllib.parse.quote(
                   os.path.basename(abspath))))
        return url, token

    def unpublish(self, token):
        with self._lock:
            self._tokens.pop(token, None)

    def stop(self):
        with self._lock:
            httpd = self._httpd
            self._httpd = None
            self._tokens = {}
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
