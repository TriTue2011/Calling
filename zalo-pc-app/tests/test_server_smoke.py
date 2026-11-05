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

from mock_server import MockZalo, TEST_PARAM_KEY  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def api(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode()
                                 if body is not None else None)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


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
                           {"callee_id": "20001", "call_id": "c9"})
        assert body["ok"] is True, body

        status, body = api("POST", "/api/logout", {})
        assert body["ok"] is True
        assert not os.path.exists(sess_path)
        status, body = api("GET", "/api/status")
        assert body["login"] is False
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
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/status" % port, method="GET")
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
