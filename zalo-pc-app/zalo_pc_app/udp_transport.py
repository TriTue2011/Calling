"""Core UDP 4200 + P2P transport for the Zalo PC app (phase 2, stage 2).

Stdlib-only: the PC app image is ``python:3.12-slim`` with no
libsrtp2/libopus, so SRTP/Opus are NEVER imported here. They arrive
through the injectable hooks in :class:`TransportConfig`
(``protect_rtp`` / ``unprotect_rtp``, plus the optional
``encode_frame`` / ``decode_frame``); agent B wires the real
SRTP/Opus implementations into those hooks.

Packet formats are verbatim from the real-call captures
(``~/workspace/zalo-pcap-pc/bao-cao.md``) and the ZaloCall.exe
disassembly (``~/workspace/zalo-pc-reverse/disasm-*.md``). Where a
report and the old mobile sample code disagree, THE REPORT WINS;
every such divergence is marked ``VECH`` (divergence) below and
listed in the final report.

VECH vs ``zalo-call-client/zalo_call/audio.py`` (old mobile code):
  * ``MediaPacket`` there uses a 9-byte mobile header, timestamp
    +960/frame @ 48 kHz, seq wrapping at 256. The PC wire format
    is a 20-byte RTP header, timestamp +320/frame @ 16 kHz, seq
    u16 BE +1. This module manages RTP seq/timestamp itself and
    does NOT reuse ``MediaPacket``.
  * ``SrtpSession`` there protects standard RTP packets; the PC
    payload after the 20-byte RTP header is SRTP-encrypted, with
    NO nested RTP packet inside (bao-cao.md B.5).

OPEN (TODO, unresolved by the reports — do NOT guess an answer):
  * P2P media packets outbound from the PC switch to exactly
    200 bytes ~7.3 s after P2P media starts (bao-cao.md B.6).
    Opus VBR cannot produce exactly 200 B 622 times in a row, so
    the engine probably pads, uses a fixed-size frame, or adds
    FEC later in the call. This module sends whatever the
    encode/protect hooks return and does NOT pad to 200 B.
  * The 115-byte token and the peer session (``0x0c646de5`` in the
    capture) are already known by the real client BEFORE setup,
    most likely from response 11300 (TLS) — their ultimate source
    is still UNCONFIRMED. They are therefore config inputs here,
    never generated locally.
  * The ``f5357a2b`` 4-byte value (setup 185B offset 21-24,
    type-02 offset 25-28, every P2P packet offset 3-6) is treated
    here as the call session, per the task brief. The disassembly
    notes it as a "common constant" whose source is unknown; if
    disassembly later proves it is a fixed protocol magic rather
    than the per-call session, ``call_session`` becomes a
    constant and the real session moves elsewhere.
  * Setup is sent to a SUBSET of probed relays in the captures
    (4/6, 4/7, 1/4); the subset rule is UNKNOWN, so this module
    sends setup to every relay in ``config.relays`` and lets the
    caller pass only the relays it wants tried.
  * The exact pairing inside the raw ``zrtc_config.servers``
    string (how RTP vs RTCP addresses are encoded) is
    UNCONFIRMED from the reports (disassembly only confirms the
    parser splits on ``':'`` and the struct holds both RTP and
    RTCP). :func:`parse_servers_string` accepts the two plausible
    shapes and documents them; B must confirm against a real
    11300 body.
"""

import base64
import binascii
import collections
import ipaddress
import os
import random
import socket
import struct
import threading
import time
from dataclasses import dataclass, field

__all__ = [
    "MissingTransportParam",
    "RelayServer",
    "parse_servers_string",
    "EXTEND_DATA_KEYS",
    "normalize_extend_data",
    "TransportConfig",
    "Udp4200Transport",
    "JitterBuffer",
    "build_probe",
    "parse_probe",
    "build_setup_init",
    "build_setup_refresh",
    "parse_type02",
    "build_type02_keepalive",
    "parse_type02_keepalive",
    "build_ping",
    "build_rtp",
    "parse_rtp",
    "build_rtcp_rr",
    "build_p2p_hello",
    "build_p2p_ack",
    "build_p2p_confirm",
    "build_p2p_media",
    "parse_p2p",
    "socket_family_for_relays",
]

# ---------------------------------------------------------------- constants

RTP_CLOCK_HZ = 16000          # PC RTP clock (bao-cao.md B.5)
RTP_TS_STEP = 320             # +320 timestamp units per 20 ms frame
FRAME_MS = 20
FRAME_SAMPLES = 320           # 20 ms @ 16 kHz mono
FRAME_BYTES = FRAME_SAMPLES * 2  # PCM16 mono LE: 640 bytes/frame
RTP_PT = 112                  # payload type observed on the wire
RTP_HEADER_LEN = 20
TOKEN_ASCII_LEN = 154         # base64url chars on the wire
TOKEN_RAW_LEN = 115           # decoded bytes
DEVICE_CONST_PROBE_ID = 0x003E9765   # hardcoded probe id (disasm 0x894b2e)
DEVICE_CONST_PROBE_C2 = 0x012F833C   # hardcoded 2nd probe constant
CALL_SESSION_LAST_BYTE = 0x2B        # last byte of call session, all captures
SETUP_REFRESH_INTERVAL = 6.0         # setup 177B repeat, seconds
PING_INTERVAL = 0.1                  # ping keepalive, seconds (~10 Hz:
                                    # the real client pings the relay at
                                    # ~10 Hz while ringing — pcap file 2:
                                    # 290 ping pairs in 29.5 s, median gap
                                    # 100 ms. The old 6.0 s was 60x slower;
                                    # the relay session itself is kept by
                                    # the 6 s setup refresh, but the ping is
                                    # part of the caller's ringing
                                    # maintenance (5-pcap re-analysis
                                    # 2026-11-08), so match the real cadence.
HELLO_INTERVAL = 0.5                 # P2P hello retransmit, seconds
RTCP_INTERVAL = 5.0                  # minimal RTCP RR cadence, seconds
PROBE_SETUP_DELAY = 0.2              # probe burst -> setup init gap,
                                    # seconds (the real client sends
                                    # setup ~0.23 s after the probe —
                                    # bao-cao.md B.2/B.10; the app sent
                                    # them back-to-back, ~4 ms apart).


class MissingTransportParam(Exception):
    """A mandatory transport parameter is missing or malformed.

    The message always names the parameter, so the integrator
    (agent B) can tell exactly what still needs to be supplied
    (relay list, token, session, call identity, SRTP hooks).
    """


# ---------------------------------------------------------------- relays

@dataclass(frozen=True)
class RelayServer:
    """One ZRTP relay: RTP and RTCP addresses (both required).

    Validity predicate from the disassembly (``0x860115``): a
    server is usable only when BOTH RTP and RTCP have an IP:port.
    """
    rtp_ip: str
    rtp_port: int
    rtcp_ip: str
    rtcp_port: int

    def rtp_addr(self):
        return (self.rtp_ip, self.rtp_port)

    def rtcp_addr(self):
        return (self.rtcp_ip, self.rtcp_port)

    def as_dict(self):
        return {"rtp_ip": self.rtp_ip, "rtp_port": self.rtp_port,
                "rtcp_ip": self.rtcp_ip, "rtcp_port": self.rtcp_port}


def _parse_ip_port(token):
    """Parse one ``IP:port`` token; return (ip, port) or None."""
    token = token.strip()
    if not token or token.count(":") != 1:
        return None
    ip_s, port_s = token.split(":")
    try:
        ipaddress.ip_address(ip_s)
        port = int(port_s)
    except (ValueError, TypeError):
        return None
    if not 1 <= port <= 65535:
        return None
    return (ip_s, port)


def parse_servers_string(s):
    """Split a raw ``zrtc_config.servers`` string into RelayServers.

    Two shapes are accepted (the exact shape is UNCONFIRMED —
    see the module docstring):
      * alternating ``IP:port`` entries: ``rtp,rtcp,rtp,rtcp,...``
        (each consecutive pair forms one server);
      * one 4-part entry ``rtpIP:rtpPort:rtcpIP:rtcpPort``.
    Entries that cannot form a complete server (missing RTP or
    RTCP, bad IP, bad port) are SKIPPED, never half-built: the
    validity predicate requires both RTP and RTCP.
    """
    if not s or not isinstance(s, str):
        return []
    # Split on commas/semicolons/whitespace, drop empties.
    parts = [p for p in
             (t for chunk in s.replace(";", ",").split(",")
              for t in chunk.split())
             if p]
    servers = []
    singles = []
    for part in parts:
        fields = part.split(":")
        if len(fields) == 4:
            # 4-part form: rtpIP:rtpPort:rtcpIP:rtcpPort
            rtp = _parse_ip_port(":".join(fields[:2]))
            rtcp = _parse_ip_port(":".join(fields[2:]))
            if rtp and rtcp:
                servers.append(RelayServer(rtp[0], rtp[1],
                                          rtcp[0], rtcp[1]))
            continue
        parsed = _parse_ip_port(part)
        if parsed is not None:
            singles.append(parsed)
        # Unparseable tokens are skipped silently (they cannot
        # form a valid server under the RTP+RTCP predicate).
    for i in range(0, len(singles) - 1, 2):
        rtp, rtcp = singles[i], singles[i + 1]
        servers.append(RelayServer(rtp[0], rtp[1], rtcp[0], rtcp[1]))
    # A trailing unpaired single is dropped: no RTCP, not valid.
    return servers


