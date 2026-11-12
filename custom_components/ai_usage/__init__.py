"""AI Usage – Auslastung des Claude-Abos in Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .const import CONF_PROVIDER, PROVIDER_CLAUDE_SUB
from .coordinator import AiUsageConfigEntry, AiUsageCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: AiUsageConfigEntry) -> bool:
    """Eintrag einrichten."""
    if entry.data.get(CONF_PROVIDER, PROVIDER_CLAUDE_SUB) != PROVIDER_CLAUDE_SUB:
        # Ab 1.1.0 wird nur noch das Claude-Abo unterstützt
        raise ConfigEntryError(
            "Dieser Anbieter wird nicht mehr unterstützt. Bitte den Eintrag löschen."
        )
    coordinator = AiUsageCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_changed))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_changed(hass: HomeAssistant, entry: AiUsageConfigEntry) -> None:
    """Nur bei geänderten Optionen neu laden, nicht bei Token-Rotation."""
    coordinator: AiUsageCoordinator = entry.runtime_data
    if dict(entry.options) != coordinator.options_snapshot:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AiUsageConfigEntry) -> bool:
    """Eintrag entladen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
