"""Thiết bị mặc định của tích hợp: loa, mic, camera, tự động phát.

Nằm trên THIẾT BỊ (các thực thể select/text/switch), lưu bằng `Store` của HA —
không phải options (bánh răng) nên đổi không làm tải lại tích hợp. Lần đầu có
tuỳ chọn cũ (speaker/mic/mic_url/camera) thì nhập sang.
"""
from __future__ import annotations

from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .rules import DEFAULT_RULE, RULES_KEY, empty_rules, get_rules

from .const import (TEXT_STYLE_KEYS, AI_EMPHASIS, AI_FORMATS, CONF_AI_EMPHASIS, CONF_AI_FORMAT, CONF_AUTO_MIC, CONF_AUTO_VIDEO,
                    CONF_AUTO_VIDEO_DELAY, CONF_CALL_VOLUME, CONF_CAMERA, CONF_ECHO_GUARD, CONF_HA_URL, CONF_MIC, CONF_MIC_URL, CONF_SPEAKER,
                    CONF_TEXT_AI_AGENT, CONF_TEXT_AI_INLINE, CONF_TEXT_AI_SMART, CONF_TEXT_AUTO_EMOJI, DOMAIN, ECHO_MODES, MAX_AUTO_VIDEO_DELAY,
                    MAX_CALL_VOLUME, STORAGE_VERSION)

# Mic/loa/camera mặc định, quy tắc người gọi và AI chỉ đặt bằng DỊCH VỤ (set_default_devices, set_rule…), không có ô cài đặt.
DEFAULTS: dict[str, Any] = {"speaker": "", "mic": "", "mic_url": "", "camera": "", CONF_AUTO_MIC: True,
                            CONF_AUTO_VIDEO: True, CONF_AUTO_VIDEO_DELAY: 0, CONF_CALL_VOLUME: 0, CONF_ECHO_GUARD: "auto",
                            CONF_HA_URL: "", RULES_KEY: empty_rules(),
                            CONF_AI_FORMAT: "markdown", CONF_AI_EMPHASIS: "off",
                            CONF_TEXT_AUTO_EMOJI: False, CONF_TEXT_AI_AGENT: "", CONF_TEXT_AI_INLINE: True, CONF_TEXT_AI_SMART: False,
                            **{k: ("red" if k == "text_auto_color" else "off") for k in TEXT_STYLE_KEYS}}
_TEXT_KEYS = ("speaker", "mic", "mic_url", "camera", CONF_HA_URL, CONF_TEXT_AI_AGENT)
# Giá trị từng nằm trong tuỳ chọn (bánh răng): lần đầu có thì nhập sang, rồi không đọc lại.
_LEGACY = {"speaker": CONF_SPEAKER, "mic": CONF_MIC, "mic_url": CONF_MIC_URL, "camera": CONF_CAMERA, CONF_HA_URL: CONF_HA_URL}


class DeviceDefaults:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(hass, STORAGE_VERSION,
                            "%s.devices.%s" % (DOMAIN, entry_id))
        self.data: dict[str, Any] = {**DEFAULTS, RULES_KEY: empty_rules()}   # bản sao riêng: không dùng chung dict quy tắc
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self, legacy_options: dict[str, Any] | None = None) -> None:
        saved = await self._store.async_load()
        saved = saved if isinstance(saved, dict) else {}
        self._merge(saved)
        self._migrate_ai_threads(saved)
        # Chỉ nhập mục CHƯA có trong kho (không ghi đè điều người dùng đã đặt trên thiết bị).
        legacy = {k: (legacy_options or {}).get(v) for k, v in _LEGACY.items()
                  if k not in saved}
        legacy = {k: v for k, v in legacy.items() if v}
        if legacy:
            self._merge(legacy)
            await self._store.async_save(self.data)

    def _migrate_ai_threads(self, saved: dict[str, Any]) -> None:
        """Bản cũ: AI trả lời tin 1-1 cho các threadId trong `ai_threads` (trợ lý `ai_agent`). Chuyển thành quy tắc theo threadID.
        `ai_threads` TRỐNG (cũ = «mọi người») thì KHÔNG chuyển: không tự mở cửa cho người lạ."""
        rules = get_rules(self)
        if any(rules.values()) or not saved.get("ai_enabled"):
            return
        threads = [t.strip() for t in str(saved.get("ai_threads") or "").split(",") if t.strip().isdigit()]
        agent = str(saved.get("ai_agent") or "").split("·")[-1].strip()
        if not threads or not agent.startswith("conversation."):
            return
        for tid in threads:
            rules["threads"][tid] = {**DEFAULT_RULE, "name": "(di trú ai_threads)", "reply_ai": True, "agent": agent}
        self.data[RULES_KEY] = rules

    def _merge(self, patch: dict[str, Any]) -> None:
        for key in _TEXT_KEYS:
            if key in patch:
                self.data[key] = str(patch[key] or "").strip()
        if CONF_HA_URL in patch:
            self.data[CONF_HA_URL] = self.data[CONF_HA_URL].rstrip("/")
        for key in (CONF_AUTO_MIC, CONF_AUTO_VIDEO, CONF_TEXT_AUTO_EMOJI, CONF_TEXT_AI_INLINE, CONF_TEXT_AI_SMART):
            if key in patch:
                self.data[key] = bool(patch[key])
        for key, (_, options, _) in TEXT_STYLE_KEYS.items():
            if patch.get(key) in options:
                self.data[key] = patch[key]
        if patch.get(CONF_AI_FORMAT) in AI_FORMATS:
            self.data[CONF_AI_FORMAT] = patch[CONF_AI_FORMAT]
        if patch.get(CONF_AI_EMPHASIS) in AI_EMPHASIS:
            self.data[CONF_AI_EMPHASIS] = patch[CONF_AI_EMPHASIS]
        if patch.get(CONF_ECHO_GUARD) in ECHO_MODES:
            self.data[CONF_ECHO_GUARD] = patch[CONF_ECHO_GUARD]
        if CONF_CALL_VOLUME in patch:
            try:
                self.data[CONF_CALL_VOLUME] = max(
                    0, min(MAX_CALL_VOLUME, int(patch[CONF_CALL_VOLUME])))
            except (TypeError, ValueError):
                pass
        if isinstance(patch.get(RULES_KEY), dict):          # quy tắc đã được rules.normalize kiểm tra ở dịch vụ
            self.data[RULES_KEY] = patch[RULES_KEY]
        if CONF_AUTO_VIDEO_DELAY in patch:
            try:
                self.data[CONF_AUTO_VIDEO_DELAY] = max(
                    0, min(MAX_AUTO_VIDEO_DELAY, int(patch[CONF_AUTO_VIDEO_DELAY])))
            except (TypeError, ValueError):
                pass

    def text_style(self) -> dict | None:
        """Kiểu chữ mặc định trên thiết bị dạng gửi app ({size, color, bold, italic, underline, heading, auto_color}); None nếu mục nào cũng tắt."""
        style = {name: self.get(key) for key, (name, _, _) in TEXT_STYLE_KEYS.items()}
        return style if any(style[n] != "off" for n in ("size", "color", "bold", "italic", "underline", "heading")) else None

    def get(self, key: str) -> Any:
        return self.data.get(key, DEFAULTS.get(key))

    async def async_set(self, **patch: Any) -> None:
        self._merge(patch)
        await self._store.async_save(self.data)
        for cb in list(self._listeners):
            cb()

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb) if cb in self._listeners else None
