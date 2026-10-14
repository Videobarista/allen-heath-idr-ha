"""Base entity for the Allen & Heath iDR integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import IdrCoordinator


class IdrEntity(CoordinatorEntity[IdrCoordinator]):
    """Base class for all Allen & Heath iDR entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IdrCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            manufacturer=MANUFACTURER,
            model=coordinator.client.model,
            name=self._device_name,
        )

    @property
    def _device_name(self) -> str:
        """Return the best known unit name.

        Before the first successful poll ``coordinator.data`` is ``None``
        (the device may simply be switched off at the time), so this falls
        back to the config entry title, which was set to the unit's name
        when the integration was first configured.
        """
        if self.coordinator.data is not None:
            return self.coordinator.data.unit_name
        return self.coordinator.config_entry.title

    @property
    def available(self) -> bool:
        """Return whether this entity's reading is currently available.

        Only true once the coordinator has completed at least one
        successful poll. Before that, or whenever the device drops
        offline again later, the entity reports unavailable rather than
        the whole config entry failing to set up.
        """
        return super().available and self.coordinator.data is not None
