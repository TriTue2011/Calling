"""«Da nhan» / «da xem» v2 nhu Zalo PC 26.11.10: than msgInfos dung dinh dang bundle, gop theo cuoc tro chuyen, tat duoc bang env.

Chay: python3 tests/test_receipts_v2.py (kieu CI cua repo: khoi __main__ in PASSED, khong dung pytest).
"""
import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mock_server import TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app.crypto import session_aes_decrypt  # noqa: E402

OWN = "111"
IN_1_1 = {"uidFrom": "222", "idTo": OWN, "msgId": "9001", "cliMsgId": "8001", "msgType": "webchat", "ts": "1794443203003", "st": 3, "at": 0, "cmd": 501}
IN_GROUP = {"uidFrom": "333", "idTo": "g777", "msgId": "9002", "cliMsgId": "8002", "msgType": "webchat", "ts": "1794443203004"}


def _chat(captured):
    def http_post(url, form, timeout=30):
        params = urllib.parse.unquote(form.split("=", 1)[1])
        captured.append((url, json.loads(session_aes_decrypt(TEST_SESSION_KEY, params))))
        return 200, {"error_code": 0, "data": ""}
    return chat_mod.Chat(lambda *a, **k: (200, {}), "IMEI-1", TEST_SESSION_KEY, http_post=http_post)


def test_msg_infos_match_zalo_pc_format():
    rows = chat_mod.Chat.msg_infos([IN_1_1], False, OWN)
    assert rows == [{"cmi": "8001", "gmi": "9001", "si": "222", "di": "0", "mt": "webchat", "st": 3, "at": 0, "cmd": 501, "ts": "1794443203003"}], rows
    grp = chat_mod.Chat.msg_infos([IN_GROUP], True, OWN)[0]
    assert grp["di"] == "777" and grp["st"] == -1 and grp["at"] == -1 and grp["cmd"] == -1, grp      # bo tien to "g", thieu st/at/cmd -> -1
    assert len(chat_mod.Chat.msg_infos([IN_1_1] * 80, False, OWN)) == 50                             # toi da 50 tin moi lan


def test_delivered_and_seen_v2_bodies():
    sent = []
    c = _chat(sent)
    c.send_delivered_v2("user", "222", [IN_1_1], own_uid=OWN)
    c.send_delivered_v2("group", "777", [IN_GROUP], own_uid=OWN)
    c.send_seen_v2("user", "222", [IN_1_1], own_uid=OWN)
    c.send_seen_v2("group", "777", [IN_GROUP], own_uid=OWN)
    (u1, b1), (u2, b2), (u3, b3), (u4, b4) = sent
    assert "/api/message/deliveredv2" in u1 and "imei" not in b1, (u1, b1)
    i1 = json.loads(b1["msgInfos"])
    assert i1["seen"] == 0 and "grid" not in i1 and i1["data"][0]["gmi"] == "9001", i1
    assert "/api/group/deliveredv2" in u2 and b2["imei"] == "IMEI-1" and json.loads(b2["msgInfos"])["grid"] == "777", b2
    assert "/api/message/seenv2" in u3 and b3["imei"] == "IMEI-1" and json.loads(b3["msgInfos"])["senderId"] == "222", b3
    assert "/api/group/seenv2" in u4 and json.loads(b4["msgInfos"])["grid"] == "777", b4


class _Store:
    def __init__(self, msgs):
        self.msgs = msgs

    def messages_for(self, thread_type, thread_id, limit=50):
        return self.msgs


def test_mark_seen_prefers_v2_with_stored_raw_messages_and_falls_back_to_v1():
    sent = []
    c = _chat(sent)
    other = dict(IN_1_1, msgId="9005", cliMsgId="8005")
    store = _Store([
        {"id": "9005", "direction": "in", "is_self": False, "raw": other},               # moi nhat truoc
        {"id": "9001", "direction": "in", "is_self": False, "raw": IN_1_1},
        {"id": "7777", "direction": "out", "is_self": True, "raw": dict(IN_1_1, msgId="7777")},   # tin minh gui: khong «da xem»
    ])
    c.mark_seen("user", "222", ["9001"], store=store, own_uid=OWN)                   # theo id
    c.mark_seen("user", "222", [], store=store, own_uid=OWN)                          # khong id: tat ca tin den (cu -> moi)
    (u1, b1), (u2, b2) = sent
    assert "/api/message/seenv2" in u1 and [r["gmi"] for r in json.loads(b1["msgInfos"])["data"]] == ["9001"], b1
    assert [r["gmi"] for r in json.loads(b2["msgInfos"])["data"]] == ["9001", "9005"], b2
    sent.clear()
    c.mark_seen("user", "222", ["12345", "abc"], store=_Store([]), own_uid=OWN)          # kho khong co: v1 dung dang Zalo PC
    c.mark_seen("group", "777", ["55"], store=None)
    (u3, b3), (u4, b4) = sent
    assert "/api/message/seen" in u3 and "v2" not in u3 and b3 == {"msg_ids": [12345, "abc"], "senderId": "222"}, (u3, b3)
    assert "/api/group/seen" in u4 and b4 == {"msg_ids": [55], "grid": "777"}, (u4, b4)


class _FakeChat:
    calls = []

    def __init__(self, *a, **k):
        pass

    def send_delivered_v2(self, thread_type, thread_id, raws, seen=False, own_uid=""):
        _FakeChat.calls.append((thread_type, thread_id, [r["msgId"] for r in raws]))


def test_batcher_groups_by_thread_and_can_be_disabled():
    real_chat, real_state = app_server.chat_mod.Chat, app_server.STATE
    app_server.chat_mod.Chat = _FakeChat
    app_server.STATE = type("S", (), {"session": {"zpw_sek": "x", "device_id": "d", "zpw_enk": TEST_SESSION_KEY, "uid": OWN}})()
    try:
        b = app_server._ReceiptBatcher()
        b.add("user", "222", dict(IN_1_1))
        b.add("user", "222", dict(IN_1_1, msgId="9003", cliMsgId="8003"))
        b.add("group", "777", dict(IN_GROUP))
        b.add("user", "222", {"msgId": "", "cliMsgId": ""})            # thieu id: bo qua
        time.sleep(0.5)
        assert sorted(_FakeChat.calls) == [("group", "777", ["9002"]), ("user", "222", ["9001", "9003"])], _FakeChat.calls
        _FakeChat.calls.clear()
        os.environ["ZALO_PC_AUTO_DELIVERED"] = "0"
        try:
            b.add("user", "222", dict(IN_1_1))
            time.sleep(0.4)
            assert _FakeChat.calls == [], _FakeChat.calls
        finally:
            os.environ.pop("ZALO_PC_AUTO_DELIVERED", None)
    finally:
        app_server.chat_mod.Chat, app_server.STATE = real_chat, real_state


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("RECEIPTS V2 TESTS PASSED")
