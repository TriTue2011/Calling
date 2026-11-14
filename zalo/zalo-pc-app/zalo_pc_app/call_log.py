"""In-memory call log for the calling monitor (stage 1.5).

Every outgoing call attempt and every end is recorded here — nothing
else. A record holds only what the calls UI needs: when it happened,
who was called, which thread, what kind, and the result. No session
secrets, no audio, no message content ever enters this log.

Statuses (Vietnamese labels live in the UI, not here):
  sent   — the requestcall was accepted by the server. NOTE (7l):
           that alone does NOT mean the far end rings: the server
           only has a complete invitation once the follow-up
           `request` step (11301 / 12434, carrying the caller's
           media endpoints) is also sent. `request_sent` records
           whether that second step went through; until the live
           test confirms the far end rings, "sent" means "invitation
           fully sent", not "the peer's phone is ringing".
  answered — the peer ANSWERED (live 2026-11-08 fix): the call is
           connected and still live. The ring timeout MUST NOT
           fire for this status, and ending it sends ENDCALL
           (11306), not cancel. `answered_at` records when, and
           `answer_source` how the app learned it ("api" = an
           explicit /api/call/answered call, e.g. from a sync
           push event; "media" = first inbound RTP arrived).
  incoming — a call is coming IN (2026-11-09, zca-js flow): the
           peer called us and the app saw the `call_event`
           (act "request") on ctrl 99101. Live until answered
           (POST /api/call/answer, 11303) or ended (missed,
           rejected, peer hung up). No ring timer is armed for
           it — the peer's side decides when it stops ringing.
  error  — the request failed; `detail` carries the error text.
  ended  — /api/call/end was called for this call_id.

"LIVE" means status in ("sent", "answered", "incoming") — every
place that looks for the live call (snapshot/active, record_end,
supersede) must accept all three; before this fix only "sent"
existed, so an answered call could never be ended through
/api/call/end.

Each entry also carries `request_sent` (True/False/None — None
means the request step was never attempted, e.g. entries recorded
before §7l) and `request_detail` (the request step's error text
when it failed, "" otherwise).

Each entry also carries `diag` (a dict of call-signaling
diagnostics, 2026-11-08): step-1/step-2 status + msg, the relay
addresses actually used, session presence + length, codec. Only
shapes/counts/presence — never a session or token value, so the
snapshot stays safe to log and to serve on /api/calls.

The log is process memory only (a restart clears it) and capped at
50 records — it is a monitor, not an archive.
"""

import threading
import time

MAX_RECORDS = 50


# Statuses that count as a LIVE call (ringing or connected).
LIVE_STATUSES = ("sent", "answered", "incoming")


def _notifies(fn):
    """Sau moi thay doi so cuoc goi goi `on_change` (neu co) NGOAI khoa — de giao dien nhan su kien tuc thi (SSE «call»). Loi o callback bi bo qua."""
    import functools

    @functools.wraps(fn)
    def wrapper(self, *a, **k):
        result = fn(self, *a, **k)
        cb = getattr(self, "on_change", None)
        if cb is not None:
            try:
                cb()
            except Exception:  # noqa: BLE001 - UI khong duoc lam hong so cuoc goi
                pass
        return result
    return wrapper


