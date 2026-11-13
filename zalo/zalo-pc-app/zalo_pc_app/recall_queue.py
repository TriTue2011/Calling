"""Hẹn giờ THU HỒI tin sau N giây tuỳ ý (13/11).

Zalo không cho đặt tự xoá theo giây: cài đặt cuộc trò chuyện chỉ nhận 1/7/14/30 ngày (1 giờ chỉ dành cho zBusiness), `ttl` gắn riêng từng tin bị bỏ qua,
và `onlyMe=0` chỉ xoá phía mình. Cách duy nhất làm tin biến mất ở cả hai bên đúng giờ là THU HỒI (undo) — Zalo để lại dòng «tin nhắn đã được thu hồi».

Hàng đợi lưu ra tệp (0600, ghi nguyên tử) để khởi động lại không làm mất hẹn. `undo(thread_type, thread_id, msg_id, cli_msg_id)` do bên gọi cung cấp
(ném ngoại lệ khi lỗi). Chưa đăng nhập: `undo` ném `NotReady` -> mục giữ nguyên, không tính là lần thử hỏng.
"""

import json
import os
import threading
import time

MAX_AFTER_SECONDS = 24 * 3600       # Zalo chỉ cho thu hồi trong một khoảng thời gian: không hẹn xa hơn 1 ngày
MAX_ATTEMPTS = 3                    # lỗi thật (khác NotReady) thử tối đa 3 lần rồi bỏ, có ghi log
RETRY_GAP = 5.0


class NotReady(RuntimeError):
    """Chưa có phiên Zalo để thu hồi — giữ mục lại."""


def parse_after(value):
    """Giây hẹn thu hồi từ tham số gọi vào: None/''/0 -> 0 (không hẹn); số 1..MAX_AFTER_SECONDS -> int; còn lại ValueError (nói rõ, không đoán)."""
    if value in (None, "", False):
        return 0
    try:
        n = int(float(str(value).strip()))
    except (TypeError, ValueError):
        raise ValueError("recall_after phai la so giay (0 = khong hen)")
    if n < 0 or n > MAX_AFTER_SECONDS:
        raise ValueError("recall_after phai trong 0..%d giay" % MAX_AFTER_SECONDS)
    return n


class RecallQueue:
    def __init__(self, path, undo, clock=time.time, log=print):
        self.path, self.undo, self.clock, self.log = path, undo, clock, log
        self._lock = threading.Lock()
        self._items = self._load()
        self._thread = None
        self._stop = threading.Event()

    # ---- lưu trữ
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        return [i for i in data if isinstance(i, dict) and i.get("msg_id") and i.get("thread_id")] if isinstance(data, list) else []

    def _save_locked(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._items, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    # ---- giao diện
    def add(self, thread_type, thread_id, msg_id, cli_msg_id, after_seconds):
        """Hẹn thu hồi; trả thời điểm (epoch giây). after_seconds = 0 hoặc thiếu mã tin -> không làm gì, trả 0."""
        if not after_seconds or not msg_id:
            return 0
        at = self.clock() + int(after_seconds)
        with self._lock:
            self._items.append({"thread_type": thread_type, "thread_id": str(thread_id), "msg_id": str(msg_id),
                                "cli_msg_id": str(cli_msg_id or ""), "at": at, "attempts": 0})
            self._save_locked()
        return at

    def pending(self):
        with self._lock:
            return [dict(i) for i in self._items]

    def run_due(self):
        """Thu hồi các mục đến hạn; trả số mục đã xử lý xong (thành công hoặc bỏ)."""
        now = self.clock()
        with self._lock:
            due = [i for i in self._items if i["at"] <= now]
        done = 0
        for it in due:
            try:
                self.undo(it["thread_type"], it["thread_id"], it["msg_id"], it["cli_msg_id"])
                self.log("[recall] da thu hoi thread=%s msg=%s" % (it["thread_id"], it["msg_id"]))
            except NotReady:
                continue
            except Exception as e:  # noqa: BLE001 - loi that tu Zalo/mang
                it["attempts"] += 1
                if it["attempts"] < MAX_ATTEMPTS:
                    it["at"] = now + RETRY_GAP
                    self.log("[recall] loi lan %d thread=%s msg=%s: %s" % (it["attempts"], it["thread_id"], it["msg_id"], str(e)[:120]))
                    with self._lock:
                        self._save_locked()
                    continue
                self.log("[recall] BO thread=%s msg=%s sau %d lan loi: %s" % (it["thread_id"], it["msg_id"], MAX_ATTEMPTS, str(e)[:120]))
            with self._lock:
                self._items = [i for i in self._items if i is not it]
                self._save_locked()
            done += 1
        return done

    def start(self, interval=1.0):
        if self._thread and self._thread.is_alive():
            return

        def loop():
            while not self._stop.wait(interval):
                try:
                    self.run_due()
                except Exception as e:  # noqa: BLE001 - vong hen khong duoc chet
                    self.log("[recall] vong hen loi: %s" % str(e)[:120])
        self._thread = threading.Thread(target=loop, daemon=True, name="recall-queue")
        self._thread.start()

    def stop(self):
        self._stop.set()
