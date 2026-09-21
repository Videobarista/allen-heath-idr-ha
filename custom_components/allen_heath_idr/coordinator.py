"""Data update coordinator for the Allen & Heath iDR integration."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    MAX_CHANNELS,
    MAX_CROSSPOINT_GROUPS,
    MAX_IO_GROUPS,
    GainType,
    IdrAuthError,
    IdrClient,
    IdrCommandError,
    IdrError,
    IdrProtocolError,
    MuteType,
    format_gain,
)
from .const import (
    CONF_CROSSPOINTS,
    CONF_GROUPS,
    CONF_INPUTS,
    CONF_OUTPUTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_INPUTS,
    DEFAULT_OUTPUTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# A gain read back from the iDR may differ a little from the requested value
# because the unit works with fixed steps. A bigger difference means that the
# value was not applied.
GAIN_TOLERANCE_DB = 3.0

type GainKey = tuple[GainType, tuple[int, ...]]
type MuteKey = tuple[MuteType, tuple[int, ...]]
type IdrConfigEntry = ConfigEntry[IdrCoordinator]


def _clamp(value: int, lower: int, upper: int) -> int:
    """Keep a value inside a range."""
    return max(lower, min(upper, value))


@dataclass(frozen=True)
class IdrOptions:
    """The options of a config entry, with defaults and safe limits."""

    inputs: int = DEFAULT_INPUTS
    outputs: int = DEFAULT_OUTPUTS
    groups: bool = False
    crosspoints: bool = False
    scan_interval: int = DEFAULT_SCAN_INTERVAL

    @classmethod
    def from_mapping(cls, options: Mapping[str, Any]) -> IdrOptions:
        """Build the options from the stored options of a config entry."""
        return cls(
            inputs=_clamp(
                int(options.get(CONF_INPUTS, DEFAULT_INPUTS)), 1, MAX_CHANNELS
            ),
            outputs=_clamp(
                int(options.get(CONF_OUTPUTS, DEFAULT_OUTPUTS)), 1, MAX_CHANNELS
            ),
            groups=bool(options.get(CONF_GROUPS, False)),
            crosspoints=bool(options.get(CONF_CROSSPOINTS, False)),
            scan_interval=_clamp(
                int(options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                MIN_SCAN_INTERVAL,
                MAX_SCAN_INTERVAL,
            ),
        )

    def gain_keys(self) -> list[GainKey]:
        """Return all gains that are exposed."""
        keys: list[GainKey] = [
            (GainType.INPUT, (number,)) for number in range(1, self.inputs + 1)
        ]
        keys.extend(
            (GainType.OUTPUT, (number,)) for number in range(1, self.outputs + 1)
        )
        if self.groups:
            keys.extend(
                (GainType.INPUT_GROUP, (number,))
                for number in range(1, MAX_IO_GROUPS + 1)
            )
            keys.extend(
                (GainType.OUTPUT_GROUP, (number,))
                for number in range(1, MAX_IO_GROUPS + 1)
            )
            keys.extend(
                (GainType.CROSSPOINT_GROUP, (number,))
                for number in range(1, MAX_CROSSPOINT_GROUPS + 1)
            )
        if self.crosspoints:
            keys.extend(
                (GainType.CROSSPOINT, (source, target))
                for source in range(1, self.inputs + 1)
                for target in range(1, self.outputs + 1)
            )
        return keys

    def mute_keys(self) -> list[MuteKey]:
        """Return all mute states that are exposed."""
        keys: list[MuteKey] = [
            (MuteType.INPUT, (number,)) for number in range(1, self.inputs + 1)
        ]
        keys.extend(
            (MuteType.OUTPUT, (number,)) for number in range(1, self.outputs + 1)
        )
        if self.crosspoints:
            keys.extend(
                (MuteType.CROSSPOINT, (source, target))
                for source in range(1, self.inputs + 1)
                for target in range(1, self.outputs + 1)
            )
        return keys


@dataclass(frozen=True)
class IdrData:
    """State of the iDR as read during one update."""

    unit_name: str
    preset: int
    response_time_ms: int
    gains: dict[GainKey, float]
    mutes: dict[MuteKey, bool]


def _gain_applied(requested: float, actual: float) -> bool:
    """Return True when the gain read back matches the requested gain."""
    if requested == -math.inf or actual == -math.inf:
        return requested == actual
    return abs(requested - actual) <= GAIN_TOLERANCE_DB


def _command_failed(err: Exception) -> HomeAssistantError:
    """Build the error that is shown when a command could not be sent."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="command_failed",
        translation_placeholders={"error": str(err)},
    )


