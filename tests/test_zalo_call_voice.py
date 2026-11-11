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
    return SimpleNamespace(api=api, voice=cv.CallVoice(), defaults=_Defaults())


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

    async def fake_ai(hass_, api, call_id, plan, voice=None):
        started.append((call_id, plan.greeting, plan.hangup))
        return {"handover": False, "heard": ""}
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
        assert end_stage in (pl.PipelineStage.INTENT, pl.PipelineStage.STT)   # TTS do call_voice tự làm bằng giọng của pipeline
        assert "điện thoại" in (conversation_extra_system_prompt or "")  # nhắc trợ lý đang nói qua điện thoại
        assert cv.HANDOVER_MARK in conversation_extra_system_prompt       # và cách tự chuyển sang trực tiếp
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
        if p == "/api/contacts":
            return web.json_response({"friends": {"rows": [{"id": "6643404425553198601", "name": "Đại ca"},
                                                           {"id": "111", "name": "Đại Ngà"}]},
                                      "groups": {"rows": [{"id": "3133467193494275911", "name": "AI học hỏi"}]}})
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


async def test_take_over_stops_ai_and_restores_house_mic(hass, monkeypatch):
    """Tự nghe máy + AI, rồi người thật tiếp quản: AI dừng (không cúp máy), mic nhà được trả về."""
    started = asyncio.Event()

    async def long_ai(hass_, api, call_id, plan, voice=None):
        started.set()
        await asyncio.sleep(60)
        return {"handover": False, "heard": ""}
    monkeypatch.setattr(cv, "async_run_ai", long_ai)

    class Api(FakeApi):
        def __init__(self):
            super().__init__()
            self.media = []

        async def media_control(self, body):
            self.media.append(body)
            return {"mic": {"alive": False}}
    api = Api()
    rt = _rt(api)
    cv.on_call_state(hass, rt, "incoming", 77, TERMINAL, True, "")
    cv.on_call_state(hass, rt, "answered", 77, TERMINAL, True, "", "auto")
    await asyncio.wait_for(started.wait(), 5)
    assert "77" in rt.voice.tasks
    res = await cv.async_take_over(rt, "77")
    assert res == {"call_id": "77", "ai_was_running": True}
    await asyncio.sleep(0.05)
    assert "77" not in rt.voice.tasks and api.ended == []                      # AI dừng, KHÔNG cúp máy
    assert {"call_id": "77", "action": "start", "target": "mic"} in api.media        # mic nhà trả về
    res2 = await cv.async_take_over(rt, "77")                                  # không còn AI: vốn đã trực tiếp
    assert res2["ai_was_running"] is False
    api.calls_n = 0
    api2 = Api()
    with pytest.raises(cv.ZaloCallError):
        api2._statuses = ["ended"]
        await cv.async_take_over(_rt(api2), None)                              # không có cuộc nào đang nói


async def test_phone_hint_carries_custom_handover_rule():
    assert cv.HANDOVER_MARK in cv.phone_hint("")
    assert "người nghe nói cần giúp" in cv.phone_hint("Nếu người nghe nói cần giúp.")


async def _patched_ai_env(monkeypatch, script):
    from homeassistant.components import assist_pipeline
    from homeassistant.components.assist_pipeline import pipeline as pl
    fake = FakePipelineModule(script)
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
    return fake


async def test_ai_decides_handover_speaks_clean_reply_then_stops(hass, monkeypatch):
    fake = await _patched_ai_env(monkeypatch, [("tôi cần gặp người trong nhà", "Mình chuyển máy cho người nhà nhé [[CHUYEN_MAY]]"),
                                              ("không bao giờ tới", "x")])
    api = FakeApi(statuses=["answered"])
    res = await cv.async_run_ai(hass, api, "77", cv.Plan(ai=True))
    assert res == {"handover": True, "heard": "tôi cần gặp người trong nhà"}
    assert [s[2].decode() for s in api.said] == ["TTS:Mình chuyển máy cho người nhà nhé"]      # dấu KHÔNG được đọc ra
    assert fake.turn == 1                                                                      # dừng ngay sau khi chuyển


