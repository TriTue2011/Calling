"""Provider tich hop transport UDP 4200 + P2P (agent B, giai doan 2
pha 2): `MediaEndpoints.for_call` that thay placeholder chuoi rong,
noi vao `Udp4200Transport` that (agent A) + `PcMediaEngine`
(`pc_media.py`).

Quy tac test (mock offline, KHONG goi that):
  * Thieu tham so bat buoc (call_id / callee_id / relays / token /
    session / local_session) hoac dia chi rong -> loi ro
    neu TEN tham so (`MissingTransportParam`), KHONG bao gio tra
    dia chi "" va KHONG gui 11301 rong. `srtp_key` KHONG con bat
    buoc cho signaling (live 2026-11-06: response 11300 that
    khong co srtpKey) — thieu khoa thi 11301 VAN gui, chi bao
    srtp "not-wired" va media khong chay (send_pcm doi hook).
  * Du tham so + khoa gia + hook identity (CHI DUNG CHO TEST — khong
    phai SRTP that) -> delivered: transport start + `for_call` tra
    dia chi "IP:port" + session + codec.
  * `FakeTransport` o day mo phong dung interface that cua A
    (`start/stop/send_pcm/set_pcm_callback/status`,
    `selected_relay`, `state`); no KHONG phai la transport that.

Chay: python3 tests/test_media_provider.py
"""

import base64
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from zalo_pc_app import media_endpoints  # noqa: E402
from zalo_pc_app import pc_media  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import udp_transport  # noqa: E402
from zalo_pc_app.media_endpoints import MissingTransportParam  # noqa: E402
from zalo_pc_app.udp_transport import RelayServer  # noqa: E402

CALL_ID = 1762345678  # epoch seconds — fits uint32, like the real client
# Token gia 115 byte (xac dinh, khong phai gia tri that): base64url
# 154 ky tu, giong dinh dang tren day.
FAKE_TOKEN = base64.urlsafe_b64encode(
    bytes((i * 7 + 3) % 256 for i in range(115))).rstrip(b"=").decode()
assert len(FAKE_TOKEN) == 154, len(FAKE_TOKEN)
FAKE_SESSION = "sess-test-123"
FAKE_LOCAL_SESSION = 0x01020304  # gia tri tong hop cho test, khong phai
# SSRC that cua thiet bi nao (KHONG dung 0x15cbea3f trong ban bat).
FAKE_RELAYS = [RelayServer("127.0.0.1", 4200, "127.0.0.1", 4201)]
FAKE_SRTP_KEY = "fake-srtp-key-test-only"


class FakeTransport:
    """Mo phong dung interface `Udp4200Transport` cua A (in-memory):
    start() chon relay dau tien dong bo (nhu type-02 dau tien ve);
    send_pcm() chay dung duong hook cua A: encode -> RTP header
    20B (seq/ts do transport quan) -> protect; deliver_inbound()
    mo phong duong nhan: unprotect -> parse RTP -> decode ->
    pcm callback."""

    def __init__(self, config):
        self.config = config
        self.selected_relay = None
        self.relay_session = b"\x01\x02\x03\x04"
        self.state = "idle"
        self.started = False
        self.stopped = False
        self.sent = []
        self._pcm_callback = None
        self._seq = 0
        self._timestamp = 0
        # Mirror of the real transport's first-media hook
        # (2026-11-08): fired once from deliver_inbound.
        self.on_first_media = None
        self._first_media_seen = False

    def start(self):
        self.started = True
        self.state = "handshaking"
        if self.config.relays:
            self.selected_relay = self.config.relays[0]
            self.state = "connected"
        return self

    def stop(self):
        self.stopped = True
        self.state = "stopped"
        return self

    def set_pcm_callback(self, fn):
        self._pcm_callback = fn

    def send_pcm(self, pcm):
        if len(pcm) != udp_transport.FRAME_BYTES:
            raise ValueError("send_pcm needs one %d-byte frame, got %d"
                             % (udp_transport.FRAME_BYTES, len(pcm)))
        if self.config.protect_rtp is None:
            raise MissingTransportParam(
                "protect_rtp: missing (SRTP hook is required to send "
                "media; inject it via TransportConfig)")
        if self.selected_relay is None:
            raise RuntimeError("no relay selected yet")
        encode = self.config.encode_frame or (lambda b: b)
        payload = encode(pcm)
        self._seq = (self._seq + 1) & 0xFFFF
        self._timestamp = (self._timestamp + 320) & 0xFFFFFFFF
        rtp = udp_transport.build_rtp(
            self._seq, self._timestamp, self.config.local_ssrc, payload)
        self.sent.append(self.config.protect_rtp(rtp))

    def deliver_inbound(self, rtp_packet):
        """Dua mot goi RTP (da protect) vao nhu transport that nhan
        duoc tu relay: unprotect -> parse -> decode -> callback.
        Giong transport that (_on_media), goi RTP den DAU TIEN goi
        on_first_media TRUOC khi kiem tra unprotect — viec nhan
        duoc goi chung minh ben kia da tra loi ngay ca khi SRTP
        chua co khoa va goi se bi drop."""
        hook = getattr(self, "on_first_media", None)
        if not getattr(self, "_first_media_seen", False):
            self._first_media_seen = True
            if hook is not None:
                hook()
        if self.config.unprotect_rtp is None:
            raise MissingTransportParam("unprotect_rtp: missing")
        plain = self.config.unprotect_rtp(rtp_packet)
        parsed = udp_transport.parse_rtp(plain)
        decode = self.config.decode_frame or (lambda b: b)
        pcm = decode(parsed["payload"])
        if self._pcm_callback is not None:
            self._pcm_callback(pcm)

    def status(self):
        return {"state": self.state,
                "selected_relay": (
                    self.selected_relay.as_dict()
                    if self.selected_relay else None),
                "sent": len(self.sent)}


class NeverSelectsTransport(FakeTransport):
    """Fake khong bao gio chon relay (mo phong khong co type-02)."""

    def start(self):
        self.started = True
        self.state = "handshaking"
        return self


def _provider(**over):
    kw = {"transport_factory": lambda cfg: FakeTransport(cfg)}
    kw.update(over)
    return media_endpoints.MediaEndpoints(**kw)


