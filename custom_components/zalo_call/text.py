"""Ô nhập URL mic bất kỳ (rtsp/http…, hoặc luồng PCM của loa R1)."""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge_core import valid_url
from .const import DOMAIN
from .entity import ZaloCallEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    add([MicUrlText(entry, hass.data[DOMAIN][entry.entry_id])])


class MicUrlText(ZaloCallEntity, TextEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Mic URL"
    _attr_icon = "mdi:microphone-message"
    _attr_mode = TextMode.PASSWORD          # URL có thể chứa mật khẩu: che khi hiện
    _attr_native_min = 0
    _attr_native_max = 255

    def __init__(self, entry: ConfigEntry, rt) -> None:
        super().__init__(entry, "mic_url")
        self._rt = rt

    @property
    def native_value(self) -> str:
        return str(self._rt.defaults.get("mic_url") or "")

    async def async_set_value(self, value: str) -> None:
        value = value.strip()
        if value and not valid_url(value):
            raise ServiceValidationError(
                "Mic URL phải là rtsp/rtsps/http/https/rtmp, ví dụ rtsp://…")
        await self._rt.defaults.async_set(mic_url=value, **({"mic": ""} if value else {}))
        await self._rt.bridge.async_push_defaults()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rt.defaults.add_listener(self.async_write_ha_state))
