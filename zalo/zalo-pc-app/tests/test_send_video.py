"""Gửi VIDEO thật vào Zalo (13/11/2026) — chat.send_video theo zca-js sendVideo / zalo_bot cũ, đo bằng ffprobe, và lấy kích thước bằng HEAD.
Chạy: python3 tests/test_send_video.py"""
import http.server
import json
import os
import subprocess
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import video_probe  # noqa: E402

URL = "https://ha.example.test/media/local/snapshots/x_video.mp4?authSig=S"
THUMB = "https://ha.example.test/media/local/snapshots/x_thumb.jpg?authSig=S"


def make_chat(size=1584546):
    c = chat_mod.Chat(lambda *a, **k: (200, {}), "dev-1", "a" * 22 + "==")
    sent = []
    c._head_size = lambda url: size
    c._post_form_retry = lambda domain, path, body, where, **k: (sent.append((domain, path, body)), {"msgId": "m1"})[1]
    return c, sent


def test_group_video_payload_matches_zca_js():
    c, sent = make_chat()
    res = c.send_video("group", "3295299208151385728", URL, THUMB, duration=5500, width=640, height=360, message="Có người", ttl=86400000)
    domain, path, body = sent[0]
    assert domain == chat_mod.FILES_DOMAIN and path == "/api/group/forward", (domain, path)
    assert body["grid"] == "3295299208151385728" and body["visibility"] == 0 and "toId" not in body, body
    assert body["msgType"] == 5 and body["zsource"] == 704 and body["ttl"] == 86400000 and body["imei"] == "dev-1", body
    assert body["clientId"] == str(res["client_id"]) and isinstance(body["clientId"], str), body
    info = json.loads(body["msgInfo"])
    assert info["videoUrl"] == URL and info["thumbUrl"] == THUMB and info["duration"] == 5500, info
    assert (info["width"], info["height"], info["fileSize"], info["title"]) == (640, 360, 1584546, "Có người"), info
    assert info["properties"] == {"color": -1, "size": -1, "type": 1003, "subType": 0,
                                  "ext": {"sSrcType": -1, "sSrcStr": "", "msg_warning_type": 0}}, info
    assert res["data"]["msgId"] == "m1"


def test_user_video_uses_message_forward_and_defaults():
    c, sent = make_chat(size=0)
    c.send_video("user", "6643404425553198601", URL)
    _d, path, body = sent[0]
    info = json.loads(body["msgInfo"])
    assert path == "/api/message/forward" and body["toId"] == "6643404425553198601" and "grid" not in body and "visibility" not in body, (path, body)
    assert info["thumbUrl"] == URL, "không có ảnh bìa thì dùng chính địa chỉ video (zalo_bot cũ)"
    assert (info["width"], info["height"], info["duration"], body["ttl"]) == (1280, 720, 0, 0), (info, body)


def test_bad_arguments_never_reach_zalo():
    c, sent = make_chat()
    for args in (("user", "1", "file:///etc/passwd"), ("user", "1", "/media/x.mp4"), ("user", "1", ""), ("room", "1", URL), ("user", "1", URL, "ftp://x/t.jpg")):
        try:
            c.send_video(*args)
            raise AssertionError("phải ném ValueError: %r" % (args,))
        except ValueError:
            pass
    assert sent == [], sent


def test_empty_zalo_answer_is_an_error_not_success():
    c, _ = make_chat()
    c._post_form_retry = lambda *a, **k: {}
    try:
        c.send_video("group", "1", URL)
        raise AssertionError("data rỗng phải là lỗi")
    except chat_mod.ZaloChatError as e:
        assert "khong co ma tin" in str(e), e


class _H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _go(self, head):
        if self.path == "/ok.mp4":
            self.send_response(200); self.send_header("Content-Length", "1234"); self.end_headers()
        elif self.path == "/nohead.mp4":
            if head:
                self.send_response(405); self.end_headers()
            else:
                self.send_response(206); self.send_header("Content-Range", "bytes 0-0/9999"); self.send_header("Content-Length", "1"); self.end_headers(); self.wfile.write(b"x")
        else:
            self.send_response(403); self.end_headers()

    def do_HEAD(self):
        self._go(True)

    def do_GET(self):
        self._go(False)


def test_head_size_reads_length_falls_back_to_get_and_explains_http_errors():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        c = chat_mod.Chat(lambda *a, **k: (200, {}), "dev-1", "a" * 22 + "==")
        assert c._head_size(base + "/ok.mp4") == 1234
        assert c._head_size(base + "/nohead.mp4") == 9999, "HEAD bị 405 thì thử GET Range 0-0"
        try:
            c._head_size(base + "/het-han.mp4")
            raise AssertionError("HTTP 403 phải là lỗi rõ")
        except chat_mod.ZaloChatError as e:
            assert "HTTP 403" in str(e), e
    finally:
        srv.shutdown()


def _run(stdout, rc=0):
    return lambda cmd, **k: subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")


def test_probe_reads_size_duration_and_swaps_rotated_phone_video():
    out = json.dumps({"streams": [{"width": 640, "height": 360}], "format": {"duration": "5.52"}})
    assert video_probe.probe_video(URL, run=_run(out)) == {"width": 640, "height": 360, "duration_ms": 5520}
    rot = json.dumps({"streams": [{"width": 1920, "height": 1080, "side_data_list": [{"rotation": -90}]}], "format": {"duration": "2"}})
    assert video_probe.probe_video(URL, run=_run(rot)) == {"width": 1080, "height": 1920, "duration_ms": 2000}


def test_probe_failures_give_empty_never_raise():
    assert video_probe.probe_video(URL, run=_run("", rc=1)) == {}
    assert video_probe.probe_video(URL, run=_run("không phải json")) == {}
    assert video_probe.probe_video("file:///etc/passwd", run=_run("{}")) == {}, "chỉ http/https"

    def boom(cmd, **k):
        raise FileNotFoundError("ffprobe")
    assert video_probe.probe_video(URL, run=boom) == {}


def test_probe_uses_protocol_whitelist():
    seen = []
    video_probe.probe_video(URL, run=lambda cmd, **k: (seen.append(cmd), subprocess.CompletedProcess(cmd, 1, stdout="", stderr=""))[1])
    assert "-protocol_whitelist" in seen[0] and "http,https,tcp,tls,crypto" in seen[0], seen


if __name__ == "__main__":
    for _n, _f in list(globals().items()):
        if _n.startswith("test_"):
            _f()
            print("PASS", _n)
    print("PASSED")
