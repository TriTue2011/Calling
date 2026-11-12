"""Nhap lich su da giai ma vao messages.db (13/11/2026). Tep SQLite gia dung dung LUOC DO THAT do tren Zalo (ChatContent ... 14 cot), znoise gia.
Run: python3 tests/test_history_import.py"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import history_import as hi  # noqa: E402
from zalo_pc_app import message_store  # noqa: E402

OWN_SHORT, OWN_NOISED = 999, "4757000000000000001"
PEER_SHORT, PEER_NOISED = 111, "6643000000000000111"
OTHER_SHORT, OTHER_NOISED = 222, "6643000000000000222"
GROUP_SHORT, GROUP_NOISED = 555, "8845000000000000555"
GHOST_SHORT = 333                                  # uid ma znoise khong doi duoc


def make_db(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE ChatContent (SenderId INTEGER, CliMsgId INTEGER, GlbMsgId INTEGER, MsgStatus INTEGER, MsgType INTEGER, TimeStamp INTEGER,"
                " TTL INTEGER, MsgContent TEXT, RefCliMsgId INTEGER, BinNet BLOB, LocalPath TEXT, SeqId INTEGER, FLStatus INTEGER, E2EE TEXT)")
    con.execute("CREATE TABLE ApiSafe (ApiId INTEGER)")
    for sender, cli, glb, mtype, ts, content in rows:
        con.execute("INSERT INTO ChatContent VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (sender, cli, glb, 3, mtype, ts, 0, content, 0, b"", "", 0, 0, ""))
    con.commit()
    con.close()


class FakeSvc:
    def __init__(self):
        self.calls = []

    def _get(self, domain, path, body):
        self.calls.append((path, body))
        assert path == "/api/znoise"
        fmap = {PEER_SHORT: PEER_NOISED, OTHER_SHORT: OTHER_NOISED, GHOST_SHORT: "0"}
        return {"fids": [fmap.get(i, "") for i in body["fids"]], "gids": ["g%s" % GROUP_NOISED if i == GROUP_SHORT else "0" for i in body["gids"]]}


def build_snapshot(tmp):
    run = os.path.join(tmp, "run")
    os.makedirs(run)
    T = 1_785_000_000_000
    make_db(os.path.join(run, "%d.db" % PEER_SHORT), [
        (PEER_SHORT, 1001, 7700000000001, 0, T + 1000, "xin chao"),
        (OWN_SHORT, 1002, 7700000000002, 0, T + 2000, "chao ban"),
        (PEER_SHORT, 1003, 7700000000003, 3, T + 3000, "[Hình ảnh] ảnh nhà mới"),
        (OWN_SHORT, 1004, 7700000000004, 22, T + 4000, "[File] bao_cao.pdf"),
        (PEER_SHORT, 1005, 7700000000005, 20, T + 5000, "Việt ngừng Tin nhắn tự xóa."),
        (OWN_SHORT, 1006, 0, 0, T + 6000, "tin chua dong bo (GlbMsgId = 0)"),
        (OWN_SHORT, 1007, 7700000000007, 36, T + 7000, ""),            # kieu 36 rong: bo qua
        (PEER_SHORT, 1008, 7700000000008, 0, T + 8000, "   "),         # chi khoang trang: bo qua
    ])
    make_db(os.path.join(run, "group_%d.db" % GROUP_SHORT), [
        (OTHER_SHORT, 2001, 7800000000001, 0, T + 1500, "chao ca nha"),
        (OWN_SHORT, 2002, 7800000000002, 0, T + 2500, "minh day"),
        (PEER_SHORT, 2003, 7800000000003, 0, T + 3500, "ok"),
    ])
    make_db(os.path.join(run, "%d.db" % GHOST_SHORT), [(GHOST_SHORT, 3001, 7900000000001, 0, T, "khong doi duoc ma")])
    return run


def test_detects_own_uid_and_imports_with_mapping_and_dedup():
    tmp = tempfile.mkdtemp(prefix="hi-")
    run = build_snapshot(tmp)
    one, grp = hi._list_files(run)
    assert hi.detect_own_short_uid(one) == OWN_SHORT, "uid cua minh = SenderId khac ten tep xuat hien nhieu nhat"
    store = message_store.MessageStore(os.path.join(tmp, "messages.db"))
    # tin da ghi truc tiep tu truoc (cung msgId + nguoi gui) KHONG duoc nhan doi
    live = {"id": "7700000000001", "sender_id": PEER_NOISED, "text": "xin chao", "time": 1785000001, "kind": "text", "direction": "in",
            "raw": {"msgId": "7700000000001", "cliMsgId": "1001"}}
    assert store.record("user", PEER_NOISED, live) is True
    svc = FakeSvc()
    res = hi.import_run(run, store, svc, "https://profile", OWN_NOISED, log=lambda m: None)
    assert res["inserted"] == 5 + 3 and res["unmapped"] == 1 and res["files"] == 2, res         # 1-1: 6 tin hop le - 1 da co = 5; nhom: 3; 1 tep khong doi duoc ma
    msgs = store.messages_for("user", PEER_NOISED, 50)
    texts = {m["text"]: m for m in msgs}
    assert "xin chao" in texts and len([m for m in msgs if m["text"] == "xin chao"]) == 1, "khong nhan doi tin da co"
    assert texts["chao ban"]["direction"] == "out" and texts["chao ban"]["sender_id"] == OWN_NOISED and texts["chao ban"]["is_self"] is True
    assert texts["[Hình ảnh] ảnh nhà mới"]["direction"] == "in" and texts["[Hình ảnh] ảnh nhà mới"]["sender_id"] == PEER_NOISED
    assert texts["[File] bao_cao.pdf"]["file_name"] == "bao_cao.pdf"
    assert texts["Việt ngừng Tin nhắn tự xóa."]["kind"] == "system"
    assert texts["tin chua dong bo (GlbMsgId = 0)"]["id"] == "c1006" and texts["tin chua dong bo (GlbMsgId = 0)"]["raw"]["msgId"] == ""
    assert not any(m["text"].strip() == "" for m in msgs), "tin rong bi bo qua"
    assert texts["xin chao"]["time"] == 1785000001 and texts["chao ban"]["time"] == 1785000002, "TimeStamp mili-giay -> giay"
    raw = texts["chao ban"]["raw"]
    assert raw["msgId"] == "7700000000002" and raw["cliMsgId"] == "1002" and raw["uidFrom"] == str(OWN_SHORT), raw          # du de Tra loi/Cam xuc/Thu hoi hoat dong
    # nhom: ma nhom bo tien to g, nguoi gui doi sang ma dai
    gm = {m["text"]: m for m in store.messages_for("group", GROUP_NOISED, 50)}
    assert gm["chao ca nha"]["sender_id"] == OTHER_NOISED and gm["minh day"]["direction"] == "out" and gm["ok"]["sender_id"] == PEER_NOISED, gm
    # hoi thoai moi nhap KHONG bi dem la chua doc
    threads = {(t["thread_type"], t["thread_id"]): t for t in store.threads()}
    assert threads[("user", PEER_NOISED)]["unread"] == 0 and threads[("group", GROUP_NOISED)]["unread"] == 0, threads
    # chay lai: khong nhan doi gi
    again = hi.import_run(run, store, FakeSvc(), "https://profile", OWN_NOISED, log=lambda m: None)
    assert again["inserted"] == 0, again
    assert len(store.messages_for("user", PEER_NOISED, 50)) == len(msgs)
    # znoise goi theo lo, nguoi va nhom rieng, dung duong dan
    assert all(c[0] == "/api/znoise" for c in svc.calls) and any(c[1]["gids"] for c in svc.calls) and any(c[1]["fids"] for c in svc.calls)


def test_keep_days_skips_old_messages_so_retention_does_not_fight_the_import():
    tmp = tempfile.mkdtemp(prefix="hi-")
    run = os.path.join(tmp, "run")
    os.makedirs(run)
    now = 1_790_000_000.0
    day = 86400
    make_db(os.path.join(run, "%d.db" % PEER_SHORT), [
        (PEER_SHORT, 1, 7700000000001, 0, int((now - 400 * day) * 1000), "rat cu"),
        (OWN_SHORT, 2, 7700000000002, 0, int((now - 10 * day) * 1000), "gan day"),
        (PEER_SHORT, 3, 7700000000003, 0, int((now - 364 * day) * 1000), "sat bien"),
    ])
    store = message_store.MessageStore(os.path.join(tmp, "messages.db"))
    res = hi.import_run(run, store, FakeSvc(), "d", OWN_NOISED, log=lambda m: None, keep_days=365, now=now)
    assert res["inserted"] == 2 and res["old_skipped"] == 1, res
    assert sorted(m["text"] for m in store.messages_for("user", PEER_NOISED, 10)) == ["gan day", "sat bien"]
    assert store.prune(365, 20000, now=now) == 0, "tin vua nhap khong bi retention xoa ngay"
    res0 = hi.import_run(run, message_store.MessageStore(os.path.join(tmp, "m2.db")), FakeSvc(), "d", OWN_NOISED, log=lambda m: None, keep_days=0, now=now)
    assert res0["inserted"] == 3 and res0["old_skipped"] == 0, "keep_days = 0 (khong tu xoa) thi nhap het"


def test_import_without_files_is_a_clear_error():
    tmp = tempfile.mkdtemp(prefix="hi-")
    store = message_store.MessageStore(os.path.join(tmp, "messages.db"))
    try:
        hi.import_run(tmp, store, FakeSvc(), "https://profile", OWN_NOISED, log=lambda m: None)
        raise AssertionError("phai bao loi")
    except hi.ImportError_ as e:
        assert "không có tệp" in str(e), e


def test_noise_ids_chunks_large_lists_and_skips_zero():
    class Svc:
        def __init__(self):
            self.sizes = []

        def _get(self, domain, path, body):
            self.sizes.append((len(body["fids"]), len(body["gids"])))
            return {"fids": ["0" if i % 2 else "9%d" % i for i in body["fids"]], "gids": ["g%d" % i for i in body["gids"]]}
    svc = Svc()
    fmap, gmap = hi.noise_ids(svc, range(1, 251), range(1000, 1003), "d")
    assert max(s[0] for s in svc.sizes) <= hi.CHUNK and max(s[1] for s in svc.sizes) <= hi.CHUNK, svc.sizes
    assert 2 in fmap and 1 not in fmap, "gia tri '0' = khong co anh xa"
    assert gmap[1000] == "1000", gmap


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL HISTORY IMPORT TESTS PASSED")
