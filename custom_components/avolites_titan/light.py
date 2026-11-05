"""Titan playbacks exposed as dimmable lights.

Turning a light on fires the playback, brightness sets its level and turning
it off releases it. State and level are polled, so changes made on the desk
show up too.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Playback, TitanError
from .const import DOMAIN
from .coordinator import TitanConfigEntry, TitanCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TitanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a light for each playback, including ones added to the console later."""
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def _add_new_playbacks() -> None:
        new = [tid for tid in coordinator.data if tid not in known]
        known.update(new)
        if new:
            async_add_entities(PlaybackLight(coordinator, tid) for tid in new)

    _add_new_playbacks()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_playbacks))


class PlaybackLight(CoordinatorEntity[TitanCoordinator], LightEntity, RestoreEntity):
    """A Titan playback."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, coordinator: TitanCoordinator, titan_id: int) -> None:
        super().__init__(coordinator)
        self._titan_id = titan_id
        # Level to fire at when turned on without a brightness.
        self._last_brightness = 255
        identity = coordinator.identity
        self._attr_unique_id = f"{identity.unique_id}_playback_{titan_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity.unique_id)},
            manufacturer="Avolites",
            model=identity.model,
            name=identity.name,
            configuration_url=f"{coordinator.client.base_url}/handles",
        )

    @property
    def _playback(self) -> Playback | None:
        return self.coordinator.data.get(self._titan_id)

    @property
    def available(self) -> bool:
        return super().available and self._playback is not None

    @property
    def name(self) -> str | None:
        playback = self._playback
        return playback.name if playback else None

    @property
    def is_on(self) -> bool | None:
        playback = self._playback
        return playback.active if playback else None

    @property
    def brightness(self) -> int | None:
        playback = self._playback
        if playback is None or not playback.active:
            return None
        return max(1, round(playback.level * 255))

    @callback
    def _handle_coordinator_update(self) -> None:
        if brightness := self.brightness:
            self._last_brightness = brightness
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        playback = self._playback
        if playback is None:
            return None
        return {
            "titan_id": playback.titan_id,
            "user_number": playback.user_number,
            "handle_group": playback.group,
            "handle_page": playback.page + 1,
            "handle_index": playback.index + 1,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and (
            brightness := last.attributes.get(ATTR_BRIGHTNESS)
        ):
            self._last_brightness = brightness
        if brightness := self.brightness:
            self._last_brightness = brightness

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._last_brightness)
        level = brightness / 255
        client = self.coordinator.client
        try:
            if self.is_on:
                await client.set_playback_level(self._titan_id, level)
            else:
                await client.fire_playback(self._titan_id, level)
        except TitanError as err:
            raise HomeAssistantError(f"Could not fire {self.name}: {err}") from err
        self._last_brightness = brightness
        self._set_state(True, level)

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.release_playback(
                self._titan_id, kwargs.get(ATTR_TRANSITION)
            )
        except TitanError as err:
            raise HomeAssistantError(f"Could not release {self.name}: {err}") from err
        self._set_state(False, 0.0)

    def _set_state(self, active: bool, level: float) -> None:
        # Reflect the change straight away; the next poll confirms it.
        if playback := self._playback:
            playback.active = active
            playback.level = level
        self.async_write_ha_state()
