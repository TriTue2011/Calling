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
import re
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
    "build_req_forward",
    "build_rtp",
    "parse_rtp",
    "build_rtcp_compound",
    "parse_sr_middle_ntp",
    "TwccRecorder",
    "RxStats",
    "read_twseq_rtp",
    "build_rtcp_rr_video",
    "read_twseq",
    "wrap_rtcp",
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
RTP_PT_ACCEPTED_INCOMING = (112, 113)  # CHI cuoc goi DEN (ta la ben nhan): dien thoai gui tieng bang 113 (do 12/11, SRTP dung nhung bi loai vi PT); cuoc goi di giu nguyen 112
RTP_HEADER_LEN = 20
RTP_PLAIN_HEADER_LEN = 12
CONNECTED_PING_INTERVAL = 1.0   # ReqForward sub 10 sau khi nghe may
VIDEO_RTCP_MSG_TYPE = 0x0F  # RTCP cua luong video
VIDEO_MSG_TYPE = 0x0D       # relay: RTP video (zcall-native MSG_TYPES.VIDEO_RTP)
VIDEO_PT_KEY = 98           # khung khoa (SPS/PPS/IDR)
VIDEO_PT_DELTA = 97         # khung con lai, cung mot day seq
VIDEO_MAX_CHUNK = 1068      # dien thoai cat manh 1068 byte (1070 ca header 1c xx)
VIDEO_BURST = 6             # goi gui lien tiep truoc khi nghi 1 ms
SUB8_DELAY = 0.2           # zcall-native: ReqForward sub 8 ~0,2 s sau khi media bat dau
TWCC_INTERVAL = 0.05       # ZaloCall: transport-cc moi ~50 ms
TOKEN_ASCII_LEN = 154         # base64url chars on the wire
TOKEN_RAW_LEN = 115           # decoded bytes
DEVICE_CONST_PROBE_ID = 0x003E9765   # hardcoded probe id (disasm 0x894b2e)
DEVICE_CONST_PROBE_C2 = 0x012F833C   # hardcoded 2nd probe constant
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
P2P_BIND_FAST = 0.1                  # bind tới ứng viên: 0,1 s trong giây đầu
P2P_BIND_SLOW = 0.4                  # rồi 0,4 s
P2P_BIND_GIVE_UP = 15.0              # bỏ cuộc sau 15 s (như engine thật)
HELLO_INTERVAL = 0.5                 # P2P hello retransmit, seconds
RTCP_INTERVAL = 0.5                  # RTCP RR cadence, seconds. Ben nhan bao
                                    # "tin hieu yeu" neu >4 s khong co bao cao
                                    # RTCP (zca-js 2.3.13: durationCheckNoReportSec
                                    # = 4; ZaloRtcSession gui moi 500 ms). Truoc
                                    # day 5.0 s = luon vuot nguong.
KEEPALIVE_MEDIA_INTERVAL = 0.02      # goi am thanh giu ket noi, 50 goi/giay.
                                    # Ben nhan can >= 14 goi/2 s (zca-js:
                                    # audio_recheck_sock checkPkgRec) — khong
                                    # co thi bao "tin hieu yeu" du mang tot.
RX_SAMPLE_MAX = 20                   # so goi nhan dau tien lay mau (byte dau payload)
VOICE_HOLD_SECONDS = 0.25            # co tieng that trong khoang nay thi KHONG chen
                                    # khung im lang: mic gui theo goi 100 ms, chen
                                    # im lang vao khoang trong se keo gian thoi
                                    # gian va tre tang dan.
