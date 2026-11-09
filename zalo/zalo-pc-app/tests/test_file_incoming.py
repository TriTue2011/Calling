"""Tin file den: nhan + tai ve + gui lai giu nguyen ten file.

Bang chung dang tin (bundle Zalo PC 26.11.10,
compact-app-pc.5c0110a3a8749b3aacde.js — doc truc tiep, khong doan):
  - Tin file den co msgType (chuoi) "share.file" -> MSG_FILE (ham
    _normalizeMessageType + bang map MSG_TYPE; zca-js 2.1.2
    getClientMessageType khop: "share.file" -> 46).
  - content cua tin file: {title, description, childnumber, action,
    params (JSON string), type, href}. Trong _normalizeMessageJSON
    (case MSG_FILE): title la ten file; neu title chua ket thuc
    bang "." + params.fileExt thi client NOI them duoi ("bao-cao"
    + ".pdf"); params JSON chua {fileSize, checksum, fileExt,
    fType} (fType 1 = file, 2 = folder — code download cua bundle
    xay lai message voi params JSON {fileSize, checksum, fileExt,
    fType} khi xu ly folder).
  - URL tai file = content.href (menu chuot phai cua bundle chi
    hien nut Download khi message.href co gia tri va msgType la
    MSG_FILE; ten file hien thi = message.title — ham getFileName
    cua download service tra message.title).
  - Kich thuoc = params.fileSize (mediaInfo.mediaSize o cloud
    item cung la gia tri nay); checksum md5 = params.checksum
    (download service doi chieu checksum khi kiem tra file da
    tai ve o dia).

App hien tai (head 1043836) CHUA xu ly gi ca: normalize_message
chi nhan kind="file" khi msgType nam trong ("file", "sharefile")
— dang that "share.file" khong khop — va khong doc content.title/
href/params, nen tin file den hien dang text (ten file) hoac bong
bong trong (anh den: content khong co msg/title), khong co URL
tai, khong tai ve, khong gui lai duoc.

Test o day (mock, khong dang nhap that, khong goi Zalo that):
  - normalize: dang that cua bundle -> kind/file_name/file_url/
    file_size/checksum dung; noi duoi file theo luat bundle; thieu
    href / params hong -> khong crash.
  - FileInbox: tai ve dung ten goc + dung noi dung; trung ten
    khong ghi de; ten chua duong dan bi chan; qua lon -> loi ro;
    thieu URL -> loi ro; checksum sai -> loi ro, khong giu file
    hong.
  - Route server: GET /api/file/download tra dung bytes + ten goc;
    POST /api/file/forward gui lai qua duong sendFileByChunkV2
    da co, ten file o buoc 2 la ten goc.
"""

import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import file_inbox as file_inbox_mod  # noqa: E402
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


def file_item(**over):
    """Tin file den dang that (bundle): msgType "share.file",
    content {title, params JSON, href}."""
    item = {
        "msgId": "f1", "cliMsgId": "c1",
        "uidFrom": "20001", "idTo": "10001",
        "msgType": "share.file", "ts": 1762345700,
        "dName": "BenBap",
        "content": {
            "title": "bao-cao",
            "description": "", "childnumber": 0, "action": "",
            "type": "",
            "params": json.dumps({
                "fileSize": 11, "checksum": hashlib.md5(b"hello world").hexdigest(),
                "fileExt": "pdf", "fType": 1}),
            "href": "https://files.example/f/abc123"},
    }
    item.update(over)
    return item


# -- normalize_message ---------------------------------------------------

def test_normalize_incoming_file_bundle_shape():
    m = chat_mod.normalize_message(file_item(), "user")
    assert m["kind"] == "file", m
    # Bundle noi duoi file: title "bao-cao" + fileExt "pdf".
    assert m["file_name"] == "bao-cao.pdf", m
    assert m["file_url"] == "https://files.example/f/abc123", m
    assert m["file_size"] == 11, m
    assert m["file_checksum"] == hashlib.md5(b"hello world").hexdigest(), m
    assert m["file_ext"] == "pdf", m
    assert m["f_type"] == 1, m
    assert m["text"] == "bao-cao.pdf", m


