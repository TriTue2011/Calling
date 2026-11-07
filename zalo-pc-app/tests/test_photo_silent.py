"""Gui anh cam (07/11/2026, ban 690edbc): Zalo tra 200/error_code=0
nhung data rong (None / {}) -> send_photo tra ve khong loi, route
/sendfile tra 200 ok:true + message local "sent" — UI hien anh nhu
da gui trong khi ben kia khong nhan duoc (thanh cong gia). Sau sua:
send_photo phai nem ZaloChatError "khong co ma tin", route phai tra
502 co error that, khong ghi tin local. Duong thanh cong (data co
msgId) van xanh.

Run: python3 tests/test_photo_silent.py
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
from zalo_pc_app.chat import ZaloChatError  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0FAKEJPEGDATA"


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    chat_mod.CHAT_DOMAIN = mock.base
    chat_mod.FILES_DOMAIN = mock.base
    chat_mod.GROUP_DOMAIN = mock.base


def make_chat(mock):
    t = app_server.make_transport("sek-test")
    return chat_mod.Chat(t, "dev-1", TEST_SESSION_KEY)


def photo_with_data(mock, payload):
    """Chi duong photo tra envelope voi data=payload (None / {} /
    msgId that). Tra ham go goc de khoi phuc."""
    orig = mock._chat_upload

    def patched(path, qs, headers, raw_body=""):
        if path in ("/api/message/photo", "/api/group/sendpt"):
            return mock._postlogin_envelope(payload)
        return orig(path, qs, headers, raw_body)

    mock._chat_upload = patched
    return orig


def test_send_photo_empty_data_raises():
    """data=None (1-1) va data={} (nhom) deu phai loi ro, khong
    duoc tra ve nhu thanh cong."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        for payload, thread_type, thread_id in (
                (None, "user", "20001"), ({}, "group", "30001")):
            orig = photo_with_data(mock, payload)
            try:
                chat.send_photo(thread_type, thread_id, "anh.jpg",
                                JPEG, "image/jpeg", 800, 600)
                raise AssertionError(
                    "expected ZaloChatError for data=%r" % (payload,))
            except ZaloChatError as e:
                assert "khong co ma tin" in str(e), str(e)
                assert "data rong" in str(e), str(e)
            finally:
                mock._chat_upload = orig
    finally:
        mock.stop()


def test_send_photo_success_still_ok():
    """Control: data co msgId -> thanh cong nhu cu."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_photo("user", "20001", "anh.jpg", JPEG,
                              "image/jpeg", 800, 600)
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
    finally:
        mock.stop()


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
    from mock_server import TEST_PARAM_KEY
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    status, body = api_json("POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = api("GET", "/api/qr/status")
        if last.get("state") == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def test_server_sendfile_empty_data_returns_502():
    """Route /sendfile khi Zalo tra data rong: 502 + error that
    ("khong co ma tin"), KHONG tra ok:true, KHONG ghi tin local
    vao lich su (tin chua gui duoc thi khong duoc hien nhu da gui)."""
    global BASE
    mock = MockZalo().start()
    mock.poll_mode = "empty"
    tmp = tempfile.mkdtemp(prefix="zalo-pc-photo-silent-")
    try:
        patch_domains(mock)
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        login_via_mock()
        orig = photo_with_data(mock, None)
        try:
            mbody, mctype = chat_mod.build_multipart(
                {"type": "user", "kind": "photo", "width": "800",
                 "height": "600"},
                [("file", "anh.jpg", "image/jpeg", JPEG)])
            status, body = api("POST", "/api/thread/20001/sendfile",
                               mbody, {"Content-Type": mctype})
            assert status == 502, (status, body)
            assert "error" in body, body
            assert "khong co ma tin" in body["error"], body
            assert "ok" not in body or body.get("ok") is not True, body
            assert "message" not in body, body
        finally:
            mock._chat_upload = orig
        # Tin loi khong duoc ghi local: lich su 1-1 van rong.
        status, body = api("GET", "/api/thread/20001/history?type=user")
        assert status == 200, body
        assert body["messages"] == [], body
        httpd.shutdown()
    finally:
        mock.stop()
        # Dung poller sync/ctrl SAU KHI mock tat: tranh abort 134
        # luc shutdown (xem ghi chu o sync_poll.run).
        state.stop_sync()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL PHOTO SILENT TESTS PASSED")
