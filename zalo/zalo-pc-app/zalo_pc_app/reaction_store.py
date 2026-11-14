"""Kho cảm xúc theo tin nhắn (14/11/2026): WebUI hiện cảm xúc dưới bong bóng như Zalo PC.

Khoá: (loại hội thoại, mã hội thoại, msgId toàn cục) -> {người thả: biểu tượng Zalo}. Nguồn: sự kiện cảm xúc của kênh ctrl (`ctrl_poll.extract_reactions`) và cảm xúc do CHÍNH ta thả
(WebUI/HA). Biểu tượng rỗng = gỡ cảm xúc của người đó. JSON ghi nguyên tử, 0600, bộ nhớ có khoá; lỗi đọc/ghi không bao giờ làm hỏng luồng nhận tin."""
import json
import os
import threading


class ReactionStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._data = {}
        self._loaded = False

    @staticmethod
    def _key(thread_type, thread_id, msg_id):
        return "%s|%s|%s" % (thread_type, thread_id, msg_id)

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            if isinstance(d, dict):
                self._data = {str(k): dict(v) for k, v in d.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        except OSError:
            pass

    def add(self, thread_type, thread_id, msg_id, uid, icon):
        """Ghi/gỡ cảm xúc của `uid` trên tin. True nếu có thay đổi."""
        thread_type, thread_id, msg_id, uid = str(thread_type or ""), str(thread_id or ""), str(msg_id or ""), str(uid or "")
        if not (thread_type and thread_id and msg_id and uid):
            return False
        key = self._key(thread_type, thread_id, msg_id)
        icon = str(icon or "")
        with self._lock:
            self._load()
            cur = self._data.setdefault(key, {})
            if icon:
                if cur.get(uid) == icon:
                    return False
                cur[uid] = icon
            else:
                if uid not in cur:
                    return False
                del cur[uid]
                if not cur:
                    self._data.pop(key, None)
            self._save()
            return True

    def for_thread(self, thread_type, thread_id):
        """{msg_id: {uid: icon}} của một hội thoại (bản sao)."""
        prefix = "%s|%s|" % (thread_type, thread_id)
        with self._lock:
            self._load()
            return {k[len(prefix):]: dict(v) for k, v in self._data.items() if k.startswith(prefix) and v}
