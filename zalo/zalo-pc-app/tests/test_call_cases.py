"""Cac truong hop NHAN cuoc goi Zalo (ca that co the gap, tim ra khi ra soat 11/11):
  1. Zalo gui lai su kien `request` cung call_id khi con chuong      -> chi mot entry, khong ringring/webhook lan hai.
  2. Zalo gui lai `request` cung call_id SAU KHI da nghe may        -> cuoc van "answered" (truoc day bi dat lai "incoming").
  3. Co cuoc thu hai DEN khi dang noi                               -> tu choi cuoc moi (cancel+endcall), cuoc dang noi nguyen ven.
  4. Cuoc DEN khi minh dang goi di (chua ai nghe)                   -> tu choi cuoc moi, cuoc goi di nguyen ven.
  5. Hai cuoc DEN lien tiep khi chua nghe cuoc nao                  -> cuoc moi thay cuoc cu (hanh vi cu giu nguyen).
Mock/offline hoan toan (mock Zalo), khuon test_call_incoming_zca."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from test_call_11301 import _api, FAKE_TOKEN  # noqa: E402
from test_call_incoming_zca import (CALL_ID_IN, CALL_ID_IN2, CALL_ID_OUT, CALLER_ID, INCOMING_EVENT, _capture_call_webhooks,  # noqa: E402
                                    _parsed_event, _wait_active, _wait_steps)
from test_call_ringing import _run, _start_call  # noqa: E402
from test_media_provider import REAL_SHAPE_SERVERS  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def _mock():
    mock = MockZalo().start()
    mock.requestcall_data = {"servers": REAL_SHAPE_SERVERS, "sessId": "sess-cases", "srtpKey": "k-test", "token": FAKE_TOKEN}
    return mock


def _event(call_id, caller="20001"):
    ev = dict(INCOMING_EVENT)
    ev["callId"], ev["uidN"] = call_id, caller
    return _parsed_event(ev)


def _calls(base):
    return {str(c["call_id"]): c for c in _api(base, "GET", "/api/calls")[1]["calls"]}


def _count(calls, call_id):
    return sum(1 for c in calls if str(c["call_id"]) == str(call_id))


def test_duplicate_request_while_ringing_is_ignored():
    mock = _mock()

    def check(base, mock, endpoints):
        sent = _capture_call_webhooks(app_server.STATE)
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN))
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN))
        time.sleep(0.5)
        calls = _api(base, "GET", "/api/calls")[1]["calls"]
        assert _count(calls, CALL_ID_IN) == 1, calls
        assert [p["type"] for p in sent].count("call.incoming") == 1, sent

    _run(mock, check)


def test_duplicate_request_after_answer_keeps_call_answered():
    mock = _mock()

    def check(base, mock, endpoints):
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        _wait_steps(mock, CALL_ID_IN, ["ringring"])
        st, body = _api(base, "POST", "/api/call/answer", {"call_id": CALL_ID_IN})
        assert body["ok"] is True, body
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN))       # Zalo gui lai request sau khi da nghe
        time.sleep(0.4)
        c = _calls(base)[str(CALL_ID_IN)]
        assert c["status"] == "answered", c
        assert _count(_api(base, "GET", "/api/calls")[1]["calls"], CALL_ID_IN) == 1

    _run(mock, check)


def test_second_incoming_while_talking_is_rejected_busy():
    mock = _mock()

    def check(base, mock, endpoints):
        sent = _capture_call_webhooks(app_server.STATE)
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        _wait_steps(mock, CALL_ID_IN, ["ringring"])
        assert _api(base, "POST", "/api/call/answer", {"call_id": CALL_ID_IN})[1]["ok"] is True
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN2, caller="20002"))
        steps2 = _wait_steps(mock, CALL_ID_IN2, ["cancel", "endcall"])
        assert "cancel" in steps2 and "endcall" in steps2 and "answer" not in steps2, steps2
        calls = _calls(base)
        assert calls[str(CALL_ID_IN)]["status"] == "answered", calls[str(CALL_ID_IN)]          # cuoc dang noi nguyen ven
        assert calls[str(CALL_ID_IN2)]["status"] == "ended" and calls[str(CALL_ID_IN2)]["detail"] == "busy_rejected"
        assert _api(base, "GET", "/api/calls")[1]["active"]["call_id"] == str(CALL_ID_IN)
        assert any(p.get("call_id") == str(CALL_ID_IN2) for p in sent), sent                       # van bao HA nhu cuoc nho

    _run(mock, check)


def test_incoming_while_dialing_out_is_rejected_busy():
    mock = _mock()

    def check(base, mock, endpoints):
        out_id = _start_call(base, "20009", CALL_ID_OUT)                # ta dang goi di, chua ai nghe
        assert _wait_active(base, out_id, "sent") is not None
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN, caller="20002"))
        steps = _wait_steps(mock, CALL_ID_IN, ["cancel", "endcall"])
        assert "cancel" in steps and "answer" not in steps, steps
        calls = _calls(base)
        assert calls[str(out_id)]["status"] == "sent", calls[str(out_id)]                            # cuoc goi di nguyen ven
        assert calls[str(CALL_ID_IN)]["detail"] == "busy_rejected", calls[str(CALL_ID_IN)]

    _run(mock, check)


def test_stale_answered_record_without_media_does_not_block_new_incoming():
    """Ban ghi "answered" bi treo (mat su kien ket thuc, khong con media) khong duoc chan cuoc goi den ke tiep."""
    mock = _mock()

    def check(base, mock, endpoints):
        app_server.STATE.calls.record_start(4242, "Stale", "20009", "user")
        app_server.STATE.calls.record_answered(4242, "test")                # co ban ghi song, KHONG co engine/media
        assert app_server.media_endpoints.ENDPOINTS.active_record(4242) is None
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN, caller="20002"))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None        # cuoc moi duoc nhan binh thuong
        calls = _calls(base)
        assert calls["4242"]["detail"] == "superseded_by_new_call"
        assert calls[str(CALL_ID_IN)]["detail"] != "busy_rejected"

    _run(mock, check)


def test_incoming_call_webhook_carries_contact_status_and_call_type_and_never_guesses():
    """HA ap quy tac theo nguoi quen/nguoi la: app bao friend/stranger va "unknown" khi chua tai duoc danh ba (HA dong cua, khong doan)."""
    mock = _mock()

    def check(base, mock, endpoints):
        state = app_server.STATE
        sent = _capture_call_webhooks(state)
        for ids, expect, cid in ((None, "unknown", CALL_ID_IN), ({"20001"}, "friend", CALL_ID_IN2), ({"999"}, "stranger", CALL_ID_IN2 + 10)):
            state._friend_ids = lambda ids=ids: ids
            before = len(sent)
            state._on_ctrl_call_event(_event(cid))
            deadline = time.time() + 5
            while time.time() < deadline and not [p for p in sent[before:] if p.get("type") == "call.incoming" and p.get("call_id") == str(cid)]:
                time.sleep(0.05)
            inc = [p for p in sent[before:] if p.get("type") == "call.incoming" and p.get("call_id") == str(cid)]
            assert inc and inc[0]["contact_status"] == expect, (expect, sent[before:])
            assert "call_type_raw" in inc[0] and inc[0]["call_type_raw"] == 0, inc[0]            # 0 = thoai (theo zca-js)
            state._on_ctrl_call_event(_parsed_event({"act": "cancel", "callId": cid, "uidN": "20001"}))   # cup de cuoc ke tiep khong bi coi la ban

    _run(mock, check)


def test_answer_with_off_overrides_never_starts_default_mic_speaker_or_camera_even_on_video_request():
    """BAT BIEN RIENG TU: HA nghe may theo quy tac gui mic_url/speaker_url/camera_url = "off" -> app KHONG tu phat mic/hinh mac dinh
    (nguoi la khong nghe duoc phong nha), ke ca khi ben kia xin len video. Doi chung: khong "off" thi mic/hinh mac dinh duoc phat."""
    mock = _mock()
    real_mic, real_vid = app_server._start_mic, app_server._start_video
    started = []
    app_server._start_mic = lambda cid, src, fmt="auto", loop=True: started.append(("mic", str(cid), src))
    app_server._start_video = lambda cid, src, params=None: started.append(("cam", str(cid), src))

    def check(base, mock, endpoints):
        st, body = _api(base, "POST", "/api/settings/devices", {"mic_url": "test", "camera_url": "test", "auto_mic": True,
                                                                "auto_video_on_request": True})
        assert body["ok"], body
        for cid, answer_body, expect_started in ((CALL_ID_IN, {"mic_url": "off", "speaker_url": "off", "camera_url": "off"}, False),
                                                 (CALL_ID_IN2, {}, True)):
            started.clear()
            app_server.STATE._on_ctrl_call_event(_event(cid, caller="20003"))
            assert _wait_active(base, cid, "incoming") is not None
            _wait_steps(mock, cid, ["ringring"])
            assert _api(base, "POST", "/api/call/answer", dict(answer_body, call_id=cid))[1]["ok"] is True
            app_server.STATE._on_video_request({"call_id": cid, "act": "audio_to_video", "data": {"params": {"status": 1}}})
            time.sleep(0.6)
            assert bool(started) is expect_started, (answer_body, started)
            _api(base, "POST", "/api/call/end", {"call_id": cid})

    try:
        _run(mock, check)
    finally:
        app_server._start_mic, app_server._start_video = real_mic, real_vid


def test_video_request_is_reported_to_ha_never_auto_accepted_by_default_and_accept_video_target_works():
    """Người gọi xin chuyển thoại sang video: app BÁO HA (status video_request) và KHÔNG tự đồng ý (mặc định tắt, riêng tư); HA đồng ý bằng
    /api/call/media target accept_video (a2v status 2), kèm camera_url thì phát hình, không kèm thì chỉ đồng ý; cuộc chưa nghe máy thì báo lỗi."""
    mock = _mock()
    real_vid, real_a2v = app_server._start_video, app_server._send_a2v_async
    a2v, started = [], []
    app_server._send_a2v_async = lambda cid, tid, st: a2v.append((str(cid), int(st)))
    app_server._start_video = lambda cid, src, params=None: started.append((str(cid), src))

    def check(base, mock, endpoints):
        state = app_server.STATE
        assert state.devices.get()["auto_video_on_request"] is False                    # mặc định TẮT
        sent = _capture_call_webhooks(state)
        state._on_ctrl_call_event(_event(CALL_ID_IN, caller="20003"))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        _wait_steps(mock, CALL_ID_IN, ["ringring"])
        # chưa nghe máy: không đồng ý được
        assert _api(base, "POST", "/api/call/media", {"call_id": CALL_ID_IN, "action": "start", "target": "accept_video"})[1] == {"ok": False, "error": "chua_nghe_may"}
        assert _api(base, "POST", "/api/call/answer", {"call_id": CALL_ID_IN, "mic_url": "off", "speaker_url": "off", "camera_url": "off"})[1]["ok"] is True
        state._on_video_request({"call_id": CALL_ID_IN, "act": "audio_to_video", "data": {"params": {"status": 1}}})
        deadline = time.time() + 5
        while time.time() < deadline and not [p for p in sent if p.get("status") == "video_request"]:
            time.sleep(0.05)
        vr = [p for p in sent if p.get("status") == "video_request"]
        assert vr and vr[0]["call_id"] == str(CALL_ID_IN) and vr[0]["thread_id"] == "20003" and "contact_status" in vr[0], sent
        time.sleep(0.4)
        assert a2v == [] and started == [], (a2v, started)                                # không tự đồng ý
        # status 2 (bên kia đồng ý lời xin của ta) không phải lời xin: không báo
        n = len(vr)
        state._on_video_request({"call_id": CALL_ID_IN, "act": "audio_to_video", "data": {"params": {"status": 2}}})
        time.sleep(0.3)
        assert len([p for p in sent if p.get("status") == "video_request"]) == n
        # HA đồng ý: chỉ đồng ý, không gửi hình
        r = _api(base, "POST", "/api/call/media", {"call_id": CALL_ID_IN, "action": "start", "target": "accept_video"})[1]
        assert r["ok"] is True and a2v == [(str(CALL_ID_IN), 2)] and started == [], (r, a2v, started)
        # đồng ý và gửi camera
        r = _api(base, "POST", "/api/call/media", {"call_id": CALL_ID_IN, "action": "start", "target": "accept_video", "camera_url": "test"})[1]
        assert r["ok"] is True and a2v[-1] == (str(CALL_ID_IN), 2) and started == [(str(CALL_ID_IN), "test")], (r, a2v, started)
        _api(base, "POST", "/api/call/end", {"call_id": CALL_ID_IN})

    try:
        _run(mock, check)
    finally:
        app_server._start_video, app_server._send_a2v_async = real_vid, real_a2v


def test_two_incoming_before_answering_newer_supersedes():
    mock = _mock()

    def check(base, mock, endpoints):
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        app_server.STATE._on_ctrl_call_event(_event(CALL_ID_IN2, caller="20002"))
        assert _wait_active(base, CALL_ID_IN2, "incoming") is not None
        assert _calls(base)[str(CALL_ID_IN)]["detail"] == "superseded_by_new_call"

    _run(mock, check)


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("ALL CALL-CASE TESTS PASSED")
