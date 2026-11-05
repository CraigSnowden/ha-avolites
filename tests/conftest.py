"""Fixtures for Avolites Titan tests."""

from __future__ import annotations

import copy

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.avolites_titan.const import DOMAIN

HOST = "10.0.0.220"
BASE = f"http://{HOST}:4430/titan"
UNIQUE_ID = "4D56:150493F9"

DEVICE_INFO = {
    "ShowName": "Teviot Building",
    "Clients": [
        {
            "Id": UNIQUE_ID,
            "Legend": "D3C-00025",
            "HardwareIdentifier": "D3 Core;Diamond3;Titan Server;Titan Console",
        }
    ],
}


def _handle(titan_id, user_number, legend, index, active=False, kind="playback"):
    return {
        "userNumber": user_number,
        "legend": legend,
        "active": active,
        "Links": [f"{BASE}/{kind}/{titan_id}"],
        "titanId": titan_id,
        "handleLocation": {"group": "RollerA", "page": 0, "index": index},
        "type": "cueHandle" if kind == "playback" else "groupHandle",
    }


HANDLES = [
    _handle(1994, "1", "Panel Intensity", 0),
    _handle(2008, "2", "Flagpole Intensity", 1, active=True),
    _handle(1896, "1", "All COLORado Panel Q40", 0, kind="group"),
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom integrations in all tests."""
    return


@pytest.fixture
def handles() -> list[dict]:
    """Return a mutable copy of the console's handles."""
    return copy.deepcopy(HANDLES)


@pytest.fixture
def mock_console(aioclient_mock: AiohttpClientMocker, handles: list[dict]):
    """Mock a reachable console."""

    def register(current: list[dict] | None = None, level: float = 0.5) -> None:
        aioclient_mock.clear_requests()
        aioclient_mock.get(f"{BASE}/get/2/Titan/DeviceLegend", json="D3C-00025")
        aioclient_mock.get(f"{BASE}/get/2/Titan/DeviceInfo", json=DEVICE_INFO)
        aioclient_mock.get(f"{BASE}/handles", json=current or handles)
        # Level reads; registered first so they win over the generic mock below.
        aioclient_mock.get(
            f"{BASE}/script/2/Playbacks/SetPlaybackLevel?level_levelDelta=0",
            json=level,
        )
        for method in ("FirePlaybackAtLevel", "SetPlaybackLevel", "ReleasePlayback"):
            aioclient_mock.get(f"{BASE}/script/2/Playbacks/{method}", text="")

    register()
    return register


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry for the mocked console."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="D3C-00025",
        unique_id=UNIQUE_ID,
        data={"host": HOST, "port": 4430},
    )
