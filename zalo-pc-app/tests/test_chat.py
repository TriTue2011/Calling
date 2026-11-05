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
        # clientId tren day la STRING (bundle sendFile ghep chuoi
        # JSON bang tay) — xem test_voice_112.py.
        assert res["data"]["clientId"] == str(res["client_id"]), res
        res = chat.send_file("group", "30001", "bao-cao.pdf",
                             b"%PDF-fake", "application/pdf")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        assert res["data"]["clientId"] == str(res["client_id"]), res
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
        res = chat.send_voice("user", "20001", "voice.mp3",
                              b"FAKEMP3DATA", "audio/mpeg")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        assert res["data"]["clientId"] == str(res["client_id"]), res
        res = chat.send_voice("group", "30001", "voice.mp3",
                              b"FAKEMP3DATA", "audio/mpeg")
        assert res["data"]["msgId"] == "msg-file-1", res
        assert isinstance(res["client_id"], int), res
        assert res["data"]["clientId"] == str(res["client_id"]), res
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
            [("file", "anh.jpg", "image/jpeg",
              b"\xff\xd8\xff\xe0FAKEJPEGDATA")])
        status, body = api("POST", "/api/thread/30001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body["message"]["kind"] == "photo", body

        # Gui file ghi am (multipart) nhom. File phai la MP3 THAT
        # (it nhat header ID3/frame sync) vi route sendvoice kiem
        # tra noi dung truoc khi gui — byte gia kieu FAKEMP3DATA
        # khong phai MP3 se bi dua di doi bang ffmpeg va loi
        # (loi 133 ngay 2026-11-05; xem test_voice_transcode.py).
        mbody, mctype = chat_mod.build_multipart(
            {"type": "group"},
            [("file", "voice.mp3", "audio/mpeg",
              b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 64)])
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
        assert not [p for p, _, _ in mock.seen if "sharefile" in p]
    finally:
        mock.stop()


def test_server_sendfile_validation():
    """Endpoint /api/thread/<id>/sendfile sau sua: file rong -> 400
    (khong goi Zalo); gif/heic gui kind=photo -> ha xuong file (200,
    sharefile_full, khong phai photo); anh that -> photo (200,
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

        def sharefile_calls():
            return [p for p, _, _ in mock.seen if "sharefile" in p]

        def photo_calls():
            return [p for p, _, _ in mock.seen
                    if p in ("/api/message/photo", "/api/group/sendpt")]

        # File rong (case live cua user: iptv-udpxy.m3u, 0 byte).
        before = len(sharefile_calls())
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "iptv-udpxy.m3u", "application/octet-stream", b"")])
        status, body = api("POST", "/api/thread/20001/sendfile",
                           mbody, {"Content-Type": mctype})
        assert status == 400, body
        assert "rong (0 byte)" in body["error"], body
        assert len(sharefile_calls()) == before, mock.seen

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
        assert len(sharefile_calls()) == before + 2, mock.seen
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CHAT TESTS PASSED")
