"""Durable message store (SQLite) — exe parity: local DB.

Bang chung bundle (Zalo PC 26.11.10): exe doc lich su 1-1 tu DB
SQLite local (`loadTopMessagesForConversation`) + API cloud
`getCloudMessage` — khong co endpoint HTTPS nao cho lich su 1-1.
App moi truoc day chi co Inbox RAM (mat tin khi restart). Store
nay ghi moi tin den qua sync (va tin gui di) xuong /data/messages.db
TRUOC/KEM khi dispatch webhook, de:
  - restart khong mat tin (webhook co the gui lai / lich su doc duoc),
  - lich su 1-1 doc tu DB thay vi "khong lay duoc".

Inbox RAM giu nguyen lam cache (khong xoa); DB la ban ghi ben,
chi doc lai khi can (history endpoint). Dedup theo cung khoa nhu
Inbox (id:<mid>:<sender> hoac ct:<sender>:<time>:<text>) de tin
nao cung chi luu mot lan. Moi thread giu toi da 5000 tin (cat bot
tin cu nhat). Ghi/doc khong bao gio nem loi ra caller: loi DB tra
False / [] va log dang loi (khong log noi dung tin).

DB thuoc ve mot tai khoan: set_account(uid) doi DB khi uid doi
(dang xuat roi dang nhap tai khoan khac) de lich su khong lan sang
tai khoan khac. Loi sqlite3.connect duoc bat o lan dung dau tien;
neu file DB hong thi ghi doc tra ve rong — app van chay bang RAM.
"""

import json
import os
import sqlite3
import threading
import time

FILENAME = "messages.db"
DEFAULT_MAX_PER_THREAD = 5000

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS meta ("
    "  key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS messages ("
    "  thread_type TEXT NOT NULL,"
    "  thread_id TEXT NOT NULL,"
    "  dedup_key TEXT NOT NULL,"
    "  sender_id TEXT NOT NULL DEFAULT '',"
    "  msg_id TEXT NOT NULL DEFAULT '',"
    "  global_msg_id TEXT NOT NULL DEFAULT '',"
    "  msg_type TEXT NOT NULL DEFAULT '',"
    "  content TEXT NOT NULL DEFAULT '',"
    "  ts REAL NOT NULL DEFAULT 0,"
    "  raw_json TEXT NOT NULL DEFAULT '{}',"
    "  PRIMARY KEY (thread_type, thread_id, dedup_key))",
    "CREATE INDEX IF NOT EXISTS idx_messages_thread_ts"
    " ON messages (thread_type, thread_id, ts DESC)",
    # Dau "da doc" tung hoi thoai: so tin chua doc = tin den co ts lon hon
    # moc nay. Ben qua restart (Inbox trong RAM thi khong).
    "CREATE TABLE IF NOT EXISTS reads ("
    "  thread_type TEXT NOT NULL, thread_id TEXT NOT NULL,"
    "  ts REAL NOT NULL DEFAULT 0,"
    "  PRIMARY KEY (thread_type, thread_id))",
)


RECALLED_TEXT = "Tin nhắn đã được thu hồi"


def recalled_copy(m):
    """Ban thay the cho tin da thu hoi: giu id/nguoi gui/gio/huong, bo chu va tep; raw chi con cac ma dinh danh."""
    raw = m.get("raw") if isinstance(m.get("raw"), dict) else {}
    return {"id": m.get("id", ""), "client_id": m.get("client_id", ""), "sender_id": m.get("sender_id", ""), "sender_name": m.get("sender_name", ""),
            "text": RECALLED_TEXT, "time": m.get("time", 0), "kind": "system", "file_name": "", "direction": m.get("direction"),
            "is_self": bool(m.get("is_self")), "recalled": True, "raw": {k: raw[k] for k in ("msgId", "cliMsgId", "uidFrom", "ts") if k in raw}}


def _id_match(gid, cid, thread_type, thread_id):
    """(menh de WHERE, tham so) tim tin trong MOT hoi thoai theo msgId (global) hoac cliMsgId — o cot msg_id/global_msg_id hoac trong raw_json."""
    pats = []
    for key, val in (("msgId", gid), ("cliMsgId", cid)):
        if val:
            pats += ['%"' + key + '": "' + val + '"%', '%"' + key + '": ' + val + ',%', '%"' + key + '": ' + val + '}%']
    conds = ["msg_id IN (?,?)", "global_msg_id IN (?,?)"] + ["raw_json LIKE ?"] * len(pats)
    args = [thread_type, thread_id, gid or "-", cid or "-", gid or "-", cid or "-"] + pats
    return "thread_type=? AND thread_id=? AND (" + " OR ".join(conds) + ")", args


