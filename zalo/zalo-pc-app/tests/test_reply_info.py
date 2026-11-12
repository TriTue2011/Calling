"""Tin TRA LOI (quote): lay tin goc + tep dinh kem cua tin goc; chiu moi dang, khong nem loi.

Chay: python3 tests/test_reply_info.py (kieu CI cua repo: khoi __main__ in PASSED, khong dung pytest).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import chat as chat_mod  # noqa: E402


def _item(quote, text="Dung roi"):
    return {"msgId": "9100", "cliMsgId": "8100", "uidFrom": "222", "idTo": "111", "msgType": "webchat", "content": text,
            "ts": "1794443203003", "quote": quote}


def test_reply_to_a_message_with_photo_attachment():
    attach = json.dumps({"title": "anh.jpg", "href": "https://example.invalid/anh.jpg", "thumb": "https://example.invalid/t.jpg"})
    q = {"ownerId": "111", "cliMsgId": "8001", "globalMsgId": "9001", "cliMsgType": 32, "ts": "1794443000000", "msg": "[Hinh anh]", "attach": attach}
    msg = chat_mod.normalize_message(_item(q))
    assert msg["text"] == "Dung roi" and msg["kind"] == "text", msg
    r = msg["reply_to"]
    assert r["owner"] == "111" and r["msg_id"] == "9001" and r["cli_msg_id"] == "8001" and r["text"] == "[Hinh anh]", r
    assert r["attach_kind"] == "photo" and r["attach_url"] == "https://example.invalid/anh.jpg" and r["attach_name"] == "anh.jpg", r


def test_reply_to_plain_text_and_odd_shapes_never_raise():
    r = chat_mod.normalize_message(_item({"ownerId": "111", "cliMsgId": 8001, "globalMsgId": 9001, "cliMsgType": 1, "msg": "chao"}))["reply_to"]
    assert r["text"] == "chao" and r["attach_kind"] == "" and r["attach_url"] == "", r
    assert chat_mod.normalize_message(_item(None))["reply_to"] is None                    # khong phai tin tra loi
    assert chat_mod.normalize_message({"msgId": "1", "content": "x"})["reply_to"] is None
    for odd in ("khong phai json", "{\"ownerId\": \"1\"}", ["a"], 5, {"attach": "{hong"}, {"attach": [1, 2]}, {"attach": ["x"]}):
        got = chat_mod.normalize_message(_item(odd))                                      # khong nem loi du dang la
        assert "reply_to" in got, odd
    s = chat_mod.normalize_message(_item(json.dumps({"ownerId": "9", "msg": "tu chuoi", "attach": json.dumps([{"title": "tep.pdf"}])})))["reply_to"]
    assert s["owner"] == "9" and s["text"] == "tu chuoi" and s["attach_name"] == "tep.pdf" and s["attach_kind"] == "file", s   # quote la chuoi JSON van doc duoc


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("REPLY INFO TESTS PASSED")
