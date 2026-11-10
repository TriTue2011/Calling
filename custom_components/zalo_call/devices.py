"""Thiết bị mặc định của tích hợp: loa, mic, camera, tự động phát.

Nằm trên THIẾT BỊ (các thực thể select/text/switch), lưu bằng `Store` của HA —
không phải options (bánh răng) nên đổi không làm tải lại tích hợp. Lần đầu có
tuỳ chọn cũ (speaker/mic/mic_url/camera) thì nhập sang.
"""
from __future__ import annotations

from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (CONF_AI_AGENT, CONF_AI_ENABLED, CONF_AI_THREADS, CONF_AUTO_MIC,
                    CONF_AUTO_VIDEO, CONF_AUTO_VIDEO_DELAY, CONF_CALL_VOLUME, CONF_CAMERA,
                    CONF_ECHO_GUARD, CONF_HA_URL, CONF_MIC, CONF_MIC_URL, CONF_SPEAKER, DOMAIN,
                    ECHO_MODES, MAX_AUTO_VIDEO_DELAY, MAX_CALL_VOLUME, STORAGE_VERSION)

DEFAULTS: dict[str, Any] = {"speaker": "", "mic": "", "mic_url": "",
                            "camera": "", CONF_AUTO_MIC: True,
                            CONF_AUTO_VIDEO: True, CONF_AUTO_VIDEO_DELAY: 0,
                            CONF_CALL_VOLUME: 0,
                            CONF_ECHO_GUARD: "auto",
                            CONF_HA_URL: "", CONF_AI_ENABLED: False,
                            CONF_AI_AGENT: "", CONF_AI_THREADS: ""}
_TEXT_KEYS = ("speaker", "mic", "mic_url", "camera", CONF_HA_URL, CONF_AI_AGENT,
              CONF_AI_THREADS)
# Giá trị từng nằm trong tuỳ chọn (bánh răng): lần đầu có thì nhập sang, rồi không đọc lại.
_LEGACY = {"speaker": CONF_SPEAKER, "mic": CONF_MIC, "mic_url": CONF_MIC_URL,
           "camera": CONF_CAMERA, CONF_HA_URL: CONF_HA_URL,
           CONF_AI_ENABLED: CONF_AI_ENABLED, CONF_AI_AGENT: CONF_AI_AGENT,
           CONF_AI_THREADS: CONF_AI_THREADS}


class DeviceDefaults:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(hass, STORAGE_VERSION,
                            "%s.devices.%s" % (DOMAIN, entry_id))
        self.data: dict[str, Any] = dict(DEFAULTS)
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self, legacy_options: dict[str, Any] | None = None) -> None:
        saved = await self._store.async_load()
        saved = saved if isinstance(saved, dict) else {}
        self._merge(saved)
        # Chỉ nhập mục CHƯA có trong kho (không ghi đè điều người dùng đã đặt trên thiết bị).
        legacy = {k: (legacy_options or {}).get(v) for k, v in _LEGACY.items()
                  if k not in saved}
        legacy = {k: v for k, v in legacy.items() if v}
        if legacy:
            self._merge(legacy)
            await self._store.async_save(self.data)

    def _merge(self, patch: dict[str, Any]) -> None:
        for key in _TEXT_KEYS:
            if key in patch:
                self.data[key] = str(patch[key] or "").strip()
        if CONF_HA_URL in patch:
            self.data[CONF_HA_URL] = self.data[CONF_HA_URL].rstrip("/")
        for key in (CONF_AUTO_MIC, CONF_AUTO_VIDEO, CONF_AI_ENABLED):
            if key in patch:
                self.data[key] = bool(patch[key])
        if patch.get(CONF_ECHO_GUARD) in ECHO_MODES:
            self.data[CONF_ECHO_GUARD] = patch[CONF_ECHO_GUARD]
        if CONF_CALL_VOLUME in patch:
            try:
                self.data[CONF_CALL_VOLUME] = max(
                    0, min(MAX_CALL_VOLUME, int(patch[CONF_CALL_VOLUME])))
            except (TypeError, ValueError):
                pass
        if CONF_AUTO_VIDEO_DELAY in patch:
            try:
                self.data[CONF_AUTO_VIDEO_DELAY] = max(
                    0, min(MAX_AUTO_VIDEO_DELAY, int(patch[CONF_AUTO_VIDEO_DELAY])))
            except (TypeError, ValueError):
                pass

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