OPUS_SILENCE_FRAME = b"\xf8\xff\xfe"   # khung Opus im lang 20 ms (TOC 0xf8 +
                                    # 0xff 0xfe), hang so cua zca-js
                                    # OPUS_SILENCE_20MS_FRAME; KHONG can libopus.
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
# nested objects below. srtpNoSeq/srtpRTCP are NOT here — they
# are keys of zrtc_config, not extendData (confirmed correction).
# `srtpKey` IS accepted here since 2026-11-09 but ONLY because
# @softtynet/zca-js 2.3.13 `buildZrtcExtendData` puts the CALLER's
# own SRTP master key (base64, 40 chars) in extendData next to
# srtpMode=1. It is sent ONLY when the experimental caller-key mode
# is selected (server.py `_srtp_mode_for_call` == "key"); the default
# mode sends none. Whether the real server/peer honours it is a
# live-test question, not settled by the disassembly notes above.
EXTEND_DATA_KEYS = frozenset([
    "p2p", "callType", "video", "newZrtc", "packetMode",
    "gccMode", "gccAudio", "gccEarlyCall", "gccSVLR", "srtpMode",
    "srtcp", "sP2P", "maxFT", "platform", "fecTP",
    "supportHevcDecode", "tpType", "spTcp", "serverAddr",
    "select2side", "extraInfo", "serverResult", "numServers",
    "supportCallBusy", "srtpKey",
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
        out["video"] = {"codec": codec if isinstance(codec, (str, list))
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
    key = out.get("srtpKey")
    if key is not None and not (isinstance(key, str) and len(key) >= 40):
        del out["srtpKey"]          # sai dang: bo, khong doan
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
    ``call_session`` defaults to the 4 bytes of ``call_id`` little-endian:
    InitZRTP carries the signalling callId there (official PC capture
    37.51 s: f5357a2b = callId 0x2b7a35f5; zcall-native `buildInitZrtpPacket`
    writes u32 callId). Random bytes (the old default — the "0x2b last byte
    invariant" was only the high byte of the callId) leave the relay unable
    to pair us with the phone's InitZRTP of the same call.
    ``peer_session`` is the peer's session/SSRC (int u32 or
    None when not yet known — e.g. before the callee's 416).
    """
    relays: list
    token: bytes
    local_session: int
    peer_session: object = None
    call_id: int = 0
    # (ip, port) cua relay ma 11300 chi dinh (`rtpIP`) — relay MA DIEN THOAI DANG
    # DUNG (11301 bao no cho dien thoai). Neu relay do tra loi thi chon no du
    # relay khac tra loi truoc: gui uplink len relay khac thi dien thoai khong
    # bao gio nhan duoc goi cua ta (do 10/11: SR cua dien thoai RC=0).
    preferred_rtp: object = None
    callee_id: str = ""
    call_type: int = 1  # 1 = audio 1-1, 5 = audio group
    codec: str = "opus"
    extend_data: dict | None = None
    protect_rtp: object = None
    unprotect_rtp: object = None
    # SRTP rieng cho day seq video (cung khoa, ROC rieng) — khong co thi khong gui hinh.
    protect_video_rtp: object = None
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
    keepalive_media: bool = True      # gui khung im lang khi khong co tieng
    keepalive_media_interval: float = KEEPALIVE_MEDIA_INTERVAL
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
            self.call_session = struct.pack("<I", self.call_id & 0xFFFFFFFF)
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
    """Ping 45B (client -> relay, disasm §7.2) = ReqForward cmd 32 sub 10.

    Slot `rtt_ms` (u32 o byte 34..37) la SO GOI AM THANH NHAN DUOC TRONG GIAY
    QUA (zcall-native `reqForwardStatus`, ~50 khi on) — server chuyen no cho
    ben kia nhu bao cao nhan cua ta; gui 0 la bao "khong nhan duoc gi".

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


def packetize_video_frame(annexb, max_chunk=VIDEO_MAX_CHUNK):
    """Mot khung H.264 (Annex-B) -> cac payload RTP theo cach dien thoai dong
    goi (zcall-native `packetizeFrame`): vua thi gui nguyen, khong thi cat
    manh <= max_chunk byte kem header 2 byte 1c 80 (dau) / 1c 00 (giua) /
    1c 40 (cuoi). Bit marker dat o goi cuoi do nguoi goi."""
    annexb = bytes(annexb)
    if len(annexb) <= max_chunk:
        return [annexb]
    out = []
    for off in range(0, len(annexb), max_chunk):
        end = min(off + max_chunk, len(annexb))
        flag = 0x80 if off == 0 else (0x40 if end == len(annexb) else 0x00)
        out.append(bytes([0x1C, flag]) + annexb[off:end])
    return out


def build_req_forward(local_ssrc, relay_session, seq, sub_cmd, payload=b""):
    """ReqForward (cmd 32) 21 byte header + payload, cung bo cuc voi `build_ping`.
    zcall-native gui sub 8 payload [4, 0] (2 u32 LE) mot lan ~0,2 s sau khi
    media bat dau."""
    relay_session = _session_to_bytes(relay_session, "relay_session")
    pkt = bytearray(21)
    pkt[0] = 0x01
    pkt[1] = 0x01
    struct.pack_into("<H", pkt, 6, seq & 0xFFFF)
    struct.pack_into("<I", pkt, 10, local_ssrc & 0xFFFFFFFF)
    pkt[14:18] = relay_session
    struct.pack_into("<H", pkt, 18, 32)
    pkt[20] = sub_cmd & 0xFF
    return bytes(pkt) + bytes(payload)


def build_rtp(seq, timestamp, ssrc, payload, marker=False,
              ext=b"\x51\x00\x00\x00", pt=None):
    """RTP packet with the 20-byte PC header (bao-cao.md B.5), or the
    plain 12-byte RTP header when ``ext`` is None.

    PC style: [0]=0x90 (V2, X=1, CC=0) [1]=0x70/0xF0 (marker + PT 112)
    [2..3]=seq BE u16 [4..7]=timestamp BE u32 [8..11]=SSRC
    [12..13]=0xBEDE [14..15]=0x0001 [16..19]=extension 4B
    (default 51 00 00 00; byte 16 is 0x51, byte 17 is 0x00/0x01
    voice-activity-ish on downlink, byte 18 changes per packet
    — exact meaning UNCONFIRMED, pass ``ext`` to set it).
    Plain style (``ext=None``): [0]=0x80, same [1..11], payload at 12 —
    what the phone sends when the call is negotiated as the old ZRTC
    (measured 2026-11-09: every inbound packet starts 0x80).
    Payload follows the header and is SRTP-encrypted on the
    wire; this function builds the PLAINTEXT header only.
    """
    pt = RTP_PT if pt is None else pt
    if ext is None:
        pkt = bytearray(RTP_PLAIN_HEADER_LEN + len(payload))
        pkt[0] = 0x80
        pkt[1] = (0x80 if marker else 0x00) | pt
        struct.pack_into(">H", pkt, 2, seq & 0xFFFF)
        struct.pack_into(">I", pkt, 4, timestamp & 0xFFFFFFFF)
        struct.pack_into(">I", pkt, 8, ssrc & 0xFFFFFFFF)
        pkt[RTP_PLAIN_HEADER_LEN:] = payload
        return bytes(pkt)
    if len(ext) != 4:
        raise ValueError("RTP extension must be 4 bytes")
    pkt = bytearray(RTP_HEADER_LEN + len(payload))
    pkt[0] = 0x90
    pkt[1] = (0x80 if marker else 0x00) | pt
    struct.pack_into(">H", pkt, 2, seq & 0xFFFF)
    struct.pack_into(">I", pkt, 4, timestamp & 0xFFFFFFFF)
    struct.pack_into(">I", pkt, 8, ssrc & 0xFFFFFFFF)
    pkt[12:14] = b"\xbe\xde"
    struct.pack_into(">H", pkt, 14, 1)
    pkt[16:20] = ext
    pkt[20:] = payload
    return bytes(pkt)


def parse_rtp(data, accept_pts=(RTP_PT,)):
    """Parse an RTP packet: PC style (0x90, 20-byte header with BEDE
    extension) or plain (0x80, 12-byte header); payload is opaque.
    ``ext`` is b"" for the plain style."""
    if len(data) < RTP_PLAIN_HEADER_LEN:
        raise ValueError("RTP packet too short: %d bytes" % len(data))
    if data[0] not in (0x90, 0x80):
        raise ValueError("RTP first byte must be 0x90 (PC) or 0x80 "
                         "(plain), got 0x%02x" % data[0])
    if data[1] & 0x7F not in accept_pts:
        raise ValueError("RTP payload type must be %s, got %d"
                         % ("/".join(str(x) for x in accept_pts),
                            data[1] & 0x7F))
    (seq,) = struct.unpack_from(">H", data, 2)
    (timestamp,) = struct.unpack_from(">I", data, 4)
    (ssrc,) = struct.unpack_from(">I", data, 8)
    if data[0] == 0x80:
        ext, payload = b"", bytes(data[RTP_PLAIN_HEADER_LEN:])
    else:
        if len(data) < RTP_HEADER_LEN:
            raise ValueError("RTP packet too short: %d bytes" % len(data))
        if data[12:14] != b"\xbe\xde":
            raise ValueError("RTP extension profile must be BEDE, got %s"
                             % bytes(data[12:14]).hex())
        (ext_len,) = struct.unpack_from(">H", data, 14)
        if ext_len != 1:
            raise ValueError("RTP extension length must be 1 word, got %d"
                             % ext_len)
        ext, payload = bytes(data[16:20]), bytes(data[20:])
    return {"version": 2, "marker": bool(data[1] & 0x80),
            "payload_type": data[1] & 0x7F, "seq": seq,
            "timestamp": timestamp, "ssrc": ssrc,
            "ext": ext, "payload": payload}


def _ntp_now(now=None):
    """(ntp_sec, ntp_frac) cua thoi diem hien tai (epoch Unix -> NTP)."""
    t = time.time() if now is None else now
    sec = int(t)
    return (sec + 2208988800) & 0xFFFFFFFF, int((t - sec) * (1 << 32)) & 0xFFFFFFFF


def build_rtcp_compound(local_ssrc, rtp_ts, pkt_count, octet_count,
                        peer_ssrc=None, highest_seq=0, last_sr_mid=0,
                        dlsr=0, now=None, relay_session=b"\x00\x00\x00\x00",
                        block=None):
    """RTCP ghep SR (PT 200) [+ 1 khoi bao cao] + SDES CNAME, boc type-05.

    Y het `buildCompoundRtcpReport` cua @softtynet/zca-js 2.3.13: dien thoai
    doi "bao cao" tu ben kia trong `durationCheckNoReportSec` (4 s) — do 10/11:
    chi RR tran (LSR/DLSR = 0) thi tu giay thu 4 dien thoai bao ket noi khong
    on dinh. Khoi bao cao chi co khi da biet SSRC cua ben kia; LSR/DLSR lay tu
    SR cuoi cung nhan duoc de ben kia tinh duoc RTT (1 <= rtt < 9999 ms), chua
    nhan SR nao thi gia dinh 25 ms nhu zca.

    Outbound type-05 = [0x05][relay-id 4B][compound RTCP]."""
    relay_session = _session_to_bytes(relay_session, "relay_session")
    sec, frac = _ntp_now(now)
    rc = 1 if (peer_ssrc is not None or block is not None) else 0
    sr = bytearray(28 + 24 * rc)
    sr[0] = 0x80 | rc
    sr[1] = 200
    struct.pack_into(">H", sr, 2, len(sr) // 4 - 1)
    struct.pack_into(">IIIIII", sr, 4, local_ssrc & 0xFFFFFFFF, sec, frac,
                     rtp_ts & 0xFFFFFFFF, pkt_count & 0xFFFFFFFF,
                     octet_count & 0xFFFFFFFF)
    if rc and block is not None:
        _pack_block(sr, 28, block)        # thong ke that (mat goi, jitter, LSR/DLSR)
    elif rc:
        mid_now = (((sec & 0xFFFF) << 16) | (frac >> 16)) & 0xFFFFFFFF
        if last_sr_mid:
            lsr, dl = last_sr_mid & 0xFFFFFFFF, max(65, int(dlsr)) & 0xFFFFFFFF
        else:
            lsr, dl = (mid_now - 1638) & 0xFFFFFFFF, 1638
        struct.pack_into(">IIIIII", sr, 28, peer_ssrc & 0xFFFFFFFF, 0,
                         highest_seq & 0xFFFFFFFF, 10, lsr, dl)
    sdes = bytearray(12)                  # nhu ZaloCall: CNAME rong
    sdes[0], sdes[1] = 0x81, 202
    struct.pack_into(">H", sdes, 2, 2)
    struct.pack_into(">I", sdes, 4, local_ssrc & 0xFFFFFFFF)
    sdes[8] = 1
    return b"\x05" + relay_session + bytes(sr) + bytes(sdes)


TWCC_EXT_ID = 5
MAX_TWCC_PACKETS = 400


def read_twseq(ext):
    """So thu tu transport-wide (RTP header extension id 5) tu 4 byte `ext`
    cua header 20 byte, hoac None. Dang ZaloCall: 0x51 hi lo 0x00."""
    if len(ext) == 4 and ext[0] >> 4 == TWCC_EXT_ID and ext[0] & 0x0F == 1:
        return (ext[1] << 8) | ext[2]
    return None


class TwccRecorder:
    """Ghi thoi diem nhan cac goi co so thu tu transport-wide va dung RTCP
    transport-cc (RTPFB 205, fmt 15) — thu ZaloCall that gui cho dien thoai
    moi ~50 ms. Thieu duong hoi nay thi bo uoc luong bang thong cua dien thoai
    thay "duong tra ve chet". Cong tu zcall-native `TwccRecorder`/`encodeTwcc`."""

    def __init__(self):
        self.arrivals = {}      # seq mo rong -> thoi diem den (don vi 250 us)
        self.top = None
        self.next = None
        self.fb_count = 0
        self._lock = threading.Lock()   # add() o luong nhan, build() o luong lich

    def _unwrap(self, seq):
        if self.top is None:
            return seq
        u = seq + (self.top - (self.top & 0xFFFF))
        if u - self.top > 0x8000:
            u -= 0x10000
        elif self.top - u > 0x8000:
            u += 0x10000
        return u

    def add(self, seq, now_ms):
        with self._lock:
            self._add(seq, now_ms)

    def _add(self, seq, now_ms):
        u = self._unwrap(seq & 0xFFFF)
        if self.next is None:
            self.next = u
        if u < self.next or u in self.arrivals:
            return
        self.arrivals[u] = int(round(now_ms * 4))
        if self.top is None or u > self.top:
            self.top = u

    def pending(self):
        return self.next is not None and self.top is not None \
            and self.top >= self.next

    def build(self, sender_ssrc, media_ssrc):
        with self._lock:
            return self._build(sender_ssrc, media_ssrc)

    def _build(self, sender_ssrc, media_ssrc):
        out = []
        while self.pending():
            base = self.next
            end = min(self.top, base + MAX_TWCC_PACKETS - 1)
            if not any(sq in self.arrivals for sq in range(base, end + 1)):
                self.next = end + 1
                continue
            out.append(_encode_twcc(sender_ssrc, media_ssrc, base, end,
                                    self.arrivals, self.fb_count & 0xFF))
            self.fb_count += 1
            for sq in range(base, end + 1):
                self.arrivals.pop(sq, None)
            self.next = end + 1
        return out


def _encode_twcc(sender_ssrc, media_ssrc, base, end, arrivals, fb_count):
    count = end - base + 1
    first_q = next(arrivals[sq] for sq in range(base, end + 1)
                   if sq in arrivals)
    ref_units = first_q // 256              # moc tham chieu: don vi 64 ms
    prev_q = ref_q = ref_units * 256
    symbols, deltas = [], []
    for sq in range(base, end + 1):
        q = arrivals.get(sq)
        if q is None:
            symbols.append(0)
            continue
        d = q - prev_q
        prev_q = q
        if 0 <= d <= 255:
            symbols.append(1)
        else:
            symbols.append(2)
            d = max(-32768, min(32767, d))
        deltas.append(d)
    chunks, i = [], 0
    while i < len(symbols):
        run = 1
        while i + run < len(symbols) and symbols[i + run] == symbols[i] \
                and run < 0x1FFF:
            run += 1
        if run >= 8:
            chunks.append((symbols[i] << 13) | run)
            i += run
            continue
        v = 0xC000
        for k in range(7):
            v |= (symbols[i + k] if i + k < len(symbols) else 0) << (12 - 2 * k)
        chunks.append(v)
        i += 7
    delta_bytes = symbols.count(1) + 2 * symbols.count(2)
    length = 4 + 8 + 8 + 2 * len(chunks) + delta_bytes
    padded = (length + 3) & ~3
    b = bytearray(padded)
    b[0], b[1] = 0x8F, 205
    struct.pack_into(">H", b, 2, padded // 4 - 1)
    struct.pack_into(">II", b, 4, sender_ssrc & 0xFFFFFFFF,
                     media_ssrc & 0xFFFFFFFF)
    struct.pack_into(">HH", b, 12, base & 0xFFFF, count)
    b[16:19] = (ref_units & 0xFFFFFF).to_bytes(3, "big")
    b[19] = fb_count & 0xFF
    o = 20
    for c in chunks:
        struct.pack_into(">H", b, o, c)
        o += 2
    di = 0
    for sym in symbols:
        if sym == 1:
            b[o] = deltas[di]
            o += 1
            di += 1
        elif sym == 2:
            struct.pack_into(">h", b, o, deltas[di])
            o += 2
            di += 1
    return bytes(b)


def parse_twcc_status(b):
    """(nhan, mat) cua mot RTPFB transport-cc 205/15: so goi cua TA ma dien thoai
    bao da nhan va chua nhan (chi dem, khong lay thoi gian)."""
    if len(b) < 20 or b[1] != 205 or b[0] & 0x1F != 15:
        return 0, 0
    count = struct.unpack_from(">H", b, 14)[0]
    status, off = [], 20
    while len(status) < count and off + 2 <= len(b):
        c = struct.unpack_from(">H", b, off)[0]
        off += 2
        if c & 0x8000 == 0:
            status += [(c >> 13) & 3] * (c & 0x1FFF)
        elif c & 0x4000:
            status += [(c >> (12 - 2 * k)) & 3 for k in range(7)]
        else:
            status += [(c >> (13 - k)) & 1 for k in range(14)]
    status = status[:count]
    got = sum(1 for x in status if x)
    return got, len(status) - got


def wrap_rtcp(rtcp, relay_session):
    """Boc mot goi RTCP tran thanh type-05 qua relay."""
    return b"\x05" + _session_to_bytes(relay_session, "relay_session") + rtcp


def read_twseq_rtp(rtp):
    """So thu tu transport-wide trong header RTP day du (duyet cac phan tu
    mo rong one-byte BEDE), hoac None. Goi video cua dien thoai co the mang
    them phan tu khac ngoai id 5."""
    if len(rtp) < 16 or not rtp[0] & 0x10:
        return None
    off = 12 + 4 * (rtp[0] & 0x0F)
    if off + 4 > len(rtp) or rtp[off:off + 2] != b"\xbe\xde":
        return None
    end = min(len(rtp), off + 4 + 4 * struct.unpack_from(">H", rtp, off + 2)[0])
    off += 4
    while off < end:
        b = rtp[off]
        if b == 0:
            off += 1
            continue
        eid, ln = b >> 4, (b & 0x0F) + 1
        if eid == 15:
            return None
        if eid == TWCC_EXT_ID and ln == 2 and off + 3 <= end:
            return struct.unpack_from(">H", rtp, off + 1)[0]
        off += 1 + ln
    return None


class RxStats:
    """Thong ke nhan mot luong RTP (RFC 3550 A.1/A.3/6.4.1) de dien khoi bao cao
    cua RTCP: mat goi, jitter that, LSR/DLSR cua SR cuoi tu ben kia. Cong tu
    zcall-native `RxStats`."""

    def __init__(self, clock_hz):
        self.clock_hz = clock_hz
        self.ssrc = 0
        self.started = False
        self.base_seq = self.max_seq = 0
        self.cycles = 0
        self.received = 0
        self.expected_prior = self.received_prior = 0
        self.jitter = 0.0
        self.transit = None
        self.lsr = 0
        self.lsr_at = None
        self._seen = collections.deque(maxlen=512)
        self._seen_set = set()

    def on_packet(self, seq, ts, ssrc, now_ms):
        if not self.started:
            self.started = True
            self.ssrc = ssrc & 0xFFFFFFFF
            self.base_seq = self.max_seq = seq
        else:
            d = (seq - self.max_seq) & 0xFFFF
            if d != 0 and d < 0x8000:
                if seq < self.max_seq:
                    self.cycles += 0x10000
                self.max_seq = seq
        ext = self.cycles + seq
        if ext in self._seen_set:
            return
        if len(self._seen) == self._seen.maxlen:
            self._seen_set.discard(self._seen[0])
        self._seen.append(ext)
        self._seen_set.add(ext)
        self.received += 1
        transit = now_ms * self.clock_hz / 1000.0 - ts
        if self.transit is not None:
            self.jitter += (abs(transit - self.transit) - self.jitter) / 16.0
        self.transit = transit

    def on_sr_middle_ntp(self, mid, now_ms):
        self.lsr, self.lsr_at = mid & 0xFFFFFFFF, now_ms

    def block(self, now_ms):
        """Khoi bao cao (dict) hoac None khi chua nhan goi nao."""
        if not self.started:
            return None
        ext_high = self.cycles + self.max_seq
        expected = ext_high - self.base_seq + 1
        lost = expected - self.received
        exp_int = expected - self.expected_prior
        rec_int = self.received - self.received_prior
        self.expected_prior, self.received_prior = expected, self.received
        lost_int = exp_int - rec_int
        frac = 0 if exp_int <= 0 or lost_int <= 0 else min(255, lost_int * 256 // exp_int)
        return {"ssrc": self.ssrc, "fraction": frac,
                "cum_lost": max(-0x800000, min(0x7FFFFF, lost)),
                "ext_high": ext_high & 0xFFFFFFFF,
                "jitter": int(round(self.jitter)),
                "lsr": self.lsr,
                "dlsr": (int((now_ms - self.lsr_at) * 65536 / 1000.0)
                         if self.lsr_at is not None else 0) & 0xFFFFFFFF}


def _pack_block(buf, off, blk):
    struct.pack_into(">I", buf, off, blk["ssrc"] & 0xFFFFFFFF)
    buf[off + 4] = blk["fraction"] & 0xFF
    buf[off + 5:off + 8] = (blk["cum_lost"] & 0xFFFFFF).to_bytes(3, "big")
    struct.pack_into(">IIII", buf, off + 8, blk["ext_high"] & 0xFFFFFFFF,
                     blk["jitter"] & 0xFFFFFFFF, blk["lsr"] & 0xFFFFFFFF,
                     blk["dlsr"] & 0xFFFFFFFF)


def build_rtcp_rr_video(local_ssrc, block, relay_session,
                        msg_type=VIDEO_RTCP_MSG_TYPE):
    """RTCP video: RR (PT 201) voi khoi bao cao luong video cua dien thoai +
    SDES rong, boc relay loai 0x0f (zcall-native `videoReport`)."""
    relay_session = _session_to_bytes(relay_session, "relay_session")
    rr = bytearray(8 + 24)
    rr[0], rr[1] = 0x81, 201
    struct.pack_into(">H", rr, 2, len(rr) // 4 - 1)
    struct.pack_into(">I", rr, 4, local_ssrc & 0xFFFFFFFF)
    _pack_block(rr, 8, block)
    sdes = bytearray(12)
    sdes[0], sdes[1] = 0x81, 202
    struct.pack_into(">H", sdes, 2, 2)
    struct.pack_into(">I", sdes, 4, local_ssrc & 0xFFFFFFFF)
    sdes[8] = 1
    return bytes([msg_type]) + relay_session + bytes(rr) + bytes(sdes)


def rtcp_kinds(rtcp):
    """[(PT, RC/FMT, byte)] cua tung goi con trong RTCP ghep (chan doan)."""
    out, off = [], 0
    while off + 4 <= len(rtcp) and len(out) < 8:
        length = (struct.unpack_from(">H", rtcp, off + 2)[0] + 1) * 4
        out.append((rtcp[off + 1], rtcp[off] & 0x1F, length))
        if length <= 0:
            break
        off += length
    return out


def parse_sr_middle_ntp(rtcp):
    """Gia tri LSR (32 bit giua cua NTP) cua SR dau tien trong goi RTCP ghep,
    hoac None. `rtcp` la RTCP tran (da bo phan boc type-05)."""
    off = 0
    while off + 4 <= len(rtcp):
        length = (struct.unpack_from(">H", rtcp, off + 2)[0] + 1) * 4
        if rtcp[off + 1] == 200 and off + 16 <= len(rtcp):
            sec, frac = struct.unpack_from(">II", rtcp, off + 8)
            return ((sec & 0xFFFF) << 16) | (frac >> 16)
        if length <= 0:
            break
        off += length
    return None


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


# Kiểu gói P2P của engine zcall-native khi NGHE MÁY (đã chạy thật với điện thoại): bind tới TỪNG ứng viên của bên gọi có
# u16 LE seq + u32 BE chỉ số ứng viên; điện thoại trả kind 2 (seq, chỉ số, "ip|port" nó thấy ta) ta đáp kind 3 lặp lại seq/chỉ số +
# "ip|port" của nó; kind 4 byte 9 = 1 là ping, đáp bằng pong (bản sao, role của ta, byte 9 = 2).
def build_p2p_bind(role, call_session, seq, index):
    return _p2p_header(role, call_session, 0x01) + struct.pack("<H", seq & 0xFFFF) + struct.pack(">I", index & 0xFFFFFFFF)


def build_p2p_bind_answer(role, call_session, request, peer_addr):
    addr_b = peer_addr.encode("latin-1")
    return _p2p_header(role, call_session, 0x03) + bytes(request[9:15]) + struct.pack("<I", len(addr_b)) + addr_b


def build_p2p_pong(role, ping):
    pong = bytearray(ping)
    pong[2] = role & 0xFF
    pong[9] = 2
    return bytes(pong)


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
        self.hold_media = False         # True: KHONG gui goi tieng nao (ca keepalive im lang lan mic) - cuoc goi den giu cho toi khi 11303 co ket qua
        self.on_init_sent = None        # goi ngay SAU khi gui goi Init dau tien (khong cho type-02): cho 11303 nghe may cuoc goi den gui sat sau Init
        self._first_media_seen = False
        self._peer_plain_rtp = False   # hoc tu goi nhan duoc (xem _on_media)
        self._sock = None
        self._stop = threading.Event()
        self._recv_thread = None
        self._sched_thread = None
        self._lock = threading.Lock()
        self._pcm_callback = None
        self._seq = random.randint(0, 0xFFFF)  # RTP seq, u16
        self._timestamp = random.randint(0, 0xFFFFFFFF)
        self._ping_seq = 0
        self._rx_mark_t = time.monotonic()   # cua so 1 s dem goi am thanh nhan
        self._rx_mark_n = 0
        self._rx_last_sec = 0
        self._sub8_due = None               # gui ReqForward sub 8 mot lan
        self._hello_count = 0
        self._p2p_acked = False
        self._p2p_cands = []            # [(ip, port, index)] ứng viên P2P bên gọi khai (cuộc gọi ĐẾN); rỗng = đường cũ
        self._p2p_bind_t0 = None
        self._p2p_bind_last = 0.0
        self._p2p_bind_seq = 0
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
        self._last_media_tx = 0.0
        self._voice_until = 0.0
        self._rx_head = []          # (do dai, byte dau) cua RX_SAMPLE_MAX payload dau
        self._highest_rx_seq = None
        self._twcc = TwccRecorder()
        self._rx_audio = RxStats(16000)
        self._rx_video = RxStats(90000)
        self._last_video_report = 0.0
        self._last_twcc = 0.0
        self._vseq = random.randrange(0x8000)   # day seq video rieng
        self._v_ts_base = random.randrange(0x7FFFFFFF)
        self._v_start = None
        self._v_key_sent = False
        self._pcm_lock = threading.Lock()   # tuan tu hoa ma hoa + gui tieng that
        self._tw_seq = 0                # so thu tu transport-wide goi di
        self._tx_pkts = 0               # cho SR cua RTCP
        self._tx_octets = 0
        self._last_sr_mid = 0           # LSR cua SR cuoi nhan duoc
        self._last_sr_at = 0.0
        self._tw_ok = 0                 # goi cua ta dien thoai bao da nhan (TWCC)
        self._tw_lost = 0
        self._peer_block = None         # khoi bao cao cuoi cua dien thoai ve luong cua ta
        self._peer_log_at = 0.0
        self._peer_sr_blocks = None     # RC cua SR cuoi tu ben kia
        self.counters = {
            "probe_tx": 0, "setup_init_tx": 0, "setup_refresh_tx": 0,
            "ping_tx": 0, "rtcp_tx": 0, "rtcp_rx": 0, "hello_tx": 0, "ack_tx": 0,
            "confirm_tx": 0, "type02_rx": 0, "keepalive_rx": 0,
            "ping_reply_rx": 0, "rtp_tx": 0, "rtp_rx": 0,
            "rtp_rx_dropped": 0, "keepalive_tx": 0, "p2p_rx": 0, "p2p_media_rx": 0,
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
        _hook = self.on_init_sent
        if _hook is not None:
            try:
                _hook()
            except Exception as exc:  # noqa: BLE001 - hook chan doan/thu nghiem khong duoc lam hong cuoc goi
                print("[media] on_init_sent failed: %s" % (exc,), flush=True)
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
        # Nhieu luong (moi POST /api/call/audio/in la mot luong) co the goi cung
        # luc: ma hoa + cap seq phai tuan tu, khong thi thu tu goi dao lon va
        # trang thai codec bi pha.
        with self._pcm_lock:
            self._send_payload(encode(pcm))
            self._voice_until = time.monotonic() + VOICE_HOLD_SECONDS

    def send_video_frame(self, annexb, key):
        """Gui mot khung H.264 (Annex-B): cat manh -> RTP (PT 98 khung khoa /
        97 con lai, marker o goi cuoi, TWCC dung chung voi am thanh) -> SRTP rieng
        -> relay loai 0x0d. Khung dau tien PHAI la khung khoa (dien thoai khong
        ve gi truoc khung khoa) — khung khac bi bo qua, tra False."""
        if self.config.protect_video_rtp is None:
            raise MissingTransportParam(
                "protect_video_rtp: missing (video needs its own SRTP hook)")
        if self.selected_relay is None or not self.relay_session:
            raise RuntimeError("no relay selected yet")
        if not key and not self._v_key_sent:
            return False
        self._v_key_sent = self._v_key_sent or bool(key)
        now = time.monotonic()
        if self._v_start is None:
            self._v_start = now
        ts = (self._v_ts_base + int((now - self._v_start) * 90000)) \
            & 0xFFFFFFFF
        chunks = packetize_video_frame(annexb)
        for i, chunk in enumerate(chunks):
            with self._lock:
                self._tw_seq = (self._tw_seq + 1) & 0xFFFF
                rtp = build_rtp(
                    self._vseq, ts, self.config.local_ssrc, chunk,
                    marker=(i == len(chunks) - 1),
                    ext=bytes([0x51, self._tw_seq >> 8,
                               self._tw_seq & 0xFF, 0]),
                    pt=VIDEO_PT_KEY if key else VIDEO_PT_DELTA)
                protected = self.config.protect_video_rtp(rtp)
                self._vseq = (self._vseq + 1) & 0xFFFF
                pkt = bytes([VIDEO_MSG_TYPE]) + self.relay_session + protected
                ok = self._send_to(pkt, self.selected_relay.rtp_addr())
            if not ok:
                raise RuntimeError("send failed: %s" % self._last_error)
            self.counters["video_tx"] = self.counters.get("video_tx", 0) + 1
            if i % VIDEO_BURST == VIDEO_BURST - 1:
                time.sleep(0.001)
        self.counters["video_frames_tx"] = \
            self.counters.get("video_frames_tx", 0) + 1
        return True

    def _send_payload(self, payload, keepalive=False):
        """One RTP media packet: header (seq +1, ts +320) -> protect_rtp
        -> relay type-03 or P2P. Shared by send_pcm and the silence
        keepalive. Raises like send_pcm."""
        if self.hold_media:
            # Cuoc goi DEN: dien thoai ben goi coi bat ky goi tieng nao cua ben nghe la «da nghe may» va xac nhan (answer_ack) truoc khi 11303 toi
            # may chu -> 11303 bi -101, Zalo phu do chuong ~45 giay. Giu tieng cho toi khi 11303 co ket qua; relay van dang ky (Init/ping giu nguyen).
            self.counters["held_tx"] = self.counters.get("held_tx", 0) + 1
            return
        if self.config.protect_rtp is None:
            raise MissingTransportParam(
                "protect_rtp: missing (SRTP hook is required to send "
                "media; inject it via TransportConfig)")
        # Giu khoa suot tu cap seq den luc gui: luong keepalive va luong
        # mic cung goi ham nay; neu protect/gui nam ngoai khoa thi seq co the
        # ra day khong theo thu tu va lam lech ROC cua SRTP.
        with self._lock:
            self._seq = (self._seq + 1) & 0xFFFF
            self._timestamp = (self._timestamp + RTP_TS_STEP) & 0xFFFFFFFF
            self._tw_seq = (self._tw_seq + 1) & 0xFFFF
            rtp = build_rtp(
                self._seq, self._timestamp,
                self.config.local_ssrc, payload,
                ext=(None if self._peer_plain_rtp else bytes(
                    [0x51, self._tw_seq >> 8, self._tw_seq & 0xFF, 0])))
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
                    "no relay selected yet (no type-02 52B received); "
                    "media cannot be sent before the relay handshake")
            if not ok:
                raise RuntimeError("send failed: %s" % self._last_error)
            self._last_media_tx = time.monotonic()
            if self._tx_pkts == 0:
                print("[media] first tx len=%d head=%s" % (
                    len(pkt), bytes(pkt[:24]).hex()), flush=True)
            self._tx_pkts += 1
            self._tx_octets += len(payload)
            self.counters["keepalive_tx" if keepalive else "rtp_tx"] += 1

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

    def set_p2p_candidates(self, cands):
        """Ứng viên P2P (IPv4) do bên gọi khai trong lời mời, dạng [{"ip", "port", "type"}]. Có ứng viên thì sau begin_p2p() ta gửi bind tới TỪNG
        ứng viên (kể cả địa chỉ LAN, đường duy nhất đi được khi hai máy cùng mạng và NAT không vòng lại) và đáp gói P2P của điện thoại."""
        out = []
        for i, c in enumerate(cands or []):
            try:
                ip, port = str(c.get("ip", "")), int(c.get("port", 0))
            except (AttributeError, TypeError, ValueError):
                continue
            if port > 0 and re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
                out.append((ip, port, i))
        self._p2p_cands = out

    def local_p2p_candidates(self, extra_hosts=()):
        """Ứng viên P2P của ta cho câu trả lời: địa chỉ IPv4 máy (kiểu 0) trên cổng của socket media."""
        port = 0
        try:
            port = self._sock.getsockname()[1]
        except (OSError, AttributeError):
            pass
        hosts = []
        for h in extra_hosts:
            if h and h not in hosts:
                hosts.append(h)
        if not hosts:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(("8.8.8.8", 53))              # không gửi gói nào, chỉ hỏi nhân hệ điều hành địa chỉ đi ra
                hosts.append(probe.getsockname()[0])
            except OSError:
                pass
            finally:
                probe.close()
        return [{"ip": h, "port": port, "type": 0} for h in hosts if port and h and h != "0.0.0.0"]

    def _send_binds(self, now):
        if self._p2p_bind_t0 is None:
            self._p2p_bind_t0 = now
        age = now - self._p2p_bind_t0
        if age > P2P_BIND_GIVE_UP or now - self._p2p_bind_last < (P2P_BIND_FAST if age < 1.0 else P2P_BIND_SLOW):
            return
        self._p2p_bind_last = now
        for ip, port, idx in self._p2p_cands:
            if self._send_to(build_p2p_bind(self._role_byte(), self.config.call_session, self._p2p_bind_seq, idx), (ip, port)):
                self.counters["bind_tx"] = self.counters.get("bind_tx", 0) + 1
        self._p2p_bind_seq += 1

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
            "rx_sample": self._rx_sample(),
            "peer_sr_blocks": self._peer_sr_blocks,
            "peer_twcc": {"ok": self._tw_ok, "lost": self._tw_lost},
            "peer_block": self._peer_block,
            "jitter_dropped_late": self._jitter.dropped_late,
            "jitter_reordered": self._jitter.reordered,
            "last_error": self._last_error,
        }

    def _rx_sample(self):
        """Dau hieu RTP tran hay da ma hoa, tu byte dau cua cac payload nhan
        duoc: Opus tran co TOC on dinh (cung mot luong -> byte dau gan nhu
        khong doi), ban ma thi byte dau ngau nhien. Khong co khoa nao o day.
        {"n", "toc_agree" (ti le byte dau pho bien nhat), "head" (<= 6 mau
        "do dai:byte dau hex")}."""
        head = list(self._rx_head)
        if not head:
            return {"n": 0, "toc_agree": 0.0, "head": []}
        firsts = [b for _n, b in head]
        top = max(set(firsts), key=firsts.count)
        return {"n": len(head),
                "toc_agree": round(firsts.count(top) / len(firsts), 2),
                "head": ["%d:%02x" % (n, b) for n, b in head[:6]]}

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
        now = time.monotonic()
        if now - self._rx_mark_t >= 1.0:
            got = self.counters["rtp_rx"] - self.counters["rtp_rx_dropped"]
            self._rx_last_sec = max(0, got - self._rx_mark_n)
            self._rx_mark_t, self._rx_mark_n = now, got
        pkt = build_ping(self.config.local_ssrc, self.relay_session,
                         self._ping_seq, rtt_ms=self._rx_last_sec)
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
        if self.selected_relay is None:
            return
        now = time.monotonic()
        dlsr = int((now - self._last_sr_at) * 65536) if self._last_sr_mid else 0
        pkt = build_rtcp_compound(
            self.config.local_ssrc, self._timestamp, self._tx_pkts,
            self._tx_octets, peer_ssrc=self._peer_ssrc,
            block=self._rx_audio.block(now * 1000.0),
            highest_seq=self._highest_rx_seq or 0,
            last_sr_mid=self._last_sr_mid, dlsr=dlsr,
            relay_session=self.relay_session or b"\x00\x00\x00\x00")
        if self._send_to(pkt, self.selected_relay.rtcp_addr()):
            self.counters["rtcp_tx"] += 1

    def _send_video_report(self, now):
        if self.selected_relay is None or not self.relay_session:
            return
        blk = self._rx_video.block(now * 1000.0)
        if blk is None:
            return
        pkt = build_rtcp_rr_video(self.config.local_ssrc, blk,
                                  self.relay_session)
        if self._send_to(pkt, self.selected_relay.rtcp_addr()):
            self.counters["video_rtcp_tx"] = \
                self.counters.get("video_rtcp_tx", 0) + 1

    def _send_twcc(self):
        if self.selected_relay is None or self._peer_ssrc is None \
                or not self.relay_session:
            return
        for fb in self._twcc.build(self.config.local_ssrc, self._peer_ssrc):
            if self._send_to(wrap_rtcp(fb, self.relay_session),
                             self.selected_relay.rtcp_addr()):
                self.counters["twcc_tx"] = self.counters.get("twcc_tx", 0) + 1

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
                # Do khi do chuong ~10 Hz, sau khi nghe may 1 Hz (pcap Zalo PC
                # chinh thuc: gap 1,0 s suot cuoc goi).
                _ping_gap = (max(cfg.ping_interval, CONNECTED_PING_INTERVAL)
                             if self._first_media_seen else cfg.ping_interval)
                if (self.selected_relay is not None
                        and now - self._last_ping >= _ping_gap):
                    self._send_ping()
                    self._last_ping = now
                if (self.peer_reflexive is not None
                        and self._p2p_started
                        and not self._p2p_confirmed
                        and now - self._last_hello >= cfg.hello_interval):
                    self._send_hello()
                if self._p2p_cands and self._p2p_started and not self._p2p_confirmed:
                    self._send_binds(now)
                if (self.state == "connected"
                        and now - self._last_rtcp >= cfg.rtcp_interval):
                    self._send_rtcp()
                    self._last_rtcp = now
                if (self.state == "connected" and self._rx_video.started
                        and now - self._last_video_report >= 1.0):
                    self._last_video_report = now
                    self._send_video_report(now)
                if (self.state == "connected"
                        and now - self._last_twcc >= TWCC_INTERVAL):
                    self._send_twcc()
                    self._last_twcc = now
                if self._sub8_due is not None and now >= self._sub8_due \
                        and self.selected_relay is not None \
                        and self.relay_session:
                    self._sub8_due = None
                    self._send_to(build_req_forward(
                        cfg.local_ssrc, self.relay_session, 0, 8,
                        struct.pack("<II", 4, 0)),
                        self.selected_relay.rtp_addr())
                self._maybe_send_keepalive_media(now)
            except Exception as exc:  # noqa: BLE001 - scheduler survives
                self._last_error = "scheduler: %s" % exc
            # 10 ms: du min cho nhip 20 ms cua goi am thanh giu ket noi.
            self._stop.wait(0.01)

    def _maybe_send_keepalive_media(self, now):
        """Khung Opus im lang 50 goi/giay khi KHONG co tieng that.

        Chi gui khi da chon relay + co hook protect (hook "plain" khi
        khong ma hoa) va khong co `send_pcm` nao trong khoang vua roi,
        nen tieng that luon thang. Loi gui (chua co relay...) khong lam
        sap vong lap lich."""
        cfg = self.config
        if (not cfg.keepalive_media or cfg.protect_rtp is None
                or self.selected_relay is None or not self.relay_session):
            return
        if now - self._last_media_tx < cfg.keepalive_media_interval \
                or now < self._voice_until:
            return
        try:
            self._send_payload(OPUS_SILENCE_FRAME, keepalive=True)
        except (RuntimeError, MissingTransportParam):
            pass

    # -- receiver ----------------------------------------------------

    def _recv_loop(self):
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:                    # stop() vua dong socket
                break
            try:
                data, addr = sock.recvfrom(65535)
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
        elif head == 0x0E:
            self._on_video(data[1:])
        elif head == 0x0F:
            self._on_video_rtcp(data)
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
        pref = self.config.preferred_rtp
        is_pref = pref is not None and relay.rtp_addr() == tuple(pref)
        if self.selected_relay is None or (
                is_pref and self.selected_relay is not relay):
            # First type-02 wins (initSuccessTime rule) — except that the
            # relay the 11300 designated beats any earlier one (see
            # TransportConfig.preferred_rtp). Both fields change together.
            with self._lock:
                self.selected_relay = relay
                self.relay_session = info["relay_session"]
            self.state = "connected"
            print("[media] relay selected %s:%s preferred=%s" % (
                relay.rtp_ip, relay.rtp_port, is_pref), flush=True)
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

    def _on_video(self, rtp):
        """Goi RTP video tu dien thoai (loai 0x0e): khong giai ma hinh, nhung PHAI
        ghi vao TWCC (chung khong gian so thu tu voi am thanh) va thong ke nhan
        — thieu thi dien thoai thay phan lon goi video cua no \"mat\" va bao mang
        yeu (do 10/11: dong ho cuoc goi video chuyen cam)."""
        if len(rtp) < 12 or rtp[0] >> 6 != 2:
            self.counters["unknown_rx"] += 1
            return
        now_ms = time.monotonic() * 1000.0
        self.counters["video_rx"] = self.counters.get("video_rx", 0) + 1
        tw = read_twseq_rtp(rtp)
        if tw is not None:
            self._twcc.add(tw, now_ms)
        seq, ts, ssrc = struct.unpack_from(">HII", rtp, 2)[0], \
            struct.unpack_from(">I", rtp, 4)[0], struct.unpack_from(">I", rtp, 8)[0]
        self._rx_video.on_packet(seq, ts, ssrc, now_ms)

    def _on_video_rtcp(self, data):
        self.counters["video_rtcp_rx"] = self.counters.get("video_rtcp_rx", 0) + 1
        mid = parse_sr_middle_ntp(bytes(data[5:]))
        if mid is not None:
            self._rx_video.on_sr_middle_ntp(mid, time.monotonic() * 1000.0)

    def _on_rtcp(self, data, addr):
        # Dem RTCP vao; chi cac truong SR can cho LSR/DLSR cua bao cao ta gui.
        self.counters["rtcp_rx"] += 1
        body = bytes(data[5:])
        if self.counters["rtcp_rx"] <= 6:
            print("[rtcp-rx] #%d %s" % (self.counters["rtcp_rx"],
                                        rtcp_kinds(body)), flush=True)
        off = 0
        while off + 4 <= len(body):
            plen = (struct.unpack_from(">H", body, off + 2)[0] + 1) * 4
            pt, rc = body[off + 1], body[off] & 0x1F
            if pt == 205 and rc == 15:
                ok, lost = parse_twcc_status(body[off:off + plen])
                self._tw_ok += ok
                self._tw_lost += lost
            elif pt in (200, 201) and rc >= 1:
                boff = off + (28 if pt == 200 else 8)
                if boff + 24 <= len(body):
                    ssrc, fl, hi, jit = struct.unpack_from(">IIII", body, boff)
                    self._peer_block = {"fraction": fl >> 24,
                                        "cum_lost": fl & 0xFFFFFF,
                                        "jitter": jit}
            if plen <= 0:
                break
            off += plen
        _now = time.monotonic()
        # Toc do goi that moi 5 giay (12/11: dien thoai chi gui ~54 goi tieng trong 18 s = qua thua): tx/rx tieng, video, RTCP, P2P; de lan sau doc
        # nhat ky la biet chieu nao dang chet va P2P co chay khong.
        if _now - getattr(self, "_cnt_log_at", 0.0) >= 5.0:
            self._cnt_log_at = _now
            _c = self.counters
            print("[media-rate] tx=%d rx=%d rx_pt113=%d rx_drop=%d video_tx=%d video_rx=%d rtcp_rx=%d p2p_rx=%d p2p_media_rx=%d binds=%d" % (
                _c.get("rtp_tx", 0), _c.get("rtp_rx", 0), _c.get("rtp_rx_pt113", 0), _c.get("rtp_rx_dropped", 0), _c.get("video_tx", 0),
                _c.get("video_rx", 0), _c.get("rtcp_rx", 0), _c.get("p2p_rx", 0), _c.get("p2p_media_rx", 0), _c.get("bind_tx", 0)), flush=True)
        if _now - self._peer_log_at >= 5.0 and (self._tw_ok or self._tw_lost):
            self._peer_log_at = _now
            print("[peer-view] twcc ok=%d lost=%d block=%s" % (
                self._tw_ok, self._tw_lost, self._peer_block), flush=True)
        if len(body) >= 2 and body[1] == 200:
            # So khoi bao cao trong SR cua ben kia: 0 = ben kia CHUA nhan duoc
            # luong RTP hop le nao cua ta (do 10/11: dien thoai bao RC=0).
            self._peer_sr_blocks = body[0] & 0x1F
        mid = parse_sr_middle_ntp(body)
        if mid is not None:
            self._last_sr_mid = mid
            self._last_sr_at = time.monotonic()
            self._rx_audio.on_sr_middle_ntp(mid, time.monotonic() * 1000.0)

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
            self._sub8_due = time.monotonic() + SUB8_DELAY
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
            rtp = parse_rtp(plain, RTP_PT_ACCEPTED_INCOMING if not self.config.is_caller else (RTP_PT,))
        except Exception as exc:  # noqa: BLE001 - bad packet, count it
            self.counters["rtp_rx_dropped"] += 1
            self._last_error = "unprotect/parse failed: %s" % exc
            if self.counters["rtp_rx_dropped"] <= 3:
                # Chan doan: chi 24 byte DAU (header), khong ghi payload.
                print("[media] rx drop #%d len=%d via=%s head=%s err=%s" % (
                    self.counters["rtp_rx_dropped"], len(rtp_data), via,
                    bytes(rtp_data[:24]).hex(), exc), flush=True)
            return
        # Dien thoai goi kieu ZRTC cu gui RTP tran 12 byte (0x80); gui lai
        # cung kieu de ben kia phan tich duoc goi cua ta.
        if self.counters["rtp_rx"] == 1:
            print("[media] first rx len=%d head=%s" % (
                len(rtp_data), bytes(rtp_data[:24]).hex()), flush=True)
        _tr = self.__dict__.setdefault("_rx_trace", [])
        if len(_tr) < 60:                                   # vet 60 goi tieng dau (seq, ts, do dai, loai goi, thoi diem ms) — chan doan «dien thoai gui thua hay goi bi mat»
            _tr.append((rtp["seq"], rtp["timestamp"], len(rtp["payload"]), rtp["payload_type"], int(time.monotonic() * 1000)))
        self._peer_plain_rtp = not rtp["ext"]
        if rtp["payload_type"] != RTP_PT:
            self.counters["rtp_rx_pt113"] = self.counters.get("rtp_rx_pt113", 0) + 1
        _tw = read_twseq(rtp["ext"])
        if _tw is not None:
            self._twcc.add(_tw, time.monotonic() * 1000.0)
        self._rx_audio.on_packet(rtp["seq"], rtp["timestamp"], rtp["ssrc"],
                                 time.monotonic() * 1000.0)
        if len(self._rx_head) < RX_SAMPLE_MAX and rtp["payload"]:
            self._rx_head.append((len(rtp["payload"]), rtp["payload"][0]))
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

    def _on_p2p_cands(self, data, addr):
        """Gói P2P khi ta nghe máy và có ứng viên của bên gọi (kiểu engine thật). True nếu đã xử lý hết (không cần đường cũ)."""
        if len(data) < 10 or bytes(data[3:7]) != _session_to_bytes(self.config.call_session, "call_session"):
            return True
        kind = data[7]
        if kind == 0x02 and len(data) >= 15:                         # điện thoại bind lại: đáp kind 3, đường P2P lên
            ans = build_p2p_bind_answer(self._role_byte(), self.config.call_session, data, "%s|%d" % (addr[0], addr[1]))
            if self._send_to(ans, addr):
                self.counters["ack_tx"] += 1
            self.peer_p2p_addr = addr
            self._p2p_acked = True
            self._switch_to_p2p()
            return True
        if kind == 0x04 and data[9] == 1:                            # ping giữ đường: đáp pong
            self._send_to(build_p2p_pong(self._role_byte(), data), addr)
            self.peer_p2p_addr = addr
            self._switch_to_p2p()
            return True
        return False

    def _on_p2p(self, data, addr):
        self.counters["p2p_rx"] += 1
        if self._p2p_cands and self._on_p2p_cands(data, addr):
            return
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