PREVIEW_LABELS = {"video": "Video", "sticker": "Nhãn dán", "link": "Liên kết", "system": "Thông báo"}   # nhãn xem trước cho tin không phải chữ


class MessageStore:
    """SQLite message store trong thu muc /data. Thread-safe
    (mot khoa, mot connection check_same_thread=False)."""

    def __init__(self, path, max_per_thread=DEFAULT_MAX_PER_THREAD):
        self.path = path
        self.max_per_thread = max_per_thread
        self._lock = threading.Lock()
        self._conn = None
        self._usable = None  # None = chua thu, False = hong
        self._account_uid = ""

    def _connect(self):
        """Mo DB (lazy) + tao schema. Tra False neu khong mo duoc
        (vd thu muc chi doc / file hong o muc mo)."""
        if self._usable is False:
            return False
        if self._conn is not None:
            return True
        try:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            had_reads = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reads'"
            ).fetchone() is not None
            for stmt in _SCHEMA:
                conn.execute(stmt)
            # Su kien `chat.delete` tung bi luu nhu tin chu (13/11: giao dien in nguyen [{'type': 1, 'actionType': 1, ...}]): don sach.
            conn.execute("DELETE FROM messages WHERE raw_json LIKE '%\"msgType\": \"chat.delete\"%'")
            if not had_reads:
                # Lan dau co bang `reads`: tin cu coi nhu da doc, de khong
                # bao hang tram tin chua doc tu lich su co san.
                conn.execute(
                    "INSERT OR REPLACE INTO reads (thread_type, thread_id, ts)"
                    " SELECT thread_type, thread_id, MAX(ts) FROM messages"
                    " GROUP BY thread_type, thread_id")
            conn.commit()
            self._conn = conn
            row = conn.execute(
                "SELECT value FROM meta WHERE key='account_uid'"
            ).fetchone()
            self._account_uid = row[0] if row else ""
            self._usable = True
            return True
        except (OSError, sqlite3.Error):
            self._conn = None
            self._usable = False
            return False

    def set_account(self, uid):
        """Gan DB cho mot tai khoan. Neu DB dang thuoc ve tai khoan
        khac thi xoa sach tin (tranh lan lich su sang tai khoan
        khac). Tra False neu DB khong dung duoc."""
        uid = str(uid or "")
        if not uid:
            return True
        with self._lock:
            if not self._connect():
                return False
            if self._account_uid and self._account_uid != uid:
                try:
                    self._conn.execute("DELETE FROM messages")
                    self._conn.commit()
                except sqlite3.Error:
                    return False
            self._account_uid = uid
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value)"
                    " VALUES ('account_uid', ?)", (uid,))
                self._conn.commit()
            except sqlite3.Error:
                return False
            return True

    def record(self, thread_type, thread_id, msg):
        """Ghi mot tin (dict da chuan hoa nhu Inbox) xuong DB.
        Tra True neu ghi moi, False neu trung (dedup) hoac loi.
        Khong bao gio nem loi."""
        thread_type = str(thread_type or "")
        thread_id = str(thread_id or "")
        if not thread_type or not thread_id \
                or not isinstance(msg, dict):
            return False
        try:
            from .sync_poll import Inbox
            dedup = Inbox._key(msg)
        except Exception:  # noqa: BLE001
            dedup = ""
        if not dedup:
            return False
        try:
            raw_json = json.dumps(msg, ensure_ascii=False)
        except (TypeError, ValueError):
            raw_json = json.dumps({
                "id": msg.get("id") or msg.get("client_id") or "",
                "sender_id": str(msg.get("sender_id") or ""),
                "text": msg.get("text") or "",
                "time": msg.get("time") or 0,
                "kind": msg.get("kind") or "",
                "file_name": msg.get("file_name") or "",
            }, ensure_ascii=False)
        with self._lock:
            if not self._connect():
                return False
            try:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO messages"
                    " (thread_type, thread_id, dedup_key, sender_id,"
                    "  msg_id, global_msg_id, msg_type, content, ts,"
                    "  raw_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (thread_type, thread_id, dedup,
                     str(msg.get("sender_id") or ""),
                     str(msg.get("id") or msg.get("client_id") or ""),
                     str(msg.get("global_msg_id") or ""),
                     str(msg.get("msg_type") or msg.get("kind") or ""),
                     str(msg.get("text") or msg.get("file_name") or ""),
                     float(msg.get("time") or 0) or 0,
                     raw_json))
                self._conn.commit()
                if cur.rowcount == 0:
                    return False
                # Cat bot: giu toi da max_per_thread tin moi nhat (0 = khong cat; cai dat o retention.py).
                if self.max_per_thread and self.max_per_thread > 0:
                    self._conn.execute(
                        "DELETE FROM messages WHERE rowid IN ("
                        " SELECT rowid FROM messages"
                        " WHERE thread_type=? AND thread_id=?"
                        " ORDER BY ts DESC, rowid DESC"
                        " LIMIT -1 OFFSET ?)",
                        (thread_type, thread_id, self.max_per_thread))
                    self._conn.commit()
                return True
            except sqlite3.Error:
                return False

    def upgrade_media(self, thread_type, thread_id, msgs):
        """Nâng cấp các tin ĐÃ nhập dạng chữ thành ảnh/tệp khi bản nhập mới giải được link (BinNet). CHỈ chạm dòng đang là 'text' và cùng khoá
        chống trùng; không thêm tin mới, không đụng tin ảnh/tệp/hệ thống đã có. Trả số dòng được nâng cấp. Không bao giờ ném lỗi."""
        thread_type, thread_id = str(thread_type or ""), str(thread_id or "")
        media = [m for m in (msgs or []) if isinstance(m, dict) and m.get("kind") in ("photo", "file") and m.get("file_url")]
        if not thread_type or not thread_id or not media:
            return 0
        from .sync_poll import Inbox
        done = 0
        with self._lock:
            if not self._connect():
                return 0
            try:
                for msg in media:
                    dedup = Inbox._key(msg)
                    if not dedup:
                        continue
                    cur = self._conn.execute(
                        "UPDATE messages SET msg_type=?, content=?, raw_json=? WHERE thread_type=? AND thread_id=? AND dedup_key=? AND msg_type='text'",
                        (str(msg["kind"]), str(msg.get("text") or msg.get("file_name") or ""), json.dumps(msg, ensure_ascii=False),
                         thread_type, thread_id, dedup))
                    done += cur.rowcount
                self._conn.commit()
            except sqlite3.Error:
                try:
                    self._conn.rollback()
                except sqlite3.Error:
                    pass
                return 0
        return done

    def bulk_record(self, thread_type, thread_id, msgs):
        """Ghi nhieu tin trong MOT giao dich (nhap lich su tu dien thoai). Khong cat theo gioi han (retention.py lo). Cung khoa chong trung voi
        record() nen chay lai khong nhan doi. Tin nhap vao duoc coi la DA DOC (dau «da doc» cua hoi thoai nang len moc tin moi nhat vua nhap).
        Tra ve (them_moi, trung_hoac_bo_qua). Khong bao gio nem loi."""
        thread_type, thread_id = str(thread_type or ""), str(thread_id or "")
        msgs = [m for m in (msgs or []) if isinstance(m, dict)]
        if not thread_type or not thread_id or not msgs:
            return 0, len(msgs)
        from .sync_poll import Inbox
        ins = skip = 0
        newest = 0.0
        with self._lock:
            if not self._connect():
                return 0, len(msgs)
            try:
                for msg in msgs:
                    dedup = Inbox._key(msg)
                    if not dedup:
                        skip += 1
                        continue
                    ts = float(msg.get("time") or 0) or 0
                    cur = self._conn.execute(
                        "INSERT OR IGNORE INTO messages (thread_type, thread_id, dedup_key, sender_id, msg_id, global_msg_id, msg_type, content, ts, raw_json)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (thread_type, thread_id, dedup, str(msg.get("sender_id") or ""), str(msg.get("id") or msg.get("client_id") or ""),
                         str(msg.get("global_msg_id") or ""), str(msg.get("msg_type") or msg.get("kind") or ""),
                         str(msg.get("text") or msg.get("file_name") or ""), ts, json.dumps(msg, ensure_ascii=False)))
                    if cur.rowcount:
                        ins += 1
                        newest = max(newest, ts)
                    else:
                        skip += 1
                if newest:
                    self._conn.execute(
                        "INSERT INTO reads (thread_type, thread_id, ts) VALUES (?,?,?)"
                        " ON CONFLICT(thread_type, thread_id) DO UPDATE SET ts = MAX(ts, excluded.ts)", (thread_type, thread_id, newest))
                self._conn.commit()
            except sqlite3.Error:
                try:
                    self._conn.rollback()
                except sqlite3.Error:
                    pass
                return 0, len(msgs)
        return ins, skip

    def recall(self, thread_type, thread_id, global_id="", cli_id=""):
        """THU HOI (nguoi khac/dien thoai thu hoi tin): thay tin goc bang dau «Tin nhắn đã được thu hồi» va XOA chu/URL goc khoi DB. Tim theo
        msgId (global) hoac cliMsgId. Tra ve danh sach `id` cac tin da doi ([] neu khong co tin goc). Khong bao gio nem loi."""
        gid, cid = str(global_id or "").strip(), str(cli_id or "").strip()
        thread_type, thread_id = str(thread_type or ""), str(thread_id or "")
        if not (gid or cid) or not thread_type or not thread_id:
            return []
        where, args = _id_match(gid, cid, thread_type, thread_id)
        changed = []
        with self._lock:
            if not self._connect():
                return []
            try:
                rows = self._conn.execute(
                    "SELECT dedup_key, raw_json FROM messages WHERE " + where, args).fetchall()
                for dedup, rj in rows:
                    try:
                        m = json.loads(rj)
                    except ValueError:
                        continue
                    raw = m.get("raw") if isinstance(m.get("raw"), dict) else {}
                    if m.get("recalled") or raw.get("msgType") == "chat.undo":
                        continue
                    new = recalled_copy(m)
                    self._conn.execute("UPDATE messages SET content=?, msg_type='system', raw_json=? WHERE thread_type=? AND thread_id=? AND dedup_key=?",
                                       (RECALLED_TEXT, json.dumps(new, ensure_ascii=False), thread_type, thread_id, dedup))
                    changed.append(str(m.get("id") or ""))
                self._conn.commit()
            except sqlite3.Error:
                return changed
        return changed

    def forget(self, thread_type, thread_id, global_id="", cli_id=""):
        """XOA han mot tin (Zalo bao `chat.delete`: chinh minh xoa / hen gio xoa). Khac recall: khong de lai dau «da thu hoi».
        Tra ve danh sach `id` cac tin da xoa ([] neu khong co). Khong bao gio nem loi."""
        gid, cid = str(global_id or "").strip(), str(cli_id or "").strip()
        thread_type, thread_id = str(thread_type or ""), str(thread_id or "")
        if not (gid or cid) or not thread_type or not thread_id:
            return []
        where, args = _id_match(gid, cid, thread_type, thread_id)
        with self._lock:
            if not self._connect():
                return []
            try:
                rows = self._conn.execute("SELECT dedup_key, msg_id FROM messages WHERE " + where, args).fetchall()
                for dedup, _mid in rows:
                    self._conn.execute("DELETE FROM messages WHERE thread_type=? AND thread_id=? AND dedup_key=?", (thread_type, thread_id, dedup))
                self._conn.commit()
            except sqlite3.Error:
                return []
        return [str(mid) for _d, mid in rows if mid]

    def prune(self, keep_days, max_per_thread, now=None):
        """Xoa tin cu hon keep_days ngay va cat moi hoi thoai con max_per_thread tin moi nhat (0 = bo qua buoc do). Xoa nhieu thi thu nho
        tep DB (checkpoint + VACUUM). Tra ve so tin da xoa. Khong bao gio nem loi."""
        now = float(now if now is not None else time.time())
        deleted = 0
        with self._lock:
            if not self._connect():
                return 0
            try:
                if keep_days:
                    deleted += self._conn.execute("DELETE FROM messages WHERE ts > 0 AND ts < ?", (now - keep_days * 86400,)).rowcount
                if max_per_thread:
                    over = self._conn.execute("SELECT thread_type, thread_id FROM messages GROUP BY thread_type, thread_id HAVING COUNT(*) > ?",
                                              (max_per_thread,)).fetchall()
                    for ttype, tid in over:
                        deleted += self._conn.execute(
                            "DELETE FROM messages WHERE rowid IN (SELECT rowid FROM messages WHERE thread_type=? AND thread_id=?"
                            " ORDER BY ts DESC, rowid DESC LIMIT -1 OFFSET ?)", (ttype, tid, max_per_thread)).rowcount
                self._conn.commit()
                if deleted:
                    self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    if deleted >= 500:
                        self._conn.execute("VACUUM")
            except sqlite3.Error:
                pass
        return deleted

    def stats(self):
        """{rows, threads, oldest_ts, db_bytes} — dung cho trang «Du lieu va tu xoa». Khong bao gio nem loi."""
        out = {"rows": 0, "threads": 0, "oldest_ts": 0, "db_bytes": 0}
        with self._lock:
            if self._connect():
                try:
                    rows, threads, oldest = self._conn.execute(
                        "SELECT COUNT(*), COUNT(DISTINCT thread_type || '|' || thread_id), MIN(CASE WHEN ts > 0 THEN ts END) FROM messages").fetchone()
                    out.update(rows=rows or 0, threads=threads or 0, oldest_ts=oldest or 0)
                except sqlite3.Error:
                    pass
        for suffix in ("", "-wal", "-shm"):
            try:
                out["db_bytes"] += os.path.getsize(self.path + suffix)
            except OSError:
                pass
        return out

    def messages_for(self, thread_type, thread_id, limit=50):
        """Tin cua mot thread, moi nhat truoc (dang dict da chuan
        hoa nhu Inbox). Tra [] neu DB khong dung duoc / khong co
        tin. Khong bao gio nem loi."""
        try:
            limit = int(limit or 50)
        except (TypeError, ValueError):
            limit = 50
        if limit <= 0:
            return []
        with self._lock:
            if not self._connect():
                return []
            try:
                rows = self._conn.execute(
                    "SELECT raw_json FROM messages"
                    " WHERE thread_type=? AND thread_id=?"
                    " ORDER BY ts DESC, rowid DESC LIMIT ?",
                    (str(thread_type or ""), str(thread_id or ""),
                     limit)).fetchall()
            except sqlite3.Error:
                return []
        out = []
        for (raw_json,) in rows:
            try:
                item = json.loads(raw_json)
            except ValueError:
                continue
            if isinstance(item, dict):
                out.append(self._heal(item))
        return out

    @staticmethod
    def _heal(m):
        """Tin luu TRUOC khi app biet ve tin he thong (binh chon moi, thu hoi...): chu rong + kind text -> tinh lai tu `raw`."""
        if not isinstance(m, dict) or (m.get("kind") or "text") not in ("text", "system"):
            return m
        placeholder = m.get("text") == "sendBubbleMessage"             # title gia cua ban ghi cuoc goi: tin luu dang «text» HOAC «system» (anh 12/11) deu phai tinh lai
        if (m.get("text") and not placeholder) or ((m.get("kind") or "text") == "system" and not placeholder):
            return m
        raw = m.get("raw")
        if isinstance(raw, dict) and raw:
            from . import chat as chat_mod              # nap muon: tranh vong import
            n = chat_mod.normalize_message(raw)
            if n.get("kind") == "system":
                return dict(m, text=n["text"], kind="system", call_record=n.get("call_record"))
        return m

    def _incoming(self, thread_type, thread_id):
        """(menh de SQL, tham so) chon tin DEN cua mot hoi thoai: 1-1 thi
        nguoi gui chinh la thread; nhom thi nguoi gui khac minh."""
        if thread_type == "group":
            return ("sender_id NOT IN (?, 'me', '')",
                    [self._account_uid or "-"])
        return "sender_id = ?", [thread_id]

    @staticmethod
    def _preview(m):
        kind = m.get("kind") or ""
        if kind == "photo":
            return "[Ảnh]"
        if kind == "voice":
            return "[Tin nhắn thoại]"
        if kind == "file":
            return "[Tệp] " + (m.get("file_name") or "")
        out = m.get("text") or m.get("file_name") or ""
        if not out and kind and kind != "text":
            # Tin không phải chữ mà không có nội dung (video, nhãn dán, liên kết…): luôn có nhãn loại, không để dòng xem trước trống («Bạn: »).
            # Loại chưa biết thì nhãn chung, không cần liệt kê hết.
            out = "[" + PREVIEW_LABELS.get(kind, "Tin đính kèm") + "]"
        return out

    def threads(self, thread_type=None, limit=500):
        """Moi hoi thoai co tin, moi nhat truoc: {thread_type, thread_id,
        count, incoming_count, unread, first_ts, last_ts, last_text,
        last_out, last_sender_name, name}. `name` = ten hien thi cua nguoi
        gui trong tin den gan nhat (Zalo gui kem dName) — cach lay ten
        nguoi la. Tra [] neu DB khong dung duoc. Khong bao gio nem loi."""
        try:
            limit = max(1, int(limit))
        except (TypeError, ValueError):
            limit = 500
        with self._lock:
            if not self._connect():
                return []
            try:
                sql = ("SELECT thread_type, thread_id, COUNT(*), MIN(ts), MAX(ts)"
                       " FROM messages")
                args = []
                if thread_type:
                    sql += " WHERE thread_type=?"
                    args.append(str(thread_type))
                sql += (" GROUP BY thread_type, thread_id"
                        " ORDER BY MAX(ts) DESC LIMIT ?")
                args.append(limit)
                rows = self._conn.execute(sql, args).fetchall()
                out = []
                for ttype, tid, cnt, first, last in rows:
                    cond, cargs = self._incoming(ttype, tid)
                    base = [ttype, tid] + cargs
                    inc = self._conn.execute(
                        "SELECT COUNT(*) FROM messages WHERE thread_type=?"
                        " AND thread_id=? AND " + cond, base).fetchone()[0]
                    read_ts = (self._conn.execute(
                        "SELECT ts FROM reads WHERE thread_type=? AND thread_id=?",
                        (ttype, tid)).fetchone() or (0,))[0]
                    unread = self._conn.execute(
                        "SELECT COUNT(*) FROM messages WHERE thread_type=?"
                        " AND thread_id=? AND " + cond + " AND ts > ?",
                        base + [read_ts]).fetchone()[0]

                    def _latest(extra, xargs):
                        r = self._conn.execute(
                            "SELECT sender_id, raw_json FROM messages WHERE"
                            " thread_type=? AND thread_id=?" + extra +
                            " ORDER BY ts DESC, rowid DESC LIMIT 1",
                            [ttype, tid] + xargs).fetchone()
                        if not r:
                            return "", {}
                        try:
                            m = json.loads(r[1])
                        except ValueError:
                            m = {}
                        return r[0], (self._heal(m) if isinstance(m, dict) else {})
                    last_sender, last_m = _latest("", [])
                    _, in_m = _latest(" AND " + cond, cargs)
                    raw = in_m.get("raw") if isinstance(in_m.get("raw"), dict) else {}
                    name = in_m.get("sender_name") or raw.get("dName") or ""
                    last_in = (last_sender == tid) if ttype != "group" else (
                        last_sender not in (self._account_uid, "me", ""))
                    out.append({
                        "thread_type": ttype, "thread_id": tid, "count": cnt,
                        "incoming_count": inc, "unread": unread,
                        "first_ts": first, "last_ts": last,
                        "last_text": self._preview(last_m), "last_out": not last_in,
                        "last_sender_name": last_m.get("sender_name") or "",
                        "name": name})
                return out
            except sqlite3.Error:
                return []

    def mark_read(self, thread_type, thread_id):
        """Dat dau da doc cho hoi thoai (moc = thoi diem hien tai hoac ts
        tin moi nhat, lay so lon hon). Khong bao gio nem loi."""
        thread_type, thread_id = str(thread_type or ""), str(thread_id or "")
        if not thread_type or not thread_id:
            return False
        with self._lock:
            if not self._connect():
                return False
            try:
                top = self._conn.execute(
                    "SELECT MAX(ts) FROM messages WHERE thread_type=?"
                    " AND thread_id=?", (thread_type, thread_id)).fetchone()[0] or 0
                self._conn.execute(
                    "INSERT OR REPLACE INTO reads (thread_type, thread_id, ts)"
                    " VALUES (?,?,?)", (thread_type, thread_id,
                                        max(float(top), time.time())))
                self._conn.commit()
                return True
            except sqlite3.Error:
                return False

    def count(self, thread_type=None, thread_id=None):
        """So tin da luu (toan DB hoac mot thread). Tra 0 neu loi."""
        with self._lock:
            if not self._connect():
                return 0
            try:
                if thread_type and thread_id:
                    row = self._conn.execute(
                        "SELECT COUNT(*) FROM messages"
                        " WHERE thread_type=? AND thread_id=?",
                        (str(thread_type), str(thread_id))).fetchone()
                else:
                    row = self._conn.execute(
                        "SELECT COUNT(*) FROM messages").fetchone()
                return int(row[0]) if row else 0
            except sqlite3.Error:
                return 0

    def clear(self):
        """Xoa sach tin (dang xuat). Tra False neu DB loi."""
        with self._lock:
            if not self._connect():
                return False
            try:
                self._conn.execute("DELETE FROM messages")
                self._conn.commit()
                return True
            except sqlite3.Error:
                return False
