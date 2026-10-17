"""Map feed for the map card.

A card subscribes to one mower and receives three kinds of event on the same
subscription:

- `geometry`: the active map's zones, no-go areas, paths, spot areas and
  maintenance points, sent when the map changed;
- `path`: the trail of the running (or last) session, sent in full first and
  then as what changed since the last one: the card keeps the first `keep`
  points it has and adds `points` after them;
- `status`: the mower, the station, the maps and the mower's state, sent
  whenever any of it changed.

Coordinates are map units with y up, the units of the vector map.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import time
from typing import Any

import voluptuous as vol

from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import ERR_HOME_ASSISTANT_ERROR, ERR_NOT_FOUND
from homeassistant.components.websocket_api.decorators import async_response, websocket_command
from homeassistant.components.websocket_api.messages import event_message
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import CONF_MAP_ROTATION, DATA_COORDINATOR, DEFAULT_MAP_ROTATION, DOMAIN
from .coordinator import DreameMowerCoordinator, zone_settings
from .dreame.const import DEVICE_SETTINGS_DO_NOT_DISTURB_KEY, DEVICE_SETTINGS_LOW_SPEED_AT_NIGHT_KEY
from .dreame.const import cutting_height_max_cm
from .dreame.status_text import status_text
from .dreame.map_data_parser import MowerVectorMap
from .dreame.map_scene import map_geometry, map_outline, trail_points

_LOGGER = logging.getLogger(__name__)

WS_SUBSCRIBE_MAP = f"{DOMAIN}/map/subscribe"
WS_WORK_LOG = f"{DOMAIN}/work_log"
WS_WORK_LOG_DETAILS = f"{DOMAIN}/work_log/details"
WS_OBSTACLE_PHOTO = f"{DOMAIN}/obstacle_photo"

# How far back the work log goes when the mower does not say since when it
# counts, in seconds.
_WORK_LOG_FALLBACK_SECONDS = 180 * 24 * 3600


def geometry_payload(geometry: dict[str, Any] | None, other_maps: list[dict[str, Any]]) -> dict[str, Any]:
    """The active map, or a map id of None when there is none yet, and an outline of the others."""
    if geometry is None:
        return {"type": "geometry", "map_id": None, "other_maps": other_maps}
    return {"type": "geometry", **geometry, "other_maps": other_maps}


def path_payload(previous: list[Any], points: list[Any]) -> dict[str, Any] | None:
    """What the card must change to get from the previous trail to this one.

    The trail mostly grows at its end, but the newest points may still be
    filled in, so the card keeps the common start and replaces the rest.
    Returns None when nothing changed.
    """
    keep = 0
    limit = min(len(previous), len(points))
    while keep < limit and previous[keep] == points[keep]:
        keep += 1
    if keep == len(previous) == len(points):
        return None
    return {"type": "path", "keep": keep, "points": points[keep:]}


def settings_payload(coordinator: DreameMowerCoordinator) -> dict[str, Any] | None:
    """The mowing settings of the active map, for the card to show and change.

    `areas` holds the settings of the map-wide record under "0" and of every
    zone that keeps its own under its id; `mode` says which of them apply.
    """
    areas = coordinator.mowing_settings
    if not areas:
        return None
    mode = coordinator.mowing_preference_mode
    return {
        "mode": None if mode is None else mode.name.lower(),
        "height_max": cutting_height_max_cm(coordinator.device_model),
        "areas": {str(area_id): settings for area_id, settings in areas.items()},
    }


def status_payload(coordinator: DreameMowerCoordinator) -> dict[str, Any]:
    """Everything on the map that moves, and the mower's state."""
    device = coordinator.device
    current_map_id = device.current_map_id
    coordinates = device.mower_coordinates
    dock = device.dock_position
    session_active = device.mowing_session_active
    online = coordinator.device_connected and coordinator.device_online
    robot = device.robot_state
    return {
        "type": "status",
        "rotation": int(coordinator.entry.options.get(CONF_MAP_ROTATION, DEFAULT_MAP_ROTATION)),
        "maps": [
            {
                "id": map_entry["id"],
                "name": map_entry["name"] or f"Map {map_entry['id']}",
                "area": map_entry["area"],
                "selected": map_entry["id"] == current_map_id,
                "has_backup": bool(map_entry.get("has_backup")),
            }
            for map_entry in device.available_maps
        ],
        # How worn the consumables are, and the cellular module's plan.
        "consumables": coordinator.consumables,
        "link_module": None
        if not coordinator.link_module_installed
        else {"plan_valid": coordinator.link_module_plan_valid},
        # The settings shown and changed in the card through actions.
        "do_not_disturb": coordinator.time_window_setting(DEVICE_SETTINGS_DO_NOT_DISTURB_KEY),
        "low_speed_at_night": coordinator.time_window_setting(DEVICE_SETTINGS_LOW_SPEED_AT_NIGHT_KEY),
        "stop_point_setting": coordinator.stop_point_setting,
        "time_zone": coordinator.time_zone,
        "light": coordinator.light_setting,
        "human_presence": coordinator.human_presence_setting,
        "robot_voice": coordinator.robot_voice_setting,
        # Whether a new task can go on from the stop points.
        "stop_point_start": coordinator.supports_start_from_stop_point,
        # Empty slots that keep the backup of a deleted map, numbered from 1.
        "deleted_maps": device.deleted_maps,
        "mower": None
        if coordinates is None
        else {"x": coordinates[0], "y": coordinates[1], "heading": device.mower_heading},
        "dock": None if dock is None else {"x": dock[0], "y": dock[1], "angle": device.dock_angle},
        "docked": device.docked,
        "obstacles": [
            *({"kind": "obstacle", **obstacle} for obstacle in device.obstacles),
            *({"kind": "ai", **obstacle} for obstacle in device.ai_obstacles),
        ],
        "zones": zone_settings(coordinator),
        "settings": settings_payload(coordinator),
        "stop_points": device.stop_points,
        "current_zone": device.current_segment if session_active else None,
        "state": {
            "available": online,
            "status": device.status,
            "session_active": session_active,
            "battery": device.battery_percent,
            "charging": device.charging_status,
            "progress": device.mowing_progress_percent if session_active else None,
            "mowed_area": device.current_area_sqm if session_active else None,
            "total_area": device.total_area_sqm if session_active else None,
            # The kind of task the session runs, and for how long it has.
            "task_mode": coordinator.session_task_mode if session_active else None,
            "session_minutes": coordinator.session_minutes if session_active else None,
            "error": device.current_problem,
            # What the mower does, said the way its app says it, and where it
            # stands: whether it knows its position and how it goes to or
            # from its station.
            "text": status_text(online, robot, device.active_codes),
            "location": robot.get("location") if robot else None,
            "docking": robot.get("docking") if robot else None,
            "leaving_station": bool(robot and robot.get("leaving_station")),
            # None until the first heartbeat says which codes are set.
            "codes": sorted(device.active_codes) if robot is not None else None,
        },
    }


