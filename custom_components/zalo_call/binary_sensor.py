"""Cảm biến: app đã đăng nhập Zalo chưa."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    add([ZaloLoginSensor(hass.data[DOMAIN][entry.entry_id].coordinator, entry)])


class ZaloLoginSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Đã đăng nhập Zalo"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id + "_login"

    @property
    def is_on(self) -> bool:
        return bool(((self.coordinator.data or {}).get("status") or {}).get("login"))

    @property
    def extra_state_attributes(self) -> dict:
        s = (self.coordinator.data or {}).get("status") or {}
        return {"uid": s.get("uid"), "phone": s.get("phonenum"),
                "sync": s.get("sync"), "ctrl": s.get("ctrl"),
                "app_version": s.get("version")}
