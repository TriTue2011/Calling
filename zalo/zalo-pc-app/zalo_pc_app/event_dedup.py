"""Chống xử lý trùng một sự kiện khi hai nguồn (WebSocket và long-poll) có thể cùng giao nó.

Tin nhắn đã có chống trùng ở Inbox.record; lớp này lo phần còn lại (điều khiển, cuộc gọi, cảm xúc, tin trang): mỗi mục trong các danh sách của một batch
được băm (JSON chuẩn hoá) và nhớ ngắn hạn. Mục ĐÃ thấy trong cửa sổ TTL thì bị bỏ khi `check` bật. Đường poll chỉ bật `check` khi WebSocket đang chạy,
nên khi WebSocket tắt thì đường poll KHÔNG đổi hành vi (chỉ ghi nhớ).
"""
from __future__ import annotations

import hashlib
import json
import threading
import time

LIST_KEYS = ("msgs", "pageMsgs", "groupMsgs", "controls", "reacts", "reactions", "reactGroups")


class EventDedup:
    def __init__(self, ttl=120.0, max_entries=4000, clock=time.time):
        self._ttl = ttl
        self._max = max_entries
        self._clock = clock
        self._seen = {}
        self._lock = threading.Lock()
        self.dropped = 0

    @staticmethod
    def digest(item):
        try:
            blob = json.dumps(item, sort_keys=True, default=str, separators=(",", ":"))
        except (TypeError, ValueError):
            blob = repr(item)
        return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()

    def _prune(self, now):
        if len(self._seen) > self._max:
            for k, t in sorted(self._seen.items(), key=lambda kv: kv[1])[:len(self._seen) - self._max + self._max // 10]:
                self._seen.pop(k, None)
        for k in [k for k, t in self._seen.items() if now - t > self._ttl]:
            del self._seen[k]

    def seen(self, key):
        """True nếu `key` đã được ghi nhớ trong cửa sổ TTL (và gia hạn); False nếu mới (và ghi nhớ ngay)."""
        now = self._clock()
        with self._lock:
            self._prune(now)
            known = key in self._seen
            self._seen[key] = now
            return known

    def filter(self, data, check):
        """Trả bản sao nông của `data` (dict của một batch) đã bỏ các mục trùng trong các danh sách LIST_KEYS khi check=True; luôn ghi nhớ mục mới."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for key in LIST_KEYS:
            items = data.get(key)
            if not isinstance(items, list):
                continue
            kept = []
            for item in items:
                known = self.seen("%s:%s" % (key, self.digest(item)))
                if known and check:
                    self.dropped += 1
                else:
                    kept.append(item)
            out[key] = kept
        return out
