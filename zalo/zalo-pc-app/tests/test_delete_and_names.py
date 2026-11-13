"""Tin chat.delete + ten nguoi la (13/11/2026). Run: python3 tests/test_delete_and_names.py"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import message_store as ms  # noqa: E402
from zalo_pc_app import profile_names as pn  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app.sync_poll import Inbox  # noqa: E402

PEER = "6643404425553198601"
# mau THAT lay tu messages.db ngay 13/11 (tin tu xoa cua chinh minh, Zalo bao lai)
RAW_DELETE = {"actionId": "14595293297338", "msgId": "8483932797796", "cliMsgId": "1794552574292", "msgType": "chat.delete", "uidFrom": "475796162066271393",
              "idTo": PEER, "dName": "Botmitbap", "ts": "1794552574348", "status": 1,
              "content": [{"type": 1, "actionType": 1, "uidFrom": 475796162066271393, "uidTo": 6643404425553198601,
                           "clientDelMsgId": 1794552564159, "globalDelMsgId": 8483932192742, "destId": 6643404425553198601}]}


def _text(msg_id, cli_id, text):
    return {"msgId": msg_id, "cliMsgId": cli_id, "uidFrom": "475796162066271393", "idTo": PEER, "ts": "1794552564159", "msgType": "webchat", "content": text}


def test_store_forget_removes_row_and_scopes():
    st = ms.MessageStore(os.path.join(tempfile.mkdtemp(prefix="dn-"), "m.db"))
    a = chat_mod.normalize_message(_text("8483932192742", "1794552564159", "thu B xoa sau 10 giay"))
    b = chat_mod.normalize_message(_text("8483932999999", "1794552999999", "tin khac"))
    assert st.record("user", PEER, a) and st.record("user", PEER, b)
    assert st.forget("user", PEER, 8483932192742, 1794552564159) == [a["id"]]
    left = [m["text"] for m in st.messages_for("user", PEER, 10)]
    assert left == ["tin khac"], left
    assert st.forget("user", PEER, 8483932192742, 1794552564159) == [], "xoa lan hai khong doi gi"
    assert st.forget("user", "KHAC", 8483932999999, "") == [], "hoi thoai khac khong bi anh huong"
    assert st.forget("user", PEER, "", "") == []


def test_old_delete_events_are_purged_on_open():
    path = os.path.join(tempfile.mkdtemp(prefix="dn-"), "m.db")
    st = ms.MessageStore(path)
    junk = chat_mod.normalize_message(RAW_DELETE)
    assert junk.get("raw", {}).get("msgType") == "chat.delete", junk
    keep = chat_mod.normalize_message(_text("1", "2", "tin that"))
    assert st.record("user", PEER, junk) and st.record("user", PEER, keep)
    st2 = ms.MessageStore(path)                   # mo lai = don sach
    texts = [m["text"] for m in st2.messages_for("user", PEER, 10)]
    assert texts == ["tin that"], texts


def test_inbox_forget():
    box = Inbox()
    m = chat_mod.normalize_message(_text("8483932192742", "1794552564159", "se bi xoa"))
    assert box.record("user", PEER, m)
    assert box.forget("user", PEER, "8483932192742", "") == [m["id"]]
    assert box.messages_for("user", PEER) == []


class _Ev:
    def __init__(self):
        self.out = []

    def publish(self, e):
        self.out.append(e)


def test_apply_delete_removes_and_publishes_once():
    st = ms.MessageStore(os.path.join(tempfile.mkdtemp(prefix="dn-"), "m.db"))
    box = Inbox()
    m = chat_mod.normalize_message(_text("8483932192742", "1794552564159", "xoa hai ben"))
    st.record("user", PEER, m)
    box.record("user", PEER, m)

    class S:
        message_store, inbox, events = st, box, _Ev()
    cls = [getattr(app_server, n) for n in dir(app_server) if hasattr(getattr(app_server, n), "_apply_delete")][0]
    ids = cls._apply_delete(S, "user", PEER, RAW_DELETE["content"])
    assert ids == [m["id"]], ids
    assert st.messages_for("user", PEER, 10) == [] and box.messages_for("user", PEER) == []
    assert len(S.events.out) == 1 and S.events.out[0]["type"] == "delete" and S.events.out[0]["msg_ids"] == [m["id"]]
    assert cls._apply_delete(S, "user", PEER, "rac") == [] and cls._apply_delete(S, "user", PEER, None) == []
    assert len(S.events.out) == 1, "khong tim thay tin thi khong bao giao dien"


def test_find_name_shapes():
    uid = "2005600327393091310"
    prof = {"userId": "123456789", "displayName": "Phương Anh", "zaloName": "pa"}
    assert pn.find_name({"changed_profiles": {uid: prof}}, uid) == "Phương Anh"
    assert pn.find_name({"changed_profiles": {uid + "_0": prof}}, uid) == "Phương Anh"
    assert pn.find_name({"data": {"unchanged_profiles": [dict(prof, userId=uid)]}}, uid) == "Phương Anh"
    assert pn.find_name({"changed_profiles": {"zzz": {"zaloName": "Chi ten Zalo", "userId": "1"}}}, uid) == "Chi ten Zalo", "chi mot ho so"
    two = {"changed_profiles": {"a": {"displayName": "A", "userId": "1"}, "b": {"displayName": "B", "userId": "2"}}}
    assert pn.find_name(two, uid) == "", "hai ho so khong khop: khong doan"
    assert pn.find_name({}, uid) == "" and pn.find_name(None, uid) == "" and pn.find_name({"x": [1, "a"]}, uid) == ""


def _wait(cond, secs=3.0):
    t0 = time.time()
    while time.time() - t0 < secs:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_profile_names_cache_negative_and_persist():
    path = os.path.join(tempfile.mkdtemp(prefix="dn-"), "p.json")
    calls, changes, clock = [], [], [1000.0]

    def lookup(u):
        calls.append(u)
        if u == "bad":
            raise RuntimeError("zalo loi")
        return {"1": "Ng Khanh Duy", "2": ""}.get(u, "")
    p = pn.ProfileNames(path, lookup, on_change=lambda: changes.append(1), now=lambda: clock[0], pause=0)
    p.ensure(["1", "2", "bad", "0", ""])
    assert _wait(lambda: len(calls) == 3 and not p._pending), calls
    assert p.name("1") == "Ng Khanh Duy" and p.name("2") == "" and p.name("bad") == "" and changes == [1]
    p.ensure(["1", "2", "bad"])
    time.sleep(0.1)
    assert len(calls) == 3, "co ten va that bai gan day khong hoi lai"
    clock[0] += pn.RETRY_SECONDS + 1
    p.ensure(["1", "2"])
    assert _wait(lambda: len(calls) == 4 and not p._pending), calls
    assert calls[-1] == "2", "chi thu lai ma chua co ten"
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    p2 = pn.ProfileNames(path, lookup, now=lambda: clock[0], pause=0)
    assert p2.name("1") == "Ng Khanh Duy" and p2.all_names() == {"1": "Ng Khanh Duy"}


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
    print("%d tests PASSED" % n)
    print("PASSED")
