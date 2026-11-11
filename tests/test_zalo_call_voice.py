"""Giọng nói TRONG cuộc gọi (call_voice.py): TTS lên cuộc gọi, kế hoạch khi nghe máy, vòng AI nói chuyện.

Chạy trong HA thật (ảnh r1-test): python -m pytest tests/test_zalo_call_voice.py -p pytest_homeassistant_custom_component -o asyncio_mode=auto
Api của app và Assist pipeline được thay bằng bản giả (không gọi thật, không STT/TTS thật)."""
import asyncio
import os
import sys
import types
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")
sys.modules.setdefault("turbojpeg", types.SimpleNamespace(TurboJPEG=object))

import custom_components  # noqa: E402

_REPO_CC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_components"))
if _REPO_CC not in [os.path.abspath(p) for p in custom_components.__path__]:
    custom_components.__path__.append(_REPO_CC)

from custom_components.zalo_call import call_voice as cv  # noqa: E402

TERMINAL = ("ended", "no_answer", "declined", "missed", "rejected", "error")


class FakeApi:
    url = "http://app.invalid"

    def __init__(self, statuses=None, mic_alive=(True, False)):
        self.said, self.ended, self.calls_n = [], [], 0
        self._statuses = list(statuses or [])
        self._mic = list(mic_alive)
        self.mic_polls = 0

    async def call_say(self, call_id, filename, data):
        self.said.append((str(call_id), filename, data))
        return {"ok": True}

    async def media_control(self, body):
        self.mic_polls += 1
        alive = self._mic.pop(0) if self._mic else False
        return {"mic": {"alive": alive}}

    async def calls(self):
        self.calls_n += 1
        st = self._statuses.pop(0) if len(self._statuses) > 1 else (self._statuses[0] if self._statuses else "answered")
        return {"calls": [{"call_id": "77", "status": st}], "active": {"call_id": "77", "status": st}}

    async def call_media_status(self, call_id):
        return {"audio_token": "tok"}

    async def call_end(self, call_id):
        self.ended.append(str(call_id))
        return {"ok": True}


def _rt(api):
    return SimpleNamespace(api=api, voice=cv.CallVoice())


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(cv, "POLL_S", 0.01)

    async def fake_tts(hass, message, engine=None, language=None, options=None):
        return "mp3", ("TTS:" + message).encode()
    monkeypatch.setattr(cv, "async_tts_audio", fake_tts)


def test_plan_from_service():
    assert cv.plan_from_service({}) is None
    p = cv.plan_from_service({"message": " Có người ngã ", "repeat": 9})
    assert p.message == "Có người ngã" and p.repeat == 3 and p.hangup is True and p.ai is False      # chỉ thông báo: cúp sau khi đọc
    p = cv.plan_from_service({"ai": True, "hangup_after": False, "tts_engine": "tts.x"})
    assert p.ai and p.hangup is False and p.engine == "tts.x"


async def test_say_uploads_tts_and_waits_until_playback_done(hass):
    api = FakeApi(mic_alive=(True, True, False))
    await cv.async_say(hass, api, "77", "Xin chào")
    assert api.said == [("77", "tts.mp3", "TTS:Xin chào".encode())]
    assert api.mic_polls == 3                      # chờ tới khi mic.alive = False
    api2 = FakeApi()
    await cv.async_say(hass, api2, "77", "   ")    # rỗng: không gọi gì
    assert api2.said == []
    await cv.async_say(hass, api2, "77", "Nhanh", wait=False)
    assert len(api2.said) == 1 and api2.mic_polls == 0


async def test_plan_runs_on_answered_then_hangs_up(hass):
    api = FakeApi()
    rt = _rt(api)
    rt.voice.plans["77"] = cv.plan_from_service({"message": "Cảnh báo: có người ngã", "repeat": 2})
    cv.on_call_state(hass, rt, "ringing", 77, TERMINAL, False, "")
    assert api.said == []                          # chưa nghe máy thì chưa đọc
    cv.on_call_state(hass, rt, "answered", 77, TERMINAL, False, "")
    await asyncio.wait_for(asyncio.gather(*rt.voice.tasks.values()), 10) if rt.voice.tasks else None
    for _ in range(100):
        if api.ended:
            break
        await asyncio.sleep(0.05)
    assert [s[2] for s in api.said] == ["TTS:Cảnh báo: có người ngã".encode()] * 2, api.said
    assert api.ended == ["77"]
    assert "77" not in rt.voice.plans


async def test_plan_cancelled_when_call_ends_before_answer(hass):
    api = FakeApi()
    rt = _rt(api)
    rt.voice.plans["77"] = cv.Plan(message="x")
    cv.on_call_state(hass, rt, "declined", 77, TERMINAL, False, "")
    cv.on_call_state(hass, rt, "answered", 77, TERMINAL, False, "")     # trạng thái muộn không được kích hoạt lại
    await asyncio.sleep(0.1)
    assert api.said == [] and not rt.voice.tasks


