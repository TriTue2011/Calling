"""Offline P2P (0x7f) tests for zalo_pc_app/udp_transport.py.

Loopback only (127.0.0.1), no real network, no login, no real call.
All addresses/sessions are SYNTHETIC (TEST-NET, made-up values).
Layouts verified against the capture hex reproduced by
deep_p2p.py (zalo.pcap / file4.pcap) — with the captured IPs
replaced by TEST-NET addresses.
"""

import base64
import os
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from zalo_pc_app import udp_transport as ut
from test_udp_transport import _Fabric

SSRC = 0x11223344
PEER_SSRC = 0x55667788
CALL_SESSION = bytes.fromhex("a1b2c32b")
RELAY_SESSION = bytes.fromhex("deadbeef")
TOKEN_RAW = bytes(range(115))
TOKEN_ASCII = base64.urlsafe_b64encode(TOKEN_RAW).rstrip(b"=")
assert len(TOKEN_ASCII) == 154


def test_p2p_hello_verbatim():
    pkt = ut.build_p2p_hello(0x00, CALL_SESSION, 0)
    assert pkt == bytes.fromhex("7f0000a1b2c32b0100000000000000")
    assert len(pkt) == 15
    pkt1 = ut.build_p2p_hello(0x00, CALL_SESSION, 1)
    assert pkt1[-1] == 0x01 and len(pkt1) == 15
    info = ut.parse_p2p(pkt1)
    assert info["role"] == 0x00 and info["subtype"] == 0x01
    assert info["call_session"] == CALL_SESSION
    assert info["count"] == 1 and info["trailing"] == b""
    # Peer form: 18B, same 15B + trailing ff 00 00.
    peer = pkt1 + b"\xff\x00\x00"
    info = ut.parse_p2p(peer)
    assert info["count"] == 1 and info["trailing"] == b"\xff\x00\x00"


def test_p2p_ack_confirm_verbatim():
    addr = "203.0.113.20|43381"  # 18 chars, TEST-NET
    assert len(addr) == 18
    pkt = ut.build_p2p_ack(0x00, CALL_SESSION, addr)
    assert len(pkt) == 37
    assert pkt[:9] == b"\x7f\x00\x00" + CALL_SESSION + b"\x02\x00"
    assert pkt[9:15] == b"\x00" * 6
    assert pkt[15] == 0x12  # length byte = 18
    assert pkt[16:19] == b"\x00" * 3
    assert pkt[19:37] == addr.encode()
    info = ut.parse_p2p(pkt)
    assert info["subtype"] == 0x02 and info["addr"] == addr
    assert info["trailing_ff"] is False
    confirm = ut.build_p2p_confirm(0x01, CALL_SESSION, addr)
    assert confirm[7] == 0x03 and len(confirm) == 37
    # Peer form: 38B, counter byte at offset 14 + trailing 0xff.
    peer = (b"\x7f\x00\x01" + CALL_SESSION + b"\x02\x00" + b"\x00" * 5
            + b"\x01\x12" + b"\x00" * 3 + addr.encode() + b"\xff")
    assert len(peer) == 38
    info = ut.parse_p2p(peer)
    assert info["addr"] == addr and info["addr_counter"] == 0x01
    assert info["trailing_ff"] is True


def test_p2p_media_roundtrip():
    rtp = ut.build_rtp(42, 42 * 320, SSRC, b"payload-bytes", marker=True)
    pkt = ut.build_p2p_media(0x00, CALL_SESSION, rtp)
    assert pkt[:9] == b"\x7f\x00\x00" + CALL_SESSION + b"\x06\x00"
    assert pkt[9:] == rtp
    info = ut.parse_p2p(pkt)
    assert info["subtype"] == 0x06
    assert info["rtp"]["seq"] == 42 and info["rtp"]["ssrc"] == SSRC
    assert info["rtp"]["payload"] == b"payload-bytes"


def test_p2p_parse_control_and_report():
    hdr = b"\x7f\x00\x01" + CALL_SESSION
    # Subtype 0x04: 4-char ASCII number at offset 18..21.
    p4 = hdr + b"\x04\x00" + bytes([0x01, 0x0F, 0x18, 0, 0, 0x04, 0, 0, 0]) \
        + b"6300" + b"\x00" * 10
    assert len(p4) == 32
    info = ut.parse_p2p(p4)
    assert info["subtype"] == 0x04 and info["control_ascii"] == "6300"
    # Subtype 0x05: 14B, flag at byte 10.
    p5 = hdr + b"\x05\x00" + bytes([0x01, 0x01, 0, 0, 0])
    assert len(p5) == 14
    assert ut.parse_p2p(p5)["flag"] == 0x01
    # Subtype 0x07: [sender SSRC][receiver SSRC] at 13/17.
    p7 = (hdr + b"\x07\x00" + bytes([0x8F, 0xCD, 0x00, 0x08])
          + struct.pack(">I", SSRC) + struct.pack(">I", PEER_SSRC)
          + b"\x00" * 24)
    assert len(p7) == 45
    info = ut.parse_p2p(p7)
    assert info["ssrc_a"] == SSRC and info["ssrc_b"] == PEER_SSRC


