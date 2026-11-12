"""Tin nhan den: sync long-poll 99100 + Inbox + merge lich su.

Mock kiem chung doc lap: con tro poll, giai ma payload dang that
(AES envelope), dinh tuyen thread 1-1/nhom, dedup, merge theo
Node.js (fresh thang, sap theo ts, cat N), route history/updates/
summary qua server app that, count 1..1000 -> 400. Khong dang
nhap that, khong nhan tin that.
"""

import base64
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
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import sync_poll as sync_mod  # noqa: E402
from zalo_pc_app import webhooks as webhooks_mod  # noqa: E402


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    chat_mod.CHAT_DOMAIN = mock.base
    chat_mod.FILES_DOMAIN = mock.base
    chat_mod.GROUP_DOMAIN = mock.base


def poll_payload():
    """Payload poll da giai ma, dang that (msgs/groupMsgs/pageMsgs
    + lastActionId/queueStatus — xem sync_poll.extract_messages)."""
    return {
        "msgs": [
            {"msgId": "pm1", "globalMsgId": "g1",
             "uidFrom": "20001", "idTo": "10001",
             "content": "Chao ban, toi la BenBap",
             "ts": 1762345700, "dName": "BenBap", "msgType": 0}],
        "groupMsgs": [
            {"msgId": "gm1", "globalMsgId": "g2",
             "uidFrom": "20002", "idTo": "30001",
             "content": {"msg": "Chao ca nhom"},
             "ts": 1762345710, "dName": "Ban B", "msgType": 0}],
        "pageMsgs": [],
        "lastActionId": "100",
        "lastActionIdOther": "50",
        "queueStatus": {}}


def test_cursor_param_initial():
    cur = sync_mod.PollCursor()
    param = cur.param()
    assert param.startswith("1,1,"), param
    # Phan base64: btoa(JSON({})) + ",1", da URL-encode.
    tail = urllib.parse.unquote(param.split(",", 2)[2])
    assert tail == base64.b64encode(b"{}").decode() + ",1", tail


def test_cursor_update_from_payload():
    cur = sync_mod.PollCursor()
    cur.update_from(poll_payload())
    assert cur.last_action_id == "100", cur.last_action_id
    assert cur.last_action_id_other == "50", cur.last_action_id_other
    assert cur.param().startswith("100,50,"), cur.param()
    # resetLastActionId: reset con tro ve id server chi dinh.
    cur.update_from({"resetLastActionId": "7"})
    assert cur.last_action_id == "7", cur.last_action_id
    assert cur.queues == {}, cur.queues


def test_extract_messages_routing():
    msgs = sync_mod.extract_messages(poll_payload(), "10001")
    assert len(msgs) == 2, msgs
    (t1, tid1, m1), (t2, tid2, m2) = msgs
    # 1-1: thread la doi phuong (uidFrom), huong vao, ten tu dName.
    assert (t1, tid1) == ("user", "20001"), (t1, tid1)
    assert m1["direction"] == "in", m1
    assert m1["text"] == "Chao ban, toi la BenBap", m1
    assert m1["sender_name"] == "BenBap", m1
    assert m1["time"] == 1762345700, m1
    # Nhom: thread la idTo, content dang dict {msg} van lay duoc.
    assert (t2, tid2) == ("group", "30001"), (t2, tid2)
    assert m2["direction"] == "in", m2
    assert m2["text"] == "Chao ca nhom", m2
    assert m2["sender_id"] == "20002", m2


def test_extract_messages_self_and_both_zero():
    data = {"msgs": [
        {"msgId": "s1", "uidFrom": "10001", "idTo": "20001",
         "content": "Toi gui tu may khac", "ts": 1762345800},
        {"msgId": "z1", "uidFrom": "0", "idTo": "0",
         "content": "?", "ts": 1762345810}],
        "groupMsgs": [], "pageMsgs": []}
    msgs = sync_mod.extract_messages(data, "10001")
    assert msgs[0][2]["direction"] == "out", msgs[0]
    assert msgs[0][1] == "20001", msgs[0]
    # Ca hai id "0": coi la tin cua minh (bundle gan idTo = uid).
    assert msgs[1][2]["direction"] == "out", msgs[1]
    assert msgs[1][2]["sender_id"] == "10001", msgs[1]


