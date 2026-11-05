"""Loi 112 tren duong gui tin nhan thoai (live 2026-11-06 06:35 +07
tren 9d87501: sau khi transcode MP3 da het loi 133, server tra
inner error_code=112 "Loi khong xac dinh").

BANG CHUNG BUNDLE (compact-app-pc...js):
- sendVoice (voicemp3 11148 / sendmp3 11169) ghep params bang
  chuoi tay: '{"toid":"<id>", "clientId":"<id>"}' — clientId la
  STRING (co dau ngoac kep), khong phai NUMBER. Gia tri la so
  epoch-ms cua generator next() (getTimeServer, tang don dieu),
  chi khac KIEU JSON khi gui di. Code cu gui NUMBER -> sai wire.
  sendFile (sharefile_full 11146/11191) ghep y het — cung loi.
  Anh thi khac: JSON.stringify({clientId: <number>, ...}) nen
  clientId van la NUMBER — khong duoc doi theo.
- Params voice CHI co toid|grid + clientId: khong ttl, khong
  duration, khong imei, khong desc.
- 112 khong co nghia rieng trong bundle: bang loi anh xa 112 ->
  "STR_ERROR_CODE_UNKNOWN", va moi bo xu ly loi deu coi 112 la
  TAM THOI va thu lai sau 1-5 giay. App thu lai gioi han (2 lan,
  cach 2 giay, cung clientId/body).
- 12060/12063 (/api/message|group/voice/upload) la duong upload
  CHUNKED cua upload-manager chung (getInfoUploadVoiceFromData,
  theo uploadMainType==Voice) — thu tu dung cho tin thoai chua
  lan duoc, khong co bang chung UI ghi am dung duong nay; duong
  truc tiep voicemp3/sendmp3 (sendVoice) moi la duong gui tin
  thoai. Giu duong truc tiep, khong doi sang 12060/12063.

Mock kiem chung doc lap (khong dang nhap that, khong gui that).
Cac test kieu-wire nay DO tren code cu (clientId NUMBER): mock
tra 112 nhu server that thi chat thu lai het luot roi van loi —
tuc la test do, dung nhu loi that. Sau fix thi xanh.
"""

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

FAKE_MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 100


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


def _uploaded_file(mock, path):
    """(filename, mime, bytes) cua fileContent mock nhan duoc gan
    nhat o `path`."""
    for p, raw in reversed(mock.seen_post_raw):
        if p != path:
            continue
        ctype = ""
        for pp, _qs, headers in reversed(mock.seen):
            if pp == path and "Content-Type" in headers:
                ctype = headers["Content-Type"]
                break
        _fields, files = chat_mod.parse_multipart(raw, ctype)
        assert "fileContent" in files, files.keys()
        return files["fileContent"]
    raise AssertionError("mock khong nhan duoc %s nao" % path)


# -- params tren day (wire) khop bundle -------------------------------

