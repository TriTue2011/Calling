"""Tin nhan thoai — CHO EVENT ASYNC ctrl `voice_aac_success` TRUOC
KHI GUI BUOC 2 (loi 114, 2026-11-06 09:46 +07).

BANG CHUNG BUNDLE (compact-app-pc.5c0110a3a8749b3aacde.js,
Zalo PC 26.11.10) — doc truc tiep tu bundle:
- Upload-manager KHONG gui buoc 2 ngay sau chunk cuoi: getUploadResp
  goi `waitAsyncFileInfo(h, fileAsyncItem, ...)` truoc (tru
  UploadPersist / TRANS_TO_FORWARD / DUPLICATE); chi khi wait resolve
  thi fileAsync moi duoc dua cho API sendMsgFileAsync (11777/13001).
- Wait dang ky handler theo fileId (`_makeHandlerAsync[fileId]`) +
  timeout mac dinh 120 s (`upload_file_timeout_wait_ctrl_event`,
  mac dinh 12e4 ms); het gio thi TIMEOUT_WAIT (khong gui buoc 2).
  Neu event da den truoc thi lay ngay tu cache (`getFileIdData`).
- Event den qua kenh CTRL long-poll RIENG 99101
  (`getControllFromPolling`, zpw_ctrs_new — KHONG phai kenh tin nhan
  99100): `_processCtrlMessages` gom `e.controls` theo `act_type`,
  `case "voice_aac_success"` -> `_processVoiceAsyncDoneEvent` ->
  `handleEventFromCtrl({fileId, data:{amr, aac}}, "VOICE")`.
  data cua event co key SO theo `VOICE_TYPE={AMR:5, AAC:6}`: data
  la {"5": <url amr>, "6": <url aac>}.
- Handler cho Voice (`__waitAsyncFileInfo`): `t.fileUrl = a.amr||a.aac`,
  `a.amr && (t.aacUrl = a.aac)`, `a.secureKey && (t.secureKey =
  a.secureKey)` — fileUrl la thu wait GATE; secureKey CHI set neu
  async data co no. Event ctrl voice CHI co amr/aac (khong co
  secureKey — secureKey chi xuat hien o mapVoiceResponse, tuc la
  passthrough tu chunk-response, va chi dung cho E2EE/pcloud o
  onReceiveUploadURL) — nen secureKey KHONG phai nguyen nhan 114
  cho tin thoai thuong; thu thieu la fileUrl.
- API sendMsgFileAsync POST `params=<AES JSON({...fileAsync})>` —
  fileUrl/aacUrl (neu wait da dien) NAM TRONG body buoc 2. App cu
  gui buoc 2 ngay sau chunk-response (chi co {finished:1, fileId},
  khong URL) nen body thieu fileUrl -> server tra 114 "Tham so
  khong hop le" (live 09:46 +07; 112 truoc do da het vi duong hai
  buoc da toi duoc server).

SUA O DAY: Chat.send_voice (a) KHONG lay URL tu chunk-response
(truong url/amr/aac neu co trong chunk-response thuoc nhanh
DUPLICATE/cache — bundle chi doc finished/fileId o do), (b) LUON
DOI event ctrl voice_aac_success qua waiter (registry do CtrlPoller
99101 nap, hoac fake o test) toi da VOICE_ASYNC_WAIT_SECONDS, (c)
het gio / kenh ctrl chua chay / khong co waiter -> loi ro rang,
KHONG gui buoc 2. Buoc 2 gui kem fileUrl=amr||aac (+ aacUrl khi co
amr, + secureKey chi khi async data / chunk-response co no).

Mock/offline hoan toan: khong dang nhap that, khong gui that.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import ctrl_poll as ctrl_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402

FAKE_AAC = b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\x00" * 100
AMR_URL = "https://f1-voice-aac-dl.zdn.vn/test-voice.amr"
AAC_URL = "https://f1-voice-aac-dl.zdn.vn/test-voice.aac"


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    chat_mod.CHAT_DOMAIN = mock.base
    chat_mod.FILES_DOMAIN = mock.base
    chat_mod.GROUP_DOMAIN = mock.base


class FakeVoiceWaiter:
    """Waiter gia cho test: tra ve URL da dinh san, hoac None
    (gia lap event khong bao gio den). Ghi lai lan goi."""

    def __init__(self, urls=None, feeder_running=True):
        self.urls = urls
        self.feeder_running = feeder_running
        self.calls = []

    def wait(self, file_id, timeout_s):
        self.calls.append((file_id, timeout_s))
        if self.urls is None:
            return None
        return dict(self.urls)


class DelayedVoiceWaiter:
    """Gia lap event den TRE (sau khi wait da bat dau): ham wait
    cho cho toi khi deliver() duoc goi tu thread khac."""

    def __init__(self):
        self.feeder_running = True
        self._event = threading.Event()
        self.urls = None

    def deliver(self, urls):
        self.urls = dict(urls)
        self._event.set()

    def wait(self, file_id, timeout_s):
        self._event.wait(timeout_s)
        return dict(self.urls) if self.urls is not None else None


def make_chat(mock, waiter=None, timeout=5.0, sleep=None):
    t = app_server.make_transport("sek-test")
    return chat_mod.Chat(t, "dev-1", TEST_SESSION_KEY,
                         voice_async=waiter,
                         voice_async_timeout=timeout, sleep=sleep)


# -- tach event ctrl voice_aac_success (bundle _processCtrlMessages) --

def test_extract_voice_async_from_ctrl_payload():
    """Payload ctrl da giai ma: controls[] voi content.data la
    CHUOI JSON, key so "5"/"6" (VOICE_TYPE AMR=5, AAC=6) -> tach
    duoc {fileId, amr, aac}; act_type khac bi bo qua."""
    data = {"controls": [
        {"content": {"act_type": "file_done", "fileId": "file-x",
                      "data": "{\"url\": \"https://example.invalid/f\"}"}},
        {"content": {"act_type": "voice_aac_success",
                      "fileId": "file-voice-1",
                      "data": json.dumps({"5": AMR_URL, "6": AAC_URL})}},
        {"content": {"act_type": "voice_aac_success",
                      "fileId": "file-voice-2",
                      "data": {"5": AMR_URL}}},
    ]}
    got = ctrl_mod.extract_voice_async(data)
    assert got == [{"fileId": "file-voice-1", "amr": AMR_URL,
                    "aac": AAC_URL},
                   {"fileId": "file-voice-2", "amr": AMR_URL,
                    "aac": None}], got


def test_extract_voice_async_ignores_malformed():
    """Event thieu fileId / thieu ca amr lan aac / data khong phai
    JSON -> bo qua, khong do (kenh ctrl con nhieu loai event)."""
    data = {"controls": [
        {"content": {"act_type": "voice_aac_success",
                      "data": {"5": AMR_URL}}},
        {"content": {"act_type": "voice_aac_success",
                      "fileId": "file-bad", "data": "khong-phai-json"}},
        {"content": {"act_type": "voice_aac_success",
                      "fileId": "file-empty", "data": {}}},
    ]}
    assert ctrl_mod.extract_voice_async(data) == []
    assert ctrl_mod.extract_voice_async({}) == []
    assert ctrl_mod.extract_voice_async(None) == []


def test_registry_deliver_before_wait_returns_immediately():
    """Event den TRUOC khi wait dang ky (bundle getFileIdData
    cache-hit): wait tra ngay, khong cho."""
    reg = ctrl_mod.VoiceAsyncRegistry()
    reg.deliver("file-voice-1", AMR_URL, AAC_URL)
    started = time.time()
    got = reg.wait("file-voice-1", timeout_s=5.0)
    assert time.time() - started < 1.0, "phai tra ngay tu cache"
    assert got == {"amr": AMR_URL, "aac": AAC_URL}, got


def test_registry_wait_then_deliver_and_timeout():
    """Wait dang ky truoc, deliver tu thread khac -> wait tra ve
    URL; fileId khong ai deliver -> het timeout tra None."""
    reg = ctrl_mod.VoiceAsyncRegistry()
    box = {}

    def _wait():
        box["got"] = reg.wait("file-voice-1", timeout_s=5.0)

    th = threading.Thread(target=_wait)
    th.start()
    time.sleep(0.2)
    reg.deliver("file-voice-1", AMR_URL, AAC_URL)
    th.join(timeout=5)
    assert box["got"] == {"amr": AMR_URL, "aac": AAC_URL}, box
    started = time.time()
    assert reg.wait("file-khong-co", timeout_s=0.3) is None
    assert time.time() - started >= 0.3


# -- Chat.send_voice: doi event roi moi gui buoc 2 ----------------------

def test_voice_waits_for_ctrl_event_and_sends_file_url():
    """Waiter tra {amr, aac} -> buoc 2 phai gui kem fileUrl=amr,
    aacUrl=aac (giong fileAsync sau wait cua bundle)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        waiter = FakeVoiceWaiter({"amr": AMR_URL, "aac": AAC_URL})
        chat = make_chat(mock, waiter=waiter)
        res = chat.send_voice("user", "20001", "voice.aac",
                              FAKE_AAC, "audio/aac")
        assert res["data"]["msgId"] == "msg-voice-1", res
        assert mock.voice_send_calls == 1, mock.voice_send_calls
        assert waiter.calls == [("file-voice-1", 5.0)], waiter.calls
        sent = mock.voice_send_bodies[0]["body"]
        assert sent["fileUrl"] == AMR_URL, sent
        assert sent["aacUrl"] == AAC_URL, sent
    finally:
        mock.stop()


