"""Tests for the app login gate (zalo_pc_app/app_auth.py + server.py).

Covers: password hashing (PBKDF2, wrong password / tampered hash
fail), env config (missing user/password -> clear error, hash env
preferred over plaintext, verifier file in the data dir), sessions
(create/validate/revoke/expiry), and the HTTP gate (every /api/* and
/app.js return 401 without the app cookie, / redirects to /login,
wrong login is one generic 401, logout revokes the session).

Test credentials below are obviously fake placeholders, used only
inside these tests — never a real password.
"""

import http.client
import json
import os
import stat
import sys
import tempfile
import threading
import time

TEST_USER = "nguoi-dung-test"
TEST_PASSWORD = "mat-khau-test-123"

tmp = tempfile.mkdtemp(prefix="zalo-pc-app-auth-test-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_APP_USER"] = TEST_USER
os.environ["ZALO_PC_APP_PASSWORD"] = TEST_PASSWORD
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import app_auth  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


# -- unit: hashing ---------------------------------------------------------
def test_hash_roundtrip_and_wrong_password():
    stored = app_auth.hash_password(TEST_PASSWORD)
    assert stored.startswith("$pbkdf2-sha256$210000$")
    assert app_auth.verify_password(TEST_PASSWORD, stored) is True
    assert app_auth.verify_password("sai-mat-khau", stored) is False
    assert app_auth.verify_password("", stored) is False
    # Same password, different salt -> different hash, both verify.
    assert app_auth.hash_password(TEST_PASSWORD) != stored
    assert app_auth.verify_password(
        TEST_PASSWORD, app_auth.hash_password(TEST_PASSWORD)) is True


def test_verify_rejects_tampered_and_bad_format():
    stored = app_auth.hash_password(TEST_PASSWORD)
    assert app_auth.verify_password(TEST_PASSWORD, stored[:-4] + "AAAA") is False
    assert app_auth.verify_password(TEST_PASSWORD, "not-a-hash") is False
    assert app_auth.verify_password(TEST_PASSWORD, "") is False
    assert app_auth.verify_password(TEST_PASSWORD, None) is False


def test_from_env_missing_credentials():
    for env in ({}, {"ZALO_PC_APP_USER": "u"},
                {"ZALO_PC_APP_PASSWORD": "p"},
                {"ZALO_PC_APP_USER": "", "ZALO_PC_APP_PASSWORD": "p"}):
        try:
            app_auth.AppAuth.from_env(tmp, env=env)
        except app_auth.MissingAppCredentials as e:
            assert "ZALO_PC_APP_" in str(e), str(e)
        else:
            raise AssertionError("expected MissingAppCredentials for %r" % env)


def test_from_env_bad_hash_format():
    try:
        app_auth.AppAuth.from_env(
            tmp, env={"ZALO_PC_APP_USER": "u",
                      "ZALO_PC_APP_PASSWORD_HASH": "sha256:abc"})
    except app_auth.MissingAppCredentials as e:
        assert "PASSWORD_HASH" in str(e), str(e)
    else:
        raise AssertionError("expected MissingAppCredentials")


