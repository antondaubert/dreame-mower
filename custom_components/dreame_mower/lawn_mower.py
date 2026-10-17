"""Minimal Lawn Mower Entity for Dreame Mower Implementation."""

from __future__ import annotations

import logging
from datetime import time as dt_time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.lawn_mower import (  # type: ignore[attr-defined]
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame import map_edit
from .dreame.device import DreameCommandError, MowingMode
from .entity import DreameMowerEntity, device_errors_as_ha_errors
from .dreame.const import (
    HUMAN_PRESENCE_INTERVALS_MINUTES,
    HUMAN_PRESENCE_MODES,
    HUMAN_PRESENCE_SENSITIVITIES,
    LIGHT_SCENES,
    VOICE_PROMPTS,
    DEVICE_SETTINGS_DO_NOT_DISTURB_KEY,
    DEVICE_SETTINGS_LOW_SPEED_AT_NIGHT_KEY,
    AI_OBSTACLE_KEY,
    DEVICE_CODE_BAD_WEATHER_PROTECTING,
    CUTTING_HEIGHT_ABSOLUTE_MAX_CM,
    CUTTING_HEIGHT_KEY,
    CUTTING_HEIGHT_MIN_CM,
    DIRECTION_ANGLE_KEY,
    DIRECTION_MODE_KEY,
    EDGE_BLADE_OFFSET_KEY,
    EDGE_MOWING_AUTO_KEY,
    EDGE_MOWING_SAFE_KEY,
    EDGE_OBSTACLE_AVOIDANCE_KEY,
    EFFICIENCY_KEY,
    LIDAR_OBSTACLE_KEY,
    OBSTACLE_DISTANCE_KEY,
    OBSTACLE_DISTANCES_CM,
    OBSTACLE_HEIGHT_KEY,
    OBSTACLE_HEIGHTS_CM,
    TURNING_METHOD_KEY,
    AiObstacleKind,
    MowingDirectionMode,
    MowingEfficiency,
    TurningMethod,
    MowingPreferenceMode,
    STATUS_PROPERTY,
    map_status_to_activity,
)

_LOGGER = logging.getLogger(__name__)

# Service-facing names for the mowing preference modes, e.g. "map_wide".
_MOWING_PREFERENCE_MODES = {mode.name.lower(): mode for mode in MowingPreferenceMode}

# Service-facing names for the mowing direction modes, e.g. "crisscross".
_MOWING_DIRECTION_MODES = {mode.name.lower(): mode for mode in MowingDirectionMode}

# The fields of the set_mowing_settings action, by the setting each changes.
_MOWING_SETTINGS_FIELDS = {
    "efficiency": EFFICIENCY_KEY,
    "cutting_height": CUTTING_HEIGHT_KEY,
    "mowing_direction": DIRECTION_ANGLE_KEY,
    "mowing_direction_mode": DIRECTION_MODE_KEY,
    "automatic_edge_mowing": EDGE_MOWING_AUTO_KEY,
    "safe_edge_mowing": EDGE_MOWING_SAFE_KEY,
    "edge_blade_offset": EDGE_BLADE_OFFSET_KEY,
    "edge_obstacle_avoidance": EDGE_OBSTACLE_AVOIDANCE_KEY,
    "lidar_obstacle_recognition": LIDAR_OBSTACLE_KEY,
    "obstacle_height": OBSTACLE_HEIGHT_KEY,
    "obstacle_distance": OBSTACLE_DISTANCE_KEY,
    "ai_obstacle_recognition": AI_OBSTACLE_KEY,
    "turning_method": TURNING_METHOD_KEY,
}

# Basic feature support for minimal implementation
MINIMAL_SUPPORT_FEATURES = (
    LawnMowerEntityFeature.START_MOWING
    | LawnMowerEntityFeature.PAUSE
    | LawnMowerEntityFeature.DOCK
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower lawn mower entity from a config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "start_all_area_mowing",
        {vol.Optional("from_stop_point"): cv.boolean},
        "async_start_all_area_mowing",
    )
    platform.async_register_entity_service(
        "end_task",
        {},
        "async_end_task",
    )
    platform.async_register_entity_service(
        "stop_returning",
        {},
        "async_stop_returning",
    )
    platform.async_register_entity_service(
        "recharge",
        {},
        "async_recharge",
    )
    platform.async_register_entity_service(
        "start_zone_mowing",
        {vol.Required("zone_ids"): [vol.Coerce(int)], vol.Optional("from_stop_point"): cv.boolean},
        "async_start_zone_mowing",
    )
    platform.async_register_entity_service(
        "start_edge_mowing",
        {vol.Required("contour_ids"): [vol.All([vol.Coerce(int)], vol.Length(min=2, max=2))]},
        "async_start_edge_mowing",
    )
    platform.async_register_entity_service(
        "start_spot_mowing",
        {vol.Required("spot_area_ids"): [vol.Coerce(int)]},
        "async_start_spot_mowing",
    )
    platform.async_register_entity_service(
        "select_map",
        {vol.Required("map_id"): vol.Coerce(int)},
        "async_select_map",
    )
    platform.async_register_entity_service(
        "set_mowing_settings",
        vol.All(
            cv.make_entity_service_schema(
                {
                    vol.Optional("efficiency"): vol.In([value.name.lower() for value in MowingEfficiency]),
                    vol.Optional("cutting_height"): vol.All(
                        vol.Coerce(float),
                        vol.Range(min=CUTTING_HEIGHT_MIN_CM, max=CUTTING_HEIGHT_ABSOLUTE_MAX_CM),
                    ),
                    vol.Optional("mowing_direction"): vol.All(vol.Coerce(int), vol.Range(min=0, max=359)),
                    vol.Optional("mowing_direction_mode"): vol.In(_MOWING_DIRECTION_MODES),
                    vol.Optional("automatic_edge_mowing"): cv.boolean,
                    vol.Optional("safe_edge_mowing"): cv.boolean,
                    vol.Optional("edge_blade_offset"): cv.boolean,
                    vol.Optional("edge_obstacle_avoidance"): cv.boolean,
                    vol.Optional("lidar_obstacle_recognition"): cv.boolean,
                    vol.Optional("obstacle_height"): vol.All(vol.Coerce(int), vol.In(OBSTACLE_HEIGHTS_CM)),
                    vol.Optional("obstacle_distance"): vol.All(vol.Coerce(int), vol.In(OBSTACLE_DISTANCES_CM)),
                    vol.Optional("ai_obstacle_recognition"): vol.All(
                        cv.ensure_list, [vol.In([str(kind.name).lower() for kind in AiObstacleKind])]
                    ),
                    vol.Optional("turning_method"): vol.In([value.name.lower() for value in TurningMethod]),
                    vol.Optional("map_id"): vol.Coerce(int),
                    vol.Optional("zone_id"): vol.Coerce(int),
                }
            ),
            cv.has_at_least_one_key(*_MOWING_SETTINGS_FIELDS),
        ),
        "async_set_mowing_settings",
    )
    _register_map_edit_services(platform)
    platform.async_register_entity_service(
        "set_mowing_preference_mode",
        {
            vol.Required("mode"): vol.In(_MOWING_PREFERENCE_MODES),
            vol.Optional("map_id"): vol.Coerce(int),
        },
        "async_set_mowing_preference_mode",
    )

    entity = DreameMowerLawnMower(coordinator)
    async_add_entities([entity])


_POINT = vol.All(vol.ExactSequence([vol.Coerce(float), vol.Coerce(float)]))
_RECT = vol.All(vol.ExactSequence([vol.Coerce(float)] * 4))
_ID = vol.Coerce(int)


def _register_map_edit_services(platform: entity_platform.EntityPlatform) -> None:
    """The actions that change what lies on the current map, and those that clear what the mower reports.

    The mower does not move for a change to the map; clearing an error lets it go on.
    """
    platform.async_register_entity_service(
        "set_no_go_zone",
        {
            vol.Required("shape"): vol.In(list(map_edit.NO_GO_SHAPES)),
            vol.Required("points"): vol.All([_POINT], vol.Length(min=1, max=2)),
            vol.Optional("radius"): vol.All(vol.Coerce(float), vol.Range(min=1)),
            vol.Optional("zone_id"): _ID,
        },
        "async_set_no_go_zone",
        supports_response=SupportsResponse.OPTIONAL,
    )
    platform.async_register_entity_service(
        "set_ignore_obstacle_area",
        {vol.Required("rect"): _RECT, vol.Optional("area_id"): _ID},
        "async_set_ignore_obstacle_area",
        supports_response=SupportsResponse.OPTIONAL,
    )
    platform.async_register_entity_service(
        "set_spot_area",
        {vol.Required("rect"): _RECT, vol.Optional("area_id"): _ID},
        "async_set_spot_area",
        supports_response=SupportsResponse.OPTIONAL,
    )
    platform.async_register_entity_service(
        "set_maintenance_point",
        {
            vol.Required("x"): vol.Coerce(float),
            vol.Required("y"): vol.Coerce(float),
            vol.Optional("heading"): vol.All(vol.Coerce(float), vol.Range(min=0, max=360)),
            vol.Optional("point_id"): _ID,
        },
        "async_set_maintenance_point",
        supports_response=SupportsResponse.OPTIONAL,
    )
    platform.async_register_entity_service(
        "delete_map_item",
        {vol.Required("kind"): vol.In(list(map_edit.ITEM_KINDS)), vol.Required("item_id"): _ID},
        "async_delete_map_item",
    )
    platform.async_register_entity_service(
        "rename_zone",
        {vol.Required("zone_id"): _ID, vol.Required("name"): cv.string},
        "async_rename_zone",
    )
    platform.async_register_entity_service(
        "split_zone",
        {vol.Required("zone_id"): _ID, vol.Required("line"): _RECT},
        "async_split_zone",
        supports_response=SupportsResponse.OPTIONAL,
    )
    platform.async_register_entity_service(
        "merge_zones",
        {vol.Required("zone_ids"): vol.All([_ID], vol.Length(min=2, max=2))},
        "async_merge_zones",
        supports_response=SupportsResponse.OPTIONAL,
    )
    platform.async_register_entity_service(
        "rename_map",
        {vol.Required("map_id"): _ID, vol.Required("name"): cv.string},
        "async_rename_map",
    )
    platform.async_register_entity_service("clear_rain_protection", {}, "async_clear_rain_protection")
    platform.async_register_entity_service("find_robot", {}, "async_find_robot")
    platform.async_register_entity_service(
        "clear_error",
        {vol.Optional("continue_task", default=True): cv.boolean},
        "async_clear_error",
    )
    window: dict[Any, Any] = {
        vol.Optional("enabled"): cv.boolean,
        vol.Optional("start"): cv.time,
        vol.Optional("end"): cv.time,
    }
    platform.async_register_entity_service("set_do_not_disturb", window, "async_set_do_not_disturb")
    platform.async_register_entity_service("set_low_speed_at_night", window, "async_set_low_speed_at_night")
    platform.async_register_entity_service(
        "set_start_from_stop_point",
        {vol.Optional("enabled"): cv.boolean, vol.Optional("days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7))},
        "async_set_start_from_stop_point",
    )
    platform.async_register_entity_service(
        "set_light",
        {
            vol.Optional("custom_period"): cv.boolean,
            vol.Optional("start"): cv.time,
            vol.Optional("end"): cv.time,
            **{vol.Optional(scene): cv.boolean for scene in LIGHT_SCENES},
        },
        "async_set_light",
    )
    platform.async_register_entity_service(
        "set_human_presence_alert",
        {
            vol.Optional("enabled"): cv.boolean,
            vol.Optional("sensitivity"): vol.In(list(HUMAN_PRESENCE_SENSITIVITIES)),
            **{vol.Optional(mode): cv.boolean for mode in HUMAN_PRESENCE_MODES},
            vol.Optional("voice"): cv.boolean,
            vol.Optional("photo"): cv.boolean,
            vol.Optional("interval"): vol.All(vol.Coerce(int), vol.In(list(HUMAN_PRESENCE_INTERVALS_MINUTES))),
        },
        "async_set_human_presence_alert",
    )
    platform.async_register_entity_service(
        "set_robot_voice",
        {
            vol.Optional("volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            **{vol.Optional(kind): cv.boolean for kind in VOICE_PROMPTS},
        },
        "async_set_robot_voice",
    )
    platform.async_register_entity_service(
        "reset_consumable", {vol.Required("item"): vol.In(["blade", "brush", "robot"])}, "async_reset_consumable"
    )
    platform.async_register_entity_service(
        "go_to_maintenance_point", {vol.Required("point_id"): _ID}, "async_go_to_maintenance_point"
    )
    platform.async_register_entity_service(
        "ignore_obstacle", {vol.Required("obstacle_id"): vol.Any(vol.Coerce(int), cv.string)}, "async_ignore_obstacle"
    )
    platform.async_register_entity_service("backup_map", {}, "async_backup_map")
    platform.async_register_entity_service(
        "restore_map", {vol.Optional("slot"): vol.All(vol.Coerce(int), vol.Range(min=1))}, "async_restore_map"
    )
    platform.async_register_entity_service("delete_map", {vol.Required("map_id"): _ID}, "async_delete_map")


class DreameMowerLawnMower(DreameMowerEntity, LawnMowerEntity):
    """Minimal Dreame Mower lawn mower entity."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the minimal lawn mower entity."""
        super().__init__(coordinator, "lawn_mower")
        
        self._attr_device_class = DOMAIN
        self._attr_supported_features = MINIMAL_SUPPORT_FEATURES
        self._attr_activity = LawnMowerActivity.DOCKED
        self._attr_icon = "mdi:robot-mower"
        self._attr_name = None  # Fix "A2 None" issue - set explicit name to None so HA uses just device name

        # Initialize activity based on current device status
        self._initialize_activity()

    async def async_added_to_hass(self) -> None:
        """Listen for status changes while the entity lives in Home Assistant."""
        await super().async_added_to_hass()

        # An entity that is disabled in the registry is never added, so it never
        # listens and never tries to write a state it does not have.
        self.coordinator.device.register_property_callback(self._on_property_change)
        self.async_on_remove(
            lambda: self.coordinator.device.unregister_property_callback(
                self._on_property_change
            )
        )

    def _initialize_activity(self) -> None:
        """Initialize activity based on current device status."""
        try:
            current_status_code = self.coordinator.device_status_code
            if current_status_code is not None:
                self._attr_activity = map_status_to_activity(current_status_code)
        except Exception as ex:
            _LOGGER.exception("Error initializing activity: %s", ex)

    @property
    def available(self) -> bool:
        """Return True if the mower is available."""
        # Inherit base availability logic and add mower-specific checks
        return super().available

    @property
    def activity(self) -> LawnMowerActivity | None:
        """Return the current activity of the mower."""
        if not self.available:
            return None
        return self._attr_activity
    
    def _on_property_change(self, property_name: str, value: Any) -> None:
        """Handle property changes from the device."""
        if property_name == STATUS_PROPERTY.name:
            new_activity = map_status_to_activity(value)
            if new_activity != self._attr_activity:
                self._attr_activity = new_activity
                self.schedule_update_ha_state()

    async def async_start_mowing(self) -> None:
        """Resume the task in progress, or else start mowing the whole map."""
        await self.async_start_all_area_mowing()

    async def async_start_all_area_mowing(self, from_stop_point: bool | None = None) -> None:
        """Resume the task in progress, or else start mowing the whole map."""
        self._check_from_stop_point(from_stop_point)
        with device_errors_as_ha_errors():
            # While a mowing session is already in progress (mowing, paused, or
            # returning to dock), resume/continue it instead of starting a new
            # task. Only when no session is active do we dispatch a fresh start.
            if self.coordinator.device.mowing_session_active:
                if not await self.coordinator.device.resume():
                    raise HomeAssistantError("Failed to resume mowing")
                return

            start_kwargs: dict[str, Any] = {"mode": MowingMode.ALL_AREA}
            if from_stop_point is not None:
                start_kwargs["from_stop_point"] = from_stop_point
            try:
                if await self.coordinator.device.start_mowing(**start_kwargs):
                    return
                _LOGGER.error("Failed to start all-area mowing")
            except DreameCommandError as ex:
                _LOGGER.error("%s", ex)

            # The generic action cannot say where to start from, so a start
            # that was told is reported as failed rather than left to chance.
            if from_stop_point is not None:
                raise HomeAssistantError("Failed to start all-area mowing")
            await self._start_all_area_generic_fallback()

    async def async_end_task(self) -> None:
        """End the running task; the mower stays where it is."""
        with device_errors_as_ha_errors():
            if not await self.coordinator.device.end_task():
                raise HomeAssistantError("Failed to end the mowing task")

    async def async_stop_returning(self) -> None:
        """Stop the mower on its way back to the station."""
        with device_errors_as_ha_errors():
            if not await self.coordinator.device.stop_returning():
                raise HomeAssistantError("Failed to stop the return to the station")

    async def async_recharge(self) -> None:
        """Send the mower to its station, keeping the running task to continue later."""
        with device_errors_as_ha_errors():
            if not await self.coordinator.device.dock_without_stopping():
                raise HomeAssistantError("Failed to send the mower to its station")

    def _check_from_stop_point(self, from_stop_point: bool | None) -> None:
        if from_stop_point is not None and not self.coordinator.supports_start_from_stop_point:
            raise HomeAssistantError("This mower cannot be told to start from the stop point")

    async def _start_all_area_generic_fallback(self) -> None:
        """Fall back to the generic device-decides START_MOWING action.

        Only used for all-area mowing: when the map-aware start payload is
        rejected or does not reach the mower, the bare 5:1 action lets the robot
        run whatever is configured in the app. For zone/edge/spot starts this
        would mow the wrong area, so the fallback is deliberately limited to
        all-area starts.
        """
        _LOGGER.warning("All-area start failed; falling back to generic START_MOWING action")
        with device_errors_as_ha_errors():
            if not await self.coordinator.device.start_mowing_generic():
                raise HomeAssistantError("Failed to start all-area mowing")

    async def async_start_zone_mowing(self, zone_ids: list[int], from_stop_point: bool | None = None) -> None:
        """Start mowing for one or more explicit zone IDs."""
        self._check_from_stop_point(from_stop_point)
        with device_errors_as_ha_errors():
            if not await self.coordinator.device.start_mowing_zones(zone_ids, from_stop_point=from_stop_point):
                raise HomeAssistantError(f"Failed to start zone mowing for zone IDs: {zone_ids}")

    async def async_start_edge_mowing(self, contour_ids: list[list[int]]) -> None:
        """Start edge mowing for one or more explicit contour IDs."""
        with device_errors_as_ha_errors():
            if not await self.coordinator.device.start_mowing_edges(contour_ids):
                raise HomeAssistantError(f"Failed to start edge mowing for contour IDs: {contour_ids}")

    async def async_start_spot_mowing(self, spot_area_ids: list[int]) -> None:
        """Start mowing for one or more explicit spot-area IDs."""
        with device_errors_as_ha_errors():
            if not await self.coordinator.device.start_mowing_spots(spot_area_ids):
                raise HomeAssistantError(f"Failed to start spot mowing for spot IDs: {spot_area_ids}")

    async def async_select_map(self, map_id: int) -> None:
        """Make another map the one the mower works on."""
        if map_id not in {int(map_entry["id"]) for map_entry in self.coordinator.available_maps}:
            raise HomeAssistantError(f"The mower holds no map with ID {map_id}")

        with device_errors_as_ha_errors():
            switched = await self.coordinator.device.set_current_map(map_id)

        if switched:
            return

        if self.coordinator.device.mowing_session_active:
            raise HomeAssistantError(
                "Cannot switch maps while a mowing task is in progress. "
                "Finish or cancel the task, then try again."
            )

        raise HomeAssistantError(f"Failed to switch to map {map_id}")

    async def _edit_map(self, change: Any) -> Any:
        """Make a change to the map and let everything showing it know."""
        with device_errors_as_ha_errors():
            result = await change
        self.coordinator.async_update_listeners()
        return result

    async def async_set_no_go_zone(
        self, shape: str, points: list[list[float]], radius: float | None = None, zone_id: int | None = None
    ) -> dict[str, Any]:
        """Draw a no-go zone, or change one."""
        return {"id": await self._edit_map(self.coordinator.device.set_no_go_zone(shape, points, radius, zone_id))}

    async def async_set_ignore_obstacle_area(self, rect: list[float], area_id: int | None = None) -> dict[str, Any]:
        """Draw an area where obstacles are driven over, or change one."""
        return {"id": await self._edit_map(self.coordinator.device.set_ignore_obstacle_area(rect, area_id))}

    async def async_set_spot_area(self, rect: list[float], area_id: int | None = None) -> dict[str, Any]:
        """Draw a spot area, or change one."""
        return {"id": await self._edit_map(self.coordinator.device.set_spot_area(rect, area_id))}

    async def async_set_maintenance_point(
        self, x: float, y: float, heading: float | None = None, point_id: int | None = None
    ) -> dict[str, Any]:
        """Place a maintenance point, or move one."""
        return {"id": await self._edit_map(self.coordinator.device.set_maintenance_point(x, y, heading, point_id))}

    async def async_delete_map_item(self, kind: str, item_id: int) -> None:
        """Delete an item of the current map."""
        await self._edit_map(self.coordinator.device.delete_map_item(kind, item_id))

    async def async_rename_zone(self, zone_id: int, name: str) -> None:
        await self._edit_map(self.coordinator.device.rename_zone(zone_id, name))

    async def async_split_zone(self, zone_id: int, line: list[float]) -> dict[str, Any]:
        return {"ids": await self._edit_map(self.coordinator.device.split_zone(zone_id, line))}

    async def async_merge_zones(self, zone_ids: list[int]) -> dict[str, Any]:
        return {"id": await self._edit_map(self.coordinator.device.merge_zones(zone_ids))}

    async def async_rename_map(self, map_id: int, name: str) -> None:
        await self._edit_map(self.coordinator.device.rename_map(map_id, name))

    async def async_clear_rain_protection(self) -> None:
        """Clear the rain the mower reports, so a task it is asked to start runs."""
        with device_errors_as_ha_errors():
            cleared = await self.coordinator.device.suppress_code(DEVICE_CODE_BAD_WEATHER_PROTECTING)
        if not cleared:
            raise HomeAssistantError("The mower kept its rain protection on")
        self.coordinator.async_update_listeners()

    async def async_find_robot(self) -> None:
        """Have the mower call out, so it can be found by its sound."""
        with device_errors_as_ha_errors():
            called = await self.coordinator.device.find_robot()
        if not called:
            raise HomeAssistantError("The mower did not call out")

    async def async_clear_error(self, continue_task: bool = True) -> None:
        """Clear the errors the mower reports and let it go on with what it did.

        A task that the error interrupted carries on; a mower that stands on
        the lawn without a task drives home.
        """
        device = self.coordinator.device
        with device_errors_as_ha_errors():
            cleared = await device.clear_errors()
            self.coordinator.async_update_listeners()
            if not cleared:
                raise HomeAssistantError("The mower kept reporting the error")
            if not continue_task:
                return
            robot = device.robot_state or {}
            if device.mowing_session_active:
                if not await device.resume():
                    raise HomeAssistantError("The error is cleared, but the mower did not resume its task")
            elif robot.get("docking") not in (None, "in_station"):
                if not await device.return_to_dock():
                    raise HomeAssistantError("The error is cleared, but the mower did not head back to its station")
        self.coordinator.async_update_listeners()

    async def async_set_do_not_disturb(
        self, enabled: bool | None = None, start: dt_time | None = None, end: dt_time | None = None
    ) -> None:
        """Switch Do Not Disturb, or change its window, keeping what is left out."""
        await self._async_set_window(DEVICE_SETTINGS_DO_NOT_DISTURB_KEY, "Do Not Disturb", enabled, start, end)

    async def async_set_low_speed_at_night(
        self, enabled: bool | None = None, start: dt_time | None = None, end: dt_time | None = None
    ) -> None:
        """Switch the low speed at night, or change its window, keeping what is left out."""
        await self._async_set_window(DEVICE_SETTINGS_LOW_SPEED_AT_NIGHT_KEY, "the low speed at night", enabled, start, end)

    async def _async_set_window(
        self, key: str, name: str, enabled: bool | None, start: dt_time | None, end: dt_time | None
    ) -> None:
        minutes = lambda moment: None if moment is None else moment.hour * 60 + moment.minute
        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_time_window_setting(key, enabled, minutes(start), minutes(end))
        if not updated:
            raise HomeAssistantError(f"The mower did not take {name}")

    async def async_set_start_from_stop_point(self, enabled: bool | None = None, days: int | None = None) -> None:
        """Choose whether a task may go on from a stop point, and how long one is kept."""
        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_stop_point_setting(enabled, days)
        if not updated:
            raise HomeAssistantError("The mower did not take the stop point setting")

    async def async_set_light(
        self, start: dt_time | None = None, end: dt_time | None = None, **changes: bool | None
    ) -> None:
        """Change the lights, keeping what is left out as it is."""
        minutes = lambda moment: None if moment is None else moment.hour * 60 + moment.minute
        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_light_setting(start=minutes(start), end=minutes(end), **changes)
        if not updated:
            raise HomeAssistantError("The mower did not take the light settings")

    async def async_set_human_presence_alert(self, **changes: Any) -> None:
        """Change the human presence alert, keeping what is left out as it is."""
        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_human_presence_setting(**changes)
        if not updated:
            raise HomeAssistantError("The mower did not take the human presence alert settings")

    async def async_set_robot_voice(self, volume: int | None = None, **prompts: bool | None) -> None:
        """Change the robot's volume or the prompts it speaks."""
        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_robot_voice(volume, **prompts)
        if not updated:
            raise HomeAssistantError("The mower did not take the voice settings")

    async def async_reset_consumable(self, item: str) -> None:
        """Start a consumable's count over, as after replacing it."""
        with device_errors_as_ha_errors():
            await self.coordinator.async_reset_consumable(item)

    async def async_go_to_maintenance_point(self, point_id: int) -> None:
        """Send the mower to a maintenance point."""
        with device_errors_as_ha_errors():
            if not await self.coordinator.async_go_to_maintenance_point(point_id):
                raise HomeAssistantError("The mower did not head to the maintenance point")

    async def async_ignore_obstacle(self, obstacle_id: int | str) -> None:
        """Have the mower forget an obstacle its camera recognised."""
        with device_errors_as_ha_errors():
            await self.coordinator.device.ignore_ai_obstacle(obstacle_id)
        self.coordinator.async_update_listeners()

    async def async_backup_map(self) -> None:
        await self._edit_map(self.coordinator.device.backup_map())

    async def async_restore_map(self, slot: int | None = None) -> None:
        """Put the current map back as its backup has it, or a deleted map back into its slot."""
        device = self.coordinator.device
        await self._edit_map(device.restore_map() if slot is None else device.restore_deleted_map(slot))

    async def async_delete_map(self, map_id: int) -> None:
        await self._edit_map(self.coordinator.device.delete_map(map_id))

    async def async_set_mowing_settings(
        self,
        map_id: int | None = None,
        zone_id: int | None = None,
        **fields: Any,
    ) -> None:
        """Change any of the mowing settings of a map, or of a single zone of it."""
        settings = {_MOWING_SETTINGS_FIELDS[name]: value for name, value in fields.items() if name in _MOWING_SETTINGS_FIELDS}
        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_mowing_settings(settings, map_id=map_id, zone_id=zone_id)

        if not updated:
            target = "the map" if zone_id is None else f"zone {zone_id}"
            raise HomeAssistantError(f"Failed to change the mowing settings of {target}")

    async def async_set_mowing_preference_mode(self, mode: str, map_id: int | None = None) -> None:
        """Choose whether a map follows one set of mowing settings or per-zone ones."""
        self._assert_cutting_height_supported()

        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_mowing_preference_mode(
                _MOWING_PREFERENCE_MODES[mode], map_id
            )

        if not updated:
            raise HomeAssistantError(f"Failed to switch the mowing preferences to {mode}")

    def _assert_cutting_height_supported(self) -> None:
        """Raise when the model has no software-adjustable cutting height."""
        if not self.coordinator.supports_cutting_height:
            raise HomeAssistantError(
                f"{self.coordinator.device_model} has no software-adjustable cutting height"
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes including available zones and contours."""
        attributes: dict[str, Any] = {}
        zones = self.coordinator.zones
        contours = self.coordinator.contours
        available_maps = self.coordinator.available_maps
        if zones:
            attributes["zones"] = zones
        if contours:
            attributes["contours"] = contours
        if available_maps:
            attributes["maps"] = available_maps
        current_map_id = self.coordinator.current_map_id
        if current_map_id is not None:
            attributes["current_map_id"] = current_map_id
        return attributes

    async def async_pause(self) -> None:
        """Pause mowing."""
        with device_errors_as_ha_errors():
            if not await self.coordinator.device.pause():
                raise HomeAssistantError("Failed to pause mowing")

    async def async_dock(self) -> None:
        """Return to dock."""
        with device_errors_as_ha_errors():
            if not await self.coordinator.device.return_to_dock():
                raise HomeAssistantError("Failed to send the mower back to its dock")
