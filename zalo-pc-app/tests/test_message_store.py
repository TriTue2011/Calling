"""Ban ghi tin ben SQLite + lich su 1-1 tu DB (webhook missing
piece 3).

Bang chung bundle (Zalo PC 26.11.10): exe doc lich su 1-1 tu DB
SQLite local (loadTopMessagesForConversation) + API cloud
getCloudMessage — khong co endpoint HTTPS nao cho lich su 1-1.
App moi truoc day chi co Inbox RAM (mat tin khi restart). Store
nay ghi moi tin den qua sync (va tin gui di) xuong /data/messages.db
kem khi dispatch webhook; Inbox RAM giu nguyen lam cache.

Mock/offline hoan toan: khong dang nhap that, khong gui that.
Khong log noi dung tin — chi dem so luong / id thread.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import message_store as store_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402

UID = "10001"


def _msg(mid, sender, text, when, thread="20001"):
    return {"id": mid, "sender_id": sender, "text": text,
            "time": when, "kind": "text", "direction": "in",
            "thread_id": thread, "raw": {"msgId": mid}}


def test_store_record_read_round_trip():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-msgstore-test-")
    store = store_mod.MessageStore(os.path.join(tmp, "messages.db"))
    assert store.record("user", "20001",
                        _msg("m1", "20001", "Chao", 100)) is True
    assert store.record("user", "20001",
                        _msg("m2", "20001", "Sao roi", 200)) is True
    assert store.count("user", "20001") == 2, store.count()
    msgs = store.messages_for("user", "20001", 50)
    assert [m["id"] for m in msgs] == ["m2", "m1"], msgs
    assert msgs[0]["text"] == "Sao roi", msgs
    assert msgs[0]["sender_id"] == "20001", msgs
    assert store.messages_for("user", "99999") == []
    assert store.messages_for("user", "20001", 1)[0]["id"] == "m2"


def test_store_dedup_same_key():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-msgstore-test-")
    store = store_mod.MessageStore(os.path.join(tmp, "messages.db"))
    msg = _msg("m1", "20001", "Chao", 100)
    assert store.record("user", "20001", msg) is True
    assert store.record("user", "20001", dict(msg)) is False
    assert store.count("user", "20001") == 1
    # Cung msgId nhung nguoi gui khac = tin khac (khoa co sender).
    assert store.record("user", "20001",
                        _msg("m1", "20002", "Chao", 100)) is True
    assert store.count("user", "20001") == 2


def test_store_prune_cap_per_thread():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-msgstore-test-")
    store = store_mod.MessageStore(os.path.join(tmp, "messages.db"),
                                   max_per_thread=3)
    for i in range(5):
        assert store.record("user", "20001", _msg(
            "m%d" % i, "20001", "Tin %d" % i, 100 + i)) is True
    msgs = store.messages_for("user", "20001", 50)
    assert [m["id"] for m in msgs] == ["m4", "m3", "m2"], msgs


def test_store_restart_persists():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-msgstore-test-")
    path = os.path.join(tmp, "messages.db")
    store = store_mod.MessageStore(path)
    store.record("user", "20001", _msg("m1", "20001", "Chao", 100))
    store.record("group", "30001", _msg("g1", "20002", "Nhom", 150))
    # Instance moi cung file (gia lap restart) doc lai du.
    store2 = store_mod.MessageStore(path)
    assert store2.count() == 2, store2.count()
    assert [m["id"] for m in store2.messages_for(
        "user", "20001", 50)] == ["m1"]
    assert [m["id"] for m in store2.messages_for(
        "group", "30001", 50)] == ["g1"]


def test_store_account_switch_clears():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-msgstore-test-")
    store = store_mod.MessageStore(os.path.join(tmp, "messages.db"))
    assert store.set_account("10001") is True
    store.record("user", "20001", _msg("m1", "20001", "Chao", 100))
    assert store.count() == 1
    # Cung tai khoan: khong xoa.
    assert store.set_account("10001") is True
    assert store.count() == 1
    # Tai khoan khac: xoa sach de lich su khong lan sang.
    assert store.set_account("99999") is True
    assert store.count() == 0
    # Uid rong: no-op, khong go bo dinh danh.
    store.record("user", "20001", _msg("m2", "20001", "Moi", 200))
    assert store.set_account("") is True
    assert store.count() == 1


def test_store_bad_path_never_raises():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-msgstore-test-")
    blocker = os.path.join(tmp, "file-chan-duong")
    with open(blocker, "w", encoding="utf-8") as f:
        f.write("x")
    store = store_mod.MessageStore(
        os.path.join(blocker, "messages.db"))
    assert store.record("user", "20001",
                        _msg("m1", "20001", "Chao", 100)) is False
    assert store.messages_for("user", "20001") == []
    assert store.count() == 0
    assert store.set_account("10001") is False
    assert store.clear() is False


def test_store_clear():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-msgstore-test-")
    store = store_mod.MessageStore(os.path.join(tmp, "messages.db"))
    store.record("user", "20001", _msg("m1", "20001", "Chao", 100))
    assert store.count() == 1
    assert store.clear() is True
    assert store.count() == 0
    assert store.messages_for("user", "20001") == []


# -- e2e: restart -> webhook cho tin lo + lich su 1-1 tu DB --------

BASE = ""


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, data=body)
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


class _Capture(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        _Capture.received.append(json.loads(body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def _wait_thread_events(thread_id, n, timeout=10.0):
    """Doi cho toi khi co n event message.received cua thread_id
    (mock gui ca tin nhom — khong dem lan voi tin 1-1)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = [e for e in _Capture.received
               if e.get("type") == "message.received"
               and e.get("thread_id") == thread_id]
        if len(got) >= n:
            return True
        time.sleep(0.1)
    return False


