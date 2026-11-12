"""Dong bo LICH SU chat tu dien thoai (13/11/2026) — cach Zalo PC lay tin cu.

Nguon: bundle Zalo PC 26.11.10 (pull_mobile_msg 12000, cancel 12700, delete_snapshot 12003, get_backupmsginfo 12096) va zca-js fork 2.3.13
(apis/sync/*, crypto/zdb-cipher). Luong:
  1. PC sinh cap khoa RSA 2048, gui khoa CONG KHAI cho dien thoai (GET files-wpa /api/message/pull_mobile_msg, params AES
     {pc_name, public_key, from_seq_id, is_retry, min_seq_id, temp_key, imei}).
  2. Dien thoai HIEN HOP XAC NHAN cho nguoi dung. Dong y -> dien thoai dong goi ban sao luu va bao qua kenh dieu khien 99101:
     control act_type "syncmsgmb" | "transfer_msg", content.act = "user_confirm" | "syncmsg_info" | "transfer_error" | "transfer_after_login".
  3. syncmsg_info {url, encrypted_key, file_name, file_size, checksum_code, from_seq_id, is_full_transfer}: tai tep `.db.crypt`.
  4. encrypted_key (base64) giai bang khoa RIENG RSA (PKCS#1 v1.5) -> khoa AES-256 = 32 ky tu hex DAU, VIET HOA, nhu chuoi ASCII.
  5. Tep = khung ZDB4.0 ma hoa AES-256-CBC theo khoi doc lap 64 KB (IV = 0; thu lech dau 0 roi 4): header "ZDB4.0" + so muc (u32 BE o byte 14)
     + moi muc {u32 do dai ten, ten, u32 kich thuoc} + luong XZ chua cac tep SQLite `<uid>.db` / `group_<gid>.db`, noi tiep theo thu tu muc.
App mo dau den buoc 5 va GHI CAU TRUC bang (ten bang/cot/so dong, KHONG ghi noi dung) de bien soan bo nhap tin sau khi thay du lieu that.
Mac dinh KHONG tu nhap vao messages.db. Moi tep luu o <data>/history_sync/<thoi diem>/ (cung vung du lieu voi messages.db)."""

import base64
import ipaddress
import json
import lzma
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ZDB_MAGIC = b"ZDB4.0"
ZDB_CHUNK = 0x10000
MAX_DOWNLOAD_BYTES = 600 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
WAIT_PHONE_SECONDS = 15 * 60
PC_NAME = "Zalo-PC-App"

SYNC_ACT_TYPES = ("syncmsgmb", "transfer_msg")
STAGES = ("idle", "requesting", "waiting_phone", "downloading", "decrypting", "done", "error", "cancelled")
BUSY = ("requesting", "waiting_phone", "downloading", "decrypting")


class SyncError(RuntimeError):
    pass


