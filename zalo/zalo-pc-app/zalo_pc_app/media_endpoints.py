"""Media-endpoint provider for the 11301/12434 "request" step.

Why this file exists: after requestcall (11300) the real PC client
sends a SECOND signaling step — `request` (11301) for 1-1 calls,
`group/request` (12434) for group calls — carrying the caller's
media endpoints (bundle evidence, Zalo PC 26.11.10 renderer
`compact-app-pc.*.js`, `handleSendSignal`):
    case 416: sendRequestCall(n.calleeId, n.rtcpAddress,
        n.rtpAddress, n.codec, n.extendData, n.session, n.callId)
    case 12434: sendRequestCallGroup(calleeId, callId, callType,
        data, session, partners, groupId)
The fields come from the NATIVE engine (ZaloCall.exe): its
`sendSignal` 416 payload is {command, calleeId, callId,
rtpAddress, rtcpAddress, extendData, session} (ZaloCall.exe strings
also list rtpAddressIPv6 / rtcpAddressIPv6 / rtcpIP, but those are
only in the GROUP builders, not the 1-1 416). The engine
allocates those relay addresses from the ZRTP relay server at call
start — the 2026-11-04 pcap shows the caller's media setup packets
to the relay starting 20–40 ms after the server's last TCP packet
(the pcap contains no timestamp of the tap, so no claim can be made
about delay after the user pressed call), and the client carries a
`timeoutMakeCall2ZRtp` setting for this step.

Phase 2 provider (this file): the placeholder is GONE. `for_call`
now drives the real `Udp4200Transport` (see `udp_transport.py`,
agent A — stdlib-only, no SRTP/Opus imports there either):
parse the relay list from response 11300 (`servers` — REAL shape:
a list of dicts keyed `rtcpaddr`/`rtpIPv6`, seen live 2026-11-05;
legacy `zrtc_config.servers` string kept as fallback),
start the transport (probe -> setup init), WAIT for the relay to
be selected (first type-02, the disassembly's
smallest-`initSuccessTime` rule), and return the selected relay's
`rtpAddress`/`rtcpAddress` as `"IP:port"` strings plus `session`
and `extendData` for signal 416 / `vc_request` (11301).

What this provider NEVER does: return empty addresses. The real
engine never sends 416 with empty rtp/rtcp/session (disassembly:
empty only when IP is empty / port <= 0, and then the engine takes
the FAIL path instead of sending 416). When a mandatory parameter
is missing, `for_call` raises `MissingTransportParam` naming that
parameter, and the caller (`server.py`, best-effort step) reports
the 11301 as not sent instead of sending an empty invitation.

Parameter sources (all UNCONFIRMED where noted — see
`zalo-pc-reverse/disasm-*.md` and `zalo-pcap-pc/bao-cao.md`):
  relays       response 11300 `servers` — REAL SHAPE, observed live
               2026-11-05 (call to a peer, build 72b91b8): a LIST of
               dicts whose keys include `rtcpaddr` and `rtpIPv6`
               (the screenshot was truncated, so more keys may
               exist). Each dict carries the relay's RTP/RTCP
               addresses as "IP:port" strings (IPv4 and/or IPv6).
               Parsed defensively by `_relay_servers_from_dict`
               (accepts rtcpaddr/rtpaddr/rtpIPv6/rtcpIPv6 and
               sibling spellings, separate ip/port keys, bracketed
               "[IPv6]:port", and unknown extra keys — which are
               ignored, never trusted). LEGACY fallback, kept:
               `zrtc_config.servers` as a raw string of `"IP:port"`
               entries, paired RTP/RTCP (see
               `udp_transport.parse_servers_string`); or an explicit
               list of `RelayServer` / `"IP:port"` / dicts in the
               old `{rtp_ip, rtp_port, rtcp_ip, rtcp_port}` shape.
               Before this fix the dict branch only knew the old
               shape, so the real list parsed to [] and step 2
               failed with "relays: empty" even though the
               response DID carry relays.
  token        115 raw bytes or the 154-char base64url string.
               SOURCE (LIVE 2026-11-06 06:35 +07, build 9d87501):
               the real 11300 response carries NO `token` key —
               its top-level keys are [changeZRTP, fec, fromId, id,
               msg, protocol, rtcpIP, rtpIP, servers, sessId,
               settings, showDebugInfo, status, toId, ts, video,
               zrtc_config]. The token is `sessId`: 115 raw bytes
               == 154-char base64url unpadded — exactly the numbers
               in the old "token: missing" error, and the only key
               whose value can have that shape (every other key is
               an id, a flag, an address, or a struct). The provider
               takes an explicit `token` first, then `sessId` —
               but ONLY when `sessId` validates as 115 bytes /
               154 chars (`_looks_like_token`); a wrong-shaped
               sessId leaves the token absent and `for_call` raises
               naming `token` (with the sessId length in the shape
               note, so the next live round can judge). The token is
               NEVER generated, randomised, or defaulted.
  session      the 416 `session` STRING. Source: 11300 `sessId`
               (same value as the token — the 154-char string, or
               the base64url form when sessId arrives as 115 raw
               bytes). UNCONFIRMED as the session, like the token
               it is the only candidate among the real keys.
  local_session  u32, the same value as the RTP SSRC (setup packet
               offset 10-13 LE = RTP SSRC BE). SOURCE CHOT
               (disassembly ZaloCall.exe 26.11.10, 2026-11-06):
               parser response 401 (fcn.0071ebd1,
               zmessagedeseralizer.cpp) doc JSON "fromId" vao
               struct+0x10, "toId" vao struct+0x14 (JSON-get-int
               0x4015a5); `_prepareCallConfig, resp` (0x7ed1d0) copy
               [resp+0x10] -> CallConfig+0x0 (= userId cua minh),
               [resp+0x14] -> CallConfig+0x4 (= partnerId) —
               khong co and/shr/mod/hash nao. Goi di: fromId =
               caller = chinh minh, toId = callee = peer (doi
               chieu goi den: parser 0x71f670 doc "uidTo" ->
               CallConfig+0, "uidFrom" -> CallConfig+4). Vay
               local_session = response 11300 `fromId` — id 32-bit
               RIENG do server cap, KHONG phai session uid (uid
               that la 64-bit, live test 09:23 +07 2026-11-06 da
               bac; low-32 cung bi loai bang pcap 09:27). Thieu
               fromId (hoac fromId khong vua u32) -> `for_call`
               loi trung thuc neu ro `local_session` + `fromId`
               (gui 11301 voi SSRC sai con te hon khong gui).
               KHONG random, KHONG default, KHONG lay tu uid.
  call_session   the 4-byte value at setup offset 21-24 / P2P
               offset 3-6. Optional: `Udp4200Transport` generates
               random bytes with last byte 0x2b when omitted.
  peer_session   u32 or None. SOURCE (cung disassembly):
               `CallConfig+0x4` = partnerId -> `[CallController
               +0x64]` -> setup `[pkt+0x38]`; pcap thay no KHAC
               nhau theo peer. Lay tu response 11300 `toId` (chi
               cho goi 1-1; goi nhom toId khong phai userId cua
               mot peer nen van None). Vang / sai dang -> None
               trung thuc: transport gui 0 o offset 25-28 cho den
               khi hoc lai SSRC peer.
  srtp_key     from `zrtc_config.srtpKey` (a STRING of unknown
               format/length). LIVE 2026-11-06: the real 11300
               `zrtc_config` carries NO `srtpKey` (nor `srtpNoSeq`
               / `srtpRTCP`) — so a missing key is NOT fatal for
               signaling any more: `for_call` still returns the
               endpoints and 11301 is still sent, with `srtp`
               reported as "not-wired" and media unwired (the
               transport starts for the handshake; `send_pcm`
               still refuses without a `protect_rtp` hook). The key
               source is still OPEN — it may live inside the
               115-byte token, in `settings`/`msg`, or be issued
               separately by the server. The provider does NOT
               decode it and does NOT guess key material: when a
               key IS present it is passed unchanged to the SRTP
               hook factory (`pc_media`), which converts it
               strictly (base64url attempt + exact suite-length
               check) or fails loudly. `srtpKey` / `srtpNoSeq` /
               `srtpRTCP` are keys of `zrtc_config`, NOT of
               extendData (disassembly correction).
  extend_data  dict or JSON string, normalized to the 23 known
               keys (`udp_transport.normalize_extend_data` — unknown
               keys dropped, bad `srtpMode` reset to 0). Optional:
               when absent, the provider only fills `srtpMode`
               from `zrtc_config` if present; otherwise None, and
               `vc_request` omits `extendData`/`subCommand=3`.
  codec        explicit > 11300 response `codec` (applyServerInfo:
               a non-empty string different from "[]" — the server
               wins, per zca-js ZaloRtcSession.applyServerInfo) >
               DEFAULT_ZALO_AUDIO_CODEC (the Opus JSON list the
               real engine sends; zca-js ZRTPPacketCodec.ts:279).
               `zrtc_config.g711` NO LONGER drives this value: it
               describes the MEDIA codec, not the signaling codec
               string, and zca-js never reads g711 for signaling
               (the old "pcmu"/"pcma"/"opus" inference was
               UNCONFIRMED and is retired — see
               allocation_from_requestcall_data).
  protect/unprotect_rtp, encode/decode_frame
               injectable hooks, passed straight into
               `TransportConfig`. SRTP/Opus are NEVER imported
               here: the app image stays stdlib-only (packaging
               decision (b) — see the final report); `pc_media`
               builds these hooks when libopus/libsrtp2 are
               available. A transport can start for the handshake
               without hooks, but `send_pcm` requires `protect_rtp`
               (the transport raises `MissingTransportParam` then).
"""

