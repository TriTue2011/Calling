"""local_session / peer_session tu response 11300 (2026-11-06).

Disassembly (ZaloCall.exe 26.11.10) — CHOT, xem bao cao vong sua
nay:
  * Parser response 401 (fcn.0071ebd1, zmessagedeseralizer.cpp,
    chuoi "invalid resp inf"): struct+0x10 <- JSON "fromId",
    struct+0x14 <- JSON "toId", qua JSON-get-int 0x4015a5
    (QVariant::toInt — nhan so JSON hoac chuoi so vua int32);
    struct+0xc <- "id", +4 <- "protocol", +0 <- "status",
    +0x80 <- "sessId", +0x20 <- "msg", +0x50 <- zrtc_config,
    +0x68 <- servers; roi dispatch struct cho signal handler.
  * `_prepareCallConfig, resp` (0x7ed1d0): `mov eax,[resp+0x10]`
    -> CallConfig+0 (0x7ed226/0x7ed229), `mov eax,[resp+0x14]`
    -> CallConfig+4 (0x7ed22f/0x7ed238) — KHONG co and/shr/mod/
    hash nao. CallConfig+0 = userId cua minh (log 0x85ea05),
    +4 = partnerId; tu do [CallController+0x60] -> goi Init
    [pkt+0x10] -> SSRC.
  * Chieu goi di (401-handler -> PW::makeCall): fromId = caller
    = chinh minh, toId = callee = peer. Doi chieu chieu goi den
    (parser 0x71f670: "uidTo" -> CallConfig+0, "uidFrom" ->
    CallConfig+4): CallConfig+0 LUON la minh, +4 LUON la peer.
  * Vay: local_session = response 11300 `fromId` (u32 do server
    cap), peer_session = `toId` (u32, None khi vang).
  * KHONG lay tu session uid: uid that la 64-bit (18 chu so),
    live test 09:23 +07 2026-11-06 da bac (phep kiem u32 loai
    no); low-32 cung bi loai bang pcap 09:27. KHONG low-32 /
    high-32 / hash / cat ngan — khong co phep nao nhu vay trong
    binary. `server._local_session_from_uid` va
    `_peer_session_for_call` (int(threadId)) DA XOA.
  * Thieu fromId (hoac fromId khong vua u32) -> `for_call` loi
    TRUNG THUC neu ro `local_session` + `fromId`; gui 11301 voi
    SSRC sai con te hon khong gui. peer vang -> None trung thuc
    (transport gui 0 o offset 25-28 roi hoc lai SSRC peer).
  * Goi nhom: toId cua response nhom khong phai userId cua mot
    peer (duong group di qua groupcallpeer.cpp, struct khac) nen
    peer_session van None.

Quy tac test (mock/offline, KHONG goi that, KHONG tai khoan that):
  * Gia tri fixture TONG HOP (10001/10002/20001/20002; uid 64-bit
    "100010001000100010"); khong gia tri that nao bi bat.
  * fromId/toId trong fixture PHAN BIET voi uid login mock
    ("10001") va callee ("20001") de test e2e phan biet duoc
    nguon that (11300) voi nguon cu (uid/threadId).

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

CALL_ID_FROMID = 1762945678
CALL_ID_FROMID_GROUP = 1762945679
CALL_ID_FROMID_MISSING = 1762945680
CALL_ID_FROMID_UID64 = 1762945681
# Id 32-bit do server cap trong response 11300 (fixture tong hop).
# CO TINH phan biet voi uid login mock ("10001") va callee
# ("20001") de e2e chung minh gia tri den tu 11300, khong phai
# tu uid / threadId.
FROM_ID = 10002
TO_ID = 20002
# Uid 64-bit dang fixture tong hop (18 chu so) — phai KHONG
# duoc dung lam local_session (khong cat low-32, khong hash).
UID_64_FIXTURE = "100010001000100010"
# uid cua tai khoan mock login (mock_server grant uid "10001").
MOCK_UID = "10001"
CALLEE_ID = "20001"
GROUP_ID = "30001"


def _bare_endpoints():
    """Provider KHONG co default nao: moi thu phai den tu
    response 11300 (relays/token/session + local_session tu
    `fromId`, peer_session tu `toId`)."""
    return media_endpoints.MediaEndpoints(
        transport_factory=lambda cfg: FakeTransport(cfg))


def _data_with_ids(from_id=FROM_ID, to_id=TO_ID):
    """Ban sao fixture 11300 that voi fromId/toId so tong hop."""
    data = dict(REAL_11300_2026_11_06)
    data["fromId"] = from_id
    data["toId"] = to_id
    return data


# ------------------------------------------------------------------ unit

def test_allocation_fromid_toid():
    """allocation lay local_session tu `fromId`, peer_session tu
    `toId` — ca dang int lan chuoi so; chuoi so phai vua u32."""
    alloc = media_endpoints.allocation_from_requestcall_data(
        _data_with_ids())
    assert alloc["local_session"] == FROM_ID, alloc
    assert alloc["peer_session"] == TO_ID, alloc
    alloc = media_endpoints.allocation_from_requestcall_data(
        _data_with_ids(str(FROM_ID), str(TO_ID)))
    assert alloc["local_session"] == FROM_ID, alloc
    assert alloc["peer_session"] == TO_ID, alloc
    # Fixture chia se (fromId/toId so 10001/20001) cung vay.
    alloc = media_endpoints.allocation_from_requestcall_data(
        REAL_11300_2026_11_06)
    assert alloc["local_session"] == 10001, alloc
    assert alloc["peer_session"] == 20001, alloc


def test_allocation_fromid_invalid_shape():
    """fromId khong vua u32 (uid 64-bit, 0, am, >= 2**32, khong
    phai so) -> KHONG co local_session, chi ghi dang (shape) de
    loi sau neu ro; toId sai dang -> KHONG co peer_session."""
    for bad in (UID_64_FIXTURE, "0", "-1", str(2 ** 32),
                "10001-test", "abc", "10001.5", 0, -5, 2 ** 32):
        alloc = media_endpoints.allocation_from_requestcall_data(
            _data_with_ids(bad, TO_ID))
        assert "local_session" not in alloc, (bad, alloc)
        assert alloc.get("local_session_invalid") is not None, \
            (bad, alloc)
    alloc = media_endpoints.allocation_from_requestcall_data(
        _data_with_ids(UID_64_FIXTURE, TO_ID))
    assert alloc["local_session_invalid"] == "str[18 chars]", alloc
    assert UID_64_FIXTURE not in str(alloc), alloc
    for bad_peer in ("abc", UID_64_FIXTURE, 0, 2 ** 32):
        alloc = media_endpoints.allocation_from_requestcall_data(
            _data_with_ids(FROM_ID, bad_peer))
        assert "peer_session" not in alloc, (bad_peer, alloc)
        assert alloc["local_session"] == FROM_ID, alloc


def test_for_call_uses_fromid_toid():
    """for_call qua requestcall_data: transport nhan
    local_session == local_ssrc == fromId, peer_session == toId
    (khac default gia, khac uid login)."""
    provider = _bare_endpoints()
    try:
        out = provider.for_call(
            call_id=CALL_ID_FROMID, callee_id=CALLEE_ID,
            requestcall_data=_data_with_ids())
        assert out["rtp_address"] == "127.0.0.1:4200", out
        assert out["rtcp_address"] == "127.0.0.1:4201", out
        cfg = out["transport"].config
        assert cfg.local_session == FROM_ID, cfg.local_session
        assert cfg.local_ssrc == FROM_ID, cfg.local_ssrc
        assert cfg.peer_session == TO_ID, cfg.peer_session
        assert cfg.local_session != FAKE_LOCAL_SESSION, cfg.local_session
    finally:
        provider.stop_all()


def test_for_call_missing_fromid_fails_loud():
    """Thieu fromId -> MissingTransportParam neu ro ca
    `local_session` lan `fromId` (khong doan tu uid, khong
    random); fromId la uid 64-bit cung loi nhu vay, loi ghi
    dang chu khong ghi gia tri."""
    for data in (_data_with_ids(None, TO_ID),
                 _data_with_ids(UID_64_FIXTURE, TO_ID)):
        data = {k: v for k, v in data.items()
                if not (k == "fromId" and v is None)}
        try:
            _bare_endpoints().for_call(
                call_id=CALL_ID_FROMID, callee_id=CALLEE_ID,
                requestcall_data=data)
        except MissingTransportParam as exc:
            msg = str(exc)
            assert "local_session" in msg, msg
            assert "fromId" in msg, msg
            assert UID_64_FIXTURE not in msg, msg
        else:
            raise AssertionError(
                "expected MissingTransportParam for data=%r" % (data,))
    shape = media_endpoints.describe_requestcall_shape(
        _data_with_ids(UID_64_FIXTURE, TO_ID))
    assert "fromId: str[18 chars]" in shape, shape
    assert UID_64_FIXTURE not in shape, shape


def test_for_call_toid_absent_peer_none():
    """toId vang (hoac sai dang) -> peer_session None trung thuc,
    buoc 2 van di duoc (transport gui 0 roi hoc lai SSRC peer)."""
    provider = _bare_endpoints()
    try:
        data = _data_with_ids()
        del data["toId"]
        out = provider.for_call(
            call_id=CALL_ID_FROMID, callee_id=CALLEE_ID,
            requestcall_data=data)
        assert out["transport"].config.peer_session is None, out
        assert out["transport"].config.local_session == FROM_ID, out
        data = _data_with_ids(FROM_ID, "abc")
        out = provider.for_call(
            call_id=CALL_ID_FROMID + 10, callee_id=CALLEE_ID,
            requestcall_data=data)
        assert out["transport"].config.peer_session is None, out
    finally:
        provider.stop_all()


def test_no_uid_derivation_in_server():
    """Ham suy local_session tu uid va peer tu threadId DA XOA:
    khong con duong nao lay uid/threadId lam SSRC."""
    assert not hasattr(app_server, "_local_session_from_uid"), \
        "_local_session_from_uid still exists"
    assert not hasattr(app_server, "_peer_session_for_call"), \
        "_peer_session_for_call still exists"


# ------------------------------------------------------------------ e2e

def test_fromid_delivered_e2e():
    """Qua API that, provider KHONG default: login mock (uid
    "10001"), callee "20001", nhung 11300 mang fromId=10002 /
    toId=20002 -> buoc 11301 DUOC GUI, transport nhan
    local_session=10002 (== local_ssrc) va peer_session=20002.
    Neu code van dung uid/threadId thi se ra 10001/20001 va
    test nay do — day la diem phan biet."""
    mock = MockZalo().start()
    mock.requestcall_data = _data_with_ids()
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _bare_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        assert app_server.STATE.session.get("uid") == MOCK_UID
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": CALLEE_ID,
                             "call_id": CALL_ID_FROMID})
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
        assert cfg.local_session == FROM_ID, cfg.local_session
        assert cfg.local_ssrc == FROM_ID, cfg.local_ssrc
        assert cfg.peer_session == TO_ID, cfg.peer_session
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
        # Dung poller sync/ctrl SAU KHI mock tat (poll se loi
        # nhanh, join kip): khong thi daemon thread con in retry
        # ra stdout luc interpreter tat -> abort 134
        # (_enter_buffered_busy) du test da pass het — loi co san,
        # thay tren base bea4f0a (xem ghi chu o sync_poll.run).
        app_server.STATE.stop_sync()


def test_uid64_and_missing_fromid_e2e():
    """Session uid la 64-bit (fixture tong hop) MA 11300 thieu
    fromId -> buoc 2 loi TRUNG THUC neu `local_session` +
    `fromId`, KHONG cat low-32 / hash uid de che SSRC; cuoc goi
    van bao ok (requestcall da qua), request_sent=false, mock
    chi thay requestcall."""
    mock = MockZalo().start()
    data = _data_with_ids()
    del data["fromId"]
    mock.requestcall_data = data
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _bare_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        app_server.STATE.session["uid"] = UID_64_FIXTURE
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": CALLEE_ID,
                             "call_id": CALL_ID_FROMID_MISSING})
        assert body["ok"] is True, body
        assert body["request_sent"] is False, body
        assert "local_session" in body["request_error"], body
        assert "fromId" in body["request_error"], body
        assert UID_64_FIXTURE not in body["request_error"], body
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
        # Dung poller sync/ctrl SAU KHI mock tat (xem
        # test_fromid_delivered_e2e — tranh abort 134 luc shutdown).
        app_server.STATE.stop_sync()


def test_uid64_ignored_when_fromid_present_e2e():
    """Uid 64-bit trong session KHONG anh huong gi khi 11300 da
    co fromId: local_session van la fromId (10002)."""
    mock = MockZalo().start()
    mock.requestcall_data = _data_with_ids()
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _bare_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        app_server.STATE.session["uid"] = UID_64_FIXTURE
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": CALLEE_ID,
                             "call_id": CALL_ID_FROMID_UID64})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        assert body["request_error"] == "", body
        eff_id = body["call_id"]
        record = endpoints.active_record(eff_id)
        cfg = record["transport"].config
        assert cfg.local_session == FROM_ID, cfg.local_session
        assert cfg.local_ssrc == FROM_ID, cfg.local_ssrc
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
        # Dung poller sync/ctrl SAU KHI mock tat (xem
        # test_fromid_delivered_e2e — tranh abort 134 luc shutdown).
        app_server.STATE.stop_sync()


def test_group_call_peer_session_none_e2e():
    """Goi nhom qua API that: buoc 12434 van duoc gui, local_session
    la fromId, nhung peer_session phai la None (toId cua response
    nhom khong phai userId cua mot peer)."""
    mock = MockZalo().start()
    mock.requestcall_data = _data_with_ids()
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _bare_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": GROUP_ID,
                             "call_id": CALL_ID_FROMID_GROUP,
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
        assert cfg.local_session == FROM_ID, cfg.local_session
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
        # Dung poller sync/ctrl SAU KHI mock tat (xem
        # test_fromid_delivered_e2e — tranh abort 134 luc shutdown).
        app_server.STATE.stop_sync()


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
