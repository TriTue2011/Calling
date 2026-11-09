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
from zalo_pc_app import server as app_server  # noqa: E402


def make_transport(cookie=""):
    # The real server.make_transport: callable http_get + .http_post
    # (getmg-v2 is a POST). Reuse it so the test exercises the same
    # shape the app runs with.
    return app_server.make_transport(cookie)


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
        # Corrected requestcall contract (§7k): typeRequest 1 (1-1
        # audio) + callId a uint32 JSON number — the old (0, "call-1")
        # draws inner 114 from the mock, like the real server.
        data = sig.request_call("20001", 1762345678, None, 1)
        assert data["body"]["calleeId"] == "20001", data
        assert data["body"]["codec"] == protocol.DEFAULT_CODEC, data
        assert data["body"]["typeRequest"] == 1, data
        assert data["body"]["callId"] == 1762345678, data
        book = contacts_mod.Contacts(t2, "dev-1", TEST_SESSION_KEY,
                                     t2.http_post)
        # First friends load sends init=1 (real client _isFirstReq()).
        friends = book.friends(init=True)
        # Real shape: bare array; "Ban B" has only zaloName, "Ban C"
        # only snake_case fields — all three must resolve to names.
        assert [r["name"] for r in friends["rows"]] == \
            ["Ban A", "Ban B", "Ban C"]
        assert [r["id"] for r in friends["rows"]] == \
            ["20001", "20002", "20003"]
        # A second load must NOT send init again.
        book.friends()
        groups = book.groups()
        assert groups["rows"][0]["name"] == "Nhom X"
        # Raw group items: id is the raw groupId, avatar comes from avt.
        assert groups["rows"][0]["id"] == "30001"
        assert groups["rows"][0]["avatar"] == "avt-x"
        # Members come from the getmg-v2 topMember list.
        assert groups["rows"][0]["members"] == ["20001", "20002"]
        assert groups["rows"][1]["members"] == ["20001"]
    finally:
        mock.stop()


def test_group_call_uses_group_endpoint():
    """Calls are addressed by threadID (addon/zca-js model): a group
    tap must go to /api/voicecall/group/requestcall (code 12433)
    with {groupId, callId, typeRequest, data, partners} — NOT to the
    1-1 /api/voicecall/requestcall (11300) with the group id as
    calleeId. The 1-1 path keeps working unchanged (calleeId is the
    user threadId)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        t2 = make_transport("sek-test")
        sig = signaling.Signaling(t2, "dev-1", TEST_SESSION_KEY)
        # partners are the group's members, loaded via getmg-v2
        # topMember (addon path) — not [].
        data = sig.request_call_group("30001", 1762345678, 5, None,
                                      ["20001", "20002"])
        assert data["body"]["groupId"] == "30001", data
        assert data["body"]["callId"] == 1762345678, data
        assert data["body"]["typeRequest"] == 5, data
        assert data["body"]["partners"] == ["20001", "20002"], data
        assert "imei" not in data["body"], data  # bundle: no imei
        gpaths = [p for p, _, _ in mock.seen
                  if p == "/api/voicecall/group/requestcall"]
        assert len(gpaths) == 1, gpaths
        # 1-1 still uses its own endpoint with calleeId = user threadId.
        data = sig.request_call("20001", 1762345679, None, 1)
        assert data["body"]["calleeId"] == "20001", data
        assert data["body"]["typeRequest"] == 1, data
        upaths = [p for p, _, _ in mock.seen
                  if p == "/api/voicecall/requestcall"]
        assert len(upaths) == 1, upaths
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
