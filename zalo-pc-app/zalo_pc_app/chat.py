"""Chat theo thread cho app Zalo kieu PC (module rieng, pha chat).

Nguon endpoint: bang lenh 231 muc trong bundle client PC that
(Zalo PC 26.11.10) + Bang 3 trong bao-cao-doi-chieu-addon.md.
Moi cuoc goi sau login deu la HTTPS voi query chung
`zpw_ver=695 & zpw_type=30` + `params=<AES-JSON ma hoa bang khoa
phien zpw_enk, AES-CBC IV 0, base64>` + cookie zpw_sek; response la
envelope hai lop (xem crypto.decode_postlogin_data) — giong het
contacts.py / signaling.py. Khong sua signaling.py hay body
requestcall (loi goi 114 do agent khac sua).

PIVOT 2026-11-05 (addon-embedded): gui tin / file / anh / voice,
typing / seen KHONG di duong PC truc tiep nua — tat ca qua sidecar
zalobot (addon_client.AddonClient -> zca-js sendMessage). Ly do: loi
send-114 — chat.py tu sinh clientId dang epoch-hex STRING, khong co
ttl; zca-js luon sinh clientId tu Date.now() (API-MAP §4.2). Cac ham
PC cu (send_text / send_file / send_photo / send_voice / send_typing
/ send_seen / history_group) DA XOA. Module nay chi con: kho tin da
gui trong phien (ChatStore), parse/build multipart (upload tu trinh
duyet), chuan hoa tin (normalize_message + normalize_addon_group_
message cho lich su nhom tu sidecar), va thong bao gioi han lich su
1-1 (khong co endpoint — API-MAP §6).

KHONG CO endpoint HTTPS (dung bia — xem Bang 3):
  - Danh sach hoi thoai: chi co DB local + kenh sync.
  - Lich su 1-1: KHONG co /api/message/history. Client PC that doc
    tu DB local + pull_mobile_msg (12000) / get_backupmsginfo
    (12096) / get_crossdb (12412). history_user() o day TRA VE
    thong bao gioi han chu khong goi endpoint khong ton tai; tin
    vua gui trong phien thi hien ngay nho ChatStore (bo nho RAM).
  - Nhan tin den: khong co endpoint polling; kenh sync/control
    chua lan het (diem mu lon nhat, can dot lan rieng / webhook O3).
  - Gui reaction: khong thay endpoint gui trong bang lenh.
  - E2EE: hoi thoai 1-1 bat E2EE co nhanh e2eeExt rieng; code nay
    gui bang 11151 thuong — neu server tra loi thi UI hien loi,
    khong gia dinh gui duoc.

Ghi chu ve `visibility` (nhom): truong rieng cua nhom, lay tu
getVisibility(convId) cua client that; gia tri that chua lan het
o dot nay. Mac dinh 0. Neu server tra loi ve visibility thi day
la nghi pham dau tien can kiem (xem BAO-CAO-CHAT.md).

Ghi chu ve ghi am: KHONG co endpoint HTTPS ghi am — ghi am la
native. UI thu bang MediaRecorder cua trinh duyet roi gui file
da ghi qua voicemp3/sendmp3. MediaRecorder cua Chrome/Firefox
thuong cho webm/opus (khong phai mp3); server forward dung file
nhan duoc, ten file giu nguyen — Zalo that co the tu choi file
khong phai mp3. Muon chac mp3 can them bo ma hoa mp3 (vd. wasm
lame) o buoc sau; xem BAO-CAO-CHAT.md.
"""

import time
import urllib.parse
import uuid

# Thong bao trung thuc khi khong lay duoc lich su 1-1 qua HTTPS.
HISTORY_USER_UNAVAILABLE = (
    "Lich su 1-1 chua lay duoc qua HTTPS: client Zalo PC that doc "
    "tin 1-1 tu DB local + dong bo tu dien thoai, khong co endpoint "
    "/api/message/history. Chi hien tin da gui/nhan trong phien nay."
)

# E2EE: hoi thoai 1-1 bat E2EE co the khong di duong sms thuong.
# Gui thu; neu server tu choi thi loi hien ro o UI, khong gia vo.
E2EE_NOTE = (
    "Hoi thoai 1-1 bat E2EE co nhanh ma hoa rieng (e2eeExt); "
    "neu gui that bai, day co the la nguyen nhan."
)


def build_multipart(fields, files):
    """Dung FormData multipart: fields {name: str}, files
    [(name, filename, mime, bytes)]. Tra ve (body_bytes,
    content_type). Server dung ham nay de gui file toi Zalo;
    test dung no de gui file toi server app."""
    boundary = "----zalo-pc-%s" % uuid.uuid4().hex
    out = bytearray()
    for name, value in (fields or {}).items():
        out += ("--%s\r\nContent-Disposition: form-data; "
                "name=\"%s\"\r\n\r\n%s\r\n"
                % (boundary, name, value)).encode("utf-8")
    for name, filename, mime, data in (files or []):
        out += ("--%s\r\nContent-Disposition: form-data; "
                "name=\"%s\"; filename=\"%s\"\r\n"
                "Content-Type: %s\r\n\r\n"
                % (boundary, name, filename,
                   mime or "application/octet-stream")).encode("utf-8")
        out += data + b"\r\n"
    out += ("--%s--\r\n" % boundary).encode("utf-8")
    return bytes(out), "multipart/form-data; boundary=%s" % boundary


