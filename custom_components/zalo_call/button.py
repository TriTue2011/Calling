"""Nút điều khiển cuộc gọi đang diễn ra: chuyển sang video, tắt hình, tắt mic."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ZaloCallError
from .bridge_core import entity_of_label
from .call_voice import async_take_over
from . import qr_login
from .const import DOMAIN
from .entity import ZaloCallEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN][entry.entry_id]
    add([CallButton(entry, rt, "upgrade_video", "Chuyển sang video",
                    "mdi:video-plus"),
         CallButton(entry, rt, "stop_video", "Tắt hình", "mdi:video-off"),
         CallButton(entry, rt, "stop_mic", "Tắt mic cuộc gọi",
                    "mdi:microphone-off"),
         CallButton(entry, rt, "take_over", "Người nhà nói trực tiếp (dừng AI)",
                    "mdi:phone-in-talk"),
         CallButton(entry, rt, "login_web", "Đăng nhập bằng QR (Web)", "mdi:qrcode-scan"),
         CallButton(entry, rt, "login_pc", "Đăng nhập bằng QR (PC)", "mdi:qrcode-scan"),
         CallButton(entry, rt, "logout", "Đăng xuất Zalo", "mdi:logout")])


class CallButton(ZaloCallEntity, ButtonEntity):
    def __init__(self, entry: ConfigEntry, rt, key: str, name: str, icon: str) -> None:
        super().__init__(entry, "btn_" + key)
        self._rt, self._key = rt, key
        self._attr_name, self._attr_icon = name, icon

    @property
    def available(self) -> bool:
        """Nút đăng nhập mờ khi ĐÃ đăng nhập; nút đăng xuất mờ khi CHƯA đăng nhập (chưa biết thì sáng). Các nút khác luôn sáng."""
        acts = qr_login.login_actions(qr_login.logged_in(self._rt.coordinator.data))
        if self._key in ("login_web", "login_pc"):
            return acts["login"]
        if self._key == "logout":
            return acts["logout"]
        return True

    async def async_added_to_hass(self) -> None:
        if self._key in ("login_web", "login_pc", "logout"):
            self.async_on_remove(self._rt.coordinator.async_add_listener(self.async_write_ha_state))

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
            elif self._key == "take_over":
                await async_take_over(self._rt)
            elif self._key in ("login_web", "login_pc"):
                await api.qr_new(self._key.split("_", 1)[1])        # kiểu đăng nhập theo nút: web / pc
                await _refresh_qr(self.hass)
                await self._rt.coordinator.async_request_refresh()
            elif self._key == "logout":
                await api.zalo_logout()
                await _refresh_qr(self.hass)
                await self._rt.coordinator.async_request_refresh()
            elif self._key == "stop_video":
                await api.media_control({"action": "stop", "target": "video"})
            else:
                await api.media_control({"action": "stop", "target": "mic"})
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err


async def _refresh_qr(hass: HomeAssistant) -> None:
    """Cập nhật ngay thực thể ảnh QR (nếu có) sau khi bắt đầu đăng nhập/đăng xuất."""
    ent = next((e for e in hass.data.get(DOMAIN + "_qr_entities", {}).values()), None)
    if ent is not None:
        await ent.async_refresh_now()
