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
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZaloCallApi, ZaloCallError
from .rules import get_rules, resolve as resolve_rule
from .styler import _speech

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
# Mô hình hay làm rơi ngoặc vuông hoặc đổi "_" thành khoảng trắng (đo thật 11/11: "… ạ. CHUYEN MAY" → không bắt được, lại bị đọc to). Nên nhận: có ngoặc
# (không phân biệt hoa thường, 1-2 ngoặc) HOẶC không ngoặc nhưng VIẾT HOA nguyên cụm, đứng riêng (lời thường có dấu tiếng Việt không bao giờ khớp).
HANDOVER_RE = re.compile(r"\[{1,2}\s*(?i:CHUYEN[_\s]?MAY)\s*\]{1,2}|(?<![A-Za-z])CHUYEN[_\s]?MAY(?![A-Za-z])")
HANDOVER_HINT = ("Khi người gọi muốn nói chuyện với người trong nhà, khi có việc khẩn cấp hoặc nguy hiểm, hoặc khi bạn không giúp "
                 "được, hãy nói ngắn gọn rằng bạn sẽ chuyển máy rồi kết thúc câu trả lời bằng đúng dấu " + HANDOVER_MARK +
                 " (dấu này sẽ không được đọc ra). Sau dấu đó cuộc gọi được nối trực tiếp với thiết bị trong nhà.")


PUBLIC_HINT = ("Người gọi CHƯA được xác thực: không tiết lộ bất kỳ thông tin nào về gia đình, thiết bị, lịch sinh hoạt hay vị trí; không điều "
               "khiển thiết bị. Chỉ chào hỏi, ghi nhận lời nhắn và chuyển máy khi cần.")


def phone_hint(handover_rule: str = "", trusted: bool = False) -> str:
    """Gợi ý cho trợ lý: nói chuyện qua điện thoại + phạm vi (người chưa tin cậy) + khi nào tự chuyển sang trực tiếp.
    Đây chỉ là lớp MỀM; giới hạn thật nằm ở trợ lý được chọn cho cuộc gọi (không có quyền thiết bị) — xem rules.py."""
    rule = (" Điều kiện chuyển máy riêng: %s." % handover_rule.strip().rstrip(".")) if handover_rule and handover_rule.strip() else ""
    return PHONE_HINT + ("" if trusted else " " + PUBLIC_HINT) + " " + HANDOVER_HINT + rule


def pipeline_agent(hass: HomeAssistant, pipeline_id: str | None) -> str:
    """Trợ lý hội thoại (entity) của một Assist pipeline; "" nếu không lấy được."""
    from homeassistant.components.assist_pipeline import pipeline as pipeline_mod
    try:
        return str(pipeline_mod.async_get_pipeline(hass, pipeline_id).conversation_engine or "")
    except Exception:  # noqa: BLE001
        return ""


def pipeline_tts(hass: HomeAssistant, pipeline_id: str | None) -> tuple[str | None, str | None, dict | None]:
    """(thực thể TTS, ngôn ngữ, tuỳ chọn giọng) của một Assist pipeline (None = pipeline ưu tiên). Không lấy được thì (None, None, None)
    = TTS mặc định của HA."""
    from homeassistant.components.assist_pipeline import pipeline as pipeline_mod
    try:
        pl = pipeline_mod.async_get_pipeline(hass, pipeline_id)
    except Exception:  # noqa: BLE001 - không có pipeline: dùng TTS mặc định
        return None, None, None
    return pl.tts_engine, pl.tts_language, ({"voice": pl.tts_voice} if pl.tts_voice else None)


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
    agent_id: str = ""           # trợ lý hội thoại RIÊNG cho cuộc gọi (trống = trợ lý của pipeline)
    trusted: bool = False        # người gọi tin cậy (không dặn kiểu «chưa xác thực»)
    alert: bool = False          # cuộc gọi CẢNH BÁO: đọc `message` rồi nối thẳng thiết bị nhà, không hỏi, không trò chuyện
    video: bool = False          # cuộc gọi video: chuyển máy mới bật camera (thoại thì không)
    # Thiết bị nhà sẽ nối KHI CHUYỂN MÁY (speaker/mic/mic_url/camera/volume), chỉ gồm thứ ĐÃ CÀI trong dịch vụ. Trống = KHÔNG nối gì, kể cả khi AI muốn.
    connect: dict = field(default_factory=dict)


