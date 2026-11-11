"""Goi den theo flow zca-js: call_event (ctrl 99101) -> 11302 ringring
-> 11303 answer; tu choi bang 11305 cancel + 11306 endcall.

Nguon: bao cao outbox/zca-js-tong-hop.md §7.4; code zca-js v2.3.13
(src/call-engine/ZaloRtcSession.ts: acceptIncomingCall ~2110,
rejectIncomingCall ~2250, parseIncomingCallEvent ~582;
src/apis/call/answerVoiceCall.ts, ringRingVoiceCall.ts,
cancelVoiceCall.ts, endVoiceCall.ts).

Dinh chinh theo code (bao cao §7.4 buoc 4 chua dung): 11304 answerack
la tin hieu cua CALLER (ack lai cau tra loi cua callee), callee
KHONG gui 11304 — mock server_call_state + zca-js deu xac nhan.
Tu choi 1-1 gui CA cancel (11305) VA endcall (11306), khong chi
11306 nhu bao cao ghi (rejectIncomingCall, zca-js, best-effort ca
hai). 11303 answer cua callee KHONG co imei (answerVoiceCall.ts:
params chi co callerId/callId/status/codec/rtcpAddress/rtpAddress/
session_id + extendData/subCommand=3) — mock phai co nhanh rieng,
vi fallthrough chung doi imei/toId/groupId.

Cuoc goi den duoc danh dau "incoming" trong CallLog (trang thai
live moi), nhan duoc qua POST /api/call/answer (11300 fallback lay
allocation moi + 11303, KHONG gui 11301 — do la tin hieu cua caller)
va tu choi qua POST /api/call/reject (11305 + 11306).

Mock/offline hoan toan: khong dang nhap that, khong gui that.
Khong log noi dung tin — chi id thread/cuoc goi dang test.
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from test_call_11301 import (  # noqa: E402
    _api, _fake_endpoints, _login, _start_app, FAKE_TOKEN)
from test_call_ringing import _run, _start_call  # noqa: E402
from test_media_provider import REAL_SHAPE_SERVERS  # noqa: E402
from zalo_pc_app import call_log as call_log_mod  # noqa: E402
from zalo_pc_app import ctrl_poll as ctrl_mod  # noqa: E402
from zalo_pc_app import media_endpoints  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import webhooks as webhooks_mod  # noqa: E402

UID = "10001"
CALLER_ID = "20001"
CALL_ID_IN = 1763201001
CALL_ID_IN2 = 1763201002
CALL_ID_OUT = 1763201003
CALL_ID_NONE = 1763201999

INCOMING_EVENT = {
    "act": "request",
    "callId": CALL_ID_IN,
    "uidN": CALLER_ID,
    "callerName": "BenBap",
    "session": "sess-incoming-1",
    "codec": media_endpoints.DEFAULT_ZALO_AUDIO_CODEC,
    "rtpAddress": "10.0.0.1:4200",
    "rtcpAddress": "10.0.0.1:4201",
    "extendData": {"callType": 0},
}


def _voip_control(data, act_type="voip"):
    return {"controlId": "c-voip",
            "content": {"act_type": act_type, "data": data}}


def _payload(*controls):
    return {"controls": list(controls)}


def _ctrl_payload_with_call(data):
    return {"controls": [_voip_control(data)],
            "reactions": [],
            "lastActionId": "88",
            "lastActionIdOther": "60",
            "queueStatus": {}}


def _parsed_event(data):
    """Event da parse qua extract_call_events — dung dang ma
    _on_ctrl_call_event nhan tu CtrlPoller."""
    got = ctrl_mod.extract_call_events(_payload(_voip_control(data)))
    assert len(got) == 1, got
    return got[0]


def _wait_steps(mock, call_id, wanted, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        steps = mock.voice_call_state(call_id)["steps"]
        if all(w in steps for w in wanted):
            return steps
        time.sleep(0.05)
    return mock.voice_call_state(call_id)["steps"]


def _wait_active(base, call_id, status, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _s, calls = _api(base, "GET", "/api/calls")
        active = calls.get("active")
        if (active is not None
                and str(active["call_id"]) == str(call_id)
                and active["status"] == status):
            return active
        time.sleep(0.05)
    _s, calls = _api(base, "GET", "/api/calls")
    return calls.get("active")


# ------------------------------------------------------------------
# 1. Trich event (ctrl_poll.extract_call_events)
# ------------------------------------------------------------------

def test_extract_call_events():
    """Event request dang dict doc duoc: call_id so, caller, session,
    codec, dia chi rtp/rtcp, callType 0 (thoai)."""
    got = ctrl_mod.extract_call_events(
        _payload(_voip_control(dict(INCOMING_EVENT))))
    assert len(got) == 1, got
    ev = got[0]
    assert ev["act"] == "request", ev
    assert ev["call_id"] == CALL_ID_IN, ev
    assert ev["caller_id"] == CALLER_ID, ev
    assert ev["caller_name"] == "BenBap", ev
    assert ev["session"] == "sess-incoming-1", ev
    assert ev["codec"] == media_endpoints.DEFAULT_ZALO_AUDIO_CODEC, ev
    assert ev["rtp_address"] == "10.0.0.1:4200", ev
    assert ev["rtcp_address"] == "10.0.0.1:4201", ev
    assert ev["call_type"] == 0 and ev["is_video"] is False, ev


def test_extract_call_events_nested_params_and_string():
    """params long nhau (dict hoac chuoi JSON) + data dang chuoi JSON
    deu doc duoc — hinh parseIncomingCallEvent cua zca-js."""
    nested = _payload(_voip_control({
        "act": "request",
        "params": json.dumps({
            "callId": CALL_ID_IN2, "uidN": CALLER_ID,
            "session": "sess-nested",
            "extendData": json.dumps({"callType": 1})})}))
    got = ctrl_mod.extract_call_events(nested)
    assert len(got) == 1, got
    assert got[0]["call_id"] == CALL_ID_IN2, got
    assert got[0]["session"] == "sess-nested", got
    assert got[0]["call_type"] == 1 and got[0]["is_video"] is True, got
    string_data = _payload(_voip_control(json.dumps(dict(INCOMING_EVENT))))
    got = ctrl_mod.extract_call_events(string_data)
    assert len(got) == 1 and got[0]["call_id"] == CALL_ID_IN, got


def test_extract_call_events_skips_bad():
    """Bo qua: act_type khac voip, thieu act, thieu call_id,
    request thieu caller, trung event trong cung batch."""
    assert ctrl_mod.extract_call_events(
        _payload(_voip_control(dict(INCOMING_EVENT),
                               act_type="group"))) == []
    no_act = dict(INCOMING_EVENT)
    del no_act["act"]
    assert ctrl_mod.extract_call_events(
        _payload(_voip_control(no_act))) == []
    no_id = dict(INCOMING_EVENT)
    del no_id["callId"]
    assert ctrl_mod.extract_call_events(
        _payload(_voip_control(no_id))) == []
    no_caller = dict(INCOMING_EVENT)
    del no_caller["uidN"]
    assert ctrl_mod.extract_call_events(
        _payload(_voip_control(no_caller))) == []
    dup = {"controls": [
        _voip_control(dict(INCOMING_EVENT)),
        _voip_control(dict(INCOMING_EVENT))]}
    assert len(ctrl_mod.extract_call_events(dup)) == 1
    # act khac (cancel/end/answer) van trich duoc — chi can call_id.
    cancel = {"act": "cancel", "callId": CALL_ID_IN}
    got = ctrl_mod.extract_call_events(_payload(_voip_control(cancel)))
    assert len(got) == 1 and got[0]["act"] == "cancel", got


# ------------------------------------------------------------------
# 2. CtrlPoller dispatch qua on_call_event
# ------------------------------------------------------------------

def test_ctrl_poller_dispatches_call_event():
    """Mot batch ctrl co event voip: di qua on_call_event, con tro
    van tien (giong test_ctrl_poller_dispatches_group_reaction...)."""
    mock = MockZalo()
    registry = ctrl_mod.VoiceAsyncRegistry()
    calls = []
    saved = []

    def http_get(url, timeout=30):
        return 200, mock._postlogin_envelope(
            _ctrl_payload_with_call(dict(INCOMING_EVENT)))

    poller = ctrl_mod.CtrlPoller(
        http_get, ["https://poll.invalid/lp-ctl"], TEST_SESSION_KEY,
        UID, registry, ctl_timeout=30,
        on_call_event=lambda e: calls.append(e),
        on_cursor=lambda c: saved.append(c.to_dict()))
    assert poller.poll_once() == "ok"
    assert len(calls) == 1, calls
    assert calls[0]["act"] == "request", calls
    assert calls[0]["call_id"] == CALL_ID_IN, calls
    assert calls[0]["caller_id"] == CALLER_ID, calls
    assert poller.last_batch["call_events"] == 1, poller.last_batch
    assert poller.cursor.last_action_id == "88"
    assert len(saved) == 1 and saved[0]["lastActionId"] == "88"


def test_ctrl_poller_call_event_callback_error_does_not_kill_poll():
    """Callback call_event loi van khong lam chet poller; con tro
    van tien."""
    mock = MockZalo()
    registry = ctrl_mod.VoiceAsyncRegistry()

    def bad_call(event):
        raise RuntimeError("callback loi gia")

    def http_get(url, timeout=30):
        return 200, mock._postlogin_envelope(
            _ctrl_payload_with_call(dict(INCOMING_EVENT)))

    poller = ctrl_mod.CtrlPoller(
        http_get, ["https://poll.invalid/lp-ctl"], TEST_SESSION_KEY,
        UID, registry, ctl_timeout=30, on_call_event=bad_call)
    assert poller.poll_once() == "ok"
    assert poller.cursor.last_action_id == "88"


# ------------------------------------------------------------------
# 3. CallLog: trang thai "incoming"
# ------------------------------------------------------------------

def test_call_log_incoming_is_live_and_supersedes():
    """record_incoming: trang thai live moi "incoming", thay the
    cuoc live truoc (giong record_start), record_answered mo cho
    "incoming" -> "answered", record_end nhan "incoming"."""
    log = call_log_mod.CallLog()
    old = log.record_start(111, "Peer", "20001", "user")
    assert old["status"] == "sent", old
    incoming = log.record_incoming(CALL_ID_IN, "BenBap", CALLER_ID,
                                   "user")
    assert incoming["status"] == "incoming", incoming
    snap = log.snapshot()
    assert snap["active"]["call_id"] == str(CALL_ID_IN), snap
    assert snap["active"]["status"] == "incoming", snap
    ended_old = [c for c in snap["calls"] if c["call_id"] == "111"][0]
    assert ended_old["status"] == "ended", ended_old
    assert ended_old["detail"] == "superseded_by_new_call", ended_old
    answered = log.record_answered(CALL_ID_IN, "api")
    assert answered is not None and answered["status"] == "answered", \
        answered
    ended = log.record_end(CALL_ID_IN, "peer_ended")
    assert ended is not None and ended["status"] == "ended", ended


# ------------------------------------------------------------------
# 4. Server: _on_ctrl_call_event
# ------------------------------------------------------------------

def _capture_call_webhooks(state):
    sent = []
    state.webhook_store.save(
        {"call_webhook_url": "https://hook.invalid/call"})
    state.webhook_dispatcher = webhooks_mod.WebhookDispatcher(
        state.webhook_store,
        post_fn=lambda url, p: sent.append(p) or 200)
    return sent


def test_server_ctrl_call_event_request_creates_incoming_and_rings():
    """Event request -> entry "incoming" + 11302 ringring gui toi
    mock + webhook call.incoming."""
    mock = MockZalo().start()

    def check(base, mock, endpoints):
        state = app_server.STATE
        sent = _capture_call_webhooks(state)
        state._on_ctrl_call_event(_parsed_event(dict(INCOMING_EVENT)))
        active = _wait_active(base, CALL_ID_IN, "incoming")
        assert active is not None, "no incoming entry"
        assert active["thread_id"] == CALLER_ID, active
        assert active["peer"] == "BenBap", active
        steps = _wait_steps(mock, CALL_ID_IN, ["ringring"])
        assert "ringring" in steps, steps
        deadline = time.time() + 5
        while time.time() < deadline and len(sent) < 1:
            time.sleep(0.05)
        assert len(sent) == 1, sent
        assert sent[0]["type"] == "call.incoming", sent
        assert sent[0]["call_id"] == str(CALL_ID_IN), sent
        assert sent[0]["thread_id"] == CALLER_ID, sent

    _run(mock, check)


def test_server_ctrl_call_event_cancel_marks_missed():
    """Event cancel cho cuoc incoming chua tra loi -> ended, detail
    "missed" (cuoc goi nho), webhook call.ended."""
    mock = MockZalo().start()

    def check(base, mock, endpoints):
        state = app_server.STATE
        sent = _capture_call_webhooks(state)
        state._on_ctrl_call_event(_parsed_event(dict(INCOMING_EVENT)))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        state._on_ctrl_call_event(_parsed_event(
            {"act": "cancel", "callId": CALL_ID_IN,
             "uidN": CALLER_ID}))
        _s, calls = _api(base, "GET", "/api/calls")
        assert calls.get("active") is None, calls
        ended = [c for c in calls["calls"]
                 if str(c["call_id"]) == str(CALL_ID_IN)][0]
        assert ended["status"] == "ended", ended
        assert ended["detail"] == "missed", ended
        deadline = time.time() + 5
        while time.time() < deadline and len(sent) < 2:
            time.sleep(0.05)
        ended_hooks = [p for p in sent
                       if p["type"] == "call.ended"]
        assert len(ended_hooks) == 1, sent

    _run(mock, check)


def test_server_ctrl_call_event_underscore_names_are_recognised():
    """Zalo gui ten su kien co dau gach duoi ("end_call", "cancel_call",
    "ring_ring", "answer_ack"). Truoc 09/11 app chi biet "end"/"endcall"/
    "cancel" nen bo qua ("ignored") khi ben goi cup may: cuoc goi den ket
    thuc ma app van coi la dang do, va khong bat duoc tu choi/khong nghe."""
    for act in ("end_call", "cancel_call", "endCall"):
        mock = MockZalo().start()

        def check(base, mock, endpoints, act=act):
            state = app_server.STATE
            state._on_ctrl_call_event(_parsed_event(dict(INCOMING_EVENT)))
            assert _wait_active(base, CALL_ID_IN, "incoming") is not None
            state._on_ctrl_call_event(_parsed_event(
                {"act": act, "callId": CALL_ID_IN, "uidN": CALLER_ID}))
            _s, calls = _api(base, "GET", "/api/calls")
            assert calls.get("active") is None, (act, calls)
            ended = [c for c in calls["calls"]
                     if str(c["call_id"]) == str(CALL_ID_IN)][0]
            assert ended["status"] == "ended", (act, ended)
            assert ended["detail"] == "missed", (act, ended)

        _run(mock, check)


def test_server_incoming_event_remembers_callers_relay():
    """Su kien cuoc goi den mang relay cua BEN GOI; app giu lai de luc nghe
    may noi vao dung relay do (zca-js acceptIncomingCall), thay vi relay cua
    11300 moi."""
    mock = MockZalo().start()

    def check(base, mock, endpoints):
        state = app_server.STATE
        app_server._INCOMING_RELAY.clear()
        state._on_ctrl_call_event(_parsed_event(dict(INCOMING_EVENT)))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        got = app_server._INCOMING_RELAY.get(str(CALL_ID_IN))
        assert got == ("10.0.0.1:4200", "10.0.0.1:4201"), got

    _run(mock, check)


def test_server_ctrl_call_event_answer_marks_outgoing_answered():
    """Event answer cho cuoc goi DI "sent" -> _mark_answered nguon
    "sync" (gui answerack 11304 — day la phia caller, dung cho
    goi di)."""
    mock = MockZalo().start()

    def check(base, mock, endpoints):
        eff_id = _start_call(base, CALLER_ID, CALL_ID_OUT)
        state = app_server.STATE
        state._on_ctrl_call_event(_parsed_event(
            {"act": "answer", "callId": eff_id, "uidN": CALLER_ID}))
        active = _wait_active(base, eff_id, "answered")
        assert active is not None, "outgoing not answered"
        assert active.get("answer_source") == "sync", active
        steps = _wait_steps(mock, eff_id, ["answerack"])
        assert "answerack" in steps, steps

    _run(mock, check)


# ------------------------------------------------------------------
# 5. POST /api/call/answer + /api/call/reject (e2e)
# ------------------------------------------------------------------

def _inject_incoming(base, mock):
    state = app_server.STATE
    state._on_ctrl_call_event(_parsed_event(dict(INCOMING_EVENT)))
    active = _wait_active(base, CALL_ID_IN, "incoming")
    assert active is not None, "no incoming entry to answer/reject"
    _wait_steps(mock, CALL_ID_IN, ["ringring"])


def _answer_extend_for_offer(offer_ext, session=None):
    """Gọi đến với extendData bên gọi khai = offer_ext, nghe máy, trả extendData bot gửi trong câu trả lời (dict)."""
    mock = MockZalo().start()
    mock.requestcall_data = {"servers": REAL_SHAPE_SERVERS, "sessId": "sess-real-e2e", "srtpKey": "k-test", "token": FAKE_TOKEN}
    out = {}

    def check(base, mock, endpoints):
        ev = dict(INCOMING_EVENT)
        ev["extendData"] = offer_ext
        if session:
            ev["session"] = session
        app_server.STATE._on_ctrl_call_event(_parsed_event(ev))
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        _wait_steps(mock, CALL_ID_IN, ["ringring"])
        status, body = _api(base, "POST", "/api/call/answer", {"call_id": CALL_ID_IN})
        assert body["ok"] is True, body
        ext = mock.voice_call_state(CALL_ID_IN).get("answer_extend")
        out["ext"] = json.loads(ext) if isinstance(ext, str) else ext
        cfg = media_endpoints.ENDPOINTS.active_record(CALL_ID_IN)["transport"].config
        out["is_caller"], out["counter"] = cfg.is_caller, cfg.call_counter
        out["token"] = cfg.token

    old = os.environ.get("ZALO_PC_P2P_HOSTS")
    os.environ["ZALO_PC_P2P_HOSTS"] = "192.0.2.50"
    try:
        _run(mock, check)
    finally:
        if old is None:
            os.environ.pop("ZALO_PC_P2P_HOSTS", None)
        else:
            os.environ["ZALO_PC_P2P_HOSTS"] = old
    _answer_extend_for_offer.last = out
    return out["ext"]


def test_answer_declares_p2p_only_when_this_phone_offers_it_and_follows_its_srtp_mode():
    """Mỗi điện thoại khai khác nhau: khai sP2P 1 kèm ứng viên thì bot khai ứng viên của mình + sP2P 1, select2side 1, numServers 0,
    supportCallBusy 0 (như engine zcall-native); khai sP2P 0 / không có ứng viên thì relay thuần; srtpMode 0 thì trả lời srtpMode 0."""
    cand = [{"ip": "172.16.10.16", "port": 46518, "type": 0}, {"ip": "42.114.42.252", "port": 46518, "type": 1}]
    ext = _answer_extend_for_offer({"callType": 0, "sP2P": 1, "p2p": cand, "srtpMode": 1, "negoVidQual": 1})
    # NGHE MÁY phải đăng ký với relay là bên NGHE MÁY (lệnh InitZRTP 12, vai P2P 1), không phải bên gọi (11): relay không nối được hai «bên gọi»
    # nên điện thoại không nhận được gì và tự cúp sau 15 giây (đo bằng bắt gói 11/11/2026).
    assert _answer_extend_for_offer.last["is_caller"] is True and _answer_extend_for_offer.last["counter"] == 11, _answer_extend_for_offer.last   # tạm: bên nghe máy (12) làm relay không trả lời
    assert ext["sP2P"] == 1 and ext["select2side"] == 1 and ext["numServers"] == 0 and ext["supportCallBusy"] == 0, ext
    assert ext["p2p"] and ext["p2p"][0]["ip"] == "192.0.2.50" and ext["p2p"][0]["type"] == 0 and ext["p2p"][0]["port"] > 0, ext
    assert ext["srtpMode"] == 1 and ext["negoVidQual"] == 1, ext                       # cờ thương lượng bên gọi khai được lặp lại
    off = _answer_extend_for_offer({"callType": 0, "sP2P": 0, "p2p": [], "srtpMode": 0})
    assert off["sP2P"] == 0 and off["p2p"] == [] and "select2side" not in off and off["srtpMode"] == 0, off
    nocand = _answer_extend_for_offer({"callType": 0, "sP2P": 1, "p2p": [], "srtpMode": 1})
    assert nocand["sP2P"] == 0 and nocand["p2p"] == [], nocand



def test_answer_registers_as_callee_with_the_callers_session_when_the_offer_has_a_full_session():
    """Bên nghe máy của engine thật: InitZRTP lệnh 12 + sessId = phiên của BÊN GỌI (154 ký tự trong tin). Tin không có phiên đủ dài thì giữ vai
    cũ (lệnh 11) để vẫn nghe máy được."""
    import base64
    sess = base64.urlsafe_b64encode(bytes(range(115))).rstrip(b"=").decode()          # 154 ký tự hợp lệ như sessId thật
    _answer_extend_for_offer({"callType": 0, "srtpMode": 1}, session=sess)
    got = _answer_extend_for_offer.last
    assert got["is_caller"] is False and got["counter"] == 12, got
    tok = got["token"]
    assert (tok.decode() if isinstance(tok, bytes) else tok) == sess, got
    _answer_extend_for_offer({"callType": 0, "srtpMode": 1}, session="ngan")
    got = _answer_extend_for_offer.last
    assert got["is_caller"] is True and got["counter"] == 11, got            # phiên không đủ 154 ký tự: nhánh cũ

def test_answer_incoming_e2e():
    """POST /api/call/answer cho cuoc incoming: 11300 fallback (cung
    callId, partner = caller) + 11303 answer voi codec list JSON;
    KHONG gui 11301 (tin hieu cua caller) va KHONG gui 11304
    answerack (tin hieu cua caller); entry -> "answered"."""
    mock = MockZalo().start()
    mock.requestcall_data = {
        "servers": REAL_SHAPE_SERVERS, "sessId": "sess-real-e2e",
        "srtpKey": "k-test", "token": FAKE_TOKEN}

    def check(base, mock, endpoints):
        _inject_incoming(base, mock)
        status, body = _api(base, "POST", "/api/call/answer",
                            {"call_id": CALL_ID_IN})
        assert body["ok"] is True, body
        assert body["status"] == "answered", body
        assert body["call_id"] == CALL_ID_IN, body
        state = mock.voice_call_state(CALL_ID_IN)
        steps = state["steps"]
        assert "requestcall" in steps, steps
        assert "answer" in steps, steps
        assert "request" not in steps, steps
        assert "answerack" not in steps, steps
        assert state.get("answer_codec") == \
            media_endpoints.DEFAULT_ZALO_AUDIO_CODEC, state
        # Nghe máy phải khai extendData kiểu «native» như cuộc gọi đi (newZrtc 1, platform 2, có codec video h264). Hồ sơ «pc» cũ
        # (newZrtc 0, platform 3) làm điện thoại coi ta là bản cũ: «kết nối không ổn định», «chưa hỗ trợ chuyển video» (đo 11/11/2026).
        ext = state.get("answer_extend")
        ext = json.loads(ext) if isinstance(ext, str) else ext
        assert ext and ext["newZrtc"] == 1 and ext["platform"] == 2 and ext["video"]["codec"][0]["name"] == "h264", ext
        active = _wait_active(base, CALL_ID_IN, "answered")
        assert active is not None, "incoming not answered"

    _run(mock, check)


def test_reject_incoming_e2e():
    """POST /api/call/reject cho cuoc incoming: gui CA cancel (11305)
    VA endcall (11306) — theo zca-js rejectIncomingCall; entry ket
    thuc voi detail "user_rejected"."""
    mock = MockZalo().start()

    def check(base, mock, endpoints):
        _inject_incoming(base, mock)
        status, body = _api(base, "POST", "/api/call/reject",
                            {"call_id": CALL_ID_IN})
        assert body["ok"] is True, body
        assert body["ended_call_id"] == CALL_ID_IN, body
        steps = _wait_steps(mock, CALL_ID_IN, ["cancel", "endcall"])
        assert "cancel" in steps, steps
        assert "endcall" in steps, steps
        _s, calls = _api(base, "GET", "/api/calls")
        assert calls.get("active") is None, calls
        ended = [c for c in calls["calls"]
                 if str(c["call_id"]) == str(CALL_ID_IN)][0]
        assert ended["status"] == "ended", ended
        assert ended["detail"] == "user_rejected", ended

    _run(mock, check)


def test_answer_and_reject_without_incoming_error():
    """Answer/reject khi khong co cuoc incoming nao -> loi ro
    "no_incoming_call", khong gui tin hieu nao."""
    mock = MockZalo().start()

    def check(base, mock, endpoints):
        status, body = _api(base, "POST", "/api/call/answer",
                            {"call_id": CALL_ID_NONE})
        assert body["ok"] is False, body
        assert body["error"] == "no_incoming_call", body
        status, body = _api(base, "POST", "/api/call/reject",
                            {"call_id": CALL_ID_NONE})
        assert body["ok"] is False, body
        assert body["error"] == "no_incoming_call", body
        assert mock.voice_call_state(CALL_ID_NONE)["steps"] == [], \
            mock.voice_call_state(CALL_ID_NONE)

    _run(mock, check)

def test_offer_extend_reads_the_caller_offer_whether_layers_are_dicts_or_json_strings():
    """Mỗi điện thoại/phiên bản Zalo có thể lồng data/params/extendData bằng dict hoặc chuỗi JSON: đọc được cả hai, thiếu thì {}."""
    ext = {"srtpMode": 1, "negoVidQual": 1, "sP2P": 1}
    as_dict = {"data": {"params": {"extendData": ext}}}
    as_str = {"data": json.dumps({"params": json.dumps({"extendData": json.dumps(ext)})})}
    top = {"data": {"extendData": ext}}
    for ev in (as_dict, as_str, top):
        assert app_server._offer_extend(ev) == ext, ev
    for ev in ({}, {"data": None}, {"data": "không phải json"}, {"data": {"params": "x"}}):
        assert app_server._offer_extend(ev) == {}, ev



if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("ALL INCOMING-CALL TESTS PASSED")