def _good_kwargs(**over):
    kw = {"call_id": CALL_ID, "callee_id": "20001",
          "relays": FAKE_RELAYS, "token": FAKE_TOKEN,
          "session": FAKE_SESSION,
          "local_session": FAKE_LOCAL_SESSION,
          "srtp_key": FAKE_SRTP_KEY,
          # Hook identity CHI DUNG CHO TEST (khong phai SRTP that).
          "protect_rtp": lambda b: b, "unprotect_rtp": lambda b: b}
    kw.update(over)
    return kw


def _assert_missing(fn, param_name):
    try:
        fn()
    except MissingTransportParam as exc:
        assert param_name in str(exc), (param_name, str(exc))
        return
    raise AssertionError(
        "expected MissingTransportParam naming %r" % param_name)


# ------------------------------------------------------------------ provider

def test_missing_call_id():
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        call_id=None)), "call_id")


def test_missing_callee_id():
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        callee_id="")), "callee_id")


def test_missing_relays():
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        relays=[])), "relays")
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        relays=None, servers=None)), "relays")


def test_missing_token():
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        token=None)), "token")


def test_token_wrong_length():
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        token=b"short")), "token")


def test_missing_session():
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        session="")), "session")


def test_missing_local_session():
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        local_session=None)), "local_session")


def test_missing_srtp_key():
    """Khong co srtp_key KHONG con chan signaling (doi hanh vi
    2026-11-06): response 11300 that khong co srtpKey, nen
    for_call VAN tra endpoint de 11301 duoc gui — nhung bao
    srtp "not-wired", khong co hook, va send_pcm van tu choi
    (can protect_rtp). Media khong chay cho den khi tim ra
    nguon khoa that; khong phat minh khoa."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        srtp_key=None, protect_rtp=None, unprotect_rtp=None,
        call_id=CALL_ID + 6))
    assert out["rtp_address"] == "127.0.0.1:4200", out
    assert out["srtp"] == "not-wired", out
    assert provider.active_record(CALL_ID + 6)["srtp_key"] is None
    try:
        out["transport"].send_pcm(b"\x00" * udp_transport.FRAME_BYTES)
    except MissingTransportParam as exc:
        assert "protect_rtp" in str(exc), str(exc)
        provider.stop_all()
        return
    raise AssertionError("expected MissingTransportParam (protect_rtp)")


def test_empty_relay_address_rejected():
    """Dia chi rong / cong 0 khong bao gio thanh endpoint: loi neu
    ten tham so (relays), khong tra chuoi rong."""
    bad = [{"rtp_ip": "", "rtp_port": 4200,
            "rtcp_ip": "127.0.0.1", "rtcp_port": 4201}]
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        relays=bad)), "relays")
    bad_port = [RelayServer("127.0.0.1", 0, "127.0.0.1", 4201)]
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        relays=bad_port)), "relays")


def test_valid_allocation_delivered():
    """Du tham so + khoa gia + hook identity -> delivered: transport
    start, for_call tra dia chi "IP:port" + session + codec."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs())
    assert out["rtp_address"] == "127.0.0.1:4200", out
    assert out["rtcp_address"] == "127.0.0.1:4201", out
    assert out["rtp_address"] != "" and out["rtcp_address"] != "", out
    assert out["session"] == FAKE_SESSION, out
    assert out["codec"] == media_endpoints.DEFAULT_ZALO_AUDIO_CODEC, \
        out  # default: chuoi JSON list Opus cua zca-js (khong "opus")
    assert out["call_id"] == CALL_ID, out
    assert out["transport"].started is True, out
    assert out["transport"].state == "connected", out
    assert out["transport"].status()["state"] == "connected", out
    assert provider.active_record(CALL_ID) is not None
    provider.stop_all()


def test_servers_string_pairing():
    """Chuoi servers dang JSON "IP:port" xen ke (parser cua A):
    cap (rtp, rtcp) thanh mot relay; for_call tra dung cap do."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        relays=None, servers="10.0.0.1:4200,10.0.0.1:4201",
        call_id=CALL_ID + 1))
    assert out["rtp_address"] == "10.0.0.1:4200", out
    assert out["rtcp_address"] == "10.0.0.1:4201", out
    provider.stop_all()


def test_selection_timeout_stops_transport():
    """Khong co type-02 (khong relay nao tra loi) -> het timeout thi
    loi ro + transport da stop, khong tra dia chi."""
    provider = media_endpoints.MediaEndpoints(
        transport_factory=lambda cfg: NeverSelectsTransport(cfg))
    try:
        provider.for_call(**_good_kwargs(selection_timeout=0.2))
    except RuntimeError as exc:
        assert "no relay selected" in str(exc), str(exc)
        return
    raise AssertionError("expected RuntimeError on selection timeout")


def test_stop_call():
    provider = _provider()
    out = provider.for_call(**_good_kwargs())
    transport = out["transport"]
    assert provider.stop_call(CALL_ID) is True
    assert transport.stopped is True
    assert transport.state == "stopped"
    assert provider.active_record(CALL_ID) is None
    assert provider.stop_call(CALL_ID) is False


def test_allocation_from_requestcall_data():
    """Lay dung vat lieu tu response 11300: servers/sessId/srtpKey/
    srtpMode — khong phat minh gia tri nao. g711 KHONG con quyet
    dinh codec signaling (zca-js: g711 mo ta codec media, khong
    phai chuoi codec trong 11301; xem test_codec_zca_js.py)."""
    data = {"zrtc_config": {
        "servers": "10.0.0.1:4200,10.0.0.1:4201",
        "sessId": "sess-xyz", "srtpKey": "k1", "srtpMode": 2,
        "g711": 1, "token": FAKE_TOKEN}}
    alloc = media_endpoints.allocation_from_requestcall_data(data)
    assert alloc["servers"] == "10.0.0.1:4200,10.0.0.1:4201", alloc
    assert alloc["session"] == "sess-xyz", alloc
    assert alloc["srtp_key"] == "k1", alloc
    assert alloc["srtp_mode"] == 2, alloc
    assert "codec" not in alloc, alloc  # g711=1 khong dat "pcmu" nua
    provider = _provider()
    out = provider.for_call(
        call_id=CALL_ID + 2, callee_id="20001",
        local_session=FAKE_LOCAL_SESSION, requestcall_data=data,
        protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
    assert out["codec"] == media_endpoints.DEFAULT_ZALO_AUDIO_CODEC, out
    assert out["session"] == "sess-xyz", out
    # srtpMode=2 from 11300 is kept inside the minimal
    # engine-default extendData (2026-11-08: 11301 always sends
    # extendData, never just {"srtpMode": ...}); the relay list
    # here is one server (10.0.0.1:4200/4201), so numServers=1
    # and serverAddr carries its RTP address.
    assert json.loads(out["extend_data"]) == \
        _expected_minimal_extend_data(
            srtp_mode=2, server_addr=["10.0.0.1:4200"]), out
    provider.stop_all()


def test_extend_data_unknown_keys_dropped():
    """extendData chi giu 23 key da biet (parser cua A); key la
    bi loai, khong bao gio gui key khong co trong schema."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        extend_data={"srtpMode": 2, "bogus_key": 1},
        call_id=CALL_ID + 3))
    assert out["extend_data"] == '{"srtpMode":2}', out
    provider.stop_all()


