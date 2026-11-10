"""Chat theo thread (module chat.py + route /api/thread/*) doi voi
mock server.

Mock kiem chung doc lap (openssl + hashlib): duong dan, body AES,
query type=2/11, multipart fileContent. Khong dang nhap that,
khong gui tin that.
"""

import contextlib
import io
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


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    # chat.py bind domain o muc module (khong doc lai protocol
    # moi lan goi) — patch ca ba cho mock.
    chat_mod.CHAT_DOMAIN = mock.base
    chat_mod.FILES_DOMAIN = mock.base
    chat_mod.GROUP_DOMAIN = mock.base


class _ImmediateVoiceWaiter:
    """Waiter gia: event ctrl voice_aac_success da den truoc
    (cache-hit cua bundle) — tra ngay {amr, aac} (loi 114)."""

    feeder_running = True

    def wait(self, file_id, timeout_s):
        return {"amr": "https://f1-voice-aac-dl.zdn.vn/test.amr",
                "aac": "https://f1-voice-aac-dl.zdn.vn/test.aac"}


class _ImmediateFileWaiter:
    """Waiter gia: event ctrl file_done da den truoc (cache-hit
    cua bundle: getFileIdData) — tra ngay {"url"} (loi 405
    sharefile_full)."""

    feeder_running = True

    def wait(self, file_id, timeout_s):
        return {"url": "https://f1-file-dl.zdn.vn/test.docx"}


def make_chat(mock):
    t = app_server.make_transport("sek-test")
    return chat_mod.Chat(t, "dev-1", TEST_SESSION_KEY,
                         voice_async=_ImmediateVoiceWaiter(),
                         voice_async_timeout=5.0,
                         file_async=_ImmediateFileWaiter(),
                         file_async_timeout=5.0)


def test_send_text_user_and_group():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_text("user", "20001", "Xin chao")
        assert res["data"]["msgId"] == "msg-1", res
        # clientId la JSON NUMBER epoch-ms, tang don dieu — loi 114
        # xuat phat tu clientId string (SERVICE-MAP.md §3.1).
        assert isinstance(res["client_id"], int), res
        assert res["client_id"] > 10 ** 12, res
        assert res["data"]["body"]["clientId"] == res["client_id"], res
        assert res["data"]["body"]["ttl"] == 0, res
        assert res["data"]["body"]["toid"] == "20001", res
        paths = [p for p, _, _ in mock.seen
                 if p == "/api/message/sms"]
        assert len(paths) == 1, mock.seen
        res2 = chat.send_text("group", "30001", "Chao ca nhom")
        assert res2["data"]["msgId"] == "msg-1", res2
        assert isinstance(res2["client_id"], int), res2
        assert res2["client_id"] > res["client_id"], res
        assert res2["data"]["body"]["ttl"] == 0, res2
        assert res2["data"]["body"]["grid"] == "30001", res2
        assert res2["data"]["body"]["visibility"] == 0, res2
        gpaths = [p for p, _, _ in mock.seen
                  if p == "/api/group/sendmsg"]
        assert len(gpaths) == 1, mock.seen
        # ttl tu xoa duoc gui nguyen (ms).
        res3 = chat.send_text("user", "20001", "Tu xoa sau 1h",
                              ttl=3600)
        assert res3["data"]["body"]["ttl"] == 3600, res3
        assert res3["client_id"] > res2["client_id"], res3
        try:
            chat.send_text("user", "20001", "   ")
            raise AssertionError("expected ValueError on empty message")
        except ValueError:
            pass
    finally:
        mock.stop()


def test_send_link():
    """Gui link 1-1 (11286) / nhom (11193): POST form params AES;
    clientId NUMBER, mentionInfo "" (1-1) / "[]" (nhom), ttl.
    (SERVICE-MAP.md §3.2, #72.)"""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_link("user", "20001",
                             "https://example.invalid/a",
                             message="Xem nay", title="Tieu de",
                             desc="Mo ta")
        assert res["data"]["msgId"] == "msg-1", res
        assert isinstance(res["client_id"], int), res
        body = res["data"]["body"]
        assert body["href"] == "https://example.invalid/a", body
        assert body["msg"] == "Xem nay", body
        assert body["title"] == "Tieu de", body
        assert body["desc"] == "Mo ta", body
        assert body["toId"] == "20001", body
        assert body["mentionInfo"] == "", body
        assert body["clientId"] == res["client_id"], body
        assert body["ttl"] == 0, body
        assert "imei" not in body, body
        paths = [p for p, _, _ in mock.seen
                 if p == "/api/message/link"]
        assert len(paths) == 1, mock.seen
        res2 = chat.send_link("group", "30001",
                              "https://example.invalid/b", ttl=3600)
        body2 = res2["data"]["body"]
        assert res2["client_id"] > res["client_id"], res2
        assert body2["grid"] == "30001", body2
        assert body2["mentionInfo"] == "[]", body2
        assert body2["visibility"] == 0, body2
        assert body2["imei"] == "dev-1", body2
        assert body2["ttl"] == 3600, body2
        gpaths = [p for p, _, _ in mock.seen
                  if p == "/api/group/sendlink"]
        assert len(gpaths) == 1, mock.seen
        try:
            chat.send_link("user", "20001", "   ")
            raise AssertionError("expected ValueError on empty href")
        except ValueError:
            pass
    finally:
        mock.stop()