def test_normalize_incoming_file_title_has_ext_already():
    item = file_item()
    item["content"]["title"] = "bao-cao.pdf"
    m = chat_mod.normalize_message(item, "user")
    assert m["file_name"] == "bao-cao.pdf", m  # khong noi trung ".pdf"


def test_normalize_incoming_photo_bundle_shape():
    item = {"msgId": "p1", "uidFrom": "20001", "idTo": "10001",
            "msgType": "chat.photo", "ts": 1762345700,
            "content": {"title": "", "href": "https://files.example/p/1",
                        "thumb": "https://files.example/p/1t",
                        "params": json.dumps({"convertible": 0})}}
    m = chat_mod.normalize_message(item, "user")
    assert m["kind"] == "photo", m
    assert m["file_url"] == "https://files.example/p/1", m


def test_normalize_incoming_voice_bundle_shape():
    item = {"msgId": "v1", "uidFrom": "20001", "idTo": "10001",
            "msgType": "chat.voice", "ts": 1762345700,
            "content": {"title": "ghi-am", "href": "https://files.example/v/1",
                        "params": json.dumps({})}}
    m = chat_mod.normalize_message(item, "user")
    assert m["kind"] == "voice", m
    assert m["file_url"] == "https://files.example/v/1", m


def test_normalize_incoming_file_no_href():
    item = file_item()
    del item["content"]["href"]
    m = chat_mod.normalize_message(item, "user")
    assert m["kind"] == "file", m
    assert m["file_url"] in (None, ""), m
    assert m["file_name"] == "bao-cao.pdf", m


def test_normalize_incoming_file_bad_params():
    item = file_item()
    item["content"]["params"] = "{khong-phai-json"
    m = chat_mod.normalize_message(item, "user")
    assert m["kind"] == "file", m
    assert m["file_size"] is None, m
    assert m["file_name"] == "bao-cao", m  # khong noi duoi khi params hong


def test_normalize_text_unchanged():
    item = {"msgId": "t1", "uidFrom": "20001", "idTo": "10001",
            "content": "Xin chao", "ts": 1762345700, "msgType": 0}
    m = chat_mod.normalize_message(item, "user")
    assert m["kind"] == "text", m
    assert m["text"] == "Xin chao", m


# -- sanitize / FileInbox --------------------------------------------------

def test_sanitize_filename():
    f = file_inbox_mod.sanitize_filename
    assert f("bao-cao.pdf") == "bao-cao.pdf"
    assert f("../../etc/passwd") == "passwd"
    assert f("/abs/path/file.txt") == "file.txt"
    assert f("a/b\\c.txt") == "c.txt"
    assert f("  spaced name .txt  ") == "spaced name .txt"
    assert f("") == ""
    assert f("...") == ""


def _fake_getter(data, status=200):
    def get(url, timeout=120):
        return status, data
    return get


def _inbox_msg(**over):
    m = chat_mod.normalize_message(file_item(), "user")
    m.update(over)
    return m


def test_file_inbox_download_ok():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-in-test-")
    inbox = file_inbox_mod.FileInbox(
        os.path.join(tmp, "downloads"),
        http_get_bytes=_fake_getter(b"hello world"))
    rec = inbox.download(_inbox_msg(), "user", "20001")
    assert rec["file_name"] == "bao-cao.pdf", rec
    assert rec["status"] == "downloaded", rec
    assert rec["size_bytes"] == 11, rec
    path = rec["local_path"]
    assert os.path.isfile(path), path
    assert open(path, "rb").read() == b"hello world"
    assert path.startswith(os.path.join(tmp, "downloads")), path
    # Registry ghi lai, tim lai duoc theo msg id.
    again = inbox.find("user", "20001", "f1")
    assert again is not None and again["file_name"] == "bao-cao.pdf", again
    assert again["local_path"] == path, again


