"""End-to-end smoke test through the real app HTTP API.

Starts the actual server (ephemeral port) with domains pointed at the
mock, runs the QR flow via /api/*, and checks:
  - /api/qr/status reaches "done"
  - session file is created with mode 0600
  - /api/status never leaks session secrets
  - /api/contacts + /api/call/request work after login
  - /api/logout clears the session
"""

import contextlib
import io
import json
import os
import socket
import stat
import struct
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-test-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_PORT"] = "0"
# App login gate (see tests/test_app_auth.py): the smoke test logs in
# through /api/app/login first and carries the cookie. Fake test-only
# credentials, never a real password.
os.environ["ZALO_PC_APP_USER"] = "nguoi-dung-test"
os.environ["ZALO_PC_APP_PASSWORD"] = "mat-khau-test-123"
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)

from mock_server import MockZalo, TEST_PARAM_KEY  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


_COOKIE = ""


def api(method, path, body=None):
    global _COOKIE
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode()
                                 if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if _COOKIE:
        req.add_header("Cookie", _COOKIE)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            _store_cookie(resp.headers.get("Set-Cookie") or "")
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        _store_cookie(e.headers.get("Set-Cookie") or "")
        return e.code, json.loads(e.read().decode())


def _store_cookie(set_cookie):
    """Keep the app session cookie; a Max-Age=0 (logout) clears it."""
    global _COOKIE
    if not set_cookie:
        return
    if "Max-Age=0" in set_cookie:
        _COOKIE = ""
    elif set_cookie.startswith("zalo_pc_app="):
        _COOKIE = set_cookie.split(";", 1)[0]


