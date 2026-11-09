"""Ctrl 99101 -> webhook group_event/reaction (webhook missing
piece 4).

Bang chung bundle (Zalo PC 26.11.10, _processCtrlMessages):
controls co act_type "group" duoc gom ve _processGroupCtrlEvents_old
(item co data {groupId, act, time, sourceId}); payload ctrl co key
"reactions" / "reacts" / "reactGroups" voi muc {idTo, msgId,
cliMsgId, content (JSON voi danh sach rMsg), uidFrom}; muc rMsg co
rMsgId, rIcon (chuoi), rType (so); exe chuan hoa "0"==idTo thanh
uidFrom. Truoc day CtrlPoller chi trich voice_aac_success, cac act
khac bo qua im lang — gio group/reaction duoc chuyen thanh
dispatch_group_event / dispatch_reaction (shape payload da co
trong webhooks.py).

Mock/offline hoan toan: khong dang nhap that, khong gui that.
Khong log noi dung tin — chi id thread/tin dang test.
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import ctrl_poll as ctrl_mod  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import webhooks as webhooks_mod  # noqa: E402

UID = "10001"
AMR_URL = "https://f1-voice-aac-dl.zdn.vn/test-voice.amr"
AAC_URL = "https://f1-voice-aac-dl.zdn.vn/test-voice.aac"


def _group_control(data, act_type="group"):
    return {"controlId": "c1",
            "content": {"act_type": act_type, "data": data}}


def test_extract_group_events():
    payload = {"controls": [
        _group_control({"groupId": "30001", "act": "group_type",
                        "time": 1762345700, "sourceId": "20002",
                        "groupType": 2}),
        # data dang chuoi JSON cung doc duoc.
        _group_control(json.dumps(
            {"groupId": "30002", "act": "group_name",
             "time": 1762345710, "sourceId": "20003"})),
        # act/groupId nam o muc content (khong nam trong data).
        {"controlId": "c3",
         "content": {"act_type": "group", "act": "group_avatar",
                     "groupId": "30003",
                     "data": {"time": 1762345720}}},
        # Bo qua: act_type khac, thieu groupId, thieu act, trung.
        _group_control({"groupId": "30004", "act": "group_type"},
                       act_type="voip"),
        _group_control({"act": "group_type"}),
        _group_control({"groupId": "30005"}),
        _group_control({"groupId": "30001", "act": "group_type",
                        "time": 1762345700, "sourceId": "20002",
                        "groupType": 2}),
        "khong-phai-dict",
        {"content": "khong-phai-dict"},
    ]}
    events = ctrl_mod.extract_group_events(payload)
    assert len(events) == 3, events
    by_thread = {e["threadId"]: e for e in events}
    assert by_thread["30001"]["type"] == "group_type", events
    assert by_thread["30001"]["group_id"] == "30001", events
    assert by_thread["30001"]["data"]["sourceId"] == "20002", events
    assert by_thread["30002"]["type"] == "group_name", events
    assert by_thread["30003"]["type"] == "group_avatar", events
    assert ctrl_mod.extract_group_events({}) == []
    assert ctrl_mod.extract_group_events({"controls": "sai"}) == []


def test_extract_reactions():
    nested = json.dumps({"rMsg": [
        {"rMsgId": "m1", "rIcon": "❤", "rType": 1,
         "uidFrom": "20002"},
        {"rMsgId": "m1", "rIcon": "👍", "rType": 1,
         "uidFrom": "20003"}]})
    payload = {
        "reactions": [
            {"idTo": "20001", "msgId": "m1", "uidFrom": "20002",
             "content": nested},
            # "0"==idTo duoc thay bang uidFrom (exe).
            {"idTo": "0", "msgId": "m2", "uidFrom": "20001",
             "rIcon": "😆"},
            # Bo qua: thieu msg, thieu nguoi tha, trung.
            {"idTo": "20001", "uidFrom": "20002", "rIcon": "❤"},
            {"idTo": "20001", "msgId": "m3", "rIcon": "❤"},
            {"idTo": "20001", "msgId": "m2", "uidFrom": "20001",
             "rIcon": "😆"},
        ],
        "reactGroups": [
            {"idTo": "30001", "msgId": "m9", "uidFrom": "20003",
             "rIcon": "👍"},
        ],
        "reacts": "khong-phai-list",
    }
    reactions = ctrl_mod.extract_reactions(payload)
    assert len(reactions) == 4, reactions
    by_key = {(r["threadId"], r["msgId"], r["uidFrom"]): r
              for r in reactions}
    assert by_key[("20001", "m1", "20002")]["icon"] == "❤"
    assert by_key[("20001", "m1", "20002")]["type"] == 0
    assert by_key[("20001", "m1", "20003")]["icon"] == "👍"
    # idTo "0" -> thread la uidFrom.
    assert ("20001", "m2", "20001") in by_key, reactions
    assert by_key[("20001", "m2", "20001")]["icon"] == "😆"
    # reactGroups -> loai thread nhom (1).
    assert by_key[("30001", "m9", "20003")]["type"] == 1
    assert by_key[("30001", "m9", "20003")]["icon"] == "👍"
    assert ctrl_mod.extract_reactions({}) == []
    assert ctrl_mod.extract_reactions({"reactions": "sai"}) == []


def test_extract_reactions_flat_and_nested_list():
    payload = {"reactions": [
        # Dang phang: rIcon o muc goc.
        {"idTo": "20001", "msgId": "m5", "uidFrom": "20004",
         "rIcon": "😮"},
        # Dang long nhau qua key "reactions" (list con).
        {"idTo": "20001", "msgId": "m6", "uidFrom": "20005",
         "reactions": [{"rMsgId": "m6", "rIcon": "😢",
                        "uidFrom": "20005"}]},
    ]}
    reactions = ctrl_mod.extract_reactions(payload)
    assert len(reactions) == 2, reactions
    assert reactions[0]["icon"] == "😮", reactions
    assert reactions[1]["icon"] == "😢", reactions
    assert reactions[1]["msgId"] == "m6", reactions


def _ctrl_payload():
    return {
        "controls": [
            {"controlId": "c-voice",
             "content": {"act_type": "voice_aac_success",
                         "fileId": "file-voice-1",
                         "data": {"5": AMR_URL, "6": AAC_URL}}},
            _group_control({"groupId": "30001", "act": "group_type",
                            "time": 1762345700,
                            "sourceId": "20002"}),
        ],
        "reactions": [
            {"idTo": "20001", "msgId": "m1", "uidFrom": "20002",
             "content": json.dumps({"rMsg": [
                 {"rMsgId": "m1", "rIcon": "❤", "rType": 1,
                  "uidFrom": "20002"}]})},
        ],
        "lastActionId": "77",
        "lastActionIdOther": "60",
        "queueStatus": {}}


def test_ctrl_poller_dispatches_group_reaction_and_voice():
    """Mot batch ctrl: voice van vao registry, group/reaction di
    qua callback, con tro duoc luu."""
    mock = MockZalo()
    registry = ctrl_mod.VoiceAsyncRegistry()
    groups = []
    reactions = []
    saved = []

    def http_get(url, timeout=30):
        return 200, mock._postlogin_envelope(_ctrl_payload())

    poller = ctrl_mod.CtrlPoller(
        http_get, ["https://poll.invalid/lp-ctl"], TEST_SESSION_KEY,
        UID, registry, ctl_timeout=30,
        on_group_event=lambda e: groups.append(e),
        on_reaction=lambda e: reactions.append(e),
        on_cursor=lambda c: saved.append(c.to_dict()))
    assert poller.poll_once() == "ok"
    # Voice async: duong cu khong doi.
    got = registry.wait("file-voice-1", timeout_s=1.0)
    assert got is not None and got["aac"] == AAC_URL, got
    assert got["amr"] == AMR_URL, got
    # Group + reaction qua callback.
    assert len(groups) == 1, groups
    assert groups[0]["threadId"] == "30001", groups
    assert groups[0]["type"] == "group_type", groups
    assert len(reactions) == 1, reactions
    assert reactions[0]["threadId"] == "20001", reactions
    assert reactions[0]["msgId"] == "m1", reactions
    assert reactions[0]["icon"] == "❤", reactions
    # Chan doan batch + con tro.
    assert poller.last_batch["group_events"] == 1, poller.last_batch
    assert poller.last_batch["reactions"] == 1, poller.last_batch
    assert poller.cursor.last_action_id == "77"
    assert len(saved) == 1 and saved[0]["lastActionId"] == "77"


def test_ctrl_poller_callback_error_does_not_kill_poll():
    """Callback group/reaction loi van khong lam chet poller;
    con tro van tien."""
    mock = MockZalo()
    registry = ctrl_mod.VoiceAsyncRegistry()

    def bad_group(event):
        raise RuntimeError("callback loi gia")

    def http_get(url, timeout=30):
        return 200, mock._postlogin_envelope(_ctrl_payload())

    poller = ctrl_mod.CtrlPoller(
        http_get, ["https://poll.invalid/lp-ctl"], TEST_SESSION_KEY,
        UID, registry, ctl_timeout=30,
        on_group_event=bad_group,
        on_reaction=lambda e: (_ for _ in ()).throw(
            RuntimeError("reaction loi gia")))
    assert poller.poll_once() == "ok"
    assert poller.cursor.last_action_id == "77"


def test_server_ctrl_callbacks_dispatch_webhooks():
    """server._on_ctrl_group_event / _on_ctrl_reaction day dung
    payload webhook (envelope type + truong) qua dispatcher that."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-ctrl-webhook-test-")
    sent = []
    store = webhooks_mod.WebhookStore(
        os.path.join(tmp, "webhooks.json"))
    store.save({"group_event_webhook_url":
                "https://hook.invalid/group",
                "reaction_webhook_url":
                "https://hook.invalid/reaction"})
    disp = webhooks_mod.WebhookDispatcher(
        store, post_fn=lambda url, p: sent.append(p) or 200)
    state = app_server.AppState(tmp)
    state.webhook_dispatcher = disp
    state.session = {"uid": UID}

    state._on_ctrl_group_event(
        {"threadId": "30001", "group_id": "30001",
         "type": "group_type", "act": "group_type",
         "data": {"groupId": "30001", "act": "group_type"}})
    state._on_ctrl_reaction(
        {"threadId": "20001", "msgId": "m1", "uidFrom": "20002",
         "icon": "❤", "type": 0})
    deadline = time.time() + 5
    while time.time() < deadline and len(sent) < 2:
        time.sleep(0.05)
    assert len(sent) == 2, sent
    by_event = {p["event"]: p for p in sent}
    group = by_event["group_event"]
    assert group["type"] == "group_event.group_type", group
    assert group["thread_id"] == "30001", group
    assert group["group_event"]["act"] == "group_type", group
    reaction = by_event["reaction"]
    assert reaction["type"] == "reaction.received", reaction
    assert reaction["thread_id"] == "20001", reaction
    assert reaction["message_id"] == "m1", reaction
    assert reaction["sender_id"] == "20002", reaction
    assert reaction["icon"] == "❤", reaction


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CTRL WEBHOOK TESTS PASSED")
