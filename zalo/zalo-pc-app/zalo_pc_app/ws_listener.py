"""Bộ nghe WebSocket của Zalo: một luồng nền giữ kết nối, nhận sự kiện, giải mã và đưa vào cùng đường xử lý với long-poll.

Học từ app iOS «GiaNô» (wss://ws1-msg.chat.zalo.me: bắt tay, nhịp tim, hết hạn xác thực, chỉ một chủ kết nối) và zca-js (listen.ts).
DỰ PHÒNG LÀ THIẾT KẾ, KHÔNG PHẢI NHÁNH PHỤ: hai bộ long-poll luôn chạy song song; WebSocket chỉ thêm đường nhanh. WebSocket lỗi, bị đóng, bị trùng kết nối
hay không chạy được thì poll vẫn nhận như cũ (và sự kiện đến cả hai nguồn được lọc trùng, xem event_dedup.py).

Trạng thái: idle -> connecting -> connected (đã nhận khoá) | backoff (chờ thử lại) | standdown (nhường vì có kết nối khác, thử lại sau 30 phút) | disabled
(bị đá hoặc bị trùng nhiều lần: không tự thử lại cho tới khi khởi động lại).
"""
from __future__ import annotations

import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import ws_client, ws_events

DEFAULT_PING_SECONDS = 30.0
BACKOFF_STEPS = (5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 300.0)
STABLE_SECONDS = 120.0               # kết nối sống ít nhất chừng này thì coi là ổn, xoá bộ đếm thử lại
DUPLICATE_STANDDOWN = 1800.0         # bị cmd 3000 / mã đóng 3000: nhường 30 phút (tránh giành kết nối với Zalo web/PC của chủ máy)
MAX_DUPLICATES = 3                   # bị trùng ngần này lần liên tiếp thì tắt hẳn
HELLO_TIMEOUT = 20.0
CLOSE_DUPLICATE, CLOSE_KICK = 3000, 3003


class _Stop(Exception):
    pass


class _Duplicate(Exception):
    pass


class _Kicked(Exception):
    pass


def build_url(base, api_version, api_type, now_ms=None):
    """Địa chỉ WebSocket: thêm zpw_ver, zpw_type, t như client thật (không ghi đè tham số đã có)."""
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("zpw_ver", str(api_version))
    query.setdefault("zpw_type", str(api_type))
    query["t"] = str(now_ms if now_ms is not None else int(time.time() * 1000))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