import base64
import binascii
import ipaddress
import json
import re
import time

from . import protocol
from .udp_transport import (
    MissingTransportParam,
    RelayServer,
    TransportConfig,
    Udp4200Transport,
    normalize_extend_data,
    parse_servers_string,
)

__all__ = ["MediaEndpoints", "MissingTransportParam",
           "allocation_from_requestcall_data", "ENDPOINTS",
           "describe_requestcall_shape", "DEFAULT_ZALO_AUDIO_CODEC"]

# Codec list the real engine sends in 11300/11301 (zca-js
# `ZRTPPacketCodec.ts:279` DEFAULT_ZALO_AUDIO_CODEC, softtyos
# v2.3.13 — bao cao outbox/zca-js-tong-hop.md §4.4/§7.2): a JSON
# LIST string, not the bare word "opus". Built with
# json.dumps(..., separators=(",", ":")) so the wire form is
# exactly '[{"dynamicFptime":0,"frmPtime":20,"name":"opus/16000/1",
# "payload":112}]' — key order dynamicFptime/frmPtime/name/payload.
DEFAULT_ZALO_AUDIO_CODEC = (
    '[{"dynamicFptime":0,"frmPtime":20,'
    '"name":"opus/16000/1","payload":112}]')


# ------------------------------------------------------------------ helpers

def _as_int(value):
    """Coerce a digit string / int to int, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_u32(value):
    """Coerce a digit string / int to a positive u32 int, else
    None. 0 is rejected: the native JSON-get-int leaves the out
    param at 0 when the key is absent / unconvertible, so 0 means
    "no id" here, never a real server-issued id. A 64-bit id
    (e.g. a session uid) is rejected, NEVER truncated to low-32
    — no truncation exists in the native client either."""
    n = _as_int(value)
    if n is None or not 1 <= n <= 2 ** 32 - 1:
        return None
    return n


def _describe_id_value(value):
    """Shape of an id value ONLY (type + length for strings) —
    never the value itself. Used for `fromId`/`toId` diagnostics
    so a live failure can be judged from the message alone."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "str[%d chars]" % len(value)
    return type(value).__name__


def _norm_relay_key(key):
    """Normalize a relay-dict key for matching: lowercase, no
    `_`/`-` (so `rtcpAddr`, `rtcp_addr` and `RTCPADDR` all match
    as `rtcpaddr`)."""
    return str(key).lower().replace("_", "").replace("-", "")


def _parse_addr_value(value):
    """Parse one relay address value to (ip, port) or None.

    Accepted (values only — never key names — are inspected):
      * "IP:port" (IPv4), "[IPv6]:port" (bracketed IPv6);
      * a bare IP with no port -> (ip, None) — the caller pairs
        it with a sibling `*port` key when one exists;
      * an unbracketed IPv6 with a trailing port
        ("2001:db8::1:4200") — accepted ONLY when the whole
        string is not itself a valid IPv6 address and the prefix
        before the last ":" parses as IPv6;
      * a dict {"ip"/"addr"/"address": ..., "port": ...}.
    A bare int, an empty string, or anything unparseable returns
    None (never a guessed address). No value is ever logged.
    """
    if isinstance(value, dict):
        ip_raw = None
        for k in ("ip", "addr", "address"):
            if value.get(k) is not None:
                ip_raw = value[k]
                break
        port_raw = value.get("port")
        if ip_raw is None:
            return None
        try:
            ip = str(ipaddress.ip_address(str(ip_raw).strip()))
        except ValueError:
            return None
        port = _as_int(port_raw)
        if port is not None and not 1 <= port <= 65535:
            return None
        return (ip, port)
    if isinstance(value, bool) or not isinstance(value, str):
        return None
    token = value.strip()
    if not token:
        return None
    if token.startswith("["):
        m = re.match(r"^\[([^\]]+)\]:(\d+)$", token)
        if not m:
            return None
        try:
            ip = str(ipaddress.ip_address(m.group(1)))
        except ValueError:
            return None
        port = int(m.group(2))
        return (ip, port) if 1 <= port <= 65535 else None
    if token.count(":") == 1:
        ip_s, port_s = token.split(":")
        try:
            ip = str(ipaddress.ip_address(ip_s))
            port = int(port_s)
        except ValueError:
            return None
        return (ip, port) if 1 <= port <= 65535 else None
    if token.count(":") == 0:
        try:
            return (str(ipaddress.ip_address(token)), None)
        except ValueError:
            return None
    # Multi-colon: a bare IPv6 address first (no port), else a
    # trailing ":port" after a valid IPv6 prefix.
    try:
        return (str(ipaddress.ip_address(token)), None)
    except ValueError:
        pass
    head, _, tail = token.rpartition(":")
    try:
        ip = str(ipaddress.ip_address(head))
        port = int(tail)
    except ValueError:
        return None
    return (ip, port) if 1 <= port <= 65535 else None


def _relay_servers_from_dict(entry):
    """One real-11300 relay dict -> list[RelayServer] (0..2).

    The real 11300 `servers` list (seen live 2026-11-05) holds
    dicts keyed e.g. `rtcpaddr` / `rtpIPv6` — the screenshot was
    truncated, so the parser matches by key SHAPE, not by one
    hardcoded key: after normalizing (`_norm_relay_key`), a key
    starting with `rtcp` is the RTCP side, one starting with
    `rtp` the RTP side; a key ending in `port` is a port, a key
    containing `addr`/`ip`/`address` (or ending in `v6`/`v4`)
    is an address. Unknown keys (id, type, priority, ...) are
    ignored. An address without a port pairs with a sibling
    `*port` key when present. IPv4 and IPv6 form separate
    servers (RTP-v4 with RTCP-v4, RTP-v6 with RTCP-v6); when
    only a mixed pair is complete (e.g. RTP-v6 + RTCP-v4) one
    mixed server is emitted — the transport addresses each
    side independently. A dict with no complete RTP+RTCP pair
    yields [] (the caller raises naming `relays`).
    """
    rtp, rtcp = {}, {}   # family ("v4"/"v6") -> (ip, port|None)
    ports = {}           # side ("rtp"/"rtcp") -> int port
    for key, value in entry.items():
        norm = _norm_relay_key(key)
        if norm.startswith("rtcp"):
            side = "rtcp"
        elif norm.startswith("rtp"):
            side = "rtp"
        else:
            continue
        if norm.endswith("port"):
            port = _as_int(value)
            if port is not None and 1 <= port <= 65535:
                ports[side] = port
            continue
        if ("addr" in norm or "ip" in norm or "address" in norm
                or norm.endswith("v6") or norm.endswith("v4")):
            parsed = _parse_addr_value(value)
            if parsed is None:
                continue
            ip, port = parsed
            family = ("v6" if isinstance(
                ipaddress.ip_address(ip), ipaddress.IPv6Address)
                else "v4")
            target = rtp if side == "rtp" else rtcp
            # First complete candidate per family wins; a later
            # duplicate key spelling must not overwrite it.
            if family not in target:
                target[family] = (ip, port)
    for side_map, side in ((rtp, "rtp"), (rtcp, "rtcp")):
        for family, (ip, port) in list(side_map.items()):
            if port is None and side in ports:
                side_map[family] = (ip, ports[side])

    def _complete(side_map):
        return {f: v for f, v in side_map.items()
                if v[1] is not None and 1 <= v[1] <= 65535}

    rtp_ok, rtcp_ok = _complete(rtp), _complete(rtcp)
    out = []
    for family in ("v4", "v6"):  # IPv4 first (most likely routed)
        if family in rtp_ok and family in rtcp_ok:
            r_ip, r_port = rtp_ok[family]
            c_ip, c_port = rtcp_ok[family]
            out.append(RelayServer(r_ip, r_port, c_ip, c_port))
    if not out and rtp_ok and rtcp_ok:
        # Mixed families only (e.g. RTP-v6 + RTCP-v4): one server
        # from the first complete candidate on each side.
        r_ip, r_port = next(iter(rtp_ok.values()))
        c_ip, c_port = next(iter(rtcp_ok.values()))
        out.append(RelayServer(r_ip, r_port, c_ip, c_port))
    return out


def _describe_servers_value(value):
    """Describe a `servers` value by SHAPE ONLY — key names,
    types and counts, never values (no IPs, no ports, no
    tokens). Used in error messages so the next live test can
    be diagnosed from the message alone."""
    if value is None:
        return "none"
    if isinstance(value, str):
        return "str[%d chars]" % len(value)
    if isinstance(value, (list, tuple)):
        kinds = []
        dict_keys = set()
        for entry in value:
            kinds.append(type(entry).__name__)
            if isinstance(entry, dict):
                dict_keys.update(str(k) for k in entry.keys())
        summary = "list[%d] of %s" % (
            len(value), ",".join(sorted(set(kinds))) or "?")
        if dict_keys:
            summary += " dict keys: [%s]" % ", ".join(sorted(dict_keys))
        return summary
    if isinstance(value, dict):
        return "dict keys: [%s]" % ", ".join(
            sorted(str(k) for k in value.keys()))
    return type(value).__name__


