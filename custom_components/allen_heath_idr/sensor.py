"""Sensor platform for the Allen & Heath iDR integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IdrCoordinator, IdrData
from .entity import IdrEntity


@dataclass(frozen=True, kw_only=True)
class IdrSensorEntityDescription(SensorEntityDescription):
    """Describes an Allen & Heath iDR diagnostic sensor."""

    value_fn: Callable[[IdrData], str | int | float | None]


SENSOR_DESCRIPTIONS: tuple[IdrSensorEntityDescription, ...] = (
    IdrSensorEntityDescription(
        key="unit_name",
        translation_key="unit_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.unit_name,
    ),
    IdrSensorEntityDescription(
        key="response_time",
        translation_key="response_time",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: round(data.response_time_ms),
    ),
    IdrSensorEntityDescription(
        key="integration_version",
        translation_key="integration_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.integration_version,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up iDR diagnostic sensors."""
    coordinator: IdrCoordinator = entry.runtime_data
    async_add_entities(IdrSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS)


class IdrSensor(IdrEntity, SensorEntity):
    """A diagnostic sensor on an iDR unit."""

    entity_description: IdrSensorEntityDescription

    def __init__(
        self, coordinator: IdrCoordinator, description: IdrSensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | None:
        """Return the sensor's current value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
