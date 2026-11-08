"""Chan doan chi tiet cho tin hieu goi di (2026-11-08).

Live 2026-11-08: goi di cho Dai ca 2 lan (call_id 1794100438 va
1794100601) deu `[call] step2 ... request_sent=True` roi
`[call] end ... reason=ring_timeout duration=30s
zalo_signal=cancel zalo_ok=True` — app cho du 30s roi timeout,
cancel duoc chap nhan, NHUNG ben kia KHONG do chuong. Peer da
chung minh ONLINE (nhan «Alo», «May gio roi» luc 08:17) nen khong
phai do peer offline — van de nam o khau chuyen loi moi goi toi
peer. Van de chan doan luc do: app chi log `request_sent=True`
(tuc la da GUI request), KHONG log may chu TRA VE gi cho
11300/11301 (status, ma loi, thieu truong nao).

Sua o vong nay:
  * Log step 1 (11300): status + msg + shape (chi ten key + do
    dai, khong gia tri); status != 0 thi coi la 11300 bi tu choi
    (loi ro, khong di tiep buoc 2).
  * Log buoc 2 (11301/12434): dia chi relay da dung + session
    co/khong + do dai (khong gia tri) truoc khi gui; log response
    dang shape (chi ten key + status/msg/ok). Response co status
    loi (hoac inner error_code) -> «may chu tu choi 11301» +
    ket thuc cuoc goi som voi reason `server_rejected` (cancel
    rut loi moi) thay vi cho 30s timeout mu.
  * Log tom tat mot dong khi het 30s timeout (`timeout-summary`):
    call_id, toId, step1/step2 status, request_sent, dia chi
    relay, zalo_signal/zalo_ok — user chi can gui mot dong la
    du chan doan.
  * `diag` tren moi entry cua /api/calls: step1/step2 status,
    dia chi relay, session co/khong + do dai, codec. Khong bao
    gio chua gia tri session/token.
  * Doi chieu 11301 app vs client that (bundle wZ, §7l bao-cao
    + disassembly ZaloCall.exe): body app gui khop nguyen van
    wZ {calleeId, rtcpAddress, rtpAddress, codec, session,
    callId, imei} (+extendData, subCommand=3 neu co extendData)
    — KHONG thieu truong nao, nen vong nay KHONG doi body 11301;
    test duoi khoa lai dieu do (khong them/khong bot field).

Cac test nay PHAI FAIL o code cu (khong co log step1/step2
send/step2 resp/timeout-summary, khong co diag, 11301 bi tu
choi chi de lai cuoc goi «sent» mai mai) va PASS o code moi.
"""

import contextlib
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from test_call_11301 import (  # noqa: E402
    _api, _bare_endpoints, _fake_endpoints, _login, _start_app)
from test_media_provider import (  # noqa: E402
    REAL_11300_2026_11_06, SESSID_154)
from zalo_pc_app import media_endpoints  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402

CALL_ID_11300_REJ = 1763200001
CALL_ID_11301_114 = 1763200002
CALL_ID_11301_STATUS = 1763200003
CALL_ID_BODY = 1763200004
CALL_ID_TIMEOUT = 1763200005
CALL_ID_DIAG_OK = 1763200006
# Id tang dan theo thu tu chay (test sap theo ten): server giu
# guard don dieu _LAST_CALL_ID, id nho hon id truoc se bi day len.


def _run(mock, fn):
    """Start mock + app, log in, run fn(base, mock, endpoints)."""
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _fake_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        fn(base, mock, endpoints)
    finally:
        endpoints.stop_all()
        media_endpoints.ENDPOINTS = old_endpoints
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        mock.stop()


def _run_bare(mock, fn):
    """Nhu _run nhung dung _bare_endpoints: moi thu phai den tu
    response 11300 that (khong default gia) — dung cho test can
    dia chi relay + session that tu 11300."""
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _bare_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        fn(base, mock, endpoints)
    finally:
        endpoints.stop_all()
        media_endpoints.ENDPOINTS = old_endpoints
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        mock.stop()


def _calls_by_id(base):
    status, body = _api(base, "GET", "/api/calls")
    assert status == 200, body
    return {c["call_id"]: c for c in body["calls"]}, body