def _looks_like_token(value):
    """True when `value` can be the 11301 token: 115 raw bytes,
    or a 154-char base64url string decoding to exactly 115
    bytes. Shape only — the value is never logged or returned.
    115 bytes == 920 bits == ceil(920/6) == 154 base64 chars
    (unpadded), which is exactly the pair the "token: missing"
    error names; any other length fails, never coerced."""
    if isinstance(value, (bytes, bytearray)):
        return len(value) == 115
    if isinstance(value, str):
        if len(value) != 154:
            return False
        try:
            raw = base64.b64decode(
                value.encode("ascii") + b"==",
                altchars=b"-_", validate=True)
        except (binascii.Error, ValueError, UnicodeEncodeError):
            return False
        return len(raw) == 115
    return False


def _sessid_to_session_str(value):
    """A `sessId` value as the 416 `session` string: a str as-is;
    115 raw bytes as their 154-char base64url form (never
    `str(bytes)`, which would yield a "b'\\x..'" literal)."""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return base64.urlsafe_b64encode(
            bytes(value)).rstrip(b"=").decode("ascii")
    return str(value)


def describe_requestcall_shape(data):
    """One-line shape summary of a decoded 11300 response: key
    names and counts ONLY, never values. Safe for the UI, the
    call log and the /api/call/request response."""
    if not isinstance(data, dict):
        return "11300 data: not a dict (%s)" % type(data).__name__
    parts = ["11300 keys: [%s]" % ", ".join(sorted(map(str, data)))]
    cfg = _zrtc_config_of(data)
    if cfg:
        parts.append("zrtc_config keys: [%s]" % ", ".join(
            sorted(map(str, cfg))))
    servers = _find_in_requestcall_data(data, "servers")
    if servers is not None:
        parts.append("servers: %s" % _describe_servers_value(servers))
    # sessId length (never the value): the token candidate's shape
    # is the one number the next live round needs to confirm.
    sess = _find_in_requestcall_data(data, "sessId")
    if sess is not None:
        if isinstance(sess, (bytes, bytearray)):
            parts.append("sessId: bytes[%d]" % len(sess))
        elif isinstance(sess, str):
            parts.append("sessId: str[%d chars]" % len(sess))
        else:
            parts.append("sessId: %s" % type(sess).__name__)
    # fromId/toId shapes (never the values): the 32-bit ids that
    # feed local_session / peer_session. A fromId that arrives as
    # a long digit string is the first thing the next live round
    # needs to see — without its value.
    for _key in ("fromId", "toId"):
        _val = _find_in_requestcall_data(data, _key)
        if _val is not None:
            parts.append("%s: %s" % (_key, _describe_id_value(_val)))
    # rtpIP/rtcpIP (2026-11-08, step 1 / D8): the relay addresses
    # the 11300 response designates. Recorded by SHAPE ONLY here
    # (this string is also the /api/call/request response's
    # data_shape, which never carries values — see the docstring):
    # a string value is "rtpIP: str[N chars]", any other type is
    # its type name. The ACTUAL addresses go into the [call]
    # step1 log line (server.py appends them from the allocation)
    # and into the /api/calls diag (rtp_ip/rtcp_ip) — relay IPs
    # are public diagnostic info, not secrets, but they do not
    # belong in a shape string.
    for _key in ("rtpIP", "rtcpIP"):
        _val = _find_in_requestcall_data(data, _key)
        if _val is not None:
            if isinstance(_val, str):
                parts.append("%s: str[%d chars]" % (_key, len(_val)))
            else:
                parts.append("%s: %s" % (_key, type(_val).__name__))
    return "; ".join(parts)


def requestcall_status(data):
    """(status, msg) of a decoded 11300 response. The real success
    case (live 2026-11-06) carries status 0 and msg ""; any other
    status is a server-side refusal of the requestcall itself,
    with msg carrying the reason. status absent (the mock's
    {"ok": True} shape) means unknown and is treated as accepted
    — the mock must not be forced to invent a status field."""
    if not isinstance(data, dict):
        return None, ""
    status = _find_in_requestcall_data(data, "status")
    msg = _find_in_requestcall_data(data, "msg")
    return status, (msg if isinstance(msg, str) else "")


def requestcall_accepted(data):
    """True when a decoded 11300 response does NOT refuse the
    call: status absent (unknown) or 0. Any other status is a
    refusal — the caller must not proceed to step 2 with it."""
    status, _msg = requestcall_status(data)
    return status is None or status in (0, "0")


def describe_request_shape(data, code="11301"):
    """One-line shape summary of a decoded request-step (11301 /
    12434) response: top-level key names + scalar status / msg /
    ok / error_code values ONLY. Never the values of session /
    token / sessId / body keys — the mock echoes the request body,
    which carries the session, so no nested content is ever
    expanded. Safe for the call log and /api/calls diag."""
    if data is None:
        return "%s data: None" % code
    if not isinstance(data, dict):
        if isinstance(data, (str, bytes, bytearray)):
            return "%s data: %s[%d]" % (code, type(data).__name__,
                                        len(data))
        return "%s data: %s" % (code, type(data).__name__)
    parts = ["%s keys: [%s]" % (code, ", ".join(
        sorted(map(str, data))))]
    for key in ("status", "ok", "error_code"):
        if key in data and isinstance(data[key], (int, str, bool)):
            parts.append("%s=%s" % (key, data[key]))
    msg = data.get("msg") or data.get("error_message") \
        or data.get("error")
    if isinstance(msg, str) and msg:
        parts.append("msg=%s" % msg[:120])
    return "; ".join(parts)


def request_step_outcome(resp):
    """Did the server accept a request step (11301 / 12434)?
    Returns (accepted, status, msg). accepted=False when the
    decoded response carries a non-zero status / error_code, or
    ok is False. status absent (the mock success shape {"ok":
    True}) counts as accepted — the mock must not invent a
    rejection the real server was never seen to make. The inner
    error_code case never reaches here (Signaling._call raises
    ServerRejectedError for it); this covers the data-level
    status the envelope check cannot see."""
    if not isinstance(resp, dict):
        return True, None, ""
    status = resp.get("status")
    err = resp.get("error_code")
    ok = resp.get("ok")
    msg = resp.get("msg") or resp.get("error_message") \
        or resp.get("error")
    if not isinstance(msg, str):
        msg = ""
    if status is not None and status not in (0, "0"):
        return False, status, msg
    if err is not None and err not in (0, "0"):
        return False, err, msg
    if ok is False:
        return False, status, msg
    return True, status, msg


def _normalize_relays(relays, servers=None):
    """Normalize every accepted relay shape to list[RelayServer].

    Accepted: list[RelayServer], list["IP:port"], list[dict] —
    the old `{rtp_ip, rtp_port, rtcp_ip, rtcp_port}` shape AND
    the real-11300 shape (dicts keyed `rtcpaddr`/`rtpIPv6`/...
    — see `_relay_servers_from_dict`), a raw `servers` string
    (parsed by `udp_transport.parse_servers_string` — alternating
    RTP/RTCP pairs or 4-part entries). Returns [] when nothing
    usable was given (the caller raises, naming `relays`).
    """
    if relays is None and servers is not None:
        relays = servers
    if relays is None:
        return []
    if isinstance(relays, str):
        return parse_servers_string(relays)
    if isinstance(relays, RelayServer):
        return [relays]
    if isinstance(relays, dict):
        relays = [relays]
    if not isinstance(relays, (list, tuple)):
        return []
    out = []
    singles = []
    for entry in relays:
        if isinstance(entry, RelayServer):
            out.append(entry)
        elif isinstance(entry, dict):
            if {"rtp_ip", "rtp_port", "rtcp_ip", "rtcp_port"} <= set(
                    entry.keys()):
                try:
                    out.append(RelayServer(
                        str(entry["rtp_ip"]), int(entry["rtp_port"]),
                        str(entry["rtcp_ip"]), int(entry["rtcp_port"])))
                except (KeyError, TypeError, ValueError):
                    continue
            else:
                out.extend(_relay_servers_from_dict(entry))
        elif isinstance(entry, str):
            singles.append(entry)
        # Anything else is skipped: a half-built relay must never
        # reach the transport (validity predicate: RTP + RTCP).
    if singles:
        out.extend(parse_servers_string(",".join(singles)))
    return out


