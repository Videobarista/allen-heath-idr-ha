"""Config flow for the Allen & Heath iDR integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
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

from .client import IdrAuthError, IdrClient, IdrConnectionError, IdrError, IdrIdentity
from .const import (
    CONF_CROSSPOINTS,
    CONF_GROUPS,
    CONF_INPUTS,
    CONF_OUTPUTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_INPUTS,
    DEFAULT_OUTPUTS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_CHANNELS,
    MAX_SCAN_INTERVAL,
    MIN_CHANNELS,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)

REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


async def _async_validate(host: str, port: int, password: str | None) -> IdrIdentity:
    """Connect to an iDR and return its identity, letting IdrError propagate."""
    client = IdrClient(host, port, password)
    try:
        return await client.async_get_identity()
    finally:
        await client.async_close()


def _error_key(err: IdrError) -> str:
    """Map a client error to a config flow error/abort key."""
    if isinstance(err, IdrAuthError):
        return "invalid_auth"
    if isinstance(err, IdrConnectionError):
        return "cannot_connect"
    return "invalid_response"


class IdrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Allen & Heath iDR integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            password = user_input.get(CONF_PASSWORD)

            self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})

            try:
                identity = await _async_validate(host, port, password)
            except IdrError as err:
                errors["base"] = _error_key(err)
            else:
                return self.async_create_entry(
                    title=identity.unit_name or host,
                    data={CONF_HOST: host, CONF_PORT: port, CONF_PASSWORD: password},
                )

        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle a reauth flow triggered by a rejected password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password and verify it before updating the entry."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            host = reauth_entry.data[CONF_HOST]
            port = reauth_entry.data.get(CONF_PORT, DEFAULT_PORT)
            password = user_input[CONF_PASSWORD]
            try:
                await _async_validate(host, port, password)
            except IdrError as err:
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry, data={**reauth_entry.data, CONF_PASSWORD: password}
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing the host, port or password of an existing entry."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            password = user_input.get(CONF_PASSWORD)
            try:
                identity = await _async_validate(host, port, password)
            except IdrError as err:
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    title=identity.unit_name or host,
                    data={CONF_HOST: host, CONF_PORT: port, CONF_PASSWORD: password},
                    reason="reconfigure_successful",
                )

        suggested = {**reconfigure_entry.data}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, suggested),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IdrOptionsFlow:
        """Return the options flow for this integration."""
        return IdrOptionsFlow()


class IdrOptionsFlow(OptionsFlow):
    """Handle options: channel counts, groups/crosspoints, and the poll interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INPUTS, default=current.get(CONF_INPUTS, DEFAULT_INPUTS)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_CHANNELS, max=MAX_CHANNELS, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_OUTPUTS, default=current.get(CONF_OUTPUTS, DEFAULT_OUTPUTS)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_CHANNELS, max=MAX_CHANNELS, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_GROUPS, default=current.get(CONF_GROUPS, False)
                ): BooleanSelector(),
                vol.Optional(
                    CONF_CROSSPOINTS, default=current.get(CONF_CROSSPOINTS, False)
                ): BooleanSelector(),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, mode=NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