def test_from_env_password_writes_verifier_file():
    d = tempfile.mkdtemp(prefix="zalo-pc-app-auth-file-")
    auth = app_auth.AppAuth.from_env(
        d, env={"ZALO_PC_APP_USER": TEST_USER,
                "ZALO_PC_APP_PASSWORD": TEST_PASSWORD})
    path = os.path.join(d, "app_auth.json")
    assert os.path.exists(path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600, oct(
        os.stat(path).st_mode)
    with open(path) as f:
        assert app_auth.verify_password(TEST_PASSWORD,
                                        json.load(f)["password_hash"])
    first = open(path).read()
    # Same password on restart: verifier file unchanged (salt kept).
    app_auth.AppAuth.from_env(
        d, env={"ZALO_PC_APP_USER": TEST_USER,
                "ZALO_PC_APP_PASSWORD": TEST_PASSWORD})
    assert open(path).read() == first
    # Rotated password: file rewritten, old password fails, new works.
    auth2 = app_auth.AppAuth.from_env(
        d, env={"ZALO_PC_APP_USER": TEST_USER,
                "ZALO_PC_APP_PASSWORD": "mat-khau-moi-456"})
    assert open(path).read() != first
    assert auth2.verify(TEST_USER, "mat-khau-moi-456") is True
    assert auth2.verify(TEST_USER, TEST_PASSWORD) is False
    assert auth.verify(TEST_USER, TEST_PASSWORD) is True


def test_from_env_hash_preferred_over_password():
    d = tempfile.mkdtemp(prefix="zalo-pc-app-auth-hash-")
    stored = app_auth.hash_password("mat-khau-bang-hash-789")
    auth = app_auth.AppAuth.from_env(
        d, env={"ZALO_PC_APP_USER": TEST_USER,
                "ZALO_PC_APP_PASSWORD": TEST_PASSWORD,
                "ZALO_PC_APP_PASSWORD_HASH": stored})
    assert auth.verify(TEST_USER, "mat-khau-bang-hash-789") is True
    assert auth.verify(TEST_USER, TEST_PASSWORD) is False
    # Hash mode writes no verifier file.
    assert not os.path.exists(os.path.join(d, "app_auth.json"))


def test_verify_does_not_reveal_user_existence():
    auth = app_auth.AppAuth.from_env(
        tmp, env={"ZALO_PC_APP_USER": TEST_USER,
                  "ZALO_PC_APP_PASSWORD": TEST_PASSWORD})
    assert auth.verify("user-khong-ton-tai", TEST_PASSWORD) is False
    assert auth.verify(TEST_USER, "sai") is False
    assert auth.verify(TEST_USER, TEST_PASSWORD) is True


def test_sessions_create_validate_revoke_expiry():
    auth = app_auth.AppAuth.from_env(
        tmp, env={"ZALO_PC_APP_USER": TEST_USER,
                  "ZALO_PC_APP_PASSWORD": TEST_PASSWORD,
                  "ZALO_PC_APP_SESSION_HOURS": "8"})
    token, expires = auth.create_session(TEST_USER)
    assert auth.validate_token(token) == TEST_USER
    assert auth.validate_token("token-la") is None
    assert auth.validate_token("") is None
    assert auth.session_count() == 1
    assert auth.revoke_token(token) is True
    assert auth.validate_token(token) is None
    assert auth.revoke_token(token) is False
    # Expired token is rejected (and purged).
    token2, _ = auth.create_session(TEST_USER)
    with auth._lock:
        user, _exp = auth._sessions[token2]
        auth._sessions[token2] = (user, time.time() - 1)
    assert auth.validate_token(token2) is None
    assert auth.session_count() == 0


def test_cookie_headers():
    header = app_auth.cookie_header("tok-test", 28800)
    assert "zalo_pc_app=tok-test" in header
    assert "HttpOnly" in header and "SameSite=Lax" in header
    assert "Path=/" in header and "Max-Age=28800" in header
    assert "Secure" not in header  # plain HTTP by default
    cleared = app_auth.clear_cookie_header()
    assert "zalo_pc_app=" in cleared and "Max-Age=0" in cleared


def test_state_without_env_has_no_auth():
    saved = {k: os.environ.pop(k, None) for k in
             ("ZALO_PC_APP_USER", "ZALO_PC_APP_PASSWORD",
              "ZALO_PC_APP_PASSWORD_HASH")}
    try:
        state = app_server.AppState(tempfile.mkdtemp())
        assert state.auth is None, "must not invent credentials"
        assert "ZALO_PC_APP_USER" in state.auth_error, state.auth_error
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# -- HTTP gate ---------------------------------------------------------------
class Client:
    def __init__(self, port):
        self.port = port
        self.cookie = ""

    def req(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        headers = {"Content-Type": "application/json"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request(method, path,
                     json.dumps(body).encode() if body is not None else None,
                     headers)
        resp = conn.getresponse()
        raw = resp.read()
        set_cookie = resp.getheader("Set-Cookie") or ""
        conn.close()
        try:
            parsed = json.loads(raw.decode())
        except Exception:
            parsed = None
        return resp.status, dict(resp.getheaders()), set_cookie, raw, parsed

    def login(self, user=TEST_USER, password=TEST_PASSWORD):
        status, _h, set_cookie, _raw, body = self.req(
            "POST", "/api/app/login", {"username": user, "password": password})
        if status == 200 and set_cookie:
            self.cookie = set_cookie.split(";", 1)[0]
        return status, body, set_cookie


def test_http_gate():
    from http.server import ThreadingHTTPServer
    state = app_server.AppState(tmp)
    assert state.auth is not None, state.auth_error
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        c = Client(port)
        # Unauthenticated: / redirects to /login; every /api/* is 401.
        status, headers, _sc, _raw, _b = c.req("GET", "/")
        assert status == 302 and headers.get("Location") == "/login", (status, headers)
        status, _h, _sc, raw, _b = c.req("GET", "/login")
        assert status == 200 and "Đăng nhập".encode() in raw, status
        assert "Tên đăng nhập".encode() in raw
        status, _h, _sc, _raw, _b = c.req("GET", "/style.css")
        assert status == 200, status  # login page resource: public
        status, _h, _sc, _raw, _b = c.req(
            "GET", "/fonts/ibmplexsans-400-latin.woff2")
        assert status == 200, status  # login page resource: public
        status, _h, _sc, _raw, _b = c.req("GET", "/app.js")
        assert status == 401, status  # app code: protected
        for method, path in [
                ("GET", "/api/status"), ("GET", "/api/qr/status"),
                ("GET", "/api/engine/status"), ("GET", "/api/contacts"),
                ("GET", "/api/calls"), ("GET", "/api/svc/catalog"),
                ("GET", "/api/khong-co"),
                ("POST", "/api/qr/new"), ("POST", "/api/call/request"),
                ("POST", "/api/call/end"), ("POST", "/api/logout")]:
            status, _h, _sc, _raw, body = c.req(method, path, {})
            assert status == 401, (method, path, status, body)
            assert body and body.get("error") == "chua_dang_nhap_app", body
        status, _h, _sc, _raw, body = c.req("GET", "/api/app/status")
        assert status == 200 and body == {"logged_in": False,
                                           "username": ""}, body

        # Wrong login: one generic 401, no cookie, same body for a
        # wrong user and a wrong password (no user-existence leak).
        status, body, set_cookie = c.login(user="user-khong-ton-tai")
        assert status == 401 and body == {"error": "sai_tai_khoan"}, body
        assert not set_cookie, set_cookie
        status, body, set_cookie = c.login(password="sai-mat-khau")
        assert status == 401 and body == {"error": "sai_tai_khoan"}, body
        assert not set_cookie, set_cookie
        status, body, set_cookie = c.login(user="", password="")
        assert status == 401, status

        # Correct login: 200 + HttpOnly session cookie.
        status, body, set_cookie = c.login()
        assert status == 200 and body.get("ok") is True, body
        assert "zalo_pc_app=" in set_cookie, set_cookie
        assert "HttpOnly" in set_cookie and "SameSite=Lax" in set_cookie
        max_age = int(set_cookie.split("Max-Age=")[1].split(";")[0])
        assert 28790 <= max_age <= 28800, max_age  # 8h, tru 1s xu ly
        assert TEST_PASSWORD not in set_cookie
        assert TEST_PASSWORD not in json.dumps(body)

        # Authenticated: / serves the app, /login bounces back,
        # /api/status works and names the app user (never secrets).
        status, _h, _sc, raw, _b = c.req("GET", "/")
        assert status == 200 and "Danh bạ".encode() in raw, status
        status, headers, _sc, _raw, _b = c.req("GET", "/login")
        assert status == 302 and headers.get("Location") == "/", (status, headers)
        status, _h, _sc, _raw, body = c.req("GET", "/api/status")
        assert status == 200, body
        assert body.get("app_user") == TEST_USER, body
        blob = json.dumps(body)
        assert TEST_PASSWORD not in blob
        assert "app_auth" not in blob and "pbkdf2" not in blob
        status, _h, _sc, _raw, body = c.req("GET", "/api/app/status")
        # Khi da dang nhap con co co `can_change_password` (khong nhay cam);
        # trang /login (chua dang nhap) van chi thay logged_in + username.
        assert status == 200 and body == {"logged_in": True,
                                           "username": TEST_USER,
                                           "can_change_password": True}, body
        status, _h, _sc, _raw, body = c.req("GET", "/api/calls")
        # No Zalo login yet: still 401, but for the ZALO session —
        # the app gate itself passed (different error code).
        assert status == 401 and body.get("error") == "chua_dang_nhap", body

        # /api/app/logout revokes the session and clears the cookie.
        status, _h, set_cookie, _raw, body = c.req("POST", "/api/app/logout")
        assert status == 200 and body.get("ok") is True, body
        assert "Max-Age=0" in set_cookie, set_cookie
        c.cookie = ""
        status, _h, _sc, _raw, body = c.req("GET", "/api/status")
        assert status == 401, body

        # /api/logout (sidebar button) also revokes the app session.
        c.login()
        status, _h, set_cookie, _raw, body = c.req("POST", "/api/logout", {})
        assert status == 200 and body.get("ok") is True, body
        assert "Max-Age=0" in set_cookie, set_cookie
        c.cookie = ""
        status, _h, _sc, _raw, body = c.req("GET", "/api/status")
        assert status == 401, body
        httpd.shutdown()
    finally:
        try:
            httpd.shutdown()
        except Exception:
            pass


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
        else:
            print("PASS %s" % t.__name__)
    print("%d/%d tests passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
