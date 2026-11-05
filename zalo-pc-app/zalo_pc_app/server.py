"""App service: stdlib HTTP server + JSON API + static UI.

API (all JSON, never returns session secrets):
  GET  /api/status        {login, uid, phonenum, engine}
  POST /api/qr/new        start a QR login (background thread)
  GET  /api/qr/status     {state, qr_image, countdown, wait_seconds, ...}
  POST /api/logout        clear the stored session
  GET  /api/contacts      {friends:[...], groups:[...]} (needs login)
  POST /api/call/request  {callee_id} -> signaling requestcall
  POST /api/call/end      {uid_to, call_id} -> signaling endcall
  GET  /api/engine/status media-engine seam status

Real transport uses urllib. Post-login calls send the session cookie
(Cookie header name configurable via ZALO_PC_COOKIE_NAME, default
"zpw_sek" — confirmed as the PC client's cookie name from main.js
setAppCookie). getLoginInfo itself is a *login* API: it carries the
login envelope (imei/computer_name/language/ts + type/client_version/
signkey, encrypted when a param cipher key is configured) plus the
session cookie — never the post-login zpw_ver/zpw_type params.
"""

import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import VERSION as _PKG_VERSION
from . import contacts as contacts_mod
from . import engine_seam
from . import protocol
from . import qr_login
from . import session as session_mod
from . import signaling as signaling_mod
from .crypto import make_device_id

# Version marker (see zalo_pc_app/__init__.py): the Docker build sets
# ZALO_PC_VERSION to the exact commit sha; without it, the code tag
# above applies. /api/status returns it and the UI footer shows it,
# so a deploy can be checked against the pushed code.
VERSION = os.environ.get("ZALO_PC_VERSION") or _PKG_VERSION

DATA_DIR = os.environ.get("ZALO_PC_DATA_DIR", "./data")
PORT = int(os.environ.get("ZALO_PC_PORT", "8080"))
HOST = os.environ.get("ZALO_PC_HOST", "127.0.0.1")
PARAM_CIPHER_KEY = os.environ.get("ZALO_PC_PARAM_CIPHER_KEY", "") or None
COOKIE_NAME = os.environ.get("ZALO_PC_COOKIE_NAME", "zpw_sek")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def make_transport(cookie_value=""):
    """http_get(url, timeout) -> (status, json_dict)."""

    def http_get(url, timeout=30):
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "zalo-pc-qr/1.0")
        if cookie_value:
            req.add_header("Cookie", "%s=%s" % (COOKIE_NAME, cookie_value))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {}
            return e.code, body
        except (TimeoutError, socket.timeout):
            raise TimeoutError("GET timeout: %s" % url)

    return http_get


