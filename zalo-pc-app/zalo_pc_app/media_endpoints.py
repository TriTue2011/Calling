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
also list rtpAddressIPv6 / rtcpAddressIPv6 / rtcpIP). The engine
allocates those relay addresses from the ZRTP relay server at call
start — the 2026-11-04 pcap shows the caller's media setup packets
to the relay starting 20–40 ms after the server's last TCP packet
(the pcap contains no timestamp of the tap, so no claim can be made
about delay after the user pressed call), and the client carries a
`timeoutMakeCall2ZRtp` setting for this step.

What this provider returns in phase 1: EMPTY strings for the
addresses/session and no extendData, because there is no media
engine attached yet (see engine_seam.py — phase 2). The codec is
the same "[]" fallback the requestcall step already uses. Empty
addresses are PLACEHOLDERS, not real endpoints: whether the real
server accepts them is UNVERIFIED from the bundle and is exactly
what the live test must show (a rejection should surface as a
server error on the request step, which server.py reports
non-fatally — the requestcall itself still succeeds).

When the phase-2 engine lands, it replaces this provider with one
that returns the real relay allocation (rtp/rtcp addresses +
session + ZRTP extendData) from the relay handshake; nothing else
in the call path changes.
"""


class MediaEndpoints:
    """Phase-1 provider: no media engine, so no real endpoints."""

    def for_call(self, codec=None):
        """Media fields for one outgoing call's request step.

        Returns {"rtcp_address", "rtp_address", "session",
        "extend_data", "codec"}. All endpoint values are "" in
        phase 1 (no engine); codec falls back to "[]" like
        requestcall does."""
        return {"rtcp_address": "",
                "rtp_address": "",
                "session": "",
                "extend_data": None,
                "codec": codec if codec is not None else "[]"}


ENDPOINTS = MediaEndpoints()
