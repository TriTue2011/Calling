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
  fType, toid|grid}; async event tra {aac, amr, secureKey} ->
  fileUrl = amr||aac (mapVoiceResponse + __waitAsyncFileInfo).
- Dinh dang that la AAC (khong phai MP3): fileType aac/amr; tin
  thoai that do duoc la AAC-LC 16 kHz mono 64 kbps ADTS .aac
  (Node.js voiceAac.js + voiceMessage.test.js); ten file tai ve
  cua tin thoai ket bang .aac; forward-voice dung m4aUrl/voiceUrl.

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
o lop native ngoai JS. fType CO trong item Voice cua
getFileAsyncItem (gia tri tu extData lop native, khong lan duoc
tu JS) — app hien chua gui (vong tham so, agent khac lam).
Neu live retest van loi thi diem can kiem dau tien la viec cho
async event {aac,amr} qua kenh sync, hien chua implement — xem
ghi chu o chat.send_voice.

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
    return chat_mod.Chat(t, "dev-1", TEST_SESSION_KEY, sleep=sleep)


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

def test_voice_two_step_params_match_bundle():
    """1 chunk AAC, 1-1: chunk POST toi /api/message/voice/upload
    voi params CHI {totalChunk, fileName, clientId NUMBER, totalSize,
    imei, chunkId, toid, fileType "aac"} (khong checksum, khong ttl/
    duration/desc); chunkContent = toan bo file; roi asyncfile/msg
    voi body {fileId, checksum=md5, checksumSha "", totalSize,
    clientId NUMBER, toid, imei, zsource}."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_voice("user", "20001", "voice.aac",
                              FAKE_AAC, "audio/aac")
        assert res["data"]["msgId"] == "msg-voice-1", res
        assert res["file_id"] == "file-voice-1", res
        assert isinstance(res["client_id"], int), res
        assert mock.voice_upload_calls == 1, mock.voice_upload_calls
        assert mock.voice_send_calls == 1, mock.voice_send_calls
        chunk = mock.upload_bodies[0]["body"]
        assert mock.upload_bodies[0]["path"] == \
            "/api/message/voice/upload", mock.upload_bodies
        assert set(chunk.keys()) == {"totalChunk", "fileName",
                                     "clientId", "totalSize", "imei",
                                     "chunkId", "toid",
                                     "fileType"}, chunk
        assert chunk["totalChunk"] == 1 and chunk["chunkId"] == 1, chunk
        assert chunk["fileName"] == "voice.aac", chunk
        assert chunk["totalSize"] == len(FAKE_AAC), chunk
        assert chunk["imei"] == "dev-1", chunk
        assert chunk["toid"] == "20001", chunk
        assert chunk["fileType"] == "aac", chunk
        assert isinstance(chunk["clientId"], int) and not \
            isinstance(chunk["clientId"], bool), chunk
        assert chunk["clientId"] == res["client_id"], chunk
        assert "checksum" not in chunk, chunk
        fname, mime, data = _uploaded_chunk(
            mock, "/api/message/voice/upload")
        assert fname == "voice.aac", fname
        assert data == FAKE_AAC, data
        sent = mock.voice_send_bodies[0]["body"]
        assert mock.voice_send_bodies[0]["path"] == \
            "/api/message/asyncfile/msg", mock.voice_send_bodies
        assert set(sent.keys()) == {"fileId", "checksum",
                                    "checksumSha", "totalSize",
                                    "clientId", "toid", "imei",
                                    "zsource"}, sent
        assert sent["fileId"] == "file-voice-1", sent
        assert sent["checksum"] == \
            hashlib.md5(FAKE_AAC).hexdigest(), sent
        assert sent["checksumSha"] == "", sent
        assert sent["totalSize"] == len(FAKE_AAC), sent
        assert sent["clientId"] == res["client_id"], sent
        assert sent["toid"] == "20001" and sent["imei"] == "dev-1", sent
        assert sent["zsource"] == -1, sent
        paths = [p for p, _q, _h in mock.seen
                 if p in ("/api/message/voice/upload",
                          "/api/message/asyncfile/msg")]
        assert paths == ["/api/message/voice/upload",
                         "/api/message/asyncfile/msg"], paths
    finally:
        mock.stop()


def test_voice_two_step_group_multi_chunk():
    """Nhom, 600_000 byte AAC -> 3 chunk 256000/256000/88000 toi
    /api/group/voice/upload (type 11), chunkId 1..3, totalChunk 3;
    roi /api/group/asyncfile/msg voi grid, KHONG imei."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        data = b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\xab" * (600000 - 7)
        res = chat.send_voice("group", "30001", "voice.aac",
                              data, "audio/aac")
        assert res["data"]["msgId"] == "msg-voice-1", res
        assert res["file_id"] == "file-voice-1", res
        assert mock.voice_upload_calls == 3, mock.voice_upload_calls
        assert mock.voice_send_calls == 1, mock.voice_send_calls
        for i, entry in enumerate(mock.upload_bodies):
            assert entry["path"] == "/api/group/voice/upload", entry
            body = entry["body"]
            assert body["totalChunk"] == 3, body
            assert body["chunkId"] == i + 1, body
            assert body["grid"] == "30001", body
            assert "toid" not in body, body
            assert body["fileType"] == "aac", body
            assert body["clientId"] == res["client_id"], body
            fname, _mime, chunk = _uploaded_chunk(
                mock, "/api/group/voice/upload", i)
            assert fname == "voice.aac", fname
            assert chunk == data[i * 256000:(i + 1) * 256000], \
                (i, len(chunk))
        assert [len(_uploaded_chunk(mock, "/api/group/voice/upload",
                                    i)[2]) for i in range(3)] == \
            [256000, 256000, 88000]
        sent = mock.voice_send_bodies[0]["body"]
        assert mock.voice_send_bodies[0]["path"] == \
            "/api/group/asyncfile/msg", mock.voice_send_bodies
        assert sent["grid"] == "30001", sent
        assert "toid" not in sent and "imei" not in sent, sent
        assert sent["checksum"] == hashlib.md5(data).hexdigest(), sent
        assert sent["totalSize"] == 600000, sent
    finally:
        mock.stop()


