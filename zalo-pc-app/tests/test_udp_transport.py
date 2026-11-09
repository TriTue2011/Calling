"""Offline tests for zalo_pc_app/udp_transport.py (core UDP 4200 + P2P).

Loopback only (127.0.0.1), no real network, no login, no real call.
All session/token/SSRC values are SYNTHETIC (TEST-NET addresses,
made-up sessions) — never the captured values. Packet layouts are
asserted byte-by-byte against the reports (bao-cao.md B.3/B.4/B.5
and disasm-udp4200-setup.md §2/§3/§7).
"""

import base64
import os
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import udp_transport as ut

# Synthetic fixtures (NOT from any capture).
SSRC = 0x11223344
PEER_SSRC = 0x55667788
CALL_SESSION = bytes.fromhex("a1b2c32b")
RELAY_SESSION = bytes.fromhex("deadbeef")
TOKEN_RAW = bytes(range(115))  # 0..114 -> base64url, 154 chars
TOKEN_ASCII = base64.urlsafe_b64encode(TOKEN_RAW).rstrip(b"=")
assert len(TOKEN_ASCII) == 154


def make_config(relays, **overrides):
    kw = dict(relays=relays, token=TOKEN_RAW, local_session=SSRC,
              peer_session=PEER_SSRC, call_id=123456789,
              callee_id="999888777", call_type=1,
              protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
    kw.update(overrides)
    return ut.TransportConfig(**kw)


def free_udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------- fake UDP
# This sandbox blocks real loopback UDP (sendto -> EPERM), so the
# flow tests run through an in-memory datagram fabric instead of
# real sockets. The fabric speaks the same calls the transport
# uses (bind/settimeout/sendto/recvfrom/getsockname/close), and
# Udp4200Transport accepts it via the socket_factory seam.

class _Fabric:
    def __init__(self):
        self._sockets = {}
        self._lock = threading.Lock()
        self._next_port = 50000

    def new_socket(self):
        return _FakeSocket(self)

    def alloc_port(self):
        with self._lock:
            self._next_port += 1
            return self._next_port

    def register(self, sock, addr):
        with self._lock:
            self._sockets[addr] = sock

    def unregister(self, addr):
        with self._lock:
            self._sockets.pop(addr, None)

    def deliver(self, src_addr, data, dest_addr):
        with self._lock:
            dst = self._sockets.get(dest_addr)
        if dst is None:
            return False  # nobody listening: packet dropped
        dst._enqueue(data, src_addr)
        return True


class _FakeSocket:
    def __init__(self, fabric):
        self._fabric = fabric
        self._addr = None
        self._queue = []
        self._cond = threading.Condition()
        self._timeout = None
        self._closed = False

    def bind(self, addr):
        _ip, port = addr
        if port == 0:
            port = self._fabric.alloc_port()
        self._addr = ("127.0.0.1", port)
        self._fabric.register(self, self._addr)

    def getsockname(self):
        return self._addr

    def settimeout(self, timeout):
        self._timeout = timeout

    def sendto(self, data, addr):
        if self._closed:
            raise OSError("socket is closed")
        self._fabric.deliver(self._addr, data, addr)
        return len(data)

    def recvfrom(self, _n):
        with self._cond:
            deadline = (None if self._timeout is None
                        else time.time() + self._timeout)
            while not self._queue:
                if self._closed:
                    raise OSError("socket is closed")
                remaining = (None if deadline is None
                             else deadline - time.time())
                if remaining is not None and remaining <= 0:
                    raise socket.timeout("timed out")
                self._cond.wait(timeout=remaining)
            return self._queue.pop(0)

    def _enqueue(self, data, src_addr):
        with self._cond:
            self._queue.append((data, src_addr))
            self._cond.notify()

    def close(self):
        self._closed = True
        if self._addr is not None:
            self._fabric.unregister(self._addr)
        with self._cond:
            self._cond.notify_all()


# ---------------------------------------------------------------- parsing

def test_parse_servers_string_pairs():
    servers = ut.parse_servers_string(
        "203.0.113.1:4200,203.0.113.1:4201,198.51.100.2:4200,"
        "198.51.100.2:4201")
    assert len(servers) == 2
    assert servers[0] == ut.RelayServer("203.0.113.1", 4200,
                                        "203.0.113.1", 4201)
    assert servers[1].rtp_ip == "198.51.100.2"


def test_parse_servers_string_four_part():
    servers = ut.parse_servers_string(
        "203.0.113.1:4200:203.0.113.1:4201")
    assert len(servers) == 1
    assert servers[0].rtcp_port == 4201


def test_parse_servers_string_invalid_skipped():
    # Bad IP, bad port, and a trailing unpaired single (no RTCP)
    # are all skipped; a lone entry never yields a half-server.
    servers = ut.parse_servers_string(
        "999.999.999.999:4200,203.0.113.1:4200,203.0.113.1:0,"
        "203.0.113.1:4200,203.0.113.1:4201,203.0.113.9:4200")
    # Survivors pair up as (4200,4200) and (4201,4200).
    assert len(servers) == 2
    assert servers[0].rtp_ip == "203.0.113.1"
    assert servers[0].rtp_port == 4200
    assert ut.parse_servers_string("") == []
    assert ut.parse_servers_string("203.0.113.1:4200") == []


# ---------------------------------------------------------------- builders

def test_build_setup_init_verbatim():
    pkt = ut.build_setup_init(SSRC, 11, CALL_SESSION, PEER_SSRC,
                              TOKEN_RAW)
    assert len(pkt) == 185
    assert pkt[0] == 0x01 and pkt[1] == 0x7E
    assert pkt[2:10] == b"\x00" * 8
    assert pkt[10:14] == struct.pack("<I", SSRC)  # LE SSRC
    assert pkt[14:18] == b"\x00" * 4
    assert pkt[18:20] == struct.pack("<H", 11)
    assert pkt[20] == 0x02
    assert pkt[21:25] == CALL_SESSION
    assert pkt[25:29] == struct.pack("<I", PEER_SSRC)  # peer LE
    assert pkt[29:31] == struct.pack("<H", 154)
    assert pkt[31:185] == TOKEN_ASCII
    # Same layout when the token is given as the 154-char string.
    pkt2 = ut.build_setup_init(SSRC, 11, CALL_SESSION, PEER_SSRC,
                               TOKEN_ASCII.decode())
    assert pkt2 == pkt


def test_build_setup_refresh_verbatim():
    pkt = ut.build_setup_refresh(SSRC, RELAY_SESSION, TOKEN_RAW)
    assert len(pkt) == 177
    assert pkt[0] == 0x01 and pkt[1] == 0x01
    assert pkt[2:10] == b"\x00" * 8
    assert pkt[10:14] == struct.pack("<I", SSRC)
    assert pkt[14:18] == RELAY_SESSION
    assert pkt[18:20] == b"\x02\x00"
    assert pkt[20] == 0x01
    assert pkt[21] == 0x9A and pkt[22] == 0x00
    assert pkt[23:177] == TOKEN_ASCII


def test_parse_type02_verbatim():
    addr = "203.0.113.7|42000"  # 17 chars -> 52B, the capture case
    assert len(addr) == 17
    pkt = bytearray(52)
    pkt[0] = 0x02
    pkt[1] = 0x7E
    struct.pack_into("<I", pkt, 10, SSRC)
    struct.pack_into("<H", pkt, 18, 11)
    pkt[20] = 0x02
    pkt[25:29] = CALL_SESSION
    pkt[29:33] = RELAY_SESSION
    struct.pack_into("<H", pkt, 33, len(addr))
    pkt[35:35 + len(addr)] = addr.encode()
    info = ut.parse_type02(bytes(pkt))
    assert info["local_ssrc"] == SSRC
    assert info["call_counter"] == 11
    assert info["call_session"] == CALL_SESSION
    assert info["relay_session"] == RELAY_SESSION
    assert info["reflexive_ip"] == "203.0.113.7"
    assert info["reflexive_port"] == 42000


def _type02_packet(reflexive, call_counter=11):
    """Type-02 reply of exact wire length (35 + len(reflexive))."""
    raw = reflexive.encode("ascii")
    pkt = bytearray(35 + len(raw))
    pkt[0] = 0x02
    pkt[1] = 0x7E
    struct.pack_into("<I", pkt, 10, SSRC)
    struct.pack_into("<H", pkt, 18, call_counter)
    pkt[20] = 0x02
    pkt[25:29] = CALL_SESSION
    pkt[29:33] = RELAY_SESSION
    struct.pack_into("<H", pkt, 33, len(raw))
    pkt[35:] = raw
    return bytes(pkt)


def test_parse_type02_variable_length():
    # Live 07/11 (690edbc): 8 setup replies arrived, 0 parsed as
    # type-02, 8 counted unknown — the parser demanded exactly
    # 52B. The length is 35 + len("IP|port"): 52B is only the
    # 17-char case. Shorter and longer reflexives must parse.
    for reflexive in ("1.2.3.4|4200",         # 12 chars -> 47B
                      "203.0.113.7|42000",    # 17 chars -> 52B
                      "203.0.113.123|5432"):  # 18 chars -> 53B
        pkt = _type02_packet(reflexive)
        assert len(pkt) == 35 + len(reflexive)
        info = ut.parse_type02(pkt)
        assert info["reflexive"] == reflexive
        ip, port = reflexive.split("|")
        assert info["reflexive_ip"] == ip
        assert info["reflexive_port"] == int(port)
        assert info["relay_session"] == RELAY_SESSION
        assert info["call_session"] == CALL_SESSION
    # Trailing bytes past the reflexive string are tolerated
    # (the old loopback builder padded to 52B).
    pkt = _type02_packet("1.2.3.4|4200") + b"\x00\x00\x00"
    assert ut.parse_type02(pkt)["reflexive"] == "1.2.3.4|4200"
    # Still rejected: too short, length field overruns the
    # packet, no '|' in the reflexive, bad IP.
    for bad in (b"\x02\x7e" + b"\x00" * 30,
                _type02_packet("203.0.113.7|42000")[:40],
                _type02_packet("203.0.113.7-42000"),
                _type02_packet("999.999.999.999|42000")):
        try:
            ut.parse_type02(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("parse_type02 accepted %r" % (bad,))


def test_type02_keepalive_roundtrip():
    pkt = ut.build_type02_keepalive(SSRC, 7)
    assert len(pkt) == 25
    assert pkt[0] == 0x02 and pkt[1] == 0x7E
    assert pkt[10:14] == struct.pack("<I", SSRC)
    info = ut.parse_type02_keepalive(pkt)
    assert info == {"kind": "keepalive", "local_ssrc": SSRC,
                    "counter": 7}
    # The disassembly's other 25B form: ping reply, byte[1]=0x01.
    ping_reply = bytearray(25)
    ping_reply[0] = 0x02
    ping_reply[1] = 0x01
    struct.pack_into("<H", ping_reply, 6, 42)
    struct.pack_into("<I", ping_reply, 10, SSRC)
    info = ut.parse_type02_keepalive(bytes(ping_reply))
    assert info["kind"] == "ping_reply" and info["seq"] == 42


def test_probe_verbatim():
    pkt = ut.build_probe(seq=5, timestamp_ms=287)
    assert len(pkt) == 26
    assert pkt[0] == 0x01 and pkt[1] == 0x01
    assert pkt[2:6] == b"\x00" * 4
    assert struct.unpack_from("<H", pkt, 6)[0] == 5
    assert pkt[8:10] == b"\x00\x00"
    assert struct.unpack_from("<I", pkt, 10)[0] == 0x003E9765
    assert struct.unpack_from("<I", pkt, 14)[0] == 0x012F833C
    assert struct.unpack_from("<H", pkt, 18)[0] == 5
    # Corrected tail layout (disasm-200b-probe-tail.md (vi).1,
    # measured on hex): [20]=00, [21]=digit count, [22]=00,
    # ASCII tail at [23..], NUL padding to 26 bytes.
    assert pkt[20] == 0x00
    assert pkt[21] == 3 and pkt[22] == 0x00
    assert pkt[23:26] == b"287"
    info = ut.parse_probe(pkt)
    assert info["seq"] == 5 and info["timestamp_ms"] == 287
    # A 5-digit tail is a 28B packet (23 + 5), same layout.
    pkt = ut.build_probe(seq=1, timestamp_ms=12345)
    assert len(pkt) == 28
    assert pkt[21] == 5 and pkt[23:28] == b"12345"
    assert ut.parse_probe(pkt)["timestamp_ms"] == 12345


def test_rtp_build_parse():
    payload = bytes(range(40))
    pkt = ut.build_rtp(1, 0, SSRC, payload, marker=True,
                       ext=b"\x51\x00\x07\x00")
    assert len(pkt) == 60
    assert pkt[0] == 0x90 and pkt[1] == 0xF0  # marker + PT 112
    assert pkt[2:4] == b"\x00\x01"
    assert pkt[4:8] == b"\x00\x00\x00\x00"
    assert pkt[8:12] == struct.pack(">I", SSRC)
    assert pkt[12:14] == b"\xbe\xde"
    assert pkt[14:16] == b"\x00\x01"
    assert pkt[16:20] == b"\x51\x00\x07\x00"
    assert pkt[20:] == payload
    info = ut.parse_rtp(pkt)
    assert info["marker"] is True and info["seq"] == 1
    assert info["timestamp"] == 0 and info["ssrc"] == SSRC
    assert info["payload"] == payload
    # No-marker form has byte[1] == 0x70.
    assert ut.build_rtp(2, 320, SSRC, b"")[1] == 0x70


def test_ping_build():
    pkt = ut.build_ping(SSRC, RELAY_SESSION, seq=3, rtt_ms=26)
    assert len(pkt) == 45
    assert pkt[0] == 0x01 and pkt[1] == 0x01
    assert struct.unpack_from("<H", pkt, 6)[0] == 3
    assert pkt[10:14] == struct.pack("<I", SSRC)
    assert pkt[14:18] == RELAY_SESSION
    assert struct.unpack_from("<H", pkt, 18)[0] == 32
    assert pkt[20] == 0x0A and pkt[21] == 0x14
    assert struct.unpack_from(">I", pkt, 34)[0] == 26  # RTT slot


def test_rtcp_rr_build():
    pkt = ut.build_rtcp_rr(SSRC, PEER_SSRC, highest_seq=99,
                           relay_session=RELAY_SESSION)
    assert pkt[0] == 0x05
    assert pkt[1:5] == RELAY_SESSION
    rr = pkt[5:]
    assert len(rr) == 32
    assert rr[0] == 0x81 and rr[1] == 201
    assert struct.unpack_from(">I", rr, 4)[0] == SSRC
    assert struct.unpack_from(">I", rr, 8)[0] == PEER_SSRC
    assert struct.unpack_from(">I", rr, 16)[0] == 99


def test_extend_data_normalize():
    out = ut.normalize_extend_data(
        {"srtpMode": 2, "p2p": 1, "bogusKey": 9, "callType": 1})
    assert out == {"srtpMode": 2, "p2p": 1, "callType": 1}
    # Invalid srtpMode resets srtpMode/srtcp/sP2P to 0 (disasm).
    out = ut.normalize_extend_data(
        {"srtpMode": 9, "srtcp": 1, "sP2P": 1})
    assert out == {"srtpMode": 0, "srtcp": 0, "sP2P": 0}
    assert ut.normalize_extend_data(None) is None
    # 2026-11-08 (buoc 2): video/extraInfo la OBJECT long nhau
    # tren day (parser doc "video" la object roi moi doc "codec"
    # ben trong; serializer 0x8e1183 build sub-object) — khong
    # phai key phang "video.codec". Flat spelling chi la alias
    # dau vao, duoc chuyen ve dang long nhau o dau ra.
    out = ut.normalize_extend_data(
        {"video": {"codec": "opus", "bogus": 1},
         "extraInfo": {"type": 2, "id": 7, "bogus": 1},
         "supportCallBusy": 1})
    assert out == {"video": {"codec": "opus"},
                   "extraInfo": {"type": 2, "id": 7},
                   "supportCallBusy": 1}, out
    out = ut.normalize_extend_data(
        {"video.codec": "pcmu", "extraInfo.type": 3,
         "extraInfo.id": 4})
    assert out == {"video": {"codec": "pcmu"},
                   "extraInfo": {"type": 3, "id": 4}}, out
    # serverAddr/serverResult phai la list (dang phan tu chua
    # chung minh duoc — chi giu list, loai dang khac).
    out = ut.normalize_extend_data(
        {"serverAddr": ["203.0.113.1:4200"], "serverResult": [],
         "numServers": 2})
    assert out == {"serverAddr": ["203.0.113.1:4200"],
                   "serverResult": [], "numServers": 2}, out
    out = ut.normalize_extend_data(
        {"serverAddr": "203.0.113.1:4200", "numServers": "x"})
    assert out == {}, out


def test_jitter_buffer():
    jb = ut.JitterBuffer(max_size=4)
    assert jb.push(10, b"a") == [b"a"]
    assert jb.push(12, b"c") == []       # gap at 11: held
    assert jb.push(11, b"b") == [b"b", b"c"]  # gap filled, in order
    assert jb.push(11, b"b") == []       # duplicate dropped
    assert jb.push(10, b"a") == []       # late dropped
    assert jb.dropped_late == 2
    assert jb.reordered == 1


# ---------------------------------------------------------------- missing params

def test_missing_params():
    base = dict(token=TOKEN_RAW, local_session=SSRC,
                peer_session=PEER_SSRC, call_id=1, callee_id="x")
    cases = [
        (dict(base, relays=[]), "relays"),
        (dict(base, relays=[ut.RelayServer("203.0.113.1", 4200,
                                           "203.0.113.1", 4201)],
              token=None), "token"),
        (dict(base, relays=[ut.RelayServer("203.0.113.1", 4200,
                                           "203.0.113.1", 4201)],
              token=b"short"), "token"),
        (dict(base, relays=[ut.RelayServer("203.0.113.1", 4200,
                                           "203.0.113.1", 4201)],
              local_session=None), "local_session"),
        (dict(base, relays=[ut.RelayServer("203.0.113.1", 4200,
                                           "203.0.113.1", 4201)],
              call_id=0), "call_id"),
        (dict(base, relays=[ut.RelayServer("203.0.113.1", 4200,
                                           "203.0.113.1", 4201)],
              callee_id=""), "callee_id"),
    ]
    relays = [ut.RelayServer("203.0.113.1", 4200, "203.0.113.1", 4201)]
    for kw, name in cases:
        kw.setdefault("relays", relays)
        try:
            ut.TransportConfig(**kw)
        except ut.MissingTransportParam as exc:
            assert name in str(exc), (name, str(exc))
        else:
            raise AssertionError("no MissingTransportParam for %s" % name)


# ---------------------------------------------------------------- loopback flow

def _build_type02_reply(setup_pkt, relay_session, reflexive):
    # Exact wire length (35 + len(reflexive)): the fake relay's
    # reflexive ("127.0.0.1|<port>") is 14-15 chars, so the reply
    # is 49-50B, NOT 52B — the loopback flow itself now proves
    # variable-length type-02 selection.
    pkt = bytearray(35 + len(reflexive))
    pkt[0] = 0x02
    pkt[1] = 0x7E
    pkt[10:14] = setup_pkt[10:14]
    pkt[18:20] = setup_pkt[18:20]
    pkt[20] = 0x02
    pkt[25:29] = setup_pkt[21:25]
    pkt[29:33] = relay_session
    struct.pack_into("<H", pkt, 33, len(reflexive))
    pkt[35:35 + len(reflexive)] = reflexive.encode()
    return bytes(pkt)


def test_relay_flow_loopback():
    """probe -> setup -> type-02 -> media, two loopback sockets.

    Runs on the in-memory fabric (real loopback UDP is blocked
    in this sandbox). The fake relay replies with a reflexive
    address pointing at a dummy socket (NOT back at the
    transport) so P2P hellos do not loop back into the transport
    itself.
    """
    fabric = _Fabric()
    relay_sock = fabric.new_socket()
    relay_sock.bind(("127.0.0.1", 0))
    relay_sock.settimeout(0.5)
    relay_port = relay_sock.getsockname()[1]
    dummy = fabric.new_socket()
    dummy.bind(("127.0.0.1", 0))
    dummy_port = dummy.getsockname()[1]
    received = []

    def fake_relay():
        setup_pkt = None
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                data, addr = relay_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            received.append((data, addr))
            if len(data) == 185 and data[1] == 0x7E and setup_pkt is None:
                setup_pkt = data
                reflexive = "127.0.0.1|%d" % dummy_port
                relay_sock.sendto(
                    _build_type02_reply(data, RELAY_SESSION, reflexive),
                    addr)
        return setup_pkt

    t = threading.Thread(target=fake_relay, daemon=True)
    t.start()
    cfg = make_config(
        [ut.RelayServer("127.0.0.1", relay_port,
                        "127.0.0.1", relay_port)],
        probe_burst=2, setup_refresh_interval=0.5, ping_interval=0.5,
        rtcp_interval=30.0, keepalive_media=False, hello_interval=5.0)
    tr = ut.Udp4200Transport(cfg, socket_factory=fabric.new_socket)
    got_pcm = []
    tr.set_pcm_callback(got_pcm.append)
    try:
        tr.start()
        deadline = time.time() + 5
        while time.time() < deadline and tr.selected_relay is None:
            time.sleep(0.05)
        assert tr.selected_relay is not None, tr.status()
        assert tr.state == "connected"
        assert tr.relay_session == RELAY_SESSION
        assert tr.peer_reflexive == ("127.0.0.1", dummy_port)
        # Media out: two frames; relay sees type-03 + RTP seq/ts.
        tr.send_pcm(b"\x01" * 640)
        tr.send_pcm(b"\x02" * 640)
        deadline = time.time() + 3
        media = [d for d, _ in received if d[:1] == b"\x03"]
        while time.time() < deadline and len(media) < 2:
            time.sleep(0.05)
            media = [d for d, _ in received if d[:1] == b"\x03"]
        assert len(media) >= 2, [d[:1] for d, _ in received]
        rtp0 = ut.parse_rtp(media[0][5:])
        rtp1 = ut.parse_rtp(media[1][5:])
        assert media[0][1:5] == RELAY_SESSION
        assert rtp0["ssrc"] == SSRC
        assert rtp1["seq"] == (rtp0["seq"] + 1) & 0xFFFF
        assert rtp1["timestamp"] == (rtp0["timestamp"] + 320) & 0xFFFFFFFF
        assert rtp0["payload"] == b"\x01" * 640
        # Setup refresh (177B) + ping (45B) arrive on schedule.
        deadline = time.time() + 3
        kinds = set()
        while time.time() < deadline and kinds != {"refresh", "ping"}:
            time.sleep(0.05)
            for d, _ in received:
                if len(d) == 177 and d[1] == 0x01:
                    kinds.add("refresh")
                if len(d) == 45 and d[1] == 0x01:
                    kinds.add("ping")
        assert kinds == {"refresh", "ping"}, kinds
        # Media in: out-of-order downlink is delivered in order.
        for seq, payload in ((8, b"\x11" * 640), (10, b"\x13" * 640),
                             (9, b"\x12" * 640)):
            rtp = ut.build_rtp(seq, seq * 320, PEER_SSRC, payload)
            relay_sock.sendto(b"\x04" + rtp,
                              ("127.0.0.1", tr._sock.getsockname()[1]))
        deadline = time.time() + 3
        while time.time() < deadline and len(got_pcm) < 3:
            time.sleep(0.05)
        assert got_pcm == [b"\x11" * 640, b"\x12" * 640, b"\x13" * 640], \
            len(got_pcm)
        st = tr.status()
        assert st["mode"] == "relay" and st["counters"]["rtp_tx"] >= 2
        assert st["counters"]["type02_rx"] >= 1
    finally:
        tr.stop()
        relay_sock.close()
        dummy.close()


def test_dispatch_variable_type02_selects_relay():
    # The live 07/11 shape, replayed directly: a 47B type-02
    # (12-char reflexive) from a listed relay must select it —
    # the old dispatcher only routed exactly 52B and counted
    # everything else unknown.
    fabric = _Fabric()
    cfg = make_config(
        [ut.RelayServer("203.0.113.7", 4200, "203.0.113.7", 4201)],
        probe_burst=0)
    tr = ut.Udp4200Transport(cfg, socket_factory=fabric.new_socket)
    try:
        tr.start()
        tr._dispatch(_type02_packet("1.2.3.4|4200"),
                     ("203.0.113.7", 4200))
        assert tr.counters["type02_rx"] == 1
        assert tr.counters["unknown_rx"] == 0
        assert tr.selected_relay is not None
        assert tr.peer_reflexive == ("1.2.3.4", 4200)
        assert tr.state == "connected"
    finally:
        tr.stop()


def _build_type02_reply(setup_pkt, relay_session, reflexive):
    """Type-02 reply to a setup init (35 + len(reflexive))."""
    raw = reflexive.encode("ascii")
    pkt = bytearray(35 + len(raw))
    pkt[0] = 0x02
    pkt[1] = 0x7E
    pkt[10:14] = setup_pkt[10:14]
    pkt[18:20] = setup_pkt[18:20]
    pkt[20] = 0x02
    pkt[25:29] = setup_pkt[21:25]
    pkt[29:33] = relay_session
    struct.pack_into("<H", pkt, 33, len(raw))
    pkt[35:] = raw
    return bytes(pkt)


def test_no_p2p_hello_while_ringing():
    """P2P hello KHONG duoc gui trong luc do chuong (2026-11-08,
    buoc 3): client that gui 0 goi P2P trong 29,5 s do chuong
    (F2); app gui 61 goi hello toi chinh dia chi cua minh
    (PCAP du 30 s). Chi begin_p2p() khi peer da tra loi."""
    fabric = _Fabric()
    cfg = make_config(
        [ut.RelayServer("127.0.0.1", 4200, "127.0.0.1", 4201)],
        probe_burst=0, setup_refresh_interval=30.0, ping_interval=30.0,
        hello_interval=0.1, rtcp_interval=30.0, keepalive_media=False)
    tr = ut.Udp4200Transport(cfg, socket_factory=fabric.new_socket)
    try:
        tr.start()
        # Fake type-02: tail la dia chi cua PEER (cong khac cong
        # cua transport) — neu code cu tu hello thi hello_tx > 0.
        tr._dispatch(_type02_packet("127.0.0.1|59999"),
                     ("127.0.0.1", 4200))
        assert tr.selected_relay is not None
        time.sleep(0.5)
        assert tr.counters["hello_tx"] == 0, tr.counters
        # Peer tra loi -> begin_p2p(): hello bat dau chay.
        tr.begin_p2p()
        deadline = time.time() + 3
        while time.time() < deadline and tr.counters["hello_tx"] == 0:
            time.sleep(0.05)
        assert tr.counters["hello_tx"] >= 1, tr.counters
    finally:
        tr.stop()


def test_no_hello_to_own_reflexive_address():
    """Hello KHONG bao gio gui toi chinh dia chi reflexive cua
    minh: type-02 trong luc do chuong mang dia chi CUA MINH
    (relay chua biet peer vi peer chua Init) — hello toi do la
    tu noi chuyen voi chinh minh. Ngay ca sau begin_p2p() (da
    tra loi), hello van phai dung cho den khi biet dia chi that
    cua peer (type-02 sau co tail khac, hoac begin_p2p(ip,
    port) ro rang)."""
    fabric = _Fabric()
    cfg = make_config(
        [ut.RelayServer("127.0.0.1", 4200, "127.0.0.1", 4201)],
        probe_burst=0, setup_refresh_interval=30.0, ping_interval=30.0,
        hello_interval=0.1, rtcp_interval=30.0, keepalive_media=False)
    tr = ut.Udp4200Transport(cfg, socket_factory=fabric.new_socket)
    try:
        tr.start()
        own_port = tr._sock.getsockname()[1]
        tr._dispatch(_type02_packet("127.0.0.1|%d" % own_port),
                     ("127.0.0.1", 4200))
        assert tr.selected_relay is not None
        assert tr.peer_reflexive == ("127.0.0.1", own_port)
        time.sleep(0.5)
        assert tr.counters["hello_tx"] == 0, tr.counters
        tr.begin_p2p()
        time.sleep(0.5)
        assert tr.counters["hello_tx"] == 0, tr.counters
    finally:
        tr.stop()


def test_setup_refresh_to_all_relays():
    """Setup refresh 177B moi 6 s gui toi TAT CA relay da tra
    type-02 (2026-11-08, buoc 3): truoc day chi toi relay da
    chon; client that (F2) refresh ca 4 relay da setup. Moi
    refresh mang relay_session RIENG cua relay do."""
    fabric = _Fabric()
    sessions = [bytes.fromhex("aaaa0001"), bytes.fromhex("bbbb0002")]
    relay_socks = []
    relay_ports = []
    received = [[], []]
    stop = threading.Event()

    def make_relay(idx):
        sock = fabric.new_socket()
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(0.2)
        relay_socks.append(sock)
        relay_ports.append(sock.getsockname()[1])

        def loop():
            answered = False
            while not stop.is_set():
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    break
                received[idx].append(data)
                if len(data) == 185 and data[1] == 0x7E \
                        and not answered:
                    answered = True
                    sock.sendto(
                        _build_type02_reply(
                            data, sessions[idx], "127.0.0.1|59999"),
                        addr)
        return loop

    for i in range(2):
        threading.Thread(target=make_relay(i), daemon=True).start()
    cfg = make_config(
        [ut.RelayServer("127.0.0.1", relay_ports[0],
                        "127.0.0.1", relay_ports[0]),
         ut.RelayServer("127.0.0.1", relay_ports[1],
                        "127.0.0.1", relay_ports[1])],
        probe_burst=1, setup_refresh_interval=0.3, ping_interval=30.0,
        hello_interval=30.0, rtcp_interval=30.0, keepalive_media=False)
    tr = ut.Udp4200Transport(cfg, socket_factory=fabric.new_socket)
    try:
        tr.start()
        # Both relays must answer type-02 (both in _relay_info).
        deadline = time.time() + 5
        while time.time() < deadline and len(tr._relay_info) < 2:
            time.sleep(0.05)
        assert len(tr._relay_info) == 2, tr.status()
        # A refresh round (0.3 s) must reach BOTH relays, each
        # carrying its own relay session.
        deadline = time.time() + 3
        seen = [False, False]
        while time.time() < deadline and not all(seen):
            time.sleep(0.05)
            for idx in range(2):
                for d in received[idx]:
                    if len(d) == 177 and d[1] == 0x01 \
                            and d[14:18] == sessions[idx]:
                        seen[idx] = True
        assert seen == [True, True], (
            [len(r) for r in received], tr.counters)
    finally:
        stop.set()
        tr.stop()
        for s in relay_socks:
            s.close()


def test_unknown_sample_recorded():
    # An unrecognized packet is counted AND its scrubbed shape
    # (length + head byte + first 16 bytes of hex) is kept for
    # the wait-failure diagnostics. The sample must never carry
    # an address: a reflexive starts at offset 35, past the 16
    # bytes kept — proven here by planting an address at 35.
    fabric = _Fabric()
    cfg = make_config(
        [ut.RelayServer("203.0.113.7", 4200, "203.0.113.7", 4201)],
        probe_burst=0)
    tr = ut.Udp4200Transport(cfg, socket_factory=fabric.new_socket)
    try:
        tr.start()
        pkt = bytearray(60)
        pkt[0] = 0x09
        pkt[35:35 + 17] = b"203.0.113.7|42000"
        tr._dispatch(bytes(pkt), ("203.0.113.7", 4200))
        assert tr.counters["unknown_rx"] == 1
        samples = tr.unknown_samples()
        assert len(samples) == 1
        assert samples[0]["len"] == 60
        assert samples[0]["head"] == 0x09
        assert samples[0]["hex"] == bytes(pkt[:16]).hex()
        assert "203.0.113" not in str(samples)
    finally:
        tr.stop()


def test_send_pcm_without_protect_raises():
    port = free_udp()
    cfg = make_config(
        [ut.RelayServer("127.0.0.1", port, "127.0.0.1", port)],
        protect_rtp=None, unprotect_rtp=None)
    tr = ut.Udp4200Transport(cfg)
    try:
        tr.start()
        try:
            tr.send_pcm(b"\x00" * 640)
        except ut.MissingTransportParam as exc:
            assert "protect_rtp" in str(exc)
        else:
            raise AssertionError("send_pcm without protect did not raise")
        try:
            tr.send_pcm(b"\x00" * 10)
        except ValueError as exc:
            assert "640" in str(exc)
        else:
            raise AssertionError("short frame did not raise ValueError")
    finally:
        tr.stop()


def test_send_pcm_without_relay_raises():
    port = free_udp()  # nobody listens: no type-02 ever arrives
    cfg = make_config(
        [ut.RelayServer("127.0.0.1", port, "127.0.0.1", port)],
        probe_burst=1)
    tr = ut.Udp4200Transport(cfg)
    try:
        tr.start()
        try:
            tr.send_pcm(b"\x00" * 640)
        except RuntimeError as exc:
            assert "no relay selected" in str(exc)
        else:
            raise AssertionError("send_pcm without relay did not raise")
    finally:
        tr.stop()


def test_socket_family_for_relays():
    v4 = [ut.RelayServer("203.0.113.1", 4200, "203.0.113.1", 4201)]
    assert ut.socket_family_for_relays(v4) == socket.AF_INET
    v6 = [ut.RelayServer("2001:db8::1", 4200, "2001:db8::2", 4201)]
    assert ut.socket_family_for_relays(v6) == socket.AF_INET6
    assert ut.socket_family_for_relays(v4 + v6) == socket.AF_INET


def test_call_counter_default_by_role():
    relay = [ut.RelayServer("203.0.113.1", 4200, "203.0.113.1", 4201)]
    assert make_config(relay).call_counter == 11  # caller: wire value
    assert make_config(relay, is_caller=False).call_counter == 12
    assert make_config(relay, call_counter=5).call_counter == 5


def test_ipv6_transport_picks_af_inet6_family():
    # IPv6-only relays must not silently fail on an AF_INET
    # socket: the transport picks AF_INET6 for the socket.
    cfg = make_config(
        [ut.RelayServer("2001:db8::1", 4200, "2001:db8::2", 4201)])
    assert ut.Udp4200Transport(cfg)._socket_family == socket.AF_INET6
    cfg = make_config(
        [ut.RelayServer("203.0.113.1", 4200, "203.0.113.1", 4201)])
    assert ut.Udp4200Transport(cfg)._socket_family == socket.AF_INET


class _FailingSocket:
    """A socket whose sendto always fails (IPv6-on-IPv4 style)."""

    def bind(self, addr):
        self._addr = ("127.0.0.1", 50001)

    def getsockname(self):
        return self._addr

    def settimeout(self, timeout):
        pass

    def sendto(self, data, addr):
        raise OSError("boom")

    def recvfrom(self, n):
        raise socket.timeout("timed out")

    def close(self):
        pass


def test_send_error_names_relay_index_not_address():
    # _last_error must never carry a relay IP (no IPs in logs/UI).
    cfg = make_config(
        [ut.RelayServer("2001:db8::1", 4200, "2001:db8::2", 4201)],
        probe_burst=1)
    tr = ut.Udp4200Transport(cfg, socket_factory=_FailingSocket)
    try:
        tr.start()
        time.sleep(0.3)
        assert tr.counters["probe_tx"] == 0
        assert tr.counters["send_errors"] > 0
        assert "2001:db8" not in (tr._last_error or "")
        assert "relay #0" in (tr._last_error or "")
    finally:
        tr.stop()


def test_probe_burst_is_26_bytes_engine_relative():
    # The burst probe must be the real 26B shape: the tail is ms
    # since the transport started (small), not monotonic ms
    # since boot (large after a long uptime).
    seen = []

    class _CaptureSocket(_FailingSocket):
        def sendto(self, data, addr):
            seen.append(bytes(data))
            raise OSError("boom")

    cfg = make_config(
        [ut.RelayServer("127.0.0.1", 4200, "127.0.0.1", 4201)],
        probe_burst=1)
    tr = ut.Udp4200Transport(cfg, socket_factory=_CaptureSocket)
    try:
        tr.start()
        assert seen, "no probe was sent"
        assert len(seen[0]) == 26, len(seen[0])
        assert ut.parse_probe(seen[0])["timestamp_ms"] < 10000
    finally:
        tr.stop()


def test_status_scrubs_addresses():
    # /api/engine/status shows status() in the UI, so no relay or
    # peer IP may appear in it: relay named by index only (ports
    # kept), peer addresses expose the port only.
    import json
    relay = ut.RelayServer("203.0.113.9", 4200, "203.0.113.9", 4201)
    cfg = make_config([relay])
    tr = ut.Udp4200Transport(cfg)
    tr.selected_relay = relay
    tr.peer_reflexive = ("198.51.100.7", 51234)
    tr.peer_p2p_addr = ("198.51.100.7", 51235)
    st = tr.status()
    assert st["selected_relay"] == {"index": 0, "rtp_port": 4200,
                                    "rtcp_port": 4201}, st
    assert st["peer_reflexive"] == {"port": 51234}, st
    assert st["peer_p2p_addr"] == {"port": 51235}, st
    blob = json.dumps(st)
    assert "203.0.113.9" not in blob, blob
    assert "198.51.100.7" not in blob, blob


# ----------------------------------------------- keepalive media (2026-11-09)
# Ben nhan Zalo bao "tin hieu yeu" neu khong nhan duoc >= 14 goi am thanh
# moi 2 s hoac thieu bao cao RTCP trong 4 s (zca-js 2.3.13 ZaloRtcSession:
# audio_recheck_sock / durationCheckNoReportSec). Cac test duoi day khoa
# hanh vi: co tieng that thi tieng thang, khong co thi khung Opus im lang.

def _connected(fabric, **overrides):
    """Transport da toi relay + type-02, kem danh sach goi relay nhan."""
    relay_sock = fabric.new_socket()
    relay_sock.bind(("127.0.0.1", 0))
    relay_sock.settimeout(0.2)
    relay_port = relay_sock.getsockname()[1]
    dummy = fabric.new_socket()
    dummy.bind(("127.0.0.1", 0))
    dummy_port = dummy.getsockname()[1]
    received = []
    stop = threading.Event()

    def fake_relay():
        answered = False
        while not stop.is_set():
            try:
                data, addr = relay_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            received.append(data)
            if len(data) == 185 and data[1] == 0x7E and not answered:
                answered = True
                relay_sock.sendto(_build_type02_reply(
                    data, RELAY_SESSION, "127.0.0.1|%d" % dummy_port), addr)

    thr = threading.Thread(target=fake_relay, daemon=True)
    thr.start()
    kw = dict(probe_burst=1, setup_refresh_interval=30.0,
              ping_interval=30.0, hello_interval=30.0)
    kw.update(overrides)
    cfg = make_config([ut.RelayServer("127.0.0.1", relay_port,
                                      "127.0.0.1", relay_port)], **kw)
    tr = ut.Udp4200Transport(cfg, socket_factory=fabric.new_socket)
    tr.start()
    deadline = time.time() + 5
    while time.time() < deadline and tr.selected_relay is None:
        time.sleep(0.02)
    assert tr.selected_relay is not None, tr.status()

    def close():
        stop.set()
        tr.stop()
        relay_sock.close()

    return tr, received, close


def _media_payloads(received):
    return [ut.parse_rtp(d[5:]) for d in list(received) if d[:1] == b"\x03"]


def test_keepalive_silence_flows_without_voice():
    tr, received, close = _connected(_Fabric())
    try:
        time.sleep(1.5)
        rtp = _media_payloads(received)
        # >= 14 goi/2 s la nguong cua ben nhan; do 1.5 s phai vuot xa.
        assert len(rtp) >= 30, len(rtp)
        assert all(p["payload"] == ut.OPUS_SILENCE_FRAME for p in rtp)
        seqs = [p["seq"] for p in rtp]
        assert all((b - a) & 0xFFFF == 1 for a, b in zip(seqs, seqs[1:]))
        st = tr.status()["counters"]
        assert st["keepalive_tx"] >= 30 and st["rtp_tx"] == 0, st
    finally:
        close()


def test_rtcp_report_arrives_well_inside_4_seconds():
    tr, received, close = _connected(_Fabric())
    try:
        time.sleep(1.3)
        rtcp = [d for d in list(received) if d[:1] == b"\x05"]
        assert len(rtcp) >= 2, len(rtcp)       # 0,5 s/lan -> >= 2 trong 1,3 s
        assert tr.config.rtcp_interval <= 1.0
    finally:
        close()


def test_real_voice_preempts_keepalive():
    # Nhip keepalive dat rat dai de vong lich khong tu gui; ta goi truc tiep
    # voi thoi diem gia lap de tach rieng dieu kien "dang co tieng".
    tr, received, close = _connected(
        _Fabric(), keepalive_media_interval=3600.0)
    try:
        tr.send_pcm(b"\x07" * 640)
        assert tr._voice_until > time.monotonic()            # vua co tieng
        counters = lambda: tr.status()["counters"]["keepalive_tx"]
        before = counters()
        tr._maybe_send_keepalive_media(time.monotonic())
        assert counters() == before                          # chua toi nhip
        # Da qua nhip (gia lap +2 gio) nhung con trong khoang giu 250 ms:
        # KHONG chen khung im lang (mic gui theo goi 100 ms, chen vao se keo
        # gian thoi gian va tre tang dan).
        now = time.monotonic() + 7200
        tr._voice_until = now + ut.VOICE_HOLD_SECONDS
        tr._maybe_send_keepalive_media(now + 0.1)
        assert counters() == before
        tr._maybe_send_keepalive_media(now + 0.4)            # het khoang giu
        assert counters() == before + 1
    finally:
        close()


def test_keepalive_can_be_turned_off_and_needs_protect_hook():
    tr, received, close = _connected(_Fabric(), keepalive_media=False)
    try:
        time.sleep(0.4)
        assert _media_payloads(received) == []
        assert tr.status()["counters"]["keepalive_tx"] == 0
    finally:
        close()
    tr, received, close = _connected(_Fabric(), protect_rtp=None,
                                     unprotect_rtp=None)
    try:
        time.sleep(0.4)
        assert _media_payloads(received) == []       # khong hook -> khong gui
        assert tr.state in ("connected", "handshaking")  # va khong sap
    finally:
        close()


def _feed(tr, payloads):
    for i, p in enumerate(payloads):
        tr._on_media(ut.build_rtp(i + 1, i * 320, PEER_SSRC, p),
                     ("127.0.0.1", 9), "relay")


def test_rx_sample_tells_plain_opus_from_ciphertext():
    plain = ut.Udp4200Transport(make_config(
        [ut.RelayServer("127.0.0.1", 4200, "127.0.0.1", 4201)]))
    _feed(plain, [b"\xf8" + bytes([i, 7, 9]) for i in range(30)])  # TOC on dinh
    s = plain.status()["rx_sample"]
    assert s["n"] == ut.RX_SAMPLE_MAX and s["toc_agree"] == 1.0, s
    assert s["head"][0] == "4:f8" and len(s["head"]) == 6
    enc = ut.Udp4200Transport(make_config(
        [ut.RelayServer("127.0.0.1", 4200, "127.0.0.1", 4201)]))
    import random
    rnd = random.Random(5)
    _feed(enc, [bytes(rnd.randrange(256) for _ in range(40)) for _ in range(20)])
    assert enc.status()["rx_sample"]["toc_agree"] < 0.5, enc.status()["rx_sample"]
    empty = ut.Udp4200Transport(make_config(
        [ut.RelayServer("127.0.0.1", 4200, "127.0.0.1", 4201)]))
    assert empty.status()["rx_sample"] == {"n": 0, "toc_agree": 0.0, "head": []}


def test_send_payload_keeps_wire_order_under_concurrent_senders():
    # Hai luong cung gui (keepalive + mic): seq tren day phai tang dan 1 don vi.
    sent = []
    tr = ut.Udp4200Transport(make_config(
        [ut.RelayServer("127.0.0.1", 4200, "127.0.0.1", 4201)],
        protect_rtp=lambda b: b))
    tr.state = "connected"
    tr.selected_relay = tr.config.relays[0]
    tr.relay_session = RELAY_SESSION
    tr._send_to = lambda pkt, addr: sent.append(ut.parse_rtp(pkt[5:])["seq"]) or True

    def worker(keepalive):
        for _ in range(300):
            tr._send_payload(b"\xf8\xff\xfe", keepalive=keepalive)

    ts = [threading.Thread(target=worker, args=(k,)) for k in (True, False)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(sent) == 600
    assert all((b - a) & 0xFFFF == 1 for a, b in zip(sent, sent[1:])), \
        "seq tren day khong theo thu tu"


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001 - report, keep running
            failed += 1
            print("FAIL %s: %r" % (t.__name__, exc))
    print("%d/%d tests passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
