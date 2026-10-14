"""Tests for integration setup/unload, focusing on offline behavior.

A device that is simply switched off at the wall (e.g. via a mains switch
or a NET IO control) is a normal state, not an error: the config entry must
load regardless, its entities go unavailable, nothing is logged as an error,
and polling keeps retrying until the device responds again.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.allen_heath_idr.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .mock_idr import MockIdr

_RETRIES = "custom_components.allen_heath_idr.coordinator.CONNECT_RETRY_ATTEMPTS"


def _offline_entry() -> MockConfigEntry:
    """An entry pointing at a local port nothing listens on."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Studio iDR",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_PASSWORD: None},
    )


def _idr_states(hass: HomeAssistant) -> list:
    return [
        state for state in hass.states.async_all() if state.domain in ("number", "sensor", "switch")
    ]


async def test_setup_succeeds_when_device_is_offline(hass: HomeAssistant) -> None:
    """Setup succeeds even when the iDR can't be reached at all."""
    entry = _offline_entry()
    entry.add_to_hass(hass)

    with patch(_RETRIES, 1):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    assert coordinator.data is not None
    assert coordinator.data.online is False
    assert coordinator.data.unit_name == "Studio iDR"  # falls back to the entry title


async def test_entities_are_unavailable_while_offline(hass: HomeAssistant) -> None:
    """Entities report unavailable rather than the config entry failing to load."""
    entry = _offline_entry()
    entry.add_to_hass(hass)

    with patch(_RETRIES, 1):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    states = _idr_states(hass)
    assert states
    assert all(state.state == "unavailable" for state in states)


async def test_offline_device_logs_no_errors(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A switched-off iDR logs one info line, never an error, however often it's polled."""
    entry = _offline_entry()
    entry.add_to_hass(hass)

    with caplog.at_level(logging.INFO), patch(_RETRIES, 1):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        await coordinator.async_refresh()
        await coordinator.async_refresh()

    idr_records = [
        r for r in caplog.records if r.name.startswith("custom_components.allen_heath_idr")
    ]
    assert not [r for r in idr_records if r.levelno >= logging.WARNING]
    assert len([r for r in idr_records if "can't be reached" in r.getMessage()]) == 1


async def test_setup_succeeds_and_polls_when_device_is_reachable(hass: HomeAssistant) -> None:
    """When the device is reachable at startup, the first poll succeeds normally."""
    server = MockIdr()
    await server.start()
    try:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: server.host, CONF_PORT: server.port, CONF_PASSWORD: None},
        )
        entry.add_to_hass(hass)

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        coordinator = entry.runtime_data
        assert coordinator.data is not None
        assert coordinator.data.online is True
        assert coordinator.data.unit_name == "Studio iDR"
    finally:
        await server.stop()


async def test_device_going_offline_and_back(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A device that drops offline and returns recovers on its own, without errors."""
    server = MockIdr()
    await server.start()
    port = server.port
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: server.host, CONF_PORT: port, CONF_PASSWORD: None},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert coordinator.data.online is True

    with caplog.at_level(logging.INFO), patch(_RETRIES, 1):
        await server.stop()  # the device is switched off
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED  # the entry itself is unaffected
        assert coordinator.data.online is False
        assert all(state.state == "unavailable" for state in _idr_states(hass))

        await server.start(port)  # ...and switched back on
        try:
            await coordinator.async_refresh()
            await hass.async_block_till_done()

            assert coordinator.data.online is True
            assert all(state.state != "unavailable" for state in _idr_states(hass))
        finally:
            await server.stop()

    idr_records = [
        r for r in caplog.records if r.name.startswith("custom_components.allen_heath_idr")
    ]
    assert not [r for r in idr_records if r.levelno >= logging.WARNING]
    assert any("back online" in r.getMessage() for r in idr_records)


async def test_unload_closes_the_client(hass: HomeAssistant) -> None:
    """Unloading the entry closes the underlying TCP client."""
    server = MockIdr()
    await server.start()
    try:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: server.host, CONF_PORT: server.port, CONF_PASSWORD: None},
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with patch(
            "custom_components.allen_heath_idr.client.IdrClient.async_close",
            AsyncMock(),
        ) as mock_close:
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
            mock_close.assert_awaited_once()
    finally:
        await server.stop()


async def test_stale_entities_are_removed(hass: HomeAssistant) -> None:
    """Entities this entry no longer provides are cleaned out of the registry.

    Covers entities left behind by older versions and channels/crosspoints
    switched off in the options; current entities must be left alone.
    """
    entry = _offline_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "number", DOMAIN, f"{entry.entry_id}_input_1_to_output_1_gain", config_entry=entry
    )
    current = registry.async_get_or_create(
        "number", DOMAIN, f"{entry.entry_id}_gain_ipgain_1", config_entry=entry
    )

    with patch(_RETRIES, 1):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert registry.async_get(stale.entity_id) is None
    assert registry.async_get(current.entity_id) is not None
