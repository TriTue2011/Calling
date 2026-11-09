"""Chon che do SRTP cua cuoc goi di theo KET QUA THAT, khong tin tuyet doi
vao mot nguon (zca-js hay phan tich disassembly).

Hai che do, chua biet may that chap nhan cai nao (xem server.py
`_srtp_mode_for_call`):
  "off" — RTP tran, extendData.srtpMode=0 (luong mac dinh cua zca-js);
  "key" — ben goi tu sinh khoa SRTP, gui trong extendData.

Che do "auto" nho cach nao tung NHAN DUOC goi that tu ben kia: thanh cong
thi giu, that bai thi cuoc goi sau thu cach con lai. Ket qua luu o
<data_dir>/srtp_mode.json; file hong/thieu thi quay ve mac dinh, khong lam
server chet. Chi ghi che do va ket qua dung/sai — khong ghi khoa.
"""

import json
import os
import threading
import time

MODES = ("off", "key")
DEFAULT_MODE = "off"
_HISTORY_MAX = 20


def other(mode):
    return "key" if mode == "off" else "off"


class SrtpModeStore:
    def __init__(self, path, clock=time.time):
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._state = self._load()

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            raw = None
        state = {"preferred": DEFAULT_MODE, "history": []}
        if isinstance(raw, dict):
            if raw.get("preferred") in MODES:
                state["preferred"] = raw["preferred"]
            hist = raw.get("history")
            if isinstance(hist, list):
                state["history"] = [
                    h for h in hist if isinstance(h, dict)
                    and h.get("mode") in MODES][-_HISTORY_MAX:]
        return state

    def _save(self):
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh)
            os.replace(tmp, self._path)
        except OSError:
            pass            # khong luu duoc thi van dung bo nho trong tien trinh

    def pick(self):
        with self._lock:
            return self._state["preferred"]

    def record(self, mode, ok):
        """Ghi ket qua mot cuoc goi da nghe may. Tra ve che do uu tien moi."""
        if mode not in MODES:
            return self.pick()
        with self._lock:
            hist = self._state["history"]
            hist.append({"mode": mode, "ok": bool(ok),
                         "at": int(self._clock())})
            del hist[:-_HISTORY_MAX]
            if ok:
                self._state["preferred"] = mode
            elif self._state["preferred"] == mode:
                self._state["preferred"] = other(mode)
            self._save()
            return self._state["preferred"]

    def snapshot(self):
        with self._lock:
            return {"preferred": self._state["preferred"],
                    "history": list(self._state["history"])}
