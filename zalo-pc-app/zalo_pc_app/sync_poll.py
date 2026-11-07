"""Sync long-poll (99100 getChatFromPolling) — tin nhan den.

Kenh nhan tin den cua client PC that (bundle Zalo PC 26.11.10,
compact-app-pc.*.js) — KHONG phai poll thu cong, cung khong phai
WebSocket rieng:

  static getChatFromPolling(e,t):
    GET W[J] + "/?" + commonParams + "&params=" + e + "&ts=" + unix
    timeout 1e3 * X   (X = lp_msg_timeout, mac dinh 30 giay)
  W = config.zpw_chts_new (danh sach URL long-poll tin nhan, server
  tra ve o getLoginInfo — app luu nguyen tu config, khong hard-code);
  X = config.zpw_conf.lp_msg_timeout.
  setEndpoints(zpw_chts_new, zpw_ctrs_new, service_map, zpw_conf,
  zpw_ws) — cung config do (xem server._fetch_login_info).

  e = idPoll.getLastActionIds() =
    "<lastActionId>,<lastActionIdOther>," +
    encodeURIComponent(btoa(JSON({queue: {lastId, ids}})) + ",1")
  (lastActionId/lastActionIdOther mac dinh "1"; queue map rong luc
  dau, server day queueStatus ve sau moi lan poll thanh cong).

  Tra loi (HTTP 200, body la envelope {error_code, data}):
    data == ""              -> long-poll het han, khong co tin: poll lai
    error_code == -69       -> dung retry + dang xuat (server bao dung)
    error_code == ERR_KICK_OUT (gia tri so chua lan duoc tu bundle
                               trong dot nay — xem KICK_OUT_NOTE) ->
                               server ep dang xuat
    error_code == 0         -> data la JSON AES (zpw_enk, giong moi
                               response post-login): {msgs, groupMsgs,
                               pageMsgs, lastActionId,
                               lastActionIdOther, queueStatus,
                               resetLastActionId}
    error_code khac         -> loi, retry voi backoff
  Timeout cuc bo ("timeout of") -> xoay endpoint J=(J+1)%len(W),
  poll lai ngay. Loi mang khac -> retry (backoff o SyncPoller.run).

  preProcessChatMsgs: msgs -> 1-1 (msgKey=uidFrom, isGroup=false);
  groupMsgs -> nhom (msgKey=GROUPID_PREFIX+idTo, isGroup=true);
  pageMsgs -> 1-1 (msgKey=uidFrom). Moi tin co uidFrom, idTo, msgId,
  globalMsgId, content (string hoac {msg, title}), ts (giay),
  dName, msgType. Tin 1-1 co ca idTo=="0" lan uidFrom=="0" thi
  client gan idTo = uid cua minh (tin tu gui / khong ro nguon).

Kenh ctrl (99101 getControllFromPolling, q = zpw_ctrs_new) mang
group_event / reaction / tin hieu dieu khien — CHUA implement o
dot nay (chi tin nhan): SyncPoller chi mo kenh msg. Group event
va reaction van cho kenh ctrl (xem webhooks.py: hook da co san,
doi nguon su kien).

Doi chieu Node.js (zalobot / zca-js, theo chi dao 23:05 +07):
  - zca-js nhan tin qua api.listener.on("message") — cung mo hinh
    long-poll nay o tang duoi. eventListeners.js: msg.type === 1
    (nhom) -> storeGroupMessage (luu JSONL, toi 5000 tin/nhom);
    tin tu gui (isSelf) KHONG day webhook (chong lap bot);
    ca hai chieu deu broadcast ra WebSocket cho trang theo doi.
  - Native giu nguyen hanh vi do: Inbox luu ca hai chieu (cap
    1000 tin/thread trong RAM dot nay — chua ghi dia nhu Node.js,
    xem GHI CHU o Inbox); webhook chi day tin den (dispatch_message
    da co san quy tac isSelf); UI lay tin moi qua
    /api/thread/<id>/updates thay cho WebSocket (server stdlib
    khong co WebSocket).
  - Lich su nhom: zca-js getGroupChatHistory(grid, count) gui
    {grid, count} — giong het chat.history_group (11240); merge
    cache theo khoa msgId/cliMsgId, ban cua Zalo thang khi trung,
    sap theo ts, cat N tin cuoi (xem chat.merge_messages).
  - Lich su 1-1: Node.js CUNG KHONG CO endpoint (chi co
    getGroupChatHistoryByAccount) — native giu thong bao gioi han
    trung thuc, tin 1-1 chi co tu kenh sync + tin da gui trong
    phien.

KICK_OUT_NOTE: gia tri so cua ERR_KICK_OUT chua lan duoc (export
  Fi trong bundle, khong tim thay phep gan so trong vung lan).
  -69 thi da ro (dung retry). Cac error_code != 0 khac deu di
  vao retry/backoff va ghi log (chi ghi ma loi + do dai, khong
  ghi noi dung) — neu server ep dang xuat bang ma khac -69 thi
  poller se retry chu khong tu dang xuat; can lan them gia tri
  Fi o dot sau.
"""

