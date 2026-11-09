"""Codec 11300/11301 theo dinh dang that cua engine (zca-js).

Bang chung moi (bao cao outbox/zca-js-tong-hop.md §4.4/§7.2, doc
truc tiep tu repo softtyos/zca-js v2.3.13):
  * `ZRTPPacketCodec.ts:279` — `DEFAULT_ZALO_AUDIO_CODEC` la chuoi
    JSON LIST, khong phai chu tran "opus":
    '[{"dynamicFptime":0,"frmPtime":20,"name":"opus/16000/1",
    "payload":112}]'
  * `ZaloRtcSession.startOutgoingCall` truyen dung chuoi list nay
    vao CA 11300 va 11301 (khong dung "[]" hay "opus").
  * `ZaloRtcSession.applyServerInfo` (dong 4505-4506): neu response
    11300 tra ve `codec` khac "[]" thi DUNG codec server tra ve
    cho 11301 (codec server thang).

Code cu gui gi:
  * 11300: "[]" (vc_requestcall fallback khi UI khong gui codec).
  * 11301: "opus" (suy luan tu zrtc_config.g711 — chinh code ghi
    la SUY LUAN, UNCONFIRMED) hoac "pcmu"/"pcma" khi g711=1/2.
  * g711 trong zrtc_config mo ta codec MEDIA (am thanh), khong
    phai chuoi codec signaling trong 11301 — zca-js khong bao gio
    doc g711 de chon codec signaling.

Cac test nay PHAI FAIL o code cu va PASS o code moi (do-truoc
xanh-sau). Khong goi that, khong dung tai khoan that.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from test_media_provider import (  # noqa: E402
    FAKE_LOCAL_SESSION, FAKE_RELAYS, FAKE_SESSION, FAKE_SRTP_KEY,
    FAKE_TOKEN, FakeTransport)
from zalo_pc_app import media_endpoints  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import signaling  # noqa: E402

CALL_ID = 1762345678  # epoch seconds — fits uint32, like the old UI sent

# Chuoi codec that — phai KHOP TU TU voi
# zca-js DEFAULT_ZALO_AUDIO_CODEC (JSON.stringify, khong khoang
# trang, dung thu tu key dynamicFptime/frmPtime/name/payload).
EXPECTED_CODEC = ('[{"dynamicFptime":0,"frmPtime":20,'
                  '"name":"opus/16000/1","payload":112}]')
# Codec server tra ve trong 11300 (dung de phan biet voi default):
# cung dang list nhung payload khac.
SERVER_CODEC = ('[{"dynamicFptime":0,"frmPtime":20,'
                '"name":"opus/16000/1","payload":111}]')


def _provider():
    return media_endpoints.MediaEndpoints(
        transport_factory=lambda cfg: FakeTransport(cfg),
        default_relays=FAKE_RELAYS, default_token=FAKE_TOKEN,
        default_session=FAKE_SESSION,
        default_local_session=FAKE_LOCAL_SESSION,
        default_srtp_key=FAKE_SRTP_KEY)


def _good_kwargs(**over):
    kw = {"call_id": CALL_ID, "callee_id": "20001",
          "local_session": FAKE_LOCAL_SESSION}
    kw.update(over)
    return kw


# ------------------------------------------------------------------ don vi

def test_default_codec_constant_is_zca_json_list():
    """Hang so codec mac dinh phai la chuoi JSON list Opus cua
    zca-js — khong phai "opus", khong phai "[]"."""
    assert media_endpoints.DEFAULT_ZALO_AUDIO_CODEC == EXPECTED_CODEC


def test_for_call_default_codec_is_zca_json_list():
    """Khong co codec o dau (UI / 11300 / default) -> for_call tra
    ve chuoi JSON list Opus, khong phai "opus" (UNCONFIRMED cu)."""
    provider = _provider()
    try:
        out = provider.for_call(**_good_kwargs())
        assert out["codec"] == EXPECTED_CODEC, out
    finally:
        provider.stop_all()


def test_server_codec_wins_apply_server_info():
    """Response 11300 tra ve `codec` khac "[]" -> alloc giu dung
    codec do, va for_call dung no cho 11301 (applyServerInfo:
    codec server thang)."""
    data = {"codec": SERVER_CODEC, "sessId": "sess-x",
            "servers": "10.0.0.1:4200,10.0.0.1:4201"}
    alloc = media_endpoints.allocation_from_requestcall_data(data)
    assert alloc["codec"] == SERVER_CODEC, alloc
    provider = _provider()
    try:
        out = provider.for_call(
            call_id=CALL_ID + 1, callee_id="20001",
            local_session=FAKE_LOCAL_SESSION, requestcall_data=data,
            protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
        assert out["codec"] == SERVER_CODEC, out
    finally:
        provider.stop_all()


def test_server_codec_empty_list_ignored():
    """Response 11300 tra ve `codec` = "[]" (khong co codec that)
    -> khong dung "[]", for_call roi ve chuoi JSON list mac dinh."""
    data = {"codec": "[]", "sessId": "sess-x",
            "servers": "10.0.0.1:4200,10.0.0.1:4201"}
    alloc = media_endpoints.allocation_from_requestcall_data(data)
    assert alloc.get("codec") in (None, "[]"), alloc
    provider = _provider()
    try:
        out = provider.for_call(
            call_id=CALL_ID + 2, callee_id="20001",
            local_session=FAKE_LOCAL_SESSION, requestcall_data=data,
            protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
        assert out["codec"] == EXPECTED_CODEC, out
    finally:
        provider.stop_all()


def test_g711_no_longer_drives_signaling_codec():
    """zrtc_config.g711=1 khong con quyet dinh codec signaling:
    alloc khong dat "pcmu" vao "codec" nua, va for_call tra ve
    chuoi JSON list mac dinh. (g711 mo ta codec media, khong
    phai chuoi codec trong 11301; zca-js khong doc g711.)"""
    data = {"zrtc_config": {
        "servers": "10.0.0.1:4200,10.0.0.1:4201",
        "sessId": "sess-xyz", "srtpKey": "k1", "srtpMode": 2,
        "g711": 1, "token": FAKE_TOKEN}}
    alloc = media_endpoints.allocation_from_requestcall_data(data)
    assert alloc.get("codec") != "pcmu", alloc
    provider = _provider()
    try:
        out = provider.for_call(
            call_id=CALL_ID + 3, callee_id="20001",
            local_session=FAKE_LOCAL_SESSION, requestcall_data=data,
            protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
        assert out["codec"] == EXPECTED_CODEC, out
    finally:
        provider.stop_all()


def test_explicit_codec_still_wins():
    """Codec UI gui len (explicit) van thang — de nguoi dung / test
    sau nay ép codec khac khi can (kha nang cu, khong mat)."""
    provider = _provider()
    try:
        out = provider.for_call(
            **_good_kwargs(call_id=CALL_ID + 4, codec="custom-list"))
        assert out["codec"] == "custom-list", out
    finally:
        provider.stop_all()


def test_vc_requestcall_docstring_names_real_codec_format():
    """Tai lieu cua vc_requestcall khong con ghi "chua biet dinh
    dang codec" — dinh dang that da co tu zca-js."""
    assert "opus/16000/1" in protocol.vc_requestcall.__doc__, \
        protocol.vc_requestcall.__doc__