def test_restart_webhook_and_history_e2e():
    """App A nhan tin 1-1 qua sync (mock): webhook ban 1 event,
    DB ghi tin, con tro luu 100/50. Tat sync (gia lap tat app),
    mo AppState B cung data dir: con tro da luu duoc nap, poll lai
    giao tin -> webhook ban event thu 2 (tin lo duoc bu) + lich
    su 1-1 doc tu DB (khong phai tu RAM)."""
    global BASE
    mock = MockZalo().start()
    capture = None
    httpd = None
    tmp = tempfile.mkdtemp(prefix="zalo-pc-msgstore-e2e-")
    try:
        protocol.AUTH_DOMAIN = mock.base
        protocol.VOICECALL_DOMAIN = mock.base
        protocol.PROFILE_DOMAIN = mock.base
        protocol.GROUP_DOMAIN = mock.base
        chat_mod.CHAT_DOMAIN = mock.base
        chat_mod.FILES_DOMAIN = mock.base
        chat_mod.GROUP_DOMAIN = mock.base
        _Capture.received = []
        capture = ThreadingHTTPServer(("127.0.0.1", 0), _Capture)
        threading.Thread(target=capture.serve_forever,
                         daemon=True).start()
        hook_url = "http://127.0.0.1:%d/hook" % \
            capture.server_address[1]

        state_a = app_server.AppState(tmp)
        state_a.webhook_store.save(
            {"message_webhook_url": hook_url})
        app_server.STATE = state_a
        httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                    app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever,
                         daemon=True).start()

        login_via_mock()
        # Doi tin 1-1 den + webhook ban event dau.
        assert _wait_thread_events("20001", 1, timeout=10), \
            _Capture.received
        assert state_a.message_store.count("user", "20001") == 1
        # Con tro da luu xuong dia sau batch.
        with open(os.path.join(tmp, "sync_cursor.json"),
                  encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["msg"]["lastActionId"] == "100", saved
        assert saved["msg"]["lastActionIdOther"] == "50", saved
        assert saved["uid"] == UID, saved

        # Tat app (gia lap): dung sync, mo AppState moi cung dir.
        state_a.stop_sync()
        state_b = app_server.AppState(tmp)
        app_server.STATE = state_b
        assert state_b.session is not None, "phien phai con"
        assert state_b.start_sync() is True
        # Con tro khoi tao tu dia (khong phai "1,1").
        assert state_b.sync.cursor.last_action_id == "100", \
            state_b.sync.cursor.last_action_id
        assert state_b.sync.cursor.last_action_id_other == "50"
        # Poll lai giao tin lo -> webhook ban event thu 2.
        assert _wait_thread_events("20001", 2, timeout=10), \
            _Capture.received
        # DB chi co 1 tin (dedup), lich su 1-1 doc tu DB.
        assert state_b.message_store.count("user", "20001") == 1
        status, body = api("GET",
                           "/api/thread/20001/history?type=user")
        assert status == 200, body
        assert [m["text"] for m in body["messages"]] == \
            ["Chao ban, toi la BenBap"], body
        assert body.get("unavailable") is False, body
        assert body.get("source") == "db+inbox", body
        assert "chi co tu khi app bat dau luu" in body.get(
            "notice", ""), body
        state_b.stop_sync()
    finally:
        if capture is not None:
            try:
                capture.shutdown()
            except Exception:
                pass
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL MESSAGE STORE TESTS PASSED")
