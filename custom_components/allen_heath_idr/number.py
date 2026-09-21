"""Number entities (gains and preset) for the Allen & Heath iDR integration."""

from __future__ import annotations

import math
from typing import Any, Final

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import GAIN_LIMITS, PRESET_MAX, PRESET_MIN, GainType
from .coordinator import GainKey, IdrConfigEntry, IdrCoordinator
from .entity import IdrEntity

GAIN_STEP_DB: Final = 0.5

_TRANSLATION_KEYS: Final[dict[GainType, str]] = {
    GainType.INPUT: "input_gain",
    GainType.OUTPUT: "output_gain",
    GainType.CROSSPOINT: "crosspoint_gain",
    GainType.INPUT_GROUP: "input_group_gain",
    GainType.OUTPUT_GROUP: "output_group_gain",
    GainType.CROSSPOINT_GROUP: "crosspoint_group_gain",
}


def _placeholders(kind: GainType, indices: tuple[int, ...]) -> dict[str, str]:
    """Return the values that are filled in the translated entity name."""
    if kind == GainType.CROSSPOINT:
        return {"input": str(indices[0]), "output": str(indices[1])}
    if kind in (
        GainType.INPUT_GROUP,
        GainType.OUTPUT_GROUP,
        GainType.CROSSPOINT_GROUP,
    ):
        return {"group": str(indices[0])}
    return {"channel": str(indices[0])}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IdrConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iDR number entities."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [IdrPresetNumber(coordinator)]
    entities.extend(IdrGainNumber(coordinator, key) for key in coordinator.gain_keys)
    async_add_entities(entities)


class IdrPresetNumber(IdrEntity, NumberEntity):
    """The current preset. Setting a value recalls that preset."""

    _attr_translation_key = "preset"
    _attr_icon = "mdi:playlist-play"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = PRESET_MIN
    _attr_native_max_value = PRESET_MAX
    _attr_native_step = 1

    def __init__(self, coordinator: IdrCoordinator) -> None:
        """Initialise the preset entity."""
        super().__init__(coordinator, "preset")

    @property
    def native_value(self) -> float | None:
        """Return the number of the current preset."""
        return self.coordinator.data.preset

    async def async_set_native_value(self, value: float) -> None:
        """Recall a preset."""
        await self.coordinator.async_recall_preset(round(value))


class IdrGainNumber(IdrEntity, NumberEntity):
    """A gain in dB. The lowest value means that the gain is off (-inf)."""

    _attr_native_step = GAIN_STEP_DB
    _attr_native_unit_of_measurement = "dB"
    _attr_icon = "mdi:volume-high"

    def __init__(self, coordinator: IdrCoordinator, key: GainKey) -> None:
        """Initialise a gain entity."""
        kind, indices = key
        name = "_".join([kind.value.lower(), *(str(index) for index in indices)])
        super().__init__(coordinator, name)
        lower, upper = GAIN_LIMITS[kind]
        self._key = key
        self._lower = lower
        self._attr_translation_key = _TRANSLATION_KEYS[kind]
        self._attr_translation_placeholders = _placeholders(kind, indices)
        self._attr_native_min_value = lower - 1
        self._attr_native_max_value = upper

    @property
    def available(self) -> bool:
        """Return True when the gain could be read from the iDR."""
        return super().available and self._key in self.coordinator.data.gains

    @property
    def native_value(self) -> float | None:
        """Return the gain in dB, or the lowest value when it is off."""
        gain = self.coordinator.data.gains.get(self._key)
        if gain is None:
            return None
        return self._attr_native_min_value if gain == -math.inf else gain

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Show whether the gain is off (-inf)."""
        gain = self.coordinator.data.gains.get(self._key)
        if gain is None:
            return None
        return {"off": gain == -math.inf}

    async def async_set_native_value(self, value: float) -> None:
        """Set the gain. Values below the lowest gain switch it off."""
        gain = -math.inf if value < self._lower else value
        await self.coordinator.async_write_gain(self._key, gain)
