"""Chat theo thread (module chat.py + route /api/thread/*) doi voi
mock server.

Mock kiem chung doc lap (openssl + hashlib): duong dan, body AES,
query type=2/11, multipart fileContent. Khong dang nhap that,
khong gui tin that.
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


def make_chat(mock):
    t = app_server.make_transport("sek-test")
    return chat_mod.Chat(t, "dev-1", TEST_SESSION_KEY)


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
        res = chat.send_file("user", "20001", "hello.txt",
                             b"hello file", "text/plain")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        assert res["data"]["clientId"] == res["client_id"], res
        res = chat.send_file("group", "30001", "bao-cao.pdf",
                             b"%PDF-fake", "application/pdf")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        res = chat.send_photo("user", "20001", "anh.jpg",
                              b"FAKEJPEGDATA", "image/jpeg", 800, 600)
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        res = chat.send_photo("group", "30001", "anh.png",
                              b"FAKEPNGDATA", "image/png", 640, 480)
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        res = chat.send_voice("user", "20001", "voice.mp3",
                              b"FAKEMP3DATA", "audio/mpeg")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        res = chat.send_voice("group", "30001", "voice.mp3",
                              b"FAKEMP3DATA", "audio/mpeg")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        seen = [p for p, _, _ in mock.seen]
        for want in ("/api/message/sharefile_full",
                     "/api/group/sharefile_full",
                     "/api/message/photo", "/api/group/sendpt",
                     "/api/message/voicemp3", "/api/group/sendmp3"):
            assert seen.count(want) == 1, (want, seen)
    finally:
        mock.stop()


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
        # (khong co lich su cu qua HTTPS) + thong bao gioi han.
        status, body = api_json("POST", "/api/thread/20001/send",
                                {"type": "user", "message": "Chao ban"})
        assert status == 200 and body["ok"] is True, body
        status, body = api("GET", "/api/thread/20001/history?type=user")
        assert [m["text"] for m in body["messages"]] == ["Chao ban"], body
        assert body.get("unavailable") is True, body

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
            [("file", "anh.jpg", "image/jpeg", b"FAKEJPEGDATA")])
        status, body = api("POST", "/api/thread/30001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "photo", body

        # Gui file ghi am (multipart) nhom.
        mbody, mctype = chat_mod.build_multipart(
            {"type": "group"},
            [("file", "voice.mp3", "audio/mpeg", b"FAKEMP3DATA")])
        status, body = api("POST", "/api/thread/30001/sendvoice",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "voice", body
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CHAT TESTS PASSED")