@dataclass
class CallVoice:
    plans: dict[str, Plan] = field(default_factory=dict)
    incoming: set[str] = field(default_factory=set)
    scheduled: set[str] = field(default_factory=set)            # call_id đã lên lịch nghe máy theo quy tắc (mỗi cuộc một lần)
    timers: dict[str, Any] = field(default_factory=dict)        # call_id -> hàm huỷ lịch
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
        for cancel in list(self.timers.values()):
            cancel()
        self.timers.clear()


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
                pipeline_id=data.get("pipeline_id") or data.get("pipeline") or None, agent_id=data.get("agent") or "", greeting=str(data.get("greeting") or "").strip(),
                handover_rule=str(data.get("handover_rule") or "").strip(),
                video=str(data.get("type") or "") == "video")


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


# Cuộc gọi AI/cảnh báo giữ máy: lúc nghe máy TẤT CẢ thiết bị nhà ĐỀU TẮT (ghi đè rỗng tường minh = không rơi về mặc định); chỉ nối khi chuyển máy.
HELD_DEVICES: dict[str, str] = {"speaker": "", "mic": "", "mic_url": "", "camera": ""}
_DEVICE_KEYS = ("speaker", "mic", "mic_url", "camera")


def devices_for_mode(devices: dict[str, Any], mode: str) -> dict[str, Any]:
    """Thiết bị sẽ nối theo chế độ `connect`: never = không gì; voice = loa + mic (bỏ camera); always = tất cả (kể cả camera)."""
    if mode not in ("voice", "always"):
        return {}
    out = {k: v for k, v in devices.items() if v not in (None, "")}
    if mode == "voice":
        out.pop("camera", None)
    return out if any(k in out for k in _DEVICE_KEYS) else {}


def rule_devices(rule: dict[str, Any]) -> dict[str, Any]:
    """Thiết bị nhà do QUY TẮC cài, lọc theo `connect` của quy tắc (mặc định never). Chỉ trường ĐÃ chọn, không rơi về mặc định."""
    out: dict[str, Any] = {k: rule[k] for k in _DEVICE_KEYS if rule.get(k)}
    if out and rule.get("volume"):
        out["volume"] = rule["volume"]
    return devices_for_mode(out, rule.get("connect") or "never")


def explicit_devices(connect: dict[str, Any]) -> dict[str, Any]:
    """Ghi đè đủ bốn nhóm thiết bị: nhóm không cài = "" (tắt tường minh), không rơi về mặc định."""
    return {**{k: "" for k in _DEVICE_KEYS}, **{k: v for k, v in connect.items() if v not in (None, "")}}