def test_extract_messages_uidfrom_zero_is_self():
    """Tin tu gui tu thiet bi khac den voi uidFrom "0" + idTo that (log that 11/11: thread "0", AI tra loi nham)."""
    data = {"msgs": [{"msgId": "e1", "uidFrom": "0", "idTo": "20001", "content": "Canh bao: cua chinh dang mo",
                      "ts": 1762345820}],
            "groupMsgs": [{"msgId": "e2", "uidFrom": "0", "idTo": "30001", "content": "Tin nhom cua minh", "ts": 1762345830}],
            "pageMsgs": []}
    msgs = sync_mod.extract_messages(data, "10001")
    (t1, tid1, m1), (t2, tid2, m2) = msgs
    assert (t1, tid1) == ("user", "20001"), msgs[0]       # thread la nguoi nhan, khong phai "0"
    assert m1["is_self"] is True and m1["direction"] == "out" and m1["sender_id"] == "10001", m1
    assert (t2, tid2) == ("group", "30001"), msgs[1]
    assert m2["is_self"] is True and m2["sender_id"] == "10001", m2
    # Nguoc lai: tin NGUOI KHAC gui cho minh (idTo "0") van la tin den cua nguoi do.
    inc = sync_mod.extract_messages({"msgs": [{"msgId": "i1", "uidFrom": "20001", "idTo": "0", "content": "Chao", "ts": 1}]},
                                    "10001")
    assert inc[0][1] == "20001" and inc[0][2]["is_self"] is False, inc


def test_normalize_poll_shape():
    item = {"msgId": "pm9", "uidFrom": "20009",
            "content": {"msg": "Xin chao", "title": "Tieu de"},
            "ts": 1762345900, "dName": "Chi Chi"}
    m = chat_mod.normalize_message(item, "user")
    assert m["text"] == "Xin chao", m
    assert m["sender_name"] == "Chi Chi", m
    assert m["time"] == 1762345900, m
    assert m["id"] == "pm9", m


def test_inbox_dedup_unread_since():
    inbox = sync_mod.Inbox()
    m1 = {"id": "pm1", "sender_id": "20001", "text": "Chao",
          "time": 100, "kind": "text", "direction": "in", "raw": {}}
    assert inbox.record("user", "20001", m1) is True
    assert inbox.record("user", "20001", dict(m1)) is False
    assert inbox.unread_for("user", "20001") == 1
    m2 = {"id": "pm2", "sender_id": "20001", "text": "Sao roi",
          "time": 200, "kind": "text", "direction": "in", "raw": {}}
    inbox.record("user", "20001", m2)
    assert inbox.unread_for("user", "20001") == 2
    assert [m["id"] for m in inbox.since("user", "20001", 150)] == ["pm2"]
    assert [m["id"] for m in inbox.since("user", "20001", 0)] == [
        "pm1", "pm2"]
    inbox.mark_read("user", "20001")
    assert inbox.unread_for("user", "20001") == 0
    assert len(inbox.messages_for("user", "20001")) == 2
    rows = inbox.summary()
    assert rows[0]["thread_id"] == "20001", rows
    assert rows[0]["last"]["text"] == "Sao roi", rows


def test_merge_messages_nodejs_semantics():
    # Cache truoc, Zalo sau: trung khoa thi ban Zalo thang; sap
    # theo time; cat N tin cuoi; dem from_cached.
    fresh = [
        {"id": "m2", "sender_id": "20002", "text": "Zalo moi",
         "time": 200, "kind": "text", "raw": {"msgId": "m2"}},
        {"id": "m3", "sender_id": "20002", "text": "Zalo 3",
         "time": 300, "kind": "text", "raw": {"msgId": "m3"}}]
    cached = [
        {"id": "m1", "sender_id": "20001", "text": "Cache 1",
         "time": 100, "kind": "text", "raw": {"msgId": "m1"}},
        {"id": "m2", "sender_id": "20002", "text": "Cache cu",
         "time": 200, "kind": "text", "raw": {"msgId": "m2"}}]
    merged, from_cached = chat_mod.merge_messages(fresh, cached, 10)
    assert [m["id"] for m in merged] == ["m1", "m2", "m3"], merged
    assert merged[1]["text"] == "Zalo moi", merged
    assert from_cached == 1, from_cached
    merged2, _ = chat_mod.merge_messages(fresh, cached, 2)
    assert [m["id"] for m in merged2] == ["m2", "m3"], merged2