def _expected_minimal_extend_data(srtp_mode=0, is_video=False,
                                  num_servers=1, server_addr=None):
    """Engine-default extendData (disassembly): the minimal dict
    for_call builds when the 11300 response carries no extendData.
    Values are the engine's reset/parse-fail defaults
    (_parseExtendData 0x8d9fbb: packetMode=2, srtpMode=0, srtcp=0,
    sP2P=0, gccMode=0, gcc bytes=0, fecTP=0, maxFT=60) plus
    callType as a 0/1 audio/video flag (0 = voice, 1 = video)
    and platform=3 (the 11300 request-param struct default,
    parser 0x71f670 init [+0x04]=3 — the only numeric platform
    evidence in the disassembly; all extendData keys are optional
    for the peer parser, so a wrong platform value cannot block
    the call, it only differs from the real client's value if
    the real value is not 3).
    callType is NOT the typeRequest enum (1/3/5/6): the group
    builder (12434, VA 0x717450) maps the makeCall type byte
    5 (group audio) -> callType 0 and 6 (group video) ->
    callType 1, i.e. callType is 0 for audio, 1 for video.
    The 00db2b9 fix wrongly put the 1-1/group enum (1/5) here,
    which made the server treat voice calls as video calls
    (live 2026-11-08: BenBap's phone showed an incoming VIDEO
    call).
    2026-11-08 (buoc 2): du 24 key — 23 key cua serializer
    0x8e1183 + callType. Cac key moi so voi ban 13 key:
    video (object, codec "" cho thoai — khong co video codec),
    newZrtc/tpType/spTcp/select2side/supportCallBusy = 0
    (default cua parser; tpType/spTcp = 0 vi transport la UDP),
    supportHevcDecode = 0 (app khong giai ma HEVC — khong co
    video), extraInfo {type: 0, id: 0} (gia tri that chua biet,
    0/0 = default cua parser), serverResult = [] (dang phan tu
    chua chung minh duoc), numServers = so relay tu 11300,
    serverAddr = dia chi RTP "IP:port" cua cac relay tu 11300
    (suy luan tot nhat tu disasm §3.1.2: phan tu duoc trich ra
    thanh chuoi roi parse dang "IP:port"; parser cua peer BO QUA
    vong lap nay o duong 1-1 ([edi+0x5d]==0) nen gia tri chi co
    y nghia neu may chu tu kiem tra)."""
    if server_addr is None:
        server_addr = ["127.0.0.1:4200"]
    return {"p2p": "", "callType": 1 if is_video else 0,
            "video": {"codec": ""},
            "newZrtc": 0, "platform": 3,
            "packetMode": 2, "gccMode": 0, "srtpMode": srtp_mode,
            "sP2P": 0, "srtcp": 0, "gccAudio": 0, "gccSVLR": 0,
            "tpType": 0, "spTcp": 0, "gccEarlyCall": 0, "maxFT": 60,
            "extraInfo": {"type": 0, "id": 0},
            "supportCallBusy": 0, "supportHevcDecode": 0,
            "serverResult": [], "numServers": num_servers,
            "select2side": 0, "serverAddr": server_addr,
            "fecTP": 0}


def test_extend_data_built_when_11300_has_none():
    """11301 LUON gui extendData + subCommand=3 (2026-11-08):
    response 11300 that khong co key extendData (va khong co
    srtpMode trong zrtc_config) — truoc day for_call tra
    extend_data=None nen 11301 chi co 6/7 field, may chu co the
    coi la request khong co media config nen khong do chuong
    (5 cuoc lien tiep, step2_status=0, ring_timeout 30s).
    Client that LUON gui du 7/7 field (builder 416 0x72eed0 chen
    vo dieu kien; extendData do serializer 0x8e1183 build tu
    trang thai engine). for_call gio dung extendData toi thieu
    tu default cua engine, va vc_request them extendData +
    subCommand=3 khi no non-empty."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(call_id=CALL_ID + 5))
    assert out["extend_data"] is not None, out
    got = json.loads(out["extend_data"])
    assert got == _expected_minimal_extend_data(), got
    body = protocol.vc_request("20001", "127.0.0.1:4201",
                               "127.0.0.1:4200", "opus", "sess",
                               CALL_ID + 5, "dev-1",
                               out["extend_data"])
    assert body["extendData"] == out["extend_data"], body
    assert body["subCommand"] == 3, body
    provider.stop_all()


def test_extend_data_minimal_keeps_given_srtp_mode():
    """srtp_mode tu 11300 (vd 2) thang trong extendData toi
    thieu — khong roi ve 0, khong mat cac key default khac."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        srtp_mode=2, call_id=CALL_ID + 6))
    got = json.loads(out["extend_data"])
    assert got == _expected_minimal_extend_data(srtp_mode=2), got
    provider.stop_all()


