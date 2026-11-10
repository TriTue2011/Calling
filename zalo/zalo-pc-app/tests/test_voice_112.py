"""Tin nhan thoai — DUONG HAI BUOC (upload chunked 12060/12063 +
asyncfile/msg 11777/13001), thay duong truc tiep voicemp3/sendmp3.

BANG CHUNG BUNDLE (compact-app-pc.5c0110a3a8749b3aacde.js,
Zalo PC 26.11.10) — doc truc tiep tu bundle, khong phai suy doan:
- sendVoice (voicemp3 11148 / sendmp3 11169) CO DINH NGHIA nhung
  KHONG CO caller nao trong toan bo app: "sendVoice(" xuat hien
  dung 1 lan moi file (dinh nghia), ".sendVoice(" = 0 (renderer,
  lazy chunk, worker, main-dist). Dispatcher gui tin cua renderer
  con tu choi thang MSG_VOICE: logCoreError("not support send this
  type"). Duong truc tiep la code chet o ban nay — va live
  2026-11-06 08:36 +07 tren 965ce96 van tra inner 112 sau khi da
  sua clientId STRING (b0e98c2). Khong dung duong nay nua.
- Duong upload-manager ho tro Voice day du: getInfoUploadVoiceFromData
  -> {files-wpa}/api/message/voice/upload (12060) / /api/group/
  voice/upload (12063), type 2/11; buildSendChunksInfo chia file
  thanh chunk 256_000 byte (getDefaultChunkSize: settings.sharefile.
  chunk_size_file neu >= 64_000, khong thi 256e3), moi chunk la
  FormData chunkContent = File([chunk], ten file), URL params AES
  {totalChunk, fileName, clientId NUMBER, totalSize, imei, chunkId,
  toid|grid, fileType: "aac"|"amr"} (KHONG co checksum trong params
  — bundle `delete` no; clientId o day la NUMBER qua JSON.stringify,
  khac voi STRING ghep tay cua sendVoice/sendFile truc tiep);
  chunk cuoi tra data {finished: 1, fileId} (handleSendChunkResp:
  hoan tat <=> finished && fileId); getFileAsyncItem(Voice) ->
  {fileId, checksum (md5 hex), checksumSha: "", totalSize, clientId,
  fType, toid|grid} — nhung fType = extData.fType, ma extData cua
  task upload Voice duy nhat lan duoc trong bundle (main-startup
  lazy chunk, dich vu khoi phuc voice-to-text _upload) la
  {uploadMainType: Voice, e2ee: false}, KHONG co fType, nen
  JSON.stringify loai truong do: item voice that KHONG co fType.
  Async event tra {aac, amr, secureKey} -> fileUrl = amr||aac,
  aacUrl = aac chi khi co amr, secureKey neu event co
  (__waitAsyncFileInfo); cac URL nay KHONG BAO GIO lay tu
  chunk-response (handleSendChunkResp chi doc finished/fileId).
- Dinh dang that la AAC (khong phai MP3): fileType aac/amr; tin
  thoai that do duoc la AAC-LC 16 kHz mono 64 kbps ADTS .aac
  (Node.js voiceAac.js + voiceMessage.test.js); ten file tai ve
  cua tin thoai ket bang .aac; forward-voice dung m4aUrl/voiceUrl.

KET LUAN LOI 114 (kiem toan tham so 2026-11-06, live retest
09:46 +07: 112 het, nay 114 "Tham so khong hop le"):
- Buoc 1 khop bundle tren moi tham so chung minh duoc (xem
  test_voice_two_step_params_match_bundle).
- Buoc 2: fType LOAI TRU (chung minh o tren). Nghi pham chinh la
  buoc 2 THIEU fileUrl (va secureKey): client that CHI gui item
  sau khi cho async event voice_aac_success qua waitAsyncFileInfo;
  app gui ngay sau chunk cuoi nen item khong co URL tin thoai nao
  — khoang trong async-event nay da duoc lap bang viec DOI event
  ctrl 99101 truoc buoc 2 (xem test_voice_async_114.py +
  ctrl_poll.py). Phan tham so sua duoc o day: bo viec gui kem
  fileUrl/aacUrl lay tu chunk-response (nguon sai — xem
  test_voice_114_step2_ignores_chunk_response_urls).
- Chua lan duoc: ten file ghi am that cua recorder native (app
  dung "voice.aac") va chunk_size_file that (app dung 256000 theo
  default cua bundle khi setting < 64000) — neu live retest van
  114 sau khi co event thi kiem 2 diem nay.

BUOC GUI SAU UPLOAD — DA XAC NHAN DUNG (vong 114, 2026-11-06):
asyncfile/msg (11777/13001, sendMsgFileAsync) la endpoint dung
cho Voice. Bang chung moi so voi vong truoc: sendMsgFileAsync la
API DUY NHAT (khong E2EE) POST dung item getFileAsyncItem
(caller duy nhat trong JS: UploadAsyncControl._sendMsgFileAsync);
bang lenh 231 muc khong co endpoint gui-tin-thoai nao khac (khong
co /api/message/voice gui bang URL; voicemp3/sendmp3 chet, 0
caller; dispatcher tu choi MSG_VOICE); zsource -1 la mac dinh cua
buildParams/transform. GIOI HAN CON LAI: khong co caller Voice
truc tiep nao quan sat duoc trong JS — sendMsgAsync chi xu ly
Photo/File, sendFileByChunkV2 tra thang urlRes cho Voice/Video
(2 call site trong JS chi la File/Photo), buoc gui sau upload nam
o lop native ngoai JS. fType LOAI TRU (xem chung minh o tren):
extData Voice duy nhat lan duoc khong co fType — app khong gui
fType la dung. CHO EVENT ASYNC (loi 114): bundle DOI event ctrl
`voice_aac_success` qua waitAsyncFileInfo truoc buoc 2 de lay URL
(amr/aac) — xem test_voice_async_114.py + ctrl_poll.py; cac test
o file nay dung waiter gia tra URL ngay (cache-hit), con truong
hop doi that / het gio duoc pin o file do.

112: van la loi chung (STR_ERROR_CODE_UNKNOWN), bundle coi la tam
thoi va thu lai sau 1-5 giay — app thu lai gioi han (2 lan, cach
2 giay, cung clientId/body) o ca buoc chunk lan buoc gui.

Mock kiem chung doc lap (khong dang nhap that, khong gui that).
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import voice_transcode as voice_mod  # noqa: E402

# ADTS AAC gia (header sync FF F1 + payload xac dinh) — du de mock
# kiem tra chunk bytes; file that duoc server route doi bang ffmpeg.
FAKE_AAC = b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\x00" * 100

# URL ghi am gia ma event ctrl voice_aac_success mang ve (xem
# test_voice_async_114.py): waiter gia tra ngay (cache-hit).
VOICE_AMR_URL = "https://f1-voice-aac-dl.zdn.vn/test.amr"
VOICE_AAC_URL = "https://f1-voice-aac-dl.zdn.vn/test.aac"


class _ImmediateVoiceWaiter:
    """Waiter gia cho test o file nay: event ctrl da den truoc
    (cache-hit cua bundle) — tra ngay {amr, aac}."""

    feeder_running = True

    def wait(self, file_id, timeout_s):
        return {"amr": VOICE_AMR_URL, "aac": VOICE_AAC_URL}


class _ImmediateFileWaiter:
    """Waiter gia: event ctrl file_done da den truoc (cache-hit
    cua bundle) — tra ngay {"url"}."""

    feeder_running = True

    def wait(self, file_id, timeout_s):
        return {"url": "https://f1-file-dl.zdn.vn/test.docx"}


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    chat_mod.CHAT_DOMAIN = mock.base
    chat_mod.FILES_DOMAIN = mock.base
    chat_mod.GROUP_DOMAIN = mock.base


class SleepRecorder:
    """sleep gia cho test: ghi lai cac khoang cho, khong cho that."""

    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


def make_chat(mock, sleep=None):
    t = app_server.make_transport("sek-test")
    return chat_mod.Chat(t, "dev-1", TEST_SESSION_KEY,
                         voice_async=_ImmediateVoiceWaiter(),
                         voice_async_timeout=5.0,
                         file_async=_ImmediateFileWaiter(),
                         file_async_timeout=5.0, sleep=sleep)


def _uploaded_chunk(mock, path, occurrence=0):
    """(filename, mime, bytes) cua chunkContent o lan goi thu
    `occurrence` toi `path` (doc tu seen_post_raw, bytes that)."""
    raws = [raw for p, raw in mock.seen_post_raw if p == path]
    assert len(raws) > occurrence, (path, len(raws))
    # Moi chunk co boundary RIENG (build_multipart sinh moi lan),
    # nen phai lay Content-Type cua dung lan goi do, khong phai
    # cua lan dau.
    ctypes = [headers.get("Content-Type", "")
              for pp, _qs, headers in mock.seen if pp == path]
    assert len(ctypes) > occurrence, (path, len(ctypes))
    ctype = ctypes[occurrence]
    _fields, files = chat_mod.parse_multipart(raws[occurrence], ctype)
    assert "chunkContent" in files, files.keys()
    assert "fileContent" not in files, files.keys()
    return files["chunkContent"]


# -- buoc 1 + 2: params tren day (wire) khop bundle --------------------











def test_file_params_match_bundle():
    """File thuong di DUONG HAI BUOC (bundle sendFileByChunkV2 ->
    uploadFile -> sendMsgAsync -> _sendMsgFileAsync ->
    sendMsgFileAsync): buoc 1 chunk len asyncfile/upload voi params
    CHI {totalChunk, fileName, clientId NUMBER, totalSize, imei,
    chunkId, toid|grid} (KHONG fileType — chi Voice moi co; KHONG
    checksum — bundle xoa truoc khi gui); buoc 2 la item
    getFileAsyncItem: {fileId, checksum (md5 hex), checksumSha "",
    extension, totalSize, fileName, clientId NUMBER, fType 1,
    fileCount 0, fdata "{}", toid|grid, imei (chi 1-1), zsource -1}
    + fileUrl tu event ctrl file_done. clientId la NUMBER o ca hai
    buoc, giong nhau giua upload va buoc 2 (JSON.stringify cua
    upload-manager) — KHAC voi duong truc tiep sharefile_full cu
    (clientId STRING ghep tay, code chet 0 caller, Zalo tra 405
    live 2026-11-07)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        data = b"hello file"
        res = chat.send_file("user", "20001", "hello.txt",
                             data, "text/plain")
        assert res["data"]["msgId"] == "msg-file-1", res
        upload = mock.file_upload_bodies[0]["body"]
        assert set(upload.keys()) == {
            "totalChunk", "fileName", "clientId", "totalSize",
            "imei", "chunkId", "toid"}, upload
        assert upload["totalChunk"] == 1, upload
        assert upload["chunkId"] == 1, upload
        assert upload["fileName"] == "hello.txt", upload
        assert upload["totalSize"] == len(data), upload
        assert isinstance(upload["clientId"], int), upload
        assert upload["clientId"] == res["client_id"], upload
        body = mock.file_send_bodies[0]["body"]
        assert set(body.keys()) == {
            "fileId", "checksum", "checksumSha", "extension",
            "totalSize", "fileName", "clientId", "fType",
            "fileCount", "fdata", "toid", "imei", "zsource",
            "fileUrl"}, body
        assert body["fileId"] == "file-1", body
        assert body["checksum"] == hashlib.md5(data).hexdigest(), body
        assert body["checksumSha"] == "", body
        assert body["extension"] == "txt", body
        assert body["totalSize"] == len(data), body
        assert body["fileName"] == "hello.txt", body
        assert isinstance(body["clientId"], int), body
        assert body["clientId"] == res["client_id"], body
        assert body["fType"] == 1, body
        assert body["fileCount"] == 0, body
        assert body["fdata"] == "{}", body
        assert body["toid"] == "20001", body
        assert body["imei"] == "dev-1", body
        assert body["zsource"] == -1, body
        assert body["fileUrl"] == \
            "https://f1-file-dl.zdn.vn/test.docx", body
        res = chat.send_file("group", "30001", "bao-cao.pdf",
                             b"%PDF-fake", "application/pdf")
        body = mock.file_send_bodies[1]["body"]
        assert set(body.keys()) == {
            "fileId", "checksum", "checksumSha", "extension",
            "totalSize", "fileName", "clientId", "fType",
            "fileCount", "fdata", "grid", "zsource",
            "fileUrl"}, body
        assert body["extension"] == "pdf", body
        assert body["grid"] == "30001", body
        assert "imei" not in body, body
        assert body["clientId"] == res["client_id"], body
    finally:
        mock.stop()


