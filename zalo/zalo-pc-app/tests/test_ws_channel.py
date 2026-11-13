"""Kênh WebSocket: client RFC 6455, giải mã sự kiện, bộ nghe (dự phòng/thử lại/trùng kết nối), chống trùng. Không gọi Zalo thật.
Chạy: python3 tests/test_ws_channel.py"""
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import event_dedup, ws_client, ws_events, ws_listener  # noqa: E402

KEY = base64.b64encode(bytes(range(16))).decode()


# ------------------------------------------------------------------ máy chủ WebSocket giả (socket thật)
class MockServer:
    def __init__(self, script, status="101 Switching Protocols", bad_accept=False):
        self.script, self.status, self.bad_accept = script, status, bad_accept
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.requests = []                     # tiêu đề bắt tay đã nhận
        self.client_frames = []                # (opcode, masked, payload) máy chủ nhận được
        self.connections = 0
        threading.Thread(target=self._accept, daemon=True).start()

    def url(self, path="/"):
        return "ws://127.0.0.1:%d%s" % (self.port, path)

    def _accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            raw = b""
            while b"\r\n\r\n" not in raw:
                raw += conn.recv(4096)
            head = raw.split(b"\r\n\r\n")[0].decode()
            hdrs = {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in head.split("\r\n")[1:]}
            self.requests.append((head.split("\r\n")[0], hdrs))
            acc = base64.b64encode(hashlib.sha1((hdrs["sec-websocket-key"] + ws_client.GUID).encode()).digest()).decode()
            if self.bad_accept:
                acc = "sai"
            conn.sendall(("HTTP/1.1 %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % (self.status, acc)).encode())
            if not self.status.startswith("101"):
                return
            self.script(self, conn)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # trợ giúp cho kịch bản
    @staticmethod
    def frame(op, payload=b"", fin=True):
        n = len(payload)
        head = bytes([(0x80 if fin else 0) | op])
        if n < 126:
            head += bytes([n])
        elif n < 65536:
            head += bytes([126]) + struct.pack(">H", n)
        else:
            head += bytes([127]) + struct.pack(">Q", n)
        return head + payload

    def read_client_frame(self, conn, timeout=3):
        conn.settimeout(timeout)
        h = conn.recv(2)
        if len(h) < 2:
            return None
        op, masked, n = h[0] & 15, bool(h[1] & 0x80), h[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", conn.recv(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", conn.recv(8))[0]
        mask = conn.recv(4) if masked else b""
        data = b""
        while len(data) < n:
            data += conn.recv(n - len(data))
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.client_frames.append((op, masked, data))
        return op, data

    def close(self):
        self.sock.close()


def _hello(conn, key=KEY):
    conn.sendall(MockServer.frame(2, ws_events.encode_frame(1, 1, 1, {"key": key})))


# ------------------------------------------------------------------ client
def test_client_handshake_headers_text_binary_fragments_ping_pong_and_masking():
    def script(srv, conn):
        conn.sendall(MockServer.frame(1, "xin chào".encode()))
        conn.sendall(MockServer.frame(2, b"\x01\x02\x03"))
        conn.sendall(MockServer.frame(2, b"AAA", fin=False) + MockServer.frame(0, b"BBB", fin=False) + MockServer.frame(0, b"CCC", fin=True))   # ghép mảnh
        conn.sendall(MockServer.frame(9, b"hi"))                                                                                               # máy chủ ping
        conn.sendall(MockServer.frame(2, b"x" * 70000))                                                                                         # khung dài 64-bit
        srv.read_client_frame(conn)
        srv.read_client_frame(conn)
        srv.read_client_frame(conn)
        time.sleep(0.3)
    srv = MockServer(script)
    c = ws_client.WsClient(srv.url("/ws?zpw_ver=1"), headers={"Origin": "https://chat.zalo.me", "Cookie": "zpw_sek=bimat"})
    c.connect()
    assert srv.requests[0][0] == "GET /ws?zpw_ver=1 HTTP/1.1"
    h = srv.requests[0][1]
    assert h["origin"] == "https://chat.zalo.me" and h["cookie"] == "zpw_sek=bimat" and h["sec-websocket-version"] == "13"
    assert "sec-websocket-extensions" not in h                                       # không xin nén permessage-deflate
    assert c.recv(2) == ("text", "xin chào")
    assert c.recv(2) == ("binary", b"\x01\x02\x03")
    assert c.recv(2) == ("binary", b"AAABBBCCC")
    assert c.recv(2) == ("binary", b"x" * 70000)                                     # ping đã được trả lời ngầm ở giữa
    c.send_binary(b"\x09" * 200)
    c.send_ping(b"p")
    time.sleep(0.3)
    ops = [(op, masked) for op, masked, _ in srv.client_frames]
    assert (10, True) in ops and (2, True) in ops and (9, True) in ops, ops           # pong, nhị phân, ping: TẤT CẢ có mặt nạ
    assert [d for op, _m, d in srv.client_frames if op == 10] == [b"hi"]
    c.close()
    srv.close()


def test_client_partial_frame_across_timeouts_close_frame_and_errors():
    def script(srv, conn):
        full = MockServer.frame(1, b"mot-khung-day-du")
        conn.sendall(full[:5])
        time.sleep(0.5)
        conn.sendall(full[5:])
        time.sleep(0.1)
        conn.sendall(MockServer.frame(8, struct.pack(">H", 3000) + "trung".encode()))
        time.sleep(0.3)
    srv = MockServer(script)
    c = ws_client.WsClient(srv.url())
    c.connect()
    assert c.recv(0.2) is None                                                        # chưa đủ khung: hết giờ, KHÔNG mất byte đã nhận
    assert c.recv(3) == ("text", "mot-khung-day-du")
    assert c.recv(3) == ("close", (3000, "trung")) and not c.connected
    try:
        c.recv(0.1)
    except ws_client.WsError:
        pass
    else:
        raise AssertionError("sau khi dong phai bao loi")
    srv.close()
    for kwargs, msg in (({"bad_accept": True}, "Accept"), ({"status": "403 Forbidden"}, "tu choi")):
        bad = MockServer(lambda s, cn: None, **kwargs)
        try:
            ws_client.WsClient(bad.url()).connect()
        except ws_client.WsError as exc:
            assert msg in str(exc), str(exc)
        else:
            raise AssertionError(kwargs)
        bad.close()
    for url in ("http://x/", "ws://", ""):
        try:
            ws_client.WsClient(url).connect()
        except ws_client.WsError:
            pass
        else:
            raise AssertionError(url)
    try:
        ws_client.WsClient("ws://127.0.0.1:1/").connect()                             # cổng đóng
    except ws_client.WsError:
        pass
    else:
        raise AssertionError("phai bao loi khi cong dong")


# ------------------------------------------------------------------ giải mã sự kiện
def test_frame_roundtrip_and_all_four_encrypt_types_with_tamper_and_missing_key():
    raw = ws_events.encode_frame(1, 501, 0, {"data": "x", "encrypt": 0})
    assert raw[:4] == bytes([1, 0xF5, 0x01, 0]) and ws_events.parse_frame(raw)[:3] == (1, 501, 0)       # cmd little-endian 2 byte
    assert ws_events.parse_frame(bytes([1, 2, 0, 1]))[3] is None                                          # không có thân
    assert ws_events.parse_frame(bytes([1, 2, 0, 1]) + b"khong json")[3] is None
    try:
        ws_events.parse_frame(b"abc")
    except ValueError:
        pass
    else:
        raise AssertionError("khung ngan")
    payload = {"data": {"msgs": [{"msgId": "1", "content": "chào ❤", "ts": 12345678901234567}]}}
    for enc in (0, 1, 2, 3):
        parsed = ws_events.encode_event_for_tests(payload, KEY, enc)
        assert parsed["encrypt"] == enc
        assert ws_events.decode_event(parsed, KEY) == payload, enc
        assert ws_events.event_payload(ws_events.decode_event(parsed, KEY)) == payload["data"]
    p2 = ws_events.encode_event_for_tests(payload, KEY, 2)
    other_key = base64.b64encode(bytes(range(1, 17))).decode()
    for args in ((p2, other_key), (p2, None), (p2, ""), ({"data": "toi-ngan", "encrypt": 2}, KEY), ({"data": 5, "encrypt": 0}, KEY),
                 ({"data": "x", "encrypt": 9}, KEY), ({"data": "x", "encrypt": True}, KEY), ({"data": "@@@", "encrypt": 1}, KEY), (None, KEY), ({"encrypt": 0}, KEY)):
        try:
            ws_events.decode_event(*args)
        except ValueError:
            pass
        else:
            raise AssertionError(args)
    assert ws_events.event_payload(None) == {} and ws_events.event_payload({"data": "chuoi"}) == {}
    assert [ws_events.route(c) for c in (501, 551, 521, 601, 612, 502, 3000, 1)] == ["sync", "sync", "sync", "ctrl", "ctrl", None, None, None]


# ------------------------------------------------------------------ chống trùng
def test_event_dedup_drops_only_when_check_is_on_and_expires():
    clock = [1000.0]
    d = event_dedup.EventDedup(ttl=60, clock=lambda: clock[0])
    batch = {"msgs": [{"id": 1}, {"id": 2}], "controls": [{"a": 1}], "queueStatus": {"x": 1}}
    first = d.filter(batch, check=True)
    assert first["msgs"] == batch["msgs"] and first["queueStatus"] == {"x": 1}              # lần đầu: giữ hết
    again = d.filter(batch, check=True)
    assert again["msgs"] == [] and again["controls"] == [] and d.dropped == 3                 # lần hai: trùng hết
    assert d.filter(batch, check=False)["msgs"] == batch["msgs"]                              # check tắt: KHÔNG bỏ gì (đường poll khi không có WS)
    mixed = d.filter({"msgs": [{"id": 2}, {"id": 3}]}, check=True)
    assert mixed["msgs"] == [{"id": 3}]
    clock[0] += 61
    assert d.filter(batch, check=True)["msgs"] == batch["msgs"]                               # quá TTL: coi như mới
    assert batch["msgs"] == [{"id": 1}, {"id": 2}]                                            # không sửa dữ liệu gốc
    assert d.filter("khong phai dict", True) == "khong phai dict" and d.filter({"msgs": "x"}, True) == {"msgs": "x"}
    assert d.seen("k") is False and d.seen("k") is True


# ------------------------------------------------------------------ bộ nghe với client giả
class FakeClient:
    """Mỗi lần dựng lấy một kịch bản: list các bước ("frame", bytes) | ("pong",) | ("close", code) | ("raise", exc) | ("idle",)."""
    scripts = []
    made = []

    def __init__(self, url, headers=None):
        self.url, self.headers = url, headers
        self.steps = list(FakeClient.scripts.pop(0)) if FakeClient.scripts else [("idle",)]
        self.sent = []
        self.connected = False
        FakeClient.made.append(self)

    def connect(self):
        step = self.steps[0] if self.steps else None
        if step and step[0] == "connect_fail":
            self.steps.pop(0)
            raise ws_client.WsError("khong noi duoc")
        self.connected = True

    def recv(self, timeout=1.0):
        time.sleep(0.005)
        if not self.steps:
            return None
        step = self.steps.pop(0)
        if step[0] == "frame":
            return ("binary", step[1])
        if step[0] == "pong":
            return ("pong", b"")
        if step[0] == "close":
            return ("close", (step[1], "x"))
        if step[0] == "raise":
            raise step[1]
        if step[0] == "idle":
            self.steps.insert(0, step)
        return None

    def send_ping(self, payload=b""):
        self.sent.append("ping")

    def send_binary(self, data):
        self.sent.append(("bin", bytes(data)))

    def close(self, *a):
        self.connected = False


def _f(cmd, sub, parsed):
    body = json.dumps(parsed).encode() if parsed is not None else b""
    return ws_events.HEADER.pack(1, cmd, sub) + body


def _listener(events, **kw):
    kw.setdefault("backoff", (0.02, 0.04))
    kw.setdefault("standdown", 0.05)
    return ws_listener.WsListener(["wss://ws1.example/?a=1", "wss://ws2.example/"], "zpw_sek=bimat", "ua/1", lambda t, d: events.append((t, d)), 695, 30, ping_seconds=5, log=lambda m: None, **kw)


def _wait(fn, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.01)
    raise AssertionError("het gio cho dieu kien")


def test_listener_routes_events_decodes_counts_and_survives_bad_frames():
    FakeClient.scripts, FakeClient.made = [[
        ("frame", _f(1, 1, {"key": KEY})),
        ("frame", _f(501, 0, ws_events.encode_event_for_tests({"data": {"msgs": [{"msgId": "m1"}]}}, KEY, 2))),
        ("frame", _f(601, 0, ws_events.encode_event_for_tests({"data": {"controls": [{"content": {"act_type": "voip"}}]}}, KEY, 3))),
        ("frame", _f(521, 0, ws_events.encode_event_for_tests({"data": {"groupMsgs": [{"msgId": "g1"}]}}, KEY, 1))),
        ("frame", _f(612, 0, ws_events.encode_event_for_tests({"data": {"reacts": [{"x": 1}]}}, KEY, 0))),
        ("frame", _f(502, 0, {"data": "bo qua", "encrypt": 0})),                   # cmd không định tuyến: chỉ đếm
        ("frame", _f(501, 0, {"data": "@@khong-giai-ma-duoc", "encrypt": 2})),     # hỏng: đếm lỗi, không đứt kênh
        ("frame", b"ab"),                                                           # ngắn hơn 4 byte
        ("frame", _f(501, 0, ws_events.encode_event_for_tests({"data": {}}, KEY, 2))),   # dữ liệu rỗng: bỏ qua
        ("pong",), ("idle",)]], []
    events = []
    L = _listener(events, client_factory=FakeClient)
    assert L.start()
    _wait(lambda: len(events) >= 4 and L.decode_errors >= 2 and L.status()["events"].get(502))
    st = L.status()
    assert [e[0] for e in events] == ["sync", "ctrl", "sync", "ctrl"]
    assert events[0][1] == {"msgs": [{"msgId": "m1"}]} and events[1][1]["controls"][0]["content"]["act_type"] == "voip"
    assert st["state"] == "connected" and st["routed"] == {"sync": 2, "ctrl": 2} and st["events"][502] == 1
    assert st["decode_errors"] >= 2 and st["active"] is True
    c = FakeClient.made[0]
    assert c.headers["Origin"] == "https://chat.zalo.me" and c.headers["Cookie"] == "zpw_sek=bimat" and c.url.startswith("wss://ws1.example/?a=1&zpw_ver=695&zpw_type=30&t=")
    L.stop()
    assert L.state == "idle"


def test_listener_on_event_exception_does_not_kill_the_channel():
    FakeClient.scripts, FakeClient.made = [[("frame", _f(1, 1, {"key": KEY})),
                                            ("frame", _f(501, 0, ws_events.encode_event_for_tests({"data": {"msgs": [1]}}, KEY, 2))),
                                            ("frame", _f(501, 0, ws_events.encode_event_for_tests({"data": {"msgs": [2]}}, KEY, 2))), ("idle",)]], []
    seen = []

    def boom(t, d):
        seen.append(d)
        raise RuntimeError("xu ly loi")
    L = ws_listener.WsListener(["wss://a/"], "c", "ua", boom, 695, 30, ping_seconds=5, log=lambda m: None, client_factory=FakeClient)
    L.start()
    _wait(lambda: len(seen) == 2)                                                   # sự kiện thứ hai vẫn tới sau khi sự kiện đầu làm callback ném lỗi
    assert L.state == "connected" and "xu ly su kien" in L.last_error
    L.stop()


def test_listener_reconnects_with_backoff_rotates_url_and_recovers():
    FakeClient.scripts, FakeClient.made = [[("connect_fail",)], [("frame", _f(1, 1, {"key": KEY})), ("raise", ws_client.WsError("rot mang"))],
                                           [("frame", _f(1, 1, {"key": KEY})), ("idle",)]], []
    L = _listener([], client_factory=FakeClient)
    L.start()
    _wait(lambda: L.state == "connected" and len(FakeClient.made) == 3)
    assert [c.url.split("/")[2] for c in FakeClient.made] == ["ws1.example", "ws2.example", "ws1.example"]   # xoay địa chỉ mỗi lần lỗi
    assert L.reconnects == 2 and "rot mang" in L.last_error
    L.stop()


def test_listener_duplicate_connection_stands_down_then_retries_and_gives_up_after_three():
    FakeClient.scripts, FakeClient.made = [[("frame", _f(1, 1, {"key": KEY})), ("close", 3000)], [("frame", _f(3000, 0, None))],
                                           [("frame", _f(1, 1, {"key": KEY})), ("close", 3000)]], []
    L = _listener([], client_factory=FakeClient)
    L.start()
    _wait(lambda: L.state == "disabled")
    assert len(FakeClient.made) == 3 and L.duplicates == 3 and L.last_close["code"] == 3000        # 3 lần trùng liên tiếp: tắt hẳn (poll vẫn chạy)
    L.stop()
    FakeClient.scripts, FakeClient.made = [[("frame", _f(1, 1, {"key": KEY})), ("close", 3000)], [("frame", _f(1, 1, {"key": KEY})), ("idle",)]], []
    L2 = _listener([], client_factory=FakeClient)
    L2.start()
    _wait(lambda: L2.state == "connected" and len(FakeClient.made) == 2)                              # sau khi nhường thì thử lại và nối được
    assert L2.duplicates == 1
    L2.stop()
    FakeClient.scripts, FakeClient.made = [[("frame", _f(1, 1, {"key": KEY})), ("close", 3003)]], []
    L3 = _listener([], client_factory=FakeClient)
    L3.start()
    _wait(lambda: L3.state == "disabled")
    assert len(FakeClient.made) == 1                                                                  # 3003 (bị đá): không thử lại
    L3.stop()


def test_listener_without_hello_key_gives_up_the_connection_and_active_goes_false_when_silent():
    FakeClient.scripts, FakeClient.made = [[("idle",)], [("frame", _f(1, 1, {"key": KEY})), ("idle",)]], []
    clock = [100.0]
    L = ws_listener.WsListener(["wss://a/"], "c", "ua", lambda t, d: None, 695, 30, ping_seconds=5, log=lambda m: None, client_factory=FakeClient,
                               backoff=(0.02,), clock=lambda: clock[0])
    L.start()
    _wait(lambda: len(FakeClient.made) >= 1)
    time.sleep(0.05)
    clock[0] += ws_listener.HELLO_TIMEOUT + 1                                                         # không nhận được khoá quá hạn
    _wait(lambda: len(FakeClient.made) >= 2 and L.state == "connected")
    assert L.active is True
    clock[0] += 5 * 2.5 + 1                                                                           # im lặng quá 2,5 nhịp: không còn «active» (poll thôi lọc trùng)
    assert L.active is False
    L.stop()
    empty = ws_listener.WsListener([], "c", "ua", lambda t, d: None, 695, 30, log=lambda m: None)
    assert empty.start() is False and empty.state == "disabled"
    assert ws_listener.WsListener(["http://sai/"], "c", "ua", lambda t, d: None, 695, 30).start() is False


def test_build_url_adds_version_type_and_timestamp_without_overriding():
    u = ws_listener.build_url("wss://ws1-msg.chat.zalo.me/?foo=1", 695, 30, now_ms=5)
    assert u == "wss://ws1-msg.chat.zalo.me/?foo=1&zpw_ver=695&zpw_type=30&t=5", u
    assert "zpw_ver=1" in ws_listener.build_url("wss://h/p?zpw_ver=1", 695, 30, now_ms=5)


# ------------------------------------------------------------------ đầu-cuối: bộ nghe thật + client thật + máy chủ giả
def test_end_to_end_real_socket_hello_events_ping_and_duplicate_close():
    def script(srv, conn):
        _hello(conn)
        conn.sendall(MockServer.frame(2, _f(501, 0, ws_events.encode_event_for_tests({"data": {"msgs": [{"msgId": "e2e"}]}}, KEY, 2))))
        end = time.time() + 6
        while time.time() < end:
            try:
                got = srv.read_client_frame(conn, timeout=0.5)
            except (socket.timeout, OSError):
                continue
            if got is None:
                return
            if got[0] == 9:
                conn.sendall(MockServer.frame(10, got[1]))
            if sum(1 for f in srv.client_frames if f[0] == 2) >= 1 and not getattr(srv, "closed_once", False):
                srv.closed_once = True
                time.sleep(0.2)
                conn.sendall(MockServer.frame(8, struct.pack(">H", 3000)))
                return
    srv = MockServer(script)
    events = []
    L = ws_listener.WsListener([srv.url("/")], "zpw_sek=bimat", "ua/1", lambda t, d: events.append((t, d)), 695, 30, ping_seconds=5, log=lambda m: None,
                               backoff=(0.05,), standdown=30)
    L._ping = 1.5                                                                                      # nhịp nhanh để test chạy nhanh (vòng nhận có độ phân giải 1 s)
    L.start()
    _wait(lambda: events, 5)
    assert events == [("sync", {"msgs": [{"msgId": "e2e"}]})] and L.state in ("connected", "standdown")
    _wait(lambda: L.state == "standdown", 8)                                                           # máy chủ đóng 3000: nhường, không giành kết nối
    assert L.duplicates == 1 and srv.connections == 1
    ops = [op for op, _m, _d in srv.client_frames]
    assert 9 in ops and 2 in ops                                                                       # đã gửi ping WebSocket và ping ứng dụng (cmd 2 sub 1)
    app_ping = [d for op, _m, d in srv.client_frames if op == 2][0]
    assert ws_events.parse_frame(app_ping)[:3] == (1, 2, 1) and "eventId" in ws_events.parse_frame(app_ping)[3]
    L.stop()
    srv.close()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL WS-CHANNEL TESTS PASSED")
