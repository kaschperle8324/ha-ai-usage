"""Sensoren für die Auslastung des Claude-Abos."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import AiUsageConfigEntry, AiUsageCoordinator
from .entity import AiUsageEntity


@dataclass(frozen=True, kw_only=True)
class AiUsageSensorDescription(SensorEntityDescription):
    """Beschreibung eines Sensors."""

    value_fn: Callable[[dict[str, Any]], Any]
    # Wenn gesetzt: Sensor nur anlegen, wenn der Schlüssel in den Daten steht
    requires: str | None = None


def _get(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda d: d.get(key)


def _remaining(key: str) -> Callable[[dict[str, Any]], Any]:
    def fn(d: dict[str, Any]) -> Any:
        value = d.get(key)
        return None if value is None else round(max(0.0, 100.0 - value), 1)

    return fn


def _percent(key: str, *, requires: str | None = None, icon: str = "mdi:gauge") -> AiUsageSensorDescription:
    return AiUsageSensorDescription(
        key=key,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon=icon,
        value_fn=_get(key),
        requires=requires,
    )


def _remaining_desc(key: str) -> AiUsageSensorDescription:
    return AiUsageSensorDescription(
        key=f"{key}_remaining",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:battery-medium",
        value_fn=_remaining(key),
    )


def _reset(key: str) -> AiUsageSensorDescription:
    return AiUsageSensorDescription(
        key=f"{key}_resets_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:timer-refresh-outline",
        value_fn=_get(f"{key}_resets_at"),
    )


SENSORS: tuple[AiUsageSensorDescription, ...] = (
    _percent("five_hour", icon="mdi:clock-time-five-outline"),
    _remaining_desc("five_hour"),
    _reset("five_hour"),
    _percent("seven_day", icon="mdi:calendar-week"),
    _remaining_desc("seven_day"),
    _reset("seven_day"),
    _percent("seven_day_opus", requires="seven_day_opus"),
    _percent("seven_day_sonnet", requires="seven_day_sonnet"),
    _percent("extra_usage", requires="extra_usage", icon="mdi:cash-plus"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AiUsageConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sensoren anlegen."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    async_add_entities(
        AiUsageSensor(coordinator, desc)
        for desc in SENSORS
        if desc.requires is None or desc.requires in data
    )
    async_add_entities([LastUpdateSensor(coordinator)])


class AiUsageSensor(AiUsageEntity, SensorEntity):
    """Ein Messwert des Abos."""

    entity_description: AiUsageSensorDescription

    def __init__(self, coordinator: AiUsageCoordinator, description: AiUsageSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or {})


class LastUpdateSensor(AiUsageEntity, SensorEntity):
    """Zeitpunkt des letzten erfolgreichen Abrufs."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:update"

    def __init__(self, coordinator: AiUsageCoordinator) -> None:
        super().__init__(coordinator, "last_update")
        self._value: datetime | None = None

    def _handle_coordinator_update(self) -> None:
        if self.coordinator.last_update_success:
            self._value = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator.last_update_success:
            self._value = dt_util.utcnow()

    @property
    def native_value(self) -> datetime | None:
        return self._value
