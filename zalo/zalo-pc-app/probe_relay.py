#!/usr/bin/env python3
"""Standalone relay reachability probe for the Zalo PC app.

Checks, WITHOUT making a call and WITHOUT any account:
  1. UDP egress: a DNS query to a public resolver (default
     8.8.8.8:53) — proves UDP datagrams leave this machine.
  2. Probe echo: the 26B engine probe (same builder the app
     uses) sent to each --relay RTP address; the relay echoes
     it back in the captures, so an echo proves UDP works both
     ways to that relay.
  3. Setup/type-02 (ONLY with --token): one setup_init sent to
     each relay; a 52B type-02 reply proves the relay accepts
     the setup. The token is the 154-char sessId from a live
     11300 response; the app does not currently expose it, so
     this step is normally skipped — the real call tests it.

Relays are identified by INDEX only (#0, #1, ...); relay
addresses and the token are NEVER printed. Run it on the
server, inside the app container if possible, e.g.:
  docker exec <container> python3 /app/probe_relay.py \\
      --relay <rtp-ip>:4200 --relay <rtp-ip>:4200
or from the repo checkout on the host:
  python3 zalo-pc-app/probe_relay.py --relay <rtp-ip>:4200

Exit code: 0 = at least one relay replied; 1 = nothing came
back (UDP blocked or relay silent); 2 = usage error.
"""

import argparse
import ipaddress
import os
import random
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from zalo_pc_app.udp_transport import (  # noqa: E402
    RelayServer, build_probe, build_setup_init, parse_probe,
    parse_type02, socket_family_for_relays)


def _parse_relay(value):
    """Parse IP:port into a RelayServer (RTP side = given
    address; RTCP side = same IP, port+1 — only the RTP side
    is used by this probe)."""
    if ":" not in value:
        raise ValueError("expected IP:port, got %r" % value)
    ip, _, port = value.rpartition(":")
    try:
        ipaddress.ip_address(ip)
        port = int(port)
    except ValueError:
        raise ValueError("expected IP:port, got %r" % value)
    if not 1 <= port <= 65535:
        raise ValueError("port out of range: %r" % value)
    return RelayServer(ip, port, ip, port + 1 if port < 65535 else port)


def dns_test(server, timeout):
    """One DNS A query for example.com; returns (ok, rtt_ms,
    error)."""
    qid = random.randint(0, 0xFFFF)
    pkt = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    pkt += b"\x07example\x03com\x00" + struct.pack(">HH", 1, 1)
    try:
        fam = (socket.AF_INET6
               if isinstance(ipaddress.ip_address(server),
                             ipaddress.IPv6Address)
               else socket.AF_INET)
    except ValueError:
        return False, None, "bad DNS server address"
    sock = socket.socket(fam, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    t0 = time.monotonic()
    try:
        sock.sendto(pkt, (server, 53))
        data, _ = sock.recvfrom(512)
    except (OSError, socket.timeout) as exc:
        return False, None, str(exc)
    finally:
        sock.close()
    rtt = (time.monotonic() - t0) * 1000
    ok = (len(data) >= 12
          and struct.unpack_from(">H", data, 0)[0] == qid
          and struct.unpack_from(">H", data, 2)[0] & 0x8000)
    return ok, rtt, None if ok else "bad DNS reply"


def probe_relay(relay, timeout, token=None, local_session=0,
                peer_session=0, call_session=None):
    """Send 5 probes (+ one setup when token is given) to one
    relay; return a dict of what came back (no addresses)."""
    fam = socket_family_for_relays([relay])
    sock = socket.socket(fam, socket.SOCK_DGRAM)
    sock.bind(("::", 0) if fam == socket.AF_INET6
              else ("0.0.0.0", 0))
    sock.settimeout(0.2)
    t0 = time.monotonic()
    result = {"echoes": 0, "type02": False, "other": 0, "error": None}
    try:
        for i in range(5):
            probe = build_probe(
                seq=i, timestamp_ms=int((time.monotonic() - t0) * 1000))
            sock.sendto(probe, relay.rtp_addr())
        if token is not None:
            setup = build_setup_init(
                local_ssrc=local_session, call_counter=11,
                call_session=call_session, peer_session=peer_session,
                token=token)
            sock.sendto(setup, relay.rtp_addr())
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, _ = sock.recvfrom(2048)
            except socket.timeout:
                continue
            if len(data) == 52 and data[0] == 0x02 and data[1] == 0x7E:
                try:
                    parse_type02(data)
                    result["type02"] = True
                except ValueError:
                    result["other"] += 1
            elif len(data) >= 24 and data[0] == 0x01 and data[1] == 0x01:
                try:
                    parse_probe(data)
                    result["echoes"] += 1
                except ValueError:
                    result["other"] += 1
            else:
                result["other"] += 1
    except OSError as exc:
        result["error"] = str(exc)
    finally:
        sock.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Probe Zalo relay UDP reachability (no call, "
                    "no account).")
    parser.add_argument("--relay", action="append", default=[],
                        help="relay RTP address IP:port (repeatable)")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="seconds to wait for replies (default 5)")
    parser.add_argument("--dns-server", default="8.8.8.8",
                        help="DNS server for the UDP egress test")
    parser.add_argument("--token", default=None,
                        help="154-char sessId token for the setup/"
                             "type-02 step (optional; never printed)")
    parser.add_argument("--local-session", type=int, default=0,
                        help="local session id for the setup step")
    parser.add_argument("--peer-session", type=int, default=0,
                        help="peer session id for the setup step")
    parser.add_argument("--call-session", default=None,
                        help="4-byte call session as 8 hex chars "
                             "(default: random)")
    args = parser.parse_args(argv)

    relays = []
    for value in args.relay:
        try:
            relays.append(_parse_relay(value))
        except ValueError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
    if args.token is not None and len(args.token) != 154:
        print("error: --token must be 154 chars", file=sys.stderr)
        return 2
    call_session = None
    if args.call_session is not None:
        try:
            call_session = bytes.fromhex(args.call_session)
            assert len(call_session) == 4
        except (ValueError, AssertionError):
            print("error: --call-session must be 8 hex chars",
                  file=sys.stderr)
            return 2
    if call_session is None:
        call_session = bytes(random.randrange(256) for _ in range(4))

    print("== UDP egress (DNS to %s:53) ==" % args.dns_server)
    ok, rtt, err = dns_test(args.dns_server, args.timeout)
    if ok:
        print("DNS reply in %.1f ms — UDP leaves this machine" % rtt)
    else:
        print("DNS FAILED (%s) — UDP may be blocked from here" % err)

    any_reply = False
    if not relays:
        print("no --relay given; relay test skipped")
        return 0 if ok else 1
    print("== relay probe (%d relay(s), %.1fs wait) ==" % (
        len(relays), args.timeout))
    for idx, relay in enumerate(relays):
        res = probe_relay(relay, args.timeout, token=args.token,
                          local_session=args.local_session,
                          peer_session=args.peer_session,
                          call_session=call_session)
        if res["error"] is not None:
            print("relay #%d: send/recv error: %s" % (idx, res["error"]))
            continue
        print("relay #%d: echoes=%d type02=%s other=%d"
              % (idx, res["echoes"],
                 "yes" if res["type02"] else "no", res["other"]))
        if res["echoes"] or res["type02"]:
            any_reply = True
    if any_reply:
        print("RESULT: at least one relay replied — UDP path works")
        return 0
    print("RESULT: no relay replied — UDP to the relay is blocked, "
          "or the relay is silent (see the app's wait error for "
          "counters)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
