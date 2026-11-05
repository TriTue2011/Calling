"""Mock Zalo server for offline tests.

Deliberately independent from the client code: AES goes through the
`openssl` CLI, signkey/enk derivations are re-implemented here from
the protocol spec, so a client bug cannot hide behind shared code.

Scenarios are switched via flags on the MockZalo instance:
  scan_mode:    "ok" | "reject" | "timeout" | "trust"
  confirm_mode: "ok" | "reject" | "no_sek"
  reqqr_mode:   "ok" | "rate_limit" | "force_plaintext_once"
  logininfo_mode: "ok" | "error102"
  friends_mode / groups_mode: "ok" | "error602" | "empty"
    "empty" simulates an account with no friends / no groups:
    friends data is [], groups data is {groups: [], hasMore: False,
    total: 0} — the client must report empty rows, not an error.

Response shapes returned by the mock are the REAL server shapes
(bundle compact-app-pc, verified 2026-11-05 — the old mock returned
pre-formatted {userId, displayName} items, which is NOT what the
server sends and hid the _extract_rows gaps):
  friends: data is a BARE ARRAY of profile items
    {userId, displayName|zaloName, avatar};
  groups (addon path, §7i in bao-cao.md — zca-js getAllGroups +
    getGroupInfo, also in the PC command table as codes 12027/12028):
    GET /api/group/getlg/v4 (no body) -> {version, gridVerMap:
    {groupId: version}}; POST /api/group/getmg-v2 (form body
    params=<AES {gridVerMap: "{groupId: 0}"}>) -> {removedsGroup,
    unchangedsGroup, gridInfoMap: {groupId: {groupId, name, avt,
    fullAvt, creatorId, topMember: [{id, ...}], totalMember, ...}}}.
    The old getlg/v3 list path was the PC client's list path, not
    the addon's — it is no longer served (the client must not call
    it); the mock 404s it like an unknown route.

Post-login responses are a TWO-LAYER envelope (bundle kCOK unwrap,
verified 2026-11-05 — the previous mock returned the inner data
directly, which hid the 0/0 bug: the client returned
payload["data"] without decrypting, so both endpoints silently
parsed an encrypted STRING as "no items"):
  outer: {error_code: 0, data: "<AES-256-CBC base64>"}
  inner: AES-decrypt data with the session key, JSON-parse ->
    {error_code: 0, data: <payload above>}.
  _postlogin_envelope() builds this shape; error paths (602 etc.)
  stay plain outer errors, as the real server sends them.
"""

