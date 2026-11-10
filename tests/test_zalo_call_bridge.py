"""Cau noi thiet bi cua custom zalo_call — chay NGOAI Home Assistant.

HA khong co san o moi truong test nen cac module `homeassistant.*` duoc thay bang
ban gia toi thieu; test chay THAT bridge_core.py, devices.py va bridge.py (phan giai
nguon mic/camera, mac dinh, ghi de moi cuoc goi, loa). Khong chung minh chay duoc
trong HA that — chi chung minh logic dieu phoi dung.
"""
import asyncio
import importlib.util
import os
import sys
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

    class NoURLAvailableError(Exception):
        pass

    holder = {"urls": {}, "saved": {}, "registry": {}, "entries": {}, "base": "http://ha:8123"}

    class Store:
        def __init__(self, hass, version, key):
            self.key = key

        async def async_load(self):
            return holder["saved"].get(self.key)

        async def async_save(self, data):
            holder["saved"][self.key] = dict(data)

    mod("homeassistant")
    mod("homeassistant.components")
    cam = mod("homeassistant.components.camera")
    mod("homeassistant.config_entries", ConfigEntry=object)
    mod("homeassistant.core", HomeAssistant=object)
    mod("homeassistant.exceptions", HomeAssistantError=HomeAssistantError)
    helpers = mod("homeassistant.helpers")
    reg_mod = mod("homeassistant.helpers.entity_registry")
    mod("homeassistant.helpers.storage", Store=Store)

    def get_url(hass, **kw):
        if not holder["base"]:
            raise NoURLAvailableError()
        return holder["base"]
    mod("homeassistant.helpers.network", NoURLAvailableError=NoURLAvailableError,
        get_url=get_url)
    sys.modules["homeassistant.components"].camera = cam
    helpers.entity_registry = reg_mod
    reg_mod.async_get = lambda hass: types.SimpleNamespace(
        async_get=lambda eid: holder["registry"].get(eid))

    async def stream_source(hass, entity_id):
        return holder["urls"].get(entity_id)
    cam.async_get_stream_source = stream_source

    pkg = types.ModuleType("zalo_call")
    pkg.__path__ = [ROOT]
    sys.modules["zalo_call"] = pkg
    for name in ("const", "api", "bridge_core", "devices", "bridge"):
        spec = importlib.util.spec_from_file_location(
            "zalo_call." + name, os.path.join(ROOT, name + ".py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules["zalo_call." + name] = m
        spec.loader.exec_module(m)
    for n in ("bridge", "bridge_core", "const", "api", "devices"):
        holder[n] = sys.modules["zalo_call." + n]
    return holder


H = _load()
core, bridge_mod, devices_mod = H["bridge_core"], H["bridge"], H["devices"]


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
    defaults = {"speaker": "media_player.loa", "mic": "camera.cam1",
                "mic_url": "", "camera": "camera.cam1"}
    got = core.pick_devices(defaults, {"speaker": "media_player.bat_ky",
                                       "mic": "", "mic_url": "rtsp://h/s"})
    assert got["speaker"] == "media_player.bat_ky"
    assert got["mic"] == "" and got["mic_url"] == "rtsp://h/s"
    assert got["camera"] == "camera.cam1"
    # explicit_off: ghi de rong cho CA nhom va khong con nguon -> tat cho cuoc nay.
    off = core.pick_devices(defaults, {"mic": "", "mic_url": ""})
    assert core.explicit_off({"mic": "", "mic_url": ""}, ("mic", "mic_url"), off) is True
    assert core.explicit_off({"speaker": "x"}, ("mic", "mic_url"), off) is False   # khong nhac toi
    assert core.explicit_off(None, ("mic", "mic_url"), off) is False
    assert core.explicit_off({"mic": ""}, ("mic", "mic_url"), core.pick_devices(
        defaults, {"mic": "", "mic_url": "rtsp://x/y"})) is False       # con mic_url


def test_intercom_helpers_and_echo_modes():
    assert core.intercom_url("http://ha:8123/", "r1_speaker", "E1", "k e") == \
        "http://ha:8123/api/r1_speaker/intercom/E1?k=k%20e"
    assert core.device_of_url("http://ha:8123/api/r1_speaker/intercom/E1?k=1") == ("r1_speaker", "E1")
    assert core.device_of_url("http://ha/api/r1_speaker/mic/E1?k=1") == ("r1_speaker", "E1")
    assert core.device_of_url("http://ha/api/dahua_talk/intercom/D9?k=1") == ("dahua_talk", "D9")
    assert core.device_of_url("rtsp://cam/x") is None and core.device_of_url("") is None
    assert core.echo_guard_on("on", False) is True and core.echo_guard_on("off", True) is False
    assert core.echo_guard_on("auto", True) is True and core.echo_guard_on("auto", False) is False
    assert core.echo_guard_on("la", True) is True                       # mode la -> coi nhu auto


def test_speaker_sink_resolution_and_echo_auto():
    async def run():
        hass, api, dd, br = _make({"speaker": "media_player.r1_loa", "mic": "assist_satellite.r1"},
                                  options={"ha_url": "http://ha.lan:8123"})
        r1 = _ent("r1_speaker", "media_player.r1_loa", "r1entry")
        _ent("r1_speaker", "assist_satellite.r1", "r1entry")
        r1.data = {"intercom_key": "KHOA", "intercom_key_x": 1}
        H["entries"]["r1entry"].data = {"intercom_key": "KHOA"}
        url = await br.async_speaker_sink("media_player.r1_loa")
        assert url == "http://ha.lan:8123/api/r1_speaker/intercom/r1entry?k=KHOA"
        # Loa va mic cung tich hop R1 -> auto bat chong vong; loa camera + mic camera khac thiet bi -> tat.
        res = await br.async_resolve(br.devices_for(), "auto")
        assert res["speaker_url"] == url and res["echo_guard"] == "true"
        assert (await br.async_resolve(br.devices_for(), "off"))["echo_guard"] == "false"
        # Mic khac thiet bi (camera) -> auto KHONG bat.
        _ent("go2rtc", "camera.cam1", "gcfg")
        res = await br.async_resolve(br.devices_for({"mic": "camera.cam1"}), "auto")
        assert res["echo_guard"] == "false" and (await br.async_resolve(
            br.devices_for({"mic": "camera.cam1"}), "on"))["echo_guard"] == "true"
        # Mic bang URL luong R1 cung entry voi cua bo dam -> cung thiet bi.
        d = br.devices_for({"mic": "", "mic_url": "http://ha/api/r1_speaker/mic/r1entry?k=x"})
        assert (await br.async_resolve(d, "auto"))["echo_guard"] == "true"
        d = br.devices_for({"mic": "", "mic_url": "http://ha/api/r1_speaker/mic/KHAC?k=x"})
        assert (await br.async_resolve(d, "auto"))["echo_guard"] == "false"
        # Camera Imou/Dahua: loa cua dahua_talk cung co cua bo dam rieng.
        dh = _ent("dahua_talk", "media_player.cam_loa", "dhentry")
        H["entries"]["dhentry"].data = {"intercom_key": "DK"}
        assert (await br.async_speaker_sink("media_player.cam_loa")).endswith(
            "/api/dahua_talk/intercom/dhentry?k=DK")
        # Loa khac (Bluetooth/Cast/TV), thuc the la, thieu khoa -> khong co cua bo dam (dung play_media).
        _ent("bluetooth_speaker", "media_player.bt", "btcfg")
        for ent in ("media_player.bt", "media_player.khong_co", ""):
            assert await br.async_speaker_sink(ent) == ""
        H["entries"]["dhentry"].data = {}
        assert await br.async_speaker_sink("media_player.cam_loa") == ""
        # Khong co dia chi noi bo cua HA -> khong doan.
        H["entries"]["r1entry"].data = {"intercom_key": "KHOA"}
        H["base"] = ""
        hass2, api2, dd2, br2 = _make({"speaker": "media_player.r1_loa"})
        _ent("r1_speaker", "media_player.r1_loa", "r1entry").data = {"intercom_key": "KHOA"}
        assert await br2.async_speaker_sink("media_player.r1_loa") == ""
        H["base"] = "http://ha:8123"
    asyncio.run(run())


def test_call_fields_and_start_use_sink_not_play_media():
    async def run():
        hass, api, dd, br = _make({"speaker": "media_player.r1_loa", "mic": "assist_satellite.r1"},
                                  options={"ha_url": "http://ha.lan:8123"})
        r1 = _ent("r1_speaker", "media_player.r1_loa", "r1entry")
        _ent("r1_speaker", "assist_satellite.r1", "r1entry")
        H["entries"]["r1entry"].data = {"intercom_key": "KHOA"}
        f = await br.async_call_fields(None)
        assert f["speaker_url"].endswith("/api/r1_speaker/intercom/r1entry?k=KHOA")
        assert f["echo_guard"] == "true" and f["mic_url"].endswith("/api/r1_speaker/mic/r1entry?k=KHOA")
        # Ghi de loa rong -> "off"; khong co echo_guard di kem.
        f = await br.async_call_fields({"speaker": ""})
        assert f["speaker_url"] == "off" and "echo_guard" not in f
        # Loa truc tiep: start() KHONG goi play_media (app tu day tieng vao bo dam).
        devices = await br.start(5)
        assert devices["speaker"] and hass.services.calls == []
        # Che do echo cua mac dinh duoc ton trong (off thi khong bat du cung thiet bi).
        dd._merge({"echo_guard": "off"})
        assert (await br.async_call_fields(None))["echo_guard"] == "false"
        dd._merge({"echo_guard": "bogus"})                                # sai -> giu "off"
        assert dd.get("echo_guard") == "off"
    asyncio.run(run())


def test_push_policy_retries_after_failure_and_recovery():
    p = core.PushPolicy()
    assert p.poll(True) is True               # chua dua duoc lan nao -> dua
    p.pushed(False)
    assert p.poll(True) is True               # lan truoc loi -> thu lai o lan hoi ke tiep
    p.pushed(True)
    assert p.poll(True) is False and p.poll(True) is False   # on dinh -> khong dua lai
    assert p.poll(False) is False             # app mat ket noi: chua dua duoc
    assert p.poll(False) is False
    assert p.poll(True) is True               # app song lai -> dua lai (app co the vua khoi dong)
    assert p.poll(True) is False              # chi MOT lan sau moi lan song lai


def test_failed_push_is_recorded_and_not_concurrent():
    async def run():
        hass, api, dd, br = _make({"speaker": "", "mic": ""})
        api.fail_devices_set = True
        await br.async_push_defaults()
        assert br.policy.pushed_ok is False
        api.fail_devices_set = False
        await br.async_push_defaults()
        assert br.policy.pushed_ok is True
        br._pushing = True                    # dang day dang do -> lan goi them bi bo qua
        n = len(api.pushed)
        await br.async_push_defaults()
        assert len(api.pushed) == n
    asyncio.run(run())


def test_legacy_gear_options_import_without_overwriting_device_values():
    async def run():
        hass = FakeHass()
        key = "zalo_call.devices.e1"
        H["saved"] = {key: {"speaker": "media_player.x", "ai_agent": "conversation.mine"}}   # kho da co
        dd = devices_mod.DeviceDefaults(hass, "e1")
        await dd.async_load({"ha_url": "http://ha:8123/", "ai_enabled": True,
                             "ai_threads": "1, 2", "ai_agent": "conversation.cu"})
        assert dd.get("ha_url") == "http://ha:8123"              # bo dau / cuoi
        assert dd.get("ai_enabled") is True and dd.get("ai_threads") == "1, 2"
        assert dd.get("ai_agent") == "conversation.mine"         # da dat tren thiet bi: khong ghi de
        assert H["saved"][key]["ha_url"] == "http://ha:8123"     # da luu: lan sau khong doc lai options
    asyncio.run(run())


def test_duplex_mode_uses_r1_duplex_url_and_leaves_mic_open():
    async def run():
        hass, api, dd, br = _make({"speaker": "media_player.r1_loa", "mic": "assist_satellite.r1"},
                                  options={"ha_url": "http://ha.lan:8123"})
        _ent("r1_speaker", "media_player.r1_loa", "r1entry")
        _ent("r1_speaker", "assist_satellite.r1", "r1entry")
        H["entries"]["r1entry"].data = {"intercom_key": "KHOA"}
        res = await br.async_resolve(br.devices_for(), "duplex")
        assert res["speaker_url"] == "http://ha.lan:8123/api/r1_speaker/duplex/r1entry?k=KHOA"
        assert res["echo_guard"] == "false"                      # mic mo: loa R1 tu khu vong
        res = await br.async_resolve(br.devices_for(), "on")
        assert "/intercom/" in res["speaker_url"] and res["echo_guard"] == "true"
        # Loa camera khong co phien song cong -> van la cua bo dam.
        _ent("dahua_talk", "media_player.cam_loa", "dhentry")
        H["entries"]["dhentry"].data = {"intercom_key": "DK"}
        assert "/intercom/dhentry" in await br.async_speaker_sink("media_player.cam_loa", "duplex")
        assert core.device_of_url("http://ha/api/r1_speaker/duplex/r1entry?k=1") == ("r1_speaker", "r1entry")
        assert core.echo_guard_on("duplex", True) is False
    asyncio.run(run())


def test_localize_url_rewrites_only_loopback():
    f = core.localize_url
    assert f("rtsp://u:p@localhost:8554/phong-khach", "172.16.10.200") == \
        "rtsp://u:p@172.16.10.200:8554/phong-khach"
    assert f("rtsp://127.0.0.1/x?a=1#f", "10.0.0.2") == "rtsp://10.0.0.2/x?a=1#f"
    assert f("http://[::1]:1984/s", "ha.lan") == "http://ha.lan:1984/s"
    assert f("rtsp://cam.lan/x", "10.0.0.2") == "rtsp://cam.lan/x"          # khong dong cham may khac
    assert f("rtsp://localhost/x", "") == "rtsp://localhost/x"               # khong co dia chi -> giu
    assert core.host_of("http://172.16.10.200:8123/") == "172.16.10.200" and core.host_of("") == ""


def test_labels_urls_and_formats():
    assert core.label("camera.a", "Camera phòng khách") == "Camera phòng khách · camera.a"
    assert core.label("camera.a", None) == "camera.a" == core.label("camera.a", "camera.a")
    assert core.entity_of_label("Camera phòng khách · camera.a") == "camera.a"
    assert core.entity_of_label("camera.a") == "camera.a" and core.entity_of_label("") == ""
    assert core.valid_url("rtsp://u:p@10.0.0.5:8554/x") and core.valid_url("http://h/a")
    for bad in ("", "/etc/passwd", "file:///x", "ftp://h/x", "rtsp://", "http://h/a b"):
        assert not core.valid_url(bad), bad
    assert core.r1_mic_url("http://ha:8123/", "abc", "k e/y") == \
        "http://ha:8123/api/r1_speaker/mic/abc?k=k%20e%2Fy"
    assert core.mic_format_for_url("http://ha/api/r1_speaker/mic/x?k=1") == "s16le16k"
    assert core.mic_format_for_url("rtsp://h/x") == "auto"
    assert core.dahua_mic_url({"mic_url": "rtsp://o"}, {"mic_url": "rtsp://d"}) == "rtsp://o"
    assert core.dahua_mic_url({}, {"mic_url": " rtsp://d "}) == "rtsp://d"
    assert core.audio_out_url("http://h:8080/", "tok") == "http://h:8080/api/call/audio/out/tok"


class FakeApi:
    url = "http://app:8080"

    def __init__(self, token="TOKEN"):
        self.token, self.pushed = token, []

    async def call_media_status(self, call_id):
        return {"audio_token": self.token} if self.token else {}

    fail_devices_set = False

    async def devices_set(self, patch):
        if self.fail_devices_set:
            raise sys.modules["zalo_call.api"].ZaloCallError("app tat")
        self.pushed.append(patch)
        return {"ok": True}


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


class FakeConfigEntries:
    def async_get_entry(self, entry_id):
        return H["entries"].get(entry_id)


class FakeHass:
    def __init__(self):
        self.services = FakeServices()
        self.config_entries = FakeConfigEntries()


class FakeEntry:
    entry_id = "e1"

    def __init__(self, options=None):
        self.options = options or {}


def _make(defaults, token="TOKEN", options=None):
    H["urls"] = {"camera.cam1": "rtsp://u:p@cam.local/stream",
                 "camera.cam2": "rtsp://cam2.local/s"}
    H["registry"], H["entries"], H["saved"] = {}, {}, {}
    hass, api = FakeHass(), FakeApi(token)
    dd = devices_mod.DeviceDefaults(hass, "e1")
    dd._merge(defaults)
    if options and options.get("ha_url"):       # «Địa chỉ HA» nay là ô trên thiết bị, không phải bánh răng
        dd._merge({"ha_url": options["ha_url"]})
    return hass, api, dd, bridge_mod.CallAudioBridge(hass, FakeEntry(options), api, dd)


def _ent(domain, entry_id, config_entry_id, device_id=None):
    H["registry"][entry_id] = types.SimpleNamespace(config_entry_id=config_entry_id,
                                                    device_id=device_id)
    H["entries"][config_entry_id] = types.SimpleNamespace(
        domain=domain, entry_id=config_entry_id, options={}, data={})
    return H["entries"][config_entry_id]


def test_defaults_store_roundtrip_legacy_import_and_listeners():
    async def run():
        hass = FakeHass()
        H["saved"] = {}
        dd = devices_mod.DeviceDefaults(hass, "e1")
        seen = []
        dd.add_listener(lambda: seen.append(1))
        await dd.async_load({"speaker": "media_player.cu", "mic": "camera.cu",
                             "mic_url": "", "camera": "camera.cu"})   # tuy chon cu (banh rang)
        assert dd.get("speaker") == "media_player.cu" and dd.get("auto_mic") is True
        assert H["saved"]["zalo_call.devices.e1"]["camera"] == "camera.cu"   # da nhap + luu
        await dd.async_set(speaker="media_player.moi", auto_video=False, mic_url=" rtsp://x/y ",
                           auto_video_delay=15)
        assert dd.get("speaker") == "media_player.moi" and dd.get("auto_video") is False
        assert dd.get("mic_url") == "rtsp://x/y" and seen == [1]
        assert dd.get("auto_video_delay") == 15
        await dd.async_set(auto_video_delay=9999)
        assert dd.get("auto_video_delay") == 120                       # kep trong gioi han
        await dd.async_set(auto_video_delay="abc")                     # sai kieu: giu nguyen
        assert dd.get("auto_video_delay") == 120
        await dd.async_set(auto_video_delay=-3)
        assert dd.get("auto_video_delay") == 0
        await dd.async_set(auto_video_delay=15)
        dd2 = devices_mod.DeviceDefaults(hass, "e1")                   # nap lai tu Store
        await dd2.async_load({"speaker": "media_player.cu"})           # Store thang tuy chon cu
        assert dd2.get("speaker") == "media_player.moi" and dd2.get("auto_video") is False
        await dd2.async_set(bogus="x")                                  # khoa la bi bo qua
        assert "bogus" not in dd2.data
    asyncio.run(run())


def test_resolve_mic_from_camera_url_r1_and_dahua():
    async def run():
        hass, api, dd, br = _make({}, options={"ha_url": "http://ha.lan:8123"})
        # camera.* -> stream cua camera
        d = br.devices_for({"mic": "Cam · camera.cam1"})
        assert await br.async_mic_source(d) == ("rtsp://u:p@cam.local/stream", "auto")
        # mic_url thang mic; luong R1 -> PCM tho
        d = br.devices_for({"mic": "camera.cam1", "mic_url": "http://ha/api/r1_speaker/mic/x?k=1"})
        assert await br.async_mic_source(d) == ("http://ha/api/r1_speaker/mic/x?k=1", "s16le16k")
        # URL xau bi tu choi
        assert await br.async_mic_source(br.devices_for({"mic_url": "ftp://x"})) == ("", "auto")
        # assist_satellite cua r1_speaker -> luong mic tu khoa intercom
        r1 = _ent("r1_speaker", "assist_satellite.r1", "r1entry")
        r1.data = {"intercom_key": "KHOA"}
        url, fmt = await br.async_mic_source(br.devices_for({"mic": "assist_satellite.r1"}))
        assert (url, fmt) == ("http://ha.lan:8123/api/r1_speaker/mic/r1entry?k=KHOA", "s16le16k")
        r1.data = {}                                                   # chua co khoa -> khong doan
        assert await br.async_mic_source(br.devices_for({"mic": "assist_satellite.r1"})) == ("", "auto")
        # assist_satellite cua camera Imou/Dahua -> mic_url cua dahua_talk
        dh = _ent("dahua_talk", "assist_satellite.cam_bep", "dhentry")
        dh.options = {"mic_url": "rtsp://bep.lan/mic"}
        assert await br.async_mic_source(br.devices_for({"mic": "assist_satellite.cam_bep"})) == (
            "rtsp://bep.lan/mic", "auto")
        # thuc the la / khong ho tro
        assert await br.async_mic_source(br.devices_for({"mic": "media_player.x"})) == ("", "auto")
        assert await br.async_mic_source(br.devices_for({"mic": "assist_satellite.khong_co"})) == ("", "auto")
        assert await br.async_mic_source(br.devices_for({})) == ("", "auto")
    asyncio.run(run())


def test_call_fields_default_override_and_off():
    async def run():
        hass, api, dd, br = _make({"mic": "camera.cam1", "camera": "camera.cam2"})
        f = await br.async_call_fields(None)
        assert f == {"mic_url": "rtsp://u:p@cam.local/stream", "mic_format": "auto",
                     "camera_url": "rtsp://cam2.local/s"}
        # ghi de: camera khac, mic URL
        f = await br.async_call_fields({"camera": "camera.cam1", "mic_url": "rtsp://z/z"})
        assert f["camera_url"] == "rtsp://u:p@cam.local/stream" and f["mic_url"] == "rtsp://z/z"
        # ghi de rong -> "off" cho rieng cuoc nay (app tat thiet bi)
        f = await br.async_call_fields({"mic": "", "camera": ""})
        assert f == {"mic_url": "off", "camera_url": "off"}
        # khong co mac dinh nao thi khong gui gi
        hass, api, dd, br = _make({})
        assert await br.async_call_fields(None) == {}
        assert await br.async_call_fields({"speaker": "media_player.x"}) == {}
    asyncio.run(run())


def test_push_defaults_to_app_with_resolved_urls():
    async def run():
        hass, api, dd, br = _make({"mic": "camera.cam1", "camera": "camera.cam2",
                                   "auto_mic": False, "auto_video": True,
                                   "auto_video_delay": 0})
        await br.async_push_defaults()
        assert api.pushed == [{"mic_url": "rtsp://u:p@cam.local/stream", "mic_format": "auto",
                               "camera_url": "rtsp://cam2.local/s", "speaker_url": "",
                               "echo_guard": False, "auto_mic": False,
                               "auto_video_on_request": True, "auto_video_delay": 0}]
        # camera khong co stream -> day rong (app khong tu phat hinh)
        H["urls"]["camera.cam2"] = "rtsp://u:p@localhost:8554/cam2-sub"        # go2rtc cua HA
        await br.async_push_defaults()
        assert api.pushed[-1]["camera_url"] == "rtsp://u:p@ha:8554/cam2-sub", api.pushed[-1]
        api.pushed.clear()
        H["urls"].pop("camera.cam2")
        api.pushed.clear()
        await br.async_push_defaults()
        assert api.pushed[0]["camera_url"] == ""
    asyncio.run(run())


def test_speaker_start_stop_and_harmless_cases():
    async def run():
        hass, api, dd, br = _make({"speaker": "Loa phòng · media_player.loa1"})
        br.remember(None, {})
        devices = await br.start(7)
        assert devices["speaker"].endswith("media_player.loa1")
        dom, svc, data = hass.services.calls[0]
        assert (dom, svc) == ("media_player", "play_media")
        assert data["entity_id"] == "media_player.loa1"                 # tach tu nhan
        assert data["media_content_id"] == "http://app:8080/api/call/audio/out/TOKEN"
        assert data["media_content_type"] == "audio/wav"
        await br.start(7)                                               # khong chay hai lan
        assert len(hass.services.calls) == 1
        await br.stop(7)
        assert hass.services.calls[-1][:2] == ("media_player", "media_stop")
        await br.stop(7)                                                # stop lap lai vo hai
        # Ghi de moi cuoc goi chi dung mot lan.
        br.remember(None, {"speaker": "media_player.may_khac"})
        await br.start(8)
        assert hass.services.calls[-1][2]["entity_id"] == "media_player.may_khac"
        assert br.devices_for(None)["speaker"].endswith("media_player.loa1")
        # Khong co loa / chua co media -> khong lam gi.
        hass, api, dd, br = _make({})
        await br.start(1)
        assert hass.services.calls == []
        hass, api, dd, br = _make({"speaker": "media_player.a"}, token=None)
        await br.start(2)
        assert hass.services.calls == []
        await br.async_shutdown()
    asyncio.run(run())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL BRIDGE TESTS PASSED")
