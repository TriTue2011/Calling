"""Bản ghi cuộc gọi khi tin VỪA ĐẾN (poll hoặc WebSocket) phải hiện chữ đúng, không phải chữ giữ chỗ «sendBubbleMessage».
Chạy: python3 tests/test_call_record_live_text.py"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import sync_poll  # noqa: E402

OWN = "365685311"


def _record(action, duration=0, **extra):
    item = {"msgId": "m1", "cliMsgId": "c1", "uidFrom": "6643404425553198601", "idTo": OWN, "msgType": "chat.recommended", "ts": 1794548079000, "dName": "Đại ca",
            "content": {"action": action, "title": "sendBubbleMessage", "description": "", "href": "", "thumb": "", "childnumber": 0,
                        "params": json.dumps({"callId": 1399396370, "calltype": 0, "duration": duration, "isCaller": False})}}
    item.update(extra)
    return item


def test_missed_and_answered_call_records_keep_the_normalized_text():
    (_t, _id, missed), = sync_poll.extract_messages({"msgs": [_record("recommened.misscall")]}, OWN)
    assert missed["text"] == "Cuộc gọi nhỡ" and missed["kind"] == "system" and missed["call_record"]["missed"] is True, missed
    (_t, _id, done), = sync_poll.extract_messages({"msgs": [_record("recommened.calltime", 62)]}, OWN)
    assert done["text"] == "Cuộc gọi · 1:02" and done["kind"] == "system" and done["call_record"]["duration"] == 62, done
    (_t, _id, zero), = sync_poll.extract_messages({"msgs": [_record("recommened.calltime", 0)]}, OWN)
    assert zero["text"] == "Cuộc gọi", zero
    assert "sendBubbleMessage" not in json.dumps([missed["text"], done["text"], zero["text"]])


def test_other_messages_keep_their_text_exactly_as_before():
    plain = {"msgId": "m2", "uidFrom": "20001", "idTo": OWN, "msgType": "webchat", "ts": 1794548079000, "content": "xin chào", "dName": "A"}
    (_t, _id, m), = sync_poll.extract_messages({"msgs": [plain]}, OWN)
    assert m["text"] == "xin chào" and m["kind"] == "text" and not m.get("call_record"), m
    other_reco = _record("recommened.khac")                                                    # chat.recommended nhưng KHÔNG phải cuộc gọi: giữ hành vi cũ
    (_t, _id, o), = sync_poll.extract_messages({"msgs": [other_reco]}, OWN)
    assert not o.get("call_record") and o["text"] == "sendBubbleMessage", o                     # không đoán thay Zalo
    (_t, _id, g), = sync_poll.extract_messages({"groupMsgs": [dict(plain, idTo="30001", content={"msg": "chào nhóm"})]}, OWN)
    assert g["text"] == "chào nhóm" and g["thread_type"] == "group"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CALL-RECORD-LIVE-TEXT TESTS PASSED")
