"""Einrichtung über die Oberfläche."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import api
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_PROVIDER,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_MINUTES,
    DEFAULT_TITLE,
    DOMAIN,
    MAX_SCAN_MINUTES,
    MIN_SCAN_MINUTES,
    PROVIDER_CLAUDE_SUB,
)

_LOGGER = logging.getLogger(__name__)

CONF_AUTH_CODE = "auth_code"
CONF_NAME = "name"


class AiUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtungsdialog."""

    VERSION = 1

    def __init__(self) -> None:
        self._pkce: api.PkceSession | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> AiUsageOptionsFlow:
        return AiUsageOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Anmeldung beim Claude-Abo über einen Code zum Einfügen."""
        errors: dict[str, str] = {}
        if self._pkce is None:
            self._pkce = api.create_pkce_session()

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                tokens = await api.claude_exchange_code(
                    session, self._pkce, user_input[CONF_AUTH_CODE]
                )
                try:
                    await api.claude_fetch_usage(session, tokens.access_token)
                except api.RateLimitError:
                    # Anmeldung hat geklappt, Werte kommen beim nächsten Abruf
                    pass
            except api.AuthError as err:
                _LOGGER.warning("Claude-Anmeldung abgelehnt: %s", err)
                errors["base"] = "invalid_code"
                self._pkce = api.create_pkce_session()
            except api.RateLimitError:
                errors["base"] = "rate_limited"
            except api.ApiError as err:
                _LOGGER.warning("Claude-Anmeldung fehlgeschlagen: %s", err)
                errors["base"] = "cannot_connect"
            else:
                data = {
                    CONF_PROVIDER: PROVIDER_CLAUDE_SUB,
                    CONF_ACCESS_TOKEN: tokens.access_token,
                    CONF_REFRESH_TOKEN: tokens.refresh_token,
                    CONF_EXPIRES_AT: tokens.expires_at,
                }
                if self.source == SOURCE_REAUTH:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=data
                    )
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or DEFAULT_TITLE, data=data
                )

        schema: dict[Any, Any] = {
            vol.Required(CONF_AUTH_CODE): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            )
        }
        if self.source != SOURCE_REAUTH:
            schema[vol.Optional(CONF_NAME, default=DEFAULT_TITLE)] = str
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            description_placeholders={"url": self._pkce.url},
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Zugang ist abgelaufen oder wurde widerrufen."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()


class AiUsageOptionsFlow(OptionsFlow):
    """Abfrageintervall einstellen."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_MINUTES)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_MINUTES,
                            max=MAX_SCAN_MINUTES,
                            step=1,
                            unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
