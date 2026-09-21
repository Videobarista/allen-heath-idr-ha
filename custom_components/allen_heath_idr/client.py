"""Asynchronous client for the Allen & Heath iDR Telnet control protocol.

The iDR (firmware V3.50 and later) offers a line based text protocol on TCP
port 23:

* every command ends with a carriage return (line feeds are ignored);
* the unit answers with the reply text followed by a prompt (``iDR8>`` or
  ``iDR4>``) that is terminated by a NUL byte;
* the input buffer of the unit is tiny, so exactly one command may be in
  flight at any time (otherwise the unit answers ``Buffer Overrun``).

This module has no Home Assistant dependencies.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT: Final = 5.0
COMMAND_TIMEOUT: Final = 5.0

MAX_CHANNELS: Final = 16
MAX_IO_GROUPS: Final = 8
MAX_CROSSPOINT_GROUPS: Final = 16
PRESET_MIN: Final = 1
PRESET_MAX: Final = 250

_PROMPT_RE: Final = re.compile(r"iDR(?P<model>\d)>\s*$")
_PASSWORD_RE: Final = re.compile(r"password\s*:\s*$", re.IGNORECASE)
_UNIT_NAME_RE: Final = re.compile(
    r"^\s*unit name\s*:\s*(?P<name>.*?)\s*$", re.IGNORECASE
)
_ERROR_MARKERS: Final = (
    "not recognised",
    "not recognized",
    "invalid",
    "error",
    "overrun",
    "out of range",
    "illegal",
    "unknown",
)
_OFF_WORDS: Final = frozenset({"-inf", "off", "-infinity"})


class IdrError(Exception):
    """Base class for all iDR client errors."""


class IdrConnectionError(IdrError):
    """The iDR could not be reached or the connection was lost."""


class IdrAuthError(IdrError):
    """The iDR requires a password that is missing or wrong."""


class IdrCommandError(IdrError):
    """The iDR reported an error for a command."""


class IdrProtocolError(IdrError):
    """The iDR sent a reply that this client does not understand."""


class GainType(StrEnum):
    """Gain values that can be read and written."""

    INPUT = "IPGAIN"
    OUTPUT = "OPGAIN"
    CROSSPOINT = "XPGAIN"
    INPUT_GROUP = "IPGROUPGAIN"
    OUTPUT_GROUP = "OPGROUPGAIN"
    CROSSPOINT_GROUP = "XPGROUPGAIN"


class MuteType(StrEnum):
    """Mute states that can be read and written."""

    INPUT = "IPMUTE"
    OUTPUT = "OPMUTE"
    CROSSPOINT = "XPMUTE"


# Gain range in dB per type. Below the lower limit the gain is -INF (off).
GAIN_LIMITS: Final[dict[GainType, tuple[float, float]]] = {
    GainType.INPUT: (-59.0, 5.0),
    GainType.OUTPUT: (-59.0, 5.0),
    GainType.CROSSPOINT: (-40.0, 0.0),
    GainType.INPUT_GROUP: (-64.0, 0.0),
    GainType.OUTPUT_GROUP: (-64.0, 0.0),
    GainType.CROSSPOINT_GROUP: (-64.0, 0.0),
}

_GAIN_INDEX_LIMITS: Final[dict[GainType, tuple[int, ...]]] = {
    GainType.INPUT: (MAX_CHANNELS,),
    GainType.OUTPUT: (MAX_CHANNELS,),
    GainType.CROSSPOINT: (MAX_CHANNELS, MAX_CHANNELS),
    GainType.INPUT_GROUP: (MAX_IO_GROUPS,),
    GainType.OUTPUT_GROUP: (MAX_IO_GROUPS,),
    GainType.CROSSPOINT_GROUP: (MAX_CROSSPOINT_GROUPS,),
}

_MUTE_INDEX_LIMITS: Final[dict[MuteType, tuple[int, ...]]] = {
    MuteType.INPUT: (MAX_CHANNELS,),
    MuteType.OUTPUT: (MAX_CHANNELS,),
    MuteType.CROSSPOINT: (MAX_CHANNELS, MAX_CHANNELS),
}


@dataclass(frozen=True)
class IdrIdentity:
    """Basic identification of an iDR."""

    unit_name: str
    model: str


def parse_gain(reply: str) -> float:
    """Convert a gain reply to dB. ``-inf`` means the gain is off."""
    text = reply.strip().lower()
    if text.endswith("db"):
        text = text[:-2].strip()
    if text in _OFF_WORDS:
        return -math.inf
    try:
        value = float(text)
    except ValueError as err:
        raise IdrProtocolError(f"Unexpected gain reply: {reply!r}") from err
    if not math.isfinite(value):
        raise IdrProtocolError(f"Unexpected gain reply: {reply!r}")
    return value


def format_gain(gain: float) -> str:
    """Convert a gain in dB to the text the iDR expects."""
    if gain == -math.inf:
        return "-Inf"
    return f"{gain:.1f}"


def parse_mute(reply: str) -> bool:
    """Convert a mute reply to a boolean (True means muted)."""
    text = reply.strip().lower()
    if text == "on":
        return True
    if text == "off":
        return False
    raise IdrProtocolError(f"Unexpected mute reply: {reply!r}")


def _validate_indices(
    kind: str, indices: tuple[int, ...], limits: tuple[int, ...]
) -> None:
    """Check that the index values are inside the ranges of the protocol."""
    if len(indices) != len(limits):
        raise ValueError(
            f"{kind} needs {len(limits)} index value(s), got {len(indices)}"
        )
    for value, upper in zip(indices, limits, strict=True):
        if not 1 <= value <= upper:
            raise ValueError(f"{kind} index {value} is outside 1..{upper}")


def _build_command(
    verb: str, kind: str, indices: tuple[int, ...], *extra: str
) -> str:
    """Build a control string such as ``GET XPGAIN 1 2``."""
    return " ".join([verb, kind, *(str(index) for index in indices), *extra])


def _raise_if_error(reply: str) -> None:
    """Raise IdrCommandError when the reply looks like an error message."""
    lowered = reply.lower()
    if any(marker in lowered for marker in _ERROR_MARKERS):
        raise IdrCommandError(reply)


class IdrClient:
    """Client for one iDR. Commands are sent strictly one at a time."""

    def __init__(
        self,
        host: str,
        port: int = 23,
        password: str | None = None,
        *,
        connect_timeout: float = CONNECT_TIMEOUT,
        command_timeout: float = COMMAND_TIMEOUT,
    ) -> None:
        """Initialise the client. No connection is made yet."""
        self._host = host
        self._port = port
        self._password = password
        self._connect_timeout = connect_timeout
        self._command_timeout = command_timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self.model: str | None = None

    @property
    def connected(self) -> bool:
        """Return True when a connection to the iDR is open."""
        return self._writer is not None

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    async def async_close(self) -> None:
        """Close the connection. Safe to call more than once."""
        async with self._lock:
            await self._async_disconnect()

    async def _async_disconnect(self) -> None:
        """Close the connection without taking the command lock."""
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            await self._async_close_writer(writer)

    @staticmethod
    async def _async_close_writer(writer: asyncio.StreamWriter) -> None:
        """Close a stream writer and log problems instead of hiding them."""
        writer.close()
        try:
            await writer.wait_closed()
        except OSError as err:
            _LOGGER.debug("Error while closing the connection: %s", err)

    async def _async_ensure_connected(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Return the open connection, opening it first when needed."""
        if self._reader is not None and self._writer is not None:
            return self._reader, self._writer
        return await self._async_connect()

    async def _async_connect(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Open a connection and wait for the first prompt."""
        try:
            async with asyncio.timeout(self._connect_timeout):
                reader, writer = await asyncio.open_connection(
                    self._host, self._port
                )
        except (OSError, TimeoutError) as err:
            raise IdrConnectionError(
                f"Cannot connect to {self._host}:{self._port}: {err}"
            ) from err

        try:
            async with asyncio.timeout(self._command_timeout):
                kind, _welcome = await self._async_read(reader, allow_password=True)
                if kind == "password":
                    await self._async_authenticate(reader, writer)
        except (OSError, TimeoutError) as err:
            await self._async_close_writer(writer)
            raise IdrConnectionError(
                f"No prompt from {self._host}:{self._port}: {err!r}"
            ) from err
        except IdrError:
            await self._async_close_writer(writer)
            raise

        self._reader = reader
        self._writer = writer
        _LOGGER.debug(
            "Connected to %s:%s (%s)", self._host, self._port, self.model
        )
        return reader, writer

    async def _async_authenticate(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Answer the password request of the iDR (one attempt only)."""
        if not self._password:
            raise IdrAuthError("The iDR is password protected but no password is set")
        try:
            writer.write(f"{self._password}\r".encode("latin-1"))
        except UnicodeEncodeError as err:
            raise IdrAuthError("The password contains unsupported characters") from err
        await writer.drain()
        try:
            kind, _text = await self._async_read(reader, allow_password=True)
        except (IdrConnectionError, OSError) as err:
            # The iDR drops the connection after a wrong password.
            raise IdrAuthError("The iDR rejected the password") from err
        if kind == "password":
            raise IdrAuthError("The iDR rejected the password")

    async def _async_read(
        self, reader: asyncio.StreamReader, *, allow_password: bool = False
    ) -> tuple[str, str]:
        """Read until a prompt (or password request) has arrived.

        Returns ("prompt" | "password", text before the prompt). The caller is
        responsible for the timeout.
        """
        buffer = ""
        while True:
            chunk = await reader.read(1024)
            if not chunk:
                raise IdrConnectionError("The iDR closed the connection")
            buffer += chunk.decode("latin-1").replace("\x00", "")
            prompt = _PROMPT_RE.search(buffer)
            if prompt:
                self.model = f"iDR-{prompt.group('model')}"
                return "prompt", buffer[: prompt.start()].strip()
            password = _PASSWORD_RE.search(buffer)
            if allow_password and password:
                return "password", buffer[: password.start()].strip()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_command(self, command: str, *, retry: bool = True) -> str:
        """Send one command and return the reply text without the prompt.

        When an already open connection turns out to be dead, the command is
        sent once more on a fresh connection, unless retry is False (use that
        for commands that must never be applied twice).
        """
        async with self._lock:
            reused = self._writer is not None
            try:
                return await self._async_exchange(command)
            except IdrConnectionError:
                await self._async_disconnect()
                if not (retry and reused):
                    raise
            _LOGGER.debug(
                "Connection to %s:%s was lost, reconnecting", self._host, self._port
            )
            try:
                return await self._async_exchange(command)
            except IdrConnectionError:
                await self._async_disconnect()
                raise

    async def _async_exchange(self, command: str) -> str:
        """Send a command on the current (or a new) connection."""
        reader, writer = await self._async_ensure_connected()
        try:
            async with asyncio.timeout(self._command_timeout):
                writer.write(f"{command}\r".encode("ascii"))
                await writer.drain()
                _kind, text = await self._async_read(reader)
        except (OSError, TimeoutError) as err:
            raise IdrConnectionError(
                f"Command {command!r} failed on {self._host}:{self._port}: {err!r}"
            ) from err
        _LOGGER.debug("iDR %s:%s %r -> %r", self._host, self._port, command, text)
        if "buffer overrun" in text.lower():
            await self._async_disconnect()
            raise IdrCommandError(text)
        return text

    # ------------------------------------------------------------------
    # Typed helpers
    # ------------------------------------------------------------------

    async def async_get_unit_name(self) -> str:
        """Return the unit name."""
        reply = await self.async_command("GetUnitName")
        match = _UNIT_NAME_RE.match(reply)
        if match is None:
            raise IdrProtocolError(f"Unexpected reply to GetUnitName: {reply!r}")
        return match.group("name")

    async def async_get_identity(self) -> IdrIdentity:
        """Return the unit name and the model derived from the prompt."""
        unit_name = await self.async_get_unit_name()
        return IdrIdentity(unit_name=unit_name, model=self.model or "iDR")

    async def async_get_preset(self) -> int:
        """Return the number of the current preset."""
        reply = await self.async_command("GET PRESET")
        _raise_if_error(reply)
        try:
            return int(reply.strip())
        except ValueError as err:
            raise IdrProtocolError(f"Unexpected preset reply: {reply!r}") from err

    async def async_set_preset(self, preset: int) -> None:
        """Recall a preset."""
        if not PRESET_MIN <= preset <= PRESET_MAX:
            raise ValueError(f"Preset {preset} is outside {PRESET_MIN}..{PRESET_MAX}")
        _raise_if_error(await self.async_command(f"SET PRESET {preset}"))

    async def async_get_gain(self, kind: GainType, indices: tuple[int, ...]) -> float:
        """Return a gain in dB (-inf when it is off)."""
        _validate_indices(kind, indices, _GAIN_INDEX_LIMITS[kind])
        reply = await self.async_command(_build_command("GET", kind, indices))
        _raise_if_error(reply)
        return parse_gain(reply)

    async def async_set_gain(
        self, kind: GainType, indices: tuple[int, ...], gain: float
    ) -> None:
        """Set a gain in dB (use -math.inf for off)."""
        _validate_indices(kind, indices, _GAIN_INDEX_LIMITS[kind])
        lower, upper = GAIN_LIMITS[kind]
        if gain != -math.inf and not lower <= gain <= upper:
            raise ValueError(f"{kind} gain {gain} is outside {lower}..{upper} dB")
        command = _build_command("SET", kind, indices, format_gain(gain))
        _raise_if_error(await self.async_command(command))

    async def async_get_mute(self, kind: MuteType, indices: tuple[int, ...]) -> bool:
        """Return a mute state (True means muted)."""
        _validate_indices(kind, indices, _MUTE_INDEX_LIMITS[kind])
        reply = await self.async_command(_build_command("GET", kind, indices))
        _raise_if_error(reply)
        return parse_mute(reply)

    async def async_set_mute(
        self, kind: MuteType, indices: tuple[int, ...], muted: bool
    ) -> None:
        """Set a mute state."""
        _validate_indices(kind, indices, _MUTE_INDEX_LIMITS[kind])
        command = _build_command("SET", kind, indices, "On" if muted else "Off")
        _raise_if_error(await self.async_command(command))
