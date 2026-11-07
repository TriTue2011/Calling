"""Cuoc goi di bi ngat sau ~8 giay (live 2026-11-07, ban b276bf9).

Live: buoc 2 (11301) da gui, ben kia do chuong, bao cuoc goi nho —
nhung tieng chuong khong giu duoc, cuoc goi ngat sau ~8 giay thay
vi do chuong toi khi ben kia tra loi hoac het timeout do chuong
binh thuong (~30 giay tro len — pcap file 2: cuoc goi di khong
duoc tra loi do chuong ~30s, ben goi van gui media trong luc do).

Dieu tra bang code + bundle/pcap + repro cho thay:
  * Khong co duong nao trong app tu ket thuc cuoc goi: UI chi goi
    /api/call/end khi bam nut Ket thuc; server chi danh dau ket
    thuc khi co /api/call/end hoac khi cuoc goi moi thay the;
    transport chi gui refresh/ping/hello, khong bao gio tu dung;
    engine seam khong ket thuc cuoc goi. Repro /tmp
    /repro_call_cutoff.py chung minh cuoc goi van song sau 12s.
  * Vi vay phia ngat o live test nam NGOAI app (nguoi dung bam
    Ket thuc — PC khong co tieng chuong hoi nen 8 giay im lang
    de hieu lam la ket — hoac ben kia tu choi), nhung app KHONG
    THE phan biet duoc vi no khong log gi ve cuoc goi ra stdout
    (docker logs live khong co dong nao ve goi) va lich su cuoc
    goi khong ghi LY DO ket thuc.
  * Khong co endpoint "state" 1-1 trong bundle (chi co
    12445 group/state); ben goi chi biet ben kia tra loi/tu choi
    qua kenh sync day ve — sync hien down (can quet QR lai).
    Nen UI khong the hien "da tra loi" cho toi khi sync chay lai;
    day la gioi han da biet, khong phai loi sua o day.

Sua o vong nay:
  * Server log vong doi cuoc goi ra stdout ([call] start/step2/
    end + ly do that + thoi luong) de lan test sau doc duoc tu
    `docker logs` ma khong can F12 (app Zalo PC khong co F12).
  * Lich su cuoc goi ghi ly do ket thuc that (user_end /
    superseded_by_new_call / user_end + loi endcall Zalo) va UI
    hien ly do do.
  * Guard chong bam doi nut Goi (startCall): mot lan bam = mot
    loi moi duy nhat (truoc day bam doi gui hai requestcall voi
    hai callId khac nhau, ben kia nhan hai loi moi).
"""

import contextlib
import io
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from test_call_11301 import (  # noqa: E402
    _api, _fake_endpoints, _login, _start_app)
from zalo_pc_app import media_endpoints  # noqa: E402

CALL_ID_RING = 1763100001  # epoch seconds, fits uint32
CALL_ID_LOG = 1763100002
CALL_ID_END = 1763100003
CALL_ID_SUPERSEDE_1 = 1763100004
CALL_ID_SUPERSEDE_2 = 1763100005
CALL_ID_ZALO_FAIL = 1763100006
WAIT_SECONDS = 10  # past the ~8s live cutoff


def _start_call(base, callee_id, call_id):
    status, body = _api(base, "POST", "/api/call/request",
                        {"callee_id": callee_id, "call_id": call_id})
    assert body["ok"] is True, body
    assert body["request_sent"] is True, body
    return body["call_id"]


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


