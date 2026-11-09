"""Trang thai cuoc goi phia SERVER phai dung: ringing -> connected
chi khi peer dong y; missed chi khi ket thuc ma khong ai tra loi.

Gia thuyet user 06:25 08/11: "Goi bao luon cuoc goi nhỡ. Ma cuoc
goi nhoz chi xay ra khi ben kia khong nhac may. Co the bi nham va
chuyen sang da ket noi ben server. Trong khi khi goi phai cho dau
kia dong y moi ket noi." Phan tich lai 5 file PCAP cu (05/11,
tai khoan phu, 2026-11-08) chung minh flow that:

* "Cuoc goi nhoz" chi ghi SAU KHI cuoc goi ket thuc ma khong ai
  tra loi (dong bo qua tt-chat4 0,1-0,6 s sau khi ket thuc;
  timeout do chuong ~30 s). KHONG BAO GIO ghi nhoz ngay luc bat
  dau goi.
* "Dang do chuong" -> "da ket noi" = tin hieu TRA LOI cua peer
  tren kenh voicecall (ben bi goi gui burst lon mang dia chi
  media) + server day sync "da tra loi" + type-04 downlink xuat
  hien + RTCP + keepalive + P2P. Cuoc goi khong tra loi co 0
  trong cac dau hieu nay.
* Tin hieu neu gui sai luc se khien server hieu nham la "da ket
  noi": chinh la tin hieu TRA LOI. Ben goi KHONG BAO GIO gui tin
  hieu nay (11303 answer / 11302 ringring la tin hieu cua ben bi
  goi).
* "Da ket noi" KHONG duoc suy ra tu viec media chay (file 2: ben
  goi gui type-03 uplink trong luc do chuong ma khong ai tra loi).
  Chi chuyen connected khi nhan tin hieu tra loi cua peer
  (voicecall/sync) + thay type-04 downlink.
* App gui 11301 LUON mang dia chi relay that (engine dung relay
  truoc: probe -> setup -> type-02 roi moi gui 11301). O head
  a523bda, for_call da cho type-02 (toi da 5 s) va raise thay vi
  gui 11301 voi dia chi rong — test o day khoa hanh vi do lai
  (regression guard), khong phai sua moi.
* Phia goi di phai duy tri relay trong luc do chuong: setup nhac
  lai moi 6 s + ping ~10 Hz; PING_INTERVAL cu 6,0 s lech 60 lan
  so voi client that (file 2: 290 cap ping trong 29,5 s) nen
  doi ve 0,1 s o vong nay.

Mock mo hinh trang thai server qua server_call_state() (xem
mock_server.py): "ringing" sau requestcall, "connected" sau
answerack, "ended" sau cancel/endcall; record "missed" khi ket
thuc ma peer chua dong y, "ended" khi ket thuc da noi. Day la
CONTRACT rut ra tu PCAP + bao cao user, khong phai noi that
ben trong server Zalo (TLS ma hoa, khong quan sat duoc tu day)
— test live moi chung minh server that hanh xu nhu vay.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from test_call_11301 import _api  # noqa: E402
from test_call_answered import _active, _start_call  # noqa: E402
from test_call_ringing import _run  # noqa: E402
from test_media_provider import FakeTransport  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import udp_transport  # noqa: E402

CALL_ID_RINGING = 1763200101
CALL_ID_CONNECT = 1763200102
CALL_ID_TIMEOUT = 1763200103
CALL_ID_END_CONNECTED = 1763200104
CALL_ID_MEDIA_CONNECT = 1763200105
CALL_ID_NO_CALLEE_SIG = 1763200106


def test_dial_stays_ringing_no_missed():
    """Goi di phai o trang thai "ringing", khong phai "connected",
    khong ghi "missed" ngay: sau requestcall + request (11300/
    11301), mock thay state "ringing", record None, steps dung
    [requestcall, request]. 11301 phai mang dia chi relay that
    (rtcp/rtp khong rong) — client that khong bao gio gui 11301
    voi dia chi media rong (PCAP 05/11)."""
    def check(base, mock, endpoints):
        eff_id = _start_call(base, "20001", CALL_ID_RINGING)
        state = mock.server_call_state(eff_id)
        assert state["state"] == "ringing", state
        assert state["record"] is None, state
        assert state["steps"] == ["requestcall", "request"], state
        addrs = state["request_addresses"]
        assert addrs is not None, state
        for key in ("rtcp", "rtp"):
            val = addrs.get(key)
            assert isinstance(val, str) and val, addrs
            assert ":" in val, addrs  # "IP:port" cua relay that
    _run(MockZalo().start(), check)


def test_no_callee_signals_at_dial():
    """Ben goi KHONG BAO GIO gui tin hieu cua ben bi goi: sau khi
    goi di, mock khong thay "answer" (11303) hay "ringring"
    (11302). Gui nham mot trong hai tin nay luc goi se khien
    server chuyen sang "da ket noi" truoc khi peer dong y — dung
    co che user nghi ngo 06:25 08/11."""
    def check(base, mock, endpoints):
        eff_id = _start_call(base, "20001", CALL_ID_NO_CALLEE_SIG)
        steps = mock.server_call_state(eff_id)["steps"]
        assert "answer" not in steps, steps
        assert "ringring" not in steps, steps
        assert "answerack" not in steps, steps
    _run(MockZalo().start(), check)


def test_answerack_connects():
    """Peer tra loi (danh dau qua POST /api/call/answered) phai
    chuyen server sang "connected": app gui answerack (11304) va
    mock thay state "connected", record van None (chua ket thuc
    nen chua co ban ghi nhoz/ended)."""
    def check(base, mock, endpoints):
        eff_id = _start_call(base, "20001", CALL_ID_CONNECT)
        status, body = _api(base, "POST", "/api/call/answered",
                            {"call_id": eff_id})
        assert body["ok"] is True, body
        # answerack di tren daemon thread — doi no toi mock.
        time.sleep(1.0)
        state = mock.server_call_state(eff_id)
        assert state["state"] == "connected", state
        assert state["record"] is None, state
        assert "answerack" in state["steps"], state
    _run(MockZalo().start(), check)


def test_unanswered_timeout_is_missed():
    """Peer khong tra loi het timeout do chuong thi moi ghi
    "missed": goi di, doi qua ring timeout (rut ngan con 2 s) —
    mock thay state "ended", record "missed", steps co cancel
    (khong co endcall). Day la TRUONG HOP DUY NHAT duoc ghi
    nhoz, va no xay ra sau khi ket thuc, khong phai luc goi."""
    old_timeout = app_server.RING_TIMEOUT_SECONDS
    app_server.RING_TIMEOUT_SECONDS = 2
    try:
        def check(base, mock, endpoints):
            eff_id = _start_call(base, "20001", CALL_ID_TIMEOUT)
            time.sleep(4.0)
            state = mock.server_call_state(eff_id)
            assert state["state"] == "ended", state
            assert state["record"] == "missed", state
            assert "cancel" in state["steps"], state
            assert "endcall" not in state["steps"], state
        _run(MockZalo().start(), check)
    finally:
        app_server.RING_TIMEOUT_SECONDS = old_timeout


def test_answered_end_is_not_missed():
    """Cuoc goi DA tra loi ma ket thuc phai ghi "ended", KHONG
    phai "missed": danh dau answered roi bam ket thuc — app gui
    ENDCALL (11306), khong phai cancel; mock thay state "ended",
    record "ended". Tren code cu (a523bda) cuoc goi da tra loi
    van ket thuc bang cancel (nhanh "answered" trong
    _send_end_signal la dead code) nen mock se ghi "missed" —
    dung loi user bao 06:25 08/11."""
    def check(base, mock, endpoints):
        eff_id = _start_call(base, "20001", CALL_ID_END_CONNECTED)
        status, body = _api(base, "POST", "/api/call/answered",
                            {"call_id": eff_id})
        assert body["ok"] is True, body
        status, body = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001", "call_id": eff_id,
                             "type": "user"})
        assert body["ok"] is True, body
        assert body["zalo_signal"] == "endcall", body
        state = mock.server_call_state(eff_id)
        assert state["state"] == "ended", state
        assert state["record"] == "ended", state
        assert "endcall" in state["steps"], state
        assert "cancel" not in state["steps"], state
    _run(MockZalo().start(), check)


def test_first_media_connects_and_survives_timeout():
    """Type-04 downlink dau tien (media tu peer/relay) la bang
    chung peer da tra loi: chi co sau khi tra loi (file 1/4),
    0 goi trong 29,5 s do chuong khong tra loi (file 2). Sau
    media den, mock phai thay "connected" va cuoc goi phai song
    qua ring timeout (khong cancel/endcall, record None). Media
    chieu DI (type-03 uplink, ben goi gui ca luc do chuong) thi
    KHONG duoc dung lam tin hieu tra loi — hook chi ban tren
    media chieu DEN."""
    old_timeout = app_server.RING_TIMEOUT_SECONDS
    app_server.RING_TIMEOUT_SECONDS = 2
    try:
        def check(base, mock, endpoints):
            eff_id = _start_call(base, "20001", CALL_ID_MEDIA_CONNECT)
            record = endpoints.active_record(eff_id)
            assert record is not None, "no transport record"
            transport = record["transport"]
            assert isinstance(transport, FakeTransport), transport
            rtp = udp_transport.build_rtp(
                1, 320, 0x11223344, b"\x00" * 20)
            try:
                transport.deliver_inbound(rtp)
            except Exception:
                pass  # expected without SRTP hooks; arrival is enough
            # answerack di tren daemon thread — doi no toi mock.
            time.sleep(1.0)
            state = mock.server_call_state(eff_id)
            assert state["state"] == "connected", state
            assert state["record"] is None, state
            time.sleep(4.0)
            active = _active(base, eff_id)
            assert active is not None, \
                "media-answered call died at ring timeout"
            assert active["status"] == "answered", active
            state = mock.server_call_state(eff_id)
            assert state["state"] == "connected", state
            assert state["record"] is None, state
            assert "cancel" not in state["steps"], state
            assert "endcall" not in state["steps"], state
        _run(MockZalo().start(), check)
    finally:
        app_server.RING_TIMEOUT_SECONDS = old_timeout


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
