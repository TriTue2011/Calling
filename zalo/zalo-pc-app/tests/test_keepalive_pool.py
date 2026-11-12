"""Poller giu ket noi song (keep-alive): hai lan hoi lien tiep chi mo MOT ket noi; ket noi cu bi server dong thi tu mo lai mot lan.

Chay: python3 tests/test_keepalive_pool.py (kieu CI cua repo: khoi __main__ in PASSED, khong dung pytest).
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import server as app_server  # noqa: E402


class _H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.server.requests += 1
        body = json.dumps({"ok": True, "path": self.path, "cookie": self.headers.get("Cookie", "")}).encode()
        code = 404 if self.path.startswith("/missing") else 200
        if self.path.startswith("/nojson"):
            body, code = b"khong phai json", 200
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        if self.server.close_after:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        if self.server.drop_after:             # dong ket noi NGAY SAU phan hoi nhung KHONG bao Connection: close (server dong ket noi nhan roi)
            self.close_connection = True


def _server(close_after=False, drop_after=False):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    srv.requests, srv.close_after, srv.drop_after, srv.conns = 0, close_after, drop_after, 0
    orig = srv.get_request

    def counting():
        srv.conns += 1
        return orig()
    srv.get_request = counting
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_two_polls_share_one_connection():
    srv = _server()
    try:
        t = app_server.make_transport("COOKIE123", keepalive=True)
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        for i in range(3):
            status, body = t.http_get(base + "/poll?i=%d" % i, timeout=5)
            assert status == 200 and body["ok"] is True and "COOKIE123" in body["cookie"], (status, body)
        assert srv.conns == 1 and srv.requests == 3, (srv.conns, srv.requests)
    finally:
        srv.shutdown()


def test_server_closed_idle_connection_is_reopened_once():
    srv = _server(drop_after=True)
    try:
        t = app_server.make_transport("", keepalive=True)
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        for i in range(3):
            status, body = t.http_get(base + "/poll?i=%d" % i, timeout=5)
            assert status == 200 and body["ok"] is True, (status, body)
        assert srv.requests == 3 and srv.conns == 3, (srv.conns, srv.requests)      # moi lan ket noi cu chet -> mo lai dung mot lan, khong loi
    finally:
        srv.shutdown()


def test_status_codes_and_non_json_match_the_urllib_path():
    srv = _server(close_after=True)
    try:
        t = app_server.make_transport("", keepalive=True)
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        status, body = t.http_get(base + "/missing", timeout=5)
        assert status == 404 and isinstance(body, dict), (status, body)
        try:
            t.http_get(base + "/nojson", timeout=5)
            raise AssertionError("phai nem NonJsonResponse")
        except app_server.sync_poll_mod.NonJsonResponse as e:
            assert e.status == 200, e.status
        assert srv.conns == 2, srv.conns                         # server bao Connection: close -> khong giu lai
    finally:
        srv.shutdown()


def test_default_transport_is_unchanged():
    t = app_server.make_transport("x")
    assert t.keepalive is False
    t2 = app_server.make_transport("x", keepalive=True)
    assert t2.keepalive is True


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("KEEPALIVE POOL TESTS PASSED")
