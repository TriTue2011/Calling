"""Giọng nói TRONG cuộc gọi Zalo: thông báo bằng TTS và AI nói chuyện (STT → trợ lý → TTS).

Dùng đúng Assist pipeline và TTS của HA nên STT/TTS/trợ lý là thứ người dùng đã cấu hình (không thêm dịch vụ ngoài):
  * ``async_say``: TTS → tệp âm thanh → app (POST /api/call/say) phát lên cuộc gọi qua đường mic.
  * ``async_run_ai``: nghe tiếng người gọi (luồng WAV của app /api/call/audio/out/<token>) → Assist pipeline
    (VAD + STT + trợ lý hội thoại) → TTS của pipeline → phát lại; lặp tới khi cuộc gọi hết, im lặng quá lâu hoặc quá giới hạn.
  * ``Plan``: kế hoạch cho một cuộc gọi (đọc thông báo, bật AI, cúp máy sau khi xong) — đăng ký lúc make_call/answer_call,
    chạy khi webhook báo «đã nghe máy». Cuộc gọi ĐẾN thì công tắc «AI trong cuộc gọi» tự tạo kế hoạch.
Không ghi nội dung hội thoại vào log (chỉ độ dài/số lượt).
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import aiohttp
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZaloCallApi, ZaloCallError

_LOGGER = logging.getLogger(__name__)

POLL_S = 0.4                 # nhịp hỏi app xem đã phát xong chưa
SAY_MAX_WAIT_S = 120.0       # chờ phát xong tối đa
TURN_TIMEOUT_S = 45.0        # một lượt nghe → hiểu (VAD cũng tự dừng sớm hơn)
MAX_CALL_S = 600.0           # AI nói chuyện tối đa 10 phút
MAX_TURNS = 30
IDLE_TURNS = 2               # im lặng/không nghe ra chữ liên tiếp ngần này lượt thì kết thúc
CHUNK_BYTES = 3200           # 100 ms PCM16 mono 16 kHz
WAV_HEADER = 44
QUEUE_MAX = 100              # ~10 s âm thanh chờ; đầy thì bỏ khúc cũ nhất (không để tụt hậu)
DEFAULT_GREETING = "Xin chào, tôi là trợ lý của gia đình. Bạn cần gì ạ?"
PHONE_HINT = ("Bạn đang nói chuyện qua điện thoại bằng giọng nói. Trả lời ngắn gọn, tự nhiên bằng lời nói: không dùng markdown, "
              "danh sách, ký hiệu hay emoji.")
HANDOVER_MARK = "[[CHUYEN_MAY]]"
HANDOVER_RE = re.compile(r"\[\[\s*CHUYEN_MAY\s*\]\]", re.IGNORECASE)
HANDOVER_HINT = ("Khi người gọi muốn nói chuyện với người trong nhà, khi có việc khẩn cấp hoặc nguy hiểm, hoặc khi bạn không giúp "
                 "được, hãy nói ngắn gọn rằng bạn sẽ chuyển máy rồi kết thúc câu trả lời bằng đúng dấu " + HANDOVER_MARK +
                 " (dấu này sẽ không được đọc ra). Sau dấu đó cuộc gọi được nối trực tiếp với thiết bị trong nhà.")


def phone_hint(handover_rule: str = "") -> str:
    """Gợi ý cho trợ lý: nói chuyện qua điện thoại + khi nào tự chuyển sang trực tiếp (handover_rule: điều kiện riêng)."""
    rule = (" Điều kiện chuyển máy riêng: %s." % handover_rule.strip().rstrip(".")) if handover_rule and handover_rule.strip() else ""
    return PHONE_HINT + " " + HANDOVER_HINT + rule


@dataclass
class Plan:
    """Việc cần làm khi cuộc gọi được nghe máy."""
    message: str = ""            # đọc (TTS) ngay khi nghe máy
    repeat: int = 1              # đọc mấy lần (1-3)
    ai: bool = False             # sau đó nghe và trả lời bằng AI
    hangup: bool = False         # xong thì cúp máy
    engine: str | None = None    # thực thể tts.* (trống = của pipeline / mặc định)
    language: str | None = None
    pipeline_id: str | None = None
    greeting: str = ""           # AI nói trước khi chưa có `message` (cuộc gọi đến)
    handover_rule: str = ""      # điều kiện riêng để AI tự chuyển sang trực tiếp (ngoài các điều kiện chung)


@dataclass
class CallVoice:
    plans: dict[str, Plan] = field(default_factory=dict)
    incoming: set[str] = field(default_factory=set)
    tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    ai_running: list[str] = field(default_factory=list)          # cuộc gọi đang có vòng AI (mới nhất ở cuối)
    handover: dict[str, str] = field(default_factory=dict)       # call_id -> lý do: AI xin chuyển sang trực tiếp (qua công cụ LLM)
    call_context_ids: set[str] = field(default_factory=set)      # id Context của các lượt AI trong cuộc gọi (để LLM API nhận ra)

    def request_handover(self, reason: str = "") -> bool:
        """Công cụ LLM `chuyen_sang_truc_tiep`: đánh dấu cuộc gọi AI mới nhất cần chuyển trực tiếp. False nếu không có AI nào đang giữ."""
        if not self.ai_running:
            return False
        self.handover[self.ai_running[-1]] = reason or "ai"
        return True

    def cancel_all(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()
        self.tasks.clear()


def plan_from_service(data: dict[str, Any]) -> Plan | None:
    """Kế hoạch từ trường của make_call/answer_call; None nếu không yêu cầu gì."""
    message = str(data.get("message") or "").strip()
    ai = bool(data.get("ai"))
    if not message and not ai:
        return None
    # Chỉ thông báo (không AI) thì mặc định cúp máy sau khi đọc; AI thì cúp khi cuộc trò chuyện xong. Người dùng ghi đè được.
    hangup = data["hangup_after"] if "hangup_after" in data else True
    return Plan(message=message, repeat=max(1, min(3, int(data.get("repeat") or 1))), ai=ai, hangup=bool(hangup),
                engine=data.get("tts_engine") or None, language=data.get("language") or None,
                pipeline_id=data.get("pipeline_id") or None, greeting=str(data.get("greeting") or "").strip(),
                handover_rule=str(data.get("handover_rule") or "").strip())


# -- TTS và phát -----------------------------------------------------------------------------------------------------

async def async_tts_audio(hass: HomeAssistant, message: str, engine: str | None = None,
                          language: str | None = None, options: dict | None = None) -> tuple[str, bytes]:
    """(đuôi tệp, byte) của giọng đọc `message` bằng TTS của HA."""
    from homeassistant.components import tts      # nạp muộn: chỉ cần khi thật sự đọc

    media_id = tts.generate_media_source_id(hass, message, engine=engine or None, language=language or None,
                                           options=options, cache=False)
    return await tts.async_get_media_source_audio(hass, media_id)


async def _wait_playback_done(api: ZaloCallApi, call_id: str) -> None:
    deadline = time.monotonic() + SAY_MAX_WAIT_S
    await asyncio.sleep(POLL_S)
    while time.monotonic() < deadline:
        res = await api.media_control({"call_id": call_id, "action": "status", "target": "mic"})
        mic = (res or {}).get("mic")
        if not mic or not mic.get("alive"):
            return
        await asyncio.sleep(POLL_S)
    _LOGGER.warning("Phát giọng nói trong cuộc gọi %s quá %.0f s, bỏ chờ", call_id, SAY_MAX_WAIT_S)


async def _restore_mic(api: ZaloCallApi, call_id: str) -> None:
    """Đọc xong thì trả mic về nguồn mặc định (đường mic bị thay bằng tệp TTS trong lúc đọc). Không có mic mặc định thì thôi."""
    try:
        await api.media_control({"call_id": call_id, "action": "start", "target": "mic"})
    except ZaloCallError as err:
        _LOGGER.debug("Không trả được mic mặc định cho cuộc gọi %s: %s", call_id, err)


async def async_say(hass: HomeAssistant, api: ZaloCallApi, call_id: str, message: str,
                    engine: str | None = None, language: str | None = None, wait: bool = True,
                    options: dict | None = None, restore_mic: bool = False) -> None:
    """Đọc `message` lên cuộc gọi đang nói. wait: chờ đọc xong mới trả về. restore_mic: rồi trả mic về mặc định."""
    message = (message or "").strip()
    if not message:
        return
    ext, data = await async_tts_audio(hass, message, engine, language, options)
    res = await api.call_say(call_id, "tts." + (ext or "mp3"), data)
    if not (res or {}).get("ok"):
        raise ZaloCallError("Không phát được giọng nói: %s" % (res or {}).get("error", "lỗi"))
    if wait:
        await _wait_playback_done(api, call_id)
        await asyncio.sleep(0.3)                 # khung cuối còn trong hàng đợi gửi
        if restore_mic:
            await _restore_mic(api, call_id)


async def _call_status(api: ZaloCallApi, call_id: str) -> str | None:
    for c in (await api.calls() or {}).get("calls", []):
        if str(c.get("call_id")) == str(call_id):
            return c.get("status")
    return None


# -- AI nói chuyện ---------------------------------------------------------------------------------------------------

class _Listener:
    """Đọc luồng tiếng người gọi từ app vào hàng đợi PCM; tạm bỏ tiếng khi đang đọc (tránh nghe lại chính mình)."""

    def __init__(self, hass: HomeAssistant, url: str) -> None:
        self._hass, self._url = hass, url
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(QUEUE_MAX)
        self.muted = False
        self.ended = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        try:
            async with async_get_clientsession(self._hass).get(self._url, timeout=aiohttp.ClientTimeout(total=None, sock_read=30)) as r:
                if r.status != 200:
                    _LOGGER.warning("Không mở được luồng tiếng người gọi (HTTP %s)", r.status)
                    return
                first = True
                async for chunk in r.content.iter_chunked(CHUNK_BYTES):
                    if first:
                        first = False
                        if chunk[:4] == b"RIFF":
                            chunk = chunk[WAV_HEADER:]
                    if self.muted or not chunk:
                        continue
                    if self.queue.full():
                        self.queue.get_nowait()
                    self.queue.put_nowait(chunk)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        finally:
            self.ended = True

    def drain(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()

    async def chunks(self) -> AsyncIterator[bytes]:
        while not self.ended or not self.queue.empty():
            try:
                yield await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if self.ended:
                    return

    def stop(self) -> None:
        if self._task:
            self._task.cancel()


async def _one_turn(hass: HomeAssistant, listener: _Listener, pipeline_id: str | None, language: str,
                    conversation_id: str | None, hint: str = PHONE_HINT,
                    context: Context | None = None) -> tuple[str, str, str | None]:
    """Nghe một câu → (chữ người gọi nói, câu trả lời của trợ lý, conversation_id). Không nghe ra chữ thì chữ = ""."""
    from homeassistant.components import assist_pipeline, stt          # nạp muộn: chỉ cần khi bật AI trong cuộc gọi
    from homeassistant.components.assist_pipeline import pipeline as pipeline_mod

    got: dict[str, Any] = {"text": "", "reply": "", "conv": conversation_id}

    def on_event(event: Any) -> None:
        data = event.data or {}
        if event.type == pipeline_mod.PipelineEventType.STT_END:
            got["text"] = str((data.get("stt_output") or {}).get("text") or "").strip()
        elif event.type == pipeline_mod.PipelineEventType.INTENT_END:
            out = data.get("intent_output") or {}
            got["conv"] = out.get("conversation_id") or got["conv"]
            got["reply"] = str((((out.get("response") or {}).get("speech") or {}).get("plain") or {}).get("speech") or "").strip()
        elif event.type == pipeline_mod.PipelineEventType.ERROR:
            _LOGGER.debug("Assist pipeline trong cuộc gọi: %s", (data or {}).get("code"))

    meta = stt.SpeechMetadata(language=language, format=stt.AudioFormats.WAV, codec=stt.AudioCodecs.PCM,
                              bit_rate=stt.AudioBitRates.BITRATE_16, sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
                              channel=stt.AudioChannels.CHANNEL_MONO)
    stream = listener.chunks()
    extra: dict[str, Any] = {}
    if "conversation_extra_system_prompt" in inspect.signature(assist_pipeline.async_pipeline_from_audio_stream).parameters:
        extra["conversation_extra_system_prompt"] = hint      # HA cũ không có tham số này thì bỏ qua
    try:
        async with asyncio.timeout(TURN_TIMEOUT_S):
            await assist_pipeline.async_pipeline_from_audio_stream(
                hass, context=context or Context(), event_callback=on_event, stt_metadata=meta, stt_stream=stream,
                pipeline_id=pipeline_id, conversation_id=conversation_id,
                end_stage=pipeline_mod.PipelineStage.INTENT,
                audio_settings=pipeline_mod.AudioSettings(is_vad_enabled=True, silence_seconds=0.8), **extra)
    except (asyncio.TimeoutError, TimeoutError):
        pass
    finally:
        await stream.aclose()
    return got["text"], got["reply"], got["conv"]


async def async_run_ai(hass: HomeAssistant, api: ZaloCallApi, call_id: str, plan: Plan,
                       voice: CallVoice | None = None) -> dict[str, Any]:
    """Vòng AI nói chuyện cho tới khi cuộc gọi hết / im lặng / quá giới hạn / AI tự chuyển sang trực tiếp.
    -> {"handover": bool, "heard": câu cuối người gọi nói}."""
    from homeassistant.components.assist_pipeline import pipeline as pipeline_mod

    pipeline = pipeline_mod.async_get_pipeline(hass, plan.pipeline_id)
    language = plan.language or pipeline.stt_language or hass.config.language
    tts_engine = plan.engine or pipeline.tts_engine
    tts_language = plan.language or pipeline.tts_language
    tts_options = {"voice": pipeline.tts_voice} if pipeline.tts_voice else None
    media = await api.call_media_status(call_id)
    token = (media or {}).get("audio_token")
    if not token:
        raise ZaloCallError("App chưa có luồng tiếng của cuộc gọi %s" % call_id)
    listener = _Listener(hass, "%s/api/call/audio/tap/%s" % (api.url, token))
    listener.start()
    start, conv, idle, turns = time.monotonic(), None, 0, 0
    hint, handover, heard = phone_hint(plan.handover_rule), False, ""
    context = Context()                           # lượt AI trong cuộc gọi có Context riêng: LLM API nhận ra để chỉ cho công cụ chuyển máy
    if voice is not None:
        voice.call_context_ids.add(context.id)
        voice.ai_running.append(call_id)
    try:
        if plan.greeting:
            listener.muted = True
            await async_say(hass, api, call_id, plan.greeting, tts_engine, tts_language, options=tts_options)
            listener.drain()
            listener.muted = False
        while turns < MAX_TURNS and time.monotonic() - start < MAX_CALL_S and not listener.ended:
            if await _call_status(api, call_id) != "answered":
                break
            text, reply, conv = await _one_turn(hass, listener, plan.pipeline_id, language, conv, hint, context)
            turns += 1
            if not text:
                idle += 1
                if idle >= IDLE_TURNS:
                    break
                continue
            idle = 0
            heard = text
            if HANDOVER_RE.search(reply):                 # AI tự quyết chuyển sang trực tiếp: đọc nốt câu (không có dấu) rồi dừng
                reply, handover = HANDOVER_RE.sub("", reply).strip(), True
            if voice is not None and call_id in voice.handover:      # hoặc AI gọi công cụ chuyen_sang_truc_tiep
                handover = True
            if reply:
                listener.muted = True
                try:
                    await async_say(hass, api, call_id, reply, tts_engine, tts_language, options=tts_options)
                finally:
                    listener.drain()
                    listener.muted = False
            if handover:
                break
        _LOGGER.debug("AI trong cuộc gọi %s xong sau %d lượt (chuyển máy: %s)", call_id, turns, handover)
        return {"handover": handover, "heard": heard}
    finally:
        listener.stop()
        if voice is not None:
            voice.call_context_ids.discard(context.id)
            if call_id in voice.ai_running:
                voice.ai_running.remove(call_id)
            voice.handover.pop(call_id, None)


# -- Vòng đời: chạy kế hoạch khi cuộc gọi được nghe máy ---------------------------------------------------------------

async def _run_plan(hass: HomeAssistant, rt: Any, call_id: str, plan: Plan) -> None:
    api: ZaloCallApi = rt.api
    try:
        for i in range(plan.repeat if plan.message else 0):
            await async_say(hass, api, call_id, plan.message, plan.engine, plan.language)
            if i + 1 < plan.repeat:
                await asyncio.sleep(1.0)
        handed = False
        if plan.ai:
            res = await async_run_ai(hass, api, call_id, plan, rt.voice)
            handed = bool(res.get("handover"))
            if handed:
                # AI quyết định chuyển: trả mic nhà (loa/mic đã nối từ lúc nghe máy), KHÔNG cúp máy, báo HA để automation xử lý.
                await _restore_mic(api, call_id)
                hass.bus.async_fire("zalo_call_ai_handover", {"call_id": call_id, "heard": res.get("heard", "")})
        if handed:
            pass
        elif plan.hangup:
            await api.call_end(call_id)
        else:
            await _restore_mic(api, call_id)
    except asyncio.CancelledError:
        raise
    except ZaloCallError as err:
        _LOGGER.warning("Giọng nói trong cuộc gọi %s: %s", call_id, err)
    except Exception:  # noqa: BLE001 - lỗi TTS/pipeline không được làm sập webhook
        _LOGGER.exception("Giọng nói trong cuộc gọi %s lỗi", call_id)
    finally:
        rt.voice.tasks.pop(call_id, None)


async def async_take_over(rt: Any, call_id: str | None = None) -> dict[str, Any]:
    """Người thật tiếp quản cuộc gọi đang do AI/thông báo giữ: dừng kế hoạch giọng nói, trả mic về nguồn mặc định (loa/mic nhà
    đã nối từ lúc nghe máy). call_id trống = cuộc gọi đang nói. Không có AI đang chạy thì cuộc gọi vốn đã trực tiếp."""
    api: ZaloCallApi = rt.api
    if call_id in (None, ""):
        active = (await api.calls() or {}).get("active")
        if not active or active.get("status") != "answered":
            raise ZaloCallError("Không có cuộc gọi nào đang nói")
        call_id = active["call_id"]
    cid = str(call_id)
    rt.voice.plans.pop(cid, None)
    task = rt.voice.tasks.pop(cid, None)
    was_ai = task is not None
    if task is not None:
        task.cancel()
    await _restore_mic(api, cid)
    return {"call_id": cid, "ai_was_running": was_ai}


def on_call_state(hass: HomeAssistant, rt: Any, state: str, call_id: Any, terminal: tuple, ai_incoming: bool,
                  greeting: str, answer_source: str = "", handover_rule: str = "") -> None:
    """Gọi từ webhook cuộc gọi. ai_incoming: công tắc «AI trong cuộc gọi» — chỉ áp cho cuộc gọi ĐẾN do app TỰ NGHE MÁY
    (answer_source == "auto"); người thật nghe máy (answer_call, R1…) thì AI không chen vào, trừ khi answer_call có ai=true."""
    cid = str(call_id)
    voice: CallVoice = rt.voice
    if state == "incoming":
        voice.incoming.add(cid)
    elif state == "answered":
        plan = voice.plans.pop(cid, None)
        if plan is None and ai_incoming and cid in voice.incoming and answer_source == "auto":
            plan = Plan(ai=True, hangup=True, greeting=greeting or DEFAULT_GREETING, handover_rule=handover_rule)
        if plan is not None and cid not in voice.tasks:
            voice.tasks[cid] = hass.async_create_task(_run_plan(hass, rt, cid, plan))
    elif state in terminal:
        voice.plans.pop(cid, None)
        voice.incoming.discard(cid)
        task = voice.tasks.pop(cid, None)
        if task:
            task.cancel()
