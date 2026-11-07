"""Con tro sync luu xuong dia + xu ly batch offline (webhook
missing pieces 1+2).

Bang chung bundle (Zalo PC 26.11.10): exe luu lastActionId /
lastActionIdOther / per-queue lastId xuong localStorage sau moi
batch (_saveData), mo lai poll tiep tu con tro da luu — server tra
tin trong hang doi ke tu do (bu tin lo). Het han thi server gui
resetLastActionId -> nhay toi id moi, lastActionIdOther ve "1",
xoa queue. Tren kenh HTTP khong co ACK rieng: luu con tro da tien
+ poll tiep chinh la ACK tuong duong DELETE_QUEUE_ACK (557/558
nam tren kenh signal E2EE ma app khong co).

Mock/offline hoan toan: khong dang nhap that, khong gui that.
Khong log noi dung tin — chi dem so luong / id con tro.
"""

import json
import os
import sys
import tempfile
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import cursor_store as cursor_mod  # noqa: E402
from zalo_pc_app import sync_poll as sync_mod  # noqa: E402

UID = "10001"


def test_cursor_to_dict_from_dict_round_trip():
    cur = sync_mod.PollCursor()
    cur.update_from({
        "lastActionId": "100", "lastActionIdOther": "50",
        "queueStatus": {"oneone": {"lastId": "9", "ids": ["a", "b"]},
                        "group": {"lastId": "3"}}})
    saved = cur.to_dict()
    assert saved["lastActionId"] == "100", saved
    assert saved["lastActionIdOther"] == "50", saved
    assert saved["queues"]["oneone"]["lastId"] == "9", saved
    restored = sync_mod.PollCursor.from_dict(saved)
    assert restored.last_action_id == "100", restored.last_action_id
    assert restored.last_action_id_other == "50", \
        restored.last_action_id_other
    assert restored.queues == cur.queues, restored.queues
    assert restored.param() == cur.param(), restored.param()
    # from_dict nhan ca PollCursor cu (khong dung) — chi dict.
    assert sync_mod.PollCursor.from_dict(None).param().startswith(
        "1,1,")


def test_cursor_from_dict_garbage_defaults():
    for bad in (None, {}, {"lastActionId": ""},
                {"lastActionId": "5", "queues": {"q": "khong-phai-dict"}},
                {"queues": {"q": {"lastId": 42}}}):
        cur = sync_mod.PollCursor.from_dict(bad)
        assert cur.last_action_id in ("1", "5"), cur.last_action_id
        assert cur.last_action_id_other == "1", cur.last_action_id_other
    cur = sync_mod.PollCursor.from_dict(
        {"queues": {"q": {"lastId": 42}}})
    assert cur.queues == {"q": {"lastId": "42"}}, cur.queues


def test_cursor_reset_exe_parity():
    """resetLastActionId: nhay toi id moi, lastActionIdOther ve
    "1" (khong giu ca hai o id cu nhu ban cu), xoa queue."""
    cur = sync_mod.PollCursor()
    cur.update_from({
        "lastActionId": "100", "lastActionIdOther": "50",
        "queueStatus": {"oneone": {"lastId": "9", "ids": ["a"]}}})
    assert cur.queues, cur.queues
    cur.update_from({"resetLastActionId": "7"})
    assert cur.last_action_id == "7", cur.last_action_id
    assert cur.last_action_id_other == "1", cur.last_action_id_other
    assert cur.queues == {}, cur.queues
    # Gia tri reset rong / "0" / "NaN" bi bo qua (guard cu).
    cur.update_from({"resetLastActionId": "0"})
    assert cur.last_action_id == "7", cur.last_action_id
    cur.update_from({"resetLastActionId": ""})
    assert cur.last_action_id == "7", cur.last_action_id


