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
