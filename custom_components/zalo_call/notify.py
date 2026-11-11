"""Người nhận Zalo thành thực thể ``notify``: bạn CHỌN người/nhóm từ danh sách danh bạ (Cài đặt → Thiết bị & dịch vụ → Zalo Call → Cấu hình → «Người/nhóm
nhận tin và cuộc gọi»), mỗi người được chọn là một thực thể ``notify.<tên>``.

Mục đích chính: blueprint và tự động hoá **chọn người nhận từ danh sách thực thể** thay vì gõ tay mã Zalo. Mỗi thực thể có thuộc tính ``thread_id`` và ``type``
(``user`` hoặc ``group``) để truyền thẳng cho ``zalo_call.send_message``, ``zalo_call.make_call``, ``zalo_call.alert_call``. Gọi ``notify.send_message`` vào thực
thể này cũng gửi tin chữ tới người đó."""
from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import device_info

CONF_RECIPIENTS = "recipients"


def split_recipient(value: str) -> tuple[str, str]:
    """«user:123» / «group:456» → (loại, mã). Giá trị lạ thì coi là người dùng."""
    kind, _, rid = str(value).partition(":")
    return (kind, rid) if kind in ("user", "group") and rid else ("user", str(value))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    chosen = [str(v) for v in (entry.options.get(CONF_RECIPIENTS) or [])]
    names: dict[str, str] = {}
    if chosen:                                                        # lấy tên hiện tại từ danh bạ; lỗi mạng thì dùng mã (không chặn nạp tích hợp)
        try:
            data = await hass.data[DOMAIN][entry.entry_id].api.contacts() or {}
        except Exception:  # noqa: BLE001 - app chưa lên thì vẫn tạo thực thể, đặt tên theo mã
            data = {}
        for part, kind in (("friends", "user"), ("groups", "group")):
            for row in (data.get(part) or {}).get("rows", []):
                names["%s:%s" % (kind, row.get("id"))] = str(row.get("name") or "")
    add([ZaloRecipient(entry, v, names.get(v) or split_recipient(v)[1]) for v in chosen])


class ZaloRecipient(NotifyEntity):
    """Một người hoặc nhóm Zalo để gửi tin / gọi."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:account-box-outline"

    def __init__(self, entry: ConfigEntry, value: str, name: str) -> None:
        self._entry = entry
        self._kind, self._rid = split_recipient(value)
        self._attr_unique_id = "%s_to_%s_%s" % (entry.entry_id, self._kind, self._rid)
        self._attr_name = "Zalo %s" % name
        self._attr_device_info = device_info(entry)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"thread_id": self._rid, "type": self._kind, "loai": "nhóm" if self._kind == "group" else "người"}

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        text = "%s\n%s" % (title, message) if title else message
        await self.hass.services.async_call(DOMAIN, "send_message", {"thread_id": self._rid, "type": self._kind, "message": text}, blocking=True)
