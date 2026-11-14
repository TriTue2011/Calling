"""Ảnh mã QR đăng nhập Zalo (hiện trên bảng điều khiển HA); đổi theo mã mới app lấy từ Zalo."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import qr_login
from .api import ZaloCallError
from .const import DOMAIN
from .entity import ZaloCallEntity

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=4)
IDLE_RECHECK_SECONDS = 60.0          # đã đăng nhập (không có QR): chỉ hỏi app mỗi phút, khỏi gọi liên tục


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    ent = ZaloQrImage(hass, entry, hass.data[DOMAIN][entry.entry_id])
    hass.data.setdefault(DOMAIN + "_qr_entities", {})[entry.entry_id] = ent
    entry.async_on_unload(lambda: hass.data.get(DOMAIN + "_qr_entities", {}).pop(entry.entry_id, None))
    add([ent])


class ZaloQrImage(ZaloCallEntity, ImageEntity):
    _attr_name = "Mã QR đăng nhập"
    _attr_icon = "mdi:qrcode-scan"
    _attr_content_type = "image/png"
    _attr_should_poll = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, rt) -> None:
        ZaloCallEntity.__init__(self, entry, "qr_login")
        ImageEntity.__init__(self, hass)
        self._rt = rt
        self._png: bytes | None = None
        self._attrs: dict = qr_login.attributes(None)
        self._next_check = 0.0

    @property
    def available(self) -> bool:
        """Ảnh QR mờ khi ĐÃ đăng nhập (không cần quét); chưa biết trạng thái thì vẫn sáng."""
        return qr_login.login_actions(qr_login.logged_in(self._rt.coordinator.data))["login"]

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rt.coordinator.async_add_listener(self.async_write_ha_state))

    async def async_image(self) -> bytes | None:
        return self._png

    @property
    def extra_state_attributes(self) -> dict:
        return self._attrs

    async def async_update(self) -> None:
        if time.monotonic() < self._next_check:
            return
        try:
            status = await self._rt.api.qr_status()
        except ZaloCallError as err:
            _LOGGER.debug("Không đọc được trạng thái QR: %s", err)
            return
        self._attrs = qr_login.attributes(status)
        png = qr_login.png_from_data_url((status or {}).get("qr_image"))
        if png != self._png:                                   # QR mới: báo giao diện tải lại ảnh
            self._png = png
            self._attr_image_last_updated = dt_util.utcnow()
        self._next_check = time.monotonic() + (IDLE_RECHECK_SECONDS if self._attrs["trang_thai"] == "done" else 0.0)
        if self._attrs["trang_thai"] == "done" and qr_login.logged_in(self._rt.coordinator.data) is False:
            await self._rt.coordinator.async_request_refresh()      # QR báo xong mà HA còn hiện «chưa đăng nhập»: cập nhật ngay, không chờ vòng 10 giây

    async def async_refresh_now(self) -> None:
        """Gọi sau khi bắt đầu/ngừng đăng nhập để ảnh và trạng thái cập nhật ngay, không chờ vòng hỏi kế tiếp."""
        self._next_check = 0.0
        await self.async_update()
        self.async_write_ha_state()