class AppState:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.store = session_mod.SessionStore(
            os.path.join(data_dir, "session.json"))
        self.lock = threading.Lock()
        self.qr = None          # current QR record (memory only)
        self.qr_state = "idle"  # idle|waiting|scanned|done|expired|
        # rejected|rate_limited|error
        self.qr_error = ""
        self.qr_wait = 0
        self.session = self.store.load() if self.store.exists() else None
        # First friends load after start/login sends init=1 (real client
        # _isFirstReq()). Cleared after the first successful friends call.
        self._contacts_init_pending = True
        self.thread = None

    # -- session helpers -------------------------------------------------
    def public_status(self):
        with self.lock:
            base = {"version": VERSION,
                    "engine": engine_seam.SEAM.status()}
            if self.session and self.session.get("zpw_sek"):
                base.update({"login": True,
                             "uid": self.session.get("uid", ""),
                             "phonenum": self.session.get("phonenum", "")})
                return base
            base.update({"login": False, "uid": "", "phonenum": ""})
            return base

    def _device_and_computer(self):
        if self.session and self.session.get("device_id"):
            device_id = self.session["device_id"]
        else:
            device_id = make_device_id()
        return device_id, socket.gethostname()

    # -- QR flow (background thread) ------------------------------------
    def start_qr(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            self.qr_state = "waiting"
            self.qr_error = ""
            self.qr = None
        self.thread = threading.Thread(target=self._qr_worker, daemon=True)
        self.thread.start()
        return True

    def _qr_worker(self):
        try:
            device_id, computer = self._device_and_computer()
            logged_uids = []
            if self.session and self.session.get("uid"):
                logged_uids = [self.session["uid"]]
            transport = make_transport()
            qr = qr_login.fetch_qr(
                transport, device_id, computer, logged_uids,
                param_cipher_key=PARAM_CIPHER_KEY, self_g=0, qr_form=0)
            with self.lock:
                self.qr = qr
                self.qr_state = "waiting"
            qr_login.wait_scan(transport, qr, trust_enabled=False)
            with self.lock:
                self.qr_state = "scanned"
            grant = qr_login.wait_confirm(transport, qr)
            # Session established: fetch login info (login envelope +
            # session cookie, exactly as the PC client sends it).
            login_info = self._fetch_login_info(grant, device_id, computer)
            sess = session_mod.new_session(device_id, computer)
            sess.update({
                "uid": grant["uid"], "dkey": grant["dkey"],
                "phonenum": grant["phonenum"],
                "zpw_sek": grant["zpw_sek"], "zpw_kt": grant["zpw_kt"],
                "zpw_enk": login_info.get("zpw_enk", ""),
                "service_map": login_info.get("config", {}).get(
                    "zpw_service_map_new", {}),
                "ws_endpoint": login_info.get("config", {}).get("zpw_ws", ""),
                "status": session_mod.STATUS_LOGGED_IN,
            })
            self.store.save(sess)
            with self.lock:
                self.session = sess
                self.qr_state = "done"
                self.qr = None
                # New session: next friends load is a first load (init=1).
                self._contacts_init_pending = True
        except qr_login.RateLimited as e:
            with self.lock:
                self.qr_state = "rate_limited"
                self.qr_wait = e.wait_seconds
        except qr_login.UserRejected:
            with self.lock:
                self.qr_state = "rejected"
        except qr_login.QRExpired:
            with self.lock:
                self.qr_state = "expired"
        except qr_login.TrustFlowRequired as e:
            with self.lock:
                self.qr_state = "error"
                self.qr_error = str(e)
        except Exception as e:  # noqa: BLE001 - surface to UI, keep server up
            with self.lock:
                self.qr_state = "error"
                self.qr_error = "%s: %s" % (type(e).__name__, e)

    def _fetch_login_info(self, grant, device_id, computer_name):
        """GET getLoginInfo, exactly as the PC client sends it
        (renderer API class getLoginInfo, api code 11134):
        login envelope (imei/computer_name/language/ts + type/
        client_version/signkey, encrypted when a param cipher key is
        configured) plus the zpw_sek session cookie. The previous
        implementation sent only zpw_ver/zpw_type + cookie, which the
        server rejects with error 102 (session key improperly
        submitted): without the envelope the session cannot be bound
        to the device. The response data carries config, dkey and
        zpw_enk (AES-decrypted first when the request went out
        encrypted)."""
        sek = grant.get("zpw_sek", "")
        if not sek:
            # Never send a cookieless request: the server answers it
            # with a cryptic 102. Name the missing field instead.
            # (The value itself is never logged.)
            raise RuntimeError(
                "getLoginInfo: confirm grant missing zpw_sek "
                "(session key); cannot authenticate without it")
        transport = make_transport(sek)
        query, enk = qr_login.logininfo_query(
            device_id, computer_name, PARAM_CIPHER_KEY)
        url = protocol.build_url(protocol.AUTH_DOMAIN,
                                 "/api/login/getLoginInfo", query)
        status, payload = transport(url, timeout=30)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("getLoginInfo: network status=%s" % status)
        if payload.get("error_code") != 0:
            raise RuntimeError("getLoginInfo: error_code=%s %s" % (
                payload.get("error_code"), payload.get("error_message", "")))
        data = qr_login.decode_response(payload, enk)
        if not isinstance(data, dict):
            data = {}
        return {"zpw_enk": data.get("zpw_enk", ""),
                "config": data.get("config", {}),
                "dkey": data.get("dkey", "")}

    def qr_status(self):
        with self.lock:
            out = {"state": self.qr_state, "error": self.qr_error,
                   "wait_seconds": self.qr_wait}
            if self.qr and self.qr.get("base64_qr"):
                out["qr_image"] = ("data:image/png;base64,"
                                   + self.qr["base64_qr"])
                out["countdown"] = self.qr.get("qr_timeout") or 90
            if self.session and self.session.get("uid"):
                out["uid"] = self.session["uid"]
                out["phonenum"] = self.session.get("phonenum", "")
            return out

    def logout(self):
        with self.lock:
            self.store.clear()
            self.session = None
            self.qr = None
            self.qr_state = "idle"


STATE = AppState(DATA_DIR)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    # -- helpers ---------------------------------------------------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _require_login(self):
        sess = STATE.session
        if not sess or not sess.get("zpw_sek"):
            return None
        return sess

    # -- routing ---------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._serve_static("app.html", "text/html")
        if path in ("/app.js", "/style.css"):
            ctype = ("text/javascript" if path.endswith(".js")
                     else "text/css")
            return self._serve_static(path.lstrip("/"), ctype)
        if path == "/api/status":
            return self._send_json(STATE.public_status())
        if path == "/api/qr/status":
            return self._send_json(STATE.qr_status())
        if path == "/api/engine/status":
            return self._send_json(engine_seam.SEAM.status())
        if path == "/api/contacts":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            try:
                transport = make_transport(sess["zpw_sek"])
                book = contacts_mod.Contacts(transport, sess["device_id"],
                                             sess["zpw_enk"])
                # Friends first, then groups — and name the failing
                # endpoint in the error (the old code lumped both into
                # one message, so a 602 could not be attributed).
                try:
                    friends = book.friends(init=STATE._contacts_init_pending)
                except Exception as e:  # noqa: BLE001
                    return self._send_json(
                        {"error": "friends: %s" % e}, status=502)
                # A successful friends call consumes the first-load flag.
                STATE._contacts_init_pending = False
                try:
                    groups = book.groups()
                except Exception as e:  # noqa: BLE001
                    return self._send_json(
                        {"error": "groups: %s" % e}, status=502)
                return self._send_json({"friends": friends,
                                        "groups": groups})
            except Exception as e:  # noqa: BLE001
                return self._send_json({"error": str(e)}, status=502)
        return self._send_json({"error": "not_found"}, status=404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        body = self._read_json()
        if path == "/api/qr/new":
            STATE.start_qr()
            return self._send_json({"ok": True})
        if path == "/api/logout":
            STATE.logout()
            return self._send_json({"ok": True})
        if path == "/api/call/request":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            try:
                transport = make_transport(sess["zpw_sek"])
                sig = signaling_mod.Signaling(transport, sess["device_id"],
                                              sess["zpw_enk"])
                data = sig.request_call(
                    body.get("callee_id", ""),
                    body.get("call_id", ""),
                    body.get("codec"),
                    body.get("type_request", 0))
                return self._send_json({"ok": True, "data": data})
            except Exception as e:  # noqa: BLE001
                return self._send_json({"error": str(e)}, status=502)
        if path == "/api/call/end":
            sess = self._require_login()
            if sess is None:
                return self._send_json({"error": "chua_dang_nhap"},
                                       status=401)
            try:
                transport = make_transport(sess["zpw_sek"])
                sig = signaling_mod.Signaling(transport, sess["device_id"],
                                              sess["zpw_enk"])
                data = sig.endcall(body.get("uid_to", ""),
                                   body.get("call_id", ""))
                return self._send_json({"ok": True, "data": data})
            except Exception as e:  # noqa: BLE001
                return self._send_json({"error": str(e)}, status=502)
        return self._send_json({"error": "not_found"}, status=404)

    def _serve_static(self, name, ctype):
        try:
            with open(os.path.join(STATIC_DIR, name), "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return self._send_json({"error": "not_found"}, status=404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = QuietServer((HOST, PORT), Handler)
    print("zalo-pc-qr app %s on http://%s:%d (data: %s)"
          % (VERSION, HOST, PORT, DATA_DIR))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


class QuietServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that stays silent when a client disconnects
    before sending a request.

    Browsers/proxies sometimes open a connection and close it (RST)
    before any request line arrives; socketserver then logs a full
    traceback (ConnectionResetError: [Errno 104] Connection reset by
    peer, in process_request_thread -> rfile.readline). The server is
    fine — the client simply went away — but the traceback pollutes
    the log and looks like the app is broken. Swallow exactly that
    class of error; anything else still prints as before."""

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


if __name__ == "__main__":
    main()
