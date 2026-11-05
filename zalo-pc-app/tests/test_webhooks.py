"""Unit + mock-HTTP tests for webhooks (zalo_pc_app/webhooks.py).

Covers: config defaults / save+load round-trip / file mode 0600 /
bad-URL rejection / per-kind toggles / call-event dispatch to a real
mock HTTP endpoint (payload shape) / webhook failure never breaking
the caller / self-message suppression / test payloads.
No real login, no real call, no real webhook URL anywhere here —
the only URLs are http://127.0.0.1:<ephemeral port> listeners spun
up inside the test.
"""
import json
import os
import stat
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import webhooks


def _tmp_store():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-webhook-test-")
    return webhooks.WebhookStore(os.path.join(tmp, "webhooks.json"))


def test_defaults_empty_and_enabled():
    store = _tmp_store()
    assert store.load() == webhooks.default_config()
    cfg = store.load()
    for field in webhooks.URL_FIELDS:
        assert cfg[field] == "", field
    for field in webhooks.ENABLED_FIELDS:
        assert cfg[field] is True, field


def test_save_load_round_trip_and_mode_0600():
    store = _tmp_store()
    cfg = store.save({
        "message_webhook_url": "https://example.invalid/hook-msg",
        "call_webhook_url": "http://127.0.0.1:9/call",
        "call_enabled": False,
    })
    assert cfg["message_webhook_url"] == "https://example.invalid/hook-msg"
    assert cfg["call_enabled"] is False
    # Untouched families keep defaults; unknown keys are dropped.
    assert cfg["reaction_webhook_url"] == ""
    assert cfg["reaction_enabled"] is True
    assert "bogus" not in cfg
    assert store.load() == cfg
    mode = stat.S_IMODE(os.stat(store.path).st_mode)
    assert mode == 0o600, oct(mode)


def test_bad_url_rejected_and_nothing_written():
    store = _tmp_store()
    for bad in ("ftp://example.invalid/x", "javascript:alert(1)",
                "example.invalid/hook", "http://", 123,
                "https://example.invalid/" + "x" * 2048):
        try:
            store.save({"message_webhook_url": bad})
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for %r" % (bad,))
    assert not store.exists()
    # A bad URL in one field must not clobber a good save.
    store.save({"message_webhook_url": "https://example.invalid/ok"})
    try:
        store.save({"call_webhook_url": "notaurl"})
    except ValueError:
        pass
    assert store.load()["message_webhook_url"] == "https://example.invalid/ok"
    assert store.load()["call_webhook_url"] == ""


def test_corrupt_file_yields_defaults():
    store = _tmp_store()
    with open(store.path, "w") as f:
        f.write("{not json")
    assert store.load() == webhooks.default_config()


def test_call_payload_shape():
    entry = {"call_id": "c1", "peer": "Ban A", "thread_id": "20001",
             "type": "user", "status": "sent", "started_at": 1700000000,
             "ended_at": None, "detail": ""}
    p = webhooks.build_call_event(entry, "10001")
    assert p["event"] == "call" and p["type"] == "call.sent"
    assert p["call_id"] == "c1" and p["thread_id"] == "20001"
    assert p["peer"] == "Ban A" and p["call_type"] == "user"
    assert p["account_id"] == "10001" and p["status"] == "sent"
    assert "detail" not in p  # detail only on error events
    err = webhooks.build_call_event(
        dict(entry, status="error", detail="inner 114"), "10001")
    assert err["type"] == "call.error" and err["detail"] == "inner 114"
    ended = webhooks.build_call_event(
        dict(entry, status="ended", ended_at=1700000060), "10001")
    assert ended["type"] == "call.ended"


def test_message_group_reaction_payload_shapes():
    m = webhooks.build_message_event(
        {"threadId": "20001", "type": 0, "uidFrom": "20002",
         "data": {"content": "chao"}, "msgId": "m1"}, "10001")
    assert m["event"] == "message" and m["type"] == "message.received"
    assert m["thread_id"] == "20001" and m["content"] == "chao"
    assert m["is_self"] is False
    g = webhooks.build_group_event_event(
        {"type": "join", "threadId": "30001"}, "10001")
    assert g["event"] == "group_event" and g["type"] == "group_event.join"
    assert g["thread_id"] == "30001"
    r = webhooks.build_reaction_event(
        {"threadId": "20001", "msgId": "m1", "uidFrom": "20002",
         "icon": "heart"}, "10001")
    assert r["event"] == "reaction" and r["icon"] == "heart"


