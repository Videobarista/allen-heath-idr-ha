"""Services for the Allen & Heath iDR integration."""

from __future__ import annotations

import math
from typing import Any

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .client import MAX_CHANNELS, OFF_WORDS, GainType, MuteType
from .const import DOMAIN
from .coordinator import IdrCoordinator

SERVICE_SET_CROSSPOINT = "set_crosspoint"

ATTR_INPUT = "input"
ATTR_OUTPUT = "output"
ATTR_GAIN = "gain"
ATTR_MUTE = "mute"

_CHANNEL_NUMBER = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_CHANNELS))


def _validate_device_ids(value: Any) -> list[str]:
    """Accept a single device_id or a list of them, always return a list."""
    return [str(item) for item in cv.ensure_list(value)]


def _validate_gain(value: Any) -> float:
    """Accept a number in dB, or one of the words that mean the gain is off."""
    if isinstance(value, str) and value.strip().lower() in OFF_WORDS:
        return -math.inf
    try:
        return float(value)
    except (TypeError, ValueError) as err:
        raise vol.Invalid(
            f"gain must be a number in dB, or one of {sorted(OFF_WORDS)}"
        ) from err


SET_CROSSPOINT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): _validate_device_ids,
        vol.Required(ATTR_INPUT): _CHANNEL_NUMBER,
        vol.Required(ATTR_OUTPUT): _CHANNEL_NUMBER,
        vol.Optional(ATTR_GAIN): _validate_gain,
        vol.Optional(ATTR_MUTE): cv.boolean,
    }
)


def _async_resolve_coordinator(hass: HomeAssistant, device_id: str) -> IdrCoordinator:
    """Look up the coordinator behind one targeted device."""
    device = dr.async_get(hass).async_get(device_id)
    if device is not None:
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is not None and entry.domain == DOMAIN:
                return entry.runtime_data
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="device_not_found",
        translation_placeholders={"device_id": device_id},
    )


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the services of this integration. Safe to call more than once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_CROSSPOINT):
        return

    async def _async_set_crosspoint(call: ServiceCall) -> None:
        """Set the gain and/or mute of one crosspoint on the targeted device(s)."""
        gain = call.data.get(ATTR_GAIN)
        mute = call.data.get(ATTR_MUTE)
        if gain is None and mute is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="crosspoint_needs_gain_or_mute",
            )
        indices = (call.data[ATTR_INPUT], call.data[ATTR_OUTPUT])
        for device_id in call.data[CONF_DEVICE_ID]:
            coordinator = _async_resolve_coordinator(hass, device_id)
            if gain is not None:
                await coordinator.async_write_gain((GainType.CROSSPOINT, indices), gain)
            if mute is not None:
                await coordinator.async_write_mute((MuteType.CROSSPOINT, indices), mute)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CROSSPOINT,
        _async_set_crosspoint,
        schema=SET_CROSSPOINT_SCHEMA,
    )
