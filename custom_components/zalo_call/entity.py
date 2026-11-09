"""Gốc chung của các thực thể Zalo Call: gắn vào MỘT thiết bị trong HA."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


def device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)},
                      name="Zalo Call", manufacturer="TriTue2011",
                      model="Zalo PC app")


class ZaloCallEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, key: str) -> None:
        self._entry = entry
        self._attr_unique_id = "%s_%s" % (entry.entry_id, key)
        self._attr_device_info = device_info(entry)