class CallLog:
    def __init__(self):
        self._lock = threading.Lock()
        self._calls = []
        self.on_change = None       # callable() sau moi thay doi (xem _notifies)

    @_notifies
    def record_start(self, call_id, peer, thread_id, call_type):
        """A requestcall was accepted: log it live, and close any
        earlier live call (starting a new call supersedes it).
        The closed entry keeps the real reason in `detail`
        ("superseded_by_new_call") so the call history — and the
        server log — can tell a superseded call apart from one
        the user ended (live 2026-11-07: a call that "cut off"
        could not be diagnosed because no end carried a reason)."""
        now = time.time()
        with self._lock:
            for c in self._calls:
                if c["status"] in LIVE_STATUSES:
                    c["status"] = "ended"
                    c["ended_at"] = now
                    c["detail"] = "superseded_by_new_call"
            entry = {"call_id": str(call_id), "peer": peer or "",
                     "thread_id": str(thread_id), "type": call_type,
                     "direction": "out", "status": "sent", "started_at": now,
                     "ended_at": None, "detail": "",
                     "request_sent": None, "request_detail": "",
                     "answered_at": None, "answer_source": "",
                     "diag": {}}
            self._calls.append(entry)
            del self._calls[:-MAX_RECORDS]
            return dict(entry)

    @_notifies
    def record_incoming(self, call_id, peer, thread_id, call_type):
        """A call is coming IN: the peer called us (call_event act
        "request" on ctrl 99101). Log it live with status
        "incoming", and close any earlier live call (an incoming
        call supersedes it, same as record_start). The closed
        entry keeps "superseded_by_new_call" in `detail`."""
        now = time.time()
        with self._lock:
            for c in self._calls:
                if c["status"] in LIVE_STATUSES:
                    c["status"] = "ended"
                    c["ended_at"] = now
                    c["detail"] = "superseded_by_new_call"
            entry = {"call_id": str(call_id), "peer": peer or "",
                     "thread_id": str(thread_id), "type": call_type,
                     "direction": "in", "status": "incoming", "started_at": now,
                     "ended_at": None, "detail": "",
                     "request_sent": None, "request_detail": "",
                     "answered_at": None, "answer_source": "",
                     "diag": {}}
            self._calls.append(entry)
            del self._calls[:-MAX_RECORDS]
            return dict(entry)

    def has_call(self, call_id):
        """Da co entry (bat ky trang thai) cho call_id nay chua — de bo qua su kien `request` lap lai."""
        with self._lock:
            return any(c["call_id"] == str(call_id) for c in self._calls)

    @_notifies
    def record_busy_rejected(self, call_id, peer, thread_id, call_type):
        """Cuoc goi DEN luc ta dang ban (dang noi / dang goi di): ghi mot entry da KET THUC ngay ("busy_rejected"),
        KHONG dung vao cuoc dang song (khac record_incoming: no don cuoc cu)."""
        now = time.time()
        with self._lock:
            entry = {"call_id": str(call_id), "peer": peer or "", "thread_id": str(thread_id), "type": call_type,
                     "status": "ended", "started_at": now, "ended_at": now, "direction": "in", "detail": "busy_rejected",
                     "request_sent": None, "request_detail": "", "answered_at": None, "answer_source": "", "diag": {}}
            self._calls.append(entry)
            del self._calls[:-MAX_RECORDS]
            return dict(entry)

    @_notifies
    def record_answered(self, call_id, source=""):
        """Mark a live (ringing) call answered: the peer picked up
        and the call is connected. "sent" -> "answered" (outgoing)
        and "incoming" -> "answered" (we picked up an incoming
        call); an already-answered entry is returned unchanged
        (idempotent) and any other status (ended/error/unknown)
        returns None. The ring timer must be disarmed by the
        caller when this returns an entry — an answered call is
        never ring-timed-out."""
        now = time.time()
        with self._lock:
            for c in self._calls:
                if c["call_id"] == str(call_id):
                    if c["status"] == "answered":
                        return dict(c)
                    if c["status"] not in ("sent", "incoming"):
                        return None
                    c["status"] = "answered"
                    c["answered_at"] = now
                    c["answer_source"] = source or ""
                    return dict(c)
            return None

    @_notifies
    def record_request(self, call_id, sent, detail=""):
        """Record the outcome of the follow-up `request` step
        (11301 / 12434) for a live call: whether the media request
        went through. Unknown ids are ignored."""
        now = time.time()
        with self._lock:
            for c in self._calls:
                if c["call_id"] == str(call_id) and c["status"] == "sent":
                    c["request_sent"] = bool(sent)
                    c["request_detail"] = detail or ""
                    return dict(c)
            return None

    def record_diag(self, call_id, diag):
        """Merge diagnostic fields (11300/11301 status + msg, relay
        addresses, session presence + length, codec) into a live
        call's `diag` dict. The caller stores shapes/counts/
        presence only — never a session or token value. Unknown
        ids (or non-live entries) are ignored."""
        if not isinstance(diag, dict):
            return None
        with self._lock:
            for c in self._calls:
                if c["call_id"] == str(call_id) \
                        and c["status"] in LIVE_STATUSES:
                    c.setdefault("diag", {}).update(diag)
                    return dict(c)
            return None

    @_notifies
    def record_error(self, call_id, peer, thread_id, call_type, detail, kind=""):
        now = time.time()
        with self._lock:
            entry = {"call_id": str(call_id), "peer": peer or "",
                     "thread_id": str(thread_id), "type": call_type,
                     "direction": "out", "status": "error", "started_at": now,
                     "ended_at": now, "detail": detail or "",
                     "request_sent": None, "request_detail": "",
                     "answered_at": None, "answer_source": "",
                     "diag": {}}
            if kind:                       # loai loi co cau truc (call_errors.KINDS); chuoi goc van o `detail`
                entry["error_kind"] = kind
            self._calls.append(entry)
            del self._calls[:-MAX_RECORDS]
            return dict(entry)

    @_notifies
    def record_end(self, call_id, detail=""):
        """Mark a live call ended. Unknown ids are ignored (the end
        endpoint still answers ok — ending is best-effort). `detail`
        carries the Zalo endcall error, if the server-side endcall
        failed — the call is ended locally either way (§7m)."""
        now = time.time()
        with self._lock:
            for c in self._calls:
                if c["call_id"] == str(call_id) \
                        and c["status"] in LIVE_STATUSES:
                    c["status"] = "ended"
                    c["ended_at"] = now
                    c["detail"] = detail or ""
                    return dict(c)
            return None

    @_notifies
    def end_active(self, detail=""):
        """End the live call, if any (there is at most one:
        starting a new call closes the earlier live one). Used when
        the end request carries no usable call_id — the End button's
        intent is unambiguous then."""
        now = time.time()
        with self._lock:
            for c in self._calls:
                if c["status"] in LIVE_STATUSES:
                    c["status"] = "ended"
                    c["ended_at"] = now
                    c["detail"] = detail or ""
                    return dict(c)
            return None

    @_notifies
    def record_end_error(self, call_id, detail):
        """Attach a Zalo endcall failure to an entry (already ended
        locally), so the history/detail can show why the
        server-side end failed even though the call ended (§7m)."""
        with self._lock:
            for c in self._calls:
                if c["call_id"] == str(call_id):
                    c["detail"] = detail or ""
                    return dict(c)
            return None

    def find(self, call_id):
        """Bản sao bản ghi của call_id (mới nhất trước), hoặc None."""
        key = str(call_id)
        with self._lock:
            for c in reversed(self._calls):
                if c["call_id"] == key:
                    return dict(c)
        return None

    def snapshot(self):
        """{"calls": [newest first], "active": <live entry or None>}."""
        with self._lock:
            calls = [dict(c) for c in reversed(self._calls)]
        active = None
        for c in calls:
            if c["status"] in LIVE_STATUSES:
                active = c
                break
        return {"calls": calls, "active": active}