def test_extend_data_minimal_group_audio_call_type_is_zero():
    """Goi nhom THOAI (call_type=5) dung callType=0 trong
    extendData toi thieu — callType la co 0/1 thoai/video,
    khong phai enum typeRequest 1/3/5/6 (xem
    _expected_minimal_extend_data)."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        call_type="group", call_id=CALL_ID + 7))
    got = json.loads(out["extend_data"])
    assert got == _expected_minimal_extend_data(), got
    provider.stop_all()


def test_extend_data_voice_call_type_is_zero():
    """Goi 1-1 THOAI dung callType=0 trong extendData toi
    thieu — live 2026-11-08: callType=1 (sai, tu 00db2b9)
    khien may BenBap hien «Cuoc goi video den» thay vi
    cuoc goi thoai."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(call_id=CALL_ID + 8))
    got = json.loads(out["extend_data"])
    assert got["callType"] == 0, got
    assert got == _expected_minimal_extend_data(), got
    provider.stop_all()


def test_extend_data_video_call_type_is_one():
    """Duong video cho TUONG LAI (user muon co ca video call):
    for_call(is_video=True) dung callType=1 trong extendData
    toi thieu. Video chua duoc lam (server van chi goi thoai,
    typeRequest 1/5) — test nay chi chung minh co video da
    duoc noi san qua flag is_video."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        is_video=True, call_id=CALL_ID + 9))
    got = json.loads(out["extend_data"])
    assert got == _expected_minimal_extend_data(is_video=True), got
    provider.stop_all()


# ------------------------------------------------------------------ step 1
# (2026-11-08): rtpIP/rtcpIP trong response 11300

def _requestcall_with_rtpip(rtp_ip, rtcp_ip, relays=None):
    """Response 11300 gia (servers + sessId + fromId/toId +
    rtpIP/rtcpIP). Dia chi TEST-NET, khong phai gia tri that."""
    if relays is None:
        relays = [{"rtpaddr": "127.0.0.1:4200",
                   "rtcpaddr": "127.0.0.1:4201"}]
    return {"servers": relays, "sessId": FAKE_TOKEN,
            "fromId": FAKE_LOCAL_SESSION, "toId": 0x55667788,
            "rtpIP": rtp_ip, "rtcpIP": rtcp_ip}


def test_allocation_extracts_rtpip_rtcpip():
    """allocation lay rtpIP/rtcpIP tu 11300 (top-level) — D8:
    truoc day bo qua hai key nay, khong log, khong doi chieu
    voi relay da chon."""
    alloc = media_endpoints.allocation_from_requestcall_data(
        _requestcall_with_rtpip("203.0.113.9:4200",
                                "203.0.113.9:4201"))
    assert alloc["rtp_ip"] == "203.0.113.9:4200", alloc
    assert alloc["rtcp_ip"] == "203.0.113.9:4201", alloc
    # Cung lay duoc tu params (parser request-param cua engine
    # doc params.rtpIP/params.rtcpIP — disasm-relay-acquisition
    # A.2).
    alloc2 = media_endpoints.allocation_from_requestcall_data(
        {"params": {"rtpIP": "198.51.100.7:4200",
                    "rtcpIP": "198.51.100.7:4201"}})
    assert alloc2["rtp_ip"] == "198.51.100.7:4200", alloc2
    assert alloc2["rtcp_ip"] == "198.51.100.7:4201", alloc2
    # Khong co key -> khong co gia tri (khong phat minh).
    assert "rtp_ip" not in media_endpoints.\
        allocation_from_requestcall_data({"servers": []})


def test_describe_requestcall_shape_includes_rtpip():
    """Shape cua 11300 (log step1 + data_shape) ghi rtpIP/rtcpIP
    — CHI DANG (do dai chuoi), khong bao gio gia tri: data_shape
    tra ve API khong duoc chua gia tri nao (xem
    test_real_11300_shape_2026_11_06_delivered_e2e). Gia tri that
    nam o dong log step1 (server.py append tu allocation) va o
    diag /api/calls (rtp_ip/rtcp_ip)."""
    shape = media_endpoints.describe_requestcall_shape(
        _requestcall_with_rtpip("203.0.113.9:4200",
                                "203.0.113.9:4201"))
    assert "rtpIP: str[16 chars]" in shape, shape
    assert "rtcpIP: str[16 chars]" in shape, shape
    assert "203.0.113.9" not in shape, shape


def test_rtpip_used_when_different_from_selected():
    """rtpIP/rtcpIP KHAC relay da chon -> 11301 dung
    rtpIP/rtcpIP (gia dinh buoc 1: may chu chi dinh 1 relay cu
    the; neu app dung relay khac thi co the khong route duoc).
    Nguon dia chi duoc ghi ro trong rtp_source."""
    provider = _provider()
    out = provider.for_call(
        call_id=CALL_ID + 11, callee_id="20001",
        requestcall_data=_requestcall_with_rtpip(
            "203.0.113.9:4200", "203.0.113.9:4201"),
        protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
    assert out["rtp_address"] == "203.0.113.9:4200", out
    assert out["rtcp_address"] == "203.0.113.9:4201", out
    assert out["rtp_source"] == "rtpIP", out
    provider.stop_all()


def test_rtpip_matching_selected_uses_selected():
    """rtpIP/rtcpIP TRUNG relay da chon -> 11301 dung relay da
    chon, rtp_source="selected" (khong doi gi)."""
    provider = _provider()
    out = provider.for_call(
        call_id=CALL_ID + 12, callee_id="20001",
        requestcall_data=_requestcall_with_rtpip(
            "127.0.0.1:4200", "127.0.0.1:4201"),
        protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
    assert out["rtp_address"] == "127.0.0.1:4200", out
    assert out["rtcp_address"] == "127.0.0.1:4201", out
    assert out["rtp_source"] == "selected", out
    provider.stop_all()


def test_rtpip_bare_ip_pairs_with_selected_port():
    """rtpIP/rtcpIP dang IP tran (khong port) -> ghep voi port
    cua relay da chon cung phia (port la thuoc tinh cua dich
    vu relay, 4200 trong moi capture)."""
    provider = _provider()
    out = provider.for_call(
        call_id=CALL_ID + 13, callee_id="20001",
        requestcall_data=_requestcall_with_rtpip(
            "203.0.113.9", "203.0.113.9"),
        protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
    assert out["rtp_address"] == "203.0.113.9:4200", out
    assert out["rtcp_address"] == "203.0.113.9:4201", out
    assert out["rtp_source"] == "rtpIP", out
    provider.stop_all()


def test_rtpip_absent_uses_selected():
    """Khong co rtpIP/rtcpIP trong 11300 -> hanh vi cu: 11301
    dung relay da chon, rtp_source="selected"."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(call_id=CALL_ID + 14))
    assert out["rtp_address"] == "127.0.0.1:4200", out
    assert out["rtcp_address"] == "127.0.0.1:4201", out
    assert out["rtp_source"] == "selected", out
    provider.stop_all()


