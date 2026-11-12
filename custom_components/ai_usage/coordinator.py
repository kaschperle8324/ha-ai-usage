"""Datenabruf je Konfigurationseintrag."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
    PROVIDER_ANTHROPIC_API,
    PROVIDER_CLAUDE_SUB,
    PROVIDER_MISTRAL_API,
    PROVIDER_OPENAI_API,
    TOKEN_REFRESH_MARGIN,
)

_LOGGER = logging.getLogger(__name__)

type AiUsageConfigEntry = ConfigEntry[AiUsageCoordinator]


class AiUsageCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fragt einen Anbieter regelmäßig ab."""

    config_entry: AiUsageConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AiUsageConfigEntry) -> None:
        self.provider: str = entry.data[CONF_PROVIDER]
        self.options_snapshot = dict(entry.options)
        minutes = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_MINUTES.get(self.provider, 30)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.provider}",
            update_interval=timedelta(minutes=minutes),
        )
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            if self.provider == PROVIDER_CLAUDE_SUB:
                return await self._update_claude()
            key = self.config_entry.data[CONF_ADMIN_KEY]
            if self.provider == PROVIDER_ANTHROPIC_API:
                return await api.anthropic_fetch(self._session, key)
            if self.provider == PROVIDER_OPENAI_API:
                return await api.openai_fetch(self._session, key)
            if self.provider == PROVIDER_MISTRAL_API:
                data = await api.mistral_fetch(self._session, key)
                _LOGGER.debug("Mistral-Rohdaten: %s", data.get("raw"))
                return data
        except api.AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except api.RateLimitError as err:
            # Beim nächsten Intervall erneut versuchen, alte Werte behalten
            if self.data is not None:
                _LOGGER.debug("Rate-Limit, behalte letzte Werte: %s", err)
                return self.data
            raise UpdateFailed(str(err)) from err
        except api.ApiError as err:
            raise UpdateFailed(str(err)) from err
        raise UpdateFailed(f"Unbekannter Anbieter {self.provider}")

    async def _ensure_claude_token(self, force: bool = False) -> str:
        data = self.config_entry.data
        expires_at = float(data.get(CONF_EXPIRES_AT, 0))
        if not force and time.time() < expires_at - TOKEN_REFRESH_MARGIN.total_seconds():
            return data[CONF_ACCESS_TOKEN]
        tokens = await api.claude_refresh(self._session, data[CONF_REFRESH_TOKEN])
        # Rotierte Tokens sofort speichern, sonst ist die Anmeldung nach einem
        # Neustart verloren.
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                **data,
                CONF_ACCESS_TOKEN: tokens.access_token,
                CONF_REFRESH_TOKEN: tokens.refresh_token,
                CONF_EXPIRES_AT: tokens.expires_at,
            },
        )
        return tokens.access_token

    async def _update_claude(self) -> dict[str, Any]:
        token = await self._ensure_claude_token()
        try:
            raw = await api.claude_fetch_usage(self._session, token)
        except api.AuthError:
            # Token wurde evtl. vorzeitig ungültig – einmal erneuern
            token = await self._ensure_claude_token(force=True)
            raw = await api.claude_fetch_usage(self._session, token)
        except api.RateLimitError:
            # Rate-Limits gelten je Zugriffstoken; ein frisches Token hilft meist
            token = await self._ensure_claude_token(force=True)
            raw = await api.claude_fetch_usage(self._session, token)
        return api.parse_claude_usage(raw)
