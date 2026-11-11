"""Người nhận Zalo thành thực thể ``notify``: bạn CHỌN người/nhóm từ danh sách danh bạ (Cài đặt → Thiết bị & dịch vụ → Zalo Call → Cấu hình → «Người/nhóm
nhận tin và cuộc gọi»), mỗi người được chọn là một thực thể ``notify.<tên>``.

Mục đích chính: blueprint và tự động hoá **chọn người nhận từ danh sách thực thể** thay vì gõ tay mã Zalo. Mỗi thực thể có thuộc tính ``thread_id`` và ``type``
(``user`` hoặc ``group``) để truyền thẳng cho ``zalo_call.send_message``, ``zalo_call.make_call``, ``zalo_call.alert_call``. Gọi ``notify.send_message`` vào thực
thể này cũng gửi tin chữ tới người đó."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .entity import device_info

CONF_RECIPIENTS = "recipients"


def split_recipient(value: str) -> tuple[str, str]:
    """«user:123» / «group:456» → (loại, mã). Giá trị lạ thì coi là người dùng."""
    kind, _, rid = str(value).partition(":")
    return (kind, rid) if kind in ("user", "group") and rid else ("user", str(value))


REFRESH_EVERY = timedelta(hours=1)          # danh bạ đổi (bạn mới, nhóm mới) thì thêm thực thể mới sau tối đa chừng này


async def _contact_names(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str] | None:
    """{«user:<id>» | «group:<id>»: tên} của TOÀN BỘ danh bạ; None nếu app chưa lên (đừng xoá/đổi gì khi không đọc được)."""
    try:
        data = await hass.data[DOMAIN][entry.entry_id].api.contacts() or {}
    except Exception:  # noqa: BLE001 - app chưa lên thì giữ nguyên hiện trạng
        return None
    names: dict[str, str] = {}
    for part, kind in (("friends", "user"), ("groups", "group")):
        for row in (data.get(part) or {}).get("rows", []):
            if row.get("id"):
                names["%s:%s" % (kind, row.get("id"))] = str(row.get("name") or "")
    return names


def _display_names(names: dict[str, str]) -> dict[str, str]:
    """Tên hiển thị: trùng tên thì thêm 4 số cuối mã để phân biệt ngay trong ô chọn (tên có thể trùng, mã thì duy nhất)."""
    count: dict[str, int] = {}
    for v, n in names.items():
        count[n] = count.get(n, 0) + 1
    return {v: ("%s (…%s)" % (n, split_recipient(v)[1][-4:]) if n and count[n] > 1 else (n or split_recipient(v)[1])) for v, n in names.items()}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    """Mỗi người/nhóm trong danh bạ Zalo là một thực thể ``notify`` (người ĐÃ CHỌN ở tuỳ chọn hiện bình thường, còn lại ẨN khỏi bảng điều khiển
    nhưng vẫn hiện trong ô chọn của blueprint, gõ chữ là lọc). Chọn xong blueprint tự lấy threadID; người lạ (không có trong danh bạ) thì dán mã."""
    chosen = [str(v) for v in (entry.options.get(CONF_RECIPIENTS) or [])]
    added: set[str] = set()

    def build(values: list[str], shown: dict[str, str]) -> list["ZaloRecipient"]:
        out = []
        for v in values:
            uid = "%s_to_%s_%s" % ((entry.entry_id,) + split_recipient(v))
            if uid not in added:
                added.add(uid)
                out.append(ZaloRecipient(entry, v, shown.get(v) or split_recipient(v)[1], visible=v in chosen))
        return out

    names = await _contact_names(hass, entry)
    shown = _display_names(names or {})
    everyone = list(dict.fromkeys(chosen + list((names or {}).keys())))
    if names is not None:                                         # chỉ dọn sổ đăng ký khi đã đọc được danh bạ (app tắt không làm mất thực thể)
        keep = {"%s_to_%s_%s" % ((entry.entry_id,) + split_recipient(v)) for v in everyone}
        registry = er.async_get(hass)
        for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
            if ent.domain == "notify" and (ent.unique_id or "").startswith("%s_to_" % entry.entry_id) and ent.unique_id not in keep:
                registry.async_remove(ent.entity_id)             # người đã xoá khỏi danh bạ và không được chọn
    add(build(everyone, shown))

    async def refresh(_now) -> None:
        fresh = await _contact_names(hass, entry)
        if fresh:
            new = build(list(fresh.keys()), _display_names(fresh))
            if new:
                add(new)

    entry.async_on_unload(async_track_time_interval(hass, refresh, REFRESH_EVERY))


class ZaloRecipient(NotifyEntity):
    """Một người hoặc nhóm Zalo để gửi tin / gọi."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:account-box-outline"

    def __init__(self, entry: ConfigEntry, value: str, name: str, visible: bool = True) -> None:
        self._entry = entry
        self._attr_entity_registry_visible_default = visible       # ngoài danh sách đã chọn: ẩn khỏi bảng điều khiển, vẫn chọn được trong blueprint
        self._kind, self._rid = split_recipient(value)
        self._attr_unique_id = "%s_to_%s_%s" % (entry.entry_id, self._kind, self._rid)
        self._attr_name = name                      # hiển thị «Zalo Call <tên>», mã thực thể notify.zalo_call_<tên>
        self._attr_device_info = device_info(entry)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"thread_id": self._rid, "type": self._kind, "loai": "nhóm" if self._kind == "group" else "người"}

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        text = "%s\n%s" % (title, message) if title else message
        await self.hass.services.async_call(DOMAIN, "send_message", {"thread_id": self._rid, "type": self._kind, "message": text}, blocking=True)
