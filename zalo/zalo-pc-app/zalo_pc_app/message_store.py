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
                # Cat bot: giu toi da max_per_thread tin moi nhat.
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
                out.append(item)
        return out

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
        return m.get("text") or m.get("file_name") or ""

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
                        return r[0], (m if isinstance(m, dict) else {})
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