def test_photo_client_id_stays_number():
    """Anh KHONG doi theo voice/file: bundle _sendPhoto dung
    JSON.stringify nen clientId van la NUMBER. Test nay chan
    viec sua qua tay thanh string het."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_photo("user", "20001", "anh.jpg",
                              b"\xff\xd8\xff\xe0FAKEJPEGDATA", "image/jpeg",
                              800, 600)
        body = res["data"]["body"]
        assert isinstance(body["clientId"], int) and not \
            isinstance(body["clientId"], bool), body
        assert body["clientId"] == res["client_id"], body
        # desc rong khi khong caption (bundle _sendPhoto: desc =
        # title || ""; anh chon tu file picker khong co title).
        # Assertion cu ("anh.jpg") ghi nhan hanh vi sai — app gui
        # ten file lam caption nen ben nhan hien ten file duoi
        # moi anh (case live 07/11); sua theo bundle, xem
        # chat.send_photo.
        assert body["desc"] == "", body
        assert body["width"] == 800 and body["height"] == 600, body
    finally:
        mock.stop()


# -- 112: thu lai -------------------------------------------------------





def test_voice_empty_rejected_before_network():
    """File ghi am rong (0 byte) bi tu choi ngay, khong goi Zalo
    — tranh mot dang 112 kho hieu khac."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        try:
            chat.send_voice("user", "20001", "voice.aac", b"",
                            "audio/aac")
            raise AssertionError("expected ValueError on empty voice")
        except ValueError as e:
            assert "rong" in str(e), e
        assert mock.voice_upload_calls == 0, mock.voice_upload_calls
        assert mock.voice_send_calls == 0, mock.voice_send_calls
    finally:
        mock.stop()


