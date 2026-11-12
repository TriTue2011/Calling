"""Gom nhom anh (07/11/2026, case live ban bea4f0a): user chon 3 anh
gui mot luc cho Dai ca — 3 anh toi ben kia nhung moi anh mot tin
rieng, moi tin kem ten file duoi anh, khong gom thanh mot nhom nhu
Zalo that. NGUYEN NHAN (bundle PC that 26.11.10):
- Moi anh van la 1 message rieng tren wire (ket luan vong 30d594b
  dung), nhung client that gan chung mot photoBundle vao params
  tung anh (11152/11164): {groupLayoutId, totalItemInGroup,
  isGroupLayout, idInGroup} — ben nhan gom cac message cung
  group_layout_id thanh album MSG_PHOTO_GROUP. App minh khong gui
  field nhom nao nen ben nhan khong gom duoc.
- desc: client that gui desc = title || "" — anh khong caption co
  desc rong. App minh gui desc = ten file nen ben nhan hien ten
  file nhu caption duoi moi anh.
- "Da gui anh: <ten file>" trong chat cua app minh chi la hien thi
  cuc bo (local_message text=filename), khong phai tin chu gui kem.
Sau sua: batch >1 anh khong-gif kem bundle chung (1 groupLayoutId,
idInGroup 0-based); anh don khong kem field nhom; desc = "" khi
khong caption; anh vua gui hien dang hinh o chat minh (localUrl —
phan nay test o test_app_js_attach.js).
Run: python3 tests/test_photo_group.py
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

JPEG = b"\xff\xd8\xff\xe0FAKEJPEGDATA"
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 20

BUNDLE = {"groupLayoutId": "1762345600000", "totalItemInGroup": 3,
          "isGroupLayout": 1, "idInGroup": 1}


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


def last_photo_body(mock):
    """Body params (da giai ma AES) cua lan gui anh gan nhat."""
    bodies = [b["body"] for b in mock.upload_bodies
              if b["path"] in ("/api/message/photo",
                               "/api/group/sendpt")]
    assert bodies, mock.upload_bodies
    return bodies[-1]


def test_send_photo_bundle_fields():
    """Anh trong batch kem du 4 field nhom (camelCase nhu client
    that) + desc rong; ca 1-1 (11152) lan nhom (11164)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_photo("user", "20001", "a.jpg", JPEG,
                              "image/jpeg", 800, 600,
                              photo_bundle=dict(BUNDLE))
        assert res["data"]["msgId"] == "msg-file-1", res
        body = last_photo_body(mock)
        assert body["groupLayoutId"] == "1762345600000", body
        assert body["totalItemInGroup"] == 3, body
        assert body["isGroupLayout"] == 1, body
        assert body["idInGroup"] == 1, body
        assert body["desc"] == "", body
        assert body["toid"] == "20001", body
        res = chat.send_photo("group", "30001", "b.png", PNG,
                              "image/png", 800, 600,
                              photo_bundle=dict(BUNDLE, idInGroup=2))
        assert res["data"]["msgId"] == "msg-file-1", res
        body = last_photo_body(mock)
        assert body["groupLayoutId"] == "1762345600000", body
        assert body["idInGroup"] == 2, body
        assert body["grid"] == "30001", body
    finally:
        mock.stop()


def test_send_photo_single_no_bundle_no_desc():
    """Anh don: khong kem field nhom nao, desc rong (khong gui
    ten file lam caption)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        res = chat.send_photo("user", "20001", "anh.jpg", JPEG,
                              "image/jpeg", 800, 600)
        assert res["data"]["msgId"] == "msg-file-1", res
        body = last_photo_body(mock)
        for key in ("groupLayoutId", "totalItemInGroup",
                    "isGroupLayout", "idInGroup"):
            assert key not in body, body
        assert body["desc"] == "", body
    finally:
        mock.stop()


def test_send_photo_bundle_invalid():
    """Bundle sai -> ValueError, khong goi Zalo (khong gui khong
    bundle de roi anh roi rac)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        chat = make_chat(mock)
        bad = [
            dict(BUNDLE, totalItemInGroup=1),   # anh don khong gom
            dict(BUNDLE, idInGroup=3),          # id >= total
            dict(BUNDLE, idInGroup=-1),
            dict(BUNDLE, isGroupLayout=0),
            dict(BUNDLE, groupLayoutId=""),
            {k: v for k, v in BUNDLE.items()
             if k != "idInGroup"},               # thieu field
            "khong-phai-dict",
        ]
        for bundle in bad:
            before = len(mock.seen)
            try:
                chat.send_photo("user", "20001", "a.jpg", JPEG,
                                "image/jpeg", 800, 600,
                                photo_bundle=bundle)
            except ValueError:
                pass
            else:
                raise AssertionError(
                    "expected ValueError for bundle=%r" % (bundle,))
            assert len(mock.seen) == before, (bundle, mock.seen)
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


def _start_app(mock, tmp):
    global BASE
    patch_domains(mock)
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    BASE = "http://127.0.0.1:%d" % port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    login_via_mock()
    return httpd, state


def _stop_app(httpd, state, mock):
    """Dung sach truoc khi process thoat: poller sync/ctrl la
    daemon thread in log ra stdout ([sync-poll]/[ctrl-poll]) —
    neu process thoat trong luc chung dang in thi interpreter
    chet voi 'Fatal Python error: _enter_buffered_busy ... at
    interpreter shutdown' (gap o full run 07/11, test da in
    ALL PASSED nhung exit code van != 0). stop_sync() set _stop
    (danh thuc ca giac retry _stop.wait) roi join thread poller
    (timeout 2s) — du vi request toi mock tra ngay o poll_mode
    empty. Goi truoc mock.stop() de join khong phai doi request
    long-poll that."""
    httpd.shutdown()
    state.stop_sync()
    mock.stop()


