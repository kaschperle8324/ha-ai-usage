"""Binärsensoren: Limit erreicht."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AiUsageConfigEntry, AiUsageCoordinator
from .entity import AiUsageEntity


@dataclass(frozen=True, kw_only=True)
class AiUsageBinaryDescription(BinarySensorEntityDescription):
    """Beschreibung eines Binärsensors."""

    value_fn: Callable[[dict[str, Any]], bool | None]
    requires: str


def _at_limit(key: str) -> Callable[[dict[str, Any]], bool | None]:
    def fn(d: dict[str, Any]) -> bool | None:
        value = d.get(key)
        return None if value is None else value >= 100

    return fn


BINARY_SENSORS: tuple[AiUsageBinaryDescription, ...] = (
    AiUsageBinaryDescription(
        key="five_hour_limit",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_at_limit("five_hour"),
        requires="five_hour",
    ),
    AiUsageBinaryDescription(
        key="seven_day_limit",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_at_limit("seven_day"),
        requires="seven_day",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AiUsageConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Binärsensoren anlegen."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    async_add_entities(
        AiUsageBinarySensor(coordinator, desc) for desc in BINARY_SENSORS if desc.requires in data
    )


class AiUsageBinarySensor(AiUsageEntity, BinarySensorEntity):
    """Limit erreicht ja/nein."""

    entity_description: AiUsageBinaryDescription

    def __init__(self, coordinator: AiUsageCoordinator, description: AiUsageBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data or {})