def test_voice_two_step_amr_filename():
    """Ten file .amr -> fileType "amr" (bundle: ten chua ".amr" thi
    amr, khong thi aac)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_voice("user", "20001", "voice.amr",
                              FAKE_AAC, "audio/amr")
        assert res["data"]["msgId"] == "msg-voice-1", res
        assert mock.upload_bodies[0]["body"]["fileType"] == "amr", \
            mock.upload_bodies[0]["body"]
    finally:
        mock.stop()


def test_file_params_match_bundle():
    """sharefile_full: KHONG DOI — bundle sendFile ghep
    '"clientId":"<id>"' — clientId STRING, chi {toid|grid,
    clientId}."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_file("user", "20001", "hello.txt",
                             b"hello file", "text/plain")
        body = res["data"]["body"]
        assert set(body.keys()) == {"toid", "clientId"}, body
        assert isinstance(body["clientId"], str), body
        assert body["clientId"] == str(res["client_id"]), body
        res = chat.send_file("group", "30001", "bao-cao.pdf",
                             b"%PDF-fake", "application/pdf")
        body = res["data"]["body"]
        assert set(body.keys()) == {"grid", "clientId"}, body
        assert isinstance(body["clientId"], str), body
        assert body["clientId"] == str(res["client_id"]), body
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
        assert body["desc"] == "anh.jpg", body
        assert body["width"] == 800 and body["height"] == 600, body
    finally:
        mock.stop()


# -- 112: thu lai -------------------------------------------------------

def test_voice_chunk_112_once_retries_and_succeeds():
    """112 tam thoi o buoc chunk: lan 1 tra 112, lan 2 ok — gui
    thanh cong, dung 2 lan goi chunk, cho 1 lan 2 giay, cung
    clientId + chunkId ca 2 lan (de server dedup, khong gui
    trung); chi 1 lan asyncfile."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        mock.voice_upload_mode = "error112_once"
        sleep = SleepRecorder()
        chat = make_chat(mock, sleep=sleep)
        res = chat.send_voice("user", "20001", "voice.aac",
                              FAKE_AAC, "audio/aac")
        assert res["data"]["msgId"] == "msg-voice-1", res
        assert mock.voice_upload_calls == 2, mock.voice_upload_calls
        assert mock.voice_send_calls == 1, mock.voice_send_calls
        assert sleep.calls == [2.0], sleep.calls
        assert len(mock.upload_bodies) == 2, mock.upload_bodies
        first = mock.upload_bodies[0]["body"]
        second = mock.upload_bodies[1]["body"]
        assert first["clientId"] == second["clientId"], \
            (first, second)
        assert first["chunkId"] == second["chunkId"] == 1, \
            (first, second)
        assert isinstance(first["clientId"], int), first
    finally:
        mock.stop()


def test_voice_send_112_persistent_fails_after_bounded_retries():
    """112 keo dai o buoc gui (asyncfile/msg): chunk ok 1 lan,
    asyncfile thu lai dung 2 lan roi bao loi (khong thu vo han,
    khong gia vo thanh cong). Tong 3 lan goi gui, cho 2 lan."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        mock.voice_send_mode = "error112"
        sleep = SleepRecorder()
        chat = make_chat(mock, sleep=sleep)
        try:
            chat.send_voice("user", "20001", "voice.aac",
                            FAKE_AAC, "audio/aac")
            raise AssertionError("expected ZaloChatError 112")
        except chat_mod.ZaloChatError as e:
            assert e.error_code == 112, e
            assert "112" in str(e), e
        assert mock.voice_upload_calls == 1, mock.voice_upload_calls
        assert mock.voice_send_calls == 3, mock.voice_send_calls
        assert sleep.calls == [2.0, 2.0], sleep.calls
    finally:
        mock.stop()


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


