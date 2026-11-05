"""Polling coordinator for the Avolites Titan integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Playback, TitanClient, TitanError, TitanIdentity
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type TitanConfigEntry = ConfigEntry[TitanCoordinator]


class TitanCoordinator(DataUpdateCoordinator[dict[int, Playback]]):
    """Polls the console's handles for playback state."""

    config_entry: TitanConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TitanConfigEntry,
        client: TitanClient,
        identity: TitanIdentity,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.identity = identity

    async def _async_update_data(self) -> dict[int, Playback]:
        try:
            playbacks = await self.client.get_playbacks()
            # Released playbacks are always at zero, so only ask about active ones.
            active = [p for p in playbacks.values() if p.active]
            levels = await asyncio.gather(
                *(self.client.get_playback_level(p.titan_id) for p in active)
            )
        except TitanError as err:
            raise UpdateFailed(str(err)) from err
        for playback, level in zip(active, levels, strict=True):
            playback.level = level
        return playbacks