import base64
import json
import sys
import threading
import time
import urllib.parse

from . import protocol
from .crypto import decode_postlogin_data
from .chat import normalize_message

# Ma loi server bao dung retry (bundle: polling handler).
ERR_STOP_RETRY = -69

# Backoff khi poll loi (khong phai timeout cuc bo): bat dau 3 giay,
# nhan doi moi lan, tran 60 giay — giong nhip retry cua client
# (retry() sau loi mang), khong doi kieu hammer.
RETRY_BASE_SECONDS = 3.0
RETRY_MAX_SECONDS = 60.0

# Tran RAM cho Inbox (Node.js giu 5000 tin/nhom TREN DIA; native
# dot nay chi giu RAM): 1000 tin/thread, cu nhat bi cat khi tran.
INBOX_MAX_PER_THREAD = 1000


class KickOut(Exception):
    """Server bao dung poll / ep dang xuat (error -69 hoac
    ERR_KICK_OUT). Poller dung, khong retry."""


class PollCursor:
    """Con tro long-poll (idPoll.getLastActionIds trong bundle).

    lastActionId / lastActionIdOther mac dinh "1" (getLatestActionId
    mac dinh t="1"); queues la map {queueName: {lastId, ids}} —
    rong luc dau, server day queueStatus ve sau moi lan poll
    thanh cong thi moi co ten queue that."""

    def __init__(self, last_action_id="1", last_action_id_other="1",
                 queues=None):
        self.last_action_id = str(last_action_id)
        self.last_action_id_other = str(last_action_id_other)
        self.queues = dict(queues or {})

    def param(self):
        """Chuoi params cho GET poll: "last,other,<b64(json)+',1'>"
        da URL-encode (bundle: encodeURIComponent(btoa(...) + ",1"))."""
        raw = json.dumps(self.queues, separators=(",", ":"),
                         ensure_ascii=False)
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return "%s,%s,%s" % (
            self.last_action_id, self.last_action_id_other,
            urllib.parse.quote(encoded + ",1", safe=""))

    def update_from(self, data):
        """Cap nhat con tro tu payload poll da giai ma. reset thi
        reset ve id server chi dinh; khong thi lay lastActionId /
        lastActionIdOther + queueStatus (chi nhan dang dict co
        lastId — dang khac bo qua, khong doan)."""
        if not isinstance(data, dict):
            return
        reset = data.get("resetLastActionId")
        if reset is not None and str(reset) not in ("", "0", "NaN"):
            # Exe: nhay TOI id reset, lastActionIdOther ve "1"
            # (khong giu ca hai o id cu nhu ban cu), xoa trang
            # thai queue — hang doi cu het han.
            self.last_action_id = str(reset)
            self.last_action_id_other = "1"
            self.queues = {}
            return
        if data.get("lastActionId") is not None:
            self.last_action_id = str(data["lastActionId"])
        if data.get("lastActionIdOther") is not None:
            self.last_action_id_other = str(data["lastActionIdOther"])
        status = data.get("queueStatus")
        if isinstance(status, dict):
            for name, info in status.items():
                if isinstance(info, dict) and "lastId" in info:
                    entry = {"lastId": str(info["lastId"])}
                    ids = info.get("ids")
                    if isinstance(ids, list):
                        entry["ids"] = [str(v) for v in ids[:10]]
                    self.queues[str(name)] = entry

    def to_dict(self):
        """Trang thai con tro dang dict JSON — de luu xuong dia
        (xem cursor_store.py)."""
        return {
            "lastActionId": self.last_action_id,
            "lastActionIdOther": self.last_action_id_other,
            "queues": {name: dict(info)
                       for name, info in self.queues.items()},
        }

    @classmethod
    def from_dict(cls, data):
        """Khoi tao con tro tu dict da luu (hoac tu mac dinh khi
        du lieu thieu/hong — khong doan)."""
        cursor = cls()
        if isinstance(data, dict):
            last = data.get("lastActionId")
            if last not in (None, ""):
                cursor.last_action_id = str(last)
            other = data.get("lastActionIdOther")
            if other not in (None, ""):
                cursor.last_action_id_other = str(other)
            queues = data.get("queues")
            if isinstance(queues, dict):
                clean = {}
                for name, info in queues.items():
                    if isinstance(info, dict) and "lastId" in info:
                        entry = {"lastId": str(info["lastId"])}
                        ids = info.get("ids")
                        if isinstance(ids, list):
                            entry["ids"] = [str(v) for v in ids[:10]]
                        clean[str(name)] = entry
                cursor.queues = clean
        return cursor


