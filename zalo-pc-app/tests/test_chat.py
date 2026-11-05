"""Chat theo thread (route /api/thread/* qua sidecar addon) doi voi
mock server + FakeAddonClient.

PIVOT 2026-11-05: duong PC truc tiep (chat.Chat.send_text/send_file/
send_photo/send_voice/send_typing/send_seen/history_group) DA XOA —
gui tin di qua zca-js sendMessage qua sidecar (send-114). Test o day
kiem chung uy quyen qua FakeAddonClient (tests/test_addon_client.py)
va route HTTP that cua server app. Khong dang nhap that, khong gui
tin that.
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
from test_addon_client import FakeAddonClient  # noqa: E402
from zalo_pc_app import addon_client as addon_client_mod  # noqa: E402
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


def test_send_text_via_addon():
    """Gui text qua FakeAddonClient: type so (0/1), khong co clientId
    tu sinh — zca-js tu sinh tu Date.now() (API-MAP §4.2)."""
    fake = FakeAddonClient()
    data = fake.send_message("20001", 0, "Xin chao")
    assert data["message"]["msgId"] == 9001, data
    data = fake.send_message("30001", 1, "Chao ca nhom")
    assert data["message"]["msgId"] == 9001, data
    name, args, kwargs = fake.calls[0]
    assert name == "send_message" and args[1] == 0, fake.calls
    assert fake.calls[1][1][1] == 1, fake.calls
    # msgId tra ve dung lam id tin local (khong co cliMsgId — API-MAP §4.2).
    assert app_server.Handler._addon_msg_id(
        {"message": {"msgId": 123}}) == "123"
    assert app_server.Handler._addon_msg_id(
        {"attachment": [{"msgId": 7}]}) == "7"
    assert app_server.Handler._addon_msg_id({}) == ""


def test_group_history_via_addon():
    fake = FakeAddonClient()
    env = fake.group_history_full("30001", 50)
    assert env["source"] == "zca-js-2.1.2", env
    assert env["groupName"] == "Nhom Test", env
    items = env["data"]["groupMsgs"]
    msgs = [chat_mod.normalize_addon_group_message(it) for it in items]
    assert [m["text"] for m in msgs] == ["Chao ca nhom", "Chao Ban A"], msgs
    assert [m["sender_id"] for m in msgs] == ["20001", "20002"], msgs
    assert [m["sender_name"] for m in msgs] == ["Ban A", "Ban B"], msgs
    assert msgs[0]["time"] == 1762345600, msgs


def test_user_history_has_no_endpoint():
    result = chat_mod.history_user_unavailable()
    assert result["unavailable"] is True
    assert result["messages"] == []
    assert result["notice"]


def test_send_file_photo_voice_via_addon():
    """sendfile/sendphoto/sendvoice qua FakeAddonClient: URL vong lap
    duoc truyen thay vi duong dan (sidecar chi download http/https)."""
    fake = FakeAddonClient()
    data = fake.send_image("20001", 0,
                           "http://127.0.0.1:9/tmp/a.jpg", message="cap")
    assert data["message"]["msgId"] == 9002, data
    data = fake.send_file("30001", 1, "http://127.0.0.1:9/tmp/f.pdf")
    assert data["message"]["msgId"] == 9004, data
    data = fake.send_voice("20001", 0, "http://127.0.0.1:9/tmp/v.aac")
    assert data["message"]["msgId"] == 9006, data
    kinds = [c[0] for c in fake.calls]
    assert kinds == ["send_image", "send_file", "send_voice"], kinds


def test_typing_and_seen_via_addon():
    fake = FakeAddonClient()
    assert fake.typing("20001") == {"status": 0}
    assert fake.seen("20001", 0, ["m1", "m2"]) == {"status": 0}
    assert fake.delivered("20001", 0, ["m1"]) == {"status": 0}
    assert [c[0] for c in fake.calls] == ["typing", "seen",
                                          "delivered"], fake.calls


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
        fake_addon = FakeAddonClient()
        state.addon = fake_addon  # uy quyen sidecar (fake) cho test nay
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

        # /api/status: truong addon tu sidecar (fake) — khong bao gio
        # lam hong status call.
        status, body = api("GET", "/api/status")
        assert status == 200, body
        assert body.get("addon", {}).get("logged_in") is True, body
        assert body.get("addon", {}).get("ok") is True, body

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

        # Dinh kem file (multipart) 1-1 + anh nhom (kind=photo).
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "hello.txt", "text/plain", b"hello file")])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "file", body
        assert body["message"]["file_name"] == "hello.txt", body
        # File stage da bi xoa sau khi gui (khong de lai trong /tmp).
        staged = os.path.join(tmp, "tmp")
        assert os.listdir(staged) == [], os.listdir(staged)
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

        # Typing + seen: goi that xuong fake sidecar, tra ok.
        status, body = api_json("POST", "/api/thread/20001/typing",
                                {"type": "user"})
        assert status == 200 and body["ok"] is True, body
        status, body = api_json("POST", "/api/thread/30001/seen",
                                {"type": "group", "msg_ids": ["m1"]})
        assert status == 200 and body["ok"] is True, body
        assert [c[0] for c in fake_addon.calls if c[0] in
                ("typing", "seen")] == ["typing", "seen"], fake_addon.calls

        # /api/addon/events (loopback): tin den duoc luu vao store +
        # hien trong lich su; family sai -> 400.
        status, body = api_json(
            "POST", "/api/addon/events?family=message",
            {"type": 1, "threadId": "30001",
             "data": {"msgId": "m9", "uidFrom": "20001",
                      "content": "Tin den", "ts": 1762345700,
                      "dName": "Ban A"}})
        assert status == 200 and body["ok"] is True, body
        assert body["family"] == "message", body
        status, body = api("GET", "/api/thread/30001/history?type=group")
        assert [m["text"] for m in body["messages"]] == \
            ["Chao ca nhom", "Chao Ban A", "Toi vua gui", "anh.jpg",
             "voice.mp3", "Tin den"], body
        status, body = api_json("POST", "/api/addon/events?family=bogus",
                                {})
        assert status == 400, body

        # Sidecar chet: gui tin tra 502 addon_unavailable (khong roi
        # ve duong PC cu — duong do da xoa).
        state.addon = FakeAddonClient(
            fail_with=addon_client_mod.AddonUnreachable("down"))
        status, body = api_json("POST", "/api/thread/20001/send",
                                {"type": "user", "message": "x"})
        assert status == 502 and str(body.get("error", "")).startswith(
            "addon_unavailable"), body
        state.addon = fake_addon

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