async def test_handover_keeps_call_open_restores_mic_and_fires_event(hass, monkeypatch):
    await _patched_ai_env(monkeypatch, [("giúp tôi với", "Có ai đó sẽ nói chuyện với bạn ngay [[chuyen_may]]")])
    events = []
    hass.bus.async_listen("zalo_call_ai_handover", lambda e: events.append(dict(e.data)))

    class Api(FakeApi):
        def __init__(self):
            super().__init__(statuses=["answered"])
            self.media = []

        async def media_control(self, body):
            self.media.append(body)
            return {"mic": {"alive": False}}
    api = Api()
    rt = _rt(api)
    await cv._run_plan(hass, rt, "77", cv.Plan(message="Phát hiện có người ngã", ai=True, hangup=True))
    await hass.async_block_till_done()
    assert api.ended == []                                                          # AI chuyển máy: KHÔNG cúp
    assert {"call_id": "77", "action": "start", "target": "mic"} in api.media       # mic nhà trả về
    assert events == [{"call_id": "77", "heard": "giúp tôi với"}]
    # không chuyển máy (hết cuộc trò chuyện) thì vẫn cúp như cũ
    api2 = Api()
    await _patched_ai_env(monkeypatch, [])
    await cv._run_plan(hass, _rt(api2), "77", cv.Plan(ai=True, hangup=True))
    assert api2.ended == ["77"]


# ---- LLM API «Zalo Call» (Assist) ------------------------------------------------------------------------------------
from homeassistant.core import Context  # noqa: E402
from homeassistant.helpers import llm  # noqa: E402
from custom_components.zalo_call import llm_api  # noqa: E402


def _ctx(context=None):
    return llm.LLMContext(platform="conversation", context=context or Context(), language="vi", assistant="conversation", device_id=None)


def test_match_people_ignores_accents_and_prefers_exact():
    rows = [{"id": "1", "name": "Đại ca"}, {"id": "2", "name": "Đại Ngà"}, {"id": "3", "name": "Bé Đại"}]
    assert [r["id"] for r in llm_api.match_people("dai ca", rows)] == ["1"]
    assert [r["id"] for r in llm_api.match_people("Đại", rows)] == ["1", "2", "3"]
    assert [r["id"] for r in llm_api.match_people("2", rows)] == ["2"]            # id đúng
    assert llm_api.match_people("", rows) == [] and llm_api.match_people("xyz", rows) == []


async def test_llm_api_registered_and_lists_call_tools_outside_a_call(hass, setup):
    api = await llm.async_get_api(hass, "zalo_call", _ctx())
    assert api.api.name == "Zalo Call"
    names = [t.name for t in api.tools]
    assert names == ["tim_nguoi", "goi_dien", "cuoc_goi", "dieu_khien_cuoc_goi", "noi_trong_cuoc_goi", "gui_tin"], names
    assert "tim_nguoi" in api.api_prompt and "chuyen_may_khi" in api.api_prompt


async def test_llm_tools_find_call_and_message_by_name(hass, setup, app):
    api = await llm.async_get_api(hass, "zalo_call", _ctx())

    async def call(name, **args):
        return await api.async_call_tool(llm.ToolInput(tool_name=name, tool_args=args))
    assert (await call("tim_nguoi", ten="dai ca"))["ket_qua"][0]["id"] == "6643404425553198601"
    assert "loi" in await call("tim_nguoi", ten="không có ai")
    amb = await call("goi_dien", nguoi="đại")                       # nhiều người khớp: phải hỏi lại, KHÔNG gọi
    assert len(amb["nhieu_ket_qua"]) == 2 and not [r for r in app.requests if r["path"] == "/api/call/request"]
    res = await call("goi_dien", nguoi="Đại ca", thong_bao="Có người ngã ở phòng khách", ai=True, chuyen_may_khi="người nghe nói cần giúp")
    assert res == {"da_lam": "dang_goi", "nguoi": "Đại ca"}
    assert app.last("/api/call/request")["path"] == "/api/call/request"
    plan = hass.data[DOMAIN][setup.entry_id].voice.plans["555"]
    assert plan.message == "Có người ngã ở phòng khách" and plan.ai and plan.handover_rule == "người nghe nói cần giúp"
    sent = await call("gui_tin", nguoi="Đại ca", noi_dung="Xin chào")
    assert sent["da_lam"] == "da_gui" and app.last("/api/thread/6643404425553198601/send")["json"]["message"] == "Xin chào"


