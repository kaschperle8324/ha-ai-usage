"""Gemeinsame Basis der Entitäten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_TITLE, DOMAIN, VERSION
from .coordinator import AiUsageCoordinator


class AiUsageEntity(CoordinatorEntity[AiUsageCoordinator]):
    """Basisklasse mit Geräteinformationen."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AiUsageCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or DEFAULT_TITLE,
            manufacturer="Anthropic",
            model=DEFAULT_TITLE,
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://claude.ai/settings/usage",
        )
