"""Webhook settings + dispatch for the Zalo PC app.

Model — taken from the addon (see
~/workspace/zalo-addon-doc/bao-cao-addon-96-services.md §4 and
~/workspace/has-addons/zalo_bot/services/webhookService.js +
eventListeners.js, read-only):

  * One account, four webhook URLs, one per event family:
    message_webhook_url, group_event_webhook_url,
    reaction_webhook_url — plus a NEW one the addon does not have,
    call_webhook_url, for call events (call.sent / call.error /
    call.ended). The addon has no call webhook because zca-js has no
    calling; the PC app does have calling, so it gets its own family.
  * The server POSTs each event as JSON to the configured URL
    (Content-Type: application/json). A message the account itself
    sent (is_self) is NOT pushed by default — same anti-loop rule as
    the addon — unless it carries self_reply=true (a keyword command
    from the owner, per-thread opt-in in the addon).
  * Payloads here are the PC app's own shape (see build_*_event):
    {"event": <family>, "type": <family>.<name>, ...fields...,
    "account_id": <uid>, "sent_at": <unix seconds>}. They are NOT
    byte-identical to the addon's zca-js listener objects (those
    carry the raw zca-js msg/group_event/reaction objects); a
    receiver written for the addon must read the documented fields
    below, not assume the raw zca-js shape.

What actually fires TODAY (read this before assuming coverage):
  * call.* — fires NOW. The hooks live in server.py
    (/api/call/request success + error, /api/call/end): every
    outgoing call attempt the app itself makes produces a call
    event, because the app is the source of that event.
  * message — fires NOW. SyncPoller (HTTP long-poll 99100) ->
    server.py _on_sync_message -> dispatch_message (wired +
    tested). Incoming messages also land in the durable SQLite
    store (message_store.py) alongside dispatch.
  * group_event / reaction — fires NOW via the ctrl channel.
    CtrlPoller (HTTP long-poll 99101) -> server.py
    _on_ctrl_group_event / _on_ctrl_reaction ->
    dispatch_group_event / dispatch_reaction (wired + unit-tested;
    the exact live payload shape still needs a live check).
    NOTE: the "O3 WebSocket" mentioned in older notes is NOT the
    only channel — the exe has a real WebSocket alongside
    long-poll 99100, and the app uses ONLY HTTP long-poll
    99100/99101, which is a complete channel for these events.
  * offline / missed messages — SyncPoller persists its cursor
    to disk after every batch (cursor_store.py) and resumes from
    the saved cursor (PollCursor.from_dict), so the server returns
    queued messages since then. Missed messages are only
    backfilled while the server still holds them in its queue
    (the server-side retention window is unproven — needs a live
    test). NOTE on ACK: DELETE_QUEUE_ACK (557/558) lives on the
    E2EE signal channel, which the app does not have; on the HTTP
    channel the exe's ACK equivalent is persisting the advanced
    cursor + polling with it (see sync_poll.py / cursor_store.py).
  * 1-1 history — read from the local SQLite DB
    (message_store.py), which holds messages recorded since the
    app started storing them. The exe reads its own local SQLite
    DB; there is no 1-1 cloud-history endpoint in the bundle
    (getCloudMessage commands 12504-12508 are group-only, via
    getGroupCloudDomain). Group history already comes from 11240.
  * Do NOT claim the live shapes are proven until a live check
    shows a real group event / reaction / missed message arriving
    through these paths.

Safety rules (same spirit as the session store):
  * Config lives in <DATA_DIR>/webhooks.json, mode 0600, written
    atomically (tmp + replace, like session.py). The file is inside
    the data volume, which .gitignore already excludes; never commit
    a sample containing a real URL.
  * A POST never blocks the operation that triggered it: dispatch()
    runs in a daemon thread with a short timeout (default 5 s, vs
    the addon's 10 s). A webhook failure (timeout, refused, 4xx/5xx)
    is swallowed and recorded in memory only — it never breaks the
    call / save / load that triggered it.
  * Logs carry ONLY the destination (scheme://host/path, query
    stripped — a token in the query must never leak) + HTTP status.
    NEVER log payload content (no message text, no peer names
    beyond what the call log already shows).
  * Only http:// and https:// URLs are accepted; anything else is
    rejected at save time. URLs are capped at 2048 chars; payloads
    at 2 MB (same cap as the addon).
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# -- config ---------------------------------------------------------------
FILENAME = "webhooks.json"
MODE = 0o600
MAX_URL_LEN = 2048
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 5.0  # seconds; short on purpose, never blocks a call

# kind -> (url field, enabled field). Order is the order the settings
# UI shows them in.
KINDS = (
    ("message", "message_webhook_url", "message_enabled"),
    ("group_event", "group_event_webhook_url", "group_event_enabled"),
    ("reaction", "reaction_webhook_url", "reaction_enabled"),
    ("call", "call_webhook_url", "call_enabled"),
)
KIND_MAP = {k: (u, e) for k, u, e in KINDS}
URL_FIELDS = tuple(u for _, u, _ in KINDS)
ENABLED_FIELDS = tuple(e for _, _, e in KINDS)


def default_config():
    """All URLs empty, all families enabled (an empty URL simply
    means 'nothing to send to'; the toggle is what turns a
    configured family off without deleting its URL)."""
    cfg = {}
    for _, url_field, enabled_field in KINDS:
        cfg[url_field] = ""
        cfg[enabled_field] = True
    return cfg


def validate_url(value):
    """'' (unset) or an http(s) URL <= 2048 chars. Returns the
    stripped value, or raises ValueError naming the problem."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("webhook URL phai la chuoi")
    value = value.strip()
    if not value:
        return ""
    if len(value) > MAX_URL_LEN:
        raise ValueError("webhook URL qua dai (> %d ky tu)" % MAX_URL_LEN)
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            "webhook URL phai bat dau bang http:// hoac https://")
    return value