def test_p2p_handshake_and_media_loopback():
    """Full relay -> P2P switch between a transport and fake peers.

    Fake relay answers type-02 with a reflexive address pointing
    at the fake P2P peer socket. The peer acks the hello, the
    transport confirms and flips mode to "p2p", and media then
    flows as 0x7f packets both ways while the relay still gets
    its 6 s-class refresh (shortened intervals for the test).
    Runs on the in-memory fabric (real loopback UDP is blocked
    in this sandbox; see test_udp_transport._Fabric).
    """
    fabric = _Fabric()
    relay_sock = fabric.new_socket()
    relay_sock.bind(("127.0.0.1", 0))
    relay_sock.settimeout(0.2)
    relay_port = relay_sock.getsockname()[1]
    peer_sock = fabric.new_socket()
    peer_sock.bind(("127.0.0.1", 0))
    peer_sock.settimeout(0.2)
    peer_port = peer_sock.getsockname()[1]
    relay_seen = []
    peer_seen = []
    stop = threading.Event()

    def build_type02(setup_pkt):
        reflexive = "127.0.0.1|%d" % peer_port
        pkt = bytearray(52)
        pkt[0] = 0x02
        pkt[1] = 0x7E
        pkt[10:14] = setup_pkt[10:14]
        pkt[18:20] = setup_pkt[18:20]
        pkt[20] = 0x02
        pkt[25:29] = setup_pkt[21:25]
        pkt[29:33] = RELAY_SESSION
        struct.pack_into("<H", pkt, 33, len(reflexive))
        pkt[35:35 + len(reflexive)] = reflexive.encode()
        return bytes(pkt)

    def fake_relay():
        answered = False
        while not stop.is_set():
            try:
                data, addr = relay_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            relay_seen.append(data)
            if len(data) == 185 and data[1] == 0x7E and not answered:
                answered = True
                relay_sock.sendto(build_type02(data), addr)

    def fake_peer():
        acked = False
        while not stop.is_set():
            try:
                data, addr = peer_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            peer_seen.append(data)
            if len(data) >= 9 and data[0] == 0x7F and data[7] == 0x01 \
                    and not acked:
                acked = True
                ack = ut.build_p2p_ack(0x01, CALL_SESSION,
                                       "127.0.0.1|%d" % peer_port)
                peer_sock.sendto(ack, addr)

    threading.Thread(target=fake_relay, daemon=True).start()
    threading.Thread(target=fake_peer, daemon=True).start()
    cfg = ut.TransportConfig(
        relays=[ut.RelayServer("127.0.0.1", relay_port,
                               "127.0.0.1", relay_port)],
        token=TOKEN_RAW, local_session=SSRC, peer_session=PEER_SSRC,
        call_id=987654321, callee_id="111222333", call_type=1,
        call_session=CALL_SESSION,
        protect_rtp=lambda b: b, unprotect_rtp=lambda b: b,
        probe_burst=1, setup_refresh_interval=0.5, ping_interval=30.0,
        hello_interval=0.1, rtcp_interval=30.0, keepalive_media=False)
    tr = ut.Udp4200Transport(cfg, socket_factory=fabric.new_socket)
    got_pcm = []
    tr.set_pcm_callback(got_pcm.append)
    try:
        tr.start()
        # 2026-11-08 (buoc 3): P2P hello chi bat dau khi peer da
        # tra loi — khong con tu hello ngay sau type-02. Fake
        # relay o day tra type-02 mang dia chi cua PEER (trang
        # thai SAU khi tra loi: relay da biet peer), nen test
        # goi begin_p2p() ro rang de mo phong "peer da tra loi"
        # roi moi doi P2P.
        tr.begin_p2p()
        deadline = time.time() + 5
        while time.time() < deadline and tr.mode != "p2p":
            time.sleep(0.05)
        assert tr.mode == "p2p", tr.status()
        assert tr.peer_p2p_addr == ("127.0.0.1", peer_port)
        # Outbound media now leaves as P2P 0x7f, not type-03.
        tr.send_pcm(b"\x05" * 640)
        deadline = time.time() + 3
        media = [d for d in peer_seen if len(d) >= 9 and d[7] == 0x06]
        while time.time() < deadline and not media:
            time.sleep(0.05)
            media = [d for d in peer_seen if len(d) >= 9 and d[7] == 0x06]
        assert media, [d[:9].hex() for d in peer_seen]
        info = ut.parse_p2p(media[0])
        assert info["rtp"]["ssrc"] == SSRC
        assert info["rtp"]["payload"] == b"\x05" * 640
        assert not any(d[:1] == b"\x03" for d in relay_seen), \
            "media leaked to relay after P2P switch"
        # Inbound P2P media reaches the PCM callback.
        rtp = ut.build_rtp(77, 77 * 320, PEER_SSRC, b"\x09" * 640)
        peer_sock.sendto(
            ut.build_p2p_media(0x01, CALL_SESSION, rtp),
            ("127.0.0.1", tr._sock.getsockname()[1]))
        deadline = time.time() + 3
        while time.time() < deadline and not got_pcm:
            time.sleep(0.05)
        assert got_pcm == [b"\x09" * 640], len(got_pcm)
        # Relay is kept as fallback: setup refresh still arrives.
        deadline = time.time() + 3
        while time.time() < deadline and not any(
                len(d) == 177 and d[1] == 0x01 for d in relay_seen):
            time.sleep(0.05)
        assert any(len(d) == 177 and d[1] == 0x01 for d in relay_seen)
    finally:
        stop.set()
        tr.stop()
        relay_sock.close()
        peer_sock.close()