def _content_text(item):
    """Text hien thi cua 1 tin poll: content co the la string hoac
    dict {msg, title} (giong eventListeners.js cua Node.js)."""
    content = item.get("content")
    if isinstance(content, dict):
        return str(content.get("msg") or content.get("title") or "")
    if content is not None:
        return str(content)
    return ""


def extract_messages(data, own_id):
    """Tach tin tu payload poll da giai ma -> [(thread_type,
    thread_id, message)] voi message da chuan hoa (chat.
    normalize_message + direction / thread / sender_name).

    1-1 (msgs, pageMsgs): thread la doi phuong (uidFrom neu khac
    minh, khong thi idTo). Nhom (groupMsgs): thread la idTo,
    sender la uidFrom. Tin co ca uidFrom lan idTo == "0" thi
    coi la tin cua minh (bundle gan idTo = uid)."""
    own = str(own_id or "")
    out = []
    if not isinstance(data, dict):
        return out
    for key, thread_type in (("msgs", "user"), ("pageMsgs", "user"),
                             ("groupMsgs", "group")):
        items = data.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            sender = str(item.get("uidFrom") or "")
            peer = str(item.get("idTo") or "")
            if sender in ("", "0") and peer in ("", "0"):
                sender, peer = own, own
                # Bundle gan idTo = uid trong truong hop nay; sua
                # ca ban sao item de normalize khong giu "0".
                item = dict(item)
                item["uidFrom"] = own
                item["idTo"] = own
            if thread_type == "group":
                thread_id = peer or sender
            else:
                thread_id = (sender if sender and sender != own
                             else peer or own)
            is_self = bool(sender and sender == own)
            text = _content_text(item)
            if not text and item.get("message"):
                text = str(item.get("message"))
            msg = normalize_message(item, thread_type)
            msg["text"] = text or msg.get("text", "")
            msg["direction"] = "out" if is_self else "in"
            msg["is_self"] = is_self
            msg["thread_type"] = thread_type
            msg["thread_id"] = str(thread_id)
            if item.get("dName"):
                msg["sender_name"] = str(item["dName"])
            out.append((thread_type, str(thread_id), msg))
    return out


