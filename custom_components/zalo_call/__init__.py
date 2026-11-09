"""Zalo Call — gọi điện, tin nhắn và 96 service Zalo cho Home Assistant.

Tích hợp này không tự nói chuyện với Zalo: nó gọi sang app Zalo PC chạy
trong Docker (`zalo-pc-app`, cùng repo), giống cách `zalo_bot` gọi gateway.
App đẩy sự kiện (tin nhắn, cuộc gọi) về HA qua webhook; HA bắn lại lên bus
dưới tên `zalo_call_message`, `zalo_call_call`, `zalo_call_group_event`,
`zalo_call_reaction`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
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
from .const import (
    CONF_HA_URL,
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EVENT_PREFIX,
    SCAN_INTERVAL_SECONDS,
)
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor"]
WEBHOOK_KINDS = ("message", "group_event", "reaction", "call")


@dataclass
class ZaloCallData:
    api: ZaloCallApi
    coordinator: "ZaloCallCoordinator"


class ZaloCallCoordinator(DataUpdateCoordinator[dict]):
    """Trạng thái đăng nhập Zalo + danh sách cuộc gọi, 10 giây một lần."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 api: ZaloCallApi) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS))
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            status = await self.api.status()
            calls = await self.api.calls()
        except ZaloCallError as err:
            raise UpdateFailed(str(err)) from err
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
    hass.data[DOMAIN][entry.entry_id] = ZaloCallData(api, coordinator)

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
        if kind == "call":
            await coordinator.async_request_refresh()
        elif kind == "message":
            hass_.async_create_task(async_ai_reply(hass_, entry, payload))
        return web.Response(status=200)

    webhook.async_register(hass, DOMAIN, "Zalo Call", webhook_id, _handle,
                           allowed_methods=["POST"])
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))
    hass.async_create_task(_async_push_webhooks(hass, entry, api, webhook_id))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_push_webhooks(hass: HomeAssistant, entry: ConfigEntry,
                               api: ZaloCallApi, webhook_id: str) -> None:
    """Báo cho app địa chỉ webhook của HA (một URL chung cho cả 4 loại).

    Không ghi đè webhook mà người dùng đã đặt sang chỗ khác: chỉ điền khi
    ô còn trống hoặc đã là của chính tích hợp này.
    """
    base = entry.options.get(CONF_HA_URL)
    try:
        base = base or get_url(hass, allow_external=False, allow_cloud=False)
    except NoURLAvailableError:
        _LOGGER.warning("Không xác định được địa chỉ nội bộ của HA; đặt "
                        "'Địa chỉ HA' trong tuỳ chọn tích hợp để nhận sự kiện")
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
