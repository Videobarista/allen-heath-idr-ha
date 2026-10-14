"""Services for the Allen & Heath iDR integration."""

from __future__ import annotations

import math
from typing import Any

import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .client import OFF_WORDS, GainType, MuteType
from .const import DOMAIN
from .coordinator import GainKey, IdrCoordinator, MuteKey

SERVICE_SET_CROSSPOINT = "set_crosspoint"

ATTR_INPUT = "input"
ATTR_OUTPUT = "output"
ATTR_GAIN = "gain"
ATTR_MUTE = "mute"

_CHANNEL_NUMBER = vol.All(vol.Coerce(int), vol.Range(min=1, max=16))


def _validate_gain(value: Any) -> float:
    """Accept a numeric dB value or one of the iDR's off-words."""
    if isinstance(value, str) and value.strip().lower() in OFF_WORDS:
        return -math.inf
    try:
        return float(value)
    except (TypeError, ValueError) as err:
        raise vol.Invalid(f"Not a valid gain: {value!r}") from err


SET_CROSSPOINT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_INPUT): _CHANNEL_NUMBER,
        vol.Required(ATTR_OUTPUT): _CHANNEL_NUMBER,
        vol.Optional(ATTR_GAIN): _validate_gain,
        vol.Optional(ATTR_MUTE): cv.boolean,
    }
)


def _async_resolve_coordinator(hass: HomeAssistant, entity_id: str) -> IdrCoordinator:
    """Resolve the iDR coordinator that owns the given entity."""
    entity_entry = er.async_get(hass).async_get(entity_id)
    if entity_entry is None or entity_entry.config_entry_id is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entity_not_found",
            translation_placeholders={"entity_id": entity_id},
        )
    entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entity_not_found",
            translation_placeholders={"entity_id": entity_id},
        )
    return entry.runtime_data


async def _async_handle_set_crosspoint(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the set_crosspoint service call."""
    gain = call.data.get(ATTR_GAIN)
    mute = call.data.get(ATTR_MUTE)
    if gain is None and mute is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="crosspoint_needs_gain_or_mute"
        )

    input_channel = call.data[ATTR_INPUT]
    output_channel = call.data[ATTR_OUTPUT]

    # A single picked "device" expands to several entity_ids that all belong to the
    # same iDR, so coordinators are deduplicated before writing to avoid writing
    # the same crosspoint more than once.
    coordinators: dict[int, IdrCoordinator] = {}
    for entity_id in call.data[ATTR_ENTITY_ID]:
        coordinator = _async_resolve_coordinator(hass, entity_id)
        coordinators[id(coordinator)] = coordinator

    for coordinator in coordinators.values():
        if gain is not None:
            await coordinator.async_write_gain(
                GainKey(GainType.CROSSPOINT, (input_channel, output_channel)), gain
            )
        if mute is not None:
            await coordinator.async_write_mute(
                MuteKey(MuteType.CROSSPOINT, (input_channel, output_channel)), mute
            )


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the integration's services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_CROSSPOINT):
        return

    async def _handle_set_crosspoint(call: ServiceCall) -> None:
        await _async_handle_set_crosspoint(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_SET_CROSSPOINT, _handle_set_crosspoint, schema=SET_CROSSPOINT_SCHEMA
    )
