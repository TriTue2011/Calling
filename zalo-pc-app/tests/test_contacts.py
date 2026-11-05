"""Contacts contract tests (bug 602, 2026-11-05).

The real Zalo server rejected the contacts calls with error_code=602
"zpw_type bị thiếu hoặc không đúng" after a successful QR login. Static
comparison against the real PC client showed the request skeleton was
right (zpw_ver=695, domains, cookie, session key) but wire-format
details were wrong:
  1. friends body missed avatar_size=160 (and init=1 on first load);
  2. groups must follow the ADDON path (§7i in bao-cao.md): GET
     getlg/v4 (no body) returns {version, gridVerMap}, then POST
     getmg-v2 with {gridVerMap: "{groupId: 0}"} returns
     {gridInfoMap} with names/avatars/topMember. The old getlg/v3
     list path was the PC client's list path, not the addon's, and
     is no longer used (nor served by the mock);
  3. the params base64 value was not fully percent-encoded (raw '/').
  4. zpw_type must be the NUMBER 30, not the string "embed" (bundle
     config: apiType:"embed"===__ZaBUNDLENAME__?31:30, bundle name
     "compact-app-pc" -> 30; see bao-cao.md 7d). The old code sent
     "embed": friends passed because profile-wpa tolerates it, but
     group-wpa validates it strictly and answered 602 — twice, for
     both getlg v1 and getlg/v3 (found live after 7bc97bf).
  5. Post-login responses are a TWO-LAYER envelope (bundle kCOK
     unwrap): outer {error_code: 0, data: "<AES base64 string>"} —
     the data field is ciphertext; the inner {error_code, data}
     only appears after AES-decrypting it with the session key.
     The old client returned payload["data"] directly, so both
     endpoints silently parsed an encrypted STRING as "no items"
     while the outer error_code stayed 0: the UI showed empty tabs
     with no error (live: the account has friends and groups for
     real, 0/0 in our app — see bao-cao.md 7g). The mock now returns
     the real double-enveloped shape, and these tests pin the
     decryption.
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


def http_post(url, form, cookie="", timeout=15):
    req = urllib.request.Request(url, method="POST",
                                 data=form.encode("utf-8"))
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if cookie:
        req.add_header("Cookie", "zpw_sek=" + cookie)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def make_book():
    return contacts_mod.Contacts(
        partial(http_get, cookie="sek-test"), "dev-1", TEST_SESSION_KEY,
        partial(http_post, cookie="sek-test"))


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
        book = make_book()
        friends = book.friends(init=True)
        assert [r["name"] for r in friends["rows"]] == \
            ["Ban A", "Ban B", "Ban C"]
        assert [r["id"] for r in friends["rows"]] == \
            ["20001", "20002", "20003"]
        groups = book.groups()
        assert [r["name"] for r in groups["rows"]] == ["Nhom X", "Nhom Y"]
        # Raw group ids (not userId) — the id must be the raw groupId,
        # otherwise tapping a group would call with an empty peer id.
        # Avatar comes from avt, not avatar. Members come from the
        # getmg-v2 topMember list and feed the group call's partners.
        assert [r["id"] for r in groups["rows"]] == ["30001", "30002"]
        assert [r["avatar"] for r in groups["rows"]] == ["avt-x", ""]
        assert [r["members"] for r in groups["rows"]] == \
            [["20001", "20002"], ["20001"]]
        # Addon path: exactly one v4 GET (the version map) and one
        # getmg-v2 POST (the details) — no pagination, no v3.
        v4paths = [p for p, _, _ in mock.seen
                   if p == "/api/group/getlg/v4"]
        assert len(v4paths) == 1, v4paths
        mgpaths = [p for p, _, _ in mock.seen
                   if p == "/api/group/getmg-v2"]
        assert len(mgpaths) == 1, mgpaths
        assert not [p for p, _, _ in mock.seen
                    if p == "/api/group/getlg/v3"], mock.seen
        # The mock saw the right common params + init on first load.
        fqs = [qs for p, qs, _ in mock.seen
               if p == "/api/social/friend/getfriends"][0]
        assert fqs["zpw_ver"] == "695" and fqs["zpw_type"] == "30"
        assert fqs["init"] == "1", fqs
    finally:
        mock.stop()


def test_extract_rows_real_shapes():
    """_extract_rows against the REAL friends shape (bundle-verified):
    bare array of {userId, displayName|zaloName, avatar}. The old
    extractor missed zaloName — so a zaloName-only friend showed its
    numeric id instead of its name. Also pins the defensive
    fallbacks ("rows" container, item nested under "profile") and
    the empty-account case. Groups are NOT parsed here — they come
    from gridInfoMap via _group_row (see test_group_row_from_info)."""
    ext = contacts_mod._extract_rows
    # Friends: bare array; one friend has only zaloName, one only
    # snake_case fields.
    rows = ext([
        {"userId": "20001", "displayName": "Ban A", "avatar": "a1"},
        {"userId": "20002", "zaloName": "Ban B", "avatar": ""},
        {"uid": "20003", "display_name": "Ban C",
         "zalo_name": "Ban C", "avatar": ""},
    ])
    assert [(r["id"], r["name"]) for r in rows] == [
        ("20001", "Ban A"), ("20002", "Ban B"), ("20003", "Ban C")], rows
    # Defensive fallbacks: "rows" container key, item under "profile".
    assert ext({"rows": [{"userId": "1", "displayName": "Mot"}]}) == [
        {"id": "1", "name": "Mot", "avatar": ""}]
    assert ext([{"profile": {"userId": "2", "displayName": "Hai"}}]) == [
        {"id": "2", "name": "Hai", "avatar": ""}]
    # Empty account: empty array -> no rows, and items without any id
    # or name are skipped (not rendered blank).
    assert ext([]) == []
    assert ext([{"foo": 1}]) == []


def test_group_row_from_info():
    """_group_row against REAL getmg-v2 gridInfoMap items (bundle
    _preFormatData + zca-js GroupInfo): name -> displayName,
    avt -> avatar, topMember [{id}] -> members (the group call's
    partners). Missing info yields an empty-name row with the id
    kept, not a crash."""
    row = contacts_mod._group_row("30001", {
        "groupId": "30001", "name": "Nhom X", "avt": "avt-x",
        "fullAvt": "full-x", "creatorId": "20001",
        "topMember": [{"id": "20001", "displayName": "Ban A"},
                      {"id": "20002", "displayName": "Ban B"}],
        "totalMember": 2, "type": 1})
    assert row == {"id": "30001", "name": "Nhom X", "avatar": "avt-x",
                   "members": ["20001", "20002"]}, row
    # Member entries may carry userId instead of id; a missing info
    # dict still yields a row with the id (name empty).
    row = contacts_mod._group_row("30002", {
        "groupId": "30002", "name": "Nhom Y", "avt": "",
        "topMember": [{"userId": "20001"}]})
    assert row["members"] == ["20001"], row
    assert contacts_mod._group_row("30003", None) == {
        "id": "30003", "name": "", "avatar": "", "members": []}


def test_empty_account():
    """Mock modes "empty": an account with no friends and no groups
    must load contacts successfully with empty rows — not an error.
    (Live, the UI showed empty tabs with no error after bd380d1; the
    counts on the tabs now make this case visible: "Bạn bè (0)" /
    "Nhóm (0)" means the account is empty, while a non-zero count
    with no names would mean a parsing bug.)"""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        mock.friends_mode = "empty"
        mock.groups_mode = "empty"
        book = make_book()
        assert book.friends(init=True)["rows"] == []
        assert book.groups()["rows"] == []
        # An empty v4 map means NO getmg-v2 call at all.
        assert not [p for p, _, _ in mock.seen
                    if p == "/api/group/getmg-v2"], mock.seen
    finally:
        mock.stop()


def _stub_transport(payload):
    def http_get_stub(url, timeout=30):
        return 200, payload
    return http_get_stub


def test_double_envelope_decrypted():
    """Regression test for the live 0/0 bug: the server's outer data
    is an AES-encrypted STRING. A client that returns payload["data"]
    directly parses a string as "no items" and reports 0 friends /
    0 groups with no error (outer error_code stays 0). The fixed
    client decrypts the inner envelope and returns the real rows."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        book = make_book()
        friends = book.friends(init=True)
        assert [r["name"] for r in friends["rows"]] == \
            ["Ban A", "Ban B", "Ban C"]
        # The decrypted inner data is a bare list, not a string.
        assert isinstance(friends["raw"], list), friends["raw"]
        groups = book.groups()
        assert [r["name"] for r in groups["rows"]] == ["Nhom X", "Nhom Y"]
        assert isinstance(groups["raw"], dict), groups["raw"]
        assert "gridInfoMap" in groups["raw"], groups["raw"]
        # And the wire shape itself: the mock's outer data is an
        # encrypted string (second friends load sends no init=1).
        body = {"incInvalid": 1, "page": 1, "count": 20000,
                "avatar_size": 160, "actiontime": 0, "imei": "dev-1"}
        enc = session_aes_encrypt(
            TEST_SESSION_KEY,
            json.dumps(body, separators=(",", ":"), ensure_ascii=False))
        qs = {"zpw_ver": "695", "zpw_type": "30", "params": enc}
        raw_qs = ("zpw_ver=695&zpw_type=30&params="
                  + urllib.parse.quote(enc, safe=""))
        # _friends returns the body dict itself (route() wraps it
        # in a (status, body) tuple — do not unpack it here).
        payload = mock._friends(qs, {"Cookie": "sek-test"}, raw_qs)
        assert payload["error_code"] == 0, payload
        assert isinstance(payload["data"], str), payload
        inner = json.loads(session_aes_decrypt(
            TEST_SESSION_KEY, payload["data"]))
        assert inner["error_code"] == 0 and len(inner["data"]) == 3, inner
    finally:
        mock.stop()


