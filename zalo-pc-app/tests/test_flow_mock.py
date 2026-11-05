"""Full QR-login + signaling + contacts flow against the mock server.

The mock verifies the wire format independently (openssl + hashlib),
so passing here means the client speaks the protocol, not just itself.
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import contacts as contacts_mod  # noqa: E402
from zalo_pc_app import protocol, qr_login, signaling  # noqa: E402


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


def test_full_flow_encrypted():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        t = make_transport()
        qr = qr_login.fetch_qr(t, "dev-1", "testhost", [],
                               param_cipher_key=TEST_PARAM_KEY)
        assert qr["chk_wait_scan"] == mock.base + "/scan"
        assert qr["qr_timeout"] == 5
        event = qr_login.wait_scan(t, qr, trust_enabled=False)
        assert event["display_name"] == "Tester"
        grant = qr_login.wait_confirm(t, qr)
        assert grant["uid"] == "10001" and grant["zpw_sek"] == "sek-test"
        # Post-login calls with the session cookie + session key.
        t2 = make_transport("sek-test")
        sig = signaling.Signaling(t2, "dev-1", TEST_SESSION_KEY)
        data = sig.request_call("20001", "call-1", None, 0)
        assert data["body"]["calleeId"] == "20001", data
        assert data["body"]["codec"] == "[]", data
        book = contacts_mod.Contacts(t2, "dev-1", TEST_SESSION_KEY)
        friends = book.friends()
        assert [r["name"] for r in friends["rows"]] == ["Ban A", "Ban B"]
        groups = book.groups()
        assert groups["rows"][0]["name"] == "Nhom X"
    finally:
        mock.stop()


def test_full_flow_plaintext():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        t = make_transport()
        qr = qr_login.fetch_qr(t, "dev-1", "testhost", [],
                               param_cipher_key=None)
        assert qr["chk_wait_scan"].endswith("/scan")
        grant = qr_login.wait_confirm(t, qr)
        assert grant["uid"] == "10001"
    finally:
        mock.stop()


def test_rejected_and_expired_and_ratelimit():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        t = make_transport()
        mock.confirm_mode = "reject"
        qr = qr_login.fetch_qr(t, "dev-1", "testhost", [])
        try:
            qr_login.wait_confirm(t, qr)
            raise AssertionError("expected UserRejected")
        except qr_login.UserRejected:
            pass
        mock.confirm_mode = "ok"
        mock.scan_mode = "timeout"
        qr = qr_login.fetch_qr(t, "dev-1", "testhost", [])
        try:
            qr_login.wait_scan(t, qr)
            raise AssertionError("expected QRExpired")
        except qr_login.QRExpired:
            pass
        mock.scan_mode = "ok"
        mock.reqqr_mode = "rate_limit"
        try:
            qr_login.fetch_qr(t, "dev-1", "testhost", [])
            raise AssertionError("expected RateLimited")
        except qr_login.RateLimited as e:
            assert e.wait_seconds >= 20
    finally:
        mock.stop()


def test_trust_flow_refused_and_19000_fallback():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        t = make_transport()
        mock.scan_mode = "trust"
        qr = qr_login.fetch_qr(t, "dev-1", "testhost", [])
        try:
            qr_login.wait_scan(t, qr, trust_enabled=False)
            raise AssertionError("expected TrustFlowRequired")
        except qr_login.TrustFlowRequired:
            pass
        mock.scan_mode = "ok"
        mock.reqqr_mode = "force_plaintext_once"
        qr = qr_login.fetch_qr(t, "dev-1", "testhost", [],
                               param_cipher_key=TEST_PARAM_KEY)
        assert qr["chk_wait_scan"].endswith("/scan")
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL FLOW TESTS PASSED")