def test_cursor_store_save_load_round_trip():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-cursor-test-")
    path = os.path.join(tmp, "sync_cursor.json")
    store = cursor_mod.SyncCursorStore(path)
    assert store.load("msg", UID) == cursor_mod.DEFAULT_STATE
    state = {"lastActionId": "100", "lastActionIdOther": "50",
             "queues": {"oneone": {"lastId": "9", "ids": ["a"]}}}
    assert store.save("msg", state, UID) is True
    assert store.save("ctrl", {"lastActionId": "77",
                               "lastActionIdOther": "60",
                               "queues": {}}, UID) is True
    # Mode 0600 nhu webhooks.json / session.py.
    assert (os.stat(path).st_mode & 0o777) == 0o600, oct(
        os.stat(path).st_mode)
    # Instance moi (gia lap restart) doc lai dung ca hai kenh.
    store2 = cursor_mod.SyncCursorStore(path)
    assert store2.load("msg", UID) == state, store2.load("msg", UID)
    assert store2.load("ctrl", UID)["lastActionId"] == "77"
    # Uid khac tai khoan -> con tro cu bi bo (mac dinh).
    assert store2.load("msg", "99999") == cursor_mod.DEFAULT_STATE


def test_cursor_store_corrupt_file_defaults():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-cursor-test-")
    path = os.path.join(tmp, "sync_cursor.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{khong-phai-json")
    store = cursor_mod.SyncCursorStore(path)
    assert store.load("msg", UID) == cursor_mod.DEFAULT_STATE
    # Ghi de file hong van duoc.
    assert store.save("msg", {"lastActionId": "5",
                              "lastActionIdOther": "4",
                              "queues": {}}, UID) is True
    assert cursor_mod.SyncCursorStore(path).load(
        "msg", UID)["lastActionId"] == "5"


def test_cursor_store_save_bad_path_no_raise():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-cursor-test-")
    blocker = os.path.join(tmp, "file-chan-duong")
    with open(blocker, "w", encoding="utf-8") as f:
        f.write("x")
    store = cursor_mod.SyncCursorStore(
        os.path.join(blocker, "sync_cursor.json"))
    # Ghi loi tra False, khong nem loi ra poller.
    assert store.save("msg", {"lastActionId": "5",
                              "lastActionIdOther": "4",
                              "queues": {}}, UID) is False
    assert store.load("msg", UID) == cursor_mod.DEFAULT_STATE


def test_cursor_store_clear():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-cursor-test-")
    path = os.path.join(tmp, "sync_cursor.json")
    store = cursor_mod.SyncCursorStore(path)
    store.save("msg", {"lastActionId": "100", "lastActionIdOther": "50",
                       "queues": {}}, UID)
    assert os.path.exists(path)
    store.clear()
    assert not os.path.exists(path)
    assert store.load("msg", UID) == cursor_mod.DEFAULT_STATE


def _fake_poll_get(mock, payload, seen_urls):
    def http_get(url, timeout=30):
        seen_urls.append(url)
        return 200, mock._postlogin_envelope(payload)
    return http_get


def _offline_payload():
    return {
        "msgs": [{"msgId": "off1", "globalMsgId": "g-off1",
                  "uidFrom": "20001", "idTo": "10001",
                  "content": "Tin gui luc app tat",
                  "ts": 1762345700, "dName": "BenBap", "msgType": 0}],
        "groupMsgs": [], "pageMsgs": [],
        "lastActionId": "100", "lastActionIdOther": "50",
        "queueStatus": {"oneone": {"lastId": "9", "ids": ["off1"]}},
        "firstPollOffline": True}


def test_poller_saves_cursor_after_offline_batch():
    """Batch co tin offline (queueStatus co ids + firstPollOffline):
    poller giao tin, ghi nhan so queue offline, va luu con tro da
    tien xuong dia — viec luu nay chinh la ACK tuong duong
    DELETE_QUEUE_ACK tren kenh HTTP."""
    mock = MockZalo()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-cursor-test-")
    store = cursor_mod.SyncCursorStore(
        os.path.join(tmp, "sync_cursor.json"))
    delivered = []
    saved = []
    poller = sync_mod.SyncPoller(
        _fake_poll_get(mock, _offline_payload(), []),
        ["https://poll.invalid/lp-msg"], TEST_SESSION_KEY, UID,
        on_message=lambda t, tid, m: delivered.append((t, tid, m)),
        msg_timeout=30,
        cursor=store.load("msg", UID),
        on_cursor=lambda c: (saved.append(c.to_dict()),
                             store.save("msg", c.to_dict(), UID)))
    assert poller.poll_once() == "ok"
    assert len(delivered) == 1, delivered
    assert delivered[0][2]["text"] == "Tin gui luc app tat", delivered
    assert poller.last_batch["messages"] == 1, poller.last_batch
    assert poller.last_batch["offline_queues"] == 1, poller.last_batch
    assert poller.cursor.last_action_id == "100"
    assert poller.cursor.last_action_id_other == "50"
    assert len(saved) == 1, saved
    assert saved[0]["lastActionId"] == "100", saved
    # Instance moi (gia lap restart) doc lai con tro da luu.
    store2 = cursor_mod.SyncCursorStore(
        os.path.join(tmp, "sync_cursor.json"))
    loaded = store2.load("msg", UID)
    assert loaded["lastActionId"] == "100", loaded
    assert loaded["lastActionIdOther"] == "50", loaded
    assert loaded["queues"]["oneone"]["lastId"] == "9", loaded