def socket_family_for_relays(relays):
    """Socket family a transport needs for `relays`.

    AF_INET6 only when EVERY relay address is IPv6, else
    AF_INET (IPv4 is the default: the parser emits IPv4
    servers first and the captures show IPv4 relays). A single
    socket cannot serve both families; an IPv6-only list on an
    AF_INET socket fails every sendto with EAFNOSUPPORT, which
    _send_to counts as send_errors and never raises — the
    silent failure that left the 07/11 call with probe_tx=0.
    """
    for relay in relays:
        for ip in (relay.rtp_ip, relay.rtcp_ip):
            try:
                fam = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if not isinstance(fam, ipaddress.IPv6Address):
                return socket.AF_INET
    return socket.AF_INET6


# ---------------------------------------------------------------- extendData

# The 24 extendData keys: the 23 keys of _parseExtendData
# (disasm-signal416-extenddata.md §3.1) + `supportCallBusy`,
# which the serializer 0x8e1183 builds but the parser does not
# read. `video` and `extraInfo` are NESTED objects on the wire
# (the parser reads "video" as an object, then "codec" inside;
# the serializer builds sub-objects) — the flat "video.codec" /
# "extraInfo.*" spellings are only INPUT aliases, converted to
# nested objects below. srtpKey/srtpNoSeq/srtpRTCP are NOT here
# — they are keys of zrtc_config, not extendData (confirmed
# correction).
EXTEND_DATA_KEYS = frozenset([
    "p2p", "callType", "video", "newZrtc", "packetMode",
    "gccMode", "gccAudio", "gccEarlyCall", "gccSVLR", "srtpMode",
    "srtcp", "sP2P", "maxFT", "platform", "fecTP",
    "supportHevcDecode", "tpType", "spTcp", "serverAddr",
    "select2side", "extraInfo", "serverResult", "numServers",
    "supportCallBusy",
])


def _as_extend_int(value):
    """An extendData int value, or None (a bool is not an int)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def normalize_extend_data(data):
    """Normalize an extendData dict per the disassembly rules.

    * Unknown keys are dropped (the real parser silently resets
      to defaults on parse errors instead of failing).
    * ``srtpMode`` must be an int in {1, 2, 3}; otherwise it is
      reset together with ``srtcp`` and ``sP2P`` to 0.
    * ``video`` / ``extraInfo`` are nested objects on the wire:
      {"video": {"codec": str}} and {"extraInfo": {"type": int,
      "id": int}} — the flat "video.codec" / "extraInfo.type" /
      "extraInfo.id" spellings are accepted as input aliases
      and converted to the nested form; unknown sub-keys are
      dropped.
    * ``serverAddr`` / ``serverResult`` must be lists (their
      element shape is unproven — disasm §3.1.2); anything else
      is dropped. ``numServers`` must be an int.
    Returns a new dict (or None for a None input).
    """
    if data is None:
        return None
    if not isinstance(data, dict):
        raise MissingTransportParam(
            "extend_data: must be a dict or None, got %r" % type(data))
    out = {k: v for k, v in data.items() if k in EXTEND_DATA_KEYS}
    # Nested video / extraInfo (wire shape) + flat aliases.
    video = out.pop("video", None)
    if isinstance(video, dict):
        codec = video.get("codec")
        out["video"] = {"codec": codec if isinstance(codec, str)
                        else ""}
    elif "video.codec" in data:
        codec = data["video.codec"]
        out["video"] = {"codec": codec if isinstance(codec, str)
                        else ""}
    extra = out.pop("extraInfo", None)
    if isinstance(extra, dict):
        etype = _as_extend_int(extra.get("type"))
        eid = _as_extend_int(extra.get("id"))
        out["extraInfo"] = {"type": etype if etype is not None else 0,
                            "id": eid if eid is not None else 0}
    elif "extraInfo.type" in data or "extraInfo.id" in data:
        etype = _as_extend_int(data.get("extraInfo.type"))
        eid = _as_extend_int(data.get("extraInfo.id"))
        out["extraInfo"] = {"type": etype if etype is not None else 0,
                            "id": eid if eid is not None else 0}
    for key in ("serverAddr", "serverResult"):
        if key in out and not isinstance(out[key], list):
            del out[key]
    if "numServers" in out \
            and _as_extend_int(out["numServers"]) is None:
        del out["numServers"]
    mode = out.get("srtpMode")
    if mode is not None and (not isinstance(mode, int)
                             or isinstance(mode, bool)
                             or mode not in (1, 2, 3)):
        out["srtpMode"] = 0
        out["srtcp"] = 0
        out["sP2P"] = 0
    return out


# ---------------------------------------------------------------- config

def _token_to_ascii(token):
    """Normalize a token to its 154-char base64url wire form.

    Accepts the 115 decoded bytes or the 154-char ASCII string.
    Anything else raises MissingTransportParam.
    """
    if token is None:
        raise MissingTransportParam(
            "token: missing (need 115 raw bytes or a 154-char "
            "base64url string from response 11300)")
    if isinstance(token, str):
        token = token.encode("ascii", "strict")
    if not isinstance(token, (bytes, bytearray)):
        raise MissingTransportParam(
            "token: must be bytes (115) or str (154 chars), got %r"
            % type(token))
    token = bytes(token)
    if len(token) == TOKEN_RAW_LEN:
        return base64.urlsafe_b64encode(token).rstrip(b"=")
    if len(token) == TOKEN_ASCII_LEN:
        try:
            raw = base64.urlsafe_b64decode(token + b"==")
        except (binascii.Error, ValueError) as exc:
            raise MissingTransportParam(
                "token: 154-char value is not valid base64url: %s"
                % exc) from exc
        if len(raw) != TOKEN_RAW_LEN:
            raise MissingTransportParam(
                "token: 154-char value decodes to %d bytes, need %d"
                % (len(raw), TOKEN_RAW_LEN))
        return token
    raise MissingTransportParam(
        "token: wrong length %d (need 115 raw bytes or 154 "
        "base64url chars)" % len(token))


def _session_to_bytes(value, name):
    """A 4-byte session as bytes (accepts bytes or u32 int)."""
    if isinstance(value, (bytes, bytearray)):
        if len(value) != 4:
            raise ValueError("%s: need 4 bytes, got %d"
                             % (name, len(value)))
        return bytes(value)
    if isinstance(value, int) and 0 <= value <= 0xFFFFFFFF:
        return struct.pack(">I", value)
    raise ValueError("%s: need 4 bytes or a u32 int" % name)


@dataclass
class TransportConfig:
    """Everything the transport needs; nothing is invented here.

    Mandatory (MissingTransportParam when absent/malformed):
      relays, token, local_session, call_id, callee_id.
    ``codec`` defaults to ``"opus"`` but that is UNCONFIRMED —
    the on-wire codec has never been proven (payload is SRTP
    encrypted); it is a parameter, not a fact.
    ``protect_rtp`` / ``unprotect_rtp`` take and return complete
    RTP packets INCLUDING the 20-byte header. They are required
    only when media is actually sent/received, so a transport
    can be started for signaling/handshake without them.
    ``encode_frame`` / ``decode_frame`` (optional, extra vs the
    contract — see final report) convert between 640-byte PCM16
    frames and encoded audio bytes; default is identity
    passthrough (NOT wire Opus) so loopback tests work without
    libopus. Agent B injects the real Opus codec here.
    ``local_ssrc`` defaults to ``local_session``: in every
    capture the setup local session and the RTP SSRC are the
    same value (LE in setup, BE in RTP). It exists only so tests
    can inject a fixed value.
    ``call_counter`` defaults to 11 for the caller / 12 for the
    callee (the wire values in all three captures: outgoing 11,
    incoming 12; the Init ctor writes (role^1)+11). Override it
    explicitly when the real counter is known.
    ``call_session`` defaults to fresh random bytes with the
    last byte 0x2b (the invariant seen in all captures).
    ``peer_session`` is the peer's session/SSRC (int u32 or
    None when not yet known — e.g. before the callee's 416).
    """
    relays: list
    token: bytes
    local_session: int
    peer_session: object = None
    call_id: int = 0
    callee_id: str = ""
    call_type: int = 1  # 1 = audio 1-1, 5 = audio group
    codec: str = "opus"
    extend_data: dict | None = None
    protect_rtp: object = None
    unprotect_rtp: object = None
    # Optional extras (documented extensions to the contract):
    encode_frame: object = None
    decode_frame: object = None
    local_ssrc: int | None = None
    call_counter: int | None = None
    call_session: bytes | None = None
    is_caller: bool = True
    local_addr: str | None = None  # "IP:port" we report in P2P ack
    probe_burst: int = 20          # probes per relay (capture: 20)
    setup_refresh_interval: float = SETUP_REFRESH_INTERVAL
    ping_interval: float = PING_INTERVAL
    hello_interval: float = HELLO_INTERVAL
    rtcp_interval: float = RTCP_INTERVAL
    jitter_buffer_size: int = 8

    def __post_init__(self):
        if not self.relays:
            raise MissingTransportParam(
                "relays: empty (need at least one RelayServer from "
                "response 11300 servers — list of dicts with "
                "rtcpaddr/rtpIPv6, or a legacy zrtc_config.servers "
                "string)")
        for r in self.relays:
            if not isinstance(r, RelayServer):
                raise MissingTransportParam(
                    "relays: every entry must be a RelayServer, got %r"
                    % type(r))
            for ip in (r.rtp_ip, r.rtcp_ip):
                try:
                    ipaddress.ip_address(ip)
                except ValueError as exc:
                    raise MissingTransportParam(
                        "relays: bad IP %r: %s" % (ip, exc)) from exc
            for port in (r.rtp_port, r.rtcp_port):
                if not 1 <= port <= 65535:
                    raise MissingTransportParam(
                        "relays: bad port %r (need 1..65535)" % port)
        self.token = _token_to_ascii(self.token)
        self.token_raw = base64.urlsafe_b64decode(self.token + b"==")
        if self.local_session is None:
            raise MissingTransportParam(
                "local_session: missing (u32, same value as the RTP "
                "SSRC in the captures)")
        if (not isinstance(self.local_session, int)
                or isinstance(self.local_session, bool)
                or not 0 <= self.local_session <= 0xFFFFFFFF):
            raise MissingTransportParam(
                "local_session: must be a u32 int, got %r"
                % (self.local_session,))
        if self.local_ssrc is None:
            self.local_ssrc = self.local_session
        if (not isinstance(self.local_ssrc, int)
                or not 0 <= self.local_ssrc <= 0xFFFFFFFF):
            raise MissingTransportParam(
                "local_ssrc: must be a u32 int, got %r"
                % (self.local_ssrc,))
        if not self.call_id:
            raise MissingTransportParam(
                "call_id: missing (uint32 call identity)")
        if not isinstance(self.call_id, int) or isinstance(self.call_id, bool):
            raise MissingTransportParam(
                "call_id: must be an int, got %r" % type(self.call_id))
        if not self.callee_id:
            raise MissingTransportParam(
                "callee_id: missing (empty string)")
        if self.call_type not in (1, 5):
            raise ValueError(
                "call_type: must be 1 (audio 1-1) or 5 (audio group), "
                "got %r" % (self.call_type,))
        if self.call_counter is None:
            # Wire values in all three captures: outgoing 11,
            # incoming 12 (Init ctor writes (role^1)+11).
            self.call_counter = 11 if self.is_caller else 12
        if not 0 <= self.call_counter <= 0xFFFF:
            raise ValueError("call_counter: must fit in u16")
        if self.call_session is None:
            self.call_session = os.urandom(3) + bytes(
                [CALL_SESSION_LAST_BYTE])
        else:
            self.call_session = _session_to_bytes(
                self.call_session, "call_session")
        if self.peer_session is not None:
            if (not isinstance(self.peer_session, int)
                    or not 0 <= self.peer_session <= 0xFFFFFFFF):
                raise MissingTransportParam(
                    "peer_session: must be a u32 int or None, got %r"
                    % (self.peer_session,))
        self.extend_data = normalize_extend_data(self.extend_data)
        if self.protect_rtp is not None and not callable(self.protect_rtp):
            raise MissingTransportParam("protect_rtp: must be callable")
        if self.unprotect_rtp is not None and not callable(self.unprotect_rtp):
            raise MissingTransportParam("unprotect_rtp: must be callable")

# ---------------------------------------------------------------- packets
# Wire layouts below are verbatim from bao-cao.md (B.3/B.4/B.5/B.6)
# and disasm-udp4200-setup.md (§2/§3/§7). Field offsets are
# asserted by the tests against synthetic values (never the
# captured session/token values).


def build_probe(seq=0, timestamp_ms=None, probe_id=DEVICE_CONST_PROBE_ID,
                const2=DEVICE_CONST_PROBE_C2):
    """Probe 26B (echo burst, before setup by ~0.23 s).

    Layout (disasm-200b-probe-tail.md (vi).1, measured on hex —
    the old disasm-udp4200-setup.md §7.1 layout was off by one
    byte): [0]=0x01 [1]=0x01 [2..5]=00 [6..7]=seq LE u16
    [8..9]=00 [10..13]=probe-id LE [14..17]=const LE
    [18..19]=5 LE [20]=00 [21]=digit count [22]=00
    [23..]=ASCII timestamp-ms tail, NUL-padded to 26 bytes.
    The tail is a MILLISECOND TIMESTAMP (base ~65-288 ms after
    engine start in the captures), NOT a sequence number.
    ``timestamp_ms`` should be ms since the engine/transport
    started (small: 3 digits in the burst, so the packet is
    26B); it defaults to the monotonic ms clock, which after a
    long uptime makes the packet longer than 26B.
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.monotonic() * 1000)
    tail = str(int(timestamp_ms)).encode("ascii")
    total = max(26, 23 + len(tail))
    pkt = bytearray(total)
    pkt[0] = 0x01
    pkt[1] = 0x01
    struct.pack_into("<H", pkt, 6, seq & 0xFFFF)
    struct.pack_into("<I", pkt, 10, probe_id & 0xFFFFFFFF)
    struct.pack_into("<I", pkt, 14, const2 & 0xFFFFFFFF)
    struct.pack_into("<H", pkt, 18, 5)
    pkt[21] = len(tail)
    pkt[23:23 + len(tail)] = tail
    return bytes(pkt)


