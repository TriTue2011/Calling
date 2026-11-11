"""Các ô chữ còn lại: địa chỉ HA cho app gọi lại. (Mic/loa/camera, quy tắc cuộc gọi và AI đặt bằng dịch vụ.)"""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge_core import valid_url
from .const import CONF_HA_URL, DOMAIN
from .entity import ZaloCallEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN][entry.entry_id]
    add([HaUrlText(entry, rt)])


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
        super().__init__(entry, rt, CONF_HA_URL, "Địa chỉ HA cho app",
                         "mdi:home-assistant")

    async def async_set_value(self, value: str) -> None:
        value = value.strip().rstrip("/")
        if value and not value.startswith(("http://", "https://")):
            raise ServiceValidationError("Địa chỉ HA phải bắt đầu bằng http:// hoặc https://")
        await self._rt.defaults.async_set(**{self._key: value})
        await self._rt.bridge.async_push_defaults()     # URL loa trực tiếp dựa vào địa chỉ này
