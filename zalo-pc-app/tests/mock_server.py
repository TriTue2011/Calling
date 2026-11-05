"""Mock Zalo server for offline tests.

Deliberately independent from the client code: AES goes through the
`openssl` CLI, signkey/enk derivations are re-implemented here from
the protocol spec, so a client bug cannot hide behind shared code.

Scenarios are switched via flags on the MockZalo instance:
  scan_mode:    "ok" | "reject" | "timeout" | "trust"
  confirm_mode: "ok" | "reject" | "no_sek"
  reqqr_mode:   "ok" | "rate_limit" | "force_plaintext_once"
  logininfo_mode: "ok" | "error102"
"""

import base64
import hashlib
import json
import subprocess
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEST_PARAM_KEY = "TEST_PARAM_KEY_32_CHARS_LONG_XXX"  # 32 chars, test only
TEST_SESSION_KEY = base64.b64encode(b"T" * 32).decode()  # zpw_enk
SIGN_SALT = "zsecure"


def _openssl_aes(key_bytes, data, decrypt=False):
    args = ["openssl", "enc", "-aes-256-cbc", "-K", key_bytes.hex(),
            "-iv", "00" * 16]
    if decrypt:
        args.append("-d")
    p = subprocess.run(args, input=data, capture_output=True, timeout=30)
    assert p.returncode == 0, p.stderr.decode()
    return p.stdout


def _even_odd(s):
    even = "".join(c for i, c in enumerate(s) if i % 2 == 0)
    odd = "".join(c for i, c in enumerate(s) if i % 2 == 1)
    return even, odd


def derive_enk(zcid, zcid_ext):
    md5_ext = hashlib.md5(zcid_ext.encode()).hexdigest().upper()
    even_md5, _ = _even_odd(md5_ext)
    even_z, odd_z = _even_odd(zcid)
    return even_md5[:8] + even_z[:12] + odd_z[::-1][:12]


def signkey_check(api_name, query):
    keys = sorted(query.keys())
    blob = SIGN_SALT + api_name + "".join(query[k] for k in keys)
    return hashlib.md5(blob.encode()).hexdigest()


