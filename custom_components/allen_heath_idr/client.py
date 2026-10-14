"""Telnet client for the Allen & Heath iDR control protocol.

This module has no Home Assistant dependency so it can be exercised in
isolation against a real or simulated iDR unit. See ``iDR-Telnet-Control-
Protocol`` (Allen & Heath, firmware V3.50+) for the wire format this
implements.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum
import logging
import math
from typing import Final, NamedTuple

_LOGGER = logging.getLogger(__name__)

#: Words the iDR uses (and accepts back) for an "off"/-infinity gain.
OFF_WORDS: Final[frozenset[str]] = frozenset({"-inf", "-infinity", "off"})

_PROMPT_SUFFIX: Final = ">"
_LINE_END: Final = "\r"
_TERMINATOR: Final = b"\x00"
_PASSWORD_PROMPT: Final = "password:"
_BYE_COMMAND: Final = "Bye"


class GainType(StrEnum):
    """Gain command types supported by the iDR."""

    INPUT = "IPGAIN"
    OUTPUT = "OPGAIN"
    CROSSPOINT = "XPGAIN"
    INPUT_GROUP = "IPGROUPGAIN"
    OUTPUT_GROUP = "OPGROUPGAIN"
    CROSSPOINT_GROUP = "XPGROUPGAIN"


class MuteType(StrEnum):
    """Mute command types supported by the iDR."""

    INPUT = "IPMUTE"
    OUTPUT = "OPMUTE"
    CROSSPOINT = "XPMUTE"


#: (min, max) dB range for each gain type, excluding the separate "-INF" off state.
GAIN_LIMITS: Final[dict[GainType, tuple[float, float]]] = {
    GainType.INPUT: (-59.0, 5.0),
    GainType.OUTPUT: (-59.0, 5.0),
    GainType.CROSSPOINT: (-40.0, 0.0),
    GainType.INPUT_GROUP: (-64.0, 0.0),
    GainType.OUTPUT_GROUP: (-64.0, 0.0),
    GainType.CROSSPOINT_GROUP: (-64.0, 0.0),
}


class IdrIdentity(NamedTuple):
    """Identifying information read back from a connected iDR."""

    model: str
    unit_name: str


class IdrError(Exception):
    """Base error for all iDR client failures."""


class IdrConnectionError(IdrError):
    """Raised when the iDR cannot be reached, or drops the connection."""


class IdrAuthError(IdrError):
    """Raised when the iDR requires or rejects a password."""


class IdrCommandError(IdrError):
    """Raised when the iDR rejects a command (out of range, buffer overrun, ...)."""


class IdrProtocolError(IdrError):
    """Raised when a reply cannot be parsed the way the protocol describes."""


def parse_gain(text: str) -> float:
    """Parse a gain value as returned by the iDR, honoring the off-words."""
    cleaned = text.strip()
    if cleaned.lower() in OFF_WORDS:
        return -math.inf
    try:
        return float(cleaned)
    except ValueError as err:
        raise IdrProtocolError(f"Could not parse gain value: {text!r}") from err


def format_gain(value: float) -> str:
    """Format a gain value for sending to the iDR."""
    if math.isinf(value) and value < 0:
        return "-INF"
    return f"{value:.1f}"


def parse_mute(text: str) -> bool:
    """Parse an ON/OFF mute state as returned by the iDR."""
    cleaned = text.strip().lower()
    if cleaned in ("on", "1", "true"):
        return True
    if cleaned in ("off", "0", "false"):
        return False
    raise IdrProtocolError(f"Could not parse mute state: {text!r}")


def format_mute(value: bool) -> str:
    """Format a mute state for sending to the iDR."""
    return "ON" if value else "OFF"


class IdrClient:
    """A single-connection Telnet client for an Allen & Heath iDR unit.

    The iDR has a very small input buffer and only ever has one command in
    flight: sending a second command before the first reply has arrived
    gets a "Buffer Overrun" error back. Every reply, including the welcome
    banner, ends with the unit's prompt (``iDR4>`` or ``iDR8>``) followed by
    a NUL byte, which is what this client frames reads on rather than on
    newlines.
    """

    def __init__(
        self,
        host: str,
        port: int = 23,
        password: str | None = None,
        *,
        connect_timeout: float = 5.0,
        command_timeout: float = 5.0,
    ) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._connect_timeout = connect_timeout
        self._command_timeout = command_timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._model: str = "iDR"

    @property
    def host(self) -> str:
        """Return the configured host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the configured port."""
        return self._port

    @property
    def model(self) -> str:
        """Return the device model derived from its prompt (iDR4 or iDR8)."""
        return self._model

    @property
    def connected(self) -> bool:
        """Return whether a TCP connection is currently open."""
        return self._writer is not None and not self._writer.is_closing()

    async def async_connect(self) -> None:
        """Open the TCP connection and consume the welcome banner."""
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._connect_timeout,
            )
        except (TimeoutError, OSError) as err:
            raise IdrConnectionError(f"Cannot connect to {self._host}:{self._port}: {err}") from err

        try:
            banner, needs_password = await self._async_read_banner()

            if needs_password:
                if self._password is None:
                    raise IdrAuthError("The iDR requires a password but none was configured")
                writer = self._require_writer()
                try:
                    writer.write((self._password + _LINE_END).encode("ascii"))
                    await writer.drain()
                    banner, needs_password = await self._async_read_banner()
                except (OSError, IdrConnectionError) as err:
                    # Per the protocol doc, the iDR allows exactly one password
                    # attempt and drops the connection outright if it's wrong,
                    # rather than reprompting - so treat a drop here as a
                    # rejected password, not a generic connection failure.
                    raise IdrAuthError("The iDR rejected the configured password") from err
                if needs_password:
                    raise IdrAuthError("The iDR rejected the configured password")
        except IdrError:
            await self.async_close()
            raise

        self._model = self._extract_model(banner)

    async def async_close(self) -> None:
        """Close the TCP connection, if open, telling the iDR we're done."""
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        try:
            writer.write((_BYE_COMMAND + _LINE_END).encode("ascii"))
            await writer.drain()
        except OSError:
            pass
        try:
            writer.close()
            await writer.wait_closed()
        except OSError:
            pass

    async def async_command(self, command: str) -> str:
        """Send a single command and return its reply.

        Reconnects and retries exactly once if the connection turns out to
        be dead (e.g. the iDR timed out an idle session).
        """
        async with self._lock:
            last_error: IdrConnectionError | None = None
            for attempt in (1, 2):
                if not self.connected:
                    await self.async_connect()
                try:
                    return await self._async_send(command)
                except IdrConnectionError as err:
                    last_error = err
                    await self.async_close()
                    if attempt == 2:
                        raise
                    _LOGGER.debug("Connection to iDR lost, retrying command once")
            raise last_error or IdrConnectionError(f"Cannot reach {self._host}:{self._port}")

    async def _async_send(self, command: str) -> str:
        writer = self._require_writer()
        try:
            writer.write((command + _LINE_END).encode("ascii"))
            await writer.drain()
            reply = await self._async_read_until_terminator()
        except OSError as err:
            raise IdrConnectionError(
                f"Connection to {self._host}:{self._port} dropped: {err}"
            ) from err

        payload = self._strip_prompt(reply)
        if "buffer overrun" in payload.lower():
            raise IdrCommandError("The iDR reported a buffer overrun")
        if payload.lower().startswith(("invalid", "unknown", "error")):
            raise IdrCommandError(f"The iDR rejected the command: {payload}")
        return payload

    async def _async_read_until_terminator(self) -> str:
        reader = self._require_reader()
        try:
            raw = await asyncio.wait_for(
                reader.readuntil(_TERMINATOR), timeout=self._command_timeout
            )
        except asyncio.IncompleteReadError as err:
            raise IdrConnectionError("The iDR closed the connection unexpectedly") from err
        except (TimeoutError, OSError) as err:
            raise IdrConnectionError(f"Timed out waiting for the iDR to reply: {err}") from err
        return raw.decode("ascii", errors="replace").rstrip("\x00")

    async def _async_read_banner(self) -> tuple[str, bool]:
        """Read the post-connect banner and report whether it's a password prompt.

        A normal banner ends in the usual NUL-terminated prompt, but a
        password challenge is sent as a bare ``Password:`` with no
        terminator at all, so this can't simply read until a NUL.
        """
        reader = self._require_reader()
        buffer = b""
        try:
            async with asyncio.timeout(self._command_timeout):
                while True:
                    chunk = await reader.read(256)
                    if not chunk:
                        raise IdrConnectionError("The iDR closed the connection unexpectedly")
                    buffer += chunk
                    if _TERMINATOR in buffer:
                        text = buffer.decode("ascii", errors="replace").rstrip("\x00")
                        return text, False
                    if buffer.rstrip().endswith(b"Password:"):
                        return buffer.decode("ascii", errors="replace"), True
        except TimeoutError as err:
            raise IdrConnectionError(f"Timed out waiting for the iDR to reply: {err}") from err
        except OSError as err:
            raise IdrConnectionError(
                f"Connection to {self._host}:{self._port} dropped: {err}"
            ) from err

    def _require_writer(self) -> asyncio.StreamWriter:
        if self._writer is None:
            raise IdrConnectionError(f"Not connected to {self._host}:{self._port}")
        return self._writer

    def _require_reader(self) -> asyncio.StreamReader:
        if self._reader is None:
            raise IdrConnectionError(f"Not connected to {self._host}:{self._port}")
        return self._reader

    @staticmethod
    def _strip_prompt(reply: str) -> str:
        """Strip the trailing ``\\riDRn>`` prompt, returning the content before it."""
        prompt_start = reply.rfind(_LINE_END)
        if prompt_start != -1 and reply[prompt_start:].rstrip().endswith(_PROMPT_SUFFIX):
            reply = reply[:prompt_start]
        return reply.strip("\r\n ")

    @staticmethod
    def _extract_model(banner: str) -> str:
        for line in reversed(banner.splitlines()):
            cleaned = line.strip("\r\n ")
            if cleaned.endswith(_PROMPT_SUFFIX) and "idr" in cleaned.lower():
                return cleaned[:-1]
        return "iDR"

    async def async_get_unit_name(self) -> str:
        """Return the configured unit name."""
        return await self.async_command("GetUnitName")

    async def async_get_identity(self) -> IdrIdentity:
        """Return the model and unit name in a single round trip."""
        unit_name = await self.async_get_unit_name()
        return IdrIdentity(model=self._model, unit_name=unit_name)

    async def async_get_preset(self) -> int:
        """Return the currently active preset number."""
        reply = await self.async_command("GET PRESET")
        try:
            return int(reply.strip())
        except ValueError as err:
            raise IdrProtocolError(f"Could not parse preset number: {reply!r}") from err

    async def async_set_preset(self, preset: int) -> None:
        """Recall the given preset number."""
        await self.async_command(f"SET PRESET {preset}")

    async def async_get_gain(self, gain_type: GainType, *channels: int) -> float:
        """Return a gain value in dB (``-math.inf`` represents off)."""
        args = " ".join(str(channel) for channel in channels)
        reply = await self.async_command(f"GET {gain_type.value} {args}")
        return parse_gain(reply)

    async def async_set_gain(self, gain_type: GainType, *channels: int, gain: float) -> None:
        """Set a gain value in dB (``-math.inf`` turns the channel off)."""
        args = " ".join(str(channel) for channel in channels)
        await self.async_command(f"SET {gain_type.value} {args} {format_gain(gain)}")

    async def async_get_mute(self, mute_type: MuteType, *channels: int) -> bool:
        """Return a mute state."""
        args = " ".join(str(channel) for channel in channels)
        reply = await self.async_command(f"GET {mute_type.value} {args}")
        return parse_mute(reply)

    async def async_set_mute(self, mute_type: MuteType, *channels: int, mute: bool) -> None:
        """Set a mute state."""
        args = " ".join(str(channel) for channel in channels)
        await self.async_command(f"SET {mute_type.value} {args} {format_mute(mute)}")
