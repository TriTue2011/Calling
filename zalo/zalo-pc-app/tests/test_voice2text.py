"""Zalo AI voice-to-text (zca-js voiceToText 13394): ket qua async qua ctrl."""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import ctrl_poll, server, voice2text, webhooks  # noqa: E402


def _payload(data, act_type="voice2text"):
    return {"controls": [{"controlId": "c1",
                          "content": {"act_type": act_type, "data": data}}]}


def test_extract_from_json_string_and_dict():
    ev = ctrl_poll.extract_voice2text_events(
        _payload(json.dumps({"req_id": "R1", "text": "xin chao"})))
    assert ev == [{"req_id": "R1", "text": "xin chao", "error": None}], ev
    ev = ctrl_poll.extract_voice2text_events(
        _payload({"req_id": 7, "content": "alo", "err": 0}))
    assert ev == [{"req_id": "7", "text": "alo", "error": None}], ev


def test_extract_reports_error_and_skips_other_or_bad_controls():
    ev = ctrl_poll.extract_voice2text_events(
        _payload({"req_id": "E", "err": 123}))
    assert ev[0]["error"] == 123 and ev[0]["text"] == "", ev
    assert ctrl_poll.extract_voice2text_events(_payload({"req_id": "x"}, "voip")) == []
    assert ctrl_poll.extract_voice2text_events(_payload("khong phai json")) == []
    assert ctrl_poll.extract_voice2text_events(_payload({"text": "thieu req_id"})) == []
    assert ctrl_poll.extract_voice2text_events({}) == []
    assert ctrl_poll.extract_voice2text_events(None) == []


def test_store_wait_returns_when_result_arrives_and_times_out_otherwise():
    st = voice2text.V2TStore()
    assert st.wait("none", 0.05) is None
    t = threading.Timer(0.1, lambda: st.put("A", "ket qua"))
    t.start()
    t0 = time.monotonic()
    got = st.wait("A", 3)
    assert got and got["text"] == "ket qua", got
    assert time.monotonic() - t0 < 2.0, "phai tra ngay khi co ket qua, khong cho het han"
    assert st.get("A")["text"] == "ket qua"


def test_store_is_bounded():
    st = voice2text.V2TStore()
    for i in range(voice2text.MAX_ENTRIES + 20):
        st.put(str(i), "x")
    assert st.get("0") is None
    assert st.get(str(voice2text.MAX_ENTRIES + 19)) is not None


def test_webhook_event_shape_and_dispatch_uses_message_url():
    ev = {"req_id": "R", "text": "tin", "error": None}
    out = webhooks.build_voice2text_event(ev, "acc1")
    assert out["event"] == "voice2text" and out["type"] == "voice2text.result"
    assert out["req_id"] == "R" and out["text"] == "tin" and out["account_id"] == "acc1"

    class D:
        def dispatch(self, kind, payload):
            self.got = (kind, payload)
            return True
    d = D()
    assert webhooks.dispatch_voice2text(d, ev, "acc1") is True
    assert d.got[0] == "message" and d.got[1]["event"] == "voice2text"
    assert webhooks.dispatch_voice2text(None, ev, "a") is False


def test_find_req_id_in_nested_response():
    assert server._find_req_id({"req_id": "Z"}) == "Z"
    assert server._find_req_id({"data": {"x": {"req_id": 5}}}) == "5"
    assert server._find_req_id({"a": 1}) == ""
    assert server._find_req_id(None) == ""


if __name__ == "__main__":
    for _n, _f in list(globals().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
            print("PASS", _n)
    print("ALL VOICE2TEXT TESTS PASSED")
