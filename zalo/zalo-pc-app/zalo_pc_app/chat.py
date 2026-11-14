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
  Dinh kem file 1-1 / nhom — DUONG HAI BUOC (upload-manager,
  giong ghi am; xem send_file):
    Buoc 1: POST multipart {files-wpa}/api/message/asyncfile/
    upload (11776) / /api/group/asyncfile/upload (13000), moi
    chunk la FormData chunkContent (chunk 256_000 byte), params
    AES {totalChunk, fileName, clientId NUMBER, totalSize, imei,
    chunkId, toid|grid} (KHONG fileType/checksum) & type=2/11;
    chunk cuoi tra data {finished: 1, fileId}.
    Buoc 1.5: DOI event ctrl file_done {fileId, url} (kenh ctrl
    99101) truoc buoc 2 — xem ctrl_poll.py.
    Buoc 2: POST form {files-wpa}/api/message/asyncfile/msg
    (11777) / /api/group/asyncfile/msg (13001), params AES la
    item getFileAsyncItem: {fileId, checksum (md5 hex),
    checksumSha: "", extension, totalSize, fileName, clientId
    NUMBER, fType: 1, fileCount: 0, fdata: "{}", toid|grid,
    imei (chi 1-1), zsource: -1} + fileUrl (tu event file_done).
  DUONG TRUC TIEP sharefile_full (11146/11191) DA BO: API sendFile
  co dinh nghia nhung KHONG CO caller nao trong bundle (giong
  sendVoice chet cua voicemp3) va Zalo tra HTTP 405 khi goi
  (live 2026-11-07: gui Word/Excel/PDF bi banner 405).
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
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import protocol, rich_text
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

# -- doi event async ctrl file (loi 405 sharefile_full) ---------------
# Cung gate nhu voice, chi khac dang event: sau chunk cuoi cua
# file thuong, bundle DOI event ctrl `file_done` {fileId, url} qua
# waitAsyncFileInfo truoc buoc 2 (handler dien fileUrl = url vao
# fileAsync); timeout mac dinh cung 12e4 ms. Xem ctrl_poll.py
# (FileAsyncRegistry) + send_file.
FILE_ASYNC_WAIT_SECONDS = 120.0


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

# -- upload file thuong theo chunk (duong hai buoc) -------------------
# CUNG getDefaultChunkSize nhu voice (settings.sharefile.
# chunk_size_file, mac dinh 256e3 byte) — chunk gui tuan tu,
# chunkId 1..totalChunk; chunk cuoi tra {finished: 1, fileId}.
FILE_CHUNK_SIZE = 256000


def _file_extension(filename):
    """extension cua ten file theo bundle (getExtension): phan sau
    dau cham CUOI, rong neu khong co dau cham hoac phan duoi dai
    >= 7 ky tu; giu nguyen hoa/thuong (bundle khong ha)."""
    name = filename or ""
    idx = name.rfind(".")
    if idx < 0:
        return ""
    ext = name[idx + 1:]
    return ext if len(ext) < 7 else ""


def _normalize_filename(filename):
    """Ten file truoc khi gui theo bundle
    (formatFileNameBeforeSend): Unicode normalize() — mac dinh
    NFC o JS."""
    name = filename or ""
    if not isinstance(name, str):
        return name
    try:
        return unicodedata.normalize("NFC", name)
    except (TypeError, ValueError):
        return name


def _utf16_len(text):
    return len(str(text).encode("utf-16-le")) // 2


def build_mentions(message, mentions):
    """Chuan hoa danh sach mention cua tin NHOM thanh mentionInfo cua Zalo: [{pos, uid, len, type}] (pos/len tinh theo UTF-16 nhu Zalo PC va
    zca-js `handleMentions`; type 1 = @Tat ca khi uid "-1", con lai 0). Moi muc: {uid, pos, len} da biet vi tri, HOAC {uid, name} — tim
    "@name" trong `message` (lan lan theo thu tu, khong chong len nhau). Nem ValueError khi khong khop / vuot do dai. None/rong -> []."""
    if not mentions:
        return []
    if not isinstance(mentions, list):
        raise ValueError("chat: mentions phai la danh sach")
    total = _utf16_len(message)
    out, cursor = [], 0
    for m in mentions:
        if not isinstance(m, dict) or not str(m.get("uid") or "").strip():
            raise ValueError("chat: moi mention can uid")
        uid = str(m["uid"]).strip()
        if m.get("pos") is not None and m.get("len") is not None:
            pos, length = int(m["pos"]), int(m["len"])
        else:
            name = str(m.get("name") or ("All" if uid == "-1" else "")).strip()
            if not name:
                raise ValueError("chat: mention %s can pos+len hoac name" % uid)
            needle = "@" + name.lstrip("@")
            at = str(message).find(needle, cursor)
            if at < 0:
                raise ValueError("chat: khong thay '%s' trong tin de mention" % needle)
            pos, length = _utf16_len(str(message)[:at]), _utf16_len(needle)
            cursor = at + len(needle)
        if pos < 0 or length <= 0 or pos + length > total:
            raise ValueError("chat: mention %s vuot do dai tin (pos=%d len=%d)" % (uid, pos, length))
        out.append({"pos": pos, "uid": uid, "len": length, "type": 1 if uid == "-1" else 0})
    return out


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
# Duong truyen VAN LA phien PC (endpoint bundle exe: asyncfile
# upload 11776/13000 + asyncfile/msg 11777/13001, photo 11152/
# 11164) — chi hanh vi / dinh dang / tham so khop Node.js. Cho nao
# exe va Node.js mau thuan ve wire thi giu theo exe (xem ghi chu
# o _new_client_id / send_file).
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
    "Lịch sử 1-1 chỉ có từ khi app bắt đầu lưu tin xuống DB local "
    "(tin cũ hơn chưa có); tin đến mới vẫn hiện trực tiếp qua "
    "kênh sync."
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


