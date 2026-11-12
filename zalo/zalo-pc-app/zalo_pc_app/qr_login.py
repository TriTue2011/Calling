"""QR login state machine (old-format path = phase 1).

Flow (mirrors the PC client, login-startup chunk):
  1. GET {auth}/api/login/reqqr  (encrypted envelope if a param cipher
     key is configured, else plaintext params + signkey)
       -> QR record: base64_qr, chk_wait_scan, chk_wait_cfirm,
          qr_retry, qr_timeout, token_id, qr_cnt, uid, master_id, ...
  2. Long-poll chk_wait_scan (timeout = qr_timeout s, up to qr_retry
     attempts):
       error 0     -> scan event (avatar, display_name, link_data)
       error -20   -> first scan done, QR2 renew requested (trust path)
       error -21   -> QR2 relink error (clear link history, new QR)
       error 18010 -> user rejected on the phone
  3. Long-poll chk_wait_cfirm (same retry shape):
       error 0 + uid + dkey -> session grant (uid, dkey, zpw_sek,
          zpw_kt, cptch_cert, profile.phonenum, devices)
  4. Caller then calls getLoginInfo (authenticated by zpw_sek) to get
     zpw_enk + service map + ws endpoint, and persists the session.

The NEW-format (trust-device) path needs the WASM trust protocol and
is deliberately NOT implemented here: encountering it raises
TrustFlowRequired instead of silently producing a broken login.

Transport: any callable `http_get(url, timeout) -> (status, json_dict)`.
This keeps the real network code and the mock-server tests on the same
state machine.
"""

import json
import time

from . import protocol
from .crypto import ParamCipher, signkey

ERR_OK = 0
ERR_QR2_RENEW = -20
ERR_QR2_RELINK = -21
ERR_USER_REJECTED = 18010


class LoginError(Exception):
    pass


class TrustFlowRequired(LoginError):
    """Server asked for the trust-device (WASM) flow; not implemented."""


class UserRejected(LoginError):
    pass


class RateLimited(LoginError):
    def __init__(self, wait_seconds):
        super().__init__("QR generation rate limited")
        self.wait_seconds = wait_seconds


class QRExpired(LoginError):
    pass


def _envelope(params, api_name, param_cipher_key, device_id):
    """Build the query dict for a login API call. Returns (query, enk).
    enk is NOT sent on the wire: the real client keeps it to decrypt
    the response (decryptResp). Login calls carry type/client_version
    inside the envelope, not zpw_ver/zpw_type (those belong to the
    post-login calls' common params)."""
    if param_cipher_key:
        cipher = ParamCipher(protocol.API_TYPE, device_id,
                             int(time.time() * 1000), param_cipher_key)
        enc, enk = cipher.encrypt(params)
        out = dict(enc)
        out["type"] = protocol.API_TYPE
        out["client_version"] = protocol.API_VERSION
        out["signkey"] = signkey(api_name, out)
        return out, enk
    out = dict(params)
    out["type"] = protocol.API_TYPE
    out["client_version"] = protocol.API_VERSION
    out["signkey"] = signkey(api_name, out)
    return out, None


def _decode_payload(payload, enk):
    """Response data: plain dict, or (encrypted mode) an AES blob that
    must be decrypted with the request enk first."""
    data = payload.get("data")
    if enk and isinstance(data, str):
        try:
            import json as _json
            data = _json.loads(ParamCipher.decrypt_response(enk, data))
        except Exception as exc:
            raise LoginError("response decrypt failed (18060?): %s" % exc)
    return data


def _truthy(v):
    return v in (1, True, "1", "true", "True")


