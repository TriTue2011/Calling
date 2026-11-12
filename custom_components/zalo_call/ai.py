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
from .call_voice import PUBLIC_HINT, async_tts_audio, pipeline_agent, pipeline_tts
from . import reply_policy
from .rules import get_rules, resolve as resolve_rule
from .styler import _speech, async_markup_for, auto_aspects, autos_off, build_inline_hint, looks_marked
from .const import CONF_AI_EMPHASIS, CONF_AI_FORMAT, CONF_TEXT_AI_INLINE, CONF_TEXT_AI_SMART, CONF_TEXT_AUTO_EMOJI, DOMAIN

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
    """Tin nhắn đến từ webhook, xử lý THEO QUY TẮC (dịch vụ set_rule). Không có quy tắc (hoặc không biết người gửi quen/lạ) = không làm gì:
    không STT, không AI, không gửi gì. Tin thoại 1-1: quy tắc `voice_text` thì Zalo STT chuyển thành chữ (bắn zalo_call_voice_text); quy tắc
    `reply_ai` thì AI (pipeline/agent trong quy tắc) trả lời, bằng tin thoại nếu tin đến là tin thoại."""
    rt = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if rt is None or event.get("is_self"):
        return
    rule = resolve_rule(get_rules(rt.defaults), event.get("thread_id"), event.get("thread_type"), event.get("contact_status"))
    if rule is None:
        return
    if str(event.get("kind") or "") == "voice" and event.get("voice_url") and not event.get("content"):
        if _is_group(event.get("thread_type")) or not rule.get("voice_text"):
            return
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
    if rule.get("reply_ai") and event.get("content"):
        ok, text = reply_policy.evaluate(rule, event)           # nhóm: từ khóa gọi + người gửi được phép (xem reply_policy.py)
        if not ok:
            return
        await async_ai_reply(hass, entry, dict(event, content=text, original_content=event.get("content")), rule)


async def _async_voice_reply(hass: HomeAssistant, rt, thread_id: str, reply: str, rule: dict, thread_type: str) -> bool:
    """Trả lời bằng TIN THOẠI: TTS (giọng của Assist pipeline của thiết bị đã chọn, không thì pipeline ưu tiên) rồi gửi tin thoại.
    False nếu không làm được (nguời gọi sẽ gửi chữ thay thế)."""
    try:
        pid = rule.get("pipeline") or None
        engine, language, options = pipeline_tts(hass, pid)
        speech = _MD.sub("", reply).strip()
        ext, data = await async_tts_audio(hass, speech, engine, language, options)
        await rt.api.thread_sendvoice(thread_type, thread_id, "tra_loi." + (ext or "mp3"), data, _MIME.get(ext or "mp3", "application/octet-stream"))
        return True
    except Exception as err:  # noqa: BLE001 - TTS/gửi lỗi thì gửi chữ
        _LOGGER.warning("AI không trả lời bằng tin thoại được (%s), gửi chữ", err)
        return False


async def async_ai_reply(hass: HomeAssistant, entry: ConfigEntry,
                         event: dict, rule: dict) -> None:
    rt = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if rt is None:
        return
    d = rt.defaults
    text = str(event.get("content") or "").strip()
    thread_id = str(event.get("thread_id") or "")
    if not text or not thread_id or event.get("is_self"):
        return
    thread_type = "group" if _is_group(event.get("thread_type")) else "user"
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
        agent = rule.get("agent") or pipeline_agent(hass, rule.get("pipeline") or None)      # trợ lý trong quy tắc (hoặc của pipeline)
        if agent:
            data["agent_id"] = agent
        if not rule.get("trusted"):                                                           # lời dặn mềm: người gửi chưa xác thực
            data["text"] += "\n\n(" + PUBLIC_HINT + ")"
        try:
            resp = await hass.services.async_call(
                "conversation", "process", data, blocking=True,
                return_response=True)
            reply = _speech(resp)
            if reply and from_voice and await _async_voice_reply(hass, rt, thread_id, reply[:MAX_REPLY], rule, thread_type):
                return
            if reply:
                emphasis = d.get(CONF_AI_EMPHASIS)
                text = reply_policy.apply_prefix(rule, reply[:MAX_REPLY])
                fmt, markup = d.get(CONF_AI_FORMAT) or "plain", None
                if inline and looks_marked(text):
                    # Trợ lý đã tự định dạng trong cùng lượt: dùng luôn (markdown), không áp quy tắc cứng chồng lên các mục auto.
                    fmt, style, auto_emoji = "markdown", autos_off(style), False
                elif aspects and d.get(CONF_TEXT_AI_SMART):
                    # Chưa định dạng và bật «dùng AI đánh giá»: gọi thêm một lần (tối đa vài giây); app chỉ nhận khi chữ không đổi.
                    markup = await async_markup_for(hass, d, text, style, auto_emoji)
                # còn lại: các mục auto dùng quy tắc cứng (tức thì) ở app
                quoted = False
                qp = reply_policy.quote_payload(rule, event, thread_type, thread_id, text)
                if qp is not None:                                  # trả lời KÈM TRÍCH DẪN tin gốc (như zalo_bot); lỗi thì gửi thường
                    try:
                        await rt.api.svc("quote_message", qp)
                        quoted = True
                    except ZaloCallError as err:
                        _LOGGER.warning("Trích dẫn tin gốc không được (%s), gửi tin thường", err)
                if not quoted:
                    await rt.api.thread_send(
                        thread_type, thread_id, text, fmt,
                        None if emphasis in (None, "", "off") else emphasis,
                        None, auto_emoji, None, style, markup)
        except ZaloCallError as err:
            _LOGGER.warning("AI không gửi được trả lời cho %s: %s", thread_id, err)
        except Exception:  # noqa: BLE001 - agent lỗi không được làm sập webhook
            _LOGGER.exception("AI trả lời lỗi cho %s", thread_id)
        finally:
            _last[thread_id] = time.monotonic()