def test_inner_error_raises():
    """An inner error_code != 0 (inside the encrypted envelope) must
    raise, naming the inner code — the outer error_code is 0 here."""
    inner = {"error_code": 1234, "error_message": "inner boom",
             "data": {}}
    payload = {"error_code": 0,
               "data": session_aes_encrypt(
                   TEST_SESSION_KEY, json.dumps(inner))}
    book = contacts_mod.Contacts(_stub_transport(payload), "dev-1",
                                 TEST_SESSION_KEY)
    try:
        book.friends(init=True)
        raise AssertionError("expected RuntimeError for inner error")
    except RuntimeError as e:
        assert "1234" in str(e), e


def test_missing_outer_data_empty():
    """Outer error_code 0 with no data field resolves to empty rows,
    not a crash (the client's unwrap resolves undefined here)."""
    book = contacts_mod.Contacts(
        _stub_transport({"error_code": 0}), "dev-1", TEST_SESSION_KEY)
    assert book.friends(init=True)["rows"] == []
    assert book.groups()["rows"] == []


def test_describe_shape_no_values():
    """describe_shape logs only types, lengths and key names — never
    a name, id, phone number or any other personal value."""
    desc = contacts_mod.describe_shape([
        {"userId": "20001", "displayName": "Ban A", "avatar": "a1"},
        {"userId": "20002", "zaloName": "Ban B", "avatar": ""}])
    assert "len=2" in desc and "userId" in desc and "displayName" in desc
    for secret in ("Ban A", "Ban B", "20001", "20002", "a1"):
        assert secret not in desc, desc
    # v4 version map: {version, gridVerMap: {id: version}} — the map
    # is a dict of strings, so only its length is reported.
    desc = contacts_mod.describe_shape({
        "version": "1", "gridVerMap": {"30001": "1", "30002": "1"}})
    assert "gridVerMap len=2" in desc, desc
    for secret in ("30001", "30002"):
        assert secret not in desc, desc
    # getmg-v2 info map: {gridInfoMap: {id: {name, avt, ...}}} — the
    # first item's KEYS are reported, never its values.
    desc = contacts_mod.describe_shape({
        "removedsGroup": [], "unchangedsGroup": [],
        "gridInfoMap": {"30001": {"groupId": "30001", "name": "Nhom X",
                                  "avt": "x", "topMember": []}}})
    assert "gridInfoMap len=1" in desc and "groupId" in desc, desc
    assert "topMember" in desc, desc
    for secret in ("Nhom X", "30001", "x"):
        assert secret not in desc, desc
    assert contacts_mod.describe_shape(None) == "null"
    assert contacts_mod.describe_shape("ciphertext...") == "str"


