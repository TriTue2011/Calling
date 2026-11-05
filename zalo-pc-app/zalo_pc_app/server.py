"""App service: stdlib HTTP server + JSON API + static UI.

API (all JSON, never returns session secrets):
  GET  /api/status        {login, uid, phonenum, engine} (needs app login)
  POST /api/qr/new        start a QR login (background thread)
  GET  /api/qr/status     {state, qr_image, countdown, wait_seconds, ...}
  POST /api/logout        clear the stored Zalo session AND the app
                          session (revokes the app cookie)
  GET  /api/contacts      {friends:[...], groups:[...]} (needs login)
    Cache phía server (TTL 120 giây, xem CONTACTS_TTL_SECONDS):
    lần load thường trả cache, chỉ gọi Zalo tươi khi hết TTL hoặc khi
    user bấm tải lại có chủ đích (?force=1). Gặp 429 thì trả cache
    (nếu có) kèm retry_after_seconds + backoff phía server, thay vì
    báo lỗi khô; nút tải lại bị khóa trong thời gian backoff.
    Response thêm: cached, source ("fresh"|"cache"|"cache-after-429"),
    fetched_at, age_seconds, retry_after_seconds, rate_limited.
  POST /api/call/request  {callee_id} -> signaling requestcall (11300)
                          + follow-up request (11301 / 12434, §7l)
  POST /api/call/end      {uid_to, call_id} -> signaling endcall
  GET  /api/svc/catalog   96-service catalog + support status
  POST /api/svc/<action>  addon-service op (services.py; needs login)
  GET  /api/engine/status media-engine seam status
  POST /api/app/login     app login {username, password} -> sets the
                          app session cookie (public)
  POST /api/app/logout    revoke the app session cookie (public)
  GET  /api/app/status    {logged_in, username} (public, for /login)
  GET  /api/webhooks      webhook config (needs login)
  POST /api/webhooks      save webhook config (needs login)
  POST /api/webhooks/test {kind} -> send a test payload, report status
                         (needs login; see zalo_pc_app/webhooks.py)

App login (cong ngoai) is mandatory: every /api/* route except
/api/app/login and /api/app/status, and every page except /login and
its resources (/style.css, /fonts/*), requires a valid app session
cookie (see zalo_pc_app/app_auth.py). Without the app credentials in
the environment the server refuses to start (main() exits). The QR
login (cong trong) stays behind the app login, unchanged.

Real transport uses urllib. Post-login calls send the session cookie
(Cookie header name configurable via ZALO_PC_COOKIE_NAME, default
"zpw_sek" — confirmed as the PC client's cookie name from main.js
setAppCookie). getLoginInfo itself is a *login* API: it carries the
login envelope (imei/computer_name/language/ts + type/client_version/
signkey, encrypted when a param cipher key is configured) plus the
session cookie — never the post-login zpw_ver/zpw_type params.
"""

import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import VERSION as _PKG_VERSION
from . import app_auth
from . import call_log
from . import chat as chat_mod
from . import contacts as contacts_mod
from . import engine_seam
from . import media_endpoints
from . import protocol
from . import qr_login
from . import services as services_mod
from . import session as session_mod
from . import signaling as signaling_mod
from . import webhooks as webhooks_mod
from .crypto import make_device_id

# Version marker (see zalo_pc_app/__init__.py): the Docker build sets
# ZALO_PC_VERSION to the exact commit sha; without it, the code tag
# above applies. /api/status returns it and the UI footer shows it,
# so a deploy can be checked against the pushed code.
VERSION = os.environ.get("ZALO_PC_VERSION") or _PKG_VERSION

DATA_DIR = os.environ.get("ZALO_PC_DATA_DIR", "./data")
PORT = int(os.environ.get("ZALO_PC_PORT", "8080"))
HOST = os.environ.get("ZALO_PC_HOST", "127.0.0.1")
PARAM_CIPHER_KEY = os.environ.get("ZALO_PC_PARAM_CIPHER_KEY", "") or None
COOKIE_NAME = os.environ.get("ZALO_PC_COOKIE_NAME", "zpw_sek")

# Contacts cache + 429 backoff (sửa lỗi 429 ngày 2026-11-05).
# Nguyên nhân gốc (log thật 17:37 +07): /api/contacts gọi lại Zalo
# tươi MỖI lần load, không cache — 7 khối [contacts-shape] giống hệt
# nhau liên tiếp (friends len=60 + groups v4 len=6 + getmg-v2 len=6)
# dội vào Zalo tới 7 lần, tới khi friends trả 429.
#   TTL 120 giây: danh bạ (bạn bè/nhóm) đổi chậm theo ngày/giờ, không
#   theo giây; 120s đủ để một phiên duyệt (chuyển tab, bấm xem lại)
#   chỉ tốn TỐI ĐA 1 lần gọi tươi, vẫn đủ mới khi có bạn/nhóm mới
#   (60s thì vẫn dội gấp đôi khi user bấm qua lại; 300s thì một nhóm
#   mới tạo phải chờ tới 5 phút mới thấy). Người dùng luôn có thể
#   bấm "Tải lại" để lấy tươi ngay (trừ khi đang backoff vì 429).
#   BACKOFF 60 giây (gấp đôi mỗi lần 429 liên tiếp, tối đa 300 giây):
#   Zalo không công bố Retry-After cho getfriends; 60s là khoảng chờ
#   an toàn, đủ để cơn giới hạn qua đi mà không bắt user chờ quá lâu,
#   và cấp số nhân ngăn việc bấm tải lại liên tục kéo dài 429.
CONTACTS_TTL_SECONDS = 120
CONTACTS_BACKOFF_BASE_SECONDS = 60
CONTACTS_BACKOFF_MAX_SECONDS = 300

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class _Transport:
    """HTTP transport for one session: callable as http_get(url,
    timeout) (the shape qr_login/signaling/contacts expect) plus an
    http_post(url, form, timeout) for the getmg-v2 POST (form body
    params=<AES JSON>, Content-Type application/x-www-form-urlencoded).
    Both carry the zpw_sek cookie when one was supplied."""

    def __init__(self, cookie_value=""):
        self.cookie_value = cookie_value

    def __call__(self, url, timeout=30):
        return self.http_get(url, timeout=timeout)

    def _request(self, url, method, data, timeout, content_type=None):
        req = urllib.request.Request(url, method=method, data=data)
        req.add_header("User-Agent", "zalo-pc-qr/1.0")
        if method == "POST":
            req.add_header("Content-Type",
                           content_type
                           or "application/x-www-form-urlencoded")
        if self.cookie_value:
            req.add_header("Cookie", "%s=%s" % (COOKIE_NAME,
                                                self.cookie_value))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {}
            return e.code, body
        except (TimeoutError, socket.timeout):
            raise TimeoutError("%s timeout: %s" % (method, url))

    def http_get(self, url, timeout=30):
        return self._request(url, "GET", None, timeout)

    def http_post(self, url, form, timeout=30):
        return self._request(url, "POST", form.encode("utf-8"), timeout)

    def http_post_multipart(self, url, body_bytes, content_type,
                            timeout=60):
        """POST multipart (chat file/photo/voice): body la bytes da
        dung san, Content-Type mang boundary (xem chat.build_multipart).
        Them cho module chat; khong doi hanh vi http_post cu."""
        return self._request(url, "POST", body_bytes, timeout,
                             content_type=content_type)