class Inbox:
    """Kho tin den trong phien (RAM — giong ChatStore): moi thread
    mot list, dedup theo khoa tin, dem unread cho tin den.

    Khoa dedup theo Node.js (groupHistoryStore.messageKey):
    msgId/cliMsgId, roi sender; khong co ca hai thi
    sender:timestamp:content. Cap 1000 tin/thread (cat cu nhat).
    GHI CHU: Node.js ghi group xuong dia JSONL (ben qua restart);
    native dot nay chua ghi dia — restart mat tin den trong phien
    (giong ChatStore hien tai)."""

    def __init__(self, max_per_thread=INBOX_MAX_PER_THREAD):
        self._lock = threading.Lock()
        self._store = {}   # (type, thread_id) -> [message, ...]
        self._unread = {}  # (type, thread_id) -> int
        self._max = max_per_thread

    @staticmethod
    def _key(msg):
        raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
        mid = (raw.get("msgId") or raw.get("msgID")
               or raw.get("cliMsgId") or raw.get("cliMsgID")
               or msg.get("id") or msg.get("client_id") or "")
        sender = str(msg.get("sender_id") or "")
        if mid:
            return "id:%s:%s" % (mid, sender)
        return "ct:%s:%s:%s" % (sender, msg.get("time") or "",
                                msg.get("text") or "")

    def record(self, thread_type, thread_id, msg):
        """Them 1 tin den; tra ve True neu moi (False neu trung).
        Tin den (direction in) tang unread cua thread."""
        key = (str(thread_type), str(thread_id))
        with self._lock:
            items = self._store.setdefault(key, [])
            k = self._key(msg)
            for old in items:
                if self._key(old) == k:
                    return False
            items.append(dict(msg))
            del items[:-self._max]
            if msg.get("direction") == "in":
                self._unread[key] = self._unread.get(key, 0) + 1
            return True

    def messages_for(self, thread_type, thread_id):
        key = (str(thread_type), str(thread_id))
        with self._lock:
            return [dict(m) for m in self._store.get(key, [])]

    def since(self, thread_type, thread_id, after_ts):
        """Tin cua thread co time > after_ts (float epoch giay).
        Tin khong co time duoc coi la moi (time=None -> lay)."""
        try:
            after = float(after_ts or 0)
        except (TypeError, ValueError):
            after = 0.0
        out = []
        for msg in self.messages_for(thread_type, thread_id):
            when = msg.get("time")
            if when is None or float(when) > after:
                out.append(msg)
        return out

    def mark_read(self, thread_type, thread_id):
        """User da mo thread: xoa unread (tin van giu)."""
        key = (str(thread_type), str(thread_id))
        with self._lock:
            self._unread.pop(key, None)

    def unread_for(self, thread_type, thread_id):
        key = (str(thread_type), str(thread_id))
        with self._lock:
            return self._unread.get(key, 0)

    def summary(self):
        """Moi thread co tin trong Inbox: {thread_id, type, unread,
        last: {text, time, sender_id, sender_name}} — sap theo
        tin moi nhat truoc. Dung cho huy hieu thread list o UI."""
        with self._lock:
            rows = []
            for (ttype, tid), items in self._store.items():
                if not items:
                    continue
                last = items[-1]
                rows.append({
                    "thread_id": tid, "type": ttype,
                    "unread": self._unread.get((ttype, tid), 0),
                    "last": {
                        "text": last.get("text", ""),
                        "time": last.get("time"),
                        "sender_id": last.get("sender_id", ""),
                        "sender_name": last.get("sender_name", ""),
                    }})
        rows.sort(key=lambda r: (r["last"]["time"] or 0), reverse=True)
        return rows

    def clear(self):
        with self._lock:
            self._store.clear()
            self._unread.clear()


