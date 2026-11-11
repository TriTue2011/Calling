"""Luồng cấu hình: địa chỉ app, tài khoản app, rồi tuỳ chọn AI / thiết bị."""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import ZaloCallApi, ZaloCallAuthError, ZaloCallError
from .const import (
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
)


def _normalize_url(raw: str) -> str:
    raw = raw.strip().rstrip("/")
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    return raw


async def _async_check(hass, url: str, username: str, password: str) -> str | None:
    """Thử đăng nhập app. None = được; ngược lại là khoá lỗi của form."""
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar(unsafe=True))
    api = ZaloCallApi(session, url, username, password)
    try:
        await api.login()
        await api.status()
    except ZaloCallAuthError:
        return "invalid_auth"
    except ZaloCallError:
        return "cannot_connect"
    return None


class ZaloCallConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ZaloCallOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize_url(user_input[CONF_URL])
            err = await _async_check(self.hass, url, user_input[CONF_USERNAME],
                                     user_input[CONF_PASSWORD])
            if err:
                errors["base"] = err
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Zalo Call (%s)" % url.split("//", 1)[-1],
                    data={CONF_URL: url,
                          CONF_USERNAME: user_input[CONF_USERNAME],
                          CONF_PASSWORD: user_input[CONF_PASSWORD],
                          CONF_WEBHOOK_ID: webhook.async_generate_id()})
        schema = vol.Schema({
            vol.Required(CONF_URL, default="http://172.16.10.110:8080"): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        })
        return self.async_show_form(step_id="user", data_schema=schema,
                                    errors=errors)

    # -- Sai mật khẩu app (ví dụ vừa đổi trong WebUI): hỏi lại mật khẩu, không phải xoá/thêm lại --
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None
                                        ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            err = await _async_check(self.hass, entry.data[CONF_URL],
                                     entry.data[CONF_USERNAME], user_input[CONF_PASSWORD])
            if err:
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]})
        schema = vol.Schema({vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors,
            description_placeholders={"url": entry.data[CONF_URL],
                                      "username": entry.data[CONF_USERNAME]})

    # -- Đổi địa chỉ / tài khoản app (đổi IP, cổng, đổi tên đăng nhập) mà không mất cấu hình --
    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None
                                     ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize_url(user_input[CONF_URL])
            err = await _async_check(self.hass, url, user_input[CONF_USERNAME],
                                     user_input[CONF_PASSWORD])
            if err:
                errors["base"] = err
            else:
                if url != entry.data[CONF_URL]:      # đổi sang địa chỉ app đã có mục khác -> từ chối
                    await self.async_set_unique_id(url)
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry, unique_id=url, title="Zalo Call (%s)" % url.split("//", 1)[-1],
                    data_updates={CONF_URL: url, CONF_USERNAME: user_input[CONF_USERNAME],
                                  CONF_PASSWORD: user_input[CONF_PASSWORD]})
        schema = vol.Schema({
            vol.Required(CONF_URL, default=entry.data[CONF_URL]): str,
            vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): str,
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        })
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)


class ZaloCallOptionsFlow(OptionsFlow):
    """Chọn người/nhóm từ danh bạ làm người nhận: mỗi người được chọn thành một thực thể ``notify`` (xem notify.py)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        rt = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if rt is None:
            return self.async_abort(reason="not_loaded")
        try:
            data = await rt.api.contacts() or {}
        except ZaloCallError:
            return self.async_abort(reason="cannot_connect")
        options = []
        for part, kind, tag in (("friends", "user", "bạn bè"), ("groups", "group", "nhóm")):
            for row in (data.get(part) or {}).get("rows", []):
                options.append(selector.SelectOptionDict(value="%s:%s" % (kind, row.get("id")),
                                                         label="%s (%s)" % (str(row.get("name") or row.get("id")), tag)))
        valid = {o["value"] for o in options}
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, "recipients": [v for v in user_input.get("recipients", []) if v in valid]})
        current = [v for v in (self.config_entry.options.get("recipients") or []) if v in valid]
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Optional("recipients", default=current): selector.SelectSelector(selector.SelectSelectorConfig(
                options=options, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN, sort=True))}))
