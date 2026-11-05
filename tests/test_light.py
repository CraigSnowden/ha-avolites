"""Tests for Titan playback lights."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    DOMAIN as LIGHT_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .conftest import BASE

PANEL = "light.d3c_00025_panel_intensity"
FLAGPOLE = "light.d3c_00025_flagpole_intensity"


async def _setup(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


def _script_calls(aioclient_mock: AiohttpClientMocker) -> list[tuple[str, dict]]:
    """Return the commands sent, leaving out level reads."""
    return [
        (url.path.rsplit("/", 1)[-1], dict(url.query))
        for _, url, _, _ in aioclient_mock.mock_calls
        if "/script/" in url.path and "level_levelDelta" not in url.query
    ]


async def _poll(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    # Scheduled refreshes run as background tasks.
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_playbacks_become_lights(
    hass: HomeAssistant, mock_console, config_entry
) -> None:
    """Only playback handles get lights, with state from the console."""
    await _setup(hass, config_entry)

    assert hass.states.get(PANEL).state == STATE_OFF
    flagpole = hass.states.get(FLAGPOLE)
    assert flagpole.state == STATE_ON
    assert flagpole.attributes[ATTR_BRIGHTNESS] == 128
    assert flagpole.attributes["titan_id"] == 2008
    assert flagpole.attributes["handle_index"] == 2
    assert len(hass.states.async_entity_ids(LIGHT_DOMAIN)) == 2


async def test_turn_on_fires_playback(
    hass: HomeAssistant, mock_console, config_entry, aioclient_mock
) -> None:
    """Turning on an inactive playback fires it at the requested level."""
    await _setup(hass, config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: PANEL, ATTR_BRIGHTNESS: 51},
        blocking=True,
    )

    assert _script_calls(aioclient_mock) == [
        (
            "FirePlaybackAtLevel",
            {"handle_titanId": "1994", "level_level": "0.2", "alwaysRefire": "false"},
        )
    ]
    state = hass.states.get(PANEL)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 51


async def test_turn_on_uses_last_level(
    hass: HomeAssistant, mock_console, config_entry, aioclient_mock
) -> None:
    """Turning on without a brightness fires at the level it was last seen at."""
    await _setup(hass, config_entry)
    for service in (SERVICE_TURN_OFF, SERVICE_TURN_ON):
        await hass.services.async_call(
            LIGHT_DOMAIN, service, {ATTR_ENTITY_ID: FLAGPOLE}, blocking=True
        )

    name, params = _script_calls(aioclient_mock)[-1]
    assert name == "FirePlaybackAtLevel"
    assert float(params["level_level"]) == pytest.approx(128 / 255)


async def test_dimming_active_playback_sets_level(
    hass: HomeAssistant, mock_console, config_entry, aioclient_mock
) -> None:
    """Changing brightness of an active playback moves its level, not re-fires."""
    await _setup(hass, config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: FLAGPOLE, ATTR_BRIGHTNESS: 255},
        blocking=True,
    )

    assert _script_calls(aioclient_mock) == [
        ("SetPlaybackLevel", {"srcHandle_titanId": "2008", "level_level": "1.0"})
    ]


@pytest.mark.parametrize(
    ("service_data", "expected"),
    [
        ({}, {"fadeTime": "0", "useMasterReleaseTime": "false"}),
        ({ATTR_TRANSITION: 3}, {"fadeTime": "3.0", "useMasterReleaseTime": "true"}),
    ],
)
async def test_turn_off_releases_playback(
    hass: HomeAssistant,
    mock_console,
    config_entry,
    aioclient_mock,
    service_data,
    expected,
) -> None:
    """Turning off releases, with an optional fade from the transition."""
    await _setup(hass, config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: FLAGPOLE, **service_data},
        blocking=True,
    )

    assert _script_calls(aioclient_mock) == [
        ("ReleasePlayback", {"handle_titanId": "2008", **expected})
    ]
    assert hass.states.get(FLAGPOLE).state == STATE_OFF


async def test_command_error_raises(
    hass: HomeAssistant, mock_console, config_entry, aioclient_mock
) -> None:
    """A rejected command surfaces as a Home Assistant error."""
    await _setup(hass, config_entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/script/2/Playbacks/FirePlaybackAtLevel",
        status=500,
        json={"title": "Error: something went wrong"},
    )

    with pytest.raises(HomeAssistantError, match="something went wrong"):
        await hass.services.async_call(
            LIGHT_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: PANEL}, blocking=True
        )


async def test_state_follows_console(
    hass: HomeAssistant, mock_console, config_entry, handles, aioclient_mock
) -> None:
    """Polling picks up changes, new playbacks, removed ones and outages."""
    await _setup(hass, config_entry)

    handles[0]["active"] = True
    handles.append(
        {
            "userNumber": "3",
            "legend": "",
            "active": False,
            "Links": [f"{BASE}/playback/2100"],
            "titanId": 2100,
            "handleLocation": {"group": "RollerA", "page": 0, "index": 2},
        }
    )
    mock_console(handles, level=0.25)
    await _poll(hass)
    panel = hass.states.get(PANEL)
    assert panel.state == STATE_ON
    assert panel.attributes[ATTR_BRIGHTNESS] == 64
    assert hass.states.get("light.d3c_00025_playback_3").state == STATE_OFF

    mock_console([h for h in handles if h["titanId"] != 2008])
    await _poll(hass)
    assert hass.states.get(FLAGPOLE).state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/handles", exc=aiohttp.ClientConnectionError)
    await _poll(hass)
    assert hass.states.get(PANEL).state == STATE_UNAVAILABLE


async def test_unload(hass: HomeAssistant, mock_console, config_entry) -> None:
    """The entry unloads cleanly."""
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_offline(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """Setup is retried while the console is unreachable."""
    aioclient_mock.get(
        f"{BASE}/get/2/Titan/DeviceLegend", exc=aiohttp.ClientConnectionError
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
