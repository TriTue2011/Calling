"""AI tự trả lời tin nhắn 1-1 (kiểu chăm sóc khách hàng).

Dùng agent hội thoại của chính HA (OpenAI, DeepSeek, local_openai, ...):
mỗi người nhắn có một conversation_id riêng nên AI nhớ ngữ cảnh từng khách.
Chỉ trả lời tin của người khác (tin tự gửi không đến webhook, và ở đây còn
chặn thêm một lớp), và chỉ trả lời hội thoại 1-1.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import ZaloCallError
from .call_voice import async_tts_audio, pipeline_for_satellite, pipeline_tts
from .styler import _speech, async_markup_for, auto_aspects, autos_off, build_inline_hint, looks_marked
from .const import (CONF_AI_AGENT, CONF_AI_CALL_DEVICE, CONF_AI_VOICE_REPLY, CONF_AUTO_VOICE_TEXT, CONF_TEXT_AUTO_EMOJI, CONF_AI_EMPHASIS, CONF_AI_ENABLED, CONF_AI_FORMAT, CONF_TEXT_AI_INLINE, CONF_TEXT_AI_SMART, CONF_AI_THREADS,
                    DOMAIN)

_LOGGER = logging.getLogger(__name__)
MIN_INTERVAL = 2.0        # giây giữa hai lượt trả lời cùng một người
MAX_REPLY = 2000          # cắt câu trả lời dài bất thường
_locks: dict[str, asyncio.Lock] = {}
_last: dict[str, float] = {}


def _is_group(thread_type) -> bool:
    return str(thread_type).lower() in ("1", "group")


_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg", "opus": "audio/ogg", "m4a": "audio/mp4", "aac": "audio/aac"}
_MD = re.compile(r"[*_#`>~]+")


async def async_handle_message(hass: HomeAssistant, entry: ConfigEntry, event: dict) -> None:
    """Tin nhắn đến từ webhook. Tin THOẠI 1-1 (kind voice + voice_url, chưa có chữ): Zalo STT (dịch vụ voice_to_text của app) chuyển thành
    chữ, bắn sự kiện zalo_call_voice_text cho automation rồi cho AI trả lời (bằng tin thoại nếu bật). Tin chữ đi thẳng tới AI."""
    rt = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if rt is not None and str(event.get("kind") or "") == "voice" and event.get("voice_url") and not event.get("content") \
            and not event.get("is_self") and not _is_group(event.get("thread_type")) and rt.defaults.get(CONF_AUTO_VOICE_TEXT):
        try:
            res = await rt.api.voice_to_text(str(event["voice_url"]), 25)
        except ZaloCallError as err:
            _LOGGER.warning("Zalo STT không chuyển được tin thoại: %s", err)
            return
        text = str((res or {}).get("text") or "").strip() if (res or {}).get("done") and not (res or {}).get("error") else ""
        if not text:
            _LOGGER.debug("Zalo STT không ra chữ cho tin thoại %s (mã %s)", event.get("message_id"), (res or {}).get("error"))
            return
        hass.bus.async_fire("zalo_call_voice_text", {"thread_id": event.get("thread_id"), "sender_id": event.get("sender_id"),
                                                    "message_id": event.get("message_id"), "text": text})
        event = dict(event, content=text, from_voice=True)
    await async_ai_reply(hass, entry, event)


async def _async_voice_reply(hass: HomeAssistant, rt, thread_id: str, reply: str) -> bool:
    """Trả lời bằng TIN THOẠI: TTS (giọng của Assist pipeline của thiết bị đã chọn, không thì pipeline ưu tiên) rồi gửi tin thoại.
    False nếu không làm được (nguời gọi sẽ gửi chữ thay thế)."""
    try:
        pid = pipeline_for_satellite(hass, str(rt.defaults.get(CONF_AI_CALL_DEVICE) or "")) or None
        engine, language, options = pipeline_tts(hass, pid)
        speech = _MD.sub("", reply).strip()
        ext, data = await async_tts_audio(hass, speech, engine, language, options)
        await rt.api.thread_sendvoice("user", thread_id, "tra_loi." + (ext or "mp3"), data, _MIME.get(ext or "mp3", "application/octet-stream"))
        return True
    except Exception as err:  # noqa: BLE001 - TTS/gửi lỗi thì gửi chữ
        _LOGGER.warning("AI không trả lời bằng tin thoại được (%s), gửi chữ", err)
        return False


async def async_ai_reply(hass: HomeAssistant, entry: ConfigEntry,
                         event: dict) -> None:
    rt = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if rt is None:
        return
    d = rt.defaults
    if not d.get(CONF_AI_ENABLED):
        return
    text = str(event.get("content") or "").strip()
    thread_id = str(event.get("thread_id") or "")
    if not text or not thread_id or event.get("is_self") \
            or _is_group(event.get("thread_type")):
        return
    allow = [t.strip() for t in str(d.get(CONF_AI_THREADS) or "").split(",")
             if t.strip()]
    if allow and thread_id not in allow:
        return
    lock = _locks.setdefault(thread_id, asyncio.Lock())
    async with lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last.get(thread_id, 0.0))
        if wait > 0:
            await asyncio.sleep(wait)
        style, auto_emoji = d.text_style(), bool(d.get(CONF_TEXT_AUTO_EMOJI))
        aspects = auto_aspects(style, auto_emoji)
        from_voice = bool(event.get("from_voice"))
        inline = bool(aspects) and bool(d.get(CONF_TEXT_AI_INLINE)) and not from_voice          # nói chuyện bằng giọng: không dặn định dạng chữ
        # Nhanh nhất: nhúng chỉ dẫn định dạng VÀO CHÍNH lượt hỏi, trợ lý vừa trả lời vừa tự định dạng/chọn emoji, không gọi thêm lần nào.
        data = {"text": text + ("\n\n" + build_inline_hint(aspects) if inline else ""), "conversation_id": "zalo_call_" + thread_id,
                "language": hass.config.language}
        if d.get(CONF_AI_AGENT):
            data["agent_id"] = d.get(CONF_AI_AGENT)
        try:
            resp = await hass.services.async_call(
                "conversation", "process", data, blocking=True,
                return_response=True)
            reply = _speech(resp)
            if reply and from_voice and d.get(CONF_AI_VOICE_REPLY) and await _async_voice_reply(hass, rt, thread_id, reply[:MAX_REPLY]):
                return
            if reply:
                emphasis = d.get(CONF_AI_EMPHASIS)
                text = reply[:MAX_REPLY]
                fmt, markup = d.get(CONF_AI_FORMAT) or "plain", None
                if inline and looks_marked(text):
                    # Trợ lý đã tự định dạng trong cùng lượt: dùng luôn (markdown), không áp quy tắc cứng chồng lên các mục auto.
                    fmt, style, auto_emoji = "markdown", autos_off(style), False
                elif aspects and d.get(CONF_TEXT_AI_SMART):
                    # Chưa định dạng và bật «dùng AI đánh giá»: gọi thêm một lần (tối đa vài giây); app chỉ nhận khi chữ không đổi.
                    markup = await async_markup_for(hass, d, text, style, auto_emoji)
                # còn lại: các mục auto dùng quy tắc cứng (tức thì) ở app
                await rt.api.thread_send(
                    "user", thread_id, text, fmt,
                    None if emphasis in (None, "", "off") else emphasis,
                    None, auto_emoji, None, style, markup)
        except ZaloCallError as err:
            _LOGGER.warning("AI không gửi được trả lời cho %s: %s", thread_id, err)
        except Exception:  # noqa: BLE001 - agent lỗi không được làm sập webhook
            _LOGGER.exception("AI trả lời lỗi cho %s", thread_id)
        finally:
            _last[thread_id] = time.monotonic()
