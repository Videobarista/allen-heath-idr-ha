"""Config flow for the Allen & Heath iDR integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import (
    MAX_CHANNELS,
    IdrAuthError,
    IdrClient,
    IdrConnectionError,
    IdrError,
    IdrIdentity,
)
from .const import (
    CONF_CROSSPOINTS,
    CONF_GROUPS,
    CONF_INPUTS,
    CONF_OUTPUTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import IdrOptions

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)

REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


async def _async_validate(host: str, port: int, password: str | None) -> IdrIdentity:
    """Connect to the iDR and read its identity."""
    client = IdrClient(host, port, password)
    try:
        return await client.async_get_identity()
    finally:
        await client.async_close()


def _error_key(err: IdrError) -> str:
    """Translate a client error into a form error key."""
    if isinstance(err, IdrAuthError):
        return "invalid_auth"
    if isinstance(err, IdrConnectionError):
        return "cannot_connect"
    return "invalid_response"


class IdrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for an Allen & Heath iDR."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return IdrOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the connection details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            password = user_input.get(CONF_PASSWORD) or None
            self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})
            try:
                identity = await _async_validate(host, port, password)
            except IdrError as err:
                _LOGGER.debug("Could not set up %s:%s: %r", host, port, err)
                errors["base"] = _error_key(err)
            else:
                data: dict[str, Any] = {CONF_HOST: host, CONF_PORT: port}
                if password:
                    data[CONF_PASSWORD] = password
                return self.async_create_entry(
                    title=identity.unit_name or host, data=data
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start the flow when the stored password no longer works."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            try:
                await _async_validate(
                    entry.data[CONF_HOST], entry.data[CONF_PORT], password
                )
            except IdrError as err:
                _LOGGER.debug("Reauthentication failed: %r", err)
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: password}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address, port or password of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            password = user_input.get(CONF_PASSWORD) or None
            duplicate = any(
                other.entry_id != entry.entry_id
                and other.data[CONF_HOST] == host
                and other.data[CONF_PORT] == port
                for other in self._async_current_entries()
            )
            if duplicate:
                errors["base"] = "already_configured"
            else:
                try:
                    await _async_validate(host, port, password)
                except IdrError as err:
                    _LOGGER.debug("Could not reconfigure %s:%s: %r", host, port, err)
                    errors["base"] = _error_key(err)
                else:
                    data: dict[str, Any] = {CONF_HOST: host, CONF_PORT: port}
                    if password:
                        data[CONF_PASSWORD] = password
                    return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )


class IdrOptionsFlow(OptionsFlow):
    """Handle the options of an Allen & Heath iDR."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which channels and controls to expose."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_INPUTS: int(user_input[CONF_INPUTS]),
                    CONF_OUTPUTS: int(user_input[CONF_OUTPUTS]),
                    CONF_GROUPS: bool(user_input[CONF_GROUPS]),
                    CONF_CROSSPOINTS: bool(user_input[CONF_CROSSPOINTS]),
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                }
            )
        current = IdrOptions.from_mapping(self.config_entry.options)
        channels = NumberSelector(
            NumberSelectorConfig(
                min=1, max=MAX_CHANNELS, step=1, mode=NumberSelectorMode.BOX
            )
        )
        interval = NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="s",
            )
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_INPUTS, default=current.inputs): channels,
                vol.Required(CONF_OUTPUTS, default=current.outputs): channels,
                vol.Required(CONF_GROUPS, default=current.groups): BooleanSelector(),
                vol.Required(
                    CONF_CROSSPOINTS, default=current.crosspoints
                ): BooleanSelector(),
                vol.Required(CONF_SCAN_INTERVAL, default=current.scan_interval): (
                    interval
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