async def test_in_call_ai_only_sees_the_transfer_tool_and_cannot_be_driven_by_the_caller(hass, setup, app):
    rt = hass.data[DOMAIN][setup.entry_id]
    ctx = Context()
    rt.voice.call_context_ids.add(ctx.id)
    api = await llm.async_get_api(hass, "zalo_call", _ctx(ctx))
    assert [t.name for t in api.tools] == ["chuyen_sang_truc_tiep"] and "MỘT công cụ" in api.api_prompt
    # dù model cố gọi công cụ khác trong cuộc gọi (người lạ sai khiến) cũng bị từ chối, và không có yêu cầu nào tới app
    full = await llm.async_get_api(hass, "zalo_call", _ctx())
    tool = next(t for t in full.tools if t.name == "goi_dien")
    out = await tool.async_call(hass, llm.ToolInput(tool_name="goi_dien", tool_args={"nguoi": "Đại ca"}), _ctx(ctx))
    assert "loi" in out and not [r for r in app.requests if r["path"] == "/api/call/request"]
    # chuyển máy: chưa có AI nào giữ cuộc gọi thì báo lỗi; có thì ghi nhận
    transfer = api.tools[0]
    assert "loi" in await transfer.async_call(hass, llm.ToolInput(tool_name="chuyen_sang_truc_tiep", tool_args={}), _ctx(ctx))
    rt.voice.ai_running.append("77")
    ok = await transfer.async_call(hass, llm.ToolInput(tool_name="chuyen_sang_truc_tiep", tool_args={"ly_do": "khẩn cấp"}), _ctx(ctx))
    assert "da_lam" in ok and rt.voice.handover == {"77": "khẩn cấp"}


async def test_ai_loop_handover_through_llm_tool(hass, monkeypatch):
    voice = cv.CallVoice()
    fake = await _patched_ai_env(monkeypatch, [("giúp tôi với", "Mình chuyển máy ngay")])
    orig = fake.run

    async def run_and_request_transfer(hass_, *, conversation_extra_system_prompt=None, **kw):
        voice.request_handover("khẩn cấp")                          # công cụ LLM được gọi trong lượt này
        return await orig(hass_, conversation_extra_system_prompt=conversation_extra_system_prompt, **kw)
    from homeassistant.components import assist_pipeline
    monkeypatch.setattr(assist_pipeline, "async_pipeline_from_audio_stream", run_and_request_transfer)
    api = FakeApi(statuses=["answered"])
    res = await cv.async_run_ai(hass, api, "77", cv.Plan(ai=True), voice)
    assert res["handover"] is True and [s[2].decode() for s in api.said] == ["TTS:Mình chuyển máy ngay"]
    assert voice.ai_running == [] and voice.handover == {} and voice.call_context_ids == set()      # dọn sạch