async def async_connect_devices(rt: Any, call_id: str, connect: dict[str, Any], video: bool = False) -> bool:
    """Nối thiết bị nhà vào cuộc gọi đang nói (khi chuyển máy / cảnh báo). Chỉ nối thứ đã cài; connect trống thì KHÔNG nối gì. Trả về có nối."""
    if not connect:
        return False
    override = explicit_devices(connect)
    camera = override.get("camera", "")
    if not video:
        override["camera"] = ""                           # cuộc thoại: camera chỉ vào qua «nâng lên video» bên dưới (connect: always)
    await rt.bridge.reconnect(call_id, override)           # loa kiểu media_player (play_media) + âm lượng
    fields = await rt.bridge.async_call_fields(override)    # mic_url/mic_format/camera_url/speaker_url/echo_guard; nhóm không cài = "off"
    res = await rt.api.media_control({"call_id": call_id, "action": "start", "target": "both", **fields})
    if res and res.get("ok") is False:
        raise ZaloCallError("App không nối được thiết bị nhà: %s" % res.get("error", "lỗi"))
    if camera and not video:
        cam = await rt.bridge.async_call_fields({"camera": camera})
        up = await rt.api.upgrade_video({"call_id": call_id, **({"camera_url": cam["camera_url"]} if cam.get("camera_url") else {})})
        if up and up.get("ok") is False:
            _LOGGER.warning("Cuộc gọi %s: nối được loa/mic nhưng không nâng lên video: %s", call_id, up.get("error", "lỗi"))
    return True


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
                    context: Context | None = None, agent_id: str = "") -> tuple[str, str, str | None]:
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
                # Có trợ lý riêng: pipeline chỉ làm STT, câu hỏi đi thẳng tới TRỢ LÝ ĐÓ (quyền của nó mới là giới hạn thật).
                end_stage=pipeline_mod.PipelineStage.STT if agent_id else pipeline_mod.PipelineStage.INTENT,
                audio_settings=pipeline_mod.AudioSettings(is_vad_enabled=True, silence_seconds=0.8), **extra)
    except (asyncio.TimeoutError, TimeoutError):
        pass
    finally:
        await stream.aclose()
    if agent_id and got["text"]:
        resp = await hass.services.async_call(
            "conversation", "process",
            {"text": "%s\n\n(%s)" % (got["text"], hint), "language": language, "agent_id": agent_id,
             **({"conversation_id": got["conv"]} if got["conv"] else {})},
            blocking=True, return_response=True, context=context or Context())
        got["reply"] = _speech(resp)
        got["conv"] = (resp or {}).get("conversation_id") or got["conv"]
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
    hint, handover, heard = phone_hint(plan.handover_rule, plan.trusted), False, ""
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
            text, reply, conv = await _one_turn(hass, listener, plan.pipeline_id, language, conv, hint, context, plan.agent_id)
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
        engine, language, options = plan.engine, plan.language, None
        if plan.pipeline_id and not engine:            # đã chọn thiết bị Assist/pipeline: đọc thông báo bằng đúng giọng của nó
            engine, tts_lang, options = pipeline_tts(hass, plan.pipeline_id)
            language = language or tts_lang
        for i in range(plan.repeat if plan.message else 0):
            await async_say(hass, api, call_id, plan.message, engine, language, options=options)
            if i + 1 < plan.repeat:
                await asyncio.sleep(1.0)
        handed, reason, heard = False, "", ""
        if plan.alert:
            handed, reason = True, "alert"                  # cảnh báo: đọc xong là nối thẳng, không hỏi
        elif plan.ai:
            res = await async_run_ai(hass, api, call_id, plan, rt.voice)
            handed, reason, heard = bool(res.get("handover")), "ai", res.get("heard", "")
        if handed:
            # Chuyển trực tiếp: KHÔNG cúp máy, nối thiết bị đã cài (không cài = không nối), báo HA để automation xử lý.
            connected = await async_connect_devices(rt, call_id, plan.connect, plan.video)
            if connected or not plan.alert:
                hass.bus.async_fire("zalo_call_ai_handover", {"call_id": call_id, "heard": heard, "reason": reason, "connected": connected})
            else:
                handed = False                              # cảnh báo mà chưa cài thiết bị nào: chỉ là thông báo, theo hangup_after
        if handed:
            pass
        elif plan.hangup:
            await api.call_end(call_id)
        elif not (plan.ai or plan.alert):
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
    plan = rt.voice.plans.pop(cid, None)
    task = rt.voice.tasks.pop(cid, None)
    was_ai = task is not None
    if task is not None:
        task.cancel()
    if not (plan is not None and await async_connect_devices(rt, cid, plan.connect, plan.video)):
        await _restore_mic(api, cid)                  # không có thiết bị cài sẵn cho cuộc này: người bấm tiếp quản thì dùng mic mặc định
    return {"call_id": cid, "ai_was_running": was_ai}


def _devices_override(rule: dict[str, Any]) -> dict[str, Any]:
    """Thiết bị nhà lúc NGHE MÁY của cuộc gọi do quy tắc. AI giữ máy: tất cả TẮT (chỉ nối khi chuyển máy). Không AI: chỉ thiết bị
    quy tắc đã cài theo `connect`, không rơi về mặc định; không cài = tắt hết."""
    if rule.get("ai"):
        return dict(HELD_DEVICES)
    connect = rule_devices(rule)
    return explicit_devices(connect) if connect else dict(HELD_DEVICES)