def parse_probe(data):
    """Parse a probe/echo packet (26/27/28/40B variants).

    Corrected tail layout (branch D, measured on hex):
    [21]=digit count, [22]=0x00, ASCII tail at [23..23+count].
    """
    if len(data) < 24 or data[0] != 0x01 or data[1] != 0x01:
        raise ValueError("not a probe packet: len=%d head=%s"
                         % (len(data), bytes(data[:2]).hex()))
    (seq,) = struct.unpack_from("<H", data, 6)
    (probe_id,) = struct.unpack_from("<I", data, 10)
    (const2,) = struct.unpack_from("<I", data, 14)
    ndigits = data[21]
    tail = bytes(data[23:23 + ndigits])
    try:
        timestamp_ms = int(tail.decode("ascii"))
    except ValueError:
        timestamp_ms = None
    return {"seq": seq, "probe_id": probe_id, "const2": const2,
            "timestamp_ms": timestamp_ms, "tail": tail}


def build_setup_init(local_ssrc, call_counter, call_session,
                     peer_session, token):
    """Setup init 185B (byte[1]=0x7e, sent once per relay).

    [0]=0x01 [1]=0x7e [2..9]=00 [10..13]=local SSRC LE
    [14..17]=00 [18..19]=call counter LE u16 [20]=0x02
    [21..24]=call session 4B [25..28]=peer session LE
    [29..30]=154 LE (token length) [31..184]=token ASCII.
    ``token`` may be 115 raw bytes or the 154-char string.
    ``peer_session`` may be a u32 int (LE on the wire) or 4
    bytes; pass 0 when the peer session is not yet known.
    """
    call_session = _session_to_bytes(call_session, "call_session")
    if isinstance(peer_session, int):
        peer_le = struct.pack("<I", peer_session & 0xFFFFFFFF)
    else:
        peer_le = _session_to_bytes(peer_session, "peer_session")[::-1]
    token_ascii = _token_to_ascii(token)
    pkt = bytearray(185)
    pkt[0] = 0x01
    pkt[1] = 0x7E
    struct.pack_into("<I", pkt, 10, local_ssrc & 0xFFFFFFFF)
    struct.pack_into("<H", pkt, 18, call_counter & 0xFFFF)
    pkt[20] = 0x02
    pkt[21:25] = call_session
    pkt[25:29] = peer_le
    struct.pack_into("<H", pkt, 29, TOKEN_ASCII_LEN)
    pkt[31:185] = token_ascii
    return bytes(pkt)


def build_setup_refresh(local_ssrc, relay_session, token):
    """Setup refresh 177B (byte[1]=0x01, every ~6 s, to every
    relay that answered type-02 — 2026-11-08 step 3: the real
    client refreshes all relays it set up, not just the
    selected one).

    [0]=0x01 [1]=0x01 [2..9]=00 [10..13]=local SSRC LE
    [14..17]=relay session 4B (from type-02) [18..19]=02 00
    [20]=0x01 [21]=0x9a [22]=0x00 [23..176]=token ASCII
    (identical token to the 185B setup of the same call).
    """
    relay_session = _session_to_bytes(relay_session, "relay_session")
    token_ascii = _token_to_ascii(token)
    pkt = bytearray(177)
    pkt[0] = 0x01
    pkt[1] = 0x01
    struct.pack_into("<I", pkt, 10, local_ssrc & 0xFFFFFFFF)
    pkt[14:18] = relay_session
    struct.pack_into("<H", pkt, 18, 2)
    pkt[20] = 0x01
    pkt[21] = 0x9A
    pkt[22] = 0x00
    pkt[23:177] = token_ascii
    return bytes(pkt)


