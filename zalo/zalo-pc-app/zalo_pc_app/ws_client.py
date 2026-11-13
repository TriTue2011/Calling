"""Client WebSocket tối giản (RFC 6455) bằng thư viện chuẩn: container không có `websockets` / `websocket-client`.

Chỉ làm đủ cho kênh nhận sự kiện của Zalo: bắt tay HTTP Upgrade (tiêu đề tuỳ chỉnh: Cookie, Origin, User-Agent), khung văn bản/nhị phân (có mặt nạ phía
client), ghép mảnh, tự trả lời ping, đóng lịch sự. KHÔNG hỗ trợ permessage-deflate (không xin nó trong bắt tay, máy chủ sẽ không nén).
Không in/ghi bất kỳ tiêu đề nào (Cookie chứa khoá phiên).
"""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct
import threading
from urllib.parse import urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 8, 9, 10


class WsError(Exception):
    """Lỗi kết nối / giao thức WebSocket."""


class WsClient:
    def __init__(self, url, headers=None, connect_timeout=15.0, ssl_context=None, max_message=8 * 1024 * 1024):
        self.url = url
        self.headers = dict(headers or {})
        self.connect_timeout = connect_timeout
        self._ssl_context = ssl_context
        self._max_message = max_message
        self._sock = None
        self._buf = bytearray()
        self._frag_op = None
        self._frag = bytearray()
        self._send_lock = threading.Lock()
        self._close_sent = False
        self.connected = False

    # -- bắt tay ---------------------------------------------------------------
    def connect(self):
        parts = urlsplit(self.url)
        if parts.scheme not in ("ws", "wss") or not parts.hostname:
            raise WsError("dia chi WebSocket khong hop le")
        port = parts.port or (443 if parts.scheme == "wss" else 80)
        path = (parts.path or "/") + (("?" + parts.query) if parts.query else "")
        try:
            sock = socket.create_connection((parts.hostname, port), timeout=self.connect_timeout)
            if parts.scheme == "wss":
                ctx = self._ssl_context or ssl.create_default_context()
                sock = ctx.wrap_socket(sock, server_hostname=parts.hostname)
        except (OSError, ssl.SSLError) as exc:
            raise WsError("khong noi duoc: %s" % type(exc).__name__) from exc
        self._sock = sock
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        host = parts.hostname + ((":%d" % parts.port) if parts.port else "")
        lines = ["GET %s HTTP/1.1" % path, "Host: %s" % host, "Upgrade: websocket", "Connection: Upgrade",
                 "Sec-WebSocket-Key: %s" % key, "Sec-WebSocket-Version: 13"]
        lines += ["%s: %s" % (k, v) for k, v in self.headers.items()]
        try:
            sock.settimeout(self.connect_timeout)
            sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
            raw = bytearray()
            while b"\r\n\r\n" not in raw:
                chunk = sock.recv(4096)
                if not chunk:
                    raise WsError("may chu dong ket noi luc bat tay")
                raw += chunk
                if len(raw) > 65536:
                    raise WsError("phan hoi bat tay qua dai")
        except (OSError, ssl.SSLError) as exc:
            self._drop()
            raise WsError("loi bat tay: %s" % type(exc).__name__) from exc
        head, _, rest = bytes(raw).partition(b"\r\n\r\n")
        status_line, *header_lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in status_line + " ":
            self._drop()
            raise WsError("bat tay bi tu choi: %s" % status_line[:40])
        hdrs = {}
        for line in header_lines:
            if ":" in line:
                k, v = line.split(":", 1)
                hdrs[k.strip().lower()] = v.strip()
        want = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
        if hdrs.get("sec-websocket-accept") != want:
            self._drop()
            raise WsError("Sec-WebSocket-Accept sai")
        self._buf = bytearray(rest)
        self.connected = True

    # -- gửi -------------------------------------------------------------------
    def _send_frame(self, opcode, payload=b""):
        if self._sock is None:
            raise WsError("chua ket noi")
        n = len(payload)
        head = bytearray([0x80 | opcode])
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        with self._send_lock:
            try:
                self._sock.sendall(bytes(head) + mask + masked)
            except (OSError, ssl.SSLError) as exc:
                raise WsError("gui loi: %s" % type(exc).__name__) from exc

    def send_text(self, text):
        self._send_frame(OP_TEXT, text.encode("utf-8"))

    def send_binary(self, data):
        self._send_frame(OP_BIN, bytes(data))

    def send_ping(self, payload=b""):
        self._send_frame(OP_PING, bytes(payload))

    def close(self, code=1000, reason=""):
        """Đóng lịch sự (gửi khung close một lần) rồi đóng socket. Không ném lỗi."""
        if self._sock is not None and not self._close_sent:
            self._close_sent = True
            try:
                self._send_frame(OP_CLOSE, struct.pack(">H", code) + reason.encode("utf-8")[:100])
            except WsError:
                pass
        self._drop()

    def _drop(self):
        self.connected = False
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    # -- nhận ------------------------------------------------------------------
    def _parse_one(self):
        """Một khung đủ byte trong bộ đệm -> (fin, opcode, payload) hoặc None nếu chưa đủ."""
        buf = self._buf
        if len(buf) < 2:
            return None
        fin, opcode = bool(buf[0] & 0x80), buf[0] & 0x0F
        masked, n, pos = bool(buf[1] & 0x80), buf[1] & 0x7F, 2
        if n == 126:
            if len(buf) < 4:
                return None
            n, pos = struct.unpack(">H", bytes(buf[2:4]))[0], 4
        elif n == 127:
            if len(buf) < 10:
                return None
            n, pos = struct.unpack(">Q", bytes(buf[2:10]))[0], 10
        if n > self._max_message:
            raise WsError("khung qua lon (%d byte)" % n)
        mask = b""
        if masked:
            if len(buf) < pos + 4:
                return None
            mask, pos = bytes(buf[pos:pos + 4]), pos + 4
        if len(buf) < pos + n:
            return None
        payload = bytes(buf[pos:pos + n])
        del buf[:pos + n]
        if masked:
            payload = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        return fin, opcode, payload

    def recv(self, timeout=1.0):
        """Chờ tối đa `timeout` giây. Trả None khi hết giờ; ("text", str) | ("binary", bytes) | ("pong", bytes) | ("close", (code, reason)).
        Ping của máy chủ được trả lời ở đây. Mất kết nối / sai giao thức thì ném WsError."""
        if self._sock is None:
            raise WsError("chua ket noi")
        while True:
            frame = self._parse_one()
            if frame is None:
                try:
                    self._sock.settimeout(timeout)
                    chunk = self._sock.recv(65536)
                except socket.timeout:
                    return None
                except (OSError, ssl.SSLError) as exc:
                    self._drop()
                    raise WsError("nhan loi: %s" % type(exc).__name__) from exc
                if not chunk:
                    self._drop()
                    raise WsError("may chu dong ket noi")
                self._buf += chunk
                continue
            fin, opcode, payload = frame
            if opcode == OP_PING:
                self._send_frame(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                return ("pong", payload)
            if opcode == OP_CLOSE:
                code = struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else 1005
                reason = payload[2:].decode("utf-8", "replace")
                if not self._close_sent:
                    self._close_sent = True
                    try:
                        self._send_frame(OP_CLOSE, payload[:2])
                    except WsError:
                        pass
                self._drop()
                return ("close", (code, reason))
            if opcode in (OP_TEXT, OP_BIN):
                if self._frag_op is not None:
                    raise WsError("khung moi khi chua het manh cu")
                if fin:
                    return (("text", payload.decode("utf-8", "replace")) if opcode == OP_TEXT else ("binary", payload))
                self._frag_op, self._frag = opcode, bytearray(payload)
                continue
            if opcode == OP_CONT:
                if self._frag_op is None:
                    raise WsError("manh tiep theo khong co manh dau")
                self._frag += payload
                if len(self._frag) > self._max_message:
                    raise WsError("thong diep qua lon")
                if fin:
                    op, data = self._frag_op, bytes(self._frag)
                    self._frag_op, self._frag = None, bytearray()
                    return (("text", data.decode("utf-8", "replace")) if op == OP_TEXT else ("binary", data))
                continue
            raise WsError("opcode la: %d" % opcode)