class MapFeed:
    """Sends a card what changed about one mower's map."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DreameMowerCoordinator,
        send: Callable[[dict[str, Any]], None],
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._send = send
        self._geometry_source: MowerVectorMap | None = None
        self._geometry_sent = False
        self._trail_revision: int | None = None
        # None until the first trail went out: a card that subscribes again
        # may still hold a trail the mower no longer has.
        self._trail: list[Any] | None = None
        self._status: dict[str, Any] | None = None
        self._lock = asyncio.Lock()
        self._unsubscribe: Callable[[], None] | None = None
        self._closed = False

    @callback
    def start(self) -> Callable[[], None]:
        """Follow the coordinator; returns what stops the feed."""
        self._unsubscribe = self._coordinator.async_add_listener(self._schedule_push)
        self._coordinator.shutdown_callbacks.append(self.close)
        return self.stop

    @callback
    def stop(self) -> None:
        self._closed = True
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self.close in self._coordinator.shutdown_callbacks:
            self._coordinator.shutdown_callbacks.remove(self.close)

    @callback
    def close(self) -> None:
        """The mower is going away; tell the card so it subscribes again later."""
        if not self._closed:
            self._send({"type": "closed"})
        self.stop()

    @callback
    def _schedule_push(self) -> None:
        self._hass.async_create_task(self.push())

    async def push(self) -> None:
        """Send what changed since the last push; pushes run one at a time."""
        try:
            async with self._lock:
                if not self._closed:
                    self._push()
        except Exception:  # noqa: BLE001 - one bad update must not end the feed
            _LOGGER.exception("Sending the map of %s failed", self._coordinator.entry.title)

    def _push(self) -> None:
        device = self._coordinator.device
        vector_map = device.vector_map
        if vector_map is not self._geometry_source or not self._geometry_sent:
            self._send(
                geometry_payload(
                    map_geometry(vector_map), [map_outline(other) for other in device.other_vector_maps]
                )
            )
            self._geometry_source = vector_map
            self._geometry_sent = True

        revision = device.trail_revision
        if revision != self._trail_revision:
            trail = trail_points(device.mowing_path_history)
            if self._trail is None:
                change: dict[str, Any] | None = {"type": "path", "keep": 0, "points": trail}
            else:
                change = path_payload(self._trail, trail)
            if change is not None:
                self._send(change)
            self._trail = trail
            self._trail_revision = revision

        status = status_payload(self._coordinator)
        if status != self._status:
            self._send(status)
            self._status = status


@callback
def _coordinator_for(hass: HomeAssistant, entity_id: str) -> DreameMowerCoordinator | None:
    registry_entry = er.async_get(hass).async_get(entity_id)
    if registry_entry is None or registry_entry.platform != DOMAIN or registry_entry.config_entry_id is None:
        return None
    entry = hass.config_entries.async_get_entry(registry_entry.config_entry_id)
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        return None
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    return None if entry_data is None else entry_data[DATA_COORDINATOR]


@websocket_command({vol.Required("type"): WS_SUBSCRIBE_MAP, vol.Required("entity_id"): cv.entity_id})
@async_response
async def ws_subscribe_map(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """Follow the map of the mower an entity belongs to."""
    coordinator = _coordinator_for(hass, msg["entity_id"])
    if coordinator is None:
        connection.send_error(msg["id"], ERR_NOT_FOUND, f"{msg['entity_id']} is not a loaded Dreame mower")
        return
    feed = MapFeed(hass, coordinator, lambda payload: connection.send_message(event_message(msg["id"], payload)))
    connection.subscriptions[msg["id"]] = feed.start()
    connection.send_result(msg["id"])
    await feed.push()


@websocket_command({vol.Required("type"): WS_WORK_LOG, vol.Required("entity_id"): cv.entity_id})
@async_response
async def ws_work_log(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """The work log of the mower an entity belongs to: its totals and its tasks."""
    coordinator = _coordinator_for(hass, msg["entity_id"])
    if coordinator is None:
        connection.send_error(msg["id"], ERR_NOT_FOUND, f"{msg['entity_id']} is not a loaded Dreame mower")
        return
    device = coordinator.device
    totals = None
    if coordinator.device_online:
        try:
            totals = await hass.async_add_executor_job(device.read_work_totals)
        except Exception as ex:  # noqa: BLE001 - the list is worth showing without the totals
            _LOGGER.debug("Work totals not available: %s", ex)
    since = totals["start"] if totals else int(time.time()) - _WORK_LOG_FALLBACK_SECONDS
    entries = await hass.async_add_executor_job(device.read_work_log, since)
    if entries is None:
        connection.send_error(msg["id"], ERR_HOME_ASSISTANT_ERROR, "The work log is not available right now")
        return
    connection.send_result(msg["id"], {"totals": totals, "entries": entries})


@websocket_command(
    {
        vol.Required("type"): WS_WORK_LOG_DETAILS,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("file"): cv.string,
    }
)
@async_response
async def ws_work_log_details(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """The details of one task of the work log."""
    coordinator = _coordinator_for(hass, msg["entity_id"])
    if coordinator is None:
        connection.send_error(msg["id"], ERR_NOT_FOUND, f"{msg['entity_id']} is not a loaded Dreame mower")
        return
    try:
        details = await hass.async_add_executor_job(coordinator.device.read_work_log_details, msg["file"])
    except ValueError as ex:
        connection.send_error(msg["id"], ERR_NOT_FOUND, str(ex))
        return
    if details is None:
        connection.send_error(msg["id"], ERR_HOME_ASSISTANT_ERROR, "The details of this task are not available")
        return
    connection.send_result(msg["id"], details)


@websocket_command(
    {
        vol.Required("type"): WS_OBSTACLE_PHOTO,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("image"): cv.string,
    }
)
@async_response
async def ws_obstacle_photo(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """The photo the mower took of an obstacle it recognised."""
    _LOGGER.debug("Photo %s asked for (request %s)", msg["image"], msg["id"])
    coordinator = _coordinator_for(hass, msg["entity_id"])
    if coordinator is None:
        connection.send_error(msg["id"], ERR_NOT_FOUND, f"{msg['entity_id']} is not a loaded Dreame mower")
        return
    try:
        photo = await hass.async_add_executor_job(coordinator.device.read_obstacle_photo, msg["image"])
    except ValueError as ex:
        connection.send_error(msg["id"], ERR_NOT_FOUND, str(ex))
        return
    if photo is None:
        connection.send_error(
            msg["id"], ERR_HOME_ASSISTANT_ERROR, "The mower did not send the photo; its connection may be weak"
        )
        return
    connection.send_result(msg["id"], photo)