def _plan_from_rule(rule: dict[str, Any], video: bool = False) -> Plan | None:
    if not rule.get("ai"):
        return None
    return Plan(ai=True, hangup=True, pipeline_id=rule.get("pipeline") or None, agent_id=rule.get("agent") or "",
                greeting=rule.get("greeting") or DEFAULT_GREETING, handover_rule=rule.get("handover_rule") or "",
                trusted=bool(rule.get("trusted")), video=video, connect=rule_devices(rule))


async def _answer_by_rule(hass: HomeAssistant, rt: Any, call_id: str, rule: dict[str, Any], video: bool = False) -> None:
    """Hết giờ chờ: hỏi lại app xem cuộc gọi còn đang đổ chuông không (người gọi có thể đã cúp), rồi nghe máy theo quy tắc."""
    api: ZaloCallApi = rt.api
    voice: CallVoice = rt.voice
    try:
        if await _call_status(api, call_id) != "incoming":
            return
        override = _devices_override(rule)
        rt.bridge.remember(call_id, override)
        fields = await rt.bridge.async_call_fields(override)
        plan = _plan_from_rule(rule, video)
        if plan is not None:
            voice.plans[call_id] = plan               # đăng ký TRƯỚC khi nghe: webhook «đã nghe máy» có thể đến ngay
        try:
            res = await api.call_answer(call_id, fields)
        except ZaloCallError:
            voice.plans.pop(call_id, None)
            raise
        if not (res or {}).get("ok", True):
            voice.plans.pop(call_id, None)
            _LOGGER.warning("Không nghe máy được cuộc gọi %s: %s", call_id, (res or {}).get("error"))
    except asyncio.CancelledError:
        raise
    except ZaloCallError as err:
        _LOGGER.warning("Nghe máy theo quy tắc cuộc gọi %s lỗi: %s", call_id, err)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Nghe máy theo quy tắc cuộc gọi %s lỗi", call_id)


def schedule_answer(hass: HomeAssistant, rt: Any, payload: dict[str, Any]) -> bool:
    """Cuộc gọi 1-1 ĐẾN: áp quy tắc (theo threadID, rồi danh bạ/người lạ). Không có quy tắc, hoặc quy tắc không cho nghe loại cuộc gọi
    này, hoặc không biết người gọi quen hay lạ → KHÔNG làm gì (chỉ đổ chuông). True nếu đã lên lịch nghe."""
    cid = str(payload.get("call_id"))
    rule = resolve_rule(get_rules(rt.defaults), payload.get("thread_id"), "user", payload.get("contact_status"))
    if not rule or not rule.get("answer"):
        return False
    ctype = "video" if str(payload.get("call_type_raw")) == "1" else "voice"        # 0 thoại / 1 video theo zca-js (chưa kiểm cuộc thật)
    if ctype not in rule.get("call_types", ()):
        return False
    voice: CallVoice = rt.voice
    if cid in voice.scheduled:
        return False                                     # webhook «incoming» đến hai lần: chỉ một lịch
    voice.scheduled.add(cid)

    async def _go(_now: Any) -> None:
        voice.timers.pop(cid, None)
        await _answer_by_rule(hass, rt, cid, rule, ctype == "video")

    voice.timers[cid] = async_call_later(hass, int(rule.get("answer_delay", 0)), _go)
    return True


def on_call_state(hass: HomeAssistant, rt: Any, state: str, call_id: Any, terminal: tuple, payload: dict[str, Any] | None = None) -> None:
    """Gọi từ webhook cuộc gọi: «incoming» → áp quy tắc nghe máy; «answered» → chạy kế hoạch (thông báo/AI); kết thúc → dọn lịch/kế hoạch."""
    cid = str(call_id)
    voice: CallVoice = rt.voice
    if state == "incoming":
        voice.incoming.add(cid)
        schedule_answer(hass, rt, payload or {"call_id": cid})
    elif state == "answered":
        plan = voice.plans.pop(cid, None)
        if plan is not None and cid not in voice.tasks:
            voice.tasks[cid] = hass.async_create_task(_run_plan(hass, rt, cid, plan))
    elif state in terminal:
        cancel = voice.timers.pop(cid, None)
        if cancel:
            cancel()
        voice.scheduled.discard(cid)
        voice.plans.pop(cid, None)
        voice.incoming.discard(cid)
        task = voice.tasks.pop(cid, None)
        if task:
            task.cancel()
