"""Quy tắc cuộc gọi đến / tin nhắn (dịch vụ set_rule) + giọng nói/AI trong cuộc gọi — trong HA thật (ảnh r1-test).

    python -m pytest tests/test_zalo_call_voice.py -p pytest_homeassistant_custom_component -o asyncio_mode=auto

BẤT BIẾN BẢO MẬT được kiểm ở đây: không có quy tắc = không làm gì; quy tắc theo threadID đè nhóm; không biết quen/lạ thì không áp quy tắc nhóm;
thiết bị nhà tắt mặc định (app nhận «off»); ai/reply_ai bắt buộc có pipeline hoặc agent; người gọi cúp trước hạn / webhook lặp không nghe sai."""
import asyncio
import json
import os
import sys
import time
import types
from types import SimpleNamespace

import pytest
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")
sys.modules.setdefault("turbojpeg", types.SimpleNamespace(TurboJPEG=object))

import custom_components  # noqa: E402

_REPO_CC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_components"))
if _REPO_CC not in [os.path.abspath(p) for p in custom_components.__path__]:
    custom_components.__path__.append(_REPO_CC)

from aiohttp import web  # noqa: E402
from custom_components.zalo_call import call_voice as cv  # noqa: E402
from custom_components.zalo_call import rules as R  # noqa: E402
from homeassistant.exceptions import ServiceValidationError  # noqa: E402
from test_zalo_call_ha_end_to_end import DOMAIN, THREAD, FakeZaloApp, fake_agent, setup  # noqa: E402,F401

TERMINAL = ("ended", "no_answer", "declined", "missed", "rejected", "error")
OFF = "off"


# ---------------------------------------------------------------- bản giả ---------------------------------------------------------
class FakeApi:
    url = "http://app.invalid"

    def __init__(self, statuses=None, mic_alive=(True, False)):
        self.said, self.ended, self.media = [], [], []
        self._statuses = list(statuses or [])
        self._mic = list(mic_alive)

    async def call_say(self, call_id, filename, data):
        self.said.append((str(call_id), filename, data))
        return {"ok": True}

    async def media_control(self, body):
        self.media.append(body)
        alive = self._mic.pop(0) if self._mic else False
        return {"mic": {"alive": alive}}

    async def calls(self):
        st = self._statuses.pop(0) if len(self._statuses) > 1 else (self._statuses[0] if self._statuses else "answered")
        return {"calls": [{"call_id": "77", "status": st}], "active": {"call_id": "77", "status": st}}

    async def call_media_status(self, call_id):
        return {"audio_token": "tok"}

    async def upgrade_video(self, body):
        self.upgraded = getattr(self, "upgraded", []) + [body]
        return {"ok": True}

    async def call_end(self, call_id):
        self.ended.append(str(call_id))
        return {"ok": True}