def test_voice_waits_for_late_ctrl_event():
    """Event den TRE (0.5 s sau khi wait bat dau) van duoc nhan:
    buoc 2 gui kem fileUrl; khong phai cho het timeout."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        waiter = DelayedVoiceWaiter()
        chat = make_chat(mock, waiter=waiter, timeout=5.0)
        box = {}

        def _send():
            try:
                box["res"] = chat.send_voice(
                    "user", "20001", "voice.aac", FAKE_AAC, "audio/aac")
            except Exception as e:  # noqa: BLE001
                box["err"] = e

        th = threading.Thread(target=_send)
        th.start()
        time.sleep(0.5)
        waiter.deliver({"amr": AMR_URL, "aac": AAC_URL})
        th.join(timeout=10)
        assert "err" not in box, box
        assert box["res"]["data"]["msgId"] == "msg-voice-1", box
        assert mock.voice_send_calls == 1, mock.voice_send_calls
        sent = mock.voice_send_bodies[0]["body"]
        assert sent["fileUrl"] == AMR_URL, sent
        assert sent["aacUrl"] == AAC_URL, sent
    finally:
        mock.stop()


def test_voice_never_sends_step2_without_async_url():
    """Event KHONG bao gio den -> het timeout thi loi ro rang va
    KHONG gui buoc 2 (khong gui "hi vong" nhu code cu — do chinh
    la cai gay ra 114 live)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        waiter = FakeVoiceWaiter(None)
        chat = make_chat(mock, waiter=waiter, timeout=0.5)
        try:
            chat.send_voice("user", "20001", "voice.aac",
                            FAKE_AAC, "audio/aac")
            raise AssertionError("expected ZaloChatError on timeout")
        except chat_mod.ZaloChatError as e:
            assert "voice" in str(e).lower() or "async" in str(e) \
                or "ctrl" in str(e) or "URL" in str(e), e
        assert mock.voice_upload_calls == 1, mock.voice_upload_calls
        assert mock.voice_send_calls == 0, mock.voice_send_calls
    finally:
        mock.stop()


