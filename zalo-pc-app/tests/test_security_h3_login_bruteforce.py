"""Tests H3: chong brute-force o /api/app/login (app_auth + server).

Sau 5 lan sai lien tiep tu cung IP: IP do bi khoa tam 5 phut
(HTTP 429, khong kiem mat khau nua). Dem rieng theo IP, dang nhap
dung reset bo dem, 1-4 lan sai chua bi khoa. Trang thai khoa chi
trong bo nho tien trinh (restart la het).

Mat khau duoi day la gia lap ro rang, chi dung trong test — khong
phai mat khau that. Khong log mat khau da thu.
"""

import http.client
import io
import json
import os
import sys
import tempfile
import threading
import time
from contextlib import redirect_stdout

TEST_USER = "nguoi-dung-test-h3"
TEST_PASSWORD = "mat-khau-test-h3-123"
WRONG_PASSWORD = "sai-mat-khau-h3"
IP_A = "203.0.113.10"
IP_B = "198.51.100.20"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import app_auth  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


class FakeClock:
    """Dong ho gia: test khong phai cho that 5 phut."""

    def __init__(self, start=1_700_000_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _make_auth(clock=None):
    return app_auth.AppAuth(
        TEST_USER, app_auth.hash_password(TEST_PASSWORD),
        time_fn=clock)


# -- unit: bo dem theo IP ---------------------------------------------
def test_5_failures_lock_6th_blocked():
    clock = FakeClock()
    auth = _make_auth(clock)
    for i in range(5):
        assert auth.is_locked(IP_A) is False, "lan sai %d chua duoc khoa" % (i + 1)
        auth.record_failed_login(IP_A)
    assert auth.is_locked(IP_A) is True
    assert auth.lock_remaining(IP_A) > 0
    assert auth.lock_remaining(IP_A) <= 300


def test_lock_expires_after_5_minutes():
    clock = FakeClock()
    auth = _make_auth(clock)
    for _ in range(5):
        auth.record_failed_login(IP_A)
    assert auth.is_locked(IP_A) is True
    clock.advance(299)
    assert auth.is_locked(IP_A) is True, "chua het 5 phut phai con khoa"
    clock.advance(2)
    assert auth.is_locked(IP_A) is False, "qua 5 phut phai het khoa"
    assert auth.failed_count(IP_A) == 0, "het khoa thi bo dem reset"


def test_other_ip_unaffected():
    clock = FakeClock()
    auth = _make_auth(clock)
    for _ in range(5):
        auth.record_failed_login(IP_A)
    assert auth.is_locked(IP_A) is True
    assert auth.is_locked(IP_B) is False
    assert auth.failed_count(IP_B) == 0
    auth.record_failed_login(IP_B)
    assert auth.is_locked(IP_B) is False


def test_1_to_4_failures_not_locked():
    clock = FakeClock()
    auth = _make_auth(clock)
    for i in range(1, 5):
        auth.record_failed_login(IP_A)
        assert auth.is_locked(IP_A) is False, "%d lan sai chua duoc khoa" % i
        assert auth.failed_count(IP_A) == i


def test_success_resets_counter():
    clock = FakeClock()
    auth = _make_auth(clock)
    for _ in range(4):
        auth.record_failed_login(IP_A)
    assert auth.failed_count(IP_A) == 4
    auth.record_successful_login(IP_A)
    assert auth.failed_count(IP_A) == 0
    assert auth.is_locked(IP_A) is False
    # Sau reset phai du 5 lan sai moi moi khoa lai, khong phai 1.
    for _ in range(4):
        auth.record_failed_login(IP_A)
    assert auth.is_locked(IP_A) is False
    auth.record_failed_login(IP_A)
    assert auth.is_locked(IP_A) is True


def test_failed_login_logged_without_password():
    clock = FakeClock()
    auth = _make_auth(clock)
    buf = io.StringIO()
    with redirect_stdout(buf):
        auth.record_failed_login(IP_A)
        for _ in range(4):
            auth.record_failed_login(IP_A)
    out = buf.getvalue()
    assert IP_A in out, out
    assert WRONG_PASSWORD not in out and TEST_PASSWORD not in out, out


# -- HTTP: /api/app/login ----------------------------------------------
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
        return resp.status, set_cookie, parsed

    def login(self, user=TEST_USER, password=TEST_PASSWORD):
        status, set_cookie, body = self.req(
            "POST", "/api/app/login", {"username": user, "password": password})
        if status == 200 and set_cookie:
            self.cookie = set_cookie.split(";", 1)[0]
        return status, body, set_cookie


def _serve(auth):
    tmp = tempfile.mkdtemp(prefix="zalo-pc-app-h3-test-")
    state = app_server.AppState(tmp, auth=auth)
    assert state.auth is not None
    app_server.STATE = state
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, Client(port)


def test_http_5_wrong_then_6th_locked_even_with_right_password():
    clock = FakeClock()
    auth = _make_auth(clock)
    httpd, c = _serve(auth)
    try:
        for i in range(5):
            status, body, _sc = c.login(password=WRONG_PASSWORD)
            assert status == 401 and body == {"error": "sai_tai_khoan"}, (i, status, body)
        # Lan thu 6 — dung mat khau that van bi chan: khoa roi thi
        # khong kiem mat khau nua, khong cap cookie.
        status, body, set_cookie = c.login(password=TEST_PASSWORD)
        assert status == 429, (status, body)
        assert body.get("error") == "bi_khoa_tam_thoi", body
        assert body.get("retry_after", 0) > 0, body
        assert not set_cookie, set_cookie
        # Het 5 phut (dong ho gia): dang nhap dung lai duoc.
        clock.advance(301)
        status, body, set_cookie = c.login(password=TEST_PASSWORD)
        assert status == 200 and body.get("ok") is True, (status, body)
        assert "zalo_pc_app=" in set_cookie, set_cookie
    finally:
        httpd.shutdown()


def test_http_correct_login_after_few_failures_resets():
    clock = FakeClock()
    auth = _make_auth(clock)
    httpd, c = _serve(auth)
    try:
        for _ in range(4):
            status, body, _sc = c.login(password=WRONG_PASSWORD)
            assert status == 401, (status, body)
        # 4 lan sai chua khoa: dang nhap dung van duoc ngay, khong cham.
        t0 = time.monotonic()
        status, body, set_cookie = c.login(password=TEST_PASSWORD)
        assert status == 200 and body.get("ok") is True, (status, body)
        assert time.monotonic() - t0 < 5, "dang nhap dung khong duoc cham"
        assert "zalo_pc_app=" in set_cookie
        # Sau dang nhap dung, bo dem reset: can du 5 lan sai moi khoa.
        c.cookie = ""
        for _ in range(4):
            status, _b, _sc = c.login(password=WRONG_PASSWORD)
            assert status == 401, status
        status, body, _sc = c.login(password=TEST_PASSWORD)
        assert status == 200, (status, body)
    finally:
        httpd.shutdown()


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