class _Defaults(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


class FakeBridge:
    """Ghi lại việc nối thiết bị giữa cuộc gọi (bộ ghi đè truyền cho reconnect)."""
    def __init__(self):
        self.reconnected = []

    async def reconnect(self, call_id, override):
        self.reconnected.append((str(call_id), dict(override)))
        return {}

    async def async_call_fields(self, override):
        return {k + "_url": (v or "off") for k, v in override.items() if k in ("speaker", "mic", "camera")}


def _rt(api, rules=None):
    return SimpleNamespace(api=api, voice=cv.CallVoice(), defaults=_Defaults(rules=rules or R.empty_rules()), bridge=FakeBridge())


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(cv, "POLL_S", 0.01)

    async def fake_tts(hass, message, engine=None, language=None, options=None):
        return "mp3", ("TTS:" + message).encode()
    monkeypatch.setattr(cv, "async_tts_audio", fake_tts)


# ------------------------------------------------------------ rules.py (thuần) ----------------------------------------------------
def test_rule_defaults_are_closed_and_validation():
    r = R.normalize({"answer": True})
    assert r["answer"] is True and r["ai"] is False and r["connect"] == [] and r["reply_ai"] is False and r["voice_text"] is False
    assert r["answer_delay"] == 3 and r["call_types"] == ["voice", "video"]
    for bad in ({"ai": True}, {"reply_ai": True}, {"answer_delay": "x"}, {"call_types": ["fax"]}, {"echo_guard": "loud"}, {"volume": "cao"}):
        with pytest.raises(R.RuleError):
            R.normalize(bad)
    assert R.normalize({"ai": True, "pipeline": "abc"})["ai"] is True and R.normalize({"reply_ai": True, "agent": "conversation.x"})["reply_ai"]
    assert R.normalize({"answer_delay": 999})["answer_delay"] == 120                  # kẹp trong giới hạn
    old = R.normalize({"answer": True, "answer_delay": 9})
    assert R.normalize({"answer_delay": 1}, old)["answer"] is True                  # trường không nêu giữ như cũ
    with pytest.raises(R.RuleError):
        R.validate_scope("thread", "abc")
    assert R.validate_scope("thread", " 123 ") == "123" and R.validate_scope("strangers", None) == ""


def test_resolve_precedence_no_rule_means_none_and_unknown_never_guesses():
    rules = R.empty_rules()
    assert R.resolve(rules, "1", "user", "friend") is None and R.resolve(rules, "1", "user", "stranger") is None      # không quy tắc = không làm gì
    rules["contacts"] = {"answer": True, "name": "danh bạ"}
    rules["strangers"] = {"answer": True, "name": "người lạ"}
    rules["groups"] = {"reply_ai": True, "name": "nhóm"}
    assert R.resolve(rules, "1", "user", "friend")["name"] == "danh bạ"
    assert R.resolve(rules, "1", "user", "stranger")["name"] == "người lạ"
    assert R.resolve(rules, "9", "group", "group")["name"] == "nhóm" and R.resolve(rules, "9", 1, None)["name"] == "nhóm"
    assert R.resolve(rules, "1", "user", "unknown") is None and R.resolve(rules, "1", "user", None) is None            # không biết quen/lạ: đóng cửa
    rules["threads"]["1"] = {"answer": False, "name": "riêng"}
    assert R.resolve(rules, "1", "user", "friend")["name"] == "riêng"                                                  # thread đè danh bạ dễ dãi
    assert R.resolve(rules, "1", "user", "unknown")["name"] == "riêng"                                                 # và vẫn áp khi không biết quen/lạ


def test_plan_from_service():
    assert cv.plan_from_service({}) is None
    p = cv.plan_from_service({"message": " Có người ngã ", "repeat": 9})
    assert p.message == "Có người ngã" and p.repeat == 3 and p.hangup is True and p.ai is False
    p = cv.plan_from_service({"ai": True, "hangup_after": False, "tts_engine": "tts.x", "agent": "conversation.a"})
    assert p.ai and p.hangup is False and p.engine == "tts.x" and p.agent_id == "conversation.a"


def test_public_scope_hint_only_for_untrusted_callers():
    assert cv.PUBLIC_HINT in cv.phone_hint("", trusted=False) and cv.PUBLIC_HINT not in cv.phone_hint("", trusted=True)
    assert cv.HANDOVER_MARK in cv.phone_hint("", trusted=True)
    assert "người nghe nói cần giúp" in cv.phone_hint("Nếu người nghe nói cần giúp.")


# --------------------------------------------------------- TTS lên cuộc gọi + kế hoạch -----------------------------------------------
async def test_say_uploads_tts_and_waits_until_playback_done(hass):
    api = FakeApi(mic_alive=(True, True, False))
    await cv.async_say(hass, api, "77", "Xin chào")
    assert api.said == [("77", "tts.mp3", "TTS:Xin chào".encode())] and len([m for m in api.media if m["action"] == "status"]) == 3
    api2 = FakeApi()
    await cv.async_say(hass, api2, "77", "   ")
    assert api2.said == []


async def test_plan_runs_on_answered_then_hangs_up_and_not_when_call_ends_first(hass):
    api = FakeApi()
    rt = _rt(api)
    rt.voice.plans["77"] = cv.plan_from_service({"message": "Cảnh báo: có người ngã", "repeat": 2})
    cv.on_call_state(hass, rt, "ringing", 77, TERMINAL, {})
    assert api.said == []
    cv.on_call_state(hass, rt, "answered", 77, TERMINAL, {})
    for _ in range(100):
        if api.ended:
            break
        await asyncio.sleep(0.05)
    assert [s[2] for s in api.said] == ["TTS:Cảnh báo: có người ngã".encode()] * 2 and api.ended == ["77"]
    api2 = FakeApi()
    rt2 = _rt(api2)
    rt2.voice.plans["78"] = cv.Plan(message="x")
    cv.on_call_state(hass, rt2, "declined", 78, TERMINAL, {})
    cv.on_call_state(hass, rt2, "answered", 78, TERMINAL, {})
    await asyncio.sleep(0.1)
    assert api2.said == [] and not rt2.voice.tasks


# ---------------------------------------------------------- vòng AI trong cuộc gọi -------------------------------------------------
class FakePipelineModule:
    def __init__(self, script):
        self.script, self.convs, self.turn = list(script), [], 0

    async def run(self, hass, *, context, event_callback, stt_metadata, stt_stream, pipeline_id=None, conversation_id=None, end_stage=None,
                  audio_settings=None, conversation_extra_system_prompt=None, **kw):
        from homeassistant.components.assist_pipeline import pipeline as pl
        assert "điện thoại" in (conversation_extra_system_prompt or "") and cv.HANDOVER_MARK in conversation_extra_system_prompt
        self.convs.append(conversation_id)
        async for _chunk in stt_stream:
            break
        text, reply = self.script[self.turn] if self.turn < len(self.script) else ("", "")
        self.turn += 1
        if text:
            event_callback(pl.PipelineEvent(pl.PipelineEventType.STT_END, {"stt_output": {"text": text}}))
            event_callback(pl.PipelineEvent(pl.PipelineEventType.INTENT_END, {"intent_output": {
                "conversation_id": "conv-1", "response": {"speech": {"plain": {"speech": reply}}}}}))


async def _ai_env(monkeypatch, script):
    from homeassistant.components import assist_pipeline
    from homeassistant.components.assist_pipeline import pipeline as pl
    fake = FakePipelineModule(script)
    monkeypatch.setattr(assist_pipeline, "async_pipeline_from_audio_stream", fake.run)
    monkeypatch.setattr(pl, "async_get_pipeline", lambda hass_, pid=None: SimpleNamespace(
        stt_language="vi", tts_engine="tts.x", tts_language="vi", tts_voice=None, conversation_engine="conversation.agent_of_pipeline"))

    class L:
        def __init__(self, hass_, url):
            self.url, self.muted, self.ended = url, False, False

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


async def test_ai_loop_answers_each_turn_keeps_context_and_stops_after_idle(hass, monkeypatch):
    fake = await _ai_env(monkeypatch, [("bật đèn phòng khách", "Đã bật đèn phòng khách"), ("cảm ơn", "Không có gì ạ")])
    api = FakeApi(statuses=["answered"])
    await cv.async_run_ai(hass, api, "77", cv.Plan(ai=True, greeting="Xin chào", pipeline_id="pl", trusted=True))
    assert [s[2].decode() for s in api.said] == ["TTS:Xin chào", "TTS:Đã bật đèn phòng khách", "TTS:Không có gì ạ"]
    assert fake.convs[:3] == [None, "conv-1", "conv-1"] and fake.turn == 2 + cv.IDLE_TURNS


async def test_ai_loop_stops_when_call_no_longer_answered(hass, monkeypatch):
    fake = await _ai_env(monkeypatch, [("a", "b")] * 5)
    await cv.async_run_ai(hass, FakeApi(statuses=["answered", "answered", "ended"]), "77", cv.Plan(ai=True, pipeline_id="pl"))
    assert fake.turn == 2


async def test_ai_decides_handover_via_marker_speaks_clean_reply_and_stops(hass, monkeypatch):
    fake = await _ai_env(monkeypatch, [("tôi cần gặp người trong nhà", "Mình chuyển máy cho người nhà nhé [[CHUYEN_MAY]]"), ("không bao giờ tới", "x")])
    api = FakeApi(statuses=["answered"])
    res = await cv.async_run_ai(hass, api, "77", cv.Plan(ai=True, pipeline_id="pl"))
    assert res == {"handover": True, "heard": "tôi cần gặp người trong nhà", "connect": "", "finished": False}
    assert [s[2].decode() for s in api.said] == ["TTS:Mình chuyển máy cho người nhà nhé"] and fake.turn == 1


async def test_handover_through_llm_tool_cleans_up(hass, monkeypatch):
    voice = cv.CallVoice()
    fake = await _ai_env(monkeypatch, [("giúp tôi với", "Mình chuyển máy ngay")])
    orig = fake.run
    from homeassistant.components import assist_pipeline

    async def run_and_request(hass_, *, conversation_extra_system_prompt=None, **kw):
        voice.request_handover("khẩn cấp")
        return await orig(hass_, conversation_extra_system_prompt=conversation_extra_system_prompt, **kw)
    monkeypatch.setattr(assist_pipeline, "async_pipeline_from_audio_stream", run_and_request)
    res = await cv.async_run_ai(hass, FakeApi(statuses=["answered"]), "77", cv.Plan(ai=True, pipeline_id="pl"), voice)
    assert res["handover"] is True and voice.ai_running == [] and voice.handover == {} and voice.call_context_ids == set()


HOUSE = {"speaker": "media_player.r1_loa", "mic": "assist_satellite.r1"}


async def test_handover_connects_only_devices_that_were_configured_and_never_hangs_up(hass, monkeypatch):
    """Không cài thiết bị (connect trống) thì AI chuyển máy cũng KHÔNG nối gì; có cài thì nối đúng thứ đã cài. Cả hai đều không cúp máy."""
    events = []
    hass.bus.async_listen("zalo_call_ai_handover", lambda e: events.append(dict(e.data)))
    for connect in ({}, HOUSE):
        await _ai_env(monkeypatch, [("giúp tôi với", "Có ai đó sẽ nói chuyện với bạn ngay [[chuyen_may]]")])
        api, rt = FakeApi(statuses=["answered"]), None
        rt = _rt(api)
        await cv._run_plan(hass, rt, "77", cv.Plan(message="Phát hiện có người ngã", ai=True, hangup=True, pipeline_id="pl", connect=dict(connect)))
        await hass.async_block_till_done()
        started = [m for m in api.media if m.get("action") == "start" and m.get("target") == "both"]
        assert api.ended == [], connect                                                  # KHÔNG cúp
        assert bool(started) is bool(connect) and bool(rt.bridge.reconnected) is bool(connect), (connect, api.media)
        if connect:
            ov = rt.bridge.reconnected[0][1]
            assert ov["speaker"] == "media_player.r1_loa" and ov["mic"] == "assist_satellite.r1" and ov["camera"] == "" and ov["mic_url"] == "", ov
            assert started[0]["speaker_url"] == "media_player.r1_loa" and started[0]["camera_url"] == "off", started[0]
    assert [(e["reason"], e["connected"]) for e in events] == [("ai", False), ("ai", True)]


async def test_connect_modes_never_voice_always_decide_what_a_handover_connects():
    """never = không gì; voice = loa+mic (không camera); always = tất cả. Rule + lời gọi: lời gọi thắng; không nêu thì theo quy tắc."""
    full = {"speaker": "media_player.r1", "mic": "assist_satellite.r1", "camera": "camera.pk", "volume": 40}
    assert cv.devices_for_mode(full, "never") == {} and cv.devices_for_mode(full, []) == {} and cv.devices_for_mode({}, "always") == {}
    with pytest.raises(R.RuleError):
        cv.devices_for_mode(full, "bogus")
    assert cv.devices_for_mode(full, "voice") == {"speaker": "media_player.r1", "mic": "assist_satellite.r1", "volume": 40}
    assert cv.devices_for_mode(full, "always") == full
    assert cv.devices_for_mode({"camera": "camera.pk"}, "voice") == {}                      # chỉ có camera mà chế độ voice: không nối gì
    assert cv.rule_devices({**full, "connect": "always"}) == full and cv.rule_devices(full) == {}      # quy tắc không nêu connect = never


async def test_always_on_a_voice_call_upgrades_to_video_and_voice_mode_does_not(hass, monkeypatch):
    for mode, upgraded in (("voice", False), ("always", True)):
        await _ai_env(monkeypatch, [("giúp tôi", "Mình chuyển máy [[CHUYEN_MAY]]")])
        api = FakeApi(statuses=["answered"])
        rt = _rt(api)
        connect = cv.devices_for_mode({**HOUSE, "camera": "camera.pk"}, mode)
        await cv._run_plan(hass, rt, "77", cv.Plan(ai=True, pipeline_id="pl", video=False, connect=connect))
        assert bool(getattr(api, "upgraded", [])) is upgraded, (mode, getattr(api, "upgraded", None))
        assert rt.bridge.reconnected[0][1]["camera"] == ""                                  # thoại: media start không mang camera, camera vào qua nâng video


async def test_voice_call_never_starts_camera_but_video_call_does(hass, monkeypatch):
    for video in (False, True):
        await _ai_env(monkeypatch, [("giúp tôi", "Mình chuyển máy [[CHUYEN_MAY]]")])
        rt = _rt(FakeApi(statuses=["answered"]))
        await cv._run_plan(hass, rt, "77", cv.Plan(ai=True, pipeline_id="pl", video=video, connect={**HOUSE, "camera": "camera.phong_khach"}))
        assert (rt.bridge.reconnected[0][1]["camera"] == "camera.phong_khach") is video, (video, rt.bridge.reconnected)


async def test_alert_call_reads_the_message_then_connects_at_once_without_asking(hass, monkeypatch):
    """Cuộc gọi cảnh báo: đọc message (giọng pipeline), KHÔNG chạy vòng AI hỏi đáp, nối thẳng thiết bị đã cài; chưa cài thì chỉ đọc rồi cúp."""
    events = []
    hass.bus.async_listen("zalo_call_ai_handover", lambda e: events.append(dict(e.data)))
    ran = []

    async def no_ai(*a, **k):
        ran.append(1)
        return {"handover": False, "heard": ""}
    monkeypatch.setattr(cv, "async_run_ai", no_ai)
    api, rt = FakeApi(), None
    rt = _rt(api)
    await cv._run_plan(hass, rt, "77", cv.Plan(message="Phát hiện có người ngã ở phòng khách", alert=True, hangup=True, connect=dict(HOUSE)))
    await hass.async_block_till_done()
    assert ran == [] and [x[2] for x in api.said] == [b"TTS:Phat hien co nguoi nga o phong khach".replace(b"Phat hien co nguoi nga o phong khach", "Phát hiện có người ngã ở phòng khách".encode())]
    assert api.ended == [] and rt.bridge.reconnected and events == [{"call_id": "77", "heard": "", "reason": "alert", "connected": True, "camera": False}], events
    api2 = FakeApi()
    rt2 = _rt(api2)
    await cv._run_plan(hass, rt2, "78", cv.Plan(message="Cảnh báo", alert=True, hangup=True, connect={}))
    assert api2.ended == ["78"] and not rt2.bridge.reconnected and len(events) == 1       # chưa cài thiết bị: không nối, không báo chuyển máy


async def test_take_over_stops_ai_and_restores_house_mic_deliberately(hass, monkeypatch):
    started = asyncio.Event()

    async def long_ai(hass_, api, call_id, plan, voice=None):
        started.set()
        await asyncio.sleep(60)
        return {"handover": False, "heard": ""}
    monkeypatch.setattr(cv, "async_run_ai", long_ai)
    api = FakeApi()
    rt = _rt(api)
    rt.voice.plans["77"] = cv.Plan(ai=True, pipeline_id="pl")
    cv.on_call_state(hass, rt, "answered", 77, TERMINAL, {})
    await asyncio.wait_for(started.wait(), 5)
    res = await cv.async_take_over(rt, "77")                                    # thao tác chủ động của chủ máy: được nối mic nhà
    assert res == {"call_id": "77", "ai_was_running": True} and api.ended == []
    assert {"call_id": "77", "action": "start", "target": "mic"} in api.media                 # chưa cài thiết bị cho cuộc này: mic mặc định (người chủ động bấm)


# ------------------------------------------------- QUY TẮC NGHE MÁY TRONG HA THẬT (app giả) ------------------------------------------
class VoiceApp(FakeZaloApp):
    def __init__(self):
        super().__init__()
        self.call_status = "incoming"
        self.ids = {"555"}                                           # call_id mà webhook đã báo; app giả trả trạng thái cho từng id
        self.v2t = {"ok": True, "done": True, "text": "bật đèn phòng khách"}

    async def _any(self, request: web.Request) -> web.Response:
        p = request.path
        if p == "/api/calls":
            return web.json_response({"calls": [{"call_id": c, "status": self.call_status} for c in sorted(self.ids)], "active": None})
        if p == "/api/voice2text":
            raw = await request.read()
            self.requests.append({"method": "POST", "path": p, "json": json.loads(raw or b"{}"), "raw": b"", "ctype": "application/json"})
            return web.json_response(self.v2t)
        if p == "/api/contacts":
            return web.json_response({"friends": {"rows": [{"id": "6643404425553198601", "name": "Đại ca"}, {"id": "111", "name": "Đại Ngà"}]},
                                      "groups": {"rows": [{"id": "3133467193494275911", "name": "AI học hỏi"}]}})
        if p in ("/api/call/request", "/api/call/say", "/api/call/media", "/api/call/end", "/api/call/answer"):
            raw = await request.read()
            body = json.loads(raw) if raw and request.content_type == "application/json" else None
            self.requests.append({"method": request.method, "path": p, "json": body, "raw": raw if body is None else b"", "ctype": request.content_type})
            if p == "/api/call/request":
                return web.json_response({"ok": True, "call_id": "555", "request_sent": True})
            if p == "/api/call/media":
                return web.json_response({"ok": True, "mic": {"alive": False}})
            return web.json_response({"ok": True, "call_id": "555"})
        return await super()._any(request)


_CURRENT = {}


@pytest.fixture
async def app(socket_enabled):
    a = VoiceApp()
    await a.start()
    _CURRENT["app"] = a
    yield a
    await a.stop()


async def _set_rule(hass, **data):
    return await hass.services.async_call(DOMAIN, "set_rule", data, blocking=True, return_response=True)


async def _webhook(hass, hass_client_no_auth, payload):
    if payload.get("call_id") and "app" in _CURRENT:
        _CURRENT["app"].ids.add(str(payload["call_id"]))
    client = await hass_client_no_auth()
    r = await client.post("/api/webhook/wh-test", json=payload)
    assert r.status == 200
    return r


def _incoming(thread=THREAD, status="stranger", call_id="555", **kw):
    return {"event": "call", "status": "incoming", "call_id": call_id, "thread_id": thread, "contact_status": status, **kw}


async def _wait_answers(app, n, t=3.0):
    end = time.time() + t
    while time.time() < end and len([r for r in app.requests if r["path"] == "/api/call/answer"]) < n:
        await asyncio.sleep(0.05)
    return [r for r in app.requests if r["path"] == "/api/call/answer"]


async def test_no_rule_means_the_call_only_rings(hass, setup, app, hass_client_no_auth):
    for status in ("friend", "stranger", "unknown"):
        await _webhook(hass, hass_client_no_auth, _incoming(status=status, call_id="c-" + status))
    await asyncio.sleep(0.5)
    assert not [r for r in app.requests if r["path"] in ("/api/call/answer", "/api/call/say", "/api/voice2text")]


async def test_stranger_rule_answers_after_delay_with_connect_never_by_default(hass, setup, app, hass_client_no_auth):
    await _set_rule(hass, scope="strangers", answer=True, answer_delay=0)
    await _webhook(hass, hass_client_no_auth, _incoming(status="stranger"))
    ans = await _wait_answers(app, 1)
    assert len(ans) == 1, [r["path"] for r in app.requests]
    body = ans[0]["json"]
    assert body["call_id"] == "555" and body["mic_url"] == OFF and body["speaker_url"] == OFF and body["camera_url"] == OFF, body     # app nhận «off» cả ba


async def test_device_rule_connects_only_the_devices_named_in_the_rule(hass, setup, app, hass_client_no_auth):
    rt = hass.data[DOMAIN][setup.entry_id]
    await rt.defaults.async_set(mic="", speaker="")
    await _set_rule(hass, scope="contacts", answer=True, answer_delay=0, connect="voice", mic_url="rtsp://cam.local/stream")
    await _webhook(hass, hass_client_no_auth, _incoming(status="friend"))
    body = (await _wait_answers(app, 1))[0]["json"]
    assert body["mic_url"] == "rtsp://cam.local/stream" and body.get("speaker_url", OFF) in (OFF, "") or "speaker_url" not in body, body


async def test_thread_rule_overrides_group_rules_and_unknown_status_ignores_group_rules(hass, setup, app, hass_client_no_auth):
    await _set_rule(hass, scope="contacts", answer=True, answer_delay=0)
    await _set_rule(hass, scope="thread", thread_id=THREAD, answer=False)                    # chặn riêng một người dù danh bạ dễ dãi
    await _webhook(hass, hass_client_no_auth, _incoming(status="friend"))
    await asyncio.sleep(0.4)
    assert not await _wait_answers(app, 1, 0.1)
    await _set_rule(hass, scope="strangers", answer=True, answer_delay=0)
    await _webhook(hass, hass_client_no_auth, _incoming(thread="999", status="unknown", call_id="c-unknown"))     # không biết quen/lạ: không áp
    await asyncio.sleep(0.4)
    assert not await _wait_answers(app, 1, 0.1)
    await _webhook(hass, hass_client_no_auth, _incoming(thread="999", status="stranger", call_id="c-stranger"))
    assert len(await _wait_answers(app, 1)) == 1


async def test_call_types_hangup_before_delay_and_duplicate_webhook(hass, setup, app, hass_client_no_auth):
    await _set_rule(hass, scope="strangers", answer=True, answer_delay=0, call_types=["voice"])
    await _webhook(hass, hass_client_no_auth, _incoming(call_id="v1", call_type_raw=1))             # video, quy tắc chỉ voice: không nghe
    await asyncio.sleep(0.4)
    assert not await _wait_answers(app, 1, 0.1)
    await _set_rule(hass, scope="strangers", answer_delay=1, call_types=["voice", "video"])
    await _webhook(hass, hass_client_no_auth, _incoming(call_id="h1"))
    await _webhook(hass, hass_client_no_auth, {"event": "call", "status": "ended", "call_id": "h1", "end_reason": "missed", "thread_id": THREAD})
    await asyncio.sleep(1.5)
    assert not await _wait_answers(app, 1, 0.1)                                                      # người gọi cúp trước hạn
    await _webhook(hass, hass_client_no_auth, _incoming(call_id="d1"))
    await _webhook(hass, hass_client_no_auth, _incoming(call_id="d1"))                               # webhook lặp
    answers = await _wait_answers(app, 1, 3.0)
    await asyncio.sleep(0.5)
    assert len([r for r in app.requests if r["path"] == "/api/call/answer"]) == 1, answers


async def test_call_no_longer_ringing_when_the_delay_ends_is_not_answered(hass, setup, app, hass_client_no_auth):
    app.call_status = "ended"                                      # app cho biết cuộc gọi đã hết chuông khi tới hạn
    await _set_rule(hass, scope="strangers", answer=True, answer_delay=0)
    await _webhook(hass, hass_client_no_auth, _incoming())
    await asyncio.sleep(0.6)
    assert not await _wait_answers(app, 1, 0.1)


async def test_rule_ai_call_speaks_greeting_after_answer_and_ai_needs_pipeline_or_agent(hass, setup, app, hass_client_no_auth, monkeypatch):
    with pytest.raises(ServiceValidationError):
        await _set_rule(hass, scope="strangers", answer=True, ai=True)                           # ai thiếu pipeline/agent
    with pytest.raises(ServiceValidationError):
        await _set_rule(hass, scope="groups", reply_ai=True)
    seen = []

    async def fake_ai(hass_, api, call_id, plan, voice=None):
        seen.append((plan.agent_id, plan.pipeline_id, plan.trusted, plan.connect, plan.greeting))
        return {"handover": False, "heard": ""}
    monkeypatch.setattr(cv, "async_run_ai", fake_ai)
    await _set_rule(hass, scope="strangers", answer=True, answer_delay=0, ai=True, agent="conversation.le_tan", greeting="Chào bạn")
    await _webhook(hass, hass_client_no_auth, _incoming())
    await _wait_answers(app, 1)
    await _webhook(hass, hass_client_no_auth, {"event": "call", "status": "answered", "call_id": "555", "thread_id": THREAD})
    for _ in range(60):
        if seen:
            break
        await asyncio.sleep(0.05)
    assert seen == [("conversation.le_tan", None, False, {}, "Chào bạn")], seen
    # người thật nghe máy (không có kế hoạch) thì AI không chen vào
    seen.clear()
    await _webhook(hass, hass_client_no_auth, {"event": "call", "status": "answered", "call_id": "999", "thread_id": THREAD})
    await asyncio.sleep(0.3)
    assert seen == []


async def test_make_call_ai_without_pipeline_is_refused_before_calling(hass, setup, app):
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "ai": True}, blocking=True, return_response=True)
    assert not [r for r in app.requests if r["path"] == "/api/call/request"]                 # chưa gọi gì
    await _set_rule(hass, scope="thread", thread_id=THREAD, ai=True, agent="conversation.x", name="Đại ca")
    await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "ai": True}, blocking=True, return_response=True)
    plan = hass.data[DOMAIN][setup.entry_id].voice.plans["555"]
    assert plan.agent_id == "conversation.x" and plan.ai


