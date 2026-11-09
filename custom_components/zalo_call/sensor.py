"""Cảm biến trạng thái cuộc gọi."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    add([ZaloCallStateSensor(hass.data[DOMAIN][entry.entry_id].coordinator, entry)])


class ZaloCallStateSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Trạng thái cuộc gọi"
    _attr_icon = "mdi:phone"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id + "_call_state"

    @property
    def _calls(self) -> dict:
        return (self.coordinator.data or {}).get("calls") or {}

    @property
    def native_value(self) -> str:
        active = self._calls.get("active")
        if not active:
            return "idle"
        return "active" if active.get("answered_at") else "ringing"

    @property
    def extra_state_attributes(self) -> dict:
        calls = self._calls.get("calls") or []
        c = self._calls.get("active") or (calls[0] if calls else {})
        return {k: c.get(k) for k in ("call_id", "peer", "thread_id", "type",
                                      "status", "started_at", "ended_at",
                                      "detail", "answer_source")
                if k in c}