async def test_ai_switch_applies_only_to_incoming_calls(hass, monkeypatch):
    started = []

    async def fake_ai(hass_, api, call_id, plan):
        started.append((call_id, plan.greeting, plan.hangup))
    monkeypatch.setattr(cv, "async_run_ai", fake_ai)
    api = FakeApi()
    rt = _rt(api)
    # cuộc gọi ĐI (không từng "incoming"): công tắc AI không áp dụng
    cv.on_call_state(hass, rt, "answered", 50, TERMINAL, True, "")
    await asyncio.sleep(0.05)
    assert started == []
    # cuộc gọi ĐẾN: có công tắc thì AI chạy, câu chào mặc định khi ô trống, cúp máy khi xong
    cv.on_call_state(hass, rt, "incoming", 77, TERMINAL, True, "")
    cv.on_call_state(hass, rt, "answered", 77, TERMINAL, True, "", "auto")
    for _ in range(100):
        if api.ended:
            break
        await asyncio.sleep(0.05)
    assert started == [("77", cv.DEFAULT_GREETING, True)] and api.ended == ["77"]
    # người thật nghe máy (answer_source "api": answer_call/R1) thì AI KHÔNG chen vào dù công tắc bật
    api2 = FakeApi()
    rt2 = _rt(api2)
    cv.on_call_state(hass, rt2, "incoming", 79, TERMINAL, True, "")
    cv.on_call_state(hass, rt2, "answered", 79, TERMINAL, True, "", "api")
    await asyncio.sleep(0.05)
    assert len(started) == 1 and not rt2.voice.tasks
    # công tắc tắt thì không chạy
    api3 = FakeApi()
    rt3 = _rt(api3)
    cv.on_call_state(hass, rt3, "incoming", 78, TERMINAL, False, "")
    cv.on_call_state(hass, rt3, "answered", 78, TERMINAL, False, "", "auto")
    await asyncio.sleep(0.05)
    assert len(started) == 1 and not rt3.voice.tasks


class FakePipelineModule:
    """Thay assist_pipeline.async_pipeline_from_audio_stream: mỗi lượt đọc một khúc từ luồng rồi phát sự kiện theo kịch bản."""

    def __init__(self, script):
        self.script, self.convs, self.turn = list(script), [], 0

    async def run(self, hass, *, context, event_callback, stt_metadata, stt_stream, pipeline_id=None,
                  conversation_id=None, end_stage=None, audio_settings=None, conversation_extra_system_prompt=None, **kw):
        from homeassistant.components.assist_pipeline import pipeline as pl
        assert end_stage == pl.PipelineStage.INTENT                     # TTS do call_voice tự làm bằng giọng của pipeline
        assert "điện thoại" in (conversation_extra_system_prompt or "")  # nhắc trợ lý đang nói qua điện thoại
        self.convs.append(conversation_id)
        async for _chunk in stt_stream:            # nghe ít nhất một khúc
            break
        text, reply = self.script[self.turn] if self.turn < len(self.script) else ("", "")
        self.turn += 1
        if text:
            event_callback(pl.PipelineEvent(pl.PipelineEventType.STT_END, {"stt_output": {"text": text}}))
            event_callback(pl.PipelineEvent(pl.PipelineEventType.INTENT_END, {"intent_output": {
                "conversation_id": "conv-1", "response": {"speech": {"plain": {"speech": reply}}}}}))


async def test_ai_loop_answers_each_turn_then_stops_after_idle(hass, monkeypatch):
    from homeassistant.components import assist_pipeline
    from homeassistant.components.assist_pipeline import pipeline as pl
    fake = FakePipelineModule([("bật đèn phòng khách", "Đã bật đèn phòng khách"), ("cảm ơn", "Không có gì ạ")])
    monkeypatch.setattr(assist_pipeline, "async_pipeline_from_audio_stream", fake.run)
    monkeypatch.setattr(pl, "async_get_pipeline", lambda hass_, pid=None: SimpleNamespace(
        stt_language="vi", tts_engine="tts.edge", tts_language="vi", tts_voice=None))

    class FakeListener:
        def __init__(self, hass_, url):
            self.url, self.muted, self.ended = url, False, False
            self.queue = asyncio.Queue()

        def start(self):
            pass

        def drain(self):
            pass

        def stop(self):
            pass

        async def chunks(self):
            while True:
                yield b"\x00" * 3200
                await asyncio.sleep(0)
    monkeypatch.setattr(cv, "_Listener", FakeListener)
    api = FakeApi(statuses=["answered"])
    await cv.async_run_ai(hass, api, "77", cv.Plan(ai=True, greeting="Xin chào"))
    said = [s[2].decode() for s in api.said]
    assert said == ["TTS:Xin chào", "TTS:Đã bật đèn phòng khách", "TTS:Không có gì ạ"], said
    assert fake.convs[:3] == [None, "conv-1", "conv-1"]            # giữ ngữ cảnh hội thoại giữa các lượt
    assert fake.turn == 2 + cv.IDLE_TURNS                         # hai lượt có chữ + IDLE_TURNS lượt im lặng thì dừng


