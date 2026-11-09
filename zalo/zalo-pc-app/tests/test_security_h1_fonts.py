"""H1 — path traversal qua /fonts/ (public, khong can dang nhap).

GET /fonts/../../../../... tra noi dung file ngoai thu muc fonts
(truoc khi sua: _serve_static noi STATIC_DIR + name ma khong kiem
tra, xem zalo_pc_app/server.py). Test chay offline: server that tren
loopback, khong can tai khoan Zalo (chi dung tai khoan phu neu test
live — dot nay chi mock).

Do-truoc-xanh-sau: cac test traversal PHAI DO truoc khi sua va XANH
sau khi sua; cac test font hop le XANH ca truoc va sau (khong vo
chuc nang dung).
"""

import os
import socket
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

tmp = tempfile.mkdtemp(prefix="zalo-pc-h1-fonts-test-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_APP_USER"] = "nguoi-dung-test"
os.environ["ZALO_PC_APP_PASSWORD"] = "mat-khau-test-123"
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import server as app_server  # noqa: E402

BASE = ""
MARKER = "H1-MARKER-SECRET-9f3a7c"

# Marker nam NGOAI thu muc fonts, o 2 do sau khac nhau:
# (a) ngay ben canh STATIC_DIR, (b) trong DATA_DIR tam.
MARKER_SIBLING = os.path.join(os.path.dirname(app_server.STATIC_DIR),
                              "h1-marker-secret.txt")
MARKER_DEEP = os.path.join(tmp, "marker-deep.txt")
for _path in (MARKER_SIBLING, MARKER_DEEP):
    with open(_path, "w") as _f:
        _f.write(MARKER + "\n")


