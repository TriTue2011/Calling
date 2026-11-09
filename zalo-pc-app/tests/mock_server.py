"""Mock Zalo server for offline tests.

Deliberately independent from the client code: AES goes through the
`openssl` CLI, signkey/enk derivations are re-implemented here from
the protocol spec, so a client bug cannot hide behind shared code.

Scenarios are switched via flags on the MockZalo instance:
  scan_mode:    "ok" | "reject" | "timeout" | "trust"
  confirm_mode: "ok" | "reject" | "no_sek"
  reqqr_mode:   "ok" | "rate_limit" | "force_plaintext_once"
  logininfo_mode: "ok" | "error102" | "nested_config" |
  "no_endpoints". "ok" tra shape THAT cua getLoginInfo (bundle
  compact-app-pc @11816376: toan bo data CHINH LA config —
  zpw_chts_new / zpw_ctrs_new / zpw_service_map_new / zpw_conf /
  zpw_ws o TOP-LEVEL cua data, khong phai duoi data.config).
  "nested_config" tra shape cu (poll URLs duoi data.config) de
  chung minh fallback van doc duoc. "no_endpoints" tra thanh
  cong nhung khong co poll URLs o dau ca (phien that nhung
  server khong cap endpoint — truong hop live 2026-11-07).
  friends_mode / groups_mode: "ok" | "error602" | "empty" | "rate429"
    "empty" simulates an account with no friends / no groups:
    friends data is [], groups data is {groups: [], hasMore: False,
    total: 0} — the client must report empty rows, not an error.
    "rate429" simulates Zalo rate-limiting the endpoint with a real
    HTTP 429 (the shape in the live 2026-11-05 log: "GET ...
    getfriends network status=429") — the client must serve cache
    + backoff instead of hammering again.

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
import time
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
        # Ctrl long-poll simulation (99101): khi dat, /lp-ctl/ tra
        # mot event file_done cho fileId "file-1" voi URL nay (de
        # test gui file end-to-end qua poller that); None thi tra
        # controls rong.
        self.ctrl_file_url = None
        # Contacts error simulation: "ok" | "error602" (server rejects
        # the call with the real 602 message, as in the 2026-11-05 bug)
        # | "rate429" (HTTP 429, the live 2026-11-05 rate limit).
        self.friends_mode = "ok"
        self.groups_mode = "ok"
        # Endcall simulation (§7m): "ok" | "error" | "slow".
        # "error" makes `endcall` (11306) / `group/endcall`
        # (12438) fail with an inner error, so tests can prove the
        # app still ends the call locally (the live 18:06 symptom:
        # End pressed, the call stayed "ringing" because
        # /api/call/end only marked the log ended when the Zalo
        # endcall succeeded). "slow" sleeps 2s before answering,
        # so tests can prove the log clears before the Zalo
        # round-trip finishes (the "End is slow/delayed" symptom).
        self.endcall_mode = "ok"
        # Cancel simulation (11305): "ok" | "error" | "slow", same
        # meanings as endcall_mode — the app must end an unanswered
        # call with CANCEL, so a rejected/slow cancel needs the same
        # local-first treatment as a rejected/slow endcall.
        self.cancel_mode = "ok"
        # Voicecall request-step simulation (§7l): "ok" | "error114"
        # | "status_error". "error114" makes the follow-up `request`
        # (11301) / `group/request` (12434) step fail with the real
        # server's inner 114, so tests can prove the app treats that
        # step as best-effort (the call itself still succeeds).
        # "status_error" makes the step return a decoded data with
        # a non-zero status instead (the shape a live data-level
        # rejection would take): the app must read the status and
        # end the call early (server_rejected), not treat the step
        # as sent.
        self.request_mode = "ok"
        # 11300 response material (§7n): when set (a dict), it is
        # merged into the decoded requestcall response data, so a
        # test can drive the app with a REAL-shaped 11300 reply —
        # e.g. servers as a list of dicts keyed rtcpaddr/rtpIPv6
        # (seen live 2026-11-05 22:58 +07), sessId, srtpKey,
        # token. Default None keeps the old behaviour (no
        # allocation material: the no-allocation tests). Values
        # here are test-only fixtures, never real credentials.
        self.requestcall_data = None
        # Call-delivery tracking (§7l): call_id -> {"steps": [...],
        # "delivered": bool}. A call is "requested" once its
        # requestcall (11300/12433) arrives and "delivered" only
        # once the follow-up request step (11301/12434) arrives with
        # the same callId — the mock's model of the real server,
        # which holds an invitation with no media endpoints instead
        # of ringing the far end (observed live 2026-11-05 17:51).
        self.voice_calls = {}
        # slow_seconds: làm Zalo trả chậm từng đó giây trên các
        # endpoint danh bạ (friends / getlg/v4 / getmg-v2) — để pin
        # stale-while-revalidate: load có cache cũ phải trả NGAY
        # thay vì chờ Zalo chậm; chỉ load chưa có cache mới chờ.
        self.slow_seconds = 0
        self._friends_first = True  # first friends call must send init=1
        # Pin list simulation: "ok" | "error212" (server chua co
        # danh sach ghim — PinDataManager dat version 0 + day cache
        # client len; xem services._set_pinned).
        self.pin_list_mode = "ok"
        # Sync long-poll simulation (99100): "messages" (tra 1 tin
        # 1-1 + 1 tin nhom, kieu shape that) | "empty" (data "" —
        # long-poll het han, khong co tin) | "error69" (error -69,
        # server bao dung retry). Mac dinh "messages".
        self.poll_mode = "messages"
        # Voice upload simulation (§7n — tin nhan thoai, DUONG HAI
        # BUOC 12060/12063 + asyncfile/msg 11777/13001 — xem
        # chat.send_voice): "ok" | "error112" | "error112_once".
        # "error112" tra inner 112 moi lan goi chunk (buoc 1) hoac
        # asyncfile (buoc 2, qua voice_send_mode); "error112_once"
        # chi tra 112 o lan goi dau tien roi ok — de pin co che thu
        # lai cua client that (bundle coi 112 la tam thoi, thu lai
        # sau 1-5 giay). voice_upload_calls dem so lan goi chunk
        # voice/upload; voice_send_calls dem so lan goi asyncfile/
        # msg; upload_bodies luu moi params AES da giai ma cua moi
        # lan goi chunk (de test khang dinh clientId giong nhau
        # giua cac lan thu lai); voice_send_bodies luu body
        # asyncfile/msg. "error133" chi con ap dung cho duong truc
        # tiep voicemp3/sendmp3 cu (da ngung dung — giu lai trong
        # _chat_upload de tai lieu hoa loi that 2026-11-05).
        self.voice_upload_mode = "ok"
        self.voice_upload_calls = 0
        # File thuong (Word/Excel/PDF — DUONG HAI BUOC asyncfile,
        # khong phai sharefile_full chet): "ok" | "empty".
        # file_upload_* dem/ghi cac lan goi chunk asyncfile/upload;
        # file_send_* dem/ghi cac lan goi buoc 2 asyncfile/msg.
        # "empty" o buoc 2 tra envelope data rong ({} — Zalo tra
        # 200/error_code=0 nhung khong tao tin nao) de pin rang
        # client phai bao loi that thay vi tra ok:true (loi cam
        # 07/11, giong send_photo truoc khi sua).
        self.file_upload_calls = 0
        self.file_upload_bodies = []
        # file_upload_extra: truong phu THEM vao data cua chunk
        # cuoi (vd. {"url": ...}) — de pin rang buoc 2 KHONG duoc
        # lay fileUrl tu response chunk (loi 114): bundle chi lay
        # URL tu async event file_done qua waitAsyncFileInfo.
        self.file_upload_extra = {}
        self.file_send_mode = "ok"
        self.file_send_calls = 0
        self.file_send_bodies = []
        # voice_upload_extra: truong phu THEM vao data cua chunk
        # cuoi (vd. {"url": ..., "amr": ..., "aac": ...}) — de pin
        # rang buoc 2 KHONG duoc lay fileUrl/aacUrl tu response
        # chunk (loi 114): bundle chi lay cac URL do tu async event
        # voice_aac_success qua waitAsyncFileInfo, khong bao gio tu
        # chunk-response (xem test_voice_112.py).
        self.voice_upload_extra = {}
        self.voice_send_mode = "ok"
        self.voice_send_calls = 0
        self.voice_send_bodies = []
        self.upload_bodies = []
        self.seen = []  # (path, query, headers) log
        self.seen_post = []  # (path, query) log — chi cac POST
        self.seen_post_raw = []  # (path, raw bytes) — de test doc
        # noi dung file that gui len (vd. fileContent co phai MP3
        # that khong); them vao vi do_POST decode utf-8 mat byte.
        self._plaintext_forced = False
        self.server = None
        self.port = 0
        self.base = ""

    def voice_call_state(self, call_id):
        """{"requested": bool, "delivered": bool, "steps": [...]}
        for one callId — the test hook for §7l delivery."""
        entry = self.voice_calls.get(call_id, {"steps": [],
                                               "delivered": False})
        steps = list(entry["steps"])
        requested = ("requestcall" in steps
                     or "group/requestcall" in steps)
        return {"requested": requested,
                "delivered": bool(entry["delivered"]), "steps": steps,
                "requestcall_codec": entry.get("requestcall_codec"),
                "request_codec": entry.get("request_codec"),
                "answer_codec": entry.get("answer_codec"),
                "answer_addresses": entry.get("answer_addresses")}

    def server_call_state(self, call_id):
        """The SERVER-side call state the mock models for one callId:
        {"state": "ringing"|"connected"|"ended"|None,
         "record": "missed"|"ended"|None,
         "request_addresses": {"rtcp": ..., "rtp": ...} | None,
         "steps": [...]}.

        The model is the CONTRACT the 5-pcap re-analysis
        (2026-11-08) proves for the real flow, and the app must
        satisfy it:
        * requestcall (11300) opens the call as "ringing" — never
          "connected" at dial, never "missed" at dial. A missed
          call is only recorded AFTER a call ends without an
          answer (ring timeout ~30 s, caller ends first, or
          callee declines); the server syncs it via tt-chat4
          0.1-0.6 s after the end.
        * answerack (11304, the caller ACKing the peer's answer)
          moves the call to "connected". The caller NEVER sends
          the answer signal itself (11303 answer / 11302 ringring
          are callee signals); sending one at dial would make the
          server switch to "connected" before the peer agrees.
        * cancel (11305) withdraws an UNANSWERED invitation, so
          the call is recorded "missed". Sent for a CONNECTED call
          it still records "missed" — that is the spurious
          "missed" the user reported on 2026-11-08 (an answered
          call killed by cancel at the 30 s ring timeout). An
          answered call must therefore end with endcall, never
          cancel.
        * endcall (11306) records "ended" when the call was
          connected, "missed" when it ends still ringing (the peer
          never agreed).
        This models the contract, not the real server's internals
        (TLS-encrypted, unobservable from here); the live test is
        what proves the real server behaves this way. The mock
        records the 11301 addresses so tests can assert the app
        never sends empty ones (the real client always carries a
        real relay address); it still does NOT reject empty
        addresses, because no server rejection was observed.
        """
        entry = self.voice_calls.get(
            call_id, {"steps": [], "delivered": False,
                      "server_state": None, "record": None,
                      "request_addresses": None})
        return {"state": entry.get("server_state"),
                "record": entry.get("record"),
                "request_addresses": entry.get("request_addresses"),
                "steps": list(entry["steps"])}

    def _record_voice_step(self, call_id, step, body=None):
        """Record one voicecall step for a callId; the follow-up
        request step only counts as delivery when a requestcall for
        the same callId was seen first (the real server correlates
        the two steps by callId). Also advances the modeled
        server-side call state (see server_call_state): requestcall
        opens "ringing", answerack moves to "connected", cancel /
        endcall close the call and set the record ("missed" when the
        call ends without the peer ever agreeing, "ended" when it
        ends connected). `body` (the 11301 request body, when given)
        is kept as request_addresses so tests can assert the media
        endpoints the app sent are real relay addresses, never
        empty. `body`'s `codec` is kept too (requestcall_codec /
        request_codec) so tests can assert the WIRE codec string
        on both steps (11300 + 11301) — the zca-js codec fix.
        The callee's "answer" (11303) is recorded the same way
        (answer_codec / answer_addresses) and moves the modeled
        server state ringing -> connected, like answerack does for
        an outgoing call."""
        entry = self.voice_calls.setdefault(
            call_id, {"steps": [], "delivered": False,
                      "server_state": None, "record": None,
                      "request_addresses": None,
                      "requestcall_codec": None,
                      "request_codec": None,
                      "answer_codec": None,
                      "answer_addresses": None})
        if step not in entry["steps"]:
            entry["steps"].append(step)
        if body is not None:
            if step in ("requestcall", "group/requestcall"):
                entry["requestcall_codec"] = body.get("codec")
            elif step in ("request", "group/request"):
                entry["request_codec"] = body.get("codec")
            elif step == "answer":
                entry["answer_codec"] = body.get("codec")
                entry["answer_addresses"] = {
                    "rtcp": body.get("rtcpAddress"),
                    "rtp": body.get("rtpAddress")}
        if step in ("request", "group/request") and (
                "requestcall" in entry["steps"]
                or "group/requestcall" in entry["steps"]):
            entry["delivered"] = True
        if entry["server_state"] == "ended":
            return entry  # a closed call keeps its first record
        if step in ("requestcall", "group/requestcall"):
            if entry["server_state"] is None:
                entry["server_state"] = "ringing"
        elif step in ("request", "group/request"):
            if body is not None:
                entry["request_addresses"] = {
                    "rtcp": body.get("rtcpAddress"),
                    "rtp": body.get("rtpAddress")}
        elif step == "answerack":
            if entry["server_state"] == "ringing":
                entry["server_state"] = "connected"
        elif step == "answer":
            # Callee answered an incoming call (11303): the call
            # is connected now, like answerack for an outgoing one.
            if entry["server_state"] == "ringing":
                entry["server_state"] = "connected"
        elif step == "cancel":
            entry["record"] = "missed"
            entry["server_state"] = "ended"
        elif step in ("endcall", "group/endcall"):
            entry["record"] = ("ended" if entry["server_state"]
                               == "connected" else "missed")
            entry["server_state"] = "ended"
        return entry
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
                # latin-1: giai ma khong mat byte (anh that la binary —
                # 0xFF 0xD8... — utf-8 se vo). Cac assert trong mock chi
                # soi chuoi ASCII ('name="fileContent"', 'filename=')
                # nen van dung.
                raw = self.rfile.read(length) if length else b""
                mock.seen_post_raw.append((parsed.path, raw))
                # decode kieu latin-1: file nhi phan (vd. MP3) co
                # byte khong phai utf-8; decode chat se loi 500
                # thay vi tra loi that — xem _chat_upload.
                raw_text = raw.decode("latin-1") if length \
                    else ""
                mock.seen.append((parsed.path, qs, dict(self.headers)))
                mock.seen_post.append((parsed.path, qs))
                try:
                    status, obj = mock.route_post(
                        parsed.path, qs, self.headers, raw_text,
                        parsed.query)
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
        if path in ("/api/social/friend/getfriends",
                    "/api/group/getlg/v4") and self.slow_seconds:
            time.sleep(self.slow_seconds)
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
            if self.friends_mode == "rate429":
                return 429, {"error_code": 429,
                             "error_message": "Too Many Requests",
                             "data": {}}
            return 200, self._friends(qs, headers, raw_qs)
        if path == "/api/group/getlg/v4":
            if self.groups_mode == "rate429":
                return 429, {"error_code": 429,
                             "error_message": "Too Many Requests",
                             "data": {}}
            return 200, self._groups_v4(qs, headers)
        if path in ("/api/message/sms", "/api/group/sendmsg"):
            return 200, self._chat_send_text(path, qs, headers, raw_qs)
        if path == "/api/group/history":
            return 200, self._group_history(qs, headers, raw_qs)
        if path == "/lp-msg/":
            return 200, self._poll(qs, headers, raw_qs)
        if path == "/lp-ctl/":
            return 200, self._ctrl_poll(qs, headers, raw_qs)
        if path in ("/api/message/typing", "/api/group/typing",
                    "/api/message/seen", "/api/group/seen"):
            return 200, self._chat_event(path, qs, headers, raw_qs)
        if path.startswith(("/api/message/", "/api/group/",
                            "/api/social/", "/api/conv/",
                            "/api/convlabel/", "/api/board/",
                            "/api/setting/", "/api/update/",
                            "/api/friend/", "/api/alias/",
                            "/api/quickmessage/", "/api/poll/",
                            "/api/archivedchat/", "/api/hiddenconvers/",
                            "/api/pinconvers/", "/api/label/",
                            "/api/profile/")):
            return 200, self._svc_get(path, qs, headers, raw_qs)
        return 404, {"error_code": 404, "error_message": "mock no route"}

    def _chat_send_text(self, path, qs, headers, raw_qs=""):
        """Gui text 1-1 (11151) / nhom (11163): GET, params AES.
        1-1 body {message, clientId NUMBER, imei, toid, ttl};
        nhom {message, clientId NUMBER, imei, visibility, grid,
        ttl} (SERVICE-MAP.md §3.1 — clientId string + thieu ttl la
        nghi pham so 1 cua loi 114, mock phai bat)."""
        self._check_postlogin(qs, headers, raw_qs, "chat send")
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert body.get("message"), body
        # clientId phai la JSON NUMBER epoch-ms (khong phai string).
        assert isinstance(body.get("clientId"), int) and not \
            isinstance(body.get("clientId"), bool), body
        assert body.get("clientId") > 10 ** 12, body
        assert isinstance(body.get("ttl"), int), body
        assert body.get("imei"), body
        if path == "/api/message/sms":
            assert body.get("toid"), body
        else:
            assert body.get("grid"), body
            assert isinstance(body.get("visibility"), int), body
        return self._postlogin_envelope(
            {"msgId": "msg-1", "clientId": body["clientId"],
             "body": body})

    def _chat_send_link(self, path, qs, headers, raw_body="",
                        raw_qs=""):
        """Gui link 1-1 (11286) / nhom (11193): POST form
        params=<AES>. 1-1 body {msg, href, title, desc, language,
        clientId NUMBER, toId, mentionInfo:"", ttl}; nhom them
        {grid, mentionInfo:"[]", visibility, imei}
        (SERVICE-MAP.md §3.2, #72)."""
        self._check_common(qs, headers, "chat send link")
        m = re.search(r"(?:^|&)params=([^&]*)", raw_body or "")
        assert m, "link POST %s needs params form body" % path
        assert "/" not in m.group(1) and "+" not in m.group(1), \
            "link POST %s params not fully percent-encoded" % path
        enc = urllib.parse.unquote(m.group(1))
        assert enc, "link POST %s needs params" % path
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(enc),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert body.get("href"), body
        # clientId phai la JSON NUMBER epoch-ms (khong phai string).
        assert isinstance(body.get("clientId"), int) and not \
            isinstance(body.get("clientId"), bool), body
        assert body.get("clientId") > 10 ** 12, body
        assert isinstance(body.get("ttl"), int), body
        assert body.get("language") == "vi", body
        if path == "/api/message/link":
            assert body.get("toId"), body
            assert body.get("mentionInfo") == "", body
        else:
            assert body.get("grid"), body
            assert body.get("mentionInfo") == "[]", body
            assert isinstance(body.get("visibility"), int), body
            assert body.get("imei"), body
        return self._postlogin_envelope(
            {"msgId": "msg-1", "clientId": body["clientId"],
             "body": body})

    def _group_history(self, qs, headers, raw_qs=""):
        """Lich su nhom (11240): GET, params AES {grid, count}."""
        self._check_postlogin(qs, headers, raw_qs, "group history")
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert body.get("grid"), body
        assert isinstance(body.get("count"), int) and body["count"] > 0, body
        return self._postlogin_envelope({
            # "path"/"body" echo (nhu _svc_get) de test dispatch cua
            # services kiem tra duoc routing; endpoint that chi tra
            # messages/hasMore.
            "path": "/api/group/history", "body": body,
            "messages": [
                {"msgId": "m1", "fromId": "20001",
                 "message": "Chao ca nhom", "timestamp": 1762345600},
                {"msgId": "m2", "fromId": "20002",
                 "message": "Chao Ban A", "timestamp": 1762345660}],
            "hasMore": False})

    def _poll(self, qs, headers, raw_qs=""):
        """Sync long-poll tin den (99100 getChatFromPolling): GET
        <poll-url>/?zpw_ver&zpw_type&params=<cursor>&ts=<unix>.
        params la chuoi con tro "last,other,<b64(json)+',1'>" (khong
        phai AES — xem sync_poll.PollCursor). Tra envelope hai lop
        giong moi response post-login; mode "empty" tra data "" (het
        han long-poll, khong co tin); mode "error69" tra -69."""
        self._check_postlogin(qs, headers, raw_qs, "sync poll")
        assert qs.get("params"), "poll can params (con tro)"
        assert qs.get("ts", "").isdigit(), "poll can ts (unix)"
        if self.poll_mode == "empty":
            return {"error_code": 0, "data": ""}
        if self.poll_mode == "error69":
            return {"error_code": -69,
                    "error_message": "stop retry", "data": {}}
        return self._postlogin_envelope({
            "msgs": [
                {"msgId": "pm1", "globalMsgId": "g1",
                 "uidFrom": "20001", "idTo": "10001",
                 "content": "Chao ban, toi la BenBap",
                 "ts": 1762345700, "dName": "BenBap",
                 "msgType": 0}],
            "groupMsgs": [
                {"msgId": "gm1", "globalMsgId": "g2",
                 "uidFrom": "20002", "idTo": "30001",
                 "content": {"msg": "Chao ca nhom"},
                 "ts": 1762345710, "dName": "Ban B",
                 "msgType": 0}],
            "pageMsgs": [],
            "lastActionId": "100",
            "lastActionIdOther": "50",
            "queueStatus": {}})

    def _ctrl_poll(self, qs, headers, raw_qs=""):
        """Ctrl long-poll (99101 getControllFromPolling): GET
        <poll-url>/?zpw_ver&zpw_type&params=<cursor>&ts=<unix>.
        Tra envelope hai lop nhu kenh tin nhan. Khi ctrl_file_url
        duoc dat, tra mot event file_done cho fileId "file-1" voi
        URL do (mock cua file upload tra fileId "file-1"); khong
        thi tra controls rong."""
        self._check_postlogin(qs, headers, raw_qs, "ctrl poll")
        assert qs.get("params"), "ctrl poll can params (con tro)"
        assert qs.get("ts", "").isdigit(), "ctrl poll can ts (unix)"
        controls = []
        if self.ctrl_file_url:
            controls.append({"controlId": "c-file-1",
                             "content": {"act_type": "file_done",
                                         "fileId": "file-1",
                                         "data": {"url":
                                                  self.ctrl_file_url}}})
        return self._postlogin_envelope({"controls": controls,
                                         "lastActionId": "77",
                                         "lastActionIdOther": "60",
                                         "queueStatus": {}})

    def _chat_event(self, path, qs, headers, raw_qs=""):
        """typing (11144/11196) / seen (11150/11167): GET, params AES."""
        self._check_postlogin(qs, headers, raw_qs, "chat event")
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        if "typing" in path:
            assert body.get("toid") or body.get("grid"), body
            assert body.get("imei"), body
        else:
            assert isinstance(body.get("msg_ids"), list), body
        return self._postlogin_envelope({"ok": True})

    def _chat_upload(self, path, qs, headers, raw_body=""):
        """Gui anh/voice truc tiep (11152/11164, voicemp3 cu):
        POST multipart, fileContent + query params=<AES {toid|grid,
        clientId}> & type=2 (1-1) / 11 (nhom). raw_body o day la
        str (mock do_POST decode latin-1 — anh that la binary).
        sharefile_full KHONG con o day: duong truc tiep do CHEt
        (0 caller trong bundle) va Zalo tra 405 — xem route_post.
        Kieu clientId theo bundle (xem chat.py): voice la STRING
        (sendVoice ghep chuoi JSON bang tay, co dau ngoac kep:
        '"clientId":"<id>"'), anh la NUMBER (JSON.stringify).
        Mock mo hinh hoa loi that 2026-11-06: voice gui clientId
        dang NUMBER bi server tu choi bang inner 112 chung chung
        — day la GIA THUYET co bang chung bundle (khong phai bang
        chung truc tiep tu server); kiem chung that van can retest
        live cua user."""
        assert headers.get("Cookie"), "chat upload needs Cookie"
        assert qs.get("zpw_ver") == "695", qs
        assert qs.get("zpw_type") == "30", qs
        ctype = headers.get("Content-Type") or ""
        assert "multipart/form-data" in ctype, ctype
        assert 'name="fileContent"' in raw_body, "needs fileContent"
        assert "filename=" in raw_body, "needs filename"
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert body.get("clientId"), body
        self.upload_bodies.append({"path": path, "body": body})
        is_group = path.startswith("/api/group/")
        if is_group:
            assert body.get("grid"), body
            assert qs.get("type") == "11", qs
        else:
            assert body.get("toid"), body
            assert qs.get("type") == "2", qs
        if path in ("/api/message/photo", "/api/group/sendpt"):
            # desc CHI can co mat, khong can khac rong: client that
            # gui desc = title || "" (bundle _sendPhoto) — anh
            # khong caption co desc = "". Assertion cu (truthy)
            # chat hon server that; ten file khong duoc gui lam
            # desc (xem chat.send_photo).
            assert "desc" in body, body
            assert isinstance(body.get("width"), int), body
            assert isinstance(body.get("height"), int), body
            assert isinstance(body.get("clientId"), int) and not \
                isinstance(body.get("clientId"), bool), body
        if path in ("/api/message/voicemp3", "/api/group/sendmp3"):
            self.voice_upload_calls += 1
            if self.voice_upload_mode == "error133":
                # Loi that khi file gui len khong phai MP3 (2026-11-05
                # 23:03): inner 133, khong phai outer error.
                return self._postlogin_envelope_error(
                    133,
                    "Bạn chỉ có thể tải tập tin có định dạng sau : MP3")
            if self.voice_upload_mode == "error112":
                # Loi that 2026-11-06 06:35 +07 tren 9d87501.
                return self._postlogin_envelope_error(
                    112, "Lỗi không xác định")
            if self.voice_upload_mode == "error112_once" \
                    and self.voice_upload_calls == 1:
                return self._postlogin_envelope_error(
                    112, "Lỗi không xác định")
            if not isinstance(body.get("clientId"), str):
                # clientId NUMBER tren duong voice: sai so voi
                # bundle (STRING) — server that tra 112 chung
                # chung. Xem ghi chu o docstring ham nay.
                return self._postlogin_envelope_error(
                    112, "Lỗi không xác định")
        return self._postlogin_envelope(
            {"msgId": "msg-file-1", "clientId": body["clientId"],
             "body": body})

    def _chat_voice_upload(self, path, qs, headers, raw_body=""):
        """Upload ghi am theo chunk — buoc 1 cua duong hai buoc
        (bundle compact-app-pc, upload-manager):
        POST multipart {files-wpa}/api/message/voice/upload
        (12060) / /api/group/voice/upload (12063), FormData
        chunkContent = 1 chunk cua file AAC, query params=<AES
        {totalChunk, fileName, clientId NUMBER, totalSize, imei,
        chunkId, toid|grid, fileType: "aac"|"amr"}> & type=2/11.
        KHONG co checksum trong params (bundle `delete` no khoi
        params truoc khi gui — checksum chi nam trong mo ta request
        phia client); clientId o day la NUMBER (JSON.stringify),
        KHAC voi duong truc tiep voicemp3 cu (STRING ghep tay).
        Chunk chua cuoi tra data {finished: 0}; chunk cuoi
        (chunkId == totalChunk) tra {finished: 1, fileId} — dung
        dieu kien hoan tat cua handleSendChunkResp (finished &&
        fileId). Cac chunk phai den dung thu tu chunkId 1..N (mock
        khong doi hoan doi — client gui tuan tu)."""
        assert headers.get("Cookie"), "voice upload needs Cookie"
        assert qs.get("zpw_ver") == "695", qs
        assert qs.get("zpw_type") == "30", qs
        ctype = headers.get("Content-Type") or ""
        assert "multipart/form-data" in ctype, ctype
        assert 'name="chunkContent"' in raw_body, "needs chunkContent"
        assert "filename=" in raw_body, "needs filename"
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert body.get("clientId"), body
        assert isinstance(body.get("clientId"), int) and not \
            isinstance(body.get("clientId"), bool), body
        assert isinstance(body.get("totalChunk"), int) \
            and body["totalChunk"] >= 1, body
        assert isinstance(body.get("chunkId"), int) \
            and 1 <= body["chunkId"] <= body["totalChunk"], body
        assert body.get("fileName"), body
        assert isinstance(body.get("totalSize"), int) \
            and body["totalSize"] > 0, body
        assert body.get("imei"), body
        assert body.get("fileType") in ("aac", "amr"), body
        assert "checksum" not in body, body
        self.upload_bodies.append({"path": path, "body": body})
        is_group = path.startswith("/api/group/")
        if is_group:
            assert body.get("grid"), body
            assert qs.get("type") == "11", qs
        else:
            assert body.get("toid"), body
            assert qs.get("type") == "2", qs
        self.voice_upload_calls += 1
        if self.voice_upload_mode == "error112":
            return self._postlogin_envelope_error(
                112, "Lỗi không xác định")
        if self.voice_upload_mode == "error112_once" \
                and self.voice_upload_calls == 1:
            return self._postlogin_envelope_error(
                112, "Lỗi không xác định")
        if body["chunkId"] < body["totalChunk"]:
            return self._postlogin_envelope({"finished": 0})
        last = {"finished": 1, "fileId": "file-voice-1"}
        last.update(self.voice_upload_extra)
        return self._postlogin_envelope(last)

    def _chat_file_upload(self, path, qs, headers, raw_body=""):
        """Upload file thuong theo chunk — buoc 1 cua duong hai
        buoc (bundle compact-app-pc, upload-manager /
        getInfoUploadFileFromData): POST multipart
        {files-wpa}/api/message/asyncfile/upload (11776) /
        /api/group/asyncfile/upload (13000), FormData chunkContent
        = 1 chunk (mac dinh 256_000 byte, getDefaultChunkSize),
        query params=<AES {totalChunk, fileName, clientId NUMBER,
        totalSize, imei, chunkId, toid|grid}> & type=2/11.
        KHONG co fileType (chi Voice moi co, buildSendChunksInfo),
        KHONG co checksum (bundle `delete` no khoi params truoc
        khi gui — checksum chi o buoc 2), KHONG isE2EE/jxl.
        clientId la NUMBER (JSON.stringify cua upload-manager).
        Chunk chua cuoi tra data {finished: 0}; chunk cuoi
        (chunkId == totalChunk) tra {finished: 1, fileId} — dung
        dieu kien hoan tat cua handleSendChunkResp (finished &&
        fileId). Cac chunk phai den dung thu tu chunkId 1..N."""
        assert headers.get("Cookie"), "file upload needs Cookie"
        assert qs.get("zpw_ver") == "695", qs
        assert qs.get("zpw_type") == "30", qs
        ctype = headers.get("Content-Type") or ""
        assert "multipart/form-data" in ctype, ctype
        assert 'name="chunkContent"' in raw_body, "needs chunkContent"
        assert "filename=" in raw_body, "needs filename"
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert body.get("clientId"), body
        assert isinstance(body.get("clientId"), int) and not \
            isinstance(body.get("clientId"), bool), body
        assert isinstance(body.get("totalChunk"), int) \
            and body["totalChunk"] >= 1, body
        assert isinstance(body.get("chunkId"), int) \
            and 1 <= body["chunkId"] <= body["totalChunk"], body
        assert body.get("fileName"), body
        assert isinstance(body.get("totalSize"), int) \
            and body["totalSize"] > 0, body
        assert body.get("imei"), body
        assert "fileType" not in body, body
        assert "checksum" not in body, body
        self.file_upload_bodies.append({"path": path, "body": body})
        is_group = path.startswith("/api/group/")
        if is_group:
            assert body.get("grid"), body
            assert qs.get("type") == "11", qs
        else:
            assert body.get("toid"), body
            assert qs.get("type") == "2", qs
        self.file_upload_calls += 1
        if body["chunkId"] < body["totalChunk"]:
            return self._postlogin_envelope({"finished": 0})
        last = {"finished": 1, "fileId": "file-1"}
        last.update(self.file_upload_extra)
        return self._postlogin_envelope(last)

    def _chat_asyncfile_msg(self, path, qs, headers, raw_body="",
                            raw_qs=""):
        """Gui tin sau khi upload xong — buoc 2 cua duong hai buoc
        (bundle: API sendMsgFileAsync 11777/13001; input la dung
        item getFileAsyncItem tra ve): POST form params=<AES JSON>.
        Voice: {fileId, checksum (md5 hex cua file AAC),
        checksumSha: "", totalSize, clientId NUMBER, toid|grid,
        imei (chi 1-1), zsource, fileUrl (BAT BUOC — URL ghi am tu
        event async ctrl voice_aac_success qua kenh ctrl 99101; gui
        khong co fileUrl la cai gay ra 114 live 2026-11-06), aacUrl
        (khi co amr), secureKey (chi khi async data co no)}>. fType
        LOAI TRU (extData Voice duy nhat lan duoc khong co fType —
        mock khong doi). File: them {extension (sau dau cham cuoi,
        rong neu khong co), fileName (NFC), fType: 1 (FILE_FTYPE
        FILE=1), fileCount: 0, fdata: "{}"} — bundle
        getFileAsyncItem + extData cua call site MSG_FILE; zca-js
        2.1.2 sendMessage "others" khop het tru mot diem: no viet
        `extention` (sai chinh ta) — bundle exe thang nen dung
        `extension`. Tra envelope {msgId, clientId, body} nhu
        _chat_upload (msgId "msg-file-1" cho File, "msg-voice-1"
        cho Voice). file_send_mode "empty" tra data rong ({}) o
        buoc 2 cua File — client phai bao loi that (xem
        test_send_file_empty_data_errors)."""
        self._check_common(qs, headers, "asyncfile msg")
        m = re.search(r"(?:^|&)params=([^&]*)", raw_body or "")
        assert m, "asyncfile msg needs params form body"
        assert "/" not in m.group(1) and "+" not in m.group(1), \
            "asyncfile msg params not fully percent-encoded"
        enc = urllib.parse.unquote(m.group(1))
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(enc),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert body.get("fileId"), body
        assert isinstance(body.get("fileUrl"), str) \
            and body["fileUrl"], body
        assert re.fullmatch(r"[0-9a-f]{32}", body.get("checksum")
                            or ""), body
        assert body.get("checksumSha") == "", body
        assert isinstance(body.get("totalSize"), int) \
            and body["totalSize"] > 0, body
        assert isinstance(body.get("clientId"), int) and not \
            isinstance(body.get("clientId"), bool), body
        is_group = path.startswith("/api/group/")
        if is_group:
            assert body.get("grid"), body
            assert "imei" not in body, body
        else:
            assert body.get("toid"), body
            assert body.get("imei"), body
        if "fileName" in body:
            # File thuong (getFileAsyncItem): them extension,
            # fileName, fType=1, fileCount=0, fdata="{}".
            assert isinstance(body.get("extension"), str), body
            assert "." not in body["extension"], body
            assert len(body["extension"]) < 7, body
            assert isinstance(body.get("fileName"), str) \
                and body["fileName"], body
            assert body.get("fType") == 1, body
            assert body.get("fileCount") == 0, body
            assert body.get("fdata") == "{}", body
            self.file_send_bodies.append({"path": path, "body": body})
            self.file_send_calls += 1
            if self.file_send_mode == "empty":
                return self._postlogin_envelope({})
            return self._postlogin_envelope(
                {"msgId": "msg-file-1", "clientId": body["clientId"],
                 "body": body})
        self.voice_send_bodies.append({"path": path, "body": body})
        self.voice_send_calls += 1
        if self.voice_send_mode == "error112":
            return self._postlogin_envelope_error(
                112, "Lỗi không xác định")
        if self.voice_send_mode == "error112_once" \
                and self.voice_send_calls == 1:
            return self._postlogin_envelope_error(
                112, "Lỗi không xác định")
        return self._postlogin_envelope(
            {"msgId": "msg-voice-1", "clientId": body["clientId"],
             "body": body})

    def route_post(self, path, qs, headers, raw_body="", raw_qs=""):
        if path == "/api/group/getmg-v2" and self.slow_seconds:
            time.sleep(self.slow_seconds)
        if path == "/api/group/getmg-v2":
            if self.groups_mode == "rate429":
                return 429, {"error_code": 429,
                             "error_message": "Too Many Requests",
                             "data": {}}
            return 200, self._group_info_multi(qs, headers, raw_body)
        if path in ("/api/message/sharefile_full",
                    "/api/group/sharefile_full"):
            # Duong truc tiep CHEt (0 caller trong bundle PC that;
            # API sendFile khong ai goi, giong sendVoice chet cua
            # voicemp3) — Zalo upstream tu choi bang HTTP 405 (live
            # 2026-11-07 09:xx +07: banner «POST /api/message/
            # sharefile_full network status=405» khi gui Word/Excel/
            # PDF). Mock tra dung 405 nhu server that: client nao
            # con goi duong nay se loi thay vi duoc gia vo thanh
            # cong. Duong that la 2 buoc asyncfile (upload 11776/
            # 13000 + asyncfile/msg 11777/13001) — xem
            # _chat_file_upload / _chat_asyncfile_msg.
            return 405, {"error_code": 405,
                         "error_message": "Method Not Allowed"}
        if path in ("/api/message/voicemp3", "/api/group/sendmp3",
                    "/api/message/photo", "/api/group/sendpt"):
            return 200, self._chat_upload(path, qs, headers, raw_body)
        if path in ("/api/message/voice/upload",
                    "/api/group/voice/upload"):
            return 200, self._chat_voice_upload(path, qs, headers,
                                                raw_body)
        if path in ("/api/message/asyncfile/upload",
                    "/api/group/asyncfile/upload"):
            return 200, self._chat_file_upload(path, qs, headers,
                                               raw_body)
        if path in ("/api/message/asyncfile/msg",
                    "/api/group/asyncfile/msg"):
            return 200, self._chat_asyncfile_msg(
                path, qs, headers, raw_body, raw_qs)
        if path in ("/api/message/link", "/api/group/sendlink"):
            return 200, self._chat_send_link(path, qs, headers,
                                             raw_body, raw_qs)
        if path in ("/api/group/upavatar", "/api/profile/upavatar"):
            return 200, self._avatar_upload(path, qs, headers,
                                            raw_body)
        if path.startswith(("/api/message/", "/api/group/",
                            "/api/social/", "/api/conv/",
                            "/api/convlabel/", "/api/board/",
                            "/api/setting/", "/api/update/",
                            "/api/friend/", "/api/alias/",
                            "/api/quickmessage/", "/api/poll/",
                            "/api/archivedchat/", "/api/hiddenconvers/",
                            "/api/pinconvers/", "/api/label/",
                            "/api/profile/")):
            return 200, self._svc_post(path, qs, headers, raw_body,
                                       raw_qs)
        return 404, {"error_code": 404, "error_message": "mock no route"}

    def _avatar_upload(self, path, qs, headers, raw_body=""):
        """Doi avatar nhom (11195) / tai khoan (11819): POST
        multipart fileContent + query params=<AES {grid|-, clientId
        NUMBER, originWidth, originHeight, imei} / {clientId,
        language}. avatarSize chua biet gia tri — mock khong doi."""
        assert headers.get("Cookie"), "avatar upload needs Cookie"
        assert qs.get("zpw_ver") == "695", qs
        assert qs.get("zpw_type") == "30", qs
        ctype = headers.get("Content-Type") or ""
        assert "multipart/form-data" in ctype, ctype
        assert 'name="fileContent"' in raw_body, "needs fileContent"
        assert "filename=" in raw_body, "needs filename"
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        body = json.loads(plain.decode("utf-8"))
        assert isinstance(body.get("clientId"), int) and not \
            isinstance(body.get("clientId"), bool), body
        if path == "/api/group/upavatar":
            assert body.get("grid"), body
            assert isinstance(body.get("originWidth"), int), body
            assert isinstance(body.get("originHeight"), int), body
            assert body.get("imei"), body
        else:
            assert body.get("language"), body
        return self._postlogin_envelope(
            {"ok": True, "path": path, "body": body})

    def _svc_get(self, path, qs, headers, raw_qs=""):
        """Generic post-login GET for the services module: strict
        common params + fully percent-encoded params, decrypt the
        body, echo it back inside the two-layer envelope. The mock
        does NOT validate per-endpoint body shapes (those are the
        audit's 'body chưa lần hết' — the test pins the wire
        contract, not an invented body).
        Dac biet:
        - /api/pinconvers/list tra shape that theo bundle
          (PinDataManager): {version, conversations:[id 'u'/'g']}.
        - /api/hiddenconvers/reset KHONG co params (chi common
          params — bundle resetPIN goi _get(e, null, 10051)).
        - params giai ma ra chuoi rong "" (get_stickers 11155:
          params AES cua chuoi rong) thi body = ""."""
        if path == "/api/hiddenconvers/reset":
            self._check_common(qs, headers, "svc GET %s" % path)
            assert "params" not in qs, \
                "reset pin takes no params: %s" % qs
            return self._postlogin_envelope(
                {"ok": True, "path": path, "body": {}})
        self._check_postlogin(qs, headers, raw_qs, "svc GET %s" % path)
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(qs["params"]),
                             decrypt=True)
        text = plain.decode("utf-8")
        body = json.loads(text) if text else ""
        if path == "/api/pinconvers/list":
            if self.pin_list_mode == "error212":
                return self._postlogin_envelope_error(
                    212, "hasn't pinned conversation")
            return self._postlogin_envelope(
                {"version": 3, "conversations": ["u20001"]})
        return self._postlogin_envelope(
            {"ok": True, "path": path, "body": body})

    def _svc_post(self, path, qs, headers, raw_body="", raw_qs=""):
        """Generic post-login POST (form params=<AES JSON>) for the
        services module: same contract as getmg-v2 (common params +
        fully percent-encoded form value), echo in two-layer
        envelope. POST_QUERY (update_auto_delete_chat 12023) de
        params trong QUERY URL thay vi form body — chap nhan ca
        hai. params giai ma ra chuoi rong thi body = ""."""
        self._check_common(qs, headers, "svc POST %s" % path)
        enc = qs.get("params")
        if enc is None:
            m = re.search(r"(?:^|&)params=([^&]*)", raw_body or "")
            assert m, "svc POST %s needs params form body" % path
            assert "/" not in m.group(1) and "+" not in m.group(1), \
                "svc POST %s params not fully percent-encoded" % path
            enc = urllib.parse.unquote(m.group(1))
        else:
            m = re.search(r"(?:^|&)params=([^&]*)", raw_qs or "")
            assert m, "svc POST %s needs raw params value" % path
            assert "/" not in m.group(1) and "+" not in m.group(1), \
                "svc POST %s params not fully percent-encoded" % path
        assert enc, "svc POST %s needs params" % path
        key = base64.b64decode(TEST_SESSION_KEY)
        plain = _openssl_aes(key, base64.b64decode(enc),
                             decrypt=True)
        text = plain.decode("utf-8")
        body = json.loads(text) if text else ""
        return self._postlogin_envelope(
            {"ok": True, "path": path, "body": body})

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
        # Shape THAT cua getLoginInfo (bundle compact-app-pc
        # @11816376: client resolve {config: e.data.data, ...} —
        # toan bo data CHINH LA config; zpw_chts_new / zpw_ctrs_new /
        # zpw_service_map_new / zpw_conf / zpw_ws o TOP-LEVEL cua
        # data, khong phai duoi data.config. App cu chi doc
        # data.config nen khong bao gio thay poll URLs tren
        # response that (live 2026-11-07: QR xong, getLoginInfo
        # thanh cong, nhung "khong co zpw_chts_new" mai).
        data = {
            "dkey": "dkey-test",
            "zpw_enk": TEST_SESSION_KEY,
            # Services map (v2 shape: string values) — REACTION /
            # QUICK_MESSAGE chi co trong map nay, khong hard-code
            # trong bundle (SERVICE-MAP.md §1). Mock tra ve chinh
            # mock base de test HTTP end-to-end di qua resolve.
            "zpw_service_map_new": {
                "reaction": self.base,
                "quick_message": self.base},
            "zpw_service_map_v3": {},
            "zpw_ws": "wss://mock.invalid/ws",
            # Sync long-poll endpoints (bundle setEndpoints):
            # zpw_chts_new = W (tin nhan, 99100), zpw_ctrs_new = q
            # (dieu khien, 99101); zpw_conf lp_* timeout (giay).
            "zpw_chts_new": [self.base + "/lp-msg"],
            "zpw_ctrs_new": [self.base + "/lp-ctl"],
            "zpw_conf": {"lp_msg_timeout": 30,
                         "lp_ctl_timeout": 30},
            "phone_number": "+84000000000",
            "current_time": 1762345600,
            "settings": {}}
        if self.logininfo_mode == "nested_config":
            # Shape cu (sai): poll URLs duoi data.config — chi de
            # chung minh fallback cua app van doc duoc.
            data = {
                "dkey": "dkey-test",
                "zpw_enk": TEST_SESSION_KEY,
                "config": {"zpw_service_map_new": {
                               "reaction": self.base,
                               "quick_message": self.base},
                           "zpw_ws": "wss://mock.invalid/ws",
                           "zpw_chts_new": [self.base + "/lp-msg"],
                           "zpw_ctrs_new": [self.base + "/lp-ctl"],
                           "zpw_conf": {"lp_msg_timeout": 30,
                                        "lp_ctl_timeout": 30}}}
        elif self.logininfo_mode == "no_endpoints":
            # Thanh cong nhung khong cap poll URLs o dau ca.
            data = {
                "dkey": "dkey-test",
                "zpw_enk": TEST_SESSION_KEY,
                "zpw_service_map_new": {},
                "zpw_ws": "",
                "zpw_conf": {"lp_msg_timeout": 30,
                             "lp_ctl_timeout": 30},
                "settings": {}}
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
            self._record_voice_step(call_id, sub, body)
            data = {"ok": True, "path": path, "body": body}
            if self.requestcall_data:
                data.update(self.requestcall_data)
            return self._postlogin_envelope(data)
        if sub in ("endcall", "group/endcall"):
            # End a call (bundle wZ sendEndCall / sendEndCallGroup):
            # 1-1 {uidTo, callId, status:3, imei} (code 11306);
            # group {calleeId, callId, callType, hostCall, data,
            # partners} (code 12438). callId must be a JSON NUMBER
            # in uint32 range — a string callId drew inner 114 for
            # requestcall (§7k) and endcall carries the same engine
            # type (%u). endcall_mode="error" simulates the real
            # server rejecting the end; "slow" simulates a sluggish
            # endcall round-trip.
            call_id = body.get("callId")
            id_ok = (isinstance(call_id, int)
                     and not isinstance(call_id, bool)
                     and 1 <= call_id <= 2 ** 32 - 1)
            if sub == "endcall":
                shape_ok = (bool(body.get("uidTo")) and id_ok
                            and body.get("status") == 3
                            and body.get("imei"))
            else:
                shape_ok = (bool(body.get("calleeId")) and id_ok
                            and body.get("callType") in (5, 6)
                            and "hostCall" in body)
            if not shape_ok:
                return self._postlogin_envelope_error(
                    114, "Tham số không hợp lệ")
            if self.endcall_mode == "error":
                return self._postlogin_envelope_error(
                    500, "mock endcall rejected")
            if self.endcall_mode == "slow":
                time.sleep(2)
            self._record_voice_step(call_id, sub)
            return self._postlogin_envelope(
                {"ok": True, "path": path, "body": body})
        if sub == "cancel":
            # Withdraw an unanswered invitation (bundle wZ
            # sendCancelCall, code 11305, mobile opcode 405 "huy"):
            # {callerId, callId, callType, status:0, imei}. This is
            # the signal the real client sends when the caller hangs
            # up before the callee answers, and at ring timeout
            # (~30s, pcap file 2: teardown voicecall stream
            # 35.33-36.22s after ~29.5s of media). The callee's
            # client handles it via [SIG]recvCancel and drops the
            # incoming-call UI; without it the peer keeps a ghost
            # "hidden call" that re-rings with a dead answer button
            # (live 2026-11-07 09:01-09:02). callType is the
            # call-type enum (1-1 audio=1, 1-1 video=3); callerId is
            # the CALLER's uid. cancel_mode mirrors endcall_mode.
            call_id = body.get("callId")
            id_ok = (isinstance(call_id, int)
                     and not isinstance(call_id, bool)
                     and 1 <= call_id <= 2 ** 32 - 1)
            shape_ok = (bool(body.get("callerId")) and id_ok
                        and body.get("callType") in (1, 3)
                        and body.get("status") == 0
                        and body.get("imei"))
            if not shape_ok:
                return self._postlogin_envelope_error(
                    114, "Tham số không hợp lệ")
            if self.cancel_mode == "error":
                return self._postlogin_envelope_error(
                    500, "mock cancel rejected")
            if self.cancel_mode == "slow":
                time.sleep(2)
            self._record_voice_step(call_id, sub)
            return self._postlogin_envelope(
                {"ok": True, "path": path, "body": body})
        if sub in ("request", "group/request"):
            # Follow-up request step (§7l, bundle class wZ
            # sendRequestCall / sendRequestCallGroup): the caller's
            # media endpoints for the invitation. Contract enforced
            # here is only what the bundle proves — calleeId +
            # callId (uint32 number) must be present, and (group)
            # groupId must be present. The endpoint VALUES
            # (rtcp/rtp/session) are NOT validated as a rejection:
            # whether the real server rejects empty addresses is
            # unverified, so the mock must not invent a rejection
            # it was never observed to make — but the addresses ARE
            # recorded (see _record_voice_step) so tests can assert
            # the app-side contract: the real client ALWAYS carries
            # a real relay address in 11301 (probe -> setup ->
            # type-02 first; 5-pcap re-analysis 2026-11-08), and
            # the app's for_call refuses to send 11301 with empty
            # endpoints. request_mode="error114" simulates the
            # rejection explicitly when a test wants it.
            call_id = body.get("callId")
            id_ok = (isinstance(call_id, int)
                     and not isinstance(call_id, bool)
                     and 1 <= call_id <= 2 ** 32 - 1)
            need = ["calleeId"]
            if sub == "group/request":
                need.append("groupId")
            if (not id_ok or any(not body.get(f) for f in need)
                    or self.request_mode == "error114"):
                return self._postlogin_envelope_error(
                    114, "Tham số không hợp lệ")
            if self.request_mode == "status_error":
                # Data-level refusal: transport ok, inner
                # error_code 0, but the decoded data carries a
                # non-zero status (see request_step_outcome).
                return self._postlogin_envelope(
                    {"ok": False, "status": 7,
                     "msg": "callee unreachable"})
            self._record_voice_step(call_id, sub, body)
            return self._postlogin_envelope(
                {"ok": True, "path": path, "body": body})
        if sub == "answerack":
            # Caller ACKs the callee's answer (bundle wZ
            # sendAnswerACKCall, code 11304, mobile opcode 408):
            # {calleeId, callId, status:0, imei}. Sent best-effort
            # when the app learns the peer answered (2026-11-08
            # fix); the mock records it so tests can assert the
            # ACK went out, and validates the shape the bundle
            # proves (uint32 callId, status 0).
            call_id = body.get("callId")
            id_ok = (isinstance(call_id, int)
                     and not isinstance(call_id, bool)
                     and 1 <= call_id <= 2 ** 32 - 1)
            shape_ok = (bool(body.get("calleeId")) and id_ok
                        and body.get("status") == 0
                        and body.get("imei"))
            if not shape_ok:
                return self._postlogin_envelope_error(
                    114, "Tham số không hợp lệ")
            self._record_voice_step(call_id, sub)
            return self._postlogin_envelope(
                {"ok": True, "path": path, "body": body})
        if sub == "ringring":
            # Callee reports ringing (bundle wZ ringRingVoiceCall,
            # code 11302, mobile opcode 407): {callerId, callId,
            # status:0, imei}. The mock records it so tests can
            # assert the app rings the caller back on an incoming
            # call_event.
            call_id = body.get("callId")
            id_ok = (isinstance(call_id, int)
                     and not isinstance(call_id, bool)
                     and 1 <= call_id <= 2 ** 32 - 1)
            shape_ok = (bool(body.get("callerId")) and id_ok
                        and body.get("status") == 0
                        and body.get("imei"))
            if not shape_ok:
                return self._postlogin_envelope_error(
                    114, "Tham số không hợp lệ")
            self._record_voice_step(call_id, sub, body)
            return self._postlogin_envelope(
                {"ok": True, "path": path, "body": body})
        if sub == "answer":
            # Callee answers (bundle wZ answerVoiceCall, code
            # 11303, mobile opcode 402): {callerId, callId,
            # status:0, codec, rtcpAddress, rtpAddress, session_id}
            # (+ extendData / subCommand=3). NOTE: NO imei in this
            # body (zca-js answerVoiceCall.ts) — the generic
            # fallthrough below would wrongly reject it, so this
            # branch must come first. The codec is recorded so
            # tests can assert the JSON-list codec went on the wire.
            call_id = body.get("callId")
            id_ok = (isinstance(call_id, int)
                     and not isinstance(call_id, bool)
                     and 1 <= call_id <= 2 ** 32 - 1)
            shape_ok = (bool(body.get("callerId")) and id_ok
                        and body.get("status") == 0
                        and isinstance(body.get("codec"), str)
                        and body.get("rtcpAddress")
                        and body.get("rtpAddress")
                        and isinstance(body.get("session_id"), str))
            if not shape_ok:
                return self._postlogin_envelope_error(
                    114, "Tham số không hợp lệ")
            self._record_voice_step(call_id, sub, body)
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
        topMember [{id, ...}], totalMember, memberIds, currentMems).
        Nhom Y is the discriminating case for the 2026-11-05 "0 thành
        viên" bug: topMember carries only 1 of its 5 members, so a
        client that counts topMember shows 1 (live: 0 when topMember
        is empty) while the true count is totalMember=5 — memberIds
        and currentMems (5 ids each) agree with totalMember here."""
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
                      "totalMember": 2,
                      "memberIds": ["20001", "20002"],
                      "currentMems": ["20001", "20002"], "type": 1},
            "30002": {"groupId": "30002", "name": "Nhom Y",
                      "avt": "", "fullAvt": "", "creatorId": "20001",
                      "topMember": [{"id": "20001", "displayName": "Ban A"}],
                      "totalMember": 5,
                      "memberIds": ["20001", "20002", "20003", "20004",
                                    "20005"],
                      "currentMems": ["20001", "20002", "20003", "20004",
                                      "20005"], "type": 1},
        }
        grid_info = {gid: infos[gid] for gid in ver_map if gid in infos}
        return self._postlogin_envelope(
            {"removedsGroup": [], "unchangedsGroup": [],
             "gridInfoMap": grid_info})