def test_group_history():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        hist = chat.history_group("30001", 50)
        assert hist["has_more"] is False, hist
        assert [m["text"] for m in hist["messages"]] == \
            ["Chao ca nhom", "Chao Ban A"], hist
        assert [m["sender_id"] for m in hist["messages"]] == \
            ["20001", "20002"], hist
        assert hist["messages"][0]["time"] == 1762345600, hist
        paths = [p for p, _, _ in mock.seen
                 if p == "/api/group/history"]
        assert len(paths) == 1, mock.seen
    finally:
        mock.stop()


def test_user_history_has_no_endpoint():
    """Lich su 1-1: KHONG co endpoint HTTPS — history_user_
    unavailable() khong goi gi ca, chi tra thong bao gioi han."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.history_user_unavailable()
        assert res["unavailable"] is True, res
        assert "chua lay duoc qua HTTPS" in res["notice"], res
        bad = [p for p, _, _ in mock.seen if "history" in p]
        assert bad == [], mock.seen
    finally:
        mock.stop()


def test_send_file_photo_voice():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        # File thuong di DUONG HAI BUOC asyncfile (upload 11776/
        # 13000 + asyncfile/msg 11777/13001) — sharefile_full
        # (11146/11191) la code chet (0 caller trong bundle) va
        # Zalo tra 405 (live 2026-11-07). clientId la NUMBER o ca
        # hai buoc (JSON.stringify cua upload-manager), giong nhau
        # giua upload va buoc 2; fileUrl lay tu event ctrl
        # file_done (waiter gia), KHONG lay tu chunk-response.
        res = chat.send_file("user", "20001", "hello.txt",
                             b"hello file", "text/plain")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        assert res["file_id"] == "file-1", res
        user_client_id = res["client_id"]
        res = chat.send_file("group", "30001", "bao-cao.pdf",
                             b"%PDF-fake", "application/pdf")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        assert res["file_id"] == "file-1", res
        group_client_id = res["client_id"]
        # Buoc 2 cua File: item getFileAsyncItem (xem
        # test_voice_112.py::test_file_params_match_bundle).
        sent = mock.file_send_bodies[0]["body"]
        assert sent["fileId"] == "file-1", sent
        assert sent["extension"] == "txt", sent
        assert sent["fileName"] == "hello.txt", sent
        assert sent["fType"] == 1, sent
        assert sent["fileCount"] == 0, sent
        assert sent["fdata"] == "{}", sent
        assert sent["fileUrl"] == \
            "https://f1-file-dl.zdn.vn/test.docx", sent
        assert sent["zsource"] == -1, sent
        assert sent["clientId"] == user_client_id, sent
        assert sent["toid"] == "20001", sent
        assert sent["imei"] == "dev-1", sent
        sent_group = mock.file_send_bodies[1]["body"]
        assert sent_group["extension"] == "pdf", sent_group
        assert sent_group["fileName"] == "bao-cao.pdf", sent_group
        assert sent_group["clientId"] == group_client_id, sent_group
        assert "imei" not in sent_group, sent_group
        assert sent_group["grid"] == "30001", sent_group
        # Upload chunk 1-1 + nhom dung cung clientId nhu buoc 2.
        assert mock.file_upload_bodies[0]["body"]["clientId"] == \
            user_client_id, mock.file_upload_bodies
        assert mock.file_upload_bodies[1]["body"]["clientId"] == \
            group_client_id, mock.file_upload_bodies
        res = chat.send_photo("user", "20001", "anh.jpg",
                              b"\xff\xd8\xff\xe0FAKEJPEGDATA", "image/jpeg",
                              800, 600)
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        assert res["data"]["clientId"] == res["client_id"], res
        res = chat.send_photo("group", "30001", "anh.png",
                              b"\x89PNG\r\n\x1a\nFAKEPNGDATA", "image/png",
                              640, 480)
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        assert res["data"]["clientId"] == res["client_id"], res
        # Voice (cach zalo cu): tai .aac len nhu TEP THUONG (asyncfile/upload + file_done) roi gui bang forward msgType 3.
        aac = b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\x00" * 100
        res = chat.send_voice("user", "20001", "voice.aac",
                              aac, "audio/aac")
        assert res["data"]["msgId"] == "msg-voice-1", res
        assert isinstance(res["client_id"], int), res
        assert res["voice_url"] == "https://f1-file-dl.zdn.vn/test.docx", res
        res = chat.send_voice("group", "30001", "voice.aac",
                              aac, "audio/aac", ttl=60000)
        assert res["data"]["msgId"] == "msg-voice-1", res
        fw = mock.voice_forward_bodies
        assert [f["path"] for f in fw] == ["/api/message/forward", "/api/group/forward"], fw
        assert fw[0]["body"]["toId"] == "20001" and fw[0]["body"]["ttl"] == 0, fw[0]
        assert fw[1]["body"]["grid"] == "30001" and fw[1]["body"]["ttl"] == 60000, fw[1]
        assert json.loads(fw[0]["body"]["msgInfo"])["fileSize"] == len(aac), fw[0]
        seen = [p for p, _, _ in mock.seen]
        # tep + tin thoai deu tai len bang asyncfile/upload (2 lan moi phia); duong cu voice/upload KHONG con duoc goi.
        for want, n in (("/api/message/asyncfile/upload", 2), ("/api/group/asyncfile/upload", 2),
                        ("/api/message/photo", 1), ("/api/group/sendpt", 1),
                        ("/api/message/forward", 1), ("/api/group/forward", 1)):
            assert seen.count(want) == n, (want, seen)
        assert not [p for p in seen if "voice/upload" in p], seen
        # asyncfile/msg: chi tep (1 lan moi phia); tin thoai khong di duong nay nua.
        assert seen.count("/api/message/asyncfile/msg") == 1, seen
        assert seen.count("/api/group/asyncfile/msg") == 1, seen
        # Duong truc tiep sharefile_full CHEt — khong bao gio duoc
        # goi nua (goi la mock tra 405 nhu Zalo that, live
        # 2026-11-07).
        assert not [p for p in seen if "sharefile" in p], seen
    finally:
        mock.stop()


def test_send_file_empty_data_errors():
    """Buoc 2 tra data rong (200/error_code=0 nhung khong tao tin
    nao) -> send_file phai bao loi that ("khong co ma tin"), KHONG
    tra ok:true — cung dang thanh cong gia nhu send_photo truoc
    khi sua (loi cam 07/11). Route tra 502, khong phai 200 ok."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        mock.file_send_mode = "empty"
        chat = make_chat(mock)
        try:
            chat.send_file("user", "20001", "bao-cao.docx",
                           b"PK\x03\x04" + b"x" * 20,
                           "application/vnd.openxmlformats-officedocument"
                           ".wordprocessingml.document")
            raise AssertionError("expected ZaloChatError on empty data")
        except chat_mod.ZaloChatError as e:
            assert "khong co ma tin" in str(e), str(e)
        assert mock.file_upload_calls == 1, mock.file_upload_calls
        assert mock.file_send_calls == 1, mock.file_send_calls
    finally:
        mock.stop()
    # Route-level: 502, khong ok:true.
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-empty-test-")
    try:
        patch_domains(mock)
        mock.file_send_mode = "empty"
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        login_via_mock()
        state.file_async.deliver("file-1",
                                 "https://f1-file-dl.zdn.vn/test.docx")
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "bao-cao.docx",
              "application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document", b"PK\x03\x04" + b"x" * 20)])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 502, body
        assert body.get("ok") is not True, body
        assert "khong co ma tin" in body["error"], body
        httpd.shutdown()
    finally:
        mock.stop()
        # Dung poller sync/ctrl SAU KHI mock tat (poll se loi
        # nhanh, join kip): khong thi daemon thread con in retry
        # ra stdout luc interpreter tat -> abort 134
        # (_enter_buffered_busy) du test da pass het — loi co san,
        # thay tren base bea4f0a (xem ghi chu o sync_poll.run).
        state.stop_sync()


