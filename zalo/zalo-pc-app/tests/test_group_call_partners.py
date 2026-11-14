"""Gọi nhóm: đổ chuông ĐỦ thành viên (không chỉ topMember rút gọn) và nhóm chỉ có gọi VIDEO nhóm (14/11/2026).
Run: python3 tests/test_group_call_partners.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
tmp = tempfile.mkdtemp(prefix="zalo-pc-grp-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_PORT"] = "0"
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as sv  # noqa: E402


def state_with_groups(rows):
    st = sv.AppState(tmp)
    st._contacts_cache = {"friends": {"rows": []}, "groups": {"rows": rows}, "fetched_at": 1, "uid": "1"}
    return st


def test_type_request_group_video_is_6_audio_is_5_and_1_1_unchanged():
    assert sv._type_request_for("group", True) == protocol.CALL_TYPE_VIDEO_GROUP == 6
    assert sv._type_request_for("group", False) == protocol.CALL_TYPE_AUDIO_GROUP == 5
    assert sv._type_request_for("group") == 5                                     # mặc định cũ không đổi
    assert sv._type_request_for("user") == 1 and sv._type_request_for("video") == 3
    assert sv._type_request_for("user", True) == 1                                # cờ video chỉ có nghĩa với nhóm


def test_partners_merge_full_member_list_without_duplicates_and_keeps_given_first():
    top = ["u1", "u2"]                                   # topMember rút gọn
    full = ["u1", "u2", "u3", "u4", "u5"]                # memberIds + currentMems
    st = state_with_groups([{"id": "G1", "members": top, "member_ids": full, "member_count": 200}, {"id": "G2", "members": ["x"], "member_ids": ["x", "y"], "member_count": 2}])
    partners, total = st._group_call_partners("G1", top)
    assert partners == ["u1", "u2", "u3", "u4", "u5"], partners        # đủ, không trùng, người UI gửi đứng trước
    assert total == 200, total                           # biết nhóm có 200 người nhưng mới có 5 id → log cảnh báo thiếu
    partners, total = st._group_call_partners("G2", [])
    assert partners == ["x", "y"] and total == 2
    # người UI gửi dạng object / số cũng được chuẩn hóa thành chuỗi
    partners, _ = st._group_call_partners("G2", [{"id": 7}, 8, "x"])
    assert partners[:3] == ["7", "8", "x"] and "y" in partners, partners


def test_unknown_group_or_no_cache_falls_back_to_given_list():
    st = sv.AppState(tmp)
    st._contacts_cache = None
    assert st._group_call_partners("G9", ["a", "b"]) == (["a", "b"], 2)
    st2 = state_with_groups([{"id": "G1", "members": ["m"], "member_ids": ["m"], "member_count": 1}])
    assert st2._group_call_partners("khac", ["a"]) == (["a"], 1)
    assert st2._group_call_partners("khac", None) == ([], 0)


def test_group_row_reads_full_member_list_from_memverlist_for_large_groups():
    from zalo_pc_app import contacts
    mem_ver = ["%d_%d" % (1000 + i, i % 7) for i in range(200)]                        # 200 thành viên dạng "userId_phiênbản"
    info = {"name": "Nhóm lớn", "totalMember": 200, "hasMoreMember": 1, "memberIds": ["1000", "1001", "1002"],        # rút gọn (log thật: không có topMember)
            "currentMems": [{"id": "1003", "dName": "X"}], "memVerList": mem_ver}
    row = contacts._group_row("G1", info)
    assert len(row["member_ids"]) == 200 and row["member_ids"][:4] == ["1000", "1001", "1002", "1003"], (len(row["member_ids"]), row["member_ids"][:5])
    assert len(set(row["member_ids"])) == 200 and row["member_count"] == 200       # không trùng, đủ 200
    assert "1199" in row["member_ids"] and all("_" not in m for m in row["member_ids"])   # bỏ hậu tố _phiênbản
    # nguồn cũ vẫn dùng được khi không có memVerList
    old = contacts._group_row("G2", {"memberIds": ["7", "8"], "currentMems": [{"id": "9"}]})
    assert old["member_ids"] == ["7", "8", "9"]
    # dữ liệu lạ trong memVerList không làm hỏng
    odd = contacts._group_row("G3", {"memVerList": [None, {"a": 1}, "55_1", 66]})
    assert odd["member_ids"] == ["55", "66"], odd["member_ids"]
    # gọi nhóm: partners lấy đủ 200 người từ danh bạ đã nạp
    st = state_with_groups([row])
    partners, total = st._group_call_partners("G1", [])
    assert len(partners) == 200 and total == 200


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, str(e)[:300])
    print("ALL GROUP CALL TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
