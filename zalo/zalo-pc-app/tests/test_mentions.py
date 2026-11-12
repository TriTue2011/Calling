"""Mention trong tin nhom nhu Zalo PC (/api/group/mention): vi tri theo UTF-16, @Tat ca, tim theo @ten, bao loi ro.

Chay: python3 tests/test_mentions.py (kieu CI cua repo: khoi __main__ in PASSED, khong dung pytest).
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mock_server import TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app.crypto import session_aes_decrypt  # noqa: E402


def test_build_mentions_positions_types_and_errors():
    msg = "Chào @Nam và @All nhé"
    rows = chat_mod.build_mentions(msg, [{"uid": "111", "name": "Nam"}, {"uid": "-1"}])
    assert rows == [{"pos": 5, "uid": "111", "len": 4, "type": 0}, {"pos": 13, "uid": "-1", "len": 4, "type": 1}], rows
    # vi tri tinh theo UTF-16: emoji ngoai BMP chiem 2 don vi
    rows = chat_mod.build_mentions("😀 @Nam", [{"uid": "5", "name": "Nam"}])
    assert rows == [{"pos": 3, "uid": "5", "len": 4, "type": 0}], rows
    # pos + len ro rang duoc giu nguyen
    assert chat_mod.build_mentions("abc def", [{"uid": "7", "pos": 4, "len": 3}])[0]["pos"] == 4
    assert chat_mod.build_mentions("abc", None) == [] and chat_mod.build_mentions("abc", []) == []
    for bad in ([{"uid": "1", "name": "Khong"}], [{"uid": "", "name": "Nam"}], [{"uid": "1", "pos": 2, "len": 9}], [{"uid": "1"}], "x"):
        try:
            chat_mod.build_mentions("Chào @Nam", bad)
            raise AssertionError("phai nem ValueError: %r" % (bad,))
        except ValueError:
            pass


def _chat(captured_post, captured_get):
    def http_post(url, form, timeout=30):
        params = urllib.parse.unquote(form.split("=", 1)[1])
        captured_post.append((url, json.loads(session_aes_decrypt(TEST_SESSION_KEY, params))))
        return 200, {"error_code": 0, "data": ""}

    def http_get(url, timeout=30):
        captured_get.append(url)
        return 200, {"error_code": 0, "data": ""}
    return chat_mod.Chat(http_get, "IMEI-1", TEST_SESSION_KEY, http_post=http_post)


def test_group_text_with_mention_goes_to_mention_endpoint_and_others_unchanged():
    posts, gets = [], []
    c = _chat(posts, gets)
    res = c.send_text("group", "777", "Chào @Nam", mentions=[{"uid": "111", "name": "Nam"}])
    (url, body), = posts
    assert "/api/group/mention" in url and not gets, (url, gets)
    assert body["grid"] == "777" and body["message"] == "Chào @Nam" and "imei" not in body, body
    assert json.loads(body["mentionInfo"]) == [{"pos": 5, "uid": "111", "len": 4, "type": 0}], body
    assert isinstance(body["clientId"], int) and body["clientId"] == res["client_id"] and body["visibility"] == 0, body
    posts.clear()
    c.send_text("group", "777", "Chào cả nhóm")                       # khong mention: duong cu (GET sendmsg)
    assert not posts and "/api/group/sendmsg" in gets[0], (posts, gets)
    gets.clear()
    c.send_text("user", "222", "Chào @Nam", mentions=[{"uid": "111", "name": "Nam"}])     # 1-1: bo qua mention
    assert not posts and "/api/message/sms" in gets[0], (posts, gets)


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("MENTION TESTS PASSED")
