"""Gửi VIDEO có chú thích như Zalo PC + chuyển tiếp tệp kèm ttl của hội thoại đích (14/11/2026).
- tệp video chọn từ WebUI -> tin video (tải lên Zalo, ảnh bìa, thời lượng, chú thích), lỗi thì quay về tệp thường;
- chuyển tiếp tệp/ảnh sang hội thoại bật tự xóa phải kèm ttl (thiếu: Zalo báo «phiên bản chưa hỗ trợ Tin nhắn tự xóa»).
Run: python3 tests/test_video_caption_send.py"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mock_server import MockZalo, TEST_PARAM_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import conv_ttl as conv_ttl_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import video_probe as vp  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"FAKEJPEG" * 20
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200


def test_probe_video_bytes_reads_size_duration_rotation_and_makes_thumb():
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[0])
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"streams": [{"width": 1920, "height": 1080, "tags": {"rotate": "90"}}], "format": {"duration": "6.338"}}), stderr="")
        with open(cmd[-1], "wb") as fh:
            fh.write(b"J" * 500)
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
    out = vp.probe_video_bytes(MP4, "cam.mp4", run=fake_run)
    assert (out["width"], out["height"], out["duration_ms"]) == (1080, 1920, 6338) and out["thumb"] == b"J" * 500, out    # quay 90°: đổi chỗ rộng/cao
    assert calls == ["ffprobe", "ffmpeg"]


def test_probe_video_bytes_never_raises_when_tools_missing():
    def boom(cmd, **kw):
        raise FileNotFoundError(cmd[0])
    assert vp.probe_video_bytes(MP4, "x.mp4", run=boom) == {}
    assert vp.is_video_name("A.MP4") and vp.is_video_name("b.mov") and not vp.is_video_name("c.jpg") and not vp.is_video_name("")


def test_send_video_file_uploads_video_then_thumb_then_sends_video_with_caption():
    c = object.__new__(chat_mod.Chat)
    log = []

    def up(tt, tid, name, data):
        log.append(("up", name, len(data)))
        return {"file_url": "https://cdn.example/" + name}
    c._upload_async = up
    c.send_video = lambda tt, tid, vu, tu, dur, w, h, msg, ttl: log.append(("send", vu, tu, dur, w, h, msg, ttl)) or {"data": {"msgId": "1"}, "client_id": 7}
    res = c.send_video_file("group", "30001", "cam.mp4", MP4, caption="🔔 Phát hiện chuyển động!", width=640, height=480, duration_ms=6338, ttl=86400000, thumb_jpeg=JPEG)
    assert log == [("up", "cam.mp4", len(MP4)), ("up", "thumb.jpg", len(JPEG)),
                   ("send", "https://cdn.example/cam.mp4", "https://cdn.example/thumb.jpg", 6338, 640, 480, "🔔 Phát hiện chuyển động!", 86400000)], log
    assert res["video_url"] == "https://cdn.example/cam.mp4" and res["client_id"] == 7
    # tải ảnh bìa lỗi: vẫn gửi video (bìa rỗng)
    log.clear()

    def up2(tt, tid, name, data):
        if name == "thumb.jpg":
            raise chat_mod.ZaloChatError("x")
        return {"file_url": "https://cdn.example/" + name}
    c._upload_async = up2
    c.send_video_file("user", "5", "a.mp4", MP4, thumb_jpeg=JPEG)
    assert log[-1][0] == "send" and log[-1][2] == "", log


BASE = ""


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_routes_send_video_with_caption_fallback_to_file_and_forward_with_ttl():
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-vcap-")
    rec = {}
    orig = {n: getattr(chat_mod.Chat, n) for n in ("send_video_file", "send_file", "send_photo")}
    try:
        for mod, names in ((protocol, ("AUTH_DOMAIN", "VOICECALL_DOMAIN", "PROFILE_DOMAIN", "GROUP_DOMAIN")), (chat_mod, ("CHAT_DOMAIN", "FILES_DOMAIN", "GROUP_DOMAIN"))):
            for n in names:
                setattr(mod, n, mock.base)
        app_server.STATE = app_server.AppState(tmp)
        app_server.STATE.conv_ttl = conv_ttl_mod.ConvTtl(lambda: {"30001": 86400000})
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
        app_server.video_probe_mod.probe_video_bytes = lambda data, name, **k: {"width": 640, "height": 480, "duration_ms": 6338, "thumb": JPEG}

        def fake_video(self, tt, tid, name, data, caption="", width=0, height=0, duration_ms=0, ttl=0, thumb_jpeg=None):
            rec["video"] = dict(tt=tt, tid=tid, name=name, caption=caption, w=width, h=height, dur=duration_ms, ttl=ttl, thumb=bool(thumb_jpeg))
            return {"data": {"msgId": "9"}, "client_id": 111}
        chat_mod.Chat.send_video_file = fake_video
        mb, ct = chat_mod.build_multipart({"type": "group", "kind": "file", "desc": "🔔 Phát hiện chuyển động!"}, [("file", "cam.mp4", "video/mp4", MP4)])
        st, body = api("POST", "/api/thread/30001/sendfile", mb, {"Content-Type": ct})
        assert st == 200 and body["message"]["kind"] == "video", (st, body)
        assert rec["video"] == dict(tt="group", tid="30001", name="cam.mp4", caption="🔔 Phát hiện chuyển động!", w=640, h=480, dur=6338, ttl=86400000, thumb=True), rec
        # lỗi tải lên -> quay về gửi tệp thường
        def bad_video(self, *a, **k):
            raise chat_mod.ZaloChatError("het gio cho file_done")
        chat_mod.Chat.send_video_file = bad_video
        chat_mod.Chat.send_file = lambda self, tt, tid, name, data, mime="", ttl=0: rec.setdefault("file", []).append((tt, tid, name, ttl)) or {"data": {"msgId": "8"}, "client_id": 112}
        st, body = api("POST", "/api/thread/30001/sendfile", mb, {"Content-Type": ct})
        assert st == 200 and body["message"]["kind"] == "file" and rec["file"] == [("group", "30001", "cam.mp4", 86400000)], (st, body, rec)
        # chuyển tiếp: tệp thường + ảnh sang hội thoại bật tự xóa phải kèm ttl; ảnh gửi như ảnh
        box = app_server.STATE.file_inbox
        box.save_local("user", "20001", "f1", "bao-cao.pdf", b"%PDF-1.4 " + b"x" * 50)
        box.save_local("user", "20001", "p1", "a.jpg", JPEG)
        chat_mod.Chat.send_photo = lambda self, tt, tid, name, data, mime="", w=0, h=0, visibility=0, desc="", photo_bundle=None, ttl=0: rec.setdefault("photo", []).append((tt, tid, name, ttl)) or {"data": {"msgId": "7"}, "client_id": 113}
        for mid in ("f1", "p1"):
            st, body = api("POST", "/api/file/forward", json.dumps({"thread_type": "user", "thread_id": "20001", "msg_id": mid, "to_thread_type": "group", "to_thread_id": "30001"}).encode(), {"Content-Type": "application/json"})
            assert st == 200 and body["ok"], (st, body)
        assert rec["file"][-1] == ("group", "30001", "bao-cao.pdf", 86400000), rec["file"]
        assert rec["photo"] == [("group", "30001", "a.jpg", 86400000)], rec.get("photo")
        # hội thoại đích KHÔNG bật tự xóa: ttl 0
        api("POST", "/api/file/forward", json.dumps({"thread_type": "user", "thread_id": "20001", "msg_id": "f1", "to_thread_type": "user", "to_thread_id": "55555"}).encode(), {"Content-Type": "application/json"})
        assert rec["file"][-1] == ("user", "55555", "bao-cao.pdf", 0), rec["file"]
        httpd.shutdown()
    finally:
        for n, f in orig.items():
            setattr(chat_mod.Chat, n, f)
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
                print("FAIL", name, type(e).__name__, str(e)[:300])
    print("ALL VIDEO CAPTION SEND TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