async def test_ai_loop_stops_when_call_no_longer_answered(hass, monkeypatch):
    from homeassistant.components import assist_pipeline
    from homeassistant.components.assist_pipeline import pipeline as pl
    fake = FakePipelineModule([("a", "b")] * 5)
    monkeypatch.setattr(assist_pipeline, "async_pipeline_from_audio_stream", fake.run)
    monkeypatch.setattr(pl, "async_get_pipeline", lambda hass_, pid=None: SimpleNamespace(
        stt_language="vi", tts_engine=None, tts_language=None, tts_voice=None))

    class L:
        def __init__(self, *a):
            self.muted = self.ended = False

        def start(self):
            pass

        def drain(self):
            pass

        def stop(self):
            pass

        async def chunks(self):
            while True:
                yield b"\x00" * 3200
                await asyncio.sleep(0)
    monkeypatch.setattr(cv, "_Listener", L)
    api = FakeApi(statuses=["answered", "answered", "ended"])        # người gọi cúp sau hai lượt
    await cv.async_run_ai(hass, api, "77", cv.Plan(ai=True))
    assert fake.turn == 2, fake.turn


# ---- Trong HA thật: dịch vụ make_call / say_in_call và webhook "đã nghe máy" ----------------------------------------
from aiohttp import web  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from test_zalo_call_ha_end_to_end import DOMAIN, THREAD, FakeZaloApp, setup  # noqa: E402,F401


class VoiceApp(FakeZaloApp):
    async def _any(self, request: web.Request) -> web.Response:
        p = request.path
        if p in ("/api/call/request", "/api/call/say", "/api/call/media", "/api/call/end"):
            raw = await request.read()
            self.requests.append({"method": request.method, "path": p, "json": None, "raw": raw, "ctype": request.content_type})
            if p == "/api/call/request":
                return web.json_response({"ok": True, "call_id": "555", "request_sent": True})
            if p == "/api/call/media":
                return web.json_response({"ok": True, "mic": {"alive": False}})
            return web.json_response({"ok": True})
        return await super()._any(request)


@pytest.fixture
async def app(socket_enabled):
    a = VoiceApp()
    await a.start()
    yield a
    await a.stop()


async def _wait_path(app, path, n=1):
    for _ in range(200):
        if sum(1 for r in app.requests if r["path"] == path) >= n:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("không thấy %s: %s" % (path, [r["path"] for r in app.requests]))


async def test_make_call_with_message_speaks_when_answered_then_hangs_up(hass, setup, app, hass_client_no_auth):
    await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "message": "Có người ngã ở phòng khách"},
                                   blocking=True, return_response=True)
    rt = hass.data[DOMAIN][setup.entry_id]
    assert rt.voice.plans["555"].message == "Có người ngã ở phòng khách"
    client = await hass_client_no_auth()
    resp = await client.post("/api/webhook/wh-test", json={"event": "call", "status": "answered", "call_id": "555",
                                                         "thread_id": THREAD})
    assert resp.status == 200
    await _wait_path(app, "/api/call/end")
    paths = [r["path"] for r in app.requests]
    assert paths.index("/api/call/say") < paths.index("/api/call/end"), paths
    say = app.last("/api/call/say")
    assert b"TTS:" in say["raw"] and "Có người ngã ở phòng khách".encode() in say["raw"], say["raw"][:200]
    assert b'name="call_id"' in say["raw"] and b"555" in say["raw"]


async def test_say_in_call_service_speaks_on_given_call(hass, setup, app):
    await hass.services.async_call(DOMAIN, "say_in_call", {"call_id": "555", "message": "Thử loa", "wait": False},
                                   blocking=True, return_response=True)
    assert "Thử loa".encode() in app.last("/api/call/say")["raw"]


async def test_new_call_settings_are_entities_and_push_to_app(hass, setup, app):
    reg = er.async_get(hass)
    ids = {e.unique_id.split("_", 1)[-1] if e.unique_id else "": e.entity_id for e in reg.entities.values() if e.platform == DOMAIN}
    keys = " ".join(e.unique_id for e in reg.entities.values() if e.platform == DOMAIN)
    for k in ("auto_answer", "auto_answer_delay", "auto_answer_from", "ai_call", "ai_call_greeting"):
        assert k in keys, (k, keys)
    sw = next(e.entity_id for e in reg.entities.values() if e.platform == DOMAIN and e.unique_id.endswith("_auto_answer"))
    await hass.services.async_call("switch", "turn_on", {"entity_id": sw}, blocking=True)
    rt = hass.data[DOMAIN][setup.entry_id]
    assert rt.defaults.get("auto_answer") is True
    tx = next(e.entity_id for e in reg.entities.values() if e.platform == DOMAIN and e.unique_id.endswith("_auto_answer_from"))
    await hass.services.async_call("text", "set_value", {"entity_id": tx, "value": "6643404425553198601, 123"}, blocking=True)
    assert rt.defaults.get("auto_answer_from") == "6643404425553198601,123"
    with pytest.raises(Exception):
        await hass.services.async_call("text", "set_value", {"entity_id": tx, "value": "abc"}, blocking=True)