# ------------------------------------------------------------------ step 2
# (2026-11-08): extendData du key cua serializer 0x8e1183

def test_extend_data_complete_keys():
    """extendData toi thieu gio du 24 key (23 key cua serializer
    0x8e1183 + callType): video/extraInfo la OBJECT long nhau
    (khong phai key phang "video.codec"), serverAddr la list
    dia chi RTP cua relay, numServers = so relay."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(call_id=CALL_ID + 15))
    got = json.loads(out["extend_data"])
    assert got == _expected_minimal_extend_data(), got
    assert isinstance(got["video"], dict), got
    assert got["video"] == {"codec": ""}, got
    assert isinstance(got["extraInfo"], dict), got
    assert got["extraInfo"] == {"type": 0, "id": 0}, got
    assert got["serverAddr"] == ["127.0.0.1:4200"], got
    assert got["numServers"] == 1, got
    assert got["serverResult"] == [], got
    assert got["callType"] == 0, got
    assert got["platform"] == 3, got
    assert got["supportCallBusy"] == 0, got
    assert got["supportHevcDecode"] == 0, got
    provider.stop_all()


def test_extend_data_num_servers_counts_relays():
    """numServers + serverAddr theo dung so relay tu 11300 (2
    relay -> numServers=2, serverAddr co 2 dia chi RTP)."""
    provider = _provider()
    out = provider.for_call(
        call_id=CALL_ID + 16, callee_id="20001",
        relays=[RelayServer("127.0.0.1", 4200, "127.0.0.1", 4201),
                RelayServer("127.0.0.2", 4200, "127.0.0.2", 4201)],
        token=FAKE_TOKEN, session=FAKE_SESSION,
        local_session=FAKE_LOCAL_SESSION,
        protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
    got = json.loads(out["extend_data"])
    assert got == _expected_minimal_extend_data(
        num_servers=2,
        server_addr=["127.0.0.1:4200", "127.0.0.2:4200"]), got
    provider.stop_all()


def test_group_call_type():
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        call_type="group", call_id=CALL_ID + 4))
    assert out["transport"].config.call_type == 5, out
    provider.stop_all()


# ------------------------------------------------------------------ pc_media

def test_opus16k_roundtrip():
    """Opus 16 kHz that (libopus tren VM): 640B PCM câm -> encode ->
    decode -> 640B PCM. Khac voi Opus 48 kHz cua mobile."""
    codec = pc_media.Opus16kCodec()
    try:
        pcm = b"\x00" * pc_media.FRAME_BYTES
        packet = codec.encode(pcm)
        assert len(packet) > 0, packet
        back = codec.decode(packet)
        assert len(back) == pc_media.FRAME_BYTES, len(back)
    finally:
        codec.close()


def test_opus16k_wrong_frame_size():
    codec = pc_media.Opus16kCodec()
    try:
        try:
            codec.encode(b"\x00" * 100)
        except ValueError as exc:
            assert "640" in str(exc), str(exc)
            return
        raise AssertionError("expected ValueError on short frame")
    finally:
        codec.close()


def test_pc_media_engine_loopback():
    """Engine qua FakeTransport + Opus 16 kHz that + hook identity:
    send_pcm (PCM câm) -> transport "gui" 1 goi; dua goi RTP ve ->
    pcm_out_frames tra 1 khung 640B. RTP seq/timestamp do
    transport quan (khong dung MediaPacket mobile)."""
    codec = pc_media.Opus16kCodec()
    try:
        provider = _provider()
        out = provider.for_call(**_good_kwargs(
            call_id=CALL_ID + 5,
            encode_frame=codec.encode, decode_frame=codec.decode))
        transport = out["transport"]
        engine = pc_media.PcMediaEngine(transport)
        engine.attach({"call_id": CALL_ID + 5})
        engine.start()
        try:
            engine.send_pcm(b"\x00" * pc_media.FRAME_BYTES)
            assert len(transport.sent) == 1, len(transport.sent)
            # Dua chinh goi vua gui ve nhu goi downlink tu relay.
            transport.deliver_inbound(transport.sent[0])
            frame = engine.read_frame(timeout=2.0)
            assert frame is not None, "no PCM frame delivered"
            assert len(frame) == pc_media.FRAME_BYTES, len(frame)
            assert engine.status()["received_frames"] == 1
        finally:
            engine.stop()
        provider.stop_all()
    finally:
        codec.close()


# ------------------------------------------------------------------ real 11300
# Hinh dang servers THAT (live test 2026-11-05 22:58 +07, ban
# 72b91b8, cuoc goi toi "Dai ca"): response 11300 TRA VE relay
# nhung KHONG phai chuoi zrtc_config.servers — no la LIST cac
# dict co key rtcpaddr / rtpIPv6 (phan sau bi cat tren man hinh,
# co the con key khac). Code cu chi biet dict dang
# {rtp_ip, rtp_port, rtcp_ip, rtcp_port} nen bo qua het -> []
# -> "relays: empty" o buoc 11301 du relay co san. Cac test nay
# dung dung hinh dang do (chi ten key + cau truc, KHONG gia tri
# IP that nao) va chung minh buoc 11301 nhan duoc relay.

# Gia tri tong hop cho test (127.0.0.1 / dia chi TEST-NET, khong
# phai dia chi that tu anh chup).
REAL_SHAPE_SERVERS = [
    {"rtcpaddr": "127.0.0.1:4201", "rtpaddr": "127.0.0.1:4200",
     "rtpIPv6": "[2001:db8::1]:4200",
     "rtcpIPv6": "[2001:db8::1]:4201",
     "unknown_future_key": "ignored"},
    {"rtcpaddr": "127.0.0.2:4211", "rtpaddr": "127.0.0.2:4210"},
]


def test_real_11300_dict_shape_delivered():
    """List dict rtcpaddr/rtpIPv6 (hinh that) -> for_call tra dia
    chi cua relay IPv4 dau tien; key la duoc bo qua, khong loi."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        relays=REAL_SHAPE_SERVERS, call_id=CALL_ID + 10))
    assert out["rtp_address"] == "127.0.0.1:4200", out
    assert out["rtcp_address"] == "127.0.0.1:4201", out
    assert out["transport"].started is True, out
    provider.stop_all()


