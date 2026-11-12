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
    CONF_ADMIN_KEY,
    CONF_EXPIRES_AT,
    CONF_PROVIDER,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_MINUTES,
    DOMAIN,
    MAX_SCAN_MINUTES,
    MIN_SCAN_MINUTES,
    PROVIDER_ANTHROPIC_API,
    PROVIDER_CLAUDE_SUB,
    PROVIDER_MISTRAL_API,
    PROVIDER_OPENAI_API,
    PROVIDER_TITLES,
)

_LOGGER = logging.getLogger(__name__)

CONF_AUTH_CODE = "auth_code"
CONF_NAME = "name"

KEY_HINTS = {
    PROVIDER_ANTHROPIC_API: "https://console.anthropic.com/settings/admin-keys",
    PROVIDER_OPENAI_API: "https://platform.openai.com/settings/organization/admin-keys",
    PROVIDER_MISTRAL_API: "https://admin.mistral.ai",
}


class AiUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtungsdialog."""

    VERSION = 1

    def __init__(self) -> None:
        self._pkce: api.PkceSession | None = None
        self._provider: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> AiUsageOptionsFlow:
        return AiUsageOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Anbieter auswählen."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[
                PROVIDER_CLAUDE_SUB,
                PROVIDER_ANTHROPIC_API,
                PROVIDER_OPENAI_API,
                PROVIDER_MISTRAL_API,
            ],
        )

    # ------------------------------------------------------------------ Claude Abo

    async def async_step_claude_subscription(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
                    title=user_input.get(CONF_NAME) or PROVIDER_TITLES[PROVIDER_CLAUDE_SUB],
                    data=data,
                )

        schema: dict[Any, Any] = {
            vol.Required(CONF_AUTH_CODE): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            )
        }
        if self.source != SOURCE_REAUTH:
            schema[vol.Optional(CONF_NAME, default=PROVIDER_TITLES[PROVIDER_CLAUDE_SUB])] = str
        return self.async_show_form(
            step_id="claude_subscription",
            data_schema=vol.Schema(schema),
            description_placeholders={"url": self._pkce.url},
            errors=errors,
        )

    # ------------------------------------------------------------------ API-Konten

    async def _admin_key_step(
        self, provider: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_ADMIN_KEY].strip()
            try:
                await api.validate_admin_key(async_get_clientsession(self.hass), provider, key)
            except api.AuthError:
                errors["base"] = "invalid_auth"
            except api.RateLimitError:
                errors["base"] = "rate_limited"
            except api.ApiError as err:
                _LOGGER.warning("Prüfung des Schlüssels fehlgeschlagen: %s", err)
                errors["base"] = "cannot_connect"
            else:
                data = {CONF_PROVIDER: provider, CONF_ADMIN_KEY: key}
                if self.source == SOURCE_REAUTH:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=data
                    )
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or PROVIDER_TITLES[provider], data=data
                )

        schema: dict[Any, Any] = {
            vol.Required(CONF_ADMIN_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            )
        }
        if self.source != SOURCE_REAUTH:
            schema[vol.Optional(CONF_NAME, default=PROVIDER_TITLES[provider])] = str
        return self.async_show_form(
            step_id=provider,
            data_schema=vol.Schema(schema),
            description_placeholders={"url": KEY_HINTS[provider]},
            errors=errors,
        )

    async def async_step_anthropic_api(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._admin_key_step(PROVIDER_ANTHROPIC_API, user_input)

    async def async_step_openai_api(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._admin_key_step(PROVIDER_OPENAI_API, user_input)

    async def async_step_mistral_api(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._admin_key_step(PROVIDER_MISTRAL_API, user_input)

    # ------------------------------------------------------------------ Erneute Anmeldung

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Zugang ist abgelaufen oder wurde widerrufen."""
        self._provider = entry_data[CONF_PROVIDER]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        if self._provider == PROVIDER_CLAUDE_SUB:
            return await self.async_step_claude_subscription()
        return await self._admin_key_step(self._provider, None)


class AiUsageOptionsFlow(OptionsFlow):
    """Abfrageintervall einstellen."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        provider = self.config_entry.data[CONF_PROVIDER]
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_MINUTES.get(provider, 30)
        )
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
