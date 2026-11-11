"""AI tự trả lời tin nhắn 1-1 (kiểu chăm sóc khách hàng).

Dùng agent hội thoại của chính HA (OpenAI, DeepSeek, local_openai, ...):
mỗi người nhắn có một conversation_id riêng nên AI nhớ ngữ cảnh từng khách.
Chỉ trả lời tin của người khác (tin tự gửi không đến webhook, và ở đây còn
chặn thêm một lớp), và chỉ trả lời hội thoại 1-1.
"""
from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import ZaloCallError
from .const import (CONF_AI_AGENT, CONF_TEXT_AUTO_EMOJI, CONF_AI_EMPHASIS, CONF_AI_ENABLED, CONF_AI_FORMAT, CONF_AI_THREADS,
                    DOMAIN)

_LOGGER = logging.getLogger(__name__)
MIN_INTERVAL = 2.0        # giây giữa hai lượt trả lời cùng một người
MAX_REPLY = 2000          # cắt câu trả lời dài bất thường
_locks: dict[str, asyncio.Lock] = {}
_last: dict[str, float] = {}


def _is_group(thread_type) -> bool:
    return str(thread_type).lower() in ("1", "group")


def _speech(resp: dict) -> str:
    try:
        return resp["response"]["speech"]["plain"]["speech"].strip()
    except (KeyError, TypeError, AttributeError):
        return ""


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
        data = {"text": text, "conversation_id": "zalo_call_" + thread_id,
                "language": hass.config.language}
        if d.get(CONF_AI_AGENT):
            data["agent_id"] = d.get(CONF_AI_AGENT)
        try:
            resp = await hass.services.async_call(
                "conversation", "process", data, blocking=True,
                return_response=True)
            reply = _speech(resp)
            if reply:
                emphasis = d.get(CONF_AI_EMPHASIS)
                await rt.api.thread_send(
                    "user", thread_id, reply[:MAX_REPLY], d.get(CONF_AI_FORMAT) or "plain",
                    None if emphasis in (None, "", "off") else emphasis,
                    None, bool(d.get(CONF_TEXT_AUTO_EMOJI)), None, d.text_style())
        except ZaloCallError as err:
            _LOGGER.warning("AI không gửi được trả lời cho %s: %s", thread_id, err)
        except Exception:  # noqa: BLE001 - agent lỗi không được làm sập webhook
            _LOGGER.exception("AI trả lời lỗi cho %s", thread_id)
        finally:
            _last[thread_id] = time.monotonic()