def test_p2p_builders_match_the_real_callee_engine_layouts():
    """Kiểu gói của engine zcall-native khi NGHE MÁY (chạy thật với điện thoại): bind = header + u16 LE seq + u32 BE chỉ số ứng viên;
    kind 3 lặp lại seq/chỉ số của kind 2 + u32 LE độ dài + "ip|port"; pong = ping với role của ta và byte 9 = 2."""
    b = ut.build_p2p_bind(0x01, CALL_SESSION, 0x0102, 3)
    assert b == bytes.fromhex("7f0001a1b2c32b0100") + bytes.fromhex("0201") + bytes.fromhex("00000003"), b.hex()
    req = bytes.fromhex("7f0000a1b2c32b0200") + bytes.fromhex("070000000002") + struct.pack("<I", 14) + b"203.0.113.9|555" + b"\xff"
    a = ut.build_p2p_bind_answer(0x01, CALL_SESSION, req, "198.51.100.4|40000")
    assert a[:9] == bytes.fromhex("7f0001a1b2c32b0300") and a[9:15] == req[9:15]
    assert struct.unpack("<I", a[15:19])[0] == len(b"198.51.100.4|40000") and a[19:] == b"198.51.100.4|40000"
    ping = bytes.fromhex("7f0000a1b2c32b0400") + bytes([1]) + b"\x00\x00\x00"
    pong = ut.build_p2p_pong(0x01, ping)
    assert pong[2] == 1 and pong[9] == 2 and pong[:2] == ping[:2] and pong[3:9] == ping[3:9] and pong[10:] == ping[10:]


