"""Tham so dich Zalo AI (translateMessage / translateMessageSuggest) dung nhu ban fork @softtynet/zca-js gui."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from zalo_pc_app import zca_api  # noqa: E402


def _entry(name):
    return zca_api.registry()[name]


def test_translate_message_params_match_the_fork():
    e = _entry("translateMessage")
    p = zca_api.build_params(e, {"reqId": "pcw_1", "msgId": "8474", "threadId": "6643", "type": "user", "srcLang": "vi",
                                 "desLang": "en", "text": "Xin chào"}, {})
    assert p == {"reqId": "pcw_1", "msgId": "8474", "threadId": "6643", "type": 0, "srcLang": "vi", "desLang": "en",
                 "msg": {"text": "Xin chào", "metadata": {"immutableItems": []}}}, p
    assert list(p) == ["reqId", "msgId", "threadId", "type", "srcLang", "desLang", "msg"], "thu tu khoa nhu ban fork"


def test_translate_defaults_group_type_and_generated_req_id():
    e = _entry("translateMessage")
    p = zca_api.build_params(e, {"msgId": "1", "threadId": "2", "type": "group", "srcLang": "vi", "desLang": "en", "text": "x"}, {})
    assert p["type"] == 1 and p["reqId"].startswith("pcw_") and p["reqId"][4:].isdigit(), p
    assert zca_api.build_params(e, {"msgId": "1", "threadId": "2", "srcLang": "vi", "desLang": "en", "text": "x"}, {})["type"] == 0


def test_suggest_has_no_msg_id():
    p = zca_api.build_params(_entry("translateMessageSuggest"), {"threadId": "2", "srcLang": "vi", "desLang": "en", "text": "x"}, {})
    assert "msgId" not in p and p["msg"]["text"] == "x", p


def test_missing_and_bad_inputs_are_refused_before_any_call():
    e = _entry("translateMessage")
    for inp in ({"threadId": "2", "srcLang": "vi", "desLang": "en", "text": "x"},                      # thiếu msgId
                {"msgId": "1", "threadId": "2", "srcLang": "vi", "desLang": "en", "text": ""},
                {"msgId": "1", "threadId": "2", "srcLang": "vi", "desLang": "en", "text": "x", "type": "9"},
                {"msgId": "1", "threadId": "2", "srcLang": "vi", "desLang": "en", "text": "x", "immutableItems": "{}"}):
        try:
            zca_api.build_params(e, inp, {})
            raise AssertionError("phai loi: %r" % (inp,))
        except zca_api.ZcaError:
            pass


def test_explicit_params_still_win_and_auto_batch_still_needs_params():
    e = _entry("translateMessage")
    raw = {"reqId": "r", "anything": 1}
    assert zca_api.build_params(e, {"params": raw}, {}) == raw
    try:
        zca_api.build_params(_entry("translateMessageAuto"), {"threadId": "2"}, {})
        raise AssertionError("Auto la lo nhieu tin: phai truyen params")
    except zca_api.ZcaError as ex:
        assert "params" in str(ex)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL ZCA TRANSLATE TESTS PASSED")