def _server_addr_list(servers, relay_list):
    """(numServers, serverAddr) values for extendData, from the
    11300 `servers` value (2026-11-08, step 2).

    The count is the number of SERVERS the 11300 response
    advertised — one entry per server dict — NOT the length of
    the normalized relay list: `_relay_servers_from_dict`
    splits each server dict into an IPv4 and an IPv6
    RelayServer (5 dicts -> 10 relays), but the server
    advertised 5 servers, and the real client's numServers is
    the length of ITS server list (one struct per server, v4+v6
    inside). serverAddr carries one RTP address per server —
    IPv4 preferred (the family this deployment's transport
    uses; `_relay_servers_from_dict` emits v4 first), IPv6
    when a server has no IPv4 RTP address.
    When the relays were passed directly (no `servers` list of
    dicts — e.g. a raw string or a list of RelayServer), the
    normalized list IS the server list: one address per relay.
    Returns a list of "IP:port" strings (possibly empty).
    """
    if isinstance(servers, (list, tuple)) and servers \
            and all(isinstance(entry, dict) for entry in servers):
        addrs = []
        for entry in servers:
            relays = _relay_servers_from_dict(entry)
            if relays:
                first = relays[0]
                addrs.append(_format_ip_port(first.rtp_ip,
                                             first.rtp_port))
        return addrs
    return [_format_ip_port(relay.rtp_ip, relay.rtp_port)
            for relay in (relay_list or [])]


def _format_ip_port(ip, port):
    """One relay address as an "IP:port" string for 11301: IPv6
    is bracketed ("[2001:db8::1]:4200") — the unbracketed form
    ("2001:db8::1:4200") is ambiguous and unparseable."""
    if ":" in str(ip):
        return "[%s]:%d" % (ip, port)
    return "%s:%d" % (ip, port)


def _resolve_11301_addresses(rtp_ip_raw, rtcp_ip_raw, selected):
    """The rtpAddress/rtcpAddress for 11301, from the 11300
    response's `rtpIP`/`rtcpIP` vs the selected relay
    (2026-11-08, step 1 / D8).

    Returns (rtp_address, rtcp_address, source) with source
    "rtpIP" when the 11300-designated addresses are used and
    "selected" when the selected relay's addresses are used.

    Rule: when BOTH rtpIP and rtcpIP parse as addresses AND at
    least one differs from the selected relay, 11301 uses
    rtpIP/rtcpIP — the hypothesis is the server designates one
    specific relay and may not route an invitation that names a
    different one (the live no-ring case: the server accepted
    11301 with the selected relay's addresses but never rang
    the peer). A bare IP (no port) pairs with the selected
    relay's port on the same side — ASSUMPTION, documented: the
    port is a property of the relay service (4200 in every
    capture; the transport is Udp4200Transport). When either
    value is missing or unparseable, or both match the selected
    relay, the selected relay is used unchanged.
    """
    selected_rtp = _format_ip_port(selected.rtp_ip, selected.rtp_port)
    selected_rtcp = _format_ip_port(selected.rtcp_ip,
                                    selected.rtcp_port)
    if not isinstance(rtp_ip_raw, str) or not rtp_ip_raw \
            or not isinstance(rtcp_ip_raw, str) or not rtcp_ip_raw:
        return selected_rtp, selected_rtcp, "selected"
    rtp_parsed = _parse_addr_value(rtp_ip_raw)
    rtcp_parsed = _parse_addr_value(rtcp_ip_raw)
    if rtp_parsed is None or rtcp_parsed is None:
        return selected_rtp, selected_rtcp, "selected"
    rtp_ip, rtp_port = rtp_parsed
    rtcp_ip, rtcp_port = rtcp_parsed
    if rtp_port is None:
        rtp_port = selected.rtp_port
    if rtcp_port is None:
        rtcp_port = selected.rtcp_port
    rtp_address = _format_ip_port(rtp_ip, rtp_port)
    rtcp_address = _format_ip_port(rtcp_ip, rtcp_port)
    if rtp_address == selected_rtp and rtcp_address == selected_rtcp:
        return selected_rtp, selected_rtcp, "selected"
    return rtp_address, rtcp_address, "rtpIP"


def _find_in_requestcall_data(data, key):
    """Search `key` in a decoded 11300 response, in the places the
    disassembly puts it: top level, nested `data`, `params`
    (the request-param parser 0x71f670 reads `params.rtpIP` /
    `params.rtcpIP` / `params.sessId` — disasm-relay-acquisition
    A.2), and inside `zrtc_config`. Returns None when absent
    everywhere."""
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    inner = data.get("data")
    if isinstance(inner, dict) and key in inner:
        return inner[key]
    params = data.get("params")
    if isinstance(params, dict) and key in params:
        return params[key]
    if isinstance(inner, dict):
        params2 = inner.get("params")
        if isinstance(params2, dict) and key in params2:
            return params2[key]
    cfg = data.get("zrtc_config")
    if isinstance(cfg, dict) and key in cfg:
        return cfg[key]
    if isinstance(inner, dict):
        cfg2 = inner.get("zrtc_config")
        if isinstance(cfg2, dict) and key in cfg2:
            return cfg2[key]
    return None


def _zrtc_config_of(data):
    """The `zrtc_config` dict of a decoded 11300 response, or {}."""
    if not isinstance(data, dict):
        return {}
    cfg = data.get("zrtc_config")
    if isinstance(cfg, dict):
        return cfg
    inner = data.get("data")
    if isinstance(inner, dict):
        cfg = inner.get("zrtc_config")
        if isinstance(cfg, dict):
            return cfg
    return {}


def allocation_from_requestcall_data(data):
    """Extract media-allocation material from a decoded 11300
    (requestcall) response `data` — the dict `Signaling._call`
    returns (inner `data` after AES unwrap).

    Returns a dict with only the keys actually present (never
    invented values): `servers` (raw string/list as received —
    the REAL shape is a list of dicts keyed rtcpaddr/rtpIPv6,
    seen live 2026-11-05; the legacy `zrtc_config.servers`
    string is kept as a fallback),
    `token` (an explicit `token` key first; else 11300 `sessId`
    — LIVE 2026-11-06 the real response has no `token` key and
    `sessId` is the 115-byte / 154-char token — but ONLY when
    its shape validates via `_looks_like_token`; a wrong-shaped
    sessId leaves `token` absent),
    `session` (from `sessId` — same value as the token),
    `local_session` (from 11300 `fromId` — the server-issued
    32-bit id of the logged-in account; disassembly 2026-11-06:
    parser 0x71ebd1 maps "fromId" -> resp+0x10, and
    `_prepareCallConfig, resp` 0x7ed1d0 copies [resp+0x10] ->
    CallConfig+0 -> SSRC. Accepted ONLY as a positive u32 int
    or digit string (`_as_u32`); a present-but-invalid `fromId`
    is reported as `local_session_invalid` (SHAPE only, never
    the value) so `for_call` can name it in the error),
    `peer_session` (from 11300 `toId` — the server-issued 32-bit
    id of the peer; parser maps "toId" -> resp+0x14 ->
    CallConfig+4. Accepted ONLY as a positive u32; absent /
    invalid -> simply missing, i.e. None downstream),
    `srtp_key` (from `zrtc_config.srtpKey` — LIVE 2026-11-06
    the real response has none; absent keys are simply missing),
    `srtp_mode`, `codec` (the 11300 response's own `codec` when
    it is a usable string, non-empty and not "[]" — applyServerInfo;
    `zrtc_config.g711` no longer feeds this: it describes the MEDIA
    codec, not the signaling codec string), `extend_data`
    (from a top-level `extendData` string/dict when present),
    `rtp_ip` / `rtcp_ip` (from `rtpIP` / `rtcpIP` — the relay
    addresses the 11300 response designates; 2026-11-08 step 1:
    for_call compares them with the selected relay and uses
    them for 11301 when they differ).
    Absent keys are simply missing: `for_call` raises naming
    each one instead of filling in a guess (except `srtp_key`,
    which no longer blocks signaling — see `for_call`).
    """
    if not isinstance(data, dict):
        return {}
    cfg = _zrtc_config_of(data)
    out = {}
    servers = _find_in_requestcall_data(data, "servers")
    if servers is not None:
        out["servers"] = servers
    token = _find_in_requestcall_data(data, "token")
    if token is None:
        # LIVE 2026-11-06 (build 9d87501): the real 11300
        # response carries NO `token` key, and step 2 (11301)
        # failed on "token: missing (need 115 raw bytes or a
        # 154-char base64url string, most likely from response
        # 11300)". The token is `sessId`: 115 raw bytes ==
        # 154-char base64url — exactly those numbers, and the
        # only real key whose value can have that shape.
        # Accepted ONLY when the shape validates; never a
        # captured value, never randomised, never coerced.
        sess_candidate = _find_in_requestcall_data(data, "sessId")
        if (sess_candidate is not None
                and _looks_like_token(sess_candidate)):
            token = sess_candidate
    if token is not None:
        out["token"] = token
    sess = _find_in_requestcall_data(data, "sessId")
    if sess is None:
        sess = _find_in_requestcall_data(data, "session")
    if sess is not None:
        out["session"] = _sessid_to_session_str(sess)
    # local_session / peer_session: the server-issued 32-bit ids
    # of the 11300 response (see module docstring). NEVER derived
    # from the session uid (64-bit) or the callee threadId — those
    # derivations were removed 2026-11-06: the live test proved
    # the uid does not fit u32, and the disassembly shows the
    # ids arrive ready-made in `fromId`/`toId`.
    from_id = _find_in_requestcall_data(data, "fromId")
    if from_id is not None:
        local = _as_u32(from_id)
        if local is not None:
            out["local_session"] = local
        else:
            out["local_session_invalid"] = _describe_id_value(from_id)
    to_id = _find_in_requestcall_data(data, "toId")
    if to_id is not None:
        peer = _as_u32(to_id)
        if peer is not None:
            out["peer_session"] = peer
    srtp_key = cfg.get("srtpKey")
    if srtp_key is None:
        # Fallback: the real 11300 layout is only partly known
        # (servers was top-level, not under zrtc_config, in the
        # live 2026-11-05 reply) — accept a top-level srtpKey
        # too. zrtc_config still wins when both carry it.
        srtp_key = _find_in_requestcall_data(data, "srtpKey")
    if srtp_key is not None:
        out["srtp_key"] = srtp_key
    srtp_mode = cfg.get("srtpMode")
    if srtp_mode is None:
        srtp_mode = _find_in_requestcall_data(data, "srtpMode")
    if isinstance(srtp_mode, int) and not isinstance(srtp_mode, bool):
        out["srtp_mode"] = srtp_mode
    # Codec (zca-js applyServerInfo, ZaloRtcSession.ts:4505-4506): codec
    # cua chinh response 11300 thang khi la chuoi dung duoc (khong rong,
    # khong "[]"); neu khong thi KHONG lay codec nao tu response va
    # for_call dung codec mac dinh. `zrtc_config.g711` khong dung o day:
    # no mo ta codec MEDIA, khong phai chuoi codec cua tin hieu.
    server_codec = _find_in_requestcall_data(data, "codec")
    if (isinstance(server_codec, str) and server_codec
            and server_codec != "[]"):
        out["codec"] = server_codec
    ext = _find_in_requestcall_data(data, "extendData")
    if ext is not None:
        out["extend_data"] = ext
    # rtpIP/rtcpIP (2026-11-08, step 1 / D8): the relay addresses
    # the 11300 response designates (top-level in the live
    # response; the native request-param parser reads them under
    # `params` — disasm-relay-acquisition A.2). Raw strings only
    # here; for_call parses them and decides whether 11301 uses
    # them or the selected relay. Absent -> simply missing.
    for _key, _out_key in (("rtpIP", "rtp_ip"),
                           ("rtcpIP", "rtcp_ip")):
        _val = _find_in_requestcall_data(data, _key)
        if isinstance(_val, str) and _val:
            out[_out_key] = _val
    return out