def _not_applied(requested: str, actual: str) -> HomeAssistantError:
    """Build the error that is shown when the iDR did not apply a value."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="not_applied",
        translation_placeholders={"requested": requested, "actual": actual},
    )


class IdrCoordinator(DataUpdateCoordinator[IdrData]):
    """Poll the iDR over its single Telnet connection and write changes."""

    config_entry: IdrConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: IdrConfigEntry, client: IdrClient
    ) -> None:
        """Initialise the coordinator."""
        options = IdrOptions.from_mapping(entry.options)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=options.scan_interval),
        )
        self.client = client
        self.options = options
        self.gain_keys = options.gain_keys()
        self.mute_keys = options.mute_keys()
        self._unreadable: set[GainKey | MuteKey] = set()

    async def _async_update_data(self) -> IdrData:
        """Read the current state from the iDR."""
        try:
            started = time.monotonic()
            preset = await self.client.async_get_preset()
            response_time_ms = round((time.monotonic() - started) * 1000)
            unit_name = await self.client.async_get_unit_name()
            gains = await self._async_read_gains()
            mutes = await self._async_read_mutes()
        except IdrAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except IdrError as err:
            raise UpdateFailed(f"Error communicating with the iDR: {err}") from err
        return IdrData(
            unit_name=unit_name,
            preset=preset,
            response_time_ms=response_time_ms,
            gains=gains,
            mutes=mutes,
        )

    async def _async_read_gains(self) -> dict[GainKey, float]:
        """Read all exposed gains. A value that cannot be read is skipped."""
        gains: dict[GainKey, float] = {}
        for key in self.gain_keys:
            kind, indices = key
            try:
                gains[key] = await self.client.async_get_gain(kind, indices)
            except (IdrCommandError, IdrProtocolError) as err:
                self._report_unreadable(key, err)
            else:
                self._unreadable.discard(key)
        return gains

    async def _async_read_mutes(self) -> dict[MuteKey, bool]:
        """Read all exposed mute states. A value that cannot be read is skipped."""
        mutes: dict[MuteKey, bool] = {}
        for key in self.mute_keys:
            kind, indices = key
            try:
                mutes[key] = await self.client.async_get_mute(kind, indices)
            except (IdrCommandError, IdrProtocolError) as err:
                self._report_unreadable(key, err)
            else:
                self._unreadable.discard(key)
        return mutes

    def _report_unreadable(self, key: GainKey | MuteKey, err: IdrError) -> None:
        """Log a value that cannot be read, once until it can be read again."""
        if key in self._unreadable:
            return
        self._unreadable.add(key)
        kind, indices = key
        _LOGGER.warning(
            "Cannot read %s %s from the iDR: %s",
            kind,
            " ".join(str(index) for index in indices),
            err,
        )

    async def async_write_gain(self, key: GainKey, gain: float) -> None:
        """Set a gain and read it back to confirm."""
        kind, indices = key
        try:
            await self.client.async_set_gain(kind, indices, gain)
            actual = await self.client.async_get_gain(kind, indices)
        except (IdrError, ValueError) as err:
            raise _command_failed(err) from err
        self.async_set_updated_data(
            replace(self.data, gains={**self.data.gains, key: actual})
        )
        if not _gain_applied(gain, actual):
            raise _not_applied(format_gain(gain), format_gain(actual))

    async def async_write_mute(self, key: MuteKey, muted: bool) -> None:
        """Set a mute state and read it back to confirm."""
        kind, indices = key
        try:
            await self.client.async_set_mute(kind, indices, muted)
            actual = await self.client.async_get_mute(kind, indices)
        except (IdrError, ValueError) as err:
            raise _command_failed(err) from err
        self.async_set_updated_data(
            replace(self.data, mutes={**self.data.mutes, key: actual})
        )
        if actual != muted:
            raise _not_applied("On" if muted else "Off", "On" if actual else "Off")

    async def async_recall_preset(self, preset: int) -> None:
        """Recall a preset, confirm it and reload all values."""
        try:
            await self.client.async_set_preset(preset)
            actual = await self.client.async_get_preset()
        except (IdrError, ValueError) as err:
            raise _command_failed(err) from err
        if actual != preset:
            self.async_set_updated_data(replace(self.data, preset=actual))
            raise _not_applied(str(preset), str(actual))
        # A preset changes levels and routing, so read everything again.
        await self.async_refresh()