def test_poller_resumes_from_saved_cursor():
    """Poller khoi tao tu con tro da luu gui params voi con tro do
    (khong phai "1,1") — server tra tin trong hang doi ke tu do."""
    mock = MockZalo()
    seen_urls = []
    poller = sync_mod.SyncPoller(
        _fake_poll_get(mock, _offline_payload(), seen_urls),
        ["https://poll.invalid/lp-msg"], TEST_SESSION_KEY, UID,
        on_message=lambda t, tid, m: None,
        msg_timeout=30,
        cursor={"lastActionId": "100", "lastActionIdOther": "50",
                "queues": {"oneone": {"lastId": "9", "ids": ["off1"]}}})
    assert poller.poll_once() == "ok"
    assert len(seen_urls) == 1, seen_urls
    params = urllib.parse.urlparse(seen_urls[0]).query
    qs = dict(urllib.parse.parse_qsl(params))
    assert qs["params"].startswith("100,50,"), qs["params"]


def test_poller_no_save_when_cursor_unchanged():
    """Batch khong lam con tro doi -> on_cursor khong duoc goi
    (khong ghi dia thua)."""
    mock = MockZalo()
    saved = []
    poller = sync_mod.SyncPoller(
        _fake_poll_get(mock, {"msgs": [], "groupMsgs": [],
                              "pageMsgs": [], "lastActionId": "1",
                              "lastActionIdOther": "1",
                              "queueStatus": {}}, []),
        ["https://poll.invalid/lp-msg"], TEST_SESSION_KEY, UID,
        on_message=lambda t, tid, m: None,
        msg_timeout=30,
        on_cursor=lambda c: saved.append(c.to_dict()))
    assert poller.poll_once() == "ok"
    assert saved == [], saved
    assert poller.last_batch["offline_queues"] == 0, poller.last_batch


def test_poller_reset_persists_other_one():
    """Reset tu server duoc luu xuong dia dung dang exe
    (other ve "1")."""
    mock = MockZalo()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-cursor-test-")
    store = cursor_mod.SyncCursorStore(
        os.path.join(tmp, "sync_cursor.json"))
    store.save("msg", {"lastActionId": "100",
                       "lastActionIdOther": "50",
                       "queues": {"oneone": {"lastId": "9"}}}, UID)
    poller = sync_mod.SyncPoller(
        _fake_poll_get(mock, {"msgs": [], "groupMsgs": [],
                              "pageMsgs": [],
                              "resetLastActionId": "200"}, []),
        ["https://poll.invalid/lp-msg"], TEST_SESSION_KEY, UID,
        on_message=lambda t, tid, m: None,
        msg_timeout=30,
        cursor=store.load("msg", UID),
        on_cursor=lambda c: store.save("msg", c.to_dict(), UID))
    assert poller.poll_once() == "ok"
    assert poller.cursor.last_action_id == "200"
    assert poller.cursor.last_action_id_other == "1"
    assert poller.cursor.queues == {}
    loaded = cursor_mod.SyncCursorStore(
        os.path.join(tmp, "sync_cursor.json")).load("msg", UID)
    assert loaded["lastActionId"] == "200", loaded
    assert loaded["lastActionIdOther"] == "1", loaded
    assert loaded["queues"] == {}, loaded


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL SYNC CURSOR TESTS PASSED")
