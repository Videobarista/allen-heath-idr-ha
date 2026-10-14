"""The Allen & Heath iDR integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.loader import async_get_integration

from .client import IdrClient
from .const import DEFAULT_PORT, DOMAIN
from .coordinator import IdrCoordinator
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]

type IdrConfigEntry = ConfigEntry[IdrCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Allen & Heath iDR integration (registers services once)."""
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: IdrConfigEntry) -> bool:
    """Set up an iDR config entry.

    Setup never waits on the device being reachable: the iDR is commonly
    switched off at the wall when Home Assistant starts, so this does a
    best-effort first poll and then always finishes setting up the config
    entry regardless of the result. The coordinator keeps polling and
    retrying on its normal schedule in the background; entities report
    themselves unavailable until the first successful poll lands.
    """
    integration = await async_get_integration(hass, DOMAIN)
    client = IdrClient(
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        entry.data.get(CONF_PASSWORD),
    )

    coordinator = IdrCoordinator(
        hass, entry, client, str(integration.version) if integration.version else "unknown"
    )
    await coordinator.async_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IdrConfigEntry) -> bool:
    """Unload an iDR config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_close()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: IdrConfigEntry) -> None:
    """Reload an iDR config entry after its options changed."""
    await hass.config_entries.async_reload(entry.entry_id)