# ------------------------------------------------------------------ e2e
# Drive the real app HTTP API (same harness shape as
# test_call_11301.py): QR login against the mock, then POST
# /api/call/request and check the WIRE codec the mock saw on
# BOTH steps (11300 + 11301) — the mock records it since this
# change (mock_server._record_voice_step keeps requestcall_codec
# / request_codec).

def _sig(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    t = app_server.make_transport("sek-test")
    return signaling.Signaling(t, "dev-1", TEST_SESSION_KEY)


def _start_app(mock):
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-codec-")
    os.environ["ZALO_PC_DATA_DIR"] = tmp
    os.environ["ZALO_PC_PORT"] = "0"
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    app_server.PARAM_CIPHER_KEY = "TEST_PARAM_KEY_32_CHARS_LONG_XXX"
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % port


def _api(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode()
                                 if body is not None else None)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _login(base):
    status, body = _api(base, "POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = _api(base, "GET", "/api/qr/status")
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def _fake_endpoints():
    return media_endpoints.MediaEndpoints(
        transport_factory=lambda cfg: FakeTransport(cfg),
        default_relays=FAKE_RELAYS, default_token=FAKE_TOKEN,
        default_session=FAKE_SESSION,
        default_local_session=FAKE_LOCAL_SESSION,
        default_srtp_key=FAKE_SRTP_KEY)


def test_wire_codec_both_steps_e2e():
    """Qua API that: UI khong gui codec -> 11300 gui chuoi JSON
    list Opus (khong phai "[]"), 11301 gui cung chuoi do (khong
    phai "opus"). Mock ghi lai codec tren day cua ca hai buoc;
    diag cua /api/calls cung ghi dung codec do."""
    mock = MockZalo().start()
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _fake_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001", "call_id": CALL_ID})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        eff_id = body["call_id"]
        state = mock.voice_call_state(eff_id)
        assert state["steps"] == ["requestcall", "request"], state
        assert state["delivered"] is True, state
        assert state["requestcall_codec"] == EXPECTED_CODEC, state
        assert state["request_codec"] == EXPECTED_CODEC, state
        status, body = _api(base, "GET", "/api/calls")
        by_id = {c["call_id"]: c for c in body["calls"]}
        assert by_id[str(eff_id)]["diag"]["codec"] == EXPECTED_CODEC, \
            body
        httpd.shutdown()
    finally:
        endpoints.stop_all()
        media_endpoints.ENDPOINTS = old_endpoints
        if httpd is not None:
            try:
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        mock.stop()


def test_wire_codec_server_codec_e2e():
    """Qua API that: response 11300 tra ve `codec` khac "[]" ->
    11301 gui dung codec server tra ve (applyServerInfo), trong
    khi 11300 van gui chuoi JSON list mac dinh."""
    mock = MockZalo().start()
    mock.requestcall_data = {
        "codec": SERVER_CODEC, "servers": FAKE_RELAYS and
        "10.0.0.1:4200,10.0.0.1:4201",
        "sessId": "sess-server-codec", "token": FAKE_TOKEN}
    httpd = None
    old_endpoints = media_endpoints.ENDPOINTS
    endpoints = _fake_endpoints()
    media_endpoints.ENDPOINTS = endpoints
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001",
                             "call_id": CALL_ID + 10})
        assert body["ok"] is True, body
        assert body["request_sent"] is True, body
        eff_id = body["call_id"]
        state = mock.voice_call_state(eff_id)
        assert state["requestcall_codec"] == EXPECTED_CODEC, state
        assert state["request_codec"] == SERVER_CODEC, state
        httpd.shutdown()
    finally:
        endpoints.stop_all()
        media_endpoints.ENDPOINTS = old_endpoints
        if httpd is not None:
            try:
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        mock.stop()


if __name__ == "__main__":
    failed = []
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_")]
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed.append(fn.__name__)
            print("FAIL", fn.__name__, exc)
    print("%d/%d tests passed" % (len(tests) - len(failed), len(tests)))
    raise SystemExit(1 if failed else 0)