def fetch_server_flags(http_get, device_id, computer_name):
    """Doc co QR cua may chu Zalo, y nhu Zalo PC luc khoi dong: GET /api/login/getServerInfo (khong ma hoa) roi lay
    data.setttings.authen.trusted_device = {qr_format_trust_device, self_g, logo_qr} (do 12/11/2026: ca ba = 0). PC chon cach dang nhap QR
    theo cac co nay: self_g=0 -> anh QR cua may chu (loai cu, app minh dung); self_g=1 -> client tu dung QR; qr_format_trust_device=1 -> lien
    ket thiet bi tin cay (QR2, Noise/AES-GCM). KHONG BAO GIO nem loi: that bai/khong doc duoc -> known=False (app van thu loai cu nhu truoc).
    Tra ve {"known", "qr_format_trust_device", "self_g", "logo_qr", "detail"}."""
    out = {"known": False, "qr_format_trust_device": False, "self_g": False, "logo_qr": False, "detail": ""}
    try:
        query, _ = _envelope({"imei": device_id, "computer_name": computer_name, "sp_mtn": -1, "bkt": -1},
                             "getserverinfo", None, device_id)
        url = protocol.build_url(protocol.AUTH_DOMAIN, "/api/login/getServerInfo", query)
        status, payload = http_get(url, timeout=15)
        if status != 200 or not isinstance(payload, dict):
            out["detail"] = "getServerInfo: HTTP %s" % status
            return out
        if payload.get("error_code") != 0:
            out["detail"] = "getServerInfo: error_code=%s" % payload.get("error_code")
            return out
        data = payload.get("data")
        if not isinstance(data, dict):
            out["detail"] = "getServerInfo: data khong phai dict"
            return out
        node = ((data.get("setttings") or {}).get("authen") or {}).get("trusted_device")
        if isinstance(node, str):
            try:
                node = json.loads(node)
            except ValueError:
                node = None
        out["known"] = True
        if isinstance(node, dict):
            out["qr_format_trust_device"] = _truthy(node.get("qr_format_trust_device"))
            out["self_g"] = _truthy(node.get("self_g"))
            out["logo_qr"] = _truthy(node.get("logo_qr"))
        else:
            out["detail"] = "may chu khong gui authen.trusted_device: PC coi la 0/0/0 (QR loai cu)"
    except Exception as e:  # noqa: BLE001 - chi la chan doan, khong duoc lam hong dang nhap
        out["detail"] = "getServerInfo: %s: %s" % (type(e).__name__, e)
    return out


def describe_server_flags(flags):
    """Cau tieng Viet mo ta co may chu (cho nhat ky, giao dien, thong bao loi)."""
    if not flags or not flags.get("known"):
        return "Chưa đọc được cờ máy chủ Zalo (%s); app dùng QR loại cũ như mặc định." % ((flags or {}).get("detail") or "không rõ lý do")
    kind = ("liên kết thiết bị tin cậy (QR2)" if flags["qr_format_trust_device"]
            else "Zalo PC tự dựng mã QR" if flags["self_g"] else "ảnh QR do máy chủ cấp (loại cũ)")
    return ("Cờ máy chủ Zalo: qr_format_trust_device=%d, self_g=%d, logo_qr=%d → Zalo PC hiện dùng %s."
            % (flags["qr_format_trust_device"], flags["self_g"], flags["logo_qr"], kind))


def flags_warning(flags):
    """Canh bao khi co may chu KHAC loai app dang ho tro ("" neu khong co gi dang ngai)."""
    if not flags or not flags.get("known"):
        return ""
    if flags["qr_format_trust_device"]:
        return ("Zalo đang bật đăng nhập QR kiểu “thiết bị tin cậy” (qr_format_trust_device=1) mà app chưa hỗ trợ. "
                "App vẫn thử QR loại cũ; nếu không quét hoặc xác nhận được thì đó là nguyên nhân.")
    if flags["self_g"]:
        return ("Zalo đang bật self_g=1 (Zalo PC tự dựng mã QR) còn app dùng ảnh QR do máy chủ cấp. "
                "Nếu mã QR không hiện, đó là nguyên nhân.")
    return ""


def fetch_qr(http_get, device_id, computer_name, logged_uids,
             param_cipher_key=None, self_g=0, qr_form=0, language="vi"):
    """Step 1: request a QR code. Returns the parsed QR record."""
    params = protocol.reqqr_params(device_id, computer_name, logged_uids,
                                   language=language, self_g=self_g,
                                   qr_form=qr_form)
    query, enk = _envelope(params, "reqqr", param_cipher_key, device_id)
    url = protocol.build_url(protocol.AUTH_DOMAIN, "/api/login/reqqr", query)
    status, payload = http_get(url, timeout=30)
    if status != 200 or not isinstance(payload, dict):
        raise LoginError("reqqr: network error status=%s" % status)
    # Server asks to drop param encryption (19000): retry once plaintext.
    if payload.get("error_code") == 19000 and param_cipher_key:
        query, enk = _envelope(params, "reqqr", None, device_id)
        url = protocol.build_url(protocol.AUTH_DOMAIN, "/api/login/reqqr",
                                 query)
        status, payload = http_get(url, timeout=30)
        if status != 200 or not isinstance(payload, dict):
            raise LoginError("reqqr: network error status=%s" % status)
    data = _decode_payload(payload, enk)
    if payload.get("error_code") != 0:
        code = payload.get("error_code")
        # Rate limit carries time_left (ms) in data.
        if isinstance(data, dict) and data.get("time_left") is not None:
            try:
                wait = round(data["time_left"] / 1000)
            except (TypeError, ValueError):
                wait = 90
            wait = wait + (5 - wait % 5)
            raise RateLimited(wait if wait > 20 else 20)
        raise LoginError("reqqr: error_code=%s %s" % (
            code, payload.get("error_message", "")))
    qr = protocol.parse_qr_data(data)
    if not qr["chk_wait_scan"] or not qr["chk_wait_cfirm"]:
        raise LoginError("reqqr: response missing poll urls")
    if not qr["base64_qr"]:
        raise LoginError("reqqr: máy chủ không trả ảnh QR (base64_qr rỗng). Thường do Zalo bật self_g/QR kiểu mới "
                         "mà app chưa hỗ trợ; xem cờ máy chủ ở /api/qr/status.")
    return qr