def test_server_sendfile_forwards_bundle():
    """Route /sendfile chuyen du 4 field nhom xuong send_photo
    (vao params AES); anh khong kem field thi khong co field nhom."""
    global BASE
    mock = MockZalo().start()
    mock.poll_mode = "empty"
    tmp = tempfile.mkdtemp(prefix="zalo-pc-photo-group-")
    try:
        httpd, state = _start_app(mock, tmp)
        try:
            fields = {"type": "user", "kind": "photo", "width": "800",
                      "height": "600", "groupLayoutId": "1762345600000",
                      "totalItemInGroup": "3", "isGroupLayout": "1",
                      "idInGroup": "0"}
            mbody, mctype = chat_mod.build_multipart(
                fields, [("file", "a.jpg", "image/jpeg", JPEG)])
            status, body = api("POST", "/api/thread/20001/sendfile",
                               mbody, {"Content-Type": mctype})
            assert status == 200 and body["ok"] is True, (status, body)
            assert body["message"]["kind"] == "photo", body
            wire = last_photo_body(mock)
            assert wire["groupLayoutId"] == "1762345600000", wire
            assert wire["totalItemInGroup"] == 3, wire
            assert wire["isGroupLayout"] == 1, wire
            assert wire["idInGroup"] == 0, wire
            assert wire["desc"] == "", wire
            # Anh don (khong field nhom) -> khong co field nhom.
            mbody, mctype = chat_mod.build_multipart(
                {"type": "user", "kind": "photo", "width": "800",
                 "height": "600"},
                [("file", "anh.jpg", "image/jpeg", JPEG)])
            status, body = api("POST", "/api/thread/20001/sendfile",
                               mbody, {"Content-Type": mctype})
            assert status == 200 and body["ok"] is True, (status, body)
            wire = last_photo_body(mock)
            for key in ("groupLayoutId", "totalItemInGroup",
                        "isGroupLayout", "idInGroup"):
                assert key not in wire, wire
            assert wire["desc"] == "", wire
        finally:
            _stop_app(httpd, state, mock)
    finally:
        mock.stop()


def test_server_sendfile_forwards_caption():
    """Anh don kem `desc`: chu thich di vao params AES cua Zalo va hien o tin cuc bo; khong co desc thi desc rong (nhu cu)."""
    mock = MockZalo().start()
    mock.poll_mode = "empty"
    tmp = tempfile.mkdtemp(prefix="zalo-pc-photo-caption-")
    try:
        httpd, state = _start_app(mock, tmp)
        try:
            mbody, mctype = chat_mod.build_multipart(
                {"type": "user", "kind": "photo", "width": "800", "height": "600", "desc": "  Ghi chú cho ảnh  "},
                [("file", "anh.jpg", "image/jpeg", JPEG)])
            status, body = api("POST", "/api/thread/20001/sendfile", mbody, {"Content-Type": mctype})
            assert status == 200 and body["ok"] is True, (status, body)
            assert last_photo_body(mock)["desc"] == "Ghi chú cho ảnh", last_photo_body(mock)
            assert body["message"]["text"] == "Ghi chú cho ảnh" and body["message"]["file_name"] == "anh.jpg", body["message"]
            mbody, mctype = chat_mod.build_multipart(
                {"type": "user", "kind": "photo", "width": "800", "height": "600"},
                [("file", "anh2.jpg", "image/jpeg", JPEG)])
            status, body = api("POST", "/api/thread/20001/sendfile", mbody, {"Content-Type": mctype})
            assert status == 200 and last_photo_body(mock)["desc"] == "", (status, last_photo_body(mock))
            assert body["message"]["text"] == "anh2.jpg", body["message"]
        finally:
            _stop_app(httpd, state, mock)
    finally:
        mock.stop()


def test_server_sendfile_partial_bundle_400():
    """Chi gui mot vai field nhom -> 400 ro, khong goi Zalo
    (khong gui khong bundle)."""
    global BASE
    mock = MockZalo().start()
    mock.poll_mode = "empty"
    tmp = tempfile.mkdtemp(prefix="zalo-pc-photo-group-")
    try:
        httpd, state = _start_app(mock, tmp)
        try:
            before = len([p for p, _, _ in mock.seen
                          if p in ("/api/message/photo",
                                   "/api/group/sendpt")])
            fields = {"type": "user", "kind": "photo", "width": "800",
                      "height": "600",
                      "groupLayoutId": "1762345600000",
                      "totalItemInGroup": "3"}  # thieu 2 field
            mbody, mctype = chat_mod.build_multipart(
                fields, [("file", "a.jpg", "image/jpeg", JPEG)])
            status, body = api("POST", "/api/thread/20001/sendfile",
                               mbody, {"Content-Type": mctype})
            assert status == 400, (status, body)
            assert "nhom anh" in body["error"], body
            after = len([p for p, _, _ in mock.seen
                         if p in ("/api/message/photo",
                                  "/api/group/sendpt")])
            assert after == before, mock.seen
        finally:
            _stop_app(httpd, state, mock)
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL PHOTO GROUP TESTS PASSED")
