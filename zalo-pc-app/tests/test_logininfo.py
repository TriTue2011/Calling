"""getLoginInfo contract tests (regression for the first real-scan 102).

The first real scan reached the grant (uid + dkey) and then failed at
getLoginInfo with server error 102, because the client sent only
zpw_ver/zpw_type + cookie. The real PC client sends the full login
envelope (imei/computer_name/language/ts + type/client_version/
signkey, encrypted when a param cipher key is configured) plus the
zpw_sek cookie. These tests pin that contract against the mock, which
now enforces it independently (openssl + hashlib).
"""

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import protocol, qr_login  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def make_transport(cookie=""):
    def http_get(url, timeout=30):
        req = urllib.request.Request(url, method="GET")
        if cookie:
            req.add_header("Cookie", "zpw_sek=" + cookie)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8"))
            except Exception:
                return e.code, {}
    return http_get


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base


def logininfo_hits(mock):
    return [(q, h) for (p, q, h) in mock.seen
            if p == "/api/login/getLoginInfo"]


def full_grant(mock, param_key):
    """Run reqqr -> scan -> confirm against the mock; return grant."""
    t = make_transport()
    qr = qr_login.fetch_qr(t, "dev-1", "testhost", [],
                           param_cipher_key=param_key)
    qr_login.wait_scan(t, qr, trust_enabled=False)
    return qr_login.wait_confirm(t, qr)


def test_logininfo_params_shape():
    before = int(time.time() * 1000)
    p = protocol.logininfo_params("dev-1", "testhost")
    after = int(time.time() * 1000)
    assert p["imei"] == "dev-1" and p["computer_name"] == "testhost"
    assert p["language"] == "vi"
    assert isinstance(p["ts"], int) and before <= p["ts"] <= after, p


def test_logininfo_plaintext_envelope():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        grant = full_grant(mock, None)
        app_server.PARAM_CIPHER_KEY = None
        state = app_server.AppState(tempfile.mkdtemp())
        info = state._fetch_login_info(grant, "dev-1", "testhost")
        assert info["zpw_enk"] == TEST_SESSION_KEY, info
        assert info["dkey"] == "dkey-test", info
        assert info["config"]["zpw_ws"] == "wss://mock.invalid/ws", info
        hits = logininfo_hits(mock)
        assert len(hits) == 1, hits
        q, h = hits[0]
        assert q["imei"] == "dev-1" and q["computer_name"] == "testhost"
        assert q["language"] == "vi" and q["ts"].isdigit()
        assert q["type"] == "embed" and q["client_version"] == "695"
        assert q["signkey"], q
        assert h["Cookie"] == "zpw_sek=sek-test", h
    finally:
        mock.stop()


def test_logininfo_encrypted_envelope():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        grant = full_grant(mock, TEST_PARAM_KEY)
        app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
        state = app_server.AppState(tempfile.mkdtemp())
        info = state._fetch_login_info(grant, "dev-1", "testhost")
        assert info["zpw_enk"] == TEST_SESSION_KEY, info
        hits = logininfo_hits(mock)
        assert len(hits) == 1 and "zcid" in hits[0][0], hits
    finally:
        mock.stop()


def test_confirm_without_sek_rejected_before_logininfo():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        mock.confirm_mode = "no_sek"
        t = make_transport()
        qr = qr_login.fetch_qr(t, "dev-1", "testhost", [])
        qr_login.wait_scan(t, qr, trust_enabled=False)
        try:
            qr_login.wait_confirm(t, qr)
            raise AssertionError("expected LoginError for missing zpw_sek")
        except qr_login.LoginError as e:
            assert "zpw_sek" in str(e), str(e)
        assert logininfo_hits(mock) == [], mock.seen
    finally:
        mock.stop()


def test_fetch_login_info_empty_sek_guard():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        state = app_server.AppState(tempfile.mkdtemp())
        grant = {"uid": "10001", "dkey": "dkey-test", "zpw_sek": ""}
        try:
            state._fetch_login_info(grant, "dev-1", "testhost")
            raise AssertionError("expected RuntimeError for empty zpw_sek")
        except RuntimeError as e:
            assert "zpw_sek" in str(e), str(e)
        assert logininfo_hits(mock) == [], mock.seen
    finally:
        mock.stop()


def test_fetch_login_info_102_surfaces():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        mock.logininfo_mode = "error102"
        grant = full_grant(mock, None)
        app_server.PARAM_CIPHER_KEY = None
        state = app_server.AppState(tempfile.mkdtemp())
        try:
            state._fetch_login_info(grant, "dev-1", "testhost")
            raise AssertionError("expected RuntimeError for error 102")
        except RuntimeError as e:
            assert "102" in str(e), str(e)
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL LOGININFO TESTS PASSED")
