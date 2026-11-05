"""Tests for the Avolites Titan config flow."""

from __future__ import annotations

import aiohttp
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.avolites_titan.const import DOMAIN

from .conftest import BASE, HOST, UNIQUE_ID

USER_INPUT = {"host": HOST, "port": 4430}


async def test_user_flow(hass: HomeAssistant, mock_console) -> None:
    """A reachable console creates an entry named after the device."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "D3C-00025"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == UNIQUE_ID


async def test_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An unreachable console shows an error and lets the user retry."""
    aioclient_mock.get(
        f"{BASE}/get/2/Titan/DeviceLegend", exc=aiohttp.ClientConnectionError
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_api_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Something answering with an API error is reported as unknown."""
    aioclient_mock.get(
        f"{BASE}/get/2/Titan/DeviceLegend",
        status=500,
        json={"title": "The property 'Titan.DeviceLegend' does not exist."},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=USER_INPUT
    )
    assert result["errors"] == {"base": "unknown"}


async def test_already_configured(
    hass: HomeAssistant, mock_console, config_entry
) -> None:
    """The same console can't be added twice."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
