"""Cảm biến trạng thái cuộc gọi."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import health_state, qr_login
from .const import DOMAIN
from .entity import device_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id].coordinator
    add([ZaloCallStateSensor(coordinator, entry), ZaloAccountHealthSensor(coordinator, entry), ZaloLoginStateSensor(coordinator, entry)])


class ZaloCallStateSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Trạng thái cuộc gọi"
    _attr_icon = "mdi:phone"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id + "_call_state"
        self._attr_device_info = device_info(entry)

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



class ZaloAccountHealthSensor(CoordinatorEntity, SensorEntity):
    """Sức khoẻ tài khoản Zalo: online / degraded / logged_out, kèm lý do phiên kết thúc lần cuối (xem health_state.py)."""
    _attr_has_entity_name = True
    _attr_name = "Sức khoẻ tài khoản"
    _attr_icon = "mdi:heart-pulse"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(health_state.STATES)

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id + "_account_health"
        self._attr_device_info = device_info(entry)

    @property
    def _status(self) -> dict:
        return (self.coordinator.data or {}).get("status") or {}

    @property
    def native_value(self) -> str:
        return health_state.account_state(self._status)

    @property
    def extra_state_attributes(self) -> dict:
        return health_state.attributes(self._status)


class ZaloLoginStateSensor(CoordinatorEntity, SensorEntity):
    """Trạng thái đăng nhập Zalo bằng chữ: đã đăng nhập / chưa đăng nhập / đang chờ quét QR / đã quét / mã hết hạn / lỗi (xem qr_login.py)."""
    _attr_has_entity_name = True
    _attr_name = "Trạng thái Zalo"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(qr_login.LOGIN_STATES)

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id + "_login_state"
        self._attr_device_info = device_info(entry)

    @property
    def _state(self) -> str | None:
        return qr_login.login_state(qr_login.logged_in(self.coordinator.data), (self.coordinator.data or {}).get("qr"))

    @property
    def native_value(self) -> str | None:
        return self._state

    @property
    def icon(self) -> str:
        return {"logged_in": "mdi:account-check", "waiting_qr": "mdi:qrcode-scan", "scanned": "mdi:cellphone-check", "expired": "mdi:timer-off", "error": "mdi:alert-circle"}.get(self._state or "", "mdi:account-off")

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        st = data.get("status") or {}
        out = {"mo_ta": qr_login.LOGIN_STATE_TEXT.get(self._state or "", "")}
        if st.get("login"):
            out.update({"uid": st.get("uid"), "so_dien_thoai": st.get("phonenum")})
        else:
            out.update({k: v for k, v in qr_login.attributes(data.get("qr")).items() if k in ("kieu_dang_nhap", "kieu_dang_nhap_ten", "het_han_sau_giay", "loi", "canh_bao")})
        return out