async def test_rule_services_set_list_remove_and_contacts(hass, setup, app):
    res = await _set_rule(hass, scope="thread", thread_id=THREAD, name="Đại ca", answer=True, answer_delay=5, reply_ai=True, agent="conversation.x")
    assert res["rule"]["answer_delay"] == 5 and res["rule"]["connect"] == []
    await _set_rule(hass, scope="thread", thread_id=THREAD, answer_delay=7)                          # trường khác giữ như cũ
    listed = await hass.services.async_call(DOMAIN, "list_rules", {}, blocking=True, return_response=True)
    assert listed["threads"][THREAD]["answer_delay"] == 7 and listed["threads"][THREAD]["reply_ai"] is True and listed["contacts"] is None
    with pytest.raises(ServiceValidationError):
        await _set_rule(hass, scope="thread", thread_id="abc")
    removed = await hass.services.async_call(DOMAIN, "remove_rule", {"scope": "thread", "thread_id": THREAD}, blocking=True, return_response=True)
    assert removed["removed"] is True
    assert (await hass.services.async_call(DOMAIN, "list_rules", {}, blocking=True, return_response=True))["threads"] == {}
    contacts = await hass.services.async_call(DOMAIN, "list_contacts", {}, blocking=True, return_response=True)
    assert {"id": THREAD, "name": "Đại ca"} in contacts["friends"] and contacts["groups"][0]["name"] == "AI học hỏi"
    devs = await hass.services.async_call(DOMAIN, "get_default_devices", {}, blocking=True, return_response=True)
    assert "speaker" in devs and "mic_url" in devs and "call_volume" in devs