def test_real_11300_ipv6_only_dict():
    """Chi co dia chi IPv6 (dang bracketed) van thanh mot relay —
    khong ep phai co IPv4."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        relays=[{"rtpIPv6": "[2001:db8::9]:4200",
                 "rtcpIPv6": "[2001:db8::9]:4201"}],
        call_id=CALL_ID + 11))
    assert out["rtp_address"] == "[2001:db8::9]:4200", out
    assert out["rtcp_address"] == "[2001:db8::9]:4201", out
    provider.stop_all()


def test_real_11300_mixed_families():
    """RTP chi co IPv6 + RTCP chi co IPv4 -> mot relay hon hop
    (moi phia gui doc lap), khong doi ca hai cung family."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        relays=[{"rtpIPv6": "[2001:db8::5]:4200",
                 "rtcpaddr": "127.0.0.1:4201"}],
        call_id=CALL_ID + 12))
    assert out["rtp_address"] == "[2001:db8::5]:4200", out
    assert out["rtcp_address"] == "127.0.0.1:4201", out
    provider.stop_all()


def test_real_11300_separate_ip_port_keys():
    """Dia chi dang ip rieng + port rieng (rtpIP/rtpPort) cung
    ghep duoc mot relay."""
    provider = _provider()
    out = provider.for_call(**_good_kwargs(
        relays=[{"rtpIP": "127.0.0.1", "rtpPort": 4200,
                 "rtcpIP": "127.0.0.1", "rtcpPort": 4201}],
        call_id=CALL_ID + 13))
    assert out["rtp_address"] == "127.0.0.1:4200", out
    assert out["rtcp_address"] == "127.0.0.1:4201", out
    provider.stop_all()


def test_real_11300_incomplete_dict_still_missing():
    """Dict thieu mot phia (chi co rtcpaddr, khong co RTP) khong
    thanh relay: loi neu ro `relays`, khong tra dia chi nua voi."""
    _assert_missing(lambda: _provider().for_call(**_good_kwargs(
        relays=[{"rtcpaddr": "127.0.0.1:4201"}],
        call_id=CALL_ID + 14)), "relays")


def test_real_11300_error_names_shape_not_values():
    """Loi relays: empty khong bao gio in GIA TRI (IP/port) —
    chi in ten key + so luong, de chup man hinh loi van an toan."""
    try:
        _provider().for_call(**_good_kwargs(
            relays=[{"rtcpaddr": "127.0.0.1:4201"}],
            call_id=CALL_ID + 15))
    except MissingTransportParam as exc:
        msg = str(exc)
        assert "rtcpaddr" in msg, msg
        assert "127.0.0.1" not in msg, msg
        assert "4201" not in msg, msg
        return
    raise AssertionError("expected MissingTransportParam")


def test_allocation_real_11300_list_shape():
    """allocation_from_requestcall_data giu nguyen list dict
    servers (khong ep thanh chuoi), va for_call qua
    requestcall_data do giao dich duoc relay that."""
    data = {"servers": REAL_SHAPE_SERVERS, "sessId": "sess-real",
            "srtpKey": "k1", "srtpMode": 2, "token": FAKE_TOKEN}
    alloc = media_endpoints.allocation_from_requestcall_data(data)
    assert alloc["servers"] == REAL_SHAPE_SERVERS, alloc
    assert alloc["session"] == "sess-real", alloc
    provider = _provider()
    out = provider.for_call(
        call_id=CALL_ID + 16, callee_id="20001",
        local_session=FAKE_LOCAL_SESSION, requestcall_data=data,
        protect_rtp=lambda b: b, unprotect_rtp=lambda b: b)
    assert out["rtp_address"] == "127.0.0.1:4200", out
    assert out["rtcp_address"] == "127.0.0.1:4201", out
    assert out["session"] == "sess-real", out
    provider.stop_all()


def test_describe_requestcall_shape_names_only():
    """Shape summary chi ghi ten key + so luong, khong ghi gia
    tri nao (IP, khoa, token)."""
    shape = media_endpoints.describe_requestcall_shape(
        {"servers": REAL_SHAPE_SERVERS,
         "zrtc_config": {"srtpKey": "SECRET", "sessId": "sess-x"}})
    assert "servers" in shape and "srtpKey" in shape, shape
    assert "rtcpaddr" in shape and "rtpIPv6" in shape, shape
    assert "SECRET" not in shape and "sess-x" not in shape, shape
    assert "127.0.0.1" not in shape, shape


# ------------------------------------------------------------------ live 11300
# 2026-11-06 06:35 +07 (ban 9d87501, cuoc goi that): buoc 1 (11300)
# GUI OK, buoc 2 (11301) KHONG gui — loi moi "token: missing
# (need 115 raw bytes or a 154-char base64url string, most likely
# from response 11300)". Hinh 11300 THAT (CHI TEN KEY, khong gia
# tri): [changeZRTP, fec, fromId, id, msg, protocol, rtcpIP,
# rtpIP, servers, sessId, settings, showDebugInfo, status, toId,
# ts, video, zrtc_config]; servers la list[5] dict voi key
# [bonus, rtcpIPv6, rtcpaddr, rtpIPv6, rtpaddr, spTcp] (relay
# parser vong truoc van dung — khong con "relays: empty");
# zrtc_config KHONG co srtpKey / srtpNoSeq / srtpRTCP (gia thuyet
# cu "srtpKey la key cua zrtc_config" SAI voi response that).
# Token = sessId: 115 byte tho == 154 ky tu base64url — dung
# cap so trong thong bao loi, va la key duy nhat co the co dang
# do. Cac fixture duoi day TONG HOP (gia tri tu sinh, khong phai
# gia tri that bi bat): sessId 154 ky tu tu 115 byte xac dinh,
# dia chi loopback / TEST-NET.
SESSID_RAW_115 = bytes((i * 11 + 5) % 256 for i in range(115))
SESSID_154 = base64.urlsafe_b64encode(SESSID_RAW_115).rstrip(
    b"=").decode()
