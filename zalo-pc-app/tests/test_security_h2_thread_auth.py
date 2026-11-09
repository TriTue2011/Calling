"""H2: POST /api/thread/* phai qua dang nhap app (server.py).

Loi: do_POST re nhanh /api/thread/* toi _handle_thread_post TRUOC
cong dang nhap app (muc /api/* o cuoi do_POST); _handle_thread_post
chi kiem phien Zalo (_require_login) nen ai toi duoc cong HTTP la
gui tin/file/ghi am thay tai khoan Zalo ma khong can mat khau app.
Truoc khi sua, POST khong cookie app tra {"error": "chua_dang_nhap"}
(cong Zalo); sau khi sua phai tra {"error": "chua_dang_nhap_app"}
(cong app) giong moi /api/* khac.

Test chay offline qua mock server (khong dang nhap that, khong gui
tin that). Mat khau duoi day la gia tri test gia, chi dung trong
test nay.
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer

TEST_USER = "nguoi-dung-test"
TEST_PASSWORD = "mat-khau-test-123"

tmp = tempfile.mkdtemp(prefix="zalo-pc-h2-test-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_APP_USER"] = TEST_USER
os.environ["ZALO_PC_APP_PASSWORD"] = TEST_PASSWORD
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    chat_mod.CHAT_DOMAIN = mock.base
    chat_mod.FILES_DOMAIN = mock.base
    chat_mod.GROUP_DOMAIN = mock.base


class Client:
    def __init__(self, port):
        self.port = port
        self.cookie = ""

    def req(self, method, path, body=None, content_type="application/json"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        headers = {}
        if body is not None:
            headers["Content-Type"] = content_type
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request(method, path, body, headers)
        resp = conn.getresponse()
        raw = resp.read()
        set_cookie = resp.getheader("Set-Cookie") or ""
        conn.close()
        try:
            parsed = json.loads(raw.decode())
        except Exception:
            parsed = None
        return resp.status, set_cookie, parsed

    def json(self, method, path, obj=None):
        data = json.dumps(obj).encode() if obj is not None else None
        return self.req(method, path, data)

    def login_app(self):
        status, set_cookie, body = self.json(
            "POST", "/api/app/login",
            {"username": TEST_USER, "password": TEST_PASSWORD})
        assert status == 200 and body.get("ok") is True, body
        assert set_cookie, "login app khong tra Set-Cookie"
        self.cookie = set_cookie.split(";", 1)[0]


def start_server(mock, data_dir):
    patch_domains(mock)
    state = app_server.AppState(data_dir)
    assert state.auth is not None, state.auth_error
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return state, httpd, Client(port)


def login_zalo_via_mock(client):
    """QR flow qua mock (mau test_chat.login_via_mock) — can cookie
    app vi /api/qr/* nam sau cong dang nhap app."""
    from mock_server import TEST_PARAM_KEY as _KEY
    app_server.PARAM_CIPHER_KEY = _KEY
    status, _sc, body = client.json("POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, _sc, last = client.json("GET", "/api/qr/status")
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def thread_posts_json():
    """(path, body) cho moi duong POST JSON cua /api/thread/*."""
    return [
        ("/api/thread/20001/send",
         {"type": "user", "message": "xin chao"}),
        ("/api/thread/20001/sendlink",
         {"type": "user", "link": "https://example.invalid/a"}),
        ("/api/thread/20001/typing", {"type": "user"}),
        ("/api/thread/20001/seen",
         {"type": "user", "msg_ids": ["m1"]}),
    ]


def thread_posts_multipart():
    """(path, body, content_type) cho sendfile/sendvoice."""
    mbody, mctype = chat_mod.build_multipart(
        {"type": "user"},
        [("file", "hello.txt", "text/plain", b"hello file")])
    aac = b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\x00" * 100
    vbody, vctype = chat_mod.build_multipart(
        {"type": "user"},
        [("file", "voice.aac", "audio/aac", aac)])
    return [
        ("/api/thread/20001/sendfile", mbody, mctype),
        ("/api/thread/20001/sendvoice", vbody, vctype),
    ]


def test_thread_post_requires_app_login():
    """Khong cookie app -> moi POST /api/thread/* tra 401
    chua_dang_nhap_app (cong app), KHONG phai chua_dang_nhap
    (cong Zalo). Day la loi H2: truoc khi sua cac POST nay tra
    chua_dang_nhap vi re nhanh truoc cong app."""
    mock = MockZalo().start()
    tmpdir = tempfile.mkdtemp(prefix="zalo-pc-h2-noauth-")
    try:
        _state, httpd, c = start_server(mock, tmpdir)
        try:
            for path, body in thread_posts_json():
                status, _sc, parsed = c.json("POST", path, body)
                assert status == 401, (path, status, parsed)
                assert parsed.get("error") == "chua_dang_nhap_app", \
                    (path, parsed)
            for path, body, ctype in thread_posts_multipart():
                status, _sc, parsed = c.req("POST", path, body, ctype)
                assert status == 401, (path, status, parsed)
                assert parsed.get("error") == "chua_dang_nhap_app", \
                    (path, parsed)
            # Doi chieu: GET lich su thread (da co cong app) cung
            # bi chan y nhu vay khi chua dang nhap app.
            status, _sc, parsed = c.json(
                "GET", "/api/thread/30001/history?type=group")
            assert status == 401, (status, parsed)
            assert parsed.get("error") == "chua_dang_nhap_app", parsed
            # Khong co cuoc goi Zalo nao duoc thuc hien khi chua
            # dang nhap app (duong gui bi chan ngay o cong).
            assert mock.seen == [], mock.seen
        finally:
            httpd.shutdown()
    finally:
        mock.stop()
        _state.stop_sync()


def test_thread_post_app_login_without_zalo_session():
    """Da dang nhap app nhung chua co phien Zalo -> cong app qua,
    cong Zalo chan: 401 chua_dang_nhap (khong phai
    chua_dang_nhap_app). Chung minh thu tu cong dung: app truoc,
    Zalo sau, va sua H2 khong vo hieu hoa kiem tra phien Zalo."""
    mock = MockZalo().start()
    tmpdir = tempfile.mkdtemp(prefix="zalo-pc-h2-app-only-")
    try:
        _state, httpd, c = start_server(mock, tmpdir)
        try:
            c.login_app()
            for path, body in thread_posts_json():
                status, _sc, parsed = c.json("POST", path, body)
                assert status == 401, (path, status, parsed)
                assert parsed.get("error") == "chua_dang_nhap", \
                    (path, parsed)
            for path, body, ctype in thread_posts_multipart():
                status, _sc, parsed = c.req("POST", path, body, ctype)
                assert status == 401, (path, status, parsed)
                assert parsed.get("error") == "chua_dang_nhap", \
                    (path, parsed)
            assert mock.seen == [], mock.seen
        finally:
            httpd.shutdown()
    finally:
        mock.stop()
        _state.stop_sync()


def test_thread_post_app_login_with_zalo_session():
    """Da dang nhap app + phien Zalo song (mock QR) -> moi duong
    POST /api/thread/* di tiep binh thuong (200 ok), gui that
    xuong mock Zalo. Chung minh sua H2 khong khoa luon duong
    gui hop le."""
    mock = MockZalo().start()
    mock.poll_mode = "empty"
    tmpdir = tempfile.mkdtemp(prefix="zalo-pc-h2-ok-")
    try:
        state, httpd, c = start_server(mock, tmpdir)
        try:
            c.login_app()
            login_zalo_via_mock(c)
            # Event ctrl da den truoc (registry cua AppState) —
            # neu khong, send_file/send_voice doi het timeout
            # (xem test_chat.test_server_thread_routes).
            state.file_async.deliver(
                "file-1", "https://f1-file-dl.zdn.vn/test.docx")
            state.voice_async.deliver(
                "file-voice-1",
                "https://f1-voice-aac-dl.zdn.vn/test.amr",
                "https://f1-voice-aac-dl.zdn.vn/test.aac")

            status, _sc, body = c.json(
                "POST", "/api/thread/20001/send",
                {"type": "user", "message": "Chao ban"})
            assert status == 200 and body["ok"] is True, body
            assert body["message"]["text"] == "Chao ban", body
            status, _sc, body = c.json(
                "POST", "/api/thread/20001/sendlink",
                {"type": "user",
                 "link": "https://example.invalid/a",
                 "message": "Xem nay"})
            assert status == 200 and body["ok"] is True, body
            status, _sc, body = c.json(
                "POST", "/api/thread/20001/typing", {"type": "user"})
            assert status == 200 and body["ok"] is True, body
            status, _sc, body = c.json(
                "POST", "/api/thread/20001/seen",
                {"type": "user", "msg_ids": ["m1"]})
            assert status == 200 and body["ok"] is True, body
            for path, mbody, mctype in thread_posts_multipart():
                status, _sc, body = c.req("POST", path, mbody, mctype)
                assert status == 200 and body["ok"] is True, \
                    (path, body)
            # Tin da gui that xuong mock Zalo (khong chi tra ok
            # gia o route).
            seen = [p for p, _, _ in mock.seen]
            for want in ("/api/message/sms", "/api/message/link",
                         "/api/message/typing", "/api/message/seen",
                         "/api/message/asyncfile/upload",
                         "/api/message/voice/upload"):
                assert seen.count(want) == 1, (want, seen)
        finally:
            httpd.shutdown()
    finally:
        mock.stop()
        # Dung poller sync/ctrl (xem test_chat — tranh abort 134
        # luc shutdown).
        state.stop_sync()


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001 - report, keep running
            failed += 1
            print("FAIL %s: %r" % (t.__name__, exc))
        else:
            print("PASS %s" % t.__name__)
    print("%d/%d tests passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
