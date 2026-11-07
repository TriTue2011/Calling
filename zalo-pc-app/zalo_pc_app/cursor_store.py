"""Persistent sync cursors (exe parity: localStorage saveActionId).

Bang chung bundle (compact-app-pc.5c0110a3a8749b3aacde.js, Zalo PC
26.11.10): exe ghi `lastActionId` / `lastActionIdOther` / per-queue
`lastId` xuong dia (localStorage) sau moi batch xu ly xong
(`_saveData`), luc mo lai doc lai va gui dung con tro da luu — nho
do server tra tin trong hang doi ke tu do (bu tin lo). Neu khong
luu, poll sau restart gui tu "1" va server phan hoi ra sao la chua
biet (co the chi gui tin moi, hoac reset — xem resetLastActionId).

File nay: sync_cursor.json trong thu muc /data (mode 0600, ghi
atomic tmp+replace nhu SessionStore/WebhookStore). Mot file giu ca
hai kenh (msg 99100 + ctrl 99101), moi kenh mot muc — giong exe
(idPoll chung duoc luu), trong khi app van giu PollCursor rieng
moi kenh de tranh race (xem ctrl_poll.py).

Con tro duoc dinh danh theo uid tai khoan: neu uid doi (dang xuat
roi dang nhap tai khoan khac) thi con tro cu bi bo, tra ve mac
dinh — tranh poll bang con tro cua tai khoan khac. Luu khong bao
gio nem loi (loi ghi chi tra False); doc file hong cung tra ve
mac dinh, khong lam chet poller.
"""

import json
import os
import threading

FILENAME = "sync_cursor.json"
MODE = 0o600

DEFAULT_STATE = {"lastActionId": "1", "lastActionIdOther": "1",
                 "queues": {}}


def _clean_state(raw):
    """Chi nhan dang dict co lastActionId/lastActionIdOther dang
    chuoi + queues dang dict {ten: {lastId}} — dang khac tra ve
    mac dinh, khong doan."""
    if not isinstance(raw, dict):
        return dict(DEFAULT_STATE)
    last = raw.get("lastActionId")
    other = raw.get("lastActionIdOther")
    queues = raw.get("queues")
    clean_queues = {}
    if isinstance(queues, dict):
        for name, info in queues.items():
            if isinstance(info, dict) and "lastId" in info:
                entry = {"lastId": str(info["lastId"])}
                ids = info.get("ids")
                if isinstance(ids, list):
                    entry["ids"] = [str(v) for v in ids[:10]]
                clean_queues[str(name)] = entry
    return {
        "lastActionId": str(last) if last not in (None, "") else "1",
        "lastActionIdOther": (str(other)
                              if other not in (None, "") else "1"),
        "queues": clean_queues,
    }


class SyncCursorStore:
    """Kho con tro sync tren dia: {"uid": str, "msg": state,
    "ctrl": state}. Giua bo nho + file dong bo duoi mot khoa de
    hai poller (msg + ctrl) ghi chung mot file khong race."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._data = {"uid": "", "msg": dict(DEFAULT_STATE),
                      "ctrl": dict(DEFAULT_STATE)}
        self._load_locked()

    def _load_locked(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        uid = raw.get("uid")
        self._data["uid"] = str(uid) if uid else ""
        for channel in ("msg", "ctrl"):
            if channel in raw:
                self._data[channel] = _clean_state(raw[channel])

    def load(self, channel, uid=""):
        """Con tro da luu cua kenh (ban sao). Tra ve mac dinh khi
        chua co file, file hong, hoac uid khac tai khoan da luu."""
        uid = str(uid or "")
        with self._lock:
            if uid and self._data.get("uid") \
                    and self._data["uid"] != uid:
                return dict(DEFAULT_STATE)
            state = self._data.get(channel)
            if not isinstance(state, dict):
                return dict(DEFAULT_STATE)
            out = dict(state)
            out["queues"] = dict(state.get("queues") or {})
            return out

    def save(self, channel, state, uid=""):
        """Ghi con tro cua kenh xuong dia (atomic). Tra False neu
        ghi loi — khong bao gio nem loi ra caller (poller). Bo nho
        chi cap nhat SAU KHI ghi file thanh cong, de trang thai
        trong bo nho luon khop voi dia (ghi loi thi load van tra
        ve con tro cu, khong phai con tro chua luu duoc)."""
        uid = str(uid or "")
        clean = _clean_state(state)
        with self._lock:
            new_data = {
                "uid": self._data.get("uid", ""),
                "msg": self._data.get("msg", dict(DEFAULT_STATE)),
                "ctrl": self._data.get("ctrl", dict(DEFAULT_STATE)),
            }
            if uid:
                new_data["uid"] = uid
            new_data[channel] = clean
        directory = os.path.dirname(self.path)
        try:
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, MODE)
            os.replace(tmp, self.path)
            try:
                os.chmod(self.path, MODE)
            except OSError:
                pass
        except OSError:
            return False
        with self._lock:
            self._data = new_data
        return True

    def clear(self):
        """Xoa file con tro (dang xuat): mo lai tu "1","1"."""
        with self._lock:
            self._data = {"uid": "", "msg": dict(DEFAULT_STATE),
                          "ctrl": dict(DEFAULT_STATE)}
        try:
            os.remove(self.path)
        except OSError:
            pass