assert len(SESSID_154) == 154, len(SESSID_154)
REAL_11300_2026_11_06_SERVERS = [
    {"bonus": 0, "rtcpaddr": "127.0.0.1:4201",
     "rtpaddr": "127.0.0.1:4200",
     "rtcpIPv6": "[2001:db8::1]:4201",
     "rtpIPv6": "[2001:db8::1]:4200", "spTcp": 0},
    {"bonus": 0, "rtcpaddr": "192.0.2.2:4211",
     "rtpaddr": "192.0.2.2:4210",
     "rtcpIPv6": "[2001:db8::2]:4211",
     "rtpIPv6": "[2001:db8::2]:4210", "spTcp": 0},
    {"bonus": 0, "rtcpaddr": "192.0.2.3:4221",
     "rtpaddr": "192.0.2.3:4220",
     "rtcpIPv6": "[2001:db8::3]:4221",
     "rtpIPv6": "[2001:db8::3]:4220", "spTcp": 0},
    {"bonus": 0, "rtcpaddr": "192.0.2.4:4231",
     "rtpaddr": "192.0.2.4:4230",
     "rtcpIPv6": "[2001:db8::4]:4231",
     "rtpIPv6": "[2001:db8::4]:4230", "spTcp": 0},
    {"bonus": 0, "rtcpaddr": "192.0.2.5:4241",
     "rtpaddr": "192.0.2.5:4240",
     "rtcpIPv6": "[2001:db8::5]:4241",
     "rtpIPv6": "[2001:db8::5]:4240", "spTcp": 0},
]
# Toan bo key top-level that — KHONG co "token", KHONG co
# "srtpKey" (ca top-level lan trong zrtc_config).
REAL_11300_2026_11_06 = {
    "changeZRTP": 0, "fec": 0, "fromId": 10001,
    "id": "1-test", "msg": "", "protocol": 0,
    "rtcpIP": "127.0.0.1", "rtpIP": "127.0.0.1",
    "servers": REAL_11300_2026_11_06_SERVERS,
    "sessId": SESSID_154, "settings": {}, "showDebugInfo": 0,
    "status": 0, "toId": 20001, "ts": 1762745678,
    "video": 0, "zrtc_config": {"srtpMode": 2}}


def test_sessid_154_is_token():
    """sessId 154 ky tu base64url -> token = sessId; for_call qua
    requestcall_data that (khong token rieng, khong srtpKey) VAN
    tra endpoint: relay van parse dung, session = sessId, srtp
    "not-wired". Day la loi cu "token: missing" da duoc sua."""
    alloc = media_endpoints.allocation_from_requestcall_data(
        REAL_11300_2026_11_06)
    assert alloc["token"] == SESSID_154, alloc
    assert alloc["session"] == SESSID_154, alloc
    assert "srtp_key" not in alloc, alloc
    provider = _provider()
    out = provider.for_call(
        call_id=CALL_ID + 20, callee_id="20001",
        local_session=FAKE_LOCAL_SESSION,
        requestcall_data=REAL_11300_2026_11_06)
    assert out["rtp_address"] == "127.0.0.1:4200", out
    assert out["rtcp_address"] == "127.0.0.1:4201", out
    assert out["session"] == SESSID_154, out
    assert out["srtp"] == "not-wired", out
    assert out["transport"].config.token == SESSID_154.encode(), out
    assert len(out["transport"].config.token_raw) == 115, out
    # zrtc_config carries srtpMode=2 here: kept inside the minimal
    # engine-default extendData (2026-11-08), not alone. The
    # fixture's 11300 advertises 5 servers (each with v4+v6
    # addresses) — numServers counts ADVERTISED servers (5),
    # not the 10 family-split relays, and serverAddr carries
    # one RTP address per server, IPv4 preferred.
    assert json.loads(out["extend_data"]) == \
        _expected_minimal_extend_data(
            srtp_mode=2, num_servers=5,
            server_addr=["127.0.0.1:4200", "192.0.2.2:4210",
                         "192.0.2.3:4220", "192.0.2.4:4230",
                         "192.0.2.5:4240"]), out
    provider.stop_all()


def test_sessid_raw_115_bytes_is_token():
    """sessId dang 115 byte tho -> token = 115 byte do; session
    la dang base64url 154 ky tu cua no (khong phai str(bytes))."""
    data = dict(REAL_11300_2026_11_06)
    data["sessId"] = SESSID_RAW_115
    alloc = media_endpoints.allocation_from_requestcall_data(data)
    assert alloc["token"] == SESSID_RAW_115, alloc
    assert alloc["session"] == SESSID_154, alloc
    provider = _provider()
    out = provider.for_call(
        call_id=CALL_ID + 21, callee_id="20001",
        local_session=FAKE_LOCAL_SESSION, requestcall_data=data)
    assert out["session"] == SESSID_154, out
    assert out["transport"].config.token == SESSID_154.encode(), out
    provider.stop_all()


def test_sessid_wrong_shape_is_not_token():
    """sessId sai dang (chuoi ngan "sess-real") KHONG duoc ep
    thanh token: allocation khong co token, for_call loi neu ro
    `token` + ghi sessId co mat nhung sai dang (ke ca do dai
    trong shape note) — khong doan, khong che gia tri."""
    data = dict(REAL_11300_2026_11_06)
    data["sessId"] = "sess-real"
    alloc = media_endpoints.allocation_from_requestcall_data(data)
    assert "token" not in alloc, alloc
    assert alloc["session"] == "sess-real", alloc
    shape = media_endpoints.describe_requestcall_shape(data)
    assert "sessId: str[9 chars]" in shape, shape
    assert "sess-real" not in shape, shape
    try:
        _provider().for_call(
            call_id=CALL_ID + 22, callee_id="20001",
            local_session=FAKE_LOCAL_SESSION, requestcall_data=data)
    except MissingTransportParam as exc:
        msg = str(exc)
        assert "token" in msg, msg
        assert "sessId was present" in msg, msg
        assert "sess-real" not in msg, msg
        return
    raise AssertionError("expected MissingTransportParam (token)")


