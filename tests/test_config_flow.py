"""Tests for the config, reauth, reconfigure and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.allen_heath_idr.client import (
    IdrAuthError,
    IdrConnectionError,
    IdrIdentity,
    IdrProtocolError,
)
from custom_components.allen_heath_idr.const import DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .mock_idr import MockIdr

VALID_IDENTITY = IdrIdentity(model="iDR8", unit_name="Studio iDR")
_VALIDATE = "custom_components.allen_heath_idr.config_flow._async_validate"


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """A successful connection creates an entry titled after the unit's name."""
    with patch(_VALIDATE, AsyncMock(return_value=VALID_IDENTITY)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "10.99.99.25", CONF_PORT: 23}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Studio iDR"
    assert result["data"] == {CONF_HOST: "10.99.99.25", CONF_PORT: 23, CONF_PASSWORD: None}


@pytest.mark.parametrize(
    ("error", "expected_key"),
    [
        (IdrConnectionError("boom"), "cannot_connect"),
        (IdrAuthError("boom"), "invalid_auth"),
        (IdrProtocolError("boom"), "invalid_response"),
    ],
)
async def test_user_flow_errors(hass: HomeAssistant, error: Exception, expected_key: str) -> None:
    """Each client error maps to the matching form error."""
    with patch(_VALIDATE, AsyncMock(side_effect=error)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "10.99.99.25", CONF_PORT: 23}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_key}


async def test_user_flow_aborts_on_duplicate(hass: HomeAssistant) -> None:
    """A second entry for the same host/port is rejected."""
    MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "10.99.99.25", CONF_PORT: 23, CONF_PASSWORD: None}
    ).add_to_hass(hass)

    with patch(_VALIDATE, AsyncMock(return_value=VALID_IDENTITY)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "10.99.99.25", CONF_PORT: 23}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_success(hass: HomeAssistant) -> None:
    """A successful reauth updates the stored password."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "10.99.99.25", CONF_PORT: 23, CONF_PASSWORD: "old"}
    )
    entry.add_to_hass(hass)

    with (
        patch(_VALIDATE, AsyncMock(return_value=VALID_IDENTITY)),
        patch(
            "custom_components.allen_heath_idr.client.IdrClient.async_connect",
            AsyncMock(side_effect=IdrConnectionError("no real device in tests")),
        ),
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new"


async def test_reauth_flow_failure(hass: HomeAssistant) -> None:
    """A rejected password during reauth shows the form again with an error."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "10.99.99.25", CONF_PORT: 23, CONF_PASSWORD: "old"}
    )
    entry.add_to_hass(hass)

    with patch(_VALIDATE, AsyncMock(side_effect=IdrAuthError("boom"))):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "still-wrong"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_flow_success(hass: HomeAssistant) -> None:
    """Reconfiguring to a different, reachable unit updates and reloads the entry."""
    old_server = MockIdr()
    old_server.unit_name = "Old iDR"
    await old_server.start()
    new_server = MockIdr()
    new_server.unit_name = "New iDR"
    await new_server.start()
    try:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: old_server.host, CONF_PORT: old_server.port, CONF_PASSWORD: None},
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: new_server.host, CONF_PORT: new_server.port},
        )
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_HOST] == new_server.host
        assert entry.data[CONF_PORT] == new_server.port
        assert entry.runtime_data.data.unit_name == "New iDR"
    finally:
        await old_server.stop()
        await new_server.stop()


async def test_options_flow(hass: HomeAssistant) -> None:
    """The options flow stores the submitted values and reloads the entry."""
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

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "inputs": 4,
                "outputs": 4,
                "expose_groups": True,
                "expose_crosspoints": True,
                "scan_interval": 15,
            },
        )
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options["inputs"] == 4
        assert entry.options["expose_crosspoints"] is True
    finally:
        await server.stop()
