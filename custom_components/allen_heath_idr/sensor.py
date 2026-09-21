"""Sensors for the Allen & Heath iDR integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import IdrConfigEntry, IdrCoordinator, IdrData
from .entity import IdrEntity


@dataclass(frozen=True, kw_only=True)
class IdrSensorEntityDescription(SensorEntityDescription):
    """Describe an iDR sensor."""

    value_fn: Callable[[IdrData], StateType]


SENSORS: tuple[IdrSensorEntityDescription, ...] = (
    IdrSensorEntityDescription(
        key="preset",
        translation_key="preset",
        icon="mdi:playlist-play",
        value_fn=lambda data: data.preset,
    ),
    IdrSensorEntityDescription(
        key="unit_name",
        translation_key="unit_name",
        icon="mdi:tag-text-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.unit_name,
    ),
    IdrSensorEntityDescription(
        key="response_time",
        translation_key="response_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.response_time_ms,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IdrConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iDR sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        IdrSensor(coordinator, description) for description in SENSORS
    )


class IdrSensor(IdrEntity, SensorEntity):
    """A sensor that shows a value read from the iDR."""

    entity_description: IdrSensorEntityDescription

    def __init__(
        self, coordinator: IdrCoordinator, description: IdrSensorEntityDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator.data)