def test_shape_log_printed():
    """friends()/groups() print shape-only lines to stdout; the
    lines carry counts/keys but no personal values. Groups now log
    TWO lines: the v4 version map and the getmg-v2 info map."""
    import contextlib
    import io
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        book = make_book()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            book.friends(init=True)
            book.groups()
        out = buf.getvalue()
        assert "[contacts-shape] friends" in out, out
        assert "[contacts-shape] groups v4" in out, out
        assert "[contacts-shape] groups info" in out, out
        assert "rows=3" in out and "rows=2" in out, out
        for secret in ("Ban A", "Ban B", "Ban C", "Nhom X", "Nhom Y",
                       "20001", "30001"):
            assert secret not in out, out
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
    # groups form: getmg-v2 body {gridVerMap: "<JSON string>"} — the
    # form value must have no raw '/' or '+', and must decrypt back.
    body2, _ = find_body_with_slash(
        lambda i: {"gridVerMap": json.dumps({"30001": 0, "30002": 0},
                                            separators=(",", ":")),
                   "pad": i})
    form2 = protocol.group_info_multi_form(
        body2, partial(session_aes_encrypt, TEST_SESSION_KEY))
    val2 = params_value(form2)
    assert "/" not in val2 and "+" not in val2, val2
    assert session_aes_decrypt(
        TEST_SESSION_KEY,
        urllib.parse.unquote(val2)) == json.dumps(
            body2, separators=(",", ":"), ensure_ascii=False)
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


