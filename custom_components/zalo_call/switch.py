"""Công tắc trên thiết bị: tự phát mic khi nghe máy; tự đồng ý khi bên kia xin video; AI tự trả lời tin nhắn."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_TEXT_AI_INLINE, CONF_TEXT_AI_SMART, CONF_TEXT_AUTO_EMOJI, CONF_VIDEO_CONSENT, DOMAIN
from .entity import ZaloCallEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN][entry.entry_id]
    add([AutoSwitch(entry, rt, CONF_VIDEO_CONSENT, "Cho phép đồng ý chuyển sang video", "mdi:video-switch", push=False),
         AutoSwitch(entry, rt, CONF_TEXT_AUTO_EMOJI, "Chữ: tự thêm emoji", "mdi:emoticon-happy-outline", push=False),
         AutoSwitch(entry, rt, CONF_TEXT_AI_INLINE, "Chữ: AI tự định dạng", "mdi:flash", push=False),
         AutoSwitch(entry, rt, CONF_TEXT_AI_SMART, "Chữ: AI đánh giá", "mdi:brain", push=False)])


class AutoSwitch(ZaloCallEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, rt, key: str, name: str, icon: str,
                 push: bool = True) -> None:
        super().__init__(entry, key)
        self._rt, self._key, self._push = rt, key, push
        self._attr_name, self._attr_icon = name, icon

    @property
    def is_on(self) -> bool:
        return bool(self._rt.defaults.get(self._key))

    async def _set(self, on: bool) -> None:
        await self._rt.defaults.async_set(**{self._key: on})
        if self._push:                       # công tắc AI chỉ dùng trong HA, không cần báo app
            await self._rt.bridge.async_push_defaults()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rt.defaults.add_listener(self.async_write_ha_state))
