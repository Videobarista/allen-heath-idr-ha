"""Number platform for the Allen & Heath iDR integration."""

from __future__ import annotations

import math

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import GAIN_LIMITS, GainType
from .const import PRESET_MAX, PRESET_MIN
from .coordinator import GainKey, IdrCoordinator
from .entity import IdrEntity

GAIN_STEP = 0.5

_TRANSLATION_KEYS: dict[GainType, str] = {
    GainType.INPUT: "input_gain",
    GainType.OUTPUT: "output_gain",
    GainType.CROSSPOINT: "crosspoint_gain",
    GainType.INPUT_GROUP: "input_group_gain",
    GainType.OUTPUT_GROUP: "output_group_gain",
    GainType.CROSSPOINT_GROUP: "crosspoint_group_gain",
}


def _placeholders(key: GainKey) -> dict[str, str]:
    """Build the translation placeholders for a gain's friendly name."""
    if key.gain_type is GainType.CROSSPOINT:
        return {"input": str(key.channels[0]), "output": str(key.channels[1])}
    return {"channel": str(key.channels[0])}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up iDR number entities (preset recall + gains)."""
    coordinator: IdrCoordinator = entry.runtime_data
    entities: list[NumberEntity] = [IdrPresetNumber(coordinator)]
    entities.extend(IdrGainNumber(coordinator, key) for key in coordinator.options.gain_keys())
    async_add_entities(entities)


class IdrPresetNumber(IdrEntity, NumberEntity):
    """Recalls an iDR preset by number."""

    _attr_translation_key = "preset"
    _attr_native_min_value = PRESET_MIN
    _attr_native_max_value = PRESET_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: IdrCoordinator) -> None:
        super().__init__(coordinator, "preset")

    @property
    def native_value(self) -> float | None:
        """Return the currently active preset number."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.preset

    async def async_set_native_value(self, value: float) -> None:
        """Recall the given preset."""
        await self.coordinator.async_recall_preset(int(value))


class IdrGainNumber(IdrEntity, NumberEntity):
    """A single gain control on an iDR unit."""

    _attr_mode = NumberMode.BOX
    _attr_native_step = GAIN_STEP
    _attr_native_unit_of_measurement = "dB"

    def __init__(self, coordinator: IdrCoordinator, key: GainKey) -> None:
        super().__init__(coordinator, f"gain_{key.unique_suffix}")
        self._key = key
        lower, upper = GAIN_LIMITS[key.gain_type]
        # One extra step below the real minimum is reserved as the "off" sentinel,
        # since the iDR's -Inf (off) state isn't a number on the normal dB scale.
        self._attr_native_min_value = lower - GAIN_STEP
        self._attr_native_max_value = upper
        self._attr_translation_key = _TRANSLATION_KEYS[key.gain_type]
        self._attr_translation_placeholders = _placeholders(key)
        if key.gain_type is GainType.CROSSPOINT:
            # Keeps the (many) crosspoints out of the main Controls list on the
            # device page, so presets, inputs and outputs stay easy to find.
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def available(self) -> bool:
        """Return whether this gain was present in the latest poll."""
        return super().available and self._key in self.coordinator.data.gains

    @property
    def native_value(self) -> float | None:
        """Return the current gain, or the off-sentinel value when the channel is off."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.gains.get(self._key)
        if value is None:
            return None
        if math.isinf(value):
            return self._attr_native_min_value
        return value

    @property
    def extra_state_attributes(self) -> dict[str, bool] | None:
        """Expose whether the channel is currently off (``-Inf`` gain)."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.gains.get(self._key)
        if value is None:
            return None
        return {"off": math.isinf(value)}

    async def async_set_native_value(self, value: float) -> None:
        """Write a new gain, translating the off-sentinel back to ``-Inf``."""
        gain = -math.inf if value <= self._attr_native_min_value else value
        await self.coordinator.async_write_gain(self._key, gain)