def test_voice_no_waiter_or_ctrl_down_fails_fast():
    """Khong co waiter, hoac kenh ctrl chua chay (feeder_running
    False) -> loi NGAY, khong doi het timeout roi moi loi, va
    khong gui buoc 2."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        for waiter in (None, FakeVoiceWaiter(
                {"amr": AMR_URL, "aac": AAC_URL}, feeder_running=False)):
            chat = make_chat(mock, waiter=waiter, timeout=30.0)
            started = time.time()
            try:
                chat.send_voice("user", "20001", "voice.aac",
                                FAKE_AAC, "audio/aac")
                raise AssertionError("expected ZaloChatError, waiter=%r"
                                     % (waiter,))
            except chat_mod.ZaloChatError:
                pass
            assert time.time() - started < 5.0, \
                "phai loi nhanh, khong doi het timeout"
        assert mock.voice_send_calls == 0, mock.voice_send_calls
    finally:
        mock.stop()


def test_voice_chunk_response_urls_do_not_skip_wait():
    """(a) CHUNK-RESPONSE CO URL VAN PHAI DOI EVENT: truong amr/aac
    trong chunk-response thuoc nhanh DUPLICATE/cache — bundle khong
    bao gio lay URL tu do (handleSendChunkResp chi doc finished/
    fileId). Mock tra chunk cuoi kem amr/aac nhung event KHONG bao
    gio den -> het timeout thi loi ro rang va KHONG gui buoc 2
    (waiter VAN duoc goi). Ban goc cua test nay ("chunk-response
    co URL thi bo qua wait") la SAI, da doi thanh pin hanh vi dung
    khi gop vong 114."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        mock.voice_upload_extra = {"amr": AMR_URL, "aac": AAC_URL}
        waiter = FakeVoiceWaiter(None)
        chat = make_chat(mock, waiter=waiter, timeout=0.5)
        try:
            chat.send_voice("user", "20001", "voice.aac",
                            FAKE_AAC, "audio/aac")
            raise AssertionError("expected ZaloChatError on timeout")
        except chat_mod.ZaloChatError:
            pass
        assert waiter.calls == [("file-voice-1", 0.5)], waiter.calls
        assert mock.voice_send_calls == 0, mock.voice_send_calls
    finally:
        mock.stop()


def test_voice_group_waits_too():
    """Nhom cung doi event nhu 1-1; buoc 2 nhom co fileUrl, grid,
    KHONG imei."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        waiter = FakeVoiceWaiter({"amr": AMR_URL, "aac": AAC_URL})
        chat = make_chat(mock, waiter=waiter)
        res = chat.send_voice("group", "30001", "voice.aac",
                              FAKE_AAC, "audio/aac")
        assert res["data"]["msgId"] == "msg-voice-1", res
        sent = mock.voice_send_bodies[0]["body"]
        assert mock.voice_send_bodies[0]["path"] == \
            "/api/group/asyncfile/msg", mock.voice_send_bodies
        assert sent["fileUrl"] == AMR_URL, sent
        assert sent["grid"] == "30001", sent
        assert "imei" not in sent, sent
    finally:
        mock.stop()


# -- e2e qua route app: registry cua AppState ---------------------------

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


BASE = ""


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
    tmpdir = __import__("tempfile").mkdtemp(prefix="zalo-pc-voice114-")
    patch_domains(mock)
    state = app_server.AppState(tmpdir)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    BASE = "http://127.0.0.1:%d" % port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    login_via_mock()
    return httpd, state


def _sendvoice_via_app():
    mbody, mctype = chat_mod.build_multipart(
        {"type": "user"},
        [("file", "voice.aac", "audio/aac", FAKE_AAC)])
    return api("POST", "/api/thread/20001/sendvoice",
               mbody, {"Content-Type": mctype})


def test_server_voice_sends_file_url_from_ctrl_registry():
    """Qua route app: event ctrl da den TRUOC (registry cua AppState
    da co URL cho file-voice-1 — duong cache-hit cua bundle) ->
    route 200 ok, buoc 2 co fileUrl."""
    mock = MockZalo().start()
    try:
        httpd, state = _run_server(mock)
        try:
            state.voice_async.deliver("file-voice-1", AMR_URL, AAC_URL)
            status, body = _sendvoice_via_app()
            assert status == 200 and body["ok"] is True, body
            assert body["message"]["kind"] == "voice", body
            assert mock.voice_send_calls == 1, mock.voice_send_calls
            sent = mock.voice_send_bodies[0]["body"]
            assert sent["fileUrl"] == AMR_URL, sent
            assert sent["aacUrl"] == AAC_URL, sent
        finally:
            httpd.shutdown()
    finally:
        mock.stop()


def test_server_voice_without_ctrl_event_fails_honestly():
    """Qua route app: khong co event ctrl nao (kenh ctrl chua chay
    o AppState test) -> route 502, loi noi ro chua co URL ghi am,
    va KHONG co lan goi asyncfile/msg nao (khong gui mu)."""
    mock = MockZalo().start()
    try:
        httpd, state = _run_server(mock)
        try:
            state.voice_async_timeout = 0.5
            status, body = _sendvoice_via_app()
            assert status == 502, body
            assert "URL" in str(body.get("error", "")) \
                or "ctrl" in str(body.get("error", "")).lower() \
                or "voice" in str(body.get("error", "")).lower(), body
            assert mock.voice_upload_calls == 1, \
                mock.voice_upload_calls
            assert mock.voice_send_calls == 0, mock.voice_send_calls
        finally:
            httpd.shutdown()
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VOICE ASYNC 114 TESTS PASSED")