def _codec_from_g711(g711):
    if g711 == 1:
        return "pcmu"
    if g711 == 2:
        return "pcma"
    return "opus"


# Minimal extendData the engine would send when the 11300
# response carries no extendData of its own (the live case:
# the real 11300 has no `extendData` key). 2026-11-08
# (step 2): the dict now carries ALL 24 keys — the 23 keys
# the real serializer 0x8e1183 builds (disasm-signal416-
# extenddata.md §3.1) + callType, which the serializer omits
# from its key list but the parser 0x8d93c8 reads (and which
# the live call proved the peer uses to tell voice from video).
# The order below follows the serializer's build order.
# Values per key (uncertainty noted where the disassembly does
# not pin it down):
#   p2p ""            — empty string (the parser reads it as a
#                       string; the serializer passes "" through).
#   callType 0/1      — 0 voice, 1 video (builder group 12434
#                       VA 0x717450 maps type 5 -> 0, 6 -> 1).
#   video {codec: ""} — the video codec: "" for a voice call
#                       (no video codec). For a future video call
#                       the codec must be a REAL video codec —
#                       the audio codec ("opus"/"pcmu") is NOT
#                       the video codec and must never be put
#                       here, so _extend_data_dict keeps "" even
#                       when is_video is True until the video
#                       path supplies one.
#   newZrtc 0         — 0 (parser default; the serializer's
#                       branch condition is unknown).
#   platform 3        — LEAST CERTAIN value in this dict: kept
#                       at 3 because the disassembly §3.1.3
#                       could not confirm it; the app has sent 3
#                       since 00db2b9 and the server accepts it.
#                       Do not change without new evidence.
#   packetMode 2      — 2 (UDP packet mode, disasm §3.2.1).
#   gccMode 0         — 0 (parser default).
#   srtpMode          — from the 11300 response (0/1/2/3) when
#                       valid, else 0 (the normalizer resets an
#                       invalid mode to 0 and zeroes srtcp/sP2P).
#   sP2P 0 / srtcp 0  — parser defaults (the app does not use
#                       P2P-SRTP or SRTCP).
#   gccAudio 0        — 0 (disasm §3.2.2).
#   gccSVLR 0         — 0 (disasm §3.2.2).
#   tpType 0          — 0: UDP transport (disasm §3.2.2).
#   spTcp 0           — 0: UDP transport (disasm §3.2.2).
#   gccEarlyCall 0    — 0 (disasm §3.2.2).
#   maxFT 60          — 60 (disasm §3.2.3: max frame time ms).
#   extraInfo {0,0}   — {"type": 0, "id": 0} (parser default;
#                       the extraInfo object is otherwise unused
#                       by the peer in 1-1 calls).
#   supportCallBusy 0 — 0 (serializer-only: the parser does
#                       NOT read this key, so the value is inert
#                       — 0 for "not supported").
#   supportHevcDecode 0 — 0 (the app cannot decode HEVC).
#   serverResult []   — [] (the peer does not read this in 1-1
#                       calls; disasm §3.1.2: the parser checks
#                       only that it is a list — the app sends an
#                       empty list because it has no server
#                       results of its own to report).
#   numServers N      — the number of SERVERS the 11300
#                       response advertised (one per server dict
#                       — see `_server_addr_list`: NOT the length
#                       of the normalized relay list, which
#                       splits each server into IPv4+IPv6
#                       entries). The app has no reason to lie
#                       about it.
#   select2side 0     — 0 (parser default).
#   serverAddr [...]  — one RTP address per advertised server
#                       as "IP:port" (IPv4 preferred — see
#                       `_server_addr_list`), from disasm §3.1.2:
#                       each element is extracted as a string,
#                       then parsed as "IP:port". BEST-EFFORT
#                       SHAPE: the exact element shape was never
#                       captured live — the disassembly only
#                       proves the parser takes strings from the
#                       list; the peer's 1-1 handler IGNORES this
#                       loop entirely (the parser only reads
#                       serverAddr in the group path), so it
#                       matters only if the SERVER checks it. The
#                       RTCP addresses are NOT included — only
#                       the RTP addresses, because the parser's
#                       loop extracts one address per server.
#   fecTP 0           — 0 (parser default).
_MINIMAL_EXTEND_DATA = {
    "p2p": "",
    "callType": 0,
    "video": {"codec": ""},
    "newZrtc": 0,
    "platform": 3,  # 11300 request-param struct default (parser
    # 0x71f670 init [+0x04]=3); the only numeric platform
    # evidence in the disassembly.
    "packetMode": 2,  # _parseExtendData parse-fail default
    "gccMode": 0,
    "srtpMode": 0,
    "sP2P": 0,
    "srtcp": 0,
    "gccAudio": 0,
    "gccSVLR": 0,
    "tpType": 0,
    "spTcp": 0,
    "gccEarlyCall": 0,
    "maxFT": 60,  # _parseExtendData parse-fail default
    "extraInfo": {"type": 0, "id": 0},
    "supportCallBusy": 0,
    "supportHevcDecode": 0,
    "serverResult": [],
    "numServers": 0,
    "select2side": 0,
    "serverAddr": [],
    "fecTP": 0,
}


def zca_extend_data(rtp, rtcp, is_video=False, srtp_mode=0, srtp_key=None):
    """extendData cua 416 theo @softtynet/zca-js 2.3.13 `buildZrtcExtendData`
    (ZRTPPacketCodec.ts:313) — doi chieu 09/11/2026:
      newZrtc 1 (app cu gui 0 = gia tri "parse loi" cua parser, khong phai gia tri that;
      pcap Zalo PC chinh thuc cho thay dien thoai tra goi 0x90+BEDE = ZRTC moi),
      maxFT 120 (app cu 60), platform 2 (app cu 3 — bao cao Muse §5.3 nghi ngo),
      packetMode 1 (khung type-03/04 dang dung; app cu khai 2 = 0x7f ma gui khung cu),
      serverAddr dang dict {rtcp,rtcpIPv6,rtp,rtpIPv6,tpType}, video.codec h264/97.
    """
    out = {
        "callType": 1 if is_video else 0, "fecTP": 0, "gccAudio": 0,
        "gccEarlyCall": 0, "gccMode": 0, "gccSVLR": 0, "maxFT": 120,
        "newZrtc": 1, "packetMode": 1, "platform": 2, "sP2P": 0,
        "serverAddr": [{"rtcp": rtcp, "rtcpIPv6": "::FFFF:%s" % rtcp,
                        "rtp": rtp, "rtpIPv6": "::FFFF:%s" % rtp, "tpType": 0}],
        "spTcp": 0, "srtcp": 0, "srtpMode": srtp_mode, "supportCallBusy": 0,
        "supportHevcDecode": 0, "tpType": 0,
        "video": {"codec": [{"name": "h264", "payload": 97}]},
    }
    if srtp_key:
        out["srtpKey"] = srtp_key
        out["srtpMode"] = 1
    return out


