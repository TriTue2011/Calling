"""Muc "Theo doi" (nguoi la), danh sach hoi thoai + so chua doc ben qua
restart, proxy, bao mat (thu hoi phien, chan do mat khau), kenh day SSE.
Chay: python3 tests/test_watch_proxy_security.py"""

import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from zalo_pc_app import app_auth, events, message_store, protocol, proxy_store  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import webhooks  # noqa: E402


def _msg(mid, sender, text, ts, name="", kind="text"):
    return {"id": mid, "sender_id": sender, "text": text, "time": ts,
            "kind": kind, "sender_name": name, "raw": {"msgId": mid, "dName": name}}


# ------------------------------------------------------------ kho tin
def test_threads_unread_name_and_mark_read():
    st = message_store.MessageStore(os.path.join(tempfile.mkdtemp(), "m.db"))
    st.set_account("ME1")
    now = time.time()
    st.record("user", "STR1", _msg("1", "STR1", "chào shop", now - 30, "Nguyễn Lạ"))
    st.record("user", "STR1", _msg("2", "STR1", "giá bao nhiêu", now - 20, "Nguyễn Lạ"))
    st.record("user", "STR1", _msg("3", "ME1", "dạ 100k", now - 10))
    st.record("group", "G1", _msg("4", "U9", "hello", now - 5, "Bạn B"))
    st.record("user", "F1", _msg("5", "F1", "", now - 3, "Bạn", kind="photo"))
    rows = {(r["thread_type"], r["thread_id"]): r for r in st.threads()}
    s = rows[("user", "STR1")]
    assert s["count"] == 3 and s["incoming_count"] == 2, s
    assert s["unread"] == 2 and s["name"] == "Nguyễn Lạ", s
    assert s["last_out"] is True and s["last_text"] == "dạ 100k", s
    assert rows[("group", "G1")]["unread"] == 1
    assert rows[("user", "F1")]["last_text"] == "[Ảnh]"
    # Thu tu: moi nhat truoc.
    assert [r["thread_id"] for r in st.threads()][0] == "F1"
    assert st.mark_read("user", "STR1") is True
    again = {(r["thread_type"], r["thread_id"]): r for r in st.threads()}
    assert again[("user", "STR1")]["unread"] == 0
    assert again[("group", "G1")]["unread"] == 1  # thread khac khong bi dung


def test_unread_survives_reopen_and_old_history_counts_as_read():
    path = os.path.join(tempfile.mkdtemp(), "m.db")
    st = message_store.MessageStore(path)
    st.set_account("ME1")
    st.record("user", "A", _msg("1", "A", "cu", time.time() - 100, "A"))
    # Gia lap DB cu (chua co bang reads): xoa bang roi mo lai.
    st._conn.execute("DROP TABLE reads")
    st._conn.commit()
    st._conn.close()
    st2 = message_store.MessageStore(path)
    st2.set_account("ME1")
    assert st2.threads()[0]["unread"] == 0, "tin cu phai tinh la da doc"
    st2.record("user", "A", _msg("2", "A", "moi", time.time() + 5, "A"))
    assert st2.threads()[0]["unread"] == 1
    st3 = message_store.MessageStore(path)       # mo lai lan nua
    st3.set_account("ME1")
    assert st3.threads()[0]["unread"] == 1, "so chua doc phai ben qua restart"


# ------------------------------------------------------------ proxy
def test_proxy_validation_and_secrets():
    ok = proxy_store.validate_proxy_url("user:pw@10.0.0.5:3128")
    assert ok == "http://user:pw@10.0.0.5:3128"
    for bad in ("", "socks5://1.2.3.4:1080", "http://", "http://h:99999",
                "http://a b:1", "ftp://x:1"):
        try:
            proxy_store.validate_proxy_url(bad)
        except ValueError:
            continue
        raise AssertionError("phai tu choi: %r" % bad)
    path = os.path.join(tempfile.mkdtemp(), "proxy.json")
    ps = proxy_store.ProxyStore(path)
    pid = ps.add("http://u:secret@10.0.0.5:3128", "nha")
    assert (os.stat(path).st_mode & 0o777) == 0o600
    pub = json.dumps(ps.public())
    assert "secret" not in pub and "10.0.0.5:3128" in pub, pub
    assert ps.public()["items"][0]["has_auth"] is True
    try:
        ps.add("http://u:secret@10.0.0.5:3128")
        raise AssertionError("trung phai bi tu choi")
    except ValueError:
        pass
    assert ps.active_url() == ""
    ps.set_active(pid)
    assert ps.active_url() == "http://u:secret@10.0.0.5:3128"
    ps.remove(pid)
    assert ps.active_url() == "" and ps.public()["items"] == []


