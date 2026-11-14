"""App service: stdlib HTTP server + JSON API + static UI.

API (all JSON, never returns session secrets):
  GET  /api/status        {login, uid, phonenum, engine, sync,
                          sync_error} (needs app login) — sync is the
                          live sync-channel state (running /
                          no_endpoints / refresh_failed / stopped /
                          logged_out / kicked_out); sync_error names
                          only the last failure type/code, never a
                          value. See AppState.sync_status.
  POST /api/sync/retry    retry opening the sync channel for the
                          current session (needs login; 30s cooldown
                          between attempts, 429 with
                          retry_after_seconds while cooling down)
  POST /api/qr/new        start a QR login (background thread)
  GET  /api/qr/status     {state, qr_image, countdown, wait_seconds, ...}
  POST /api/logout        clear the stored Zalo session AND the app
                          session (revokes the app cookie)
  POST /api/zalo/logout   clear ONLY the Zalo session (app login kept) -> UI shows the QR screen
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
                          (11306) for an answered call, cancel
                          (11305) for an unanswered one
  POST /api/call/answered {call_id} -> mark the live call answered
                          (peer picked up): disarms the ring timer,
                          sends answerack (11304) best-effort for
                          1-1 calls; also fired by first inbound
                          RTP (media proves the answer, no sync
                          channel needed)
  POST /api/call/answer   {call_id} -> answer an INCOMING call
                          (we are the callee): 11300 fallback +
                          11303 answer; NO 11301 and NO 11304
                          (both are the caller's signals, zca-js)
  POST /api/call/reject   {call_id} -> reject an INCOMING call:
                          cancel (11305) + endcall (11306),
                          zca-js rejectIncomingCall
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
import re
import http.client
import socket
import sys
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import VERSION as _PKG_VERSION
from . import app_auth
from . import call_audio as call_audio_mod
from . import ffmpeg_log as ffmpeg_log_mod
from . import account_health
from . import event_dedup as event_dedup_mod
from . import ws_listener as ws_listener_mod
from . import recall_queue as recall_mod
from . import profile_names as profile_names_mod
from . import video_probe as video_probe_mod
from . import image_size as image_size_mod
from . import call_tags as call_tags_mod
from .calls import outgoing as outgoing_calls  # noqa: E402  (calls/outgoing.py)
_ring_timeout_fire = outgoing_calls._ring_timeout_fire
_arm_ring_timer = outgoing_calls._arm_ring_timer
_disarm_ring_timer = outgoing_calls._disarm_ring_timer
_send_answerack_async = outgoing_calls._send_answerack_async
EXTEND_PROFILES = outgoing_calls.EXTEND_PROFILES
_extend_profile_for_call = outgoing_calls._extend_profile_for_call
from .calls import incoming as incoming_calls  # noqa: E402  (calls/incoming.py)
_send_ringring_async = incoming_calls._send_ringring_async
_offer_extend = incoming_calls._offer_extend
_reject_signals = incoming_calls._reject_signals
_answer_incoming = incoming_calls._answer_incoming
from .calls import voice as voice_calls  # noqa: E402  luồng voice tách riêng (calls/voice.py)
AUDIO_SENDERS = voice_calls.AUDIO_SENDERS
SPEAKER_SINKS = voice_calls.SPEAKER_SINKS
ECHO_GUARDS = voice_calls.ECHO_GUARDS
_stop_mic = voice_calls._stop_mic
_stop_speaker = voice_calls._stop_speaker
_guard_for_call = voice_calls._guard_for_call
_start_speaker = voice_calls._start_speaker
_start_mic = voice_calls._start_mic
DEAD_MEDIA_SECONDS = voice_calls.DEAD_MEDIA_SECONDS
_media_is_dead = voice_calls._media_is_dead
_watch_dead_media = voice_calls._watch_dead_media
from .calls import video as video_calls  # noqa: E402  luồng video tách riêng (calls/video.py)
VIDEO_SENDERS = video_calls.VIDEO_SENDERS
VIDEO_START_DELAY_S = video_calls.VIDEO_START_DELAY_S
CAMERA_STATE_REPEAT = video_calls.CAMERA_STATE_REPEAT
CAMERA_STATE_KEEP_SECONDS = video_calls.CAMERA_STATE_KEEP_SECONDS
_stop_video = video_calls._stop_video
_send_camera_inband = video_calls._send_camera_inband
_send_camera_state_async = video_calls._send_camera_state_async
_repeat_camera_state = video_calls._repeat_camera_state
_start_video = video_calls._start_video
_send_a2v_async = video_calls._send_a2v_async
from . import conv_ttl as conv_ttl_mod
from . import privacy as privacy_mod
from . import call_errors
from . import call_log
from . import chat as chat_mod
from . import contacts as contacts_mod
from . import ctrl_poll as ctrl_poll_mod
from . import history_sync as history_sync_mod
from . import history_import as history_import_mod
from . import retention as retention_mod
from . import cursor_store as cursor_store_mod
from . import engine_seam
from . import file_inbox as file_inbox_mod
from . import media_endpoints
from . import message_store as message_store_mod
from . import events as events_mod
from . import proxy_store as proxy_store_mod
from . import protocol
from . import qr_login
from . import group_polls as group_polls_mod
from . import rich_text
from . import services as services_mod
from . import session as session_mod
from . import signaling as signaling_mod
from . import srtp_mode as srtp_mode_mod
from . import video_tx as video_tx_mod
from . import audio_tx as audio_tx_mod
from . import audio_rx as audio_rx_mod
from . import deps as deps_mod
from . import devices as devices_mod
from . import sync_poll as sync_poll_mod
from . import voice_transcode as voice_mod
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

# Sync retry: a kept session whose one startup refresh failed must
# not sit at "no_endpoints" for the whole process lifetime (that is
# issue 2 — the only recovery used to be a QR re-scan or a restart).
# The background loop retries start_sync() every 5 minutes while
# the channel is down with a retryable state; the manual retry
# endpoint is rate-limited to one attempt per 30 seconds so neither
# path hammers getLoginInfo. Kicked-out sessions are never retried
# (the server told us to stop).
# The loop WAKES every SYNC_RETRY_CHECK_SECONDS (60s) so a poller
# that stopped itself after persistent errors (loi live 08/11) is
# respawned quickly, but it ATTEMPTS a restart at most once per
# SYNC_RETRY_INTERVAL_SECONDS (300s) — the attempt guard uses the
# same _sync_last_retry_at timestamp as POST /api/sync/retry.
SYNC_RETRY_CHECK_SECONDS = 60
SYNC_RETRY_INTERVAL_SECONDS = 300
SYNC_RETRY_COOLDOWN_SECONDS = 30

# Kiem chung phien bang keepAlive (sua loi H5 + I1): /api/status
# truoc day chi kiem session.json con zpw_sek nen phien bi da van
# bao login=true. keepAlive la GET chat /keepalive (11770) nhe,
# body chi {imei} — xem services.OPS["keepAlive"].
#   CHECK_INTERVAL 300s: vong nen hoi lai dinh ky (5 phut/lan —
#     du thua de phat hien phien bi da ma khong hammer Zalo).
#   STATUS_TTL 60s: /api/status dung ket qua keepAlive gan nhat;
#     chi kich probe nen khi ket qua cu hon 60s, khong goi moi lan
#     status duoc hoi.
#   AUTH_FAILURES_TO_EXPIRE 2: phien chi bi xoa sau 2 loi auth
#     (600/401/403) LIEN TIEP — 1 lan co the la loi thoang qua,
#     loi mang khong bao gio xoa phien (chi dem loi auth).
KEEPALIVE_CHECK_INTERVAL_SECONDS = 300
KEEPALIVE_STATUS_TTL_SECONDS = 60
KEEPALIVE_AUTH_FAILURES_TO_EXPIRE = 2
KEEPALIVE_AUTH_CODES = (600, 401, 403)


def _classify_keepalive_error(exc):
    """Xep loai loi keepAlive: "auth" neu phien het han,
    "transient" neu loi mang / loi khac (khong duoc xoa phien).
    Auth la: ServiceError ma 600 (phien het han — loi audit H5) /
    401 / 403, hoac HTTP status 401/403 trong thong diep loi mang
    ("network status=401" — Services._unwrap nem khi HTTP != 200),
    hoac "error_code=600/401/403" trong thong diep (inner envelope).
    Moi thu khac (URLError, timeout, 500, ma loi la) la transient:
    chi ghi nhan, retry lan sau."""
    if isinstance(exc, services_mod.ServiceError) \
            and exc.code in KEEPALIVE_AUTH_CODES:
        return "auth"
    text = str(exc)
    if re.search(r"network status=(401|403)\b", text):
        return "auth"
    if re.search(r"error_code=(600|401|403)\b", text):
        return "auth"
    return "transient"


def _poller_is_alive(poller):
    """True khi poller dang chay. Poller that (SyncPoller /
    CtrlPoller) co is_alive(); fake cu trong test chi co
    kicked_out thi mac dinh True — tranh AttributeError khi
    doc trang thai."""
    is_alive = getattr(poller, "is_alive", None)
    if callable(is_alive):
        return bool(is_alive())
    return True

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
FONTS_DIR = os.path.join(STATIC_DIR, "fonts")


def _safe_static_path(name, base_dir=STATIC_DIR):
    """Resolve `name` inside `base_dir`, or return None.

    H1 (path traversal qua /fonts/): the old _serve_static joined
    STATIC_DIR + name unchecked, so /fonts/../../... read any file
    (session.json, app_auth.json, messages.db trong container).
    Giai ma percent-escape LAP (toi da 3 vong, de double-encode
    %252e%252e khong luon qua), loai NUL byte va duong dan tuyet
    doi, roi kiem realpath phai nam trong base_dir (symlink cung
    khong thoat ra ngoai duoc). Tra ve duong dan tuyet doi da giai
    quyet, hoac None khi khong hop le — caller tra 404 chung chung,
    khong lo duong dan that.
    """
    decoded = name
    for _ in range(3):
        nxt = urllib.parse.unquote(decoded)
        if nxt == decoded:
            break
        decoded = nxt
    if "\x00" in decoded:
        return None
    decoded = decoded.replace("\\", "/")
    if os.path.isabs(decoded):
        return None
    base = os.path.realpath(base_dir)
    resolved = os.path.realpath(os.path.join(base, decoded))
    if resolved != base and not resolved.startswith(base + os.sep):
        return None
    return resolved


def _zalo_urlopen(req, timeout):
    """Mo mot request toi Zalo, qua proxy dang bat (neu co). Chi dung cho
    luong goi ra Zalo; webhook ve HA/n8n dung urlopen thang (khong qua proxy)."""
    state = globals().get("STATE")
    proxy = state.proxy_store.active_url() if state is not None else ""
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        return opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def _test_proxy(url):
    """Thu di qua mot proxy toi Zalo: {ok, status, ms, error}. Nhan duoc bat
    ky ma HTTP nao (ke ca 4xx) nghia la proxy thong."""
    try:
        url = proxy_store_mod.validate_proxy_url(url)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": url, "https": url}))
    started = time.time()
    req = urllib.request.Request("https://wpa.zalo.me/",
                                 headers={"User-Agent": "zalo-pc-qr/1.0"})
    try:
        with opener.open(req, timeout=8) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:  # noqa: BLE001 - bao loi cho nguoi dung
        return {"ok": False, "error": str(getattr(e, "reason", e))[:160]}
    return {"ok": True, "status": status, "ms": int((time.time() - started) * 1000)}


class _ReceiptBatcher:
    """Gui «da nhan» (deliveredv2) cho tin den, gop theo cuoc tro chuyen trong 150 ms, toi da 50 tin / lan — Zalo PC gui ngay khi tin den, app
    chua tung gui nen nguoi gui khong thay «Da nhan». Chay nen, best-effort; ZALO_PC_AUTO_DELIVERED=0 tat. Chi ghi so luong, khong ghi noi dung."""
    WINDOW = 0.15
    MAX_BATCH = 50

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = {}
        self._timer = None
        self.sent = 0
        self.failed = 0
        self.last_error = ""

    def add(self, thread_type, thread_id, raw):
        if os.environ.get("ZALO_PC_AUTO_DELIVERED", "1") == "0" or not isinstance(raw, dict):
            return
        if not raw.get("msgId") or not raw.get("cliMsgId"):
            return
        with self._lock:
            self._pending.setdefault((thread_type, str(thread_id)), []).append(raw)
            if self._timer is None:
                self._timer = threading.Timer(self.WINDOW, self.flush)
                self._timer.daemon = True
                self._timer.start()

    def flush(self):
        with self._lock:
            pending, self._pending, self._timer = self._pending, {}, None
        state = globals().get("STATE")
        sess = getattr(state, "session", None) if state is not None else None
        if not pending or not sess:
            return
        chat = chat_mod.Chat(make_transport(sess["zpw_sek"]), sess["device_id"], sess["zpw_enk"])
        for (thread_type, thread_id), raws in pending.items():
            for i in range(0, len(raws), self.MAX_BATCH):
                part = raws[i:i + self.MAX_BATCH]
                try:
                    chat.send_delivered_v2(thread_type, thread_id, part, own_uid=sess.get("uid", ""))
                    self.sent += len(part)
                    if self.sent <= 3 and not sys.is_finalizing():
                        print("[receipt] da gui «da nhan» %d tin (thread %s)" % (len(part), thread_type), flush=True)
                except Exception as exc:  # noqa: BLE001 - chi la bao «da nhan»
                    self.failed += 1
                    self.last_error = str(exc)[:120]
                    if self.failed <= 3 and not sys.is_finalizing():
                        print("[receipt] gui «da nhan» loi: %s" % self.last_error, flush=True)


class _KeepAlivePool:
    """Ket noi HTTP(S) giu song cho cac poller (long-poll tin nhan 99100 / dieu khien 99101).

    Truoc day moi lan hoi mo TCP + TLS moi (urllib dat Connection: close): tin den ngay luc poller dang bat tay lai phai doi them 1-3 RTT toi
    Zalo, va sau MOI tin den poller lai bat tay nua. Zalo PC dung WebSocket (day tin) nen khong co khoang nay. Pool nay chi cho GET (hoi lap
    an toan): lay ket noi roi tu hang doi, tra lai sau khi doc xong; ket noi cu bi server dong thi mo lai dung MOT lan."""

    IDLE_TTL = 20.0                     # giay: ket noi nhan roi lau hon bo di (server Zalo dong ket noi nhan roi)
    MAX_IDLE = 6

    def __init__(self):
        self._lock = threading.Lock()
        self._idle = {}                 # (scheme, host, port) -> [(conn, lan_dung_cuoi)]
        self.opened = 0                 # so ket noi da mo (chan doan / test)

    def _take(self, key):
        now = time.monotonic()
        with self._lock:
            lst = self._idle.get(key) or []
            while lst:
                conn, last = lst.pop()
                if now - last <= self.IDLE_TTL:
                    return conn
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
        return None

    def _give(self, key, conn):
        with self._lock:
            lst = self._idle.setdefault(key, [])
            lst.append((conn, time.monotonic()))
            while len(lst) > self.MAX_IDLE:
                old, _ = lst.pop(0)
                try:
                    old.close()
                except Exception:  # noqa: BLE001
                    pass

    def get(self, url, headers, timeout):
        """GET -> (status, body bytes). Nem TimeoutError khi qua han; loi mang khac nem nguyen (OSError/http.client)."""
        parts = urllib.parse.urlsplit(url)
        https = parts.scheme == "https"
        port = parts.port or (443 if https else 80)
        key = (parts.scheme, parts.hostname, port)
        target = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        last_exc = None
        for attempt in (0, 1):
            conn = self._take(key) if attempt == 0 else None
            reused = conn is not None
            if conn is None:
                cls = http.client.HTTPSConnection if https else http.client.HTTPConnection
                conn = cls(parts.hostname, port, timeout=timeout)
                with self._lock:
                    self.opened += 1
            try:
                if conn.sock is not None:
                    conn.sock.settimeout(timeout)
                else:
                    conn.timeout = timeout
                conn.request("GET", target, headers=headers)
                if conn.sock is not None:
                    conn.sock.settimeout(timeout)
                resp = conn.getresponse()
                body = resp.read()
            except (socket.timeout, TimeoutError):
                conn.close()
                raise TimeoutError("GET timeout: %s" % url)
            except (OSError, http.client.HTTPException) as exc:
                conn.close()
                last_exc = exc
                if reused:                  # ket noi nhan roi bi server dong: mo lai dung mot lan
                    continue
                raise
            if resp.will_close:
                conn.close()
            else:
                self._give(key, conn)
            return resp.status, body
        raise last_exc


_KEEPALIVE_POOL = _KeepAlivePool()
RECEIPTS = _ReceiptBatcher()
_REPLY_LOGS = [0]                      # so dong log «tin tra loi» da ghi (gioi han de khong tran log)


class _Transport:
    """HTTP transport for one session: callable as http_get(url,
    timeout) (the shape qr_login/signaling/contacts expect) plus an
    http_post(url, form, timeout) for the getmg-v2 POST (form body
    params=<AES JSON>, Content-Type application/x-www-form-urlencoded).
    Both carry the zpw_sek cookie when one was supplied."""

    def __init__(self, cookie_value="", keepalive=False):
        self.cookie_value = cookie_value
        self.keepalive = keepalive          # True: GET qua pool giu ket noi song (poller); proxy dang bat thi van di duong cu

    def __call__(self, url, timeout=30):
        return self.http_get(url, timeout=timeout)

    def _request_keepalive(self, url, timeout):
        """GET qua pool giu song; None = khong dung duoc (proxy, 3xx) -> caller dung duong urllib cu."""
        state = globals().get("STATE")
        if state is not None and state.proxy_store.active_url():
            return None
        url = protocol.adapt_url(url)
        headers = {"User-Agent": protocol.user_agent_for(url), "Connection": "keep-alive"}
        if self.cookie_value:
            headers["Cookie"] = "%s=%s" % (COOKIE_NAME, self.cookie_value)
        status, raw = _KEEPALIVE_POOL.get(url, headers, timeout)
        if 300 <= status < 400:
            return None                     # urllib tu theo chuyen huong
        text = raw.decode("utf-8-sig", errors="replace")
        try:
            return status, json.loads(text)
        except json.JSONDecodeError:
            if status >= 400:
                return status, {}           # nhu nhanh HTTPError cua urllib
            raise sync_poll_mod.NonJsonResponse(status, text)

    def _request(self, url, method, data, timeout, content_type=None):
        """Áp kiểu theo dịch vụ (gọi điện luôn PC). Kiểu web mà Zalo từ chối vì chính zpw_type/zpw_ver thì học máy chủ đó cần PC rồi thử lại 1 lần."""
        url = protocol.adapt_url(url)
        status, body = self._request_once(url, method, data, timeout, content_type)
        if protocol.client_name() == "web" and not protocol.uses_pc_identity(url) and protocol.type_rejected(body):
            retry_url = protocol.to_pc(url)
            if retry_url != url:
                status2, body2 = self._request_once(retry_url, method, data, timeout, content_type, force_pc=True)
                if not protocol.type_rejected(body2):      # PC được chấp nhận -> máy chủ này dùng kiểu PC từ giờ (chưa chắc thì không học)
                    if protocol.learn_pc(url):
                        print("[zpw] %s từ chối zpw_type/zpw_ver của web (%s): máy chủ này dùng kiểu PC từ giờ" % (
                            urllib.parse.urlsplit(url).netloc, str(body.get("error_message", ""))[:60]), flush=True)
                    return status2, body2
        return status, body

    def _request_once(self, url, method, data, timeout, content_type=None, force_pc=False):
        req = urllib.request.Request(url, method=method, data=data)
        req.add_header("User-Agent", protocol.user_agent_for(url, force_pc=force_pc))
        if method == "POST":
            req.add_header("Content-Type",
                           content_type
                           or "application/x-www-form-urlencoded")
        if self.cookie_value:
            req.add_header("Cookie", "%s=%s" % (COOKIE_NAME,
                                                self.cookie_value))
        try:
            with _zalo_urlopen(req, timeout) as resp:
                raw = resp.read()
                # Giai ma mot lan (utf-8-sig bo BOM neu co);
                # body khong phai JSON -> NonJsonResponse mang
                # status + preview (loi live 08/11: ca hai poller
                # bao JSONDecodeError — khong ai biet server tra
                # gi, status bao nhieu). Bare json.loads o day
                # tung vang JSONDecodeError tran ra ngoai.
                text = raw.decode("utf-8-sig", errors="replace")
                try:
                    return resp.status, json.loads(text)
                except json.JSONDecodeError:
                    raise sync_poll_mod.NonJsonResponse(
                        resp.status, text)
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {}
            return e.code, body
        except (TimeoutError, socket.timeout):
            raise TimeoutError("%s timeout: %s" % (method, url))

    def http_get(self, url, timeout=30):
        if self.keepalive:
            done = self._request_keepalive(url, timeout)
            if done is not None:
                return done
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

    def http_get_bytes(self, url, timeout=120, max_bytes=None):
        """GET tho tra ve bytes (tai file den — xem file_inbox):
        (status, bytes). Doc theo chunk, dung khi qua max_bytes
        (neu co) de khong doi day RAM vi file qua lon; cookie
        zpw_sek kem theo nhu moi loi goi khac. HTTPError -> (code,
        b""); timeout -> TimeoutError."""
        url = protocol.adapt_url(url)
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", protocol.user_agent_for(url))
        if self.cookie_value:
            req.add_header("Cookie", "%s=%s" % (COOKIE_NAME,
                                                self.cookie_value))
        try:
            with _zalo_urlopen(req, timeout) as resp:
                status = resp.status
                if max_bytes is None:
                    return status, resp.read()
                chunks = []
                remaining = max_bytes + 1
                while remaining > 0:
                    chunk = resp.read(min(65536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                data = b"".join(chunks)
                if len(data) > max_bytes:
                    raise ValueError("http_get_bytes: qua gioi han "
                                     "%d byte" % max_bytes)
                return status, data
        except urllib.error.HTTPError as e:
            try:
                e.read()
            except Exception:
                pass
            return e.code, b""
        except (TimeoutError, socket.timeout):
            raise TimeoutError("GET timeout: %s" % url)


def make_transport(cookie_value="", keepalive=False):
    """http_get(url, timeout) -> (status, json_dict), callable, with
    .http_post(url, form, timeout) attached (see _Transport). keepalive=True cho poller (giu ket noi song)."""
    return _Transport(cookie_value, keepalive=keepalive)


# Call-id counter (deep comparison §5.1, 2026-11-09): the native
# engine mints callId from a process-wide atomic counter — 1, 2, 3,
# ... (`lock xadd` in ZaloCall.exe) — never from the UI. The app used
# to keep the UI's epoch seconds (~1.7e9): the server accepts both
# (status=0) but the peer may treat the engine's small counter
# differently from epoch seconds, so the small counter is the top
# suspect for the no-ring bug. The counter is guarded by a lock so
# concurrent calls never collide; it wraps to 1 after uint32 max
# (unreachable in practice — ~4 billion calls per process).
_CALL_ID_LOCK = threading.Lock()
_CALL_ID_COUNTER = 0


SRTP_MODES = srtp_mode_mod.MODES
SRTP_JUDGE_MIN_SECONDS = 6.0     # nghe may it nhat chung nay giay moi xet dung/sai
SRTP_JUDGE_MIN_SAMPLES = 8       # so goi nhan toi thieu de phan biet RTP tran / ban ma
SRTP_PLAIN_MIN_AGREE = 0.7       # ti le byte dau payload trung nhau coi la RTP tran
_CALL_SRTP = {}                  # call_id -> che do da dung cho cuoc goi di
# call_id -> (rtp "IP:port", rtcp "IP:port") ben goi viet trong su kien cuoc
# goi den. Ben nghe PHAI noi vao DUNG relay do (zca-js acceptIncomingCall chi xin
# cap phat 11300 khi su kien thieu cong); xin relay moi thi hai ben o hai relay
# khac nhau va dien thoai khong gui goi nao ve (do 09/11: rtp_rx = 0).
_INCOMING_RELAY = {}
from . import voice2text as voice2text_mod  # noqa: E402
V2T = voice2text_mod.V2TStore()
_INCOMING_SRTP = {}              # call_id -> khoa SRTP ben goi (chi bo nho, khong API)


def _srtp_mode_for_call(body):
    """(che_do, nguon) cho cuoc goi di; nguon = "forced" | "auto".

    "sess" (MAC DINH): khoa SRTP = 30 ky tu dau `sessId` cua 11300 — do tren
    may that 09/11/2026 (HMAC-SHA1-80 dung 8/8 goi, giai ma ra Opus). "off":
    RTP tran, extendData.srtpMode=0 (luong mac dinh cua zca-js). "key" (THU):
    ben goi tu sinh khoa, gui trong extendData (srtpMode=1 + srtpKey).
    Truong `srtp` trong body > bien moi truong ZALO_PC_SRTP ep cung mot che
    do; neu khong thi "auto" = che do da tung nhan duoc goi that tu ben kia
    (mac dinh "sess"), doi sang cai khac khi that bai."""
    for value in ((body or {}).get("srtp"), os.environ.get("ZALO_PC_SRTP")):
        if isinstance(value, str) and value.strip().lower() in SRTP_MODES:
            return value.strip().lower(), "forced"
    return STATE.srtp_modes.pick(), "auto"


def _evaluate_srtp_outcome(ended):
    """Cuoc goi di vua ket thuc: nghe may du lau ma van KHONG nhan duoc goi
    nao tu ben kia (da qua xac thuc/giai ma) thi coi che do da dung la hong.
    Phai goi TRUOC khi dung transport. Khong bao gio nem loi.

    Han che da biet: o che do "off" khong co xac thuc nen goi rac van tinh
    la "nhan duoc" — bang chung manh chi o che do "key" (HMAC dung)."""
    try:
        info = _CALL_SRTP.pop(str(ended.get("call_id")), None)
        if info is None:
            return
        mode, source = info
        answered, finished = ended.get("answered_at"), ended.get("ended_at")
        if not answered or not finished \
                or float(finished) - float(answered) < SRTP_JUDGE_MIN_SECONDS:
            return
        rec = media_endpoints.ENDPOINTS.active_record(int(ended["call_id"]))
        snap = rec["transport"].status() if rec else {}
        counters = snap.get("counters") or {}
        got = int(counters.get("rtp_rx", 0)) \
            - int(counters.get("rtp_rx_dropped", 0))
        ok = got > 0
        sample = snap.get("rx_sample") or {}
        if ok and mode == "off":
            # RTP tran khong co xac thuc: ban ma ben kia gui van "nhan duoc".
            # Phan biet bang byte dau payload: Opus tran on dinh, ban ma
            # ngau nhien. Chua du mau (< SRTP_JUDGE_MIN_SAMPLES) thi chua ket
            # luan — khong ghi nho de khoi khoa nham vao "off".
            if int(sample.get("n", 0)) < SRTP_JUDGE_MIN_SAMPLES:
                _log_call("srtp outcome call_id=%s mode=off inconclusive "
                          "n=%s" % (ended.get("call_id"), sample.get("n", 0)))
                return
            ok = float(sample.get("toc_agree", 0)) >= SRTP_PLAIN_MIN_AGREE
        # Bang chung MANH chi khi co goi toi (rtp_rx > 0) ma khong xac thuc/giai ma duoc; "khong nhan duoc gi" co the do ben kia im lang.
        pref = STATE.srtp_modes.record(mode, ok, strong=ok or int(counters.get("rtp_rx", 0)) > 0)
        _log_call("srtp outcome call_id=%s mode=%s source=%s ok=%s "
                  "rx_ok=%s toc_agree=%s head=%s peer_sr_blocks=%s "
                  "rtcp_rx=%s rtcp_tx=%s video_rx=%s video_tx=%s "
                  "unknown_rx=%s peer_twcc=%s peer_block=%s -> next_auto=%s"
                  % (ended.get("call_id"), mode, source, ok, got,
                     sample.get("toc_agree"), sample.get("head"),
                     snap.get("peer_sr_blocks"), counters.get("rtcp_rx"),
                     counters.get("rtcp_tx"), counters.get("video_rx"),
                     counters.get("video_tx"), counters.get("unknown_rx"),
                     snap.get("peer_twcc"), snap.get("peer_block"), pref))
    except Exception as exc:  # noqa: BLE001 - chi la ghi nho, khong chen ngang
        _log_call("srtp outcome error: %s" % str(exc)[:120])


def _next_call_id():
    """Mint the next callId from the process-wide counter, starting
    at 1 (native engine behaviour)."""
    global _CALL_ID_COUNTER
    with _CALL_ID_LOCK:
        _CALL_ID_COUNTER += 1
        if _CALL_ID_COUNTER > 2 ** 32 - 1:
            _CALL_ID_COUNTER = 1
        return _CALL_ID_COUNTER


def _seed_call_id_counter(now=None):
    """Gieo bo dem callId bang moc thoi gian (giay) luc server khoi
    dong. Server Zalo nho callId cua cac cuoc goi da thanh cong va tu
    choi 11301 bang loi noi -101 neu mot id duoc dung lai: truoc day
    bo dem luon ve 1 sau moi lan khoi dong lai container nen cuoc goi
    dau tien sau do bi tu choi (do live 09/11/2026: call_id=1 -> 11301
    inner -101 hai lan lien tiep sau hai lan restart). Moc thoi gian
    tang theo thoi gian nen khong bao gio trung giua cac lan chay;
    ben trong mot process van la bo dem don dieu +1 nhu engine."""
    global _CALL_ID_COUNTER
    seed = int(now if now is not None else time.time())
    with _CALL_ID_LOCK:
        if seed > _CALL_ID_COUNTER:
            _CALL_ID_COUNTER = seed


def _log_call(msg):
    """One call-lifecycle line to stdout (visible in `docker logs`).

    The live 2026-11-07 test proved the app logs NOTHING about
    calls: a call that "cut off" after ~8s left no line at all in
    the server log, so no one could tell whether the user pressed
    End, the peer rejected, or the server withdrew it — and the
    Zalo PC app has no F12 to inspect the browser instead. Every
    lifecycle event gets one line here: start, step-2 outcome,
    end with the REAL reason + duration. Call ids / peer names /
    thread ids only — never secrets, tokens, or message content.
    """
    print("[call] %s%s" % (msg, call_tags_mod.suffix(msg, lambda cid: STATE.calls.find(cid), protocol.client_name(), protocol.call_client_name())), flush=True)


def _describe_session_value(session):
    """Session presence + length ONLY, never the value (the 11301
    session is the sessId token — a secret). Used in the step-2
    send log so the next live round can judge whether step 2
    carried a real session without ever seeing it."""
    if session is None:
        return "missing"
    if isinstance(session, (str, bytes, bytearray)):
        return "present[%d]" % len(session)
    return "present[%s]" % type(session).__name__


# Ring timeout for an outgoing call nobody answers (seconds).
# The real client ends an unanswered call after ~30s (pcap file 2:
# media 5.74-35.26s = 29.52s, teardown voicecall stream 35.33-36.22s;
# live 2026-11-07 09:00 the call was still ringing at 00:31 and then
# became missed). Measured from step 2 sent — the moment the peer
# starts ringing. Without this timeout the app leaves a "sent" call
# — and its UDP transport — alive forever when the peer never
# answers and sync is down, so /api/calls still reports the call as
# connecting after it ended server-side (live 2026-11-07 09:03).
# The value is a module constant so tests can shorten it.
RING_TIMEOUT_SECONDS = 30.0

# Ring-timer handles, keyed by str(call_id): the timer is armed
# when step 2 is sent and MUST be disarmed when the peer answers
# (2026-11-08 fix) — before this fix no handle was kept, so an
# answered call was killed at 30s by the same timer that guards
# an unanswered ring. Guarded by a lock: arm/disarm/fire run on
# the HTTP thread, the timer thread and the transport's receiver
# thread (first-media hook).
_RING_TIMERS = {}
_RING_TIMERS_LOCK = threading.Lock()


def _send_end_signal(entry, sess, group_data=None, group_partners=None):
    """Send the wire termination signal for one call entry.

    Returns (signal, zalo_ok, zalo_error, data). `signal` names the
    signal sent ("cancel" / "endcall" / "group/endcall") or "none"
    when nothing had to be sent. Best-effort: a failure is returned,
    never raised — the call is already ended locally.

    Which signal (bundle wZ, 1-1):
    - never answered (status "sent" at end time) -> CANCEL (11305,
      sendCancelCall, {callerId, callId, callType, status:0, imei}).
      This withdraws the pending invitation; the peer's client drops
      the incoming-call UI on [SIG]recvCancel. The app used to send
      endcall here instead — and the peer kept a ghost "hidden call"
      that re-rang with a dead answer button (live 2026-11-07
      09:01-09:02).
    - answered (status "answered") -> ENDCALL (11306, {uidTo, callId,
      status:3, imei}): ends an established call. Entries reach
      "answered" through POST /api/call/answered or the transport's
      first-media hook (2026-11-08 fix) — before that fix no entry
      ever carried "answered" and this branch was dead code.
    - group calls -> group/endcall (12438): the group cancel
      (group_cancel) shape is not traced yet, so group ends keep the
      existing signal.
    The signal is sent for EVERY live ("sent") entry, even when
    step 2 was never sent (request_sent is not True): requestcall
    (11300) already created a server-side invitation for this
    callId, and only the termination signal withdraws it. (An
    earlier draft skipped the signal when step 2 failed — wrong:
    the server still holds the invitation, and the pre-existing
    end tests require the signal in exactly that case.)
    """
    call_id = int(entry["call_id"])
    call_type = entry.get("type") or "user"
    try:
        transport = make_transport(sess["zpw_sek"])
        sig = signaling_mod.Signaling(transport, sess["device_id"],
                                      sess["zpw_enk"])
        if call_type == "group":
            data = sig.endcall_group(
                entry["thread_id"], call_id,
                protocol.CALL_TYPE_AUDIO_GROUP, True,
                group_data, group_partners)
            return "group/endcall", True, "", data
        if entry.get("status") == "answered":
            data = sig.endcall(entry["thread_id"], call_id)
            return "endcall", True, "", data
        data = sig.cancel(sess.get("uid", ""), call_id,
                          _type_request_for(call_type))
        return "cancel", True, "", data
    except Exception as e:  # noqa: BLE001 - best-effort
        signal = ("group/endcall" if call_type == "group"
                  else "endcall" if entry.get("status") == "answered"
                  else "cancel")
        return signal, False, str(e), {}


def _terminate_call(call_id, reason, sess, group_data=None,
                    group_partners=None):
    """End one call completely: local log + webhook + wire signal +
    transport stop. `reason` is the true end reason recorded in the
    entry's detail ("user_end" / "ring_timeout" /
    "superseded_by_new_call"). Returns (ended_entry_or_None, signal,
    zalo_ok, zalo_error, data).

    Local-first (§7m): the entry is marked ended BEFORE the wire
    signal is attempted, so a slow or rejected Zalo signal never
    leaves the call stuck on "ringing". A wire failure is appended
    to the detail as "<reason>; zalo_<signal>: <error>" so the
    reason survives (the 2026-11-07 live test could not tell a
    user-ended call from a cut-off one precisely because no end
    carried a reason).
    """
    snap = STATE.calls.snapshot()
    before = None
    for c in snap["calls"]:
        if str(c["call_id"]) == str(call_id) \
                and c["status"] in ("sent", "answered"):
            before = c
            break
    if before is None:
        return None, "none", False, "no_live_call", {}
    _disarm_ring_timer(call_id)
    ended = STATE.calls.record_end(call_id, reason)
    if ended is None:
        return None, "none", False, "no_live_call", {}
    webhooks_mod.dispatch_call_event(
        STATE.webhook_dispatcher, ended, (sess or {}).get("uid", ""))
    signal, zalo_ok, zalo_error, data = "none", True, "", {}
    if sess is not None:
        signal, zalo_ok, zalo_error, data = _send_end_signal(
            before, sess, group_data, group_partners)
    else:
        zalo_ok, zalo_error = False, "no_session"
    if not zalo_ok and signal != "none":
        STATE.calls.record_end_error(
            int(ended["call_id"]),
            "%s; zalo_%s: %s" % (reason, signal, zalo_error))
    # Phase 2: stop the media engine + the relay transport for this
    # call (best-effort; a stuck UDP socket must not leave the call
    # half-alive after it ends).
    _cleanup_call_media(ended)
    _log_call("end call_id=%s reason=%s duration=%.0fs "
              "zalo_signal=%s zalo_ok=%s%s"
              % (ended["call_id"], reason,
                 max(0.0, float(ended.get("ended_at") or 0)
                     - float(ended.get("started_at") or 0)),
                 signal, zalo_ok,
                 (" zalo_error=" + zalo_error) if zalo_error else ""))
    return ended, signal, zalo_ok, zalo_error, data













def _thread_of_call(call_id):
    for c in STATE.calls.snapshot()["calls"]:
        if str(c["call_id"]) == str(call_id):
            return str(c.get("thread_id") or c.get("peer") or "")
    return ""






def _find_req_id(obj, depth=0):
    """req_id trong phan hoi voiceToText (co the long trong data)."""
    if depth > 4:
        return ""
    if isinstance(obj, dict):
        if obj.get("req_id"):
            return str(obj["req_id"])
        for v in obj.values():
            r = _find_req_id(v, depth + 1)
            if r:
                return r
    return ""


def _calls_snapshot_with_media():
    """Call-log snapshot + live media state: every entry whose
    transport is still running gains "media": {"srtp":
    "wired"|"not-wired"} so the UI can report honestly — a
    connected call with srtp "not-wired" is "da noi, chua co
    tieng (thieu khoa SRTP)", not silent voice and not a reason
    to drop the call. Entries without a running transport (ended
    / error) carry no media key."""
    snap = STATE.calls.snapshot()
    for entry in snap["calls"]:
        try:
            record = media_endpoints.ENDPOINTS.active_record(
                entry["call_id"])
        except Exception:  # noqa: BLE001 - media is best-effort
            record = None
        if record is not None:
            media = {"srtp": record.get("srtp", "not-wired")}
            mode = _CALL_SRTP.get(str(entry["call_id"]))
            if mode:
                media["srtp_mode"] = mode[0]
            try:
                counters = record["transport"].status().get("counters") or {}
                media["counters"] = {k: counters.get(k, 0) for k in (
                    "rtp_tx", "keepalive_tx", "rtcp_tx", "rtp_rx",
                    "rtp_rx_dropped", "p2p_media_rx")}
                media["rx_sample"] = record["transport"].status().get(
                    "rx_sample")
            except Exception:  # noqa: BLE001 - chan doan, khong chen ngang
                pass
            # Token phat am thanh theo cuoc goi — chi cap cho phien da dang
            # nhap app (route nay yeu cau cookie), het han khi goi ket thuc.
            media["audio_token"] = STATE.audio_tokens.token_for(
                entry["call_id"])
            _v = VIDEO_SENDERS.get(str(entry["call_id"]))
            _m = AUDIO_SENDERS.get(str(entry["call_id"]))
            media["video"] = _v.status() if _v else None
            media["mic"] = _m.status() if _m else None
            _s = SPEAKER_SINKS.get(str(entry["call_id"]))
            media["speaker"] = _s.status() if _s else None
            entry["media"] = media
    return snap


def _engine_for_call(call_id):
    """Engine media dang gan cho dung cuoc goi nay, hoac None."""
    engine = engine_seam.SEAM.engine
    info = getattr(engine, "call_info", None) or {}
    if engine is not None and str(info.get("call_id")) == str(call_id):
        return engine
    return None


_CALL_DEVICES = {}               # call_id -> ghi de rieng cua cuoc goi (mic/camera)
_CALL_DEVICE_KEYS = ("mic_url", "mic_format", "camera_url", "speaker_url", "echo_guard")



def _log_media_stats(kind, call_id, obj):
    """Ghi số liệu của một nguồn/đích tiếng khi dừng (khung gửi/nhận, bị chặn, lỗi): để lần sau biết «không ổn định» do đâu."""
    try:
        st = obj.status()
        _log_call("%s stats call_id=%s %s" % (kind, call_id, ", ".join("%s=%s" % (k, str(v)[:60]) for k, v in st.items() if k != "ffmpeg_err" or v)))
    except Exception:  # noqa: BLE001 - ghi nhật ký không được làm hỏng việc dừng
        pass


_INCOMING_OFFER = {}             # call_id -> extendData bên gọi khai (dict)
_CALLEE_EVENT = set()             # call_id mà nhánh «event» dùng vai bên nghe máy đúng engine thật
_INCOMING_INFO = {}              # call_id -> {"session": sessId của BÊN GỌI, "uid_from", "uid_to": uid media 9 chữ số}


def _as_uid(v):
    try:
        n = int(v)
        return n if 0 < n <= 0xFFFFFFFF else None
    except (TypeError, ValueError):
        return None




def _key_fp(key):
    """Dấu vân tay ngắn của khoá SRTP (6 hex đầu SHA-1) để so khoá giữa hai nguồn trong nhật ký mà không lộ khoá."""
    if not key:
        return "none"
    import hashlib
    return hashlib.sha1(key if isinstance(key, (bytes, bytearray)) else str(key).encode()).hexdigest()[:6]










def _remember_call_devices(call_id, body):
    """Ghi de thiet bi rieng cua cuoc goi (tu body request/answer). Gia tri "off"
    = tat thiet bi do cho cuoc nay (du co mac dinh)."""
    over = {}
    if isinstance(body, dict):
        for key in _CALL_DEVICE_KEYS:
            val = body.get(key)
            if val in (None, ""):
                continue
            if key == "echo_guard":
                over[key] = val is True or str(val).strip().lower() in ("1", "true", "yes", "on")
                continue
            val = str(val).strip()
            if key == "speaker_url":
                if val.lower() == "off":
                    over[key] = ""
                elif re.match(r"^https?://\S+$", val):
                    over[key] = val
                continue
            if key == "mic_format":
                if val in devices_mod.MIC_FORMATS:
                    over[key] = val
            elif val.lower() == "off":
                over[key] = ""
            elif devices_mod.valid_source(val):
                over[key] = val
    if over:
        if len(_CALL_DEVICES) > 50:
            _CALL_DEVICES.clear()
        _CALL_DEVICES[str(call_id)] = over
    return over


_LOGENDCALL_SENT = set()          # call_id da gui logendcall (moi cuoc goi gui dung mot lan)
_LOGENDCALL_LOCK = threading.Lock()


def _logendcall_status(entry):
    """Trang thai 406 nhu engine Zalo that (engine-core.js `_finish`): 50 da noi may, 103 ta la ben goi va huy / het gio / ket thuc truoc khi
    noi may, 160 tu choi (ta tu choi, hoac ben kia tu choi cuoc ta goi). None = khong gui: cuoc goi den bi nho (nguoi goi huy truoc khi ta nghe),
    bi thay the, hoac bi tu choi vi ban."""
    detail = str(entry.get("detail") or "")
    if detail.startswith("superseded") or detail == "busy_rejected" or (entry.get("type") or "user") == "group":
        return None
    if entry.get("answered_at"):
        return 50
    if entry.get("direction") == "in":
        return 160 if detail.startswith("user_rejected") else None
    return 160 if detail.startswith("peer_declined") else 103


def _logendcall_async(entry, status=None, rx=0, tx=0):
    """Gui logendcall (11311) cho cuoc goi 1-1 vua ket thuc — Zalo PC luon gui, app chua tung gui (so voi bundle 12/11): thieu no thi lich su chat
    hien cuoc da nghe la «bi nho». Best-effort tren luong nen, moi call_id mot lan, khong lam hong luong ket thuc cuoc goi."""
    st = _logendcall_status(entry) if status is None else status
    sess = STATE.session
    if st is None or not sess:
        return
    key = str(entry.get("call_id"))
    with _LOGENDCALL_LOCK:
        if key in _LOGENDCALL_SENT:
            return
        if len(_LOGENDCALL_SENT) > 200:
            _LOGENDCALL_SENT.clear()
        _LOGENDCALL_SENT.add(key)
    answered_at, ended_at = entry.get("answered_at"), entry.get("ended_at") or time.time()
    duration = int(round(max(0.0, float(ended_at) - float(answered_at)))) if (st == 50 and answered_at) else 0
    role = entry.get("direction") != "in"
    logdata = json.dumps({"Codec": ["opus/16000/1", "20"], "NewZRTC": 1, "RxTotalPkt": int(rx or 0), "SrtpMode": 1,
                          "TxTotalPkt": int(tx or 0), "sysInfo": "zalo-pc-app"}, sort_keys=True, separators=(",", ":"))

    def run():
        try:
            transport = make_transport(sess["zpw_sek"])
            sig = signaling_mod.Signaling(transport, sess["device_id"], sess["zpw_enk"])
            sig.logendcall(entry["thread_id"], int(entry["call_id"]), st, logdata, duration, role)
            _log_call("logendcall call_id=%s status=%s duration=%ss role=%s ok" % (key, st, duration, "caller" if role else "callee"))
        except Exception as exc:  # noqa: BLE001 - chi ghi lich su, khong anh huong cuoc goi
            _log_call("logendcall call_id=%s status=%s FAILED: %s" % (key, st, str(exc)[:140]))
    # Khong daemon: luong ngan (mot GET, timeout 30 s) va khong de no in ra luc interpreter dang tat (loi "could not acquire lock for stdout").
    threading.Thread(target=run, daemon=False).start()






def _devices_for_call(call_id):
    """Cai dat mac dinh + ghi de cua cuoc goi (ban co mat khau, noi bo)."""
    cfg = STATE.devices.get()
    cfg.update(_CALL_DEVICES.get(str(call_id), {}))
    return cfg


def _transport_for_call(call_id):
    rec = media_endpoints.ENDPOINTS.active_record(int(call_id))
    return (rec or {}).get("transport")




SAY_MAX_BYTES = 8 * 1024 * 1024
SAY_KEEP_SECONDS = 3600


def _prune_say_files(folder):
    """Xoa tep giong noi cu hon SAY_KEEP_SECONDS (chi trong thu muc say cua app)."""
    now = time.time()
    for name in os.listdir(folder):
        fp = os.path.join(folder, name)
        try:
            if os.path.isfile(fp) and now - os.path.getmtime(fp) > SAY_KEEP_SECONDS:
                os.remove(fp)
        except OSError:
            pass



def _schedule_recall(thread_type, thread_id, res, after):
    """Hẹn thu hồi tin vừa gửi sau `after` giây (0 = không). Trả thời điểm thu hồi (epoch giây) hoặc 0 khi không hẹn được."""
    if not after:
        return 0
    data = res.get("data") if isinstance(res, dict) else None
    msg_id = (data.get("msgId") or data.get("globalMsgId") or "") if isinstance(data, dict) else ""
    if not msg_id:
        print("[recall] khong hen duoc thread=%s: Zalo khong tra ma tin" % thread_id, flush=True)
        return 0
    return STATE.recall.add(thread_type, thread_id, msg_id, res.get("client_id"), after)



def _auto_media_async(call_id):
    """Cuoc goi vua duoc nghe may: tu phat mic (va hinh neu la cuoc goi video)
    theo thiet bi mac dinh / ghi de cua cuoc goi. Khong nem loi.
    Moi buoc ghi mot dong auto-media (chi co/khong, kieu nguon, thoi gian — khong ghi URL) de biet buoc nao im lang (su co 12/11)."""
    def run():
        t0 = time.monotonic()

        def note(msg):
            _log_call("auto-media call_id=%s +%.1fs %s" % (call_id, time.monotonic() - t0, msg))

        def kind(url):
            """none | «http:» | «http:r1_speaker/duplex» (cửa bộ đệm của loa/mic trong nhà: ghi loại phiên, KHÔNG ghi khoá/địa chỉ)."""
            if not url:
                return "none"
            m = re.search(r"/api/([a-z0-9_]+)/(duplex|intercom)/", str(url))
            return str(url).split(":", 1)[0] + ":" + (("%s/%s" % m.groups()) if m else "")
        try:
            note("bat dau cho transport")
            for _ in range(50):                      # doi transport toi 5 s
                if _transport_for_call(call_id) is not None:
                    break
                time.sleep(0.1)
            cfg = _devices_for_call(call_id)
            entry = next((c for c in STATE.calls.snapshot()["calls"]
                          if str(c["call_id"]) == str(call_id)), {})
            note("transport=%s engine=%s auto_mic=%s mic=%s speaker=%s camera=%s type=%s echo_guard=%s override=%s"
                 % (_transport_for_call(call_id) is not None, _engine_for_call(call_id) is not None, bool(cfg.get("auto_mic")),
                    kind(cfg.get("mic_url")), kind(cfg.get("speaker_url")), kind(cfg.get("camera_url")),
                    entry.get("type") or "user", bool(cfg.get("echo_guard")), sorted(_CALL_DEVICES.get(str(call_id), {}).keys())))
            if cfg["auto_mic"] and cfg["mic_url"]:
                note("start_mic")
                _start_mic(call_id, cfg["mic_url"], cfg["mic_format"])
                note("start_mic xong")
            else:
                note("bo qua mic (auto_mic tat hoac khong co mic_url)")
            if cfg.get("speaker_url"):
                note("start_speaker")
                _start_speaker(call_id, cfg["speaker_url"])
                note("start_speaker xong")
            else:
                note("bo qua loa (khong co speaker_url)")
            if (entry.get("type") or "user") == "video" and cfg["camera_url"]:
                time.sleep(VIDEO_START_DELAY_S)
                _start_video(call_id, cfg["camera_url"])
            note("xong")
        except Exception as exc:  # noqa: BLE001
            _log_call("auto media call_id=%s error=%s: %s" % (call_id, type(exc).__name__, str(exc)[:160]))
    threading.Thread(target=run, daemon=True).start()


def _cleanup_call_media(entry):
    """Cuoc goi da ket thuc: danh gia ket qua SRTP, dung engine + transport,
    huy token am thanh. Best-effort, khong nem loi."""
    try:
        try:
            _tr = _transport_for_call(entry["call_id"])
            _cnt = dict(getattr(_tr, "counters", {}) or {})
            _log_call("media counters call_id=%s %s" % (entry["call_id"], json.dumps(_cnt, sort_keys=True)[:600]))
            try:
                _ra = getattr(_tr, "_rx_audio", None)
                if _ra is not None and _ra.started:
                    _hi = _ra.cycles + _ra.max_seq
                    _log_call("rx-audio call_id=%s ssrc=%08x base_seq=%d cao_nhat=%d ky_vong=%d nhan=%d mat=%d jitter=%.0f" % (
                        entry["call_id"], _ra.ssrc, _ra.base_seq, _hi, _hi - _ra.base_seq + 1, _ra.received, (_hi - _ra.base_seq + 1) - _ra.received, _ra.jitter))
                _trace = list(getattr(_tr, "_rx_trace", []) or [])
                if _trace:
                    _rows, _prev = [], None
                    for _s, _t, _l, _p, _ms in _trace[:40]:
                        _rows.append("%d/%s/%d/p%d/%s" % (_s, ("+%d" % (_t - _prev[1])) if _prev else "ts0", _l, _p, ("+%dms" % (_ms - _prev[2])) if _prev else "0"))
                        _prev = (_s, _t, _ms)
                    _log_call("rx-trace call_id=%s n=%d (seq/dts/len/pt/dt) %s" % (entry["call_id"], len(_trace), " ".join(_rows)))
            except Exception:  # noqa: BLE001 - chan doan khong duoc lam hong don dep cuoc goi
                pass
            if str(entry.get("detail") or "").startswith("user_rejected"):
                pass                               # tu choi: ham tu choi tu gui logendcall 160 sau khi bao 11303(3)
            else:
                _logendcall_async(entry, rx=_cnt.get("rtp_rx", 0), tx=_cnt.get("rtp_tx", 0))
        except Exception:  # noqa: BLE001 - chi de chan doan / lich su
            pass
        _evaluate_srtp_outcome(entry)
        _stop_video(entry["call_id"])
        _stop_mic(entry["call_id"])
        _stop_speaker(entry["call_id"])
        ECHO_GUARDS.pop(str(entry["call_id"]), None)
        _CALL_DEVICES.pop(str(entry["call_id"]), None)
        engine_seam.SEAM.stop_media()
        media_endpoints.ENDPOINTS.stop_call(int(entry["call_id"]))
        STATE.audio_tokens.drop(entry["call_id"])
    except Exception as exc:  # noqa: BLE001
        _log_call("cleanup media error: %s" % str(exc)[:120])


# Cuộc gọi ĐẾN mà sau khi nghe máy điện thoại KHÔNG gửi bất kỳ gói nào (rtp/rtcp/video đều 0) là cuộc «chết» (13/11: 12/20 cuộc khi gói đầu chưa tới
# lúc chọn relay; gửi lại InitZRTP không cứu được). Nghe im lặng suốt cuộc thì vô ích và điện thoại báo «kết nối không ổn định» — tự kết thúc sớm
# (lý do «dead_media» đi theo webhook cuộc gọi để HA báo/gọi lại) để người gọi gọi lại ngay. ZALO_PC_DEAD_MEDIA_SECONDS, 0 = tắt.
VIDEO_VIEWERS_MAX = 2
VIDEO_VIEW_LOCK = threading.Lock()
VIDEO_VIEW_COUNT = [0]
# Đo thật 14/11 trong container (ffmpeg 7): `-fflags nobuffer` + pipe H.264 -> KHÔNG ra khung nào; H.264 thô không có dấu thời gian nên bộ lọc fps cũng
# không ra khung -> dùng `-framerate 15` ở đầu vào, `-flags low_delay`, giới hạn dò nhỏ; JPEG cần yuvj420p. 45/45 khung ra.
VIDEO_VIEW_FFMPEG = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-flags", "low_delay", "-probesize", "16384", "-analyzeduration", "100000",
                     "-framerate", "15", "-f", "h264", "-i", "pipe:0", "-vf", "scale=640:-2,format=yuvj420p", "-q:v", "7",
                     "-f", "mpjpeg", "-boundary_tag", "frame", "pipe:1"]






def _mark_answered(call_id, source, send_ack=True):
    """Mark a live (ringing) call answered: the peer picked up and
    the call is connected. `source` names how the app learned it
    ("api" = POST /api/call/answered, e.g. from a sync push event;
    "media" = first inbound RTP arrived; "sync" = a call_event
    "answer" on ctrl 99101). Idempotent: marking an
    already-answered call returns it unchanged without re-logging
    or re-ACKing. Returns the entry, or None when there is no live
    call with that id. Side effects on transition: the ring timer
    is disarmed (an answered call is never ring-timed-out), a
    [call] answered line is logged, a call webhook event fires,
    and — for an OUTGOING call only (send_ack=True) — an answerack
    (11304) is sent best-effort on a daemon thread for 1-1 calls.
    An INCOMING call is answered with send_ack=False: the callee
    never sends 11304 — it is the CALLER's signal (zca-js
    acceptIncomingCall sends no answerack; the mock's
    server_call_state confirms 11304 is the caller's ACK of the
    callee's answer). It also starts the P2P hello handshake
    (transport.begin_p2p, best-effort): only now — after the
    answer — does the relay know the peer's address, so only
    now can the hello go to the peer instead of to ourselves
    (2026-11-08, step 3)."""
    snap = STATE.calls.snapshot()
    live = None
    for c in snap["calls"]:
        if str(c["call_id"]) == str(call_id) \
                and c["status"] in ("sent", "answered", "incoming"):
            live = c
            break
    if live is None:
        return None
    if live["status"] == "answered":
        return dict(live)
    entry = STATE.calls.record_answered(call_id, source)
    if entry is None:
        return None
    _disarm_ring_timer(call_id)
    # Start the P2P hello handshake NOW (2026-11-08, step 3):
    # the peer has answered, so the relay knows the peer's
    # address and the type-02 tail is the peer (not us). The
    # transport never hellos on its own any more — before this
    # fix it helloed all through ringing to our own reflexive
    # address (61 hellos in the 30 s pcap). Defensive getattr:
    # an older fake transport without begin_p2p() must not
    # break the answer path.
    try:
        record = media_endpoints.ENDPOINTS.active_record(
            entry["call_id"])
        transport = (record or {}).get("transport")
        begin_p2p = getattr(transport, "begin_p2p", None)
        if callable(begin_p2p):
            begin_p2p()
    except Exception:  # noqa: BLE001 - P2P start is best-effort
        pass
    _log_call("answered call_id=%s source=%s"
              % (entry["call_id"], source))
    webhooks_mod.dispatch_call_event(
        STATE.webhook_dispatcher, entry,
        (STATE.session or {}).get("uid", ""))
    if (entry.get("type") or "user") != "group":
        _auto_media_async(entry["call_id"])
    if (entry.get("direction") or "") == "in" and (entry.get("type") or "user") != "group":
        _watch_dead_media(entry["call_id"])
    if send_ack and (entry.get("type") or "user") != "group":
        thread = threading.Thread(
            target=_send_answerack_async,
            args=(int(entry["call_id"]), entry["thread_id"]),
            daemon=True)
        thread.start()
    return entry


def _normalize_call_id(value):
    """Effective callId for a new outgoing call: always minted from
    the process-wide counter (see _next_call_id), starting at 1.
    The UI-supplied value is IGNORED by design — the real client's
    callId comes from the native engine's atomic counter (`lock
    xadd`), never from the UI; the UI used to send epoch seconds
    (~1.7e9), which the server accepts (status=0) but which is the
    top suspect for the peer never ringing (deep comparison §5.1).
    Like _type_request_for, this does not trust the body's value.
    The minted id is returned to the UI in the /api/call/request
    response, and the UI reuses it for /api/call/end — so one call
    keeps one id across 11300, 11301, cancel/endcall/answerack."""
    return _next_call_id()


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
    if call_type == "group":
        return protocol.CALL_TYPE_AUDIO_GROUP
    if call_type == "video":
        return protocol.CALL_TYPE_VIDEO_1_1
    return protocol.CALL_TYPE_AUDIO_1_1


class AppState(incoming_calls.IncomingCalls):
    def __init__(self, data_dir, auth=None):
        self.data_dir = data_dir
        # Nho che do SRTP nao tung nhan duoc goi that tu ben kia (che do
        # "auto" — khong tin tuyet doi vao mot nguon, xem srtp_mode.py).
        self.srtp_modes = srtp_mode_mod.SrtpModeStore(
            os.path.join(data_dir, "srtp_mode.json"))
        self.audio_tokens = call_audio_mod.CallAudioTokens()
        self.devices = devices_mod.DeviceStore(
            os.path.join(data_dir, "devices.json"))
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
        self.history_sync = history_sync_mod.HistorySync(
            data_dir, self._history_services, cookie_provider=lambda: (self.session or {}).get("zpw_sek", ""),
            imei_provider=lambda: (self.session or {}).get("device_id", ""), opener=lambda req, timeout: _zalo_urlopen(req, timeout))
        self.qr_flags = None    # co QR cua may chu Zalo (getServerInfo authen.trusted_device), doc moi lan lay ma QR
        self.qr_warning = ""    # canh bao khi may chu bat loai QR app chua ho tro
        # load() tra None ca khi file hong (H4): file da duoc doi
        # ten thanh session.json.corrupt trong load(), server khoi
        # dong voi phien trong thay vi chet truoc main(). Moi cho
        # dung self.session deu chiu duoc None (xem public_status,
        # start_sync, cac handler dung `(self.session or {})`).
        self.session = self.store.load() if self.store.exists() else None
        if self.session and self.session.get("client"):
            protocol.set_client(self.session["client"])      # phiên đã cấp theo kiểu nào thì mọi yêu cầu khai đúng kiểu đó
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
        # handlers below; message events fire from _on_sync_message
        # (SyncPoller 99100), group_event/reaction from
        # _on_ctrl_group_event / _on_ctrl_reaction (CtrlPoller 99101).
        self.webhook_store = webhooks_mod.WebhookStore(
            os.path.join(data_dir, webhooks_mod.FILENAME))
        self.webhook_dispatcher = webhooks_mod.WebhookDispatcher(
            self.webhook_store)
        # Chat: tin da gui trong phien (RAM, mat khi restart) de hien
        # ngay tin vua gui + lam lich su tam cho 1-1 (chat.ChatStore).
        self.chat_store = chat_mod.ChatStore()
        # INBOX (sync_poll.Inbox): tin DEN qua kenh sync long-poll
        # 99100 (tin 1-1 + nhom, ca hai chieu) — nguon cho lich su
        # ghep + /api/thread/*/updates + /api/inbox/summary.
        self.inbox = sync_poll_mod.Inbox()
        # Nhat ky suc khoe tai khoan (account_health.py): khoi dong / dang nhap / mo kenh / phien ket thuc + ly do.
        self.health = account_health.HealthLog(os.path.join(data_dir, "health.jsonl"))
        self.health.record("start", VERSION)
        # Kenh WebSocket (ws_listener.py) + loc trung giua WebSocket va long-poll (event_dedup.py). ZALO_PC_WS=off de tat.
        self.event_dedup = event_dedup_mod.EventDedup()
        self.ws = None
        self._revoke_hits = {}                 # trang thai kenh -> so lan kiem lien tiep (xem check_revoked)
        self.recall = recall_mod.RecallQueue(os.path.join(data_dir, "recall_queue.json"), self._recall_undo, log=lambda m: print(m, flush=True))
        self.conv_ttl = conv_ttl_mod.ConvTtl(self._fetch_conv_ttl, log=lambda m: print(m, flush=True))
        # Ma PIN rieng tu (privacy.py): TAT neu khong dat ZALO_PC_APP_PIN / ZALO_PC_APP_PIN_HASH. Dat sai dinh dang thi ne loi luc khoi dong
        # (khong am tham tat mot tinh nang bao mat).
        self.privacy = privacy_mod.PrivacyGate.from_env()
        # Con tro sync tren dia (cursor_store.py) + ban ghi tin ben
        # (message_store.py) — webhook missing pieces: con tro poll
        # luu xuong dia sau moi batch (restart van poll tiep tu cho
        # cu, server bu tin lo); tin den/gui ghi xuong SQLite de
        # restart khong mat + lich su 1-1 doc tu DB. DB gan voi uid
        # tai khoan hien tai (doi uid thi xoa — xem set_account).
        self.cursor_store = cursor_store_mod.SyncCursorStore(
            os.path.join(data_dir, cursor_store_mod.FILENAME))
        self.message_store = message_store_mod.MessageStore(
            os.path.join(data_dir, message_store_mod.FILENAME))
        if self.session and self.session.get("uid"):
            self.message_store.set_account(self.session["uid"])
        self.retention = retention_mod.Retention(data_dir, self.message_store)
        self.profile_names = profile_names_mod.ProfileNames(
            os.path.join(data_dir, profile_names_mod.FILENAME), self._lookup_profile_name,
            on_change=lambda: self.events.publish({"type": "names", "at": time.time()}))
        # Proxy ra Zalo, kenh day su kien cho giao dien (SSE), chan do mat
        # khau dang nhap app, va do tre nhan tin gan day (ms).
        self.proxy_store = proxy_store_mod.ProxyStore(
            os.path.join(data_dir, proxy_store_mod.FILENAME))
        self.events = events_mod.EventHub()
        self.calls.on_change = lambda: self.events.publish({"type": "call", "at": time.time()})    # popup cuoc goi den hien tuc thi
        self.login_limiter = app_auth.LoginLimiter(
            max_fails=int(os.environ.get("ZALO_PC_APP_LOGIN_MAX_FAILS") or 5))
        self.sync_lag = []
        # FILE INBOX (file_inbox.py): file den qua kenh sync duoc
        # tai ve dia + registry, de tai xuong / gui lai giu nguyen
        # ten goc. Getter doc phien tai thoi diem goi (phien co the
        # doi sau khi khoi tao) — khong giu transport cu.
        self.file_inbox = file_inbox_mod.FileInbox(
            os.path.join(data_dir, file_inbox_mod.DOWNLOADS_DIRNAME),
            http_get_bytes=self._file_http_get_bytes)
        # Sync poller (long-poll 99100): chay nen khi co phien +
        # poll_msg_urls; None khi chua co endpoint (phien cu) hoac
        # chua dang nhap. Duoc bao ve boi _sync_lock (start/stop
        # co the goi tu QR worker, main(), logout()).
        self.sync = None
        self._sync_lock = threading.Lock()
        # Registry URL ghi am async + poller kenh ctrl (99101):
        # CtrlPoller nap registry khi event voice_aac_success ve;
        # Chat.send_voice doi registry truoc khi gui buoc 2 (loi
        # 114 — xem chat.py / ctrl_poll.py). Registry ton tai ca
        # khi kenh ctrl chua chay (khi do send_voice loi ro thay
        # vi gui buoc 2 khong co fileUrl). voice_async_timeout mac
        # dinh 120 s nhu bundle (upload_file_timeout_wait_ctrl_event).
        self.voice_async = ctrl_poll_mod.VoiceAsyncRegistry()
        # Registry URL file async + timeout (loi 405 sharefile_full
        # — xem chat.send_file): CtrlPoller nap registry khi event
        # file_done ve; Chat.send_file doi registry truoc khi gui
        # buoc 2. Cung quy tac nhu voice: registry ton tai ca khi
        # kenh ctrl chua chay (khi do send_file loi ro thay vi gui
        # buoc 2 khong co fileUrl); timeout mac dinh 120 s nhu
        # bundle.
        self.file_async = ctrl_poll_mod.FileAsyncRegistry()
        self.ctrl = None
        self.voice_async_timeout = chat_mod.VOICE_ASYNC_WAIT_SECONDS
        self.file_async_timeout = chat_mod.FILE_ASYNC_WAIT_SECONDS
        # Last sync start/refresh failure, as "Type" or "Type
        # error_code=N" only — never a value (no sek/enk/uid, no
        # server message text). "" means no failure recorded.
        # sync_status() uses it to tell a failed getLoginInfo
        # refresh ("refresh_failed") apart from a session the
        # server genuinely gave no endpoints to ("no_endpoints").
        self.sync_error = ""
        # Chan doan hinh dang response getLoginInfo lan cuoi (ten
        # key cua data/config, khong ghi gia tri) — chi co khi
        # refresh tra ve khong co poll URLs; {} khi chua co loi
        # dang ghi. Hien o /api/status (sync_debug) de doc log
        # la biet server tra gi.
        self.sync_debug = {}
        # Background sync-retry loop (main() only) + manual-retry
        # cooldown for POST /api/sync/retry.
        self._sync_retry_thread = None
        self._sync_last_retry_at = 0.0
        self.thread = None
        # Ket qua keepAlive gan nhat (sua H5 + I1) — duoc bao ve
        # boi self.lock (cung khoa voi session). _ka_uid: uid ma
        # cache thuoc ve; doi tai khoan thi cache cu vo hieu
        # (trang thai ve "unknown", dem auth ve 0). _ka_state:
        # "unknown" (chua check) | "ok" | "auth_failed" (loi auth,
        # chua du nguong) | "network_error" (loi mang, phien giu
        # nguyen) | "expired" (du nguong, phien da bi xoa).
        # _ka_probe_running: co probe nen dang chay khong (de
        # /api/status khong spawn nhieu thread khi cache het han).
        self._ka_uid = None
        self._ka_at = 0.0
        self._ka_ok = None
        self._ka_state = "unknown"
        self._ka_auth_failures = 0
        self._ka_probe_running = False
        self._keepalive_thread = None
        # Stale-while-revalidate (sửa lỗi load chậm 2026-11-05): khi
        # cache đã hết TTL, GET /api/contacts trả cache cũ NGAY
        # (source "stale") rồi làm mới nền trong một thread riêng,
        # thay vì bắt trình duyệt chờ gọi tươi lên Zalo. Chỉ khi
        # hoàn toàn chưa có cache mới chờ gọi tươi. _contacts_refreshing
        # + _contacts_refresh_token chống hai lần làm mới nền chồng
        # nhau; token để thread cũ kết thúc không xóa cờ của lần mới.
        self._contacts_refreshing = False
        self._contacts_refresh_token = 0

    def _ctrl_error_text(self):
        """Loi cuoi cua kenh ctrl cho /api/status (ctrl_error):
        poller.last_error khi kenh ton tai, "" khi chua co kenh
        hoac kenh dang tot. Chi chup nhanh tham chieu poller
        duoi _sync_lock roi doc last_error (ghi/xoa last_error
        la phep gan str nguyen tu duoi GIL)."""
        with self._sync_lock:
            ctrl = self.ctrl
        if ctrl is None:
            return ""
        return getattr(ctrl, "last_error", "") or ""

    # -- session helpers -------------------------------------------------
    def public_status(self, app_user=""):
        # Read the session fields under self.lock, then call
        # sync_status() AFTER releasing it: sync_status() takes
        # _sync_lock, and start_sync() used to take self.lock while
        # holding _sync_lock (see start_sync) — holding both locks
        # in opposite orders wedged /api/status whenever a status
        # request overlapped a sync start. No path now holds one
        # sync lock while taking the other.
        with self.lock:
            sess = self.session
            logged = bool(sess and sess.get("zpw_sek"))
            uid = sess.get("uid", "") if sess else ""
            phonenum = sess.get("phonenum", "") if sess else ""
            # Ket qua keepAlive gan nhat (sua H5): /api/status
            # khong chi dua vao zpw_sek con trong file — neu
            # keepAlive da bao phien het (expired) thi session da
            # bi xoa o check_keepalive nen logged o tren la False.
            # Cache tu tai khoan khac khong duoc dung (ve unknown).
            if uid and self._ka_uid == uid:
                ka_state = self._ka_state
                ka_at = self._ka_at
                ka_failures = self._ka_auth_failures
            elif not uid and self._ka_state == "expired":
                # Phien vua bi keepAlive xoa (logout() reset ve
                # "unknown" nen "expired" chi co tu _expire_session):
                # giu lai ly do de status noi ro vi sao login=false.
                ka_state = "expired"
                ka_at = self._ka_at
                ka_failures = self._ka_auth_failures
            else:
                ka_state = "unknown"
                ka_at = 0.0
                ka_failures = 0
            # Cache het TTL + chua co probe nao dang chay thi kich
            # probe nen (khong goi mang ngay trong request status —
            # lan nay tra ket qua cu, lan sau co ket qua moi).
            need_probe = (
                logged and not self._ka_probe_running
                and (ka_at == 0.0
                     or time.time() - ka_at > KEEPALIVE_STATUS_TTL_SECONDS))
            if need_probe:
                self._ka_probe_running = True
        if need_probe:
            threading.Thread(
                target=self._keepalive_probe_background,
                daemon=True).start()
        base = {"version": VERSION,
                "deps": {k: v["ok"] for k, v in deps_mod.check().items()
                         if isinstance(v, dict)},
                "engine": engine_seam.SEAM.status(),
                "sync": self.sync_status(),
                "sync_error": self.sync_error,
                "ctrl": self.ctrl_status(),
                # ctrl_error: loi cuoi cua kenh ctrl (neu co) —
                # chan doan tren /api/status, giong sync_error.
                # Lay tu poller.last_error (da duoc _poll_once
                # xoa khi poll thanh cong) nen chi hien loi
                # dang ton tai, khong phai loi cu da khoi phuc.
                "ctrl_error": self._ctrl_error_text(),
                # keepalive: lan hoi Zalo gan nhat ve phien
                # (state/checked_at/auth_failures — khong lo
                # secret). UI hien QR khi login=false; khi state
                # la "expired" thi qr_error o /api/qr/status giai
                # thich ly do quet lai.
                "keepalive": {"state": ka_state,
                              "checked_at": ka_at,
                              "auth_failures": ka_failures},
                "app_user": app_user,
                # Nhat ky suc khoe tai khoan: vai su kien cuoi + ly do phien ket thuc gan nhat (HA doc de bao).
                "health": self.health.summary(),
                "ws": (self.ws.status() if self.ws is not None else {"state": "off"})}
        if self.sync_debug:
            base["sync_debug"] = dict(self.sync_debug)
        if logged:
            base.update({"login": True, "uid": uid,
                         "phonenum": phonenum})
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

    def _apply_recall(self, thread_type, thread_id, global_id, cli_id):
        """Mot tin bi THU HOI (nguoi khac / dien thoai / chinh minh): thay tin goc trong DB + RAM bang dau «da thu hoi», xoa chu goc, bao giao
        dien qua SSE «recall». Tra ve True neu tim thay tin goc (khi do khong luu them tin bao «Mot tin nhan da duoc thu hoi»)."""
        try:
            ids = list(self.message_store.recall(thread_type, thread_id, global_id, cli_id)) + list(self.inbox.recall(thread_type, thread_id, global_id, cli_id))
        except Exception:  # noqa: BLE001
            return False
        ids = list(dict.fromkeys(i for i in ids if i))
        if ids:
            try:
                self.events.publish({"type": "recall", "thread_type": thread_type, "thread_id": str(thread_id), "msg_ids": ids, "at": time.time()})
            except Exception:  # noqa: BLE001
                pass
        return bool(ids)

    def _apply_delete(self, thread_type, thread_id, content):
        """`chat.delete`: Zalo bao mot tin da bi XOA (chinh minh xoa, hen gio xoa/thu hoi...): bo tin goc khoi DB + RAM, bao giao dien qua SSE
        «delete». Chinh su kien KHONG BAO GIO duoc luu/hien nhu tin nhan (13/11: giao dien in nguyen [{'type': 1, 'actionType': 1, ...}])."""
        items = content if isinstance(content, list) else [content]
        ids = []
        for it in items:
            if not isinstance(it, dict):
                continue
            gid, cid = it.get("globalDelMsgId"), it.get("clientDelMsgId")
            try:
                ids += list(self.message_store.forget(thread_type, thread_id, gid, cid)) + list(self.inbox.forget(thread_type, thread_id, gid, cid))
            except Exception:  # noqa: BLE001
                pass
        ids = list(dict.fromkeys(i for i in ids if i))
        if ids:
            try:
                self.events.publish({"type": "delete", "thread_type": thread_type, "thread_id": str(thread_id), "msg_ids": ids, "at": time.time()})
            except Exception:  # noqa: BLE001
                pass
        return ids

    def _lookup_profile_name(self, uid):
        """Tra ho so Zalo theo ma nguoi dung (getprofiles/v2) de lay ten hien thi cua nguoi la."""
        status, res = services_mod.handle_svc(self, "get_user_info", {"user_id": str(uid)})
        if status != 200:
            raise RuntimeError("get_user_info %s %s" % (status, str((res or {}).get("error"))[:60]))
        return profile_names_mod.find_name((res or {}).get("data"), uid)

    def start_history_import(self):
        """Nhap lich su da giai ma vao messages.db (nen, tien do o history_sync.status()['import_state'])."""
        hs = self.history_sync
        if (hs.status().get("import_state") or {}).get("stage") == "running":
            raise RuntimeError("đang nhập, chờ xong đã")
        run_dir = hs.latest_run_dir()
        if not run_dir:
            raise RuntimeError("chưa có dữ liệu đồng bộ đã giải mã; hãy chạy Đồng bộ lịch sử trước")
        svc = self._history_services()
        own = str((self.session or {}).get("uid") or "")
        hs._set(import_state={"stage": "running", "detail": "Đang nhập…"})

        def work():
            try:
                days = self.retention.get()["messages_days"]
                res = history_import_mod.import_run(run_dir, self.message_store, svc, protocol.PROFILE_DOMAIN, own, keep_days=days,
                                                    progress=lambda t: hs._set(import_state={"stage": "running", "detail": t}))
                detail = "Đã nhập %d tin mới (%d tin trùng/bỏ qua) vào %d cuộc trò chuyện%s%s." % (
                    res["inserted"], res["skipped"], res["threads"], (", %d chưa đổi được mã" % res["unmapped"]) if res["unmapped"] else "",
                    (", %d tin cũ hơn %d ngày bị bỏ qua theo cài đặt tự xóa" % (res["old_skipped"], days)) if res["old_skipped"] else "")
                if res.get("upgraded"):
                    detail += " Đã cập nhật %d tin thành ảnh/tệp có link." % res["upgraded"]
                hs._set(import_state=dict(res, stage="done", detail=detail))
                self.events.publish({"type": "history_imported", "at": time.time()})
            except Exception as e:  # noqa: BLE001
                print("[history-import] loi: %s: %s" % (type(e).__name__, str(e)[:200]), flush=True)
                hs._set(import_state={"stage": "error", "detail": "Không nhập được: %s" % str(e)[:200]})
        threading.Thread(target=work, daemon=True).start()

    def _history_services(self):
        """Services cho phien hien tai (dong bo lich su: pull_mobile_msg...). Chua dang nhap -> RuntimeError."""
        sess = self.session
        if not sess or not sess.get("zpw_sek"):
            raise RuntimeError("chưa đăng nhập Zalo")
        transport = make_transport(sess["zpw_sek"])
        svc = services_mod.Services(transport, transport.http_post, sess["device_id"], sess["zpw_enk"],
                                    service_map=sess.get("service_map"))
        svc.uid = str(sess.get("uid") or "")
        return svc

    def _recall_undo(self, thread_type, thread_id, msg_id, cli_msg_id):
        """Thu hồi một tin đã hẹn. Chưa đăng nhập -> NotReady (mục giữ lại, không tính lỗi)."""
        try:
            svc = self._history_services()
        except RuntimeError as e:
            raise recall_mod.NotReady(str(e))
        svc.dispatch("undo_message", {"thread_id": thread_id, "type": thread_type, "msg_id": msg_id, "cli_msg_id": cli_msg_id})

    def _fetch_conv_ttl(self):
        """{thread_id: ttl_ms} của các cuộc trò chuyện đang bật tự xoá (xem conv_ttl.py)."""
        res = self._history_services().dispatch("get_auto_delete_chat", {})
        return {str(c["destId"]): int(c["ttl"]) for c in (res or {}).get("convers", []) if c.get("ttl")}

    # -- QR flow (background thread) ------------------------------------
    def start_qr(self, client=None, restart=False):
        """restart=True (UI chọn kiểu đăng nhập): bỏ QR đang chờ, lấy QR mới theo kiểu vừa chọn (luồng cũ bị đánh dấu «cũ» và im lặng thoát)."""
        with self.lock:
            running = bool(self.thread and self.thread.is_alive())
            if running and not restart:
                return False
            if not running:
                self._qr_prev_client = protocol.client_name()     # kiểu cần trả lại nếu QR hỏng/hết hạn
            self.qr_gen = getattr(self, "qr_gen", 0) + 1
            gen = self.qr_gen
            self.qr_client = client if client in protocol.CLIENTS else None     # None = giữ kiểu hiện tại
            self.qr_state = "waiting"
            self.qr_error = ""
            self.qr_warning = ""
            self.qr = None
        self.thread = threading.Thread(target=self._qr_worker, args=(gen,), daemon=True)
        self.thread.start()
        return True

    def _qr_worker(self, gen=None):
        prev_client = getattr(self, "_qr_prev_client", None) or protocol.client_name()
        chosen = getattr(self, "qr_client", None)
        logged_in = False

        def _stale():        # đã có QR mới thay thế luồng này (người dùng bấm quay lại rồi chọn kiểu khác)
            return gen is not None and gen != getattr(self, "qr_gen", gen)
        try:
            if chosen:
                protocol.set_client(chosen)          # phong bì đăng nhập + mọi yêu cầu sau đó khai kiểu này
            device_id, computer = self._device_and_computer()
            logged_uids = []
            if self.session and self.session.get("uid"):
                logged_uids = [self.session["uid"]]
            transport = make_transport()
            # Doc co may chu TRUOC khi lay ma, y nhu Zalo PC (do 12/11: PC chon QR loai cu/tu dung/thiet bi tin cay theo cac co nay).
            # Khong doc duoc thi van di tiep loai cu (nhu truoc), chi ghi ro vao nhat ky.
            flags = qr_login.fetch_server_flags(transport, device_id, computer)
            if _stale():
                return
            warning = qr_login.flags_warning(flags)
            with self.lock:
                self.qr_flags = flags
                self.qr_warning = warning
            print("[qr] %s%s" % (qr_login.describe_server_flags(flags), (" CANH BAO: " + warning) if warning else ""), flush=True)
            qr = qr_login.fetch_qr(
                transport, device_id, computer, logged_uids,
                param_cipher_key=PARAM_CIPHER_KEY, self_g=0, qr_form=0)
            if _stale():
                return
            with self.lock:
                self.qr = qr
                self.qr_state = "waiting"
            print("[qr] da tao ma QR (cho quet; het han sau ~%ss, toi da %s lan hoi)" % (qr.get("qr_timeout"), qr.get("qr_retry")), flush=True)
            qr_login.wait_scan(transport, qr, trust_enabled=False)
            if _stale():
                return
            with self.lock:
                self.qr_state = "scanned"
            print("[qr] dien thoai da quet, cho xac nhan", flush=True)
            grant = qr_login.wait_confirm(transport, qr)
            if _stale():
                return
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
                "poll_msg_urls": login_info.get("poll_msg_urls", []),
                "poll_ctl_urls": login_info.get("poll_ctl_urls", []),
                "poll_msg_timeout": login_info.get("poll_msg_timeout", 30),
                "poll_ctl_timeout": login_info.get("poll_ctl_timeout", 30),
                "status": session_mod.STATUS_LOGGED_IN,
                "client": protocol.client_name(),
            })
            if self.qr_flags and self.qr_flags.get("known"):
                sess["trusted_device"] = {k: bool(self.qr_flags[k]) for k in ("self_g", "qr_format_trust_device", "logo_qr")}
            self.store.save(sess)
            self.health.record("login", "qr")
            with self.lock:
                self.session = sess
                self.qr_state = "done"
                self.qr = None
                # New session: next friends load is a first load (init=1).
                self._contacts_init_pending = True
            # New session: the old session's contacts cache is stale.
            self._contacts_clear_cache()
            # Phien moi co poll endpoints -> mo kenh sync nhan tin den.
            self.start_sync()
            logged_in = True
        except qr_login.RateLimited as e:
            if _stale():
                return
            print("[qr] bi gioi han tan suat: phai cho %ss roi tao lai (Zalo tra time_left)" % e.wait_seconds, flush=True)
            with self.lock:
                self.qr_state = "rate_limited"
                self.qr_wait = e.wait_seconds
        except qr_login.UserRejected:
            if _stale():
                return
            print("[qr] nguoi dung tu choi dang nhap tren dien thoai (18010)", flush=True)
            with self.lock:
                self.qr_state = "rejected"
        except qr_login.QRExpired:
            if _stale():
                return
            print("[qr] ma QR het han (khong ai quet/xac nhan kip)", flush=True)
            with self.lock:
                self.qr_state = "expired"
        except qr_login.TrustFlowRequired as e:
            if _stale():
                return
            with self.lock:
                self.qr_state = "error"
                self.qr_error = ("Zalo yêu cầu đăng nhập QR kiểu “thiết bị tin cậy” (QR2) mà app chưa hỗ trợ. %s "
                                 "Chi tiết kỹ thuật: %s" % (qr_login.describe_server_flags(self.qr_flags), e))
        except Exception as e:  # noqa: BLE001 - surface to UI, keep server up
            if _stale():
                return
            print("[qr] loi dang nhap: %s: %s" % (type(e).__name__, str(e)[:200]), flush=True)
            with self.lock:
                self.qr_state = "error"
                self.qr_error = "%s: %s" % (type(e).__name__, e)
        finally:
            if chosen and not logged_in and not _stale():
                protocol.set_client(prev_client)     # QR hỏng/hết hạn: phiên đang sống (nếu có) giữ nguyên kiểu cũ

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
        # HINH DANG response (bundle compact-app-pc @11816376):
        # client resolve {config: e.data.data,
        # UIN: e.data.data.dkey, decryptKey: e.data.data.zpw_enk}
        # — toan bo data CHINH LA config. zpw_chts_new /
        # zpw_ctrs_new / zpw_service_map_new / zpw_conf / zpw_ws o
        # TOP-LEVEL cua data, khong phai duoi data.config. Ban cu
        # chi doc data["config"] nen tren response that khong bao
        # gio thay poll URLs (live 2026-11-07: QR xong, getLoginInfo
        # thanh cong, nhung "khong co zpw_chts_new" mai, ca hai
        # kenh khong mo duoc). Doc top-level truoc, roi fallback
        # sang data.config (shape cu) neu top-level thieu.
        # _data_keys / _config_keys chi la chan doan (ten key,
        # khong ghi gia tri) de lan sau doc log la biet server
        # tra gi thay vi chi biet "khong co zpw_chts_new".
        nested = data.get("config")
        config = dict(nested) if isinstance(nested, dict) else {}
        for key, value in data.items():
            if key != "config":
                config[key] = value
        # Kenh sync long-poll (bundle setEndpoints): W = zpw_chts_new
        # (tin nhan, 99100), q = zpw_ctrs_new (dieu khien, 99101),
        # X/Q = zpw_conf lp_msg_timeout / lp_ctl_timeout (giay).
        # Chi luu DANG list URL + so timeout — khong hard-code host.
        conf = config.get("zpw_conf", {}) or {}
        try:
            msg_timeout = int(conf.get("lp_msg_timeout") or 30)
        except (TypeError, ValueError):
            msg_timeout = 30
        try:
            ctl_timeout = int(conf.get("lp_ctl_timeout") or 30)
        except (TypeError, ValueError):
            ctl_timeout = 30
        return {"zpw_enk": data.get("zpw_enk", ""),
                "config": config,
                "dkey": data.get("dkey", ""),
                "poll_msg_urls": [u for u in
                                  (config.get("zpw_chts_new") or [])
                                  if isinstance(u, str) and u],
                "poll_ctl_urls": [u for u in
                                  (config.get("zpw_ctrs_new") or [])
                                  if isinstance(u, str) and u],
                "poll_msg_timeout": msg_timeout if msg_timeout > 0 else 30,
                "poll_ctl_timeout": ctl_timeout if ctl_timeout > 0 else 30,
                "_data_keys": sorted(data.keys()),
                "_config_keys": sorted(config.keys())}

    def qr_status(self):
        with self.lock:
            out = {"state": self.qr_state, "error": self.qr_error,
                   "wait_seconds": self.qr_wait, "client": protocol.client_name()}
            if self.qr_flags is not None:
                out["server_flags"] = dict(self.qr_flags, text=qr_login.describe_server_flags(self.qr_flags))
            if self.qr_warning:
                out["warning"] = self.qr_warning
            if self.qr and self.qr.get("base64_qr"):
                out["qr_image"] = ("data:image/png;base64,"
                                   + self.qr["base64_qr"])
                out["countdown"] = self.qr.get("qr_timeout") or 90
            if self.session and self.session.get("uid"):
                out["uid"] = self.session["uid"]
                out["phonenum"] = self.session.get("phonenum", "")
            return out

    def logout(self):
        self.health.record("session_end", "local_logout")
        with self.lock:
            self.store.clear()
            self.session = None
            self.qr = None
            self.qr_state = "idle"
            self._ka_uid = None
            self._ka_at = 0.0
            self._ka_ok = None
            self._ka_state = "unknown"
            self._ka_auth_failures = 0
        # Logged out: the session's contacts cache must go too.
        self._contacts_clear_cache()
        # Dang xuat: dung kenh sync + xoa tin den trong phien.
        self.stop_sync()
        self.inbox.clear()
        # Dang xuat: con tro + ban ghi tin thuoc ve tai khoan cu
        # — xoa de tai khoan khac dang nhap sau khong poll bang
        # con tro cu / khong doc lich su cu (message_store cung
        # xoa khi set_account doi uid, day la lop phong thu them).
        self.cursor_store.clear()
        self.message_store.clear()

    # -- sync long-poll (tin den) --------------------------------------
    def _file_http_get_bytes(self, url, timeout=120):
        """GET bytes cho FileInbox: dung transport cua phien Zalo
        hien tai (cookie zpw_sek), gioi han kich thuoc o muc
        MAX_DOWNLOAD_BYTES + 1 de khong doi day RAM. Khong co
        phien -> FileDownloadError (khong tai)."""
        sess = self.session
        if not sess or not sess.get("zpw_sek"):
            raise file_inbox_mod.FileDownloadError(
                "chua dang nhap Zalo — khong tai duoc file den")
        transport = make_transport(sess["zpw_sek"])
        return transport.http_get_bytes(
            url, timeout=timeout,
            max_bytes=file_inbox_mod.MAX_DOWNLOAD_BYTES + 1)

    def _on_sync_message(self, thread_type, thread_id, msg):
        """Callback moi tin den tu SyncPoller: ghi Inbox + ghi DB
        ben + day webhook message (dispatch_message tu choi tin tu
        gui, theo quy tac chong lap cua addon — xem webhooks.py).
        Chi log so luong, khong log noi dung tin. Tin dinh kem
        (file/anh co URL tai) duoc tai nen ve dia qua FileInbox
        (download_async — khong chan kenh sync, loi chi ghi log +
        registry)."""
        raw0 = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
        if raw0.get("msgType") == "chat.delete":
            self._apply_delete(thread_type, thread_id, raw0.get("content"))
            return                      # su kien xoa tin: khong luu, khong hien, khong day webhook
        if raw0.get("msgType") == "chat.undo":
            ct = raw0.get("content") if isinstance(raw0.get("content"), dict) else {}
            if self._apply_recall(thread_type, thread_id, ct.get("globalMsgId"), ct.get("cliMsgId")):
                return                  # da thay tin goc bang dau «da thu hoi»: khong luu them tin bao thu hoi
        try:
            is_new = self.inbox.record(thread_type, thread_id, msg)
        except Exception:
            return
        if not is_new:
            return
        # Day ngay cho giao dien (SSE) TRUOC moi viec nang (DB, tai file).
        self._note_lag(msg)
        if not msg.get("is_self"):
            RECEIPTS.add(thread_type, thread_id, msg.get("raw"))          # «da nhan» nhu Zalo PC (gop 150 ms, nen)
        try:
            self.events.publish({
                "type": "message", "thread_type": thread_type,
                "thread_id": str(thread_id), "msg": msg,
                "stranger": self.is_stranger(thread_type, thread_id),
                "received_at": time.time()})
        except Exception:  # noqa: BLE001 - UI khong duoc chan kenh sync
            pass
        # Ban ghi ben TRUOC khi dispatch: neu webhook loi / app
        # tat ngay sau do, tin van con trong DB de bu sau.
        try:
            self.message_store.record(thread_type, thread_id, msg)
        except Exception:
            pass
        # Tai file den ve dia (chi tin den co dinh kem + URL tai;
        # tin tu gui khong tai lai — file do chinh minh gui da co
        # o may gui). Loi khong bao gio nem ra day.
        try:
            if isinstance(msg, dict) and not msg.get("is_self") \
                    and msg.get("kind") \
                    in file_inbox_mod.AUTO_DOWNLOAD_KINDS \
                    and msg.get("file_url"):
                self.file_inbox.download_async(msg, thread_type,
                                               thread_id)
        except Exception:
            pass
        try:
            account_id = (self.session or {}).get("uid", "")
            ev = {"threadId": str(thread_id),
                  "type": 1 if thread_type == "group" else 0,
                  "senderId": msg.get("sender_id", ""),
                  "msgId": msg.get("id", ""),
                  "content": msg.get("text", ""),
                  "isSelf": bool(msg.get("is_self", False)),
                  "time": msg.get("time"),
                  "kind": msg.get("kind") or "",
                  "senderName": msg.get("sender_name") or (
                      msg.get("raw") if isinstance(msg.get("raw"), dict)
                      else {}).get("dName") or "",
                  "isStranger": self.is_stranger(thread_type, thread_id),
                  "contactStatus": self.contact_status(thread_type, thread_id),
                  "raw": msg.get("raw") if isinstance(msg.get("raw"), dict) else {}}     # ma goc (cliMsgId, uidFrom, ts) cho HA trich dan
            if msg.get("reply_to"):
                ev["replyTo"] = msg["reply_to"]            # tin nay TRA LOI mot tin khac (kem tep cua tin goc neu co)
                _rt = msg["reply_to"]
                if _REPLY_LOGS[0] < 8 and not sys.is_finalizing():     # chi ghi HINH DANG de biet dang that: khong ghi noi dung
                    _REPLY_LOGS[0] += 1
                    _q = (msg.get("raw") or {}).get("quote")
                    print("[reply] tin tra loi: thread=%s kind=%s quote_khoa=%s tep_goc=%s kieu_goc=%s" % (
                        thread_type, msg.get("kind"), sorted(_q.keys()) if isinstance(_q, dict) else type(_q).__name__,
                        _rt.get("attach_kind") or "khong", _rt.get("cli_msg_type")), flush=True)
            if msg.get("kind") == "voice" and msg.get("file_url") and not msg.get("is_self"):
                ev["voiceUrl"] = str(msg["file_url"])          # tin thoai den: HA tu goi voice_to_text voi URL nay (Zalo STT)
            if not msg.get("call_record"):           # ban ghi cuoc goi da co su kien call.*; day sang HA se khien AI «tra loi» no
                webhooks_mod.dispatch_message(self.webhook_dispatcher, ev, account_id)
        except Exception:
            pass

    def _save_sync_cursor(self, channel, cursor):
        """Luu con tro mot kenh (msg/ctrl) xuong dia sau moi batch
        (SyncCursorStore — khong bao gio nem loi)."""
        try:
            uid = (self.session or {}).get("uid", "")
            self.cursor_store.save(channel, cursor.to_dict(), uid)
        except Exception:
            pass

    def _on_ctrl_group_event(self, event):
        """Callback event nhom tu CtrlPoller (99101): day webhook
        group_event theo shape da co trong webhooks.py. Chi log
        dang event, khong log noi dung."""
        try:
            account_id = (self.session or {}).get("uid", "")
            webhooks_mod.dispatch_group_event(
                self.webhook_dispatcher, event, account_id)
        except Exception:
            pass

    def _on_ctrl_reaction(self, event):
        """Callback reaction tu CtrlPoller (99101): day webhook
        reaction theo shape da co trong webhooks.py (event la
        dict {threadId, msgId, uidFrom, icon, type} — xem
        ctrl_poll.extract_reactions)."""
        try:
            account_id = (self.session or {}).get("uid", "")
            webhooks_mod.dispatch_reaction(
                self.webhook_dispatcher, event, account_id)
        except Exception:
            pass

    def _on_ctrl_voice2text(self, event):
        """Ket qua Zalo AI chuyen giong noi: luu theo req_id + webhook. Chi log do dai."""
        V2T.put(event["req_id"], event.get("text", ""), event.get("error"))
        _log_call("voice2text req=%s chars=%d error=%s" % (
            event["req_id"], len(event.get("text") or ""), event.get("error")))
        try:
            webhooks_mod.dispatch_voice2text(
                self.webhook_dispatcher, event,
                (STATE.session or {}).get("uid", ""))
        except Exception:  # noqa: BLE001
            pass

    def _on_ctrl_call_event(self, event):
        """Callback call_event tu CtrlPoller (99101): su kien goi
        thoai theo flow zca-js (ZaloRtcSession: call_event act
        "request" -> ringring 11302 -> answer 11303 -> answerack
        11304 o phia caller; tu choi bang cancel 11305 + endcall
        11306). Chi log dang event + id, khong log noi dung."""
        try:
            act_raw = (event or {}).get("act", "")
            # Zalo gui ten co dau gach duoi ("end_call", "ring_ring",
            # "answer_ack", "cancel_call"...): chuan hoa roi moi so khop,
            # neu khong cuoc goi den bi bo qua khi ben goi cup may.
            act = str(act_raw).replace("_", "").replace("-", "").lower()
            call_id = (event or {}).get("call_id")
            if call_id is None:
                return
            _d, _ts = (event or {}).get("data"), None
            if isinstance(_d, dict):
                _p = _d.get("params")
                _ts = _d.get("ts") or (_p.get("ts") if isinstance(_p, dict) else None)
            # Khoa = act + call_id + TOAN BO noi dung data (ts, params...): hai su kien cung ts nhung khac noi dung (tat roi bat camera) la hai su kien.
            # Khong co ts thi KHONG loc (khong the phan biet hai lan bam giong het nhau).
            if _ts and self.event_dedup.seen("call:%s:%s:%s" % (act, call_id, event_dedup_mod.EventDedup.digest(_d))):
                return                              # cung mot su kien den hai nguon (WebSocket + poll): chi xu ly mot lan
            if act != "request":      # «request» da co dong «incoming offer» + «offer-params»; cac su kien con lai ghi day du de xem Zalo bao gi khi thiet bi KHAC nghe may / tu choi
                try:
                    def _clean(o, k=""):
                        if isinstance(o, dict):
                            return {a: _clean(b, a) for a, b in o.items()}
                        if isinstance(o, list):
                            return [_clean(b, k) for b in o[:8]]
                        if isinstance(o, str) and any(w in k.lower() for w in ("sess", "key", "token")):
                            return "<%d ky tu>" % len(o)
                        if isinstance(o, str):
                            try:
                                j = json.loads(o)
                                if isinstance(j, (dict, list)):
                                    return _clean(j, k)
                            except ValueError:
                                pass
                            return o if len(o) <= 120 else o[:120] + "..."
                        return o
                    _log_call("call_event raw act=%s call_id=%s %s" % (act_raw, call_id, json.dumps(_clean(event), ensure_ascii=False, sort_keys=True)[:5000]))
                except Exception:  # noqa: BLE001 - chan doan
                    pass
            if act == "request":
                self._on_incoming_call_request(event)
            elif act in ("cancel", "end", "endcall", "cancelcall"):
                self._on_incoming_call_ended(event, act)
            elif act == "answer":
                # Peer answered OUR outgoing call (sync path):
                # mark answered, source "sync" — _mark_answered
                # sends the caller's answerack (11304) itself.
                entry = _mark_answered(call_id, "sync")
                if entry is not None:
                    _log_call("call_event answer call_id=%s "
                              "answered" % call_id)
            elif act in ("audiotovideo", "requestaudio2video"):
                self._on_video_request(event)
            elif act == "onoffcamera":
                # «Xin bat camera» cua ben kia = xin chuyen cuoc thoai sang VIDEO (Zalo PC: ZaloCall.exe nhan ra `onoff_camera`). KHONG nhan act "1":
                # 12/11 18:53 act "1" den dung luc bam LOA NGOAI tren dien thoai, chua xac nhan la nut camera.
                self._on_camera_toggle(event)
            elif act in ("ringring", "answerack"):
                _log_call("call_event %s call_id=%s" % (act, call_id))
            elif act in ("grouprequest", "groupcancel", "groupend"):
                # Group incoming: chua ho tro (chi 1-1 o vong nay).
                _log_call("call_event %s call_id=%s "
                          "unsupported=group" % (act, call_id))
            else:
                _log_call("call_event act=%s call_id=%s ignored"
                          % (act_raw, call_id))
        except Exception:
            pass

    def _on_camera_toggle(self, event):
        """Su kien onoff_camera cua ben kia (act "1" / "onoff_camera", params.type 1 = bat, 0 = tat). Bat camera khi cuoc dang THOAI = loi xin chuyen sang
        video: xu ly nhu loi xin (status 1) de HA/quy tac quyet dinh dong y hay khong; cuoc da la video hoac tat camera thi chi ghi nhat ky."""
        call_id = int(event["call_id"])
        def _obj(x):                     # data / params cua Zalo co the la CHUOI JSON
            if isinstance(x, str):
                try:
                    x = json.loads(x)
                except ValueError:
                    return {}
            return x if isinstance(x, dict) else {}
        data = _obj(event.get("data"))
        params = _obj(data.get("params"))
        try:
            cam_on = int(params.get("type", data.get("type", 0))) == 1
        except (TypeError, ValueError):
            cam_on = False
        entry = next((c for c in STATE.calls.snapshot()["calls"] if str(c["call_id"]) == str(call_id)), None)
        already_video = bool(entry is not None and (entry.get("video") or entry.get("is_video") or entry.get("call_type") == "video"))
        _log_call("call_event camera call_id=%s %s%s" % (call_id, "bat" if cam_on else "tat", " (cuoc da la video)" if already_video else ""))
        _send_camera_inband(call_id, str(call_id) in VIDEO_SENDERS)       # zca-js: bên kia đổi camera thì gửi lại trạng thái camera của ta ngay
        if not cam_on or already_video:
            return
        self._on_video_request(dict(event, data=dict(data, params=dict(params, status=1))))

    def _on_video_request(self, event):
        """Dien thoai xin chuyen cuoc goi THOAI dang dien ra sang VIDEO (12056).
        status 1 = loi xin: neu bat `auto_video_on_request` thi sau `auto_video_delay`
        giay (0 = ngay) dong y (status 2) va, neu co camera mac dinh, phat hinh —
        chi khi luc do cuoc goi van dang noi may. status 2 = dong y loi xin cua ta."""
        call_id = int(event["call_id"])
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        params = data.get("params") if isinstance(data.get("params"), dict) else data
        try:
            status = int(params.get("status", data.get("status", 1)))
        except (TypeError, ValueError):
            status = 1
        _log_call("video request call_id=%s status=%s" % (call_id, status))
        if status == 1:
            # Báo cho HA (zalo_call_call_state state=video_request) để quy tắc/blueprint quyết định đồng ý hay không.
            try:
                entry = next((c for c in STATE.calls.snapshot()["calls"] if str(c["call_id"]) == str(call_id)), None)
                if entry is not None:
                    webhooks_mod.dispatch_call_event(STATE.webhook_dispatcher, entry, (STATE.session or {}).get("uid", ""),
                                                     extra={"status": "video_request",
                                                            "contact_status": self.contact_status("user", entry["thread_id"])})
            except Exception:  # noqa: BLE001 - báo HA là best-effort
                pass
        cfg = _devices_for_call(call_id)
        if status != 1 or not cfg["auto_video_on_request"]:
            return
        delay = int(cfg.get("auto_video_delay") or 0)

        def accept():
            entry = next((c for c in STATE.calls.snapshot()["calls"]
                          if str(c["call_id"]) == str(call_id)), None)
            if entry is None or entry["status"] != "answered":
                _log_call("video auto call_id=%s bo qua (cuoc goi da het)"
                          % call_id)
                return
            _send_a2v_async(call_id, entry["thread_id"], 2)
            cam = _devices_for_call(call_id)["camera_url"]
            if cam:
                try:
                    _start_video(call_id, cam)
                except (ValueError, RuntimeError) as exc:
                    _log_call("video auto call_id=%s error=%s"
                              % (call_id, str(exc)[:80]))

        if delay <= 0:
            accept()
        else:
            _log_call("video auto call_id=%s se dong y sau %ds" % (call_id, delay))
            timer = threading.Timer(delay, accept)
            timer.daemon = True
            timer.start()


    def _reject_busy(self, call_id, caller_id, peer):
        """Co cuoc goi DEN khi ta dang ban (dang noi hoac dang goi di): tu choi cuoc MOI (cancel + endcall), giu nguyen cuoc
        dang song; ghi mot entry ket thuc "busy_rejected" + webhook (nhu cuoc nho)."""
        entry = STATE.calls.record_busy_rejected(call_id, peer, caller_id, "user")
        sess = STATE.session
        ok, err = (False, "chua_dang_nhap")
        if sess:
            ok, err = _reject_signals(sess, caller_id, call_id, decline=False)
        _log_call("incoming call_id=%s tu choi vi dang ban zalo_ok=%s%s" % (call_id, ok, (" error=" + err[:80]) if err else ""))
        try:
            webhooks_mod.dispatch_call_event(STATE.webhook_dispatcher, entry, (sess or {}).get("uid", ""))
        except Exception:  # noqa: BLE001
            pass


    @staticmethod
    def _sync_error_text(exc):
        """Failure label for sync_error: exception type + a
        getLoginInfo error_code when one is present — never a
        value (no sek/enk/uid, no server message text)."""
        msg = str(exc)
        code = ""
        marker = "error_code="
        if marker in msg:
            tail = msg.split(marker, 1)[1].split()[0].strip(",")
            if tail:
                code = " error_code=%s" % tail
        return "%s%s" % (type(exc).__name__, code)

    def _refresh_poll_endpoints(self, sess):
        """Phien cu (luu truoc khi co poll endpoints, hoac thieu
        zpw_enk): goi lai getLoginInfo mot lan de lay
        zpw_chts_new/zpw_ctrs_new/zpw_conf + zpw_enk tu server,
        luu vao session.json. Best-effort: loi thi ghi sync_error
        (chi kieu/ma loi) va tra False. CHI duoc goi khi khong
        giu _sync_lock (no lay self.lock de luu — giu ca hai khoa
        theo thu tu nguoc nhau la deadlock, xem start_sync).

        Tra False trong 2 truong hop phan biet duoc qua sync_error:
        refresh loi (sync_error = "Type [error_code=N]") va server
        tra ve nhung khong co endpoint that
        (sync_error = "no_endpoints_from_server")."""
        try:
            device_id, computer = self._device_and_computer()
            info = self._fetch_login_info(
                {"zpw_sek": sess.get("zpw_sek", "")},
                device_id, computer)
        except Exception as e:  # noqa: BLE001 - best-effort
            self.sync_error = self._sync_error_text(e)
            print("[sync-poll] refresh endpoints loi: %s"
                  % self.sync_error, flush=True)
            return False
        if not info.get("poll_msg_urls"):
            self.sync_error = "no_endpoints_from_server"
            # Chan doan hinh dang response (ten key thoi, khong ghi
            # gia tri/bi mat) — de lan sau doc log la biet server
            # tra gi thay vi chi biet "khong co zpw_chts_new".
            # Quet QR lai KHONG sua duoc truong hop nay (dinh chinh
            # user 23:24 07/11: sau QR app phai tu lay duoc kenh);
            # app se tu thu lai qua vong retry.
            self.sync_debug = {
                "logininfo_data_keys": info.get("_data_keys", []),
                "logininfo_config_keys": info.get("_config_keys", []),
            }
            print("[sync-poll] getLoginInfo tra ve khong co "
                  "zpw_chts_new (data keys: %s; config keys: %s); "
                  "se tu thu lai"
                  % (self.sync_debug["logininfo_data_keys"],
                     self.sync_debug["logininfo_config_keys"]),
                  flush=True)
            return False
        with self.lock:
            cur = self.session
            if cur is None or cur.get("uid") != sess.get("uid"):
                return False
            cur["poll_msg_urls"] = info["poll_msg_urls"]
            cur["poll_ctl_urls"] = info["poll_ctl_urls"]
            cur["poll_msg_timeout"] = info["poll_msg_timeout"]
            cur["poll_ctl_timeout"] = info["poll_ctl_timeout"]
            # Refresh cung la co hoi sua zpw_enk / service_map /
            # ws_endpoint cua phien cu: phien thieu zpw_enk khong
            # bao gio mo duoc poller neu chi luu poll URLs (loi
            # cu: start_sync chan o zpw_enk truoc ca khi refresh).
            if info.get("zpw_enk"):
                cur["zpw_enk"] = info["zpw_enk"]
            config = info.get("config") or {}
            if config.get("zpw_service_map_new"):
                cur["service_map"] = config["zpw_service_map_new"]
            if config.get("zpw_ws"):
                cur["ws_endpoint"] = config["zpw_ws"]
            if info.get("dkey"):
                cur["dkey"] = info["dkey"]
            self.store.save(cur)
        self.sync_error = ""
        self.sync_debug = {}
        return True

    def start_sync(self):
        """Mo kenh sync long-poll neu co phien + poll_msg_urls +
        zpw_enk. Tra ve True khi poller chay, False khi chua du
        dieu kien. An toan khi goi nhieu lan; co the goi lai sau
        mot lan refresh loi (vong retry nen / POST /api/sync/retry).

        THU TU KHOA (sua issue 2 — deadlock + phien cu khong bao
        gio mo duoc): KHONG giu _sync_lock trong luc goi mang.
        Pha 1 chup nhanh phien duoi _sync_lock; pha 2 refresh
        getLoginInfo (lay self.lock luc luu, khong giu _sync_lock);
        pha 3 tao poller duoi _sync_lock (khong goi mang, khong
        lay self.lock). Ban cu giu _sync_lock xuyen suot ca
        refresh trong khi _refresh lay self.lock, con
        public_status lay self.lock truoc roi moi lay _sync_lock
        — mot request /api/status chen ngang luc dang nhap QR la
        ket ca hai luong vinh vien.
        Pha 2 chay khi thieu poll_msg_urls HOAC thieu zpw_enk:
        ban cu chan o zpw_enk truoc ca khi refresh, nen phien cu
        thieu enk khong bao gio duoc sua."""
        with self._sync_lock:
            poller = self.sync
            sess = dict(self.session) if self.session else None
        # Phien het han (401/403 — poller danh dau auth_failed):
        # dung retry mu, bao ro de user quet QR lai. Phien chet
        # thi refresh getLoginInfo cung khong cuu duoc; poller
        # se tu dung sau N loi lien tiep, khong mo lai o day.
        if poller is not None \
                and getattr(poller, "auth_failed", False):
            self.sync_error = getattr(poller, "last_error", "") \
                or "auth_failed"
            return False
        # Poller ton tai nhung thread da chet (tu dung sau loi
        # keo dai): coi nhu chua chay. Don tham chieu cu ngay
        # (pha 3 tra True ngay neu self.sync khong phai None)
        # de pha 3 tao poller moi; ban cu chi kiem `is not
        # None` nen POST /api/sync/retry cung khong mo lai
        # duoc poller da chet.
        sync_running = poller is not None \
            and _poller_is_alive(poller)
        need_refresh = False
        if poller is not None and not sync_running:
            need_refresh = getattr(poller, "stopped_reason", "") \
                == "persistent_errors"
            with self._sync_lock:
                if self.sync is poller:
                    self.sync = None
        if sync_running:
            # Sync da chay: dam bao kenh ctrl cung chay (kenh ctrl
            # co the chet rieng khi sync van song — KickOut -69 chi
            # dung ctrl; start_sync cu tra True ngay ma khong kiem
            # tra, nen kenh ctrl chet thi khong ai mo lai).
            self._ensure_ctrl_poller()
            return True
        if not sess or not sess.get("zpw_sek"):
            return False
        # Poller chet vi loi keo dai (persistent_errors) thi
        # refresh endpoints truoc: URL cu co the het han, dung
        # lai URL cu chi lap lai loi.
        if not sess.get("poll_msg_urls") or not sess.get("zpw_enk") \
                or not sess.get("poll_ctl_urls") or need_refresh:
            if not self._refresh_poll_endpoints(sess):
                print("[sync-poll] chua mo duoc kenh nhan tin den; "
                      "se thu lai (xem sync_error o /api/status)",
                      flush=True)
                return False
            with self.lock:
                sess = dict(self.session) if self.session else None
            if not sess:
                return False
        with self._sync_lock:
            if self.sync is not None:
                return True
            cur = self.session
            if cur is None or cur.get("uid") != sess.get("uid"):
                return False
            if not cur.get("zpw_sek") or not cur.get("zpw_enk") \
                    or not cur.get("poll_msg_urls"):
                if not cur.get("zpw_enk"):
                    self.sync_error = "missing_zpw_enk"
                elif not cur.get("poll_msg_urls"):
                    self.sync_error = "no_endpoints_from_server"
                return False
            transport = make_transport(cur["zpw_sek"], keepalive=True)
            uid = cur.get("uid", "")
            # DB gan voi uid tai khoan (doi uid thi xoa lich su cu);
            # con tro khoi tao tu dia (restart van poll tiep tu
            # cho cu — server bu tin lo trong hang doi).
            self.message_store.set_account(uid)
            try:
                poller = sync_poll_mod.SyncPoller(
                    transport, cur.get("poll_msg_urls"),
                    cur["zpw_enk"], uid,
                    on_message=self._on_sync_message,
                    msg_timeout=cur.get("poll_msg_timeout", 30),
                    cursor=self.cursor_store.load("msg", uid),
                    on_cursor=lambda c: self._save_sync_cursor(
                        "msg", c))
            except ValueError as e:
                self.sync_error = self._sync_error_text(e)
                print("[sync-poll] %s" % self.sync_error, flush=True)
                return False
            poller.dedup, poller.dedup_check = self.event_dedup, self._ws_active
            poller.start()
            self.sync = poller
            self.sync_error = ""
            print("[sync-poll] da mo kenh nhan tin den (%d endpoint)"
                  % len(poller.urls), flush=True)
            self.health.record("channel_open", "sync")
            # Kenh ctrl (99101, zpw_ctrs_new): event
            # voice_aac_success mang URL ghi am cho send_voice (loi
            # 114) va file_done mang URL file cho send_file (loi 405
            # sharefile_full). Mo kem kenh tin nhan; thieu endpoint
            # thi chi ghi log — send_voice/send_file se loi ro
            # (khong gui buoc 2 khong co fileUrl) thay vi im lang.
            # Chi mo khi chua co kenh nao dang chay: mo lai sync
            # sau khi poller chet ma ctrl van song thi khong tao
            # trung kenh ctrl (le thread + 2 poller cung doc mot
            # kenh). Khong mo lai kenh bi da (kicked_out) — nhu
            # _ensure_ctrl_poller.
            ctrl = self.ctrl
            if ctrl is None or (not _poller_is_alive(ctrl)
                                and not ctrl.kicked_out):
                self._spawn_ctrl_poller_locked()
            self._start_ws_locked(cur)
            return True

    # -- kenh WebSocket (hoc tu app iOS «GiaNo» + zca-js): du phong = hai bo poll luon chay song song ---------------------
    def _ws_active(self):
        ws = self.ws
        return bool(ws is not None and ws.active)

    def _start_ws_locked(self, cur):
        """Mo bo nghe WebSocket neu chua chay. CHI goi khi dang giu _sync_lock; khong goi mang (bo nghe tu chay trong luong rieng).
        Loi o day KHONG bao gio lam hong viec mo kenh poll."""
        try:
            if os.environ.get("ZALO_PC_WS", "on").strip().lower() in ("0", "off", "false", "no"):
                return
            if self.ws is not None and self.ws.state not in ("idle", "disabled"):
                return
            urls = cur.get("ws_endpoint") or []
            urls = [urls] if isinstance(urls, str) else list(urls)
            try:
                ping = float(os.environ.get("ZALO_PC_WS_PING_SECONDS") or ws_listener_mod.DEFAULT_PING_SECONDS)
            except ValueError:
                ping = ws_listener_mod.DEFAULT_PING_SECONDS
            ws = ws_listener_mod.WsListener(
                urls, "zpw_sek=%s" % cur["zpw_sek"], protocol.user_agent(), self._on_ws_event, protocol.API_VERSION, protocol.API_TYPE,
                ping_seconds=ping, on_state=self._on_ws_state,
                log=lambda m: print(m, flush=True))
            if ws.start():
                self.ws = ws
        except Exception as e:  # noqa: BLE001 - WebSocket la phan them: loi thi chi ghi log, poll van chay
            print("[ws] khong mo duoc: %s" % type(e).__name__, flush=True)

    def _on_ws_state(self, state, note=""):
        try:
            self.health.record("ws", ("%s: %s" % (state, note)) if note else state)
        except Exception:  # noqa: BLE001
            pass
        ws = self.ws
        if state == "disabled" and ws is not None and (ws.last_close or {}).get("code") == ws_listener_mod.CLOSE_KICK:
            threading.Thread(target=self._probe_after_kick, daemon=True, name="probe-after-kick").start()

    def _on_ws_event(self, kind, data):
        """Su kien da giai ma tu WebSocket -> CUNG ham xu ly voi long-poll (extract_messages / extract_call_events...)."""
        with self._sync_lock:
            poller = self.sync if kind == "sync" else self.ctrl
        if poller is not None and hasattr(poller, "handle_decoded"):
            poller.handle_decoded(data, via="ws")

    def _spawn_ctrl_poller_locked(self):
        """Tao + start CtrlPoller tu phien hien tai. CHI goi khi
        dang giu _sync_lock (khong goi mang, khong lay self.lock).
        Tra True neu poller chay. Thieu endpoint/enk thi chi ghi
        log, tra False — sync van chay, send_voice/send_file se
        loi ro thay vi gui buoc 2 khong co fileUrl."""
        cur = self.session
        if cur is None or not cur.get("zpw_sek") \
                or not cur.get("zpw_enk"):
            return False
        ctl_urls = cur.get("poll_ctl_urls") or []
        if not ctl_urls:
            print("[sync-poll] khong co zpw_ctrs_new — kenh "
                  "ctrl (99101) chua mo; gui ghi am/file se loi ro "
                  "thay vi gui khong URL", flush=True)
            return False
        try:
            ctrl = ctrl_poll_mod.CtrlPoller(
                make_transport(cur["zpw_sek"], keepalive=True), ctl_urls,
                cur["zpw_enk"], cur.get("uid", ""), self.voice_async,
                ctl_timeout=cur.get("poll_ctl_timeout", 30),
                cursor=self.cursor_store.load(
                    "ctrl", cur.get("uid", "")),
                on_cursor=lambda c: self._save_sync_cursor("ctrl", c),
                on_group_event=self._on_ctrl_group_event,
                on_reaction=self._on_ctrl_reaction,
                on_call_event=self._on_ctrl_call_event,
                on_voice2text=self._on_ctrl_voice2text,
                on_sync_event=self.history_sync.on_event,
                file_registry=self.file_async)
        except ValueError as e:
            print("[sync-poll] kenh ctrl khong mo duoc: %s"
                  % e, flush=True)
            return False
        ctrl.dedup, ctrl.dedup_check = self.event_dedup, self._ws_active
        ctrl.start()
        self.ctrl = ctrl
        print("[sync-poll] da mo kenh ctrl (99101, %d endpoint)"
              % len(ctrl.urls), flush=True)
        self.health.record("channel_open", "ctrl")
        return True

    def _ensure_ctrl_poller(self):
        """Dam bao kenh ctrl chay (dung khi sync da chay, hoac tu
        vong retry). Neu ctrl dang chay thi khong lam gi; neu chet
        thi mo lai; neu thieu poll_ctl_urls thi refresh getLoginInfo
        mot lan truoc. KHONG mo lai khi ctrl bi da (kicked_out).
        Khong giu khoa nao khi vao (refresh goi mang + lay
        self.lock); chi giu _sync_lock trong tung buoc ngan."""
        with self._sync_lock:
            ctrl = self.ctrl
            if ctrl is not None and _poller_is_alive(ctrl):
                return True
            if ctrl is not None and ctrl.kicked_out:
                return False
            ctl_urls = ((self.session or {}).get("poll_ctl_urls")
                        or [])
        if not ctl_urls:
            sess = dict(self.session) if self.session else None
            if not sess or not sess.get("zpw_sek"):
                return False
            if not self._refresh_poll_endpoints(sess):
                return False
            with self._sync_lock:
                ctl_urls = ((self.session or {}).get("poll_ctl_urls")
                            or [])
            if not ctl_urls:
                return False
        with self._sync_lock:
            ctrl = self.ctrl
            if ctrl is not None and _poller_is_alive(ctrl):
                return True
            if ctrl is not None and ctrl.kicked_out:
                return False
            return self._spawn_ctrl_poller_locked()

    def _ctrl_needs_restart(self):
        """True khi sync dang chay nhung kenh ctrl khong chay va
        khong bi da — vong retry nen goi start_sync() de mo lai
        (start_sync se goi _ensure_ctrl_poller). False khi sync
        chua chay (duong retry sync lo) hoac ctrl bi da."""
        with self._sync_lock:
            if self.sync is None:
                return False
            ctrl = self.ctrl
            if ctrl is None:
                return True
            if ctrl.kicked_out:
                return False
            return not _poller_is_alive(ctrl)

    def ctrl_status(self):
        """Trang thai kenh ctrl (99101) cho /api/status:
        running / no_endpoints / stopped / kicked_out /
        auth_failed / logged_out.
        - running: poller dang chay (event file_done/voice ve duoc).
        - no_endpoints: phien co that nhung khong co zpw_ctrs_new
          (getLoginInfo khong cap) — app tu thu lai, quet QR lai
          KHONG sua duoc (kenh phai tu mo sau QR).
        - stopped: co endpoint nhung poller chua chay / da dung.
        - kicked_out: server bao dung (-69), khong tu mo lai.
        - auth_failed: server tra 401/403 (phien het han) — can
          quet QR lai, khong retry mu.
        - logged_out: chua dang nhap."""
        with self._sync_lock:
            sess = self.session
            ctrl = self.ctrl
        if not sess or not sess.get("zpw_sek"):
            return "logged_out"
        if ctrl is not None:
            if ctrl.kicked_out:
                return "kicked_out"
            if getattr(ctrl, "auth_failed", False):
                return "auth_failed"
            if _poller_is_alive(ctrl):
                return "running"
            return "stopped"
        if not (sess.get("poll_ctl_urls") or []):
            return "no_endpoints"
        return "stopped"

    def start_sync_retry_thread(self):
        """Vong retry nen cho kenh sync (chi main() goi): kiem tra
        moi SYNC_RETRY_CHECK_SECONDS (60s), thu start_sync() mot
        lan khi phien dang dang nhap ma kenh dang xuong o trang
        thai thu lai duoc, toi da 1 lan moi
        SYNC_RETRY_INTERVAL_SECONDS (300s). Khong bao gio thu lai
        sau kicked_out (server bao dung) hay auth_failed (phien
        het han, can quet QR). An toan khi goi nhieu lan."""
        with self._sync_lock:
            if self._sync_retry_thread is not None \
                    and self._sync_retry_thread.is_alive():
                return False
            thread = threading.Thread(target=self._sync_retry_loop,
                                      daemon=True)
            self._sync_retry_thread = thread
            thread.start()
            return True

    def _sync_retry_loop(self):
        while True:
            time.sleep(SYNC_RETRY_CHECK_SECONDS)
            try:
                sess = self.session
                if not sess or not sess.get("zpw_sek"):
                    continue
                # sync_status() bao "stopped" ca khi poller ton
                # tai nhung thread da chet (tu dung sau loi keo
                # dai) — ban cu doi `self.sync is None` nen
                # khong bao gio mo lai poller ket trong backoff
                # (self.sync van tro toi no). Khong thu lai sau
                # kicked_out hay auth_failed (hai trang thai do
                # khong nam trong danh sach thu lai duoc duoi
                # day). Kiem tra moi 60s nhung thu toi da 1 lan
                # / 300s (dung chung _sync_last_retry_at voi
                # POST /api/sync/retry) de khong hammer
                # getLoginInfo.
                needs_sync = self.sync_status() in (
                    "no_endpoints", "refresh_failed", "stopped")
                if needs_sync or self._ctrl_needs_restart():
                    now = time.time()
                    if now - self._sync_last_retry_at \
                            < SYNC_RETRY_INTERVAL_SECONDS:
                        continue
                    self._sync_last_retry_at = now
                    self.start_sync()
            except Exception:  # noqa: BLE001 - retry nen khong chet
                pass

    # -- kiem chung phien bang keepAlive (sua H5 + I1) --------------
    def _keepalive_probe(self, sess):
        """Mot lan goi keepAlive that (GET chat /keepalive, {imei}).
        Tra data da giai ma; nem ServiceError / RuntimeError khi
        loi. Tach rieng de test monkeypatch duoc (mock/offline)."""
        transport = make_transport(sess["zpw_sek"])
        svc = services_mod.Services(
            transport, transport.http_post,
            sess["device_id"], sess["zpw_enk"],
            service_map=sess.get("service_map") or {},
            http_post_multipart=transport.http_post_multipart)
        return svc.dispatch("keepAlive", {})

    def check_keepalive(self):
        """Hoi Zalo mot lan xem phien hien tai con song khong.
        Tra True (phien song) / False (loi) / None (khong co
        phien de hoi — khong lam gi). Khong bao gio nem loi ra
        ngoai (loi da phan loai o day); khong crash server.
        Loi auth (600/401/403) dem lien tiep; du nguong
        KEEPALIVE_AUTH_FAILURES_TO_EXPIRE thi xoa phien (xem
        _expire_session) de UI hien lai QR. Loi mang chi ghi
        nhan — phien duoc giu, retry lan sau."""
        with self.lock:
            sess = dict(self.session) if self.session else None
        if not sess or not sess.get("zpw_sek"):
            return None
        try:
            self._keepalive_probe(sess)
        except Exception as e:  # noqa: BLE001 - phan loai roi xu ly
            kind = _classify_keepalive_error(e)
            expired = False
            with self.lock:
                cur = self.session
                if cur is None or cur.get("uid") != sess.get("uid"):
                    # Phien doi giua chung (dang nhap moi / dang
                    # xuat) — bo ket qua cua phien cu.
                    return False
                if self._ka_uid != sess.get("uid"):
                    self._ka_uid = sess.get("uid")
                    self._ka_auth_failures = 0
                self._ka_at = time.time()
                self._ka_ok = False
                if kind == "auth":
                    self._ka_auth_failures += 1
                    self._ka_state = "auth_failed"
                    expired = (self._ka_auth_failures
                               >= KEEPALIVE_AUTH_FAILURES_TO_EXPIRE)
                else:
                    # Loi mang / loi khac: phien giu nguyen, dem
                    # auth khong tang (loi thoang qua khong xoa).
                    self._ka_state = "network_error"
            if expired:
                self._expire_session(
                    sess.get("uid"),
                    "Phiên Zalo đã hết hạn (keepAlive báo lỗi xác "
                    "thực %d lần liên tiếp) — quét lại QR để đăng "
                    "nhập." % KEEPALIVE_AUTH_FAILURES_TO_EXPIRE, wipe=False)     # giữ tin: set_account tự xoá nếu người đăng nhập sau là tài khoản khác
            return False
        with self.lock:
            cur = self.session
            if cur is None or cur.get("uid") != sess.get("uid"):
                return False
            if self._ka_uid != sess.get("uid"):
                self._ka_uid = sess.get("uid")
            self._ka_at = time.time()
            self._ka_ok = True
            self._ka_state = "ok"
            self._ka_auth_failures = 0
        return True

    def _expire_session(self, uid, reason, wipe=True, code="session_rejected"):
        """Xoa phien Zalo da het han (keepAlive bao loi auth du
        nguong) — giong logout nhung chi khi phien hien tai dung
        la phien da check (uid khop), de khong xoa nham mot lan
        dang nhap moi vua xong. UI se hien lai QR vi /api/status
        ve login=false; qr_error giai thich ly do quet lai.
        Tra True khi da xoa, False khi phien da doi."""
        with self.lock:
            cur = self.session
            if cur is None or cur.get("uid") != uid:
                return False
            self.store.clear()
            self.session = None
            self.qr = None
            self.qr_state = "idle"
            self.qr_error = reason
            self._ka_state = "expired"
        self.health.record("session_end", code)
        # Du lieu cua tai khoan cu phai di theo phien (giong
        # logout): cache danh ba, kenh sync, tin den, con tro +
        # ban ghi tin — khong de tai khoan moi doc du lieu cu.
        # wipe=False (bi thu hoi tu xa / het phien): GIU tin va con tro — message_store.set_account() tu xoa neu nguoi dang nhap
        # sau la TAI KHOAN KHAC, con cung tai khoan thi khong mat lich su chi vi bi da.
        self._contacts_clear_cache()
        self.stop_sync()
        self.inbox.clear()
        if wipe:
            self.cursor_store.clear()
            self.message_store.clear()
        return True

    def start_keepalive_thread(self):
        """Vong nen keepAlive (chi main() goi): hoi ngay luc khoi
        dong de validate phien cu, roi moi
        KEEPALIVE_CHECK_INTERVAL_SECONDS. An toan khi goi nhieu
        lan; khong bao gio chet vi loi (vong loop bat het)."""
        with self.lock:
            if self._keepalive_thread is not None \
                    and self._keepalive_thread.is_alive():
                return False
            thread = threading.Thread(target=self._keepalive_loop,
                                      daemon=True)
            self._keepalive_thread = thread
            thread.start()
            return True

    # -- giam sat thu hoi phien (hoc tu app iOS «GiaNo»: remote_revoked) --
    REVOKE_WATCH_INTERVAL_SECONDS = 10
    _REVOKE_STATES = {
        "kicked_out": ("remote_revoked",
                       "Zalo báo dừng kênh nhận của phiên này (đăng nhập ở nơi khác hoặc bị thu hồi từ xa). Quét QR để đăng nhập lại."),
        "auth_failed": ("session_rejected",
                        "Zalo từ chối phiên này (hết hạn hoặc bị thu hồi). Quét QR để đăng nhập lại."),
    }

    def check_revoked(self):
        """Mot lan kiem: neu kenh nhan tin hoac kenh ctrl da bao kicked_out (-69) / auth_failed (401, 403 sau khi da dem du) thi ket thuc phien NGAY
        (hien lai QR, ghi ly do) thay vi cho keepAlive (5 phut/lan, can 2 lan loi) — truoc day app van bao «da dang nhap» trong khi khong
        nhan duoc gi va gui tin deu loi. Tra ma ly do neu da ket thuc phien, "" neu khong."""
        with self.lock:
            sess = self.session
        if not sess or not sess.get("zpw_sek"):
            return ""
        uid = sess.get("uid", "")
        seen = set()
        for state in (self.sync_status(), self.ctrl_status()):
            hit = self._REVOKE_STATES.get(state)
            if not hit:
                continue
            seen.add(state)
            # kicked_out (-69) la lenh ro rang cua may chu: thoat ngay. auth_failed can 2 lan kiem lien tiep (>= 10 giay) de mot loi thoang qua
            # khong dang xuat nham (co se tu xoa khi poll thanh cong lai).
            self._revoke_hits[state] = self._revoke_hits.get(state, 0) + 1
            if state == "kicked_out" or self._revoke_hits[state] >= 2:
                if self._expire_session(uid, hit[1], wipe=False, code=hit[0]):
                    self._revoke_hits.clear()
                    print("[session] phien ket thuc: %s (kenh bao %s)" % (hit[0], state), flush=True)
                    return hit[0]
        for state in list(self._revoke_hits):
            if state not in seen:
                del self._revoke_hits[state]
        return ""

    def _probe_after_kick(self, gap=3.0):
        """WebSocket bi da (3003) = tin hieu thu hoi som nhat (som hon poll ~9 giay, hon keepAlive vai phut): hoi keepAlive NGAY hai lan cach nhau `gap` giay
        (dung nguong KEEPALIVE_AUTH_FAILURES_TO_EXPIRE) thay vi cho vong 5 phut. Neu phien van song (3003 vi ly do khac) thi keepAlive tra OK va khong lam gi."""
        for i in range(KEEPALIVE_AUTH_FAILURES_TO_EXPIRE):
            try:
                self.check_keepalive()
            except Exception:  # noqa: BLE001
                pass
            if i + 1 < KEEPALIVE_AUTH_FAILURES_TO_EXPIRE:
                time.sleep(gap)

    def _revoke_watch_loop(self):
        while True:
            time.sleep(self.REVOKE_WATCH_INTERVAL_SECONDS)
            try:
                self.check_revoked()
            except Exception:  # noqa: BLE001 - vong nen khong chet
                pass

    def start_revoke_watchdog(self):
        """Chi main() goi. An toan khi goi nhieu lan."""
        with self.lock:
            t = getattr(self, "_revoke_thread", None)
            if t is not None and t.is_alive():
                return False
            self._revoke_thread = threading.Thread(target=self._revoke_watch_loop, daemon=True)
            self._revoke_thread.start()
            return True

    def _keepalive_loop(self):
        while True:
            try:
                self.check_keepalive()
            except Exception:  # noqa: BLE001 - vong nen khong chet
                pass
            time.sleep(KEEPALIVE_CHECK_INTERVAL_SECONDS)

    def _keepalive_probe_background(self):
        """Probe nen do /api/status kich khi cache het TTL."""
        try:
            self.check_keepalive()
        except Exception:  # noqa: BLE001 - loi nen khong chet
            pass
        finally:
            with self.lock:
                self._ka_probe_running = False

    def stop_sync(self):
        """Dung kenh sync + kenh ctrl (dang xuat)."""
        with self._sync_lock:
            poller, self.sync = self.sync, None
            ctrl, self.ctrl = self.ctrl, None
            ws, self.ws = self.ws, None
        if ws is not None:
            ws.stop()
        if poller is not None:
            poller.stop()
        if ctrl is not None:
            ctrl.stop()

    def sync_status(self):
        """Trang thai kenh sync cho /api/status (khong lo secret):
        running / no_endpoints / refresh_failed / stopped /
        logged_out / kicked_out / auth_failed.

        - running: poller dang chay (tin den se ve).
        - no_endpoints: phien co that nhung server khong cap
          endpoint (getLoginInfo tra ve khong co zpw_chts_new) —
          app tu thu lai qua vong retry; quet QR lai KHONG sua
          duoc truong hop nay (kenh phai tu mo sau QR — dinh chinh
          user 23:24 07/11).
        - refresh_failed: getLoginInfo refresh loi (sync_error
          giu kieu/ma loi) — thu lai duoc, chua ket luan la
          thieu endpoint.
        - stopped: co endpoint nhung poller chua chay / da dung
          (tu dung sau loi keo dai, hoac chua mo). Khi poller
          chet ma con loi cuoi thi sync_error giu loi do de
          /api/status thay ro ly do.
        - auth_failed: server tra 401/403 (phien het han) — can
          quet QR lai, khong retry mu.
        - logged_out / kicked_out: chua dang nhap / server bao
          dung poll (-69).

        Chi chup nhanh tham chieu poller duoi _sync_lock roi
        tha khoa ngay — khong giu khoa trong luc doc session,
        de khong tao vong khoa cheo voi start_sync()."""
        with self._sync_lock:
            poller = self.sync
        if poller is not None:
            if poller.kicked_out:
                return "kicked_out"
            if getattr(poller, "auth_failed", False):
                last_error = getattr(poller, "last_error", "")
                if last_error:
                    self.sync_error = last_error
                return "auth_failed"
            # Ban cu tra "running" chi can poller ton tai — app
            # bao "running" trong khi thread da chet (loi live
            # 08/11: ca hai poller loi JSON ma /api/status van
            # "running"). Gio kiem tra thread con song khong.
            if _poller_is_alive(poller):
                return "running"
            last_error = getattr(poller, "last_error", "")
            if last_error:
                self.sync_error = last_error
            return "stopped"
        sess = self.session
        if not sess or not sess.get("zpw_sek"):
            return "logged_out"
        if not sess.get("poll_msg_urls"):
            if self.sync_error \
                    and self.sync_error != "no_endpoints_from_server":
                return "refresh_failed"
            return "no_endpoints"
        return "stopped"

    def _friend_ids(self):
        """Tap userId ban be tu cache danh ba; None neu chua tai danh ba."""
        with self._contacts_lock:
            cache = self._contacts_cache
        if cache is None:
            return None
        rows = (cache.get("friends") or {}).get("rows") or []
        return {str(r["id"]) for r in rows if isinstance(r, dict) and r.get("id")}

    def contact_status(self, thread_type, thread_id):
        """"group" | "friend" | "stranger" | "unknown" (chua tai duoc danh ba: KHONG doan — HA coi la khong biet va dong cua)."""
        if thread_type == "group":
            return "group"
        ids = self._friend_ids()
        if ids is None:
            return "unknown"
        if str(thread_id) == str((self.session or {}).get("uid", "")):
            return "friend"
        return "friend" if str(thread_id) in ids else "stranger"

    def is_stranger(self, thread_type, thread_id):
        """Nguoi lap tin 1-1 khong co trong danh ba (chi biet khi da tai danh ba)."""
        if thread_type == "group":
            return False
        ids = self._friend_ids()
        mine = str((self.session or {}).get("uid", ""))
        return ids is not None and str(thread_id) not in ids and str(thread_id) != mine

    def _note_lag(self, msg):
        """Ghi do tre = gio app nhan - gio Zalo ghi cho tin (ms). Chi tham khao:
        lech dong ho giua may chu va Zalo cung nam trong so nay."""
        try:
            if msg.get("call_record"):
                return                         # ban ghi cuoc goi: Zalo tao khi cuoc goi ket thuc nen «tre» = thoi luong cuoc goi, khong phai do tre nhan tin
            raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
            ts_ms = float(raw.get("ts") or 0) or float(msg.get("time") or 0) * 1000
            if ts_ms:
                lag_ms = time.time() * 1000 - ts_ms
                self.sync_lag = (self.sync_lag + [lag_ms])[-100:]
                if lag_ms > 3000:                      # chi ghi so do, khong ghi noi dung tin
                    print("[sync-poll] tin den tre %d ms so voi gio Zalo ghi (lech dong ho cung nam trong so nay)" % lag_ms, flush=True)
        except (TypeError, ValueError):
            pass

    def lag_summary(self):
        lag = self.sync_lag
        if not lag:
            return None
        ordered = sorted(lag)
        return {"last": int(lag[-1]), "avg": int(sum(lag) / len(lag)), "p50": int(ordered[len(ordered) // 2]), "max": int(ordered[-1]), "n": len(lag)}

    def _sender_names(self):
        """Map userId -> ten hien thi tu cache danh ba (friends
        rows) — lam giau sender_name cho tin lich su/inbox ma
        khong can goi getUserInfo (body 11140 chua xac minh).
        Node.js lam giau bang getUserInfo (changed_profiles);
        native dot nay dung cache local co san, thieu thi de
        trong chu khong doan."""
        names = {}
        with self._contacts_lock:
            cache = self._contacts_cache
            rows = []
            if cache is not None:
                friends = cache.get("friends") or {}
                rows = friends.get("rows") or []
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                names[str(row["id"])] = row.get("name") or ""
        for k, v in self.profile_names.all_names().items():      # nguoi la: ten tra tu ho so Zalo
            names.setdefault(k, v)
        return names

    @staticmethod
    def _enrich_sender_names(messages, names):
        """Dien sender_name cho tin chua co (tu map danh ba)."""
        for msg in messages:
            if not msg.get("sender_name"):
                msg["sender_name"] = names.get(
                    str(msg.get("sender_id") or ""), "")
        return messages


def _photo_bundle_from_fields(fields):
    """Doc 4 field gom nhom anh tu form sendfile (xem
    chat._validate_photo_bundle): UI gui du 4 field khi batch co
    >1 anh khong-gif. Khong co field nao -> None (anh don, khong
    gom nhom). Co mot vai field -> ValueError (400, khong gui
    khong bundle — gui thieu field thi anh roi rac). So nguyen
    parse o day; validate day du (total >= 2, id trong khoang)
    o chat._validate_photo_bundle."""
    keys = ("groupLayoutId", "totalItemInGroup", "isGroupLayout",
            "idInGroup")
    values = [fields.get(k) for k in keys]
    if all(v is None for v in values):
        return None
    if any(v is None for v in values):
        raise ValueError(
            "thieu truong nhom anh — gui du groupLayoutId, "
            "totalItemInGroup, isGroupLayout, idInGroup")
    try:
        return chat_mod._validate_photo_bundle({
            "groupLayoutId": values[0],
            "totalItemInGroup": int(values[1]),
            "isGroupLayout": int(values[2]),
            "idInGroup": int(values[3])})
    except (TypeError, ValueError) as e:
        raise ValueError("truong nhom anh khong hop le: %s" % e)


def _gp_svc(action, body):
    """Gọi dịch vụ có sẵn của app cho phần bình chọn nhóm; lỗi -> group_polls.PollError."""
    return group_polls_mod._unwrap(services_mod.handle_svc(STATE, action, body))


def _group_poll_summary(p):
    return {"poll_id": p["poll_id"], "question": p["question"], "closed": p["closed"], "anonymous": p["anonymous"], "multi": p["multi"],
            "num_vote": p["num_vote"], "voted": len(group_polls_mod.poll_voters(p)), "created_time": p["created_time"],
            "options": [{"content": o["content"], "votes": o["votes"]} for o in p["options"]]}


def _group_poll_view(gid, op, body):
    """Tuyến /api/group/<gid>/{polls|poll_non_voters|remove_members}: trả (status, obj). PollError -> 400."""
    try:
        group = group_polls_mod.load_group(_gp_svc, gid)
        polls = group_polls_mod.load_polls(_gp_svc, gid)
        if op == "polls":
            return 200, {"group": {"name": group["name"], "members": len(group["members"]), "total": group["total"],
                                   "complete": group["complete"]},
                         "polls": [_group_poll_summary(p) for p in polls]}
        chosen = group_polls_mod.select_polls(polls, body.get("poll_ids"))
        own = str((STATE.session or {}).get("uid") or "")
        res = group_polls_mod.compute_non_voters(group, chosen, own, str(body.get("mode") or "none"), body.get("min_votes") or 1)
        if op == "poll_non_voters":
            return 200, res
        out = group_polls_mod.remove_members(_gp_svc, gid, group, res, body.get("member_ids"), body.get("confirm"),
                                             take_all=body.get("all") is True)
        for r in out["results"]:
            _log_call("poll-kick group=%s member=%s ok=%s" % (gid, r["id"], r["ok"]))
        return 200, {"results": out["results"], "removed": sum(1 for r in out["results"] if r["ok"]), "remaining": out["remaining"]}
    except group_polls_mod.PollError as exc:
        return 400, {"error": str(exc)}


_GROUP_POLL_RE = re.compile(r"^/api/group/(\d{1,30})/(polls|poll_non_voters|remove_members)$")


STATE = AppState(DATA_DIR)


def _link_preview(link):
    """(tiêu đề, mô tả, ảnh) xem trước của liên kết, lấy từ chính Zalo (dịch vụ parse_link) như app thật làm trước khi gửi.
    Zalo từ chối (114) liên kết gửi lên thiếu tiêu đề/mô tả. Không lấy được thì trả rỗng để việc gửi vẫn thử như cũ."""
    try:
        status, obj = services_mod.handle_svc(STATE, "parse_link", {"link": link})
        d = ((obj.get("data") or {}).get("data") or {}) if status == 200 and isinstance(obj, dict) else {}
        return str(d.get("title") or ""), str(d.get("desc") or ""), str(d.get("thumb") or "")
    except Exception:  # noqa: BLE001 - xem trước chỉ là bổ trợ, không được làm hỏng việc gửi
        return "", "", ""


class Handler(outgoing_calls.OutgoingCalls, BaseHTTPRequestHandler):
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

    def _send_bytes(self, data, filename, mime="application/octet-stream",
                    status=200):
        """Tra ve bytes file (tai file den ve — xem /api/file/
        download): Content-Disposition attachment voi ten goc
        (RFC 5987 filename* UTF-8 + filename ASCII du phong)."""
        safe = "".join(ch if ch.isalnum() or ch in "._- "
                       else "_" for ch in (filename or "file"))
        safe = safe.strip() or "file"
        quoted = urllib.parse.quote(filename or "file", safe="")
        disp = ("attachment; filename=\"%s\"; filename*=UTF-8''%s"
                % (safe, quoted))
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", disp)
        self.end_headers()
        self.wfile.write(data)

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
        return STATE.auth.validate_token(self._app_token())

    def _app_token(self):
        """Token phien app trong cookie cua yeu cau ("" neu khong co)."""
        cookies = {}
        for part in (self.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                name, value = part.strip().split("=", 1)
                cookies[name.strip()] = value.strip()
        return cookies.get(app_auth.COOKIE_NAME, "")

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
        if not user:
            return None
        # Ma PIN rieng tu: MAC DINH CHAN. Phien chua mo khoa chi vao duoc danh sach cho phep; moi duong /api/* khac (lich su, cap nhat, SSE,
        # tai tep, cong /api/svc...) deu di qua day nen khong co duong nao bi sot. Handler.handle_one_request doi ngoai le nay thanh HTTP 423.
        gate = getattr(STATE, "privacy", None)
        if gate is not None and gate.enabled:
            path = self.path.split("?", 1)[0]
            if not gate.allowed(path) and not gate.is_unlocked(self._app_token()):
                raise privacy_mod.PrivacyLocked(path)
        return user

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except privacy_mod.PrivacyLocked:
            try:
                self._send_json({"error": "privacy_locked"}, status=423)
                self.wfile.flush()
            except OSError:
                pass

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

    def _serve_call_video_view(self):
        """Xem hình điện thoại gửi sang (WebUI): khung H.264 đã giải mã SRTP + ghép (udp_transport add_video_tap) -> ffmpeg -> MJPEG nhiều phần
        (multipart/x-mixed-replace) cho thẻ <img>. Mỗi người xem một ffmpeg (tối đa VIDEO_VIEWERS_MAX); ngắt kết nối thì dọn tiến trình."""
        qs = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        call_id = _coerce_call_id((qs.get("call_id") or [""])[0])
        if call_id is None:
            live = STATE.calls.snapshot()["active"]
            call_id = int(live["call_id"]) if live is not None else None
        transport = _transport_for_call(call_id) if call_id is not None else None
        if transport is None or not hasattr(transport, "add_video_tap"):
            return self._send_json({"error": "chua_co_hinh"}, status=409)
        if shutil.which("ffmpeg") is None:
            return self._send_json({"error": "thieu_ffmpeg"}, status=503)
        with VIDEO_VIEW_LOCK:
            if VIDEO_VIEW_COUNT[0] >= VIDEO_VIEWERS_MAX:
                return self._send_json({"error": "qua_nhieu_nguoi_xem"}, status=429)
            VIDEO_VIEW_COUNT[0] += 1
        tap = transport.add_video_tap()
        proc = None
        try:
            proc = subprocess.Popen(VIDEO_VIEW_FFMPEG, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            def feed():
                try:
                    while proc.poll() is None:
                        if _transport_for_call(call_id) is not transport:        # cuộc gọi đã kết thúc
                            break
                        try:
                            annexb, _key = tap.get(timeout=1)
                        except queue.Empty:
                            continue
                        proc.stdin.write(annexb)
                except (OSError, ValueError):
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except (OSError, ValueError):
                        pass
            threading.Thread(target=feed, daemon=True, name="video-view-feed").start()
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except OSError:
            pass                            # trình duyệt đóng thẻ: bình thường
        finally:
            transport.remove_video_tap(tap)
            ffmpeg_log_mod.kill_and_reap(proc)
            with VIDEO_VIEW_LOCK:
                VIDEO_VIEW_COUNT[0] -= 1

    def _serve_call_audio_tap(self, token):
        """Nhu /api/call/audio/out nhung doc BAN SAO khung (tap) — dung cho nguoi nghe thu hai (AI trong cuoc goi) ma khong
        tranh khung voi loa."""
        call_id = STATE.audio_tokens.call_for(token)
        if call_id is None:
            return self._send_json({"error": "token_khong_hop_le"}, status=404)
        engine = _engine_for_call(call_id)
        if engine is None or not hasattr(engine, "add_tap"):
            return self._send_json({"error": "chua_co_media"}, status=409)
        tap = engine.add_tap()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def write(chunk):
            self.wfile.write(chunk)
            self.wfile.flush()

        def read():
            try:
                return tap.get_nowait()
            except queue.Empty:
                return None

        def live():
            return (STATE.audio_tokens.call_for(token) is not None and _engine_for_call(call_id) is engine)

        try:
            call_audio_mod.stream_out(engine, write, live, read=read, depth=tap.qsize)
        except OSError:
            pass
        finally:
            engine.remove_tap(tap)

    def _serve_call_audio_out(self, token):
        """Phat lien tuc am thanh ben kia (WAV 16 kHz mono) cho mot thiet
        bi bat ky. Xac thuc bang token cua cuoc goi, khong dung cookie."""
        call_id = STATE.audio_tokens.call_for(token)
        if call_id is None:
            return self._send_json({"error": "token_khong_hop_le"},
                                   status=404)
        engine = _engine_for_call(call_id)
        if engine is None:
            return self._send_json({"error": "chua_co_media"}, status=409)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def write(chunk):
            self.wfile.write(chunk)
            self.wfile.flush()

        def live():
            return (STATE.audio_tokens.call_for(token) is not None
                    and _engine_for_call(call_id) is engine)

        try:
            call_audio_mod.stream_out(engine, write, live)
        except OSError:
            pass            # thiet bi ngat ket noi: binh thuong

    def _handle_call_media(self, path, body):
        """Dieu khien mic / hinh cua cuoc goi dang song.

        /api/call/video          {action: start|stop|status, source, width, height,
                                  fps, bitrate_kbps}
        /api/call/media          {action: start|stop|status, target: mic|video|speaker|both,
                                  mic_url, mic_format, camera_url, speaker_url}  (thieu thi dung mac dinh)
        /api/call/upgrade_video  {camera_url?}  chuyen cuoc goi THOAI sang VIDEO
        """
        snap = STATE.calls.snapshot()
        live = snap["active"]
        call_id = _coerce_call_id(body.get("call_id", ""))
        if call_id is None and live is not None:
            call_id = int(live["call_id"])
        if call_id is None:
            return self._send_json({"ok": False, "error": "no_live_call"})
        action = str(body.get("action") or "start").lower()

        def vstat():
            sd = VIDEO_SENDERS.get(str(call_id))
            return sd.status() if sd else None

        def mstat():
            sd = AUDIO_SENDERS.get(str(call_id))
            return sd.status() if sd else None

        def sstat():
            sd = SPEAKER_SINKS.get(str(call_id))
            return sd.status() if sd else None

        if action not in ("start", "stop", "status"):
            return self._send_json({"error": "action_khong_hop_le"}, status=400)
        if path == "/api/call/video":
            target = "video"
        elif path == "/api/call/media":
            target = str(body.get("target") or "both").lower()
        else:
            target = "upgrade"
        if action == "status":
            return self._send_json({"ok": True, "call_id": call_id,
                                    "video": vstat(), "mic": mstat(),
                                    "speaker": sstat()})
        if action == "stop":
            if target in ("video", "both"):
                if _stop_video(call_id) is not None:
                    video_calls._send_camera_state_async(
                        call_id, _thread_of_call(call_id), False)
            if target in ("mic", "both"):
                _stop_mic(call_id)
            if target in ("speaker", "both"):
                _stop_speaker(call_id)
            return self._send_json({"ok": True, "call_id": call_id,
                                    "video": vstat(), "mic": mstat(),
                                    "speaker": sstat()})
        # Nối thiết bị GIỮA cuộc gọi (HA chuyển máy từ AI sang trực tiếp): bộ thiết bị đưa kèm thành thiết bị riêng của cuộc gọi này (đủ
        # bốn nhóm, nhóm không cài = "off" → không rơi về mặc định); có nhóm nào thì nối nhóm đó.
        if any(k in body for k in _CALL_DEVICE_KEYS):
            _CALL_DEVICES.pop(str(call_id), None)
            _remember_call_devices(call_id, body)
            # "off" = nhóm này không cài: đã ghi vào thiết bị riêng của cuộc gọi (rỗng), nay bỏ khỏi body để không bị coi là URL.
            body = {k: v for k, v in body.items() if not (k in ("mic_url", "speaker_url", "camera_url") and str(v).strip().lower() == "off")}
        if target == "accept_video":
            # Đồng ý lời xin chuyển sang video của người gọi (HA quyết định); camera_url trống = chỉ đồng ý, không gửi hình trong nhà.
            entry = next((c for c in snap["calls"] if str(c["call_id"]) == str(call_id)), None)
            if entry is None or entry["status"] != "answered":
                return self._send_json({"ok": False, "error": "chua_nghe_may"})
            _send_a2v_async(call_id, _thread_of_call(call_id), 2)
            src = str(body.get("camera_url") or "")
            if src:
                try:
                    _start_video(call_id, src)
                except (ValueError, RuntimeError) as exc:
                    return self._send_json({"ok": False, "error": str(exc)[:120]})
            return self._send_json({"ok": True, "call_id": call_id, "video": vstat(), "mic": mstat(), "speaker": sstat()})
        cfg = _devices_for_call(call_id)
        try:
            if target == "upgrade":
                entry = next((c for c in snap["calls"]
                              if str(c["call_id"]) == str(call_id)), None)
                if entry is None or entry["status"] != "answered":
                    return self._send_json({"ok": False,
                                            "error": "chua_nghe_may"})
                _send_a2v_async(call_id, _thread_of_call(call_id), 1)
                src = str(body.get("camera_url") or body.get("source")
                          or cfg["camera_url"] or "test")
                _start_video(call_id, src)
            else:
                if target in ("mic", "both"):
                    src = str(body.get("mic_url")
                              or (body.get("source") if target == "mic" else "")
                              or cfg["mic_url"] or "")
                    if src:
                        _start_mic(call_id, src,
                                   str(body.get("mic_format") or cfg["mic_format"]))
                if target in ("speaker", "both"):
                    spk = str(body.get("speaker_url")
                              or (body.get("source") if target == "speaker" else "")
                              or cfg.get("speaker_url") or "")
                    if spk:
                        if not re.match(r"^https?://\S+$", spk):
                            raise ValueError("speaker_url phai la URL http(s)")
                        _start_speaker(call_id, spk)
                    elif target == "speaker":
                        raise ValueError("chua_co_speaker_url")
                if target in ("video", "both"):
                    src = str(body.get("camera_url") or body.get("source")
                              or cfg["camera_url"] or "")
                    if src or target == "video":
                        params = {k: body[k] for k in
                                  ("width", "height", "fps", "bitrate_kbps")
                                  if k in body}
                        _start_video(call_id, src or "test", params)
        except (ValueError, RuntimeError) as exc:
            return self._send_json({"ok": False, "error": str(exc)[:120]})
        return self._send_json({"ok": True, "call_id": call_id,
                                "video": vstat(), "mic": mstat(),
                                "speaker": sstat()})

    def _handle_call_say(self):
        """POST /api/call/say (multipart: file, call_id?) — phat mot doan am thanh (mp3/wav/ogg... do HA tao bang TTS) len
        cuoc goi DANG NOI qua cung duong mic (thay nguon mic hien tai). Tra ngay khi bat dau phat; nguoi goi poll
        /api/call/media {action: status}: mic.alive=false la phat xong."""
        if self._require_app_login() is None:
            return self._unauthorized()
        if self._require_login() is None:
            return self._send_json({"error": "chua_dang_nhap"}, status=401)
        raw = self._read_raw()
        if len(raw) > SAY_MAX_BYTES + 4096:
            return self._send_json({"error": "am_thanh_qua_lon"}, status=413)
        fields, files = chat_mod.parse_multipart(raw, self.headers.get("Content-Type") or "")
        f = (files or {}).get("file")
        fname, _mime, data = f if f else ("", "", b"")
        if not data:
            return self._send_json({"ok": False, "error": "thieu_file"}, status=400)
        if len(data) > SAY_MAX_BYTES:
            return self._send_json({"error": "am_thanh_qua_lon"}, status=413)
        snap = STATE.calls.snapshot()
        call_id = _coerce_call_id(fields.get("call_id", ""))
        entry = next((c for c in snap["calls"] if call_id is not None and str(c["call_id"]) == str(call_id)), None) \
            if call_id is not None else snap["active"]
        if entry is None or entry["status"] != "answered":
            return self._send_json({"ok": False, "error": "chua_nghe_may"})
        call_id = int(entry["call_id"])
        ext = os.path.splitext(str(fname or ""))[1].lower()
        if not re.match(r"^\.[a-z0-9]{1,5}$", ext):
            ext = ".bin"
        folder = os.path.join(STATE.data_dir, "say")
        try:
            os.makedirs(folder, exist_ok=True)
            _prune_say_files(folder)
            path = os.path.join(folder, "%s-%d%s" % (call_id, int(time.time() * 1000), ext))
            with open(path, "wb") as fh:
                fh.write(data)
            _start_mic(call_id, path, "auto", loop=False, echo_gate=False)   # MOT lan, khong lap, KHONG gate chong vong
        except (ValueError, RuntimeError, OSError) as exc:
            return self._send_json({"ok": False, "error": str(exc)[:120]})
        return self._send_json({"ok": True, "call_id": call_id, "bytes": len(data)})

    def _handle_call_audio_in(self, call_id):
        """Nhan PCM16 16 kHz mono (boi so 640 byte) tu mic cua thiet bi bat
        ky va dua vao cuoc goi. Can dang nhap app."""
        if self._require_app_login() is None:
            return self._unauthorized()
        engine = _engine_for_call(call_id)
        if engine is None:
            return self._send_json({"ok": False, "error": "chua_co_media"},
                                   status=409)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return self._send_json({"ok": False, "error": "thieu_noi_dung"},
                                   status=400)
        if length > call_audio_mod.MAX_IN_BYTES:
            return self._send_json({"ok": False, "error": "qua_lon"},
                                   status=413)
        data = self.rfile.read(length)
        sent, errors, last = call_audio_mod.feed_frames(engine, data)
        return self._send_json({"ok": errors == 0, "frames": sent,
                                "errors": errors, "last_error": last})

    def _require_login(self):
        sess = STATE.session
        if not sess or not sess.get("zpw_sek"):
            return None
        return sess

    # -- routing ---------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/call/audio/tap/"):
            # Ban sao khung cho nguoi nghe thu hai (AI); cung xac thuc bang TOKEN.
            return self._serve_call_audio_tap(path[len("/api/call/audio/tap/"):])
        if path.startswith("/api/call/audio/out/"):
            # Public theo TOKEN (media_player khong co cookie).
            return self._serve_call_audio_out(
                path[len("/api/call/audio/out/"):])
        if path == "/login":
            # The login page itself is public. Already logged in?
            # Back to the app.
            if self._require_app_login() is not None:
                return self._send_redirect("/")
            return self._serve_static("login.html", "text/html")
        if path == "/":
            if self._require_app_login() is None:
                return self._send_redirect("/login")
            return self._serve_static("zalo/index.html", "text/html")
        if path == "/classic":
            # Giao dien cu (giu lai de doi chieu / lui lai neu can).
            if self._require_app_login() is None:
                return self._send_redirect("/login")
            return self._serve_static("app.html", "text/html")
        if path == "/ui/app.css":
            return self._serve_static("zalo/app.css", "text/css")
        if path == "/ui/app.js":
            if self._require_app_login() is None:
                return self._unauthorized()
            return self._serve_static("zalo/app.js", "text/javascript")
        if path == "/app.js":
            if self._require_app_login() is None:
                return self._unauthorized()
            return self._serve_static("app.js", "text/javascript")
        if path == "/style.css":
            # Shared by the login page: public.
            return self._serve_static("style.css", "text/css")
        if path.startswith("/fonts/"):
            # Login page resources: public — NHUNG chi file font
            # that trong static/fonts (H1): realpath phai nam trong
            # FONTS_DIR va duoi .woff2 (toan bo font UI hien dung
            # .woff2, xem style.css). Duong con trong fonts/ duoc
            # phep; moi duong ra ngoai (.., encode, null byte)
            # deu tra 404 chung chung, khong lo noi dung.
            rel = path[len("/fonts/"):]
            resolved = _safe_static_path(rel, FONTS_DIR)
            if (resolved is None
                    or not resolved.lower().endswith(".woff2")):
                return self._send_json({"error": "not_found"},
                                       status=404)
            return self._serve_static_file(resolved, "font/woff2")
        if path == "/api/privacy/status":
            if not self._app_user():
                return self._unauthorized()
            return self._send_json(STATE.privacy.status(self._app_token()))
        if path == "/api/app/status":
            # Public: the login page uses it to redirect when the
            # session is already valid. Never leaks anything else.
            user = self._app_user()
            out = {"logged_in": bool(user), "username": user or ""}
            if user and STATE.auth is not None:
                # Chi lo khi DA dang nhap: trang /login khong duoc biet gi them.
                out["can_change_password"] = not STATE.auth.managed_by_env_hash
            return self._send_json(out)
        if path.startswith("/api/"):
            app_user = self._require_app_login()
            if app_user is None:
                return self._unauthorized()
            return self._api_get(path, app_user)
        return self._send_json({"error": "not_found"}, status=404)

    def _api_get(self, path, app_user):
        if path == "/api/status":
            status = STATE.public_status(app_user)
            status["sync_lag_ms"] = STATE.lag_summary()
            status["keepalive"] = {"opened": _KEEPALIVE_POOL.opened}     # so ket noi poller da mo (it = giu song tot)
            status["receipts"] = {"sent": RECEIPTS.sent, "failed": RECEIPTS.failed, "last_error": RECEIPTS.last_error}
            return self._send_json(status)
        if path == "/api/qr/status":
            return self._send_json(STATE.qr_status())
        if path == "/api/engine/status":
            return self._send_json(engine_seam.SEAM.status())
        if path == "/api/svc/catalog":
            # Danh mục 96 service + trạng thái hỗ trợ: chỉ là mô tả
            # tĩnh, không chứa dữ liệu tài khoản — nhưng vẫn nằm sau
            # cổng đăng nhập app như mọi /api/* khác (xem do_GET).
            return self._send_json(services_mod.catalog_public())
        if path.startswith("/api/stickers/"):
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            from . import stickers as stickers_mod, zca_api as zca_mod
            sub = path[len("/api/stickers/"):]
            qs = urllib.parse.parse_qs(self.path.split("?", 1)[1]
                                       if "?" in self.path else "")
            try:
                svc, ctx = services_mod.make_services(STATE)
                st = stickers_mod.Stickers(svc, ctx)
                if sub == "search":
                    q = (qs.get("q") or [""])[0].strip()
                    if not q:
                        return self._send_json({"ok": False, "error": "thieu q"},
                                               status=400)
                    items = st.search(q)
                elif sub == "recommended":
                    items = st.recommended()
                elif sub.startswith("category/"):
                    items = st.category(sub[len("category/"):])
                else:
                    return self._send_json({"error": "khong co"}, status=404)
            except zca_mod.ZcaManual as m:
                return self._send_json({"ok": False, "error": m.reason}, status=409)
            except (zca_mod.ZcaError, ValueError) as m:
                return self._send_json({"ok": False, "error": str(m)}, status=400)
            except Exception as m:  # noqa: BLE001 - loi Zalo/mang
                return self._send_json({"ok": False, "error": str(m)}, status=502)
            return self._send_json({"ok": True, "items": items})
        if path.startswith("/api/voice2text/"):
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            got = V2T.get(path[len("/api/voice2text/"):])
            if got is None:
                return self._send_json({"ok": True, "done": False})
            return self._send_json({"ok": True, "done": True, **got})
        if path == "/api/call/video/view":
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            return self._serve_call_video_view()
        if path == "/api/calls":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            return self._send_json(_calls_snapshot_with_media())
        if path == "/api/settings/devices":
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            return self._send_json({"ok": True,
                                    "devices": STATE.devices.public()})
        if path == "/api/retention":
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            return self._send_json({"settings": STATE.retention.get(), "usage": STATE.retention.usage(), "last_report": STATE.retention.last_report})
        if path == "/api/history-sync/status":
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            return self._send_json(STATE.history_sync.status())
        # WEBHOOK HOOK (webhooks.py): read the webhook config. Auth is
        # the same _require_login() as /api/calls — the login-app agent
        # owns that check; do NOT open this route without it.
        if path == "/api/webhooks":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            return self._send_json(STATE.webhook_store.load())
        m_gp = _GROUP_POLL_RE.match(path)
        if m_gp and m_gp.group(2) == "polls":
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            status, obj = _group_poll_view(m_gp.group(1), "polls", {})
            return self._send_json(obj, status=status)
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
        # Nhom: GET group/history (11240) that + tin den trong
        # phien (Inbox qua kenh sync) + tin da gui trong phien,
        # ghep theo kieu Node.js (chat.merge_messages: trung khoa
        # thi ban Zalo thang, sap theo ts, cat N tin cuoi).
        # 1-1: KHONG co endpoint HTTPS (ca Node.js cung khong co)
        # — doc tu DB local (message_store: tin den/gui da ghi
        # xuong dia tu khi app bat dau luu) + ghep tin den trong
        # phien (Inbox) + tin da gui trong phien (chat.py). DB
        # trong thi tra thong bao gioi han trung thuc cu.
        # count theo Node.js (routes/api.js): so nguyen 1..1000,
        # ngoai khoang -> 400 (khong clamp lam nhu cu).
        # Mo thread = da doc: xoa unread cua thread do o Inbox.
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
                return self._send_json(
                    {"error": "count phai la so nguyen tu 1 den 1000"},
                    status=400)
            if count < 1 or count > 1000:
                return self._send_json(
                    {"error": "count phai la so nguyen tu 1 den 1000"},
                    status=400)
            try:
                transport = make_transport(sess["zpw_sek"])
                chat = chat_mod.Chat(transport, sess["device_id"],
                                     sess["zpw_enk"])
                if thread_type == "group":
                    result = chat.history_group(thread_id, count)
                    source = "zalo"
                else:
                    # 1-1: KHONG co endpoint HTTPS (ca Node.js cung
                    # khong co) — doc tu DB local (message_store):
                    # tin den/gui da ghi xuong dia tu khi app bat
                    # dau luu. DB trong thi giu thong bao gioi han
                    # trung thuc cu; DB co tin thi bao ro la lich
                    # su CHUA DU (chi tu khi bat dau luu).
                    db_msgs = STATE.message_store.messages_for(
                        thread_type, thread_id, count)
                    if db_msgs:
                        result = {
                            "messages": db_msgs, "has_more": False,
                            "unavailable": False,
                            "notice": chat_mod.HISTORY_USER_DB_PARTIAL,
                        }
                        source = "db+inbox"
                    else:
                        result = chat.history_user_unavailable()
                        source = "inbox+session"
                # Nhom: ngoai ban tuoi cua Zalo + RAM, doc them kho BEN (restart/dung lai container lam RAM trong -> nhom hien trang, 13/11).
                db_extra = (STATE.message_store.messages_for(thread_type, thread_id, count)
                            if thread_type == "group" else [])
                cached = (db_extra
                          + STATE.inbox.messages_for(thread_type, thread_id)
                          + STATE.chat_store.sent_for(thread_type,
                                                      thread_id))
                merged, from_cached = chat_mod.merge_messages(
                    result["messages"], cached, count)
                print("[history] type=%s id=...%s zalo=%d kho=%d ram+gui=%d tron=%d" % (
                    thread_type, str(thread_id)[-4:], len(result.get("messages") or []), len(db_extra),
                    len(cached) - len(db_extra), len(merged)), flush=True)
                if from_cached > 0 and thread_type == "group":
                    source = "zalo+inbox"
                STATE._enrich_sender_names(
                    merged, STATE._sender_names())
                STATE.inbox.mark_read(thread_type, thread_id)
                STATE.message_store.mark_read(thread_type, thread_id)
                result = dict(result)
                result["messages"] = merged
                result["thread_id"] = thread_id
                result["type"] = thread_type
                result["source"] = source
                result["requested"] = count
                result["returned"] = len(merged)
                result["fromCache"] = from_cached
                return self._send_json(result)
            except Exception as e:  # noqa: BLE001
                print("[history] LOI type=%s id=...%s %s: %s" % (thread_type, thread_id[-4:], type(e).__name__, str(e)[:160]), flush=True)
                return self._send_json({"error": str(e)}, status=502)
        # -- INBOX HOOK (sync_poll.Inbox) --
        # GET /api/thread/<id>/updates?type=user|group&after=<epoch>
        # Tin MOI cua thread tu Inbox (chi RAM, khong goi Zalo):
        # UI goi moi 5 giay khi thread dang mo de tin den tu hien
        # ma khong phai tai lai toan bo lich su (tranh 429).
        # after = epoch giay (float); tra tin co time > after.
        # Lay updates cua thread dang mo cung la da doc.
        if path.startswith("/api/thread/") and path.endswith("/updates"):
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            import urllib.parse as _up
            thread_id = path[len("/api/thread/"):-len("/updates")]
            thread_id = _up.unquote(thread_id.strip("/"))
            qs = dict(_up.parse_qsl(_up.urlparse(self.path).query))
            thread_type = qs.get("type") or "user"
            if thread_type not in ("user", "group"):
                return self._send_json({"error": "type phai la user|group"},
                                       status=400)
            try:
                after = float(qs.get("after") or 0)
            except ValueError:
                after = 0.0
            messages = STATE.inbox.since(thread_type, thread_id, after)
            STATE._enrich_sender_names(messages, STATE._sender_names())
            if messages:
                STATE.inbox.mark_read(thread_type, thread_id)
                STATE.message_store.mark_read(thread_type, thread_id)
            return self._send_json({
                "messages": messages,
                "thread_id": thread_id, "type": thread_type,
                "server_time": time.time(),
                "has_new": bool(messages)})
        # GET /api/inbox/summary — moi thread co tin trong Inbox:
        # unread + tin moi nhat (de UI gan huy hieu / xem truoc o
        # thread list). Khong goi Zalo.
        if path in ("/api/conversations", "/api/watch"):
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            # threadId "0"/rong la tin Zalo khong ghi ro doi tac (idTo=0): khong
            # phai hoi thoai that, nhin vao danh sach chi gay roi.
            rows = [r for r in STATE.message_store.threads(limit=300)
                    if r["thread_id"] not in ("", "0")]
            ids = STATE._friend_ids()
            mine = str(sess.get("uid", ""))
            for r in rows:
                r["stranger"] = bool(
                    r["thread_type"] == "user" and ids is not None
                    and r["thread_id"] not in ids and r["thread_id"] != mine)
            # Nguoi la khong co ten trong tin (tin nhap tu lich su khong mang dName): tra ten tu ho so Zalo, nen, luu ben.
            _noname = [r for r in rows if r["stranger"] and not (r.get("name") or "").strip()]
            if _noname:
                STATE.profile_names.ensure([r["thread_id"] for r in _noname])
                for r in _noname:
                    r["name"] = STATE.profile_names.name(r["thread_id"])
            if path == "/api/watch":
                return self._send_json({
                    "ready": ids is not None,
                    "strangers": [r for r in rows
                                  if r["stranger"] and r["incoming_count"] > 0]})
            return self._send_json({
                "threads": rows, "contacts_ready": ids is not None,
                "unread_total": sum(r["unread"] for r in rows)})
        if path == "/api/proxy":
            return self._send_json(STATE.proxy_store.public())
        if path == "/api/security":
            return self._send_json({
                "app_user": app_user,
                "session_hours": STATE.auth.session_hours if STATE.auth else None,
                "sessions": STATE.auth.session_count() if STATE.auth else 0,
                "blocked_ips": STATE.login_limiter.blocked_count(),
                "login_max_fails": STATE.login_limiter.max_fails,
                "password_source": ("hash" if os.environ.get(
                    "ZALO_PC_APP_PASSWORD_HASH") else "env")})
        if path == "/api/events":
            q = STATE.events.subscribe()
            if q is None:
                return self._send_json({"error": "qua_nhieu_ket_noi"},
                                       status=429)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                self.wfile.write(b"retry: 2000\n\n")
                self.wfile.flush()
                while True:
                    try:
                        ev = q.get(timeout=15)
                        self.wfile.write(("event: %s\ndata: %s\n\n" % (
                            ev.get("type", "message"),
                            json.dumps(ev, ensure_ascii=False))).encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except OSError:
                pass  # nguoi xem dong tab
            finally:
                STATE.events.unsubscribe(q)
            return
        if path == "/api/inbox/summary":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            rows = STATE.inbox.summary()
            names = STATE._sender_names()
            for row in rows:
                last = row.get("last") or {}
                if not last.get("sender_name"):
                    last["sender_name"] = names.get(
                        str(last.get("sender_id") or ""), "")
            return self._send_json({"threads": rows})
        # -- FILE INBOX HOOK (file_inbox.py) --
        # GET /api/file/download?thread_type=user|group&thread_id=
        # <id>&msg_id=<id> — tai file den da tai ve dia xuong may
        # user, giu nguyen ten goc (Content-Disposition attachment).
        # Chi phuc vu file trong registry + con ton tai o dia (duong
        # dan lay tu registry, KHONG nhan duong dan tu user — chan
        # path traversal). Chua tai xong -> 404 + status (pending/
        # failed) de UI hien dung.
        if path == "/api/file/download":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            import urllib.parse as _up
            qs = dict(_up.parse_qsl(_up.urlparse(self.path).query))
            thread_type = qs.get("thread_type") or "user"
            thread_id = qs.get("thread_id") or ""
            msg_id = qs.get("msg_id") or ""
            if thread_type not in ("user", "group") \
                    or not thread_id or not msg_id:
                return self._send_json(
                    {"error": "thieu thread_type/thread_id/msg_id"},
                    status=400)
            rec = STATE.file_inbox.find(thread_type, thread_id, msg_id)
            if rec is None:
                return self._send_json(
                    {"error": "file chua tai ve (msg %s)" % msg_id,
                     "status": "pending"}, status=404)
            if rec.get("status") != "downloaded":
                return self._send_json(
                    {"error": "file tai ve that bai: %s"
                     % (rec.get("error") or "khong ro"),
                     "status": rec.get("status") or "failed"},
                    status=404)
            try:
                with open(rec["local_path"], "rb") as fh:
                    data = fh.read()
            except OSError:
                return self._send_json(
                    {"error": "file da tai khong con o dia",
                     "status": "missing"}, status=404)
            return self._send_bytes(data, rec.get("file_name") or "file")
        # GET /api/file/list?thread_type=user|group&thread_id=<id>
        # — file da nhan/tai cua mot thread (de UI gan trang thai
        # tai xuong + nut chuyen tiep vao bong bong tin).
        if path == "/api/file/list":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            import urllib.parse as _up
            qs = dict(_up.parse_qsl(_up.urlparse(self.path).query))
            thread_type = qs.get("thread_type") or "user"
            thread_id = qs.get("thread_id") or ""
            if thread_type not in ("user", "group") or not thread_id:
                return self._send_json(
                    {"error": "thieu thread_type/thread_id"}, status=400)
            files = STATE.file_inbox.list_for_thread(thread_type,
                                                     thread_id)
            return self._send_json({
                "files": [{k: v for k, v in rec.items()
                           if k != "local_path"}
                          for rec in files],
                "thread_id": thread_id, "type": thread_type})
        return self._send_json({"error": "not_found"}, status=404)

    def _chat_client(self, sess):
        """Chat client cho mot phien Zalo (transport mang cookie
        zpw_sek + http_post_multipart cho upload file). Nap
        voice_async registry + timeout cua AppState de send_voice
        doi event ctrl voice_aac_success truoc buoc 2 (loi 114),
        va file_async registry + timeout de send_file doi event
        ctrl file_done truoc buoc 2 (loi 405 sharefile_full)."""
        transport = make_transport(sess["zpw_sek"])
        return chat_mod.Chat(transport, sess["device_id"],
                             sess["zpw_enk"],
                             voice_async=getattr(STATE, "voice_async",
                                                 None),
                             voice_async_timeout=getattr(
                                 STATE, "voice_async_timeout",
                                 chat_mod.VOICE_ASYNC_WAIT_SECONDS),
                             file_async=getattr(STATE, "file_async",
                                                None),
                             file_async_timeout=getattr(
                                 STATE, "file_async_timeout",
                                 chat_mod.FILE_ASYNC_WAIT_SECONDS),
                             # Trang thai kenh live de send_file /
                             # send_voice bao ro nguyen nhan + cach
                             # sua khi kenh ctrl xuong (thay vi chi
                             # "kenh ctrl chua chay").
                             ctrl_status=lambda: {
                                 "ctrl": STATE.ctrl_status(),
                                 "sync": STATE.sync_status(),
                                 "sync_error": STATE.sync_error,
                             })

    def _read_raw(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        return self.rfile.read(length) if length else b""

    def _handle_thread_post(self, path):
        """-- CHAT HOOK (module chat.py; diem moc duy nhat o do_POST) --
        POST /api/thread/<id>/send | sendfile | sendvoice | typing
        | seen | sendlink. Tat ca can dang nhap app TRUOC (cong
        _require_app_login, giong moi /api/* khac — H2: nhanh nay
        tung re truoc cong app o do_POST nen chi kiem phien Zalo)
        roi moi can _require_login (phien Zalo). sendfile/sendvoice
        la multipart (doc raw, khong doc JSON nhu cac POST khac).
        sendlink gui link (11286/11193) qua chat.send_link."""
        if self._require_app_login() is None:
            return self._unauthorized()
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
        if action in ("send", "typing", "seen", "sendlink", "sendvideo"):
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
            recall_after = recall_mod.parse_after(body["_fields"].get("recall_after") if "_fields" in body else body.get("recall_after"))
        except ValueError as exc:
            return self._send_json({"error": str(exc)}, status=400)
        try:
            chat = self._chat_client(sess)
            if action == "send":
                raw_msg = body.get("message") or ""
                styles = None
                fmt = str(body.get("format") or "plain").strip().lower()
                auto_emoji = str(body.get("auto_emoji") or "").strip().lower() \
                    not in ("", "0", "false", "off", "no", "none")
                style_in, ai_used = body.get("style"), False
                if body.get("ai_markup") and fmt in ("plain", "markdown") \
                        and not body.get("styles"):
                    # «auto» theo ngu canh: AI (qua tich hop HA) da danh dau
                    # dinh dang + emoji; chi nhan khi chu goc khong bi doi.
                    try:
                        ai_used, raw_msg, fmt, style_in, auto_emoji = \
                            rich_text.use_ai_markup(
                                raw_msg, body.get("ai_markup"), style_in,
                                auto_emoji, fmt == "markdown")
                    except ValueError as exc:
                        return self._send_json({"error": str(exc)},
                                               status=400)
                if fmt != "plain" or body.get("auto_emphasis") \
                        or body.get("styles") or body.get("emoji") \
                        or body.get("zalo_emoji") or style_in \
                        or auto_emoji:
                    # Dinh dang chu: markdown nhe / tu nhan manh so bang mau /
                    # styles tu tinh (rich_text.py). Sai tham so -> 400 ro rang,
                    # khong gui mu (Zalo im lang bo qua ma style la).
                    try:
                        message, styles = rich_text.render(
                            raw_msg, fmt,
                            rich_text.normalize_emphasis(
                                body.get("auto_emphasis")),
                            body.get("styles"), body.get("emoji"),
                            auto_emoji, body.get("zalo_emoji"),
                            style_in)
                    except ValueError as exc:
                        return self._send_json({"error": str(exc)},
                                               status=400)
                else:
                    message = raw_msg.strip()
                if not message.strip():
                    return self._send_json({"error": "message rong"},
                                           status=400)
                try:
                    ttl = int(body.get("ttl") or 0)
                except (TypeError, ValueError):
                    ttl = 0
                try:
                    res = chat.send_text(thread_type, thread_id, message,
                                         ttl=ttl, styles=styles,
                                         mentions=body.get("mentions"))
                except ValueError as exc:               # mention sai (khong thay @ten / vuot do dai): bao ro, khong gui mu
                    return self._send_json({"error": str(exc)}, status=400)
                local = STATE.chat_store.local_message(
                    thread_type, thread_id, "text", text=message,
                    client_id=res["client_id"])
                STATE.chat_store.record_sent(thread_type, thread_id,
                                             local)
                STATE.message_store.record(thread_type, thread_id,
                                           local)
                return self._send_json({"ok": True, "data": res["data"],
                                        "message": local,
                                        "recall_at": _schedule_recall(thread_type, thread_id, res, recall_after),
                                        "ai_style": ai_used})
            if action == "sendlink":
                link = (body.get("link") or "").strip()
                if not link:
                    return self._send_json({"error": "link rong"},
                                           status=400)
                try:
                    ttl = int(body.get("ttl") or 0)
                except (TypeError, ValueError):
                    ttl = 0
                title = body.get("title") or ""
                desc = body.get("desc") or ""
                thumb = body.get("thumbnail") or body.get("thumb") or ""
                if not (title or desc):
                    title, desc, thumb_pv = _link_preview(link)
                    thumb = thumb or thumb_pv
                res = chat.send_link(
                    thread_type, thread_id, link,
                    message=body.get("message") or "",
                    title=title, desc=desc, thumb=thumb, ttl=ttl)
                local = STATE.chat_store.local_message(
                    thread_type, thread_id, "text",
                    text=body.get("message") or link,
                    client_id=res["client_id"])
                STATE.chat_store.record_sent(thread_type, thread_id,
                                             local)
                STATE.message_store.record(thread_type, thread_id,
                                           local)
                return self._send_json({"ok": True, "data": res["data"],
                                        "message": local,
                                        "recall_at": _schedule_recall(thread_type, thread_id, res, recall_after)})
            if action == "sendvideo":
                # Video THAT (khung phat duoc), khong phai tep dinh kem: gui DIA CHI video + anh bia bang forward msgType 5 (zca-js sendVideo / zalo_bot
                # cu). May chu Zalo tu tai ve roi luu lai nen dia chi phai cong khai (HA cap dia chi cho tep trong www / media).
                video_url = str(body.get("video_url") or "").strip()
                if not video_url.lower().startswith(("http://", "https://")):
                    return self._send_json({"error": "video_url phai la dia chi http(s) cong khai ma Zalo tai duoc"}, status=400)

                def _num(key):
                    try:
                        return max(0, int(float(body.get(key) or 0)))
                    except (TypeError, ValueError):
                        return 0
                width, height, duration = _num("width"), _num("height"), _num("duration")        # duration: mili giay
                if not (width and height and duration):
                    probed = video_probe_mod.probe_video(video_url)                                # thieu thi do bang ffprobe, do hong -> mac dinh
                    if not (width and height):
                        width, height = probed.get("width", 0), probed.get("height", 0)
                    duration = duration or probed.get("duration_ms", 0)
                caption = str(body.get("message") or "")
                print("[sendvideo] thread=%s %sx%s %dms" % (thread_id, width or "?", height or "?", duration), flush=True)
                try:
                    res = chat.send_video(thread_type, thread_id, video_url, body.get("thumbnail_url") or "", duration, width, height,
                                          caption, _num("ttl") or STATE.conv_ttl.get(thread_id))
                except ValueError as exc:
                    return self._send_json({"error": str(exc)}, status=400)
                local = STATE.chat_store.local_message(thread_type, thread_id, "video", text=caption, file_name="video",
                                                       client_id=res["client_id"])
                STATE.chat_store.record_sent(thread_type, thread_id, local)
                STATE.message_store.record(thread_type, thread_id, local)
                return self._send_json({"ok": True, "data": res["data"], "message": local,
                                        "recall_at": _schedule_recall(thread_type, thread_id, res, recall_after),
                                        "video": {"width": width, "height": height, "duration_ms": duration}})
            if action == "typing":
                data = chat.send_typing(thread_type, thread_id)
                return self._send_json({"ok": True, "data": data})
            if action == "seen":
                msg_ids = body.get("msg_ids") or []
                data = chat.mark_seen(thread_type, thread_id, msg_ids, store=STATE.message_store, own_uid=sess.get("uid", ""))
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
                # Phan loai lai theo luat Node.js (chi jpg/jpeg/png/
                # webp moi la anh — gif/heic/bmp/... la tep dinh
                # kem), roi kiem tra truoc khi goi Zalo: ten thieu /
                # file rong / anh qua lon / anh khong that -> 400 voi
                # loi ro rang thay vi day sang Zalo roi moi loi (hoac
                # im). Gioi han file hieu luc o day la 100 MB (guard
                # chung tren, cung bao ve sendvoice) — chat hon cap
                # 150 MB cua sendFile Node.js, huong chat (an toan
                # hon); gioi han that cua Zalo theo phien
                # (max_size_share_file_v3) chua lan duoc.
                kind = chat_mod.effective_kind(
                    fields.get("kind") or "file", filename, mime)
                # Log ra stdout (docker logs): app khong co F12 nen
                # lan sau dinh kem loi la co du kien ngay (thread,
                # kind, size, ket qua/loi) ma khong can mo trinh
                # duyet. Chi ghi size, khong ghi ten file/noi dung.
                print("[sendfile] thread=%s kind=%s size=%d"
                      % (thread_id, kind, len(data_bytes)), flush=True)
                try:
                    chat_mod.validate_attachment(kind, filename, mime,
                                                 data_bytes)
                except ValueError as e:
                    print("[sendfile] thread=%s kind=%s size=%d -> loi: %s"
                          % (thread_id, kind, len(data_bytes), e),
                          flush=True)
                    return self._send_json({"error": str(e)}, status=400)
                try:
                    try:                  # ttl (mili giay) do nguoi goi dat (zalo_bot cu); khong co thi theo cai dat tu xoa cua hoi thoai
                        ttl_eff = max(0, int(float(fields.get("ttl") or 0))) or STATE.conv_ttl.get(thread_id)
                    except (TypeError, ValueError):
                        ttl_eff = STATE.conv_ttl.get(thread_id)
                    if kind == "photo":
                        try:
                            width = int(fields.get("width") or 0)
                            height = int(fields.get("height") or 0)
                        except ValueError:
                            width, height = 0, 0
                        if not (width and height):          # nguoi goi khong khai (dich vu HA gui tep tho): do tu chinh anh, khong thi Zalo xep o vuong cat
                            width, height = image_size_mod.image_size(data_bytes)
                        # Gom nhom anh: UI gui du 4 field khi batch
                        # co >1 anh khong-gif (xem
                        # _photo_bundle_from_fields); thieu/sai ->
                        # ValueError -> 400 o except duoi, khong
                        # gui khong bundle.
                        bundle = _photo_bundle_from_fields(fields)
                        # Chu thich: Zalo that gui desc = chu cua nguoi dung (zca-js sendMessage `desc: msg`; bundle _sendPhoto
                        # `desc: title || ""`). Rong = anh khong chu thich. Gioi han 4000 ky tu nhu o nhap tin.
                        caption_text = str(fields.get("desc") or "").strip()[:4000]
                        res = chat.send_photo(thread_type, thread_id,
                                              filename, data_bytes, mime,
                                              width, height,
                                              desc=caption_text,
                                              photo_bundle=bundle,
                                              ttl=ttl_eff)
                        local_kind = "photo"
                    else:
                        res = chat.send_file(thread_type, thread_id,
                                             filename, data_bytes, mime,
                                             ttl=ttl_eff)
                        caption_text = ""
                        local_kind = "file"
                except ValueError as e:
                    # Phong thu them (validate trong chat.send_*):
                    # loi kiem tra van la 400, khong phai 502.
                    print("[sendfile] thread=%s kind=%s size=%d -> loi: %s"
                          % (thread_id, kind, len(data_bytes), e),
                          flush=True)
                    return self._send_json({"error": str(e)}, status=400)
                print("[sendfile] thread=%s kind=%s size=%d -> ok client_id=%s"
                      % (thread_id, kind, len(data_bytes),
                         res["client_id"]), flush=True)
                local = STATE.chat_store.local_message(
                    thread_type, thread_id, local_kind,
                    text=(caption_text or filename), file_name=filename,
                    client_id=res["client_id"])
                STATE.chat_store.record_sent(thread_type, thread_id,
                                             local)
                STATE.message_store.record(thread_type, thread_id,
                                           local)
                return self._send_json({"ok": True, "data": res["data"],
                                        "message": local,
                                        "recall_at": _schedule_recall(thread_type, thread_id, res, recall_after)})
            # sendvoice: file ghi am cua trinh duyet (MediaRecorder) hoac TTS.
            # Chrome cho webm/opus, Safari cho mp4/aac: doi sang AAC o
            # server (ensure_voice_aac), roi chat.send_voice tai .aac len
            # NHU TEP THUONG (asyncfile/upload + event file_done) va gui bang
            # forward msgType 3 — dung cach zalo cu (zalo_bot voiceAac.js +
            # zca-js sendVoice); duong cu voice/upload 12060/12063 bi Zalo
            # tra 114 (do thay 10/11/2026). Khong co URL thi KHONG gui mu.
            # Doi sang AAC:
            # day TRUOC khi gui, theo dung cach Node.js lam
            # (zalobot voiceAac.js: ffmpeg server-side, mono 16 kHz
            # 64 kbps, timeout 60 s) — Y HET tham so, khong con lech
            # codec; xem voice_transcode.py. File da la AAC thi gui
            # thang, khong ton ffmpeg. Chuyen doi that bai -> loi ro
            # cho UI, KHONG gui file goc va KHONG lam rot ban ghi am
            # lang le. (Duong truc tiep voicemp3/sendmp3 cu bat MP3
            # va tra 133 — da bo vi bundle khong goi sendVoice.)
            try:
                aac_bytes, aac_name, aac_mime, converted = (
                    voice_mod.ensure_voice_aac(
                        filename, mime, data_bytes))
            except voice_mod.VoiceTranscodeError as e:
                return self._send_json(
                    {"error": "khong_chuyen_duoc_sang_aac: %s" % e},
                    status=502)
            res = chat.send_voice(thread_type, thread_id, aac_name,
                                  aac_bytes, aac_mime, ttl=STATE.conv_ttl.get(thread_id))
            local = STATE.chat_store.local_message(
                thread_type, thread_id, "voice", text=aac_name,
                file_name=aac_name, client_id=res["client_id"])
            STATE.chat_store.record_sent(thread_type, thread_id, local)
            STATE.message_store.record(thread_type, thread_id, local)
            return self._send_json({"ok": True, "data": res["data"],
                                    "message": local,
                                    "recall_at": _schedule_recall(thread_type, thread_id, res, recall_after),
                                    "voice_url": res.get("voice_url"),
                                    "converted_to_aac": converted,
                                    "note": "Thu am tai trinh duyet, "
                                    "da chuyen sang AAC (ffmpeg, mono "
                                    "16 kHz 64 kbps ADTS) truoc khi gui "
                                    "qua duong hai buoc (upload 12060/"
                                    "12063 + asyncfile/msg); khong phai "
                                    "ghi am native cua Zalo PC."})
        except Exception as e:  # noqa: BLE001
            if action == "sendfile":
                print("[sendfile] thread=%s -> loi: %s"
                      % (thread_id, e), flush=True)
            return self._send_json({"error": str(e)}, status=502)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        # CHAT HOOK: route /api/thread/* doc o _handle_thread_post
        # (multipart thi doc raw, khong doc JSON truoc). Dang nhap
        # app kiem tra ngay dau _handle_thread_post (H2) — nhanh
        # nay phai o truoc cong /api/* chung vi no doc body rieng.
        if path.startswith("/api/thread/"):
            return self._handle_thread_post(path)
        # Phat giong noi (TTS cua HA) len cuoc goi dang song: multipart, doc raw (khong doc JSON truoc).
        if path == "/api/call/say":
            return self._handle_call_say()
        # Am thanh mic vao cuoc goi: body la PCM tho, khong phai JSON.
        if path.startswith("/api/call/audio/in/"):
            return self._handle_call_audio_in(
                path[len("/api/call/audio/in/"):])
        # /api/svc/* multipart (doi avatar): doc raw o _api_post,
        # khong doc JSON truoc (giong /api/thread/*).
        if path.startswith("/api/svc/") and "multipart/form-data" in (
                self.headers.get("Content-Type") or ""):
            body = {}
        else:
            body = self._read_json()
        if path in ("/api/privacy/unlock", "/api/privacy/lock"):
            if not self._app_user():
                return self._unauthorized()
            token = self._app_token()
            if path.endswith("/lock"):
                STATE.privacy.lock(token)
                return self._send_json({"ok": True, **STATE.privacy.status(token)})
            ok, why = STATE.privacy.unlock(token, body.get("pin"), self.client_address[0])
            if ok:
                STATE.health.record("note", "privacy_unlocked")
                return self._send_json({"ok": True, **STATE.privacy.status(token)})
            code = 429 if why == "qua_nhieu_lan_sai" else 400 if why == "chua_bat" else 401
            return self._send_json({"error": why}, status=code)
        if path == "/api/app/login":
            # Public. One generic failure for a wrong user OR a wrong
            # password — never say which one exists.
            if STATE.auth is None:
                return self._send_json(
                    {"error": "app_chua_cau_hinh"}, status=503)
            ip = self.client_address[0]
            if STATE.login_limiter.blocked(ip):
                return self._send_json(
                    {"error": "qua_nhieu_lan_sai", "retry_after_seconds": 900},
                    status=429)
            if STATE.auth.verify(body.get("username", ""),
                                 body.get("password", "")):
                STATE.login_limiter.reset(ip)
                token, expires = STATE.auth.create_session(
                    body.get("username", ""))
                max_age = max(0, int(expires - time.time()))
                return self._send_json(
                    {"ok": True, "username": body.get("username", "")},
                    extra_headers=[("Set-Cookie",
                                    app_auth.cookie_header(token, max_age))])
            STATE.login_limiter.fail(ip)
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

    def _cookie_token(self):
        cookies = {}
        for part in (self.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                name, value = part.strip().split("=", 1)
                cookies[name.strip()] = value.strip()
        return cookies.get(app_auth.COOKIE_NAME, "")

    def _revoke_app_token(self):
        if STATE.auth is None:
            return
        STATE.auth.revoke_token(self._cookie_token())


    def _api_post(self, path, body, app_user):
        if path == "/api/app/password":
            # Doi mat khau app tu WebUI. Can phien dang nhap + mat khau cu; dung chung
            # bo han che sai mat khau voi /api/app/login (theo IP). Thanh cong thi
            # thu hoi moi phien KHAC cua tai khoan.
            if STATE.auth is None:
                return self._send_json({"error": "app_chua_cau_hinh"},
                                       status=503)
            ip = self.client_address[0]
            if STATE.login_limiter.blocked(ip):
                return self._send_json(
                    {"error": "qua_nhieu_lan_sai", "retry_after_seconds": 900},
                    status=429)
            try:
                revoked = STATE.auth.change_password(
                    body.get("old_password"), body.get("new_password"),
                    keep_token=self._cookie_token())
            except app_auth.PasswordChangeError as exc:
                if exc.code == "sai_mat_khau_cu":
                    STATE.login_limiter.fail(ip)
                    status = 403
                elif exc.code == "managed_by_env":
                    status = 409
                else:
                    status = 400
                return self._send_json({"ok": False, "error": exc.code},
                                       status=status)
            STATE.login_limiter.reset(ip)
            _log_call("app password changed (other sessions revoked: %d)"
                      % revoked)
            return self._send_json({"ok": True,
                                    "other_sessions_revoked": revoked})
        m_gp = _GROUP_POLL_RE.match(path)
        if m_gp and m_gp.group(2) in ("poll_non_voters", "remove_members"):
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            status, obj = _group_poll_view(m_gp.group(1), m_gp.group(2), body or {})
            return self._send_json(obj, status=status)
        if path in ("/api/retention", "/api/retention/run"):
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            try:
                if path.endswith("/run"):
                    report = STATE.retention.run()
                else:
                    STATE.retention.update(body if isinstance(body, dict) else {})
                    report = None
            except retention_mod.RetentionError as e:
                return self._send_json({"ok": False, "error": str(e)}, status=400)
            return self._send_json({"ok": True, "settings": STATE.retention.get(), "usage": STATE.retention.usage(), "report": report})
        if path in ("/api/history-sync/start", "/api/history-sync/cancel", "/api/history-sync/retry", "/api/history-sync/import"):
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            try:
                if path.endswith("/start"):
                    STATE.history_sync.start()
                elif path.endswith("/retry"):
                    STATE.history_sync.retry()
                elif path.endswith("/import"):
                    STATE.start_history_import()
                else:
                    STATE.history_sync.cancel()
            except Exception as e:  # noqa: BLE001 - tra ly do cho UI
                return self._send_json({"ok": False, "error": str(e)[:200]}, status=400)
            return self._send_json({"ok": True, "status": STATE.history_sync.status()})
        if path == "/api/qr/new":
            # body {"client": "web"|"pc"}: kiểu đăng nhập người dùng chọn (không gửi = giữ kiểu hiện tại).
            _c = (body if isinstance(body, dict) else {}).get("client")
            STATE.start_qr(_c, restart=bool(_c))     # body: do_POST đã đọc sẵn, KHÔNG đọc rfile lần hai (sẽ treo)     # body: do_POST đã đọc sẵn, KHÔNG đọc rfile lần hai (sẽ treo)
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
            if action == "undo_message" and status == 200 and isinstance(obj, dict) and not obj.get("error") and isinstance(body, dict):
                STATE._apply_recall("group" if body.get("type") == "group" else "user", str(body.get("thread_id") or ""),
                                    body.get("msg_id"), body.get("cli_msg_id"))
            return self._send_json(obj, status=status)
        if path == "/api/sync/retry":
            # Thu mo lai kenh sync cho phien hien tai (nut "Thu ket
            # noi lai" o UI khi sync dang xuong). Gioi han 1 lan /
            # 30 giay de khong doi getLoginInfo lien tuc; bi da
            # (kicked_out) thi khong thu lai — server da bao dung.
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            if STATE.sync_status() == "kicked_out":
                return self._send_json(
                    {"ok": False, "sync": "kicked_out",
                     "sync_error": STATE.sync_error})
            now = time.time()
            if now - STATE._sync_last_retry_at \
                    < SYNC_RETRY_COOLDOWN_SECONDS:
                wait = int(SYNC_RETRY_COOLDOWN_SECONDS
                           - (now - STATE._sync_last_retry_at)) + 1
                return self._send_json(
                    {"ok": False, "sync": STATE.sync_status(),
                     "sync_error": STATE.sync_error,
                     "retry_after_seconds": wait}, status=429)
            STATE._sync_last_retry_at = now
            STATE.start_sync()
            st = STATE.sync_status()
            return self._send_json(
                {"ok": st == "running", "sync": st,
                 "sync_error": STATE.sync_error})
        if path == "/api/file/forward":
            # Gui lai file da nhan sang thread khac, GIU NGUYEN
            # TEN FILE GOC (yeu cau cua user 08/11): doc bytes tu
            # dia (chi file trong registry) roi gui qua duong
            # sendFileByChunkV2 da co (chat.send_file) voi
            # fileName = ten goc. Body JSON: {thread_type,
            # thread_id, msg_id, to_thread_type, to_thread_id}.
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            src_type = body.get("thread_type") or "user"
            src_id = str(body.get("thread_id") or "")
            msg_id = str(body.get("msg_id") or "")
            to_type = body.get("to_thread_type") or "user"
            to_id = str(body.get("to_thread_id") or "")
            if src_type not in ("user", "group") \
                    or to_type not in ("user", "group") \
                    or not src_id or not msg_id or not to_id:
                return self._send_json(
                    {"error": "thieu thread_id/msg_id/to_thread_id"},
                    status=400)
            try:
                rec, data = STATE.file_inbox.read_local(
                    src_type, src_id, msg_id)
            except file_inbox_mod.FileDownloadError as e:
                return self._send_json({"error": str(e)}, status=404)
            try:
                chat = self._chat_client(sess)
                res = chat.send_file(to_type, to_id,
                                     rec["file_name"], data)
            except Exception as e:  # noqa: BLE001 - loi Zalo -> 502
                return self._send_json({"error": str(e)}, status=502)
            STATE.chat_store.record_sent(
                to_type, to_id,
                STATE.chat_store.local_message(
                    to_type, to_id, "file",
                    text=rec["file_name"], file_name=rec["file_name"],
                    client_id=str(res.get("client_id") or "")))
            return self._send_json({
                "ok": True, "file_name": rec["file_name"],
                "size_bytes": len(data),
                "client_id": res.get("client_id"),
                "to_thread_id": to_id, "to_thread_type": to_type})
        if path == "/api/file/redownload":
            # Tai lai file den (khi lan dau loi / file mat khoi
            # dia): lay URL goc tu registry (da luu luc nhan tin)
            # roi tai lai bang FileInbox. Body JSON: {thread_type,
            # thread_id, msg_id}.
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            thread_type = body.get("thread_type") or "user"
            thread_id = str(body.get("thread_id") or "")
            msg_id = str(body.get("msg_id") or "")
            if thread_type not in ("user", "group") \
                    or not thread_id or not msg_id:
                return self._send_json(
                    {"error": "thieu thread_type/thread_id/msg_id"},
                    status=400)
            rec = STATE.file_inbox.registry.find(
                thread_type, thread_id, msg_id)
            if rec is None or not rec.get("file_url"):
                return self._send_json(
                    {"error": "khong co URL goc de tai lai (msg %s)"
                     % msg_id}, status=404)
            msg = {"id": msg_id,
                   "sender_id": rec.get("sender_id") or "",
                   "sender_name": rec.get("sender_name") or "",
                   "file_name": rec.get("file_name") or "",
                   "file_url": rec.get("file_url") or "",
                   "file_size": rec.get("expected_size"),
                   "file_checksum": rec.get("checksum") or None}
            try:
                new_rec = STATE.file_inbox.download(
                    msg, thread_type, thread_id)
            except file_inbox_mod.FileDownloadError as e:
                return self._send_json({"error": str(e)}, status=502)
            return self._send_json({"ok": True,
                                    "file_name": new_rec["file_name"],
                                    "size_bytes": new_rec["size_bytes"],
                                    "status": new_rec["status"]})
        if path == "/api/zalo/logout":
            # Chi dang xuat ZALO (xoa phien Zalo, ve man hinh QR); GIU phien app (user/mat khau) — nut «Dang xuat Zalo» trong
            # cai dat. /api/logout ben duoi la dang xuat TOAN BO (ca app) roi ve /login.
            STATE.logout()
            return self._send_json({"ok": True})
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
            return self._api_call_request(body)
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
            # the Zalo signal (best-effort); a failure is recorded
            # in the log entry's detail and returned, never leaves
            # the call stuck. The response is always ok when a call
            # was ended locally, even if Zalo rejected the signal.
            # The wire signal is chosen by _terminate_call: an
            # UNANSWERED 1-1 call ends with CANCEL (11305), not
            # endcall (11306) — see _send_end_signal. The response
            # keeps "zalo_endcall_ok" (the UI and the old tests read
            # it: it means "the Zalo-side termination signal was
            # accepted") and adds "zalo_signal" naming the signal.
            # Resolve the target: the body's call_id (coerced to a
            # uint32 number — the detail view builds it from the
            # log record, where it is a STRING; sending it as a
            # string can draw inner 114, same lesson as
            # requestcall §7k), else the live call (there is at
            # most one; the End button's intent is unambiguous).
            raw_id = body.get("call_id", "")
            call_id = _coerce_call_id(raw_id)
            snap = STATE.calls.snapshot()
            live = snap["active"]
            target_id = None
            if call_id is not None:
                for c in snap["calls"]:
                    if (str(c["call_id"]) == str(call_id)
                            and c["status"] == "sent"):
                        target_id = call_id
                        break
            if target_id is None and live is not None:
                target_id = int(live["call_id"])
            if target_id is None:
                _log_call("end call_id=None reason=no_live_call")
                return self._send_json(
                    {"ok": True, "ended_call_id": None,
                     "zalo_endcall_ok": False,
                     "zalo_error": "no_live_call"})
            ended, signal, zalo_ok, zalo_error, data = _terminate_call(
                target_id, "user_end", sess,
                body.get("data"), body.get("partners"))
            if ended is None:
                _log_call("end call_id=None reason=no_live_call")
                return self._send_json(
                    {"ok": True, "ended_call_id": None,
                     "zalo_endcall_ok": False,
                     "zalo_error": "no_live_call"})
            return self._send_json(
                {"ok": True, "ended_call_id": int(ended["call_id"]),
                 "zalo_signal": signal,
                 "zalo_endcall_ok": zalo_ok, "zalo_error": zalo_error,
                 "data": data})
        if path == "/api/settings/devices":
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            try:
                STATE.devices.update(body)
            except ValueError as exc:
                return self._send_json({"ok": False, "error": str(exc)[:80]},
                                       status=400)
            return self._send_json({"ok": True,
                                    "devices": STATE.devices.public()})
        if path in ("/api/call/video", "/api/call/media",
                    "/api/call/upgrade_video"):
            if self._require_login() is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            return self._handle_call_media(path, body)
        if path == "/api/call/answered":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            # Mark the live call answered (the peer picked up).
            # Callers: a future sync-push handler (the server
            # reports "da tra loi" on the sync channel), tests, or
            # a manual trigger. The transport's first-media hook
            # calls _mark_answered directly instead. Target
            # resolution mirrors /api/call/end: the body's call_id,
            # else the live call (there is at most one). Idempotent:
            # marking an already-answered call answers ok again.
            raw_id = body.get("call_id", "")
            call_id = _coerce_call_id(raw_id)
            snap = STATE.calls.snapshot()
            live = snap["active"]
            target_id = None
            if call_id is not None:
                for c in snap["calls"]:
                    if (str(c["call_id"]) == str(call_id)
                            and c["status"] in ("sent", "answered")):
                        target_id = call_id
                        break
            if target_id is None and live is not None:
                target_id = int(live["call_id"])
            if target_id is None:
                _log_call("answered call_id=None reason=no_live_call")
                return self._send_json({"ok": False,
                                        "error": "no_live_call"})
            entry = _mark_answered(target_id, "api")
            if entry is None:
                return self._send_json({"ok": False,
                                        "error": "no_live_call"})
            return self._send_json(
                {"ok": True, "call_id": int(entry["call_id"]),
                 "status": entry["status"],
                 "answered_at": entry.get("answered_at"),
                 "answer_source": entry.get("answer_source", "")})
        if path == "/api/voice2text":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"}, status=401)
            url = str((body or {}).get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                return self._send_json(
                    {"ok": False, "error": "can url tep ghi am (http/https)"},
                    status=400)
            try:
                wait = max(0.0, min(60.0, float((body or {}).get("wait") or 0)))
            except (TypeError, ValueError):
                wait = 0.0
            code, res = services_mod.handle_svc(
                STATE, "voice_to_text", {"voiceUrl": url})
            if code != 200:
                return self._send_json(res, status=code)
            req_id = _find_req_id(res.get("data"))
            if not req_id:
                return self._send_json(
                    {"ok": False, "error": "Zalo khong tra req_id"}, status=502)
            got = V2T.wait(req_id, wait) if wait else V2T.get(req_id)
            out = {"ok": True, "req_id": req_id, "done": got is not None}
            if got is not None:
                out.update(got)
            return self._send_json(out)
        if path == "/api/call/answer":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            return self._send_json(_answer_incoming(sess, body))
        if path == "/api/call/reject":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            # Reject an INCOMING call (we are the callee). zca-js
            # rejectIncomingCall (1-1): cancelVoiceCall (11305)
            # AND endVoiceCall (11306, status 3), both best-effort.
            # LOCAL-FIRST like /api/call/end: the entry is ended
            # locally first, then the signals are attempted.
            raw_id = body.get("call_id", "")
            call_id = _coerce_call_id(raw_id)
            snap = STATE.calls.snapshot()
            live = snap["active"]
            target = None
            if call_id is not None:
                for c in snap["calls"]:
                    if (str(c["call_id"]) == str(call_id)
                            and c["status"] == "incoming"):
                        target = c
                        break
            if target is None and live is not None \
                    and live["status"] == "incoming":
                target = live
            if target is None:
                _log_call("reject call_id=%s reason=no_incoming_call"
                          % raw_id)
                return self._send_json(
                    {"ok": False, "error": "no_incoming_call"})
            call_id = int(target["call_id"])
            caller_id = target["thread_id"]
            entry = STATE.calls.record_end(call_id, "user_rejected")
            if entry is not None:
                _cleanup_call_media(entry)
            zalo_ok, zalo_error = _reject_signals(sess, caller_id, call_id)
            if entry is not None:
                _logendcall_async(entry, status=160)
                webhooks_mod.dispatch_call_event(
                    STATE.webhook_dispatcher, entry,
                    (STATE.session or {}).get("uid", ""))
                _log_call("reject call_id=%s zalo_ok=%s%s"
                          % (call_id, zalo_ok,
                             (" zalo_error=" + zalo_error)
                             if zalo_error else ""))
            return self._send_json(
                {"ok": True, "ended_call_id": call_id,
                 "zalo_ok": zalo_ok, "zalo_error": zalo_error})
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
        if path == "/api/proxy":
            action = body.get("action")
            try:
                if action == "add":
                    STATE.proxy_store.add(body.get("url", ""),
                                          body.get("name", ""))
                elif action == "remove":
                    STATE.proxy_store.remove(str(body.get("id", "")))
                elif action == "activate":
                    STATE.proxy_store.set_active(str(body.get("id", "")))
                elif action == "deactivate":
                    STATE.proxy_store.set_active("")
                elif action == "test":
                    url = (STATE.proxy_store.url_of(str(body.get("id", "")))
                           or body.get("url", ""))
                    return self._send_json(_test_proxy(url))
                else:
                    return self._send_json({"error": "action khong hop le"},
                                           status=400)
            except ValueError as e:
                return self._send_json({"error": str(e)}, status=400)
            return self._send_json(STATE.proxy_store.public())
        if path == "/api/security":
            action = body.get("action")
            if STATE.auth is None:
                return self._send_json({"ok": True, "revoked": 0})
            if action == "revoke_others":
                n = STATE.auth.revoke_all(keep_token=self._cookie_token())
                return self._send_json({"ok": True, "revoked": n})
            if action == "revoke_all":
                n = STATE.auth.revoke_all()
                return self._send_json(
                    {"ok": True, "revoked": n},
                    extra_headers=[("Set-Cookie",
                                    app_auth.clear_cookie_header())])
            return self._send_json({"error": "action khong hop le"},
                                   status=400)
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
        # Ten co dinh o do_GET (login.html/app.html/app.js/style.css)
        # cung di qua _safe_static_path: phong thu theo chieu sau,
        # khong rieng route /fonts/ moi an toan.
        resolved = _safe_static_path(name)
        if resolved is None:
            return self._send_json({"error": "not_found"}, status=404)
        return self._serve_static_file(resolved, ctype)

    def _serve_static_file(self, resolved, ctype):
        # `resolved` da qua _safe_static_path (nam trong thu muc
        # cho phep). Chi tra 404 chung chung, khong lo duong dan.
        try:
            with open(resolved, "rb") as f:
                body = f.read()
        except (FileNotFoundError, IsADirectoryError, OSError):
            return self._send_json({"error": "not_found"}, status=404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def _warm_contacts_loop():
    """Nap danh ba nen (khi da dang nhap Zalo) de nhan dien nguoi la ngay sau
    khi khoi dong, khong doi co nguoi mo giao dien. Lam moi 10 phut. get_contacts
    da co cache + lui 429 nen khong don Zalo."""
    time.sleep(3)
    while True:
        try:
            sess = STATE.session
            if sess and sess.get("zpw_sek"):
                STATE.get_contacts(sess)
        except Exception:  # noqa: BLE001 - nen, khong duoc lam chet tien trinh
            pass
        time.sleep(600)


class _LogTee:
    """Ghi MOI dong in ra stdout/stderr vao <data>/logs/app.log (kem gio UTC) de dung lai/dung lai container khong mat bang chung
    (12/11: dung lai container xoa nhat ky cuoc goi cua chu may). Xoay vong khi > 8 MB (giu mot ban .1). Loi ghi tep khong lam hong app."""

    MAX_BYTES = 8 * 1024 * 1024

    def __init__(self, stream, path):
        self._s = stream
        self._path = path
        self._lock = threading.Lock()
        self._buf = ""
        self._f = None
        self._count = 0

    def write(self, text):
        n = self._s.write(text)
        try:
            self._to_file(text if isinstance(text, str) else str(text))
        except Exception:  # noqa: BLE001
            pass
        return n

    def _to_file(self, text):
        with self._lock:
            self._buf += text
            if "\n" not in self._buf:
                return
            body, self._buf = self._buf.rsplit("\n", 1)
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z ", time.localtime())
            if self._f is None:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                self._f = open(self._path, "a", encoding="utf-8", buffering=1)
            self._f.write("".join(stamp + line + "\n" for line in body.split("\n")))
            self._count += 1
            if self._count % 200 == 0 and os.path.getsize(self._path) > self.MAX_BYTES:
                self._f.close()
                os.replace(self._path, self._path + ".1")
                self._f = None

    def flush(self):
        return self._s.flush()

    def __getattr__(self, name):
        return getattr(self._s, name)


def _install_log_tee(data_dir):
    path = os.path.join(data_dir, "logs", "app.log")
    sys.stdout = _LogTee(sys.stdout, path)
    sys.stderr = _LogTee(sys.stderr, path)


def main():
    _install_log_tee(STATE.data_dir)
    STATE.retention.start()
    # App login is mandatory: refuse to start without credentials
    # instead of ever serving the app unprotected.
    if STATE.auth is None:
        print("KHONG KHOI DONG DUOC: %s" % STATE.auth_error,
              file=sys.stderr)
        print("Dat ZALO_PC_APP_USER + ZALO_PC_APP_PASSWORD (hoac "
              "ZALO_PC_APP_PASSWORD_HASH) luc deploy, roi chay lai.",
              file=sys.stderr)
        raise SystemExit(2)
    _seed_call_id_counter()
    _deps = deps_mod.check()
    for _name, _info in _deps.items():
        if isinstance(_info, dict) and not _info["ok"]:
            print("[deps] CANH BAO thieu %s: %s (cuoc goi/video se loi hoac cham)"
                  % (_name, _info["detail"]), file=sys.stderr, flush=True)
    threading.Thread(target=_warm_contacts_loop, daemon=True).start()
    server = QuietServer((HOST, PORT), Handler)
    print("zalo-pc-qr app %s on http://%s:%d (data: %s)"
          % (VERSION, HOST, PORT, DATA_DIR))
    print("Dang nhap app: bat buoc (user %s, phien %s gio)"
          % (STATE.auth.username, STATE.auth.session_hours))
    # Phien Zalo cu (tu session.json) ma co poll endpoints thi mo
    # kenh sync nhan tin den ngay; thieu endpoints thi start_sync
    # tu refresh getLoginInfo mot lan, hong thi thoi (khong chan
    # khoi dong — vong retry nen se thu lai moi 5 phut, va UI co
    # nut "Thu ket noi lai" goi POST /api/sync/retry; chi khi
    # server tra ve that su khong co endpoint thi moi can quet QR
    # lai).
    try:
        STATE.start_sync()
    except Exception as e:  # noqa: BLE001 - best-effort
        print("[sync-poll] khong mo duoc kenh luc khoi dong: %s"
              % type(e).__name__, flush=True)
    try:
        STATE.start_sync_retry_thread()
    except Exception as e:  # noqa: BLE001 - best-effort
        print("[sync-poll] khong mo duoc vong retry: %s"
              % type(e).__name__, flush=True)
    # Validate phien cu ngay luc khoi dong + hoi lai dinh ky
    # (keepAlive nhe): phien bi da se tu xoa + hien lai QR thay
    # vi bao login=true voi du lieu cu (loi H5).
    try:
        STATE.start_keepalive_thread()
    except Exception as e:  # noqa: BLE001 - best-effort
        print("[keepalive] khong mo duoc vong kiem chung phien: %s"
              % type(e).__name__, flush=True)
    try:
        STATE.start_revoke_watchdog()
        STATE.recall.start()
    except Exception as e:  # noqa: BLE001 - best-effort
        print("[session] khong mo duoc vong giam sat thu hoi phien: %s"
              % type(e).__name__, flush=True)
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
