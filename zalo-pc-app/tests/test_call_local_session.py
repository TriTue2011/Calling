"""local_session = uid cua tai khoan dang dang nhap (2026-11-06).

Disassembly (xem disasm-local-session-source.md): `local_session`
(u32, = RTP SSRC) = `CallConfig+0x0` = userId cua chinh tai khoan
dang dang nhap, copy vao `[CallController+0x60]` -> goi Init
`[pkt+0x10]` -> SSRC tren day. Pcap 3 cuoc goi: offset 10-13
GIONG nhau ca 3 (dung tinh chat userId cua minh), offset 25-28
(peer session = partnerId, `CallConfig+0x4`) KHAC nhau ca 3.
App da co uid san tu luc dang nhap: `session["uid"]`.

Quy tac test (mock/offline, KHONG goi that):
  * `server._local_session_from_uid` tra `int(uid)`; uid thieu /
    khong phai so / ngoai u32 -> `MissingTransportParam` neu ro
    `local_session` (uid), KHONG random, KHONG dung gia tri da bat.
  * `server._peer_session_for_call` tra `int(thread_id)` chi cho
    goi 1-1 (threadId 1-1 = userId cua peer); goi nhom (threadId
    = groupId, khong phai userId) hoac id khong phai so -> None
    (transport gui 0 o offset 25-28 nhu cu — peer_session la
    optional, `for_call`/`TransportConfig` khong yeu cau no).
  * E2E qua API that voi provider KHONG co default local_session:
    login mock (uid "10001") -> buoc 2 khong con loi
    local_session, transport nhan local_session=10001 (int uid)
    va peer_session=20001 (int callee); uid thieu -> request_sent
    false + loi trung thuc neu `local_session`.

Chay: python3 tests/test_call_local_session.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from test_call_11301 import _api, _login, _start_app  # noqa: E402
from test_media_provider import (  # noqa: E402
    FAKE_LOCAL_SESSION, FakeTransport, REAL_11300_2026_11_06)
from zalo_pc_app import media_endpoints  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app.media_endpoints import MissingTransportParam  # noqa: E402

CALL_ID_UID = 1762845678
CALL_ID_UID_GROUP = 1762845679
CALL_ID_UID_MISSING = 1762845680
# uid cua tai khoan mock login (mock_server grant uid "10001").
MOCK_UID = 10001
MOCK_UID_STR = "10001"
CALLEE_ID = "20001"
GROUP_ID = "30001"


def _bare_endpoints():
    """Provider KHONG co default nao: moi thu phai den tu
    response 11300 (relays/token/session) hoac tu server.py
    (local_session = int uid, peer_session = int callee)."""
    return media_endpoints.MediaEndpoints(
        transport_factory=lambda cfg: FakeTransport(cfg))


# ------------------------------------------------------------------ unit

def test_local_session_from_uid():
    assert app_server._local_session_from_uid(
        {"uid": MOCK_UID_STR}) == MOCK_UID
    assert app_server._local_session_from_uid(
        {"uid": MOCK_UID}) == MOCK_UID
    for bad in ({}, {"uid": ""}, {"uid": None}, {"uid": "abc"},
                {"uid": "0"}, {"uid": "-1"},
                {"uid": str(2 ** 32)}, {"uid": "10001.5"}):
        try:
            app_server._local_session_from_uid(bad)
        except MissingTransportParam as exc:
            assert "local_session" in str(exc), exc
            assert "uid" in str(exc), exc
        else:
            raise AssertionError(
                "expected MissingTransportParam for uid=%r" % (bad,))


def test_peer_session_for_call():
    assert app_server._peer_session_for_call("user", CALLEE_ID) == 20001
    assert app_server._peer_session_for_call("user", 20001) == 20001
    # Nhom: threadId la groupId, KHONG phai userId cua peer.
    assert app_server._peer_session_for_call("group", GROUP_ID) is None
    assert app_server._peer_session_for_call("group", CALLEE_ID) is None
    # Id khong phai so / ngoai u32 -> None (optional, khong loi).
    assert app_server._peer_session_for_call("user", "") is None
    assert app_server._peer_session_for_call("user", "abc") is None
    assert app_server._peer_session_for_call(
        "user", str(2 ** 32)) is None


def test_for_call_with_uid_local_session():
    """for_call voi local_session=int(uid) + peer_session=int(callee)
    di qua: khong con raise local_session; transport nhan dung
    local_session (== local_ssrc) va peer_session."""
    provider = _bare_endpoints()
    try:
        out = provider.for_call(
            call_id=CALL_ID_UID, callee_id=CALLEE_ID,
            local_session=MOCK_UID, peer_session=20001,
            requestcall_data=dict(REAL_11300_2026_11_06))
        assert out["rtp_address"] == "127.0.0.1:4200", out
        assert out["rtcp_address"] == "127.0.0.1:4201", out
        cfg = out["transport"].config
        assert cfg.local_session == MOCK_UID, cfg.local_session
        assert cfg.local_ssrc == MOCK_UID, cfg.local_ssrc
        assert cfg.peer_session == 20001, cfg.peer_session
        assert cfg.local_session != FAKE_LOCAL_SESSION, cfg.local_session
    finally:
        provider.stop_all()


# ------------------------------------------------------------------ e2e

def test_uid_local_session_delivered_e2e():
    """Qua API that, provider KHONG default local_session: login
    mock (uid "10001") -> buoc 11301 VAN DUOC GUI (truoc fix nay
    loi `local_session: missing`), mock thay du 2 buoc, delivered;
    transport nhan local_session=int(uid) va peer_session=int(
    callee)."""
    mock = MockZalo().start()
    mock.requestcall_data = dict(REAL_11300_2026_11_06)
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _bare_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": CALLEE_ID,
                             "call_id": CALL_ID_UID})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        assert body["request_error"] == "", body
        eff_id = body["call_id"]
        state = mock.voice_call_state(eff_id)
        assert state["steps"] == ["requestcall", "request"], state
        assert state["delivered"] is True, state
        record = endpoints.active_record(eff_id)
        assert record is not None, body
        cfg = record["transport"].config
        assert cfg.local_session == MOCK_UID, cfg.local_session
        assert cfg.local_ssrc == MOCK_UID, cfg.local_ssrc
        assert cfg.peer_session == 20001, cfg.peer_session
        httpd.shutdown()
    finally:
        endpoints.stop_all()
        media_endpoints.ENDPOINTS = old_endpoints
        if httpd is not None:
            try:
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        mock.stop()


def test_missing_uid_e2e():
    """Session khong co uid dung duoc -> buoc 2 loi TRUNG THUC neu
    `local_session` (uid), khong random, khong gia tri da bat;
    cuoc goi van bao ok (requestcall da qua), request_sent=false."""
    mock = MockZalo().start()
    mock.requestcall_data = dict(REAL_11300_2026_11_06)
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _bare_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        app_server.STATE.session["uid"] = ""
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": CALLEE_ID,
                             "call_id": CALL_ID_UID_MISSING})
        assert body["ok"] is True, body
        assert body["request_sent"] is False, body
        assert "local_session" in body["request_error"], body
        assert "uid" in body["request_error"], body
        eff_id = body["call_id"]
        state = mock.voice_call_state(eff_id)
        assert state["steps"] == ["requestcall"], state
        assert state["delivered"] is False, state
        httpd.shutdown()
    finally:
        endpoints.stop_all()
        media_endpoints.ENDPOINTS = old_endpoints
        if httpd is not None:
            try:
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        mock.stop()


def test_group_call_peer_session_none_e2e():
    """Goi nhom qua API that: buoc 12434 van duoc gui, nhung
    peer_session phai la None (group threadId khong phai userId)."""
    mock = MockZalo().start()
    mock.requestcall_data = dict(REAL_11300_2026_11_06)
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _bare_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": GROUP_ID,
                             "call_id": CALL_ID_UID_GROUP,
                             "type": "group",
                             "partners": [CALLEE_ID, "20002"]})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        assert body["request_error"] == "", body
        eff_id = body["call_id"]
        state = mock.voice_call_state(eff_id)
        assert state["steps"] == ["group/requestcall",
                                  "group/request"], state
        assert state["delivered"] is True, state
        record = endpoints.active_record(eff_id)
        assert record is not None, body
        cfg = record["transport"].config
        assert cfg.local_session == MOCK_UID, cfg.local_session
        assert cfg.peer_session is None, cfg.peer_session
        httpd.shutdown()
    finally:
        endpoints.stop_all()
        media_endpoints.ENDPOINTS = old_endpoints
        if httpd is not None:
            try:
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        mock.stop()


if __name__ == "__main__":
    failed = []
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_")]
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed.append(fn.__name__)
            print("FAIL", fn.__name__, exc)
    print("%d/%d tests passed" % (len(tests) - len(failed), len(tests)))
    raise SystemExit(1 if failed else 0)