def make_poller(mock, delivered, mode=None):
    if mode is not None:
        mock.poll_mode = mode
    transport = app_server.make_transport("sek-test")
    poller = sync_mod.SyncPoller(
        transport, [mock.base + "/lp-msg"], TEST_SESSION_KEY, "10001",
        on_message=lambda t, tid, m: delivered.append((t, tid, m)),
        msg_timeout=30)
    return poller


def test_poller_delivers_and_advances_cursor():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        delivered = []
        poller = make_poller(mock, delivered)
        assert poller.poll_once() == "ok"
        assert len(delivered) == 2, delivered
        assert poller.cursor.last_action_id == "100"
        assert poller.cursor.last_action_id_other == "50"
        # URL poll mang con tro + ts + common params (khong AES).
        path, qs, _ = mock.seen[-1]
        assert path == "/lp-msg/", mock.seen[-1]
        assert qs.get("params", "").startswith("1,1,"), qs
        assert qs.get("ts", "").isdigit(), qs
        assert qs.get("zpw_ver") == "695", qs
        # Poll lai tra cung tin — poller giao lai, Inbox dedup.
        inbox = sync_mod.Inbox()
        delivered.clear()
        assert poller.poll_once() == "ok"
        assert len(delivered) == 2, delivered
        assert inbox.record(*delivered[0]) is True
        assert inbox.record(*delivered[0]) is False
    finally:
        mock.stop()


def test_poller_empty_and_stop_code():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        delivered = []
        poller = make_poller(mock, delivered, mode="empty")
        assert poller.poll_once() == "empty"
        assert delivered == []
        poller2 = make_poller(mock, delivered, mode="error69")
        try:
            poller2.poll_once()
            raise AssertionError("expected KickOut on -69")
        except sync_mod.KickOut:
            pass
        assert poller2.kicked_out is True
    finally:
        mock.stop()


def test_poller_timeout_rotates_endpoint():
    def flaky(url, timeout=30):
        raise TimeoutError("local timeout")
    poller = sync_mod.SyncPoller(
        flaky, ["https://a.invalid/lp", "https://b.invalid/lp"],
        TEST_SESSION_KEY, "10001", msg_timeout=30)
    assert poller.poll_once() == "rotated"
    assert poller._idx == 1
    assert poller.poll_once() == "rotated"
    assert poller._idx == 0