def test_step1_and_step2_diag_logged():
    """Duong goi thanh cong phai log du chan doan: step1 (11300)
    status + shape (gom rtpIP/rtcpIP — 2026-11-08 buoc 1); step2
    send (dia chi relay + nguon dia chi rtp_source + session chi
    co/khong + do dai); step2 resp (shape). /api/calls diag ghi du
    cac truong; KHONG ro ri gia tri session (sessId 154 ky tu)
    ra log hay API."""
    mock = MockZalo().start()
    mock.requestcall_data = dict(REAL_11300_2026_11_06)

    def check(base, mock, endpoints):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            status, body = _api(base, "POST", "/api/call/request",
                                {"callee_id": "20001",
                                 "call_id": CALL_ID_DIAG_OK})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        eff_id = body["call_id"]
        log = captured.getvalue()
        assert ("[call] step1 call_id=%s status=0" % eff_id) in log, log
        assert ("[call] step2 send call_id=%s rtp=127.0.0.1:4200 "
                "rtcp=127.0.0.1:4201 rtp_source=selected "
                "session=present[154] codec=opus"
                % eff_id) in log, log
        assert ("[call] step2 resp call_id=%s 11301 keys:" % eff_id) \
            in log, log
        assert ("[call] step2 call_id=%s request_sent=True "
                "step2_status=None" % eff_id) in log, log
        assert SESSID_154 not in log, log
        by_id, calls_body = _calls_by_id(base)
        entry = by_id[str(eff_id)]
        diag = entry["diag"]
        assert diag["step1_status"] == 0, entry
        # Mock 11301 tra {"ok": True, "path", "body"} — KHONG co
        # truong status, nen step2_status la None («response
        # khong mang status») chu khong phai 0; response that
        # neu co status se hien gia tri that cua no.
        assert diag["step2_status"] is None, entry
        assert diag["rtp"] == "127.0.0.1:4200", entry
        assert diag["rtcp"] == "127.0.0.1:4201", entry
        # 2026-11-08 buoc 1: diag ghi nguon dia chi 11301 dung
        # (rtpIP cua mock trung relay da chon -> "selected") va
        # rtpIP/rtcpIP goc tu 11300 (IP tran o fixture nay).
        assert diag["rtp_source"] == "selected", entry
        assert diag["rtp_ip"] == "127.0.0.1", entry
        assert diag["rtcp_ip"] == "127.0.0.1", entry
        assert diag["session_present"] is True, entry
        assert diag["session_len"] == 154, entry
        assert diag["codec"] == "opus", entry
        assert SESSID_154 not in json.dumps(calls_body), calls_body
        state = mock.voice_call_state(eff_id)
        assert state["delivered"] is True, state

    _run_bare(mock, check)


def test_11300_status_rejected():
    """Response 11300 co status != 0 (kem msg) thi cuoc goi loi
    ro ngay tu buoc 1: HTTP 502, loi neu «11300» + status; buoc 2
    KHONG duoc gui; entry lich su ghi status error."""
    mock = MockZalo().start()
    mock.requestcall_data = {"status": 5, "msg": "peer offline"}

    def check(base, mock, endpoints):
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001",
                             "call_id": CALL_ID_11300_REJ})
        assert status == 502, body
        assert "11300" in body["error"], body
        assert "status=5" in body["error"], body
        by_id, _ = _calls_by_id(base)
        errors = [c for c in by_id.values() if c["status"] == "error"]
        assert len(errors) == 1, by_id
        entry = errors[0]
        assert "11300" in entry["detail"], entry
        eff_id = int(entry["call_id"])
        state = mock.voice_call_state(eff_id)
        assert state["requested"] is True, state
        assert state["delivered"] is False, state
        assert "request" not in state["steps"], state

    _run(mock, check)


def test_11301_status_rejected_ends_early():
    """Server tra response 11301 co status != 0 thi app phai ket
    thuc cuoc goi SOM voi reason server_rejected (cancel rut loi
    moi) thay vi de cuoc goi «sent» mai mai khong timer: response
    van ok nhung request_sent=false + loi neu ro status; entry
    lich su ended/server_rejected; mock thay cancel duoc gui."""
    mock = MockZalo()
    mock.request_mode = "status_error"
    mock = mock.start()

    def check(base, mock, endpoints):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            status, body = _api(base, "POST", "/api/call/request",
                                {"callee_id": "20001",
                                 "call_id": CALL_ID_11301_STATUS})
        assert body["ok"] is True, body
        assert body["request_sent"] is False, body
        assert "11301" in body["request_error"], body
        assert "status=7" in body["request_error"], body
        assert body.get("ended_reason") == "server_rejected", body
        log = captured.getvalue()
        assert "may chu tu choi 11301" in log, log
        assert ("[call] end call_id=%s reason=server_rejected"
                % body["call_id"]) in log, log
        by_id, _ = _calls_by_id(base)
        entry = by_id[str(body["call_id"])]
        assert entry["status"] == "ended", entry
        assert "server_rejected" in entry["detail"], entry
        assert entry["request_sent"] is False, entry
        state = mock.voice_call_state(body["call_id"])
        assert state["requested"] is True, state
        assert state["delivered"] is False, state
        assert "cancel" in state["steps"], state

    _run(mock, check)