def _file_params(item, content):
    """params dinh kem cua tin file/anh (bundle: content.params la
    JSON string {fileSize, checksum, fileExt, fType, ...} — xem
    _normalizeMessageJSON case MSG_FILE; cung chap nhan dict san
    hoac field top-level). Tra dict (rong khi khong co / hong) —
    khong bao gio nem loi."""
    raw = None
    if isinstance(content, dict):
        raw = content.get("params")
    if raw is None:
        raw = item.get("params")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


# Loai tin dang chuoi cua server (bundle _normalizeMessageType +
# zca-js getClientMessageType khop nhau): "share.file" la tin
# file, "chat.photo"/"chat.gif" la anh, "chat.voice" la ghi am,
# "chat.video.msg" la video. Cac dang cu ("file", "photo", ...)
# giu lai de test cu + shape khac khong vo.
_MSG_TYPE_KIND = {
    "share.file": "file",
    "chat.photo": "photo",
    "chat.gif": "photo",
    "chat.voice": "voice",
    "chat.video.msg": "video",
    "file": "file",
    "sharefile": "file",
    "photo": "photo",
    "image": "photo",
    "voice": "voice",
    "voicemp3": "voice",
    "mp3": "voice",
}


def _int_or_none(value):
    """So nguyen hoac None (best-effort, khong nem loi)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# Tin HE THONG (khong co chu cua nguoi dung): su kien nhom (bao gom binh chon moi), sticker, thu hoi. Mau cau co SAN trong
# params.msg ({"vi": "%1$s tao cuoc binh chon moi: %2$s", "en": ...}) nen ve theo mau, khong liet ke tung loai su kien.
_PLACEHOLDER_TEXT = {"chat.sticker": "[Sticker]", "chat.undo": "Một tin nhắn đã được thu hồi"}
_ARG_RE = re.compile(r"%(\d+)\$s")


def _system_text(msg_type, content, item):
    """Chu hien thi cho tin he thong, hoac "" neu khong phai (khong doan)."""
    if msg_type in _PLACEHOLDER_TEXT:
        return _PLACEHOLDER_TEXT[msg_type]
    params = content.get("params")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except ValueError:
            return ""
    if not isinstance(params, dict) or not isinstance(params.get("msg"), dict):
        return ""
    tmpl = params["msg"].get("vi") or params["msg"].get("en") or next(
        (v for v in params["msg"].values() if isinstance(v, str)), "")
    if not tmpl:
        return ""
    # Quy uoc cua Zalo: %1$s = nguoi thuc hien, %2$s = doi tuong (cau hoi binh chon, ten nhom, ...).
    actor = str(params.get("dName") or item.get("dName") or "Ai đó")
    obj = ""
    for key in ("question", "groupName", "title", "name", "text"):
        if params.get(key):
            obj = str(params[key])
            break
    args = {"1": actor, "2": obj}
    return _ARG_RE.sub(lambda m: args.get(m.group(1), ""), tmpl).strip()


def _poll_ref(msg_type, content, item):
    """(poll_id, câu hỏi) của tin bình chọn (group.poll: tạo mới / tham gia / đổi phiếu), hoặc ("", ""). Thẻ bình chọn trên WebUI dựng từ poll_id
    (get_poll_detail / danh sách bình chọn của nhóm): chính tin chỉ là SỰ KIỆN hệ thống, không chứa phương án hay số phiếu."""
    if msg_type != "group.poll" or not isinstance(content, dict):
        return "", ""
    params = content.get("params")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except ValueError:
            return "", ""
    if not isinstance(params, dict) or params.get("pollId") in (None, ""):
        return "", ""
    return str(params["pollId"]), str(params.get("question") or "")


def call_record_info(msg_type, content):
    """Ban ghi cuoc goi Zalo tu tao: msgType `chat.recommended`, content {action: "recommened.calltime" | "recommened.misscall", title, params:
    {callId, calltype, duration, isCaller, reason...}}. Tra ve {call_id, duration, missed, is_caller, text} hoac None (khong doan thang khac)."""
    if str(msg_type) != "chat.recommended" or not isinstance(content, dict):
        return None
    action = str(content.get("action") or "")
    if action not in ("recommened.calltime", "recommened.misscall"):
        return None
    params = content.get("params")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except ValueError:
            params = {}
    params = params if isinstance(params, dict) else {}
    missed = action == "recommened.misscall"
    try:
        duration = int(params.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    # `title` cua Zalo la placeholder «sendBubbleMessage» (do 12/11: moi ban ghi that), chu hien thi do CLIENT tu dung tu action + duration.
    # KHONG phan biet thoai/video: ban ghi cua mot cuoc goi VIDEO that (callId 1304883739, 12/11) van mang calltype 0.
    label = "Cuộc gọi"
    if missed:
        text = label + " nhỡ"
    else:
        text = label + ((" · %d:%02d" % (duration // 60, duration % 60)) if duration > 0 else "")
    return {"call_id": str(params.get("callId") or ""), "duration": duration, "missed": missed,
            "is_caller": bool(params.get("isCaller")), "text": text}


def reply_info(item):
    """Tin TRA LOI: Zalo gui kem `quote` = {ownerId, cliMsgId, globalMsgId, cliMsgType, ts, msg, attach, fromD, ttl} (zca-js TQuote).
    Tra ve {owner, msg_id, cli_msg_id, ts, text, attach_kind, attach_url, attach_name} hoac None. `attach` la CHUOI JSON cua tep dinh kem
    cua tin goc (anh/file/...): ta chi lay duong dan + ten de nguoi dung biet tin goc co tep — khong tai ve. Chiu moi dang (best-effort):
    sai dang thi bo qua phan do, khong nem loi."""
    q = item.get("quote") if isinstance(item, dict) else None
    if isinstance(q, str):
        try:
            q = json.loads(q)
        except ValueError:
            q = None
    if not isinstance(q, dict):
        return None
    attach = q.get("attach")
    if isinstance(attach, str) and attach.strip():
        try:
            attach = json.loads(attach)
        except ValueError:
            attach = None
    if isinstance(attach, list):
        attach = attach[0] if attach and isinstance(attach[0], dict) else None
    url = name = ""
    if isinstance(attach, dict):
        url = str(attach.get("href") or attach.get("hdUrl") or attach.get("normalUrl") or attach.get("thumb") or "")
        name = str(attach.get("title") or attach.get("fileName") or "")
    msg_type = str(q.get("cliMsgType") if q.get("cliMsgType") is not None else "")
    ext = (name or url.split("?")[0]).rsplit(".", 1)[-1].lower() if (name or url) and "." in (name or url.split("?")[0]) else ""
    by_ext = ("photo" if ext in ("jpg", "jpeg", "png", "webp", "gif", "bmp", "heic") else "voice" if ext in ("mp3", "aac", "m4a", "amr", "ogg", "opus", "wav")
              else "video" if ext in ("mp4", "mov", "mkv", "webm") else "file" if (name or ext) else "")
    kind = _MSG_TYPE_KIND.get(msg_type) or (by_ext if (attach and url) else ("file" if name else ""))
    return {"owner": str(q.get("ownerId") or q.get("fromD") or ""), "msg_id": str(q.get("globalMsgId") or ""),
            "cli_msg_id": str(q.get("cliMsgId") or ""), "ts": q.get("ts"), "text": str(q.get("msg") or ""),
            "attach_kind": kind if (attach or kind in ("photo", "file", "voice", "video")) else "",
            "attach_url": url, "attach_name": name, "cli_msg_type": msg_type}


def normalize_message(item, thread_type="user"):
    """Chuan hoa 1 tin (best-effort — shape lich su nhom that chua
    duoc thay truc tiep): {id, sender_id, text, time, kind, file_name,
    file_url, file_size, file_checksum, file_ext, f_type,
    sender_name, raw}. Cac key that co the gap: msgId/messageId/id;
    fromId/uidFrom/senderId; message/text/content/body; timestamp/
    createdAt/time/sentAt/ts. Shape poll/zca-js (sync_poll): content
    co the la dict {msg, title} (lay msg, khong thi title); dName la
    ten hien thi cua nguoi gui; cliMsgId la id client.

    Tin dinh kem den (bundle _normalizeMessageJSON + download
    service): msgType la chuoi ("share.file"/"chat.photo"/
    "chat.voice"/...); content la dict {title, href, params, ...}:
      - title = ten file (bundle noi them "." + params.fileExt
        neu title chua co duoi — xem _normalizeMessageJSON case
        MSG_FILE; ham nay lam dung luat do),
      - href = URL tai file (menu download cua bundle chi hien
        khi message.href co gia tri),
      - params (JSON string) = {fileSize, checksum, fileExt,
        fType} (fType 1 = file, 2 = folder).
    Cac truong file_* tra None/rong khi tin khong co dinh kem."""
    if not isinstance(item, dict):
        return {"id": "", "sender_id": "", "text": str(item),
                "time": None, "kind": "text", "file_name": "",
                "file_url": None, "file_size": None,
                "file_checksum": None, "file_ext": "", "f_type": None,
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
    # -- dinh kem den (xem docstring) --------------------------------
    params = _file_params(item, content)
    content_dict = content if isinstance(content, dict) else {}
    msg_type = str(item.get("msgType") or item.get("type") or "")
    kind = _MSG_TYPE_KIND.get(msg_type)
    call_record = call_record_info(msg_type, content_dict)
    if call_record:
        kind, text = "system", call_record["text"]
    # Hanh vi cu: title/fileName o TOP-LEVEL thi la file (giữ
    # nguyên để không đổi kind của các shape cũ); content.title
    # CHỈ đọc khi tin đã là đính kèm theo msgType — tin text có
    # content {msg, title} vẫn là text, không thành file.
    file_name = (item.get("fileName") or item.get("file_name")
                 or item.get("title") or "")
    if kind is None:
        kind = "file" if file_name else "text"
    if not text and kind == "text":
        sys_text = _system_text(msg_type, content_dict, item) if (content_dict or msg_type in _PLACEHOLDER_TEXT) else ""
        if sys_text:
            text, kind = sys_text, "system"
    file_url = (content_dict.get("href")
                or item.get("fileUrl") or item.get("file_url")
                or item.get("href") or None)
    file_size = _int_or_none(
        params.get("fileSize") if isinstance(params, dict) else None)
    if file_size is None:
        file_size = _int_or_none(item.get("fileSize")
                                 or item.get("file_size")
                                 or item.get("totalSize"))
    checksum = (params.get("checksum") if isinstance(params, dict)
                else None) or item.get("checksum") or None
    file_ext = ""
    if isinstance(params, dict) and params.get("fileExt"):
        file_ext = str(params.get("fileExt") or "").lower()
    if kind in ("file", "photo", "voice", "video"):
        if not file_name:
            file_name = content_dict.get("title") or ""
        if not file_ext:
            file_ext = _file_ext(file_name)
        # Luat bundle (_normalizeMessageJSON case MSG_FILE): title
        # thieu duoi thi noi "." + fileExt (khong noi trung).
        if file_name and file_ext \
                and not str(file_name).lower().endswith("." + file_ext):
            file_name = "%s.%s" % (file_name, file_ext)
        if file_name:
            text = file_name
    f_type = _int_or_none(
        params.get("fType") if isinstance(params, dict) else None)
    poll_id, poll_question = _poll_ref(msg_type, content_dict, item) if kind == "system" else ("", "")
    return {"id": str(msg_id), "sender_id": str(sender),
            "text": str(text), "time": when, "kind": kind,
            "file_name": str(file_name),
            "file_url": (str(file_url) if file_url else None),
            "file_size": file_size,
            "file_checksum": (str(checksum) if checksum else None),
            "file_ext": file_ext,
            "f_type": f_type,
            "sender_name": str(item.get("dName") or ""),
            "poll_id": poll_id, "poll_question": poll_question,
            "reply_to": reply_info(item),
            "call_record": call_record,
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
                 voice_async=None, voice_async_timeout=None,
                 file_async=None, file_async_timeout=None,
                 ctrl_status=None):
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
        # Doi event async ctrl file (loi 405 sharefile_full — xem
        # send_file): file_async la object co .wait(file_id,
        # timeout_s) -> {"url"} | None va .feeder_running; server
        # nap bang ctrl_poll.FileAsyncRegistry + CtrlPoller. None
        # = khong co kenh cho event — send_file loi ro thay vi
        # gui mu.
        self.file_async = file_async
        try:
            timeout = float(file_async_timeout
                            if file_async_timeout is not None
                            else FILE_ASYNC_WAIT_SECONDS)
        except (TypeError, ValueError):
            timeout = FILE_ASYNC_WAIT_SECONDS
        self.file_async_timeout = (timeout if timeout > 0
                                   else FILE_ASYNC_WAIT_SECONDS)
        # Trang thai kenh live (callable tra dict {"ctrl", "sync",
        # "sync_error"} — server nap bang AppState.ctrl_status() /
        # sync_status()) de loi gui file/ghi am khi kenh ctrl xuong
        # noi ro nguyen nhan + cach sua thay vi chi "kenh ctrl chua
        # chay". None = khong co thong tin live, loi giu nguyen.
        self._ctrl_status_fn = ctrl_status

    def _ctrl_status_info(self):
        """Dict trang thai kenh live (best-effort); {} khi khong co
        ham trang thai hoac ham loi."""
        fn = self._ctrl_status_fn
        if fn is None:
            return {}
        try:
            info = fn()
        except Exception:
            return {}
        return info if isinstance(info, dict) else {}

    def _ctrl_hint(self):
        """Hau to huong dan khi kenh ctrl xuong, dua tren trang
        thai live ("" khi khong co thong tin live).
        - no_endpoints (server khong cap poll URLs): app tu thu
          lai; quet QR lai KHONG sua duoc (kenh phai tu mo sau QR)
          -> chi duong thu tay POST /api/sync/retry.
        - refresh_failed + 600 (phien het han): quet QR lai.
        - kicked_out (server bao dung -69): quet QR lai mo phien
          moi.
        - stopped (kenh dung): thu POST /api/sync/retry."""
        info = self._ctrl_status_info()
        if not info:
            return ""
        ctrl = info.get("ctrl", "") or "?"
        sync = info.get("sync", "") or "?"
        sync_error = str(info.get("sync_error", ""))
        if "600" in sync_error:
            hint = ("phien het han (600) — quet QR lai de dang "
                    "nhap lai")
        elif ctrl == "kicked_out":
            hint = ("kenh ctrl bi server da ra (-69) — quet QR lai "
                    "de mo phien moi")
        elif ctrl == "no_endpoints":
            hint = ("kenh sync/ctrl chua co endpoint (getLoginInfo "
                    "khong tra poll URLs) — app dang tu thu lai, "
                    "thu POST /api/sync/retry de mo lai kenh")
        elif ctrl == "stopped":
            hint = "kenh ctrl da dung — thu POST /api/sync/retry " \
                   "de mo lai kenh"
        elif ctrl == "logged_out":
            hint = "chua dang nhap Zalo — quet QR de dang nhap"
        else:
            hint = ("kiem tra /api/status roi thu POST "
                    "/api/sync/retry")
        return " (kenh ctrl: %s; sync: %s — %s)" % (ctrl, sync, hint)

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
                  visibility=0, ttl=0, styles=None, mentions=None):
        """11151 (1-1) / 11163 (nhom). Body {message, clientId:
        NUMBER, imei, toid|grid, visibility (nhom), ttl} — ttl =
        ms tu xoa cua hoi thoai, 0 = khong tu xoa (SERVICE-MAP.md
        §3.1). Tra ve data giai ma + clientId de UI map tin dang
        gui."""
        if not message or not str(message).strip():
            raise ValueError("chat: message rong")
        client_id = _new_client_id()
        # Dinh dang chu (dam/nghieng/mau/co): textProperties = {"styles":[{start,len,st}],"ver":0}, start/len tinh theo
        # UTF-16, dung cach zca-js 2.1.2 (sendMessage.js handleStyles) va add-on zalo_bot cu. Xem rich_text.py.
        extra = {"textProperties": rich_text.text_properties(
            rich_text.validate_styles(message, styles))} if styles else {}
        info = build_mentions(message, mentions) if thread_type == "group" else []        # 1-1 khong co mention (Zalo PC / zca-js bo qua)
        if info:
            # Nhu Zalo PC `sendMentionMessage`: POST /api/group/mention {grid, message, clientId, mentionInfo (chuoi JSON), language, visibility}
            # (+ ttl / dinh dang chu neu co, nhu zca-js); khong kem imei.
            body = {"grid": str(thread_id), "message": message, "clientId": client_id,
                    "mentionInfo": json.dumps(info, separators=(",", ":"), ensure_ascii=False),
                    "language": protocol.LANGUAGE, "visibility": visibility, "ttl": int(ttl), **extra}
            data = self._post_form(GROUP_DOMAIN, "/api/group/mention", body, "POST /api/group/mention")
        elif thread_type == "group":
            body = {"message": message, "clientId": client_id,
                    "imei": self.device_id, "visibility": visibility,
                    "grid": str(thread_id), "ttl": int(ttl), **extra}
            url = _url_with_params(GROUP_DOMAIN, "/api/group/sendmsg",
                                   body, self.zpw_enk)
            data = self._get(url, "GET /api/group/sendmsg")
        else:
            body = {"message": message, "clientId": client_id,
                    "imei": self.device_id, "toid": str(thread_id),
                    "ttl": int(ttl), **extra}
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
    def _upload_async(self, thread_type, thread_id, file_name, data):
        """Buoc 1 + 1.5 cua gui file: tai len theo khoi (asyncfile/upload 11776/13000) roi DOI event ctrl `file_done` de co URL.
        Dung chung cho send_file (buoc 2 = asyncfile/msg) va send_voice (buoc 2 = forward msgType 3, giong zalo cu:
        zca-js uploadAttachment tai .aac nhu tep thuong). Tra {file_id, file_url, client_id, total_size}.
        Het gio / khong co kenh ctrl / khong co URL -> ZaloChatError, KHONG gui buoc 2 khong co fileUrl."""
        is_group = thread_type == "group"
        client_id = _new_client_id()
        total_size = len(data)
        total_chunks = (total_size + FILE_CHUNK_SIZE - 1) \
            // FILE_CHUNK_SIZE
        if is_group:
            upload_path = "/api/group/asyncfile/upload"
            type_param = TYPE_FILE_GROUP
        else:
            upload_path = "/api/message/asyncfile/upload"
            type_param = TYPE_FILE_USER
        # -- buoc 1: upload chunked ------------------------------------
        file_id = None
        upload_data = {}
        for chunk_id in range(1, total_chunks + 1):
            chunk = data[(chunk_id - 1) * FILE_CHUNK_SIZE:
                         chunk_id * FILE_CHUNK_SIZE]
            params = {"totalChunk": total_chunks,
                      "fileName": file_name,
                      "clientId": client_id,
                      "totalSize": total_size,
                      "imei": self.device_id,
                      "chunkId": chunk_id}
            if is_group:
                params["grid"] = str(thread_id)
            else:
                params["toid"] = str(thread_id)
            url = _multipart_url(FILES_DOMAIN, upload_path, params,
                                 self.zpw_enk, type_param)
            body, ctype = build_multipart(
                {}, [("chunkContent", file_name,
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
                        "chat: upload file xong nhung Zalo khong "
                        "tra fileId (finished/fileId thieu): %r"
                        % (upload_data,), error_code=0)
                file_id = upload_data["fileId"]
        # -- buoc 1.5: doi event async ctrl file_done ----------------
        # Bundle DOI event (waitAsyncFileInfo) truoc buoc 2 de lay
        # URL file; chunk-response chi co {finished:1, fileId} —
        # bundle KHONG BAO GIO lay URL tu chunk-response (truong
        # url trong chunk-response thuoc nhanh DUPLICATE/cache),
        # nen ham nay LUON doi event (wait tra ngay neu event da
        # ve truoc — cache-hit cua bundle). Het gio / khong co
        # kenh ctrl / khong co waiter -> loi ro, KHONG gui buoc 2
        # (gui buoc 2 khong co fileUrl la cai gay ra 114 live o
        # voice).
        waiter = self.file_async
        if waiter is None:
            raise ZaloChatError(
                "chat: gui file chua nhan duoc URL file — khong co "
                "kenh cho event async ctrl file_done (99101); "
                "khong gui buoc 2 khong co fileUrl"
                + self._ctrl_hint(), error_code=0)
        if not getattr(waiter, "feeder_running", True):
            raise ZaloChatError(
                "chat: gui file chua nhan duoc URL file — kenh ctrl "
                "(99101) chua chay; khong gui buoc 2 khong co "
                "fileUrl" + self._ctrl_hint(), error_code=0)
        got = waiter.wait(file_id, self.file_async_timeout)
        file_url = None
        if isinstance(got, dict):
            url = got.get("url")
            file_url = url if isinstance(url, str) and url else None
        if not file_url:
            raise ZaloChatError(
                "chat: gui file het %.0f giay cho event async ctrl "
                "file_done ma khong thay URL file cho fileId da "
                "upload xong; khong gui buoc 2 khong co fileUrl"
                % self.file_async_timeout + self._ctrl_hint(),
                error_code=0)
        return {"file_id": file_id, "file_url": file_url,
                "client_id": client_id, "total_size": total_size}

    def send_file(self, thread_type, thread_id, filename, data,
                  mime="application/octet-stream", ttl=0):
        """Gui file thuong (Word/Excel/PDF/...) — DUONG HAI BUOC
        cua upload-manager (bundle PC 26.11.10; xem ghi chu o dau
        module):
        Buoc 1: POST multipart chunkContent len asyncfile/upload
        11776 (1-1) / 13000 (nhom), moi chunk 256_000 byte, params
        AES {totalChunk, fileName, clientId NUMBER, totalSize, imei,
        chunkId, toid|grid} (KHONG fileType — chi Voice moi co;
        KHONG checksum — bundle xoa truoc khi gui; KHONG
        isE2EE/jxl), & type=2/11. Chunk cuoi tra data {finished: 1,
        fileId}.
        Buoc 1.5: DOI event ctrl `file_done` {fileId, url} qua
        waitAsyncFileInfo (kenh ctrl 99101 — xem ctrl_poll.py),
        toi da FILE_ASYNC_WAIT_SECONDS (mac dinh 120 s nhu bundle).
        Buoc 2: POST form params=<AES JSON> len asyncfile/msg
        11777 (1-1) / 13001 (nhom), body la item getFileAsyncItem:
        {fileId, checksum (md5 hex cua toan file), checksumSha: "",
        extension, totalSize, fileName, clientId NUMBER, fType: 1,
        fileCount: 0, fdata: "{}", toid|grid, imei (chi 1-1),
        zsource: -1} + fileUrl (tu event file_done — DOI truoc
        buoc 2, xem ctrl_poll.py).
        Response giai ma rong (None/{}) -> ZaloChatError "khong co
        ma tin": Zalo tra 200/error_code=0 nhung khong tao tin nao
        thi khong duoc bao thanh cong (loi cam 07/11, giong
        send_photo). Kiem tra truoc (validate_attachment): ten
        thieu / file rong / file qua lon -> ValueError voi loi ro
        rang, khong goi Zalo. Thu lai gioi han khi gap 112 o CA
        hai buoc (tam thoi theo bundle; dung cung clientId/body
        de server dedup, tranh gui trung).

        GHI CHU TRUNG THUC VE DUONG CU (DA XAC NHAN CHET, vong
        405 2026-11-07 — khong con la suy luan theo shape):
        API sendFile truc tiep (11146/11191, POST multipart
        fileContent len sharefile_full) co 0 caller trong bundle
        JS — khong co code nao goi no (giong sendVoice chet cua
        voicemp3/sendmp3, live van 112). Live 2026-11-07 09:xx
        +07: gui Word/Excel/PDF cho Dai ca bi banner «chat: POST
        /api/message/sharefile_full network status=405» — Zalo
        upstream tu choi duong chet do. Host KHONG phai nguyen
        nhan o day: send_file cu da dung FILES_DOMAIN
        (files-wpa) dung nhu bundle (apiFileDomain), khac voi loi
        405 cua anh (e0d6eed: send_photo sai host chat-wpa).
        Duong that duy nhat trong JS la sendFileByChunkV2 (2 call
        site: File va Photo) -> uploadFile -> sendMsgAsync ->
        _sendMsgFileAsync -> API sendMsgFileAsync (15136113).
        zca-js 2.1.2 khop hoan toan: uploadAttachment dung
        asyncfile/upload, sendMessage "others" dung asyncfile/msg
        — khong co sharefile_full trong ca thu vien.
        Chi tiet item (getFileAsyncItem, 4552015): extension =
        getExtension(fileName) (sau dau cham cuoi, rong neu dai
        >= 7); fileName = formatFileNameBeforeSend (Unicode
        normalize); fType = FILE_FTYPE.FILE = 1 (Ne={FILE:1,
        FOLDER:2}); fileCount = totalFile||0 (gui 1 file rieng
        -> 0); fdata = JSON.stringify(fdata || {}) (file thuong
        -> "{}"). zca-js viet `extention` (sai chinh ta) o buoc 2
        — bundle exe thang nen dung `extension`. zca-js khong gui
        imei o buoc 2, bundle thi them imei cho 1-1
        (sendMsgFileAsync) — app gui theo bundle, giong voice.
        Chunk 256_000 byte = getDefaultChunkSize cua bundle
        (settings.sharefile.chunk_size_file neu >= 64_000, khong
        thi 256e3); chunkId 1..totalChunk (zca-js cung vay).
        KHONG lay fileUrl tu chunk-response (truong url do thuoc
        nhanh DUPLICATE/cache — giong bai hoc 114 cua voice):
        LUON doi event file_done, het gio / kenh ctrl chua chay /
        khong co waiter -> loi ro, KHONG gui buoc 2."""
        validate_attachment("file", filename, mime, data)
        file_name = _normalize_filename(filename)
        extension = _file_extension(file_name)
        is_group = thread_type == "group"
        up = self._upload_async(thread_type, thread_id, file_name, data)
        client_id, total_size = up["client_id"], up["total_size"]
        file_id, file_url = up["file_id"], up["file_url"]
        send_path = ("/api/group/asyncfile/msg" if is_group
                     else "/api/message/asyncfile/msg")
        # -- buoc 2: gui bang fileId -----------------------------------
        item = {"fileId": file_id,
                "checksum": hashlib.md5(data).hexdigest(),
                "checksumSha": "",
                "extension": extension,
                "totalSize": total_size,
                "fileName": file_name,
                "clientId": client_id,
                "fType": 1,
                "fileCount": 0,
                "fdata": "{}",
                "zsource": -1,
                "fileUrl": file_url}
        if int(ttl or 0) > 0:
            # Hoi thoai dang bat tu xoa (nhom AI Camera: 1 ngay): Zalo doi tin gui vao kem dung `ttl` cua no, thieu thi tra inner 801 va dang dong
            # «Khong the gui tin nhan tu xoa do dang dung phien ban cu» (anh da sua 13/11, tep thuong con sot: loi 801 luc 17:18 cung ngay).
            item["ttl"] = int(ttl)
        if is_group:
            item["grid"] = str(thread_id)
        else:
            item["toid"] = str(thread_id)
            item["imei"] = self.device_id
        send_data = self._post_form_retry(
            FILES_DOMAIN, send_path, item, "POST %s" % send_path)
        if not send_data:
            # Zalo tra 200/error_code=0 nhung khong tao tin nao
            # (data rong) — phai bao loi that: neu tra ok, route
            # se tra ok:true + message local, UI hien file nhu da
            # gui trong khi ben kia khong nhan duoc (thanh cong
            # gia — loi cam 07/11, giong send_photo truoc khi sua).
            # Tin gui thanh cong that luon co data {msgId, ...}.
            raise ZaloChatError(
                "file: Zalo tra ve khong co ma tin — file chua duoc "
                "tao (data rong sau khi giai ma)")
        return {"data": send_data, "client_id": client_id,
                "file_id": file_id}

    def _head_size(self, url):
        """Kich thuoc video (byte) tu Content-Length cua yeu cau HEAD — zca-js sendVideo cung lam vay (HEAD khong duoc thi thu GET Range 0-0).
        Loi mang/HTTP -> ZaloChatError ro rang: may chu Zalo khong tai duoc dia chi nay thi tin video se hong, bao loi som tot hon."""
        def ask(method):
            headers = {"User-Agent": "Mozilla/5.0"}
            if method == "GET":
                headers["Range"] = "bytes=0-0"
            with urllib.request.urlopen(urllib.request.Request(url, method=method, headers=headers), timeout=15) as r:
                return r.headers
        try:
            try:
                h = ask("HEAD")
            except urllib.error.HTTPError as e:
                if e.code not in (405, 501):
                    raise
                h = ask("GET")
        except urllib.error.HTTPError as e:
            raise ZaloChatError("video: dia chi video tra HTTP %d (Zalo cung se khong tai duoc): kiem tra URL cong khai / chu ky het han" % e.code)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ZaloChatError("video: khong mo duoc dia chi video: %s" % str(e)[:120])
        rng = h.get("Content-Range") or ""
        if "/" in rng and rng.rsplit("/", 1)[1].isdigit():
            return int(rng.rsplit("/", 1)[1])
        try:
            return int(h.get("Content-Length") or 0)
        except ValueError:
            return 0

    def send_video(self, thread_type, thread_id, video_url, thumbnail_url="", duration=0, width=0, height=0, message="", ttl=0):
        """Gui VIDEO THAT (khung phat duoc ngay trong chat, khong phai tep dinh kem) — Y HET zca-js sendVideo va zalo_bot cu (sendVideoByAccount):
        POST form params=<AES JSON> len {files-wpa}/api/message/forward (1-1) | /api/group/forward (nhom), msgType 5, zsource 704,
        msgInfo = JSON {videoUrl, thumbUrl, duration (mili giay), width, height, fileSize, properties {type 1003...}, title}.
        KHONG tai video len Zalo: gui DIA CHI, may chu Zalo tu tai ve roi luu lai (ban ghi VideoGroup cu o nhom AI Camera co url dlfl.vn) — nen dia chi
        phai cong khai. Khong co anh bia thi dung chinh dia chi video (zalo_bot cu cung vay)."""
        video_url = str(video_url or "").strip()
        if not video_url.lower().startswith(("http://", "https://")):
            raise ValueError("video: can dia chi http(s) cong khai ma Zalo tai duoc")
        thumb = str(thumbnail_url or "").strip() or video_url
        if not thumb.lower().startswith(("http://", "https://")):
            raise ValueError("video: anh bia phai la dia chi http(s)")
        if thread_type not in ("user", "group"):
            raise ValueError("video: type phai la user|group")
        size = self._head_size(video_url)
        client_id = _new_client_id()           # bo sinh chung (tang don dieu, an toan da luong): hai tin cung mili giay khong trung ma
        info = {"videoUrl": video_url, "thumbUrl": thumb, "duration": int(duration or 0), "width": int(width or 1280),
                "height": int(height or 720), "fileSize": int(size),
                "properties": {"color": -1, "size": -1, "type": 1003, "subType": 0,
                               "ext": {"sSrcType": -1, "sSrcStr": "", "msg_warning_type": 0}},
                "title": str(message or "")}
        is_group = thread_type == "group"
        params = {("grid" if is_group else "toId"): str(thread_id), "clientId": str(client_id), "ttl": int(ttl or 0), "zsource": 704,
                  "msgType": 5, "msgInfo": json.dumps(info, separators=(",", ":"), ensure_ascii=False), "imei": self.device_id}
        if is_group:
            params["visibility"] = 0
        path = "/api/group/forward" if is_group else "/api/message/forward"
        data = self._post_form_retry(FILES_DOMAIN, path, params, "POST %s" % path)
        if not data:
            raise ZaloChatError("video: Zalo tra ve khong co ma tin — video chua duoc tao (data rong sau khi giai ma)")
        return {"data": data, "client_id": client_id, "video_url": video_url}

    def send_video_file(self, thread_type, thread_id, filename, data, caption="", width=0, height=0, duration_ms=0, ttl=0, thumb_jpeg=None):
        """Gui TỆP VIDEO nguoi dung chon (WebUI) thanh TIN VIDEO co chu thich nhu Zalo PC: tai video len Zalo (asyncfile/upload + file_done, nhu tep thuong) lay URL
        cua Zalo, tai them anh bia JPEG (neu co) de lay URL anh, roi gui `send_video` (forward msgType 5, title = chu thich). URL do Zalo giu nen khong phu thuoc may nha.
        Loi tai len -> ZaloChatError (de caller quay ve gui tep thuong)."""
        up = self._upload_async(thread_type, thread_id, filename, data)
        video_url = up["file_url"]
        thumb_url = ""
        if thumb_jpeg:
            try:
                thumb_url = self._upload_async(thread_type, thread_id, "thumb.jpg", bytes(thumb_jpeg))["file_url"]
            except ZaloChatError:
                thumb_url = ""             # khong co anh bia: van gui video (send_video dung chinh URL video lam bia)
        res = self.send_video(thread_type, thread_id, video_url, thumb_url, duration_ms, width, height, caption, ttl)
        res["video_url"] = video_url
        return res

    def send_photo(self, thread_type, thread_id, filename, data,
                   mime="image/jpeg", width=0, height=0, visibility=0,
                   desc="", photo_bundle=None, ttl=0):
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
            if ttl:                                  # cuoc tro chuyen dang bat tu xoa: Zalo doi anh kem dung ttl cua no (thieu -> inner 801)
                params["ttl"] = int(ttl)
            params["grid"] = str(thread_id)
            url = _multipart_url(FILES_DOMAIN, "/api/group/sendpt",
                                 params, self.zpw_enk, TYPE_FILE_GROUP)
            where = "POST /api/group/sendpt"
        else:
            params = {"clientId": client_id, "desc": desc,
                      "width": int(width), "height": int(height)}
            if photo_bundle is not None:
                params.update(photo_bundle)
            if ttl:
                params["ttl"] = int(ttl)
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
                   mime="audio/aac", ttl=0):
        """Gui tin thoai (bong bong ghi am phat duoc) — DUNG CACH ZALO CU (zalo_bot: voiceAac.js + zca-js sendVoice):
        1) du lieu da la AAC-LC 16 kHz mono ADTS (server doi bang voice_transcode.ensure_voice_aac truoc khi toi day);
        2) tai len nhu TEP THUONG qua asyncfile/upload + doi event `file_done` lay URL (_upload_async) — zca-js
           uploadAttachment xu ly .aac nhu tep thuong;
        3) gui bang `forward` tren may chu tep: POST {files-wpa}/api/message/forward (1-1) | /api/group/forward (nhom),
           params AES {toId|grid, ttl, zsource: -1, msgType: 3, clientId, msgInfo: JSON {voiceUrl, m4aUrl, fileSize},
           imei, visibility (nhom)} — dung sendVoice.js cua zca-js 2.1.2.
        Tai sao bo duong cu (voice/upload 12060/12063 + asyncfile/msg, `fileType: aac`): Zalo tra 114 ngay o buoc tai len
        (do thay 10/11/2026: 0,3-0,8 giay, ca mp3 lan aac), con duong tep thuong thi dang chay tot. Du lieu rong bi tu choi
        truoc khi goi mang. Zalo tra data rong (khong tao tin) -> ZaloChatError, khong bao thanh cong gia."""
        validate_attachment("voice", filename, mime, data)
        try:
            ttl = int(ttl or 0)
        except (TypeError, ValueError):
            raise ValueError("chat: ttl phai la so")
        if ttl < 0:
            raise ValueError("chat: ttl khong am")
        file_name = _normalize_filename(filename)
        if not file_name.lower().endswith(".aac"):
            file_name = "voice.aac"
        up = self._upload_async(thread_type, thread_id, file_name, data)
        client_id = up["client_id"]
        info = json.dumps({"voiceUrl": up["file_url"], "m4aUrl": up["file_url"],
                           "fileSize": up["total_size"]},
                          separators=(",", ":"))
        item = {"ttl": ttl, "zsource": -1, "msgType": 3,
                "clientId": str(client_id), "msgInfo": info,
                "imei": self.device_id}
        if thread_type == "group":
            item["grid"] = str(thread_id)
            item["visibility"] = 0
            path = "/api/group/forward"
        else:
            item["toId"] = str(thread_id)
            path = "/api/message/forward"
        send_data = self._post_form_retry(FILES_DOMAIN, path, item,
                                          "POST %s" % path)
        if not send_data:
            raise ZaloChatError(
                "voice: Zalo tra ve khong co ma tin — tin thoai chua "
                "duoc tao (data rong sau khi giai ma)")
        return {"data": send_data, "client_id": client_id,
                "file_id": up["file_id"], "voice_url": up["file_url"]}

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

    @staticmethod
    def msg_infos(raws, group, own_uid=""):
        """`data` cua msgInfos (deliveredv2 / seenv2), dung nhu Zalo PC 26.11.10 (bundle `sendSeenV2` / zca-js sendDeliveredEvent): moi tin
        {cmi: cliMsgId, gmi: msgId, si: nguoi gui, di: nguoi nhan ("0" khi la minh), mt: loai tin, st/at/cmd: gia tri that hoac -1, ts}.
        `raws` la dict tin GOC Zalo gui ve (msg["raw"]); toi da 50."""
        def num(v):
            return -1 if v in (None, "") else v
        out = []
        for e in list(raws)[-50:]:
            sender = str(e.get("uidFrom") or e.get("fromUid") or "")
            to = str(e.get("idTo") or e.get("toUid") or "")
            if group and to.startswith("g"):
                to = to[1:]                             # GROUPID_PREFIX cua bundle
            out.append({"cmi": e.get("cliMsgId"), "gmi": e.get("msgId"), "si": sender,
                        "di": to if (group or (to and to != str(own_uid) and to != sender)) else "0",
                        "mt": e.get("originMsgType") or e.get("msgType"),
                        "st": num(e.get("st")), "at": num(e.get("at")), "cmd": num(e.get("cmd")),
                        "ts": e.get("ts") or e.get("sendDttm") or -1})
        return out

    def send_delivered_v2(self, thread_type, thread_id, raws, seen=False, own_uid=""):
        """POST /api/message/deliveredv2 (12117) / /api/group/deliveredv2 (12119): bao nguoi gui «da nhan». Zalo PC gui ngay khi tin den."""
        group = thread_type == "group"
        infos = {"seen": 1 if seen else 0, "data": self.msg_infos(raws, group, own_uid)}
        body = {}
        if group:
            infos["grid"] = str(thread_id)
            body["imei"] = self.device_id
        body["msgInfos"] = json.dumps(infos, separators=(",", ":"), ensure_ascii=False)
        domain, path = (GROUP_DOMAIN, "/api/group/deliveredv2") if group else (CHAT_DOMAIN, "/api/message/deliveredv2")
        return self._post_form(domain, path, body, "POST " + path)

    def send_seen_v2(self, thread_type, thread_id, raws, own_uid=""):
        """POST /api/message/seenv2 (12118) / /api/group/seenv2 (12124): bao «da xem». Zalo PC luon kem imei."""
        group = thread_type == "group"
        infos = {"data": self.msg_infos(raws, group, own_uid)}
        infos["grid" if group else "senderId"] = str(thread_id)
        body = {"msgInfos": json.dumps(infos, separators=(",", ":"), ensure_ascii=False), "imei": self.device_id}
        domain, path = (GROUP_DOMAIN, "/api/group/seenv2") if group else (CHAT_DOMAIN, "/api/message/seenv2")
        return self._post_form(domain, path, body, "POST " + path)

    def mark_seen(self, thread_type, thread_id, msg_ids=None, store=None, own_uid=""):
        """Danh dau «da xem» nhu Zalo PC: tim tin DEN goc (msg["raw"]) trong kho `store` (message_store.MessageStore) — theo `msg_ids` neu co
        (khop id / msgId / cliMsgId), khong co thi toi da 50 tin den moi nhat — roi gui seenv2. Khong tim duoc tin goc (kho trong) thi roi ve
        send_seen v1."""
        ids = {str(i) for i in (msg_ids or []) if str(i)}
        raws = []
        if store is not None:
            for m in store.messages_for(thread_type, thread_id, 200):           # moi nhat truoc
                raw = m.get("raw") if isinstance(m, dict) else None
                if not isinstance(raw, dict) or m.get("is_self") or m.get("direction") == "out":
                    continue
                if ids and not ids & {str(m.get("id")), str(raw.get("msgId")), str(raw.get("cliMsgId"))}:
                    continue
                raws.append(raw)
                if len(raws) >= 50:
                    break
        if raws:
            raws.reverse()                                                          # cu -> moi, nhu Zalo PC
            return self.send_seen_v2(thread_type, thread_id, raws, own_uid=own_uid)
        return self.send_seen(thread_type, thread_id, msg_ids)

    def send_seen(self, thread_type, thread_id, msg_ids=None):
        """v1 (11150 1-1 / 11167 nhom) — dang cua Zalo PC (bundle `sendSeen` / `sendGroupSeen`): POST params={msg_ids:[so], senderId | grid}.
        Ban cu gui GET kem khoa `toid` (sai dang). Con dung lam du phong khi khong co tin goc de gui v2."""
        ids = [int(i) if str(i).isdigit() else str(i) for i in (msg_ids or [])]
        if thread_type == "group":
            body = {"msg_ids": ids, "grid": str(thread_id)}
            return self._post_form(GROUP_DOMAIN, "/api/group/seen", body, "POST /api/group/seen")
        body = {"msg_ids": ids, "senderId": str(thread_id)}
        return self._post_form(CHAT_DOMAIN, "/api/message/seen", body, "POST /api/message/seen")
