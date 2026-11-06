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

BUOC GUI SAU UPLOAD — SUY LUAN CO GHI RO, KHONG PHAI BANG CHUNG
TRUC TIEP: khong co code JS nao trong bundle khoi tao task upload
Voice (0 lan `uploadMainType: *.c.Voice`), khong co
sendMsgVoiceAsync, sendMsgAsync chi xu ly Photo/File — viec ghi
am + gui sau upload nam o lop native (khong co MediaRecorder
trong JS). Buoc 2 o day dung asyncfile/msg (11777/13001,
sendMsgFileAsync): endpoint PC DUY NHAT nhan dung item ma
getFileAsyncItem tra ve (fileId/checksum/checksumSha/totalSize/
clientId + toid|grid, + imei chi 1-1, + zsource -1 qua buildParams/
transform). Neu live retest van loi thi day la diem can kiem dau
tien (kem theo viec cho async event {aac,amr} qua kenh sync, hien
chua implement — xem ghi chu o chat.send_voice).

112: van la loi chung (STR_ERROR_CODE_UNKNOWN), bundle coi la tam
thoi va thu lai sau 1-5 giay — app thu lai gioi han (2 lan, cach
2 giay, cung clientId/body) o ca buoc chunk lan buoc gui.

Mock kiem chung doc lap (khong dang nhap that, khong gui that).
"""

import hashlib
import json
import os
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VOICE 112 TESTS PASSED")
