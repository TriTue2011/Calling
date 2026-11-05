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
"zpw_sek" — the cookie-name assumption is flagged in bao-cao.md).
"""

import json
import os
import socket
import threading
import urllib.error
import urllib.request

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import contacts as contacts_mod
from . import engine_seam
from . import protocol
from . import qr_login
from . import session as session_mod
from . import signaling as signaling_mod
from .crypto import make_device_id

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
        self.thread = None

    # -- session helpers -------------------------------------------------
    def public_status(self):
        with self.lock:
            if self.session and self.session.get("zpw_sek"):
                return {"login": True,
                        "uid": self.session.get("uid", ""),
                        "phonenum": self.session.get("phonenum", ""),
                        "engine": engine_seam.SEAM.status()}
            return {"login": False, "uid": "", "phonenum": "",
                    "engine": engine_seam.SEAM.status()}

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
            # Session established: fetch login info (cookie auth).
            login_info = self._fetch_login_info(grant)
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

    def _fetch_login_info(self, grant):
        """GET getLoginInfo with the fresh session cookie.
        Contract (mock-tested): common params + session cookie; the
        response data carries config, dkey and zpw_enk. Exact extra
        params, if the real server wants any, are a real-test fix
        (flagged in bao-cao.md)."""
        transport = make_transport(grant["zpw_sek"])
        params = protocol.common_params()
        url = protocol.build_url(protocol.AUTH_DOMAIN,
                                 "/api/login/getLoginInfo", params)
        status, payload = transport(url, timeout=30)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("getLoginInfo: network status=%s" % status)
        if payload.get("error_code") != 0:
            raise RuntimeError("getLoginInfo: error_code=%s %s" % (
                payload.get("error_code"), payload.get("error_message", "")))
        data = payload.get("data") or {}
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
                return self._send_json({"friends": book.friends(),
                                        "groups": book.groups()})
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
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("zalo-pc-qr app on http://%s:%d (data: %s)"
          % (HOST, PORT, DATA_DIR))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
