"""Contacts contract tests (bug 602, 2026-11-05).

The real Zalo server rejected the contacts calls with error_code=602
"zpw_type bị thiếu hoặc không đúng" after a successful QR login. Static
comparison against the real PC client showed the request skeleton was
right (zpw_ver=695, zpw_type="embed", domains, cookie, session key)
but three wire-format details were wrong:
  1. friends body missed avatar_size=160 (and init=1 on first load);
  2. groups body was {imei} instead of {avatar_size, member_avatar_size};
  3. the params base64 value was not fully percent-encoded (raw '/').
These tests pin the corrected contract and prove the strict mock
rejects the old (pre-fix) requests.
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
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import contacts as contacts_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app.crypto import session_aes_decrypt, session_aes_encrypt  # noqa: E402


def http_get(url, cookie="", timeout=15):
    req = urllib.request.Request(url, method="GET")
    if cookie:
        req.add_header("Cookie", "zpw_sek=" + cookie)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base


def params_value(url):
    return url.split("params=", 1)[1].split("&", 1)[0]


def find_body_with_slash(make_body):
    """Return (body, raw_base64) whose encryption contains '/'."""
    for i in range(100):
        body = make_body(i)
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        enc = session_aes_encrypt(TEST_SESSION_KEY, raw)
        if "/" in enc:
            return body, enc
    raise AssertionError("no '/' in 100 encryptions (unexpected)")


def test_friends_groups_contract():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        book = contacts_mod.Contacts(
            partial(http_get, cookie="sek-test"), "dev-1", TEST_SESSION_KEY)
        friends = book.friends(init=True)
        assert [r["name"] for r in friends["rows"]] == ["Ban A", "Ban B"]
        groups = book.groups()
        assert groups["rows"][0]["name"] == "Nhom X"
        # The mock saw the right common params + init on first load.
        fqs = [qs for p, qs, _ in mock.seen
               if p == "/api/social/friend/getfriends"][0]
        assert fqs["zpw_ver"] == "695" and fqs["zpw_type"] == "embed"
        assert fqs["init"] == "1", fqs
    finally:
        mock.stop()


def test_params_encoding_round_trip():
    # friends URL: no raw '/' or '+' in the params value, decrypts back.
    body, enc = find_body_with_slash(
        lambda i: {"incInvalid": 1, "page": 1, "count": 20000,
                   "avatar_size": 160, "actiontime": 0,
                   "imei": "dev-%d" % i})
    url = contacts_mod._url_with_params(
        "https://profile-wpa.zalo.me", contacts_mod.FRIENDS_PATH,
        body, TEST_SESSION_KEY, {"init": 1})
    val = params_value(url)
    assert "/" not in val and "+" not in val, val
    assert session_aes_decrypt(
        TEST_SESSION_KEY,
        urllib.parse.unquote(val)) == json.dumps(
            body, separators=(",", ":"), ensure_ascii=False)
    # groups URL: same property.
    body2, _ = find_body_with_slash(
        lambda i: {"avatar_size": 160, "member_avatar_size": 160,
                   "pad": i})
    url2 = contacts_mod._url_with_params(
        "https://group-wpa.zalo.me", contacts_mod.GROUPS_PATH,
        body2, TEST_SESSION_KEY)
    val2 = params_value(url2)
    assert "/" not in val2 and "+" not in val2, val2
    # voicecall URL: same property (protocol.voicecall_params had the
    # same quote() bug).
    body3, _ = find_body_with_slash(
        lambda i: {"calleeId": "20001", "callId": "c%d" % i,
                   "codec": "[]", "typeRequest": 0, "imei": "dev-1"})
    url3 = protocol.voicecall_params(
        "requestcall", body3, partial(session_aes_encrypt, TEST_SESSION_KEY))
    val3 = params_value(url3)
    assert "/" not in val3 and "+" not in val3, val3


def _handbuilt_url(base, path, body, use_raw_quote):
    enc = session_aes_encrypt(
        TEST_SESSION_KEY,
        json.dumps(body, separators=(",", ":"), ensure_ascii=False))
    quote = (urllib.parse.quote(enc) if use_raw_quote
             else urllib.parse.quote(enc, safe=""))
    qs = urllib.parse.urlencode(protocol.common_params())
    return "%s%s?%s&params=%s" % (base, path, qs, quote)


def test_old_friends_body_rejected():
    """Pre-fix friends body (no avatar_size) must fail the strict mock."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        old_body = {"incInvalid": 1, "page": 1, "count": 20000,
                    "actiontime": 0, "imei": "dev-1"}
        url = _handbuilt_url(mock.base, "/api/social/friend/getfriends",
                             old_body, use_raw_quote=False)
        url += "&init=1"  # isolate the failure to the body, not init
        status, payload = http_get(url, cookie="sek-test")
        assert status == 500, (status, payload)
        assert "avatar_size" in payload.get("error_message", ""), payload
    finally:
        mock.stop()


def test_old_groups_body_rejected():
    """Pre-fix groups body ({imei} only) must fail the strict mock."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        url = _handbuilt_url(mock.base, "/api/group/getlg",
                             {"imei": "dev-1"}, use_raw_quote=False)
        status, payload = http_get(url, cookie="sek-test")
        assert status == 500, (status, payload)
        assert "avatar_size" in payload.get("error_message", ""), payload
    finally:
        mock.stop()


def test_raw_slash_in_params_rejected():
    """A params value with a raw '/' (pre-fix quote() default) must fail."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        body, _ = find_body_with_slash(
            lambda i: {"incInvalid": 1, "page": 1, "count": 20000,
                       "avatar_size": 160, "actiontime": 0,
                       "imei": "dev-%d" % i})
        url = _handbuilt_url(mock.base, "/api/social/friend/getfriends",
                             body, use_raw_quote=True)
        assert "/" in params_value(url)  # precondition: raw '/' present
        url += "&init=1"
        status, payload = http_get(url, cookie="sek-test")
        assert status == 500, (status, payload)
        assert "percent-encoded" in payload.get("error_message", ""), payload
    finally:
        mock.stop()


def _start_app_server(mock, tmp):
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % port


def _api(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode()
                                 if body is not None else None)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _login_via_qr(base):
    status, body = _api(base, "POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = _api(base, "GET", "/api/qr/status")
        if last["state"] == "done":
            return
        time.sleep(0.5)
    raise AssertionError("qr did not reach done: %s" % last)


def test_contacts_error_attribution():
    """A 602 from friends vs groups must be named in the UI error, and a
    failed friends call must NOT consume the first-load init=1 flag."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-test-")
    mock = MockZalo().start()
    httpd = None
    try:
        patch_domains(mock)
        httpd, base = _start_app_server(mock, tmp)
        _login_via_qr(base)

        mock.friends_mode = "error602"
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 502 and "friends:" in body["error"], body
        assert "602" in body["error"], body

        mock.friends_mode = "ok"
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200 and body["friends"]["rows"], body

        mock.groups_mode = "error602"
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 502 and "groups:" in body["error"], body
        assert "602" in body["error"], body

        # init=1 on the two friends loads that followed a failed first
        # load (flag stays pending until a friends call succeeds), and
        # absent on the third load (after a success).
        fqs = [qs for p, qs, _ in mock.seen
               if p == "/api/social/friend/getfriends"]
        assert [q.get("init") for q in fqs] == ["1", "1", None], fqs
    finally:
        if httpd:
            httpd.shutdown()
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CONTACTS TESTS PASSED")
