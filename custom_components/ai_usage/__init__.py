"""AI Usage – Verbrauch von Claude, OpenAI und Mistral in Home Assistant."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import AiUsageConfigEntry, AiUsageCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: AiUsageConfigEntry) -> bool:
    """Eintrag einrichten."""
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