# -- e2e qua route server app -------------------------------------------
BASE = ""


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def api_json(method, path, obj=None):
    data = json.dumps(obj).encode() if obj is not None else None
    return api(method, path, data, {"Content-Type": "application/json"})


def login_via_mock():
    from mock_server import TEST_PARAM_KEY
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    status, body = api_json("POST", "/api/qr/new", {})
    assert body["ok"] is True
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = api("GET", "/api/qr/status")
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def _run_server(mock):
    global BASE
    tmp = tempfile.mkdtemp(prefix="zalo-pc-voice112-test-")
    patch_domains(mock)
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    BASE = "http://127.0.0.1:%d" % port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    login_via_mock()
    # Event ctrl voice_aac_success da den truoc (registry cua
    # AppState) — neu khong, send_voice doi het timeout roi loi
    # thay vi gui buoc 2 khong co fileUrl (loi 114); mock tra
    # fileId "file-voice-1" dinh san nen deliver truoc duoc.
    state.voice_async.deliver("file-voice-1", VOICE_AMR_URL,
                              VOICE_AAC_URL)
    return httpd


def _sendvoice_via_app_bytes(filename, mime, data):
    """Gui giong het trinh duyet (app.js toggleRecord): field type
    + file la blob MediaRecorder (ten voice.webm, type
    audio/webm;codecs=opus o Chrome)."""
    mbody, mctype = chat_mod.build_multipart(
        {"type": "user"},
        [("file", filename, mime, data)])
    return api("POST", "/api/thread/20001/sendvoice",
               mbody, {"Content-Type": mctype})


