"""Chọn loa, mic, camera mặc định cho cuộc gọi — ngay trên thiết bị (không cần bánh răng).

Danh sách lấy từ chính HA: loa = mọi media_player; camera = mọi camera; mic = camera,
vệ tinh Assist (camera Imou/Dahua, loa R1…) hoặc "URL" (ô Mic URL).
"""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .bridge_core import entity_of_label, label
from .const import DOMAIN, MIC_URL_LABEL, NONE_LABEL
from .entity import ZaloCallEntity

REFRESH = timedelta(minutes=1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN][entry.entry_id]
    add([
        DeviceSelect(hass, entry, rt, "speaker", "Loa mặc định",
                     "mdi:speaker", ("media_player",)),
        DeviceSelect(hass, entry, rt, "mic", "Mic mặc định",
                     "mdi:microphone", ("camera", "assist_satellite"),
                     extra=(MIC_URL_LABEL,)),
        DeviceSelect(hass, entry, rt, "camera", "Camera mặc định",
                     "mdi:cctv", ("camera",)),
    ])


class DeviceSelect(ZaloCallEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass, entry, rt, key, name, icon, domains, extra=()) -> None:
        super().__init__(entry, key)
        self.hass = hass
        self._rt = rt
        self._key = key
        self._domains = domains
        self._extra = extra
        self._attr_name = name
        self._attr_icon = icon

    def _label_of(self, entity_id: str) -> str:
        st = self.hass.states.get(entity_id)
        return label(entity_id, st.attributes.get("friendly_name") if st else None)

    @property
    def options(self) -> list[str]:
        ids = sorted(e for d in self._domains
                     for e in self.hass.states.async_entity_ids(d))
        opts = [NONE_LABEL, *self._extra, *[self._label_of(e) for e in ids]]
        cur = self.current_option
        if cur and cur not in opts:                # thuc the da bi go: van hien de doi/chon lai
            opts.insert(1, cur)
        return opts

    @property
    def current_option(self) -> str:
        if self._key == "mic" and self._rt.defaults.get("mic_url") \
                and not self._rt.defaults.get("mic"):
            return MIC_URL_LABEL
        value = str(self._rt.defaults.get(self._key) or "")
        return self._label_of(entity_of_label(value)) if value else NONE_LABEL

    async def async_select_option(self, option: str) -> None:
        if option == NONE_LABEL:
            patch = {self._key: ""}
            if self._key == "mic":
                patch["mic_url"] = ""
        elif option == MIC_URL_LABEL:
            patch = {"mic": ""}
        else:
            patch = {self._key: entity_of_label(option)}
            if self._key == "mic":
                patch["mic_url"] = ""
        await self._rt.defaults.async_set(**patch)
        await self._rt.bridge.async_push_defaults()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rt.defaults.add_listener(self.async_write_ha_state))
        self.async_on_remove(async_track_time_interval(
            self.hass, lambda _now: self.async_write_ha_state(), REFRESH))
