"""Zalo Call — gọi điện, tin nhắn và 96 service Zalo cho Home Assistant.

Tích hợp này không tự nói chuyện với Zalo: nó gọi sang app Zalo PC chạy
trong Docker (`zalo/zalo-pc-app`, cùng repo), giống cách `zalo_bot` gọi gateway.
App đẩy sự kiện (tin nhắn, cuộc gọi) về HA qua webhook; HA bắn lại lên bus
dưới tên `zalo_call_message`, `zalo_call_call`, `zalo_call_group_event`,
`zalo_call_reaction`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

import aiohttp
from aiohttp import web

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .ai import async_ai_reply
from .api import ZaloCallApi, ZaloCallAuthError, ZaloCallError
from .bridge import CallAudioBridge
from .bridge_core import derive_state
from .call_voice import CallVoice, on_call_state
from .devices import DeviceDefaults
from .const import (
    CONF_AI_CALL,
    CONF_AI_CALL_GREETING,
    CONF_AI_CALL_HANDOVER,
    CONF_HA_URL,
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EVENT_PREFIX,
    EVENT_STATE,
    SCAN_INTERVAL_SECONDS,
)
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor", "select", "text", "switch", "button",
             "number"]
WEBHOOK_KINDS = ("message", "group_event", "reaction", "call")
# Trang thai ket thuc: dung cau noi am thanh (loa/mic) cua cuoc goi do.
TERMINAL_STATES = ("ended", "no_answer", "declined", "missed", "rejected",
                   "error")


@dataclass
class ZaloCallData:
    api: ZaloCallApi
    coordinator: "ZaloCallCoordinator"
    bridge: CallAudioBridge
    defaults: DeviceDefaults
    voice: CallVoice = field(default_factory=CallVoice)     # kế hoạch giọng nói/AI theo từng cuộc gọi


class ZaloCallCoordinator(DataUpdateCoordinator[dict]):
    """Trạng thái đăng nhập Zalo + danh sách cuộc gọi, 10 giây một lần."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 api: ZaloCallApi) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS))
        self.api = api
        self.bridge: CallAudioBridge | None = None   # gan sau khi tao (de day lai mac dinh)

    async def _async_update_data(self) -> dict:
        try:
            status = await self.api.status()
            calls = await self.api.calls()
        except ZaloCallAuthError as err:
            # Doi mat khau trong WebUI app: dung hoi, de HA mo luong nhap lai mat khau.
            raise ConfigEntryAuthFailed(str(err)) from err
        except ZaloCallError as err:
            if self.bridge is not None:
                self.bridge.policy.poll(False)
            raise UpdateFailed(str(err)) from err
        if self.bridge is not None and self.bridge.policy.poll(True):
            self.hass.async_create_task(self.bridge.async_push_defaults())
        return {"status": status, "calls": calls}


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_create_clientsession(
        hass, cookie_jar=aiohttp.CookieJar(unsafe=True))
    api = ZaloCallApi(session, entry.data[CONF_URL], entry.data[CONF_USERNAME],
                      entry.data[CONF_PASSWORD])
    try:
        await api.login()
    except ZaloCallAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ZaloCallError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = ZaloCallCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    defaults = DeviceDefaults(hass, entry.entry_id)
    await defaults.async_load(entry.options)
    bridge = CallAudioBridge(hass, entry, api, defaults)
    coordinator.bridge = bridge
    hass.data[DOMAIN][entry.entry_id] = ZaloCallData(api, coordinator, bridge,
                                                     defaults)

    webhook_id = entry.data[CONF_WEBHOOK_ID]

    async def _handle(hass_: HomeAssistant, wid: str, request: web.Request):
        try:
            payload = await request.json()
        except ValueError:
            return web.Response(status=400)
        if not isinstance(payload, dict):
            return web.Response(status=400)
        kind = str(payload.get("event") or "")
        if kind in WEBHOOK_KINDS:
            hass_.bus.async_fire(EVENT_PREFIX + kind, payload)
        if kind == "voice2text":
            # Ket qua Zalo AI chuyen giong noi: zalo_call_voice_to_text {req_id, text, error}
            hass_.bus.async_fire(EVENT_PREFIX + "voice_to_text", payload)
            return web.Response(status=200)
        if kind == "call":
            await coordinator.async_request_refresh()
            await _async_call_state(hass_, bridge, payload)
            state = derive_state(payload)
            if state is not None:
                on_call_state(hass_, hass_.data[DOMAIN][entry.entry_id], state, payload.get("call_id"), TERMINAL_STATES,
                              bool(defaults.get(CONF_AI_CALL)), str(defaults.get(CONF_AI_CALL_GREETING) or ""),
                              str(payload.get("answer_source") or ""), str(defaults.get(CONF_AI_CALL_HANDOVER) or ""))
        elif kind == "message":
            hass_.async_create_task(async_ai_reply(hass_, entry, payload))
        return web.Response(status=200)

    webhook.async_register(hass, DOMAIN, "Zalo Call", webhook_id, _handle,
                           allowed_methods=["POST"])
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))
    hass.async_create_task(_async_push_webhooks(hass, defaults, api, webhook_id))
    # Đổi ô «Địa chỉ HA» trên thiết bị: báo lại cho app địa chỉ webhook mới (không cần tải lại).
    last_url = {"v": defaults.get(CONF_HA_URL)}

    def _on_defaults_changed() -> None:
        if defaults.get(CONF_HA_URL) != last_url["v"]:
            last_url["v"] = defaults.get(CONF_HA_URL)
            hass.async_create_task(_async_push_webhooks(hass, defaults, api, webhook_id))

    entry.async_on_unload(defaults.add_listener(_on_defaults_changed))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Dua thiet bi mac dinh (da phan giai ra URL luong) cho app: WebUI hien thong nhat
    # va cuoc goi nghe may ngoai HA / ben kia xin len video cung dung dung nguon.
    hass.async_create_task(bridge.async_push_defaults())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data is not None:
            data.voice.cancel_all()
            await data.bridge.async_shutdown()
    return ok


