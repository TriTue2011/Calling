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
  Gui anh 1-1:   POST multipart {files-wpa}/api/message/photo (11152)
                 FormData fileContent + params AES {clientId, desc,
                 width, height, toid}, & type=2 — HOST LA files-wpa
                 (bundle: _sendPhoto domainType FILE; loi that
                 2026-11-07: gui len chat-wpa bi 405).
  Gui anh nhom:  POST multipart {files-wpa}/api/group/sendpt (11164)
                 params {clientId, desc, width, height, visibility,
                 grid}, & type=11 — cung files-wpa (khong phai
                 group-wpa).
  Gui file ghi am 1-1 / nhom — DUONG HAI BUOC (upload-manager):
    Buoc 1: POST multipart {files-wpa}/api/message/voice/upload
    (12060) / /api/group/voice/upload (12063), moi chunk la FormData
    chunkContent (chunk 256_000 byte), params AES {totalChunk,
    fileName, clientId NUMBER, totalSize, imei, chunkId, toid|grid,
    fileType: "aac"|"amr"} & type=2/11; chunk cuoi tra data
    {finished: 1, fileId}.
    Buoc 2: POST form {files-wpa}/api/message/asyncfile/msg (11777)
    / /api/group/asyncfile/msg (13001), params AES la item
    getFileAsyncItem: {fileId, checksum (md5 hex), checksumSha: "",
    totalSize, clientId NUMBER, toid|grid, imei (chi 1-1),
    zsource: -1} + fileUrl (= amr||aac tu event async ctrl
    voice_aac_success — DOI truoc buoc 2, xem ctrl_poll.py) +
    aacUrl (chi khi co amr) + secureKey (chi khi async data co no).
    File ghi am la AAC-LC 16 kHz mono 64 kbps ADTS (xem
    voice_transcode.ensure_voice_aac) — KHONG phai MP3.
  DUONG TRUC TIEP CU (voicemp3 11148 / sendmp3 11169) DA BO:
    bundle co dinh nghia sendVoice nhung KHONG CO caller nao trong
    toan bo app (renderer, lazy chunk, worker, main-dist:
    "sendVoice(" dung 1 lan/file = dinh nghia; ".sendVoice(" = 0),
    dispatcher gui tin tu choi MSG_VOICE ("not support send this
    type"), va live 2026-11-06 08:36 +07 tren 965ce96 van tra inner
    112 sau khi da sua clientId STRING — nen duong truc tiep la
    code chet, khong dung nua. Buoc 2 asyncfile/msg DA DUOC XAC
    NHAN DUNG (vong 114, 2026-11-06): sendMsgFileAsync la API duy
    nhat (khong E2EE) POST dung item getFileAsyncItem, toi
    asyncfile/msg 11777/13001; bang lenh khong co endpoint gui-tin-
    thoai nao khac (khong co /api/message/voice gui bang URL);
    zsource -1 la mac dinh cua buildParams/transform. Xem ghi chu
    o send_voice (gioi han con lai: khong co caller Voice truc
    tiep nao quan sat duoc trong JS — buoc gui sau upload nam o
    lop native; fType LOAI TRU — extData Voice duy nhat lan duoc
    khong co fType nen app khong gui).
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
  - Nhan tin den: kenh sync long-poll 99100 (xem sync_poll.py) —
    tin den vao Inbox, lich su 1-1/nhom ghep tu Inbox (merge_messages).
    Kenh ctrl 99101 (xem ctrl_poll.py) chi mo cho event async voice
    (voice_aac_success, phuc vu send_voice); group_event/reaction
    van cho kenh ctrl day du.
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
da ghi qua duong hai buoc (upload chunked 12060/12063 +
asyncfile/msg). MediaRecorder cua Chrome/Firefox thuong cho
webm/opus — server DOI SANG AAC TRUOC KHI GUI
(voice_transcode.py: ffmpeg, mono 16 kHz 64 kbps ADTS, theo cach
Node.js voiceAac.js lam — Y HET tham so). File da la AAC thi gui
thang, khong doi. Duong truc tiep voicemp3/sendmp3 cu (bat MP3,
loi that inner 133 ngay 2026-11-05) da bo vi bundle khong goi
sendVoice — xem send_voice.
"""

import hashlib
import json
import re
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

# -- loi 112 + thu lai (voice/file) --------------------------------------
# error_code=112 tren duong voice (gap that tren may chu 2026-11-06
# 06:35 +07, "Loi khong xac dinh", va VAN CON tren 965ce96 luc
# 08:36 +07 sau khi da sua clientId STRING tren duong truc tiep):
# bundle khong dinh nghia rieng cho 112 — bang loi anh xa 112
# -> "STR_ERROR_CODE_UNKNOWN", va moi bo xu ly loi trong bundle deu
# coi 112 la TAM THOI va thu lai sau 1-5 giay (fetch/mark-unread/
# clear-unread/reaction/...). Nen app thu lai gioi han khi gap 112,
# dung cung clientId/body (clientId de server dedup, tranh gui
# trung). 112 la loi CHUNG, khong phai ma rieng cho mot truong nao.
# LUU Y: clientId STRING tren duong truc tiep voicemp3 (fix b0e98c2)
# da bi BAC BO la nguyen nhan (duy nhat) — live 08:36 +07 van 112;
# doc bundle ky lai thay sendVoice truc tiep khong co caller nao,
# nen duong hai buoc moi la duong that (xem send_voice).
VOICE_112_MAX_RETRIES = 2
VOICE_112_RETRY_DELAY_SECONDS = 2.0

# -- doi event async ctrl voice (loi 114) ------------------------------
# Sau chunk cuoi, bundle KHONG gui buoc 2 ngay: upload-manager DOI
# event ctrl `voice_aac_success` qua waitAsyncFileInfo (kenh ctrl
# long-poll 99101, zpw_ctrs_new — xem ctrl_poll.py) truoc khi gui.
# Timeout mac dinh cua bundle: upload_file_timeout_wait_ctrl_event
# = 12e4 ms (120 giay); het gio thi TIMEOUT_WAIT, khong gui buoc 2.
# Live 2026-11-06 09:46 +07: 112 da het (duong hai buoc toi duoc
# server) nhung buoc 2 tra 114 "Tham so khong hop le" — vi app cu
# gui buoc 2 ngay sau chunk-response (chi co {finished:1, fileId})
# nen body thieu fileUrl ma event async moi mang ve (amr/aac).
VOICE_ASYNC_WAIT_SECONDS = 120.0


def _voice_urls_from_async_data(data):
    """(file_url, aac_url, secure_key) tu du lieu async cua tin
    thoai — CHI tu event ctrl voice_aac_success (handler cua
    __waitAsyncFileInfo), KHONG BAO GIO tu chunk-response (xem
    buoc 1.5 o send_voice). Quy tac giong handler cua bundle:
    fileUrl = amr||aac; aacUrl CHI khi co amr; secureKey CHI khi
    du lieu co no (event ctrl voice khong co secureKey — chi dung
    cho E2EE/pcloud — nen thuong la None, khong phai loi). Tra
    None cho phan thieu."""
    if not isinstance(data, dict):
        return None, None, None
    amr = data.get("amr")
    amr = amr if isinstance(amr, str) and amr else None
    aac = data.get("aac")
    aac = aac if isinstance(aac, str) and aac else None
    file_url = amr or aac
    aac_url = aac if amr else None
    secure_key = _voice_secure_key(data)
    return file_url, aac_url, secure_key


def _voice_secure_key(data):
    """secureKey (neu co) tu chunk-response (mapVoiceResponse)
    hoac event ctrl — chi dung cho E2EE/pcloud, thuong vang;
    KHONG phai nguyen nhan 114 cho tin thoai thuong."""
    if not isinstance(data, dict):
        return None
    secure_key = data.get("secureKey")
    return (secure_key if isinstance(secure_key, str)
            and secure_key else None)

# -- upload ghi am theo chunk (duong hai buoc) -------------------------
# getDefaultChunkSize cua bundle: settings.sharefile.chunk_size_file
# neu >= 64_000, khong thi 256e3 byte. Chunk gui tuan tu, chunkId
# 1..totalChunk; chunk cuoi tra {finished: 1, fileId}.
VOICE_CHUNK_SIZE = 256000


class ZaloChatError(RuntimeError):
    """Loi Zalo tra ve qua envelope (error_code != 0), mang theo ma
    loi de caller quyet dinh co thu lai khong (vd. 112). Subclass
    cua RuntimeError nen moi `except RuntimeError` cu van bat duoc;
    message giu nguyen dinh dang cu ("chat: <where> error_code=...")."""

    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code

# -- dinh kem: gioi han + phan loai theo Node.js (zalobot / zca-js) ---
# Nguon chinh (lay tu lich su git 34ed43b, zalo-pc-app/zalobot-embedded):
#  - sendFile (api/zalo/zalo.js sendFileByAccount :748-792): tai file
#    qua saveFileFromUrl, cap 150 MB (FILE_DOWNLOAD_MAX_BYTES,
#    utils/helpers.js), roi gui api.sendMessage({msg: message||"",
#    attachments:[path], ttl}).
#  - sendImage (zalo.js sendImageByAccount :391-433): tai anh qua
#    saveImage, cap 25 MB (IMAGE_DOWNLOAD_MAX_BYTES) + soi magic
#    bytes (JPEG/PNG/GIF/WebP/BMP that, khong tin duoi ten) + doi
#    duoi ten cho khop dinh dang that (helpers.js doiDuoiChoKhop —
#    vi zca-js phan loai dinh kem bang DUOI TEN).
#  - Chi jpg/jpeg/png/webp vao duoc khoi album (EXT_ALBUM trong
#    utils/sendImages.js); gif di duong rieng cua zca-js, ext khac
#    bi xep "others" va gui nhu TEP DINH KEM.
#  - Gioi han phien that (settings.features.sharefile: max_file,
#    max_size_share_file_v3, restricted_ext_file) chi co luc dang
#    nhap zca-js; phien PC o day khong co — dung cac cap cung cua
#    Node.js lam gioi han mac dinh.
# Duong truyen VAN LA phien PC (endpoint bundle exe: sharefile_full
# 11146/11191, photo 11152/11164) — chi hanh vi / dinh dang / tham
# so khop Node.js. Cho nao exe va Node.js mau thuan ve wire thi
# giu theo exe (xem ghi chu o _new_client_id / send_file).
MAX_FILE_BYTES = 150 * 1024 * 1024
MAX_PHOTO_BYTES = 25 * 1024 * 1024
PHOTO_EXTS = frozenset({"jpg", "jpeg", "png", "webp"})
_MIME_TO_PHOTO_EXT = {"image/jpeg": "jpg", "image/png": "png",
                      "image/webp": "webp"}


def _file_ext(filename):
    """Duoi ten file (lowercase, khong dau cham); "" neu khong co
    duoi hop le. Zalo phan loai dinh kem bang duoi ten."""
    name = (filename or "").strip()
    if "." not in name:
        return ""
    ext = name.rsplit(".", 1)[1].strip().lower()
    return ext if ext.isalnum() else ""


def is_photo_file(filename, mime=""):
    """Anh that gui duong photo (11152/11164) chi khi duoi nam trong
    EXT_ALBUM cua Node.js (jpg/jpeg/png/webp). Gif/bmp/heic/svg/...
    gui dang tep dinh kem, khong phai anh — khop cach zca-js xep
    loai "others". Khong co duoi thi xet MIME (image/jpeg|png|webp)."""
    ext = _file_ext(filename)
    if ext:
        return ext in PHOTO_EXTS
    return (mime or "").strip().lower() in _MIME_TO_PHOTO_EXT


def effective_kind(kind, filename, mime=""):
    """kind hieu luc cho sendfile: client co the gui kind=photo cho
    gif/heic/... — ha xuong file theo luat Node.js, khong bao gio
    day ext la len endpoint photo."""
    if (kind or "file") == "photo" and is_photo_file(filename, mime):
        return "photo"
    return "file"


def detect_image_format(data):
    """Dinh dang anh that theo magic bytes (giong duoiAnhThat trong
    helpers.js cua Node.js): 'jpg' | 'png' | 'gif' | 'webp' | 'bmp'
    | None. Can toi thieu 12 byte de nhan WebP; file ngan hon tra
    None."""
    if not data or len(data) < 2:
        return None
    if data[0:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[0:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[0:4] == b"GIF8":
        return "gif"
    if len(data) >= 12 and data[0:4] == b"RIFF" \
            and data[8:12] == b"WEBP":
        return "webp"
    if data[0:2] == b"BM":
        return "bmp"
    return None


def validate_attachment(kind, filename, mime, data):
    """Kiem tra dinh kem TRUOC KHI goi Zalo (fail-fast, loi ro rang
    thay vi doi Zalo tra ma loi kho hieu hoac im lang). ValueError
    mang thong bao tieng Viet hien thang o UI. Quy tac theo Node.js:
    - ten file bat buoc; file rong (0 byte) bi tu choi — Zalo khong
      nhan file rong (tuong tu voice bi error_code=133 khi sai dinh
      dang); day la case live 23:00 +07 (iptv-udpxy.m3u, 0 byte).
    - file: toi da MAX_FILE_BYTES (150 MB, cap sendFile Node.js).
    - anh: toi da MAX_PHOTO_BYTES (25 MB, cap saveImage Node.js) +
      noi dung phai dung la anh (magic bytes)."""
    name = (filename or "").strip()
    if not name:
        raise ValueError("dinh kem: thieu ten file")
    if data is None or len(data) == 0:
        raise ValueError("file \"%s\" rong (0 byte) — Zalo khong nhan "
                         "file rong, hay chon file khac" % name)
    if kind == "photo":
        if len(data) > MAX_PHOTO_BYTES:
            raise ValueError("anh \"%s\" qua lon (%.1f MB > 25 MB) — "
                             "hay nen nho anh truoc khi gui"
                             % (name, len(data) / 1048576.0))
        fmt = detect_image_format(data)
        if fmt not in PHOTO_EXTS:
            raise ValueError("file \"%s\" khong phai anh that (noi dung "
                             "khong khop JPEG/PNG/WebP) — kiem tra lai "
                             "file" % name)
    elif len(data) > MAX_FILE_BYTES:
        raise ValueError("file \"%s\" qua lon (%.1f MB > 150 MB)"
                         % (name, len(data) / 1048576.0))

# Thong bao trung thuc khi khong lay duoc lich su 1-1 qua HTTPS.
# (Cau dau giu nguyen de test cu van bat duoc; phan sau noi ro
# tin den van ve qua kenh sync — xem sync_poll.py.)
HISTORY_USER_UNAVAILABLE = (
    "Lich su 1-1 chua lay duoc qua HTTPS: client Zalo PC that doc "
    "tin 1-1 tu DB local + dong bo tu dien thoai, khong co endpoint "
    "/api/message/history. Tin den moi van hien truc tiep qua kenh "
    "sync; chi lich su cu truoc phien nay la chua co."
)

# Thong bao khi lich su 1-1 doc tu DB local cua app (message_store):
# DB chi co tin tu khi app bat dau luu (sau ban webhook), tin cu
# hon van chua co — noi ro de khong tuong la day du.
HISTORY_USER_DB_PARTIAL = (
    "Lich su 1-1 chi co tu khi app bat dau luu tin xuong DB local "
    "(tin cu hon chua co); tin den moi van hien truc tiep qua "
    "kenh sync."
)

# E2EE: hoi thoai 1-1 bat E2EE co the khong di duong sms thuong.
# Gui thu; neu server tu choi thi loi hien ro o UI, khong gia vo.
E2EE_NOTE = (
    "Hoi thoai 1-1 bat E2EE co nhanh ma hoa rieng (e2eeExt); "
    "neu gui that bai, day co the la nguyen nhan."
)


def _validate_photo_bundle(bundle):
    """Kiem tra bundle gom nhom anh (xem send_photo): phai la dict
    du 4 field camelCase nhu client that merge vao params 11152/
    11164 — groupLayoutId (str khong rong, duy nhat moi batch),
    totalItemInGroup (int >= 2), isGroupLayout (== 1), idInGroup
    (int, 0 <= id < total). Tra ban sao da chuan hoa (int/str);
    sai -> ValueError, khong gui (gui khong bundle thi anh roi
    rac)."""
    if not isinstance(bundle, dict):
        raise ValueError("photo_bundle phai la dict")
    missing = [k for k in ("groupLayoutId", "totalItemInGroup",
                          "isGroupLayout", "idInGroup")
               if k not in bundle]
    if missing:
        raise ValueError("photo_bundle thieu truong: %s"
                         % ", ".join(missing))
    group_layout_id = bundle["groupLayoutId"]
    if not isinstance(group_layout_id, str) or not group_layout_id:
        raise ValueError("photo_bundle groupLayoutId phai la chuoi "
                         "khong rong")
    try:
        total = int(bundle["totalItemInGroup"])
        is_group = int(bundle["isGroupLayout"])
        index = int(bundle["idInGroup"])
    except (TypeError, ValueError):
        raise ValueError("photo_bundle totalItemInGroup/isGroupLayout/"
                         "idInGroup phai la so")
    if isinstance(bundle["totalItemInGroup"], bool) \
            or isinstance(bundle["isGroupLayout"], bool) \
            or isinstance(bundle["idInGroup"], bool):
        raise ValueError("photo_bundle totalItemInGroup/isGroupLayout/"
                         "idInGroup phai la so")
    if total < 2:
        raise ValueError("photo_bundle totalItemInGroup phai >= 2 "
                         "(anh don khong gom nhom)")
    if is_group != 1:
        raise ValueError("photo_bundle isGroupLayout phai == 1")
    if index < 0 or index >= total:
        raise ValueError("photo_bundle idInGroup phai trong "
                         "[0, totalItemInGroup)")
    return {"groupLayoutId": group_layout_id,
            "totalItemInGroup": total,
            "isGroupLayout": is_group,
            "idInGroup": index}


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
    sender_name, raw}. Cac key that co the gap: msgId/messageId/id;
    fromId/uidFrom/senderId; message/text/content/body; timestamp/
    createdAt/time/sentAt/ts. Shape poll/zca-js (sync_poll): content
    co the la dict {msg, title} (lay msg, khong thi title); dName la
    ten hien thi cua nguoi gui; cliMsgId la id client."""
    if not isinstance(item, dict):
        return {"id": "", "sender_id": "", "text": str(item),
                "time": None, "kind": "text", "file_name": "",
                "sender_name": "", "raw": item}
    content = item.get("content")
    if isinstance(content, dict):
        text = (content.get("msg") or content.get("title") or "")
    else:
        text = (item.get("message") or content
                or item.get("text") or item.get("body") or "")
    sender = (item.get("fromId") or item.get("uidFrom")
              or item.get("senderId") or item.get("sender")
              or item.get("uid") or "")
    msg_id = (item.get("msgId") or item.get("msgID")
              or item.get("messageId")
              or item.get("cliMsgId") or item.get("cliMsgID")
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
            "file_name": str(file_name),
            "sender_name": str(item.get("dName") or ""),
            "raw": item}


def _merge_key(msg):
    """Khoa dedup giong Node.js (groupHistoryStore.messageKey +
    zalo.js khoa ghep): msgId/msgID/cliMsgId/cliMsgID, roi id/
    client_id; khong co thi sender:time:text."""
    raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
    mid = (raw.get("msgId") or raw.get("msgID")
           or raw.get("cliMsgId") or raw.get("cliMsgID")
           or msg.get("id") or msg.get("client_id") or "")
    if mid:
        return "id:%s" % mid
    return "ct:%s:%s:%s" % (msg.get("sender_id") or "",
                            msg.get("time") or "",
                            msg.get("text") or "")


def merge_messages(fresh, cached, count):
    """Ghep lich su giong Node.js (zalo.js getGroupChatHistoryByAccount
    + groupHistoryStore): cache truoc, ban tuoi cua Zalo sau — trung
    khoa thi ban Zalo thang (moi hon); sap theo time tang dan; cat
    N tin cuoi. Tra ve (merged, from_cached): from_cached la so tin
    trong merged chi co tu cache."""
    merged_map = {}
    cached_keys = set()
    for msg in (cached or []):
        key = _merge_key(msg)
        cached_keys.add(key)
        merged_map[key] = msg
    fresh_keys = set()
    for msg in (fresh or []):
        key = _merge_key(msg)
        fresh_keys.add(key)
        merged_map[key] = msg
    merged = sorted(merged_map.values(),
                    key=lambda m: (m.get("time") or 0))
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = len(merged)
    merged = merged[-n:] if n > 0 else []
    from_cached = sum(1 for m in merged
                      if _merge_key(m) in cached_keys
                      and _merge_key(m) not in fresh_keys)
    return merged, from_cached


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
                 http_post_multipart=None, http_post=None, sleep=None,
                 voice_async=None, voice_async_timeout=None):
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
        # sleep cho khoang cho giua cac lan thu lai 112 (mac dinh
        # time.sleep; test inject ham ghi lai de khong cho that).
        self._sleep = sleep or time.sleep
        # Doi event async ctrl voice (loi 114 — xem send_voice):
        # voice_async la object co .wait(file_id, timeout_s) ->
        # {"amr", "aac"} | None va .feeder_running (True khi kenh
        # ctrl 99101 dang chay); server nap bang
        # ctrl_poll.VoiceAsyncRegistry + CtrlPoller. None = khong
        # co kenh cho event — send_voice loi ro thay vi gui mu.
        self.voice_async = voice_async
        try:
            timeout = float(voice_async_timeout
                            if voice_async_timeout is not None
                            else VOICE_ASYNC_WAIT_SECONDS)
        except (TypeError, ValueError):
            timeout = VOICE_ASYNC_WAIT_SECONDS
        self.voice_async_timeout = (timeout if timeout > 0
                                    else VOICE_ASYNC_WAIT_SECONDS)

    # -- co so -----------------------------------------------------------
    def _unwrap(self, status, payload, where):
        if status != 200 or not isinstance(payload, dict):
            raise ZaloChatError("chat: %s network status=%s"
                                % (where, status))
        if payload.get("error_code") != 0:
            raise ZaloChatError("chat: %s error_code=%s %s" % (
                where, payload.get("error_code"),
                payload.get("error_message", "")),
                error_code=payload.get("error_code"))
        try:
            return decode_postlogin_data(payload, self.zpw_enk)
        except RuntimeError as e:
            # Loi inner nam trong envelope da giai ma (vd.
            # "response inner error_code=112 ..."): doi sang
            # ZaloChatError mang theo ma loi (giu nguyen message)
            # de caller quyet dinh co thu lai khong.
            match = re.search(r"error_code=(-?\d+)", str(e))
            code = int(match.group(1)) if match else None
            raise ZaloChatError(str(e), error_code=code) from e

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

    def _post_multipart_retry(self, url, body_bytes, content_type,
                              where,
                              retries=VOICE_112_MAX_RETRIES,
                              delay_s=VOICE_112_RETRY_DELAY_SECONDS):
        """POST multipart, thu lai gioi han khi Zalo tra 112
        (tam thoi theo bundle: thu lai sau 1-5 giay). Moi lan thu
        dung NGUYEN url/body (cung clientId) de server dedup, khong
        gui trung. Loi khac 112, hoac het luot, thi nem thang."""
        attempts = 0
        while True:
            try:
                return self._post_multipart(url, body_bytes,
                                            content_type, where)
            except ZaloChatError as e:
                attempts += 1
                if e.error_code != 112 or attempts > retries:
                    raise
                self._sleep(delay_s)

    def _post_form_retry(self, domain, path, body, where,
                         retries=VOICE_112_MAX_RETRIES,
                         delay_s=VOICE_112_RETRY_DELAY_SECONDS):
        """POST form params=<AES JSON>, thu lai gioi han khi Zalo
        tra 112 — giong _post_multipart_retry (dung nguyen body,
        cung clientId de server dedup). Dung cho buoc 2 cua tin
        thoai (asyncfile/msg)."""
        attempts = 0
        while True:
            try:
                return self._post_form(domain, path, body, where)
            except ZaloChatError as e:
                attempts += 1
                if e.error_code != 112 or attempts > retries:
                    raise
                self._sleep(delay_s)

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
        """11146 (1-1) / 11191 (nhom): multipart fileContent.
        Kiem tra truoc (validate_attachment): ten thieu / file rong
        / file qua lon -> ValueError voi loi ro rang, khong goi Zalo.
        clientId la STRING tren duong nay (bundle sendFile ghep
        chuoi JSON bang tay: '{"toid":"<id>", "clientId":"<id>"}'
        — co dau ngoac kep; gia tri van la epoch-ms cua
        protocol.new_client_id, chi khac kieu JSON). Ghi chu cu noi
        "exe dung number" la SAI doi voi file/voice — number chi
        dung cho text/anh/link (JSON.stringify). Gui NUMBER o day
        bi server tu choi bang 112 chung chung (live 2026-11-06
        tren duong voice; cung mau thuan wire). Thu lai gioi han
        khi gap 112 (xem _post_multipart_retry).
        """
        validate_attachment("file", filename, mime, data)
        client_id = _new_client_id()
        if thread_type == "group":
            url = _multipart_url(
                FILES_DOMAIN, "/api/group/sharefile_full",
                {"grid": str(thread_id), "clientId": str(client_id)},
                self.zpw_enk, TYPE_FILE_GROUP)
            where = "POST /api/group/sharefile_full"
        else:
            url = _multipart_url(
                FILES_DOMAIN, "/api/message/sharefile_full",
                {"toid": str(thread_id), "clientId": str(client_id)},
                self.zpw_enk, TYPE_FILE_USER)
            where = "POST /api/message/sharefile_full"
        body, ctype = build_multipart(
            {}, [("fileContent", filename, mime, data)])
        return {"data": self._post_multipart_retry(url, body, ctype,
                                                   where),
                "client_id": client_id}

    def send_photo(self, thread_type, thread_id, filename, data,
                   mime="image/jpeg", width=0, height=0, visibility=0,
                   desc="", photo_bundle=None):
        """11152 (1-1) / 11164 (nhom): multipart fileContent +
        params AES {clientId, desc, width, height, toid|grid}.
        width/height lay tu anh that o UI; 0 = khong biet (best
        effort — server that co the doi kich thuoc that). Kiem tra
        truoc (validate_attachment): anh rong / qua lon / noi dung
        khong phai anh -> ValueError, khong goi Zalo. Chi jpg/jpeg/
        png/webp moi goi ham nay (xem effective_kind) — gif/bmp/
        heic/... di duong send_file theo luat Node.js. Response
        giai ma rong (None/{}) -> ZaloChatError "khong co ma tin":
        Zalo tra 200/error_code=0 nhung khong tao tin nao thi
        khong duoc bao thanh cong (loi cam 07/11). Tin gui thanh
        cong that luon co data {msgId, ...}.

        desc: caption cua anh. Client that gui desc = title || ""
        (bundle _sendPhoto) — anh chon tu file picker khong co
        title nen desc = "" (rong, khong phai ten file). Truoc day
        ham nay gui desc = ten file nen ben nhan hien ten file
        nhu caption duoi moi anh (case live 07/11). Gi nu tham so
        desc de sau nay co o nhap caption thi truyen vao.

        photo_bundle: gom nhom anh — client that gom nhieu anh
        chon mot luc bang cach gan chung mot bundle vao params
        tung anh (bundle _sendPhoto: t.photoBundle &&
        Object.assign(h, t.photoBundle); file-input handler tao
        bundle khi chon >1 anh khong-phai-gif): {"groupLayoutId":
        chuoi epoch-ms duy nhat moi batch, "totalItemInGroup":
        so anh khong-gif trong batch, "isGroupLayout": 1,
        "idInGroup": 0-based theo thu tu chon}. Ben nhan gom cac
        message cung group_layout_id thanh mot album MSG_PHOTO_GROUP
        (bundle @12913083). Anh don KHONG kem field nhom; GIF di
        duong file, khong dem, khong nhan idInGroup. Bundle sai
        (thieu field / total < 2 / id ngoai khoang) -> ValueError,
        khong gui — gui khong bundle thi anh roi rac, khong duoc
        bao thanh cong gia."""
        validate_attachment("photo", filename, mime, data)
        if photo_bundle is not None:
            photo_bundle = _validate_photo_bundle(photo_bundle)
        client_id = _new_client_id()
        if thread_type == "group":
            params = {"clientId": client_id, "desc": desc,
                      "width": int(width), "height": int(height)}
            if photo_bundle is not None:
                params.update(photo_bundle)
            params["visibility"] = visibility
            params["grid"] = str(thread_id)
            url = _multipart_url(FILES_DOMAIN, "/api/group/sendpt",
                                 params, self.zpw_enk, TYPE_FILE_GROUP)
            where = "POST /api/group/sendpt"
        else:
            params = {"clientId": client_id, "desc": desc,
                      "width": int(width), "height": int(height)}
            if photo_bundle is not None:
                params.update(photo_bundle)
            params["toid"] = str(thread_id)
            url = _multipart_url(FILES_DOMAIN, "/api/message/photo",
                                 params, self.zpw_enk, TYPE_FILE_USER)
            where = "POST /api/message/photo"
        body, ctype = build_multipart(
            {}, [("fileContent", filename, mime, data)])
        sent = self._post_multipart(url, body, ctype, where)
        if not sent:
            # Zalo tra 200/error_code=0 nhung khong tao tin nao
            # (data rong) — phai bao loi that: neu tra ok, route
            # se tra ok:true + message local, UI hien anh nhu da
            # gui trong khi ben kia khong nhan duoc (thanh cong
            # gia — loi cam 07/11). Tin gui thanh cong that luon
            # co data {msgId, ...}.
            raise ZaloChatError(
                "photo: Zalo tra ve khong co ma tin — anh chua duoc "
                "tao (data rong sau khi giai ma)")
        return {"data": sent, "client_id": client_id}

    def send_voice(self, thread_type, thread_id, filename, data,
                   mime="audio/aac"):
        """Gui tin thoai — DUONG HAI BUOC cua upload-manager
        (bundle PC 26.11.10; xem ghi chu o dau module):
        Buoc 1: POST multipart chunkContent len 12060 (1-1) /
        12063 (nhom), moi chunk 256_000 byte, params AES
        {totalChunk, fileName, clientId NUMBER, totalSize, imei,
        chunkId, toid|grid, fileType: "aac"|"amr"} (KHONG checksum
        trong params — bundle xoa truoc khi gui; checksum chi o
        client-side), & type=2/11. Chunk cuoi tra data
        {finished: 1, fileId}.
        Buoc 2: POST form params=<AES JSON> len asyncfile/msg
        11777 (1-1) / 13001 (nhom), body la item getFileAsyncItem:
        {fileId, checksum (md5 hex cua toan file), checksumSha: "",
        totalSize, clientId NUMBER, toid|grid, imei (chi 1-1),
        zsource: -1} + fileUrl (= amr||aac tu event async ctrl
        voice_aac_success — DOI truoc buoc 2, xem ctrl_poll.py) +
        aacUrl (chi khi co amr) + secureKey (chi khi async data
        co no).
        Ghi am la viec cua trinh duyet (MediaRecorder) + server doi
        sang AAC truoc (voice_transcode.ensure_voice_aac) — ham nay
        chi gui file AAC ADTS da chuan bi. File rong bi tu choi
        ngay truoc khi goi mang. Thu lai gioi han khi gap 112 o
        CA hai buoc (tam thoi theo bundle; dung cung clientId/body
        de server dedup, tranh gui trung).

        GHI CHU TRUNG THUC VE BUOC 2 (DA XAC NHAN DUNG, vong 114
        2026-11-06 — khong con la suy luan theo shape): trong
        bundle, sendMsgFileAsync (API class, 15136113) la API duy
        nhat (khong E2EE) POST dung item getFileAsyncItem, toi
        {files-wpa}/api/message/asyncfile/msg (11777) / /api/group/
        asyncfile/msg (13001), POST form params=<AES JSON>; caller
        duy nhat trong JS la UploadAsyncControl._sendMsgFileAsync
        (8579214). Bang lenh 231 muc khong co endpoint gui-tin-
        thoai nao khac: khong co /api/message/voice (gui bang URL);
        voicemp3/sendmp3 chet (0 caller); dispatcher gui tin tu
        choi MSG_VOICE. zsource -1 la mac dinh cua buildParams/
        transform (3955260: khong co src thi zsource=-1).
        GIOI HAN CON LAI (khong phai bang chung chong lai
        endpoint): khong co caller Voice TRUC TIEP nao quan sat
        duoc trong JS — sendMsgAsync chi xu ly Photo/File, va
        sendFileByChunkV2 tra thang urlRes cho Voice/Video (cho
        lop native gui sau upload); 2 call site cua
        sendFileByChunkV2 trong JS chi la File va Photo. Viec ghi
        am + gui sau upload nam o lop native ngoai JS, nen buoc
        gui cuoi cua lop do khong doc duoc tu bundle JS.
        fType LOAI TRU (kiem toan tham so vong 114): extData cua
        task upload Voice duy nhat lan duoc ({uploadMainType:
        Voice, e2ee: false}) khong co fType nen JSON.stringify
        loai truong do — item voice that khong co fType, app bo
        qua la dung. Duong truc tiep voicemp3/sendmp3 cu DA BO
        (code chet, 0 caller; live 2026-11-06 08:36 +07 van 112)
        — khong giu lam fallback.

        KET LUAN LOI 114 (kiem toan tham so 2026-11-06, xem
        tests/test_voice_112.py::test_voice_114_*): buoc 1 khop
        bundle tren MOI tham so chung minh duoc (totalChunk,
        fileName, clientId NUMBER, totalSize, imei, chunkId 1..N,
        toid|grid, fileType aac|amr; khong checksum; khong
        isE2EE tren duong thuong). Nghi pham chinh la buoc 2
        THIEU fileUrl: client that CHI gui item sau khi cho async
        event voice_aac_success {aac, amr, secureKey} qua
        waitAsyncFileInfo (__waitAsyncFileInfo: fileUrl = amr||
        aac, aacUrl = aac chi khi co amr, secureKey neu event co)
        roi moi gui; app gui ngay sau chunk cuoi, khong co URL
        tin thoai nao trong item — server tu choi bang 114 "Tham
        so khong hop le" (thieu tham so bat buoc). Da sua: KHONG
        gui fileUrl/aacUrl lay tu response chunk (nguon sai —
        bundle khong bao gio lay URL tu do) va DOI event truoc
        buoc 2 (xem DOI EVENT ASYNC ben duoi). Neu live retest
        van 114 sau khi co event, diem can kiem tiep la ten file
        ghi am that (app dung "voice.aac"; ten cua recorder
        native chua lan duoc) va chunk_size_file that (app dung
        256000 theo default cua bundle khi setting < 64000).

        DOI EVENT ASYNC (loi 114, 2026-11-06 09:46 +07 — DA
        IMPLEMENT): truoc buoc 2, bundle DOI event ctrl
        `voice_aac_success` qua waitAsyncFileInfo (kenh ctrl 99101,
        xem ctrl_poll.py) — event mang {amr, aac} (key so "5"/"6");
        handler dien fileUrl=amr||aac (+ aacUrl khi co amr) vao
        fileAsync, roi API sendMsgFileAsync moi POST {...fileAsync}.
        Ham nay lam dung vay: LUON doi waiter (VoiceAsyncRegistry
        do CtrlPoller nap; tra ngay neu event da ve truoc —
        cache-hit) toi da voice_async_timeout (mac dinh 120 s nhu
        bundle); het gio / kenh ctrl chua chay / khong co waiter
        -> loi ro rang, KHONG gui buoc 2 (gui mu chinh la cai gay
        ra 114 live). URL buoc 2 CHI tu event — KHONG BAO GIO lay
        tu chunk-response (khac ban goc cua vong async: shortcut
        "chunk-response co URL thi dung luon" la SAI vi truong url
        trong chunk-response thuoc nhanh DUPLICATE/cache, khong
        phai URL tin thoai de gui).
        secureKey: event ctrl voice KHONG co secureKey (chi co
        amr/aac) — secureKey chi co trong mapVoiceResponse (tu
        chunk-response) va chi dung cho E2EE/pcloud; ham nay gui
        kem secureKey CHI khi chunk-response hoac event co no
        (thuong vang — KHONG phai nguyen nhan 114 cho tin thoai
        thuong).
        Con thieu so voi bundle: khong replay chunk cuoi khi het
        gio (bundle replay sau 30 s voi file nho) — het timeout thi
        loi, khong tu replay. fType LOAI TRU (xem o tren) — khong
        gui fType."""
        if not data:
            raise ValueError("chat: file ghi am rong (0 byte) — Zalo "
                             "khong nhan tin thoai rong, hay ghi am lai")
        is_group = thread_type == "group"
        client_id = _new_client_id()
        total_size = len(data)
        total_chunks = (total_size + VOICE_CHUNK_SIZE - 1) \
            // VOICE_CHUNK_SIZE
        file_type = ("amr" if ".amr" in (filename or "").lower()
                     else "aac")
        if is_group:
            upload_path = "/api/group/voice/upload"
            send_path = "/api/group/asyncfile/msg"
            type_param = TYPE_FILE_GROUP
        else:
            upload_path = "/api/message/voice/upload"
            send_path = "/api/message/asyncfile/msg"
            type_param = TYPE_FILE_USER
        # -- buoc 1: upload chunked ------------------------------------
        file_id = None
        upload_data = {}
        for chunk_id in range(1, total_chunks + 1):
            chunk = data[(chunk_id - 1) * VOICE_CHUNK_SIZE:
                         chunk_id * VOICE_CHUNK_SIZE]
            params = {"totalChunk": total_chunks,
                      "fileName": filename,
                      "clientId": client_id,
                      "totalSize": total_size,
                      "imei": self.device_id,
                      "chunkId": chunk_id,
                      "fileType": file_type}
            if is_group:
                params["grid"] = str(thread_id)
            else:
                params["toid"] = str(thread_id)
            url = _multipart_url(FILES_DOMAIN, upload_path, params,
                                 self.zpw_enk, type_param)
            body, ctype = build_multipart(
                {}, [("chunkContent", filename,
                      "application/octet-stream", chunk)])
            upload_data = self._post_multipart_retry(
                url, body, ctype,
                "POST %s chunk %d/%d" % (upload_path, chunk_id,
                                         total_chunks))
            if chunk_id == total_chunks:
                if not isinstance(upload_data, dict) \
                        or not upload_data.get("finished") \
                        or not upload_data.get("fileId"):
                    raise ZaloChatError(
                        "chat: upload ghi am xong nhung Zalo khong "
                        "tra fileId (finished/fileId thieu): %r"
                        % (upload_data,), error_code=0)
                file_id = upload_data["fileId"]
        # -- buoc 1.5: doi event async ctrl voice_aac_success -------
        # Bundle DOI event (waitAsyncFileInfo) truoc buoc 2 de lay
        # URL ghi am (amr/aac); chunk-response chi co
        # {finished:1, fileId} — bundle KHONG BAO GIO lay URL tu
        # chunk-response (handleSendChunkResp chi doc finished/
        # fileId; truong url trong chunk-response thuoc nhanh
        # DUPLICATE/cache), nen ham nay LUON doi event (wait tra
        # ngay neu event da ve truoc — cache-hit cua bundle).
        # secureKey (neu co) lay tu chunk-response hoac event
        # (chi dung cho E2EE/pcloud; thuong vang). Het gio /
        # khong co kenh ctrl / khong co waiter -> loi ro, KHONG
        # gui buoc 2 (gui buoc 2 khong co fileUrl la cai gay ra
        # 114 live).
        chunk_key = _voice_secure_key(upload_data)
        waiter = self.voice_async
        if waiter is None:
            raise ZaloChatError(
                "chat: gui ghi am chua nhan duoc URL ghi am "
                "(amr/aac) — khong co kenh cho event async ctrl "
                "voice_aac_success (99101); khong gui buoc 2 "
                "khong co fileUrl", error_code=0)
        if not getattr(waiter, "feeder_running", True):
            raise ZaloChatError(
                "chat: gui ghi am chua nhan duoc URL ghi am "
                "(amr/aac) — kenh ctrl (99101) chua chay; "
                "khong gui buoc 2 khong co fileUrl",
                error_code=0)
        got = waiter.wait(file_id, self.voice_async_timeout)
        file_url, aac_url, event_key = \
            _voice_urls_from_async_data(got)
        secure_key = event_key or chunk_key
        if not file_url:
            raise ZaloChatError(
                "chat: gui ghi am het %.0f giay cho event async "
                "ctrl voice_aac_success ma khong thay URL ghi am "
                "(amr/aac) cho fileId da upload xong; khong gui "
                "buoc 2 khong co fileUrl"
                % self.voice_async_timeout, error_code=0)
        # -- buoc 2: gui bang fileId -----------------------------------
        item = {"fileId": file_id,
                "checksum": hashlib.md5(data).hexdigest(),
                "checksumSha": "",
                "totalSize": total_size,
                "clientId": client_id,
                "zsource": -1}
        if is_group:
            item["grid"] = str(thread_id)
        else:
            item["toid"] = str(thread_id)
            item["imei"] = self.device_id
        # URL ghi am tu event async (bundle: fileAsync.fileUrl =
        # amr||aac, aacUrl chi khi co amr; secureKey chi khi async
        # data co no). Buoc 2 KHONG bao gio gui khi thieu fileUrl
        # (xem khoi doi event o tren).
        item["fileUrl"] = file_url
        if aac_url:
            item["aacUrl"] = aac_url
        if secure_key:
            item["secureKey"] = secure_key
        send_data = self._post_form_retry(
            FILES_DOMAIN, send_path, item, "POST %s" % send_path)
        return {"data": send_data, "client_id": client_id,
                "file_id": file_id}

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
