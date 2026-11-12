"""Thu hoi tin + tu xoa du lieu (13/11/2026).
Chu may: «tin nhan ben zalo khac thu hoi nhung ben zalo phu khong mat» — app chi luu them tin bao «Mot tin nhan da duoc thu hoi», tin goc van con.
Run: python3 tests/test_recall_retention.py"""

import json
import os
import queue
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import message_store as ms  # noqa: E402
from zalo_pc_app import retention as rt  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app.sync_poll import Inbox  # noqa: E402

PEER = "6643000000000000111"


def _raw_text(msg_id, cli_id, text, ts=1794325284060, uid="207908325"):
    return {"msgId": msg_id, "cliMsgId": cli_id, "uidFrom": uid, "idTo": "0", "ts": str(ts), "msgType": "webchat", "content": text}


def _raw_undo(msg_id, cli_id, target_global, target_cli, uid="207908325"):
    return {"msgId": msg_id, "cliMsgId": cli_id, "uidFrom": uid, "idTo": "0", "ts": "1794325286152", "msgType": "chat.undo",
            "content": {"cliMsgId": target_cli, "deleteMsg": 0, "destId": "0", "globalMsgId": target_global, "srcId": "0"}}


def test_store_recall_replaces_content_and_is_idempotent_and_scoped():
    tmp = tempfile.mkdtemp(prefix="rr-")
    st = ms.MessageStore(os.path.join(tmp, "m.db"))
    m1 = chat_mod.normalize_message(_raw_text("8474470959615", "1794325284060", "mat khau la 123456"))
    m1["sender_id"] = PEER
    notice = chat_mod.normalize_message(_raw_undo("8474471046867", "1794325286152", "8474470959615", "1794325284060"))
    assert notice["kind"] == "system" and "thu hồi" in notice["text"], notice
    other = chat_mod.normalize_message(_raw_text("8474470959999", "1794325288888", "tin khac van con"))
    assert st.record("user", PEER, m1) and st.record("user", PEER, other) and st.record("user", "OTHERTHREAD", dict(m1, id="x"))
    ids = st.recall("user", PEER, "8474470959615", "1794325284060")
    assert ids == [m1["id"]], ids
    got = {m["id"]: m for m in st.messages_for("user", PEER, 10)}
    assert got[m1["id"]]["kind"] == "system" and got[m1["id"]]["text"] == ms.RECALLED_TEXT and got[m1["id"]]["recalled"] is True
    raw_db = st._conn.execute("SELECT content, raw_json FROM messages WHERE thread_id=? AND msg_id=?", (PEER, m1["id"])).fetchone()
    assert "123456" not in raw_db[0] and "123456" not in raw_db[1], "noi dung goc phai bi xoa khoi DB"
    assert got[other["id"]]["text"] == "tin khac van con", "tin khac khong bi anh huong"
    assert st.recall("user", PEER, "8474470959615", "1794325284060") == [], "thu hoi lan hai khong doi gi"
    assert [m for m in st.messages_for("user", "OTHERTHREAD", 10)][0]["text"] != ms.RECALLED_TEXT, "hoi thoai khac khong bi anh huong"
    # chi co cliMsgId (khong biet msgId) van tim ra
    other2 = chat_mod.normalize_message(_raw_text("8474470960000", "1794325299999", "chi biet cli"))
    st.record("user", PEER, other2)
    assert st.recall("user", PEER, "", "1794325299999") == [other2["id"]]
    assert st.recall("user", PEER, "", "") == [] and st.recall("user", PEER, "no-such", "0") == []


def test_inbox_recall_in_memory():
    box = Inbox()
    m = chat_mod.normalize_message(_raw_text("8474470959615", "1794325284060", "bi mat"))
    assert box.record("user", PEER, m)
    assert box.recall("user", PEER, "8474470959615", "") == [m["id"]]
    items = box.messages_for("user", PEER)
    assert items[0]["recalled"] is True and items[0]["text"] == ms.RECALLED_TEXT and "bi mat" not in json.dumps(items[0])
    assert box.recall("user", PEER, "8474470959615", "") == []


def test_server_recall_end_to_end_via_sync_message_path():
    state = app_server.AppState(tempfile.mkdtemp(prefix="rr-"))
    q = state.events.subscribe()
    orig = chat_mod.normalize_message(_raw_text("8474470959615", "1794325284060", "se bi thu hoi"))
    orig["sender_id"] = PEER
    state._on_sync_message("user", PEER, orig)
    assert state.message_store.messages_for("user", PEER, 10)[0]["text"] == "se bi thu hoi"
    while not q.empty():
        q.get_nowait()
    notice = chat_mod.normalize_message(_raw_undo("8474471046867", "1794325286152", "8474470959615", "1794325284060"))
    notice["sender_id"] = PEER
    state._on_sync_message("user", PEER, notice)
    rows = state.message_store.messages_for("user", PEER, 10)
    assert len(rows) == 1 and rows[0]["text"] == ms.RECALLED_TEXT and rows[0]["recalled"] is True, rows         # tin goc doi thanh dau, KHONG them tin bao
    assert state.inbox.messages_for("user", PEER)[0]["recalled"] is True
    ev = q.get(timeout=2)
    assert ev["type"] == "recall" and ev["thread_id"] == PEER and ev["msg_ids"] == [orig["id"]], ev
    # thu hoi tin KHONG co trong kho: van luu tin bao nhu cu (khong mat thong tin)
    n2 = chat_mod.normalize_message(_raw_undo("8474471099999", "1794325297777", "1111111", "2222222"))
    n2["sender_id"] = PEER
    state._on_sync_message("user", PEER, n2)
    assert len(state.message_store.messages_for("user", PEER, 10)) == 2
    state.events.unsubscribe(q)


