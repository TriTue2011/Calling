"""Cau noi am thanh cua custom zalo_call — chay NGOAI Home Assistant.

HA khong co san o moi truong test nen cac module `homeassistant.*` duoc thay
bang ban gia toi thieu; test chay THAT bridge_core.py va bridge.py (loa,
mic qua tien trinh ffmpeg gia, dung cuoc goi). Khong chung minh chay duoc
trong HA that — chi chung minh logic dieu phoi dung.
"""
import asyncio
import importlib.util
import os
import stat
import sys
import tempfile
import types

ROOT = os.path.join(os.path.dirname(__file__), "..", "custom_components",
                    "zalo_call")


def _load():
    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    class HomeAssistantError(Exception):
        pass

    holder = {"binary": None}
    mod("homeassistant")
    mod("homeassistant.components")
    cam = mod("homeassistant.components.camera")
    # bridge.py gan ten ham luc import, nen ban gia phai co san va tra ve gia
    # tri doi duoc qua holder["binary"].
    ff = mod("homeassistant.components.ffmpeg",
             get_ffmpeg_manager=lambda hass: types.SimpleNamespace(
                 binary=holder["binary"]))
    mod("homeassistant.config_entries", ConfigEntry=object)
    mod("homeassistant.core", HomeAssistant=object)
    mod("homeassistant.exceptions", HomeAssistantError=HomeAssistantError)
    sys.modules["homeassistant.components"].camera = cam
    holder["cam"], holder["ff"] = cam, ff

    pkg = types.ModuleType("zalo_call")
    pkg.__path__ = [ROOT]
    sys.modules["zalo_call"] = pkg
    for name in ("const", "api", "bridge_core", "bridge"):
        spec = importlib.util.spec_from_file_location(
            "zalo_call." + name, os.path.join(ROOT, name + ".py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules["zalo_call." + name] = m
        spec.loader.exec_module(m)
    holder["bridge"] = sys.modules["zalo_call.bridge"]
    holder["core"] = sys.modules["zalo_call.bridge_core"]
    holder["const"] = sys.modules["zalo_call.const"]
    holder["api"] = sys.modules["zalo_call.api"]
    return holder


H = _load()
core, bridge_mod = H["core"], H["bridge"]


def test_derive_state_distinguishes_decline_no_answer_and_missed():
    d = core.derive_state
    assert d({"status": "sent"}) == "ringing"
    assert d({"status": "incoming"}) == "incoming"
    assert d({"status": "answered"}) == "answered"
    assert d({"status": "ended", "end_reason": "peer_declined"}) == "declined"
    assert d({"status": "ended", "end_reason": "ring_timeout"}) == "no_answer"
    assert d({"status": "ended", "end_reason": "missed"}) == "missed"
    assert d({"status": "ended", "end_reason": "user_rejected"}) == "rejected"
    assert d({"status": "ended", "end_reason": "peer_ended"}) == "ended"
    assert d({"status": "ended", "end_reason": "la-hoac"}) == "ended"
    assert d({"status": "ended"}) == "ended"
    assert d({"status": "error"}) == "error" and d({"status": "x"}) is None


def test_pick_devices_default_override_and_explicit_off():
    defaults = {"speaker": "media_player.loa_phong_khach", "mic": "camera.cam1",
                "mic_url": "", "camera": "camera.cam1"}
    assert core.pick_devices(defaults) == {
        "speaker": "media_player.loa_phong_khach", "mic": "camera.cam1",
        "mic_url": "", "camera": "camera.cam1"}
    got = core.pick_devices(defaults, {"speaker": "media_player.bat_ky",
                                       "mic": "", "mic_url": "rtsp://h/s"})
    assert got["speaker"] == "media_player.bat_ky"      # ghi de
    assert got["mic"] == "" and got["mic_url"] == "rtsp://h/s"   # "" = tat
    assert got["camera"] == "camera.cam1"                # khong nhac -> mac dinh
    assert core.mic_source_kind(got) == ("url", "rtsp://h/s")
    assert core.mic_source_kind({"mic": "camera.c", "mic_url": ""}) == \
        ("camera", "camera.c")
    assert core.mic_source_kind({"mic": "", "mic_url": ""}) is None


def test_ffmpeg_args_only_network_sources():
    a = core.ffmpeg_args("rtsp://u:p@10.0.0.5:554/s")
    assert a[a.index("-i") + 1] == "rtsp://u:p@10.0.0.5:554/s"
    assert "-rtsp_transport" in a and a[-1] == "pipe:1"
    assert "-ar" in a and a[a.index("-ar") + 1] == "16000"
    assert "-rtsp_transport" not in core.ffmpeg_args("http://h/a.mp3")
    for bad in ("/etc/passwd", "file:///etc/passwd", "concat:a|b", "",
                "rtsp://", "-i x", "udp://1.2.3.4:5"):
        try:
            core.ffmpeg_args(bad)
        except ValueError:
            continue
        raise AssertionError("phai tu choi nguon: %r" % bad)
    assert core.audio_out_url("http://h:8080/", "tok") == \
        "http://h:8080/api/call/audio/out/tok"


class FakeApi:
    url = "http://app:8080"

    def __init__(self, token="TOKEN"):
        self.token = token
        self.audio = []

    async def call_media(self, call_id):
        return {"audio_token": self.token} if self.token else {}

    async def audio_in(self, call_id, chunk):
        self.audio.append((str(call_id), len(chunk)))
        return {"ok": True}


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


class FakeHass:
    def __init__(self):
        self.services = FakeServices()

    def async_create_background_task(self, coro, name):
        return asyncio.ensure_future(coro)


class FakeEntry:
    def __init__(self, options):
        self.options = options


def _fake_ffmpeg(chunks):
    """Tien trinh ffmpeg gia: in `chunks` goi 3200 byte roi thoat."""
    path = os.path.join(tempfile.mkdtemp(), "ffmpeg")
    with open(path, "w") as fh:
        fh.write("#!%s\nimport sys\nsys.stdout.buffer.write(bytes(3200 * %d))\n"
                 % (sys.executable, chunks))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def _make(options, token="TOKEN", chunks=3):
    H["binary"] = _fake_ffmpeg(chunks)

    async def stream_source(hass, entity_id):
        return "rtsp://cam.local/stream" if entity_id == "camera.cam1" else None

    H["cam"].async_get_stream_source = stream_source
    hass, api = FakeHass(), FakeApi(token)
    return hass, api, bridge_mod.CallAudioBridge(hass, FakeEntry(options), api)


def test_bridge_uses_default_devices_then_stops_them():
    async def run():
        hass, api, br = _make({"speaker": "media_player.loa1",
                               "mic": "camera.cam1"})
        devices = await br.start(7)
        assert devices["speaker"] == "media_player.loa1"
        dom, svc, data = hass.services.calls[0]
        assert (dom, svc) == ("media_player", "play_media")
        assert data["entity_id"] == "media_player.loa1"
        assert data["media_content_id"] == \
            "http://app:8080/api/call/audio/out/TOKEN"
        assert data["media_content_type"] == "audio/wav"
        await asyncio.sleep(1.0)                 # ffmpeg gia ra 3 goi roi thoat
        assert api.audio == [("7", 3200)] * 3, api.audio
        await br.start(7)                         # khong chay hai lan
        assert len(hass.services.calls) == 1
        await br.stop(7)
        assert hass.services.calls[-1][:2] == ("media_player", "media_stop")
        await br.stop(7)                          # stop lap lai vo hai
    asyncio.run(run())


def test_bridge_any_device_override_per_call_and_mic_url():
    async def run():
        hass, api, br = _make({"speaker": "media_player.loa1",
                               "mic": "camera.cam1"})
        br.remember(None, {"speaker": "media_player.may_khac",
                           "mic": "", "mic_url": "rtsp://x/y"})
        d = await br.start(8)
        assert d["speaker"] == "media_player.may_khac"
        assert hass.services.calls[0][2]["entity_id"] == "media_player.may_khac"
        await asyncio.sleep(1.0)
        assert len(api.audio) == 3
        await br.stop(8)
        # Cuoc goi ke tiep quay lai mac dinh (ghi de chi dung mot lan).
        assert br.devices_for(9)["speaker"] == "media_player.loa1"
    asyncio.run(run())


def test_bridge_no_devices_or_no_token_is_harmless():
    async def run():
        hass, api, br = _make({})                 # khong thiet bi nao
        await br.start(1)
        assert hass.services.calls == [] and api.audio == []
        await br.stop(1)
        hass, api, br = _make({"speaker": "media_player.a"}, token=None)
        await br.start(2)                         # chua co media -> khong phat
        assert hass.services.calls == []
        # Camera khong co stream -> khong sap.
        hass, api, br = _make({"mic": "camera.khong_co"})
        await br.start(3)
        await asyncio.sleep(0.2)
        assert api.audio == []
        await br.async_shutdown()
    asyncio.run(run())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL BRIDGE TESTS PASSED")
