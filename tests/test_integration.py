"""Einrichtung, Sensoren und Token-Erneuerung mit Home Assistant."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ai_usage import api
from custom_components.ai_usage.const import DOMAIN

CLAUDE_RAW = {
    "five_hour": {"utilization": 42.0, "resets_at": "2026-11-12T12:00:00Z"},
    "seven_day": {"utilization": 100.0, "resets_at": "2026-11-17T07:00:00Z"},
    "seven_day_sonnet": {"utilization": 12.0, "resets_at": None},
}

async def test_claude_flow_sensors_and_refresh(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"
    assert result["description_placeholders"]["url"].startswith("https://claude.ai/oauth/authorize?")

    tokens = api.OAuthTokens("at1", "rt1", time.time() + 3600)
    with (
        patch.object(api, "claude_exchange_code", AsyncMock(return_value=tokens)),
        patch.object(api, "claude_fetch_usage", AsyncMock(return_value=CLAUDE_RAW)),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"auth_code": "c#s", "name": "Claude"})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert hass.states.get("sensor.claude_5_hour_usage").state == "42.0"
    assert hass.states.get("sensor.claude_5_hour_remaining").state == "58.0"
    assert hass.states.get("sensor.claude_weekly_usage_sonnet").state == "12.0"
    assert hass.states.get("sensor.claude_weekly_usage_opus") is None
    assert hass.states.get("binary_sensor.claude_weekly_limit_reached").state == "on"
    assert hass.states.get("binary_sensor.claude_5_hour_limit_reached").state == "off"
    reset = hass.states.get("sensor.claude_5_hour_reset").state
    assert datetime.fromisoformat(reset) == datetime(2026, 11, 12, 12, tzinfo=UTC)

    # Abgelaufenes Token -> Erneuerung, rotierte Tokens werden gespeichert, kein Neuladen
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    hass.config_entries.async_update_entry(entry, data={**entry.data, "expires_at": 0})
    coordinator = entry.runtime_data
    new_tokens = api.OAuthTokens("at2", "rt2", time.time() + 3600)
    fetch = AsyncMock(return_value={**CLAUDE_RAW, "five_hour": {"utilization": 50.0}})
    with (
        patch.object(api, "claude_refresh", AsyncMock(return_value=new_tokens)) as refresh,
        patch.object(api, "claude_fetch_usage", fetch),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    refresh.assert_awaited_once()
    assert fetch.await_args.args[1] == "at2"
    assert entry.data["refresh_token"] == "rt2"
    assert entry.runtime_data is coordinator  # nicht neu geladen
    assert hass.states.get("sensor.claude_5_hour_usage").state == "50.0"


async def test_claude_auth_failure_starts_reauth(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Claude",
        data={"provider": "claude_subscription", "access_token": "a", "refresh_token": "r", "expires_at": 0},
    )
    entry.add_to_hass(hass)
    with patch.object(api, "claude_refresh", AsyncMock(side_effect=api.AuthError("invalid_grant"))):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_rate_limit_keeps_values(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Claude",
        data={"provider": "claude_subscription", "access_token": "a", "refresh_token": "r", "expires_at": time.time() + 3600},
    )
    entry.add_to_hass(hass)
    with patch.object(api, "claude_fetch_usage", AsyncMock(return_value=CLAUDE_RAW)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    with (
        patch.object(api, "claude_fetch_usage", AsyncMock(side_effect=api.RateLimitError("429"))),
        patch.object(api, "claude_refresh", AsyncMock(return_value=api.OAuthTokens("b", "r2", time.time() + 3600))),
    ):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get("sensor.claude_5_hour_usage").state == "42.0"


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Claude",
        data={"provider": "claude_subscription", "access_token": "a", "refresh_token": "r", "expires_at": time.time() + 3600},
    )
    entry.add_to_hass(hass)
    with patch.object(api, "claude_fetch_usage", AsyncMock(return_value=CLAUDE_RAW)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.update_interval.total_seconds() == 600
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 15})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"scan_interval": 15}
    assert entry.runtime_data.update_interval.total_seconds() == 900


async def test_removed_provider_does_not_load(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="OpenAI", data={"provider": "openai_api", "admin_key": "k"})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
