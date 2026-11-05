"""PC-style voicecall signaling client (outgoing direction, phase 1).

Every call is HTTPS GET:
  {voicecall}/api/voicecall/<path>?zpw_ver&zpw_type&params=<AES JSON>
with the params encrypted by the *session* key (zpw_enk from
getLoginInfo), AES-CBC zero IV, base64 output.

The transport is the same `http_get(url, timeout)` callable shape as
qr_login, plus an optional Cookie header value (zpw_sek) carried by
the caller via the `cookie` argument of each method.
"""

from . import protocol
from .crypto import session_aes_encrypt


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
            raise RuntimeError("voicecall %s: error_code=%s %s" % (
                path, payload.get("error_code"),
                payload.get("error_message", "")))
        return payload.get("data")

    def request_call(self, callee_id, call_id, codec=None, type_request=0):
        return self._call("requestcall", protocol.vc_requestcall(
            callee_id, call_id, codec, type_request, self.device_id))

    def send_request(self, callee_id, rtcp_address, rtp_address, codec,
                     session, call_id, extend_data=None):
        return self._call("request", protocol.vc_request(
            callee_id, rtcp_address, rtp_address, codec, session, call_id,
            self.device_id, extend_data))

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

    def hold_request(self, to_id):
        return self._call("holdreq", protocol.vc_hold(to_id))

    def hold_response(self, to_id):
        return self._call("holdresp", protocol.vc_hold(to_id))

    def unhold_request(self, to_id):
        return self._call("unholdreq", protocol.vc_hold(to_id))

    def unhold_response(self, to_id):
        return self._call("unholdresp", protocol.vc_hold(to_id))
