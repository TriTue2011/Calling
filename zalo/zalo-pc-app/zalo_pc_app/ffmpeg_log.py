"""Ghi lại lỗi của ffmpeg con (mic / hình / loa) thay vì vứt vào /dev/null.

Trước đây ba bộ gửi đều chạy ffmpeg với ``stderr=DEVNULL`` nên camera không đọc được (401, codec lạ, mạng chặn) hay loa từ chối chỉ lộ ra là «không có
hình / không có tiếng», không có dòng lỗi nào. ``StderrTail`` giữ vài dòng cuối (đã che mật khẩu và khoá ``?k=``) để đưa vào nhật ký và trạng thái cuộc gọi.
KHÔNG bao giờ đưa URL gốc (có thể chứa khoá hay mật khẩu) ra ngoài."""
from __future__ import annotations

import collections
import re
import subprocess
import threading

_SECRET = re.compile(r"(://[^/\s:@]+:)[^@/\s]*@|([?&]k=)[^&\s\"']+", re.I)


def kill_and_reap(proc, timeout: float = 2.0) -> None:
    """Giết ffmpeg con RỒI thu xác nó. ``kill()`` một mình để lại tiến trình ma (zombie) cho tới lần ``Popen`` kế tiếp;
    trên máy yếu, gọi nhiều cuộc liên tiếp là tích dần. Tiến trình giả (test) không có ``wait`` thì bỏ qua."""
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.kill()
    except OSError:
        return
    try:
        proc.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, OSError, AttributeError):
        pass


def redact(text: str) -> str:
    return _SECRET.sub(lambda m: (m.group(1) + "***@") if m.group(1) else (m.group(2) + "***"), text or "")


class StderrTail:
    """Đọc ``proc.stderr`` ở luồng nền, giữ ``maxlen`` dòng cuối. Process giả (test) không có ``stderr`` thì không làm gì."""

    def __init__(self, proc, maxlen: int = 12) -> None:
        self._lines: collections.deque[str] = collections.deque(maxlen=maxlen)
        self._thread = None
        stream = getattr(proc, "stderr", None)
        if stream is not None and hasattr(stream, "readline"):
            self._thread = threading.Thread(target=self._run, args=(stream,), daemon=True)
            self._thread.start()

    def _run(self, stream) -> None:
        try:
            for raw in iter(stream.readline, b""):
                line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else str(raw).strip()
                if line:
                    self._lines.append(redact(line)[:200])
        except (OSError, ValueError):
            pass

    def text(self, n: int = 4) -> str:
        return " | ".join(list(self._lines)[-n:])
