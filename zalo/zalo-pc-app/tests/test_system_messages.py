"""Tin HE THONG khong con ve bong bong trong (loi that 11/11: bình chọn mới tạo trên điện thoại hiện bong bóng trống trong WebUI).
Dang du lieu lay tu tin that: msgType group.poll, content {action:"create", params:"{msg:{vi:'%1$s ...%2$s'}, question, dName, ...}"}."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import chat, sync_poll  # noqa: E402

POLL_PARAMS = {"dName": "Nguyễn Việt", "groupId": 3133467193494275911, "isAnonymous": False, "pollId": 1179126996, "pollVer": 1,
               "question": "Kiểm tra", "uid": 6643404425553198601,
               "msg": {"vi": "%1$s tạo cuộc bình chọn mới: %2$s", "en": "%1$s created a new poll: %2$s", "my": "%1$s ... %2$s"}}


def _poll_item():
    return {"msgId": "m1", "uidFrom": "6643404425553198601", "idTo": "3133467193494275911", "msgType": "group.poll", "dName": "Nguyễn Việt",
            "content": {"title": "", "description": "", "href": "", "thumb": "", "childnumber": 0, "action": "create",
                        "params": json.dumps(POLL_PARAMS)}, "ts": 1794356943}


def test_poll_created_renders_from_the_template_in_params():
    m = chat.normalize_message(_poll_item(), "group")
    assert m["text"] == "Nguyễn Việt tạo cuộc bình chọn mới: Kiểm tra", m["text"]
    assert m["kind"] == "system", m["kind"]


def test_other_group_event_templates_work_without_listing_event_types():
    item = _poll_item()
    item["msgType"] = "group.whatever_new_event"
    p = dict(POLL_PARAMS)
    p.pop("question")
    p["groupName"] = "AI học hỏi"
    p["msg"] = {"vi": "%1$s đã đổi tên nhóm thành %2$s"}
    item["content"]["params"] = json.dumps(p)
    assert chat.normalize_message(item, "group")["text"] == "Nguyễn Việt đã đổi tên nhóm thành AI học hỏi"
    p["msg"] = {"en": "%1$s joined"}                                  # chỉ có tiếng Anh: dùng tạm, không rỗng
    item["content"]["params"] = json.dumps(p)
    assert chat.normalize_message(item, "group")["text"] == "Nguyễn Việt joined"
    p["msg"] = {"vi": "%1$s mời %3$s"}                                # tham số lạ: bỏ, không để lại %3$s
    item["content"]["params"] = json.dumps(p)
    assert "%" not in chat.normalize_message(item, "group")["text"]


def test_sticker_and_undo_have_placeholders_and_normal_messages_are_untouched():
    st = chat.normalize_message({"msgId": "s", "uidFrom": "1", "msgType": "chat.sticker", "content": {"catId": 1, "id": 2, "type": 7}}, "user")
    assert st["text"] == "[Sticker]" and st["kind"] == "system"
    un = chat.normalize_message({"msgId": "u", "uidFrom": "1", "msgType": "chat.undo", "content": {"globalMsgId": 5}}, "user")
    assert un["kind"] == "system" and "thu hồi" in un["text"]
    tx = chat.normalize_message({"msgId": "t", "uidFrom": "1", "msgType": "webchat", "content": "Xin chào"}, "user")
    assert tx["text"] == "Xin chào" and tx["kind"] == "text"
    ph = chat.normalize_message({"msgId": "p", "uidFrom": "1", "msgType": "chat.photo",
                                 "content": {"title": "a.jpg", "href": "http://x/a.jpg", "params": "{}"}}, "user")
    assert ph["kind"] == "photo"                                          # media vẫn là media, không bị coi là tin hệ thống
    broken = chat.normalize_message({"msgId": "b", "uidFrom": "1", "msgType": "group.poll", "content": {"params": "{không phải json"}}, "group")
    assert broken["kind"] == "text" and broken["text"] == ""              # không đoán khi không đọc được


def test_sync_path_delivers_the_readable_text_to_inbox_and_webhook():
    out = sync_poll.extract_messages({"groupMsgs": [_poll_item()]}, "999")
    (ttype, tid, msg), = out
    assert ttype == "group" and tid == "3133467193494275911"
    assert msg["text"] == "Nguyễn Việt tạo cuộc bình chọn mới: Kiểm tra" and msg["kind"] == "system"


def test_old_stored_poll_message_is_healed_on_read_and_in_thread_preview():
    import tempfile
    from zalo_pc_app import message_store
    store = message_store.MessageStore(os.path.join(tempfile.mkdtemp(), "m.db"))
    store.set_account("999")
    old = {"id": "m1", "sender_id": "6643404425553198601", "text": "", "kind": "text", "time": 1794356943, "sender_name": "Nguyễn Việt",
           "direction": "in", "raw": _poll_item()}                                   # đúng như bản ghi cũ: chữ rỗng
    store.record("group", "3133467193494275911", old)
    got = store.messages_for("group", "3133467193494275911")
    assert got[0]["text"] == "Nguyễn Việt tạo cuộc bình chọn mới: Kiểm tra" and got[0]["kind"] == "system", got
    th = [t for t in store.threads() if t["thread_id"] == "3133467193494275911"][0]
    assert th["last_text"] == "Nguyễn Việt tạo cuộc bình chọn mới: Kiểm tra", th      # xem trước ở danh sách hội thoại hết trống


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("ALL SYSTEM-MESSAGE TESTS PASSED")