def _get_raw(path):
    """GET voi request-target gui nguyen van qua socket tho.
    (http.client/urllib chuan hoa `..` phia client nen khong dung
    de kiem traversal; curl cung vay neu khong --path-as-is.)
    Doc phan hoi theo Content-Length."""
    host, port = BASE.rsplit(":", 1)
    sock = socket.create_connection((host.replace("http://", ""),
                                     int(port)), timeout=10)
    try:
        sock.sendall(("GET %s HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                      "Connection: close\r\n\r\n" % path).encode("ascii"))
        raw = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            raw += chunk
    finally:
        sock.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    status = int(lines[0].split()[1])
    ctype = ""
    for line in lines[1:]:
        if line.lower().startswith("content-type:"):
            ctype = line.split(":", 1)[1].strip()
    return status, body, ctype


def _assert_blocked(path):
    """Duong traversal/bi encode phai bi chan: 404/403, khong tra
    noi dung file, khong lo duong dan that trong thong bao loi."""
    status, body, _ctype = _get_raw(path)
    assert status in (403, 404), (path, status, body[:200])
    assert MARKER.encode() not in body, path
    # Khong lo duong dan that (vi du /tmp/... hay duong dan repo).
    assert tmp.encode() not in body, path
    assert b"h1-marker-secret" not in body, path


def test_fonts_traversal_plain():
    """(1) ../ tho va ../ sau deu bi chan. Chu y: URL tinh tu
    fonts/ (sau hon STATIC_DIR 1 cap): can 2x `..` moi ra khoi
    static/, vi du fonts/../../<file> moi toi zalo_pc_app/."""
    fonts_dir = os.path.join(app_server.STATIC_DIR, "fonts")
    # 2 cap: fonts/.. -> static/, .. -> zalo_pc_app/, noi co marker.
    _assert_blocked("/fonts/../../h1-marker-secret.txt")
    # Nhieu cap: tu fonts/ ra toi DATA_DIR tam.
    rel = os.path.relpath(MARKER_DEEP, fonts_dir)
    rel = rel.replace(os.sep, "/")
    assert rel.startswith("../"), rel
    _assert_blocked("/fonts/" + rel)


def test_fonts_traversal_encoded():
    """(2) Bien the encode deu bi chan (ke ca double-encode).
    Can 2 cap `..` moi ra khoi static/ toi marker (xem tren)."""
    _assert_blocked("/fonts/..%2f..%2fh1-marker-secret.txt")
    _assert_blocked("/fonts/%2e%2e%2f%2e%2e%2fh1-marker-secret.txt")
    _assert_blocked("/fonts/%2e%2e/%2e%2e/h1-marker-secret.txt")
    _assert_blocked("/fonts/....//....//h1-marker-secret.txt")
    _assert_blocked("/fonts/%252e%252e%252f%252e%252e%252fh1-marker-secret.txt")
    # Null byte: khong 500, khong tra noi dung.
    status, body, _ctype = _get_raw("/fonts/%00")
    assert status in (403, 404), (status, body[:200])
    assert MARKER.encode() not in body


def test_fonts_cannot_escape_to_other_static():
    """File hop le o thu muc static khac (style.css) khong duoc phep
    lay qua /fonts/ — chi file trong fonts/ moi duoc serve."""
    _assert_blocked("/fonts/../style.css")
    _assert_blocked("/fonts/%2e%2e%2fstyle.css")
    # File khong phai font dat TRONG fonts/ cung khong duoc serve.
    evil = os.path.join(app_server.STATIC_DIR, "fonts", "evil.txt")
    try:
        with open(evil, "w") as f:
            f.write(MARKER + "\n")
        status, body, _ctype = _get_raw("/fonts/evil.txt")
        assert status in (403, 404), (status, body[:200])
        assert MARKER.encode() not in body
    finally:
        if os.path.exists(evil):
            os.remove(evil)


def test_fonts_valid_still_served():
    """(3) File font hop le trong thu muc van serve duoc 200."""
    name = "ibmplexsans-400-latin.woff2"
    with open(os.path.join(app_server.STATIC_DIR, "fonts", name),
              "rb") as f:
        expected = f.read()
    status, body, ctype = _get_raw("/fonts/" + name)
    assert status == 200, (status, body[:200])
    assert ctype == "font/woff2", ctype
    assert body == expected


def test_fonts_valid_subdir_still_served():
    """(4) Duong con hop le trong fonts/ (fonts/sub/font.woff2)
    van dung — chi chan duong RA NGOAI fonts/."""
    sub = os.path.join(app_server.STATIC_DIR, "fonts", "sub")
    os.makedirs(sub, exist_ok=True)
    font = os.path.join(sub, "h1-test.woff2")
    try:
        with open(font, "wb") as f:
            f.write(b"\x77\x4f\x46\x32h1-test")
        status, body, ctype = _get_raw("/fonts/sub/h1-test.woff2")
        assert status == 200, (status, body[:200])
        assert ctype == "font/woff2", ctype
        assert body == b"\x77\x4f\x46\x32h1-test"
    finally:
        if os.path.exists(font):
            os.remove(font)
        if os.path.isdir(sub):
            os.rmdir(sub)


def _start_server():
    global BASE
    app_server.STATE = app_server.AppState(tmp)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    BASE = "http://127.0.0.1:%d" % port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _stop_server(httpd):
    httpd.shutdown()
    httpd.server_close()
    for _path in (MARKER_SIBLING, MARKER_DEEP):
        if os.path.exists(_path):
            os.remove(_path)


try:
    import pytest
except ImportError:  # chay kieu script: khong can pytest
    pytest = None

if pytest is not None:
    # De pytest (python3 -m pytest tests/ -q) chay duoc ma khong
    # can _run_all(): server khoi dong 1 lan cho ca module.
    @pytest.fixture(scope="module", autouse=True)
    def _h1_server():
        httpd = _start_server()
        try:
            yield
        finally:
            _stop_server(httpd)


def _run_all():
    httpd = _start_server()
    try:
        test_fonts_traversal_plain()
        print("PASS test_fonts_traversal_plain")
        test_fonts_traversal_encoded()
        print("PASS test_fonts_traversal_encoded")
        test_fonts_cannot_escape_to_other_static()
        print("PASS test_fonts_cannot_escape_to_other_static")
        test_fonts_valid_still_served()
        print("PASS test_fonts_valid_still_served")
        test_fonts_valid_subdir_still_served()
        print("PASS test_fonts_valid_subdir_still_served")
        print("ALL H1 FONTS TESTS PASSED")
    finally:
        _stop_server(httpd)


if __name__ == "__main__":
    _run_all()
