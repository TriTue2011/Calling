"""Tu nghe may cuoc goi 1-1 DEN (`auto_answer`): chi khi bat + nguoi goi nam trong `auto_answer_from` + sau bo dem
`auto_answer_delay`, va cuoc goi con "incoming" luc het gio.

Mock/offline hoan toan (mock Zalo), dung khuon test_call_incoming_zca. Khong log noi dung."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from test_call_11301 import _api, FAKE_TOKEN  # noqa: E402
from test_call_incoming_zca import (CALL_ID_IN, CALLER_ID, INCOMING_EVENT, _parsed_event, _wait_active,  # noqa: E402
                                    _wait_steps)
from test_call_ringing import _run  # noqa: E402
from test_media_provider import REAL_SHAPE_SERVERS  # noqa: E402
from zalo_pc_app import devices as devices_mod  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def _mock():
    mock = MockZalo().start()
    mock.requestcall_data = {"servers": REAL_SHAPE_SERVERS, "sessId": "sess-auto", "srtpKey": "k-test", "token": FAKE_TOKEN}
    return mock


def _set(base, **cfg):
    st, body = _api(base, "POST", "/api/settings/devices", cfg)
    assert st == 200 and body.get("ok"), body


def _ring(base, mock):
    app_server.STATE._on_ctrl_call_event(_parsed_event(dict(INCOMING_EVENT)))
    assert _wait_active(base, CALL_ID_IN, "incoming") is not None
    _wait_steps(mock, CALL_ID_IN, ["ringring"])


def _status(mock):
    return mock.voice_call_state(CALL_ID_IN)["steps"]


def test_parse_id_list_and_settings_validation():
    assert devices_mod.parse_id_list(" 123, 456;789\n") == ["123", "456", "789"]
    assert devices_mod.parse_id_list("") == [] and devices_mod.parse_id_list(None) == []
    for bad in ("abc", "123,x", "12 34"):
        try:
            devices_mod.parse_id_list(bad)
        except ValueError:
            continue
        raise AssertionError("phai tu choi: %r" % bad)
    d = devices_mod.DEFAULTS
    assert d["auto_answer"] is False and d["auto_answer_from"] == ""      # mac dinh: tat, khong ai


def test_enabled_and_listed_answers_after_delay():
    mock = _mock()

    def check(base, mock, endpoints):
        _set(base, auto_answer=True, auto_answer_delay=1, auto_answer_from=CALLER_ID + ",999")
        _ring(base, mock)
        time.sleep(0.4)
        assert "answer" not in _status(mock), "chua toi han ma da nghe may"
        assert _wait_active(base, CALL_ID_IN, "incoming") is not None
        assert _wait_active(base, CALL_ID_IN, "answered", timeout=6.0) is not None, "khong tu nghe may"
        steps = _status(mock)
        assert "answer" in steps and "request" not in steps and "answerack" not in steps, steps
        c = [x for x in _api(base, "GET", "/api/calls")[1]["calls"] if str(x["call_id"]) == str(CALL_ID_IN)][0]
        assert c["answer_source"] == "auto", c                  # de HA phan biet voi nguoi that nghe may (answer_source "api")

    _run(mock, check)


def test_not_listed_empty_list_or_disabled_never_answers():
    for cfg in ({"auto_answer": True, "auto_answer_delay": 0, "auto_answer_from": "999"},      # khong nam trong danh sach
                {"auto_answer": True, "auto_answer_delay": 0, "auto_answer_from": ""},         # danh sach trong = khong ai
                {"auto_answer": False, "auto_answer_delay": 0, "auto_answer_from": CALLER_ID}):  # tat
        mock = _mock()

        def check(base, mock, endpoints, cfg=cfg):
            _set(base, **cfg)
            _ring(base, mock)
            time.sleep(1.2)
            assert "answer" not in _status(mock), (cfg, _status(mock))
            assert _wait_active(base, CALL_ID_IN, "incoming") is not None, cfg

        _run(mock, check)


def test_caller_hangs_up_before_delay_no_answer():
    mock = _mock()

    def check(base, mock, endpoints):
        _set(base, auto_answer=True, auto_answer_delay=1, auto_answer_from=CALLER_ID)
        _ring(base, mock)
        app_server.STATE._on_ctrl_call_event(_parsed_event({"act": "cancel", "callId": CALL_ID_IN, "uidN": CALLER_ID}))
        time.sleep(1.6)
        steps = _status(mock)
        assert "answer" not in steps and "requestcall" not in steps, steps       # khong nghe may mot cuoc da cup

    _run(mock, check)


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("ALL AUTO-ANSWER TESTS PASSED")
