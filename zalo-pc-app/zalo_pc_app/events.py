"""Kênh đẩy sự kiện trong tiến trình: giao diện web nghe qua SSE (/api/events)
nên tin mới hiện ngay khi kênh sync nhận được, không chờ vòng hỏi lại.

Mỗi người nghe có một hàng đợi nhỏ; đầy thì bỏ sự kiện cũ nhất (người nghe
chậm không được làm nghẽn kênh sync).
"""
import queue
import threading

MAX_SUBSCRIBERS = 50
QUEUE_SIZE = 200


class EventHub:
    def __init__(self):
        self._subs = []
        self._lock = threading.Lock()

    def subscribe(self):
        """Hàng đợi mới, hoặc None khi đã đủ người nghe."""
        with self._lock:
            if len(self._subs) >= MAX_SUBSCRIBERS:
                return None
            q = queue.Queue(maxsize=QUEUE_SIZE)
            self._subs.append(q)
            return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def count(self):
        with self._lock:
            return len(self._subs)

    def publish(self, event):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (queue.Empty, queue.Full):
                    pass
