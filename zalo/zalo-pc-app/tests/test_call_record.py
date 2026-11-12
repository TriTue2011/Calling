"""Ban ghi cuoc goi cua Zalo (chat.recommended) la tin he thong, khong phai tin nguoi dung.

Chay: python3 tests/test_call_record.py (kieu CI cua repo: khoi __main__ in PASSED, khong dung pytest).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import chat as chat_mod  # noqa: E402


def _item(action, params, title="Cuộc gọi thoại"):
    return {"msgId": "9200", "cliMsgId": "8200", "uidFrom": "222", "idTo": "111", "msgType": "chat.recommended", "ts": "1794443203003",
            "content": {"action": action, "title": title, "description": "", "href": "", "thumb": "", "childnumber": 0, "type": 0,
                        "params": json.dumps(params)}}


def test_call_time_record_is_a_system_message_with_duration():
    m = chat_mod.normalize_message(_item("recommened.calltime", {"callId": 1305618176, "calltype": 0, "duration": 14, "isCaller": 0}))
    assert m["kind"] == "system" and m["text"] == "Cuộc gọi · 0:14", m
    assert m["call_record"] == {"call_id": "1305618176", "duration": 14, "missed": False, "is_caller": False, "text": "Cuộc gọi · 0:14"}, m["call_record"]


def test_missed_call_record_and_ordinary_messages_are_not_confused():
    m = chat_mod.normalize_message(_item("recommened.misscall", {"callId": 7, "duration": 0, "isCaller": 1, "reason": 3}, title=""))
    assert m["kind"] == "system" and m["call_record"]["missed"] is True and m["text"] == "Cuộc gọi nhỡ", m
    v = chat_mod.normalize_message(_item("recommened.calltime", {"callId": 8, "calltype": 1, "duration": 125}))
    assert v["text"] == "Cuộc gọi · 2:05", v
    plain = chat_mod.normalize_message({"msgId": "1", "msgType": "webchat", "content": "xin chao", "uidFrom": "2", "idTo": "1"})
    assert plain["kind"] == "text" and plain["call_record"] is None and plain["text"] == "xin chao", plain
    other = chat_mod.normalize_message(_item("recommened.khac", {}))             # action la: khong doan
    assert other["call_record"] is None, other
    broken = _item("recommened.calltime", {})
    broken["content"]["params"] = "{hong"
    assert chat_mod.normalize_message(broken)["call_record"]["duration"] == 0      # params hong: khong nem loi


def test_old_stored_call_record_is_healed_on_read():
    """Tin luu TRUOC ban sua co text «sendBubbleMessage» + kind text: doc ra phai thanh tin he thong co chu that."""
    from zalo_pc_app import message_store
    raw = _item("recommened.calltime", {"callId": 5, "calltype": 0, "duration": 18, "isCaller": 1})
    old = {"id": "1", "text": "sendBubbleMessage", "kind": "text", "raw": raw}
    healed = message_store.MessageStore._heal(old)
    assert healed["kind"] == "system" and healed["text"] == "Cuộc gọi · 0:18" and healed["call_record"]["duration"] == 18, healed
    normal = {"id": "2", "text": "sendBubbleMessage", "kind": "text", "raw": {"msgType": "webchat", "content": "sendBubbleMessage"}}
    assert message_store.MessageStore._heal(normal) == normal       # nguoi dung that su go chu nay: giu nguyen


def test_old_stored_system_placeholder_call_record_is_healed_too():
    """Anh 12/11: ban ghi luu o giua hai ban sua da co kind «system» NHUNG text van la sendBubbleMessage — phai tinh lai tu raw."""
    from zalo_pc_app import message_store
    raw = _item("recommened.calltime", {"callId": 6, "calltype": 0, "duration": 19, "isCaller": 1})
    old = {"id": "1", "text": "sendBubbleMessage", "kind": "system", "raw": raw, "call_record": {"duration": 19}}
    healed = message_store.MessageStore._heal(old)
    assert healed["kind"] == "system" and healed["text"] == "Cuộc gọi · 0:19" and healed["call_record"]["duration"] == 19, healed
    other = {"id": "2", "text": "Bình chọn mới", "kind": "system", "raw": {"msgType": "chat.poll"}}
    assert message_store.MessageStore._heal(other) == other          # tin he thong khac giu nguyen


def test_reply_to_audio_attachment_is_not_labelled_photo():
    """Anh 12/11: tra loi mot tep tts_kiem_thu.mp3 hien «[Anh] tts_kiem_thu.mp3»."""
    base = {"quote": {"ownerId": "1", "cliMsgId": "9", "globalMsgId": "9", "cliMsgType": 99, "ts": 1, "msg": "", "fromD": "", "ttl": 0}}
    cases = [("tts_kiem_thu.mp3", "voice"), ("a.jpg", "photo"), ("bao_cao.pdf", "file"), ("clip.mp4", "video")]
    for name, want in cases:
        item = json.loads(json.dumps(base))
        item["quote"]["attach"] = json.dumps({"href": "https://x/y/" + name, "title": name})
        got = chat_mod.reply_info(item)
        assert got["attach_kind"] == want, (name, got)


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("CALL RECORD TESTS PASSED")
