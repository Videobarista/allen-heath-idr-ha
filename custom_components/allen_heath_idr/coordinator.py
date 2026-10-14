"""Data update coordinator for the Allen & Heath iDR integration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
import logging
import math
import time
from typing import Any, NamedTuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    GainType,
    IdrAuthError,
    IdrClient,
    IdrConnectionError,
    IdrError,
    MuteType,
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
    MAX_CHANNELS,
    MAX_SCAN_INTERVAL,
    MIN_CHANNELS,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

#: Input/output group numbers the protocol supports (fixed, not user-configurable).
GROUP_COUNT = 8

#: Allowed drift between a value we just wrote and the one read back to confirm it.
#: The iDR can ramp a gain change over a short time rather than jump instantly, so
#: an immediate read-back is not always bit-for-bit identical to what was sent.
GAIN_TOLERANCE_DB = 3.0

#: How many times to retry connecting within a single poll before giving up. This
#: smooths over brief network hiccups so a single dropped packet doesn't flip every
#: entity to unavailable. Module-level so tests can shrink them.
CONNECT_RETRY_ATTEMPTS = 3
CONNECT_RETRY_DELAY = 1.5


class GainKey(NamedTuple):
    """Identifies a single gain reading/control."""

    gain_type: GainType
    channels: tuple[int, ...]

    @property
    def unique_suffix(self) -> str:
        """Return a stable suffix for unique_id / translation placeholders."""
        parts = "_".join(str(channel) for channel in self.channels)
        return f"{self.gain_type.value.lower()}_{parts}"


class MuteKey(NamedTuple):
    """Identifies a single mute reading/control."""

    mute_type: MuteType
    channels: tuple[int, ...]

    @property
    def unique_suffix(self) -> str:
        """Return a stable suffix for unique_id / translation placeholders."""
        parts = "_".join(str(channel) for channel in self.channels)
        return f"{self.mute_type.value.lower()}_{parts}"


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class IdrOptions:
    """Resolved, clamped configuration options for a config entry."""

    inputs: int = DEFAULT_INPUTS
    outputs: int = DEFAULT_OUTPUTS
    groups: bool = False
    crosspoints: bool = False
    scan_interval: int = DEFAULT_SCAN_INTERVAL

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> IdrOptions:
        """Build options from a merged config/options entry mapping, clamping values."""
        inputs = _clamp(int(data.get(CONF_INPUTS, DEFAULT_INPUTS)), MIN_CHANNELS, MAX_CHANNELS)
        outputs = _clamp(int(data.get(CONF_OUTPUTS, DEFAULT_OUTPUTS)), MIN_CHANNELS, MAX_CHANNELS)
        scan_interval = _clamp(
            int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            MIN_SCAN_INTERVAL,
            MAX_SCAN_INTERVAL,
        )
        return cls(
            inputs=inputs,
            outputs=outputs,
            groups=bool(data.get(CONF_GROUPS, False)),
            crosspoints=bool(data.get(CONF_CROSSPOINTS, False)),
            scan_interval=scan_interval,
        )

    def gain_keys(self) -> list[GainKey]:
        """Return every gain reading this configuration should poll/expose."""
        keys = [GainKey(GainType.INPUT, (ch,)) for ch in range(1, self.inputs + 1)]
        keys += [GainKey(GainType.OUTPUT, (ch,)) for ch in range(1, self.outputs + 1)]
        if self.groups:
            keys += [GainKey(GainType.INPUT_GROUP, (g,)) for g in range(1, GROUP_COUNT + 1)]
            keys += [GainKey(GainType.OUTPUT_GROUP, (g,)) for g in range(1, GROUP_COUNT + 1)]
        if self.crosspoints:
            keys += [
                GainKey(GainType.CROSSPOINT, (ip, op))
                for ip in range(1, self.inputs + 1)
                for op in range(1, self.outputs + 1)
            ]
        return keys

    def mute_keys(self) -> list[MuteKey]:
        """Return every mute reading this configuration should poll/expose."""
        keys = [MuteKey(MuteType.INPUT, (ch,)) for ch in range(1, self.inputs + 1)]
        keys += [MuteKey(MuteType.OUTPUT, (ch,)) for ch in range(1, self.outputs + 1)]
        if self.crosspoints:
            keys += [
                MuteKey(MuteType.CROSSPOINT, (ip, op))
                for ip in range(1, self.inputs + 1)
                for op in range(1, self.outputs + 1)
            ]
        return keys


@dataclass
class IdrData:
    """A single poll's worth of data from the iDR."""

    unit_name: str
    preset: int | None
    response_time_ms: float
    integration_version: str
    gains: dict[GainKey, float] = field(default_factory=dict)
    mutes: dict[MuteKey, bool] = field(default_factory=dict)


def _gain_matches(confirmed: float, requested: float) -> bool:
    if math.isinf(confirmed) or math.isinf(requested):
        return confirmed == requested
    return abs(confirmed - requested) <= GAIN_TOLERANCE_DB


