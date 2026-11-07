"""Cuoc goi di duoc tra loi phai GIU DUOC, khong tu ngat (live 2026-11-08).

Bao cao user 06:08 08/11: "cuoc goi khong giu ma ngat luon". Cac cuoc
test truoc deu khong co nguoi nhac may (do chuong toi timeout 30s roi
cancel) — CHUA TUNG co cuoc goi nao duoc tra loi that tu app PC.
Dieu tra bang code + bundle/pcap cho thay HAI loi gop lai:

1. App KHONG CO duong answer: signaling.answer()/answer_ack() khong
   ai goi; sync/ctrl khong trich event tra loi; CallLog khong co
   trang thai "answered" (nhanh "answered" trong _send_end_signal
   la dead code — docstring tu nhan). Ring timer (30s) duoc arm o
   buoc 2 va KHONG BAO GIO duoc go, nen cuoc goi duoc tra loi van
   bi giet o moc 30s bang cancel — ben kia nhac may muon (vd 25s)
   thi cuoc goi chet vai giay sau khi nhac may ("vua nhac may da
   ngat"); nhac may som thi chet o 30s ("khong giu").
2. Khong co media chieu nao: 11300 that khong co srtpKey
   (live 06/11), srtp "not-wired", send_pcm tu choi, media den
   bi drop; engine that dung ZRTP (Init 185B, _doInitZRTP) ma app
   khong cai dat. Sau khi ben kia nhac may, engine that doi media/
   ZRTP trong vai giay roi tu ket thuc — phia app khong thay gi
   (sync down, khong co duong answer) nen cuoc goi van hien
   "sent" toi khi ring timer giet. ZRTP day du la viec lon, ngoai
   pham vi vong nay; vong nay sua (1) + bao trung thuc trang thai
   media thay vi ngat.

Sua o vong nay:
* CallLog: trang thai "answered" (live) + record_answered +
  answered_at/answer_source; snapshot()/record_end()/record_start
  coi "answered" la live (neu khong, cuoc goi da tra loi se khong
  ket thuc duoc qua /api/call/end).
* Ring timer: luu handle theo call_id, go khi tra loi; ham fire
  bo qua cuoc goi da "answered" (phong thu hai lop).
* POST /api/call/answered: danh dau cuoc goi song la da tra loi
  (nguon "api" — moi cho handler sync sau nay); gui answerack
  (11304, sendAnswerACKCall trong bundle) best-effort cho goi 1-1.
* Media den dau tien (RTP qua relay) chung minh ben kia da tra
  loi (pcap: chi co media sau khi tra loi; goi khong tra loi nhan
  0 media) — transport goi on_first_media, server noi vao
  _mark_answered nguon "media". Hoat dong khong can kenh sync.
* Ket thuc cuoc goi da tra loi gui ENDCALL (11306), khong phai
  cancel (nhanh da co san trong _send_end_signal, gio moi song).
* /api/calls kem media.srtp ("not-wired" khi chua co khoa) de UI
  bao trung thuc "da noi, chua co tieng (thieu khoa SRTP)".
* UI: trang thai "answered" hien "Dang goi" (khong phai "Dang do
  chuong"), man hinh goi khong dong khi peer tra loi.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from test_call_11301 import (  # noqa: E402
    _api, _fake_endpoints, _login, _start_app)
from test_call_ringing import _run  # noqa: E402
from test_media_provider import FakeTransport  # noqa: E402
from zalo_pc_app import media_endpoints  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import udp_transport  # noqa: E402

CALL_ID_ANSWER = 1763200001
CALL_ID_END_ANSWERED = 1763200002
CALL_ID_MEDIA = 1763200003
CALL_ID_NO_LIVE = 1763200004
CALL_ID_MEDIA_STATE = 1763200005


def _start_call(base, callee_id, call_id):
    status, body = _api(base, "POST", "/api/call/request",
                        {"callee_id": callee_id, "call_id": call_id})
    assert body["ok"] is True, body
    assert body["request_sent"] is True, body
    return body["call_id"]


def _active(base, call_id):
    _s, calls = _api(base, "GET", "/api/calls")
    active = calls.get("active")
    if active is None or str(active["call_id"]) != str(call_id):
        return None
    return active


def test_answered_call_survives_ring_timeout():
    """Cuoc goi da tra loi phai SONG qua moc ring timeout: danh dau
    answered qua POST /api/call/answered roi doi qua timeout (rut
    ngan con 2s) — cuoc goi van active, status "answered", mock
    khong thay cancel/endcall nao, transport van chay. Day la loi
    chinh cua bao cao 08/11 (cuoc goi khong giu, ngat luon)."""
    old_timeout = app_server.RING_TIMEOUT_SECONDS
    app_server.RING_TIMEOUT_SECONDS = 2
    try:
        def check(base, mock, endpoints):
            eff_id = _start_call(base, "20001", CALL_ID_ANSWER)
            status, body = _api(base, "POST", "/api/call/answered",
                                {"call_id": eff_id})
            assert body["ok"] is True, body
            assert body["status"] == "answered", body
            assert body["call_id"] == eff_id, body
            time.sleep(4.0)
            active = _active(base, eff_id)
            assert active is not None, "answered call vanished"
            assert active["status"] == "answered", active
            assert active.get("answered_at"), active
            steps = mock.voice_call_state(eff_id)["steps"]
            bad = [s for s in steps if s in ("endcall", "cancel",
                                             "group/endcall",
                                             "group/cancel")]
            assert bad == [], steps
            record = endpoints.active_record(eff_id)
            assert record is not None, "transport record vanished"
            assert record["transport"].stopped is False, \
                "transport stopped after answer"
        _run(MockZalo().start(), check)
    finally:
        app_server.RING_TIMEOUT_SECONDS = old_timeout


def test_answered_call_ends_with_endcall():
    """Ket thuc cuoc goi DA tra loi phai gui ENDCALL (11306), KHONG
    phai cancel (11305): cancel chi huy loi moi chua tra loi; cuoc
    goi da noi phai ket thuc bang endcall. Nhanh nay da co san
    trong _send_end_signal nhung la dead code vi khong entry nao
    co status "answered" — test nay lam no song."""
    def check(base, mock, endpoints):
        eff_id = _start_call(base, "20001", CALL_ID_END_ANSWERED)
        status, body = _api(base, "POST", "/api/call/answered",
                            {"call_id": eff_id})
        assert body["ok"] is True, body
        status, body = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001", "call_id": eff_id,
                             "type": "user"})
        assert body["ok"] is True, body
        assert body["zalo_signal"] == "endcall", body
        assert body["zalo_endcall_ok"] is True, body
        steps = mock.voice_call_state(eff_id)["steps"]
        assert "cancel" not in steps, steps
        assert steps[-1] == "endcall", steps
        _s, calls = _api(base, "GET", "/api/calls")
        assert calls.get("active") is None, calls
        by_id = {c["call_id"]: c for c in calls["calls"]}
        assert by_id[str(eff_id)]["detail"] == "user_end", calls
        assert endpoints.active_record(eff_id) is None, \
            "transport still running after end"
    _run(MockZalo().start(), check)


def test_first_media_marks_answered():
    """Media den dau tien (RTP qua relay) chung minh ben kia da tra
    loi — pcap: chi co media sau khi tra loi, goi khong tra loi
    nhan 0 media. Du SRTP chua co khoa (not-wired, dung nhu live)
    thi goi RTP den van phai danh dau answered: viec nhan duoc goi
    khong phu thuoc giai ma duoc no. Sau do cuoc goi song qua ring
    timeout ma khong can POST /api/call/answered."""
    old_timeout = app_server.RING_TIMEOUT_SECONDS
    app_server.RING_TIMEOUT_SECONDS = 2
    try:
        def check(base, mock, endpoints):
            eff_id = _start_call(base, "20001", CALL_ID_MEDIA)
            record = endpoints.active_record(eff_id)
            assert record is not None, "no transport record"
            assert record["srtp"] == "not-wired", record
            transport = record["transport"]
            assert isinstance(transport, FakeTransport), transport
            # Mot goi RTP (da protect) tu relay — nhu peer bat dau
            # gui media sau khi nhac may. Khong co SRTP hook that
            # nen deliver_inbound se loi (giong transport that
            # drop goi khi unprotect thieu), nhung viec NHAN duoc
            # goi da du de danh dau answered.
            rtp = udp_transport.build_rtp(
                1, 320, 0x11223344, b"\x00" * 20)
            try:
                transport.deliver_inbound(rtp)
            except Exception:
                pass  # expected without SRTP hooks; arrival is enough
            active = _active(base, eff_id)
            assert active is not None, "call vanished after media"
            assert active["status"] == "answered", active
            assert active.get("answer_source") == "media", active
            time.sleep(4.0)
            active = _active(base, eff_id)
            assert active is not None, \
                "media-answered call died at ring timeout"
            assert active["status"] == "answered", active
            steps = mock.voice_call_state(eff_id)["steps"]
            assert "cancel" not in steps, steps
            assert "endcall" not in steps, steps
        _run(MockZalo().start(), check)
    finally:
        app_server.RING_TIMEOUT_SECONDS = old_timeout


def test_answered_endpoint_no_live_call():
    """POST /api/call/answered khi khong co cuoc goi song phai bao
    loi ro (no_live_call), khong crash; goi 2 lan cho cung cuoc goi
    phai idempotent (van answered, khong loi)."""
    def check(base, mock, endpoints):
        status, body = _api(base, "POST", "/api/call/answered",
                            {"call_id": CALL_ID_NO_LIVE})
        assert body["ok"] is False, body
        assert body["error"] == "no_live_call", body
        eff_id = _start_call(base, "20001", CALL_ID_MEDIA_STATE)
        status, body = _api(base, "POST", "/api/call/answered",
                            {"call_id": eff_id})
        assert body["ok"] is True, body
        status, body = _api(base, "POST", "/api/call/answered",
                            {"call_id": eff_id})
        assert body["ok"] is True, body
        assert body["status"] == "answered", body
        active = _active(base, eff_id)
        assert active is not None and active["status"] == "answered", \
            active
    _run(MockZalo().start(), check)


def test_calls_response_reports_media_state():
    """/api/calls phai kem media.srtp cho cuoc goi song de UI bao
    trung thuc: da noi nhung "not-wired" (chua co khoa SRTP) thi
    hien "chua co tieng (thieu khoa SRTP)" thay vi gia vo da co
    tieng hay tu ngat cuoc goi."""
    def check(base, mock, endpoints):
        eff_id = _start_call(base, "20001", CALL_ID_MEDIA_STATE + 1)
        status, body = _api(base, "POST", "/api/call/answered",
                            {"call_id": eff_id})
        assert body["ok"] is True, body
        active = _active(base, eff_id)
        assert active is not None, "no active call"
        media = active.get("media")
        assert media is not None, active
        assert media.get("srtp") == "not-wired", media
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
