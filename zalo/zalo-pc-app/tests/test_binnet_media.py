"""Ảnh/tệp từ lịch sử điện thoại: giải BinNet -> link, dựng tin, nâng cấp tin cũ đã nhập dạng chữ, thành viên nhóm.
Chạy: python3 tests/test_binnet_media.py"""
import json
import os
import sqlite3
import struct
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import binnet  # noqa: E402
from zalo_pc_app import contacts  # noqa: E402
from zalo_pc_app import history_import as hi  # noqa: E402
from zalo_pc_app import message_store  # noqa: E402

HD = "https://f8-zpcloud.zdn.vn/1757707383984600229/72d1ee33f6f82ca675e9.jpg"
THUMB = "https://t-f8-zpcloud.zdn.vn/1757707383984600229/72d1ee33f6f82ca675e9.jpg"
FILE_URL = "https://file-stal-6.dlfl.vn/no/998069582710f04ea901/AgHc8GGmetwvZu0zrDZExOHOjW2AbXXs2tpG3sNrE"


def blob(params, urls, prefixed=True):
    """Dựng BinNet đúng bố cục đã quan sát: đầu 28 byte (độ dài JSON ở 24..28), JSON, rồi URL có tiền tố 1 byte độ dài."""
    js = json.dumps(params).encode()
    head = struct.pack(">IIIIIII", 6, 0x160, 0x2c, 4, 0, 0x2e, len(js))
    body = b""
    for u in urls:
        e = u.encode()
        body += (bytes([len(e)]) if prefixed else b"\x00") + e
    return head + js + body + b"\x00\x00\x00\x07Botmitbap"


def test_decode_reads_params_and_urls_in_order_and_never_raises():
    d = binnet.decode(blob({"width": 1280, "height": 960, "fileSize": 214299}, [HD, THUMB]))
    assert d["urls"] == [HD, THUMB] and d["params"]["width"] == 1280
    assert binnet.decode(blob({"fileSize": "16484", "fileExt": "xlsx"}, [FILE_URL]))["urls"] == [FILE_URL]
    d2 = binnet.decode(blob({"a": 1}, [HD], prefixed=False))                      # không có tiền tố độ dài: dò theo ký tự
    assert d2["urls"][0].startswith(HD[:40])
    for bad in (None, b"", b"\x00" * 10, "chuoi", 123, b"\xff" * 64, bytes(range(256))):
        r = binnet.decode(bad)
        assert isinstance(r, dict) and isinstance(r["urls"], list) and isinstance(r["params"], dict), bad
    assert binnet.decode(blob({"a": 1}, [HD, HD]))["urls"] == [HD]                 # không lặp


def _row(mtype, content, bn, cli=1001, glb=7700000000001):
    return (111, cli, glb, 3, mtype, 1_785_000_001_000, 0, content, 0, bn, "", 0, 0, "")


def test_build_message_turns_photo_and_file_with_links_into_media_and_keeps_text_otherwise():
    photo = hi.build_message(_row(3, "[Hình ảnh] nhà mới", blob({"width": 1280, "height": 960, "fileSize": 214299}, [HD, THUMB])), 999, "OWN", {111: "PEER"})
    assert photo["kind"] == "photo" and photo["file_url"] == HD and photo["thumb_url"] == THUMB
    assert photo["text"] == "nhà mới" and photo["file_size"] == 214299 and photo["width"] == 1280
    assert photo["file_name"] == "72d1ee33f6f82ca675e9.jpg" and photo["imported"] is True
    blank = hi.build_message(_row(3, "[Hình ảnh] ", blob({}, [HD, THUMB])), 999, "OWN", {111: "PEER"})
    assert blank["kind"] == "photo" and blank["text"] == ""                       # không để chữ «[Hình ảnh]» làm chú thích
    f = hi.build_message(_row(22, "[File] Bảng kê 11 - 2026", blob({"fileSize": "16484", "fileExt": "xlsx", "checksum": "ab12"}, [FILE_URL])), 999, "OWN", {111: "PEER"})
    assert f["kind"] == "file" and f["file_name"] == "Bảng kê 11 - 2026.xlsx" and f["file_url"] == FILE_URL and f["file_size"] == 16484
    f2 = hi.build_message(_row(22, "[File] a.pdf", blob({"fileExt": "pdf"}, [FILE_URL])), 999, "OWN", {111: "PEER"})
    assert f2["file_name"] == "a.pdf"                                             # đã có đuôi thì không thêm lần nữa
    for mtype, bn in ((3, b""), (3, None), (3, b"khong giai duoc" * 5), (22, blob({}, [])), (0, blob({}, [HD]))):
        m = hi.build_message(_row(mtype, "[Hình ảnh] x" if mtype == 3 else "chu", bn), 999, "OWN", {111: "PEER"})
        assert m["kind"] == "text" and "file_url" not in m, (mtype, bn)           # không có link: vẫn là chữ như trước


