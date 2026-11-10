"""Thời gian chờ trước khi tự đồng ý khi bên kia xin chuyển sang video."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (CONF_AUTO_VIDEO_DELAY, CONF_CALL_VOLUME, DOMAIN, MAX_AUTO_VIDEO_DELAY,
                    MAX_CALL_VOLUME)
from .entity import ZaloCallEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN][entry.entry_id]
    add([AutoVideoDelay(entry, rt), CallVolume(entry, rt)])


class AutoVideoDelay(ZaloCallEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Chờ trước khi tự đồng ý video"
    _attr_icon = "mdi:timer-sand"
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_AUTO_VIDEO_DELAY
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX

    def __init__(self, entry: ConfigEntry, rt) -> None:
        super().__init__(entry, CONF_AUTO_VIDEO_DELAY)
        self._rt = rt

    @property
    def native_value(self) -> float:
        return float(self._rt.defaults.get(CONF_AUTO_VIDEO_DELAY) or 0)

    async def async_set_native_value(self, value: float) -> None:
        await self._rt.defaults.async_set(**{CONF_AUTO_VIDEO_DELAY: int(value)})
        await self._rt.bridge.async_push_defaults()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rt.defaults.add_listener(self.async_write_ha_state))


class CallVolume(ZaloCallEntity, NumberEntity):
    """Âm lượng loa trong lúc gọi: đặt khi nghe máy, trả mức cũ khi cuộc gọi kết thúc."""
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Âm lượng cuộc gọi"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_CALL_VOLUME
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: ConfigEntry, rt) -> None:
        super().__init__(entry, CONF_CALL_VOLUME)
        self._rt = rt

    @property
    def native_value(self) -> float:
        return float(self._rt.defaults.get(CONF_CALL_VOLUME) or 0)

    async def async_set_native_value(self, value: float) -> None:
        # Chỉ HA dùng (bridge.start/stop đặt rồi trả âm lượng loa), không cần báo cho app.
        await self._rt.defaults.async_set(**{CONF_CALL_VOLUME: int(value)})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rt.defaults.add_listener(self.async_write_ha_state))
