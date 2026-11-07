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
  error  — the request failed; `detail` carries the error text.
  ended  — /api/call/end was called for this call_id.

"LIVE" means status in ("sent", "answered") — every place that
looks for the live call (snapshot/active, record_end, supersede)
must accept both; before this fix only "sent" existed, so an
answered call could never be ended through /api/call/end.

Each entry also carries `request_sent` (True/False/None — None
means the request step was never attempted, e.g. entries recorded
before §7l) and `request_detail` (the request step's error text
when it failed, "" otherwise).

The log is process memory only (a restart clears it) and capped at
50 records — it is a monitor, not an archive.
"""

import threading
import time

MAX_RECORDS = 50


# Statuses that count as a LIVE call (ringing or connected).
LIVE_STATUSES = ("sent", "answered")


class CallLog:
    def __init__(self):
        self._lock = threading.Lock()
        self._calls = []

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
                     "status": "sent", "started_at": now,
                     "ended_at": None, "detail": "",
                     "request_sent": None, "request_detail": "",
                     "answered_at": None, "answer_source": ""}
            self._calls.append(entry)
            del self._calls[:-MAX_RECORDS]
            return dict(entry)

    def record_answered(self, call_id, source=""):
        """Mark a live (ringing) call answered: the peer picked up
        and the call is connected. Only "sent" -> "answered"; an
        already-answered entry is returned unchanged (idempotent)
        and any other status (ended/error/unknown) returns None.
        The ring timer must be disarmed by the caller when this
        returns an entry — an answered call is never ring-timed-out."""
        now = time.time()
        with self._lock:
            for c in self._calls:
                if c["call_id"] == str(call_id):
                    if c["status"] == "answered":
                        return dict(c)
                    if c["status"] != "sent":
                        return None
                    c["status"] = "answered"
                    c["answered_at"] = now
                    c["answer_source"] = source or ""
                    return dict(c)
            return None

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

    def record_error(self, call_id, peer, thread_id, call_type, detail):
        now = time.time()
        with self._lock:
            entry = {"call_id": str(call_id), "peer": peer or "",
                     "thread_id": str(thread_id), "type": call_type,
                     "status": "error", "started_at": now,
                     "ended_at": now, "detail": detail or "",
                     "request_sent": None, "request_detail": "",
                     "answered_at": None, "answer_source": ""}
            self._calls.append(entry)
            del self._calls[:-MAX_RECORDS]
            return dict(entry)

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