def test_call_stays_live_past_ring_cutoff():
    """Cuoc goi da gui buoc 2 phai van song sau 10 giay (qua moc
    ~8s live): log van 'sent', transport chua bao gio dung, mock
    khong thay bat ky endcall/cancel nao — app khong tu ngat
    cuoc goi."""
    def check(base, mock, endpoints):
        eff_id = _start_call(base, "20001", CALL_ID_RING)
        state = mock.voice_call_state(eff_id)
        assert state["steps"] == ["requestcall", "request"], state
        assert state["delivered"] is True, state
        t_end = time.time() + WAIT_SECONDS
        while time.time() < t_end:
            status, calls = _api(base, "GET", "/api/calls")
            active = calls.get("active")
            assert active is not None, "call vanished from /api/calls"
            assert active["status"] == "sent", active
            assert str(active["call_id"]) == str(eff_id), active
            time.sleep(1.0)
        state = mock.voice_call_state(eff_id)
        bad = [s for s in state["steps"]
               if s in ("endcall", "cancel", "group/endcall",
                        "group/cancel")]
        assert bad == [], state
        record = endpoints.active_record(eff_id)
        assert record is not None, "transport record vanished"
        assert record["transport"].stopped is False, "transport stopped"
    _run(MockZalo().start(), check)


def test_call_lifecycle_logged():
    """Server log vong doi cuoc goi ra stdout: [call] start, [call]
    step2, [call] end + ly do that + thoi luong — de lan test sau
    doc duoc tu `docker logs` ma khong can F12."""
    def check(base, mock, endpoints):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            eff_id = _start_call(base, "20001", CALL_ID_LOG)
            status, body = _api(base, "POST", "/api/call/end",
                                {"uid_to": "20001", "call_id": eff_id,
                                 "type": "user"})
            assert body["ok"] is True, body
        log = captured.getvalue()
        assert ("[call] start call_id=%s peer=20001 thread=20001 "
                "type=user" % eff_id) in log, log
        assert ("[call] step2 call_id=%s request_sent=True"
                % eff_id) in log, log
        assert ("[call] end call_id=%s reason=user_end duration="
                % eff_id) in log, log
        assert "zalo_endcall_ok=True" in log, log
        # No session material in the log (no token / sessId value).
        assert "sessId" not in log, log
        assert "zpw_" not in log, log
    _run(MockZalo().start(), check)


def test_end_reason_recorded_in_log():
    """Ly do ket thuc that duoc ghi vao lich su cuoc goi: bam Ket
    thuc -> detail 'user_end'; cuoc goi moi thay the -> cuoc cu
    detail 'superseded_by_new_call' + dong log supersede."""
    def check(base, mock, endpoints):
        eff_id = _start_call(base, "20001", CALL_ID_END)
        status, body = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001", "call_id": eff_id,
                             "type": "user"})
        assert body["ok"] is True, body
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(eff_id)]["status"] == "ended", body
        assert by_id[str(eff_id)]["detail"] == "user_end", body
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            eff_1 = _start_call(base, "20001", CALL_ID_SUPERSEDE_1)
            eff_2 = _start_call(base, "20002", CALL_ID_SUPERSEDE_2)
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(eff_1)]["status"] == "ended", body
        assert by_id[str(eff_1)]["detail"] == "superseded_by_new_call", body
        assert by_id[str(eff_2)]["status"] == "sent", body
        log = captured.getvalue()
        assert ("[call] end call_id=%s reason=superseded_by_new_call"
                % eff_1) in log, log
    _run(MockZalo().start(), check)


def test_end_reason_kept_when_zalo_endcall_fails():
    """Zalo tu choi endcall (mock error) thi cuoc goi van ket thuc
    local, va detail giu DUOC ly do user_end kem loi Zalo thay vi
    bi loi Zalo ghi de mat."""
    def check(base, mock, endpoints):
        mock.endcall_mode = "error"
        eff_id = _start_call(base, "20001", CALL_ID_ZALO_FAIL)
        status, body = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001", "call_id": eff_id,
                             "type": "user"})
        assert body["ok"] is True, body
        assert body["zalo_endcall_ok"] is False, body
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        detail = by_id[str(eff_id)]["detail"]
        assert detail.startswith("user_end; zalo_endcall: "), detail
        assert "mock endcall rejected" in detail, detail
    _run(MockZalo().start(), check)
