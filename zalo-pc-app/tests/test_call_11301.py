"""Buoc `request` (11301 / 12434) con thieu sau requestcall
(2026-11-05 17:51, chay that): bam goi mot ban be 1-1 tren ban
01f7ee7 -> KHONG con loi 114; UI hien "Dang do chuong" dong ho
00:26, muc Cuoc goi ghi lai lan goi. NHUNG dien thoai nguoi duoc
goi KHONG hien cuoc goi den. Requestcall (11300) duoc server chap
nhan nhung cuoc goi chua duoc chuyen toi thiet bi ben kia; "dang do
chuong" tren UI chi la trang thai cuc bo.

Nguyen nhan goc (bundle PC that, compact-app-pc, xem §7l
bao-cao.md): client that gui HAI buoc. Buoc 1: native phat signal
401 -> renderer gui requestcall (11300). Buoc 2: native phat signal
416 (kem dia chi media do engine cap tu relay ZRTP) -> renderer
gui `request` (11301) {calleeId, rtcpAddress, rtpAddress, codec,
session, callId, imei} (+extendData, subCommand=3 neu co). Chi khi
do server moi co loi moi day du (kem dia chi media) de chuyen toi
ben kia. Code cu chi gui buoc 1 — ham send_request (11301) da co
san trong signaling.py nhung KHONG AI GOI (dead code).

Bang chung moi 17:54 lam ro them: vai phut sau cuoc goi PC, Dai ca
GOI LAI cho user (banner cuoc goi den tren dien thoai user luc dang
goi cho BenBap). Tia hieu DA toi ben kia o muc nao do — khong phai
hoan toan khong toi: hai gia thuyet chua phan biet duoc la (a) cuoc
goi PC toi muon (server giu loi moi den khi co 11301, hoac day cham)
hay (b) ben kia chi thay cuoc goi nho roi goi lai. Ca hai deu chi
ve cung mot cho thieu: buoc 11301. Bao cao cuoi phai neu ro hai gia
thuyet nay + hoi user xac nhan (Dai ca goi lai hay cuoc PC toi muon)
truoc khi ket luan.

Mock phan biet duoc hai luong: requestcall rieng -> "requested"
nhung KHONG BAO GIO "delivered" (tai hien trieu chung that); them
buoc request cung callId -> "delivered". Cac test nay PHAI FAIL o
code cu (server chi gui 11300) va PASS o code moi.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from test_media_provider import (  # noqa: E402
    FAKE_LOCAL_SESSION, FAKE_RELAYS, FAKE_SESSION, FAKE_SRTP_KEY,
    FAKE_TOKEN, FakeTransport)
from zalo_pc_app import media_endpoints  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import signaling  # noqa: E402

CALL_ID = 1762345678  # epoch seconds — fits uint32, like the real client
CALL_ID_GROUP = 1762345679
# Rieng cho test failure-mode: phai khac CALL_ID/CALL_ID_GROUP vi
# server giu guard don dieu _LAST_CALL_ID (module-global, song
# suot process test) — dung lai CALL_ID o test sau se bi day len
# mot id khac, mock se khong thay buoc nao cho CALL_ID cu.
CALL_ID_FAIL = 1762545678
CALL_ID_REAL_SHAPE = 1762645678  # test hinh 11300 that (§7n)
CALL_ID_REAL_SHAPE_1106 = 1762745678  # test hinh 11300 that 2026-11-06


def _sig(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    t = app_server.make_transport("sek-test")
    return signaling.Signaling(t, "dev-1", TEST_SESSION_KEY)


def test_vc_request_body_matches_bundle():
    """Body 11301 dung nhu lop wZ gui (static sendRequestCall):
    {calleeId, rtcpAddress, rtpAddress, codec, session, callId,
    imei}; chi khi co extendData moi them extendData + subCommand=3
    (bundle: i && (c.extendData=i, c.subCommand=3))."""
    body = protocol.vc_request("20001", "10.0.0.1:5000", "10.0.0.1:5001",
                               "[]", "sess-1", CALL_ID, "dev-1")
    assert body == {"calleeId": "20001", "rtcpAddress": "10.0.0.1:5000",
                    "rtpAddress": "10.0.0.1:5001", "codec": "[]",
                    "session": "sess-1", "callId": CALL_ID,
                    "imei": "dev-1"}, body
    assert "extendData" not in body and "subCommand" not in body, body
    body2 = protocol.vc_request("20001", "10.0.0.1:5000",
                                "10.0.0.1:5001", "[]", "sess-1",
                                CALL_ID, "dev-1", "ext-blob")
    assert body2["extendData"] == "ext-blob", body2
    assert body2["subCommand"] == 3, body2


def test_vc_request_group_body_matches_bundle():
    """Body 12434 dung nhu lop wZ gui (static sendRequestCallGroup):
    {calleeId, callId, callType, data, session, partners, groupId} —
    khong co imei, khong co extendData/subCommand."""
    body = protocol.vc_request_group("30001", CALL_ID_GROUP, 5, None,
                                     "sess-2", ["20001", "20002"],
                                     "30001")
    assert body == {"calleeId": "30001", "callId": CALL_ID_GROUP,
                    "callType": 5, "data": None, "session": "sess-2",
                    "partners": ["20001", "20002"],
                    "groupId": "30001"}, body
    assert "imei" not in body, body


def test_old_flow_never_delivered():
    """Luong cu (chi requestcall, dung nhu ban 01f7ee7): server chap
    nhan nhung mock KHONG BAO GIO danh dau delivered — tai hien
    trieu chung that (UI "dang do chuong", ben kia khong thay gi)."""
    mock = MockZalo().start()
    try:
        sig = _sig(mock)
        sig.request_call("20001", CALL_ID, None, 1)
        state = mock.voice_call_state(CALL_ID)
        assert state["requested"] is True, state
        assert state["delivered"] is False, state
        assert state["steps"] == ["requestcall"], state
    finally:
        mock.stop()


def test_request_without_requestcall_not_delivered():
    """Buoc request gui truoc khi co requestcall cung callId thi
    khong tinh la delivered — server tuong quan hai buoc bang
    callId (ghi lai thu tu bat buoc nay)."""
    mock = MockZalo().start()
    try:
        sig = _sig(mock)
        sig.send_request("20001", "", "", "[]", "", CALL_ID)
        state = mock.voice_call_state(CALL_ID)
        assert state["requested"] is False, state
        assert state["delivered"] is False, state
    finally:
        mock.stop()


def test_send_request_body_echo():
    """Gui truc tiep 11301 qua Signaling: body gui di dung dang
    bundle (codec "[]", session kem theo, callId so)."""
    mock = MockZalo().start()
    try:
        sig = _sig(mock)
        sig.request_call("20001", CALL_ID, None, 1)
        data = sig.send_request("20001", "10.0.0.1:5000",
                                "10.0.0.1:5001", "[]", "sess-1",
                                CALL_ID)
        assert data["body"]["calleeId"] == "20001", data
        assert data["body"]["rtcpAddress"] == "10.0.0.1:5000", data
        assert data["body"]["rtpAddress"] == "10.0.0.1:5001", data
        assert data["body"]["session"] == "sess-1", data
        assert data["body"]["callId"] == CALL_ID, data
        assert data["body"]["imei"] == "dev-1", data
        assert mock.voice_call_state(CALL_ID)["delivered"] is True
    finally:
        mock.stop()


# ------------------------------------------------------------------ e2e
# Drive the real app HTTP API (same harness shape as
# test_server_smoke.py): QR login against the mock, then POST
# /api/call/request and check the mock saw BOTH steps in order.

def _start_app(mock):
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-11301-")
    os.environ["ZALO_PC_DATA_DIR"] = tmp
    os.environ["ZALO_PC_PORT"] = "0"
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    app_server.PARAM_CIPHER_KEY = "TEST_PARAM_KEY_32_CHARS_LONG_XXX"
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


def _login(base):
    status, body = _api(base, "POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = _api(base, "GET", "/api/qr/status")
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def _fake_endpoints():
    """Provider voi allocation gia + FakeTransport (chi dung cho
    test): mo phong response 11300 co du zrtc_config."""
    return media_endpoints.MediaEndpoints(
        transport_factory=lambda cfg: FakeTransport(cfg),
        default_relays=FAKE_RELAYS, default_token=FAKE_TOKEN,
        default_session=FAKE_SESSION,
        default_local_session=FAKE_LOCAL_SESSION,
        default_srtp_key=FAKE_SRTP_KEY)


def test_no_allocation_not_delivered_e2e():
    """Khong co allocation relay (mock 11300 khong tra zrtc_config)
    thi buoc request KHONG duoc gui voi dia chi rong: cuoc goi van
    bao ok (requestcall da qua) nhung request_sent=false, loi neu
    ro tham so thieu (relays), mock chi thay requestcall, khong
    delivered. Day la hanh vi dung theo disassembly (engine that
    khong bao gio gui 416 rong) — test cu `test_new_flow_delivered
    _e2e` khang dinh nguoc lai (placeholder rong = delivered) nen
    duoc thay bang test nay."""
    mock = MockZalo().start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001", "call_id": CALL_ID})
        assert body["ok"] is True, body
        assert body["request_sent"] is False, body
        assert "relays" in body["request_error"], body
        # call_id hieu luc lay tu response: server giu guard don
        # dieu _LAST_CALL_ID (module-global) nen goi lai cung ID o
        # test sau trong cung process se duoc day len mot id khac.
        eff_id = body["call_id"]
        state = mock.voice_call_state(eff_id)
        assert state["steps"] == ["requestcall"], state
        assert state["delivered"] is False, state
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "30001",
                             "call_id": CALL_ID_GROUP, "type": "group",
                             "partners": ["20001", "20002"]})
        assert body["ok"] is True, body
        assert body["request_sent"] is False, body
        eff_group = body["call_id"]
        state = mock.voice_call_state(eff_group)
        assert state["steps"] == ["group/requestcall"], state
        assert state["delivered"] is False, state
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(eff_id)]["request_sent"] is False, body
        assert by_id[str(eff_group)]["request_sent"] is False, body
        httpd.shutdown()
    finally:
        if httpd is not None:
            try:
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        mock.stop()


def test_allocated_flow_delivered_e2e():
    """Co allocation (provider gia) thi luong moi qua API that: goi
    1-1 roi goi nhom — moi cuoc mock deu thay du 2 buoc dung thu
    tu, cung callId, va danh dau delivered; response tra
    request_sent=true; call log ghi nhan."""
    mock = MockZalo().start()
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _fake_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001", "call_id": CALL_ID})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        assert body["request_error"] == "", body
        # call_id hieu luc lay tu response (guard don dieu
        # _LAST_CALL_ID co the day ID len khi test chay sau test
        # khac trong cung process — xem test_no_allocation).
        eff_id = body["call_id"]
        state = mock.voice_call_state(eff_id)
        assert state["steps"] == ["requestcall", "request"], state
        assert state["delivered"] is True, state
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "30001",
                             "call_id": CALL_ID_GROUP, "type": "group",
                             "partners": ["20001", "20002"]})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        eff_group = body["call_id"]
        state = mock.voice_call_state(eff_group)
        assert state["steps"] == ["group/requestcall",
                                  "group/request"], state
        assert state["delivered"] is True, state
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(eff_id)]["request_sent"] is True, body
        assert by_id[str(eff_group)]["request_sent"] is True, body
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


def test_request_failure_is_non_fatal_e2e():
    """Khong co allocation (mock 11300 khong tra zrtc_config) thi
    buoc request khong gui duoc — cuoc goi VAN bao ok (requestcall
    da qua) nhung request_sent=false + request_error neu ro tham
    so thieu. Buoc 2 la best-effort, khong duoc lam hong cuoc goi.
    (Truoc day test nay dung mock request_mode=error114 de mo
    phong server tu choi 11301; truong hop do gio nam o
    test_request_114_with_allocation_e2e vi 11301 chi duoc gui
    khi da co allocation.)"""
    mock = MockZalo()
    mock = mock.start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001",
                             "call_id": CALL_ID_FAIL})
        assert body["ok"] is True, body
        assert body["request_sent"] is False, body
        assert "relays" in body["request_error"], body
        eff_id = body["call_id"]  # guard don dieu co the day ID len
        state = mock.voice_call_state(eff_id)
        assert state["requested"] is True, state
        assert state["delivered"] is False, state
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        entry = by_id[str(eff_id)]
        assert entry["request_sent"] is False, body
        assert "relays" in entry["request_detail"], body
        httpd.shutdown()
    finally:
        if httpd is not None:
            try:
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        mock.stop()


def test_request_114_with_allocation_e2e():
    """Co allocation ma server that tu choi buoc request (mock
    request_mode=error114) thi cuoc goi VAN bao ok nhung
    request_sent=false + request_error ghi ro 114 — buoc 2 la
    best-effort, khong duoc lam hong cuoc goi."""
    mock = MockZalo()
    mock.request_mode = "error114"
    mock = mock.start()
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _fake_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001",
                             "call_id": CALL_ID_FAIL})
        assert body["ok"] is True, body
        assert body["request_sent"] is False, body
        assert "114" in body["request_error"], body
        eff_id = body["call_id"]  # guard don dieu co the day ID len
        state = mock.voice_call_state(eff_id)
        assert state["requested"] is True, state
        assert state["delivered"] is False, state
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        entry = by_id[str(eff_id)]
        assert entry["request_sent"] is False, body
        assert "114" in entry["request_detail"], body
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


def test_real_11300_shape_delivered_e2e():
    """Hinh 11300 THAT (live 2026-11-05 22:58 +07, ban 72b91b8):
    servers la LIST cac dict co rtcpaddr/rtpIPv6 (khong phai
    chuoi zrtc_config.servers). Mock tra dung hinh do + sessId /
    srtpKey / token -> qua API that, buoc 11301 NHAN DUOC relay
    (khong con "relays: empty"), mock thay du 2 buoc dung thu tu
    va danh dau delivered; response tra request_sent=true va chi
    tra data_shape (ten key + so luong), KHONG tra raw data
    (co the chua srtpKey/token).
    GIOI HAN HONEST cua test nay: local_session van lay tu
    default cua provider gia (nhu test_allocated_flow) vi
    nguon that cua no (SSRC hang muc thiet bi) chua biet —
    test nay chung minh PHAN TICH RELAY qua duong that, khong
    chung minh cuoc goi that chay tron ven tren production."""
    from test_media_provider import REAL_SHAPE_SERVERS  # noqa: E402
    mock = MockZalo().start()
    mock.requestcall_data = {
        "servers": REAL_SHAPE_SERVERS, "sessId": "sess-real-e2e",
        "srtpKey": "k-test", "token": FAKE_TOKEN}
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _fake_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001",
                             "call_id": CALL_ID_REAL_SHAPE})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        assert body["request_error"] == "", body
        assert "data" not in body, body
        assert "rtcpaddr" in body["data_shape"], body
        assert "127.0.0.1" not in body["data_shape"], body
        eff_id = body["call_id"]
        state = mock.voice_call_state(eff_id)
        assert state["steps"] == ["requestcall", "request"], state
        assert state["delivered"] is True, state
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(eff_id)]["request_sent"] is True, body
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


def _bare_endpoints():
    """Provider KHONG co default token/session/srtp_key — moi
    thu phai den tu response 11300 (chi local_session van lay
    tu default gia, vi nguon that cua no chua biet)."""
    return media_endpoints.MediaEndpoints(
        transport_factory=lambda cfg: FakeTransport(cfg),
        default_local_session=FAKE_LOCAL_SESSION)


def test_real_11300_shape_2026_11_06_delivered_e2e():
    """Hinh 11300 THAT 2026-11-06 06:35 +07 (ban 9d87501, loi
    "token: missing" tren may chu that): KHONG co key `token`,
    KHONG co `srtpKey` (ca top-level lan zrtc_config); servers
    la list[5] dict voi key [bonus, rtcpIPv6, rtcpaddr, rtpIPv6,
    rtpaddr, spTcp]; sessId la chuoi base64url 154 ky tu TONG
    HOP (khong phai gia tri that bi bat). Qua API that, buoc
    11301 VAN DUOC GUI voi token = sessId (mock thay du 2 buoc
    dung thu tu, delivered) va request_sent=true; data_shape
    chi ghi ten key + do dai sessId, KHONG tra gia tri nao.
    GIOI HAN HONEST: local_session van lay tu default gia;
    srtp "not-wired" (khong co srtpKey that) nen test nay chung
    minh SIGNALING (11301 duoc gui, ben kia co the do chuong),
    KHONG chung minh co tieng — nguon khoa SRTP van mo."""
    from test_media_provider import (  # noqa: E402
        REAL_11300_2026_11_06, SESSID_154)
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
                            {"callee_id": "20001",
                             "call_id": CALL_ID_REAL_SHAPE_1106})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        assert body["request_error"] == "", body
        assert "data" not in body, body
        assert "sessId: str[154 chars]" in body["data_shape"], body
        assert "rtcpaddr" in body["data_shape"], body
        assert "127.0.0.1" not in body["data_shape"], body
        assert SESSID_154 not in body["data_shape"], body
        eff_id = body["call_id"]
        state = mock.voice_call_state(eff_id)
        assert state["steps"] == ["requestcall", "request"], state
        assert state["delivered"] is True, state
        # Token that dung trong transport chinh la sessId (khong
        # phai default gia nao — provider nay khong co default).
        record = endpoints.active_record(eff_id)
        assert record is not None, body
        assert record["transport"].config.token == \
            SESSID_154.encode(), body
        assert len(record["transport"].config.token_raw) == 115, body
        assert record["srtp_key"] is None, body
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(eff_id)]["request_sent"] is True, body
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
