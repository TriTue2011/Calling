"""In-memory call log for the calling monitor (stage 1.5).

Every outgoing call attempt and every end is recorded here — nothing
else. A record holds only what the calls UI needs: when it happened,
who was called, which thread, what kind, and the result. No session
secrets, no audio, no message content ever enters this log.

Statuses (Vietnamese labels live in the UI, not here):
  sent   — the requestcall was accepted by the server, so the far end
           rings; the call is live until it is ended or superseded.
  error  — the request failed; `detail` carries the error text.
  ended  — /api/call/end was called for this call_id.

The log is process memory only (a restart clears it) and capped at
50 records — it is a monitor, not an archive.
"""

import threading
import time

MAX_RECORDS = 50


class CallLog:
    def __init__(self):
        self._lock = threading.Lock()
        self._calls = []

    def record_start(self, call_id, peer, thread_id, call_type):
        """A requestcall was accepted: log it live, and close any
        earlier live call (starting a new call supersedes it)."""
        now = time.time()
        with self._lock:
            for c in self._calls:
                if c["status"] == "sent":
                    c["status"] = "ended"
                    c["ended_at"] = now
            entry = {"call_id": str(call_id), "peer": peer or "",
                     "thread_id": str(thread_id), "type": call_type,
                     "status": "sent", "started_at": now,
                     "ended_at": None, "detail": ""}
            self._calls.append(entry)
            del self._calls[:-MAX_RECORDS]
            return dict(entry)

    def record_error(self, call_id, peer, thread_id, call_type, detail):
        now = time.time()
        with self._lock:
            entry = {"call_id": str(call_id), "peer": peer or "",
                     "thread_id": str(thread_id), "type": call_type,
                     "status": "error", "started_at": now,
                     "ended_at": now, "detail": detail or ""}
            self._calls.append(entry)
            del self._calls[:-MAX_RECORDS]
            return dict(entry)

    def record_end(self, call_id):
        """Mark a live call ended. Unknown ids are ignored (the end
        endpoint still answers ok — ending is best-effort)."""
        now = time.time()
        with self._lock:
            for c in self._calls:
                if c["call_id"] == str(call_id) and c["status"] == "sent":
                    c["status"] = "ended"
                    c["ended_at"] = now
                    return dict(c)
            return None

    def snapshot(self):
        """{"calls": [newest first], "active": <live entry or None>}."""
        with self._lock:
            calls = [dict(c) for c in reversed(self._calls)]
        active = None
        for c in calls:
            if c["status"] == "sent":
                active = c
                break
        return {"calls": calls, "active": active}
