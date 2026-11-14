"""Nhan file den: tai ve + luu giu nguyen ten goc + registry.

Bang chung dang tin (bundle Zalo PC 26.11.10,
compact-app-pc.5c0110a3a8749b3aacde.js):
  - Tin file den: msgType "share.file", ten file = content.title
    (noi them "." + params.fileExt neu thieu — xem
    _normalizeMessageJSON case MSG_FILE), URL tai = content.href,
    kich thuoc = params.fileSize, checksum md5 = params.checksum,
    fType 1 = file / 2 = folder. Ten hien thi de tai ve =
    message.title (ham getFileName cua download service).
  - Client that luu file tai ve duoi ten goc vao thu muc Downloads
    cua minh (getUserZaloDownloadsDir + saveDir "file"/"file/group"
    theo loai thread), kiem tra checksum sau khi tai (matchChecksum)
    va gioi han file qua lon (checkDownloadBigFileByCloud: > 4 GB
    thi tu choi — app dung cap 150 MB cua duong gui Node.js thay
    vi 4 GB, xem MAX_FILE_BYTES o chat.py).

Module nay:
  - FileInbox.download(msg, thread_type, thread_id): tai file tu
    msg["file_url"] ve <data>/downloads/<thread_type>_<thread_id>/
    <ten file goc> (ten goc giu nguyen; trung ten thi them
    " (1)", " (2)", ... truoc duoi — khong ghi de file cu).
  - Registry JSON (<data>/downloads/registry.json, 0600): moi tin
    file mot ban ghi {msg_id, thread, sender, file_name goc,
    local_path, size, checksum, status, ...} de UI tai xuong /
    gui lai ma khong can nho duong dan.
  - download_async: tai nen (khong chan kenh sync), loi chi ghi
    log + registry status "failed", khong bao gio nem loi ra
    caller.
  - Chi doc/ghi trong thu muc downloads cua app: ten file duoc
    sanitize (lay basename, bo ky tu dieu khien / "/" / "\\"),
    duong dan dich luon nam trong downloads (kiem tra sau khi
    noi duong dan); khong bao gio log noi dung file.

http_get_bytes(url, timeout) -> (status, bytes): do caller nap
(server dung transport cua phien Zalo — cookie zpw_sek; test
dung ham gia). Khong co getter -> download loi ro.
"""

import hashlib
import json
import os
import re
import threading
import time

from . import chat as chat_mod

# Thu muc + registry trong /data (giong webhooks.json / messages.db).
DOWNLOADS_DIRNAME = "downloads"
REGISTRY_FILENAME = "registry.json"

# Cap kich thuoc file nhan ve: giong cap gui cua Node.js
# (sendFile 150 MB — xem chat.MAX_FILE_BYTES). File lon hon bi
# tu choi ro rang truoc khi tai, khong crash, khong doi day RAM.
MAX_DOWNLOAD_BYTES = chat_mod.MAX_FILE_BYTES

# Timeout tai file (giay): file lon qua CDN co the cham; 120 s
# giong timeout doi event async cua duong gui.
DOWNLOAD_TIMEOUT_SECONDS = 120

# Cac kind duoc tu dong tai ve khi tin den (chi dinh kem co URL).
AUTO_DOWNLOAD_KINDS = ("file", "photo")

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class FileDownloadError(RuntimeError):
    """Loi tai file den (thieu URL / qua lon / mang / checksum) —
    message tieng Viet hien thang o UI/log, khong kem noi dung
    file hay secret."""


def sanitize_filename(name):
    """Ten file an toan de luu xuong dia: chi lay phan ten (bo
    moi thu muc cha — chan path traversal "../", "/abs", "a\\b"),
    bo ky tu dieu khien + khoang trang thua hai dau, bo dau cham
    o cuoi ten (Windows khong thich). Tra "" neu khong con gi
    (caller dung ten du phong theo msg id)."""
    if not name:
        return ""
    name = str(name)
    # Lay basename theo ca "/" lan "\\" (ten tu Windows co the
    # chua backslash).
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = _CONTROL_CHARS.sub("", name).strip().strip(".")
    name = name.strip()
    if name in ("", ".", ".."):
        return ""
    return name


def _split_name(name):
    """(stem, ext) de chen hau to trung ten: "a.pdf" -> ("a",
    ".pdf"); "a" -> ("a", ""); ".gitignore" -> (".gitignore", "")."""
    if name.startswith(".") and name.count(".") == 1:
        return name, ""
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        return name, ""
    return stem, "." + ext