def native_extend_data(rtp, rtcp, is_video=False, rtp_v6="", rtcp_v6=""):
    """extendData cua 416 y het engine zcall-native (Zalo-Linux, chay that voi
    dien thoai): newZrtc 1, platform 2, packetMode 2, gcc bat, spTcp 1,
    supportCallBusy 1, serverAddr dang dict cua relay duoc chon. Do 10/11/2026:
    voi bo "pc" cu (newZrtc 0, platform 3) dien thoai tra RTP kieu cu 12 byte va
    khong bao nhan duoc luong cua ta (SR RC=0) -> tu giay thu 4 bao khong on dinh."""
    return {
        "callType": 1 if is_video else 0, "fecTP": 0, "gccAudio": 1,
        "gccEarlyCall": 0, "gccMode": 1, "gccSVLR": 1, "maxFT": 60,
        "newZrtc": 1, "p2p": [], "packetMode": 2, "platform": 2, "sP2P": 0,
        "serverAddr": [{"rtcp": rtcp, "rtcpIPv6": rtcp_v6 or "::FFFF:%s" % rtcp,
                        "rtp": rtp, "rtpIPv6": rtp_v6 or "::FFFF:%s" % rtp,
                        "tpType": 0}],
        "spTcp": 1, "srtcp": 0, "srtpMode": 1, "supportCallBusy": 1,
        "supportHevcDecode": 0, "tpType": 0,
        "video": {"codec": [{"name": "h264", "payload": 97}]},
    }


def _extend_data_dict(extend_data, srtp_mode, is_video=False,
                      server_addrs=None, srtp_key=None):
    """Normalize extendData to a dict for TransportConfig.

    Explicit dict/JSON string wins (normalized by
    `udp_transport.normalize_extend_data` — unknown keys
    dropped, nothing merged in). Otherwise build the full
    engine-default dict (`_MINIMAL_EXTEND_DATA`, all 24 keys —
    2026-11-08 step 2) plus `callType` (a 0/1 audio/video flag:
    0 for a voice call, 1 for a video call) and `srtpMode`
    (the 11300 value when the response carries one, else 0 —
    the engine default; 0 is valid per the validator, only
    {1, 2, 3} are non-zero modes). `server_addrs` (the 11300
    servers' RTP addresses as "IP:port" strings — see
    `_server_addr_list`: one per ADVERTISED server, IPv4
    preferred) fills `numServers` and `serverAddr`. Never
    returns None.

    `callType` is NOT the typeRequest enum (1/3/5/6): the group
    builder (12434, VA 0x717450) maps the makeCall type byte
    5 (group audio) -> callType 0 and 6 (group video) ->
    callType 1, i.e. callType is 0 for audio, 1 for video.
    The 00db2b9 fix wrongly put the 1-1/group enum (1/5) here,
    which made the server treat voice calls as video calls
    (live 2026-11-08: BenBap's phone showed an incoming VIDEO
    call). The 1-1/group distinction lives in `typeRequest`
    (11300) and in `TransportConfig.call_type`, never in
    extendData's callType.

    `is_video` is False by default (voice calls — what this
    app places today). It is the hook for the future video-call
    feature the user wants: when video is implemented, the
    caller passes is_video=True (and server.py must derive
    typeRequest 3/6 instead of 1/5 at the same time).

    The minimal dict exists because the real client ALWAYS sends
    extendData in 11301 (builder 416 at VA 0x72eed0 inserts all
    7 fields unconditionally; extendData is built by serializer
    0x8e1183 from engine state), while the real 11300 response
    carries no `extendData` key — so without this, 11301 went
    out with only 6/7 fields (no extendData, no subCommand=3)
    and the server could treat it as a request with no media
    config and never ring the peer (live 2026-11-08: 5 calls,
    step2_status=0, ring_timeout 30s).
    """
    if extend_data is not None:
        if isinstance(extend_data, str):
            try:
                extend_data = json.loads(extend_data)
            except ValueError as exc:
                raise MissingTransportParam(
                    "extend_data: not valid JSON: %s" % exc) from exc
        return normalize_extend_data(extend_data)
    mode = (srtp_mode if isinstance(srtp_mode, int)
            and not isinstance(srtp_mode, bool) else 0)
    minimal = dict(_MINIMAL_EXTEND_DATA)
    minimal["callType"] = 1 if is_video else 0
    minimal["srtpMode"] = mode
    if srtp_key is not None:
        # Che do thu "key" (2026-11-09): ben goi gui khoa SRTP cua chinh
        # no, y het ZaloRtcSession.buildZrtcExtendData cua zca-js 2.3.13
        # (srtpMode=1 + srtpKey base64). Mac dinh KHONG di vao day.
        minimal["srtpKey"] = srtp_key
        minimal["srtpMode"] = 1
    # video.codec stays "" even for video (see the
    # _MINIMAL_EXTEND_DATA comment): the audio codec is not the
    # video codec; the future video path must supply a real one.
    minimal["video"] = {"codec": (list(protocol.VIDEO_CODEC)
                                  if is_video else "")}
    minimal["serverResult"] = []
    if server_addrs:
        minimal["numServers"] = len(server_addrs)
        minimal["serverAddr"] = list(server_addrs)
    else:
        minimal["numServers"] = 0
        minimal["serverAddr"] = []
    return normalize_extend_data(minimal)


# ------------------------------------------------------------------ provider

def _latest_unknown_sample(transport):
    """Latest unrecognized packet as a scrubbed one-liner, or "".

    Reads transport.unknown_samples() when present (the real
    transport keeps them; fakes may not). A sample holds only
    the length, the head byte, and the first 16 bytes as hex —
    no address — so it is safe to put in an error message. The
    first 16 bytes can never hold a reflexive address (that
    starts at offset 35), and the hex prefix is what tells the
    next live test whether the reply was a type-02 of an
    unexpected shape or something else entirely.
    """
    getter = getattr(transport, "unknown_samples", None)
    if not callable(getter):
        return ""
    try:
        samples = getter()
    except Exception:  # noqa: BLE001 - diagnostics must not raise
        return ""
    if not samples:
        return ""
    last = samples[-1]
    try:
        return ("; last unknown packet: len=%s head=0x%02x hex=%s"
                % (last.get("len"), last.get("head") or 0,
                   last.get("hex", "")))
    except Exception:  # noqa: BLE001 - diagnostics must not raise
        return ""


def _describe_wait_failure(transport):
    """Diagnostic summary for a relay-selection timeout.

    Counters and relay families ONLY — never relay IPs/ports,
    never the token. The next live test can be judged from this
    alone:
      * probe_tx==0 + send_errors>0: no datagram ever left the
        socket (wrong address family, unreachable network).
      * probe_tx>0 + type02_rx==0 + unknown_rx==0: the path is
        silent in both directions (UDP blocked, or the relay
        rejected the setup without answering).
      * unknown_rx>0 / recv_errors>0: replies arrived but were
        not recognized as type-02.
      * type02_rx>0: a type-02 arrived but was not selected
        (see last_error — e.g. an unlisted sender).
    """
    counters = getattr(transport, "counters", None)
    if not isinstance(counters, dict):
        counters = {}

    def _n(name):
        try:
            return int(counters.get(name) or 0)
        except (TypeError, ValueError):
            return 0

    relays_txt = ""
    config = getattr(transport, "config", None)
    relays = getattr(config, "relays", None) if config is not None else None
    if isinstance(relays, (list, tuple)) and relays:
        v4 = v6 = 0
        for r in relays:
            try:
                fam = ipaddress.ip_address(str(getattr(r, "rtp_ip", "")))
            except ValueError:
                continue
            if isinstance(fam, ipaddress.IPv6Address):
                v6 += 1
            else:
                v4 += 1
        relays_txt = "; relays=%d (v4=%d, v6=%d)" % (len(relays), v4, v6)
    last_error = getattr(transport, "_last_error", None) or "none"
    summary = (" | probe_tx=%d setup_init_tx=%d send_errors=%d "
               "type02_rx=%d unknown_rx=%d recv_errors=%d "
               "ping_reply_rx=%d%s; last_error=%s"
               % (_n("probe_tx"), _n("setup_init_tx"), _n("send_errors"),
                  _n("type02_rx"), _n("unknown_rx"), _n("recv_errors"),
                  _n("ping_reply_rx"), relays_txt, last_error))
    if _n("send_errors") > 0 and _n("probe_tx") == 0 \
            and _n("setup_init_tx") == 0:
        hint = ("hint: no probe/setup datagram left the socket "
                "(send_errors=%d) — check the relay address "
                "family / socket" % _n("send_errors"))
    elif _n("type02_rx") > 0:
        hint = ("hint: type-02 arrived but was not selected "
                "(see last_error)")
    elif _n("unknown_rx") > 0 or _n("recv_errors") > 0:
        hint = ("hint: unrecognized packets arrived "
                "(unknown_rx=%d, recv_errors=%d)"
                % (_n("unknown_rx"), _n("recv_errors")))
        hint += _latest_unknown_sample(transport)
    else:
        hint = ("hint: probes/setups were sent but nothing came "
                "back in the wait — the UDP path to the relay or "
                "the relay's reply may be blocked, or the setup "
                "was rejected")
    return summary + "; " + hint