def test_11301_inner_114_ends_early():
    """Server tu choi 11301 bang inner error_code 114 (mock
    request_mode=error114) cung ket thuc som server_rejected
    nhu tren — khong chi truong hop status trong data."""
    mock = MockZalo()
    mock.request_mode = "error114"
    mock = mock.start()

    def check(base, mock, endpoints):
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001",
                             "call_id": CALL_ID_11301_114})
        assert body["ok"] is True, body
        assert body["request_sent"] is False, body
        assert "114" in body["request_error"], body
        assert body.get("ended_reason") == "server_rejected", body
        by_id, _ = _calls_by_id(base)
        entry = by_id[str(body["call_id"])]
        assert entry["status"] == "ended", entry
        assert "server_rejected" in entry["detail"], entry
        state = mock.voice_call_state(body["call_id"])
        assert "cancel" in state["steps"], state

    _run(mock, check)


def test_ring_timeout_summary_line():
    """Het timeout do chuong phai co mot dong tom tat duy nhat
    du thong tin chan doan: call_id, toId, step1/step2 status,
    request_sent, dia chi relay, zalo_signal/zalo_ok."""
    mock = MockZalo().start()
    mock.requestcall_data = dict(REAL_11300_2026_11_06)
    old_timeout = app_server.RING_TIMEOUT_SECONDS
    app_server.RING_TIMEOUT_SECONDS = 1

    def check(base, mock, endpoints):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            status, body = _api(base, "POST", "/api/call/request",
                                {"callee_id": "20001",
                                 "call_id": CALL_ID_TIMEOUT})
            assert body["request_sent"] is True, body
            eff_id = body["call_id"]
            time.sleep(2.5)
        log = captured.getvalue()
        assert ("[call] timeout-summary call_id=%s peer=20001 "
                "toId=20001 step1_status=0 step2_status=None "
                "request_sent=True rtp=127.0.0.1:4200 "
                "rtcp=127.0.0.1:4201 duration=" % eff_id) in log, log
        assert "zalo_signal=cancel zalo_ok=True" in log, log
        by_id, _ = _calls_by_id(base)
        assert by_id[str(eff_id)]["status"] == "ended", by_id

    try:
        _run_bare(mock, check)
    finally:
        app_server.RING_TIMEOUT_SECONDS = old_timeout


def test_11301_body_has_no_fields_beyond_bundle():
    """Khoa dang body 11301 theo bundle wZ (§7l bao-cao.md +
    disassembly): chi {calleeId, rtcpAddress, rtpAddress, codec,
    session, callId, imei} (+extendData, subCommand=3 neu co
    extendData) — khong them, khong bot field. Vong nay KHONG
    doi body 11301 vi doi chieu cho thay khong thieu truong nao;
    test nay chan truot dang ve sau."""
    body = protocol.vc_request("20001", "127.0.0.1:4201",
                               "127.0.0.1:4200", "opus", "sess",
                               CALL_ID_BODY, "dev-1")
    assert set(body) == {"calleeId", "rtcpAddress", "rtpAddress",
                         "codec", "session", "callId", "imei"}, body
    body2 = protocol.vc_request("20001", "127.0.0.1:4201",
                                "127.0.0.1:4200", "opus", "sess",
                                CALL_ID_BODY, "dev-1", '{"srtpMode":2}')
    assert set(body2) == {"calleeId", "rtcpAddress", "rtpAddress",
                          "codec", "session", "callId", "imei",
                          "extendData", "subCommand"}, body2
    assert body2["subCommand"] == 3, body2
    assert body2["extendData"] == '{"srtpMode":2}', body2


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
    print("%d/%d tests passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