def test_file_inbox_duplicate_name():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-dup-test-")
    inbox = file_inbox_mod.FileInbox(
        os.path.join(tmp, "downloads"),
        http_get_bytes=_fake_getter(b"hello world"))
    r1 = inbox.download(_inbox_msg(), "user", "20001")
    m2 = _inbox_msg()
    m2["id"] = "f2"  # tin khac, cung ten file
    r2 = inbox.download(m2, "user", "20001")
    assert r1["local_path"] != r2["local_path"], (r1, r2)
    assert os.path.basename(r2["local_path"]) == "bao-cao (1).pdf", r2
    assert open(r1["local_path"], "rb").read() == b"hello world"
    assert open(r2["local_path"], "rb").read() == b"hello world"


def test_file_inbox_traversal_name():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-trav-test-")
    inbox = file_inbox_mod.FileInbox(
        os.path.join(tmp, "downloads"),
        http_get_bytes=_fake_getter(b"hello world"))
    m = _inbox_msg()
    m["file_name"] = "../../etc/passwd"
    rec = inbox.download(m, "user", "20001")
    assert os.path.basename(rec["local_path"]) == "passwd", rec
    assert rec["local_path"].startswith(
        os.path.join(tmp, "downloads")), rec["local_path"]
    assert not os.path.exists("/tmp/etc/passwd")


def test_file_inbox_oversize():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-big-test-")
    inbox = file_inbox_mod.FileInbox(
        os.path.join(tmp, "downloads"),
        http_get_bytes=_fake_getter(b"x" * 10))
    m = _inbox_msg()
    m["file_size"] = chat_mod.MAX_FILE_BYTES + 1
    try:
        inbox.download(m, "user", "20001")
        raise AssertionError("expected FileDownloadError on oversize")
    except file_inbox_mod.FileDownloadError as e:
        assert "qua lon" in str(e), str(e)
    assert inbox.find("user", "20001", "f1") is None


def test_file_inbox_missing_url():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-nourl-test-")
    inbox = file_inbox_mod.FileInbox(
        os.path.join(tmp, "downloads"),
        http_get_bytes=_fake_getter(b"hello world"))
    m = _inbox_msg()
    m["file_url"] = None
    try:
        inbox.download(m, "user", "20001")
        raise AssertionError("expected FileDownloadError on missing url")
    except file_inbox_mod.FileDownloadError as e:
        assert "khong co" in str(e).lower() or "URL" in str(e), str(e)


def test_file_inbox_checksum_mismatch():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-sum-test-")
    inbox = file_inbox_mod.FileInbox(
        os.path.join(tmp, "downloads"),
        http_get_bytes=_fake_getter(b"hello worle"))  # 11 byte, sai md5
    try:
        inbox.download(_inbox_msg(), "user", "20001")
        raise AssertionError("expected FileDownloadError on checksum")
    except file_inbox_mod.FileDownloadError as e:
        assert "checksum" in str(e).lower(), str(e)
    # File hong bi xoa, khong giu lai de gui di.
    assert inbox.find("user", "20001", "f1") is None


def test_file_inbox_download_async():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-async-test-")
    inbox = file_inbox_mod.FileInbox(
        os.path.join(tmp, "downloads"),
        http_get_bytes=_fake_getter(b"hello world"))
    inbox.download_async(_inbox_msg(), "user", "20001")
    deadline = time.time() + 5
    rec = None
    while time.time() < deadline:
        rec = inbox.find("user", "20001", "f1")
        if rec is not None:
            break
        time.sleep(0.05)
    assert rec is not None and rec["status"] == "downloaded", rec


# -- server routes ---------------------------------------------------------

BASE = ""


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype:
                return resp.status, json.loads(raw.decode()), dict(resp.headers)
            return resp.status, raw, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode()), dict(e.headers)
        except ValueError:
            return e.code, raw, dict(e.headers)


def api_json(method, path, obj=None):
    data = json.dumps(obj).encode() if obj is not None else None
    status, body, _ = api(method, path, data,
                          {"Content-Type": "application/json"})
    return status, body


def login_via_mock():
    from mock_server import TEST_PARAM_KEY
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    status, body = api_json("POST", "/api/qr/new", {})
    assert body["ok"] is True
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = api("GET", "/api/qr/status")[0:2]
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def _serve(tmp):
    global BASE
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    BASE = "http://127.0.0.1:%d" % port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return state, httpd