# ---------------------------------------------------------------- mat ma (openssl CLI + so nguyen Python: container khong co thu vien `cryptography`)
def _openssl(args, data=None):
    try:
        p = subprocess.run(["openssl"] + list(args), input=data, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SyncError("openssl: %s" % e)
    if p.returncode != 0:
        raise SyncError("openssl %s: %s" % (args[0], (p.stderr or b"")[:200].decode("utf-8", "replace").strip()))
    return p.stdout


def generate_keypair(key_path):
    """Sinh khoa RSA 2048 vao key_path (0600). Tra ve khoa CONG KHAI dang SPKI DER base64 (dung dinh dang zca-js `publicKeyBase64`)."""
    _openssl(["genrsa", "-out", key_path, "2048"])
    os.chmod(key_path, 0o600)
    return base64.b64encode(_openssl(["rsa", "-in", key_path, "-pubout", "-outform", "DER"])).decode("ascii")


def _rsa_numbers(key_path):
    text = _openssl(["rsa", "-in", key_path, "-noout", "-text"]).decode("utf-8", "replace")

    def grab(name):
        m = re.search(r"^%s:\s*((?:[0-9a-f]{2}:?\s*)+)" % name, text, re.M)
        if not m:
            raise SyncError("khong doc duoc %s tu khoa RSA" % name)
        return int(re.sub(r"[^0-9a-f]", "", m.group(1)), 16)
    return grab("modulus"), grab("privateExponent")


def rsa_decrypt_pkcs1(key_path, cipher_bytes):
    """RSA PKCS#1 v1.5 giai ma bang so nguyen (giong rsaDecryptPkcs1Manual cua zca-js; OpenSSL 3 co the chan padding nay)."""
    n, d = _rsa_numbers(key_path)
    k = (n.bit_length() + 7) // 8
    if len(cipher_bytes) != k:
        raise SyncError("encrypted_key sai do dai (%d byte, can %d)" % (len(cipher_bytes), k))
    em = pow(int.from_bytes(cipher_bytes, "big"), d, n).to_bytes(k, "big")
    if em[0] != 0 or em[1] != 2:
        raise SyncError("RSA PKCS#1 v1.5: padding khong hop le (sai khoa rieng?)")
    sep = em.find(b"\x00", 2)
    if sep < 10:
        raise SyncError("RSA PKCS#1 v1.5: dau phan cach padding khong hop le")
    return em[sep + 1:]


def derive_zdb_aes_key(decrypted_rsa_bytes):
    """Khoa AES-256 = 32 ky tu hex DAU (viet hoa) cua byte da giai RSA, coi nhu chuoi ASCII (zca-js deriveZdbAesKey)."""
    upper = decrypted_rsa_bytes.hex().upper()
    if len(upper) < 32:
        raise SyncError("khoa giai RSA qua ngan (%d ky tu hex, can >= 32)" % len(upper))
    return upper[:32].encode("ascii")


def _cbc_zero_iv_chunked(key, data, chunk=ZDB_CHUNK):
    """AES-256-CBC, IV 0, moi khoi `chunk` byte DOC LAP — bang ECB toan bo roi XOR voi khoi ma truoc (khoi dau moi chunk XOR 0). Mot tien
    trinh openssl thay vi hang tram."""
    n = len(data) // 16 * 16
    if n < 16:
        raise SyncError("du lieu ZDB qua ngan")
    data = data[:n]
    dec = _openssl(["enc", "-d", "-aes-256-ecb", "-nopad", "-K", key.hex()], data)
    prev = bytearray(bytes(16) + data[:-16])
    for off in range(0, n, chunk):
        prev[off:off + 16] = bytes(16)
    return (int.from_bytes(dec, "big") ^ int.from_bytes(prev, "big")).to_bytes(n, "big")


def decrypt_zdb(buf, key):
    """Giai ma khung ZDB4.0; thu lech dau 0 roi 4 (zca-js decryptZdbBuffer). Sai khoa/khong phai ZDB -> SyncError."""
    for start in (0, 4):
        body = buf[start:]
        if len(body) // 16 * 16 < 16:
            continue
        head = _cbc_zero_iv_chunked(key, body[:ZDB_CHUNK])
        if head[:len(ZDB_MAGIC)] != ZDB_MAGIC:
            continue
        return _cbc_zero_iv_chunked(key, body)
    raise SyncError("sai khoa AES hoac tep khong phai khung ZDB4.0")


def parse_zdb_header(plain):
    """Muc luc ZDB: tra ve ([{name, size}], xz_offset)."""
    count_off = 14
    if len(plain) < count_off + 4 or plain[:len(ZDB_MAGIC)] != ZDB_MAGIC:
        raise SyncError("khong phai khung ZDB4.0 da giai ma")
    count = int.from_bytes(plain[count_off:count_off + 4], "big")
    if count > 100000:
        raise SyncError("so muc ZDB vuot gioi han an toan (%d)" % count)
    off, entries = count_off + 4, []
    for _ in range(count):
        if off + 4 > len(plain):
            raise SyncError("ZDB bi cat khi doc do dai ten")
        nlen = int.from_bytes(plain[off:off + 4], "big")
        if nlen > 4096 or off + 4 + nlen + 4 > len(plain):
            raise SyncError("ZDB bi cat/sai khi doc muc luc")
        raw = plain[off + 4:off + 4 + nlen].decode("utf-8", "replace").rstrip("\x00")
        name = re.split(r"[\\/]", raw)[-1] or raw
        if ".." in name or not re.fullmatch(r"[A-Za-z0-9_.\-]+", name):
            raise SyncError("ten tep khong an toan trong ZDB: %r" % raw[:60])
        entries.append({"name": name, "size": int.from_bytes(plain[off + 4 + nlen:off + 8 + nlen], "big")})
        off += 4 + nlen + 4
    return entries, off


def unpack_zdb(plain, out_dir):
    """Giai nen luong XZ va tach cac tep SQLite theo thu tu muc luc vao out_dir. Tra ve [{name, size, path}]."""
    entries, xz_off = parse_zdb_header(plain)
    dec = lzma.LZMADecompressor()
    raw = dec.decompress(plain[xz_off:], max_length=MAX_UNPACKED_BYTES)
    os.makedirs(out_dir, exist_ok=True)
    files, pos = [], 0
    for e in entries:
        part = raw[pos:pos + e["size"]]
        if len(part) != e["size"]:
            raise SyncError("ZDB: tep %s thieu du lieu (%d/%d byte)" % (e["name"], len(part), e["size"]))
        path = os.path.join(out_dir, e["name"])
        with open(path, "wb") as f:
            f.write(part)
        files.append({"name": e["name"], "size": e["size"], "path": path})
        pos += e["size"]
    return files


def inspect_sqlite(path):
    """Cau truc bang cua mot tep SQLite: {ten_bang: {"columns": [...], "rows": n}}. CHI ten va so dong, khong doc noi dung."""
    out = {}
    con = sqlite3.connect("file:%s?mode=ro" % urllib.parse.quote(path), uri=True)
    try:
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            cols = [r[1] for r in con.execute('PRAGMA table_info("%s")' % name.replace('"', '""'))]
            try:
                rows = con.execute('SELECT COUNT(*) FROM "%s"' % name.replace('"', '""')).fetchone()[0]
            except sqlite3.Error:
                rows = None
            out[name] = {"columns": cols, "rows": rows}
    finally:
        con.close()
    return out


# ---------------------------------------------------------------- tai ve
_BLOCKED_HOSTS = ("localhost", "metadata.google.internal")


def check_download_url(url, allow_local=False):
    """Chi http(s); chan IP noi bo/metadata (nhu zca-js downloadTransferSync, them chan IP rieng) — su kien den tu kenh Zalo da xac thuc
    nhung van khong tai ve dia chi noi bo."""
    p = urllib.parse.urlparse(str(url or ""))
    if p.scheme not in ("https", "http") or not p.hostname:
        raise SyncError("URL tai ve khong hop le (chi http/https)")
    if allow_local:
        return
    host = p.hostname.lower()
    if host in _BLOCKED_HOSTS:
        raise SyncError("URL tai ve tro toi dia chi noi bo bi chan")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
        raise SyncError("URL tai ve tro toi dia chi noi bo bi chan")


BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"


def _body_snippet(e):
    try:
        raw = e.read(300).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""
    return re.sub(r"\s+", " ", raw).strip()[:160]


def download_bytes(url, opener, cookie="", limit=MAX_DOWNLOAD_BYTES, timeout=120):
    """GET tep sao luu. 12/11 that: kieu «chi User-Agent app» bi may chu tra HTTP 400 nen thu lan luot (1) UA app, (2) header giong trinh duyet nhu
    zca-js getSyncData, (3) them cookie phien; dung o lan thanh cong. Tat ca that bai -> SyncError ghi MA HTTP + than phan hoi cua tung lan."""
    browser = {"User-Agent": BROWSER_UA, "Accept": "*/*", "Accept-Language": "en-US", "Cache-Control": "no-store, must-revalidate",
               "Pragma": "no-cache", "Expires": "0"}
    attempts = [("app", {"User-Agent": "zalo-pc-qr/1.0"}), ("trinh-duyet", browser)]
    if cookie:
        attempts.append(("trinh-duyet+cookie", dict(browser, Cookie="zpw_sek=%s" % cookie)))
    failures = []
    for name, headers in attempts:
        req = urllib.request.Request(url, headers=headers)
        try:
            with opener(req, timeout) as resp:
                length = resp.headers.get("Content-Length")
                if length and length.isdigit() and int(length) > limit:
                    raise SyncError("tep sao luu qua lon (%s byte)" % length)
                data = resp.read(limit + 1)
                if len(data) > limit:
                    raise SyncError("tep sao luu vuot gioi han %d byte" % limit)
                return data
        except urllib.error.HTTPError as e:
            snip = _body_snippet(e)                      # chi doc than MOT lan (doc lan hai se rong)
            failures.append("%s: HTTP %s%s" % (name, e.code, (" «%s»" % snip) if snip else ""))
        except urllib.error.URLError as e:
            raise SyncError("tai tep sao luu: %s" % (e.reason,))
    raise SyncError("tai tep sao luu that bai (%s)" % "; ".join(failures))


def describe_url(url):
    """Mo ta URL de GHI LOG ma khong lo chu ky: may chu + duong dan + TEN cac tham so (khong gia tri)."""
    p = urllib.parse.urlparse(str(url or ""))
    return "%s%s ?%s" % (p.hostname or "?", p.path[:80], ",".join(sorted(urllib.parse.parse_qs(p.query))) or "-")


# ---------------------------------------------------------------- su kien kenh dieu khien
def _scalars(d, limit=12):
    """Chi cac gia tri don gian ngan (so/bool/chuoi <= 80 ky tu), bo URL/khoa — de ghi chan doan ma khong lo bi mat."""
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            if len(out) >= limit:
                break
            if k in ("url", "encrypted_key", "public_key", "temp_key") or isinstance(v, (dict, list)):
                continue
            if isinstance(v, (int, float, bool)) or (isinstance(v, str) and len(v) <= 80):
                out[str(k)[:40]] = v
    return out


def extract_sync_events(data):
    """Tu payload kenh dieu khien -> [{act, act_type, data}] cho control act_type syncmsgmb/transfer_msg (zca-js control.handler)."""
    out = []
    controls = (data or {}).get("controls") if isinstance(data, dict) else None
    for ctl in controls or []:
        content = (ctl or {}).get("content") if isinstance(ctl, dict) else None
        if not isinstance(content, dict) or content.get("act_type") not in SYNC_ACT_TYPES:
            continue
        raw = content.get("data")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = {}
        out.append({"act": str(content.get("act") or ""), "act_type": content["act_type"], "data": raw if isinstance(raw, dict) else {}})
    return out


# ---------------------------------------------------------------- may trang thai
class HistorySync:
    def __init__(self, data_dir, services_factory, cookie_provider=None, imei_provider=None, opener=None, allow_local=False, log=None):
        self.root = os.path.join(data_dir, "history_sync")
        self.services_factory = services_factory
        self.cookie_provider = cookie_provider or (lambda: "")
        self.imei_provider = imei_provider or (lambda: "")
        self.opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))   # urlopen(req, X): X la `data`, phai noi ro timeout=
        self.allow_local = allow_local
        self.log = log or (lambda m: print("[history-sync] %s" % m, flush=True))
        self.lock = threading.Lock()
        self.state = {"stage": "idle", "detail": "", "updated_at": 0, "started_at": 0, "files": [], "schema": {}, "events": []}
        self._public_key = ""
        self._key_path = os.path.join(self.root, "key.pem")
        self._run_dir = ""
        self._thread = None

    # ---- tien ich
    def _set(self, stage=None, detail=None, **extra):
        with self.lock:
            if stage:
                self.state["stage"] = stage
            if detail is not None:
                self.state["detail"] = detail
            self.state.update(extra)
            self.state["updated_at"] = int(time.time())

    def status(self):
        with self.lock:
            st = json.loads(json.dumps(self.state))
        if st["stage"] == "waiting_phone" and st["started_at"] and time.time() - st["started_at"] > WAIT_PHONE_SECONDS:
            st["stale"] = True
            st["detail"] = "Đã chờ quá %d phút mà điện thoại chưa trả lời; có thể bạn chưa bấm xác nhận. Bấm Huỷ rồi thử lại." % (WAIT_PHONE_SECONDS // 60)
        st["busy"] = st["stage"] in BUSY
        st["can_retry"] = st["stage"] == "error" and self._last_saved() is not None
        return st

    def _note_event(self, ev):
        with self.lock:
            self.state["events"] = (self.state["events"] + [{"at": int(time.time()), "act": ev["act"], "act_type": ev["act_type"],
                                                                  "fields": _scalars(ev["data"])}])[-10:]

    def _payload(self, **extra):
        p = {"pc_name": PC_NAME, "public_key": self._public_key, "imei": self.imei_provider()}
        p.update(extra)
        return p

    # ---- hanh dong nguoi dung
    def start(self, from_seq_id=0):
        with self.lock:
            if self.state["stage"] in BUSY:
                raise SyncError("đang có một lượt đồng bộ chạy (%s)" % self.state["stage"])
        os.makedirs(self.root, mode=0o700, exist_ok=True)
        self._set("requesting", "Đang gửi yêu cầu tới điện thoại…", started_at=int(time.time()), files=[], schema={}, events=[])
        try:
            self._public_key = generate_keypair(self._key_path)
            svc = self.services_factory()
            svc._get(svc_domain(), "/api/message/pull_mobile_msg",
                     self._payload(from_seq_id=int(from_seq_id), is_retry=0, min_seq_id=0, temp_key=""))
        except Exception as e:  # noqa: BLE001 - hien ro cho nguoi dung
            self._set("error", "Gửi yêu cầu thất bại: %s" % str(e)[:200])
            self.log("pull_mobile_msg loi: %s" % str(e)[:200])
            raise
        self._set("waiting_phone", "Đã gửi. Hãy mở Zalo trên ĐIỆN THOẠI và bấm xác nhận đồng bộ tin nhắn.")
        self.log("da gui pull_mobile_msg (cho dien thoai xac nhan)")

    def cancel(self):
        if self.state["stage"] not in BUSY:
            return
        try:
            if self._public_key:
                svc = self.services_factory()
                svc._get(svc_domain(), "/api/message/cancel_pull_mobile_msg", self._payload())
        except Exception as e:  # noqa: BLE001 - huy cuc bo van tiep tuc
            self.log("cancel_pull_mobile_msg loi (bo qua): %s" % str(e)[:120])
        self._set("cancelled", "Đã huỷ.")

    # ---- su kien tu kenh dieu khien
    def on_event(self, ev):
        act = ev.get("act", "")
        data = ev.get("data") or {}
        self._note_event(ev)
        self.log("su kien act=%s act_type=%s truong=%s" % (act, ev.get("act_type"), sorted(_scalars(data))))
        pending = self.state["stage"] in ("waiting_phone", "requesting")
        # Khop voi YEU CAU CUA MINH nhu Zalo PC (isUserConfirm/isBackupSuccess... so khop pc_name + public_key): su kien cua yeu cau khac bi bo qua.
        if self._public_key and data.get("public_key") and data["public_key"] != self._public_key:
            self.log("bo qua su kien cua yeu cau khac (public_key khac)")
            return
        if act == "user_confirm":
            action = data.get("user_action")
            if not pending:
                return
            if action == 0:
                self._set("error", "Bạn đã TỪ CHỐI đồng bộ trên điện thoại.")
            elif action == 2:
                self._set(detail="Điện thoại đang khôi phục dữ liệu, đang chờ…")
            elif action in (1, 3):
                self._set(detail="Điện thoại đã đồng ý (user_action=%s), đang chuẩn bị gói dữ liệu…" % action)
            else:
                self._set(detail="Điện thoại đã phản hồi, đang chờ gói dữ liệu…")
        elif act == "transfer_error":
            code = data.get("error_code")
            status = data.get("status")
            if status in (1, 2) and code in (None, 0):               # PC: status 1 = dien thoai dang ban sao luu, 2 = dang ranh
                if pending:
                    self._set(detail="Điện thoại đang bận sao lưu…" if status == 1 else "Điện thoại đang rảnh, chờ bạn xác nhận…")
            elif self.state["stage"] in BUSY:                        # ma loi != 0, hoac dang la lao khong ro: bao loi that, khong nuot
                self._set("error", "Điện thoại báo lỗi khi sao lưu (%s)." % ("mã %s" % code if code not in (None, 0) else "không rõ mã"))
        elif act == "syncmsg_info":
            if not pending:
                self.log("bo qua syncmsg_info: khong co yeu cau nao dang cho")
                return
            self._set("downloading", "Đang tải bản sao lưu từ máy chủ Zalo…")
            self._thread = threading.Thread(target=self._process, args=(data,), daemon=True)
            self._thread.start()

    # ---- thu lai khong can xac nhan lai tren dien thoai
    def _last_saved(self):
        """(info, run_dir) cua su kien syncmsg_info gan nhat da luu (event.json); None neu chua co."""
        if not os.path.isdir(self.root):
            return None
        for name in sorted(os.listdir(self.root), reverse=True):
            d = os.path.join(self.root, name)
            f = os.path.join(d, "event.json")
            if os.path.isfile(f):
                try:
                    return json.load(open(f, encoding="utf-8")), d
                except (OSError, ValueError):
                    continue
        return None

    def latest_run_dir(self):
        """Thu muc dong bo moi nhat da co tep .db giai ma (de nhap vao khung chat); None neu chua co."""
        if not os.path.isdir(self.root):
            return None
        for name in sorted(os.listdir(self.root), reverse=True):
            d = os.path.join(self.root, name)
            if re.match(r"^\d{8}-\d{6}$", name) and os.path.isdir(d) and any(f.endswith(".db") for f in os.listdir(d)):
                return d
        return None

    def retry(self):
        """Tai/giai ma lai tu su kien da luu (khong hoi lai dien thoai). Link tai co han: het han thi phai Bat dau lai."""
        if self.state["stage"] in BUSY:
            raise SyncError("đang có một lượt đồng bộ chạy (%s)" % self.state["stage"])
        saved = self._last_saved()
        if not saved:
            raise SyncError("chưa có gói dữ liệu nào từ điện thoại để thử lại; hãy bấm Bắt đầu đồng bộ")
        info, run_dir = saved
        self._set("downloading", "Đang thử tải lại từ sự kiện đã lưu…", started_at=int(time.time()))
        self._thread = threading.Thread(target=self._process, args=(info, run_dir), daemon=True)
        self._thread.start()

    def _process(self, info, run_dir=None):
        try:
            check_download_url(info.get("url"), self.allow_local)
            enc_key = base64.b64decode(str(info.get("encrypted_key") or ""))
            if not enc_key:
                raise SyncError("syncmsg_info thiếu encrypted_key")
            if run_dir is None:
                run_dir = os.path.join(self.root, time.strftime("%Y%m%d-%H%M%S"))
                os.makedirs(run_dir, mode=0o700, exist_ok=True)
                # Luu NGAY su kien + khoa rieng cua yeu cau nay (0600): tai loi thi thu lai duoc, khong phai xac nhan lai tren dien thoai.
                for fname, payload in (("event.json", json.dumps(info).encode("utf-8")),
                                       ("key.pem", open(self._key_path, "rb").read() if os.path.exists(self._key_path) else b"")):
                    if payload:
                        fd = os.open(os.path.join(run_dir, fname), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                        with os.fdopen(fd, "wb") as f:
                            f.write(payload)
            self._run_dir = run_dir
            key_path = os.path.join(run_dir, "key.pem") if os.path.exists(os.path.join(run_dir, "key.pem")) else self._key_path
            self.log("tai ve: %s (khai bao %s byte)" % (describe_url(info.get("url")), info.get("file_size")))
            data = download_bytes(info["url"], self.opener, self.cookie_provider())
            with open(os.path.join(run_dir, "snapshot.db.crypt"), "wb") as f:
                f.write(data)
            meta = {k: info.get(k) for k in ("file_name", "file_size", "checksum_code", "from_seq_id", "is_full_transfer")}
            self._set("decrypting", "Đã tải %d KB, đang giải mã…" % (len(data) // 1024), meta=meta)
            key = derive_zdb_aes_key(rsa_decrypt_pkcs1(key_path, enc_key))
            files = unpack_zdb(decrypt_zdb(data, key), run_dir)
            schema = {f["name"]: inspect_sqlite(f["path"]) for f in files}
            for name, tables in schema.items():
                self.log("tep %s: %s" % (name, "; ".join("%s(%s)=%s dong" % (t, ",".join(v["columns"][:30]), v["rows"]) for t, v in tables.items())))
            self._set("done", "Xong: đã giải mã %d tệp SQLite vào %s." % (len(files), run_dir), run_dir=run_dir,
                      files=[{"name": f["name"], "size": f["size"]} for f in files], schema=schema)
            self._cleanup_remote()
        except Exception as e:  # noqa: BLE001 - mot loi bat ky -> trang thai error co thong bao ro
            self.log("xu ly ban sao luu loi: %s: %s" % (type(e).__name__, str(e)[:400]))
            self._set("error", "Không xử lý được bản sao lưu: %s" % str(e)[:400])

    def _cleanup_remote(self):
        """PC xoa ban chup tren may chu sau khi lay (delete_snapshot_mobile_msg 12003 {public_key, imei}); loi thi bo qua."""
        try:
            svc = self.services_factory()
            svc._get(svc_domain(), "/api/message/delete_snapshot_mobile_msg", {"public_key": self._public_key, "imei": self.imei_provider()})
        except Exception as e:  # noqa: BLE001
            self.log("delete_snapshot_mobile_msg loi (bo qua): %s" % str(e)[:120])


def svc_domain():
    """Domain tep (files-wpa) — khop Services._DOMAINS['file']."""
    from . import protocol
    return protocol.FILE_DOMAIN