async def _async_call_state(hass: HomeAssistant, bridge: CallAudioBridge,
                            payload: dict) -> None:
    """Su kien `zalo_call_call_state` cho automation + dieu khien cau noi am
    thanh. state: incoming / ringing / answered / declined / no_answer /
    missed / rejected / ended / error ("tu choi" va "khong nghe may" la
    declined va no_answer — dung de lam tac vu khac sau do)."""
    state = derive_state(payload)
    if state is None:
        return
    call_id = payload.get("call_id")
    devices: dict[str, str] = {}
    if state == "answered":
        devices = await bridge.start(call_id)
    elif state in TERMINAL_STATES:
        await bridge.stop(call_id)
    event = {"state": state, "call_id": call_id,
             "thread_id": payload.get("thread_id"), "peer": payload.get("peer"),
             "call_type": payload.get("call_type"),
             "end_reason": payload.get("end_reason", "")}
    if devices:    # khong dua mic_url (co the chua mat khau) ra bus
        event["speaker"] = devices.get("speaker", "")
        event["camera"] = devices.get("camera", "")
        event["mic"] = devices.get("mic", "") or (
            "url" if devices.get("mic_url") else "")
    hass.bus.async_fire(EVENT_STATE, event)


async def _async_push_webhooks(hass: HomeAssistant, defaults: DeviceDefaults,
                               api: ZaloCallApi, webhook_id: str) -> None:
    """Báo cho app địa chỉ webhook của HA (một URL chung cho cả 4 loại).

    Không ghi đè webhook mà người dùng đã đặt sang chỗ khác: chỉ điền khi
    ô còn trống hoặc đã là của chính tích hợp này.
    """
    base = defaults.get(CONF_HA_URL)
    try:
        base = base or get_url(hass, allow_external=False, allow_cloud=False)
    except NoURLAvailableError:
        _LOGGER.warning("Không xác định được địa chỉ nội bộ của HA; đặt "
                        "ô «Địa chỉ HA» trên thiết bị Zalo Call để nhận sự kiện")
        return
    url = base.rstrip("/") + webhook.async_generate_path(webhook_id)
    try:
        current = await api.get_webhooks()
        cfg = dict(current)
        changed = False
        for kind in WEBHOOK_KINDS:
            key = kind + "_webhook_url"
            old = current.get(key) or ""
            if old and old != url:
                _LOGGER.warning("Webhook %s của app đang trỏ nơi khác, giữ "
                                "nguyên (không ghi đè)", kind)
                continue
            if old != url:
                cfg[key] = url
                changed = True
        if changed:
            await api.set_webhooks(cfg)
    except ZaloCallError as err:
        _LOGGER.warning("Không đặt được webhook cho app: %s", err)