def test_webhook_dispatch_on_incoming():
    # Tin den -> day webhook; tin tu gui -> khong day (quy tac
    # chong lap cua addon). Dung post_fn gia de bat payload.
    sent = []
    store = webhooks_mod.WebhookStore(
        os.path.join(tempfile.mkdtemp(), "webhooks.json"))
    store.save({"message_webhook_url": "https://hook.invalid/in",
                "message_enabled": True})
    disp = webhooks_mod.WebhookDispatcher(
        store, post_fn=lambda url, payload: sent.append(payload) or 200)
    state = app_server.AppState(tempfile.mkdtemp())
    state.webhook_dispatcher = disp
    state.session = {"uid": "10001"}
    msg_in = {"id": "pm1", "sender_id": "20001", "text": "Chao",
              "time": 100, "kind": "text", "direction": "in",
              "is_self": False, "raw": {}}
    state._on_sync_message("user", "20001", msg_in)
    # dispatch() la fire-and-forget (daemon thread): doi toi da
    # 5 giay cho payload toi post_fn gia.
    deadline = time.time() + 5
    while time.time() < deadline and len(sent) == 0:
        time.sleep(0.05)
    assert len(sent) == 1, sent
    assert sent[0]["type"] == "message.received", sent[0]
    assert sent[0]["sender_id"] == "20001", sent[0]
    assert sent[0]["content"] == "Chao", sent[0]
    msg_self = dict(msg_in, id="s1", direction="out", is_self=True)
    state._on_sync_message("user", "20001", msg_self)
    time.sleep(0.3)  # du cho thread dispatch (neu co) chay xong
    assert len(sent) == 1, sent  # tin tu gui khong day


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
    assert body["ok"] is True
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = api("GET", "/api/qr/status")
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def test_server_incoming_e2e():
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-incoming-test-")
    try:
        patch_domains(mock)
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        status, body = api("GET", "/api/thread/20001/history?type=user")
        assert status == 401, body

        login_via_mock()
        # Phien luu poll endpoints tu getLoginInfo (zpw_chts_new).
        assert state.session.get("poll_msg_urls") == \
            [mock.base + "/lp-msg"], state.session
        assert state.session.get("poll_msg_timeout") == 30
        # Kenh sync tu mo sau login; cho tin den vao Inbox (poll
        # 1 giay/vong o mock — cho toi 10 giay).
        deadline = time.time() + 10
        while time.time() < deadline:
            if state.inbox.messages_for("user", "20001"):
                break
            time.sleep(0.5)
        assert state.inbox.messages_for("user", "20001"), \
            "sync poller chua giao tin 1-1 den"
        assert state.inbox.messages_for("group", "30001"), \
            "sync poller chua giao tin nhom den"
        assert state.sync is not None, "poller chua chay"
        assert state.sync_status() == "running"

        # Summary: co unread truoc khi mo thread.
        status, body = api("GET", "/api/inbox/summary")
        assert status == 200, body
        by_id = {t["thread_id"]: t for t in body["threads"]}
        assert by_id["20001"]["unread"] == 1, by_id
        assert by_id["20001"]["last"]["text"] == \
            "Chao ban, toi la BenBap", by_id
        assert by_id["30001"]["unread"] == 1, by_id

        # Lich su 1-1: tin den hien; tin den da ghi xuong DB local
        # (message_store) nen unavailable False + bao ro lich su chi
        # tu khi app bat dau luu (DB partial, khong phai day du).
        status, body = api("GET", "/api/thread/20001/history?type=user")
        assert status == 200, body
        assert body.get("unavailable") is False, body
        assert "chỉ có từ khi app bắt đầu lưu" in body.get("notice", ""), \
            body
        assert [m["text"] for m in body["messages"]] == \
            ["Chao ban, toi la BenBap"], body
        assert body.get("source") == "db+inbox", body
        assert body.get("requested") == 50, body
        assert body.get("returned") == 1, body
        # Mo thread = da doc: summary het unread o thread nay.
        status, body = api("GET", "/api/inbox/summary")
        assert by_id["20001"]["unread"] == 1  # snapshot cu, khong doi
        assert {t["thread_id"]: t for t in body["threads"]}[
            "20001"]["unread"] == 0, body

        # Lich su nhom: tin Zalo + tin den ghep, khong trung, sap
        # theo thoi gian (mock: 5600, 5660; tin den: 5710).
        status, body = api("GET",
                           "/api/thread/30001/history?type=group&count=50")
        assert status == 200, body
        assert [m["text"] for m in body["messages"]] == \
            ["Chao ca nhom", "Chao Ban A", "Chao ca nhom"], body
        assert body.get("source") == "zalo+inbox", body
        assert body.get("fromCache") == 1, body
        assert body.get("has_more") is False, body

        # Updates: chi tin moi sau moc; moc 0 tra het tin Inbox.
        status, body = api(
            "GET", "/api/thread/20001/updates?type=user&after=0")
        assert status == 200, body
        assert [m["text"] for m in body["messages"]] == \
            ["Chao ban, toi la BenBap"], body
        assert body.get("has_new") is True, body
        status, body = api(
            "GET", "/api/thread/20001/updates?type=user&after=9999999999")
        assert body["messages"] == [], body
        assert body.get("has_new") is False, body

        # count theo Node.js: 1..1000, ngoai khoang -> 400.
        status, body = api(
            "GET", "/api/thread/30001/history?type=group&count=0")
        assert status == 400, body
        assert "1 den 1000" in body.get("error", ""), body
        status, body = api(
            "GET", "/api/thread/30001/history?type=group&count=1001")
        assert status == 400, body
        status, body = api(
            "GET", "/api/thread/30001/history?type=group&count=1000")
        assert status == 200, body

        # Dang xuat: poller dung, Inbox xoa, route lai 401.
        state.stop_sync()
        status, body = api_json("POST", "/api/logout", {})
        assert body["ok"] is True
        assert state.inbox.messages_for("user", "20001") == []
        status, body = api("GET", "/api/inbox/summary")
        assert status == 401, body
        httpd.shutdown()
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL INCOMING TESTS PASSED")
