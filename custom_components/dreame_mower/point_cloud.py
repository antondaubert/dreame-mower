"""Serve the mower's 3D maps (point clouds) to the 3D map card.

The card asks ``dreame_mower/point_clouds`` for the maps of its mower, then
fetches each map's cloud from an authenticated endpoint. A cloud is downloaded
once and kept on disk under its cloud file name, so it is only fetched again
when the mower stores a new one.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import ERR_HOME_ASSISTANT_ERROR, ERR_NOT_FOUND
from homeassistant.components.websocket_api.decorators import async_response, websocket_command
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView

from .const import DATA_COORDINATOR, DATA_POINT_CLOUD, DOMAIN

if TYPE_CHECKING:
    from .dreame.device import DreameMowerDevice

_LOGGER = logging.getLogger(__name__)

POINT_CLOUD_URL = "/api/dreame_mower/{entry_id}/point_cloud/{map_index}"
# How long the list of stored clouds is trusted before the mower is asked again.
NAMES_TTL_SECONDS = 600


def point_cloud_url(entry_id: str, map_index: int) -> str:
    """Return the endpoint that serves the 3D map of one map index."""
    return POINT_CLOUD_URL.format(entry_id=entry_id, map_index=map_index)


class PointCloudStore:
    """The stored point clouds of one mower, cached on disk by cloud file name."""

    def __init__(self, device: DreameMowerDevice, cache_dir: str) -> None:
        self._device = device
        self._cache_dir = cache_dir
        self._names: list[str | None] = []
        # None until the list was first read: the monotonic clock may start
        # near zero, on a machine that has just booted.
        self._names_read_at: float | None = None
        self._lock = threading.Lock()

    def names(self) -> list[str | None]:
        """Return the stored cloud file name of each map index.

        Runs in the executor: it may ask the mower.
        """
        with self._lock:
            return list(self._current_names())

    def _current_names(self) -> list[str | None]:
        if self._names_read_at is None or time.monotonic() - self._names_read_at > NAMES_TTL_SECONDS:
            self._names = self._device.read_point_cloud_names()
            self._names_read_at = time.monotonic()
        return self._names

    def get(self, map_index: int) -> tuple[bytes, str] | None:
        """Return the cloud of a map index and its file name, or None when it has none.

        Runs in the executor: it may ask the mower and download the file.
        """
        with self._lock:
            names = self._current_names()
            if not 0 <= map_index < len(names) or not (name := names[map_index]):
                return None
            path = os.path.join(self._cache_dir, f"{map_index}.pcd")
            name_path = os.path.join(self._cache_dir, f"{map_index}.name")
            try:
                with open(name_path, encoding="utf-8") as name_file:
                    cached = name_file.read() == name
                if cached:
                    with open(path, "rb") as cloud_file:
                        return cloud_file.read(), name
            except OSError:
                pass
            data = self._device.download_point_cloud(name)
            os.makedirs(self._cache_dir, exist_ok=True)
            # Each file is written whole or not at all, the cloud before the
            # name that marks it as current.
            _write_atomically(path, data)
            _write_atomically(name_path, name.encode("utf-8"))
            return data, name


def _write_atomically(path: str, data: bytes) -> None:
    """Write a file through a temporary one beside it, so a reader never sees half of it."""
    temporary = f"{path}.tmp"
    with open(temporary, "wb") as file:
        file.write(data)
    os.replace(temporary, path)


class DreameMowerPointCloudView(HomeAssistantView):
    """Serve one map's point cloud to signed-in users."""

    url = POINT_CLOUD_URL
    name = "api:dreame_mower:point_cloud"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, map_index: str) -> web.StreamResponse:
        """Return the PCD file, or 404 when the map has none."""
        hass = request.app[KEY_HASS]
        store = hass.data.get(DOMAIN, {}).get(entry_id, {}).get(DATA_POINT_CLOUD)
        if store is None or not map_index.isdigit():
            return self.json_message("Unknown mower or map", HTTPStatus.NOT_FOUND)
        try:
            result = await hass.async_add_executor_job(store.get, int(map_index))
        except Exception as ex:  # noqa: BLE001 - a cloud or file error must not crash the view
            _LOGGER.warning("Could not read the 3D map of map index %s: %s", map_index, ex)
            return self.json_message("The 3D map could not be read", HTTPStatus.BAD_GATEWAY)
        if result is None:
            return self.json_message("No 3D map is stored for this map", HTTPStatus.NOT_FOUND)
        data, name = result
        etag = '"' + hashlib.sha1(name.encode()).hexdigest() + '"'
        headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=HTTPStatus.NOT_MODIFIED, headers=headers)
        return web.Response(body=data, content_type="application/octet-stream", headers=headers)


@websocket_command(
    {vol.Required("type"): "dreame_mower/point_clouds", vol.Required("entity_id"): str}
)
@async_response
async def ws_point_clouds(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """List the maps of a mower with their 3D map endpoints, and the active map.

    Each map says whether it has a stored cloud, so the card can offer the 3D
    view without downloading anything.
    """
    registry = er.async_get(hass)
    entry = registry.async_get(msg["entity_id"])
    entry_id = entry.config_entry_id if entry is not None and entry.platform == DOMAIN else None
    data = hass.data.get(DOMAIN, {}).get(entry_id) if entry_id else None
    if entry_id is None or not data or DATA_POINT_CLOUD not in data:
        connection.send_error(msg["id"], ERR_NOT_FOUND, "Not a Dreame mower")
        return
    try:
        names = await hass.async_add_executor_job(data[DATA_POINT_CLOUD].names)
    except Exception as ex:  # noqa: BLE001 - the mower may not answer
        _LOGGER.debug("Could not list the 3D maps: %s", ex)
        connection.send_error(msg["id"], ERR_HOME_ASSISTANT_ERROR, "The 3D maps are not available right now")
        return
    device = data[DATA_COORDINATOR].device
    maps = [m for m in device.available_maps if isinstance(m.get("index"), int)]
    current = device.current_map_id
    connection.send_result(
        msg["id"],
        {
            "maps": [
                {
                    "id": m.get("id"),
                    "index": m["index"],
                    "name": m["name"],
                    "url": point_cloud_url(entry_id, m["index"]),
                    "has_cloud": m["index"] < len(names) and bool(names[m["index"]]),
                }
                for m in maps
            ],
            "active_index": next((m["index"] for m in maps if m.get("id") == current), None),
        },
    )