def test_server_file_download_route():
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-dl-test-")
    try:
        patch_domains(mock)
        state, httpd = _serve(tmp)
        try:
            login_via_mock()
            # Gia lap file da tai ve (qua FileInbox that, getter gia).
            state.file_inbox._http_get_bytes = _fake_getter(b"hello world")
            rec = state.file_inbox.download(_inbox_msg(), "user", "20001")
            assert rec["status"] == "downloaded", rec
            status, body, headers = api(
                "GET", "/api/file/download?thread_type=user"
                "&thread_id=20001&msg_id=f1")
            assert status == 200, (status, body)
            assert body == b"hello world", body
            disp = headers.get("Content-Disposition", "")
            assert "bao-cao.pdf" in disp, disp
            # Chua tai ve -> 404 ro rang, khong crash.
            status, body, _ = api(
                "GET", "/api/file/download?thread_type=user"
                "&thread_id=20001&msg_id=khong-co")
            assert status == 404, (status, body)
            # List file cua thread.
            status, body = api_json(
                "GET", "/api/file/list?thread_type=user&thread_id=20001")
            assert status == 200, body
            assert len(body["files"]) == 1, body
            assert body["files"][0]["file_name"] == "bao-cao.pdf", body
            httpd.shutdown()
        finally:
            try:
                state.stop_sync()
            except Exception:
                pass
    finally:
        mock.stop()


def test_server_file_forward_route_keeps_original_name():
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-fw-test-")
    try:
        patch_domains(mock)
        state, httpd = _serve(tmp)
        try:
            login_via_mock()
            state.file_inbox._http_get_bytes = _fake_getter(b"hello world")
            rec = state.file_inbox.download(_inbox_msg(), "user", "20001")
            assert rec["status"] == "downloaded", rec
            # file_done cho buoc 1.5 cua send_file (mock tra fileId
            # "file-1" o chunk cuoi — xem test_chat.py).
            state.file_async.deliver(
                "file-1", "https://f1-file-dl.zdn.vn/bao-cao.pdf")
            status, body = api_json("POST", "/api/file/forward", {
                "thread_type": "user", "thread_id": "20001",
                "msg_id": "f1",
                "to_thread_type": "user", "to_thread_id": "20002"})
            assert status == 200, body
            assert body.get("ok") is True, body
            assert body.get("file_name") == "bao-cao.pdf", body
            # Ten file o buoc 2 (asyncfile/msg) phai la ten goc.
            assert mock.file_send_calls == 1, mock.file_send_calls
            sent = mock.file_send_bodies[0]["body"]
            assert sent["fileName"] == "bao-cao.pdf", sent
            assert sent["totalSize"] == 11, sent
            httpd.shutdown()
        finally:
            try:
                state.stop_sync()
            except Exception:
                pass
    finally:
        mock.stop()


def test_on_sync_message_autodownloads_file():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-file-auto-test-")
    state = app_server.AppState(tmp)
    state.file_inbox._http_get_bytes = _fake_getter(b"hello world")
    state.session = {"uid": "10001"}
    msg = _inbox_msg()
    msg["direction"] = "in"
    msg["is_self"] = False
    state._on_sync_message("user", "20001", msg)
    deadline = time.time() + 5
    rec = None
    while time.time() < deadline:
        rec = state.file_inbox.find("user", "20001", "f1")
        if rec is not None:
            break
        time.sleep(0.05)
    assert rec is not None and rec["status"] == "downloaded", rec
    assert os.path.isfile(rec["local_path"]), rec
    assert open(rec["local_path"], "rb").read() == b"hello world"
    # Tin text khong kich hoat tai ve.
    state._on_sync_message("user", "20001", {
        "id": "t9", "sender_id": "20001", "text": "Xin chao",
        "time": 100, "kind": "text", "direction": "in",
        "is_self": False, "raw": {}})
    time.sleep(0.3)
    assert state.file_inbox.find("user", "20001", "t9") is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL FILE-INCOMING TESTS PASSED")
