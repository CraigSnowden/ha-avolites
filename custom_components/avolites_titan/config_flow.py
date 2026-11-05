"""Config flow for the Avolites Titan integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import TitanClient, TitanConnectionError, TitanError
from .const import DEFAULT_PORT, DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class TitanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Titan console."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the console's address and check it responds."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = TitanClient(
                async_get_clientsession(self.hass),
                user_input[CONF_HOST],
                user_input[CONF_PORT],
            )
            try:
                identity = await client.get_identity()
            except TitanConnectionError:
                errors["base"] = "cannot_connect"
            except TitanError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(identity.unique_id)
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(title=identity.name, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )
