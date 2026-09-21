"""The Allen & Heath iDR integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .client import IdrClient
from .coordinator import IdrConfigEntry, IdrCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: IdrConfigEntry) -> bool:
    """Set up an Allen & Heath iDR from a config entry."""
    client = IdrClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_PASSWORD),
    )
    coordinator = IdrCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except (ConfigEntryNotReady, ConfigEntryAuthFailed):
        await client.async_close()
        raise

    entry.async_on_unload(client.async_close)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IdrConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