class MockZalo:
    def __init__(self):
        self.scan_mode = "ok"
        self.confirm_mode = "ok"
        self.reqqr_mode = "ok"
        self.logininfo_mode = "ok"
        self.seen = []  # (path, query, headers) log
        self._plaintext_forced = False
        self.server = None
        self.port = 0
        self.base = ""

    # -- server plumbing -------------------------------------------------
    def start(self):
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                qs = {k: v[0] for k, v in
                      urllib.parse.parse_qs(parsed.query).items()}
                mock.seen.append((parsed.path, qs, dict(self.headers)))
                try:
                    status, obj = mock.route(parsed.path, qs, self.headers)
                except Exception as e:  # noqa: BLE001 - mock must answer
                    status, obj = 500, {"error_code": -1,
                                        "error_message": "mock: %s" % e}
                body = json.dumps(obj).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()
        return self

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    # -- routes ------------------------------------------------------------
    def route(self, path, qs, headers):
        if path == "/api/login/reqqr":
            return 200, self._reqqr(qs)
        if path == "/scan":
            return self._scan()
        if path == "/confirm":
            return self._confirm()
        if path == "/api/login/getLoginInfo":
            return 200, self._logininfo(qs, headers)
        if path.startswith("/api/voicecall/"):
            return 200, self._voicecall(path, qs, headers)
        if path == "/api/social/friend/getfriends":
            return 200, self._friends(qs, headers)
        if path == "/api/group/getlg":
            return 200, self._groups(qs, headers)
        return 404, {"error_code": 404, "error_message": "mock no route"}

    def _reqqr(self, qs):
        if self.reqqr_mode == "rate_limit":
            return {"error_code": 12345, "error_message": "rate",
                    "data": {"time_left": 61000}}
        if self.reqqr_mode == "force_plaintext_once" \
                and not self._plaintext_forced:
            self._plaintext_forced = True
            return {"error_code": 19000, "error_message": "need plaintext",
                    "data": {}}
        qr = {
            "base64_qr": base64.b64encode(b"FAKEPNG").decode(),
            "chk_wait_scan": self.base + "/scan",
            "chk_wait_cfirm": self.base + "/confirm",
            "qr_retry": 3, "qr_timeout": 5,
            "token_id": "tok1", "ntk": "ntk1", "qr_cnt": "1",
            "uid": "", "master_id": "", "regen_qr": 0,
        }
        if "zcid" in qs:
            # Encrypted mode: verify envelope with openssl + hashlib.
            assert qs.get("type") == "embed", qs
            assert qs.get("client_version") == "695", qs
            assert qs.get("enc_ver") == "v2", qs
            expect_sig = signkey_check("reqqr", {
                k: v for k, v in qs.items() if k != "signkey"})
            assert qs.get("signkey") == expect_sig, (
                "signkey mismatch: %s != %s" % (qs.get("signkey"), expect_sig))
            zcid_raw = _openssl_aes(
                TEST_PARAM_KEY.encode(), bytes.fromhex(qs["zcid"]),
                decrypt=True)
            parts = zcid_raw.decode("utf-8").split(",")
            assert parts[0] == "embed", parts
            enk = derive_enk(qs["zcid"], qs["zcid_ext"])
            plain = _openssl_aes(
                enk.encode(), base64.b64decode(qs["params"]), decrypt=True)
            params = json.loads(plain.decode("utf-8"))
            assert parts[1] == params["imei"], (parts, params)
            assert params["self_g"] == 0 and params["qr_form"] == 0
            # Response data is AES-encrypted with enk (like the real server).
            enc = _openssl_aes(enk.encode(),
                               json.dumps(qr).encode("utf-8"))
            return {"error_code": 0,
                    "data": base64.b64encode(enc).decode()}
        # Plaintext mode: params inline + signkey.
        expect_sig = signkey_check("reqqr", {
            k: v for k, v in qs.items() if k != "signkey"})
        assert qs.get("signkey") == expect_sig, "plaintext signkey mismatch"
        assert qs.get("imei"), "plaintext reqqr needs imei"
        assert qs.get("self_g") == "0" and qs.get("qr_form") == "0"
        return {"error_code": 0, "data": qr}

    def _scan(self):
        if self.scan_mode == "timeout":
            return 408, {"error_code": 408, "error_message": "timeout"}
        if self.scan_mode == "reject":
            return 200, {"error_code": 18010, "error_message": "rejected",
                         "data": {}}
        if self.scan_mode == "trust":
            return 200, {"error_code": 0, "data": {
                "avatar": "", "display_name": "Tester",
                "link_data": {"enc_link_data": "AAA",
                              "enc_link_hmac": "BBB"}}}
        return 200, {"error_code": 0, "data": {
            "avatar": "", "display_name": "Tester", "link_data": {}}}

    def _logininfo(self, qs, headers):
        """getLoginInfo, enforcing the real PC contract (renderer API
        class getLoginInfo): session cookie zpw_sek + login envelope
        (imei/computer_name/language/ts + type/client_version/signkey,
        encrypted when a param cipher key is used). The old mock only
        required a Cookie header, which let the missing-envelope bug
        (server error 102) pass offline."""
        if self.logininfo_mode == "error102":
            return {"error_code": 102,
                    "error_message": "The session key was improperly "
                    "submitted or has reached its timeout. Direct the "
                    "user to log in again to obtain another key",
                    "data": {}}
        assert headers.get("Cookie") == "zpw_sek=sek-test", (
            "getLoginInfo needs zpw_sek cookie, got: %r"
            % (headers.get("Cookie"),))
        data = {
            "dkey": "dkey-test",
            "zpw_enk": TEST_SESSION_KEY,
            "config": {"zpw_service_map_new": {},
                       "zpw_ws": "wss://mock.invalid/ws"}}
        if "zcid" in qs:
            assert qs.get("type") == "embed", qs
            assert qs.get("client_version") == "695", qs
            assert qs.get("enc_ver") == "v2", qs
            expect_sig = signkey_check("getlogininfo", {
                k: v for k, v in qs.items() if k != "signkey"})
            assert qs.get("signkey") == expect_sig, (
                "signkey mismatch: %s != %s" % (qs.get("signkey"), expect_sig))
            zcid_raw = _openssl_aes(
                TEST_PARAM_KEY.encode(), bytes.fromhex(qs["zcid"]),
                decrypt=True)
            parts = zcid_raw.decode("utf-8").split(",")
            assert parts[0] == "embed", parts
            enk = derive_enk(qs["zcid"], qs["zcid_ext"])
            plain = _openssl_aes(
                enk.encode(), base64.b64decode(qs["params"]), decrypt=True)
            params = json.loads(plain.decode("utf-8"))
            assert parts[1] == params["imei"], (parts, params)
            assert params["computer_name"] and params["language"], params
            assert str(params["ts"]).isdigit(), params
            enc = _openssl_aes(enk.encode(), json.dumps(data).encode())
            return {"error_code": 0,
                    "data": base64.b64encode(enc).decode()}
        expect_sig = signkey_check("getlogininfo", {
            k: v for k, v in qs.items() if k != "signkey"})
        assert qs.get("signkey") == expect_sig, "plaintext signkey mismatch"
        assert qs.get("imei"), "plaintext getLoginInfo needs imei"
        assert qs.get("computer_name"), "needs computer_name"
        assert qs.get("language"), "needs language"
        assert qs.get("ts", "").isdigit(), "needs ts (ms)"
        assert qs.get("type") == "embed", qs
        assert qs.get("client_version") == "695", qs
        return {"error_code": 0, "data": data}

    def _confirm(self):
        if self.confirm_mode == "reject":
            return 200, {"error_code": 18010, "error_message": "rejected",
                         "data": {}}
        if self.confirm_mode == "no_sek":
            return 200, {"error_code": 0, "data": {
                "uid": "10001", "dkey": "dkey-test",
                "profile": {"phonenum": "+84000000000"},
                "needSyncMsg": False, "cptch_cert": "cert",
                "zpw_sek": "", "zpw_kt": "kt-test", "devices": []}}
        return 200, {"error_code": 0, "data": {
            "uid": "10001", "dkey": "dkey-test",
            "profile": {"phonenum": "+84000000000"},
            "needSyncMsg": False, "cptch_cert": "cert",
            "zpw_sek": "sek-test", "zpw_kt": "kt-test", "devices": []}}

    def _voicecall(self, path, qs, headers):
        assert headers.get("Cookie"), "voicecall needs Cookie"
        assert qs.get("zpw_ver") == "695" and qs.get("zpw_type") == "embed"
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert body.get("imei") or "toId" in body, body
        return {"error_code": 0, "data": {"ok": True, "path": path,
                                          "body": body}}

    def _friends(self, qs, headers):
        assert headers.get("Cookie"), "friends needs Cookie"
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert body["count"] == 20000 and body["page"] == 1, body
        return {"error_code": 0, "data": {
            "friends": [{"userId": "20001", "displayName": "Ban A",
                         "avatar": ""},
                        {"userId": "20002", "displayName": "Ban B",
                         "avatar": ""}]}}

    def _groups(self, qs, headers):
        assert headers.get("Cookie"), "groups needs Cookie"
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        json.loads(plain.decode("utf-8"))  # must be valid JSON
        return {"error_code": 0, "data": {
            "groups": [{"userId": "30001", "displayName": "Nhom X",
                        "avatar": ""}]}}