def parse_type02(data):
    """Parse a type-02 relay reply (variable length: 35 +
    len("IP|port")).

    [0]=0x02 [1]=0x7e [2..9]=00 [10..13]=local SSRC LE
    [14..17]=00 [18..19]=call counter [20]=0x02 [21..24]=00
    [25..28]=call session [29..32]=relay session (per relay)
    [33..34]=ASCII length LE u16 [35..]=ASCII "IP|port".
    Returns the relay session, the peer reflexive address, and
    the echoed call identity. Raises ValueError on bad shape.

    The 52B in the captures is the 17-char case, NOT a fixed
    size: the engine reads the u16 LE length at [33..34] and
    copies exactly that many ASCII chars of the reflexive
    "IP|port" (disasm-init-serializer-reflexive.md §4.2), so a
    peer whose reflexive string is shorter or longer yields a
    shorter or longer packet. Requiring exactly 52 bytes
    rejected every such reply as "unknown" (live 07/11: 8
    setup replies -> 8 unknown_rx, 0 type02_rx). Trailing
    bytes past the reflexive string are tolerated.
    """
    if len(data) < 36:
        raise ValueError(
            "type-02 reply too short: %d bytes (need at least 36)"
            % len(data))
    if data[0] != 0x02 or data[1] != 0x7E:
        raise ValueError("type-02 reply head must be 02 7e, got %s"
                         % bytes(data[:2]).hex())
    (local_ssrc,) = struct.unpack_from("<I", data, 10)
    (call_counter,) = struct.unpack_from("<H", data, 18)
    (addr_len,) = struct.unpack_from("<H", data, 33)
    if 35 + addr_len > len(data):
        raise ValueError("type-02 reflexive length %d overruns packet"
                         % addr_len)
    raw = bytes(data[35:35 + addr_len]).decode("ascii", "strict")
    if "|" not in raw:
        raise ValueError("type-02 reflexive %r has no '|'" % raw)
    ip_s, port_s = raw.split("|", 1)
    try:
        port = int(port_s)
        ipaddress.ip_address(ip_s)
    except ValueError as exc:
        raise ValueError("type-02 reflexive %r is not IP|port: %s"
                         % (raw, exc)) from exc
    return {"local_ssrc": local_ssrc,
            "call_counter": call_counter,
            "call_session": bytes(data[25:29]),
            "relay_session": bytes(data[29:33]),
            "reflexive_ip": ip_s,
            "reflexive_port": port,
            "reflexive": raw}


def build_type02_keepalive(local_ssrc, counter):
    """Type-02 keepalive 25B (relay -> client, ~1 Hz, bao-cao.md B.4).

    [0]=0x02 [1]=0x7e [2..9]=00 [10..13]=local SSRC LE
    [14..17]=00 [18..21]=counter LE u32 (1, 2, 3, ...)
    [22..24]=00. NOTE: the disassembly (§7.2) describes a
    DIFFERENT 25B type-02 (byte[1]=0x01, seq at [6..7]) which is
    the reply to the 45B ping; see parse_type02_keepalive, which
    accepts both forms and reports which one it saw.
    """
    pkt = bytearray(25)
    pkt[0] = 0x02
    pkt[1] = 0x7E
    struct.pack_into("<I", pkt, 10, local_ssrc & 0xFFFFFFFF)
    struct.pack_into("<I", pkt, 18, counter & 0xFFFFFFFF)
    return bytes(pkt)


def parse_type02_keepalive(data):
    """Parse a 25B type-02 packet (keepalive or ping reply)."""
    if len(data) != 25 or data[0] != 0x02:
        raise ValueError("type-02 25B packet expected, got len=%d "
                         "head=%s" % (len(data), bytes(data[:2]).hex()))
    (local_ssrc,) = struct.unpack_from("<I", data, 10)
    if data[1] == 0x7E:
        (counter,) = struct.unpack_from("<I", data, 18)
        return {"kind": "keepalive", "local_ssrc": local_ssrc,
                "counter": counter}
    if data[1] == 0x01:
        (seq,) = struct.unpack_from("<H", data, 6)
        return {"kind": "ping_reply", "local_ssrc": local_ssrc,
                "seq": seq}
    raise ValueError("type-02 25B unknown subtype 0x%02x" % data[1])


def build_ping(local_ssrc, relay_session, seq, rtt_ms=0):
    """Ping 45B (client -> relay, disasm §7.2).

    [0]=0x01 [1]=0x01 [2..5]=00 [6..7]=seq LE [8..9]=00
    [10..13]=local session LE [14..17]=relay-id
    [18..19]=32 LE [20]=0x0a [21]=0x14
    [22..41]=stats block, 5 x u32 BE: 0, 1, 1, RTT, 0
    [42..44]=00. RTT is a best-effort measurement (SUY LUẬN in
    the report); pass 0 when unknown.
    """
    relay_session = _session_to_bytes(relay_session, "relay_session")
    pkt = bytearray(45)
    pkt[0] = 0x01
    pkt[1] = 0x01
    struct.pack_into("<H", pkt, 6, seq & 0xFFFF)
    struct.pack_into("<I", pkt, 10, local_ssrc & 0xFFFFFFFF)
    pkt[14:18] = relay_session
    struct.pack_into("<H", pkt, 18, 32)
    pkt[20] = 0x0A
    pkt[21] = 0x14
    for i, value in enumerate((0, 1, 1, rtt_ms & 0xFFFFFFFF, 0)):
        struct.pack_into(">I", pkt, 22 + 4 * i, value)
    return bytes(pkt)


def build_rtp(seq, timestamp, ssrc, payload, marker=False,
              ext=b"\x51\x00\x00\x00"):
    """RTP packet with the 20-byte PC header (bao-cao.md B.5).

    [0]=0x90 (V2, X=1, CC=0) [1]=0x70/0xF0 (marker + PT 112)
    [2..3]=seq BE u16 [4..7]=timestamp BE u32 [8..11]=SSRC
    [12..13]=0xBEDE [14..15]=0x0001 [16..19]=extension 4B
    (default 51 00 00 00; byte 16 is 0x51, byte 17 is 0x00/0x01
    voice-activity-ish on downlink, byte 18 changes per packet
    — exact meaning UNCONFIRMED, pass ``ext`` to set it).
    Payload follows the header and is SRTP-encrypted on the
    wire; this function builds the PLAINTEXT header only.
    """
    if len(ext) != 4:
        raise ValueError("RTP extension must be 4 bytes")
    pkt = bytearray(RTP_HEADER_LEN + len(payload))
    pkt[0] = 0x90
    pkt[1] = (0x80 if marker else 0x00) | RTP_PT
    struct.pack_into(">H", pkt, 2, seq & 0xFFFF)
    struct.pack_into(">I", pkt, 4, timestamp & 0xFFFFFFFF)
    struct.pack_into(">I", pkt, 8, ssrc & 0xFFFFFFFF)
    pkt[12:14] = b"\xbe\xde"
    struct.pack_into(">H", pkt, 14, 1)
    pkt[16:20] = ext
    pkt[20:] = payload
    return bytes(pkt)


def parse_rtp(data):
    """Parse a 20-byte-header RTP packet; payload is opaque."""
    if len(data) < RTP_HEADER_LEN:
        raise ValueError("RTP packet too short: %d bytes" % len(data))
    if data[0] != 0x90:
        raise ValueError("RTP first byte must be 0x90, got 0x%02x"
                         % data[0])
    if data[1] & 0x7F != RTP_PT:
        raise ValueError("RTP payload type must be 112, got %d"
                         % (data[1] & 0x7F))
    if data[12:14] != b"\xbe\xde":
        raise ValueError("RTP extension profile must be BEDE, got %s"
                         % bytes(data[12:14]).hex())
    (ext_len,) = struct.unpack_from(">H", data, 14)
    if ext_len != 1:
        raise ValueError("RTP extension length must be 1 word, got %d"
                         % ext_len)
    (seq,) = struct.unpack_from(">H", data, 2)
    (timestamp,) = struct.unpack_from(">I", data, 4)
    (ssrc,) = struct.unpack_from(">I", data, 8)
    return {"version": 2, "marker": bool(data[1] & 0x80),
            "payload_type": RTP_PT, "seq": seq,
            "timestamp": timestamp, "ssrc": ssrc,
            "ext": bytes(data[16:20]),
            "payload": bytes(data[20:])}


