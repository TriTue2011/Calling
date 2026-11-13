"""Đo kích thước ảnh khi nơi gọi không khai (14/11/2026).

Gốc lỗi: dịch vụ HA `zalo_call.send_images_*` gửi tệp thô, không kèm width/height -> app gửi Zalo 0x0 -> Zalo xếp album thành 3 ô vuông cắt,
khác ảnh zalo_bot (khung ngang 2+1). Sau sửa: server tự đọc kích thước từ byte ảnh. Khai sẵn thì giữ nguyên số khai.

Run: python3 tests/test_image_size.py
"""

import json
import os
import struct
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zlib
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app.image_size import image_size  # noqa: E402


def jpeg(w, h, orient=None, progressive=False):
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\0\x01\x01\0\0\x01\0\x01\0\0"
    exif = b""
    if orient:
        t = b"MM\0\x2a\0\0\0\x08" + struct.pack(">H", 1) + struct.pack(">HHIHH", 0x0112, 3, 1, orient, 0) + b"\0\0\0\0"
        exif = b"\xff\xe1" + struct.pack(">H", 2 + 6 + len(t)) + b"Exif\0\0" + t
    sof = (b"\xff\xc2" if progressive else b"\xff\xc0") + struct.pack(">HBHHB", 17, 8, h, w, 3) + b"\x01\x22\0\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + app0 + exif + sof + b"\xff\xda\0\x08\x01\x01\0\0?\0" + b"\x00" * 8 + b"\xff\xd9"


def png(w, h):
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))


def gif(w, h):
    return b"GIF89a" + struct.pack("<HH", w, h) + b"\x00\x00\x00;"


def webp_vp8x(w, h):
    body = b"VP8X" + struct.pack("<I", 10) + b"\0\0\0\0" + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def webp_vp8l(w, h):
    bits = (w - 1) | ((h - 1) << 14)
    body = b"VP8L" + struct.pack("<I", 5) + b"\x2f" + struct.pack("<I", bits)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def webp_vp8(w, h):
    body = b"VP8 " + struct.pack("<I", 14) + b"\x10\x02\0\x9d\x01\x2a" + struct.pack("<HH", w, h) + b"\0\0\0\0"
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def test_each_format():
    assert image_size(jpeg(1280, 720)) == (1280, 720)
    assert image_size(jpeg(640, 480, progressive=True)) == (640, 480)
    assert image_size(png(1920, 1080)) == (1920, 1080)
    assert image_size(gif(320, 240)) == (320, 240)
    assert image_size(webp_vp8x(1000, 500)) == (1000, 500)
    assert image_size(webp_vp8l(800, 600)) == (800, 600)
    assert image_size(webp_vp8(1024, 768)) == (1024, 768)


def test_jpeg_exif_rotation_swaps():
    """Ảnh điện thoại chụp dọc: tệp 4000x3000 + EXIF xoay 6/8 -> hiển thị 3000x4000, Zalo phải nhận số đã xoay."""
    assert image_size(jpeg(4000, 3000, orient=6)) == (3000, 4000)
    assert image_size(jpeg(4000, 3000, orient=8)) == (3000, 4000)
    assert image_size(jpeg(4000, 3000, orient=1)) == (4000, 3000)
    assert image_size(jpeg(4000, 3000, orient=3)) == (4000, 3000)


def test_matches_pillow_when_available():
    try:
        from PIL import Image
    except ImportError:
        print("SKIP: khong co Pillow")
        return
    import io
    for fmt, size in (("JPEG", (1280, 720)), ("PNG", (333, 777)), ("GIF", (50, 20)), ("WEBP", (640, 360))):
        buf = io.BytesIO()
        Image.new("RGB", size, (200, 30, 30)).save(buf, fmt)
        assert image_size(buf.getvalue()) == size, fmt
    buf = io.BytesIO()
    Image.new("RGBA", (321, 123)).save(buf, "WEBP", lossless=True)
    assert image_size(buf.getvalue()) == (321, 123)


def test_garbage_and_truncated_never_raise():
    for bad in (b"", None, b"not an image at all", b"\xff\xd8", b"\xff\xd8\xff\xe0FAKEJPEGDATA", b"\x89PNG\r\n\x1a\n", b"GIF89a",
                b"RIFF\0\0\0\0WEBPVP8X", jpeg(100, 50)[:20], b"\xff\xd8" + b"\xff" * 50):
        assert image_size(bad) == (0, 0), bad
    assert image_size(jpeg(0, 0)) == (0, 0)           # kích thước 0 không phải kích thước


# -- e2e qua route /sendfile ------------------------------------------
BASE = ""


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def patch_domains(mock):
    for mod, names in ((protocol, ("AUTH_DOMAIN", "VOICECALL_DOMAIN", "PROFILE_DOMAIN", "GROUP_DOMAIN")),
                       (chat_mod, ("CHAT_DOMAIN", "FILES_DOMAIN", "GROUP_DOMAIN"))):
        for n in names:
            setattr(mod, n, mock.base)


def photo_bodies(mock):
    return [b["body"] for b in mock.upload_bodies if b["path"] in ("/api/message/photo", "/api/group/sendpt")]


def test_route_measures_when_caller_gives_no_size_and_keeps_given_size():
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-imgsize-")
    try:
        patch_domains(mock)
        app_server.STATE = app_server.AppState(tmp)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
        api("POST", "/api/qr/new", json.dumps({}).encode(), {"Content-Type": "application/json"})
        deadline, last = time.time() + 20, {}
        while time.time() < deadline:
            _, last = api("GET", "/api/qr/status")
            if last.get("state") == "done":
                break
            time.sleep(0.5)
        assert last.get("state") == "done", last

        def send(tid, ttype, data, name, mime, extra=None):
            fields = {"type": ttype, "kind": "photo"}
            fields.update(extra or {})
            mb, ct = chat_mod.build_multipart(fields, [("file", name, mime, data)])
            st, body = api("POST", "/api/thread/%s/sendfile" % tid, mb, {"Content-Type": ct})
            assert st == 200, (st, body)
            return photo_bodies(mock)[-1]

        # kiểu dịch vụ HA: tệp thô + 4 trường album, KHÔNG width/height
        album = {"groupLayoutId": "1794612680000", "totalItemInGroup": "3", "isGroupLayout": "1", "idInGroup": "0"}
        b = send("30001", "group", jpeg(1280, 720), "go2rtc_cua_gui1.jpg", "image/jpeg", album)
        assert (b["width"], b["height"]) == (1280, 720), b
        assert b["groupLayoutId"] == "1794612680000", b
        b = send("20001", "user", png(640, 360), "a.png", "image/png")
        assert (b["width"], b["height"]) == (640, 360), b
        b = send("20001", "user", jpeg(4000, 3000, orient=6), "d.jpg", "image/jpeg")
        assert (b["width"], b["height"]) == (3000, 4000), b
        # khai sẵn (WebUI): giữ nguyên
        b = send("20001", "user", jpeg(1280, 720), "c.jpg", "image/jpeg", {"width": "800", "height": "600"})
        assert (b["width"], b["height"]) == (800, 600), b
        # ảnh hỏng: không chặn việc gửi, vẫn 0x0 như trước
        b = send("20001", "user", b"\xff\xd8\xff\xe0FAKEJPEGDATA", "e.jpg", "image/jpeg")
        assert (b["width"], b["height"]) == (0, 0), b
        httpd.shutdown()
    finally:
        mock.stop()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, e)
    print("ALL IMAGE SIZE TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