def test_server_voice_two_step_succeeds():
    """Duong hai buoc qua route app: file AAC that gui thang (khong
    doi), 200 ok, kind voice; 1 chunk + 1 asyncfile."""
    mock = MockZalo().start()
    try:
        httpd = _run_server(mock)
        try:
            status, body = _sendvoice_via_app()
            assert status == 200 and body["ok"] is True, body
            assert body["message"]["kind"] == "voice", body
            assert body["message"]["file_name"] == "voice.aac", body
            assert body.get("converted_to_aac") is False, body
            assert mock.voice_upload_calls == 1, \
                mock.voice_upload_calls
            assert mock.voice_send_calls == 1, mock.voice_send_calls
        finally:
            httpd.shutdown()
    finally:
        mock.stop()


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

def test_server_voice_webm_browser_shape_arrives_as_aac():
    """Blob webm/opus dang trinh duyet gui (field type + file
    voice.webm, audio/webm;codecs=opus) qua route phai duoc doi
    sang AAC that roi gui hai buoc: 1 chunk toi
    /api/message/voice/upload voi chunkContent = AAC (voice.aac),
    params CHI {totalChunk, fileName, clientId NUMBER, totalSize,
    imei, chunkId, toid, fileType "aac"}; roi 1 lan asyncfile/msg
    voi body {fileId, checksum=md5(AAC), checksumSha "", totalSize,
    clientId NUMBER, toid, imei, zsource -1}; route tra 200 ok +
    converted_to_aac=true."""
    webm = _webm_fixture()
    if webm is None:
        print("SKIP test_server_voice_webm_browser_shape_arrives_as_aac "
              "(no ffmpeg)")
        return
    assert not voice_mod.is_mp3(webm), "fixture phai la webm, khong phai mp3"
    assert not voice_mod.is_aac(webm), "fixture phai la webm, khong phai aac"
    mock = MockZalo().start()
    try:
        httpd = _run_server(mock)
        try:
            status, body = _sendvoice_via_app_bytes(
                "voice.webm", "audio/webm;codecs=opus", webm)
            assert status == 200 and body["ok"] is True, body
            assert body["message"]["kind"] == "voice", body
            assert body["converted_to_aac"] is True, body
            assert mock.voice_upload_calls == 1, mock.voice_upload_calls
            assert mock.voice_send_calls == 1, mock.voice_send_calls
            chunk = mock.upload_bodies[0]["body"]
            assert mock.upload_bodies[0]["path"] == \
                "/api/message/voice/upload", mock.upload_bodies
            assert set(chunk.keys()) == {"totalChunk", "fileName",
                                         "clientId", "totalSize", "imei",
                                         "chunkId", "toid",
                                         "fileType"}, chunk
            assert chunk["totalChunk"] == 1 and chunk["chunkId"] == 1, chunk
            assert chunk["fileName"] == "voice.aac", chunk
            assert chunk["fileType"] == "aac", chunk
            assert chunk["toid"] == "20001", chunk
            # Qua route, imei la device id do server sinh (khong
            # phai "dev-1" cua test chat-layer); chi pin no co
            # dang chuoi khong rong + khop giua 2 buoc (xem duoi).
            assert isinstance(chunk["imei"], str) and chunk["imei"], chunk
            assert isinstance(chunk["clientId"], int) and not \
                isinstance(chunk["clientId"], bool), chunk
            fname, mime, data = _uploaded_chunk(
                mock, "/api/message/voice/upload")
            assert fname == "voice.aac", fname
            assert voice_mod.is_aac(data), data[:16]
            assert data != webm, \
                "chunkContent phai la AAC da doi, khong phai webm goc"
            assert chunk["totalSize"] == len(data), chunk
            sent = mock.voice_send_bodies[0]["body"]
            assert mock.voice_send_bodies[0]["path"] == \
                "/api/message/asyncfile/msg", mock.voice_send_bodies
            assert set(sent.keys()) == {"fileId", "checksum",
                                        "checksumSha", "totalSize",
                                        "clientId", "toid", "imei",
                                        "zsource"}, sent
            assert sent["fileId"] == "file-voice-1", sent
            assert sent["checksum"] == \
                hashlib.md5(data).hexdigest(), sent
            assert sent["checksumSha"] == "", sent
            assert sent["totalSize"] == len(data), sent
            assert sent["clientId"] == chunk["clientId"], sent
            assert sent["toid"] == "20001" and \
                sent["imei"] == chunk["imei"], sent
            assert sent["zsource"] == -1, sent
        finally:
            httpd.shutdown()
    finally:
        mock.stop()