class _Capture(BaseHTTPRequestHandler):
    received = []
    status_to_send = 200

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        _Capture.received.append(
            {"path": self.path, "body": body,
             "ctype": self.headers.get("Content-Type")})
        data = json.dumps({"ok": True}).encode()
        self.send_response(_Capture.status_to_send)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def _start_capture(status=200):
    _Capture.received = []
    _Capture.status_to_send = status
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Capture)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d/hook" % httpd.server_address[1]


def _wait_received(n=1, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(_Capture.received) >= n:
            return True
        time.sleep(0.05)
    return False


def test_dispatch_call_event_hits_endpoint():
    store = _tmp_store()
    httpd, url = _start_capture()
    try:
        store.save({"call_webhook_url": url})
        disp = webhooks.WebhookDispatcher(store)
        entry = {"call_id": "c7", "peer": "Ban A", "thread_id": "20001",
                 "type": "user", "status": "sent",
                 "started_at": 1700000000, "ended_at": None, "detail": ""}
        assert webhooks.dispatch_call_event(disp, entry, "10001") is True
        assert _wait_received(1), "no webhook POST arrived"
        payload = json.loads(_Capture.received[0]["body"].decode())
        assert payload["event"] == "call" and payload["type"] == "call.sent"
        assert payload["call_id"] == "c7" and payload["account_id"] == "10001"
        assert _Capture.received[0]["ctype"] == "application/json"
    finally:
        httpd.shutdown()


def test_disabled_or_empty_url_sends_nothing():
    store = _tmp_store()
    httpd, url = _start_capture()
    try:
        # Empty URL: nothing to send to.
        disp = webhooks.WebhookDispatcher(store)
        assert disp.send_sync(
            "call", webhooks.build_test_event("call", "10001"))[
            "reason"] == "no_url"
        # Configured but toggled off: still nothing.
        store.save({"call_webhook_url": url, "call_enabled": False})
        res = disp.send_sync(
            "call", webhooks.build_test_event("call", "10001"))
        assert res["reason"] == "disabled" and res["dispatched"] is False
        time.sleep(0.3)
        assert _Capture.received == []
    finally:
        httpd.shutdown()


def test_webhook_http_error_reported_not_raised():
    store = _tmp_store()
    httpd, url = _start_capture(status=500)
    try:
        store.save({"call_webhook_url": url})
        disp = webhooks.WebhookDispatcher(store)
        res = disp.send_sync(
            "call", webhooks.build_test_event("call", "10001"))
        assert res["dispatched"] is False and res["status"] == 500
        # And the async path (what the call handlers use) also
        # swallows it — the caller never sees an exception.
        assert disp.dispatch(
            "call", webhooks.build_test_event("call", "10001")) is True
        time.sleep(0.5)
    finally:
        httpd.shutdown()


def test_webhook_unreachable_does_not_break_caller():
    store = _tmp_store()
    # Port 9 (discard) on loopback: connection refused, fast.
    store.save({"call_webhook_url": "http://127.0.0.1:9/hook"})
    disp = webhooks.WebhookDispatcher(store, timeout=2.0)
    res = disp.send_sync("call", webhooks.build_test_event("call", "10001"))
    assert res["dispatched"] is False and res["status"] is None
    assert res["reason"] == "error"
    # Async dispatch of the same failure must not raise either.
    assert disp.dispatch("call", webhooks.build_test_event("call", "10001"))


def test_self_message_not_dispatched_by_default():
    seen = []
    store = _tmp_store()
    store.save({"message_webhook_url": "http://127.0.0.1:9/hook"})
    disp = webhooks.WebhookDispatcher(
        store, post_fn=lambda url, p: seen.append(p) or 200)
    assert webhooks.dispatch_message(
        disp, {"isSelf": True, "threadId": "20001",
               "data": {"content": "tu tra loi"}}, "10001") is False
    time.sleep(0.2)
    assert seen == []
    # …unless it is an owner keyword command (self_reply=true).
    assert webhooks.dispatch_message(
        disp, {"isSelf": True, "self_reply": True, "threadId": "20001",
               "data": {"content": "@ha lam gi do"}}, "10001") is True
    time.sleep(0.5)
    assert len(seen) == 1 and seen[0]["self_reply"] is True


def test_send_test_payload_shape():
    seen = []
    store = _tmp_store()
    store.save({"reaction_webhook_url": "http://127.0.0.1:9/hook"})
    disp = webhooks.WebhookDispatcher(
        store, post_fn=lambda url, p: seen.append(p) or 200)
    res = disp.send_test("reaction", "10001")
    assert res["dispatched"] is True and res["status"] == 200
    assert seen[0]["type"] == "reaction.test" and seen[0]["test"] is True
    assert seen[0]["icon"] == "like"


def test_safe_url_strips_query():
    assert (webhooks.safe_url_for_log(
        "https://example.invalid/hook?token=SECRET&x=1")
        == "https://example.invalid/hook")
    assert webhooks.safe_url_for_log("not a url") == ""


def test_last_deliveries_never_hold_payload():
    store = _tmp_store()
    disp = webhooks.WebhookDispatcher(
        store, post_fn=lambda url, p: 200)
    store.save({"message_webhook_url": "http://127.0.0.1:9/hook"})
    disp.send_sync("message", webhooks.build_message_event(
        {"threadId": "1", "data": {"content": "bi mat"}}, "10001"))
    blob = json.dumps(disp.last_deliveries())
    assert "bi mat" not in blob
    assert disp.last_deliveries()[0]["status"] == 200


# -- API end-to-end through the real server + mock Zalo ------------------
# (same harness shape as tests/test_server_smoke.py: QR login via the
# mock, then the webhook routes + a real call request that must
# dispatch call.sent to a mock HTTP endpoint — and must still answer
# ok when the webhook endpoint is unreachable.)

def _api(base, method, path, body=None):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_api_webhooks_e2e():
    sys.path.insert(0, os.path.dirname(__file__))
    from mock_server import MockZalo, TEST_PARAM_KEY
    from zalo_pc_app import protocol
    from zalo_pc_app import server as app_server

    tmp = tempfile.mkdtemp(prefix="zalo-pc-webhook-e2e-")
    httpd_capture, hook_url = _start_capture()
    mock = MockZalo().start()
    try:
        protocol.AUTH_DOMAIN = mock.base
        protocol.VOICECALL_DOMAIN = mock.base
        protocol.PROFILE_DOMAIN = mock.base
        protocol.GROUP_DOMAIN = mock.base
        app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        base = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        # Webhook routes require login, like /api/calls.
        status, body = _api(base, "GET", "/api/webhooks")
        assert status == 401, body

        # Log in via the mock QR flow.
        status, body = _api(base, "POST", "/api/qr/new", {})
        assert body["ok"] is True
        deadline = time.time() + 20
        last = {}
        while time.time() < deadline:
            status, last = _api(base, "GET", "/api/qr/status")
            if last["state"] == "done":
                break
            time.sleep(0.5)
        assert last["state"] == "done", last

        # GET returns defaults; the config file is created on save.
        status, cfg = _api(base, "GET", "/api/webhooks")
        assert status == 200 and cfg == webhooks.default_config(), cfg

        # Bad URL -> 400, nothing written.
        status, body = _api(base, "POST", "/api/webhooks",
                            {"call_webhook_url": "ftp://example.invalid/x"})
        assert status == 400, body

        # Save: call webhook points at the mock endpoint.
        status, body = _api(base, "POST", "/api/webhooks",
                            {"call_webhook_url": hook_url})
        assert status == 200 and body["ok"] is True, body
        assert body["config"]["call_webhook_url"] == hook_url
        assert os.path.exists(os.path.join(tmp, "webhooks.json"))
        mode = stat.S_IMODE(os.stat(
            os.path.join(tmp, "webhooks.json")).st_mode)
        assert mode == 0o600, oct(mode)

        # «Gửi thử» reports the HTTP status and the endpoint got it.
        _Capture.received = []
        status, body = _api(base, "POST", "/api/webhooks/test",
                            {"kind": "call"})
        assert status == 200 and body["dispatched"] is True, body
        assert body["status"] == 200, body
        assert len(_Capture.received) == 1
        test_payload = json.loads(_Capture.received[0]["body"].decode())
        assert test_payload["type"] == "call.test"
        assert test_payload["test"] is True

        # A real call request still answers ok AND dispatches
        # call.sent to the webhook (async — wait briefly).
        # call_id must be a uint32 number: the server normalizes a
        # non-numeric id to epoch seconds (114 fix), so the webhook
        # carries the EFFECTIVE id, not the raw string.
        _Capture.received = []
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001", "call_id": "123456789"})
        assert status == 200 and body["ok"] is True, body
        assert _wait_received(1), "call.sent webhook never arrived"
        sent = json.loads(_Capture.received[0]["body"].decode())
        assert sent["event"] == "call" and sent["type"] == "call.sent"
        assert sent["call_id"] == "123456789" and sent["thread_id"] == "20001"

        # Webhook endpoint down: the call still succeeds (the
        # failure is swallowed, never breaks the original op).
        status, body = _api(base, "POST", "/api/webhooks",
                            {"call_webhook_url":
                             "http://127.0.0.1:9/hook"})
        assert status == 200, body
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001", "call_id": "123456790"})
        assert status == 200 and body["ok"] is True, body
        httpd.shutdown()
    finally:
        httpd_capture.shutdown()
        mock.stop()


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
    print("%d/%d tests passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
