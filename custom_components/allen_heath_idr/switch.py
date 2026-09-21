"""Mute switches for the Allen & Heath iDR integration."""

from __future__ import annotations

from typing import Any, Final

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import MuteType
from .coordinator import IdrConfigEntry, IdrCoordinator, MuteKey
from .entity import IdrEntity

_TRANSLATION_KEYS: Final[dict[MuteType, str]] = {
    MuteType.INPUT: "input_mute",
    MuteType.OUTPUT: "output_mute",
    MuteType.CROSSPOINT: "crosspoint_mute",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IdrConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iDR mute switches."""
    coordinator = entry.runtime_data
    async_add_entities(IdrMuteSwitch(coordinator, key) for key in coordinator.mute_keys)


class IdrMuteSwitch(IdrEntity, SwitchEntity):
    """A mute state. The switch is on when the channel or crosspoint is muted."""

    _attr_icon = "mdi:volume-off"

    def __init__(self, coordinator: IdrCoordinator, key: MuteKey) -> None:
        """Initialise a mute switch."""
        kind, indices = key
        name = "_".join([kind.value.lower(), *(str(index) for index in indices)])
        super().__init__(coordinator, name)
        self._key = key
        self._attr_translation_key = _TRANSLATION_KEYS[kind]
        if kind == MuteType.CROSSPOINT:
            self._attr_translation_placeholders = {
                "input": str(indices[0]),
                "output": str(indices[1]),
            }
        else:
            self._attr_translation_placeholders = {"channel": str(indices[0])}

    @property
    def available(self) -> bool:
        """Return True when the mute state could be read from the iDR."""
        return super().available and self._key in self.coordinator.data.mutes

    @property
    def is_on(self) -> bool | None:
        """Return True when muted."""
        return self.coordinator.data.mutes.get(self._key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute."""
        await self.coordinator.async_write_mute(self._key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute."""
        await self.coordinator.async_write_mute(self._key, False)