def normalize_config(raw):
    """Coerce an untrusted dict (POST body / file content) into a
    clean config: unknown keys dropped, URLs validated, toggles
    coerced to bool. Raises ValueError on a bad URL."""
    if not isinstance(raw, dict):
        raise ValueError("cau hinh webhook phai la doi tuong JSON")
    cfg = default_config()
    for _, url_field, enabled_field in KINDS:
        if url_field in raw:
            cfg[url_field] = validate_url(raw[url_field])
        if enabled_field in raw:
            cfg[enabled_field] = bool(raw[enabled_field])
    return cfg


def safe_url_for_log(url):
    """Destination for logs only: scheme://host/path, query and
    fragment stripped (a token in the query must never reach a log).
    Returns '' for an unparseable value."""
    try:
        p = urllib.parse.urlparse(url or "")
        if not p.scheme or not p.netloc:
            return ""
        return "%s://%s%s" % (p.scheme, p.netloc, p.path or "/")
    except Exception:
        return ""


class WebhookStore:
    """Persistent webhook config: one JSON file, mode 0600, atomic
    write (same pattern as session.SessionStore)."""

    def __init__(self, path):
        self.path = path

    def exists(self):
        return os.path.exists(self.path)

    def load(self):
        """Stored config merged over defaults (a missing/corrupt
        file yields defaults; a corrupt file does NOT raise — the
        settings page must still open)."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return normalize_config(raw)
        except (OSError, ValueError):
            return default_config()

    def save(self, raw):
        """Validate + persist. Raises ValueError on a bad URL (the
        API turns that into 400; nothing is written)."""
        cfg = normalize_config(raw)
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, MODE)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, MODE)
        except OSError:
            pass
        return cfg

    def get_url(self, kind):
        url_field, _ = KIND_MAP[kind]
        return self.load().get(url_field, "")

    def is_enabled(self, kind):
        _, enabled_field = KIND_MAP[kind]
        return bool(self.load().get(enabled_field, True))


# -- payload builders -----------------------------------------------------
# Every payload: {"event": family, "type": family.name, ...fields,
# "account_id": uid, "sent_at": unix seconds}. "account_id" is the
# PC account uid (the addon's _accountId, same role).

def _base(event, type_name, account_id):
    return {"event": event, "type": type_name,
            "account_id": account_id or "",
            "sent_at": int(time.time())}


def build_call_event(call_entry, account_id):
    """call_entry is a call_log record ({call_id, peer, thread_id,
    type, status, started_at, ended_at, detail}). type is
    call.sent / call.answered / call.error / call.ended, from
    status. `detail` carries the error text for error events only
    (it is the same text the Calls UI already shows; it never
    holds a secret)."""
    status = (call_entry or {}).get("status", "")
    payload = _base("call", "call." + status, account_id)
    payload.update({
        "call_id": str(call_entry.get("call_id", "")),
        "thread_id": str(call_entry.get("thread_id", "")),
        "peer": call_entry.get("peer", "") or "",
        "call_type": call_entry.get("type", "user") or "user",
        "status": status,
        "started_at": call_entry.get("started_at"),
        "ended_at": call_entry.get("ended_at"),
    })
    if status == "error":
        payload["detail"] = call_entry.get("detail", "") or ""
    if status == "answered":
        # api = nguoi/automation (HA) goi answer; media = thay RTP dau tien; sync = ben kia nghe may.
        payload["answer_source"] = str(call_entry.get("answer_source", "") or "")
    if status == "ended":
        # Ly do ket thuc that (user_end / ring_timeout / peer_declined /
        # peer_ended / missed / user_rejected ...), chi phan truoc dau ";"
        # (phan sau la loi tin hieu Zalo, khong dua ra ngoai). Cho phep
        # automation phan biet "tu choi" / "khong nghe may" / "cup may".
        payload["end_reason"] = str(
            call_entry.get("detail", "") or "").split(";", 1)[0].strip()
    return payload


def _add_media_fields(payload, msg, raw):
    """Anh / video / tep: HA nhan DU thong tin de tai ve va xu ly (truoc day chi co chu + nhan `kind`, nen tep va anh gui toi la mat tich).
    file_url = dia chi tai tren may chu Zalo (tai tu may chu, KHONG gui header Referer: video bi 403 neu co Referer);
    thumb_url = anh bia/thu nho; width/height/duration_ms + nhom anh (album) lay tu params cua tin Zalo."""
    for key in ("file_url", "file_name", "file_ext"):
        if msg.get(key):
            payload[key] = str(msg[key])
    try:
        size = int(msg.get("file_size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size > 0:
        payload["file_size"] = size
    content = raw.get("content") if isinstance(raw.get("content"), dict) else {}
    if content.get("thumb"):
        payload["thumb_url"] = str(content["thumb"])
    params = content.get("params")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except ValueError:
            params = None
    if isinstance(params, dict):
        for src, dst in (("width", "width"), ("height", "height"), ("video_width", "width"), ("video_height", "height"),
                         ("duration", "duration_ms"), ("group_layout_id", "album_id"),
                         ("id_in_group", "album_index"), ("total_item_in_group", "album_total")):
            if params.get(src) not in (None, ""):
                payload[dst] = params[src]


def build_message_event(msg, account_id):
    """msg is the incoming-message dict the sync channel will
    deliver (fields mirror the addon's listener msg: threadId,
    type 0=user/1=group, sender id, content, isSelf). Missing
    fields degrade to '' — a partial event is still delivered
    rather than dropped. NOTE: `content` IS included — the
    receiver is the user's own webhook (HA/n8n), exactly as the
    addon forwards the whole msg. It is never written to logs."""
    msg = msg or {}
    data = msg.get("data") if isinstance(msg.get("data"), dict) else {}
    content = msg.get("content", data.get("content", ""))
    if not isinstance(content, str):
        content = (content.get("msg") or content.get("title") or ""
                   if isinstance(content, dict) else "")
    if not content:
        content = msg.get("text", "") or ""
    payload = _base("message", "message.received", account_id)
    payload.update({
        "thread_id": str(msg.get("threadId", msg.get("thread_id", ""))),
        "thread_type": msg.get("type", msg.get("thread_type",
                                              data.get("type", 0))),
        "sender_id": str(msg.get("senderId", msg.get("sender_id",
                                                     msg.get("uidFrom", "")))),
        "message_id": str(msg.get("msgId", msg.get("message_id",
                                                   msg.get("id", "")))),
        "content": content,
        "is_self": bool(msg.get("isSelf", msg.get("is_self", False))),
        # Ten hien thi Zalo gui kem tin (dName) va co "nguoi la" (khong co
        # trong danh ba) de HA/n8n biet ai vua nhan tin ma khong tra them.
        "sender_name": str(msg.get("senderName", msg.get("sender_name", "")) or ""),
        # Gio Zalo ghi cho tin (giay) va gio app nhan duoc: hieu so la do tre.
        "zalo_time": msg.get("time", msg.get("ts", 0)) or 0,
        "received_at": round(time.time(), 3),
        "is_stranger": bool(msg.get("isStranger", msg.get("is_stranger", False))),
    })
    # Ma goc cua tin (de HA TRICH DAN khi tra loi, nhu zalo_bot: can message_id + cli_msg_id + uid_from; msg_ts = gio goc ms).
    raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
    if raw.get("cliMsgId") not in (None, ""):
        payload["cli_msg_id"] = str(raw["cliMsgId"])
    if raw.get("uidFrom") not in (None, ""):
        payload["uid_from"] = str(raw["uidFrom"])
    if raw.get("ts") not in (None, ""):
        payload["msg_ts"] = str(raw["ts"])
    if raw.get("msgType"):
        payload["zalo_msg_type"] = str(raw["msgType"])
    if msg.get("contactStatus"):
        payload["contact_status"] = str(msg["contactStatus"])      # group / friend / stranger / unknown (chua tai duoc danh ba)
    if msg.get("kind"):
        payload["kind"] = str(msg["kind"])                         # text / voice / photo / file / system
    if msg.get("voiceUrl"):
        payload["voice_url"] = str(msg["voiceUrl"])                # tin thoai: URL tren may chu Zalo (cho voice_to_text)
    _add_media_fields(payload, msg, raw)
    if msg.get("self_reply"):
        payload["self_reply"] = True
    if msg.get("tag_khop"):
        payload["tag_khop"] = msg["tag_khop"]
    return payload


def build_group_event_event(data, account_id):
    """data is the group_event dict from the sync channel. Its own
    `type`/`event` fields (if any) are kept verbatim under
    `group_event` so nothing is lost; the envelope type is
    group_event.<that type> when known, else group_event.received."""
    data = data or {}
    inner = str(data.get("type", data.get("event", "")) or "")
    payload = _base("group_event",
                    "group_event." + inner if inner else
                    "group_event.received", account_id)
    payload.update({
        "thread_id": str(data.get("threadId", data.get("group_id",
                                                       data.get("thread_id", "")))),
        "group_event": {k: v for k, v in data.items()},
    })
    return payload


def build_reaction_event(reaction, account_id):
    """reaction is the reaction dict from the sync channel (icon,
    threadId, msgId, uidFrom, type)."""
    reaction = reaction or {}
    payload = _base("reaction", "reaction.received", account_id)
    payload.update({
        "thread_id": str(reaction.get("threadId",
                                      reaction.get("thread_id", ""))),
        "thread_type": reaction.get("type", 0),
        "message_id": str(reaction.get("msgId",
                                       reaction.get("message_id", ""))),
        "sender_id": str(reaction.get("uidFrom",
                                      reaction.get("sender_id", ""))),
        "icon": reaction.get("icon", "") or "",
    })
    return payload


def build_test_event(kind, account_id):
    """Payload for the settings page's «Gửi thử» button: the same
    envelope as a real event of that family, marked test=true, with
    no real peer/message content in it."""
    payload = _base(kind, kind + ".test", account_id)
    payload["test"] = True
    payload["message"] = "Gui thu webhook tu Zalo PC"
    if kind == "call":
        payload.update({"call_id": "test", "thread_id": "",
                        "peer": "", "call_type": "user",
                        "status": "sent", "started_at": payload["sent_at"],
                        "ended_at": None})
    elif kind == "message":
        payload.update({"thread_id": "", "thread_type": 0,
                        "sender_id": "", "message_id": "",
                        "content": "Tin nhan thu", "is_self": False})
    elif kind == "group_event":
        payload.update({"thread_id": "", "group_event": {}})
    elif kind == "reaction":
        payload.update({"thread_id": "", "thread_type": 0,
                        "message_id": "", "sender_id": "",
                        "icon": "like"})
    return payload


# -- dispatcher -----------------------------------------------------------
class WebhookDispatcher:
    """POSTs events to configured URLs. post_fn(url, payload_dict)
    -> HTTP status int; injectable for tests (default: urllib POST).
    dispatch() is async (daemon thread, never blocks the caller);
    send_sync() is the synchronous core used by dispatch, by the
    «Gửi thử» endpoint (which must report the HTTP status), and by
    tests. Both swallow every failure and return a small result
    dict — a webhook error must never propagate into the call,
    save or sync operation that triggered it."""

    def __init__(self, store, post_fn=None, timeout=DEFAULT_TIMEOUT):
        self.store = store
        self.timeout = timeout
        self._post = post_fn or self._default_post
        self._lock = threading.Lock()
        self._last = []  # last 20 deliveries: kind/type/status/error
        # only (URL host is never stored here; see _record).

    def _default_post(self, url, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_PAYLOAD_BYTES:
            raise ValueError("webhook payload vuot qua %d bytes"
                             % MAX_PAYLOAD_BYTES)
        req = urllib.request.Request(url, method="POST", data=body)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "zalo-pc-qr-webhook/1.0")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
                return resp.status
        except urllib.error.HTTPError as e:
            try:
                e.read()
            except Exception:
                pass
            return e.code

    def _record(self, kind, type_name, status, error):
        with self._lock:
            self._last.append({"kind": kind, "type": type_name,
                               "status": status, "error": error or "",
                               "at": int(time.time())})
            del self._last[:-20]

    def last_deliveries(self):
        with self._lock:
            return [dict(d) for d in reversed(self._last)]

    def send_sync(self, kind, payload):
        """POST one payload now. Returns {"dispatched": bool,
        "status": int|None, "error": str, "reason": str}. Never
        raises. Log line carries only destination + status."""
        if kind not in KIND_MAP:
            return {"dispatched": False, "status": None,
                    "error": "kind khong hop le: %s" % kind,
                    "reason": "bad_kind"}
        cfg = self.store.load()
        url_field, enabled_field = KIND_MAP[kind]
        url = cfg.get(url_field, "")
        if not cfg.get(enabled_field, True):
            return {"dispatched": False, "status": None, "error": "",
                    "reason": "disabled"}
        if not url:
            return {"dispatched": False, "status": None, "error": "",
                    "reason": "no_url"}
        type_name = payload.get("type", kind) if isinstance(payload, dict) else kind
        try:
            status = self._post(url, payload)
            # Log: destination + status ONLY (query stripped, no
            # payload content — no message text, no peer detail).
            print("[webhook] kind=%s type=%s dest=%s status=%s"
                  % (kind, type_name, safe_url_for_log(url), status))
            self._record(kind, type_name, status, "")
            ok = 200 <= status < 300
            return {"dispatched": ok, "status": status,
                    "error": "" if ok else "HTTP %s" % status,
                    "reason": "sent" if ok else "http_error"}
        except Exception as e:  # noqa: BLE001 - webhook must not break caller
            print("[webhook] kind=%s type=%s dest=%s error=%s"
                  % (kind, type_name, safe_url_for_log(url),
                     type(e).__name__))
            self._record(kind, type_name, None, type(e).__name__)
            return {"dispatched": False, "status": None,
                    "error": "%s: %s" % (type(e).__name__, e),
                    "reason": "error"}

    def dispatch(self, kind, payload):
        """Fire-and-forget: POST in a daemon thread, return at once.
        The caller (call request/end, sync hook) never waits."""
        thread = threading.Thread(target=self.send_sync,
                                  args=(kind, payload), daemon=True)
        thread.start()
        return True

    def send_test(self, kind, account_id=""):
        """«Gửi thử»: synchronous test payload to kind's URL, so the
        API can report the HTTP status back to the settings page."""
        return self.send_sync(kind, build_test_event(kind, account_id))


# -- hook points ----------------------------------------------------------
# server.py calls dispatch_call_event() from /api/call/request (sent
# + error) and /api/call/end (ended); _on_sync_message() calls
# dispatch_message() (long-poll 99100); _on_ctrl_group_event() /
# _on_ctrl_reaction() call dispatch_group_event() /
# dispatch_reaction() (long-poll 99101).

def build_voice2text_event(ev, account_id):
    """Ket qua chuyen giong noi (Zalo AI). `content` = van ban: la du lieu cua nguoi
    dung gui toi webhook cua chinh ho (nhu tin nhan), KHONG ghi vao log."""
    out = _base("voice2text", "voice2text.result", account_id)
    out.update({"req_id": str(ev.get("req_id", "")),
                "text": ev.get("text", ""), "error": ev.get("error")})
    return out


def dispatch_voice2text(dispatcher, ev, account_id):
    """Di chung URL webhook tin nhan (message_webhook_url); `event` = "voice2text"."""
    if dispatcher is None:
        return False
    return dispatcher.dispatch("message", build_voice2text_event(ev, account_id))


def dispatch_call_event(dispatcher, call_entry, account_id, extra=None):
    """Call event from a call_log record (sent/answered/error/ended).
    Fires NOW — the app itself is the source, no sync channel needed."""
    if dispatcher is None or not call_entry:
        return False
    payload = build_call_event(call_entry, account_id)
    if extra:
        payload.update({k: v for k, v in extra.items() if v is not None and v != ""})
    return dispatcher.dispatch("call", payload)


def dispatch_message(dispatcher, msg, account_id):
    """HOOK for the sync channel (long-poll 99100): called from
    server.py _on_sync_message with each incoming message.
    Self-sent messages are skipped by default (addon anti-loop
    rule); only a self message carrying self_reply=true (owner
    keyword command) is forwarded."""
    if dispatcher is None:
        return False
    if msg and (msg.get("isSelf") or msg.get("is_self")) \
            and not msg.get("self_reply"):
        return False
    return dispatcher.dispatch(
        "message", build_message_event(msg, account_id))


def dispatch_group_event(dispatcher, data, account_id):
    """HOOK for the ctrl channel (long-poll 99101): called from
    server.py _on_ctrl_group_event with each group event the
    CtrlPoller extracts (see ctrl_poll.extract_group_events)."""
    if dispatcher is None:
        return False
    return dispatcher.dispatch(
        "group_event", build_group_event_event(data, account_id))


def dispatch_reaction(dispatcher, reaction, account_id):
    """HOOK for the ctrl channel (long-poll 99101): called from
    server.py _on_ctrl_reaction with each reaction the CtrlPoller
    extracts (see ctrl_poll.extract_reactions)."""
    if dispatcher is None:
        return False
    return dispatcher.dispatch(
        "reaction", build_reaction_event(reaction, account_id))
