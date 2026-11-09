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

Sua o vong nay (2 commit: 2cb1e7f + vong ket thuc):
  * Server log vong doi cuoc goi ra stdout ([call] start/step2/
    end + ly do that + thoi luong) de lan test sau doc duoc tu
    `docker logs` ma khong can F12 (app Zalo PC khong co F12).
  * Lich su cuoc goi ghi ly do ket thuc that (user_end /
    superseded_by_new_call / ring_timeout / user_end + loi Zalo)
    va UI hien ly do do.
  * Guard chong bam doi nut Goi (startCall): mot lan bam = mot
    loi moi duy nhat.
  * KET THUC DUNG TIN HIEU (live 09:01-09:03): cuoc goi 1-1 CHUA
    tra loi ket thuc bang CANCEL (11305), khong phai endcall
    (11306) — cancel moi la tin hieu huy loi moi, peer tat man
    hinh cuoc goi den qua [SIG]recvCancel; gui endcall de lai
    "cuoc goi an" ma tren dien thoai ben kia. Cuoc goi nhom giu
    endcall_group (group_cancel chua truy vet).
  * TIMEOUT DO CHUONG ~30s (pcap file 2 + live 00:31): cuoc goi
    do chuong khong ai tra loi tu ket thuc (cancel tren wire,
    ly do ring_timeout), dung transport — thay vi song mai o
    trang thai "sent" va bao "dang ket noi" sau khi da ket thuc.
  * Cuoc goi cu bi thay the cung duoc cancel + dung transport.
  * UI dong man hinh goi khi poll thay cuoc goi da het o noi
    khac, va dong trang thai do chuong noi ro gioi han ~30 giay.
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
from zalo_pc_app import server as app_server  # noqa: E402

CALL_ID_RING = 1763100001  # epoch seconds, fits uint32
CALL_ID_LOG = 1763100002
CALL_ID_END = 1763100003
CALL_ID_SUPERSEDE_1 = 1763100004
CALL_ID_SUPERSEDE_2 = 1763100005
CALL_ID_ZALO_FAIL = 1763100006
CALL_ID_TIMEOUT = 1763110001
CALL_ID_CANCEL = 1763110002
CALL_ID_SUPERSEDE_C1 = 1763110003
CALL_ID_SUPERSEDE_C2 = 1763110004
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
        # The end signal for an unanswered 1-1 call is cancel, not
        # endcall (see _send_end_signal).
        assert "zalo_signal=cancel zalo_ok=True" in log, log
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


def test_end_reason_kept_when_zalo_cancel_fails():
    """Zalo tu choi cancel (mock error) thi cuoc goi van ket thuc
    local, va detail giu DUOC ly do user_end kem loi Zalo thay vi
    bi loi Zalo ghi de mat."""
    def check(base, mock, endpoints):
        mock.cancel_mode = "error"
        eff_id = _start_call(base, "20001", CALL_ID_ZALO_FAIL)
        status, body = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001", "call_id": eff_id,
                             "type": "user"})
        assert body["ok"] is True, body
        assert body["zalo_endcall_ok"] is False, body
        assert body["zalo_signal"] == "cancel", body
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        detail = by_id[str(eff_id)]["detail"]
        assert detail.startswith("user_end; zalo_cancel: "), detail
        assert "mock cancel rejected" in detail, detail
    _run(MockZalo().start(), check)


def test_unanswered_call_ends_with_cancel():
    """Ket thuc cuoc goi 1-1 CHUA tra loi phai gui CANCEL (11305),
    KHONG phai endcall (11306): cancel moi la tin hieu huy loi
    moi — peer tat man hinh cuoc goi den qua [SIG]recvCancel.
    Response noi ro tin hieu da gui (zalo_signal)."""
    def check(base, mock, endpoints):
        eff_id = _start_call(base, "20001", CALL_ID_CANCEL)
        status, body = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001", "call_id": eff_id,
                             "type": "user"})
        assert body["ok"] is True, body
        assert body["zalo_signal"] == "cancel", body
        assert body["zalo_endcall_ok"] is True, body
        steps = mock.voice_call_state(eff_id)["steps"]
        assert steps == ["requestcall", "request", "cancel"], steps
        status, body = _api(base, "GET", "/api/calls")
        assert body["active"] is None, body
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(eff_id)]["detail"] == "user_end", body
        assert endpoints.active_record(eff_id) is None, \
            "transport still running after end"
    _run(MockZalo().start(), check)


def test_ring_timeout_cancels_call():
    """Cuoc goi do chuong khong ai tra loi phai TU ket thuc sau
    timeout do chuong (o day rut ngan con 2s; gia tri that ~30s):
    ly do ring_timeout, mock thay cancel, transport dung,
    /api/calls het active — khong con bao "dang ket noi" sau khi
    cuoc goi da ket thuc (live 09:03)."""
    old_timeout = app_server.RING_TIMEOUT_SECONDS
    app_server.RING_TIMEOUT_SECONDS = 2
    try:
        def check(base, mock, endpoints):
            eff_id = _start_call(base, "20001", CALL_ID_TIMEOUT)
            ended = None
            for _ in range(20):
                time.sleep(0.5)
                _s, calls = _api(base, "GET", "/api/calls")
                if calls.get("active") is None:
                    ended = [c for c in calls["calls"]
                             if str(c["call_id"]) == str(eff_id)]
                    break
            assert ended, "call still 'sent' after ring timeout"
            assert ended[0]["status"] == "ended", ended
            assert ended[0]["detail"] == "ring_timeout", ended
            # The cancel is sent by the timer thread AFTER record_end
            # marks the call ended, so the mock may not show it yet
            # the instant /api/calls reports no active call: poll
            # for it briefly instead of asserting at once.
            steps = []
            for _ in range(20):
                steps = mock.voice_call_state(eff_id)["steps"]
                if "cancel" in steps:
                    break
                time.sleep(0.25)
            assert steps == ["requestcall", "request", "cancel"], steps
            # Cuoc goi duoc danh dau ket thuc TRUOC khi transport dung xong (dong
            # luong + giai phong socket): cho toi 3 s cho tinh nhat quan cuoi cung.
            for _ in range(30):
                if endpoints.active_record(eff_id) is None:
                    break
                time.sleep(0.1)
            assert endpoints.active_record(eff_id) is None, \
                "transport still running after ring timeout"
        _run(MockZalo().start(), check)
    finally:
        app_server.RING_TIMEOUT_SECONDS = old_timeout


def test_superseded_call_cancelled_and_stopped():
    """Goi moi thay the goi cu dang do chuong: goi cu phai duoc
    cancel tren wire (peer cu het do chuong) VA transport cua no
    phai dung — truoc day ca hai deu khong xay ra."""
    def check(base, mock, endpoints):
        eff_1 = _start_call(base, "20001", CALL_ID_SUPERSEDE_C1)
        eff_2 = _start_call(base, "20002", CALL_ID_SUPERSEDE_C2)
        steps_1 = mock.voice_call_state(eff_1)["steps"]
        assert steps_1 == ["requestcall", "request", "cancel"], steps_1
        assert endpoints.active_record(eff_1) is None, \
            "superseded call's transport still running"
        assert endpoints.active_record(eff_2) is not None, \
            "new call's transport missing"
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(eff_1)]["detail"] == "superseded_by_new_call", body
        assert by_id[str(eff_2)]["status"] == "sent", body
    _run(MockZalo().start(), check)


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