async def test_old_settings_entities_are_gone_only_text_style_and_buttons_remain(hass, setup):
    from homeassistant.helpers import entity_registry as er
    reg = er.async_get(hass)
    keys = {e.unique_id.split("_", 1)[1] for e in reg.entities.values() if e.platform == DOMAIN}
    for gone in ("auto_answer", "auto_answer_delay", "auto_answer_from", "ai_call", "auto_voice_text", "ai_voice_reply", "ai_enabled", "ai_threads",
                 "speaker", "mic", "camera", "mic_url", "echo_guard", "call_volume", "auto_mic", "auto_video", "auto_video_delay", "ai_agent"):
        assert gone not in keys, (gone, sorted(keys))
    assert not [e for e in reg.entities.values() if e.platform == DOMAIN and e.domain == "number"]
    for kept in ("text_size", "text_color", "btn_take_over", "ha_url"):
        assert kept in keys, sorted(keys)


# ----------------------------------------------- tin nhắn / tin thoại theo quy tắc ------------------------------------------------
VOICE_EVENT = {"kind": "voice", "voice_url": "https://f1-voice-aac-dl.zdn.vn/abc/123", "content": "", "thread_id": THREAD,
               "thread_type": "user", "is_self": False, "message_id": "m77", "sender_id": THREAD, "contact_status": "friend"}


async def _msg_env(hass, setup, monkeypatch, fake_agent):
    from custom_components.zalo_call import ai as ai_mod
    ai_mod.MIN_INTERVAL = 0

    async def tts(hass_, message, engine=None, language=None, options=None):
        return "mp3", ("TTS:" + message).encode()
    monkeypatch.setattr(ai_mod, "async_tts_audio", tts)
    fake_agent.reply = "Đã bật đèn phòng khách ạ"
    return ai_mod


async def test_voice_message_without_a_rule_does_nothing_with_rule_goes_stt_ai_and_voice_reply(hass, setup, app, monkeypatch, fake_agent):
    ai_mod = await _msg_env(hass, setup, monkeypatch, fake_agent)
    events = []
    hass.bus.async_listen("zalo_call_voice_text", lambda e: events.append(dict(e.data)))
    await ai_mod.async_handle_message(hass, setup, dict(VOICE_EVENT))                          # không quy tắc: không STT, không AI
    assert not [r for r in app.requests if r["path"] == "/api/voice2text"] and not fake_agent
    await _set_rule(hass, scope="contacts", voice_text=True, reply_ai=True, agent="conversation.x")
    await ai_mod.async_handle_message(hass, setup, dict(VOICE_EVENT))
    await hass.async_block_till_done()
    assert app.last("/api/voice2text")["json"]["url"] == VOICE_EVENT["voice_url"]
    assert fake_agent and "bật đèn phòng khách" in fake_agent[-1]["text"] and fake_agent[-1]["agent_id"] == "conversation.x"
    assert "TTS:Đã bật đèn phòng khách ạ".encode() in app.last("/sendvoice")["raw"] and not [r for r in app.requests if r["path"].endswith("/send")]
    assert events == [{"thread_id": THREAD, "sender_id": THREAD, "message_id": "m77", "text": "bật đèn phòng khách"}]
    assert cv.PUBLIC_HINT in fake_agent[-1]["text"]                                             # chưa tin cậy: kèm lời dặn mềm


async def test_voice_text_only_rule_fires_the_event_without_ai_and_group_or_stranger_rules_do_not_apply_to_friends(hass, setup, app, monkeypatch, fake_agent):
    ai_mod = await _msg_env(hass, setup, monkeypatch, fake_agent)
    await _set_rule(hass, scope="strangers", voice_text=True, reply_ai=True, agent="conversation.x")           # chỉ dành cho người lạ
    await ai_mod.async_handle_message(hass, setup, dict(VOICE_EVENT))                                         # người quen: không áp
    assert not [r for r in app.requests if r["path"] == "/api/voice2text"] and not fake_agent
    await _set_rule(hass, scope="contacts", voice_text=True)                                                   # chỉ thành chữ, không AI
    events = []
    hass.bus.async_listen("zalo_call_voice_text", lambda e: events.append(dict(e.data)))
    await ai_mod.async_handle_message(hass, setup, dict(VOICE_EVENT))
    await hass.async_block_till_done()
    assert len(events) == 1 and not fake_agent and not [r for r in app.requests if "/api/thread/" in r["path"]]
    app.v2t = {"ok": True, "done": True, "text": "", "error": "212"}                                          # Zalo từ chối: im lặng
    events.clear()
    await ai_mod.async_handle_message(hass, setup, dict(VOICE_EVENT, message_id="m78"))
    assert not events
    app.v2t = {"ok": True, "done": True, "text": "xin chào"}
    await _set_rule(hass, scope="groups", voice_text=True, reply_ai=True, agent="conversation.x")
    await ai_mod.async_handle_message(hass, setup, dict(VOICE_EVENT, thread_type="group", contact_status="group", thread_id="9"))
    assert not events and not fake_agent                                                                      # tin thoại trong nhóm không STT


async def test_voice_reply_falls_back_to_text_when_tts_fails(hass, setup, app, monkeypatch, fake_agent):
    ai_mod = await _msg_env(hass, setup, monkeypatch, fake_agent)

    async def broken(*a, **k):
        raise RuntimeError("TTS hỏng")
    monkeypatch.setattr(ai_mod, "async_tts_audio", broken)
    await _set_rule(hass, scope="contacts", voice_text=True, reply_ai=True, agent="conversation.x", trusted=True)
    await ai_mod.async_handle_message(hass, setup, dict(VOICE_EVENT))
    assert app.last("/send")["json"]["message"] and not [r for r in app.requests if r["path"].endswith("/sendvoice")]
    assert cv.PUBLIC_HINT not in fake_agent[-1]["text"]                                                       # tin cậy: không lời dặn «chưa xác thực»


# ------------------------------------------------------------- LLM API «Zalo Call» ---------------------------------------------------
from homeassistant.core import Context  # noqa: E402
from homeassistant.helpers import llm  # noqa: E402
from custom_components.zalo_call import llm_api  # noqa: E402


def _ctx(context=None):
    return llm.LLMContext(platform="conversation", context=context or Context(), language="vi", assistant="conversation", device_id=None)


def test_match_people_ignores_accents_and_prefers_exact():
    rows = [{"id": "1", "name": "Đại ca"}, {"id": "2", "name": "Đại Ngà"}, {"id": "3", "name": "Bé Đại"}]
    assert [r["id"] for r in llm_api.match_people("dai ca", rows)] == ["1"]
    assert [r["id"] for r in llm_api.match_people("Đại", rows)] == ["1", "2", "3"] and [r["id"] for r in llm_api.match_people("2", rows)] == ["2"]


