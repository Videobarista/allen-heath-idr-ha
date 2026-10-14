"""Tests for the standalone Telnet client (no Home Assistant dependency)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import math

import pytest

from custom_components.allen_heath_idr.client import (
    GainType,
    IdrAuthError,
    IdrClient,
    IdrCommandError,
    IdrConnectionError,
    MuteType,
    format_gain,
    format_mute,
    parse_gain,
    parse_mute,
)

from .mock_idr import MockIdr


@pytest.fixture
async def mock_idr() -> AsyncGenerator[MockIdr]:
    """A running fake iDR server."""
    server = MockIdr()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
async def client(mock_idr: MockIdr) -> AsyncGenerator[IdrClient]:
    """An IdrClient connected to the fake server."""
    idr_client = IdrClient(mock_idr.host, mock_idr.port, connect_timeout=2, command_timeout=2)
    yield idr_client
    await idr_client.async_close()


async def test_unit_name_and_identity(client: IdrClient) -> None:
    """GetUnitName and the model parsed from the prompt are both returned."""
    assert await client.async_get_unit_name() == "Studio iDR"
    identity = await client.async_get_identity()
    assert identity.model == "iDR8"
    assert identity.unit_name == "Studio iDR"


async def test_preset_get_set(client: IdrClient) -> None:
    """A preset can be recalled and read back."""
    await client.async_set_preset(7)
    assert await client.async_get_preset() == 7


async def test_gain_get_set_including_off(client: IdrClient) -> None:
    """A gain can be set to a normal value and to -Inf (off)."""
    await client.async_set_gain(GainType.INPUT, 1, gain=-6.0)
    assert await client.async_get_gain(GainType.INPUT, 1) == -6.0

    await client.async_set_gain(GainType.INPUT, 1, gain=-math.inf)
    assert math.isinf(await client.async_get_gain(GainType.INPUT, 1))


async def test_crosspoint_gain(client: IdrClient) -> None:
    """A crosspoint gain takes two channel numbers."""
    await client.async_set_gain(GainType.CROSSPOINT, 2, 3, gain=-10.0)
    assert await client.async_get_gain(GainType.CROSSPOINT, 2, 3) == -10.0


async def test_mute_get_set(client: IdrClient) -> None:
    """A mute state can be toggled and read back."""
    await client.async_set_mute(MuteType.OUTPUT, 4, mute=True)
    assert await client.async_get_mute(MuteType.OUTPUT, 4) is True

    await client.async_set_mute(MuteType.OUTPUT, 4, mute=False)
    assert await client.async_get_mute(MuteType.OUTPUT, 4) is False


async def test_crosspoint_mute(client: IdrClient) -> None:
    """A crosspoint mute takes two channel numbers."""
    await client.async_set_mute(MuteType.CROSSPOINT, 1, 1, mute=True)
    assert await client.async_get_mute(MuteType.CROSSPOINT, 1, 1) is True


async def test_buffer_overrun_raises_command_error(client: IdrClient, mock_idr: MockIdr) -> None:
    """A "Buffer Overrun" reply is surfaced as IdrCommandError."""
    mock_idr.force_overrun_once = True
    with pytest.raises(IdrCommandError):
        await client.async_get_gain(GainType.INPUT, 1)


async def test_dead_connection_is_retried_once(client: IdrClient) -> None:
    """A connection that died underneath the client is transparently reopened."""
    await client.async_get_unit_name()  # establish a connection
    client._writer.close()  # type: ignore[union-attr]  # simulate it dying
    assert await client.async_get_unit_name() == "Studio iDR"


async def test_correct_password_connects(mock_idr: MockIdr) -> None:
    """A correctly configured password lets the client connect."""
    mock_idr.password = "secret"  # noqa: S105 - test fixture, not a real credential
    idr_client = IdrClient(
        mock_idr.host, mock_idr.port, "secret", connect_timeout=2, command_timeout=2
    )
    assert await idr_client.async_get_unit_name() == "Studio iDR"
    await idr_client.async_close()


async def test_wrong_password_raises_auth_error(mock_idr: MockIdr) -> None:
    """A rejected password raises IdrAuthError, not a generic connection error."""
    mock_idr.password = "secret"  # noqa: S105 - test fixture, not a real credential
    idr_client = IdrClient(
        mock_idr.host, mock_idr.port, "wrong", connect_timeout=2, command_timeout=2
    )
    with pytest.raises(IdrAuthError):
        await idr_client.async_get_unit_name()


async def test_unreachable_host_raises_connection_error() -> None:
    """Connecting to a closed port raises IdrConnectionError."""
    idr_client = IdrClient("127.0.0.1", 1, connect_timeout=1, command_timeout=1)
    with pytest.raises(IdrConnectionError):
        await idr_client.async_get_unit_name()


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-math.inf, "-INF"), (-6.0, "-6.0"), (0.0, "0.0"), (5.0, "5.0")],
)
def test_format_gain(value: float, expected: str) -> None:
    """Gains format with one decimal place, and -Inf becomes -INF."""
    assert format_gain(value) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("-Inf", -math.inf), ("OFF", -math.inf), ("-infinity", -math.inf), ("-6.5", -6.5)],
)
def test_parse_gain(text: str, expected: float) -> None:
    """Off-words parse to -Inf regardless of case; everything else is a float."""
    assert parse_gain(text) == expected


def test_format_and_parse_mute() -> None:
    """Mute states round-trip through ON/OFF text."""
    assert format_mute(True) == "ON"
    assert format_mute(False) == "OFF"
    assert parse_mute("ON") is True
    assert parse_mute("off") is False
