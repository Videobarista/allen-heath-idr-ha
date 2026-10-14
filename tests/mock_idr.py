"""A faithful in-process fake of the iDR Telnet protocol, for driving IdrClient
in tests without a real device: NUL-terminated prompts, a GetUnitName command,
GET/SET for presets, gains and mutes, an optional password challenge, and hooks
to simulate a buffer overrun or a dropped connection.
"""

from __future__ import annotations

import asyncio

from custom_components.allen_heath_idr.client import (
    format_gain,
    format_mute,
    parse_gain,
    parse_mute,
)

_TERMINATOR = b"\x00"


class MockIdr:
    """A local asyncio TCP server that behaves like an Allen & Heath iDR unit."""

    def __init__(self, *, model: str = "iDR8", password: str | None = None) -> None:
        self.model = model
        self.password = password
        self.unit_name = "Studio iDR"
        self.preset = 1
        self.gains: dict[tuple[str, tuple[int, ...]], float] = {}
        self.mutes: dict[tuple[str, tuple[int, ...]], bool] = {}
        self.drop_next_connection = False
        self.force_overrun_once = False
        self.connection_count = 0
        self.host = "127.0.0.1"
        self.port = 0
        self._server: asyncio.base_events.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()

    async def start(self, port: int = 0) -> None:
        """Start listening, on an ephemeral local port unless one is given.

        Passing the previous port lets a test "switch the device back on" at
        the same address the integration is configured for.
        """
        self._server = await asyncio.start_server(self._handle, self.host, port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop listening and drop any open connection.

        Open client connections are closed explicitly first: since Python 3.12,
        ``wait_closed()`` waits for every connection to finish, so it would hang
        forever while Home Assistant still holds its connection to the "device".
        """
        if self._server is None:
            return
        self._server.close()
        for writer in list(self._writers):
            writer.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        try:
            await self._serve(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connection_count += 1
        if self.drop_next_connection:
            self.drop_next_connection = False
            writer.close()
            return

        writer.write(b"Connected to iDR\r\n")
        await writer.drain()

        if self.password is not None:
            writer.write(b"Password:")
            await writer.drain()
            try:
                line = await reader.readuntil(b"\r")
            except asyncio.IncompleteReadError:
                writer.close()
                return
            if line.rstrip(b"\r").decode() != self.password:
                # The real unit drops the connection after one failed attempt.
                writer.close()
                return

        writer.write(f"\r{self.model}>".encode() + _TERMINATOR)
        await writer.drain()

        while True:
            try:
                line = await reader.readuntil(b"\r")
            except asyncio.IncompleteReadError:
                return
            command = line.rstrip(b"\r").decode()
            if command == "Bye":
                writer.close()
                return
            if self.force_overrun_once:
                self.force_overrun_once = False
                reply = "Buffer Overrun"
            else:
                reply = self._dispatch(command)
            writer.write(f"{reply}\r\n\r{self.model}>".encode() + _TERMINATOR)
            await writer.drain()

    def _dispatch(self, command: str) -> str:
        parts = command.split()
        verb, kind = parts[0].upper(), (parts[1].upper() if len(parts) > 1 else "")

        if command == "GetUnitName":
            return self.unit_name

        if kind == "PRESET":
            if verb == "GET":
                return str(self.preset)
            self.preset = int(parts[2])
            return ""

        if kind in ("IPGAIN", "OPGAIN", "XPGAIN", "IPGROUPGAIN", "OPGROUPGAIN"):
            channels_count = 2 if kind == "XPGAIN" else 1
            if verb == "GET":
                channels = tuple(int(p) for p in parts[2 : 2 + channels_count])
                return format_gain(self.gains.get((kind, channels), 0.0))
            channels = tuple(int(p) for p in parts[2 : 2 + channels_count])
            self.gains[(kind, channels)] = parse_gain(parts[2 + channels_count])
            return ""

        if kind in ("IPMUTE", "OPMUTE", "XPMUTE"):
            channels_count = 2 if kind == "XPMUTE" else 1
            if verb == "GET":
                channels = tuple(int(p) for p in parts[2 : 2 + channels_count])
                return format_mute(self.mutes.get((kind, channels), False))
            channels = tuple(int(p) for p in parts[2 : 2 + channels_count])
            self.mutes[(kind, channels)] = parse_mute(parts[2 + channels_count])
            return ""

        return "Unknown Command"