def test_retention_settings_are_validated_and_applied():
    tmp = tempfile.mkdtemp(prefix="rr-")
    st = ms.MessageStore(os.path.join(tmp, "m.db"))
    r = rt.Retention(tmp, st, log=lambda m: None)
    assert r.get() == rt.DEFAULTS and st.max_per_thread == rt.DEFAULTS["max_per_thread"]
    cfg = r.update({"messages_days": 90, "max_per_thread": 0})
    assert cfg["messages_days"] == 90 and st.max_per_thread == 0, "doi la ap dung ngay cho kho tin"
    assert rt.Retention(tmp, st, log=lambda m: None).get()["messages_days"] == 90, "luu ben vao retention.json"
    for bad in ({"khong_co": 1}, {"messages_days": -1}, {"messages_days": 99999}, {"files_days": "7"}, {"sync_days": True}, "x"):
        try:
            r.update(bad)
            raise AssertionError("phai tu choi %r" % (bad,))
        except rt.RetentionError:
            pass
    assert r.get()["messages_days"] == 90, "gia tri sai khong lam doi gi"


def _m(i, ts, text="x"):
    return {"id": str(i), "sender_id": "1", "text": text, "time": ts, "kind": "text", "direction": "in", "raw": {"msgId": str(i)}}


def test_prune_by_days_and_per_thread_and_run_cleans_files_and_sync_dirs():
    tmp = tempfile.mkdtemp(prefix="rr-")
    st = ms.MessageStore(os.path.join(tmp, "m.db"))
    now = time.time()
    day = 86400
    for i in range(10):                                           # 10 tin: tuoi 1..10 ngay
        st.record("user", "A", _m(i + 1, now - (i + 1) * day))
    st.record("user", "B", _m(100, 0, "ts bang 0 (khong ro)"))
    r = rt.Retention(tmp, st, log=lambda m: None, clock=lambda: now)
    r.update({"messages_days": 5, "max_per_thread": 0, "files_days": 7, "sync_days": 3})
    # tep tai ve va thu muc dong bo
    dl = os.path.join(tmp, "downloads", "user_A")
    os.makedirs(dl)
    old_f, new_f, reg = os.path.join(dl, "cu.bin"), os.path.join(dl, "moi.bin"), os.path.join(tmp, "downloads", "registry.json")
    for p in (old_f, new_f, reg):
        open(p, "wb").write(b"x" * 1000)
    os.utime(old_f, (now - 30 * day, now - 30 * day))
    os.utime(reg, (now - 90 * day, now - 90 * day))               # registry.json cu van phai giu
    hs = os.path.join(tmp, "history_sync")
    os.makedirs(os.path.join(hs, "20260101-000000"))
    os.makedirs(os.path.join(hs, "20261112-000000"))
    os.makedirs(os.path.join(hs, "khong-phai-thu-muc-dong-bo"))
    open(os.path.join(hs, "20260101-000000", "a.db"), "wb").write(b"y" * 500)
    open(os.path.join(hs, "key.pem"), "wb").write(b"KEY")
    os.utime(os.path.join(hs, "20260101-000000"), (now - 30 * day, now - 30 * day))
    os.utime(os.path.join(hs, "khong-phai-thu-muc-dong-bo"), (now - 99 * day, now - 99 * day))
    rep = r.run()
    assert rep["messages_deleted"] == 5, rep                       # tuoi 6..10 ngay bi xoa; tin dung 5 ngay tuoi nam tren bien nen duoc GIU
    left = sorted(m["id"] for m in st.messages_for("user", "A", 50))
    assert left == ["1", "2", "3", "4", "5"], left
    assert [m["text"] for m in st.messages_for("user", "B", 5)] == ["ts bang 0 (khong ro)"], "ts = 0 (khong biet gio) khong bi xoa"
    assert rep["files_deleted"] == 1 and not os.path.exists(old_f) and os.path.exists(new_f) and os.path.exists(reg)
    assert rep["sync_dirs_deleted"] == 1 and not os.path.exists(os.path.join(hs, "20260101-000000")), rep
    assert os.path.exists(os.path.join(hs, "20261112-000000")) and os.path.exists(os.path.join(hs, "key.pem")) and os.path.exists(os.path.join(hs, "khong-phai-thu-muc-dong-bo"))
    assert rep["freed_bytes"] >= 0 and r.last_report == rep
    # cat theo so tin moi hoi thoai
    for i in range(30):
        st.record("user", "C", _m(1000 + i, now - 100 + i))
    r.update({"messages_days": 0, "max_per_thread": 10})
    st2 = r.run()
    cnt = len(st.messages_for("user", "C", 100))
    assert cnt == 10 and st2["messages_deleted"] == 20, (cnt, st2)
    assert min(m["id"] for m in st.messages_for("user", "C", 100)) == "1020", "giu 10 tin MOI NHAT"
    stats = st.stats()
    assert stats["rows"] == len(st.messages_for("user", "A", 99)) + 1 + 10 and stats["threads"] == 3 and stats["db_bytes"] > 0, stats


def test_record_respects_runtime_cap_and_zero_means_unlimited():
    tmp = tempfile.mkdtemp(prefix="rr-")
    st = ms.MessageStore(os.path.join(tmp, "m.db"))
    st.max_per_thread = 5
    for i in range(12):
        st.record("user", "A", _m(i + 1, 1700000000 + i))
    assert len(st.messages_for("user", "A", 50)) == 5
    st.max_per_thread = 0
    for i in range(12, 40):
        st.record("user", "A", _m(i + 1, 1700000000 + i))
    assert len(st.messages_for("user", "A", 100)) == 5 + 28, "0 = khong cat"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL RECALL/RETENTION TESTS PASSED")