def test_server_voice_webm_112_once_retries_same_aac():
    """112 mot lan tren duong webm-that (o buoc chunk): thu lai
    phai chay ngay tren duong nay (2 lan goi chunk, cung clientId
    NUMBER, cung chunkContent AAC da doi o ca 2 lan; chi 1 lan
    asyncfile voi checksum cua AAC do) va route tra 200 ok — pin
    rang co che thu lai khong bi bypass boi buoc transcode."""
    webm = _webm_fixture()
    if webm is None:
        print("SKIP test_server_voice_webm_112_once_retries_same_aac "
              "(no ffmpeg)")
        return
    mock = MockZalo().start()
    try:
        mock.voice_upload_mode = "error112_once"
        httpd = _run_server(mock)
        try:
            status, body = _sendvoice_via_app_bytes(
                "voice.webm", "audio/webm;codecs=opus", webm)
            assert status == 200 and body["ok"] is True, body
            assert body["message"]["kind"] == "voice", body
            assert body["converted_to_aac"] is True, body
            assert mock.voice_upload_calls == 2, mock.voice_upload_calls
            assert mock.voice_send_calls == 1, mock.voice_send_calls
            assert len(mock.upload_bodies) == 2, mock.upload_bodies
            first = mock.upload_bodies[0]["body"]
            second = mock.upload_bodies[1]["body"]
            assert first["clientId"] == second["clientId"], (first, second)
            assert isinstance(first["clientId"], int), first
            assert first["chunkId"] == second["chunkId"] == 1, \
                (first, second)
            first_chunk = _uploaded_chunk(
                mock, "/api/message/voice/upload", 0)
            second_chunk = _uploaded_chunk(
                mock, "/api/message/voice/upload", 1)
            assert first_chunk[2] == second_chunk[2], \
                "thu lai phai gui lai dung AAC da doi"
            assert voice_mod.is_aac(first_chunk[2]), first_chunk[2][:16]
            assert first_chunk[0] == "voice.aac", first_chunk
            sent = mock.voice_send_bodies[0]["body"]
            assert sent["checksum"] == \
                hashlib.md5(first_chunk[2]).hexdigest(), sent
            assert sent["clientId"] == first["clientId"], sent
        finally:
            httpd.shutdown()
    finally:
        mock.stop()


def test_server_voice_send_112_surfaces_not_faked():
    """112 keo dai o buoc gui qua route app: tra 502 chua '112',
    khong gia vo thanh cong — dung trieu chung live 2026-11-06."""
    mock = MockZalo().start()
    try:
        mock.voice_send_mode = "error112"
        httpd = _run_server(mock)
        try:
            status, body = _sendvoice_via_app()
            assert status == 502, body
            assert "112" in str(body.get("error", "")), body
            assert mock.voice_upload_calls == 1, \
                mock.voice_upload_calls
            assert mock.voice_send_calls == 3, mock.voice_send_calls
        finally:
            httpd.shutdown()
    finally:
        mock.stop()


def test_server_voice_chunk_112_once_succeeds_via_retry():
    """112 mot lan o buoc chunk qua route app: thu lai trong chat
    layer lam cuoc goi UI thanh cong (200, ok)."""
    mock = MockZalo().start()
    try:
        mock.voice_upload_mode = "error112_once"
        httpd = _run_server(mock)
        try:
            status, body = _sendvoice_via_app()
            assert status == 200 and body["ok"] is True, body
            assert body["message"]["kind"] == "voice", body
            assert mock.voice_upload_calls == 2, \
                mock.voice_upload_calls
            assert mock.voice_send_calls == 1, mock.voice_send_calls
        finally:
            httpd.shutdown()
    finally:
        mock.stop()