def test_voice_params_match_bundle():
    """voicemp3/sendmp3: params CHI {toid|grid, clientId};
    clientId la STRING bang str(epoch-ms); khong ttl/duration/
    imei/desc; fileContent = voice.mp3, audio/mpeg."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_voice("user", "20001", "voice.mp3",
                              b"FAKEMP3DATA", "audio/mpeg")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        body = res["data"]["body"]
        assert set(body.keys()) == {"toid", "clientId"}, body
        assert body["toid"] == "20001", body
        assert isinstance(body["clientId"], str), body
        assert body["clientId"] == str(res["client_id"]), body
        assert "ttl" not in body and "duration" not in body, body
        assert "imei" not in body and "desc" not in body, body
        fname, mime, data = _uploaded_file(mock, "/api/message/voicemp3")
        assert fname == "voice.mp3", fname
        assert mime == "audio/mpeg", mime
        assert data == b"FAKEMP3DATA", data

        res = chat.send_voice("group", "30001", "voice.mp3",
                              b"FAKEMP3DATA", "audio/mpeg")
        body = res["data"]["body"]
        assert set(body.keys()) == {"grid", "clientId"}, body
        assert body["grid"] == "30001", body
        assert isinstance(body["clientId"], str), body
        assert body["clientId"] == str(res["client_id"]), body
        assert "ttl" not in body and "duration" not in body, body
        fname, mime, data = _uploaded_file(mock, "/api/group/sendmp3")
        assert fname == "voice.mp3" and mime == "audio/mpeg", (fname, mime)
        paths = [p for p, _q, _h in mock.seen
                 if p in ("/api/message/voicemp3", "/api/group/sendmp3")]
        assert len(paths) == 2, mock.seen
    finally:
        mock.stop()


def test_file_params_match_bundle():
    """sharefile_full: cung mau thuan wire nhu voice (bundle
    sendFile ghep '"clientId":"<id>"') — clientId STRING, chi
    {toid|grid, clientId}."""
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

def test_voice_112_once_retries_and_succeeds():
    """112 tam thoi: lan 1 tra 112, lan 2 ok — gui thanh cong,
    dung 2 lan goi, cho 1 lan 2 giay, cung clientId ca 2 lan
    (de server dedup, khong gui trung)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        mock.voice_upload_mode = "error112_once"
        sleep = SleepRecorder()
        chat = make_chat(mock, sleep=sleep)
        res = chat.send_voice("user", "20001", "voice.mp3",
                              b"FAKEMP3DATA", "audio/mpeg")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert mock.voice_upload_calls == 2, mock.voice_upload_calls
        assert sleep.calls == [2.0], sleep.calls
        assert len(mock.upload_bodies) == 2, mock.upload_bodies
        first = mock.upload_bodies[0]["body"]
        second = mock.upload_bodies[1]["body"]
        assert first["clientId"] == second["clientId"], \
            (first, second)
        assert isinstance(first["clientId"], str), first
    finally:
        mock.stop()


def test_voice_112_persistent_fails_after_bounded_retries():
    """112 keo dai: thu lai dung 2 lan roi bao loi (khong thu vo
    han, khong gia vo thanh cong). Tong 3 lan goi, cho 2 lan."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        mock.voice_upload_mode = "error112"
        sleep = SleepRecorder()
        chat = make_chat(mock, sleep=sleep)
        try:
            chat.send_voice("user", "20001", "voice.mp3",
                            b"FAKEMP3DATA", "audio/mpeg")
            raise AssertionError("expected ZaloChatError 112")
        except chat_mod.ZaloChatError as e:
            assert e.error_code == 112, e
            assert "112" in str(e), e
        assert mock.voice_upload_calls == 3, mock.voice_upload_calls
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
            chat.send_voice("user", "20001", "voice.mp3", b"",
                            "audio/mpeg")
            raise AssertionError("expected ValueError on empty voice")
        except ValueError as e:
            assert "rong" in str(e), e
        assert mock.voice_upload_calls == 0, mock.voice_upload_calls
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
        [("file", "voice.mp3", "audio/mpeg", FAKE_MP3)])
    return api("POST", "/api/thread/20001/sendvoice",
               mbody, {"Content-Type": mctype})


def test_server_voice_112_surfaces_not_faked():
    """112 keo dai qua route app: tra 502 chua '112', khong gia
    vo thanh cong — dung trieu chung live 2026-11-06."""
    mock = MockZalo().start()
    try:
        mock.voice_upload_mode = "error112"
        httpd = _run_server(mock)
        try:
            status, body = _sendvoice_via_app()
            assert status == 502, body
            assert "112" in str(body.get("error", "")), body
            assert mock.voice_upload_calls == 3, mock.voice_upload_calls
        finally:
            httpd.shutdown()
    finally:
        mock.stop()


def test_server_voice_112_once_succeeds_via_retry():
    """112 mot lan qua route app: thu lai trong chat layer lam
    cuoc goi UI thanh cong (200, ok)."""
    mock = MockZalo().start()
    try:
        mock.voice_upload_mode = "error112_once"
        httpd = _run_server(mock)
        try:
            status, body = _sendvoice_via_app()
            assert status == 200 and body["ok"] is True, body
            assert body["message"]["kind"] == "voice", body
            assert mock.voice_upload_calls == 2, mock.voice_upload_calls
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