def test_typing_and_seen():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        assert chat.send_typing("user", "20001")["ok"] is True
        assert chat.send_typing("group", "30001")["ok"] is True
        assert chat.send_seen("user", "20001", ["m1"])["ok"] is True
        assert chat.send_seen("group", "30001", ["m1", "m2"])["ok"] is True
        seen = [p for p, _, _ in mock.seen]
        for want in ("/api/message/typing", "/api/group/typing",
                     "/api/message/seen", "/api/group/seen"):
            assert seen.count(want) == 1, (want, seen)
    finally:
        mock.stop()


def test_multipart_roundtrip():
    body, ctype = chat_mod.build_multipart(
        {"type": "group", "kind": "file"},
        [("file", "a.txt", "text/plain", b"hello")])
    fields, files = chat_mod.parse_multipart(body, ctype)
    assert fields == {"type": "group", "kind": "file"}, fields
    assert files["file"][0] == "a.txt", files
    assert files["file"][1] == "text/plain", files
    assert files["file"][2] == b"hello", files


def test_chat_store_local_echo():
    store = chat_mod.ChatStore()
    msg = store.local_message("user", "20001", "text",
                              text="Xin chao", client_id="c1")
    store.record_sent("user", "20001", msg)
    assert store.sent_for("user", "20001")[0]["text"] == "Xin chao"
    assert store.sent_for("group", "30001") == []


# -- e2e qua server app that -------------------------------------------
BASE = ""


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def api_json(method, path, obj=None):
    data = json.dumps(obj).encode() if obj is not None else None
    return api(method, path, data, {"Content-Type": "application/json"})


def login_via_mock():
    """QR flow qua mock (mau tu test_server_smoke) — de server co
    phien Zalo that (mock) roi moi test route chat."""
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