def test_incoming_call_binds_to_every_caller_candidate_answers_kind2_and_pongs_then_flips_to_p2p():
    """Cuộc gọi ĐẾN: điện thoại khai ứng viên P2P (LAN, công khai...). Ta bind tới TỪNG ứng viên (không chỉ địa chỉ công khai), đáp kind 2 bằng
    kind 3 (lặp lại seq/chỉ số), đáp ping bằng pong, rồi đường P2P lên và tiếng của điện thoại tới được hàm nhận PCM."""
    fabric = _Fabric()
    relay_sock = fabric.new_socket()
    relay_sock.bind(("127.0.0.1", 0))
    relay_sock.settimeout(0.2)
    relay_port = relay_sock.getsockname()[1]
    peer_sock = fabric.new_socket()
    peer_sock.bind(("127.0.0.1", 0))
    peer_sock.settimeout(0.2)
    peer_port = peer_sock.getsockname()[1]
    peer_seen, stop = [], threading.Event()

    def fake_relay():                                   # relay im lặng: ta chỉ cần socket để gửi
        while not stop.is_set():
            try:
                relay_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

    def fake_peer():                                    # điện thoại: nhận bind rồi bind lại (kind 2) kèm "ip|port"
        replied = False
        while not stop.is_set():
            try:
                data, addr = peer_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            peer_seen.append(data)
            if len(data) >= 15 and data[0] == 0x7F and data[7] == 0x01 and not replied:
                replied = True
                txt = ("127.0.0.1|%d" % addr[1]).encode()
                peer_sock.sendto(bytes.fromhex("7f0000a1b2c32b0200") + data[9:15] + struct.pack("<I", len(txt)) + txt + b"\xff", addr)
                peer_sock.sendto(bytes.fromhex("7f0000a1b2c32b0400") + bytes([1]) + b"\x00\x00\x00", addr)

    threading.Thread(target=fake_relay, daemon=True).start()
    threading.Thread(target=fake_peer, daemon=True).start()
    cfg = ut.TransportConfig(
        relays=[ut.RelayServer("127.0.0.1", relay_port, "127.0.0.1", relay_port)],
        token=TOKEN_RAW, local_session=SSRC, peer_session=PEER_SSRC, call_id=987654321, callee_id="111222333", call_type=1,
        call_session=CALL_SESSION, protect_rtp=lambda b: b, unprotect_rtp=lambda b: b, probe_burst=1, setup_refresh_interval=30.0,
        ping_interval=30.0, hello_interval=30.0, rtcp_interval=30.0, keepalive_media=False, is_caller=False)
    tr = ut.Udp4200Transport(cfg, socket_factory=fabric.new_socket)
    got_pcm = []
    tr.set_pcm_callback(got_pcm.append)
    try:
        tr.start()
        tr.set_p2p_candidates([{"ip": "198.51.100.7", "port": 1, "type": 1},          # công khai: không tới được (như hairpin hỏng)
                               {"ip": "127.0.0.1", "port": peer_port, "type": 0},       # LAN: tới được
                               {"ip": "2001:db8::1", "port": 9, "type": 0},             # IPv6: bỏ qua
                               {"ip": "x", "port": 0}])
        assert [c[:2] for c in tr._p2p_cands] == [("198.51.100.7", 1), ("127.0.0.1", peer_port)]
        mine = tr.local_p2p_candidates(["192.0.2.50"])
        assert mine == [{"ip": "192.0.2.50", "port": tr._sock.getsockname()[1], "type": 0}], mine
        tr.begin_p2p()
        deadline = time.time() + 5
        while time.time() < deadline and tr.mode != "p2p":
            time.sleep(0.05)
        assert tr.mode == "p2p", tr.status()
        assert tr.peer_p2p_addr == ("127.0.0.1", peer_port)
        binds = [d for d in peer_seen if d[7] == 0x01]
        assert binds and binds[0][:9] == bytes.fromhex("7f0001a1b2c32b0100") and binds[0][9:] == bytes.fromhex("000000000001"), binds[0].hex()   # seq 0, chỉ số ứng viên 1
        deadline = time.time() + 3
        while time.time() < deadline and not [d for d in peer_seen if d[7] == 0x03]:
            time.sleep(0.05)
        kind3 = [d for d in peer_seen if d[7] == 0x03]
        assert kind3 and kind3[0][9:15] == binds[0][9:15], peer_seen                        # đáp kind 2 bằng kind 3, lặp lại seq/chỉ số
        pongs = [d for d in peer_seen if d[7] == 0x04 and d[9] == 2]
        assert pongs and pongs[0][2] == 1, [d[:12].hex() for d in peer_seen]            # đáp ping bằng pong, role callee
        rtp = ut.build_rtp(5, 5 * 320, PEER_SSRC, b"\x07" * 640)
        peer_sock.sendto(ut.build_p2p_media(0x01, CALL_SESSION, rtp), ("127.0.0.1", tr._sock.getsockname()[1]))
        deadline = time.time() + 3
        while time.time() < deadline and not got_pcm:
            time.sleep(0.05)
        assert got_pcm == [b"\x07" * 640], len(got_pcm)
    finally:
        stop.set()
        tr.stop()
        relay_sock.close()
        peer_sock.close()


def test_callee_config_registers_as_callee_with_relay_and_p2p_role_one():
    base = dict(relays=[ut.RelayServer("127.0.0.1", 1, "127.0.0.1", 2)], token=TOKEN_RAW, local_session=SSRC, peer_session=PEER_SSRC,
                call_id=1, callee_id="1", call_type=1, call_session=CALL_SESSION, protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
    caller = ut.TransportConfig(**base)
    callee = ut.TransportConfig(is_caller=False, **base)
    assert (caller.is_caller, caller.call_counter) == (True, 11)             # InitZRTP lệnh 11 = bên gọi (mặc định, cuộc gọi đi)
    assert (callee.is_caller, callee.call_counter) == (False, 12)            # lệnh 12 = bên nghe máy
    assert ut.Udp4200Transport(callee)._role_byte() == 0x01 and ut.Udp4200Transport(caller)._role_byte() == 0x00


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