class WsListener:
    def __init__(self, urls, cookie, user_agent, on_event, api_version, api_type, ping_seconds=DEFAULT_PING_SECONDS, log=print,
                 client_factory=None, clock=time.time, backoff=BACKOFF_STEPS, standdown=DUPLICATE_STANDDOWN, on_state=None):
        self._urls = [u for u in (urls if isinstance(urls, (list, tuple)) else [urls]) if isinstance(u, str) and u.startswith(("ws://", "wss://"))]
        self._cookie = cookie
        self._ua = user_agent
        self._on_event = on_event
        self._api = (api_version, api_type)
        self._ping = max(5.0, float(ping_seconds))
        self._log = log
        self._factory = client_factory or ws_client.WsClient
        self._clock = clock
        self._backoff = tuple(backoff)
        self._standdown = standdown
        self._on_state = on_state
        self._stop = threading.Event()
        self._thread = None
        self._idx = 0
        self._lock = threading.Lock()
        self._cipher_key = None
        self._client = None
        self.state = "idle"
        self.connected_at = 0.0
        self.last_rx = 0.0
        self.last_pong = 0.0
        self.last_event_at = 0.0
        self.counts = {}                 # cmd -> số khung
        self.routed = {"sync": 0, "ctrl": 0}
        self.decode_errors = 0
        self.reconnects = 0
        self.duplicates = 0
        self.last_error = ""
        self.last_close = None

    # -- điều khiển ------------------------------------------------------------
    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            if not self._urls:
                self._set_state("disabled", "khong co dia chi ws")
                return False
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="ws-listener", daemon=True)
            self._thread.start()
            return True

    def stop(self):
        self._stop.set()
        client = self._client
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=5)
        self._set_state("idle")

    @property
    def active(self):
        """True khi đang kết nối, đã có khoá, và còn nghe thấy máy chủ (pong/khung) trong 2,5 nhịp ping — lúc đó đường poll bật lọc trùng."""
        if self.state != "connected":
            return False
        return (self._clock() - max(self.last_pong, self.last_rx)) < self._ping * 2.5

    def status(self):
        now = self._clock()
        return {"state": self.state, "active": self.active, "connected_for": int(now - self.connected_at) if self.state == "connected" else 0,
                "events": dict(self.counts), "routed": dict(self.routed), "decode_errors": self.decode_errors, "reconnects": self.reconnects,
                "duplicates": self.duplicates, "last_close": self.last_close, "last_error": self.last_error,
                "last_event_ago": int(now - self.last_event_at) if self.last_event_at else None, "ping_seconds": self._ping}

    def _set_state(self, state, note=""):
        if state != self.state:
            self.state = state
            if self._on_state is not None:
                try:
                    self._on_state(state, note)
                except Exception:  # noqa: BLE001
                    pass

    # -- vòng chính ------------------------------------------------------------
    def _run(self):
        attempt = 0
        dup_streak = 0
        while not self._stop.is_set():
            url = build_url(self._urls[self._idx % len(self._urls)], *self._api, now_ms=int(self._clock() * 1000))
            began = self._clock()
            try:
                self._set_state("connecting")
                self._session(url)
                self.last_error = "may chu dong ket noi"
            except _Stop:
                return
            except _Duplicate:
                dup_streak += 1
                self.duplicates += 1
                if dup_streak >= MAX_DUPLICATES:
                    self._set_state("disabled", "bi trung ket noi %d lan lien tiep" % dup_streak)
                    self._log("[ws] tat han: bi trung ket noi %d lan lien tiep (co Zalo web/PC khac dang mo cung tai khoan?); poll van chay" % dup_streak)
                    return
                self._set_state("standdown", "co ket noi khac")
                self._log("[ws] co ket noi khac cua tai khoan nay (3000): nhuong %d phut roi thu lai; poll van chay" % int(self._standdown / 60))
                if self._stop.wait(self._standdown):
                    return
                continue
            except _Kicked:
                self._set_state("disabled", "bi da (3003)")
                self._log("[ws] bi da khoi ket noi (3003): tat han; poll van chay")
                return
            except (ws_client.WsError, OSError, ValueError) as exc:
                self.last_error = str(exc)[:120]
            except Exception as exc:  # noqa: BLE001 - luong nen khong chet
                self.last_error = "%s: %s" % (type(exc).__name__, str(exc)[:100])
            dup_streak = 0
            if self._clock() - began >= STABLE_SECONDS:
                attempt = 0
            delay = self._backoff[min(attempt, len(self._backoff) - 1)]
            attempt += 1
            self.reconnects += 1
            self._idx += 1                                   # lần sau thử địa chỉ kế tiếp (nếu có nhiều)
            self._set_state("backoff", self.last_error)
            self._log("[ws] mat ket noi (%s); thu lai sau %.0fs; poll van chay" % (self.last_error, delay))
            if self._stop.wait(delay):
                return

    def _session(self, url):
        client = self._factory(url, headers={"Origin": "https://chat.zalo.me", "User-Agent": self._ua, "Cookie": self._cookie,
                                              "Accept-Language": "vi", "Cache-Control": "no-cache", "Pragma": "no-cache"})
        self._client = client
        self._cipher_key = None
        try:
            client.connect()
            started = self._clock()
            self.last_rx = self.last_pong = started
            last_ping = started
            while not self._stop.is_set():
                got = client.recv(timeout=1.0)
                now = self._clock()
                if got is not None:
                    self.last_rx = now
                    kind, payload = got
                    if kind == "pong":
                        self.last_pong = now
                    elif kind == "close":
                        code, reason = payload
                        self.last_close = {"code": code, "reason": str(reason)[:60], "at": now}
                        if code == CLOSE_DUPLICATE:
                            raise _Duplicate()
                        if code == CLOSE_KICK:
                            raise _Kicked()
                        raise ws_client.WsError("may chu dong (ma %s)" % code)
                    elif kind == "binary":
                        self._on_frame(payload, now)
                if self._cipher_key is None and now - started > HELLO_TIMEOUT:
                    raise ws_client.WsError("khong nhan duoc khoa phien sau %.0fs" % HELLO_TIMEOUT)
                if self._cipher_key is not None and now - last_ping >= self._ping:
                    last_ping = now
                    client.send_ping()                                     # nhịp tim mức WebSocket: bằng chứng còn sống
                    client.send_binary(ws_events.build_ping())              # nhịp tim mức ứng dụng (như client thật)
                if self._cipher_key is not None and now - self.last_pong > self._ping * 3:
                    raise ws_client.WsError("khong co pong trong %.0fs" % (self._ping * 3))
            raise _Stop()
        finally:
            self._client = None
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
            if self.state == "connected":
                self._set_state("backoff")

    def _on_frame(self, raw, now):
        try:
            version, cmd, sub, parsed = ws_events.parse_frame(raw)
        except ValueError:
            self.decode_errors += 1
            return
        if cmd not in self.counts:
            self._log("[ws] khung dau tien cua cmd=%s sub=%s (%d byte)" % (cmd, sub, len(raw)))        # chi so/kich thuoc, khong noi dung
        self.counts[cmd] = self.counts.get(cmd, 0) + 1
        if (cmd, sub) == ws_events.CMD_HELLO:
            key = parsed.get("key") if isinstance(parsed, dict) else None
            if isinstance(key, str) and key:
                first = self._cipher_key is None
                self._cipher_key = key
                self.connected_at = now
                self._set_state("connected")
                if first:
                    self._log("[ws] da ket noi, nhan khoa phien (nhip tim %.0fs)" % self._ping)
            return
        if cmd == ws_events.CMD_DUPLICATE:
            raise _Duplicate()
        target = ws_events.route(cmd)
        if target is None or parsed is None:
            return
        try:
            decoded = ws_events.decode_event(parsed, self._cipher_key)
        except (ValueError, KeyError) as exc:
            self.decode_errors += 1
            if self.decode_errors <= 5:
                self._log("[ws] khong giai ma duoc su kien cmd=%s: %s" % (cmd, str(exc)[:60]))
            return
        data = ws_events.event_payload(decoded)
        if not data:
            return
        self.routed[target] += 1
        self.last_event_at = now
        if self.routed[target] <= 30:
            self._log("[ws] su kien cmd=%s -> %s: %s" % (cmd, target, ", ".join("%s=%d" % (k, len(v)) for k, v in data.items() if isinstance(v, list) and v) or "khong co danh sach"))
        try:
            self._on_event(target, data)
        except Exception as exc:  # noqa: BLE001 - lỗi xử lý không làm đứt kênh
            self.last_error = "xu ly su kien: %s" % type(exc).__name__