def test_voice_step2_endpoint_confirmed_asyncfile_msg():
    """PIN BUOC 2 (vong 114, 2026-11-06): asyncfile/msg la endpoint
    DUNG cho Voice — khong con la suy luan theo shape.
    Bang chung bundle (compact-app-pc.5c0110a3a8749b3aacde.js,
    Zalo PC 26.11.10):
    - sendMsgFileAsync la API DUY NHAT (khong E2EE) POST dung item
      getFileAsyncItem, toi {files-wpa}/api/message/asyncfile/msg
      (11777) / /api/group/asyncfile/msg (13001), POST form
      params=<AES JSON>; caller duy nhat trong JS la
      UploadAsyncControl._sendMsgFileAsync.
    - Bang lenh khong co endpoint gui-tin-thoai nao khac: khong co
      /api/message/voice (gui bang URL); voicemp3/sendmp3 chet
      (0 caller); dispatcher gui tin tu choi MSG_VOICE
      ("not support send this type"); sendMsgAsync chi xu ly
      Photo/File — Voice/Video duoc tra thang urlRes cho lop
      native gui sau upload, nen khong co caller Voice truc tiep
      nao quan sat duoc trong JS (gioi han da biet, khong phai
      bang chung chong lai endpoint).
    Test pin hanh vi: send_voice chi goi dung 2 duong
    (voice/upload + asyncfile/msg), KHONG goi bat cu endpoint gui
    nao khac (voicemp3/sendmp3/sms/sendmsg/photo/sharefile) — neu
    ai doi buoc 2 sang duong truc tiep cu hay endpoint khac, test
    nay do ngay."""
    dead = {"/api/message/voicemp3", "/api/group/sendmp3",
            "/api/message/sms", "/api/group/sendmsg",
            "/api/message/photo", "/api/group/sendpt",
            "/api/message/sharefile_full",
            "/api/group/sharefile_full"}
    for thread_type, thread_id, up, send in (
            ("user", "20001", "/api/message/voice/upload",
             "/api/message/asyncfile/msg"),
            ("group", "30001", "/api/group/voice/upload",
             "/api/group/asyncfile/msg")):
        mock = MockZalo().start()
        try:
            patch_domains(mock)
            chat = make_chat(mock)
            res = chat.send_voice(thread_type, thread_id, "voice.aac",
                                  FAKE_AAC, "audio/aac")
            assert res["file_id"] == "file-voice-1", res
            seen_paths = [p for p, _q, _h in mock.seen]
            assert not (set(seen_paths) & dead), seen_paths
            voice_paths = [p for p in seen_paths
                           if "voice" in p or "asyncfile" in p]
            assert voice_paths == [up, send], voice_paths
        finally:
            mock.stop()


def test_voice_step2_group_item_keys_match_bundle():
    """Nhom: item buoc 2 co DUNG cac key cua getFileAsyncItem(Voice)
    + buildParams: {fileId, checksum, checksumSha, totalSize,
    clientId NUMBER, grid, zsource -1} — khong toid, khong imei
    (imei chi 1-1: sendMsgFileAsync them imei khi khong phai nhom).
    fType: bundle CO trong item Voice (gia tri tu extData cua lop
    native, khong lan duoc tu JS) — app hien chua gui; thuoc vong
    tham so (agent khac lam), test nay KHONG doi fType."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        data = b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\xab" * 99993
        res = chat.send_voice("group", "30001", "voice.aac",
                              data, "audio/aac")
        assert res["file_id"] == "file-voice-1", res
        assert mock.voice_send_calls == 1, mock.voice_send_calls
        sent = mock.voice_send_bodies[0]["body"]
        assert mock.voice_send_bodies[0]["path"] == \
            "/api/group/asyncfile/msg", mock.voice_send_bodies
        assert set(sent.keys()) == {"fileId", "checksum",
                                    "checksumSha", "totalSize",
                                    "clientId", "grid",
                                    "zsource"}, sent
        assert sent["checksum"] == hashlib.md5(data).hexdigest(), sent
        assert sent["checksumSha"] == "", sent
        assert sent["totalSize"] == len(data), sent
        assert isinstance(sent["clientId"], int) and not \
            isinstance(sent["clientId"], bool), sent
        assert sent["clientId"] == res["client_id"], sent
        assert sent["grid"] == "30001", sent
        assert sent["zsource"] == -1, sent
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VOICE 112 TESTS PASSED")
