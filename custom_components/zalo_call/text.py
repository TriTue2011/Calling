"""Các ô nhập trên thiết bị: URL mic bất kỳ, địa chỉ HA cho app gọi lại, danh sách threadId cho AI."""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge_core import valid_url
from .const import CONF_AI_THREADS, CONF_HA_URL, DOMAIN
from .entity import ZaloCallEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN][entry.entry_id]
    add([MicUrlText(entry, rt), HaUrlText(entry, rt), AiThreadsText(entry, rt)])


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


class _PlainText(ZaloCallEntity, TextEntity):
    """Ô chữ thường lưu thẳng vào kho mặc định của thiết bị."""
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min = 0
    _attr_native_max = 255

    def __init__(self, entry: ConfigEntry, rt, key: str, name: str, icon: str) -> None:
        super().__init__(entry, key)
        self._rt, self._key = rt, key
        self._attr_name, self._attr_icon = name, icon

    @property
    def native_value(self) -> str:
        return str(self._rt.defaults.get(self._key) or "")

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rt.defaults.add_listener(self.async_write_ha_state))


class HaUrlText(_PlainText):
    """Địa chỉ HA mà app gọi được (webhook sự kiện cuộc gọi/tin nhắn, URL loa trực tiếp)."""

    def __init__(self, entry: ConfigEntry, rt) -> None:
        super().__init__(entry, rt, CONF_HA_URL, "Địa chỉ HA mà app gọi được (webhook)",
                         "mdi:home-assistant")

    async def async_set_value(self, value: str) -> None:
        value = value.strip().rstrip("/")
        if value and not value.startswith(("http://", "https://")):
            raise ServiceValidationError("Địa chỉ HA phải bắt đầu bằng http:// hoặc https://")
        await self._rt.defaults.async_set(**{self._key: value})
        await self._rt.bridge.async_push_defaults()     # URL loa trực tiếp dựa vào địa chỉ này


class AiThreadsText(_PlainText):
    def __init__(self, entry: ConfigEntry, rt) -> None:
        super().__init__(entry, rt, CONF_AI_THREADS,
                         "AI chỉ trả lời các threadId này (cách nhau dấu phẩy, trống = tất cả)",
                         "mdi:account-voice")

    async def async_set_value(self, value: str) -> None:
        await self._rt.defaults.async_set(**{self._key: value})
