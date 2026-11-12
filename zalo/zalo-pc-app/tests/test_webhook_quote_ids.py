"""Webhook tin nhan mang them ma goc de HA TRICH DAN khi tra loi nhom (cli_msg_id, uid_from, msg_ts, zalo_msg_type).
Run: python3 tests/test_webhook_quote_ids.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import webhooks  # noqa: E402


def test_build_message_event_carries_original_ids():
    msg = {"threadId": "8845", "type": 1, "senderId": "6643", "msgId": "8474470959615", "content": "@Bot bat den", "kind": "text",
           "raw": {"cliMsgId": 1794325284060, "uidFrom": 207908325, "ts": "1794325284060", "msgType": "webchat"}}
    ev = webhooks.build_message_event(msg, "acc")
    assert ev["message_id"] == "8474470959615" and ev["cli_msg_id"] == "1794325284060" and ev["uid_from"] == "207908325", ev
    assert ev["msg_ts"] == "1794325284060" and ev["zalo_msg_type"] == "webchat", ev
    bare = webhooks.build_message_event({"threadId": "1", "type": 0, "senderId": "2", "msgId": "3", "content": "x"}, "acc")
    for k in ("cli_msg_id", "uid_from", "msg_ts", "zalo_msg_type"):
        assert k not in bare, (k, bare)                    # khong co raw thi khong them truong (tuong thich cu)


class FakeDisp:
    def __init__(self):
        self.sent = []

    def dispatch(self, kind, payload):
        self.sent.append((kind, payload))
        return True

    def is_enabled(self, kind):
        return True


def test_sync_message_path_forwards_ids_to_webhook():
    state = app_server.AppState(tempfile.mkdtemp(prefix="wq-"))
    state.webhook_dispatcher = FakeDisp()
    raw = {"msgId": "8474470959615", "cliMsgId": "1794325284060", "uidFrom": "207908325", "idTo": "0", "ts": "1794325284060", "msgType": "webchat",
           "content": "@Bot bật đèn", "dName": "Đại ca"}
    msg = chat_mod.normalize_message(raw)
    msg["sender_id"] = "6643404425553198601"
    state._on_sync_message("group", "8845", msg)
    kinds = [(k, p) for k, p in state.webhook_dispatcher.sent if k == "message"]
    assert kinds, state.webhook_dispatcher.sent
    p = kinds[0][1]
    assert p["thread_id"] == "8845" and p["content"] == "@Bot bật đèn" and p["cli_msg_id"] == "1794325284060" and p["uid_from"] == "207908325", p
    assert p["sender_id"] == "6643404425553198601" and p["message_id"] == "8474470959615", p


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL WEBHOOK QUOTE ID TESTS PASSED")
