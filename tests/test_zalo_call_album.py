"""Gửi nhiều ảnh một lúc thành album (album.py). Nạp file theo đường dẫn (không kéo homeassistant).
Chạy: python3 tests/test_zalo_call_album.py (hoặc pytest)."""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.dirname(HERE), "custom_components", "zalo_call")
spec = importlib.util.spec_from_file_location("zc_album", os.path.join(BASE, "album.py"))
al = importlib.util.module_from_spec(spec)
spec.loader.exec_module(al)


def test_three_photos_become_one_album_in_order():
    plan = al.album_plan([("a.jpg", "image/jpeg"), ("b.PNG", ""), ("c.webp", "image/webp")], 1794570000000)
    assert [p["idInGroup"] for p in plan] == ["0", "1", "2"], plan
    assert {p["groupLayoutId"] for p in plan} == {"1794570000000"} and {p["totalItemInGroup"] for p in plan} == {"3"}, plan
    assert {p["isGroupLayout"] for p in plan} == {"1"}, plan


def test_gif_and_other_files_are_sent_apart_and_do_not_count_in_the_album():
    plan = al.album_plan([("a.jpg", ""), ("anim.gif", "image/gif"), ("b.jpg", ""), ("doc.pdf", "application/pdf"), ("c.heic", "")], 5)
    assert plan[1] is None and plan[3] is None and plan[4] is None, plan
    assert [plan[0]["idInGroup"], plan[2]["idInGroup"]] == ["0", "1"] and plan[0]["totalItemInGroup"] == "2", plan


def test_a_single_photo_or_none_is_never_an_album():
    assert al.album_plan([("a.jpg", "")], 1) == [None]
    assert al.album_plan([("a.jpg", ""), ("b.gif", "")], 1) == [None, None], "một ảnh + một GIF: ảnh không đủ 2 để thành album"
    assert al.album_plan([], 1) == []


def test_mime_is_used_only_when_there_is_no_extension():
    assert al.is_album_photo("anh", "image/jpeg") and not al.is_album_photo("anh", "image/gif") and not al.is_album_photo("anh.gif", "image/jpeg")


if __name__ == "__main__":
    for _n, _f in list(globals().items()):
        if _n.startswith("test_"):
            _f()
            print("PASS", _n)
    print("PASSED")
