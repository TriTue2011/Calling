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
be selected (first type-02 52B, the disassembly's
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
               Ultimate source UNCONFIRMED (most likely 11300);
               the provider takes it from `zrtc_config["token"]`
               or an explicit argument — it never generates one.
  session      the 416 `session` STRING. Candidate source:
               11300 `sessId` (same struct as `servers`) —
               UNCONFIRMED, the disassembly never found who writes
               it first. The provider uses an explicit `session`
               first, then `sessId`.
  local_session  u32, the same value as the RTP SSRC (setup packet
               offset 10-13 LE = RTP SSRC BE). A per-device value
               whose source is UNKNOWN — it is NOT the captured
               `0x15cbea3f` (that is one device's SSRC, never baked
               in as a default). Must be supplied by the caller.
  call_session   the 4-byte value at setup offset 21-24 / P2P
               offset 3-6. Optional: `Udp4200Transport` generates
               random bytes with last byte 0x2b when omitted.
  peer_session   u32 or None (not yet known before the callee's
               416); optional.
  srtp_key     from `zrtc_config.srtpKey` (a STRING of unknown
               format/length). The provider does NOT decode it and
               does NOT guess key material: it is passed unchanged
               to the SRTP hook factory (`pc_media`), which
               converts it strictly (base64url attempt + exact
               suite-length check) or fails loudly. `srtpKey` /
               `srtpNoSeq` / `srtpRTCP` are keys of `zrtc_config`,
               NOT of extendData (disassembly correction).
  extend_data  dict or JSON string, normalized to the 23 known
               keys (`udp_transport.normalize_extend_data` — unknown
               keys dropped, bad `srtpMode` reset to 0). Optional:
               when absent, the provider only fills `srtpMode`
               from `zrtc_config` if present; otherwise None, and
               `vc_request` omits `extendData`/`subCommand=3`.
  codec        explicit > `zrtc_config.g711` (1->"pcmu", 2->"pcma",
               else "opus" — SUY LUAN, disasm §3.3) > "opus"
               (UNCONFIRMED default; the on-wire codec was never
               proven because the payload is SRTP-encrypted).
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

import ipaddress
import json
import re
import time

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
           "describe_requestcall_shape"]


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
    return "; ".join(parts)


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


def _format_ip_port(ip, port):
    """One relay address as an "IP:port" string for 11301: IPv6
    is bracketed ("[2001:db8::1]:4200") — the unbracketed form
    ("2001:db8::1:4200") is ambiguous and unparseable."""
    if ":" in str(ip):
        return "[%s]:%d" % (ip, port)
    return "%s:%d" % (ip, port)