def test_server_e2e():
    global BASE
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
        BASE = "http://127.0.0.1:%d" % port
        import threading
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        status, body = api("GET", "/api/status")
        assert status == 401, body  # app gate: no cookie yet
        status, body = api("POST", "/api/app/login",
                           {"username": "nguoi-dung-test",
                            "password": "mat-khau-test-123"})
        assert status == 200 and body["ok"] is True, body

        status, body = api("GET", "/api/status")
        assert body["login"] is False, body
        # Version marker: /api/status always reports the running
        # version, so a deploy can be checked against the pushed code.
        assert body.get("version"), body

        status, body = api("POST", "/api/qr/new", {})
        assert body["ok"] is True
        deadline = time.time() + 20
        last = {}
        while time.time() < deadline:
            status, last = api("GET", "/api/qr/status")
            if last["state"] == "done":
                break
            time.sleep(0.5)
        assert last["state"] == "done", last

        # Session file: exists, mode 0600, holds the grant.
        sess_path = os.path.join(tmp, "session.json")
        assert os.path.exists(sess_path)
        mode = stat.S_IMODE(os.stat(sess_path).st_mode)
        assert mode == 0o600, oct(mode)
        with open(sess_path) as f:
            sess = json.load(f)
        assert sess["uid"] == "10001" and sess["zpw_enk"], sess.keys()

        # Public status must NOT leak secrets.
        status, body = api("GET", "/api/status")
        assert body["login"] is True and body["uid"] == "10001"
        assert body.get("version"), body
        blob = json.dumps(body)
        for secret in ("sek-test", "kt-test", sess["zpw_enk"], "dkey-test"):
            assert secret not in blob, secret

        status, body = api("GET", "/api/contacts")
        assert body["friends"]["rows"][0]["name"] == "Ban A", body

        status, body = api("POST", "/api/call/request",
                           {"callee_id": "20001", "call_id": "9001"})
        assert body["ok"] is True, body
        # §7k contract (114 fix, parallel agent): call_id is
        # normalized to a uint32 JSON number server-side and the
        # EFFECTIVE id is returned — the client must use that id
        # for /api/call/end, not the id it sent. Non-numeric ids
        # ("c9"/"g9" as before) fall back to epoch seconds and can
        # collide within one second, so this test sends numeric
        # ids and asserts on the returned ones.
        cid_user = body["call_id"]
        assert cid_user == 9001, body

        # A group tap goes to the group endpoint (12433), addressed
        # by the group threadId — not to the 1-1 requestcall — with
        # partners = the members loaded with the contacts.
        status, body = api("GET", "/api/contacts")
        members = body["groups"]["rows"][0]["members"]
        assert members == ["20001", "20002"], members
        # Số thành viên hiển thị đi kèm hàng nhóm (bug "0 thành viên"
        # 2026-11-05): Nhom Y chỉ có 1 topMember nhưng totalMember=5.
        assert [r["member_count"] for r in body["groups"]["rows"]] == \
            [2, 5], body
        status, body = api("POST", "/api/call/request",
                           {"callee_id": "30001", "call_id": "9002",
                            "type": "group", "partners": members})
        assert body["ok"] is True, body
        cid_group = body["call_id"]
        assert cid_group == 9002, body

        # The call log (UI Calls view + rail) records both calls,
        # newest first, with threadId + type, and the live one.
        # Starting the group call already closed the older user
        # call (a new call replaces the live one).
        status, body = api("GET", "/api/calls")
        assert status == 200, body
        assert [c["thread_id"] for c in body["calls"]] == ["30001", "20001"], body
        assert [c["type"] for c in body["calls"]] == ["group", "user"], body
        assert [c["status"] for c in body["calls"]] == ["sent", "ended"], body
        assert body["active"]["call_id"] == str(cid_group), body
        blob = json.dumps(body)
        for secret in ("zpw_sek", "zpw_enk", "zpw_kt", "dkey", "sek-test",
                       "enk-test"):
            assert secret not in blob, secret

        # Ending the group call marks it ended and leaves no live call.
        # The end uses the EFFECTIVE call_id from the request (§7k).
        status, body = api("POST", "/api/call/end",
                           {"uid_to": "30001", "call_id": cid_group})
        assert body["ok"] is True, body
        status, body = api("GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(cid_group)]["status"] == "ended", body
        assert by_id[str(cid_user)]["status"] == "ended", body
        assert body["active"] is None, body

        status, body = api("POST", "/api/logout", {})
        assert body["ok"] is True
        assert not os.path.exists(sess_path)
        # /api/logout also revokes the app session: the app gate now
        # answers 401 until a fresh app login.
        status, body = api("GET", "/api/status")
        assert status == 401, body
        # /api/calls also requires login.
        status, body = api("GET", "/api/calls")
        assert status == 401, body
        httpd.shutdown()
    finally:
        mock.stop()


def test_connection_reset_silenced():
    """A client that RSTs before sending a request (browser/proxy
    closing early — seen live from LAN client 172.16.10.1) must NOT
    produce a ConnectionResetError traceback in the server log, and
    the server must keep answering afterwards. The traceback came
    from socketserver.handle_error; QuietServer swallows exactly
    ConnectionResetError/BrokenPipeError."""
    # Deterministic unit part: call handle_error with a live
    # ConnectionResetError and check nothing is printed.
    srv = app_server.QuietServer(("127.0.0.1", 0), app_server.Handler)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            try:
                raise ConnectionResetError(104, "Connection reset by peer")
            except ConnectionResetError:
                srv.handle_error(None, ("127.0.0.1", 12345))
            try:
                raise BrokenPipeError(32, "Broken pipe")
            except BrokenPipeError:
                srv.handle_error(None, ("127.0.0.1", 12345))
        assert "Traceback" not in buf.getvalue(), buf.getvalue()
        assert "ConnectionResetError" not in buf.getvalue(), buf.getvalue()
        # A different error must still print (no blanket silencing).
        buf2 = io.StringIO()
        with contextlib.redirect_stderr(buf2):
            try:
                raise ValueError("boom")
            except ValueError:
                srv.handle_error(None, ("127.0.0.1", 12345))
        assert "Traceback" in buf2.getvalue(), buf2.getvalue()
    finally:
        srv.server_close()
    # Live part: real RSTs against a running QuietServer.
    live = app_server.QuietServer(("127.0.0.1", 0), app_server.Handler)
    port = live.server_address[1]
    threading.Thread(target=live.serve_forever, daemon=True).start()
    try:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            for _ in range(5):
                s = socket.socket()
                s.connect(("127.0.0.1", port))
                # Close with RST instead of FIN: abortive close.
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                             struct.pack("ii", 1, 0))
                s.close()
            time.sleep(0.5)
        assert "Traceback" not in buf.getvalue(), buf.getvalue()
        # The app gate is on for the import-time global STATE (the
        # test env sets app credentials at the top of this file):
        # log in first, then the status check carries the cookie.
        login_req = urllib.request.Request(
            "http://127.0.0.1:%d/api/app/login" % port, method="POST",
            data=json.dumps({"username": "nguoi-dung-test",
                             "password": "mat-khau-test-123"}).encode())
        login_req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(login_req, timeout=10) as resp:
            cookie = resp.headers.get("Set-Cookie").split(";", 1)[0]
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/status" % port, method="GET")
        req.add_header("Cookie", cookie)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
        assert resp.status == 200 and body.get("version"), body
    finally:
        live.shutdown()
        live.server_close()


if __name__ == "__main__":
    BASE = ""
    test_server_e2e()
    print("PASS test_server_e2e")
    test_connection_reset_silenced()
    print("PASS test_connection_reset_silenced")
    print("ALL SERVER TESTS PASSED")
