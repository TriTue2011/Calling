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
    CONF_AI_AGENT,
    CONF_AI_ENABLED,
    CONF_AI_THREADS,
    CONF_CAMERA,
    CONF_HA_URL,
    CONF_MIC,
    CONF_MIC_URL,
    CONF_PASSWORD,
    CONF_SPEAKER,
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


class ZaloCallConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize_url(user_input[CONF_URL])
            session = async_create_clientsession(
                self.hass, cookie_jar=aiohttp.CookieJar(unsafe=True))
            api = ZaloCallApi(session, url, user_input[CONF_USERNAME],
                              user_input[CONF_PASSWORD])
            try:
                await api.login()
                await api.status()
            except ZaloCallAuthError:
                errors["base"] = "invalid_auth"
            except ZaloCallError:
                errors["base"] = "cannot_connect"
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

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return ZaloCallOptionsFlow()


class ZaloCallOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = self.config_entry.options

        def opt(key, selector_):
            cur = o.get(key)
            return vol.Optional(key, description={"suggested_value": cur}), selector_

        fields = dict([
            opt(CONF_HA_URL, selector.TextSelector()),
            (vol.Optional(CONF_AI_ENABLED, default=o.get(CONF_AI_ENABLED, False)),
             selector.BooleanSelector()),
            opt(CONF_AI_AGENT, selector.EntitySelector(
                selector.EntitySelectorConfig(domain="conversation"))),
            opt(CONF_AI_THREADS, selector.TextSelector()),
            opt(CONF_SPEAKER, selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player"))),
            opt(CONF_MIC, selector.EntitySelector(
                selector.EntitySelectorConfig(domain="camera"))),
            opt(CONF_MIC_URL, selector.TextSelector()),
            opt(CONF_CAMERA, selector.EntitySelector(
                selector.EntitySelectorConfig(domain="camera"))),
        ])
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