def _find_in_requestcall_data(data, key):
    """Search `key` in a decoded 11300 response, in the places the
    disassembly puts it: top level, nested `data`, and inside
    `zrtc_config`. Returns None when absent everywhere."""
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    inner = data.get("data")
    if isinstance(inner, dict) and key in inner:
        return inner[key]
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
    `token`, `session` (from `sessId` — UNCONFIRMED candidate),
    `srtp_key` (from `zrtc_config.srtpKey`), `srtp_mode`,
    `codec` (from `zrtc_config.g711`), `extend_data` (from a
    top-level `extendData` string/dict when present).
    Absent keys are simply missing: `for_call` raises naming
    each one instead of filling in a guess.
    """
    if not isinstance(data, dict):
        return {}
    cfg = _zrtc_config_of(data)
    out = {}
    servers = _find_in_requestcall_data(data, "servers")
    if servers is not None:
        out["servers"] = servers
    token = _find_in_requestcall_data(data, "token")
    if token is not None:
        out["token"] = token
    sess = _find_in_requestcall_data(data, "sessId")
    if sess is None:
        sess = _find_in_requestcall_data(data, "session")
    if sess is not None:
        out["session"] = str(sess)
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
    g711 = cfg.get("g711")
    if g711 is None:
        g711 = _find_in_requestcall_data(data, "g711")
    if isinstance(g711, int) and not isinstance(g711, bool):
        out["codec"] = ("pcmu" if g711 == 1 else
                        "pcma" if g711 == 2 else "opus")
    ext = _find_in_requestcall_data(data, "extendData")
    if ext is not None:
        out["extend_data"] = ext
    return out


def _codec_from_g711(g711):
    if g711 == 1:
        return "pcmu"
    if g711 == 2:
        return "pcma"
    return "opus"


def _extend_data_dict(extend_data, srtp_mode):
    """Normalize extendData to a dict for TransportConfig.

    Explicit dict/JSON string wins (normalized by
    `udp_transport.normalize_extend_data`). Otherwise, when the
    11300 config carries a `srtpMode`, emit just that one known
    key — every other key stays absent rather than invented.
    Returns None when there is nothing to send.
    """
    if extend_data is not None:
        if isinstance(extend_data, str):
            try:
                extend_data = json.loads(extend_data)
            except ValueError as exc:
                raise MissingTransportParam(
                    "extend_data: not valid JSON: %s" % exc) from exc
        return normalize_extend_data(extend_data)
    if isinstance(srtp_mode, int) and not isinstance(srtp_mode, bool):
        return normalize_extend_data({"srtpMode": srtp_mode})
    return None


# ------------------------------------------------------------------ provider

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
                 extend_data=None, srtp_mode=None,
                 zrtc_config=None, requestcall_data=None,
                 protect_rtp=None, unprotect_rtp=None,
                 encode_frame=None, decode_frame=None,
                 selection_timeout=5.0, transport_factory=None):
        """Media fields for one outgoing call's request step (11301).

        Returns {"rtcp_address", "rtp_address", "session",
        "extend_data", "codec", "transport", "selected_relay",
        "call_id", "callee_id"} — the first five are exactly what
        `signaling.Signaling.send_request` / `send_request_group`
        need; `transport` is the started `Udp4200Transport` (kept
        in `self.active[call_id]` until `stop_call`).

        `rtp_address`/`rtcp_address` are `"IP:port"` strings of
        the SELECTED relay (first type-02 wins, per disassembly);
        `for_call` waits up to `selection_timeout` seconds for
        the selection and raises (after stopping the transport)
        when no relay answers. Addresses are NEVER "".

        Raises `MissingTransportParam` naming the missing
        parameter when any of these is absent: `call_id`,
        `callee_id`, `relays`/`servers`, `token`, `session`,
        `local_session`, `srtp_key`. (A missing `srtp_key` is
        fatal here even though the transport itself can start
        without SRTP hooks: without the key the call can never
        carry voice, so promising media in 11301 would be a lie.
        Supplying explicit `protect_rtp`/`unprotect_rtp` hooks
        does NOT waive the key — the key is the call's SRTP
        material from `zrtc_config.srtpKey`.)
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
        if local_session is None:
            local_session = self._defaults["local_session"]
        if peer_session is None:
            peer_session = self._defaults["peer_session"]
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
        if isinstance(call_type, str):
            call_type = 1 if call_type != "group" else 5
        if call_type not in (1, 5):
            raise ValueError(
                "call_type: must be 1 (audio 1-1) or 5 (audio group), "
                "got %r" % (call_type,))

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

        # 4. Token / session / local session / SRTP key.
        if token is None or token == b"" or token == "":
            raise MissingTransportParam(
                "token: missing (need 115 raw bytes or a 154-char "
                "base64url string, most likely from response 11300%s)"
                % (("; " + shape_note) if shape_note else ""))
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
                "as the RTP SSRC; the captures show it CONSTANT per "
                "device, so it is NOT generated fresh per call and "
                "never defaulted to the captured 0x15cbea3f — its "
                "source is still unknown, it must be supplied%s)"
                % (("; " + shape_note) if shape_note else ""))
        local_session = _as_int(local_session)
        if local_session is None or not 0 <= local_session <= 2 ** 32 - 1:
            raise MissingTransportParam(
                "local_session: must be a u32 int, got %r"
                % (local_session,))
        if srtp_key is None or srtp_key == b"" or srtp_key == "":
            raise MissingTransportParam(
                "srtp_key: missing (need zrtc_config.srtpKey from "
                "response 11300; without it the call can never carry "
                "voice%s)"
                % (("; " + shape_note) if shape_note else ""))

        # 5. Codec + extendData.
        if codec is None:
            codec = "opus"  # UNCONFIRMED default (see module docstring)
        codec = str(codec)
        ext_dict = _extend_data_dict(extend_data, srtp_mode)
        extend_str = (json.dumps(ext_dict, separators=(",", ":"),
                                 ensure_ascii=False)
                      if ext_dict else None)

        # 6. SRTP hooks: explicit hooks win; else build from the key
        # via the injected factory; else handshake-only (None).
        if protect_rtp is None and unprotect_rtp is None \
                and self._srtp_factory is not None:
            protect_rtp, unprotect_rtp = self._srtp_factory(srtp_key)
        srtp_state = ("wired" if protect_rtp is not None
                      and unprotect_rtp is not None else "not-wired")

        # 7. Build the transport config (TransportConfig itself
        # re-validates relays/token/session/call identity and raises
        # MissingTransportParam naming the parameter).
        config = TransportConfig(
            relays=relay_list, token=token,
            local_session=local_session, peer_session=peer_session,
            call_id=call_id, callee_id=str(callee_id),
            call_type=call_type, codec=codec, extend_data=ext_dict,
            protect_rtp=protect_rtp, unprotect_rtp=unprotect_rtp,
            encode_frame=encode_frame, decode_frame=decode_frame,
            call_session=call_session,
            **({"call_counter": call_counter}
               if call_counter is not None else {}))
        factory = transport_factory or self._transport_factory
        transport = factory(config)

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
        rtp_address = _format_ip_port(selected.rtp_ip,
                                      selected.rtp_port)
        rtcp_address = _format_ip_port(selected.rtcp_ip,
                                       selected.rtcp_port)
        if not selected.rtp_ip or selected.rtp_port <= 0 \
                or not selected.rtcp_ip or selected.rtcp_port <= 0:
            try:
                transport.stop()
            except Exception:  # noqa: BLE001 - stop is best-effort
                pass
            raise RuntimeError(
                "selected relay has an empty address (rtp=%r rtcp=%r); "
                "refusing to send 11301 with empty endpoints"
                % (rtp_address, rtcp_address))
        record = {"transport": transport, "srtp_key": srtp_key,
                  "codec": codec, "call_id": call_id,
                  "callee_id": str(callee_id),
                  "selected_relay": selected, "srtp": srtp_state}
        self.active[call_id] = record
        return {"rtcp_address": rtcp_address,
                "rtp_address": rtp_address,
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
        seconds; raise RuntimeError (naming the missing type-02)
        on timeout. A fake/loopback transport selects
        synchronously, so tests do not wait."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            selected = getattr(transport, "selected_relay", None)
            if selected is not None:
                return selected
            if time.monotonic() >= deadline:
                state = getattr(transport, "state", "?")
                raise RuntimeError(
                    "no relay selected within %.1fs (transport "
                    "state=%s): no type-02 52B arrived from any "
                    "relay, so there is no address to put in 11301"
                    % (timeout, state))
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
