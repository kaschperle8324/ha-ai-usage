"""Sensoren für Auslastung, Kosten und Tokens."""

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

from .api import day_start, month_start
from .const import (
    CONF_PROVIDER,
    PROVIDER_ANTHROPIC_API,
    PROVIDER_CLAUDE_SUB,
    PROVIDER_MISTRAL_API,
    PROVIDER_OPENAI_API,
)
from .coordinator import AiUsageConfigEntry, AiUsageCoordinator
from .entity import AiUsageEntity


@dataclass(frozen=True, kw_only=True)
class AiUsageSensorDescription(SensorEntityDescription):
    """Beschreibung eines Sensors."""

    value_fn: Callable[[dict[str, Any]], Any]
    # Wenn gesetzt: Sensor nur anlegen, wenn der Schlüssel in den Daten steht
    requires: str | None = None
    monthly_total: bool = False
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


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


def _reset(key: str, *, requires: str | None = None) -> AiUsageSensorDescription:
    return AiUsageSensorDescription(
        key=f"{key}_resets_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:timer-refresh-outline",
        value_fn=_get(f"{key}_resets_at"),
        requires=requires,
    )


def _cost(key: str, *, monthly: bool) -> AiUsageSensorDescription:
    return AiUsageSensorDescription(
        key=key,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:cash",
        value_fn=_get(key),
        monthly_total=monthly,
    )


def _tokens(key: str, *, monthly: bool = True) -> AiUsageSensorDescription:
    return AiUsageSensorDescription(
        key=key,
        native_unit_of_measurement="Tokens",
        state_class=SensorStateClass.TOTAL,
        icon="mdi:counter",
        value_fn=_get(key),
        monthly_total=monthly,
    )


CLAUDE_SENSORS: tuple[AiUsageSensorDescription, ...] = (
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

API_SENSORS: tuple[AiUsageSensorDescription, ...] = (
    _cost("cost_month", monthly=True),
    _cost("cost_today", monthly=False),
    _tokens("input_tokens_month"),
    _tokens("output_tokens_month"),
    _tokens("tokens_today", monthly=False),
)

OPENAI_EXTRA: tuple[AiUsageSensorDescription, ...] = (
    AiUsageSensorDescription(
        key="requests_month",
        native_unit_of_measurement="Anfragen",
        state_class=SensorStateClass.TOTAL,
        icon="mdi:swap-horizontal",
        value_fn=_get("requests_month"),
        monthly_total=True,
    ),
)

MISTRAL_SENSORS: tuple[AiUsageSensorDescription, ...] = (
    AiUsageSensorDescription(
        key="cost_month",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:cash",
        value_fn=_get("cost_month"),
        monthly_total=True,
        attr_fn=lambda d: {"kategorien": d.get("categories", {})},
    ),
)

SENSORS_BY_PROVIDER: dict[str, tuple[AiUsageSensorDescription, ...]] = {
    PROVIDER_CLAUDE_SUB: CLAUDE_SENSORS,
    PROVIDER_ANTHROPIC_API: API_SENSORS,
    PROVIDER_OPENAI_API: API_SENSORS + OPENAI_EXTRA,
    PROVIDER_MISTRAL_API: MISTRAL_SENSORS,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AiUsageConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sensoren anlegen."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    descriptions = SENSORS_BY_PROVIDER.get(entry.data[CONF_PROVIDER], ())
    async_add_entities(
        AiUsageSensor(coordinator, desc)
        for desc in descriptions
        if desc.requires is None or desc.requires in data
    )
    async_add_entities([LastUpdateSensor(coordinator)])


class AiUsageSensor(AiUsageEntity, SensorEntity):
    """Ein Messwert eines Anbieters."""

    entity_description: AiUsageSensorDescription

    def __init__(self, coordinator: AiUsageCoordinator, description: AiUsageSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.device_class == SensorDeviceClass.MONETARY:
            self._attr_native_unit_of_measurement = (coordinator.data or {}).get("currency", "USD")

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def last_reset(self) -> datetime | None:
        if self.entity_description.state_class != SensorStateClass.TOTAL:
            return None
        if self.entity_description.monthly_total:
            return month_start()
        return day_start()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator.data or {})


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