class SyncPoller:
    """Long-poll tin den chay nen: GET lien tuc toi W (xoay
    endpoint khi timeout cuc bo), giai ma payload, cap nhat con
    tro, giao tin cho on_message(thread_type, thread_id, msg).

    http_get(url, timeout) -> (status, json) — giong transport
    cua Chat/Signaling (mang cookie zpw_sek). Loi mang -> backoff
    roi poll lai; KickOut (-69) -> dung han."""

    def __init__(self, http_get, poll_urls, zpw_enk, own_id,
                 on_message=None, msg_timeout=30, cursor=None,
                 on_cursor=None):
        urls = [u for u in (poll_urls or []) if u]
        if not urls:
            raise ValueError("sync_poll: can it nhat 1 poll URL "
                             "(zpw_chts_new tu getLoginInfo)")
        self.http_get = http_get
        self.urls = urls
        self.zpw_enk = zpw_enk
        self.own_id = str(own_id or "")
        self.on_message = on_message
        try:
            self.msg_timeout = int(msg_timeout or 30)
        except (TypeError, ValueError):
            self.msg_timeout = 30
        if self.msg_timeout <= 0:
            self.msg_timeout = 30
        # Con tro khoi tao tu dia (SyncCursorStore) thay vi luon
        # "1","1" — restart van poll tiep tu cho cu, server tra
        # tin trong hang doi ke tu do (bu tin lo). cursor co the
        # la PollCursor hoac dict da luu.
        if isinstance(cursor, PollCursor):
            self.cursor = cursor
        elif isinstance(cursor, dict):
            self.cursor = PollCursor.from_dict(cursor)
        else:
            self.cursor = PollCursor()
        # on_cursor(cursor) duoc goi sau moi batch lam con tro doi
        # — caller luu xuong dia (cursor_store.py). Luu loi khong
        # lam chet poller.
        self.on_cursor = on_cursor
        # Chan doan batch vua xu ly (khong log noi dung tin):
        # so tin + so queue offline co tin cho.
        self.last_batch = {"messages": 0, "offline_queues": 0,
                           "at": 0}
        self._idx = 0
        self._stop = threading.Event()
        self._thread = None
        self.kicked_out = False
        self.last_error = ""
        self.polls = 0  # dem so lan poll (chan doan, khong log nd)

    def _poll_url(self):
        base = self.urls[self._idx % len(self.urls)].rstrip("/")
        qs = urllib.parse.urlencode(protocol.common_params())
        return "%s/?%s&params=%s&ts=%d" % (
            base, qs, self.cursor.param(), int(time.time()))

    def poll_once(self):
        """Mot lan long-poll. Tra ve "ok" | "empty" | "rotated".
        Timeout cuc bo -> xoay endpoint, tra "rotated". Loi HTTP /
        loi giai ma -> RuntimeError (caller backoff). Server bao
        dung -> KickOut."""
        url = self._poll_url()
        try:
            status, payload = self.http_get(url,
                                            timeout=self.msg_timeout + 5)
        except TimeoutError:
            self._idx = (self._idx + 1) % len(self.urls)
            return "rotated"
        except Exception as e:  # noqa: BLE001 - mang loi -> backoff
            raise RuntimeError("sync_poll: poll loi mang: %s"
                               % type(e).__name__)
        self.polls += 1
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("sync_poll: network status=%s" % status)
        if payload.get("data") == "":
            return "empty"
        code = payload.get("error_code")
        if code == ERR_STOP_RETRY:
            self.kicked_out = True
            raise KickOut("sync_poll: server tra -69, dung retry")
        if code not in (0, None):
            # error_code khac 0 (ke ca ERR_KICK_OUT neu gap): chua
            # phan biet duoc kick-out that voi loi tam — retry voi
            # backoff, ghi ma loi (khong ghi noi dung). Xem
            # KICK_OUT_NOTE o docstring module.
            raise RuntimeError("sync_poll: error_code=%s" % code)
        data = decode_postlogin_data(payload, self.zpw_enk)
        if data is None:
            return "empty"
        messages = extract_messages(data, self.own_id)
        before = self.cursor.to_dict()
        self.cursor.update_from(data)
        # Tin offline: server gui queueStatus co queue co ids (tin
        # cho trong hang doi luc app tat) hoac firstPollOffline.
        # Xu ly het batch roi con tro tien (luu dia) chinh la ACK
        # tuong duong DELETE_QUEUE_ACK tren kenh HTTP: exe khong co
        # ACK rieng ngoai viec luu con tro + poll tiep bang con
        # tro moi (557/558 nam tren kenh signal E2EE ma app khong
        # co — xem cursor_store.py / bao cao webhook). Chi log so
        # luong, khong log noi dung tin.
        offline = 0
        status = data.get("queueStatus")
        if isinstance(status, dict):
            for info in status.values():
                if isinstance(info, dict) and info.get("ids"):
                    offline += 1
        if data.get("firstPollOffline"):
            offline = max(offline, 1)
        self.last_batch = {"messages": len(messages),
                           "offline_queues": offline,
                           "at": time.time()}
        if self.on_message is not None:
            for thread_type, thread_id, msg in messages:
                self.on_message(thread_type, thread_id, msg)
        if offline and messages and not sys.is_finalizing():
            print("[sync-poll] xu ly %d tin offline tu %d queue"
                  % (len(messages), offline), flush=True)
        if self.on_cursor is not None \
                and self.cursor.to_dict() != before:
            try:
                self.on_cursor(self.cursor)
            except Exception:  # noqa: BLE001 - luu con tro loi
                pass
        return "ok"

    def run(self):
        """Vong poll lien tuc cho toi stop(): poll xong poll lai
        ngay; loi -> backoff (3s, nhan doi, tran 60s). San 1 giay
        moi vong: server that giu long-poll toi lp_msg_timeout
        (30s) khi khong co tin, nen vong < 1 giay la bat thuong —
        san nay ngan tight-loop doi Zalo neu endpoint tra ngay
        lap tuc (va giu mock test o ~1 poll/giay). Tre tin toi
        da 1 giay la chap nhan duoc cho chat."""
        backoff = RETRY_BASE_SECONDS
        while not self._stop.is_set():
            started = time.time()
            try:
                self.poll_once()
                backoff = RETRY_BASE_SECONDS
            except KickOut:
                return
            except Exception as e:  # noqa: BLE001 - poller khong chet
                self.last_error = str(e)
                # Khong in khi interpreter dang tat: mot daemon
                # thread ma print() dung luc stdout dang duoc dong
                # se abort ca tien trinh (_enter_buffered_busy) —
                # gap khong on dinh o cuoi cac file test mo poller
                # roi tat mock ma khong stop_sync (8/8 test pass
                # nhung tien trinh chet 134 luc shutdown).
                if not sys.is_finalizing():
                    print("[sync-poll] %s; retry sau %.0fs"
                          % (self.last_error, backoff), flush=True)
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, RETRY_MAX_SECONDS)
                continue
            elapsed = time.time() - started
            if elapsed < 1.0 and self._stop.wait(1.0 - elapsed):
                return

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2)
