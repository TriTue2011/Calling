"""Chuyen giong noi thanh van ban bang Zalo AI (zca-js `voiceToText`, lenh 13394).

POST {ai_features}/api/aifeatures/voice2text  params {url: <URL tep ghi am>}  ->  {req_id}.
Ket qua KHONG tra ngay: Zalo day ve qua kenh dieu khien (ctrl 99101) mot control
act_type "voice2text" {req_id, text|content, err}. Module nay giu ket qua theo
req_id de (a) endpoint GET /api/voice2text/<req_id>, (b) POST /api/voice2text cho
phep cho toi `wait` giay roi tra thang van ban, (c) webhook cho HA.

Gioi han: chi chuyen duoc TIN NHAN THOAI da nam tren may chu Zalo (can URL tep).
Khong phai STT truc tiep tu mic — mic thoi gian thuc nen dung STT cua HA.
Van ban cuoc noi la du lieu rieng: khong bao gio ghi vao log.
"""

import json
import threading
import time

MAX_ENTRIES = 200


class V2TStore:
    def __init__(self, clock=time.time):
        self._cond = threading.Condition()
        self._items = {}              # req_id -> {"text","error","at"}
        self._order = []
        self._clock = clock

    def put(self, req_id, text="", error=None):
        req_id = str(req_id)
        with self._cond:
            if req_id not in self._items:
                self._order.append(req_id)
                while len(self._order) > MAX_ENTRIES:
                    self._items.pop(self._order.pop(0), None)
            self._items[req_id] = {"text": text or "", "error": error,
                                   "at": int(self._clock())}
            self._cond.notify_all()

    def get(self, req_id):
        with self._cond:
            item = self._items.get(str(req_id))
            return dict(item) if item else None

    def wait(self, req_id, timeout):
        """Cho ket qua toi `timeout` giay; tra None neu chua co."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        req_id = str(req_id)
        with self._cond:
            while req_id not in self._items:
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self._cond.wait(left)
            return dict(self._items[req_id])


def parse_event_data(data):
    """{req_id, text, error} tu content.data cua control voice2text."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return None
    if not isinstance(data, dict) or not data.get("req_id"):
        return None
    text = data.get("text")
    if not isinstance(text, str):
        text = data.get("content") if isinstance(data.get("content"), str) else ""
    err = data.get("err")
    return {"req_id": str(data["req_id"]), "text": text,
            "error": err if err not in (None, 0, "0") else None}