def _sendvoice_via_app():
    mbody, mctype = chat_mod.build_multipart(
        {"type": "user"},
        [("file", "voice.aac", "audio/aac", FAKE_AAC)])
    return api("POST", "/api/thread/20001/sendvoice",
               mbody, {"Content-Type": mctype})




FFMPEG = shutil.which("ffmpeg")
_TMP = tempfile.mkdtemp(prefix="zalo-voice112c-webm-")


def _webm_fixture():
    """File ghi am that dang webm/opus 0.5 s (sine 440 Hz) nhu
    Chrome MediaRecorder tao ra — dung de chay het duong that qua
    route: parse multipart -> doi AAC -> upload chunk + asyncfile.
    Tra ve bytes, hoac None neu khong co ffmpeg."""
    if not FFMPEG:
        return None
    path = os.path.join(_TMP, "rec.webm")
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
           "-vn", "-ac", "1", "-ar", "16000",
           "-c:a", "libopus", "-b:a", "64k", path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    with open(path, "rb") as f:
        return f.read()


# -- e2e (audit duong (c), 2026-11-06, adapted sang duong hai buoc) --
# Blob webm cua trinh duyet qua route phai toi Zalo duoi dang AAC
# dung wire cua bundle (upload chunk 12060 + asyncfile/msg 11777).
# Khoa duong da kiem chung: khong co buoc nao tren duong nay doi
# field/ten file/params — neu mot buoc nao doi (vd. bo transcode,
# gui thang webm), test nay do ngay. (Ban goc cua (c) pin duong
# truc tiep voicemp3/MP3; duong do da bi (b) bo vi la code chet
# trong bundle + live van 112 — test duoc viet lai theo duong
# hai buoc, giu nguyen y dinh e2e.)













if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VOICE 112 TESTS PASSED")
