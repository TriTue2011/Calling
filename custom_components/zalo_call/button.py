"""Nút điều khiển cuộc gọi đang diễn ra: chuyển sang video, tắt hình, tắt mic."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ZaloCallError
from .bridge_core import entity_of_label
from .const import DOMAIN
from .entity import ZaloCallEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN][entry.entry_id]
    add([CallButton(entry, rt, "upgrade_video", "Chuyển sang video",
                    "mdi:video-plus"),
         CallButton(entry, rt, "stop_video", "Tắt hình", "mdi:video-off"),
         CallButton(entry, rt, "stop_mic", "Tắt mic cuộc gọi",
                    "mdi:microphone-off")])


class CallButton(ZaloCallEntity, ButtonEntity):
    def __init__(self, entry: ConfigEntry, rt, key: str, name: str, icon: str) -> None:
        super().__init__(entry, "btn_" + key)
        self._rt, self._key = rt, key
        self._attr_name, self._attr_icon = name, icon

    async def async_press(self) -> None:
        api, bridge = self._rt.api, self._rt.bridge
        try:
            if self._key == "upgrade_video":
                cam = entity_of_label(bridge.devices_for().get("camera", ""))
                body = {}
                if cam:
                    url = await bridge.async_camera_url(cam)
                    if url:
                        body["camera_url"] = url
                await api.upgrade_video(body)
            elif self._key == "stop_video":
                await api.media_control({"action": "stop", "target": "video"})
            else:
                await api.media_control({"action": "stop", "target": "mic"})
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
