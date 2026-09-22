"""The Allen & Heath iDR integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .client import IdrClient
from .const import DOMAIN
from .coordinator import IdrConfigEntry, IdrCoordinator
from .services import async_register_services

PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]

# This integration is set up through the UI only; there is nothing to
# configure via configuration.yaml.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the services of this integration (once, regardless of how many
    iDR units are configured)."""
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: IdrConfigEntry) -> bool:
    """Set up an Allen & Heath iDR from a config entry."""
    integration = await async_get_integration(hass, DOMAIN)
    client = IdrClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_PASSWORD),
    )
    coordinator = IdrCoordinator(
        hass, entry, client, str(integration.version or "unknown")
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except (ConfigEntryNotReady, ConfigEntryAuthFailed):
        await client.async_close()
        raise

    entry.async_on_unload(client.async_close)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IdrConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: IdrConfigEntry) -> None:
    """Reload the entry when the options have changed."""
    await hass.config_entries.async_reload(entry.entry_id)