# ------------------------------------------------------------ bao mat
def test_revoke_all_keeps_current_and_limiter_blocks():
    auth = app_auth.AppAuth("u", app_auth.hash_password("pw"))
    t1, _ = auth.create_session("u")
    t2, _ = auth.create_session("u")
    t3, _ = auth.create_session("u")
    assert auth.revoke_all(keep_token=t1) == 2
    assert auth.validate_token(t1) == "u" and auth.validate_token(t2) is None
    assert auth.revoke_all() == 1 and auth.session_count() == 0
    lim = app_auth.LoginLimiter(max_fails=3, window=60)
    now = 1000.0
    for _ in range(3):
        assert not lim.blocked("1.1.1.1", now)
        lim.fail("1.1.1.1", now)
    assert lim.blocked("1.1.1.1", now + 1) and not lim.blocked("2.2.2.2", now)
    assert lim.blocked_count(now + 1) == 1
    assert not lim.blocked("1.1.1.1", now + 61), "het cua so thi mo lai"
    lim.fail("3.3.3.3", now); lim.reset("3.3.3.3")
    assert not lim.blocked("3.3.3.3", now)


# ------------------------------------------------------------ kenh day
def test_event_hub_fanout_and_drop_oldest():
    hub = events.EventHub()
    a, b = hub.subscribe(), hub.subscribe()
    hub.publish({"n": 1})
    assert a.get_nowait() == {"n": 1} and b.get_nowait() == {"n": 1}
    for i in range(events.QUEUE_SIZE + 5):
        hub.publish({"n": i})
    assert a.qsize() == events.QUEUE_SIZE          # khong tran, bo cai cu nhat
    assert a.get_nowait() == {"n": 5}
    hub.unsubscribe(a)
    assert hub.count() == 1
    for _ in range(events.MAX_SUBSCRIBERS):
        hub.subscribe()
    assert hub.subscribe() is None


def test_webhook_message_event_has_name_stranger_and_latency_fields():
    ev = webhooks.build_message_event({
        "threadId": "T1", "type": 0, "senderId": "T1", "msgId": "m", "content": "hi",
        "senderName": "Nguyễn Lạ", "isStranger": True, "time": 1794000000}, "ME")
    assert ev["sender_name"] == "Nguyễn Lạ" and ev["is_stranger"] is True, ev
    assert ev["zalo_time"] == 1794000000 and ev["received_at"] > 1.7e9, ev
    old = webhooks.build_message_event({"threadId": "T1", "content": "x"}, "ME")
    assert old["sender_name"] == "" and old["is_stranger"] is False


def test_poll_loop_does_not_sleep_after_data():
    """Co tin ("ok") thi vong poll hoi tiep ngay — san 1 giay chi ap khi rong."""
    import inspect
    from zalo_pc_app import ctrl_poll, sync_poll
    for mod in (sync_poll, ctrl_poll):
        src = inspect.getsource(mod)
        assert 'result != "ok"' in src and "result = self.poll_once()" in src, mod.__name__


# ------------------------------------------------------------ e2e
def _start_app(mock):
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-watch-")
    os.environ["ZALO_PC_DATA_DIR"] = tmp
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    app_server.PARAM_CIPHER_KEY = "TEST_PARAM_KEY_32_CHARS_LONG_XXX"
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1], state