class IdrCoordinator(DataUpdateCoordinator[IdrData]):
    """Polls an iDR unit on a fixed interval and serves cached data to entities.

    Setup never blocks on the device being reachable: a config entry is set up
    successfully even if the iDR is switched off at the time, and polling just
    keeps retrying in the background on its normal schedule. ``data`` stays
    ``None`` until the first successful poll, and entities are expected to
    report themselves unavailable while that is the case (see ``entity.py``).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: IdrClient,
        integration_version: str,
    ) -> None:
        self.client = client
        self.options = IdrOptions.from_mapping({**entry.data, **entry.options})
        self._integration_version = integration_version
        self._unreadable: set[str] = set()
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{entry.title} coordinator",
            update_interval=timedelta(seconds=self.options.scan_interval),
        )

    async def _async_update_data(self) -> IdrData:
        try:
            return await self._async_fetch_with_retry()
        except IdrAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except IdrConnectionError as err:
            raise UpdateFailed(
                f"Could not reach the iDR at {self.client.host}:{self.client.port}. "
                "Check that it is switched on and connected to the network."
            ) from err
        except IdrError as err:
            raise UpdateFailed(f"The iDR reported a problem: {err}") from err

    async def _async_fetch_with_retry(self) -> IdrData:
        """Fetch a full poll, retrying a few times on a connection failure."""
        for attempt in range(1, CONNECT_RETRY_ATTEMPTS + 1):
            try:
                return await self._async_fetch()
            except IdrConnectionError as err:
                if attempt == CONNECT_RETRY_ATTEMPTS:
                    raise
                _LOGGER.debug(
                    "Poll attempt %s/%s failed, retrying in %.1fs: %s",
                    attempt,
                    CONNECT_RETRY_ATTEMPTS,
                    CONNECT_RETRY_DELAY,
                    err,
                )
                await asyncio.sleep(CONNECT_RETRY_DELAY)
        # Unreachable: the final attempt above always returns or raises.
        raise IdrConnectionError(f"Cannot reach {self.client.host}:{self.client.port}")

    async def _async_fetch(self) -> IdrData:
        start = time.monotonic()

        try:
            preset: int | None = await self.client.async_get_preset()
        except IdrConnectionError:
            raise
        except IdrError as err:
            self._report_unreadable("preset", err)
            preset = None

        try:
            unit_name = await self.client.async_get_unit_name()
        except IdrConnectionError:
            raise
        except IdrError as err:
            self._report_unreadable("unit name", err)
            unit_name = self.config_entry.title

        gains: dict[GainKey, float] = {}
        for key in self.options.gain_keys():
            try:
                gains[key] = await self.client.async_get_gain(key.gain_type, *key.channels)
            except IdrConnectionError:
                raise
            except IdrError as err:
                self._report_unreadable(key.unique_suffix, err)

        mutes: dict[MuteKey, bool] = {}
        for key in self.options.mute_keys():
            try:
                mutes[key] = await self.client.async_get_mute(key.mute_type, *key.channels)
            except IdrConnectionError:
                raise
            except IdrError as err:
                self._report_unreadable(key.unique_suffix, err)

        response_time_ms = (time.monotonic() - start) * 1000

        return IdrData(
            unit_name=unit_name,
            preset=preset,
            response_time_ms=response_time_ms,
            integration_version=self._integration_version,
            gains=gains,
            mutes=mutes,
        )

    def _report_unreadable(self, label: str, err: IdrError) -> None:
        if label not in self._unreadable:
            self._unreadable.add(label)
            _LOGGER.warning("Could not read %s from the iDR: %s", label, err)
        else:
            _LOGGER.debug("Could not read %s from the iDR: %s", label, err)

    async def async_write_gain(self, key: GainKey, value: float) -> None:
        """Write a gain and confirm it took effect, raising a translated error otherwise."""
        try:
            await self.client.async_set_gain(key.gain_type, *key.channels, gain=value)
            confirmed = await self.client.async_get_gain(key.gain_type, *key.channels)
        except IdrError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        if not _gain_matches(confirmed, value):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_applied",
                translation_placeholders={
                    "requested": f"{value:.1f}",
                    "actual": f"{confirmed:.1f}",
                },
            )

        if self.data is not None:
            self.data.gains[key] = confirmed
            self.async_set_updated_data(self.data)

    async def async_write_mute(self, key: MuteKey, value: bool) -> None:
        """Write a mute state and confirm it took effect."""
        try:
            await self.client.async_set_mute(key.mute_type, *key.channels, mute=value)
            confirmed = await self.client.async_get_mute(key.mute_type, *key.channels)
        except IdrError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        if confirmed != value:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_applied",
                translation_placeholders={
                    "requested": "on" if value else "off",
                    "actual": "on" if confirmed else "off",
                },
            )

        if self.data is not None:
            self.data.mutes[key] = confirmed
            self.async_set_updated_data(self.data)

    async def async_recall_preset(self, preset: int) -> None:
        """Recall a preset and re-poll, since it can change many gains/mutes at once."""
        try:
            await self.client.async_set_preset(preset)
        except IdrError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.async_request_refresh()