def unique_path(directory, name):
    """Duong dan chua ton tai trong directory cho ten file: ten
    goc neu chua co; trung thi "ten (1).ext", "ten (2).ext", ...
    Khong bao gio ghi de file cu."""
    candidate = os.path.join(directory, name)
    if not os.path.exists(candidate):
        return candidate
    stem, ext = _split_name(name)
    n = 1
    while True:
        candidate = os.path.join(directory, "%s (%d)%s" % (stem, n, ext))
        if not os.path.exists(candidate):
            return candidate
        n += 1


def format_size(size):
    """Kich thuoc doc duoc ("967 B", "19,9 MB") cho UI/log."""
    try:
        n = int(size)
    except (TypeError, ValueError):
        return ""
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%.1f MB" % (n / 1048576.0)


class FileRegistry:
    """Registry file da nhan/tai ve (JSON, 0600, ghi atomic).

    Khoa: (thread_type, thread_id, msg_id). Moi ban ghi:
    {thread_type, thread_id, msg_id, sender_id, file_name (goc),
     file_url, local_path, size_bytes, expected_size, checksum,
     status ("downloaded"|"failed"|"pending"), error,
     downloaded_at (epoch giay)}. Chi luu metadata, khong luu
    noi dung file."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._entries = {}  # key -> record dict
        self._loaded = False

    def _key(self, thread_type, thread_id, msg_id):
        return "%s|%s|%s" % (thread_type, thread_id, msg_id)

    def _load_locked(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            for key, rec in data.items():
                if isinstance(rec, dict):
                    self._entries[str(key)] = rec

    def _save_locked(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._entries, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def record(self, entry):
        """Ghi/cap nhat mot ban ghi (entry phai co thread_type,
        thread_id, msg_id). Tra ban ghi da luu (ban sao)."""
        with self._lock:
            self._load_locked()
            key = self._key(entry.get("thread_type", ""),
                            entry.get("thread_id", ""),
                            entry.get("msg_id", ""))
            self._entries[key] = dict(entry)
            try:
                self._save_locked()
            except OSError:
                pass
            return dict(self._entries[key])

    def find(self, thread_type, thread_id, msg_id):
        """Ban ghi cua mot tin, hoac None. Ban sao — sua khong
        anh huong registry."""
        with self._lock:
            self._load_locked()
            rec = self._entries.get(
                self._key(thread_type, thread_id, msg_id))
            return dict(rec) if rec else None

    def list_for_thread(self, thread_type, thread_id):
        """Tat ca ban ghi cua mot thread, moi nhat truoc."""
        with self._lock:
            self._load_locked()
            out = [dict(rec) for rec in self._entries.values()
                   if rec.get("thread_type") == str(thread_type)
                   and rec.get("thread_id") == str(thread_id)]
        out.sort(key=lambda r: r.get("downloaded_at") or 0,
                 reverse=True)
        return out


class FileInbox:
    """Tai file den ve dia + registry.

    downloads_dir: <data>/downloads (duoc tao khi can).
    http_get_bytes(url, timeout) -> (status, bytes): GET tho
    tra ve bytes file; None = chua nap (download loi ro)."""

    def __init__(self, downloads_dir, http_get_bytes=None,
                 max_bytes=MAX_DOWNLOAD_BYTES):
        self.downloads_dir = downloads_dir
        self.registry = FileRegistry(
            os.path.join(downloads_dir, REGISTRY_FILENAME))
        self._http_get_bytes = http_get_bytes
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    # -- tai -------------------------------------------------------------
    def _thread_dir(self, thread_type, thread_id):
        """Thu muc cua mot thread trong downloads (ten an toan,
        chi chu/so/gach)."""
        safe_type = re.sub(r"[^A-Za-z0-9_-]", "_",
                           str(thread_type or "user")) or "user"
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_",
                         str(thread_id or "")) or "unknown"
        directory = os.path.join(self.downloads_dir,
                                 "%s_%s" % (safe_type, safe_id))
        os.makedirs(directory, exist_ok=True)
        return directory

    def _resolve_within(self, directory, name):
        """Duong dan dich nam CHAC CHAN trong directory (chan
        traversal ke ca khi ten da sanitize — phong thu lop 2)."""
        base = os.path.realpath(directory)
        target = os.path.realpath(os.path.join(directory, name))
        if os.path.commonpath([base, target]) != base:
            raise FileDownloadError(
                "ten file khong hop le: %s" % name)
        return target

    def download(self, msg, thread_type, thread_id):
        """Tai 1 tin file/anh den ve dia (dong bo). Tra ban ghi
        registry (status "downloaded"). Loi -> FileDownloadError
        (khong giu file hong / file nua chung). msg la dict da
        chuan hoa (normalize_message): can file_url, file_name,
        id; file_size/checksum neu co thi duoc kiem tra."""
        if not isinstance(msg, dict):
            raise FileDownloadError("tin nhan khong hop le")
        msg_id = str(msg.get("id") or msg.get("client_id") or "")
        if not msg_id:
            raise FileDownloadError("tin nhan thieu id — khong tai duoc")
        url = msg.get("file_url")
        if not url:
            raise FileDownloadError(
                "tin file \"%s\" khong co URL tai — Zalo khong gui "
                "kem duong dan file, khong tai duoc"
                % (msg.get("file_name") or msg_id))
        expected = msg.get("file_size")
        if expected is not None:
            try:
                expected = int(expected)
            except (TypeError, ValueError):
                expected = None
        if expected is not None and expected > self.max_bytes:
            raise FileDownloadError(
                "file \"%s\" qua lon (%s > %s) — khong tai"
                % (msg.get("file_name") or msg_id,
                   format_size(expected), format_size(self.max_bytes)))
        name = sanitize_filename(msg.get("file_name") or "")
        if not name:
            name = "file-%s" % msg_id
        # Da tai xong tin nay roi (gui lai / nhan trung) -> tra
        # lai ban ghi cu, khong tai lai, khong tao "ten (1)".
        existing = self.find(thread_type, thread_id, msg_id)
        if existing is not None \
                and existing.get("status") == "downloaded":
            return existing
        if self._http_get_bytes is None:
            raise FileDownloadError(
                "chua nap duong tai file (http_get_bytes) — khong "
                "tai duoc file \"%s\"" % name)
        try:
            status, data = self._http_get_bytes(
                url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        except FileDownloadError:
            raise
        except ValueError as e:
            # Transport gioi han kich thuoc (qua max_bytes) — loi
            # ro, khong phai loi mang.
            raise FileDownloadError(
                "tai file \"%s\" that bai: %s" % (name, e))
        except Exception as e:  # noqa: BLE001 - loi mang -> loi ro
            raise FileDownloadError(
                "tai file \"%s\" loi mang: %s" % (name, type(e).__name__))
        if status != 200:
            raise FileDownloadError(
                "tai file \"%s\" that bai (HTTP %s)" % (name, status))
        if not isinstance(data, (bytes, bytearray)):
            raise FileDownloadError(
                "tai file \"%s\": phan hoi khong phai du lieu file"
                % name)
        data = bytes(data)
        if len(data) > self.max_bytes:
            raise FileDownloadError(
                "file \"%s\" qua lon (%s > %s) — khong luu"
                % (name, format_size(len(data)),
                   format_size(self.max_bytes)))
        if expected is not None and len(data) != expected:
            raise FileDownloadError(
                "file \"%s\" tai ve thieu/du (%s, doi %s) — khong luu"
                % (name, format_size(len(data)), format_size(expected)))
        checksum = msg.get("file_checksum")
        if checksum:
            actual = hashlib.md5(data).hexdigest()
            if actual != str(checksum).lower():
                raise FileDownloadError(
                    "file \"%s\" sai checksum — du lieu tai ve "
                    "khong khop, khong luu" % name)
        with self._lock:
            directory = self._thread_dir(thread_type, thread_id)
            path = unique_path(directory, name)
            self._resolve_within(directory, os.path.basename(path))
            tmp = path + ".part"
            try:
                with open(tmp, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            except OSError as e:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise FileDownloadError(
                    "khong ghi duoc file \"%s\": %s" % (name, e))
        record = {
            "thread_type": str(thread_type),
            "thread_id": str(thread_id),
            "msg_id": msg_id,
            "sender_id": str(msg.get("sender_id") or ""),
            "sender_name": str(msg.get("sender_name") or ""),
            "file_name": name,
            "file_url": str(url),
            "local_path": path,
            "size_bytes": len(data),
            "expected_size": expected,
            "checksum": str(checksum or ""),
            "status": "downloaded",
            "error": "",
            "downloaded_at": time.time(),
        }
        self.registry.record(record)
        print("[file-in] da tai \"%s\" (%s) -> %s"
              % (name, format_size(len(data)), path), flush=True)
        return dict(record)

    def download_async(self, msg, thread_type, thread_id):
        """Tai nen (khong chan kenh sync): loi chi ghi log +
        registry status "failed", khong bao gio nem loi."""
        msg = dict(msg) if isinstance(msg, dict) else {}
        msg_id = str(msg.get("id") or msg.get("client_id") or "")
        thread = threading.Thread(
            target=self._download_async_worker,
            args=(msg, thread_type, thread_id, msg_id), daemon=True)
        thread.start()
        return thread

    def _download_async_worker(self, msg, thread_type, thread_id,
                               msg_id):
        try:
            self.download(msg, thread_type, thread_id)
        except FileDownloadError as e:
            try:
                self.registry.record({
                    "thread_type": str(thread_type),
                    "thread_id": str(thread_id),
                    "msg_id": msg_id,
                    "sender_id": str(msg.get("sender_id") or ""),
                    "sender_name": str(msg.get("sender_name") or ""),
                    "file_name": sanitize_filename(
                        msg.get("file_name") or "") or msg_id,
                    "file_url": str(msg.get("file_url") or ""),
                    "local_path": "",
                    "size_bytes": 0,
                    "expected_size": msg.get("file_size"),
                    "checksum": str(msg.get("file_checksum") or ""),
                    "status": "failed",
                    "error": str(e),
                    "downloaded_at": time.time(),
                })
            except Exception:
                pass
            print("[file-in] tai file that bai (%s): %s"
                  % (msg_id, e), flush=True)
        except Exception as e:  # noqa: BLE001 - worker khong chet
            print("[file-in] tai file loi khong ro (%s): %s"
                  % (msg_id, type(e).__name__), flush=True)

    # -- tra cuu -----------------------------------------------------------
    def save_local(self, thread_type, thread_id, msg_id, name, data, sender_id="me", source_url=""):
        """Lưu BẢN SAO tệp/ảnh/video do CHÍNH TA gửi (WebUI, dịch vụ HA…) để WebUI hiện xem trước và có nút tải về như tin đến (14/11/2026: tin gửi từ HA chỉ hiện
        «Tệp đính kèm» trống). Ghi vào registry như tệp đã tải (status downloaded). Quá cỡ/lỗi ghi -> FileDownloadError. Trả bản ghi registry."""
        msg_id = str(msg_id or "")
        if not msg_id:
            raise FileDownloadError("tin thieu id — khong luu duoc ban sao")
        data = bytes(data or b"")
        if not data:
            raise FileDownloadError("du lieu rong — khong luu ban sao")
        if len(data) > self.max_bytes:
            raise FileDownloadError("file qua lon (%s > %s) — khong luu ban sao" % (format_size(len(data)), format_size(self.max_bytes)))
        fname = sanitize_filename(name or "") or "file-%s" % msg_id
        with self._lock:
            directory = self._thread_dir(thread_type, thread_id)
            path = unique_path(directory, fname)
            self._resolve_within(directory, os.path.basename(path))
            tmp = path + ".part"
            try:
                with open(tmp, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            except OSError as e:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise FileDownloadError("khong ghi duoc ban sao \"%s\": %s" % (fname, e))
        record = {"thread_type": str(thread_type), "thread_id": str(thread_id), "msg_id": msg_id, "sender_id": str(sender_id or ""), "sender_name": "",
                  "file_name": fname, "file_url": str(source_url or ""), "local_path": path, "size_bytes": len(data), "expected_size": len(data),
                  "checksum": hashlib.md5(data).hexdigest(), "status": "downloaded", "error": "", "downloaded_at": time.time()}
        self.registry.record(record)
        return dict(record)

    def find(self, thread_type, thread_id, msg_id):
        """Ban ghi cua mot tin + file local con ton tai khong.
        Tra None neu chua co ban ghi / file da mat (khi do UI
        hien lai trang thai chua tai)."""
        rec = self.registry.find(thread_type, thread_id, msg_id)
        if rec is None:
            return None
        if rec.get("status") == "downloaded":
            path = rec.get("local_path") or ""
            if not path or not os.path.isfile(path):
                return None
        return rec

    def list_for_thread(self, thread_type, thread_id):
        """File da tai/thu tai cua mot thread (chi ban ghi co
        file local con ton tai, hoac loi — de UI hien dung)."""
        out = []
        for rec in self.registry.list_for_thread(thread_type,
                                                 thread_id):
            if rec.get("status") == "downloaded":
                path = rec.get("local_path") or ""
                if not path or not os.path.isfile(path):
                    continue
            out.append(rec)
        return out

    def read_local(self, thread_type, thread_id, msg_id):
        """(ban ghi, bytes) cua file da tai ve — dung cho gui lai.
        Loi -> FileDownloadError (chua tai / file mat / doc loi)."""
        rec = self.find(thread_type, thread_id, msg_id)
        if rec is None or rec.get("status") != "downloaded":
            raise FileDownloadError(
                "file chua tai ve xong (msg %s) — tai xong roi gui lai"
                % msg_id)
        path = rec.get("local_path") or ""
        try:
            with open(path, "rb") as fh:
                return rec, fh.read()
        except OSError as e:
            raise FileDownloadError(
                "khong doc duoc file da tai \"%s\": %s"
                % (rec.get("file_name") or msg_id, e))