def _api(base, method, path, body=None, headers=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _login(base):
    _api(base, "POST", "/api/qr/new", {})
    for _ in range(40):
        _, last = _api(base, "GET", "/api/qr/status")
        if last.get("state") == "done":
            return
        time.sleep(0.5)
    raise AssertionError("QR khong xong")


def test_e2e_conversations_watch_proxy_security_sse():
    mock = MockZalo().start()
    httpd = None
    try:
        httpd, base, state = _start_app(mock)
        _login(base)
        uid = state.session["uid"]
        state.message_store.set_account(uid)
        now = time.time()
        # Nguoi la nhan tin: khong co trong danh ba (mock co ban 20001...).
        state.message_store.record("user", "999000111", _msg("a1", "999000111", "alo shop", now, "Người Lạ"))
        state.message_store.record("user", "0", _msg("z1", "0", "rac", now, "Rác"))
        state._contacts_cache = {"friends": {"rows": [{"id": "20001", "name": "Ban"}]}, "groups": {"rows": []}}
        status, conv = _api(base, "GET", "/api/conversations")
        assert status == 200 and conv["contacts_ready"] is True, conv
        row = [t for t in conv["threads"] if t["thread_id"] == "999000111"][0]
        assert row["stranger"] is True and row["unread"] == 1 and row["name"] == "Người Lạ", row
        assert conv["unread_total"] >= 1
        assert "0" not in [t["thread_id"] for t in conv["threads"]], "thread 0 phai bi loc"
        status, watch = _api(base, "GET", "/api/watch")
        assert [s["thread_id"] for s in watch["strangers"]] == ["999000111"], watch
        # Mo hoi thoai (history) = da doc, ben vung.
        _api(base, "GET", "/api/thread/999000111/history?type=user&count=5")
        _, conv2 = _api(base, "GET", "/api/conversations")
        assert [t for t in conv2["threads"] if t["thread_id"] == "999000111"][0]["unread"] == 0
        # Trang thai co do tre.
        state._note_lag({"raw": {"ts": str(int((time.time() - 0.5) * 1000))}})
        _, st = _api(base, "GET", "/api/status")
        assert st["sync_lag_ms"]["n"] >= 1, st
        # Proxy qua API.
        _, p = _api(base, "POST", "/api/proxy", {"action": "add", "url": "http://u:pw@10.9.9.9:8080", "name": "t"})
        assert "pw" not in json.dumps(p) and len(p["items"]) == 1, p
        pid = p["items"][0]["id"]
        _, p = _api(base, "POST", "/api/proxy", {"action": "activate", "id": pid})
        assert p["active"] == pid
        assert app_server.STATE.proxy_store.active_url().endswith("10.9.9.9:8080")
        code, bad = _api(base, "POST", "/api/proxy", {"action": "add", "url": "socks5://x:1"})
        assert code == 400 and "error" in bad
        _api(base, "POST", "/api/proxy", {"action": "remove", "id": pid})
        assert app_server.STATE.proxy_store.active_url() == ""
        # Bao mat.
        _, sec = _api(base, "GET", "/api/security")
        assert "sessions" in sec and sec["login_max_fails"] == 5, sec
        # SSE: mo luong, day mot tin, doc duoc ngay.
        host, port = base.replace("http://", "").split(":")
        s = socket.create_connection((host, int(port)), timeout=5)
        s.sendall(b"GET /api/events HTTP/1.1\r\nHost: x\r\n\r\n")
        buf = b""
        t0 = time.time()
        while b"retry:" not in buf and time.time() - t0 < 5:
            buf += s.recv(4096)
        state.events.publish({"type": "message", "thread_id": "T9", "msg": {"text": "x"}})
        t1 = time.time()
        while b"T9" not in buf and time.time() - t1 < 5:
            buf += s.recv(4096)
        assert b"event: message" in buf and b"T9" in buf, buf
        assert time.time() - t1 < 1.0, "SSE phai giao gan nhu tuc thoi"
        s.close()
    finally:
        try:
            app_server.STATE.stop_sync()
        except Exception:  # noqa: BLE001
            pass
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        mock.stop()


if __name__ == "__main__":
    failed = []
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            failed.append(fn.__name__)
            print("FAIL", fn.__name__, exc)
    print("%d/%d tests passed" % (len(tests) - len(failed), len(tests)))
    raise SystemExit(1 if failed else 0)