def build_rtcp_rr(local_ssrc, peer_ssrc, highest_seq, packets_lost=0,
                  jitter=0, relay_session=b"\x00\x00\x00\x00"):
    """Minimal RTCP receiver report, wrapped as type-05 (disasm §7.5).

    Outbound type-05 = [0x05][relay-id 4B][RTCP RR 32B].
    The RR itself is plain RFC 3550: 0x81 (V2, RC=1), PT 201,
    length 7, SSRC, one report block (peer SSRC, fraction lost 0,
    cumulative lost, highest seq, jitter, LSR 0, DLSR 0).
    This is the MINIMUM RTCP the transport sends; the capture
    also shows SR + SDES in type-05, which is not reproduced.
    """
    relay_session = _session_to_bytes(relay_session, "relay_session")
    rr = bytearray(32)
    rr[0] = 0x81
    rr[1] = 201
    struct.pack_into(">H", rr, 2, 7)
    struct.pack_into(">I", rr, 4, local_ssrc & 0xFFFFFFFF)
    struct.pack_into(">I", rr, 8, peer_ssrc & 0xFFFFFFFF)
    rr[12] = 0  # fraction lost
    struct.pack_into(">I", rr, 13, packets_lost & 0xFFFFFF)
    struct.pack_into(">I", rr, 16, highest_seq & 0xFFFFFFFF)
    struct.pack_into(">I", rr, 20, jitter & 0xFFFFFFFF)
    # LSR (24..27) and DLSR (28..31) stay 0.
    return b"\x05" + relay_session + bytes(rr)


# ---------------------------------------------------------------- P2P (0x7f)
# Layouts verified against the capture hex in deep_p2p.py output
# (zalo.pcap + file4.pcap): hello 15B (PC) / 18B (peer, trailing
# ff 00 00), ack/confirm 37B (PC) / 38B (peer, trailing 0xff),
# media = 9-byte header + RTP at offset 9, session report 0x07
# carries [sender SSRC][receiver SSRC] at offset 13/17.

def _p2p_header(role, call_session, subtype):
    call_session = _session_to_bytes(call_session, "call_session")
    return bytes([0x7F, 0x00, role & 0xFF]) + call_session + bytes(
        [subtype, 0x00])


def build_p2p_hello(role, call_session, count):
    """P2P hello 15B (subtype 0x01): header + 5 x 00 + count byte.

    Sent repeatedly until the peer answers; the last byte is
    the retransmit count (observed 0, 1, ...). The peer's hello
    is 18B (same 15B + trailing ff 00 00) — see parse_p2p.
    """
    return _p2p_header(role, call_session, 0x01) + b"\x00" * 5 + bytes(
        [count & 0xFF])


def _build_p2p_addr_packet(role, call_session, subtype, addr):
    """Ack (0x02) / confirm (0x03), PC form 37B for an 18-char addr.

    header + 6 x 00 + [length byte] + 3 x 00 + ASCII "IP|port".
    General length: 19 + len(addr) bytes. The peer's form is
    38B: same bytes plus a trailing 0xff, with a counter byte
    at offset 14 (observed 0x01/0x02) — parse_p2p accepts both.
    """
    addr_b = addr.encode("ascii")
    if len(addr_b) > 255:
        raise ValueError("P2P address too long: %d" % len(addr_b))
    return (_p2p_header(role, call_session, subtype) + b"\x00" * 6
            + bytes([len(addr_b)]) + b"\x00" * 3 + addr_b)


def build_p2p_ack(role, call_session, addr):
    """P2P ack 0x02: carries OUR lan address as "IP|port"."""
    return _build_p2p_addr_packet(role, call_session, 0x02, addr)


def build_p2p_confirm(role, call_session, addr):
    """P2P confirm 0x03: same shape as ack."""
    return _build_p2p_addr_packet(role, call_session, 0x03, addr)


def build_p2p_media(role, call_session, rtp_packet):
    """P2P media 0x06: 9-byte header + full RTP packet."""
    return _p2p_header(role, call_session, 0x06) + rtp_packet


def parse_p2p(data):
    """Parse any P2P 0x7f packet; subtype-specific fields decoded.

    hello (0x01): ``count`` = byte 14; peer 18B form also has
      ``trailing`` b"ff 00 00".
    ack/confirm (0x02/0x03): ``addr`` (ASCII "IP|port"),
      ``addr_counter`` = byte 14, ``trailing_ff`` bool.
    control pair (0x04): ``control_ascii`` (4 chars at 18..21).
    small control (0x05): ``flag`` = byte 10.
    media (0x06): ``rtp`` = parse_rtp() of bytes from offset 9.
    session report (0x07): ``ssrc_a``/``ssrc_b`` at 13/17
      ([sender][receiver]).
    Unknown subtypes return the raw payload only.
    """
    if len(data) < 9 or data[0] != 0x7F:
        raise ValueError("not a P2P packet: len=%d head=%s"
                         % (len(data), bytes(data[:1]).hex()))
    subtype = data[7]
    out = {"role": data[2],
           "call_session": bytes(data[3:7]),
           "subtype": subtype,
           "payload": bytes(data[9:])}
    if subtype == 0x01:
        if len(data) < 15:
            raise ValueError("P2P hello too short: %d" % len(data))
        out["count"] = data[14]
        out["trailing"] = bytes(data[15:])
    elif subtype in (0x02, 0x03):
        if len(data) < 19:
            raise ValueError("P2P ack/confirm too short: %d" % len(data))
        addr_len = data[15]
        if 19 + addr_len > len(data):
            raise ValueError("P2P ack address length %d overruns "
                             "packet (%d)" % (addr_len, len(data)))
        out["addr"] = bytes(data[19:19 + addr_len]).decode("ascii")
        out["addr_counter"] = data[14]
        out["trailing_ff"] = len(data) > 19 + addr_len and \
            data[19 + addr_len] == 0xFF
    elif subtype == 0x04:
        if len(data) >= 22:
            out["control_ascii"] = bytes(data[18:22]).decode(
                "ascii", "replace").strip("\x00")
        out["byte9"] = data[9] if len(data) > 9 else None
        out["byte10"] = data[10] if len(data) > 10 else None
    elif subtype == 0x05:
        out["flag"] = data[10] if len(data) > 10 else None
    elif subtype == 0x06:
        out["rtp"] = parse_rtp(bytes(data[9:]))
    elif subtype == 0x07:
        if len(data) < 21:
            raise ValueError("P2P session report too short: %d"
                             % len(data))
        (out["ssrc_a"],) = struct.unpack_from(">I", data, 13)
        (out["ssrc_b"],) = struct.unpack_from(">I", data, 17)
    return out

# ---------------------------------------------------------------- jitter

def _seq_diff(a, b):
    """Signed (a - b) on the u16 sequence circle."""
    d = (a - b) & 0xFFFF
    return d - 0x10000 if d >= 0x8000 else d


class JitterBuffer:
    """Minimal in-order jitter buffer (seq-keyed, bounded).

    Holds out-of-order frames until the missing sequence shows
    up; if the buffer fills, the lowest buffered sequence is
    released so one lost packet cannot stall the stream.
    Late packets (seq behind the expected one) are dropped and
    counted. This is deliberately minimal — no adaptive delay,
    no PLC — agent B may replace it with a fuller buffer.
    """

    def __init__(self, max_size=8):
        self.max_size = max_size
        self._buf = {}
        self._expected = None
        self.dropped_late = 0
        self.reordered = 0

    def push(self, seq, item):
        """Insert one frame; returns the list of in-order frames."""
        if self._expected is None:
            self._expected = seq
        if _seq_diff(seq, self._expected) < 0:
            self.dropped_late += 1
            return []
        if seq in self._buf:
            return []  # duplicate
        if seq != self._expected:
            self.reordered += 1
        self._buf[seq] = item
        ready = []
        while self._expected in self._buf:
            ready.append(self._buf.pop(self._expected))
            self._expected = (self._expected + 1) & 0xFFFF
        while len(self._buf) > self.max_size:
            # Buffer full: release the lowest buffered seq so the
            # stream keeps moving; the gap is a loss, not a stall.
            lowest = min(self._buf, key=lambda s: _seq_diff(s, 0))
            ready.append(self._buf.pop(lowest))
            self._expected = (lowest + 1) & 0xFFFF
            while self._expected in self._buf:
                ready.append(self._buf.pop(self._expected))
                self._expected = (self._expected + 1) & 0xFFFF
        return ready

    def flush(self):
        """Release everything buffered, in sequence order."""
        out = [self._buf[s] for s in sorted(
            self._buf, key=lambda s: _seq_diff(s, 0))]
        self._buf.clear()
        return out


# ---------------------------------------------------------------- transport

