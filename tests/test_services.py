"""Tests for the set_crosspoint service."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.allen_heath_idr.client import GainType, MuteType
from custom_components.allen_heath_idr.const import DOMAIN
from custom_components.allen_heath_idr.coordinator import GainKey, MuteKey
from custom_components.allen_heath_idr.services import SERVICE_SET_CROSSPOINT
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .mock_idr import MockIdr


async def _setup_entry(hass: HomeAssistant, server: MockIdr) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: server.host, CONF_PORT: server.port, CONF_PASSWORD: None},
        options={"expose_crosspoints": True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _crosspoint_gain_entity_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Look up the gain entity_id for crosspoint 1->1 via its known unique_id.

    Looked up rather than hardcoded, since the exact entity_id slug depends on
    Home Assistant's own slugification of the device/entity name.
    """
    registry = er.async_get(hass)
    key = GainKey(GainType.CROSSPOINT, (1, 1))
    unique_id = f"{entry.entry_id}_gain_{key.unique_suffix}"
    entity_id = registry.async_get_entity_id("number", DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


async def test_set_crosspoint_writes_gain_and_mute(hass: HomeAssistant) -> None:
    """The service writes both gain and mute when both are given."""
    server = MockIdr()
    await server.start()
    try:
        entry = await _setup_entry(hass, server)
        entity_id = _crosspoint_gain_entity_id(hass, entry)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_CROSSPOINT,
            {"entity_id": [entity_id], "input": 1, "output": 1, "gain": -5.0, "mute": True},
            blocking=True,
        )

        coordinator = entry.runtime_data
        assert coordinator.data.gains[GainKey(GainType.CROSSPOINT, (1, 1))] == -5.0
        assert coordinator.data.mutes[MuteKey(MuteType.CROSSPOINT, (1, 1))] is True
    finally:
        await server.stop()


async def test_set_crosspoint_requires_gain_or_mute(hass: HomeAssistant) -> None:
    """Calling the service with neither gain nor mute raises a clear error."""
    server = MockIdr()
    await server.start()
    try:
        entry = await _setup_entry(hass, server)
        entity_id = _crosspoint_gain_entity_id(hass, entry)
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_CROSSPOINT,
                {"entity_id": [entity_id], "input": 1, "output": 1},
                blocking=True,
            )
    finally:
        await server.stop()


async def test_set_crosspoint_unknown_entity(hass: HomeAssistant) -> None:
    """A non-iDR entity_id is rejected with a clear error."""
    server = MockIdr()
    await server.start()
    try:
        await _setup_entry(hass, server)
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_CROSSPOINT,
                {
                    "entity_id": ["number.does_not_exist"],
                    "input": 1,
                    "output": 1,
                    "gain": -5.0,
                },
                blocking=True,
            )
    finally:
        await server.stop()