class MediaEndpoints:
    """Phase-2 provider: real relay allocation via Udp4200Transport.

    `transport_factory` is `callable(config) -> transport` (default:
    the real `Udp4200Transport`); tests inject a fake. `srtp_factory`
    is `callable(srtp_key) -> (protect_rtp, unprotect_rtp)` (default
    None: no SRTP hooks are built — the transport still starts for
    the handshake, and media stays unwired until hooks are injected;
    see `pc_media.media_hooks_for_call`).

    Constructor-level `default_*` values exist ONLY so tests can
    pre-configure an instance; the module-global `ENDPOINTS` has
    none, so a real call without 11300 allocation raises instead
    of silently using a stale default.
    """

    def __init__(self, transport_factory=None, srtp_factory=None,
                 default_relays=None, default_token=None,
                 default_session=None, default_local_session=None,
                 default_srtp_key=None, default_call_session=None,
                 default_peer_session=None, default_codec=None):
        self._transport_factory = (
            transport_factory or self._default_transport_factory)
        self._srtp_factory = srtp_factory
        self._defaults = {
            "relays": default_relays, "token": default_token,
            "session": default_session,
            "local_session": default_local_session,
            "srtp_key": default_srtp_key,
            "call_session": default_call_session,
            "peer_session": default_peer_session,
            "codec": default_codec,
        }
        # call_id -> {"transport", "srtp_key", "codec", ...} (memory
        # only; the SRTP key value is NEVER logged or serialized).
        self.active = {}

    @staticmethod
    def _default_transport_factory(config):
        return Udp4200Transport(config)

    # -- main entry point ------------------------------------------

    def for_call(self, call_id=None, callee_id=None, call_type="user",
                 codec=None, relays=None, servers=None, token=None,
                 session=None, local_session=None, peer_session=None,
                 call_session=None, call_counter=None, srtp_key=None,
                 extend_data=None, srtp_mode=None, is_video=False,
                 zrtc_config=None, requestcall_data=None,
                 protect_rtp=None, unprotect_rtp=None,
                 protect_video_rtp=None,
                 encode_frame=None, decode_frame=None,
                 selection_timeout=5.0, transport_factory=None,
                 on_first_media=None, advertise_srtp_key=False,
                 extend_profile="pc", is_caller=True):
        """Media fields for one outgoing call's request step (11301).

        `is_caller=False` khi NGHE MÁY cuộc gọi đến: InitZRTP gửi lệnh 12 (callee) thay vì 11 (caller) và gói P2P mang role 1. Engine
        zcall-native (chạy thật với điện thoại) phân biệt hai lệnh này; gửi 11 khi nghe máy làm relay có hai bên «gọi» và không có
        bên nghe máy để nối với điện thoại (đo 11/11/2026: 0 gói tiếng từ điện thoại về qua relay).

        Returns {"rtcp_address", "rtp_address", "rtp_source",
        "session", "extend_data", "codec", "transport",
        "selected_relay", "call_id", "callee_id"} — the first five
        are exactly what `signaling.Signaling.send_request` /
        `send_request_group` need; `transport` is the started
        `Udp4200Transport` (kept in `self.active[call_id]` until
        `stop_call`).

        `rtp_address`/`rtcp_address` are `"IP:port"` strings —
        the 11300 response's `rtpIP`/`rtcpIP` when they differ
        from the selected relay (`rtp_source` = "rtpIP"), else
        the SELECTED relay's addresses (`rtp_source` =
        "selected"; first type-02 wins, per disassembly).
        `for_call` waits up to `selection_timeout` seconds for
        the selection and raises (after stopping the transport)
        when no relay answers. Addresses are NEVER "".

        Raises `MissingTransportParam` naming the missing
        parameter when any of these is absent: `call_id`,
        `callee_id`, `relays`/`servers`, `token`, `session`,
        `local_session` (the server-issued 32-bit id of the
        logged-in account, from response 11300 `fromId` — see
        the module docstring; never derived from the session
        uid, never randomised, never defaulted). (`token` comes
        from an explicit `token` key or from 11300 `sessId`
        when it validates as 115 bytes / 154 chars — LIVE
        2026-11-06; see `allocation_from_requestcall_data`.)
        `peer_session` comes from 11300 `toId` for 1-1 calls
        only (a group response's `toId` is not one peer's id,
        so group calls keep None); when `toId` is absent or
        invalid it stays None honestly.
        `srtp_key` is NOT in that list any more: the real 11300
        response (live 2026-11-06) carries NO `srtpKey`, so
        requiring it made 11301 unsendable on every real call.
        Without a key the call still signals (11301 is sent, the
        transport handshakes) but media stays unwired — `srtp`
        is reported as "not-wired", no SRTP hooks are built, and
        `send_pcm` refuses without a `protect_rtp` hook. The key
        source is still open (it may live inside the 115-byte
        token, in `settings`/`msg`, or be issued separately);
        nothing is invented to stand in for it.
        """
        # 1. Merge sources: explicit args > 11300 response > zrtc_config.
        alloc = {}
        if requestcall_data is not None:
            alloc.update(allocation_from_requestcall_data(requestcall_data))
        if isinstance(zrtc_config, dict):
            alloc.update(allocation_from_requestcall_data(
                {"zrtc_config": zrtc_config}))
        # Shape note (key names + counts ONLY, never values): every
        # missing-param error below carries it, so one live-test
        # screenshot tells the next round exactly which keys the
        # real 11300 response does/does not carry.
        _note_data = (dict(requestcall_data)
                      if isinstance(requestcall_data, dict) else {})
        if isinstance(zrtc_config, dict):
            _note_data.setdefault("zrtc_config", zrtc_config)
        shape_note = (describe_requestcall_shape(_note_data)
                      if _note_data else "")
        if servers is None and alloc.get("servers") is not None:
            servers = alloc["servers"]
        if relays is None:
            relays = self._defaults["relays"]
        if token is None:
            token = alloc.get("token", self._defaults["token"])
        if session is None:
            session = alloc.get("session", self._defaults["session"])
        # call_type is needed for the peer merge below (a group
        # response's toId is not one peer's id), so normalize it
        # here, before the merge; section 2 re-checks the value.
        if isinstance(call_type, str):
            call_type = 1 if call_type != "group" else 5
        if call_type not in (1, 5):
            raise ValueError(
                "call_type: must be 1 (audio 1-1) or 5 (audio group), "
                "got %r" % (call_type,))
        # local_session / peer_session: explicit arg > instance
        # default > response 11300 (`fromId` / `toId`). The
        # response is the ONLY live source: the session uid is
        # 64-bit and is never converted, truncated, or hashed
        # into a u32 (no such conversion exists in the native
        # client), and the callee threadId is not a user id.
        if local_session is None:
            local_session = self._defaults["local_session"]
        if local_session is None:
            local_session = alloc.get("local_session")
        if peer_session is None:
            peer_session = self._defaults["peer_session"]
        if peer_session is None and call_type != 5:
            peer_session = alloc.get("peer_session")
        if call_session is None:
            call_session = self._defaults["call_session"]
        if srtp_key is None:
            srtp_key = alloc.get("srtp_key", self._defaults["srtp_key"])
        if codec is None:
            codec = alloc.get("codec", self._defaults["codec"])
        if srtp_mode is None:
            srtp_mode = alloc.get("srtp_mode")
        if extend_data is None and alloc.get("extend_data") is not None:
            extend_data = alloc["extend_data"]

        # 2. Validate identity first (names the parameter).
        call_id = _as_int(call_id)
        if call_id is None or not 1 <= call_id <= 2 ** 32 - 1:
            raise MissingTransportParam(
                "call_id: missing (need a uint32 call identity, got %r)"
                % (call_id,))
        if not callee_id or not isinstance(callee_id, str):
            raise MissingTransportParam(
                "callee_id: missing (need the callee threadId string)")

        # 3. Relays (never an empty / half-built list).
        relay_list = _normalize_relays(relays, servers)
        if not relay_list:
            raise MissingTransportParam(
                "relays: empty (need at least one relay from response "
                "11300: servers as a list of dicts with rtcpaddr/"
                "rtpIPv6 (real shape, seen live 2026-11-05) or a "
                "legacy zrtc_config.servers string; got %s%s)"
                % (_describe_servers_value(
                    servers if servers is not None else relays),
                    ("; " + shape_note) if shape_note else ""))

        # 4. Token / session / local session (SRTP key: see below).
        if token is None or token == b"" or token == "":
            raise MissingTransportParam(
                "token: missing (need 115 raw bytes or a 154-char "
                "base64url string, most likely response 11300 "
                "sessId%s%s)"
                % ("; sessId was present but is not a 115-byte / "
                   "154-char token"
                   if alloc.get("session") is not None else "",
                   ("; " + shape_note) if shape_note else ""))
        if session is None or (isinstance(session, str)
                               and not session):
            raise MissingTransportParam(
                "session: missing (need the 416 session string; "
                "candidate source is response 11300 sessId, "
                "UNCONFIRMED%s)"
                % (("; " + shape_note) if shape_note else ""))
        session = str(session)
        if local_session is None:
            raise MissingTransportParam(
                "local_session: missing (need a u32 — the same value "
                "as the RTP SSRC; per disassembly 2026-11-06 it is "
                "the server-issued 32-bit id of the logged-in "
                "account, carried by response 11300 `fromId` "
                "(CallConfig+0x0 = userId) — it is NOT derived "
                "from the session uid (64-bit), NOT generated "
                "fresh per call, never defaulted%s%s)"
                % (("; `fromId` was present but is not a u32: %s"
                    % alloc.get("local_session_invalid"))
                   if alloc.get("local_session_invalid") else "",
                   ("; " + shape_note) if shape_note else ""))
        local_session = _as_int(local_session)
        if local_session is None or not 0 <= local_session <= 2 ** 32 - 1:
            raise MissingTransportParam(
                "local_session: must be a u32 int, got %r"
                % (local_session,))
        # srtp_key is OPTIONAL for signaling (see docstring):
        # the real 11300 carries no srtpKey (live 2026-11-06),
        # so blocking 11301 on it would block every real call.
        # Without a key the transport handshakes and 11301 is
        # sent, but `srtp` stays "not-wired" and voice cannot
        # flow until the key source is found — never a lie, and
        # never a guessed key.

        # 5. Codec + extendData. extendData is ALWAYS built now
        # (never None): the real client always sends it in 11301,
        # and _extend_data_dict fills the engine defaults when the
        # 11300 response carries none — see its docstring.
        # `is_video` only selects extendData's callType flag
        # (0 = voice, 1 = video); the 1-1/group `call_type`
        # (1/5) never goes into extendData. Voice is the default
        # (this app only places voice calls today); video is a
        # future feature — when it lands, the caller must also
        # switch typeRequest to 3/6 in server.py.
        if codec is None:
            codec = protocol.DEFAULT_CODEC
        codec = str(codec)
        ext_dict = _extend_data_dict(
            extend_data, srtp_mode, is_video,
            server_addrs=_server_addr_list(servers, relay_list),
            srtp_key=(srtp_key if advertise_srtp_key
                      and isinstance(srtp_key, str) else None))
        extend_str = (json.dumps(ext_dict, separators=(",", ":"),
                                 ensure_ascii=False)
                      if ext_dict else None)

        # 6. SRTP hooks: explicit hooks win; else build from the key
        # via the injected factory (only when a key exists); else
        # handshake-only (None). An empty key counts as no key.
        if srtp_key == b"" or srtp_key == "":
            srtp_key = None
        if protect_rtp is None and unprotect_rtp is None \
                and self._srtp_factory is not None \
                and srtp_key is not None:
            protect_rtp, unprotect_rtp = self._srtp_factory(srtp_key)
        srtp_state = ("wired" if protect_rtp is not None
                      and unprotect_rtp is not None else "not-wired")

        # 7. Build the transport config (TransportConfig itself
        # re-validates relays/token/session/call identity and raises
        # MissingTransportParam naming the parameter).
        preferred = None
        _raw_rtp = alloc.get("rtp_ip")
        _pa = _parse_addr_value(_raw_rtp) if isinstance(_raw_rtp, str) \
            and _raw_rtp else None
        if _pa is not None:
            for _r in relay_list:
                if _r.rtp_ip == _pa[0] and _pa[1] in (None, _r.rtp_port):
                    preferred = _r.rtp_addr()
                    break
        config = TransportConfig(
            preferred_rtp=preferred,
            relays=relay_list, token=token,
            local_session=local_session, peer_session=peer_session,
            call_id=call_id, callee_id=str(callee_id),
            call_type=call_type, codec=codec, extend_data=ext_dict,
            protect_rtp=protect_rtp, unprotect_rtp=unprotect_rtp,
            protect_video_rtp=protect_video_rtp,
            encode_frame=encode_frame, decode_frame=decode_frame,
            call_session=call_session, is_caller=is_caller,
            **({"call_counter": call_counter}
               if call_counter is not None else {}))
        factory = transport_factory or self._transport_factory
        transport = factory(config)
        # First-media hook (2026-11-08): the caller (server.py)
        # passes a callback that marks the call answered when the
        # first inbound RTP arrives — arrival alone proves the
        # peer answered (pcap), so this works without the sync
        # channel. Set as an attribute (TransportConfig has no
        # such field); a factory that rejects it must not break
        # the call, so the assignment is guarded.
        if on_first_media is not None:
            try:
                transport.on_first_media = on_first_media
            except Exception:  # noqa: BLE001 - hook is optional
                pass

        # 8. Start + wait for relay selection (first type-02).
        # The 416 addresses are the SELECTED relay's addresses, not
        # a guess: the real client only sends 416 after Init
        # (pcap file 4: setup 11.66 s -> answer burst 11.72 s).
        transport.start()
        try:
            selected = self._wait_selected(transport, selection_timeout)
        except Exception:
            try:
                transport.stop()
            except Exception:  # noqa: BLE001 - stop is best-effort
                pass
            raise
        if not selected.rtp_ip or selected.rtp_port <= 0 \
                or not selected.rtcp_ip or selected.rtcp_port <= 0:
            try:
                transport.stop()
            except Exception:  # noqa: BLE001 - stop is best-effort
                pass
            raise RuntimeError(
                "selected relay has an empty address (rtp=%r rtcp=%r); "
                "refusing to send 11301 with empty endpoints"
                % (_format_ip_port(selected.rtp_ip, selected.rtp_port),
                   _format_ip_port(selected.rtcp_ip, selected.rtcp_port)))
        # 11301 addresses (2026-11-08, step 1 / D8): the 11300
        # response designates rtpIP/rtcpIP — when they differ
        # from the selected relay, 11301 uses THEM (the server
        # may not route an invitation naming a different relay
        # than the one it designated); otherwise the selected
        # relay. `rtp_source` ("rtpIP" / "selected") records
        # which one was used, so the live log can tell the next
        # round whether the designated addresses changed
        # anything.
        rtp_address, rtcp_address, rtp_source = \
            _resolve_11301_addresses(alloc.get("rtp_ip"),
                                     alloc.get("rtcp_ip"), selected)
        if extend_profile == "native":
            _sv = next((x for x in (servers or [])
                        if isinstance(x, dict)
                        and x.get("rtpaddr") == rtp_address), {})
            extend_str = json.dumps(
                native_extend_data(rtp_address, rtcp_address, is_video,
                                   _sv.get("rtpIPv6", ""),
                                   _sv.get("rtcpIPv6", "")),
                separators=(",", ":"), ensure_ascii=False)
        elif extend_profile == "zca":
            extend_str = json.dumps(
                zca_extend_data(rtp_address, rtcp_address, is_video,
                                ext_dict.get("srtpMode", 0), srtp_key
                                if advertise_srtp_key else None),
                separators=(",", ":"), ensure_ascii=False)
        record = {"transport": transport, "srtp_key": srtp_key,
                  "codec": codec, "call_id": call_id,
                  "callee_id": str(callee_id),
                  "selected_relay": selected, "srtp": srtp_state}
        self.active[call_id] = record
        return {"rtcp_address": rtcp_address,
                "rtp_address": rtp_address,
                "rtp_source": rtp_source,
                "session": session,
                "extend_data": extend_str,
                "codec": codec,
                "transport": transport,
                "selected_relay": selected,
                "call_id": call_id,
                "callee_id": str(callee_id),
                "srtp": srtp_state}

    @staticmethod
    def _wait_selected(transport, timeout):
        """Poll for `transport.selected_relay` up to `timeout`
        seconds; raise RuntimeError (naming the missing type-02
        plus the transport's counters, so the next live test can
        be diagnosed from the message alone) on timeout. A
        fake/loopback transport selects synchronously, so tests
        do not wait."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            selected = getattr(transport, "selected_relay", None)
            if selected is not None:
                return selected
            if time.monotonic() >= deadline:
                state = getattr(transport, "state", "?")
                raise RuntimeError(
                    "no relay selected within %.1fs (transport "
                    "state=%s): no type-02 arrived from any "
                    "relay, so there is no address to put in 11301%s"
                    % (timeout, state,
                       _describe_wait_failure(transport)))
            time.sleep(0.02)

    # -- lifecycle -------------------------------------------------

    def active_record(self, call_id):
        """Memory-only record for a started call (transport +
        srtp_key + codec). The SRTP key value is never logged or
        put in an HTTP response; `server.py` uses this only to
        wire the media engine."""
        return self.active.get(_as_int(call_id) or call_id)

    def stop_call(self, call_id):
        """Stop + forget the transport of one call. Best-effort,
        never raises."""
        record = self.active.pop(_as_int(call_id) or call_id, None)
        if record is None:
            return False
        try:
            record["transport"].stop()
        except Exception:  # noqa: BLE001 - stop is best-effort
            pass
        return True

    def stop_all(self):
        """Stop every active transport. Best-effort, never raises."""
        for call_id in list(self.active):
            self.stop_call(call_id)


ENDPOINTS = MediaEndpoints()
