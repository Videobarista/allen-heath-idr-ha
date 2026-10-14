"""Tests for integration setup/unload, focusing on offline-tolerant setup.

This is the behavior the integration was specifically changed to support:
a device that is simply switched off at the wall (e.g. via a mains switch
or a NET IO control) must not show as "Failed to set up" - the config
entry should load regardless, with the coordinator retrying on its normal
schedule in the background.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.allen_heath_idr.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant

from .mock_idr import MockIdr


async def test_setup_succeeds_when_device_is_offline(hass: HomeAssistant) -> None:
    """Setup succeeds even when the iDR can't be reached at all."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_PASSWORD: None},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.allen_heath_idr.coordinator.CONNECT_RETRY_ATTEMPTS", 1):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    coordinator = entry.runtime_data
    assert coordinator.data is None
    assert coordinator.last_update_success is False


async def test_entities_are_unavailable_while_offline(hass: HomeAssistant) -> None:
    """Entities report unavailable rather than the config entry failing to load."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_PASSWORD: None},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.allen_heath_idr.coordinator.CONNECT_RETRY_ATTEMPTS", 1):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    idr_states = [
        state for state in hass.states.async_all() if state.domain in ("number", "sensor", "switch")
    ]
    assert idr_states
    assert all(state.state == "unavailable" for state in idr_states)


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
        assert coordinator.data.unit_name == "Studio iDR"
    finally:
        await server.stop()


async def test_device_going_offline_later_marks_entities_unavailable(
    hass: HomeAssistant,
) -> None:
    """A device that drops offline after a successful setup degrades gracefully."""
    server = MockIdr()
    await server.start()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: server.host, CONF_PORT: server.port, CONF_PASSWORD: None},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert coordinator.data is not None

    await server.stop()  # the device "goes offline"

    with patch("custom_components.allen_heath_idr.coordinator.CONNECT_RETRY_ATTEMPTS", 1):
        await coordinator.async_refresh()

    assert entry.state is ConfigEntryState.LOADED  # the entry itself is unaffected
    assert coordinator.last_update_success is False


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