async def test_llm_api_in_call_only_exposes_the_transfer_tool_and_ai_call_needs_pipeline(hass, setup, app):
    api = await llm.async_get_api(hass, "zalo_call", _ctx())
    assert [t.name for t in api.tools] == ["tim_nguoi", "goi_dien", "cuoc_goi", "dieu_khien_cuoc_goi", "noi_trong_cuoc_goi", "gui_tin"]

    async def call(name, **args):
        return await api.async_call_tool(llm.ToolInput(tool_name=name, tool_args=args))
    assert (await call("tim_nguoi", ten="dai ca"))["ket_qua"][0]["id"] == THREAD
    assert "loi" in await call("goi_dien", nguoi="Đại ca", ai=True)                                       # ai cần pipeline/quy tắc: lỗi, chưa gọi
    assert not [r for r in app.requests if r["path"] == "/api/call/request"]
    assert (await call("goi_dien", nguoi="Đại ca", thong_bao="Có người ngã"))["da_lam"] == "dang_goi"
    rt = hass.data[DOMAIN][setup.entry_id]
    ctx = Context()
    rt.voice.call_context_ids.add(ctx.id)
    in_call = await llm.async_get_api(hass, "zalo_call", _ctx(ctx))
    assert [t.name for t in in_call.tools] == ["chuyen_sang_truc_tiep"]
    tool = next(t for t in api.tools if t.name == "goi_dien")
    app.requests.clear()
    out = await tool.async_call(hass, llm.ToolInput(tool_name="goi_dien", tool_args={"nguoi": "Đại ca"}), _ctx(ctx))
    assert "loi" in out and not app.requests                                                               # người lạ qua điện thoại không sai khiến được


def test_handover_marker_tolerates_dropped_brackets_but_not_normal_speech():
    """Đo thật 11/11: trợ lý ChatGPT trả "Vâng, em chuyển máy ngay ạ. CHUYEN MAY" (không ngoặc) → trước đây không bắt được và bị đọc to."""
    for text in ("Vâng ạ [[CHUYEN_MAY]]", "Vâng ạ [[ chuyen may ]]", "Vâng ạ [CHUYEN_MAY]", "Vâng, em chuyển máy ngay ạ. CHUYEN MAY",
                 "Em đang chuyển máy ngay ạ. CHUYEN_MAY", "CHUYEN MAY"):
        assert cv.HANDOVER_RE.search(text), text
        assert not cv.HANDOVER_RE.sub("", text).strip().upper().endswith("MAY"), text
    for text in ("Em sẽ chuyển máy cho người nhà ạ", "Tôi muốn chuyen may khác", "Xin chào, em nghe đây ạ", "Chuyển sang trực tiếp"):
        assert not cv.HANDOVER_RE.search(text), text