# ---- Phạm vi theo người gọi: trợ lý RIÊNG (giới hạn thật) + lời dặn mềm ---------------------------------------------------
class _Defaults(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


def test_pick_agent_tiers_by_caller():
    d = _Defaults(ai_call_agent="conversation.le_tan", ai_call_agent_trusted="conversation.nguoi_nha", ai_call_trusted="111, 222")
    assert cv.pick_agent(d, "999") == ("conversation.le_tan", False)             # người lạ (kể cả người trong danh bạ nhưng không tin cậy)
    assert cv.pick_agent(d, "111") == ("conversation.nguoi_nha", True)           # người tin cậy
    d2 = _Defaults(ai_call_agent="conversation.le_tan", ai_call_trusted="111")   # tin cậy nhưng chưa chọn trợ lý riêng cho họ
    assert cv.pick_agent(d2, "111") == ("conversation.le_tan", True)
    assert cv.pick_agent(_Defaults(), "111") == ("", False)                      # chưa cấu hình: dùng trợ lý của pipeline


def test_public_scope_hint_only_for_untrusted_callers():
    assert cv.PUBLIC_HINT in cv.phone_hint("", trusted=False)
    assert cv.PUBLIC_HINT not in cv.phone_hint("", trusted=True)
    assert cv.HANDOVER_MARK in cv.phone_hint("", trusted=True)


async def test_incoming_ai_picks_agent_by_caller_tier(hass, monkeypatch):
    seen = []

    async def fake_ai(hass_, api, call_id, plan, voice=None):
        seen.append((call_id, plan.agent_id, plan.trusted))
        return {"handover": False, "heard": ""}
    monkeypatch.setattr(cv, "async_run_ai", fake_ai)
    for cid, caller in (("71", "999"), ("72", "111")):
        rt = _rt(FakeApi())
        rt.defaults = _Defaults(ai_call_agent="conversation.le_tan", ai_call_agent_trusted="conversation.nguoi_nha", ai_call_trusted="111")
        cv.on_call_state(hass, rt, "incoming", cid, TERMINAL, True, "", "", "", caller)
        cv.on_call_state(hass, rt, "answered", cid, TERMINAL, True, "", "auto", "", caller)
        for _ in range(60):
            if len(seen) and seen[-1][0] == cid:
                break
            await asyncio.sleep(0.02)
    assert seen == [("71", "conversation.le_tan", False), ("72", "conversation.nguoi_nha", True)], seen


async def test_dedicated_agent_gets_the_question_pipeline_only_does_stt(hass, monkeypatch):
    """Có trợ lý riêng: pipeline dừng ở STT (không đi qua trợ lý của pipeline), câu hỏi tới ĐÚNG trợ lý được chọn."""
    from homeassistant.components import assist_pipeline
    from homeassistant.components.assist_pipeline import pipeline as pl
    from homeassistant.core import SupportsResponse
    from pytest_homeassistant_custom_component.common import async_mock_service
    stages = []

    async def run(hass_, *, context, event_callback, stt_metadata, stt_stream, end_stage=None, conversation_extra_system_prompt=None, **kw):
        stages.append(end_stage)
        async for _c in stt_stream:
            break
        event_callback(pl.PipelineEvent(pl.PipelineEventType.STT_END, {"stt_output": {"text": "đèn phòng khách đang bật không"}}))
    monkeypatch.setattr(assist_pipeline, "async_pipeline_from_audio_stream", run)
    monkeypatch.setattr(pl, "async_get_pipeline", lambda hass_, pid=None: SimpleNamespace(
        stt_language="vi", tts_engine=None, tts_language=None, tts_voice=None))
    calls = async_mock_service(hass, "conversation", "process", response={"conversation_id": "c9", "response": {"speech": {"plain": {"speech": "Mình không có thông tin đó ạ"}}}},
                               supports_response=SupportsResponse.OPTIONAL)

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
    api = FakeApi(statuses=["answered", "ended"])
    await cv.async_run_ai(hass, api, "77", cv.Plan(ai=True, agent_id="conversation.le_tan", trusted=False))
    assert stages and all(s == pl.PipelineStage.STT for s in stages)
    assert len(calls) == 1 and calls[0].data["agent_id"] == "conversation.le_tan"
    assert "đèn phòng khách đang bật không" in calls[0].data["text"] and cv.PUBLIC_HINT in calls[0].data["text"]
    assert [s[2].decode() for s in api.said] == ["TTS:Mình không có thông tin đó ạ"]