def _poll(http_get, url, timeout_s, max_attempts):
    """Long-poll loop. Returns (status, payload) of the first
    non-timeout answer, or raises QRExpired after max_attempts."""
    attempts = max_attempts if max_attempts and max_attempts > 0 else 1
    for _ in range(attempts):
        try:
            status, payload = http_get(url, timeout=timeout_s + 5)
        except TimeoutError:
            continue
        if status == 200 and isinstance(payload, dict):
            return status, payload
        # HTTP-level timeout (408) is a repoll, anything else is fatal.
        if status == 408:
            continue
        raise LoginError("poll: network error status=%s" % status)
    raise QRExpired("poll attempts exhausted")


def wait_scan(http_get, qr, trust_enabled=False):
    """Step 2: wait for the phone scan. Returns the scan event dict."""
    timeout = qr["qr_timeout"] or 90
    _, payload = _poll(http_get, qr["chk_wait_scan"], timeout,
                       qr["qr_retry"])
    code = payload.get("error_code")
    if code == ERR_OK:
        event = protocol.parse_scan_event(payload.get("data") or {})
        if event["enc_link_data"] or event["enc_link_hmac"]:
            if not trust_enabled:
                raise TrustFlowRequired(
                    "scan event carries trust link data; new-format flow "
                    "is not implemented in phase 1")
            raise TrustFlowRequired("trust link data verification (WASM) "
                                    "is not implemented in phase 1")
        return event
    if code == ERR_QR2_RENEW:
        if trust_enabled:
            raise TrustFlowRequired("QR2 renew (multi-layer trust flow)")
        # Old-format defensive path: the confirm poll is authoritative.
        return {"avatar": "", "display_name": "",
                "enc_link_data": "", "enc_link_hmac": ""}
    if code == ERR_QR2_RELINK:
        raise LoginError("QR2 relink error (-21): clear link history "
                         "and fetch a new QR")
    if code == ERR_USER_REJECTED:
        raise UserRejected("user rejected the login on the phone (18010)")
    raise LoginError("wait_scan: error_code=%s %s" % (
        code, payload.get("error_message", "")))


def wait_confirm(http_get, qr):
    """Step 3: wait for the phone confirmation. Returns session grant."""
    timeout = qr["qr_timeout"] or 90
    _, payload = _poll(http_get, qr["chk_wait_cfirm"], timeout,
                       qr["qr_retry"])
    code = payload.get("error_code")
    if code == ERR_OK:
        grant = protocol.parse_confirm(payload.get("data") or {})
        if grant["uid"] and grant["dkey"]:
            if not grant["zpw_sek"]:
                # A grant without the session key would produce a
                # cookieless getLoginInfo and a cryptic server 102.
                # Fail here, naming the missing field, instead.
                raise LoginError(
                    "confirm: success payload without zpw_sek "
                    "(session key missing from grant)")
            return grant
        raise LoginError("confirm: success payload without uid/dkey")
    if code == ERR_USER_REJECTED:
        raise UserRejected("user rejected the login on the phone (18010)")
    raise LoginError("wait_confirm: error_code=%s %s" % (
        code, payload.get("error_message", "")))


def logininfo_query(device_id, computer_name, param_cipher_key=None,
                    language="vi"):
    """(query, enk) for getLoginInfo, mirroring the PC client: the
    login envelope (imei/computer_name/language/ts + type/
    client_version/signkey, encrypted when a param cipher key is
    configured) with api name "getlogininfo". The session itself is
    authenticated by the zpw_sek cookie, which the caller's transport
    attaches — never by a query parameter."""
    params = protocol.logininfo_params(device_id, computer_name,
                                       language=language)
    return _envelope(params, "getlogininfo", param_cipher_key, device_id)


def decode_response(payload, enk):
    """Decode a login-API response body (plain dict, or AES blob when
    the request went out encrypted)."""
    return _decode_payload(payload, enk)