class Udp4200Transport:
    """UDP 4200 relay + P2P transport for one call.

    Lifecycle: ``start()`` (probe burst -> setup init -> listen)
    -> relay selected on the first type-02 (sticky: the
    first UDP success wins; a challenger only replaces a TCP
    best, and this transport is UDP-only) -> ``send_pcm()`` /
    PCM callback carry voice -> ``stop()``.

    Relay selection follows the disassembly rule: the server
    with the smallest ``initSuccessTime`` among servers that
    have a token wins. On the wire that is the first type-02
    response to arrive; echo RTT is measured/logged only, never
    used for the final choice.

    Media path (relay): ``[0x03][relay session 4B][RTP...]``
    uplink, ``[0x04][RTP...]`` downlink. Media path (P2P):
    ``0x7f`` header + RTP at offset 9, subtype 0x06.
    P2P starts ONLY after the peer has answered, when the
    server calls ``begin_p2p()`` (2026-11-08, step 3): hello
    -> ack -> confirm; once the P2P handshake completes,
    ``mode`` flips to ``"p2p"`` and media leaves via P2P while
    the relay is kept as a fallback (setup refresh every 6 s to
    EVERY relay that answered type-02 + ping every 0.1 s +
    inbound 1 Hz keepalive counted). The type-02 tail is our
    OWN reflexive address until the peer has done Init, so
    helloing to it before the answer would be talking to
    ourselves — _send_hello refuses that address outright.
    In the captures relay media lasts only ~1 s before P2P
    takes over; this transport switches as soon as P2P is
    confirmed, which is the same rule.

    Threading: one receiver thread + one scheduler thread
    (setup refresh / ping / hello retransmit / RTCP). All
    socket errors are counted, never raised out of a thread;
    the latest error string is visible in ``status()``.
    """

    def __init__(self, config, bind_addr=("0.0.0.0", 0),
                 socket_factory=None):
        if not isinstance(config, TransportConfig):
            raise MissingTransportParam(
                "config: need a TransportConfig, got %r" % type(config))
        self.config = config
        self.bind_addr = bind_addr
        # Test seam: a callable returning a UDP-socket-like object
        # (bind/settimeout/sendto/recvfrom/getsockname/close).
        # Default is a real UDP socket of the family the relays
        # need (AF_INET6 only when every relay address is IPv6;
        # an IPv6-only list on an AF_INET socket fails every
        # sendto with EAFNOSUPPORT, counted as send_errors and
        # never raised — see socket_family_for_relays). The seam
        # exists because some sandboxes block loopback UDP
        # (sendto -> EPERM), so loopback tests run through an
        # in-memory fabric instead; production always uses real
        # sockets.
        self._socket_family = socket_family_for_relays(config.relays)
        self._socket_factory = socket_factory or (
            lambda: socket.socket(self._socket_family,
                                  socket.SOCK_DGRAM))
        self.state = "idle"
        self.mode = "relay"
        self.selected_relay = None
        self.relay_session = None       # bytes, per-relay, from type-02
        self.peer_reflexive = None      # (ip, port) from type-02
        self.peer_p2p_addr = None       # (ip, port) confirmed via P2P ack
        # First-media hook (2026-11-08): a callable fired ONCE when
        # the first INBOUND media packet arrives — type-04 downlink
        # from the relay, or P2P media — from `_on_media` BEFORE the
        # SRTP check. Inbound only: `_dispatch` routes head 0x04
        # and P2P media here, while type-02 (setup reply, arrives
        # during ringing), ping replies and RTCP never reach it.
        # The captures show inbound media only AFTER the peer
        # answers (file 1: type-04 from ~0.5 s after the answer;
        # file 4: 52 packets after the answer; file 2: ZERO inbound
        # in 29.5 s of ringing) — so arrival is evidence the peer
        # answered, even while SRTP is unwired and the packet itself
        # is dropped. It is a PROXY, not the answer signal itself:
        # the answer signal is the peer's answer on voicecall/sync,
        # which the app cannot receive yet (sync down, no parser) —
        # the explicit path is POST /api/call/answered. And
        # OUTBOUND media proves nothing (file 2: the caller sends
        # type-03 uplink for the whole 29.5 s of ringing with no
        # answer), so only the inbound direction counts. The server
        # wires it to mark the call answered; a callback failure
        # never breaks the receiver loop. None by default.
        self.on_first_media = None
        self._first_media_seen = False
        self._sock = None
        self._stop = threading.Event()
        self._recv_thread = None
        self._sched_thread = None
        self._lock = threading.Lock()
        self._pcm_callback = None
        self._seq = random.randint(0, 0xFFFF)  # RTP seq, u16
        self._timestamp = random.randint(0, 0xFFFFFFFF)
        self._ping_seq = 0
        self._hello_count = 0
        self._p2p_acked = False
        self._p2p_confirmed = False
        # P2P hello gate (2026-11-08, step 3 / D4): False until
        # begin_p2p() is called explicitly — i.e. until the peer
        # has answered. The transport NEVER starts the P2P hello
        # handshake on its own (the old code called begin_p2p()
        # from _on_type02, so it helloed all through ringing —
        # 61 hellos in the 30 s pcap — to its own reflexive
        # address, because the type-02 tail during ringing is
        # OUR address: the relay does not know the peer yet).
        self._p2p_started = False
        self._peer_ssrc = config.peer_session  # learned if None
        self._last_error = None
        self._jitter = JitterBuffer(config.jitter_buffer_size)
        self._relay_info = {}  # relay addr -> {arrived_at, session, ...}
        self._last_setup_refresh = 0.0
        self._last_ping = 0.0
        # Engine-relative clock for the probe tail (the tail is a
        # timestamp since the transport started, not monotonic ms
        # since boot — see build_probe). Re-based in start().
        self._probe_t0 = time.monotonic()
        self._last_hello = 0.0
        self._last_rtcp = 0.0
        self._highest_rx_seq = None
        self.counters = {
            "probe_tx": 0, "setup_init_tx": 0, "setup_refresh_tx": 0,
            "ping_tx": 0, "rtcp_tx": 0, "rtcp_rx": 0, "hello_tx": 0, "ack_tx": 0,
            "confirm_tx": 0, "type02_rx": 0, "keepalive_rx": 0,
            "ping_reply_rx": 0, "rtp_tx": 0, "rtp_rx": 0,
            "rtp_rx_dropped": 0, "p2p_rx": 0, "p2p_media_rx": 0,
            "unknown_rx": 0, "send_errors": 0, "recv_errors": 0,
        }
        # Last unrecognized packets (bounded, scrubbed — see
        # _record_unknown): the wait-failure diagnostics show the
        # latest one so the next live test can be read from the
        # error alone.
        self._unknown_samples = collections.deque(maxlen=8)

    # -- public API ------------------------------------------------

    def start(self):
        """Bind, probe every relay, send setup init, start loops."""
        if self.state != "idle":
            raise RuntimeError("transport already started "
                               "(state=%s)" % self.state)
        self._sock = self._socket_factory()
        bind_addr = self.bind_addr
        if (self._socket_family == socket.AF_INET6
                and bind_addr == ("0.0.0.0", 0)):
            # An AF_INET6 socket cannot bind an IPv4 wildcard.
            bind_addr = ("::", 0)
        self._sock.bind(bind_addr)
        self._sock.settimeout(0.2)
        self.state = "probing"
        # Re-base the probe timestamp clock at the moment probing
        # actually starts (closest to the engine's start time).
        self._probe_t0 = time.monotonic()
        self._send_probe_burst()
        # Probe -> setup gap (2026-11-08, step 3 / D7): the real
        # client waits ~0.23 s after the probe burst before setup
        # (bao-cao.md B.2/B.10); the app sent them back-to-back.
        time.sleep(PROBE_SETUP_DELAY)
        self._send_setup_init()
        self.state = "handshaking"
        self._last_setup_refresh = time.monotonic()
        self._last_ping = time.monotonic()
        self._last_rtcp = time.monotonic()
        self._recv_thread = threading.Thread(
            target=self._recv_loop, name="zalo-udp4200-recv", daemon=True)
        self._sched_thread = threading.Thread(
            target=self._sched_loop, name="zalo-udp4200-sched",
            daemon=True)
        self._recv_thread.start()
        self._sched_thread.start()
        return self

    def stop(self):
        """Stop loops, close the socket. Idempotent."""
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        for t in (self._recv_thread, self._sched_thread):
            if t is not None and t.is_alive():
                t.join(timeout=2.0)
        self.state = "stopped"
        return self

    def set_pcm_callback(self, fn):
        """fn(pcm_bytes) is called for each in-order decoded frame."""
        if fn is not None and not callable(fn):
            raise ValueError("pcm callback must be callable or None")
        self._pcm_callback = fn

    def send_pcm(self, pcm):
        """Send one 20 ms PCM16 mono 16 kHz frame (640 bytes).

        PCM -> encode_frame (identity by default, NOT wire Opus)
        -> RTP header (seq +1, timestamp +320, local SSRC)
        -> protect_rtp (SRTP hook) -> type-03 via the selected
        relay, or P2P 0x7f media once P2P is confirmed.
        Raises MissingTransportParam if protect_rtp is missing,
        ValueError on a wrong frame size, RuntimeError if no
        relay has been selected yet.
        """
        if self.state in ("idle", "stopped"):
            raise RuntimeError("transport not started (state=%s)"
                               % self.state)
        if len(pcm) != FRAME_BYTES:
            raise ValueError("send_pcm needs one %d-byte frame, got %d"
                             % (FRAME_BYTES, len(pcm)))
        if self.config.protect_rtp is None:
            raise MissingTransportParam(
                "protect_rtp: missing (SRTP hook is required to send "
                "media; inject it via TransportConfig)")
        encode = self.config.encode_frame or (lambda b: b)
        payload = encode(pcm)
        with self._lock:
            self._seq = (self._seq + 1) & 0xFFFF
            self._timestamp = (self._timestamp + RTP_TS_STEP) & 0xFFFFFFFF
            seq, ts = self._seq, self._timestamp
        rtp = build_rtp(seq, ts, self.config.local_ssrc, payload)
        protected = self.config.protect_rtp(rtp)
        if self.mode == "p2p" and self.peer_p2p_addr is not None:
            pkt = build_p2p_media(self._role_byte(),
                                  self.config.call_session, protected)
            ok = self._send_to(pkt, self.peer_p2p_addr)
        elif self.selected_relay is not None and self.relay_session:
            pkt = b"\x03" + self.relay_session + protected
            ok = self._send_to(pkt, self.selected_relay.rtp_addr())
        else:
            raise RuntimeError(
                "no relay selected yet (no type-02 received); "
                "media cannot be sent before the relay handshake")
        if not ok:
            raise RuntimeError("send failed: %s" % self._last_error)
        self.counters["rtp_tx"] += 1

    def begin_p2p(self, peer_ip=None, peer_port=None):
        """(Re)start the P2P hello handshake to a peer address.

        This is the ONLY way the hello handshake starts
        (2026-11-08, step 3): the server calls it when the peer
        has answered (call state "answered" — see server.py
        _mark_answered). It is NEVER called from _on_type02 any
        more — the old auto-start helloed all through ringing to
        our own reflexive address. Defaults to the reflexive
        address from type-02; _send_hello refuses to hello to
        our own address (see _is_own_reflexive), so the
        handshake only really starts once a real peer address is
        known (a later type-02 tail, or an explicit peer
        address here).
        """
        if peer_ip is not None and peer_port is not None:
            self.peer_reflexive = (peer_ip, peer_port)
        self._p2p_started = True
        self._hello_count = 0
        self._last_hello = 0.0  # send immediately on next tick
        self._send_hello()

    def _is_own_reflexive(self, addr):
        """True when `addr` is our own reflexive address — i.e.
        the relay echoing us back, not the peer.

        Detection: the relay reports the source port it sees for
        our Init packets, and in this deployment (Docker NAT)
        that mapped port equals our bound port (live PCAP
        2026-11-08: local ephemeral 58180, type-02 tail
        113.22.187.193|58180). So a tail whose PORT equals our
        bound port is us. LIMIT: if a NAT remapped our port, the
        tail port would differ from our bound port and this
        check would miss — then the hello could loop back to our
        own socket and self-handshake (the fabric test proved
        it: hello_tx=1, ack_tx=1, confirm_tx=1 with itself).
        A peer can only false-positive here if its mapped port
        coincidentally equals our bound ephemeral port (~1 in
        30000, and only delays P2P initiation — the peer's
        incoming hello is still answered via _on_p2p).
        """
        if addr is None or self._sock is None:
            return False
        try:
            own_port = self._sock.getsockname()[1]
        except (OSError, AttributeError, TypeError):
            return False
        try:
            return int(addr[1]) == int(own_port)
        except (TypeError, ValueError, IndexError):
            return False

    def status(self):
        """Snapshot: state, selected relay, mode, counters.

        No addresses leave the transport here: the selected relay
        is named by index only (ports kept, IPs dropped) and peer
        addresses expose the port only. /api/engine/status shows
        this snapshot in the UI, so relay/peer IPs must never
        appear in it (same rule as _last_error).
        """
        selected = None
        if self.selected_relay is not None:
            idx = next((i for i, r in enumerate(self.config.relays)
                        if r is self.selected_relay), None)
            selected = {"index": idx,
                        "rtp_port": self.selected_relay.rtp_port,
                        "rtcp_port": self.selected_relay.rtcp_port}
        return {
            "state": self.state,
            "mode": self.mode,
            "selected_relay": selected,
            "relay_session": (self.relay_session.hex()
                              if self.relay_session else None),
            "peer_reflexive": ({"port": self.peer_reflexive[1]}
                               if self.peer_reflexive else None),
            "peer_p2p_addr": ({"port": self.peer_p2p_addr[1]}
                              if self.peer_p2p_addr else None),
            "local_ssrc": "0x%08x" % self.config.local_ssrc,
            "call_session": self.config.call_session.hex(),
            "call_id": self.config.call_id,
            "callee_id": self.config.callee_id,
            "codec": self.config.codec,
            "counters": dict(self.counters),
            "jitter_dropped_late": self._jitter.dropped_late,
            "jitter_reordered": self._jitter.reordered,
            "last_error": self._last_error,
        }

    # -- handshake sends -------------------------------------------

    def _role_byte(self):
        return 0x00 if self.config.is_caller else 0x01

    def _send_to(self, pkt, addr):
        """Send one datagram; True on success, False on failure.

        Failures are counted and recorded, never raised out of a
        background thread (the scheduler/receiver must survive
        them); send_pcm() raises instead — see below.
        """
        try:
            self._sock.sendto(pkt, addr)
            return True
        except (OSError, AttributeError) as exc:
            self.counters["send_errors"] += 1
            idx = self._relay_index(addr)
            self._last_error = (
                "send to relay #%d failed: %s" % (idx, exc)
                if idx is not None else "send failed: %s" % (exc,))
            return False

    def _relay_index(self, addr):
        """Index of a relay by its RTP/RTCP address, or None.

        Lets diagnostics name a relay without its address (no
        IPs in logs or UI errors).
        """
        for i, relay in enumerate(self.config.relays):
            if relay.rtp_addr() == addr or relay.rtcp_addr() == addr:
                return i
        return None

    def _send_probe_burst(self):
        burst = max(1, int(self.config.probe_burst))
        # Engine-relative ms (small in the burst, so the packet is
        # the real 26B): the tail is a timestamp since the
        # transport started, not monotonic ms since boot.
        ts_ms = int((time.monotonic() - self._probe_t0) * 1000)
        for relay in self.config.relays:
            for i in range(burst):
                probe = build_probe(seq=i, timestamp_ms=ts_ms)
                if self._send_to(probe, relay.rtp_addr()):
                    self.counters["probe_tx"] += 1

    def _send_setup_init(self):
        cfg = self.config
        for relay in cfg.relays:
            pkt = build_setup_init(
                cfg.local_ssrc, cfg.call_counter, cfg.call_session,
                cfg.peer_session if cfg.peer_session is not None else 0,
                cfg.token)
            if self._send_to(pkt, relay.rtp_addr()):
                self.counters["setup_init_tx"] += 1

    def _send_setup_refresh(self):
        # 2026-11-08 (step 3 / D5): refresh EVERY relay that
        # answered type-02, not just the selected one — the real
        # client (F2) refreshes all 4 relays it set up, every
        # 6 s. Each relay gets its OWN relay session (from
        # _relay_info); a relay that never answered has no
        # session and gets no refresh.
        if not self._relay_info:
            return
        for addr, info in list(self._relay_info.items()):
            session = info.get("relay_session")
            if not session:
                continue
            pkt = build_setup_refresh(self.config.local_ssrc,
                                      session, self.config.token)
            if self._send_to(pkt, addr):
                self.counters["setup_refresh_tx"] += 1

    def _send_ping(self):
        if self.selected_relay is None or not self.relay_session:
            return
        self._ping_seq = (self._ping_seq + 1) & 0xFFFF
        pkt = build_ping(self.config.local_ssrc, self.relay_session,
                         self._ping_seq)
        if self._send_to(pkt, self.selected_relay.rtp_addr()):
            self.counters["ping_tx"] += 1

    def _send_hello(self):
        if self.peer_reflexive is None or self._p2p_confirmed:
            return
        # Never hello to our own reflexive address (2026-11-08,
        # step 3 / D4): the type-02 tail during ringing is OUR
        # address — the relay echoes us because the peer has not
        # done Init yet. Helloing there is talking to ourselves
        # (61 hellos in the 30 s pcap, to 113.22.187.193:58180).
        if self._is_own_reflexive(self.peer_reflexive):
            return
        pkt = build_p2p_hello(self._role_byte(),
                              self.config.call_session, self._hello_count)
        if self._send_to(pkt, self.peer_reflexive):
            self.counters["hello_tx"] += 1
        self._hello_count += 1
        self._last_hello = time.monotonic()

    def _send_rtcp(self):
        if self.selected_relay is None or self._peer_ssrc is None:
            return
        pkt = build_rtcp_rr(
            self.config.local_ssrc, self._peer_ssrc,
            self._highest_rx_seq or 0,
            relay_session=self.relay_session or b"\x00\x00\x00\x00")
        if self._send_to(pkt, self.selected_relay.rtcp_addr()):
            self.counters["rtcp_tx"] += 1

    def _local_addr_string(self):
        """Our address as "IP|port" for P2P ack/confirm."""
        if self.config.local_addr:
            return self.config.local_addr.replace(":", "|", 1)
        port = 0
        try:
            port = self._sock.getsockname()[1]
        except (OSError, AttributeError):
            pass
        ip = "::1" if self._socket_family == socket.AF_INET6 else "127.0.0.1"
        if self.peer_reflexive is not None:
            # Learn the source IP the peer would see (no packet sent).
            probe = socket.socket(self._socket_family, socket.SOCK_DGRAM)
            try:
                probe.connect(self.peer_reflexive)
                ip = probe.getsockname()[0]
            except OSError:
                pass
            finally:
                probe.close()
        return "%s|%d" % (ip, port)

    # -- scheduler ---------------------------------------------------

    def _sched_loop(self):
        cfg = self.config
        while not self._stop.is_set():
            now = time.monotonic()
            try:
                if (self.selected_relay is not None
                        and now - self._last_setup_refresh
                        >= cfg.setup_refresh_interval):
                    self._send_setup_refresh()
                    self._last_setup_refresh = now
                if (self.selected_relay is not None
                        and now - self._last_ping >= cfg.ping_interval):
                    self._send_ping()
                    self._last_ping = now
                if (self.peer_reflexive is not None
                        and self._p2p_started
                        and not self._p2p_confirmed
                        and now - self._last_hello >= cfg.hello_interval):
                    self._send_hello()
                if (self.state == "connected"
                        and now - self._last_rtcp >= cfg.rtcp_interval):
                    self._send_rtcp()
                    self._last_rtcp = now
            except Exception as exc:  # noqa: BLE001 - scheduler survives
                self._last_error = "scheduler: %s" % exc
            self._stop.wait(0.05)

    # -- receiver ----------------------------------------------------

    def _recv_loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self.counters["recv_errors"] += 1
                    self._last_error = "recv failed: %s" % exc
                break
            try:
                self._dispatch(data, addr)
            except Exception as exc:  # noqa: BLE001 - one bad packet
                self.counters["recv_errors"] += 1
                self._last_error = "dispatch failed: %s" % (exc,)

    def _dispatch(self, data, addr):
        if not data:
            self._record_unknown(data)
            return
        head = data[0]
        if head == 0x02:
            if len(data) == 25:
                self._on_type02_25(data, addr)
            elif len(data) >= 36 and data[1] == 0x7E:
                # Setup reply: variable length (35 + len of the
                # reflexive "IP|port"), NOT fixed 52B — see
                # parse_type02.
                self._on_type02(data, addr)
            else:
                self._record_unknown(data)
        elif head == 0x04:
            self._on_media(data[1:], addr, via="relay")
        elif head == 0x05:
            self._on_rtcp(data, addr)
        elif head == 0x7F:
            self._on_p2p(data, addr)
        elif head == 0x01:
            # Probe echo / ping reply / quality report: counted,
            # contents not needed for the media path.
            self.counters["ping_reply_rx"] += 1
        else:
            self._record_unknown(data)

    def _record_unknown(self, data):
        """Count an unrecognized packet and keep a scrubbed sample.

        The sample holds only the length, the head byte, and the
        first 16 bytes as hex. A reflexive address (if the packet
        has one) starts at offset 35, so no address can leak
        through it — same rule as _last_error and status().
        """
        self.counters["unknown_rx"] += 1
        self._unknown_samples.append({
            "len": len(data),
            "head": data[0] if data else None,
            "hex": bytes(data[:16]).hex(),
        })

    def unknown_samples(self):
        """Last unrecognized packets (bounded, scrubbed)."""
        return [dict(s) for s in self._unknown_samples]

    def _relay_for_addr(self, addr):
        for relay in self.config.relays:
            if relay.rtp_addr() == addr or relay.rtcp_addr() == addr:
                return relay
        return None

    def _on_type02(self, data, addr):
        try:
            info = parse_type02(data)
        except ValueError as exc:
            self.counters["recv_errors"] += 1
            self._last_error = "bad type-02: %s" % (exc,)
            return
        self.counters["type02_rx"] += 1
        relay = self._relay_for_addr(addr)
        if relay is None:
            # Unknown sender: do not select it. The address is
            # recorded in _relay_info only (never in _last_error,
            # which surfaces in the UI error).
            self._last_error = ("type-02 from unlisted relay "
                                "(not in config.relays)")
            return
        self._relay_info[addr] = {
            "arrived_at": time.monotonic(),
            "relay_session": info["relay_session"],
            "reflexive": (info["reflexive_ip"], info["reflexive_port"]),
        }
        # The type-02 tail is a reflexive address: OUR OWN address
        # while the peer has not done Init (the relay echoes us),
        # the PEER's address once the relay knows it (after the
        # peer's Init). Refresh it on every type-02 — the first
        # one arrives during ringing (our own address), a later
        # one may carry the peer's. _send_hello refuses to hello
        # to our own address, so a self-tail can never start a
        # self-handshake.
        self.peer_reflexive = (info["reflexive_ip"],
                               info["reflexive_port"])
        if self.selected_relay is None:
            # First type-02 wins and sticks (initSuccessTime
            # rule; UDP challenger never replaces a UDP best).
            self.selected_relay = relay
            self.relay_session = info["relay_session"]
            self.state = "connected"
            # NO begin_p2p() here (2026-11-08, step 3): the P2P
            # hello handshake starts only when the peer has
            # answered (server.py _mark_answered calls
            # begin_p2p()). Auto-starting here helloed all
            # through ringing to our own reflexive address.

    def _on_type02_25(self, data, addr):
        try:
            info = parse_type02_keepalive(data)
        except ValueError as exc:
            self.counters["recv_errors"] += 1
            self._last_error = "bad type-02 25B: %s" % (exc,)
            return
        if info["kind"] == "keepalive":
            self.counters["keepalive_rx"] += 1
        else:
            self.counters["ping_reply_rx"] += 1

    def _on_rtcp(self, data, addr):
        # Minimal: count inbound RTCP; contents (SR/SDES) are not
        # needed for the media path yet.
        self.counters["rtcp_rx"] += 1

    def _on_media(self, rtp_data, addr, via):
        self.counters["rtp_rx"] += 1
        if via == "p2p":
            self.counters["p2p_media_rx"] += 1
        # First inbound RTP = the peer answered (see on_first_media
        # in __init__): fire once, BEFORE the SRTP check, so an
        # unwired call is still recognised as answered even though
        # this packet is dropped below for lack of unprotect_rtp.
        # A callback failure is recorded, never raised — the
        # receiver loop must not die on it.
        if not self._first_media_seen:
            self._first_media_seen = True
            hook = self.on_first_media
            if hook is not None:
                try:
                    hook()
                except Exception as exc:  # noqa: BLE001
                    self._last_error = (
                        "on_first_media failed: %s" % (exc,))
        if self.config.unprotect_rtp is None:
            self.counters["rtp_rx_dropped"] += 1
            self._last_error = (
                "unprotect_rtp: missing (SRTP hook is required to "
                "receive media; inject it via TransportConfig)")
            return
        try:
            plain = self.config.unprotect_rtp(rtp_data)
            rtp = parse_rtp(plain)
        except Exception as exc:  # noqa: BLE001 - bad packet, count it
            self.counters["rtp_rx_dropped"] += 1
            self._last_error = "unprotect/parse failed: %s" % exc
            return
        if self._peer_ssrc is None:
            self._peer_ssrc = rtp["ssrc"]  # learn peer SSRC
        elif rtp["ssrc"] != self._peer_ssrc:
            # Not our peer's stream; drop (do not feed the callback).
            self.counters["rtp_rx_dropped"] += 1
            return
        self._highest_rx_seq = rtp["seq"]
        decode = self.config.decode_frame or (lambda b: b)
        try:
            pcm = decode(rtp["payload"])
        except Exception as exc:  # noqa: BLE001 - decoder error
            self.counters["rtp_rx_dropped"] += 1
            self._last_error = "decode failed: %s" % exc
            return
        if self._pcm_callback is None:
            return
        for frame in self._jitter.push(rtp["seq"], pcm):
            try:
                self._pcm_callback(frame)
            except Exception as exc:  # noqa: BLE001 - callback error
                self._last_error = "pcm callback failed: %s" % exc

    def _on_p2p(self, data, addr):
        self.counters["p2p_rx"] += 1
        try:
            pkt = parse_p2p(data)
        except ValueError as exc:
            self.counters["recv_errors"] += 1
            self._last_error = "bad P2P: %s" % (exc,)
            return
        subtype = pkt["subtype"]
        if pkt["call_session"] != self.config.call_session:
            # Not our call; ignore.
            return
        if subtype == 0x01:
            # Peer says hello: answer with ack carrying our address.
            self.peer_p2p_addr = addr
            ack = build_p2p_ack(self._role_byte(),
                                self.config.call_session,
                                self._local_addr_string())
            if self._send_to(ack, addr):
                self.counters["ack_tx"] += 1
        elif subtype == 0x02:
            # Peer acked our hello: confirm, then switch to P2P.
            self.peer_p2p_addr = addr
            self._p2p_acked = True
            confirm = build_p2p_confirm(
                self._role_byte(), self.config.call_session,
                self._local_addr_string())
            if self._send_to(confirm, addr):
                self.counters["confirm_tx"] += 1
            self._switch_to_p2p()
        elif subtype == 0x03:
            self.peer_p2p_addr = addr
            self._switch_to_p2p()
        elif subtype == 0x06:
            self._on_media(bytes(data[9:]), addr, via="p2p")
        # Subtypes 0x04/0x05/0x07 are counted above; their
        # contents (control numbers, session report) are not
        # needed for the media path yet.

    def _switch_to_p2p(self):
        if self._p2p_confirmed:
            return
        self._p2p_confirmed = True
        self.mode = "p2p"
