"""Tin tệp/ảnh/video do CHÍNH TA gửi (HA, WebUI) phải có bản sao trong kho tải về để WebUI hiện xem trước + nút tải (14/11/2026: tin gửi từ HA chỉ hiện «Tệp đính kèm» trống).
Run: python3 tests/test_sent_file_copy.py"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mock_server import MockZalo, TEST_PARAM_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import file_inbox as fi  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"FAKEJPEG" * 20


def test_save_local_writes_file_and_registry_and_rejects_bad_input():
    d = tempfile.mkdtemp(prefix="zalo-save-local-")
    box = fi.FileInbox(d)
    rec = box.save_local("user", "20001", "m1", "../../anh x.jpg", JPEG)
    assert rec["status"] == "downloaded" and rec["size_bytes"] == len(JPEG) and os.path.isfile(rec["local_path"])
    assert os.path.dirname(os.path.realpath(rec["local_path"])).startswith(os.path.realpath(d)), rec["local_path"]   # tên bị làm sạch, không thoát thư mục
    assert box.find("user", "20001", "m1")["file_name"] == rec["file_name"]
    assert box.list_for_thread("user", "20001")[0]["msg_id"] == "m1"
    _, data = box.read_local("user", "20001", "m1")
    assert data == JPEG
    for bad in (dict(msg_id="", data=JPEG), dict(msg_id="m2", data=b"")):
        try:
            box.save_local("user", "20001", bad["msg_id"], "a.jpg", bad["data"])
            raise AssertionError("phải lỗi")
        except fi.FileDownloadError:
            pass
    small = fi.FileInbox(d, max_bytes=10)
    try:
        small.save_local("user", "20001", "m3", "a.jpg", JPEG)
        raise AssertionError("phải lỗi quá cỡ")
    except fi.FileDownloadError:
        pass


BASE = ""


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_sendfile_route_keeps_a_copy_the_webui_can_list_and_download():
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-sent-copy-")
    try:
        for mod, names in ((protocol, ("AUTH_DOMAIN", "VOICECALL_DOMAIN", "PROFILE_DOMAIN", "GROUP_DOMAIN")), (chat_mod, ("CHAT_DOMAIN", "FILES_DOMAIN", "GROUP_DOMAIN"))):
            for n in names:
                setattr(mod, n, mock.base)
        app_server.STATE = app_server.AppState(tmp)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
        api("POST", "/api/qr/new", json.dumps({}).encode(), {"Content-Type": "application/json"})
        deadline, last = time.time() + 20, {}
        while time.time() < deadline:
            _, raw = api("GET", "/api/qr/status")
            last = json.loads(raw)
            if last.get("state") == "done":
                break
            time.sleep(0.5)
        assert last.get("state") == "done", last
        mb, ct = chat_mod.build_multipart({"type": "user", "kind": "photo", "width": "40", "height": "30"}, [("file", "go2rtc_cua_gui1.jpg", "image/jpeg", JPEG)])
        st, raw = api("POST", "/api/thread/20001/sendfile", mb, {"Content-Type": ct})
        body = json.loads(raw)
        assert st == 200 and body["ok"], (st, body)
        mid = str(body["message"]["id"])
        st, raw = api("GET", "/api/file/list?thread_type=user&thread_id=20001")
        files = json.loads(raw)["files"]
        rec = next((f for f in files if str(f["msg_id"]) == mid), None)
        assert rec and rec["status"] == "downloaded", files
        st, raw = api("GET", "/api/file/download?thread_type=user&thread_id=20001&msg_id=" + mid)
        assert st == 200 and raw == JPEG, (st, raw[:30])
        httpd.shutdown()
    finally:
        mock.stop()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, e)
    print("ALL SENT FILE COPY TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
