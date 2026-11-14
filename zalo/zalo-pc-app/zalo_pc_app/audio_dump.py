"""Chẩn đoán vọng: ghi HAI luồng của cuộc gọi (tiếng bên kia gửi ra loa; tiếng mic nhận về) vào <dữ liệu>/diag/echo-<giờ>.bin để phân tích NGOẠI TUYẾN
(tools/echo_analyze.py: độ trễ loa→mic, mức vọng còn lại). Vì sao cần: từ phía app chỉ đếm khung, không biết vọng lớn cỡ nào hay trễ bao nhiêu (số erle_db/độ trễ
của bộ khử vọng nằm bên HA và mất khi cúp máy).

QUYỀN RIÊNG TƯ: tệp chứa GIỌNG NÓI thật của cuộc gọi. Mặc định TẮT; bật bằng ZALO_PC_AUDIO_DUMP_SECONDS=<giây tối đa mỗi cuộc, vd 60>. Chỉ giữ 5 tệp gần nhất
trên đĩa của chính máy chủ này; không gửi đi đâu. Đo xong thì tắt biến và xoá thư mục diag/echo-*.bin.

Định dạng tệp: lặp lại bản ghi = 1 byte loại (0 = loa/far, 1 = mic/near trước khi chặn, 2 = mic GỬI ĐI sau khi chặn vọng và chỉnh âm lượng) + 8 byte float64 giờ đơn điệu (little-endian) + 640 byte PCM16 mono 16 kHz (20 ms).
"""
import glob
import os
import struct
import threading
import time

FRAME_BYTES = 640
KEEP_FILES = 5
GAP_NEW_CALL = 5.0          # im > ngần này giây = cuộc gọi mới (tệp mới)
_REC = struct.Struct("<Bd")


def _seconds():
    try:
        return float(os.environ.get("ZALO_PC_AUDIO_DUMP_SECONDS", "0") or 0)
    except ValueError:
        return 0.0


class _Dump:
    def __init__(self):
        self._lock = threading.Lock()
        self._fh = None
        self._t0 = 0.0
        self._last = 0.0
        self._capped = False        # cuộc này đã đủ hạn mức giây: bỏ qua tới khi im > GAP_NEW_CALL (cuộc kế)
        self.path = ""

    def record(self, kind, frame, now=None, directory=None):
        limit = _seconds()
        if limit <= 0 or not frame:
            return
        now = time.monotonic() if now is None else now
        with self._lock:
            quiet = self._last and now - self._last > GAP_NEW_CALL
            if quiet:                                   # im lâu = cuộc gọi mới
                self._close()
                self._capped = False
            self._last = now
            if self._capped:
                return
            if self._fh is None and not self._open(now, directory):
                return
            if now - self._t0 > limit:
                self._close()
                self._capped = True
                return
            self._fh.write(_REC.pack(kind, now) + bytes(frame)[:FRAME_BYTES].ljust(FRAME_BYTES, b"\0"))

    def _open(self, now, directory):
        d = directory or os.path.join(os.environ.get("ZALO_PC_DATA_DIR", "."), "diag")
        try:
            os.makedirs(d, exist_ok=True)
            self.path = os.path.join(d, "echo-%s.bin" % time.strftime("%Y%m%d-%H%M%S"))
            self._fh = open(self.path, "wb", buffering=1 << 16)
        except OSError:
            self._fh = None
            return False
        self._t0 = now
        for old in sorted(glob.glob(os.path.join(d, "echo-*.bin")))[:-KEEP_FILES]:
            try:
                os.remove(old)
            except OSError:
                pass
        return True

    def _close(self):
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
        self._fh = None


_DUMP = _Dump()


def far(frame):
    """Khung tiếng bên kia GỬI RA LOA (trước khi chỉnh âm lượng)."""
    _DUMP.record(0, frame)


def near(frame):
    """Khung tiếng mic NHẬN VỀ (trước khi chặn/chỉnh âm lượng)."""
    _DUMP.record(1, frame)


def sent(frame):
    """Khung mic THỰC SỰ gửi sang bên kia (sau chặn vọng và chỉnh âm lượng): so với `near` để đo bộ chặn giảm được bao nhiêu."""
    _DUMP.record(2, frame)