def parse_multipart(body, content_type):
    """Parser multipart toi gian (1 file + vai field text) cho
    server app: tra ve (fields {name: str}, files {name:
    (filename, mime, bytes)}). Chi dung cho upload tu trinh duyet
    (khong phai de doc phan hoi Zalo)."""
    fields, files = {}, {}
    if not content_type or "multipart/form-data" not in content_type:
        return fields, files
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[len("boundary="):].strip().strip('"')
    if not boundary:
        return fields, files
    sep = ("--" + boundary).encode("utf-8")
    chunks = body.split(sep)
    for chunk in chunks[1:]:
        if chunk.startswith(b"--"):
            break
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        head, _, payload = chunk.partition(b"\r\n\r\n")
        if not _:
            continue
        headers = head.decode("utf-8", "replace")
        name, filename, mime = None, None, None
        for line in headers.split("\r\n"):
            low = line.lower()
            if low.startswith("content-disposition:"):
                for seg in line.split(";"):
                    seg = seg.strip()
                    if seg.startswith("name="):
                        name = seg[5:].strip().strip('"')
                    elif seg.startswith("filename="):
                        filename = seg[9:].strip().strip('"')
            elif low.startswith("content-type:"):
                mime = line.split(":", 1)[1].strip()
        if name is None:
            continue
        if filename is not None:
            files[name] = (filename, mime or "application/octet-stream",
                           payload)
        else:
            fields[name] = payload.decode("utf-8", "replace")
    return fields, files


def _norm_time(value):
    """timestamp ve giay (epoch): nhan ms neu thay gia tri ms."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n > 1e12:
        n = n / 1000.0
    return int(n)


def normalize_message(item, thread_type="user"):
    """Chuan hoa 1 tin (best-effort — shape lich su nhom that chua
    duoc thay truc tiep): {id, sender_id, text, time, kind, file_name,
    raw}. Cac key that co the gap: msgId/messageId/id; fromId/
    uidFrom/senderId; message/text/content/body; timestamp/
    createdAt/time/sentAt."""
    if not isinstance(item, dict):
        return {"id": "", "sender_id": "", "text": str(item),
                "time": None, "kind": "text", "file_name": "",
                "raw": item}
    text = (item.get("message") or item.get("text")
            or item.get("content") or item.get("body") or "")
    if isinstance(text, dict):
        text = text.get("msg") or text.get("title") or ""
    sender = (item.get("fromId") or item.get("uidFrom")
              or item.get("senderId") or item.get("sender") or "")
    msg_id = (item.get("msgId") or item.get("messageId")
              or item.get("id") or item.get("msg_id") or "")
    when = _norm_time(item.get("timestamp") or item.get("createdAt")
                      or item.get("time") or item.get("sentAt")
                      or item.get("ts"))
    kind = "text"
    file_name = (item.get("fileName") or item.get("file_name")
                 or item.get("title") or "")
    msg_type = str(item.get("msgType") or item.get("type") or "")
    if file_name or msg_type in ("file", "sharefile"):
        kind = "file"
    elif msg_type in ("photo", "image"):
        kind = "photo"
    elif msg_type in ("voice", "voicemp3", "mp3"):
        kind = "voice"
    return {"id": str(msg_id), "sender_id": str(sender),
            "text": str(text), "time": when, "kind": kind,
            "file_name": str(file_name), "raw": item}


class ChatStore:
    """Kho tin da gui trong phien (RAM, mat khi restart — giong
    call_log.CallLog). Dung de hien ngay tin vua gui + lam lich su
    tam cho 1-1 khi chua co endpoint HTTPS. Chi luu id/text/kind/
    ten file — khong luu noi dung file."""

    def __init__(self):
        self._sent = {}  # (thread_type, thread_id) -> [message, ...]

    def record_sent(self, thread_type, thread_id, message):
        key = (thread_type, str(thread_id))
        self._sent.setdefault(key, []).append(message)
        return message

    def sent_for(self, thread_type, thread_id):
        return list(self._sent.get((thread_type, str(thread_id)), []))

    def record_received(self, thread_type, thread_id, message):
        """Incoming message from the sidecar listener (via
        /api/addon/events): stored in the same per-thread list so
        history shows it next to sent messages."""
        return self.record_sent(thread_type, thread_id, message)

    def local_message(self, thread_type, thread_id, kind, text="",
                      file_name="", client_id="", msg_id=""):
        return {"id": str(msg_id or client_id),
                "client_id": str(client_id),
                "sender_id": "me", "text": text, "time": int(time.time()),
                "kind": kind, "file_name": file_name,
                "direction": "out", "status": "sent"}


def history_user_unavailable():
    """Lich su 1-1: KHONG co endpoint HTTPS — khong goi gi ca, tra
    thong bao gioi han de UI hien trung thuc (API-MAP §6: khong co
    route/history handler nao cho 1-1; zca-js cung khong co)."""
    return {"messages": [], "has_more": False,
            "unavailable": True, "notice": HISTORY_USER_UNAVAILABLE}


def normalize_addon_group_message(item):
    """Chuan hoa 1 tin trong lich su nhom tu sidecar
    (getGroupChatHistoryByAccount, API-MAP §6): moi item la mot
    GroupMessage {type, threadId, data:{msgId, uidFrom, content,
    ts, dName, msgType, ...}} — boc data ra roi dung
    normalize_message nhu cu. `dName` (da duoc sidecar enrich qua
    getUserInfo) giu lai o truong sender_name de UI hien ten."""
    if not isinstance(item, dict):
        return normalize_message(item, "group")
    data = item.get("data") if isinstance(item.get("data"), dict) else item
    flat = dict(data)
    flat.setdefault("threadId", item.get("threadId", ""))
    msg = normalize_message(flat, "group")
    msg["sender_name"] = str(data.get("dName") or "")
    return msg
