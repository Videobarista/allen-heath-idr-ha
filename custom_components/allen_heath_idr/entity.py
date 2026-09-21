"""Base entity for the Allen & Heath iDR integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import IdrCoordinator


class IdrEntity(CoordinatorEntity[IdrCoordinator]):
    """Base class for all iDR entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IdrCoordinator, key: str) -> None:
        """Initialise the entity and link it to the iDR device."""
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            manufacturer=MANUFACTURER,
            model=coordinator.client.model,
            name=coordinator.data.unit_name,
        )
