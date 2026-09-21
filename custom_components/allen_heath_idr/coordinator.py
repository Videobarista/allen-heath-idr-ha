"""Data update coordinator for the Allen & Heath iDR integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import IdrAuthError, IdrClient, IdrError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type IdrConfigEntry = ConfigEntry[IdrCoordinator]


@dataclass(frozen=True)
class IdrData:
    """State of the iDR as read during one update."""

    unit_name: str
    preset: int
    response_time_ms: int


class IdrCoordinator(DataUpdateCoordinator[IdrData]):
    """Poll the iDR over its single Telnet connection."""

    config_entry: IdrConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: IdrConfigEntry, client: IdrClient
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> IdrData:
        """Read the current state from the iDR."""
        try:
            started = time.monotonic()
            preset = await self.client.async_get_preset()
            response_time_ms = round((time.monotonic() - started) * 1000)
            unit_name = await self.client.async_get_unit_name()
        except IdrAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except IdrError as err:
            raise UpdateFailed(f"Error communicating with the iDR: {err}") from err
        return IdrData(
            unit_name=unit_name,
            preset=preset,
            response_time_ms=response_time_ms,
        )