def test_explicit_token_wins_over_sessid():
    """Neu response co ca `token` rieng lan `sessId` thi `token`
    rieng thang (tuong thich nguoc voi mock cu)."""
    data = dict(REAL_11300_2026_11_06)
    data["token"] = FAKE_TOKEN
    alloc = media_endpoints.allocation_from_requestcall_data(data)
    assert alloc["token"] == FAKE_TOKEN, alloc
    assert alloc["session"] == SESSID_154, alloc


def test_token_absent_without_sessid():
    """Khong co `token` lan khong co `sessId` -> loi neu ro
    `token` (khong ghi "sessId was present" vi that su khong
    co) — day la thong bao loi ma test that 2026-11-06 da thay."""
    data = {"servers": REAL_11300_2026_11_06_SERVERS}
    try:
        _provider().for_call(
            call_id=CALL_ID + 23, callee_id="20001",
            local_session=FAKE_LOCAL_SESSION, requestcall_data=data)
    except MissingTransportParam as exc:
        msg = str(exc)
        assert "token" in msg, msg
        assert "sessId was present" not in msg, msg
        return
    raise AssertionError("expected MissingTransportParam (token)")


def test_srtp_key_wrong_length():
    """Khoa SRTP khong dung do dai suite -> ValueError neu ro do
    dai can (khong cat/xen, khong doan dinh dang)."""
    try:
        pc_media.make_srtp_hooks(b"short")
    except ValueError as exc:
        assert "30" in str(exc), str(exc)
        return
    raise AssertionError("expected ValueError on short SRTP key")


def test_srtp_hooks_unavailable_without_lib():
    """Trong image stdlib-only (khong co zalo_call.srtp) thi
    make_srtp_hooks loi ro SrtpUnavailable thay vi gia vo co SRTP.
    Bo qua neu moi truong nay co san zalo_call.srtp."""
    try:
        _spec = importlib.util.find_spec("zalo_call.srtp")
    except (ImportError, ValueError):
        # find_spec raises when the parent package does not exist.
        _spec = None
    if _spec is not None:
        print("SKIP test_srtp_hooks_unavailable_without_lib: "
              "zalo_call.srtp is installed here")
        return
    try:
        pc_media.make_srtp_hooks(b"\x00" * 30)
    except pc_media.SrtpUnavailable as exc:
        assert "libsrtp2" in str(exc) or "zalo_call" in str(exc), \
            str(exc)
        return
    raise AssertionError("expected SrtpUnavailable")


def test_wait_selected_error_includes_diagnostics():
    # The 07/11 live error named only the missing type-02, so the
    # failure could not be diagnosed from the message. The error
    # must now carry the transport counters + a hint, and must
    # never carry a relay address.
    class _FakeTransport:
        selected_relay = None
        state = "handshaking"
        counters = {"probe_tx": 0, "setup_init_tx": 0, "send_errors": 14,
                    "type02_rx": 0, "unknown_rx": 0, "recv_errors": 0,
                    "ping_reply_rx": 0}
        _last_error = "send to relay #0 failed: boom"
        config = None

    try:
        media_endpoints.MediaEndpoints._wait_selected(
            _FakeTransport(), 0.01)
    except RuntimeError as exc:
        msg = str(exc)
        assert "no relay selected" in msg
        assert "probe_tx=0" in msg and "send_errors=14" in msg
        assert "type02_rx=0" in msg and "unknown_rx=0" in msg
        assert "last_error=send to relay #0 failed: boom" in msg
        assert "hint: no probe/setup datagram left the socket" in msg
    else:
        raise AssertionError("no timeout raised")


def test_wait_selected_error_includes_unknown_sample():
    # Live 07/11 shape: replies arrived but were not recognized
    # (unknown_rx=8, type02_rx=0). The error must name the latest
    # unknown packet (length + head byte + hex prefix) so the
    # next live test can be read from the message alone — and
    # must never carry an address.
    class _FakeTransport:
        selected_relay = None
        state = "handshaking"
        counters = {"probe_tx": 160, "setup_init_tx": 8, "send_errors": 0,
                    "type02_rx": 0, "unknown_rx": 8, "recv_errors": 0,
                    "ping_reply_rx": 160}
        _last_error = None
        config = None

        def unknown_samples(self):
            return [{"len": 47, "head": 0x02,
                     "hex": "027e0000000000000000000000000000"}]

    try:
        media_endpoints.MediaEndpoints._wait_selected(
            _FakeTransport(), 0.01)
    except RuntimeError as exc:
        msg = str(exc)
        assert "unknown_rx=8" in msg and "type02_rx=0" in msg
        assert "hint: unrecognized packets arrived" in msg
        assert "last unknown packet: len=47 head=0x02" in msg
        assert "hex=027e0000000000000000000000000000" in msg
        assert "203.0.113" not in msg
    else:
        raise AssertionError("no timeout raised")


def test_wait_selected_error_sent_but_silent_hint():
    # Probes/setups left the socket and nothing came back: the
    # hint must say so, and the relay families must be listed
    # (shape only — no addresses).
    class _FakeConfig:
        relays = [RelayServer("203.0.113.1", 4200, "203.0.113.1", 4201),
                  RelayServer("2001:db8::1", 4200, "2001:db8::2", 4201)]

    class _FakeTransport:
        selected_relay = None
        state = "handshaking"
        counters = {"probe_tx": 140, "setup_init_tx": 7, "send_errors": 0,
                    "type02_rx": 0, "unknown_rx": 0, "recv_errors": 0,
                    "ping_reply_rx": 0}
        _last_error = None
        config = _FakeConfig()

    try:
        media_endpoints.MediaEndpoints._wait_selected(
            _FakeTransport(), 0.01)
    except RuntimeError as exc:
        msg = str(exc)
        assert "probe_tx=140" in msg and "setup_init_tx=7" in msg
        assert "relays=2 (v4=1, v6=1)" in msg
        assert "203.0.113" not in msg and "2001:db8" not in msg
        assert "hint: probes/setups were sent but nothing came back" \
            in msg
    else:
        raise AssertionError("no timeout raised")


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
