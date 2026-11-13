"""Địa chỉ công khai cho video gửi từ HA (video_urls) — tệp trong www / thư mục media thành địa chỉ Zalo tải được.
Nạp file theo đường dẫn (không kéo homeassistant). Chạy: python3 tests/test_zalo_call_video_urls.py (hoặc pytest)."""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.dirname(HERE), "custom_components", "zalo_call")


def _load(name):
    spec = importlib.util.spec_from_file_location("zc_" + name, os.path.join(BASE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vu = _load("video_urls")
BASE_URL = "https://ha.example.test"
KW = dict(www_dir="/config/www", media_dirs={"local": "/media"}, base_url=BASE_URL)


def _sign(p):
    return p + "?authSig=SIG"


def test_www_file_maps_to_local_without_signature():
    got = vu.local_to_public("/config/www/clips/a b.mp4", sign=_sign, **KW)
    assert got == "https://ha.example.test/local/clips/a%20b.mp4", got


def test_media_file_maps_to_signed_media_url():
    got = vu.local_to_public("/media/snapshots/go2rtc_phong_khach_video.mp4", sign=_sign, **KW)
    assert got == "https://ha.example.test/media/local/snapshots/go2rtc_phong_khach_video.mp4?authSig=SIG", got


def test_outside_allowed_dirs_or_traversal_gives_none():
    assert vu.local_to_public("/etc/passwd", sign=_sign, **KW) is None
    assert vu.local_to_public("/config/www/../secrets.yaml", sign=_sign, **KW) is None
    assert vu.local_to_public("/media/../etc/passwd", sign=_sign, **KW) is None
    assert vu.local_to_public("/config/www", sign=_sign, **KW) is None, "chính thư mục gốc không phải tệp"
    assert vu.local_to_public("/media/snapshots/a.mp4", sign=_sign, **dict(KW, base_url="")) is None, "chưa có địa chỉ ngoài"


def test_sibling_thumb_candidates_order_and_camera_blueprint_convention():
    c = vu.sibling_thumb_candidates("/media/snapshots/go2rtc_phong_khach_video.mp4")
    assert c[0] == "/media/snapshots/go2rtc_phong_khach_thumb.jpg", c       # đúng quy ước bản thiết kế camera
    assert "/media/snapshots/go2rtc_phong_khach_video.jpg" in c and len(c) == len(set(c)), c
    assert vu.sibling_thumb_candidates("/config/www/x.mp4")[0] == "/config/www/x_thumb.jpg"


if __name__ == "__main__":
    for _n, _f in list(globals().items()):
        if _n.startswith("test_"):
            _f()
            print("PASS", _n)
    print("PASSED")