def test_upgrade_media_only_touches_old_text_rows_and_is_idempotent():
    tmp = tempfile.mkdtemp(prefix="up-")
    store = message_store.MessageStore(os.path.join(tmp, "m.db"))
    store.set_account("OWN")
    old = hi.build_message(_row(3, "[Hình ảnh] nhà", b""), 999, "OWN", {111: "PEER"})          # lần nhập cũ: dạng chữ
    assert old["kind"] == "text"
    assert store.bulk_record("user", "T1", [old]) == (1, 0)
    new = hi.build_message(_row(3, "[Hình ảnh] nhà", blob({"fileSize": 10}, [HD, THUMB])), 999, "OWN", {111: "PEER"})
    assert store.bulk_record("user", "T1", [new]) == (0, 1)                        # INSERT OR IGNORE: không đổi
    assert store.upgrade_media("user", "T1", [new]) == 1
    assert store.upgrade_media("user", "T1", [new]) == 0                           # lần hai: dòng đã là photo, không chạm nữa
    assert store.upgrade_media("user", "KHAC", [new]) == 0                         # sai hội thoại: không có gì để nâng cấp
    msgs = store.messages_for("user", "T1")
    assert len(msgs) == 1 and msgs[0]["kind"] == "photo" and msgs[0]["thumb_url"] == THUMB
    for bad in (None, [], [None], [{"kind": "photo"}], [{"kind": "text", "file_url": "x"}]):
        assert store.upgrade_media("user", "T1", bad) == 0, bad


def test_import_run_reports_upgraded_count_end_to_end():
    tmp = tempfile.mkdtemp(prefix="imp-")
    run = os.path.join(tmp, "run")
    os.makedirs(run)
    con = sqlite3.connect(os.path.join(run, "111.db"))
    con.execute("CREATE TABLE ChatContent (SenderId INTEGER, CliMsgId INTEGER, GlbMsgId INTEGER, MsgStatus INTEGER, MsgType INTEGER, TimeStamp INTEGER,"
                " TTL INTEGER, MsgContent TEXT, RefCliMsgId INTEGER, BinNet BLOB, LocalPath TEXT, SeqId INTEGER, FLStatus INTEGER, E2EE TEXT)")
    con.execute("INSERT INTO ChatContent VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", _row(3, "[Hình ảnh] a", b""))
    con.commit()
    con.close()

    class Svc:
        def _get(self, domain, path, body):
            return {"fids": ["6643000000000000111" for _ in body["fids"]], "gids": []}
    store = message_store.MessageStore(os.path.join(tmp, "m.db"))
    store.set_account("OWN")
    first = hi.import_run(run, store, Svc(), "d", "OWN", log=lambda m: None)
    assert first["inserted"] == 1 and first.get("upgraded") == 0
    con = sqlite3.connect(os.path.join(run, "111.db"))                              # lần chạy sau: bản nhập mới có BinNet
    con.execute("UPDATE ChatContent SET BinNet=?", (blob({"fileSize": 5}, [HD, THUMB]),))
    con.commit()
    con.close()
    second = hi.import_run(run, store, Svc(), "d", "OWN", log=lambda m: None)
    assert second["inserted"] == 0 and second["upgraded"] == 1
    assert store.messages_for("user", "6643000000000000111")[0]["file_url"] == HD


def test_group_row_member_ids_merges_three_sources_but_members_stays_the_call_list():
    row = contacts._group_row("G1", {"name": "N", "topMember": [{"id": "1"}], "memberIds": ["1", "2", 3], "currentMems": [{"id": "4"}, {"userId": "2"}, None]})
    assert row["members"] == ["1"]                                                  # danh sách người cần GỌI giữ nguyên
    assert row["member_ids"] == ["1", "2", "3", "4"]
    only_ids = contacts._group_row("G2", {"name": "N", "memberIds": ["7", "8"]})
    assert only_ids["members"] == [] and only_ids["member_ids"] == ["7", "8"]       # ca «Thành viên (0)» trước đây
    assert contacts._group_row("G3", {})["member_ids"] == []
    assert len(contacts._group_row("G4", {"memberIds": [str(i) for i in range(6000)]})["member_ids"]) == contacts.MAX_GROUP_MEMBER_IDS == 5000    # trần an toàn (đã nâng từ 1000: nhóm 200 người phải đủ)
    assert len(contacts._group_row("G5", {"memberIds": [str(i) for i in range(1500)]})["member_ids"]) == 1500


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL BINNET-MEDIA TESTS PASSED")