def make_transport(cookie_value=""):
    """http_get(url, timeout) -> (status, json_dict), callable, with
    .http_post(url, form, timeout) attached (see _Transport)."""
    return _Transport(cookie_value)


_LAST_CALL_ID = 0


def _normalize_call_id(value):
    """Coerce a UI-supplied call_id to the JSON NUMBER the real
    client sends (native engine: callId is uint32 — ZaloCall.exe
    `_initCallConfig ... callId = %u`). The pre-fix UI sent
    String(Date.now()) — a 13-digit string, wrong type AND out of
    uint32 range — one of the two 114 suspects (§7k). Digit
    strings are kept (int of them); anything else (missing,
    non-numeric, out of range) falls back to epoch seconds, which
    fits uint32. Every result is made strictly greater than the
    previous callId, so rapid successive calls never collide."""
    global _LAST_CALL_ID
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= 2 ** 32 - 1:
        n = int(time.time())
    if n <= _LAST_CALL_ID:
        n = _LAST_CALL_ID + 1
    _LAST_CALL_ID = n
    return n


def _coerce_call_id(value):
    """Coerce a UI-supplied call_id to the JSON NUMBER the real
    client sends (native engine: callId is uint32), or None when it
    is missing/non-numeric/out of range. Unlike _normalize_call_id
    this invents NO id: an end with no usable id must not mint a
    fresh callId — it falls back to the live call instead (see
    /api/call/end)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if not 1 <= n <= 2 ** 32 - 1:
        return None
    return n


def _type_request_for(call_type):
    """typeRequest for an AUDIO call of this thread type: 1 for a
    1-1 call, 5 for a group call (bundle makeCall enum
    1/3/5/6 — see protocol.CALL_TYPE_*). The body's type_request
    is NOT trusted: the pre-fix UI sent 0, a value that exists
    nowhere in the client's vocabulary and drew inner 114 from
    the real server (§7k). Video would be 3/6, but this app only
    places audio calls."""
    return (protocol.CALL_TYPE_AUDIO_GROUP if call_type == "group"
            else protocol.CALL_TYPE_AUDIO_1_1)


class AppState:
    def __init__(self, data_dir, auth=None):
        self.data_dir = data_dir
        # App login (cong ngoai): load from env unless the caller
        # injects one (tests). Missing credentials -> auth is None and
        # auth_error names the missing env vars; main() refuses to
        # serve in that case, so the app never runs without a password.
        # (auth=None here only lets unit tests construct a state
        # without env creds; the HTTP handler treats it as "not
        # configured", never as "open" in production — see main().)
        self.auth_error = ""
        if auth is not None:
            self.auth = auth
        else:
            try:
                self.auth = app_auth.AppAuth.from_env(data_dir)
            except app_auth.MissingAppCredentials as e:
                self.auth = None
                self.auth_error = str(e)
        self.store = session_mod.SessionStore(
            os.path.join(data_dir, "session.json"))
        self.lock = threading.Lock()
        self.qr = None          # current QR record (memory only)
        self.qr_state = "idle"  # idle|waiting|scanned|done|expired|
        # rejected|rate_limited|error
        self.qr_error = ""
        self.qr_wait = 0
        self.session = self.store.load() if self.store.exists() else None
        # First friends load after start/login sends init=1 (real client
        # _isFirstReq()). Cleared after the first successful friends call.
        self._contacts_init_pending = True
        # Contacts cache (in-memory, per current Zalo session): the
        # 429 fix — see CONTACTS_TTL_SECONDS above. {"friends": {...},
        # "groups": {...}, "fetched_at": float epoch, "uid": str}.
        # Serialised by _contacts_lock so concurrent loads cannot
        # stampede Zalo with duplicate fresh fetches.
        self._contacts_lock = threading.Lock()
        # Fetch lock (second lock, see get_contacts): serialises the
        # Zalo calls themselves (one fresh fetch at a time). It is
        # separate from _contacts_lock so a slow Zalo fetch never
        # blocks other loads from being served stale from the cache.
        self._contacts_fetch_lock = threading.Lock()
        self._contacts_cache = None
        # 429 backoff: epoch until which no fresh Zalo call is made.
        # _contacts_backoff_seconds is the NEXT wait (doubles on each
        # consecutive 429, capped; reset to base on any success).
        self._contacts_backoff_until = 0.0
        self._contacts_backoff_seconds = CONTACTS_BACKOFF_BASE_SECONDS
        # Call log (in-memory only): every outgoing call attempt and
        # every end, for the calling monitor (GET /api/calls).
        self.calls = call_log.CallLog()
        # WEBHOOK HOOK (webhooks.py): config in <data_dir>/webhooks.json
        # (mode 0600) + dispatcher. Call events fire from the /api/call
        # handlers below; message/group_event/reaction dispatchers are
        # hooked in webhooks.py for the sync channel (O3) to call.
        self.webhook_store = webhooks_mod.WebhookStore(
            os.path.join(data_dir, webhooks_mod.FILENAME))
        self.webhook_dispatcher = webhooks_mod.WebhookDispatcher(
            self.webhook_store)
        # Chat: tin da gui trong phien (RAM, mat khi restart) de hien
        # ngay tin vua gui + lam lich su tam cho 1-1 (chat.ChatStore).
        self.chat_store = chat_mod.ChatStore()
        self.thread = None
        # Stale-while-revalidate (sửa lỗi load chậm 2026-11-05): khi
        # cache đã hết TTL, GET /api/contacts trả cache cũ NGAY
        # (source "stale") rồi làm mới nền trong một thread riêng,
        # thay vì bắt trình duyệt chờ gọi tươi lên Zalo. Chỉ khi
        # hoàn toàn chưa có cache mới chờ gọi tươi. _contacts_refreshing
        # + _contacts_refresh_token chống hai lần làm mới nền chồng
        # nhau; token để thread cũ kết thúc không xóa cờ của lần mới.
        self._contacts_refreshing = False
        self._contacts_refresh_token = 0

    # -- session helpers -------------------------------------------------
    def public_status(self, app_user=""):
        with self.lock:
            base = {"version": VERSION,
                    "engine": engine_seam.SEAM.status(),
                    "app_user": app_user}
            if self.session and self.session.get("zpw_sek"):
                base.update({"login": True,
                             "uid": self.session.get("uid", ""),
                             "phonenum": self.session.get("phonenum", "")})
                return base
            base.update({"login": False, "uid": "", "phonenum": ""})
            return base

    # -- contacts cache + 429 backoff ------------------------------------
    def _contacts_clear_cache(self):
        """Drop the contacts cache and any backoff. Called on logout
        and on a new login (new session = new cache key); never
        touches the session itself."""
        with self._contacts_lock:
            self._contacts_cache = None
            self._contacts_backoff_until = 0.0
            self._contacts_backoff_seconds = CONTACTS_BACKOFF_BASE_SECONDS

    @staticmethod
    def _is_rate_limited(exc):
        """True when an exception is a Zalo 429. contacts._unwrap
        raises "contacts: ... network status=429" for an HTTP 429
        (the shape in the real 2026-11-05 log) or "... error_code=429"
        for a 429 carried as an error code; both count."""
        s = str(exc)
        return ("status=429" in s or "error_code=429" in s
                or "HTTP 429" in s or "Too Many Requests" in s)

    @staticmethod
    def _contacts_payload(friends, groups, source, fetched_at,
                          rate_limited=False, retry_after_seconds=0,
                          stale=False):
        """One /api/contacts body. `friends`/`groups` are the
        Contacts results ({rows, raw}); the extra fields let the UI
        show cache/429 state instead of guessing. `fetched_at` is
        the epoch the cached data was fetched from Zalo. `stale`
        is True only for source "stale": dữ liệu cũ đã hết TTL,
        trả ngay trong lúc chờ làm mới nền (xem get_contacts)."""
        now = time.time()
        return {"friends": friends, "groups": groups,
                "cached": source != "fresh",
                "source": source,
                "fetched_at": int(fetched_at),
                "age_seconds": max(0, int(now - fetched_at)),
                "retry_after_seconds": int(retry_after_seconds),
                "rate_limited": bool(rate_limited),
                "stale": bool(stale)}

    def get_contacts(self, sess, force=False):
        """GET /api/contacts implementation: (http_status, payload).

        - Session change invalidates the cache (uid differs).
        - Backoff (after a 429) blocks EVERY fresh fetch, forced or
          not: return the cache if there is one (200), else 429 with
          retry_after_seconds — never call Zalo again mid-backoff.
        - Fresh cache (age < TTL) + no force: return the cache, no
          Zalo call at all. This is the 429 fix: the old code called
          Zalo fresh on every load (7 identical [contacts-shape]
          blocks in a row in the real log; 8 by 17:53).
        - STALE-WHILE-REVALIDATE (sửa lỗi load chậm 2026-11-05):
          cache exists but is past TTL + no force: return the stale
          cache IMMEDIATELY (source "stale", stale=true) and refresh
          in a background thread, so a refresh never hangs the page
          while Zalo is slow or rate-limiting. The UI shows the old
          list at once and re-loads shortly after to pick up the
          fresh data. Only a load with NO cache at all waits for a
          fresh fetch. ?force=1 still fetches synchronously (the
          user explicitly asked for fresh now) but still honours
          the backoff.
        - Otherwise fetch fresh (friends, then groups — parse code
          unchanged, in contacts.py). Friends success consumes the
          init=1 flag even if groups then fails (old behaviour);
          friends failure leaves it pending. Only a fully successful
          fetch is cached and resets the backoff.
        - A 429 mid-fetch: set/extend the backoff (exponential up
          to the cap), discard the partial fresh result, and return
          the cache if there is one (200, source "cache-after-429")
          or 429 with retry_after_seconds if there is none.
        - Any other endpoint failure keeps the old attribution:
          502 with "friends: ..." / "groups: ..." naming the
          failing endpoint, and nothing is cached.
        The whole fetch runs under _contacts_lock, so concurrent
        loads queue behind one fresh fetch instead of each firing
        their own Zalo calls. The background refresh uses the same
        lock and the same fetch helper.
        TWO LOCKS (sửa lỗi load chậm 2026-11-05 — concurrent stale
        loads queued behind the background fetch): _contacts_lock
        guards only the in-memory state (cache / backoff /
        refreshing flag / init flag) and is held for short
        decisions; _contacts_fetch_lock serialises the Zalo calls
        themselves. A load that can be served from state never
        waits for a fetch, and a fetch never waits for a load."""
        uid = sess.get("uid", "")
        now = time.time()
        with self._contacts_lock:
            cache = self._contacts_cache
            if cache is not None and cache.get("uid") != uid:
                cache = None
                self._contacts_cache = None
            served = self._contacts_serve_from_state_locked(
                sess, uid, cache, now, force)
            if served is not None:
                return served
        # No servable state (no cache, or ?force=1): fetch fresh.
        # The state lock is released first, so this wait never
        # blocks a concurrent load from being served from the cache.
        return self._contacts_fetch_fresh(sess, uid, force)

    def _contacts_serve_from_state_locked(self, sess, uid, cache, now,
                                          force):
        """Serve a load from in-memory state, or None when a fresh
        fetch is needed. Called with _contacts_lock held. Covers
        the backoff branch, the fresh-cache branch and the stale
        branch (stale also starts the background refresh)."""
        if self._contacts_backoff_until > now:
            remaining = int(self._contacts_backoff_until - now) + 1
            if cache is not None:
                print("[contacts-cache] backoff cache-hit "
                      "retry_after=%ds" % remaining, flush=True)
                return 200, self._contacts_payload(
                    cache["friends"], cache["groups"],
                    "cache-after-429", cache["fetched_at"],
                    rate_limited=True,
                    retry_after_seconds=remaining)
            print("[contacts-cache] backoff no-cache "
                  "retry_after=%ds" % remaining, flush=True)
            return 429, {"error": "Zalo đang giới hạn (429): "
                         "danh bạ tạm thời không tải được, "
                         "thử lại sau %d giây." % remaining,
                         "rate_limited": True,
                         "retry_after_seconds": remaining,
                         "cached": False, "source": "rate-limited"}
        if (not force and cache is not None
                and now - cache["fetched_at"] < CONTACTS_TTL_SECONDS):
            print("[contacts-cache] cache-hit age=%ds"
                  % int(now - cache["fetched_at"]), flush=True)
            return 200, self._contacts_payload(
                cache["friends"], cache["groups"],
                "cache", cache["fetched_at"])
        if not force and cache is not None:
            # Stale cache: serve it NOW, refresh in background.
            # (Backoff was already checked above, so a refresh
            # here is allowed; if it hits 429 it sets the
            # backoff and the cache stays for the next load.)
            self._contacts_start_background_refresh_locked(sess, uid)
            print("[contacts-cache] stale-hit age=%ds "
                  "refresh-background"
                  % int(now - cache["fetched_at"]), flush=True)
            return 200, self._contacts_payload(
                cache["friends"], cache["groups"],
                "stale", cache["fetched_at"], stale=True)
        return None

    def _contacts_fetch_fresh(self, sess, uid, force):
        """Fresh fetch for a foreground load: serialised by the
        fetch lock (one Zalo fetch at a time), then applied under
        the state lock. Re-checks state after acquiring the fetch
        lock — a concurrent fetch (foreground or background) may
        have filled the cache or set a backoff while we waited, in
        which case its result is served instead of fetching again."""
        with self._contacts_fetch_lock:
            with self._contacts_lock:
                cache = self._contacts_cache
                if cache is not None and cache.get("uid") != uid:
                    cache = None
                    self._contacts_cache = None
                now = time.time()
                served = self._contacts_serve_from_state_locked(
                    sess, uid, cache, now, force)
                if served is not None:
                    return served
                init = self._contacts_init_pending
            result = self._contacts_do_fetch(sess, uid, init)
            with self._contacts_lock:
                return self._contacts_apply_fetch_result_locked(
                    uid, result)

    @staticmethod
    def _contacts_do_fetch(sess, uid, init):
        """The Zalo calls themselves (friends, then groups), run
        with NEITHER lock held so a slow Zalo never blocks other
        loads from being served from the cache. Returns (True,
        friends, groups) on success or (False, stage, exc) on an
        endpoint failure — never raises for one; the caller applies
        the result under the state lock."""
        transport = make_transport(sess["zpw_sek"])
        book = contacts_mod.Contacts(transport, sess["device_id"],
                                     sess["zpw_enk"],
                                     transport.http_post)
        try:
            friends = book.friends(init=init)
        except Exception as e:  # noqa: BLE001 - returned, not raised
            return (False, "friends", e)
        try:
            groups = book.groups()
        except Exception as e:  # noqa: BLE001 - returned, not raised
            return (False, "groups", e)
        return (True, friends, groups)

    def _contacts_apply_fetch_result_locked(self, uid, result):
        """Apply a finished fetch under the state lock (held by the
        caller): cache a full success + reset the backoff, or run
        the failure tail (_contacts_fetch_failed). Friends success
        consumes the init=1 flag even if groups then failed (old
        behaviour). A success whose session changed mid-fetch
        (logout / new login) is reported but NOT cached, so a
        background refresh can never resurrect the old session's
        contacts."""
        if result[0]:
            _, friends, groups = result
            self._contacts_init_pending = False
            fetched_at = time.time()
            cur = self.session
            if cur is None or cur.get("uid", "") != uid:
                print("[contacts-cache] fresh discarded: session "
                      "changed during fetch", flush=True)
                return 200, self._contacts_payload(
                    friends, groups, "fresh", fetched_at)
            self._contacts_cache = {"friends": friends, "groups": groups,
                                    "fetched_at": fetched_at, "uid": uid}
            self._contacts_backoff_until = 0.0
            self._contacts_backoff_seconds = CONTACTS_BACKOFF_BASE_SECONDS
            print("[contacts-cache] fresh fetched_at=%d"
                  % int(fetched_at), flush=True)
            return 200, self._contacts_payload(
                friends, groups, "fresh", fetched_at)
        _, stage, exc = result
        if stage == "groups":
            # Friends already succeeded before groups failed.
            self._contacts_init_pending = False
        cache = self._contacts_cache
        if cache is not None and cache.get("uid") != uid:
            cache = None
        return self._contacts_fetch_failed(stage, exc, cache)

    def _contacts_start_background_refresh_locked(self, sess, uid):
        """Start one background refresh thread (lock already held).
        No-op when one is already running — concurrent stale loads
        share it instead of each firing their own refresh."""
        if self._contacts_refreshing:
            return
        self._contacts_refreshing = True
        self._contacts_refresh_token += 1
        token = self._contacts_refresh_token
        snapshot = dict(sess)
        t = threading.Thread(
            target=self._contacts_refresh_background,
            args=(snapshot, uid, token), daemon=True)
        t.start()

    def _contacts_refresh_background(self, sess, uid, token):
        """Background leg of stale-while-revalidate: fetch fresh
        under the fetch lock (so it serialises with any foreground
        fetch) and apply the result under the state lock, exactly
        like a foreground fetch; the returned payload is discarded
        — the UI picks the new data up on its next load. Re-checks
        state after acquiring the fetch lock: a backoff set (or a
        fresh cache filled) while waiting means there is nothing
        to do. A 429 here only sets the backoff; the stale cache
        stays served. The refreshing flag is cleared only if this
        thread is still the current one (a logout/login in between
        may have started a newer one)."""
        try:
            with self._contacts_fetch_lock:
                with self._contacts_lock:
                    cache = self._contacts_cache
                    if cache is not None and cache.get("uid") != uid:
                        cache = None
                    now = time.time()
                    if self._contacts_backoff_until > now:
                        return
                    if (cache is not None
                            and now - cache["fetched_at"]
                            < CONTACTS_TTL_SECONDS):
                        return
                    init = self._contacts_init_pending
                result = self._contacts_do_fetch(sess, uid, init)
                with self._contacts_lock:
                    self._contacts_apply_fetch_result_locked(uid, result)
        except Exception as e:  # noqa: BLE001 - background must not die loud
            print("[contacts-cache] background refresh error: %s" % e,
                  flush=True)
        finally:
            with self._contacts_lock:
                if token == self._contacts_refresh_token:
                    self._contacts_refreshing = False

    def _contacts_fetch_failed(self, stage, exc, cache):
        """Shared tail of get_contacts() for a failed fresh fetch.
        Called with _contacts_lock held. Returns (status, payload)."""
        if self._is_rate_limited(exc):
            wait = self._contacts_backoff_seconds
            self._contacts_backoff_until = time.time() + wait
            self._contacts_backoff_seconds = min(
                wait * 2, CONTACTS_BACKOFF_MAX_SECONDS)
            print("[contacts-cache] 429 at %s backoff=%ds"
                  % (stage, wait), flush=True)
            if cache is not None:
                return 200, self._contacts_payload(
                    cache["friends"], cache["groups"],
                    "cache-after-429", cache["fetched_at"],
                    rate_limited=True, retry_after_seconds=wait)
            return 429, {"error": "Zalo đang giới hạn (429): "
                         "danh bạ tạm thời không tải được, "
                         "thử lại sau %d giây." % wait,
                         "rate_limited": True,
                         "retry_after_seconds": wait,
                         "cached": False, "source": "rate-limited"}
        return 502, {"error": "%s: %s" % (stage, exc)}

    def _device_and_computer(self):
        if self.session and self.session.get("device_id"):
            device_id = self.session["device_id"]
        else:
            device_id = make_device_id()
        return device_id, socket.gethostname()

    # -- QR flow (background thread) ------------------------------------
    def start_qr(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            self.qr_state = "waiting"
            self.qr_error = ""
            self.qr = None
        self.thread = threading.Thread(target=self._qr_worker, daemon=True)
        self.thread.start()
        return True

    def _qr_worker(self):
        try:
            device_id, computer = self._device_and_computer()
            logged_uids = []
            if self.session and self.session.get("uid"):
                logged_uids = [self.session["uid"]]
            transport = make_transport()
            qr = qr_login.fetch_qr(
                transport, device_id, computer, logged_uids,
                param_cipher_key=PARAM_CIPHER_KEY, self_g=0, qr_form=0)
            with self.lock:
                self.qr = qr
                self.qr_state = "waiting"
            qr_login.wait_scan(transport, qr, trust_enabled=False)
            with self.lock:
                self.qr_state = "scanned"
            grant = qr_login.wait_confirm(transport, qr)
            # Session established: fetch login info (login envelope +
            # session cookie, exactly as the PC client sends it).
            login_info = self._fetch_login_info(grant, device_id, computer)
            sess = session_mod.new_session(device_id, computer)
            sess.update({
                "uid": grant["uid"], "dkey": grant["dkey"],
                "phonenum": grant["phonenum"],
                "zpw_sek": grant["zpw_sek"], "zpw_kt": grant["zpw_kt"],
                "zpw_enk": login_info.get("zpw_enk", ""),
                "service_map": login_info.get("config", {}).get(
                    "zpw_service_map_new", {}),
                "ws_endpoint": login_info.get("config", {}).get("zpw_ws", ""),
                "status": session_mod.STATUS_LOGGED_IN,
            })
            self.store.save(sess)
            with self.lock:
                self.session = sess
                self.qr_state = "done"
                self.qr = None
                # New session: next friends load is a first load (init=1).
                self._contacts_init_pending = True
            # New session: the old session's contacts cache is stale.
            self._contacts_clear_cache()
        except qr_login.RateLimited as e:
            with self.lock:
                self.qr_state = "rate_limited"
                self.qr_wait = e.wait_seconds
        except qr_login.UserRejected:
            with self.lock:
                self.qr_state = "rejected"
        except qr_login.QRExpired:
            with self.lock:
                self.qr_state = "expired"
        except qr_login.TrustFlowRequired as e:
            with self.lock:
                self.qr_state = "error"
                self.qr_error = str(e)
        except Exception as e:  # noqa: BLE001 - surface to UI, keep server up
            with self.lock:
                self.qr_state = "error"
                self.qr_error = "%s: %s" % (type(e).__name__, e)

    def _fetch_login_info(self, grant, device_id, computer_name):
        """GET getLoginInfo, exactly as the PC client sends it
        (renderer API class getLoginInfo, api code 11134):
        login envelope (imei/computer_name/language/ts + type/
        client_version/signkey, encrypted when a param cipher key is
        configured) plus the zpw_sek session cookie. The previous
        implementation sent only zpw_ver/zpw_type + cookie, which the
        server rejects with error 102 (session key improperly
        submitted): without the envelope the session cannot be bound
        to the device. The response data carries config, dkey and
        zpw_enk (AES-decrypted first when the request went out
        encrypted)."""
        sek = grant.get("zpw_sek", "")
        if not sek:
            # Never send a cookieless request: the server answers it
            # with a cryptic 102. Name the missing field instead.
            # (The value itself is never logged.)
            raise RuntimeError(
                "getLoginInfo: confirm grant missing zpw_sek "
                "(session key); cannot authenticate without it")
        transport = make_transport(sek)
        query, enk = qr_login.logininfo_query(
            device_id, computer_name, PARAM_CIPHER_KEY)
        url = protocol.build_url(protocol.AUTH_DOMAIN,
                                 "/api/login/getLoginInfo", query)
        status, payload = transport(url, timeout=30)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("getLoginInfo: network status=%s" % status)
        if payload.get("error_code") != 0:
            raise RuntimeError("getLoginInfo: error_code=%s %s" % (
                payload.get("error_code"), payload.get("error_message", "")))
        data = qr_login.decode_response(payload, enk)
        if not isinstance(data, dict):
            data = {}
        return {"zpw_enk": data.get("zpw_enk", ""),
                "config": data.get("config", {}),
                "dkey": data.get("dkey", "")}

    def qr_status(self):
        with self.lock:
            out = {"state": self.qr_state, "error": self.qr_error,
                   "wait_seconds": self.qr_wait}
            if self.qr and self.qr.get("base64_qr"):
                out["qr_image"] = ("data:image/png;base64,"
                                   + self.qr["base64_qr"])
                out["countdown"] = self.qr.get("qr_timeout") or 90
            if self.session and self.session.get("uid"):
                out["uid"] = self.session["uid"]
                out["phonenum"] = self.session.get("phonenum", "")
            return out

    def logout(self):
        with self.lock:
            self.store.clear()
            self.session = None
            self.qr = None
            self.qr_state = "idle"
        # Logged out: the session's contacts cache must go too.
        self._contacts_clear_cache()


STATE = AppState(DATA_DIR)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    # -- helpers ---------------------------------------------------------
    def _send_json(self, obj, status=200, extra_headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or []):
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _app_user(self):
        """Username of the app session in this request, or None.

        STATE.auth is None only when the process was started without
        app credentials (tests constructing a bare state, or the
        import-time global before main() checks it). In that case
        return "" (treated as configured-off by the caller); main()
        refuses to serve, so production never takes this path."""
        if STATE.auth is None:
            return ""
        cookies = {}
        for part in (self.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                name, value = part.strip().split("=", 1)
                cookies[name.strip()] = value.strip()
        return STATE.auth.validate_token(
            cookies.get(app_auth.COOKIE_NAME, ""))

    def _require_app_login(self):
        """Username when the request carries a valid app session;
        "" when app auth is not configured at all (STATE.auth is
        None — only the import-time global / bare test states; main()
        refuses to serve in that case, so production never takes
        this path); None when auth is configured but the request has
        no valid session (caller answers 401 / redirects to /login)."""
        if STATE.auth is None:
            return ""
        user = self._app_user()
        return user if user else None

    def _unauthorized(self):
        return self._send_json({"error": "chua_dang_nhap_app"},
                               status=401)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _require_login(self):
        sess = STATE.session
        if not sess or not sess.get("zpw_sek"):
            return None
        return sess

    # -- routing ---------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/login":
            # The login page itself is public. Already logged in?
            # Back to the app.
            if self._require_app_login() is not None:
                return self._send_redirect("/")
            return self._serve_static("login.html", "text/html")
        if path == "/":
            if self._require_app_login() is None:
                return self._send_redirect("/login")
            return self._serve_static("app.html", "text/html")
        if path == "/app.js":
            if self._require_app_login() is None:
                return self._unauthorized()
            return self._serve_static("app.js", "text/javascript")
        if path == "/style.css":
            # Shared by the login page: public.
            return self._serve_static("style.css", "text/css")
        if path.startswith("/fonts/"):
            # Login page resources: public.
            return self._serve_static(path.lstrip("/"),
                                      "font/woff2")
        if path == "/api/app/status":
            # Public: the login page uses it to redirect when the
            # session is already valid. Never leaks anything else.
            user = self._app_user()
            return self._send_json({"logged_in": bool(user),
                                    "username": user or ""})
        if path.startswith("/api/"):
            app_user = self._require_app_login()
            if app_user is None:
                return self._unauthorized()
            return self._api_get(path, app_user)
        return self._send_json({"error": "not_found"}, status=404)

    def _api_get(self, path, app_user):
        if path == "/api/status":
            return self._send_json(STATE.public_status(app_user))
        if path == "/api/qr/status":
            return self._send_json(STATE.qr_status())
        if path == "/api/engine/status":
            return self._send_json(engine_seam.SEAM.status())
        if path == "/api/svc/catalog":
            # Danh mục 96 service + trạng thái hỗ trợ: chỉ là mô tả
            # tĩnh, không chứa dữ liệu tài khoản — nhưng vẫn nằm sau
            # cổng đăng nhập app như mọi /api/* khác (xem do_GET).
            return self._send_json(services_mod.catalog_public())
        if path == "/api/calls":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            return self._send_json(STATE.calls.snapshot())
        # WEBHOOK HOOK (webhooks.py): read the webhook config. Auth is
        # the same _require_login() as /api/calls — the login-app agent
        # owns that check; do NOT open this route without it.
        if path == "/api/webhooks":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            return self._send_json(STATE.webhook_store.load())
        if path == "/api/contacts":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            # ?force=1 = user bấm "Tải lại" có chủ đích: bỏ qua TTL
            # nhưng KHÔNG bỏ qua backoff sau 429 (xem get_contacts).
            # Mọi load thường (chuyển tab, xem lại, gọi xong quay về)
            # trả cache trong TTL và không gọi Zalo — đó là sửa lỗi 429.
            qs = urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query)
            force = qs.get("force", [""])[0] == "1"
            status, payload = STATE.get_contacts(sess, force=force)
            return self._send_json(payload, status=status)
        # -- CHAT HOOK (module chat.py; diem moc duy nhat o do_GET) --
        # GET /api/thread/<id>/history?type=user|group&count=50
        # Nhom: GET group/history (11240) that + tin da gui trong
        # phien. 1-1: KHONG co endpoint HTTPS — tra thong bao gioi
        # han trung thuc + tin da gui trong phien (chat.py).
        # Auth: _require_login (phien Zalo). Dang nhap app
        # (user/mat khau) chua co trong ban copy nay — integrator
        # phai gan them kiem tra dang nhap app o day khi phan do
        # xong (xem BAO-CAO-CHAT.md).
        if path.startswith("/api/thread/") and path.endswith("/history"):
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            import urllib.parse as _up
            thread_id = path[len("/api/thread/"):-len("/history")]
            thread_id = _up.unquote(thread_id.strip("/"))
            qs = dict(_up.parse_qsl(_up.urlparse(self.path).query))
            thread_type = qs.get("type") or "user"
            if thread_type not in ("user", "group"):
                return self._send_json({"error": "type phai la user|group"},
                                       status=400)
            try:
                count = int(qs.get("count") or 50)
            except ValueError:
                count = 50
            count = max(1, min(count, 200))
            try:
                transport = make_transport(sess["zpw_sek"])
                chat = chat_mod.Chat(transport, sess["device_id"],
                                     sess["zpw_enk"])
                if thread_type == "group":
                    result = chat.history_group(thread_id, count)
                else:
                    result = chat.history_user_unavailable()
                sent = STATE.chat_store.sent_for(thread_type, thread_id)
                seen_ids = {m.get("id") for m in result["messages"]}
                merged = list(result["messages"]) + [
                    m for m in sent
                    if m.get("id") not in seen_ids
                    and m.get("client_id") not in seen_ids]
                result = dict(result)
                result["messages"] = merged
                result["thread_id"] = thread_id
                result["type"] = thread_type
                return self._send_json(result)
            except Exception as e:  # noqa: BLE001
                return self._send_json({"error": str(e)}, status=502)
        return self._send_json({"error": "not_found"}, status=404)

    def _chat_client(self, sess):
        """Chat client cho mot phien Zalo (transport mang cookie
        zpw_sek + http_post_multipart cho upload file)."""
        transport = make_transport(sess["zpw_sek"])
        return chat_mod.Chat(transport, sess["device_id"],
                             sess["zpw_enk"])

    def _read_raw(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        return self.rfile.read(length) if length else b""

    def _handle_thread_post(self, path):
        """-- CHAT HOOK (module chat.py; diem moc duy nhat o do_POST) --
        POST /api/thread/<id>/send | sendfile | sendvoice | typing
        | seen | sendlink. Tat ca can _require_login (phien Zalo);
        dang nhap app chua co trong ban copy — xem ghi
        chu o route history tren. sendfile/sendvoice la multipart
        (doc raw, khong doc JSON nhu cac POST khac). sendlink gui
        link (11286/11193) qua chat.send_link."""
        import urllib.parse as _up
        segs = [s for s in path.split("/") if s]
        # segs = ["api", "thread", <id>, <action>]
        if len(segs) != 4:
            return self._send_json({"error": "not_found"}, status=404)
        thread_id = _up.unquote(segs[2])
        action = segs[3]
        sess = self._require_login()
        if sess is None:
            return self._send_json({"error": "chua_dang_nhap"},
                                   status=401)
        thread_type = None
        if action in ("send", "typing", "seen", "sendlink"):
            body = self._read_json()
            thread_type = body.get("type") or "user"
        elif action in ("sendfile", "sendvoice"):
            raw = self._read_raw()
            fields, files = chat_mod.parse_multipart(
                raw, self.headers.get("Content-Type") or "")
            thread_type = fields.get("type") or "user"
            body = {"_fields": fields, "_files": files}
        else:
            return self._send_json({"error": "not_found"}, status=404)
        if thread_type not in ("user", "group"):
            return self._send_json({"error": "type phai la user|group"},
                                   status=400)
        try:
            chat = self._chat_client(sess)
            if action == "send":
                message = (body.get("message") or "").strip()
                if not message:
                    return self._send_json({"error": "message rong"},
                                           status=400)
                try:
                    ttl = int(body.get("ttl") or 0)
                except (TypeError, ValueError):
                    ttl = 0
                res = chat.send_text(thread_type, thread_id, message,
                                     ttl=ttl)
                local = STATE.chat_store.local_message(
                    thread_type, thread_id, "text", text=message,
                    client_id=res["client_id"])
                STATE.chat_store.record_sent(thread_type, thread_id,
                                             local)
                return self._send_json({"ok": True, "data": res["data"],
                                        "message": local})
            if action == "sendlink":
                link = (body.get("link") or "").strip()
                if not link:
                    return self._send_json({"error": "link rong"},
                                           status=400)
                try:
                    ttl = int(body.get("ttl") or 0)
                except (TypeError, ValueError):
                    ttl = 0
                res = chat.send_link(
                    thread_type, thread_id, link,
                    message=body.get("message") or "",
                    title=body.get("title") or "",
                    desc=body.get("desc") or "",
                    thumb=body.get("thumbnail") or "", ttl=ttl)
                local = STATE.chat_store.local_message(
                    thread_type, thread_id, "text",
                    text=body.get("message") or link,
                    client_id=res["client_id"])
                STATE.chat_store.record_sent(thread_type, thread_id,
                                             local)
                return self._send_json({"ok": True, "data": res["data"],
                                        "message": local})
            if action == "typing":
                data = chat.send_typing(thread_type, thread_id)
                return self._send_json({"ok": True, "data": data})
            if action == "seen":
                msg_ids = body.get("msg_ids") or []
                data = chat.send_seen(thread_type, thread_id, msg_ids)
                return self._send_json({"ok": True, "data": data})
            # sendfile / sendvoice: multipart, field file = fileContent.
            files = body["_files"]
            fields = body["_fields"]
            if "file" not in files:
                return self._send_json(
                    {"error": "thieu file (field 'file')"}, status=400)
            filename, mime, data_bytes = files["file"]
            if len(data_bytes) > 100 * 1024 * 1024:
                return self._send_json({"error": "file qua lon (>100MB)"},
                                       status=400)
            if action == "sendfile":
                kind = fields.get("kind") or "file"
                if kind == "photo":
                    try:
                        width = int(fields.get("width") or 0)
                        height = int(fields.get("height") or 0)
                    except ValueError:
                        width, height = 0, 0
                    res = chat.send_photo(thread_type, thread_id,
                                          filename, data_bytes, mime,
                                          width, height)
                    local_kind = "photo"
                else:
                    res = chat.send_file(thread_type, thread_id,
                                         filename, data_bytes, mime)
                    local_kind = "file"
                local = STATE.chat_store.local_message(
                    thread_type, thread_id, local_kind,
                    text=filename, file_name=filename,
                    client_id=res["client_id"])
                STATE.chat_store.record_sent(thread_type, thread_id,
                                             local)
                return self._send_json({"ok": True, "data": res["data"],
                                        "message": local})
            # sendvoice: file ghi am cua trinh duyet (MediaRecorder).
            # Ten file giu nguyen (thuong .webm, khong phai .mp3) —
            # xem ghi chu o chat.py; Zalo that co the tu choi file
            # khong phai mp3.
            res = chat.send_voice(thread_type, thread_id, filename,
                                  data_bytes, mime)
            local = STATE.chat_store.local_message(
                thread_type, thread_id, "voice", text=filename,
                file_name=filename, client_id=res["client_id"])
            STATE.chat_store.record_sent(thread_type, thread_id, local)
            return self._send_json({"ok": True, "data": res["data"],
                                    "message": local,
                                    "note": "Thu am tai trinh duyet "
                                    "roi gui file (khong phai ghi am "
                                    "native cua Zalo PC)."})
        except Exception as e:  # noqa: BLE001
            return self._send_json({"error": str(e)}, status=502)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        # CHAT HOOK: route /api/thread/* doc o _handle_thread_post
        # (multipart thi doc raw, khong doc JSON truoc).
        if path.startswith("/api/thread/"):
            return self._handle_thread_post(path)
        # /api/svc/* multipart (doi avatar): doc raw o _api_post,
        # khong doc JSON truoc (giong /api/thread/*).
        if path.startswith("/api/svc/") and "multipart/form-data" in (
                self.headers.get("Content-Type") or ""):
            body = {}
        else:
            body = self._read_json()
        if path == "/api/app/login":
            # Public. One generic failure for a wrong user OR a wrong
            # password — never say which one exists.
            if STATE.auth is None:
                return self._send_json(
                    {"error": "app_chua_cau_hinh"}, status=503)
            if STATE.auth.verify(body.get("username", ""),
                                 body.get("password", "")):
                token, expires = STATE.auth.create_session(
                    body.get("username", ""))
                max_age = max(0, int(expires - time.time()))
                return self._send_json(
                    {"ok": True, "username": body.get("username", "")},
                    extra_headers=[("Set-Cookie",
                                    app_auth.cookie_header(token, max_age))])
            return self._send_json({"error": "sai_tai_khoan"}, status=401)
        if path == "/api/app/logout":
            # Public on purpose: a stale page must be able to drop a
            # dead session. Revokes the token if one is presented.
            self._revoke_app_token()
            return self._send_json(
                {"ok": True},
                extra_headers=[("Set-Cookie",
                                app_auth.clear_cookie_header())])
        if path.startswith("/api/"):
            app_user = self._require_app_login()
            if app_user is None:
                return self._unauthorized()
            return self._api_post(path, body, app_user)
        return self._send_json({"error": "not_found"}, status=404)

    def _revoke_app_token(self):
        if STATE.auth is None:
            return
        cookies = {}
        for part in (self.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                name, value = part.strip().split("=", 1)
                cookies[name.strip()] = value.strip()
        STATE.auth.revoke_token(cookies.get(app_auth.COOKIE_NAME, ""))

    def _api_post(self, path, body, app_user):
        if path == "/api/qr/new":
            STATE.start_qr()
            return self._send_json({"ok": True})
        if path.startswith("/api/svc/"):
            # MÓC DỊCH VỤ (services.py): POST /api/svc/<action>.
            # Bảo vệ bằng phiên Zalo (_require_login), giống
            # /api/contacts và /api/call/*. Đăng nhập app
            # (user/mật khẩu) chưa có — integrator bọc thêm auth
            # app quanh nhánh này khi agent đăng nhập xong (xem
            # services.AUTH_NOTE). Không đụng signaling/call.
            action = path[len("/api/svc/"):]
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            if not action or "/" in action:
                return self._send_json({"error": "not_found"},
                                       status=404)
            # Doi avatar (change_group_avatar / change_account_
            # avatar): multipart field "file" — doc raw o day vi
            # do_POST chua doc body (xem ghi chu o do_POST).
            files = None
            if "multipart/form-data" in (
                    self.headers.get("Content-Type") or ""):
                raw = self._read_raw()
                fields, files = chat_mod.parse_multipart(
                    raw, self.headers.get("Content-Type") or "")
                body = fields
            status, obj = services_mod.handle_svc(
                STATE, action, body, files=files)
            return self._send_json(obj, status=status)
        if path == "/api/logout":
            # Dang xuat: xoa ca phien Zalo (cu) LAN phien app (moi)
            # — nut "Dang xuat" o sidebar goi endpoint nay roi ve
            # trang /login. Cookie app bi thu hoi + xoa o client.
            self._revoke_app_token()
            STATE.logout()
            return self._send_json(
                {"ok": True},
                extra_headers=[("Set-Cookie",
                                app_auth.clear_cookie_header())])
        if path == "/api/call/request":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            # Log the attempt for the calling monitor (GET /api/calls):
            # the UI sends the peer's display name; the log never
            # carries secrets, only who/when/which thread/result.
            # The requestcall body is built to match the real client
            # (§7k): call_id is normalized to a uint32 JSON number
            # and type_request is derived from the thread type
            # (1-1 audio=1, group audio=5) — the body's own
            # type_request is NOT trusted (the pre-fix UI sent 0).
            # The effective call_id is returned so the UI uses the
            # same id for /api/call/end (endcall must carry the same
            # callId the requestcall used).
            call_id = _normalize_call_id(body.get("call_id"))
            thread_id = body.get("callee_id", "")
            call_type = body.get("type") or "user"
            type_request = _type_request_for(call_type)
            peer = body.get("peer_name") or thread_id
            try:
                transport = make_transport(sess["zpw_sek"])
                sig = signaling_mod.Signaling(transport, sess["device_id"],
                                              sess["zpw_enk"])
                # Calls are addressed by threadID (addon/zca-js model):
                # type "user"  -> 1-1 requestcall (11300), calleeId is
                #   the user threadId; type "group" -> group/requestcall
                #   (12433), groupId is the group threadId. Sending a
                #   group id through the 1-1 endpoint is wrong.
                if call_type == "group":
                    data = sig.request_call_group(
                        thread_id,
                        call_id,
                        type_request,
                        body.get("data"),
                        body.get("partners"))
                else:
                    data = sig.request_call(
                        thread_id,
                        call_id,
                        body.get("codec"),
                        type_request)
                # §7l — SECOND STEP, the one the 17:51 live call was
                # missing: after requestcall the real client sends
                # `request` (11301, 1-1) / `group/request` (12434)
                # with the caller's media endpoints, and only then
                # does the server hold a complete invitation for the
                # far end. Without it the requestcall is accepted
                # (no error) but the callee's phone never rings.
                # Phase 2 (stage 2): the endpoints come from the
                # real relay allocation (`media_endpoints`, backed
                # by `Udp4200Transport`) — the 11300 response's
                # `zrtc_config.servers` / `sessId` / `srtpKey`
                # (see `allocation_from_requestcall_data`). When
                # that allocation is missing, `for_call` raises
                # `MissingTransportParam` NAMING the missing
                # parameter instead of returning the phase-1 empty
                # placeholders: the real engine NEVER sends 416
                # with empty addresses, so this app does not
                # either. The step stays BEST-EFFORT: the call is
                # still reported ok (requestcall succeeded) but
                # request_sent=False is returned and logged, so
                # the UI/monitor can tell "invitation may not
                # have been delivered" apart from "fully sent".
                # Media hooks (Opus 16 kHz + SRTP) are best-effort
                # too: `pc_media.media_hooks_for_call` builds them
                # when libopus/libsrtp2 are available; when they
                # are not (the stdlib-only image), the transport
                # still handshakes and the call signals, but voice
                # stays unwired — never a crash, never a lie.
                request_sent, request_error = True, ""
                endpoints = None
                try:
                    hooks = {}
                    _alloc = media_endpoints.\
                        allocation_from_requestcall_data(data)
                    if _alloc.get("srtp_key") is not None:
                        try:
                            from . import pc_media
                            hooks = pc_media.media_hooks_for_call(
                                _alloc["srtp_key"])
                        except Exception:  # noqa: BLE001 - optional
                            hooks = {}
                    endpoints = media_endpoints.ENDPOINTS.for_call(
                        call_id=call_id, callee_id=thread_id,
                        call_type=call_type, codec=body.get("codec"),
                        requestcall_data=data, **hooks)
                except Exception as exc:  # noqa: BLE001 - best-effort
                    request_sent, request_error = False, str(exc)
                if endpoints is not None:
                    try:
                        if call_type == "group":
                            sig.send_request_group(
                                thread_id, call_id, type_request,
                                body.get("data"), endpoints["session"],
                                body.get("partners"), thread_id)
                        else:
                            sig.send_request(
                                thread_id, endpoints["rtcp_address"],
                                endpoints["rtp_address"],
                                endpoints["codec"],
                                endpoints["session"], call_id,
                                endpoints["extend_data"])
                        # 11301 accepted: attach the media engine
                        # to the started transport (best-effort;
                        # never breaks the call when it fails).
                        engine_seam.SEAM.attach_pc_media(
                            media_endpoints.ENDPOINTS.active_record(
                                call_id))
                    except Exception as exc:  # noqa: BLE001 - best-effort
                        request_sent, request_error = False, str(exc)
                sent_entry = STATE.calls.record_start(call_id, peer, thread_id,
                                         call_type)
                STATE.calls.record_request(call_id, request_sent,
                                           request_error)
                # WEBHOOK HOOK (webhooks.py): call.sent fires NOW —
                # the app is the source, no sync channel needed.
                # Fire-and-forget: never blocks the call response.
                webhooks_mod.dispatch_call_event(
                    STATE.webhook_dispatcher, sent_entry,
                    sess.get("uid", ""))
                return self._send_json({"ok": True, "data": data,
                                        "call_id": call_id,
                                        "request_sent": request_sent,
                                        "request_error": request_error})
            except Exception as e:  # noqa: BLE001
                err_entry = STATE.calls.record_error(call_id, peer, thread_id,
                                         call_type, str(e))
                # WEBHOOK HOOK (webhooks.py): call.error, same as above.
                webhooks_mod.dispatch_call_event(
                    STATE.webhook_dispatcher, err_entry,
                    sess.get("uid", ""))
                return self._send_json({"error": str(e)}, status=502)
        if path == "/api/call/end":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            # End is LOCAL-FIRST (§7m). The live 18:06 bug: the old
            # handler only marked the log ended when the Zalo
            # endcall succeeded — a slow or failing endcall left
            # the call stuck on "ringing" in the UI (and the UI
            # ignored the 502). Mark it ended first, then attempt
            # the Zalo endcall (best-effort); a failure is recorded
            # in the log entry's detail and returned, never leaves
            # the call stuck. The response is always ok when a call
            # was ended locally, even if Zalo rejected the endcall.
            # Resolve the target: the body's call_id (coerced to a
            # uint32 number — the detail view builds it from the
            # log record, where it is a STRING; sending it as a
            # string can draw inner 114, same lesson as
            # requestcall §7k), else the live call (there is at
            # most one; the End button's intent is unambiguous).
            raw_id = body.get("call_id", "")
            call_id = _coerce_call_id(raw_id)
            live = STATE.calls.snapshot()["active"]
            ended = None
            if call_id is not None:
                ended = STATE.calls.record_end(call_id)
            if ended is None and live is not None:
                ended = STATE.calls.end_active()
            if ended is None:
                return self._send_json(
                    {"ok": True, "ended_call_id": None,
                     "zalo_endcall_ok": False,
                     "zalo_error": "no_live_call"})
            # WEBHOOK HOOK (webhooks.py): call.ended — kept from
            # the merge; dispatch with the ended entry, after the
            # local-first record_end, only when a live call record
            # existed (ended is not None here).
            webhooks_mod.dispatch_call_event(
                STATE.webhook_dispatcher, ended,
                sess.get("uid", ""))
            ended_id = int(ended["call_id"])
            uid_to = body.get("uid_to") or ended["thread_id"]
            call_type = (body.get("type") or ended.get("type")
                         or "user")
            zalo_ok, zalo_error, data = True, "", {}
            try:
                transport = make_transport(sess["zpw_sek"])
                sig = signaling_mod.Signaling(transport, sess["device_id"],
                                              sess["zpw_enk"])
                if call_type == "group":
                    data = sig.endcall_group(
                        ended["thread_id"], ended_id,
                        protocol.CALL_TYPE_AUDIO_GROUP, True,
                        body.get("data"), body.get("partners"))
                else:
                    data = sig.endcall(uid_to, ended_id)
            except Exception as e:  # noqa: BLE001 - best-effort
                zalo_ok, zalo_error = False, str(e)
                STATE.calls.record_end_error(ended_id, zalo_error)
            # Phase 2: stop the media engine + the relay transport
            # for this call (best-effort; a stuck UDP socket must
            # not leave the call half-alive after the user ends it).
            engine_seam.SEAM.stop_media()
            media_endpoints.ENDPOINTS.stop_call(ended_id)
            return self._send_json(
                {"ok": True, "ended_call_id": ended_id,
                 "zalo_endcall_ok": zalo_ok, "zalo_error": zalo_error,
                 "data": data})
        # WEBHOOK HOOK (webhooks.py): save the webhook config. Auth is
        # the same _require_login() as /api/calls. Bad URL -> 400,
        # nothing written. Unknown keys are dropped by normalize.
        if path == "/api/webhooks":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            try:
                cfg = STATE.webhook_store.save(body)
            except ValueError as e:
                return self._send_json({"error": str(e)}, status=400)
            return self._send_json({"ok": True, "config": cfg})
        # WEBHOOK HOOK (webhooks.py): «Gửi thử» one family. Body:
        # {"kind": "message"|"group_event"|"reaction"|"call"}.
        # Synchronous on purpose: the settings page needs the HTTP
        # status back. Short timeout (5 s); a failure is reported,
        # never raised.
        if path == "/api/webhooks/test":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            kind = body.get("kind", "")
            if kind not in webhooks_mod.KIND_MAP:
                return self._send_json(
                    {"error": "kind khong hop le: %s" % kind}, status=400)
            result = STATE.webhook_dispatcher.send_test(
                kind, sess.get("uid", ""))
            return self._send_json(result)
        return self._send_json({"error": "not_found"}, status=404)

    def _serve_static(self, name, ctype):
        try:
            with open(os.path.join(STATIC_DIR, name), "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return self._send_json({"error": "not_found"}, status=404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    # App login is mandatory: refuse to start without credentials
    # instead of ever serving the app unprotected.
    if STATE.auth is None:
        print("KHONG KHOI DONG DUOC: %s" % STATE.auth_error,
              file=sys.stderr)
        print("Dat ZALO_PC_APP_USER + ZALO_PC_APP_PASSWORD (hoac "
              "ZALO_PC_APP_PASSWORD_HASH) luc deploy, roi chay lai.",
              file=sys.stderr)
        raise SystemExit(2)
    server = QuietServer((HOST, PORT), Handler)
    print("zalo-pc-qr app %s on http://%s:%d (data: %s)"
          % (VERSION, HOST, PORT, DATA_DIR))
    print("Dang nhap app: bat buoc (user %s, phien %s gio)"
          % (STATE.auth.username, STATE.auth.session_hours))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


class QuietServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that stays silent when a client disconnects
    before sending a request.

    Browsers/proxies sometimes open a connection and close it (RST)
    before any request line arrives; socketserver then logs a full
    traceback (ConnectionResetError: [Errno 104] Connection reset by
    peer, in process_request_thread -> rfile.readline). The server is
    fine — the client simply went away — but the traceback pollutes
    the log and looks like the app is broken. Swallow exactly that
    class of error; anything else still prints as before."""

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


if __name__ == "__main__":
    main()
