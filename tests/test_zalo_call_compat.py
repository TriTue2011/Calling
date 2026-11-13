"""Tương thích tên trường với zalo_bot cũ (compat.py). Nạp file theo đường dẫn (không kéo homeassistant).
Chạy: python3 tests/test_zalo_call_compat.py (hoặc pytest)."""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("zc_compat", os.path.join(os.path.dirname(HERE), "custom_components", "zalo_call", "compat.py"))
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


def test_old_names_become_new_names_when_the_service_has_the_target_field():
    out = cp.rename_aliases("send_video", {"video_path_or_url": "/a.mp4", "thumbnail_url": "t", "ttl": 5}, {"file", "thumbnail", "ttl"})
    assert out == {"file": "/a.mp4", "thumbnail": "t", "ttl": 5}, out
    assert cp.rename_aliases("send_images_to_user", {"image_paths": "a,b"}, {"files"}) == {"files": "a,b"}
    assert cp.rename_aliases("delete_message", {"uid_from": "7"}, {"owner_id", "msg_id"}) == {"owner_id": "7"}
    assert cp.rename_aliases("forward_message", {"thread_ids": "1,2"}, {"dest_thread_ids"}) == {"dest_thread_ids": "1,2"}


def test_group_id_becomes_thread_id_even_though_thread_id_is_not_a_catalog_field():
    assert cp.rename_aliases("leave_group", {"group_id": "9"}, set()) == {"thread_id": "9"}


def test_target_wins_and_nothing_is_renamed_without_a_target_or_when_old_is_a_real_field():
    assert cp.rename_aliases("send_image", {"image_path": "old", "file": "new"}, {"file"}) == {"file": "new"}
    assert cp.rename_aliases("send_message", {"image_path": "x"}, {"message"}) == {"image_path": "x"}, "không có trường file: giữ nguyên để cảnh báo"
    assert cp.rename_aliases("x", {"group_id": "9"}, {"group_id"}) == {"group_id": "9"}, "group_id là trường thật của dịch vụ này"
    assert cp.rename_aliases("x", "không phải dict", set()) == "không phải dict"


def test_original_dict_is_not_mutated():
    src = {"image_path": "a"}
    cp.rename_aliases("send_image", src, {"file"})
    assert src == {"image_path": "a"}


def test_unknown_keys_ignore_account_selection_and_the_generic_keys():
    got = cp.unknown_keys({"message": "x", "account_selection": "a", "own_id": "1", "entry_id": "e", "thread_id": "1", "type": "user", "ttl": 1, "quote": {}},
                          {"message"})
    assert got == ["quote", "ttl"], got


if __name__ == "__main__":
    for _n, _f in list(globals().items()):
        if _n.startswith("test_"):
            _f()
            print("PASS", _n)
    print("PASSED")
