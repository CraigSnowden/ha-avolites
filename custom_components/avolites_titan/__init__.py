"""The Avolites Titan integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TitanClient, TitanError
from .coordinator import TitanConfigEntry, TitanCoordinator

PLATFORMS = [Platform.LIGHT]


async def async_setup_entry(hass: HomeAssistant, entry: TitanConfigEntry) -> bool:
    """Set up a Titan console from a config entry."""
    client = TitanClient(
        async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT]
    )
    try:
        identity = await client.get_identity()
    except TitanError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = TitanCoordinator(hass, entry, client, identity)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TitanConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
