"""Chat theo thread cho app Zalo kieu PC (module rieng, pha chat).

Nguon endpoint: bang lenh 231 muc trong bundle client PC that
(Zalo PC 26.11.10) + Bang 3 trong bao-cao-doi-chieu-addon.md.
Moi cuoc goi sau login deu la HTTPS voi query chung
`zpw_ver=695 & zpw_type=30` + `params=<AES-JSON ma hoa bang khoa
phien zpw_enk, AES-CBC IV 0, base64>` + cookie zpw_sek; response la
envelope hai lop (xem crypto.decode_postlogin_data) — giong het
contacts.py / signaling.py. Khong sua signaling.py hay body
requestcall (loi goi 114 do agent khac sua).

Endpoint da dung (ma lenh trong ngoac):
  Gui text 1-1:  GET {chat-wpa}/api/message/sms (11151)
                 body {message, clientId, imei, toid, ttl}
  Gui text nhom: GET {group-wpa}/api/group/sendmsg (11163)
                 body {message, clientId, imei, visibility, grid, ttl}
  clientId la JSON NUMBER epoch-ms tang don dieu (NMlV.next() —
  xem protocol.new_client_id); ttl = ms tu xoa cua hoi thoai
  (0 = khong tu xoa). Code cu gui clientId dang string + thieu
  ttl — sai so voi client that, nghi pham so 1 cua loi 114
  (SERVICE-MAP.md §3.1).
  Lich su nhom:  GET {group-wpa}/api/group/history (11240)
                 body {grid, count}
  Dinh kem file 1-1: POST multipart {files-wpa}/api/message/
                 sharefile_full (11146), query params=<AES
                 {toid, clientId}> & type=2, FormData fileContent
  Dinh kem file nhom: POST multipart {files-wpa}/api/group/
                 sharefile_full (11191), params {grid, clientId},
                 & type=11
  Gui anh 1-1:   POST multipart {chat-wpa}/api/message/photo (11152)
                 FormData fileContent + params AES {clientId, desc,
                 width, height, toid}, & type=2
  Gui anh nhom:  POST multipart {group-wpa}/api/group/sendpt (11164)
                 params {clientId, desc, width, height, visibility,
                 grid}, & type=11
  Gui file ghi am 1-1: POST multipart {files-wpa}/api/message/
                 voicemp3 (11148), params {toid, clientId}, & type=2
  Gui file ghi am nhom: POST multipart {files-wpa}/api/group/
                 sendmp3 (11169), params {grid, clientId}, & type=11
  Dang go 1-1:   GET {chat-wpa}/api/message/typing (11144)
                 body {toid, destType, imei}
  Dang go nhom:  GET {group-wpa}/api/group/typing (11196)
                 body {grid, imei}
  Da xem 1-1:    GET {chat-wpa}/api/message/seen (11150)
  Da xem nhom:   GET {group-wpa}/api/group/seen (11167)
                 body {msg_ids: [...]} (1-1; nhom tuong tu)

KHONG CO endpoint HTTPS (dung bia — xem Bang 3):
  - Danh sach hoi thoai: chi co DB local + kenh sync.
  - Lich su 1-1: KHONG co /api/message/history. Client PC that doc
    tu DB local + pull_mobile_msg (12000) / get_backupmsginfo
    (12096) / get_crossdb (12412). history_user() o day TRA VE
    thong bao gioi han chu khong goi endpoint khong ton tai; tin
    vua gui trong phien thi hien ngay nho ChatStore (bo nho RAM).
  - Nhan tin den: khong co endpoint polling; kenh sync/control
    chua lan het (diem mu lon nhat, can dot lan rieng / webhook O3).
  - Gui reaction: xem services.add_reaction (REACTION domain,
    /api/message/reaction 12410 / /api/group/reaction 12411).
  - Gui video: chi co buoc upload (12058-12062), buoc send sau
    upload chua lan het — chua implement (SERVICE-MAP.md #75).
  - Gui card user thuong: chua lan rieng (chi co bien the OA
    forwardContactOA) — chua implement (SERVICE-MAP.md #71).
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

import json
import time
import urllib.parse
import uuid

from . import protocol
from .crypto import decode_postlogin_data, session_aes_encrypt

CHAT_DOMAIN = "https://chat-wpa.zalo.me"
FILES_DOMAIN = "https://files-wpa.zalo.me"
GROUP_DOMAIN = protocol.GROUP_DOMAIN

# type=2 (1-1) / type=11 (nhom) trong query cua cac loi goi kem
# file — loai dich, KHONG phai thread type 0/1 cua addon.
TYPE_FILE_USER = 2
TYPE_FILE_GROUP = 11

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


def _new_client_id():
    """clientId do client tu sinh: JSON NUMBER epoch-ms tang don
    dieu (NMlV.next() — xem protocol.new_client_id). Dung chung
    mot generator cho moi lan gui trong phien, giong client that."""
    return protocol.new_client_id()


def _url_with_params(base, path, body, zpw_enk, extra_query=None):
    """GET url: common params + params=<AES JSON> (giong
    contacts._url_with_params; quote safe='' de '/' trong base64
    thanh %2F nhu client that)."""
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    enc = session_aes_encrypt(zpw_enk, raw)
    params = protocol.common_params()
    if extra_query:
        params.update(extra_query)
    qs = urllib.parse.urlencode(params)
    return "%s%s?%s&params=%s" % (
        base, path, qs, urllib.parse.quote(enc, safe=""))


def _multipart_url(base, path, body, zpw_enk, file_type):
    """URL cho cac loi goi multipart kem file: common params +
    params=<AES JSON> & type=2 (1-1) / 11 (nhom)."""
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    enc = session_aes_encrypt(zpw_enk, raw)
    qs = urllib.parse.urlencode(protocol.common_params())
    return "%s%s?%s&params=%s&type=%d" % (
        base, path, qs, urllib.parse.quote(enc, safe=""), file_type)


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
    sender = (item.get("fromId") or item.get("uidFrom")
              or item.get("senderId") or item.get("sender") or "")
    msg_id = (item.get("msgId") or item.get("messageId")
              or item.get("id") or item.get("msg_id") or "")
    when = _norm_time(item.get("timestamp") or item.get("createdAt")
                      or item.get("time") or item.get("sentAt"))
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

    def local_message(self, thread_type, thread_id, kind, text="",
                      file_name="", client_id="", msg_id=""):
        return {"id": str(msg_id or client_id),
                "client_id": str(client_id),
                "sender_id": "me", "text": text, "time": int(time.time()),
                "kind": kind, "file_name": file_name,
                "direction": "out", "status": "sent"}


class Chat:
    """Client chat PC: gui text/file/anh/voice/link, lich su nhom,
    typing/seen. Transport giong signaling/contacts: http_get
    callable (url, timeout) -> (status, json) + .http_post_multipart
    (url, body_bytes, content_type, timeout) cho upload file +
    .http_post (url, form, timeout) cho POST form (send_link)."""

    def __init__(self, http_get, device_id, zpw_enk,
                 http_post_multipart=None, http_post=None):
        self.http_get = http_get
        self.device_id = device_id
        self.zpw_enk = zpw_enk
        if http_post_multipart is None:
            http_post_multipart = getattr(http_get,
                                          "http_post_multipart", None)
        self.http_post_multipart = http_post_multipart
        if http_post is None:
            http_post = getattr(http_get, "http_post", None)
        self.http_post = http_post

    # -- co so -----------------------------------------------------------
    def _unwrap(self, status, payload, where):
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("chat: %s network status=%s"
                               % (where, status))
        if payload.get("error_code") != 0:
            raise RuntimeError("chat: %s error_code=%s %s" % (
                where, payload.get("error_code"),
                payload.get("error_message", "")))
        return decode_postlogin_data(payload, self.zpw_enk)

    def _get(self, url, where):
        status, payload = self.http_get(url, timeout=30)
        return self._unwrap(status, payload, where)

    def _post_multipart(self, url, body_bytes, content_type, where):
        if self.http_post_multipart is None:
            raise RuntimeError(
                "chat: %s can thieu multipart transport" % where)
        status, payload = self.http_post_multipart(
            url, body_bytes, content_type, timeout=60)
        return self._unwrap(status, payload, where)

    def _post_form(self, domain, path, body, where):
        """POST form params=<AES JSON> (send_link): common params
        o query, params o form body — giong Services._post."""
        if self.http_post is None:
            raise RuntimeError(
                "chat: %s can thieu POST transport" % where)
        url = "%s%s?%s" % (domain, path, urllib.parse.urlencode(
            protocol.common_params()))
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        form = "params=" + urllib.parse.quote(
            session_aes_encrypt(self.zpw_enk, raw), safe="")
        status, payload = self.http_post(url, form, timeout=30)
        return self._unwrap(status, payload, where)

    # -- lich su ---------------------------------------------------------
    def history_group(self, grid, count=50):
        """GET {group-wpa}/api/group/history (11240), body
        {grid, count}. Tra ve {messages: [normalized], has_more,
        raw}. Shape that: data la dict {messages:[...], hasMore}
        hoac bare list."""
        url = _url_with_params(GROUP_DOMAIN, "/api/group/history",
                               {"grid": str(grid), "count": int(count)},
                               self.zpw_enk)
        data = self._get(url, "GET /api/group/history")
        has_more = False
        items = []
        if isinstance(data, dict):
            has_more = bool(data.get("hasMore", False))
            for key in ("messages", "msgs", "list", "data"):
                val = data.get(key)
                if isinstance(val, list):
                    items = val
                    break
        elif isinstance(data, list):
            items = data
        return {"messages": [normalize_message(it, "group")
                             for it in items],
                "has_more": has_more, "raw": data}

    def history_user_unavailable(self):
        """Lich su 1-1: KHONG co endpoint HTTPS — khong goi gi ca,
        tra thong bao gioi han de UI hien trung thuc."""
        return {"messages": [], "has_more": False,
                "unavailable": True, "notice": HISTORY_USER_UNAVAILABLE}

    # -- gui text --------------------------------------------------------
    def send_text(self, thread_type, thread_id, message,
                  visibility=0, ttl=0):
        """11151 (1-1) / 11163 (nhom). Body {message, clientId:
        NUMBER, imei, toid|grid, visibility (nhom), ttl} — ttl =
        ms tu xoa cua hoi thoai, 0 = khong tu xoa (SERVICE-MAP.md
        §3.1). Tra ve data giai ma + clientId de UI map tin dang
        gui."""
        if not message or not str(message).strip():
            raise ValueError("chat: message rong")
        client_id = _new_client_id()
        if thread_type == "group":
            body = {"message": message, "clientId": client_id,
                    "imei": self.device_id, "visibility": visibility,
                    "grid": str(thread_id), "ttl": int(ttl)}
            url = _url_with_params(GROUP_DOMAIN, "/api/group/sendmsg",
                                   body, self.zpw_enk)
            data = self._get(url, "GET /api/group/sendmsg")
        else:
            body = {"message": message, "clientId": client_id,
                    "imei": self.device_id, "toid": str(thread_id),
                    "ttl": int(ttl)}
            url = _url_with_params(CHAT_DOMAIN, "/api/message/sms",
                                   body, self.zpw_enk)
            data = self._get(url, "GET /api/message/sms")
        return {"data": data, "client_id": client_id}

    def send_link(self, thread_type, thread_id, href, message="",
                  title="", desc="", thumb="", visibility=0, ttl=0):
        """Gui link 1-1 POST /api/message/link (11286) / nhom POST
        /api/group/sendlink (11193). Body: {msg, href, title, desc,
        language, thumb (neu co), clientId NUMBER, toId|grid,
        mentionInfo, imei (nhom)} + buildParams (ttl). Cac truong
        src/type/media cua ham bundle chua lan duoc gia tri — KHONG
        gui (SERVICE-MAP.md §3.2, #72). mentionInfo nhom: "[]" khi
        khong co mention."""
        if not href or not str(href).strip():
            raise ValueError("chat: href rong")
        client_id = _new_client_id()
        body = {"msg": message or "", "href": href,
                "title": title or "", "desc": desc or "",
                "language": protocol.LANGUAGE,
                "clientId": client_id, "ttl": int(ttl)}
        if thumb:
            body["thumb"] = thumb
        if thread_type == "group":
            body.update({"grid": str(thread_id), "mentionInfo": "[]",
                         "visibility": visibility,
                         "imei": self.device_id})
            return {"data": self._post_form(
                GROUP_DOMAIN, "/api/group/sendlink", body,
                "POST /api/group/sendlink"),
                "client_id": client_id}
        body.update({"toId": str(thread_id), "mentionInfo": ""})
        return {"data": self._post_form(
            CHAT_DOMAIN, "/api/message/link", body,
            "POST /api/message/link"),
            "client_id": client_id}

    # -- gui file / anh / voice ------------------------------------------
    def send_file(self, thread_type, thread_id, filename, data,
                  mime="application/octet-stream"):
        """11146 (1-1) / 11191 (nhom): multipart fileContent."""
        client_id = _new_client_id()
        if thread_type == "group":
            url = _multipart_url(
                FILES_DOMAIN, "/api/group/sharefile_full",
                {"grid": str(thread_id), "clientId": client_id},
                self.zpw_enk, TYPE_FILE_GROUP)
            where = "POST /api/group/sharefile_full"
        else:
            url = _multipart_url(
                FILES_DOMAIN, "/api/message/sharefile_full",
                {"toid": str(thread_id), "clientId": client_id},
                self.zpw_enk, TYPE_FILE_USER)
            where = "POST /api/message/sharefile_full"
        body, ctype = build_multipart(
            {}, [("fileContent", filename, mime, data)])
        return {"data": self._post_multipart(url, body, ctype, where),
                "client_id": client_id}

    def send_photo(self, thread_type, thread_id, filename, data,
                   mime="image/jpeg", width=0, height=0, visibility=0):
        """11152 (1-1) / 11164 (nhom): multipart fileContent +
        params AES {clientId, desc, width, height, toid|grid}.
        width/height lay tu anh that o UI; 0 = khong biet (best
        effort — server that co the doi kich thuoc that)."""
        client_id = _new_client_id()
        if thread_type == "group":
            params = {"clientId": client_id, "desc": filename,
                      "width": int(width), "height": int(height),
                      "visibility": visibility, "grid": str(thread_id)}
            url = _multipart_url(GROUP_DOMAIN, "/api/group/sendpt",
                                 params, self.zpw_enk, TYPE_FILE_GROUP)
            where = "POST /api/group/sendpt"
        else:
            params = {"clientId": client_id, "desc": filename,
                      "width": int(width), "height": int(height),
                      "toid": str(thread_id)}
            url = _multipart_url(CHAT_DOMAIN, "/api/message/photo",
                                 params, self.zpw_enk, TYPE_FILE_USER)
            where = "POST /api/message/photo"
        body, ctype = build_multipart(
            {}, [("fileContent", filename, mime, data)])
        return {"data": self._post_multipart(url, body, ctype, where),
                "client_id": client_id}

    def send_voice(self, thread_type, thread_id, filename, data,
                   mime="audio/mpeg"):
        """11148 (1-1) / 11169 (nhom): multipart fileContent = file
        mp3 DA GHI XONG. Ghi am la viec cua trinh duyet
        (MediaRecorder) — ham nay chi gui file."""
        client_id = _new_client_id()
        if thread_type == "group":
            url = _multipart_url(
                FILES_DOMAIN, "/api/group/sendmp3",
                {"grid": str(thread_id), "clientId": client_id},
                self.zpw_enk, TYPE_FILE_GROUP)
            where = "POST /api/group/sendmp3"
        else:
            url = _multipart_url(
                FILES_DOMAIN, "/api/message/voicemp3",
                {"toid": str(thread_id), "clientId": client_id},
                self.zpw_enk, TYPE_FILE_USER)
            where = "POST /api/message/voicemp3"
        body, ctype = build_multipart(
            {}, [("fileContent", filename, mime, data)])
        return {"data": self._post_multipart(url, body, ctype, where),
                "client_id": client_id}

    # -- typing / seen ----------------------------------------------------
    def send_typing(self, thread_type, thread_id):
        """11144 (1-1) / 11196 (nhom)."""
        if thread_type == "group":
            url = _url_with_params(
                GROUP_DOMAIN, "/api/group/typing",
                {"grid": str(thread_id), "imei": self.device_id},
                self.zpw_enk)
            return self._get(url, "GET /api/group/typing")
        url = _url_with_params(
            CHAT_DOMAIN, "/api/message/typing",
            {"toid": str(thread_id), "destType": "USER",
             "imei": self.device_id}, self.zpw_enk)
        return self._get(url, "GET /api/message/typing")

    def send_seen(self, thread_type, thread_id, msg_ids=None):
        """11150 (1-1) / 11167 (nhom). msg_ids: list id tin da doc
        (neu biet); rong thi chi gui danh dau chung."""
        body = {"msg_ids": list(msg_ids or [])}
        if thread_type == "group":
            body["grid"] = str(thread_id)
            url = _url_with_params(GROUP_DOMAIN, "/api/group/seen",
                                   body, self.zpw_enk)
            return self._get(url, "GET /api/group/seen")
        body["toid"] = str(thread_id)
        url = _url_with_params(CHAT_DOMAIN, "/api/message/seen",
                               body, self.zpw_enk)
        return self._get(url, "GET /api/message/seen")
