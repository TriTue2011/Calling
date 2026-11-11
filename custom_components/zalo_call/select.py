"""Chọn loa, mic, camera mặc định cho cuộc gọi — ngay trên thiết bị (không cần bánh răng).

Danh sách lấy từ chính HA: loa = mọi media_player; camera = mọi camera; mic = camera,
vệ tinh Assist (camera Imou/Dahua, loa R1…) hoặc "URL" (ô Mic URL).
"""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .bridge_core import entity_of_label, label
from .const import (AI_EMPHASIS, AI_FORMATS, CONF_AI_EMPHASIS, CONF_AI_FORMAT, CONF_TEXT_AI_AGENT, DOMAIN, NONE_LABEL, TEXT_STYLE_KEYS)
from .entity import ZaloCallEntity

REFRESH = timedelta(minutes=1)
# Kiểu chữ mặc định cho mọi tin tích hợp gửi (dịch vụ send_message ghi đè từng tin); mỗi ô có «auto» (tự theo nội dung chữ).
_TEXT_STYLE_SELECTS = (
    ("text_size", "Chữ: cỡ chữ", "mdi:format-size"),
    ("text_color", "Chữ: màu chữ", "mdi:palette"),
    ("text_bold", "Chữ: in đậm", "mdi:format-bold"),
    ("text_italic", "Chữ: in nghiêng", "mdi:format-italic"),
    ("text_underline", "Chữ: gạch chân", "mdi:format-underline"),
    ("text_heading", "Chữ: tiêu đề", "mdi:format-header-1"),
    ("text_auto_color", "Chữ: màu cho auto", "mdi:invert-colors"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN][entry.entry_id]
    add([
        DeviceSelect(hass, entry, rt, CONF_TEXT_AI_AGENT, "Chữ: trợ lý auto", "mdi:forum-outline", ("conversation",), push=False),
        AiOptionSelect(entry, rt, CONF_AI_FORMAT, "AI: định dạng chữ", "mdi:format-text", AI_FORMATS),
        AiOptionSelect(entry, rt, CONF_AI_EMPHASIS, "AI: nhấn mạnh số", "mdi:palette", AI_EMPHASIS),
        *[AiOptionSelect(entry, rt, key, name, icon, TEXT_STYLE_KEYS[key][1]) for key, name, icon in _TEXT_STYLE_SELECTS],
    ])


class DeviceSelect(ZaloCallEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass, entry, rt, key, name, icon, domains, extra=(), push=True) -> None:
        super().__init__(entry, key)
        self._push = push
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
        value = str(self._rt.defaults.get(self._key) or "")
        return self._label_of(entity_of_label(value)) if value else NONE_LABEL

    async def async_select_option(self, option: str) -> None:
        patch = {self._key: "" if option == NONE_LABEL else entity_of_label(option)}
        await self._rt.defaults.async_set(**patch)
        if self._push:
            await self._rt.bridge.async_push_defaults()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rt.defaults.add_listener(self.async_write_ha_state))
        @callback
        def _lam_moi(_now) -> None:
            # PHẢI là @callback: hàm thường bị HA chạy ở luồng nền, và async_write_ha_state
            # gọi từ luồng ngoài vòng lặp thì HA báo lỗi mỗi phút (đo 10/11/2026).
            self.async_write_ha_state()

        self.async_on_remove(async_track_time_interval(self.hass, _lam_moi, REFRESH))


class AiOptionSelect(ZaloCallEntity, SelectEntity):
    """Ô chọn một giá trị cố định cho cách AI định dạng trả lời (chỉ dùng trong HA, không cần báo app)."""
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, rt, key: str, name: str, icon: str, options) -> None:
        super().__init__(entry, key)
        self._rt, self._key = rt, key
        self._attr_name, self._attr_icon, self._attr_options = name, icon, list(options)

    @property
    def current_option(self) -> str:
        return str(self._rt.defaults.get(self._key))

    async def async_select_option(self, option: str) -> None:
        await self._rt.defaults.async_set(**{self._key: option})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rt.defaults.add_listener(self.async_write_ha_state))
