"""PC-style voicecall signaling client (outgoing direction, phase 1).

Every call is HTTPS GET:
  {voicecall}/api/voicecall/<path>?zpw_ver&zpw_type&params=<AES JSON>
with the params encrypted by the *session* key (zpw_enk from
getLoginInfo), AES-CBC zero IV, base64 output.

The transport is the same `http_get(url, timeout)` callable shape as
qr_login, plus an optional Cookie header value (zpw_sek) carried by
the caller via the `cookie` argument of each method.

Responses use the same two-layer envelope as contacts (bundle kCOK
unwrap): outer {error_code: 0, data: "<AES base64>"} — the data
field is ciphertext; the inner {error_code, data} only appears after
AES-decrypting it with the session key. _call decodes it via
crypto.decode_postlogin_data; returning payload["data"] directly
would hand the caller an encrypted string instead of the result.
"""

from . import protocol
from .crypto import decode_postlogin_data, session_aes_encrypt


class ServerRejectedError(RuntimeError):
    """The Zalo server refused a voicecall step (outer or inner
    error_code != 0, e.g. inner 114 "Tham so khong hop le").
    A subclass of RuntimeError so old `except RuntimeError`
    handlers still catch it; `server.py` catches THIS type
    specifically to end a rejected call early (reason
    `server_rejected`) instead of leaving it "sent" with no
    timer. Network failures and decrypt failures stay plain
    RuntimeError — they are NOT a server refusal (the request
    may or may not have arrived)."""


class Signaling:
    def __init__(self, http_get, device_id, zpw_enk, cookie=""):
        self.http_get = http_get
        self.device_id = device_id
        self.zpw_enk = zpw_enk
        self.cookie = cookie

    def _aes(self, raw_json):
        return session_aes_encrypt(self.zpw_enk, raw_json)

    def _call(self, path, body):
        url = protocol.voicecall_params(path, body, self._aes)
        status, payload = self.http_get(url, timeout=30)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("voicecall %s: network status=%s"
                               % (path, status))
        if payload.get("error_code") != 0:
            raise ServerRejectedError("voicecall %s: error_code=%s %s" % (
                path, payload.get("error_code"),
                payload.get("error_message", "")))
        # Two-layer envelope: outer data is an AES-encrypted string;
        # decode it to the inner {error_code, data} first. An inner
        # error_code is a server refusal too (same type, same
        # message) — the caller can tell it apart from a network
        # or decrypt failure.
        try:
            return decode_postlogin_data(payload, self.zpw_enk)
        except RuntimeError as exc:
            if str(exc).startswith("response inner error_code="):
                raise ServerRejectedError(str(exc)) from exc
            raise

    def request_call(self, callee_id, call_id, codec=None,
                     type_request=protocol.CALL_TYPE_AUDIO_1_1):
        # Default is the 1-1 AUDIO call type (1) — never 0; the
        # pre-fix default 0 drew inner 114 from the real server
        # (§7k in bao-cao.md). call_id must be a JSON number in
        # uint32 range (epoch seconds; see server._normalize_call_id).
        return self._call("requestcall", protocol.vc_requestcall(
            callee_id, call_id, codec, type_request, self.device_id))

    def request_call_group(self, group_id, call_id,
                           type_request=protocol.CALL_TYPE_AUDIO_GROUP,
                           data=None, partners=None):
        """Group call request (code 12433): POST-equivalent GET to
        /api/voicecall/group/requestcall with {groupId, callId,
        typeRequest, data, partners}. group_id is the group's
        threadId (raw group id)."""
        return self._call("group/requestcall",
                          protocol.vc_requestcall_group(
                              group_id, call_id, type_request, data,
                              partners))

    def send_request(self, callee_id, rtcp_address, rtp_address, codec,
                     session, call_id, extend_data=None):
        return self._call("request", protocol.vc_request(
            callee_id, rtcp_address, rtp_address, codec, session, call_id,
            self.device_id, extend_data))

    def send_request_group(self, callee_id, call_id, call_type, data,
                           session, partners, group_id):
        """Group media request (code 12434): POST-equivalent GET to
        /api/voicecall/group/request with {calleeId, callId,
        callType, data, session, partners, groupId} (bundle class
        wZ sendRequestCallGroup). The 1-1 twin is send_request
        (11301); a group call needs this step for the same reason —
        without it the server holds an invitation with no media
        endpoints, so the members' phones never ring."""
        return self._call("group/request",
                          protocol.vc_request_group(
                              callee_id, call_id, call_type, data, session,
                              partners, group_id))

    def ringring(self, caller_id, call_id):
        return self._call("ringring", protocol.vc_ringring(
            caller_id, call_id, self.device_id))

    def answer(self, caller_id, call_id, status, codec, rtcp_address,
               rtp_address, session_id, extend_data=None):
        return self._call("answer", protocol.vc_answer(
            caller_id, call_id, status, codec, rtcp_address, rtp_address,
            session_id, extend_data))

    def answer_ack(self, callee_id, call_id):
        return self._call("answerack", protocol.vc_answerack(
            callee_id, call_id, self.device_id))

    def cancel(self, caller_id, call_id, call_type):
        return self._call("cancel", protocol.vc_cancel(
            caller_id, call_id, call_type, self.device_id))

    def endcall(self, uid_to, call_id):
        return self._call("endcall", protocol.vc_endcall(
            uid_to, call_id, self.device_id))

    def endcall_group(self, callee_id, call_id, call_type, host_call=True,
                      data=None, partners=None):
        """Group end (code 12438): /api/voicecall/group/endcall with
        {calleeId, callId, callType, hostCall, data, partners}
        (bundle class wZ sendEndCallGroup). The 1-1 endcall (11306)
        carries a user id as uidTo — sending a groupId through it
        is wrong, same lesson as requestcall (§7i)."""
        return self._call("group/endcall",
                          protocol.vc_endcall_group(
                              callee_id, call_id, call_type, host_call,
                              data, partners))

    def conf(self, callee_id, call_id, cam=-1, mic=-1):
        """Bao trang thai camera/mic cua ta (12006, /api/voicecall/conf)."""
        return self._call("conf", protocol.vc_conf(callee_id, call_id, cam, mic))

    def hold_request(self, to_id):
        return self._call("holdreq", protocol.vc_hold(to_id))

    def hold_response(self, to_id):
        return self._call("holdresp", protocol.vc_hold(to_id))

    def unhold_request(self, to_id):
        return self._call("unholdreq", protocol.vc_hold(to_id))

    def unhold_response(self, to_id):
        return self._call("unholdresp", protocol.vc_hold(to_id))