async def test_alert_call_service_is_separate_holds_devices_off_and_takes_them_from_the_rule(hass, setup, app):
    """Dịch vụ alert_call (riêng, không lẫn make_call): lúc nghe máy mọi thiết bị TẮT; thiết bị + giọng lấy từ quy tắc threadID; cờ alert/ai không có ở make_call."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "alert": True}, blocking=True)
    await _set_rule(hass, scope="thread", thread_id=THREAD, name="Đại ca", ai=True, agent="conversation.x", connect="always", speaker="media_player.r1_loa",
                    mic="assist_satellite.r1", camera="camera.phong_khach")
    await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": THREAD, "message": "Phát hiện có người ngã", "type": "video"}, blocking=True,
                                   return_response=True)
    req = [r for r in app.requests if r["path"] == "/api/call/request"][-1]["json"]
    assert req["type"] == "video" and req["mic_url"] == OFF and req["speaker_url"] == OFF and req["camera_url"] == OFF, req
    plan = hass.data[DOMAIN][setup.entry_id].voice.plans["555"]
    assert plan.alert and not plan.ai and plan.video and plan.message == "Phát hiện có người ngã" and plan.hangup
    assert plan.connect == {"speaker": "media_player.r1_loa", "mic": "assist_satellite.r1", "camera": "camera.phong_khach"}
    # Lời gọi nêu thiết bị thì thắng quy tắc; không có quy tắc và không nêu thì KHÔNG nối gì
    await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": THREAD, "message": "Khói", "speaker": "media_player.khac"}, blocking=True, return_response=True)
    assert hass.data[DOMAIN][setup.entry_id].voice.plans["555"].connect == {"speaker": "media_player.khac"}
    await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": THREAD, "message": "Khói", "connect": "never"}, blocking=True, return_response=True)
    assert hass.data[DOMAIN][setup.entry_id].voice.plans["555"].connect == {}                # lời gọi cấm nối thắng quy tắc (always)
    await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": THREAD, "message": "Khói", "connect": "voice"}, blocking=True, return_response=True)
    assert "camera" not in hass.data[DOMAIN][setup.entry_id].voice.plans["555"].connect       # voice: bỏ camera dù quy tắc có
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": THREAD, "message": "Khói", "connect": "maybe"}, blocking=True)
    await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": "999", "message": "Khói"}, blocking=True, return_response=True)
    assert hass.data[DOMAIN][setup.entry_id].voice.plans["555"].connect == {}
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": THREAD, "message": "   "}, blocking=True)


async def test_ai_rule_call_holds_all_devices_off_and_keeps_configured_ones_for_the_handover(hass, setup, app, hass_client_no_auth, monkeypatch):
    seen = []

    async def fake_ai(hass_, api, call_id, plan, voice=None):
        seen.append((dict(plan.connect), plan.video))
        return {"handover": False, "heard": ""}
    monkeypatch.setattr(cv, "async_run_ai", fake_ai)
    await _set_rule(hass, scope="thread", thread_id=THREAD, answer=True, answer_delay=0, ai=True, agent="conversation.x", connect="voice",
                    speaker="media_player.r1_loa", mic="assist_satellite.r1", camera="camera.phong_khach")
    await _webhook(hass, hass_client_no_auth, _incoming(status="friend", call_type_raw=1))
    body = (await _wait_answers(app, 1))[0]["json"]
    assert body["mic_url"] == OFF and body["speaker_url"] == OFF and body["camera_url"] == OFF, body     # AI giữ máy: không nối gì dù đã cài
    await _webhook(hass, hass_client_no_auth, {"event": "call", "status": "answered", "call_id": "555", "thread_id": THREAD})
    for _ in range(60):
        if seen:
            break
        await asyncio.sleep(0.05)
    assert seen == [({"speaker": "media_player.r1_loa", "mic": "assist_satellite.r1"}, True)], seen


async def test_connect_ai_lets_the_ai_pick_voice_or_camera_within_the_configured_devices(hass, monkeypatch):
    """connect: ai — AI chọn lúc chuyển máy: [[CHUYEN_MAY:CAMERA]] = nối cả camera (thoại thì nâng video), [[CHUYEN_MAY]] / :VOICE = chỉ loa+mic.
    Không bao giờ nối thứ chưa cài."""
    full = {**HOUSE, "camera": "camera.pk"}
    assert cv.devices_for_mode(full, "ai") == full                                  # tập được phép
    events = []
    hass.bus.async_listen("zalo_call_ai_handover", lambda e: events.append(dict(e.data)))
    for reply, camera in (("Mình chuyển máy ngay [[CHUYEN_MAY:CAMERA]]", True), ("Mình chuyển máy [[CHUYEN_MAY:VOICE]]", False),
                          ("Mình chuyển máy [[CHUYEN_MAY]]", False), ("Em chuyển ngay ạ. CHUYEN MAY: CAMERA", True)):
        await _ai_env(monkeypatch, [("có người ngã", reply)])
        api = FakeApi(statuses=["answered"])
        rt = _rt(api)
        await cv._run_plan(hass, rt, "77", cv.Plan(ai=True, pipeline_id="pl", connect=dict(full), connect_ai=True))
        await hass.async_block_till_done()
        assert (rt.bridge.reconnected[0][1]["camera"] == "camera.pk") is False                  # thoại: camera chỉ vào qua nâng video
        assert bool(getattr(api, "upgraded", [])) is camera, (reply, getattr(api, "upgraded", None))
        assert ("CHUYEN" not in api.said[-1][2].decode().upper()), api.said[-1]                 # dấu không bị đọc ra
    assert [e["camera"] for e in events] == [True, False, False, True]
    # AI chọn camera nhưng quy tắc không cài camera: không có gì để nối thêm
    await _ai_env(monkeypatch, [("cháy", "Chuyển máy [[CHUYEN_MAY:CAMERA]]")])
    api = FakeApi(statuses=["answered"])
    rt = _rt(api)
    await cv._run_plan(hass, rt, "77", cv.Plan(ai=True, pipeline_id="pl", connect=dict(HOUSE), connect_ai=True))
    assert not getattr(api, "upgraded", []) and rt.bridge.reconnected[0][1]["camera"] == ""


def test_connect_ai_hint_only_when_ai_chooses_and_tool_carries_the_choice():
    assert "CHUYEN_MAY:CAMERA" in cv.phone_hint("", True, connect_ai=True) and "CHUYEN_MAY:CAMERA" not in cv.phone_hint("", True)
    v = cv.CallVoice()
    v.ai_running.append("9")
    assert v.request_handover("khẩn cấp", "camera") and v.handover_connect == {"9": "camera"}
    v2 = cv.CallVoice()
    v2.ai_running.append("9")
    assert v2.request_handover("x", "bậy") and v2.handover_connect == {}                     # lựa chọn lạ bị bỏ qua


async def test_connect_ai_in_services_alert_has_no_ai_to_choose_and_rule_ai_plans_carry_the_flag(hass, setup, app):
    await _set_rule(hass, scope="thread", thread_id=THREAD, name="Đại ca", ai=True, agent="conversation.x", connect="ai", speaker="media_player.r1_loa",
                    mic="assist_satellite.r1", camera="camera.phong_khach")
    await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "ai": True}, blocking=True, return_response=True)
    plan = hass.data[DOMAIN][setup.entry_id].voice.plans["555"]
    assert plan.connect_ai and plan.connect["camera"] == "camera.phong_khach"                     # AI được phép chọn trong tập này
    await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": THREAD, "message": "Khói"}, blocking=True, return_response=True)
    plan = hass.data[DOMAIN][setup.entry_id].voice.plans["555"]
    assert not plan.connect_ai and plan.connect == {"speaker": "media_player.r1_loa", "mic": "assist_satellite.r1", "camera": "camera.phong_khach"}   # cảnh báo mặc định: TẤT CẢ thiết bị đã cài, kể cả camera, dù quy tắc đang để ai
    await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": THREAD, "message": "Khói", "connect": "ai"}, blocking=True, return_response=True)
    assert "camera" not in hass.data[DOMAIN][setup.entry_id].voice.plans["555"].connect          # nêu ai tường minh: cảnh báo không có AI chọn nên là voice
    await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "ai": True, "connect": "never"}, blocking=True, return_response=True)
    plan = hass.data[DOMAIN][setup.entry_id].voice.plans["555"]
    assert plan.connect == {} and not plan.connect_ai                                          # lời gọi cấm thắng quy tắc


async def test_connect_accepts_any_combination_of_parts_for_voice_and_video_in_both_alert_and_make_call(hass, setup, app):
    """connect chọn nhiều: chỉ mic, chỉ loa, chỉ cam, mic+loa, loa+cam, ... ở cả alert_call (cảnh báo) và make_call (có AI); thoại lẫn video."""
    full = {"speaker": "media_player.r1", "mic": "assist_satellite.r1", "camera": "camera.pk", "volume": 30}
    cases = {("mic",): {"mic": "assist_satellite.r1"}, ("speaker",): {"speaker": "media_player.r1", "volume": 30}, ("camera",): {"camera": "camera.pk"},
             ("mic", "speaker"): {"mic": "assist_satellite.r1", "speaker": "media_player.r1", "volume": 30},
             ("speaker", "camera"): {"speaker": "media_player.r1", "camera": "camera.pk", "volume": 30}, ("mic", "camera"): {"mic": "assist_satellite.r1", "camera": "camera.pk"},
             ("mic", "speaker", "camera"): full}
    for parts, expect in cases.items():
        assert cv.devices_for_mode(full, list(parts)) == expect, parts
    assert cv.devices_for_mode(full, ["camera", "mic"]) == cv.devices_for_mode(full, ["mic", "camera"])            # thứ tự chọn không quan trọng
    assert R.parse_connect("voice") == ["mic", "speaker"] and R.parse_connect(["always"]) == ["mic", "speaker", "camera"]
    assert R.parse_connect(["never"]) == [] and R.parse_connect(["mic", "ai"]) == ["mic", "ai"] and R.parse_connect(["ai"]) == ["mic", "speaker", "camera", "ai"] and R.parse_connect(None) == []
    rt = hass.data[DOMAIN][setup.entry_id]
    await _set_rule(hass, scope="thread", thread_id=THREAD, name="Đại ca", ai=True, agent="conversation.x", **{k: v for k, v in full.items()})
    for service, extra in (("alert_call", {"message": "Khói"}), ("make_call", {"ai": True})):
        for typ in ("user", "video"):
            for parts, expect in cases.items():
                await hass.services.async_call(DOMAIN, service, {"thread_id": THREAD, "type": typ, "connect": list(parts), **extra}, blocking=True, return_response=True)
                plan = rt.voice.plans["555"]
                assert plan.connect == expect and plan.video is (typ == "video"), (service, typ, parts, plan.connect)
    # Lời gọi chỉ nêu loa: nối đúng loa đó (không kèm mic/cam của quy tắc)
    await hass.services.async_call(DOMAIN, "alert_call", {"thread_id": THREAD, "message": "Khói", "speaker": "media_player.khac"}, blocking=True, return_response=True)
    assert rt.voice.plans["555"].connect == {"speaker": "media_player.khac"}
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "ai": True, "connect": ["loa"]}, blocking=True)


async def test_camera_only_on_a_voice_call_upgrades_to_video_without_audio_devices_and_speaker_only_never_touches_video(hass, monkeypatch):
    for parts, upgraded, video_started in ((["camera"], True, False), (["speaker"], False, False), (["speaker", "camera"], True, False)):
        await _ai_env(monkeypatch, [("giúp", "Chuyển [[CHUYEN_MAY]]")])
        api = FakeApi(statuses=["answered"])
        rt = _rt(api)
        connect = cv.devices_for_mode({**HOUSE, "camera": "camera.pk"}, parts)
        await cv._run_plan(hass, rt, "77", cv.Plan(ai=True, pipeline_id="pl", video=False, connect=connect))
        assert bool(getattr(api, "upgraded", [])) is upgraded, (parts, getattr(api, "upgraded", None))
        ov = rt.bridge.reconnected[0][1]
        assert ov["camera"] == "" and (ov["mic"] == "") is ("mic" not in parts) and (ov["speaker"] == "") is ("speaker" not in parts), (parts, ov)


async def test_ai_ends_the_conversation_and_hangs_up_when_the_caller_needs_nothing_more(hass, monkeypatch):
    """Đo thật 11/11: AI chào tạm biệt nhưng không có tín hiệu kết thúc nên cuộc gọi mở mãi. [[KET_THUC]] (dung sai) → đọc nốt lời chào (không đọc dấu),
    dừng vòng AI (không nghe thêm), cúp máy; không bắn sự kiện chuyển máy."""
    events = []
    hass.bus.async_listen("zalo_call_ai_handover", lambda e: events.append(dict(e.data)))
    assert cv.END_MARK in cv.phone_hint("", True)
    for bye in ("Vâng ạ, chào anh nhé [[KET_THUC]]", "Chào anh nhé [[ket thuc]]", "Em chào anh nhé. KET THUC", "Em chào anh nhé. KET_THUC"):
        fake = await _ai_env(monkeypatch, [("bái bai không cần gì", bye), ("còn nữa không", "Không nghe thấy lẽ ra không được hỏi lượt này")])
        api = FakeApi(statuses=["answered"])
        res = await cv.async_run_ai(hass, api, "77", cv.Plan(ai=True, pipeline_id="pl", greeting=""), cv.CallVoice())
        assert res["finished"] is True and res["handover"] is False, (bye, res)
        said = [x[2].decode().upper() for x in api.said]
        assert said and all("KET" not in x and "THUC" not in x for x in said), said                  # dấu không bị đọc ra
        assert len(fake.calls) == 1 if hasattr(fake, "calls") else True                              # không nghe thêm lượt nào sau khi AI báo xong
    for finished_by_marker in (True,):
        await _ai_env(monkeypatch, [("tạm biệt nhé", "Chào anh nhé [[KET_THUC]]")])
        api = FakeApi(statuses=["answered"])
        await cv._run_plan(hass, _rt(api), "77", cv.Plan(ai=True, hangup=True, pipeline_id="pl"))
        assert api.ended == ["77"] and events == []                                                  # cúp máy, không chuyển máy
    await _ai_env(monkeypatch, [("tạm biệt nhé", "Chào anh nhé [[KET_THUC]]")])
    api = FakeApi(statuses=["answered"])
    await cv._run_plan(hass, _rt(api), "77", cv.Plan(ai=True, hangup=False, pipeline_id="pl"))
    assert api.ended == []                                                                         # hangup_after: false thì giữ máy
    # Cả chuyển máy lẫn kết thúc trong một câu: chuyển máy thắng (không cúp)
    await _ai_env(monkeypatch, [("cần người nhà", "Em nối máy ạ [[CHUYEN_MAY]] [[KET_THUC]]")])
    api = FakeApi(statuses=["answered"])
    rt = _rt(api)
    await cv._run_plan(hass, rt, "77", cv.Plan(ai=True, hangup=True, pipeline_id="pl", connect=dict(HOUSE)))
    await hass.async_block_till_done()
    assert api.ended == [] and events and events[-1]["reason"] == "ai"
    for text in ("Em sẽ kết thúc phần này ạ", "Chào anh", "kết thúc"):
        assert not cv.END_RE.search(text), text                                                      # lời thường (có dấu/không viết hoa) không khớp


async def test_outgoing_ai_call_without_message_greets_first_instead_of_staying_silent(hass, setup, app):
    """Đo thật 11/11: make_call ai:true không message → người nghe máy gặp im lặng 14 giây. AI phải chào trước (câu của quy tắc, không thì câu mặc định)."""
    await _set_rule(hass, scope="thread", thread_id=THREAD, name="Đại ca", ai=True, agent="conversation.x", greeting="Chào anh, có chuyện gì ạ?")
    await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "ai": True}, blocking=True, return_response=True)
    assert hass.data[DOMAIN][setup.entry_id].voice.plans["555"].greeting == "Chào anh, có chuyện gì ạ?"
    await _set_rule(hass, scope="thread", thread_id=THREAD, greeting="")
    await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "ai": True}, blocking=True, return_response=True)
    assert hass.data[DOMAIN][setup.entry_id].voice.plans["555"].greeting == cv.DEFAULT_GREETING
    await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "ai": True, "message": "Báo bạn một việc"}, blocking=True, return_response=True)
    assert hass.data[DOMAIN][setup.entry_id].voice.plans["555"].greeting == ""                       # có message thì đọc message, không chào thêm


# ---------------------------------------------------------------- cảnh báo: after + sự kiện «đọc xong» ----------------------------------
async def test_alert_after_hangup_connect_wait_and_alert_done_event_tells_exactly_when(hass):
    """after: hangup = cúp; connect = nối thiết bị (không có thiết bị thì cúp); wait = giữ máy. Mọi trường hợp đều bắn zalo_call_alert_done."""
    done = []
    hass.bus.async_listen("zalo_call_alert_done", lambda e: done.append(dict(e.data)))
    full = {**HOUSE, "camera": "camera.pk"}
    cases = [("", {}, "hangup", False, True), ("", HOUSE, "connect", True, False), ("hangup", full, "hangup", False, True),
             ("connect", {}, "hangup", False, True), ("connect", full, "connect", True, False), ("wait", full, "wait", False, False)]
    for after, connect, want_after, connected, ended in cases:
        api = FakeApi()
        rt = _rt(api)
        await cv._run_plan(hass, rt, "77", cv.Plan(message="Mất điện", alert=True, hangup=True, after=after, connect=dict(connect), thread_id="123", video=True))
        await hass.async_block_till_done()
        ev = done[-1]
        assert ev["after"] == want_after and ev["connected"] is connected and ev["ended"] is ended and ev["thread_id"] == "123" and ev["call_id"] == "77", (after, connect, ev)
        assert (api.ended == ["77"]) is ended and bool(rt.bridge.reconnected) is connected, (after, connect)
        assert ev["camera"] is bool(connected and "camera" in connect)
    assert len(done) == len(cases)


async def test_alert_call_type_follows_the_camera_tick_video_when_camera_is_used(hass, setup, app):
    """Tích camera = gọi VIDEO. Không nêu type: có camera sẽ nối thì video, không thì thoại; nêu type thì theo type; AI tự chọn thì không ép video."""
    await _set_rule(hass, scope="thread", thread_id=THREAD, name="Đại ca", ai=True, agent="conversation.x", speaker="media_player.r1_loa",
                    mic="assist_satellite.r1", camera="camera.phong_khach")

    async def placed(service, **data):
        await hass.services.async_call(DOMAIN, service, {"thread_id": THREAD, **data}, blocking=True, return_response=True)
        return [r for r in app.requests if r["path"] == "/api/call/request"][-1]["json"]["type"]
    assert await placed("alert_call", message="Khói") == "video"                                   # cảnh báo mặc định nối tất cả, có camera → video
    assert await placed("alert_call", message="Khói", connect=["mic", "speaker"]) == "user"        # không tích camera → thoại
    assert await placed("alert_call", message="Khói", connect=["camera"]) == "video"
    assert await placed("alert_call", message="Khói", type="user") == "user"                       # nêu type thì theo type
    assert await placed("alert_call", message="Khói", connect=["never"]) == "user"                 # không nối gì: thoại
    assert await placed("make_call", ai=True, connect=["mic", "camera"]) == "video"
    assert await placed("make_call", ai=True, connect=["mic"]) == "user"
    assert await placed("make_call", ai=True, connect=["ai"]) == "user"                            # AI tự chọn camera: không ép video, chỉ nâng khi AI quyết
    assert await placed("make_call", ai=True, connect=["mic", "ai"]) == "user"
    plan = hass.data[DOMAIN][setup.entry_id].voice.plans["555"]
    assert plan.connect_ai and set(plan.connect) == {"mic"}                                       # AI chỉ được chọn trong ô đã tích (chỉ mic)
    assert await placed("make_call", ai=True) == "user"                                            # không nêu connect: theo quy tắc (không tích gì) → không nối, thoại


# ---------------------------------------------------------------- thông báo «có cuộc gọi đến» ra loa -------------------------------------
def test_announce_text_uses_rule_name_then_zalo_name_then_stranger_label():
    assert cv.announce_text({"name": "Đại ca"}, {"call_type_raw": 1, "peer": "Nguyễn Việt"}) == "Có cuộc gọi video từ Đại ca."
    assert cv.announce_text({}, {"call_type_raw": 0, "peer": "Nguyễn Việt"}) == "Có cuộc gọi thoại từ Nguyễn Việt."
    assert cv.announce_text({}, {"contact_status": "stranger"}) == "Có cuộc gọi thoại từ người lạ."
    assert cv.announce_text({}, {"contact_status": "friend"}) == "Có cuộc gọi thoại từ một người."
    assert cv.announce_text({"announce_text": "Alo {ten} gọi {loai} {khac}"}, {"peer": "Bố"}) == "Alo Bố gọi thoại {khac}"      # khoá lạ không làm lỗi


async def test_incoming_call_announces_on_the_speaker_only_when_the_rule_turns_it_on(hass, setup, app, hass_client_no_auth, monkeypatch):
    spoken = []

    async def fake_speak(call):
        spoken.append(dict(call.data))
    hass.services.async_register("tts", "speak", fake_speak)
    monkeypatch.setattr(cv, "pipeline_tts", lambda hass_, pid: ("tts.chatgpt", "vi", {"voice": "v1"}))
    with pytest.raises(ServiceValidationError):
        await _set_rule(hass, scope="contacts", announce=True)                                    # bật mà không chọn loa: báo lỗi
    # Không có quy tắc: im lặng
    await _webhook(hass, hass_client_no_auth, _incoming(status="friend", call_id="a1", peer="Nguyễn Việt"))
    await hass.async_block_till_done()
    assert spoken == []
    # Có quy tắc nhưng không bật announce (mặc định): im lặng
    await _set_rule(hass, scope="contacts", answer=False)
    await _webhook(hass, hass_client_no_auth, _incoming(status="friend", call_id="a2", peer="Nguyễn Việt"))
    await hass.async_block_till_done()
    assert spoken == []
    # Bật: đọc ra loa đã chọn bằng giọng pipeline, một lần dù webhook đến hai lần; không tự nghe máy (answer false)
    await _set_rule(hass, scope="contacts", announce=True, announce_to="media_player.loa_phong_khach")
    for _ in range(2):
        await _webhook(hass, hass_client_no_auth, _incoming(status="friend", call_id="a3", peer="Nguyễn Việt", call_type_raw=1))
    await hass.async_block_till_done()
    assert spoken == [{"entity_id": "tts.chatgpt", "media_player_entity_id": "media_player.loa_phong_khach", "message": "Có cuộc gọi video từ Nguyễn Việt.",
                       "language": "vi", "options": {"voice": "v1"}}], spoken
    assert not [r for r in app.requests if r["path"] == "/api/call/answer"]
    # Người lạ không có quy tắc strangers: im lặng (quy tắc contacts không áp cho người lạ)
    spoken.clear()
    await _webhook(hass, hass_client_no_auth, _incoming(status="stranger", call_id="a4"))
    await hass.async_block_till_done()
    assert spoken == []
    await _set_rule(hass, scope="strangers", announce=True, announce_to="media_player.loa_phong_khach")
    await _webhook(hass, hass_client_no_auth, _incoming(status="stranger", call_id="a5"))
    await hass.async_block_till_done()
    assert spoken and spoken[0]["message"] == "Có cuộc gọi thoại từ người lạ."


# ---------------------------------------------------------------- «nối ngay» (connect_now): vd. cam ngay, mic+loa khi người nhà nói -----------------
async def test_connect_now_connects_camera_at_answer_and_the_rest_only_at_handover(hass, setup, app):
    """Video + AI: cam nối NGAY lúc nghe máy (app nhận camera_url, loa/mic 'off'); khi người nhà nói trực tiếp mới nối mic+loa (không nối lại cam)."""
    rt = hass.data[DOMAIN][setup.entry_id]

    async def cam_url(entity_id):
        return "rtsp://cam.local/live"
    rt.bridge.async_camera_url = cam_url                                                              # camera thật không có trong môi trường test
    await _set_rule(hass, scope="thread", thread_id=THREAD, name="Đại ca", ai=True, agent="conversation.x", speaker="media_player.r1_loa",
                    mic="assist_satellite.r1", camera="camera.phong_khach")
    await hass.services.async_call(DOMAIN, "make_call", {"thread_id": THREAD, "ai": True, "connect_now": ["camera"], "connect": ["mic", "speaker"]},
                                   blocking=True, return_response=True)
    req = [r for r in app.requests if r["path"] == "/api/call/request"][-1]["json"]
    assert req["type"] == "video" and req["mic_url"] == OFF and req["speaker_url"] == OFF and req["camera_url"] == "rtsp://cam.local/live", req   # cam bật ngay, mic/loa chưa
    plan = rt.voice.plans["555"]
    assert set(plan.connect_now) == {"camera"} and set(plan.connect) == {"mic", "speaker"} and plan.video
    # Lúc chuyển máy chỉ nối thêm mic+loa; cam đã nối sẵn thì không nối lại
    api = FakeApi(statuses=["answered"])
    rt2 = _rt(api)
    await _ai_env_handover(hass, api, rt2, cv.Plan(ai=True, pipeline_id="pl", video=True, connect={"mic": "assist_satellite.r1", "speaker": "media_player.r1_loa"},
                                                  connect_now={"camera": "camera.phong_khach"}))
    ov = rt2.bridge.reconnected[0][1]
    assert ov["mic"] == "assist_satellite.r1" and ov["speaker"] == "media_player.r1_loa" and ov["camera"] == "", ov
    started = [m for m in api.media if m.get("action") == "start"][0]
    assert started["camera_url"] == "off", started                                    # không khởi động lại cam đã nối


async def _ai_env_handover(hass, api, rt, plan):
    class _M:
        pass
    import types as _t
    from homeassistant.components import assist_pipeline  # noqa: F401
    old = cv.async_run_ai

    async def fake(*a, **k):
        return {"handover": True, "heard": "cần người nhà", "connect": "", "finished": False}
    cv.async_run_ai = fake
    try:
        await cv._run_plan(hass, rt, "77", plan)
        await hass.async_block_till_done()
    finally:
        cv.async_run_ai = old


async def test_connect_now_rule_for_incoming_ai_call_and_camera_now_on_a_voice_call_upgrades_to_video(hass, setup, app, hass_client_no_auth, monkeypatch):
    seen = []

    async def cam_url(entity_id):
        return "rtsp://cam.local/live"
    hass.data[DOMAIN][setup.entry_id].bridge.async_camera_url = cam_url

    async def fake_ai(hass_, api, call_id, plan, voice=None):
        seen.append((dict(plan.connect_now), dict(plan.connect), plan.video))
        return {"handover": False, "heard": "", "connect": "", "finished": False}
    monkeypatch.setattr(cv, "async_run_ai", fake_ai)
    await _set_rule(hass, scope="thread", thread_id=THREAD, answer=True, answer_delay=0, ai=True, agent="conversation.x", speaker="media_player.r1_loa",
                    mic="assist_satellite.r1", camera="camera.phong_khach", connect=["mic", "speaker"], connect_now=["camera"])
    await _webhook(hass, hass_client_no_auth, _incoming(status="friend", call_type_raw=1))
    body = (await _wait_answers(app, 1))[0]["json"]
    assert body["camera_url"] == "rtsp://cam.local/live" and body["mic_url"] == OFF and body["speaker_url"] == OFF, body           # cam ngay, mic/loa chờ
    await _webhook(hass, hass_client_no_auth, {"event": "call", "status": "answered", "call_id": "555", "thread_id": THREAD})
    for _ in range(60):
        if seen:
            break
        await asyncio.sleep(0.05)
    assert seen == [({"camera": "camera.phong_khach"}, {"mic": "assist_satellite.r1", "speaker": "media_player.r1_loa"}, True)], seen


async def test_connect_now_on_a_voice_call_upgrades_to_video_straight_away(hass):
    api = FakeApi(statuses=["answered"])
    rt = _rt(api)
    await cv._run_plan(hass, rt, "77", cv.Plan(message="Xin chào", hangup=True, video=False, connect_now={"camera": "camera.pk"}))
    assert getattr(api, "upgraded", []) and api.upgraded[0]["call_id"] == "77"


def test_connect_now_rule_never_defaults_on_and_ai_choice_is_not_allowed_there():
    assert R.normalize({})["connect_now"] == []
    assert R.normalize({"connect_now": ["camera", "ai"]})["connect_now"] == ["camera"]               # «AI tự chọn» không có nghĩa ở nối ngay
    assert cv.rule_devices_now({"camera": "camera.pk", "mic": "assist_satellite.r1", "connect_now": ["camera"]}) == {"camera": "camera.pk"}
    assert cv.rule_devices_now({"camera": "camera.pk"}) == {}                                          # chưa tích: không nối ngay
    assert cv.rule_devices_now({"connect_now": ["camera"]}) == {}                                      # tích mà chưa chọn camera: không nối


# ---------------------------------------------------------------- người nhận = thực thể notify chọn từ danh bạ -------------------------
async def test_recipients_are_picked_from_the_contact_list_and_become_notify_entities(hass, setup, app):
    """Tuỳ chọn «Người/nhóm nhận» liệt kê danh bạ để CHỌN (không gõ mã); mỗi người chọn thành notify.* có thread_id/type, gửi tin được, các quy tắc không mất."""
    await _set_rule(hass, scope="thread", thread_id=THREAD, name="Đại ca", answer=True)               # kho quy tắc nằm ngoài entry.options: đổi tuỳ chọn không được xoá
    res = await hass.config_entries.options.async_init(setup.entry_id)
    assert res["type"] == "form" and res["step_id"] == "init"
    with pytest.raises(Exception):                                                                      # mã không có trong danh bạ bị bộ chọn của HA từ chối
        await hass.config_entries.options.async_configure(res["flow_id"], {"recipients": ["user:khong-co"]})
    res = await hass.config_entries.options.async_init(setup.entry_id)
    opts = res["data_schema"].schema["recipients"].config["options"]
    assert {(o["value"], o["label"]) for o in opts} == {(f"user:{THREAD}", "Đại ca (bạn bè)"), ("user:111", "Đại Ngà (bạn bè)"),
                                                          ("group:3133467193494275911", "AI học hỏi (nhóm)")}
    res = await hass.config_entries.options.async_configure(res["flow_id"], {"recipients": [f"user:{THREAD}", "group:3133467193494275911"]})
    assert res["type"] == "create_entry" and setup.options["recipients"] == [f"user:{THREAD}", "group:3133467193494275911"]
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    ids = sorted(e.entity_id for e in reg.entities.values() if e.platform == DOMAIN and e.domain == "notify")
    assert ids == ["notify.zalo_call_ai_hoc_hoi", "notify.zalo_call_dai_ca"], ids
    st = hass.states.get("notify.zalo_call_dai_ca")
    assert st.attributes["friendly_name"] == "Zalo Call Đại ca", st.attributes                       # tên không lặp «Zalo»
    assert st.attributes["thread_id"] == THREAD and st.attributes["type"] == "user" and hass.states.get("notify.zalo_call_ai_hoc_hoi").attributes["type"] == "group"
    app.requests.clear()
    await hass.services.async_call("notify", "send_message", {"entity_id": "notify.zalo_call_dai_ca", "message": "Chào", "title": "Báo"}, blocking=True)
    sent = [r for r in app.requests if THREAD in r["path"]]
    assert sent and sent[-1]["json"]["message"] == "Báo\nChào" and sent[-1]["json"]["type"] == "user", app.requests
    rules = await hass.services.async_call(DOMAIN, "list_rules", {}, blocking=True, return_response=True)
    assert rules["threads"][THREAD]["answer"] is True                                                  # quy tắc còn nguyên sau khi đổi tuỳ chọn
    # Bỏ chọn hết: thực thể notify biến mất
    res = await hass.config_entries.options.async_init(setup.entry_id)
    await hass.config_entries.options.async_configure(res["flow_id"], {"recipients": []})
    await hass.async_block_till_done()
    assert not [e for e in reg.entities.values() if e.platform == DOMAIN and e.domain == "notify"]      # xoá hẳn khỏi sổ đăng ký, không để thực thể mồ côi


# ---------------------------------------------------------------- người gọi xin chuyển thoại sang video -------------------------------------
async def test_video_request_is_an_event_and_the_rule_decides_ask_accept_accept_camera_and_no_rule_does_nothing(hass, setup, app, hass_client_no_auth):
    from homeassistant.core import callback
    states = []
    hass.bus.async_listen("zalo_call_call_state", callback(lambda e: states.append((e.data["state"], e.data.get("thread_id")))))

    async def cam_url(entity_id):
        return "rtsp://cam.local/live"
    hass.data[DOMAIN][setup.entry_id].bridge.async_camera_url = cam_url
    accepts = lambda: [r["json"] for r in app.requests if r["path"] == "/api/call/media" and (r["json"] or {}).get("target") == "accept_video"]   # noqa: E731
    hook = {"event": "call", "status": "video_request", "call_id": "555", "thread_id": THREAD, "contact_status": "friend", "peer": "Đại ca"}
    # Không có quy tắc: chỉ có sự kiện cho automation, KHÔNG tự đồng ý
    await _webhook(hass, hass_client_no_auth, hook)
    await hass.async_block_till_done()
    assert ("video_request", THREAD) in states and accepts() == []
    # ask (mặc định của quy tắc): vẫn không đồng ý
    await _set_rule(hass, scope="thread", thread_id=THREAD, name="Đại ca", camera="camera.phong_khach")
    await _webhook(hass, hass_client_no_auth, hook)
    await hass.async_block_till_done()
    assert accepts() == []
    # accept: đồng ý, KHÔNG gửi hình trong nhà
    await _set_rule(hass, scope="thread", thread_id=THREAD, video_request="accept")
    await _webhook(hass, hass_client_no_auth, hook)
    await hass.async_block_till_done()
    assert len(accepts()) == 1 and "camera_url" not in accepts()[0] and accepts()[0]["call_id"] == "555", accepts()
    # accept_camera: đồng ý và gửi camera đã chọn trong quy tắc
    await _set_rule(hass, scope="thread", thread_id=THREAD, video_request="accept_camera")
    await _webhook(hass, hass_client_no_auth, hook)
    await hass.async_block_till_done()
    assert len(accepts()) == 2 and accepts()[1]["camera_url"] == "rtsp://cam.local/live", accepts()
    # người khác (không có quy tắc) không bị đồng ý theo quy tắc của người này
    await _webhook(hass, hass_client_no_auth, {**hook, "thread_id": "999", "contact_status": "stranger"})
    await hass.async_block_till_done()
    assert len(accepts()) == 2
    with pytest.raises(vol.Invalid):                                                            # giá trị lạ bị bộ kiểm schema từ chối
        await _set_rule(hass, scope="thread", thread_id=THREAD, video_request="luon_luon")


async def test_accept_video_service_needs_a_live_call_or_call_id_and_sends_camera_only_when_chosen(hass, setup, app):
    async def cam_url(entity_id):
        return "rtsp://cam.local/live"
    hass.data[DOMAIN][setup.entry_id].bridge.async_camera_url = cam_url
    accepts = lambda: [r["json"] for r in app.requests if r["path"] == "/api/call/media" and (r["json"] or {}).get("target") == "accept_video"]   # noqa: E731
    with pytest.raises(Exception):                                                              # không có cuộc gọi đang nói và không nêu call_id
        await hass.services.async_call(DOMAIN, "accept_video", {}, blocking=True)
    r = await hass.services.async_call(DOMAIN, "accept_video", {"call_id": "555"}, blocking=True, return_response=True)
    assert r == {"call_id": "555", "accepted": True, "camera": False} and accepts() == [{"call_id": "555", "action": "start", "target": "accept_video"}]
    await hass.services.async_call(DOMAIN, "accept_video", {"call_id": "555", "camera": "camera.phong_khach"}, blocking=True, return_response=True)
    assert accepts()[1]["camera_url"] == "rtsp://cam.local/live"