import base64
import hashlib
import json
import re
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
        # Contacts error simulation: "ok" | "error602" (server rejects
        # the call with the real 602 message, as in the 2026-11-05 bug).
        self.friends_mode = "ok"
        self.groups_mode = "ok"
        self._friends_first = True  # first friends call must send init=1
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
                    status, obj = mock.route(
                        parsed.path, qs, self.headers, parsed.query)
                except Exception as e:  # noqa: BLE001 - mock must answer
                    status, obj = 500, {"error_code": -1,
                                        "error_message": "mock: %s" % e}
                body = json.dumps(obj).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                qs = {k: v[0] for k, v in
                      urllib.parse.parse_qs(parsed.query).items()}
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length \
                    else ""
                mock.seen.append((parsed.path, qs, dict(self.headers)))
                try:
                    status, obj = mock.route_post(
                        parsed.path, qs, self.headers, raw)
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
    def route(self, path, qs, headers, raw_qs=""):
        if path == "/api/login/reqqr":
            return 200, self._reqqr(qs)
        if path == "/scan":
            return self._scan()
        if path == "/confirm":
            return self._confirm()
        if path == "/api/login/getLoginInfo":
            return 200, self._logininfo(qs, headers)
        if path.startswith("/api/voicecall/"):
            return 200, self._voicecall(path, qs, headers, raw_qs)
        if path == "/api/social/friend/getfriends":
            return 200, self._friends(qs, headers, raw_qs)
        if path == "/api/group/getlg/v4":
            return 200, self._groups_v4(qs, headers)
        return 404, {"error_code": 404, "error_message": "mock no route"}

    def route_post(self, path, qs, headers, raw_body=""):
        if path == "/api/group/getmg-v2":
            return 200, self._group_info_multi(qs, headers, raw_body)
        return 404, {"error_code": 404, "error_message": "mock no route"}

    def _check_common(self, qs, headers, name, strict_type=True):
        """Cookie + zpw_ver=695/zpw_type=30 (strict) or "30"/"embed"
        (lenient, friends only). Shared by GET endpoints with and
        without a params body."""
        assert headers.get("Cookie"), "%s needs Cookie" % name
        assert qs.get("zpw_ver") == "695", "%s common params: %s" % (name, qs)
        if strict_type:
            assert qs.get("zpw_type") == "30", \
                "%s common params: %s" % (name, qs)
        else:
            assert qs.get("zpw_type") in ("30", "embed"), \
                "%s common params: %s" % (name, qs)

    def _check_postlogin(self, qs, headers, raw_qs, name,
                         strict_type=True):
        """Strict contract shared by post-login GET endpoints (lesson
        from bug 102: a loose mock lets a wrong request slip through).
        Cookie + zpw_ver=695/zpw_type=30 + the params value fully
        percent-encoded (encodeURIComponent parity: no literal '/' or
        '+' inside it, only %2F/%2B).
        zpw_type=30 is the real PC client's value (bundle config:
        apiType:"embed"===__ZaBUNDLENAME__?31:30, bundle name
        "compact-app-pc" -> 30). The old code sent zpw_type="embed":
        profile-wpa (friends) tolerates it, but group-wpa rejects it
        with 602 — observed live twice (v1 and v3). So friends is
        checked lenient (strict_type=False: accepts "30" or "embed"),
        while groups/voicecall are strict (only "30")."""
        self._check_common(qs, headers, name, strict_type)
        m = re.search(r"(?:^|&)params=([^&]*)", raw_qs or "")
        assert m, "%s needs raw params value" % name
        assert "/" not in m.group(1) and "+" not in m.group(1), \
            "%s params not fully percent-encoded: %s" % (name, m.group(1))

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
            assert qs.get("type") == "30", qs
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
            assert parts[0] == "30", parts
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
            assert qs.get("type") == "30", qs
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
            assert parts[0] == "30", parts
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
        assert qs.get("type") == "30", qs
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

    def _postlogin_envelope(self, payload):
        """Wrap a payload in the real two-layer post-login envelope:
        outer {error_code: 0, data} where data is the inner
        {error_code: 0, data: payload} AES-256-CBC encrypted with the
        session key (TEST_SESSION_KEY) — exactly what the real server
        sends for friends/groups/voicecall (bundle kCOK unwrap)."""
        inner = json.dumps({"error_code": 0, "data": payload})
        key = base64.b64decode(TEST_SESSION_KEY)
        enc = _openssl_aes(key, inner.encode("utf-8"))
        return {"error_code": 0, "data": base64.b64encode(enc).decode()}

    def _postlogin_envelope_error(self, code, message):
        """Same two-layer envelope, but the INNER error_code is
        non-zero — exactly how the real server answers a bad
        requestcall (inner 114 "Tham số không hợp lệ", observed live
        2026-11-05 17:31). The client surfaces it via
        decode_postlogin_data as "response inner error_code=114 ...".
        An outer error would be the WRONG shape here: the request
        reached the server and the envelope was fine."""
        inner = json.dumps({"error_code": code, "error_message": message,
                            "data": {}})
        key = base64.b64decode(TEST_SESSION_KEY)
        enc = _openssl_aes(key, inner.encode("utf-8"))
        return {"error_code": 0, "data": base64.b64encode(enc).decode()}

    def _voicecall(self, path, qs, headers, raw_qs=""):
        self._check_postlogin(qs, headers, raw_qs, "voicecall")
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        # route() passes the FULL path ("/api/voicecall/requestcall");
        # the contract check below keys on the sub-path.
        sub = path[len("/api/voicecall/"):]
        if sub in ("requestcall", "group/requestcall"):
            # requestcall contract (bundle class wZ + ZaloCall.exe
            # %u callId; §7k in bao-cao.md): typeRequest must be a
            # real call type (1-1: 1 audio / 3 video; group: 5
            # audio / 6 video) and callId must be a JSON NUMBER in
            # uint32 range. The pre-fix body (typeRequest 0, callId
            # a 13-digit string) is answered with the real server's
            # inner 114, so the test reproduces the live failure
            # instead of hiding it behind a mock assertion.
            want_types = ((1, 3) if sub == "requestcall"
                          else (5, 6))
            call_id = body.get("callId")
            id_ok = (isinstance(call_id, int)
                     and not isinstance(call_id, bool)
                     and 1 <= call_id <= 2 ** 32 - 1)
            id_field = ("calleeId" if sub == "requestcall"
                        else "groupId")
            if (body.get("typeRequest") not in want_types
                    or not id_ok or not body.get(id_field)):
                return self._postlogin_envelope_error(
                    114, "Tham số không hợp lệ")
            return self._postlogin_envelope(
                {"ok": True, "path": path, "body": body})
        # 1-1 requestcall carries imei; group/requestcall carries
        # groupId instead (bundle: {groupId, callId, typeRequest,
        # data, partners}, no imei) — both are valid voicecall bodies.
        assert (body.get("imei") or "toId" in body
                or "groupId" in body), body
        return self._postlogin_envelope(
            {"ok": True, "path": path, "body": body})

    def _friends(self, qs, headers, raw_qs=""):
        if self.friends_mode == "error602":
            return {"error_code": 602,
                    "error_message": "zpw_type bị thiếu hoặc không đúng",
                    "data": {}}
        # profile-wpa tolerates zpw_type="embed" (observed live: friends
        # passed with "embed" while groups 602'd) — lenient check.
        self._check_postlogin(qs, headers, raw_qs, "friends",
                              strict_type=False)
        # Real client: init=1 on the FIRST friends load only.
        if self._friends_first:
            assert qs.get("init") == "1", "first friends load needs init=1"
            self._friends_first = False
        else:
            assert "init" not in qs, "init only on first friends load"
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        # Real getFriendsList body: {incInvalid:1, page:1, count:20000,
        # avatar_size:160, actiontime:0, imei}. The pre-fix code missed
        # avatar_size — the mock must reject that (bug 102 lesson).
        assert body["count"] == 20000 and body["page"] == 1, body
        assert body.get("avatar_size") == 160, \
            "friends body needs avatar_size=160: %s" % body
        assert body.get("actiontime") == 0 and body.get("imei"), body
        if self.friends_mode == "empty":
            return self._postlogin_envelope([])
        # Real shape: data is a BARE ARRAY of profile items (the
        # client's FriendListManager checks Array.isArray(data)).
        # "Ban B" carries only zaloName (no displayName) and "Ban C"
        # only snake_case fields — both must still resolve to a name
        # (UI fallback: displayName || zaloName; the reformatter also
        # accepts zalo_name / display_name / uid).
        return self._postlogin_envelope([
            {"userId": "20001", "displayName": "Ban A", "avatar": ""},
            {"userId": "20002", "zaloName": "Ban B", "avatar": ""},
            {"userId": "20003", "display_name": "Ban C",
             "zalo_name": "Ban C", "avatar": ""}])

    def _groups_v4(self, qs, headers):
        """getlg/v4 (addon path): GET, no body, no pagination — just
        the common params. Returns the version map {version,
        gridVerMap: {groupId: version}}. group-wpa validates
        zpw_type strictly (only "30"); "embed" is answered with the
        real server's 602, as observed live."""
        if self.groups_mode == "error602":
            return {"error_code": 602,
                    "error_message": "zpw_type bị thiếu hoặc không đúng",
                    "data": {}}
        if qs.get("zpw_type") == "embed":
            return {"error_code": 602,
                    "error_message": "zpw_type bị thiếu hoặc không đúng",
                    "data": {}}
        self._check_common(qs, headers, "groups v4")
        assert "params" not in qs, "v4 takes no params body: %s" % qs
        if self.groups_mode == "empty":
            return self._postlogin_envelope(
                {"version": "1", "gridVerMap": {}})
        return self._postlogin_envelope(
            {"version": "1",
             "gridVerMap": {"30001": "1", "30002": "1"}})

    def _group_info_multi(self, qs, headers, raw_body=""):
        """getmg-v2 (addon path): POST, form body params=<AES JSON>
        with {gridVerMap: "<JSON string of {groupId: 0}>"}.
        Returns {removedsGroup, unchangedsGroup, gridInfoMap} with
        one group info per requested id (name, avt, creatorId,
        topMember [{id, ...}], totalMember)."""
        if self.groups_mode == "error602":
            return {"error_code": 602,
                    "error_message": "zpw_type bị thiếu hoặc không đúng",
                    "data": {}}
        self._check_common(qs, headers, "group info")
        # The params value must be fully percent-encoded in the RAW
        # form body (encodeURIComponent parity) — check before
        # parse_qsl decodes it back (decoded base64 legitimately
        # contains '/' and '+').
        m = re.search(r"(?:^|&)params=([^&]*)", raw_body or "")
        assert m, "getmg-v2 needs params form body"
        assert "/" not in m.group(1) and "+" not in m.group(1), \
            "getmg-v2 params not fully percent-encoded"
        form = dict(urllib.parse.parse_qsl(raw_body or ""))
        assert "params" in form, "getmg-v2 needs params form body"
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(form["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        # The map value must be a JSON STRING (both real clients do
        # gridVerMap: JSON.stringify(map)), not a nested object.
        assert isinstance(body.get("gridVerMap"), str), \
            "getmg-v2 body needs gridVerMap as a JSON string: %s" % body
        ver_map = json.loads(body["gridVerMap"])
        assert isinstance(ver_map, dict) and ver_map, \
            "getmg-v2 gridVerMap must be a non-empty map: %s" % ver_map
        assert all(v == 0 for v in ver_map.values()), \
            "getmg-v2 gridVerMap values must be 0: %s" % ver_map
        if self.groups_mode == "empty":
            return self._postlogin_envelope(
                {"removedsGroup": [], "unchangedsGroup": [],
                 "gridInfoMap": {}})
        infos = {
            "30001": {"groupId": "30001", "name": "Nhom X",
                      "avt": "avt-x", "fullAvt": "", "creatorId": "20001",
                      "topMember": [{"id": "20001", "displayName": "Ban A"},
                                    {"id": "20002", "displayName": "Ban B"}],
                      "totalMember": 2, "type": 1},
            "30002": {"groupId": "30002", "name": "Nhom Y",
                      "avt": "", "fullAvt": "", "creatorId": "20001",
                      "topMember": [{"id": "20001", "displayName": "Ban A"}],
                      "totalMember": 1, "type": 1},
        }
        grid_info = {gid: infos[gid] for gid in ver_map if gid in infos}
        return self._postlogin_envelope(
            {"removedsGroup": [], "unchangedsGroup": [],
             "gridInfoMap": grid_info})
