"""Gemeinsame Basis der Entitäten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PROVIDER, DOMAIN, PROVIDER_TITLES, VERSION
from .coordinator import AiUsageCoordinator

MANUFACTURERS = {
    "claude_subscription": "Anthropic",
    "anthropic_api": "Anthropic",
    "openai_api": "OpenAI",
    "mistral_api": "Mistral AI",
}

CONFIG_URLS = {
    "claude_subscription": "https://claude.ai/settings/usage",
    "anthropic_api": "https://console.anthropic.com/settings/usage",
    "openai_api": "https://platform.openai.com/usage",
    "mistral_api": "https://console.mistral.ai/usage",
}


class AiUsageEntity(CoordinatorEntity[AiUsageCoordinator]):
    """Basisklasse mit Geräteinformationen."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AiUsageCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        provider = entry.data[CONF_PROVIDER]
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or PROVIDER_TITLES.get(provider, provider),
            manufacturer=MANUFACTURERS.get(provider),
            model=PROVIDER_TITLES.get(provider),
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=CONFIG_URLS.get(provider),
        )
