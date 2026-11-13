"""Nhật ký sức khoẻ tài khoản Zalo: ghi lại các mốc đáng chú ý (khởi động, đăng nhập, mở kênh nhận, phiên kết thúc và LÝ DO) để đọc lại sau.

Học từ ZaloCRM (ZaloAccountStatusLog) và app iOS «GiaNô» (remote_revoked / cleared_local_session): trước đây chỉ có log chữ trộn lẫn nên khi mất
kết nối phải đọc tay. Mỗi sự kiện là một dòng JSON trong <data>/health.jsonl (0600, tự cắt gọn); KHÔNG ghi khoá, mật khẩu hay nội dung tin.
"""
from __future__ import annotations

import json
import os
import threading
import time

KINDS = ("start", "login", "channel_open", "session_end", "note")
# Lý do phiên kết thúc (trường `detail` của sự kiện session_end):
#   local_logout      người dùng bấm đăng xuất
#   remote_revoked    Zalo báo dừng kênh nhận (-69): đăng nhập ở nơi khác / bị thu hồi từ xa
#   session_rejected  Zalo trả 401/403 cho kênh nhận hoặc keepAlive: phiên hết hạn
SESSION_END_REASONS = ("local_logout", "remote_revoked", "session_rejected")

MAX_EVENTS = 200
MAX_FILE_BYTES = 256 * 1024


class HealthLog:
    def __init__(self, path="", max_events=MAX_EVENTS, clock=time.time):
        self._path = path
        self._max = max_events
        self._clock = clock
        self._lock = threading.Lock()
        self._events = []
        self.started_at = clock()
        self._load()

    def _load(self):
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as fh:
                for line in fh.readlines()[-self._max:]:
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(ev, dict) and isinstance(ev.get("t"), (int, float)) and isinstance(ev.get("kind"), str):
                        self._events.append(ev)
        except OSError:
            self._events = []

    def record(self, kind, detail=""):
        """Ghi một sự kiện; lỗi đĩa không bao giờ ném ra cho nơi gọi."""
        ev = {"t": round(self._clock(), 3), "kind": str(kind), "detail": str(detail)[:200]}
        with self._lock:
            self._events.append(ev)
            del self._events[:-self._max]
            self._append(ev)
        return ev

    def _append(self, ev):
        if not self._path:
            return
        try:
            if os.path.exists(self._path) and os.path.getsize(self._path) > MAX_FILE_BYTES:
                tmp = self._path + ".tmp"
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    for old in self._events[:-1]:
                        fh.write(json.dumps(old, ensure_ascii=False) + "\n")
                os.replace(tmp, self._path)
            fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def last(self, kind):
        with self._lock:
            for ev in reversed(self._events):
                if ev["kind"] == kind:
                    return dict(ev)
        return None

    def summary(self, n=8):
        """Gọn cho /api/status: vài sự kiện cuối + lần phiên kết thúc cuối cùng (lý do) + số lần theo loại."""
        with self._lock:
            events = [dict(e) for e in self._events[-n:]]
            counts = {}
            for e in self._events:
                counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        return {"started_at": self.started_at, "events": events, "counts": counts,
                "last_session_end": self.last("session_end"), "last_login": self.last("login")}