def test_server_thread_routes():
    global BASE
    mock = MockZalo().start()
    # Kenh sync tu mo sau login (sync_poll): khoa poll o che do
    # "empty" TRUOC login de test nay khong bi tin den chen vao
    # lich su (tin den duoc kiem o test_incoming.py, ca don le
    # lan e2e). Poller van chay nen nhung khong giao tin nao.
    mock.poll_mode = "empty"
    tmp = tempfile.mkdtemp(prefix="zalo-pc-chat-test-")
    try:
        patch_domains(mock)
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        # Chua dang nhap: route chat tra 401 (giong /api/contacts).
        status, body = api("GET", "/api/thread/30001/history?type=group")
        assert status == 401, body
        status, body = api_json("POST", "/api/thread/20001/send",
                                {"type": "user", "message": "x"})
        assert status == 401, body

        login_via_mock()

        # Event ctrl voice_aac_success da den truoc (registry cua
        # AppState) — neu khong, send_voice doi het timeout roi loi
        # thay vi gui buoc 2 khong co fileUrl (loi 114); mock tra
        # fileId "file-voice-1" dinh san nen deliver truoc duoc.
        state.voice_async.deliver(
            "file-voice-1",
            "https://f1-voice-aac-dl.zdn.vn/test.amr",
            "https://f1-voice-aac-dl.zdn.vn/test.aac")
        # Event ctrl file_done da den truoc (registry cua AppState)
        # — giong voice: neu khong, send_file doi het timeout roi
        # loi thay vi gui buoc 2 khong co fileUrl; mock tra fileId
        # "file-1" dinh san nen deliver truoc duoc.
        state.file_async.deliver(
            "file-1", "https://f1-file-dl.zdn.vn/test.docx")

        # (poll_mode "empty" da dat truoc login — xem dau test.)

        # Lich su nhom: tin mock + chua co tin gui trong phien.
        status, body = api("GET",
                           "/api/thread/30001/history?type=group&count=50")
        assert status == 200, body
        assert [m["text"] for m in body["messages"]] == \
            ["Chao ca nhom", "Chao Ban A"], body
        assert body.get("has_more") is False, body

        # Lich su 1-1: thong bao gioi han trung thuc, khong bia tin.
        status, body = api("GET", "/api/thread/20001/history?type=user")
        assert status == 200, body
        assert body.get("unavailable") is True, body
        assert "chua lay duoc qua HTTPS" in body.get("notice", ""), body
        assert body["messages"] == [], body

        # Gui text nhom: thanh cong + hien ngay trong lich su sau do.
        status, body = api_json("POST", "/api/thread/30001/send",
                                {"type": "group",
                                 "message": "Toi vua gui"})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["text"] == "Toi vua gui", body
        assert body["message"]["direction"] == "out", body
        status, body = api("GET", "/api/thread/30001/history?type=group")
        assert [m["text"] for m in body["messages"]] == \
            ["Chao ca nhom", "Chao Ban A", "Toi vua gui"], body

        # Gui text 1-1: thanh cong, lich su sau do chi co tin vua gui
        # (khong co lich su cu qua HTTPS) — tin vua gui da ghi xuong
        # DB local (message_store) nen unavailable False + bao ro
        # lich su chi tu khi bat dau luu (DB partial).
        status, body = api_json("POST", "/api/thread/20001/send",
                                {"type": "user", "message": "Chao ban"})
        assert status == 200 and body["ok"] is True, body
        status, body = api("GET", "/api/thread/20001/history?type=user")
        assert [m["text"] for m in body["messages"]] == ["Chao ban"], body
        assert body.get("unavailable") is False, body
        assert "chi co tu khi app bat dau luu" in body.get("notice", ""), \
            body
        assert body.get("source") == "db+inbox", body

        # Gui rong -> 400, khong goi Zalo.
        status, body = api_json("POST", "/api/thread/20001/send",
                                {"type": "user", "message": "   "})
        assert status == 400, body

        # Gui link 1-1 + nhom (11286/11193): thanh cong, luu local.
        status, body = api_json("POST", "/api/thread/20001/sendlink",
                                {"type": "user",
                                 "link": "https://example.invalid/a",
                                 "message": "Xem nay"})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["text"] == "Xem nay", body
        assert body["message"]["direction"] == "out", body
        status, body = api_json("POST", "/api/thread/30001/sendlink",
                                {"type": "group",
                                 "link": "https://example.invalid/b",
                                 "ttl": 3600})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["text"] == "https://example.invalid/b", body
        # Link rong -> 400, khong goi Zalo.
        status, body = api_json("POST", "/api/thread/20001/sendlink",
                                {"type": "user", "link": "   "})
        assert status == 400, body

        # Dinh dang chu: markdown + tu nhan manh -> textProperties (UTF-16) den Chat.send_text,
        # ca 1-1 lan nhom; styles sai -> 400, khong gui.
        got = []
        real_send_text = chat_mod.Chat.send_text

        def spy_send_text(self, thread_type, thread_id, message, **kw):
            got.append((thread_type, message, kw.get("styles")))
            return real_send_text(self, thread_type, thread_id, message, **kw)
        chat_mod.Chat.send_text = spy_send_text
        try:
            status, body = api_json("POST", "/api/thread/20001/send", {
                "type": "user", "message": "Nhiet do **29C** va 75%", "format": "markdown", "auto_emphasis": "cam"})
            assert status == 200 and got[-1][1] == "Nhiet do 29C va 75%", (status, got)
            assert got[-1][2] == [{"start": 9, "len": 3, "st": "c_f27806,b"},
                                  {"start": 16, "len": 3, "st": "c_f27806,b"}], got[-1]
            assert body["message"]["text"] == "Nhiet do 29C va 75%", body
            status, body = api_json("POST", "/api/thread/30001/send", {
                "type": "group", "message": "Xin chao", "styles": [{"start": 0, "len": 3, "st": "b"}]})
            assert status == 200 and got[-1][2] == [{"start": 0, "len": 3, "st": "b"}], got[-1]
            n = len(got)
            for bad in ({"message": "abc", "styles": [{"start": 0, "len": 3, "st": "f_20"}]},
                        {"message": "abc", "format": "html"},
                        {"message": "abc", "auto_emphasis": "tim"},
                        {"message": "{red}{/}", "format": "markdown"}):      # chi con the -> khong con chu -> rong
                status, body = api_json("POST", "/api/thread/20001/send", dict(bad, type="user"))
                assert status == 400 and "error" in body, (bad, status, body)
            assert len(got) == n, "request sai khong duoc tới Zalo"
        finally:
            chat_mod.Chat.send_text = real_send_text

        # Link thieu title/desc: Zalo tu choi (114) -> app tu lay xem truoc
        # tu dich vu parse_link, co title tu truyen thi giu nguyen, parse_link
        # hong thi van gui nhu cu (khong lam hong viec gui).
        sent = []
        real_send_link = chat_mod.Chat.send_link
        real_handle = app_server.services_mod.handle_svc

        def spy_send_link(self, thread_type, thread_id, href, **kw):
            sent.append(kw)
            return real_send_link(self, thread_type, thread_id, href, **kw)
        chat_mod.Chat.send_link = spy_send_link
        try:
            app_server.services_mod.handle_svc = lambda st, action, b, **k: (
                200, {"ok": True, "data": {"data": {
                    "title": "Tieu de PV", "desc": "Mo ta PV", "thumb": "https://x/t.jpg"}}})
            status, body = api_json("POST", "/api/thread/20001/sendlink",
                                    {"type": "user", "link": "https://example.invalid/c"})
            assert status == 200 and sent[-1]["title"] == "Tieu de PV" \
                and sent[-1]["desc"] == "Mo ta PV" \
                and sent[-1]["thumb"] == "https://x/t.jpg", sent
            api_json("POST", "/api/thread/20001/sendlink",
                     {"type": "user", "link": "https://example.invalid/d", "title": "Tu dat"})
            assert sent[-1]["title"] == "Tu dat", sent
            def boom(*a, **k):
                raise RuntimeError("parse_link hong")
            app_server.services_mod.handle_svc = boom
            status, body = api_json("POST", "/api/thread/20001/sendlink",
                                    {"type": "user", "link": "https://example.invalid/e"})
            assert status == 200 and sent[-1]["title"] == "" and sent[-1]["desc"] == "", (status, sent)
        finally:
            chat_mod.Chat.send_link = real_send_link
            app_server.services_mod.handle_svc = real_handle

        # Dinh kem file (multipart) 1-1 + anh nhom (kind=photo).
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "hello.txt", "text/plain", b"hello file")])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "file", body
        assert body["message"]["file_name"] == "hello.txt", body
        mbody, mctype = chat_mod.build_multipart(
            {"type": "group", "kind": "photo", "width": "800",
             "height": "600"},
            [("file", "anh.jpg", "image/jpeg",
              b"\xff\xd8\xff\xe0FAKEJPEGDATA")])
        status, body = api("POST", "/api/thread/30001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "photo", body

        # Gui file ghi am (multipart) nhom. File phai la AAC ADTS
        # THAT (it nhat header ADTS sync) vi route sendvoice kiem
        # tra noi dung truoc khi gui — byte gia khong phai AAC se
        # bi dua di doi bang ffmpeg va loi (xem
        # test_voice_transcode.py).
        mbody, mctype = chat_mod.build_multipart(
            {"type": "group"},
            [("file", "voice.aac", "audio/aac",
              b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\x00" * 100)])
        status, body = api("POST", "/api/thread/30001/sendvoice",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "voice", body
        assert body["message"]["file_name"] == "voice.aac", body
        assert body.get("converted_to_aac") is False, body
        assert "trinh duyet" in body.get("note", ""), body

        # Thieu file -> 400.
        mbody, mctype = chat_mod.build_multipart({"type": "user"}, [])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 400, body

        # Typing + seen: goi that xuong mock, tra ok.
        status, body = api_json("POST", "/api/thread/20001/typing",
                                {"type": "user"})
        assert status == 200 and body["ok"] is True, body
        status, body = api_json("POST", "/api/thread/30001/seen",
                                {"type": "group", "msg_ids": ["m1"]})
        assert status == 200 and body["ok"] is True, body

        # Dang xuat: route chat lai 401.
        status, body = api_json("POST", "/api/logout", {})
        assert body["ok"] is True
        status, body = api("GET", "/api/thread/30001/history?type=group")
        assert status == 401, body
        httpd.shutdown()
    finally:
        mock.stop()
        # Dung poller sync/ctrl (xem test_send_file_empty_data_errors
        # — tranh abort 134 luc shutdown).
        state.stop_sync()


def test_attach_validation():
    """Dinh kem theo Node.js (zalobot): chi jpg/jpeg/png/webp la anh
    (EXT_ALBUM); gif/heic/bmp/... la tep; file rong bi tu choi
    truoc khi goi Zalo; anh phai dung la anh (magic bytes)."""
    assert chat_mod.MAX_FILE_BYTES == 150 * 1024 * 1024
    assert chat_mod.MAX_PHOTO_BYTES == 25 * 1024 * 1024
    # Phan loai anh: duoi ten quyet dinh (Zalo phan loai bang duoi).
    for name in ("a.jpg", "A.JPG", "a.jpeg", "a.png", "a.webp"):
        assert chat_mod.is_photo_file(name, ""), name
    for name, mime in (("a.gif", "image/gif"), ("a.bmp", "image/bmp"),
                       ("a.heic", "image/heic"), ("a.svg", "image/svg+xml"),
                       ("a.m3u", ""), ("a.txt", "text/plain"),
                       ("a.mp4", "video/mp4"), ("khong-duoi", "")):
        assert not chat_mod.is_photo_file(name, mime), (name, mime)
    # Khong co duoi thi xet MIME.
    assert chat_mod.is_photo_file("anh", "image/png")
    assert not chat_mod.is_photo_file("anh", "image/gif")
    assert not chat_mod.is_photo_file("anh", "")
    # effective_kind: photo chi giu khi dung la anh.
    assert chat_mod.effective_kind("photo", "a.jpg", "") == "photo"
    assert chat_mod.effective_kind("photo", "a.gif", "image/gif") == "file"
    assert chat_mod.effective_kind("photo", "a.heic", "") == "file"
    assert chat_mod.effective_kind("file", "a.jpg", "") == "file"
    assert chat_mod.effective_kind("", "a.jpg", "") == "file"
    # Magic bytes (giong duoiAnhThat cua Node.js).
    assert chat_mod.detect_image_format(b"\xff\xd8\xff" + b"x" * 9) == "jpg"
    assert chat_mod.detect_image_format(
        b"\x89PNG\r\n\x1a\n" + b"x" * 4) == "png"
    assert chat_mod.detect_image_format(b"GIF89a" + b"x" * 6) == "gif"
    assert chat_mod.detect_image_format(
        b"RIFFxxxxWEBP" + b"x" * 4) == "webp"
    assert chat_mod.detect_image_format(b"BM" + b"x" * 10) == "bmp"
    assert chat_mod.detect_image_format(b"NOTANIMAGE....") is None
    assert chat_mod.detect_image_format(b"") is None
    assert chat_mod.detect_image_format(b"\xff\xd8") is None
    # validate_attachment: ten thieu / file rong / qua lon / anh gia.
    for bad_args, want in (
            (("file", "", "", b"x"), "thieu ten file"),
            (("file", "a.m3u", "", b""), "rong (0 byte)"),
            (("photo", "a.jpg", "image/jpeg", b""), "rong (0 byte)"),
            (("photo", "a.jpg", "image/jpeg", b"NOTANIMAGE...."),
             "khong phai anh that")):
        try:
            chat_mod.validate_attachment(*bad_args)
            raise AssertionError("expected ValueError for %r" % (bad_args,))
        except ValueError as e:
            assert want in str(e), (want, str(e))
    # Gioi han kich thuoc (doi hang so tam de khong can cap MB that).
    old_file, old_photo = (chat_mod.MAX_FILE_BYTES,
                          chat_mod.MAX_PHOTO_BYTES)
    try:
        chat_mod.MAX_FILE_BYTES = 10
        chat_mod.MAX_PHOTO_BYTES = 10
        try:
            chat_mod.validate_attachment("file", "a.txt", "", b"x" * 11)
            raise AssertionError("expected ValueError on oversize file")
        except ValueError as e:
            assert "qua lon" in str(e), str(e)
        try:
            chat_mod.validate_attachment(
                "photo", "a.jpg", "image/jpeg",
                b"\xff\xd8\xff" + b"x" * 8)
            raise AssertionError("expected ValueError on oversize photo")
        except ValueError as e:
            assert "25 MB" in str(e), str(e)
    finally:
        chat_mod.MAX_FILE_BYTES = old_file
        chat_mod.MAX_PHOTO_BYTES = old_photo
    # Hop le: file thuong (ke ca .m3u cua user), anh jpg/png that.
    chat_mod.validate_attachment("file", "iptv-udpxy.m3u", "", b"data")
    chat_mod.validate_attachment("photo", "a.jpg", "image/jpeg",
                                 b"\xff\xd8\xff" + b"x" * 20)
    chat_mod.validate_attachment("photo", "a.png", "image/png",
                                 b"\x89PNG\r\n\x1a\n" + b"x" * 20)
    # send_file/send_photo tu choi file rong truoc khi goi mang.
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        try:
            chat.send_file("user", "20001", "rong.txt", b"", "text/plain")
            raise AssertionError("expected ValueError on empty send_file")
        except ValueError as e:
            assert "rong (0 byte)" in str(e), str(e)
        assert not [p for p, _, _ in mock.seen
                    if "sharefile" in p or "asyncfile" in p]
    finally:
        mock.stop()


def test_server_sendfile_validation():
    """Endpoint /api/thread/<id>/sendfile sau sua: file rong -> 400
    (khong goi Zalo); gif/heic gui kind=photo -> ha xuong file (200,
    asyncfile/upload, khong phai photo); anh that -> photo (200,
    sendpt); anh gia -> 400; loi Zalo -> 502 voi loi ro rang."""
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-attach-test-")
    try:
        patch_domains(mock)
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        login_via_mock()
        # Event ctrl file_done da den truoc (registry cua AppState)
        # — neu khong, send_file doi het timeout roi loi thay vi
        # gui buoc 2 khong co fileUrl (giong loi 114 cua voice);
        # mock tra fileId "file-1" dinh san nen deliver truoc duoc.
        state.file_async.deliver("file-1",
                                 "https://f1-file-dl.zdn.vn/test.docx")

        def file_upload_calls():
            return [p for p, _, _ in mock.seen
                    if p in ("/api/message/asyncfile/upload",
                             "/api/group/asyncfile/upload")]

        def photo_calls():
            return [p for p, _, _ in mock.seen
                    if p in ("/api/message/photo", "/api/group/sendpt")]

        # File rong (case live cua user: iptv-udpxy.m3u, 0 byte).
        before = len(file_upload_calls())
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "iptv-udpxy.m3u", "application/octet-stream", b"")])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 400, body
        assert "rong (0 byte)" in body["error"], body
        assert len(file_upload_calls()) == before, mock.seen

        # File .m3u khong rong: duoi khong bi chan, gui duoc.
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "iptv-udpxy.m3u", "text/plain", b"#EXTM3U\n")])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "file", body

        # GIF gui kind=photo -> ha xuong tep dinh kem (200, kind=file).
        gif = b"GIF89a" + b"\x01\x00\x01\x00\x00\x00\x00;"
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user", "kind": "photo", "width": "1",
             "height": "1"},
            [("file", "a.gif", "image/gif", gif)])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "file", body
        assert len(file_upload_calls()) == before + 2, mock.seen
        assert photo_calls() == [], mock.seen

        # HEIC gui kind=photo -> cung ha xuong tep.
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user", "kind": "photo", "width": "1",
             "height": "1"},
            [("file", "anh.heic", "image/heic", b"ftypheic" + b"x" * 8)])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "file", body

        # Anh PNG that, kind=photo -> duong photo (sendpt/sharefile
        # deu khong dung; mock ghi /api/message/photo).
        png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user", "kind": "photo", "width": "800",
             "height": "600"},
            [("file", "anh.png", "image/png", png)])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "photo", body
        assert photo_calls() == ["/api/message/photo"], mock.seen

        # Anh "gia": duoi .jpg nhung noi dung khong phai anh -> 400.
        before_photo = len(photo_calls())
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user", "kind": "photo", "width": "800",
             "height": "600"},
            [("file", "gia.jpg", "image/jpeg", b"<html>not image</html>")])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 400, body
        assert "khong phai anh that" in body["error"], body
        assert len(photo_calls()) == before_photo, mock.seen

        # Thieu ten file -> 400.
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "", "text/plain", b"x")])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 400, body
        assert "thieu ten file" in body["error"], body

        # Anh qua lon (doi hang so tam): 400, khong goi Zalo.
        old_photo = chat_mod.MAX_PHOTO_BYTES
        try:
            chat_mod.MAX_PHOTO_BYTES = 10
            mbody, mctype = chat_mod.build_multipart(
                {"type": "user", "kind": "photo", "width": "1",
                 "height": "1"},
                [("file", "lon.png", "image/png", png)])
            status, body = api("POST", "/api/thread/20001/sendfile",
                               mbody, {"Content-Type": mctype})
            assert status == 400, body
            assert "qua lon" in body["error"], body
        finally:
            chat_mod.MAX_PHOTO_BYTES = old_photo

        # Loi Zalo (error_code != 0) -> 502 voi loi ro rang (UI hien).
        real_make_transport = app_server.make_transport

        class ErrTransport:
            def __call__(self, url, timeout=30):
                return 200, {"error_code": 0, "data": {}}

            def http_post_multipart(self, url, body_bytes, content_type,
                                    timeout=60):
                return 200, {"error_code": 133,
                             "error_message": "File rong hoac sai dinh "
                             "dang", "data": {}}

        app_server.make_transport = lambda cookie="": ErrTransport()
        try:
            mbody, mctype = chat_mod.build_multipart(
                {"type": "user"},
                [("file", "x.txt", "text/plain", b"xx")])
            status, body = api("POST", "/api/thread/20001/sendfile",
                               mbody, {"Content-Type": mctype})
            assert status == 502, body
            assert "133" in body["error"], body
        finally:
            app_server.make_transport = real_make_transport
        httpd.shutdown()
    finally:
        mock.stop()
        # Dung poller sync/ctrl (xem test_send_file_empty_data_errors
        # — tranh abort 134 luc shutdown).
        state.stop_sync()


