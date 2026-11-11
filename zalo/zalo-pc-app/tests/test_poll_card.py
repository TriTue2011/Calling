"""Thẻ bình chọn trên WebUI: tin group.poll mang poll_id + câu hỏi (để WebUI dựng thẻ từ danh sách bình chọn của nhóm), và mô hình thẻ (thanh số phiếu,
cờ đã đóng/ẩn danh/chọn nhiều, ai dẫn đầu) tính đúng. Phần JS chạy bằng node (tests/test_poll_card.js)."""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import chat  # noqa: E402

PARAMS = {"dName": "Nguyễn Việt", "groupId": 3133467193494275911, "isAnonymous": False, "pollId": 1179126996, "question": "Kiểm tra", "uid": 1,
          "msg": {"vi": "%1$s tham gia cuộc bình chọn: %2$s"}}


def _item(msg_type="group.poll", params=PARAMS):
    return {"msgId": "m1", "uidFrom": "1", "idTo": "3133467193494275911", "msgType": msg_type, "dName": "Nguyễn Việt",
            "content": {"action": "vote", "params": json.dumps(params)}, "ts": 1794393994805}


def test_poll_event_carries_poll_id_and_question_as_strings_without_rounding():
    m = chat.normalize_message(_item(), "group")
    assert m["kind"] == "system" and m["poll_id"] == "1179126996" and m["poll_question"] == "Kiểm tra", m
    assert chat.normalize_message(_item(params={**PARAMS, "pollId": 8477247680834123456}), "group")["poll_id"] == "8477247680834123456"


def test_other_messages_have_no_poll_id():
    assert chat.normalize_message(_item(msg_type="group.other"), "group")["poll_id"] == ""
    st = chat.normalize_message({"msgId": "s", "uidFrom": "1", "msgType": "chat.sticker", "content": {"catId": 1}}, "user")
    assert st["poll_id"] == "" and st["kind"] == "system"
    tx = chat.normalize_message({"msgId": "t", "uidFrom": "1", "msgType": "webchat", "content": "Xin chào"}, "user")
    assert tx["poll_id"] == "" and tx["kind"] == "text"
    bad = chat.normalize_message({"msgId": "b", "uidFrom": "1", "msgType": "group.poll", "content": {"params": "{không phải json"}}, "group")
    assert bad["poll_id"] == ""


def test_poll_card_model_and_one_card_per_poll_in_js():
    if shutil.which("node") is None:          # không cần pytest: CI chạy file như script
        print("bỏ qua: không có node")
        return
    r = subprocess.run(["node", os.path.join(os.path.dirname(__file__), "test_poll_card.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


if __name__ == "__main__":
    # CI chạy mỗi file như một script: tự chạy các test rồi in dòng PASSED (không cần pytest).
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("ALL POLL CARD TESTS PASSED")
