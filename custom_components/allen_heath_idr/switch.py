"""Switch platform for the Allen & Heath iDR integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import MuteType
from .coordinator import IdrCoordinator, MuteKey
from .entity import IdrEntity

_TRANSLATION_KEYS: dict[MuteType, str] = {
    MuteType.INPUT: "input_mute",
    MuteType.OUTPUT: "output_mute",
    MuteType.CROSSPOINT: "crosspoint_mute",
}


def _placeholders(key: MuteKey) -> dict[str, str]:
    """Build the translation placeholders for a mute's friendly name."""
    if key.mute_type is MuteType.CROSSPOINT:
        return {"input": str(key.channels[0]), "output": str(key.channels[1])}
    return {"channel": str(key.channels[0])}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up iDR mute switches."""
    coordinator: IdrCoordinator = entry.runtime_data
    async_add_entities(IdrMuteSwitch(coordinator, key) for key in coordinator.options.mute_keys())


class IdrMuteSwitch(IdrEntity, SwitchEntity):
    """A single mute control on an iDR unit."""

    def __init__(self, coordinator: IdrCoordinator, key: MuteKey) -> None:
        super().__init__(coordinator, f"mute_{key.unique_suffix}")
        self._key = key
        self._attr_translation_key = _TRANSLATION_KEYS[key.mute_type]
        self._attr_translation_placeholders = _placeholders(key)
        if key.mute_type is MuteType.CROSSPOINT:
            # See number.py: crosspoints live in the Configuration section.
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def available(self) -> bool:
        """Return whether this mute was present in the latest poll."""
        return super().available and self._key in self.coordinator.data.mutes

    @property
    def is_on(self) -> bool | None:
        """Return whether the channel is currently muted."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.mutes.get(self._key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute the channel."""
        await self.coordinator.async_write_mute(self._key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute the channel."""
        await self.coordinator.async_write_mute(self._key, False)