def test_server_sendfile_logs():
    """Log sendfile ra stdout (docker logs): moi lan goi sendfile
    phai de lai 1 dong [sendfile] thread/kind/size + ket qua/loi —
    live 07/11: log server khong co dong nao ve dinh kem nen khong
    chan doan duoc tu docker logs (app khong co F12)."""
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-sendfile-log-test-")
    try:
        patch_domains(mock)
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        login_via_mock()
        # Event ctrl file_done da den truoc (registry cua AppState)
        # — xem test_server_sendfile_validation.
        state.file_async.deliver("file-1",
                                 "https://f1-file-dl.zdn.vn/test.docx")

        # Gui file thanh cong -> log co entry + ok.
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "x.txt", "text/plain", b"#EXTM3U\n")])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status, body = api("POST", "/api/thread/20001/sendfile",
                               mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        log = buf.getvalue()
        assert "[sendfile] thread=20001 kind=file size=8" in log, log
        assert "-> ok client_id=" in log, log

        # File rong -> 400, log co entry + loi ro.
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "rong.txt", "text/plain", b"")])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status, body = api("POST", "/api/thread/20001/sendfile",
                               mbody, {"Content-Type": mctype})
        assert status == 400, body
        log = buf.getvalue()
        assert "[sendfile] thread=20001 kind=file size=0" in log, log
        assert "-> loi:" in log and "rong (0 byte)" in log, log
        httpd.shutdown()
    finally:
        mock.stop()
        # Dung poller sync/ctrl (xem test_send_file_empty_data_errors
        # — tranh abort 134 luc shutdown).
        state.stop_sync()


