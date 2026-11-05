"""Async client for the Avolites Titan WebAPI.

The WebAPI is plain HTTP on port 4430 with no authentication. Read calls use
`/titan/get/2/<Provider>/<Property>`, actions use
`/titan/script/2/<Provider>/<Method>?<params>`, and `/titan/handles` lists
everything on the console's handle pages.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import aiohttp

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


class TitanError(Exception):
    """Base error for the Titan client."""


class TitanConnectionError(TitanError):
    """The console could not be reached."""


class TitanApiError(TitanError):
    """The console rejected a request."""


@dataclass(slots=True)
class TitanIdentity:
    """Identifying details of a console."""

    unique_id: str
    name: str
    model: str | None
    show_name: str | None


@dataclass(slots=True)
class Playback:
    """A playback on one of the console's handle pages."""

    titan_id: int
    user_number: str
    legend: str
    active: bool
    group: str
    page: int
    index: int
    level: float = 0.0

    @property
    def name(self) -> str:
        """Return the legend, or a fallback when the handle has none."""
        return self.legend or f"Playback {self.user_number}"


class TitanClient:
    """Talks to a single Titan console."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self._session = session
        self.base_url = f"http://{host}:{port}/titan"
        self.host = host

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path}"
        try:
            async with self._session.get(
                url, params=params, timeout=REQUEST_TIMEOUT
            ) as resp:
                body = await resp.text()
                if resp.status >= 400:
                    raise TitanApiError(_error_title(body) or f"HTTP {resp.status}")
        except (TimeoutError, aiohttp.ClientError) as err:
            raise TitanConnectionError(f"Error talking to {url}: {err}") from err
        if not body.strip():
            return None
        try:
            return json.loads(body)
        except ValueError:
            return body

    async def get(self, provider: str, prop: str) -> Any:
        """Read a property."""
        return await self._request(f"get/2/{provider}/{prop}")

    async def script(self, provider: str, method: str, **params: Any) -> Any:
        """Run a script method."""
        return await self._request(
            f"script/2/{provider}/{method}",
            {k: _format_param(v) for k, v in params.items()},
        )

    async def get_identity(self) -> TitanIdentity:
        """Return details used to identify the console in Home Assistant."""
        legend = await self.get("Titan", "DeviceLegend")
        info = await self.get("Titan", "DeviceInfo") or {}
        clients = info.get("Clients") or []
        # DeviceInfo lists every session member; prefer the one we're talking to.
        client = next(
            (c for c in clients if c.get("Legend") == legend),
            clients[0] if clients else {},
        )
        hardware = client.get("HardwareIdentifier") or ""
        return TitanIdentity(
            unique_id=client.get("Id") or self.host,
            name=legend or self.host,
            model=hardware.split(";")[0] or None,
            show_name=info.get("ShowName"),
        )

    async def get_playbacks(self) -> dict[int, Playback]:
        """Return all playbacks on the console's handle pages, keyed by titan ID."""
        handles = await self._request("handles") or []
        playbacks: dict[int, Playback] = {}
        for handle in handles:
            if not any(
                "/titan/playback/" in link for link in handle.get("Links") or []
            ):
                continue
            location = handle.get("handleLocation") or {}
            playback = Playback(
                titan_id=handle["titanId"],
                user_number=str(handle.get("userNumber") or ""),
                legend=handle.get("legend") or "",
                active=bool(handle.get("active")),
                group=location.get("group", ""),
                page=location.get("page", 0),
                index=location.get("index", 0),
            )
            playbacks[playback.titan_id] = playback
        return playbacks

    async def get_playback_level(self, titan_id: int) -> float:
        """Return a playback's level between 0 and 1.

        There is no getter for this, but SetPlaybackLevel returns the resulting
        level, so nudging it by zero reads the level without changing it. The
        parameter must be spelt `level_levelDelta`; the `level_leveldelta` shown
        in the API reference is rejected.
        """
        level = await self.script(
            "Playbacks",
            "SetPlaybackLevel",
            srcHandle_titanId=titan_id,
            level_levelDelta=0,
        )
        return min(max(float(level or 0), 0.0), 1.0)

    async def fire_playback(self, titan_id: int, level: float) -> None:
        """Fire a playback at a level between 0 and 1."""
        await self.script(
            "Playbacks",
            "FirePlaybackAtLevel",
            handle_titanId=titan_id,
            level_level=level,
            alwaysRefire=False,
        )

    async def set_playback_level(self, titan_id: int, level: float) -> None:
        """Move a playback's fader to a level between 0 and 1."""
        await self.script(
            "Playbacks",
            "SetPlaybackLevel",
            srcHandle_titanId=titan_id,
            level_level=level,
        )

    async def release_playback(self, titan_id: int, fade: float | None = None) -> None:
        """Release a playback, using its own release time unless a fade is given."""
        await self.script(
            "Playbacks",
            "ReleasePlayback",
            handle_titanId=titan_id,
            fadeTime=fade or 0,
            useMasterReleaseTime=fade is not None,
        )


def _format_param(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _error_title(body: str) -> str | None:
    try:
        return json.loads(body).get("title")
    except (ValueError, AttributeError):
        return None