def _handbuilt_url_with_type(base, path, body, zpw_type):
    """Like _handbuilt_url but with an explicit zpw_type value, to
    reproduce the pre-fix request (zpw_type="embed") against the mock."""
    enc = session_aes_encrypt(
        TEST_SESSION_KEY,
        json.dumps(body, separators=(",", ":"), ensure_ascii=False))
    qs = urllib.parse.urlencode({"zpw_ver": 695, "zpw_type": zpw_type})
    return "%s%s?%s&params=%s" % (
        base, path, qs, urllib.parse.quote(enc, safe=""))


def test_groups_v4_zpwtype_embed_rejected():
    """Pre-fix groups call (getlg/v4, but zpw_type="embed") must be
    rejected with the real server's 602 — group-wpa validates
    zpw_type strictly. The correct value is the numeric 30."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        url = protocol.build_url(
            mock.base, "/api/group/getlg/v4",
            {"zpw_ver": 695, "zpw_type": "embed"})
        status, payload = http_get(url, cookie="sek-test")
        assert status == 200, (status, payload)
        assert payload.get("error_code") == 602, payload
        assert "zpw_type" in payload.get("error_message", ""), payload
    finally:
        mock.stop()


def test_friends_zpwtype_embed_accepted():
    """Documents the observed live asymmetry: friends (profile-wpa)
    ACCEPTED zpw_type="embed" while groups 602'd on the same value.
    The client now sends 30 everywhere (the real client's value);
    this test only pins why the two endpoints behaved differently."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        url = _handbuilt_url_with_type(
            mock.base, "/api/social/friend/getfriends",
            {"incInvalid": 1, "page": 1, "count": 20000,
             "avatar_size": 160, "actiontime": 0, "imei": "dev-1"},
            "embed")
        url += "&init=1"
        status, payload = http_get(url, cookie="sek-test")
        assert status == 200, (status, payload)
        assert payload.get("error_code") == 0, payload
        # Real friends shape: outer data is an AES-encrypted STRING
        # (double envelope); decrypting it gives the inner data,
        # a bare array (not {"friends": [...]}).
        assert isinstance(payload["data"], str), payload
        inner = json.loads(session_aes_decrypt(
            TEST_SESSION_KEY, payload["data"]))
        assert inner["error_code"] == 0, inner
        assert isinstance(inner["data"], list) and inner["data"], inner
    finally:
        mock.stop()


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


def test_group_info_wrong_body_rejected():
    """A getmg-v2 call whose body lacks gridVerMap (or sends it as a
    nested object instead of a JSON string) must fail the strict
    mock — both real clients send gridVerMap: JSON.stringify(map)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        url = protocol.group_info_multi_url().replace(
            "https://group-wpa.zalo.me", mock.base)
        for bad_body in ({"foo": 1},
                         {"gridVerMap": {"30001": 0}}):
            form = protocol.group_info_multi_form(
                bad_body, partial(session_aes_encrypt, TEST_SESSION_KEY))
            status, payload = http_post(url, form, cookie="sek-test")
            assert status == 500, (status, payload)
            assert "gridVerMap" in payload.get("error_message", ""), payload
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