def test_send_photo_uses_files_domain():
    """Loi that 2026-11-07 06:50 +07 (user, ban 16a223c): gui anh 1-1
    cho Dai ca bi banner «Lỗi gửi file: chat: POST /api/message/photo
    network status=405» — 405 tu Zalo upstream, khong phai tu route
    app (route /api/thread/<id>/sendfile van nhan, chi sai host khi
    goi sang Zalo). NGUYEN NHAN: send_photo POST len
    {chat-wpa}/api/message/photo (1-1) / {group-wpa}/api/group/sendpt
    (nhom), nhung bundle PC that (bang lenh 231 muc, ham
    _sendPhoto: domainType FILE, commandId 11152/11164) + SERVICE-MAP
    §3.2 deu noi hai duong nay o files-wpa — chat-wpa/group-wpa
    khong phuc vu duong nay nen tra 405. Mock cu khong bat duoc vi
    patch_domains() gan ca ba domain ve cung mock.base (mock chi
    phan biet theo path) — test nay gan domain GIA KHAC NHAU de bat
    dung host, va chan _post_multipart de khong can mang that."""
    urls = []

    def fake_post(self, url, body_bytes, content_type, where):
        urls.append(url)
        # Tra payload thanh cong that ({msgId, ...}) — send_photo
        # doi data khong rong (loi cam 07/11: data rong = loi).
        return {"msgId": "msg-file-1"}

    orig_post = chat_mod.Chat._post_multipart
    orig_chat = chat_mod.CHAT_DOMAIN
    orig_files = chat_mod.FILES_DOMAIN
    orig_group = chat_mod.GROUP_DOMAIN
    chat_mod.Chat._post_multipart = fake_post
    try:
        chat_mod.CHAT_DOMAIN = "https://chat-wpa.test"
        chat_mod.FILES_DOMAIN = "https://files-wpa.test"
        chat_mod.GROUP_DOMAIN = "https://group-wpa.test"
        chat = chat_mod.Chat(lambda *a, **k: (200, {}), "dev-1",
                             TEST_SESSION_KEY)
        png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
        chat.send_photo("user", "20001", "anh.png", png, "image/png",
                        800, 600)
        chat.send_photo("group", "30001", "anh.png", png, "image/png",
                        800, 600)
    finally:
        chat_mod.Chat._post_multipart = orig_post
        chat_mod.CHAT_DOMAIN = orig_chat
        chat_mod.FILES_DOMAIN = orig_files
        chat_mod.GROUP_DOMAIN = orig_group
    assert len(urls) == 2, urls
    assert urls[0].startswith(
        "https://files-wpa.test/api/message/photo"), urls
    assert "type=2" in urls[0], urls
    assert urls[1].startswith(
        "https://files-wpa.test/api/group/sendpt"), urls
    assert "type=11" in urls[1], urls


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CHAT TESTS PASSED")
