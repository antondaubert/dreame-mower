"""Device communication layer for Dreame Mower Implementation.

This module provides the device abstraction for communicating with the Dreame Mower.
It handles MQTT/Cloud API connections and device state management.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import base64
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from enum import Enum, IntEnum
import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable
from datetime import datetime

from .cloud.cloud_device import DreameMowerCloudDevice
from .map_data_parser import (
    MowerVectorMap,
    assemble_vector_map,
    convert_device_map,
    has_map,
    parse_ai_obstacles,
    parse_batch_map_data,
    parse_obstacles,
    parse_cached_maps,
    parse_mower_map,
)
from .utils import download_file
from . import map_edit
from .work_log import work_log_details, work_log_entries
from .obstacle_photo import obstacle_photo_boxes
from .property import (
    MiscPropertyHandler,
    DeviceCodeHandler,
    SchedulingPropertyHandler,
    MissionCompletionEventHandler,
    PoseCoverageHandler,
    DEVICE_CODE_ERROR_PROPERTY_NAME,
    DEVICE_CODE_WARNING_PROPERTY_NAME,
    DEVICE_CODE_INFO_PROPERTY_NAME,
    POSE_COVERAGE_PROGRESS_PROPERTY_NAME,
    POSE_COVERAGE_COORDINATES_PROPERTY_NAME,
)
from .property.pose_coverage import decode_pose_point
from .property.property_misc import PROPERTY_1_1_TASK_STATUS_NAME
from .const import (
    AI_OBSTACLE_KEY,
    CUTTING_HEIGHT_KEY,
    DIRECTION_ANGLE_KEY,
    DIRECTION_MODE_KEY,
    EDGE_OBSTACLE_AVOIDANCE_KEY,
    EFFICIENCY_KEY,
    LIDAR_OBSTACLE_KEY,
    MOWING_PREFERENCE_AI_OBSTACLE_INDEX,
    MOWING_PREFERENCE_EDGE_OBSTACLE_AVOIDANCE_INDEX,
    MOWING_PREFERENCE_EFFICIENCY_INDEX,
    MOWING_PREFERENCE_LIDAR_OBSTACLE_INDEX,
    MOWING_PREFERENCE_OBSTACLE_DISTANCE_INDEX,
    MOWING_PREFERENCE_OBSTACLE_HEIGHT_INDEX,
    MOWING_PREFERENCE_TURNING_METHOD_INDEX,
    OBSTACLE_DISTANCE_KEY,
    OBSTACLE_DISTANCES_CM,
    OBSTACLE_HEIGHT_KEY,
    OBSTACLE_HEIGHTS_CM,
    TURNING_METHOD_KEY,
    has_camera,
    AiObstacleKind,
    MowingEfficiency,
    TurningMethod,
    AI_OBSTACLES_KEY,
    DOCK_KEY,
    POSITION_KEY,
    STOP_POINTS_KEY,
    AI_OBSTACLE_PHOTO_DIR,
    AI_OBSTACLES_SEEN_FILE,
    AI_OBSTACLES_SEEN_LIMIT,
    AI_OBSTACLE_PHOTO_KIND,
    AI_OBSTACLE_PHOTO_TIMEOUT,
    AI_OBSTACLE_PHOTO_TRIES,
    WORK_LOG_LIMIT,
    WORK_TOTALS_KEY,
    TRAIL_KEY,
    TRAIL_MAX_PAGES,
    TRAIL_PAGE_SIZE,
    DOCK_POSITION_SCALE,
    DOCK_YAW_SCALE,
    OBSTACLES_KEY,
    BATTERY_PROPERTY,
    STATUS_PROPERTY,
    BLUETOOTH_PROPERTY,
    SCHEDULING_TASK_PROPERTY,
    SCHEDULING_SUMMARY_PROPERTY,
    POWER_STATE_PROPERTY,
    SERVICE2_PROPERTY_55,
    IGNORED_PROPERTIES,
    FIRMWARE_INSTALL_STATE_PROPERTY,
    FIRMWARE_DOWNLOAD_PROGRESS_PROPERTY,
    POSE_COVERAGE_PROPERTY,
    SERVICE1_PROPERTY_50,
    SERVICE1_PROPERTY_51,
    STATUS_MAPPING,
    PROPERTY_FIRMWARE,
    CHARGING_STATUS_PROPERTY,
    CHARGING_STATUS_MAPPING,
    FIRMWARE_INSTALL_STATE_MAPPING,
    FIRMWARE_UPDATE_ALLOWED_STATUSES,
    FIRMWARE_UPDATE_MIN_BATTERY_PERCENT,
    FirmwareInstallState,
    DEVICE_FILE_PATH_PROPERTY,
    DEVICE_FILE_PATH_PROPERTY_20,
    FIRMWARE_VALIDATION_EVENT,
    MISSION_COMPLETION_EVENT,
    ActionIdentifier,
    ACTION_START_MOWING,
    ACTION_PAUSE,
    ACTION_STOP,
    ACTION_DOCK,
    TASK_PAYLOAD_RESUME,
    TASK_PAYLOAD_STOP_RETURNING,
    DEVICE_CODE_PROPERTY,
    PROPERTY_1_1,
    ONLINE_OFFLINE_DEBOUNCE_POLLS,
    TRANSPORT_DISCONNECT_GRACE_SECONDS,
    CURRENT_MAP_ID_PROPERTY_NAME,
    MAP_SWITCH_ANNOUNCED_PROPERTY_NAME,
    TASK_OPCODE_MAP_SWITCH,
    CUTTING_HEIGHT_ABSOLUTE_MAX_CM,
    CUTTING_HEIGHT_MIN_CM,
    CUTTING_HEIGHT_STEP_CM,
    CUTTING_HEIGHT_PROPERTY_NAME,
    EDGE_BLADE_OFFSET_KEY,
    EDGE_MOWING_AUTO_KEY,
    EDGE_MOWING_SAFE_KEY,
    EDGE_MOWING_SETTINGS_PROPERTY_NAME,
    MOWING_DIRECTION_ANGLE_KEY,
    MOWING_DIRECTION_ANGLE_PERIOD_DEGREES,
    MOWING_DIRECTION_MODE_KEY,
    MOWING_DIRECTION_PROPERTY_NAME,
    MowingDirectionMode,
    ZONE_MOWING_DIRECTIONS_PROPERTY_NAME,
    MOWING_PREFERENCE_AREA_ID_INDEX,
    MOWING_PREFERENCE_CUTTING_HEIGHT_INDEX,
    MOWING_PREFERENCE_DIRECTION_ANGLE_INDEX,
    MOWING_PREFERENCE_DIRECTION_MODE_INDEX,
    MOWING_PREFERENCE_EDGE_BLADE_OFFSET_INDEX,
    MOWING_PREFERENCE_EDGE_BLADE_OFFSET_MIN_LAPS,
    MOWING_PREFERENCE_EDGE_MOWING_AUTO_INDEX,
    MOWING_PREFERENCE_EDGE_MOWING_LAPS_INDEX,
    MOWING_PREFERENCE_EDGE_MOWING_SAFE_INDEX,
    MOWING_PREFERENCE_GLOBAL_AREA_ID,
    MOWING_PREFERENCE_LEGACY_LENGTH,
    MOWING_PREFERENCE_MAP_INDEX_INDEX,
    MOWING_PREFERENCE_MODE_PROPERTY_NAME,
    MOWING_PREFERENCE_STATUS_INVALID,
    MOWING_PREFERENCE_STATUS_SUCCESS,
    MOWING_PREFERENCE_VERSION_INDEX,
    MOWING_PREFERENCE_WRITE_VERSION,
    ZONE_CUTTING_HEIGHTS_PROPERTY_NAME,
    ZONE_EDGE_MOWING_SETTINGS_PROPERTY_NAME,
    BATTERY_SETTING_CHARGING_PERIOD_ENABLED_INDEX,
    BATTERY_SETTING_CHARGING_PERIOD_END_INDEX,
    BATTERY_SETTING_CHARGING_PERIOD_START_INDEX,
    BATTERY_SETTING_LENGTH,
    BATTERY_SETTING_RECHARGE_LEVEL_INDEX,
    BATTERY_SETTING_RESUME_AFTER_CHARGING_INDEX,
    BATTERY_SETTING_RESUME_LEVEL_INDEX,
    ANTI_THEFT_SETTING_LIFT_ALARM_INDEX,
    ANTI_THEFT_SETTING_LENGTH,
    ANTI_THEFT_SETTING_LOCATION_INDEX,
    ANTI_THEFT_SETTING_OFF_MAP_ALARM_INDEX,
    ANTI_THEFT_SETTING_PIN_CHECK_INDEX,
    DEVICE_SETTINGS_ANTI_THEFT_KEY,
    DEVICE_SETTINGS_BATTERY_KEY,
    DEVICE_SETTINGS_RAIN_KEY,
    SCHEDULE_CHUNK_SIZE,
    MAP_LIST_KEY,
    MAP_INFO_KEY,
    MAP_DATA_KEY,
    MAP_CHUNK_SIZE,
    SCHEDULE_DATA_KEY,
    SCHEDULE_ENABLE_KEY,
    SCHEDULE_INFO_KEY,
    SCHEDULE_MOVA_DATA_KEY,
    SCHEDULE_MOVA_ENABLE_KEY,
    SCHEDULE_MOVA_INFO_KEY,
    SCHEDULE_PLAN_ENABLED_INDEX,
    SCHEDULE_PLAN_NAME_INDEX,
    SCHEDULE_PLAN_SLOT_INDEX,
    SCHEDULE_PLAN_TASKS_INDEX,
    SCHEDULE_STATUS_SUCCESS,
    SCHEDULE_STATUS_VERSION_ERROR,
    SCHEDULE_SLOT_COUNT,
    SCHEDULE_TABLE_CYCLIC_TYPE_OFFSET,
    SCHEDULE_TABLE_ENABLE_KEY,
    SCHEDULE_TABLE_ENABLED_INDEX,
    SCHEDULE_TABLE_ID_INDEX,
    SCHEDULE_TABLE_INFO_KEY,
    SCHEDULE_TABLE_NAME_INDEX,
    SCHEDULE_TABLE_TASK_DAYS_INDEX,
    SCHEDULE_TABLE_TASK_ENABLED_INDEX,
    SCHEDULE_TABLE_TASK_KEY,
    SCHEDULE_TABLE_UNSUPPORTED_REPLY,
    SCHEDULE_TABLE_TASK_REGIONS_INDEX,
    SCHEDULE_TABLE_TASK_START_INDEX,
    SCHEDULE_TABLE_TASK_TYPE_INDEX,
    SCHEDULE_TABLE_TASKS_INDEX,
    SCHEDULE_TASK_MINIMUM_LENGTH,
    SCHEDULE_TASK_START_MARKER,
    SCHEDULE_TASK_TYPE_MAPPING,
    SCHEDULE_WEEK_DAYS,
    SCHEDULES_PROPERTY_NAME,
    ScheduleTaskType,
    MINUTES_PER_DAY,
    RAIN_DELAY_MIN_HOURS,
    RAIN_DELAY_MAX_HOURS,
    RAIN_SETTING_DEFAULT_SENSITIVITY,
    RAIN_SETTING_DELAY_INDEX,
    RAIN_SETTING_ENABLED_INDEX,
    RAIN_SETTING_LENGTH,
    RAIN_SETTING_MINIMUM_LENGTH,
    RAIN_SETTING_SENSITIVITY_INDEX,
    MowingPreferenceMode,
    DeviceStatus,
)

_LOGGER = logging.getLogger(__name__)


# What the name of an obstacle photo looks like; nothing else is fetched or kept.
_PHOTO_NAME = re.compile(r"[0-9A-Za-z_-][0-9A-Za-z._-]*")


# Whether a task mows only what an unfinished one left in its zones.
FROM_STOP_POINT_KEY = "need_bp"

# The action that clears a code the mower reports.
SUPPRESS_CODE_ACTION = 11

# The action that has the mower call out, so it can be found by its sound.
FIND_ROBOT_ACTION = 9

# Codes that remind of maintenance (a worn blade, a worn station brush, the
# maintenance time) without holding the mower up.
MAINTENANCE_REMINDER_CODES = frozenset({28, 29, 30})

# The heartbeat of a mower out mowing: main state 4, task status 2 (33 + 2).
AI_OBSTACLE_MOWING_MAIN_STATE = 4
AI_OBSTACLE_MOWING_SUB_STATE = 35
# The mower's answer to ignoring an obstacle it does not know.
AI_OBSTACLE_UNKNOWN = 2

# How long the mower may take to confirm a change to its map, in seconds.
MAP_EDIT_ANSWER_SECONDS = 30
# A map deleted or brought back shows in the mower's list of maps only a moment
# after it confirmed the change, so the list is read until it does.
MAP_SLOTS_SETTLE_ATTEMPTS = 5
MAP_SLOTS_SETTLE_SECONDS = 2.0

# A task's duration counts whole minutes, so its end may lie this much later.
_TASK_END_SLACK_SECONDS = 60


def _photo_time(image: str) -> float:
    """When a photo was taken: its name starts with the unix time."""
    try:
        return float(image.split("_", 1)[0])
    except ValueError:
        return 0.0


def _read_bytes(path: str) -> bytes | None:
    """The content of a file, or None when there is none to read."""
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _write_bytes(path: str, content: bytes) -> None:
    """Keep content in a file, replacing it whole; a failure is only logged."""
    temporary = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(temporary, "wb") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except OSError as ex:
        _LOGGER.warning("Could not keep %s: %s", path, ex)


def _same_obstacle(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Whether two recognised obstacles are the same one: where they are and what."""
    return (one["x"], one["y"], one["type"]) == (other["x"], other["y"], other["type"])


def _enum_name(enum: type[IntEnum], value: int) -> str | int:
    """The lowercase name of a known enum value; an unknown value stays a number."""
    try:
        return enum(value).name.lower()
    except ValueError:
        return value

# The mower acknowledges a map switch even when it refuses to act on it, so the
# switch is confirmed by re-reading the map list. The device needs a moment to
# apply the change, hence more than one attempt.
MAP_SWITCH_VERIFY_ATTEMPTS = 3
MAP_SWITCH_VERIFY_DELAY_SECONDS = 1.0

CONSUMABLE_COUNTER_TOTAL_MINUTES: dict[str, int] = {
    "blade": 6000,
    "brush": 30000,
    "robot": 3600,
}

CONSUMABLE_COUNTER_INDEX: dict[str, int] = {
    "blade": 0,
    "blades": 0,
    "brush": 1,
    "cleaning_brush": 1,
    "robot": 2,
    "maintenance": 2,
    "robot_maintenance": 2,
}


class DreameCommandError(Exception):
    """Raised when a command to the mower did not complete a round trip.

    This covers every way the exchange itself can fail: a dropped connection, a
    request that timed out, a mower that is offline, or an error the cloud
    reported in place of the mower's reply. The message carries the reason the
    connection gave, which is the only account there is of why the command did
    not happen.

    It is deliberately distinct from a falsy return value. A device method that
    returns None or False has been answered: the mower refused the write, or
    replied with something that could not be read. Only this exception means the
    command's outcome is unknown, so the two are never treated alike.
    """


class _StaleScheduleVersion(Exception):
    """Raised when a schedule write quotes a version the mower has moved on from."""


class MowingMode(str, Enum):
    """Mowing modes exposed by the mower task protocol."""

    ALL_AREA = "all_area"
    EDGE = "edge"
    ZONE = "zone"
    SPOT = "spot"
    MANUAL = "manual"


class DreameMowerDevice:
    """Device communication handler for Dreame Mower.

    This class manages the connection and communication with the physical mower device.
    It provides a high-level interface for controlling the mower and receiving status updates.

    Every method that talks to the mower reports failure the same way. A falsy
    return value is the mower's own answer: it refused the command, or replied
    with something that could not be read, and the method has logged what it
    saw. A DreameCommandError means the exchange never completed and the outcome
    is unknown; it carries the reason the connection gave, which is the only
    account of why the command did not happen and is therefore never traded for
    a return value here. Callers with nobody waiting on the result — the polls
    and the reads at startup — are the ones that decide to carry on regardless.
    """

    def __init__(
        self,
        device_id: str,
        username: str,
        password: str,
        account_type: str,
        country: str,
        hass_config_dir: str,
        model: str | None = None,
    ) -> None:
        """Initialize the device handler.
        
        Args:
            device_id: Unique device identifier
            username: Username for device authentication
            password: Password for device authentication
            account_type: Account type for cloud authentication
            country: Country for cloud authentication
            hass_config_dir: The path to the Home Assistant configuration directory.
            model: The model identifier, when known ahead of the first cloud read.
        """
        self._device_id = device_id
        self._model = model
        self._username = username
        self._password = password
        self._account_type = account_type
        # Set once a MOVA mower turns the table read down, after which its
        # schedules are read as a document for the rest of the session.
        self._schedule_tables_unsupported = False
        self._country = country
        self._hass_config_dir = hass_config_dir
        
        # Initialize cloud device
        self._cloud_device = DreameMowerCloudDevice(
            username=username,
            password=password,
            country=country,
            account_type=account_type,
            device_id=device_id,
        )
        
        # Pullable properties
        self._firmware = "Unknown"
        self._last_update = datetime.now()
        self._battery_percent = 0
        self._status_code = 0

        # Whether the device itself is reachable via the cloud. The MQTT link the
        # integration keeps open stays connected even when the robot drops off the
        # cloud, so this is tracked separately from the transport connection and
        # refreshed by the connectivity heartbeat poll. Defaults to online so
        # entities are available until the first poll proves otherwise.
        self._online = True
        # Consecutive offline heartbeat polls seen so far; the device is only
        # flipped offline once this reaches ONLINE_OFFLINE_DEBOUNCE_POLLS.
        self._offline_poll_count = 0
        # Monotonic time the transport dropped while we were connected, or None.
        # While set and within TRANSPORT_DISCONNECT_GRACE_SECONDS the device is
        # still reported connected, so a quick broker reconnect does not flap.
        self._transport_down_since: float | None = None
        self._transport_grace_timer: threading.Timer | None = None

        # MQTT properties
        self._bluetooth_connected: bool | None = None
        self._charging_status: str | None = None
        self._device_file_path: str | None = None
        self._firmware_install_state: int | None = None
        self._firmware_download_progress: int | None = None
        self._firmware_new_available: bool = False
        self._firmware_latest_version: str | None = None
        self._firmware_release_notes: str | None = None
        # Whether the cloud OTA service has answered a version check yet; until
        # it has, the latest firmware version is not known either way.
        self._firmware_status_checked: bool = False

        # Property handlers
        self._misc_handler = MiscPropertyHandler()
        self._device_code_handler = DeviceCodeHandler()
        self._scheduling_handler = SchedulingPropertyHandler()
        self._mission_completion_handler = MissionCompletionEventHandler()
        self._pose_coverage_handler = PoseCoverageHandler()
        
        # Vector map, read from the mower and the cloud copy of its maps
        self._vector_map: MowerVectorMap | None = None
        # Where the charging station stands and which way it faces, as the
        # mower reports it; and the obstacles on the active map.
        self._dock_position: tuple[int, int] | None = None
        self._dock_angle: float | None = None
        self._obstacles: list[dict[str, Any]] = []
        self._ai_obstacles: list[dict[str, Any]] = []
        # One obstacle photo is fetched at a time; every photo that came is
        # kept, so it never has to come over the mower's connection again.
        self._photo_lock = threading.Lock()
        # Photos of the obstacles of the tasks the work log was asked about.
        self._work_log_photos: set[str] = set()
        # The photos each kept task file lists; such a file never changes.
        self._task_file_photos: dict[str, frozenset[str]] = {}
        # Every recognised obstacle with a photo seen while mowing, by photo:
        # the mower drops one it later finds gone, and the task it was met in
        # then no longer lists it. Read from where it is kept on first use.
        self._seen_ai_obstacles: dict[str, dict[str, Any]] | None = None
        self._seen_lock = threading.Lock()
        self._stop_points: list[dict[str, Any]] = []
        # The map slots the mower keeps a backup of, by index.
        self._map_backups: set[int] = set()
        # The slots the mower reports as holding a map, by index.
        self._held_map_slots: set[int] | None = None
        # Which way each maintenance point faces, by map index, with the hash of
        # the map they were read from: only the mower's own copy of a map says.
        self._point_headings: dict[int, tuple[str, dict[int, float | None]]] = {}
        # Commands waiting for the mower's confirmation, by their "o".
        self._task_answers: dict[int, concurrent.futures.Future[dict[str, Any]]] = {}
        self._task_answers_lock = threading.Lock()
        # One change to the map at a time.
        self._map_edit_lock = asyncio.Lock()
        # The task files the work log listed last; only those are read.
        self._work_log_files: set[str] = set()
        # Whether a mowing session ran as of the last task status; None until
        # the first one arrives.
        self._session_was_active: bool | None = None
        self._current_map_id: int | None = None
        # Hash of every map slot that holds a map, as of the last map read; None
        # while the maps have not been read from the mower itself.
        self._map_hashes: dict[int, str] | None = None
        # A map data read continues whichever map the info read before it named,
        # so two map reads must not interleave.
        self._map_read_lock = threading.Lock()

        # Mowing settings of the current map, alongside the mode that decides
        # which of them the mower applies. Read on demand from the mowing
        # preference records; the device does not push them.
        self._cutting_height: float | None = None
        self._zone_cutting_heights: dict[int, float] = {}
        self._edge_mowing_settings: dict[str, bool] | None = None
        self._zone_edge_mowing_settings: dict[int, dict[str, bool]] = {}
        self._mowing_direction: dict[str, int] | None = None
        self._zone_mowing_directions: dict[int, dict[str, int]] = {}
        self._mowing_preference_mode: MowingPreferenceMode | None = None
        # The records themselves, by area id (0 for the map-wide one).
        self._mowing_records: dict[int, list[int]] = {}

        # Schedule slots of the current map, alongside the map they were read
        # from and the version the mower holds them under. Also read on demand;
        # the device does not push them.
        self._schedules: list[dict[str, Any]] | None = None
        self._schedule_map_index: int | None = None
        self._schedule_version: int | None = None
        # Decoded tasks of the schedule tables, by table and task id, alongside
        # the version they were read at. The tables are numbered across maps, so
        # the cache stays valid when the map changes.
        self._schedule_table_tasks: dict[tuple[int, int], tuple[int, list[dict[str, Any]]]] = {}

        # Property change callbacks
        self._property_callbacks: list[Callable[[str, Any], None]] = []
        
        # Stop-then-dock sequence - wait for mission completion event
        self._mission_completed_event: asyncio.Event = asyncio.Event()

    @property
    def connected(self) -> bool:
        """Return True if device is connected.

        A transport drop is only reported once it has outlasted
        TRANSPORT_DISCONNECT_GRACE_SECONDS.
        """
        if self._cloud_device.connected:
            return True
        down_since = self._transport_down_since
        return (
            down_since is not None
            and time.monotonic() - down_since < TRANSPORT_DISCONNECT_GRACE_SECONDS
        )

    @property
    def device_reachable(self) -> bool:
        """Return True if device is reachable via cloud API."""
        return self._cloud_device.device_reachable

    @property
    def online(self) -> bool:
        """Return True if the device itself is online per the cloud heartbeat."""
        return self._online

    @property
    def firmware(self) -> str:
        """Return device firmware version."""
        return self._firmware

    @property
    def last_update(self) -> datetime:
        """Return timestamp of last successful update."""
        return self._last_update

    @property
    def battery_percent(self) -> int:
        """Return battery percentage."""
        return self._battery_percent

    @property
    def status(self) -> str:
        """Return device status."""
        return STATUS_MAPPING.get(self._status_code, f"Unknown ({self._status_code})")

    @property
    def status_code(self) -> int:
        """Return raw device status code."""
        return self._status_code

    @property
    def mowing_session_active(self) -> bool:
        """Return True while a mowing session is in progress (used by the live map)."""
        return self._misc_handler.mowing_session_active

    @property
    def robot_state(self) -> dict[str, Any] | None:
        """Return where the mower stands and what it does, from its heartbeat."""
        return self._misc_handler.robot_state

    @property
    def active_codes(self) -> frozenset[int]:
        """Return the codes the mower currently reports in its heartbeat."""
        return self._misc_handler.active_codes or frozenset()

    @property
    def current_problem(self) -> str | None:
        """Return what the error or warning the mower reports now says, if any.

        An error comes before a warning, and a maintenance reminder is no
        problem. Taken from the codes its heartbeat reports as set; before the
        first heartbeat, from the last code it announced.
        """
        if self._misc_handler.active_codes is not None:
            problems = self._problem_codes(self.active_codes)
            return self._device_code_handler.describe(problems[0]) if problems else None
        handler = self._device_code_handler
        return handler.device_code_description if handler.device_code_is_error else None

    def _problem_codes(self, codes: Iterable[int]) -> list[int]:
        """The codes that hold the mower up, errors first."""
        handler = self._device_code_handler
        problems = [code for code in set(codes) if handler.is_problem(code) and code not in MAINTENANCE_REMINDER_CODES]
        return sorted(problems, key=lambda code: (not handler.is_error(code), code))

    async def clear_errors(self) -> bool:
        """Clear the errors and warnings the mower reports.

        Returns whether the mower took every clearing; True when nothing was set.
        """
        codes = set(self.active_codes)
        current = self._device_code_handler.device_code
        if isinstance(current, int):
            codes.add(current)
        cleared = True
        for code in self._problem_codes(codes):
            cleared = await self.suppress_code(code) and cleared
        return cleared

    async def suppress_code(self, code: int) -> bool:
        """Clear a code the mower reports, as one does to start despite rain protection."""
        result = await self._send_task_payload("code suppress", {"m": "a", "p": 0, "o": SUPPRESS_CODE_ACTION, "d": {"fault": code}})
        return bool(result)

    async def find_robot(self) -> bool:
        """Have the mower call out, so it can be found by its sound. It does not move."""
        result = await self._send_task_payload("find robot", {"m": "a", "p": 1, "o": FIND_ROBOT_ACTION})
        return bool(result)

    @property
    def link_module_installed(self) -> bool | None:
        """Return whether the mower has a cellular module fitted, if it is known."""
        return self._misc_handler.link_module_installed

    @property
    def link_module_plan_valid(self) -> bool | None:
        """Return whether the cellular module's data plan is valid, if it is known."""
        return self._misc_handler.link_module_plan_valid

    @property
    def wifi_signal_dbm(self) -> int | None:
        """Return the Wi-Fi signal in dBm, if the mower is on Wi-Fi."""
        return self._misc_handler.wifi_signal_dbm

    @property
    def cellular_signal_dbm(self) -> int | None:
        """Return the cellular signal in dBm, if a module on a valid plan reports one."""
        return self._misc_handler.cellular_signal_dbm

    @property
    def bluetooth_connected(self) -> bool | None:
        """Return Bluetooth connection status."""
        return self._bluetooth_connected
    
    @property
    def firmware_latest_version(self) -> str | None:
        """Return the latest available firmware version, if any."""
        return self._firmware_latest_version

    @property
    def firmware_release_notes(self) -> str | None:
        """Return the release notes of the available firmware, if any."""
        return self._firmware_release_notes

    @property
    def firmware_status_checked(self) -> bool:
        """Return whether the cloud has answered a firmware version check yet."""
        return self._firmware_status_checked

    @property
    def firmware_update_in_progress(self) -> bool:
        """Return whether the mower is downloading or installing a firmware update.

        The mower reports the update on 1:2, and also shows it in its status
        while installing. Download progress on 1:3 between 0 and 100 means an
        update is under way even before 1:2 says so, unless 1:2 already reports
        that the update ended.
        """
        if self._status_code == DeviceStatus.UPDATING:
            return True
        state = self._firmware_install_state
        if state == FirmwareInstallState.UPGRADING:
            return True
        if state in (
            FirmwareInstallState.UPGRADE_SUCCESS,
            FirmwareInstallState.UPGRADE_FAILED,
            FirmwareInstallState.CANNOT_UPGRADE,
        ):
            return False
        progress = self._firmware_download_progress
        return progress is not None and 0 < progress < 100

    @property
    def firmware_update_percentage(self) -> int | None:
        """Return how far a running firmware update has come, in percent."""
        if not self.firmware_update_in_progress:
            return None
        return self._firmware_download_progress
    
    @property
    def current_task_data(self) -> dict | None:
        """Return current task data from the TaskHandler."""
        task_handler = self._scheduling_handler._task_handler
        if task_handler.task_type is None:
            return None
        return task_handler.get_notification_data()

    @property
    def charging_status(self) -> str | None:
        """Return charging status mapped text."""
        return self._charging_status
    
    @property
    def mowing_progress_percent(self) -> float | None:
        """Return current mowing progress percentage."""
        return self._pose_coverage_handler.progress_percent

    @property
    def current_area_sqm(self) -> float | None:
        """Return current mowed area in square meters."""
        return self._pose_coverage_handler.current_area_sqm

    @property
    def total_area_sqm(self) -> float | None:
        """Return total planned area in square meters."""
        return self._pose_coverage_handler.total_area_sqm

    @property
    def mower_coordinates(self) -> tuple[int, int] | None:
        """Return current mower coordinates as (x, y) tuple."""
        x = self._pose_coverage_handler.x_coordinate
        y = self._pose_coverage_handler.y_coordinate
        if x is not None and y is not None:
            return (x, y)
        return None

    @property
    def current_segment(self) -> int | None:
        """Return current mowing segment/lane index."""
        return self._pose_coverage_handler.segment

    @property
    def mower_heading(self) -> float | None:
        """Return current mower heading in degrees."""
        return self._pose_coverage_handler.heading

    @property
    def mowing_path_history(self) -> list[list[int]]:
        """Return the trail of the running or last session ([x, y] in map units)."""
        return self._pose_coverage_handler.path_history

    @property
    def trail_revision(self) -> int:
        """Return a number that changes whenever the session's trail changed."""
        return self._pose_coverage_handler.trail_revision

    @property
    def dock_position(self) -> tuple[int, int] | None:
        """Return where the charging station stands in map units, if it is known."""
        return self._dock_position

    @property
    def dock_angle(self) -> float | None:
        """Return the direction the charging station faces, in degrees, if it is known."""
        return self._dock_angle

    @property
    def docked(self) -> bool:
        """Return whether the mower stands in its charging station.

        Only a charging state says so for certain. The mower also reports
        "not charging" away from the station, so that state, like none at all,
        leaves it to the status: one that only a docked mower has.
        """
        status = self.charging_status
        if status in ("charging", "charging_completed") or (status or "").startswith("charging_paused"):
            return True
        if status in ("not_docked", "return_to_charge"):
            return False
        return self.status.startswith("charging")

    @property
    def obstacles(self) -> list[dict[str, Any]]:
        """Return the obstacles the mower ran into on the active map.

        Each is ``{"id", "type", "x", "y", "polygon"}`` in map units, the
        position being the centre of the outline.
        """
        return list(self._obstacles)

    @property
    def ai_obstacles(self) -> list[dict[str, Any]]:
        """Return the obstacles the mower's camera recognised on the active map.

        Each is ``{"id", "type", "x", "y"}`` in map units, ``type`` naming what
        the mower took it for. Obstacles the user chose to ignore are left out.
        """
        return list(self._ai_obstacles)

    def refresh_trail(self) -> bool:
        """Read the running session's trail back from the mower. Blocking.

        The position reports only carry the newest few points, so a trail that
        was not followed from the session's start (Home Assistant started in
        the middle of it) is read back page by page, from the first point it
        lacks. A trail that lacks none is not read. Returns True when the
        trail changed.
        """
        start = self._pose_coverage_handler.first_missing_trail_index()
        if start is None:
            return False
        changed = False
        for _page in range(TRAIL_MAX_PAGES):
            result = self._cloud_device.action(
                SCHEDULING_TASK_PROPERTY.siid,
                SCHEDULING_TASK_PROPERTY.piid,
                [{"m": "g", "t": TRAIL_KEY, "d": {"idx": start, "size": TRAIL_PAGE_SIZE}}],
            )
            status, data = self._preference_response(result)
            track = data.get("track") if status in (None, 0) and isinstance(data, dict) else None
            if not track:
                break
            try:
                raw = base64.b64decode(track)
            except ValueError:
                _LOGGER.debug("Trail page at %s could not be decoded", start)
                break
            if len(raw) % 5:
                _LOGGER.debug("Trail page at %s has a broken length of %s bytes", start, len(raw))
                break
            points = [decode_pose_point(raw[i : i + 5]) for i in range(0, len(raw), 5)]
            if self._pose_coverage_handler.merge_trail(start, points):
                changed = True
            if len(points) < TRAIL_PAGE_SIZE:
                break
            start += TRAIL_PAGE_SIZE
        if changed:
            self._notify_property_change("trail", self._pose_coverage_handler.trail_revision)
        return changed

    @property
    def stop_points(self) -> list[dict[str, Any]]:
        """Return where an unfinished task left off in the zones of the active map.

        Each is ``{"zone_id", "progress", "date"}``: how far the zone got, in
        percent, and the day the task stopped as the mower words it.
        """
        return list(self._stop_points)

    def read_work_totals(self) -> dict[str, int] | None:
        """Read the totals of the work log. Blocking.

        Returns the area mowed in m², the time in minutes, the number of tasks
        and since when (unix time) they are counted, or None when the mower
        does not answer.
        """
        result = self._cloud_device.action(
            SCHEDULING_TASK_PROPERTY.siid,
            SCHEDULING_TASK_PROPERTY.piid,
            [{"m": "g", "t": WORK_TOTALS_KEY}],
        )
        status, data = self._preference_response(result)
        if status not in (None, 0) or not isinstance(data, dict):
            _LOGGER.debug("Work totals read returned nothing usable: %s", result)
            return None
        try:
            return {key: int(data[key]) for key in ("area", "time", "count", "start")}
        except (KeyError, TypeError, ValueError):
            return None

    def read_work_log(self, since: int) -> list[dict[str, Any]] | None:
        """Read the mowing tasks since a unix time, newest first. Blocking.

        Returns None when the cloud does not answer.
        """
        records = self._cloud_device.get_event_history(
            MISSION_COMPLETION_EVENT.siid, MISSION_COMPLETION_EVENT.eiid, since, WORK_LOG_LIMIT
        )
        if records is None:
            return None
        entries = work_log_entries(records)
        self._work_log_files = {entry["file"] for entry in entries if entry["file"]}
        with self._seen_lock:
            seen = list(self._seen())
        for entry in entries:
            entry["photos"] = len(self._task_photos(entry, seen))
        return entries

    def _task_file_path(self, file: str) -> str | None:
        """Where a task's file is kept, or None for a name that leads elsewhere."""
        root = os.path.realpath(os.path.join(self._hass_config_dir, "www", "dreame"))
        path = os.path.realpath(os.path.join(root, file))
        return path if path.startswith(root + os.sep) else None

    def _task_photos(self, entry: dict[str, Any], seen: list[str]) -> set[str]:
        """The photos of recognised obstacles a task met, as far as known.

        The ones seen while it ran, and those its file lists when that file is
        at hand already; nothing is downloaded for it.
        """
        start, duration = entry["start"], entry.get("duration")
        minutes = duration if isinstance(duration, (int, float)) else 0
        end = start + minutes * 60 + _TASK_END_SLACK_SECONDS
        photos = {image for image in seen if start <= _photo_time(image) <= end}
        file = entry["file"]
        if file:
            if file not in self._task_file_photos:
                path = self._task_file_path(file)
                content = _read_bytes(path) if path else None
                if content is None:
                    return photos
                try:
                    document = json.loads(content)
                    listed = parse_ai_obstacles(document.get("ai_obstacle") or [])
                except (ValueError, TypeError, AttributeError):
                    listed = []
                self._task_file_photos[file] = frozenset(obstacle["image"] for obstacle in listed if obstacle["image"])
            photos |= self._task_file_photos[file]
        return photos

    def read_work_log_details(self, file: str) -> dict[str, Any] | None:
        """Read the details of one task of the work log from its file. Blocking.

        Only a file the last read of the log listed is read. A copy kept from
        before is used, otherwise the file is downloaded and kept. Returns
        None when the file cannot be had.
        """
        if file not in self._work_log_files:
            raise ValueError("This task is not in the work log")
        local = self._task_file_path(file)
        if local is None:
            raise ValueError("This task is not in the work log")
        if not os.path.isfile(local):
            downloaded = download_file(
                file_path=file,
                get_download_url=self._cloud_device.get_file_download_url,
                hass_config_dir=self._hass_config_dir,
                timeout=15,
            )
            if not downloaded:
                return None
            local = downloaded["local_path"]
        try:
            with open(local, encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError) as ex:
            _LOGGER.warning("Work log file %s could not be read: %s", file, ex)
            return None
        if not isinstance(document, dict):
            return None
        try:
            details = work_log_details(document)
        except (KeyError, TypeError, ValueError, IndexError) as ex:
            _LOGGER.warning("Work log file %s could not be parsed: %s", file, ex)
            return None
        details["obstacles"] += self._ai_obstacles_seen_during(details, details["obstacles"])
        self._work_log_photos |= {
            obstacle["image"] for obstacle in details["obstacles"] if obstacle["kind"] == "ai" and obstacle.get("image")
        }
        for fault in details["faults"]:
            fault["description"] = self._device_code_handler.describe(fault["code"])
        return details

    def refresh_stop_points(self) -> bool:
        """Read where an unfinished task left off on the active map. Blocking.

        Returns True when the stop points changed.
        """
        vector_map = self.vector_map
        map_index = vector_map.map_index if vector_map is not None else 0
        result = self._cloud_device.action(
            SCHEDULING_TASK_PROPERTY.siid,
            SCHEDULING_TASK_PROPERTY.piid,
            [{"m": "g", "t": STOP_POINTS_KEY, "d": {"idx": map_index}}],
        )
        status, data = self._preference_response(result)
        if status not in (None, 0) or not isinstance(data, list):
            _LOGGER.debug("Stop point read returned nothing usable: %s", result)
            return False
        stop_points = []
        for entry in data:
            try:
                day_end = entry.get("bp_ts_utc")
                stop_points.append(
                    {
                        "zone_id": int(entry["rg_id"]),
                        "progress": int(entry["pro"]) / 100,
                        "date": str(entry.get("bp_ts", "")),
                        # When the day the task stopped on ended, in seconds since the epoch.
                        "day_end": int(day_end) if isinstance(day_end, (int, float)) and not isinstance(day_end, bool) else None,
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        if stop_points == self._stop_points:
            return False
        self._stop_points = stop_points
        self._notify_property_change("stop_points", stop_points)
        return True

    def refresh_mower_position(self) -> bool:
        """Read where the mower stands and which way it faces. Blocking.

        The position reports only come while the mower moves, so one standing
        on the lawn is placed by asking it. A running session has those reports,
        so it is not asked then. Returns True when it moved.
        """
        if self.mowing_session_active:
            return False
        result = self._cloud_device.action(
            SCHEDULING_TASK_PROPERTY.siid,
            SCHEDULING_TASK_PROPERTY.piid,
            [{"m": "g", "t": POSITION_KEY}],
        )
        status, data = self._preference_response(result)
        if status not in (None, 0) or not isinstance(data, dict):
            _LOGGER.debug("Position read returned nothing usable: %s", result)
            return False
        if not data.get("x") and not data.get("y") and not data.get("yaw"):
            # A mower that does not know where it is answers with nothing but zeros.
            return False
        try:
            x, y, yaw = int(data["x"]), int(data["y"]), int(data.get("yaw", 0))
        except (KeyError, TypeError, ValueError):
            return False
        before = (self.mower_coordinates, self.mower_heading)
        self._pose_coverage_handler.set_position(x, y, yaw / 255.0 * 360.0)
        if (self.mower_coordinates, self.mower_heading) == before:
            return False
        self._notify_property_change(POSE_COVERAGE_COORDINATES_PROPERTY_NAME, self._pose_coverage_handler.get_coordinates_notification_data())
        return True

    def refresh_dock_position(self) -> bool:
        """Read where the charging station stands. Blocking.

        Returns True when the position changed.
        """
        result = self._cloud_device.action(
            SCHEDULING_TASK_PROPERTY.siid,
            SCHEDULING_TASK_PROPERTY.piid,
            [{"m": "g", "t": DOCK_KEY}],
        )
        status, data = self._preference_response(result)
        dock = data.get("dock") if status in (None, 0) and isinstance(data, dict) else None
        if not isinstance(dock, dict):
            _LOGGER.debug("Station position read returned nothing usable: %s", result)
            return False
        try:
            position = (int(dock["x"]) * DOCK_POSITION_SCALE, int(dock["y"]) * DOCK_POSITION_SCALE)
            angle = int(dock.get("yaw", 0)) / DOCK_YAW_SCALE
        except (KeyError, TypeError, ValueError):
            _LOGGER.debug("Station position could not be read: %s", dock)
            return False
        if (position, angle) == (self._dock_position, self._dock_angle):
            return False
        self._dock_position = position
        self._dock_angle = angle
        self._notify_property_change("dock_position", position)
        return True

    def refresh_obstacles(self) -> bool:
        """Read the obstacles of the active map, both kinds. Blocking.

        A read that does not come through keeps what was known. Returns True
        when either list changed.
        """
        vector_map = self.vector_map
        map_index = vector_map.map_index if vector_map is not None else 0
        changed = False
        known_before = list(self._ai_obstacles)
        for key, field, parse, attribute in (
            (OBSTACLES_KEY, "obstacle", parse_obstacles, "_obstacles"),
            (AI_OBSTACLES_KEY, "obs", parse_ai_obstacles, "_ai_obstacles"),
        ):
            result = self._cloud_device.action(
                SCHEDULING_TASK_PROPERTY.siid,
                SCHEDULING_TASK_PROPERTY.piid,
                [{"m": "g", "t": key, "d": {"idx": map_index}}],
            )
            status, data = self._preference_response(result)
            if status not in (None, 0) or not isinstance(data, dict) or not isinstance(data.get(field), list):
                _LOGGER.debug("Obstacle read %s returned nothing usable: %s", key, result)
                continue
            obstacles = parse(data[field])
            if attribute == "_ai_obstacles":
                # An obstacle pushed while the list was read is not in it yet.
                obstacles += [
                    obstacle
                    for obstacle in self._ai_obstacles
                    if obstacle not in known_before and not any(_same_obstacle(obstacle, read) for read in obstacles)
                ]
            if obstacles != getattr(self, attribute):
                setattr(self, attribute, obstacles)
                changed = True
        if changed:
            self._remember_ai_obstacles(self._ai_obstacles)
            self._notify_property_change("obstacles", self._obstacles + self._ai_obstacles)
        return changed

    def _deliver_task_answer(self, value: Any) -> None:
        """Hand the mower's confirmation of a command to whoever waits for it."""
        if not isinstance(value, dict) or value.get("t") != "TASK" or not isinstance(value.get("d"), dict):
            return
        answer = value["d"]
        with self._task_answers_lock:
            waiting = self._task_answers.pop(answer.get("o"), None)
        if waiting is not None and not waiting.done():
            waiting.set_result(answer)

    async def _command(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a 2:50 action and wait for the mower to confirm it.

        Raises DreameCommandError when the command did not go out or the mower
        did not confirm it in time, and ValueError when it refused it.
        """
        operation = payload["o"]
        waiting: concurrent.futures.Future[dict[str, Any]] = concurrent.futures.Future()
        with self._task_answers_lock:
            self._task_answers[operation] = waiting
        try:
            if not await self._send_task_payload(name, payload):
                raise DreameCommandError(f"The mower did not take the {name} command")
            try:
                answer = await asyncio.wait_for(asyncio.wrap_future(waiting), MAP_EDIT_ANSWER_SECONDS)
            except TimeoutError as ex:
                raise DreameCommandError(f"The mower did not confirm the {name} command") from ex
        finally:
            with self._task_answers_lock:
                if self._task_answers.get(operation) is waiting:
                    del self._task_answers[operation]
        reason = map_edit.refusal(operation, answer)
        if reason is not None:
            raise ValueError(reason)
        return answer

    def _check_map_edit_allowed(self) -> None:
        """Refuse a change to the map while the mower is at work."""
        status = str(self.status or "")
        if self.mowing_session_active or "return" in status:
            raise ValueError("The map can only be changed while the mower is not mowing or returning")

    async def _edit_map(self, name: str, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Make changes to the current map in the mower's edit mode.

        The mower enters its edit mode, takes each change and leaves the mode
        again, also when a change is refused. The map is read again after.
        """
        self._check_map_edit_allowed()
        answers: list[dict[str, Any]] = []
        async with self._map_edit_lock:
            try:
                try:
                    await self._command("map edit start", map_edit.action(map_edit.EDIT_ENTER))
                except DreameCommandError:
                    # The mower may have entered its edit mode all the same.
                    await self._leave_edit_mode(quietly=True)
                    raise
                try:
                    for payload in payloads:
                        answers.append(await self._command(name, payload))
                except BaseException:
                    # Why the change failed matters more than whether the
                    # mower then left its edit mode.
                    await self._leave_edit_mode(quietly=True)
                    raise
                await self._leave_edit_mode(quietly=False)
            finally:
                await asyncio.get_running_loop().run_in_executor(None, self.fetch_vector_map)
        return answers

    async def _leave_edit_mode(self, *, quietly: bool) -> None:
        """Have the mower leave its edit mode; quietly only logs a failure."""
        try:
            await self._command("map edit end", map_edit.action(map_edit.EDIT_EXIT, p=1))
        except (DreameCommandError, ValueError) as ex:
            if not quietly:
                raise
            _LOGGER.warning("The mower may still be in its map edit mode: %s", ex)

    async def set_no_go_zone(
        self,
        shape: str,
        points: list[list[float]],
        radius: float | None = None,
        zone_id: int | None = None,
    ) -> int | None:
        """Draw a no-go zone, or change one; returns its id."""
        answers = await self._edit_map("no-go zone", [map_edit.no_go_zone(zone_id, shape, points, radius)])
        return answers[0].get("id", zone_id)

    async def set_ignore_obstacle_area(self, rect: list[float], area_id: int | None = None) -> int | None:
        """Draw an area where obstacles are driven over, or change one; returns its id."""
        answers = await self._edit_map("ignore obstacles area", [map_edit.ignore_obstacle_area(area_id, rect)])
        return answers[0].get("id", area_id)

    async def set_spot_area(self, rect: list[float], area_id: int | None = None) -> int | None:
        """Draw a spot area, or change one; returns its id."""
        answers = await self._edit_map("spot area", [map_edit.spot_area(area_id, rect)])
        return answers[0].get("id", area_id)

    async def set_maintenance_point(
        self, x: float, y: float, heading: float | None = None, point_id: int | None = None
    ) -> int | None:
        """Place a maintenance point, or move one; returns its id.

        Without a heading a moved point keeps the one it had, and a new one
        faces 0 degrees.
        """
        if heading is None:
            heading = self._maintenance_point_heading(point_id)
            if heading is None:
                # Not known yet: read from the mower, rather than turn the point.
                await asyncio.get_running_loop().run_in_executor(None, self._read_current_point_headings)
                heading = self._maintenance_point_heading(point_id)
            if heading is None:
                raise ValueError("Which way the maintenance point faces is not known yet; give its heading")
        answers = await self._edit_map("maintenance point", [map_edit.maintenance_point(point_id, x, y, heading)])
        return answers[0].get("id", point_id)

    def _maintenance_point_heading(self, point_id: int | None) -> float | None:
        """The heading a maintenance point of the current map has: 0 for a new one, None when not known."""
        vector_map = self.vector_map
        if point_id is None or vector_map is None:
            return 0.0
        for point in vector_map.maintenance_points:
            if point.point_id == point_id:
                return point.heading
        return 0.0

    def _read_current_point_headings(self) -> None:
        """Read the current map from the mower for the headings of its maintenance points. Blocking."""
        vector_map = self.vector_map
        if vector_map is None:
            return
        fresh = self._read_device_map(vector_map.map_index)
        if fresh is None:
            return
        headings = {point.point_id: point.heading for point in fresh.maintenance_points}
        self._point_headings[vector_map.map_index] = (fresh.md5sum or "", headings)
        for point in vector_map.maintenance_points:
            if point.point_id in headings:
                point.heading = headings[point.point_id]

    async def delete_map_item(self, kind: str, item_id: int) -> None:
        """Delete a zone, path, no-go zone, spot area, maintenance point or ignore-obstacles area."""
        await self._edit_map("map item delete", [map_edit.delete_item(kind, item_id)])

    async def rename_zone(self, zone_id: int, name: str) -> None:
        await self._edit_map("zone rename", [map_edit.rename_zone(zone_id, name)])

    async def split_zone(self, zone_id: int, line: list[float]) -> list[int]:
        """Split a zone along a line across it; returns the two zones' ids."""
        answers = await self._edit_map("zone split", [map_edit.split_zone(zone_id, line)])
        return list(answers[0].get("ids") or [])

    async def merge_zones(self, zone_ids: list[int]) -> int | None:
        """Merge two neighbouring zones; returns the id of the zone they make."""
        answers = await self._edit_map("zone merge", [map_edit.merge_zones(zone_ids)])
        return answers[0].get("id")

    async def rename_map(self, map_id: int, name: str) -> None:
        if not self._validate_map_id(map_id):
            raise ValueError(f"There is no map {map_id}")
        payload = map_edit.action(
            map_edit.RENAME_MAP, {"idx": self._map_index_from_id(map_id), "name": map_edit.checked_name(name)}
        )
        self._check_map_edit_allowed()
        async with self._map_edit_lock:
            await self._command("map rename", payload)
        await asyncio.get_running_loop().run_in_executor(None, self.fetch_vector_map)

    async def backup_map(self) -> None:
        """Back the current map up, replacing the backup it had."""
        index = self._current_map_index()
        await self._edit_map("map backup", [map_edit.action(map_edit.BACKUP_MAP, {"idx": index})])
        self._map_backups.add(index)

    async def restore_map(self) -> None:
        """Put the current map back as its backup has it."""
        await self._edit_map("map restore", [map_edit.action(map_edit.RESTORE_MAP, {"idx": self._current_map_index()})])

    @property
    def deleted_maps(self) -> list[int]:
        """Return the map slots, numbered from 1, that hold no map but a backup of a deleted one.

        Taken from the mower's own list of its slots, not from the maps that
        could be read.
        """
        if self._held_map_slots is None:
            return []
        return [index + 1 for index in sorted(self._map_backups - self._held_map_slots)]

    async def restore_deleted_map(self, slot: int) -> None:
        """Bring a deleted map back into its empty slot, numbered from 1, from its backup.

        The mower takes it in its edit mode, which it enters on the current
        map; the map in use stays the same.
        """
        if slot not in self.deleted_maps:
            raise ValueError(f"Map slot {slot} holds no backup of a deleted map")
        # The slot is checked once more with the mower: a backup put back
        # into a slot that holds a map would overwrite that map.
        if slot not in await asyncio.get_running_loop().run_in_executor(None, self._read_deleted_maps):
            raise ValueError(f"Map slot {slot} holds no backup of a deleted map")
        await self._edit_map("deleted map restore", [map_edit.action(map_edit.RESTORE_MAP, {"idx": slot - 1})])
        await self._read_maps_once_settled(lambda held: slot - 1 in held)

    async def delete_map(self, map_id: int) -> None:
        """Delete a map with everything on it; it keeps its backup."""
        if not self._validate_map_id(map_id):
            raise ValueError(f"There is no map {map_id}")
        self._check_map_edit_allowed()
        index = self._map_index_from_id(map_id)
        async with self._map_edit_lock:
            await self._command("map delete", map_edit.action(map_edit.DELETE_MAP, {"idx": index}))
        await self._read_maps_once_settled(lambda held: index not in held)

    async def _read_maps_once_settled(self, settled: Callable[[set[int]], bool]) -> None:
        """Read the maps back once the mower's list of them shows a change it confirmed.

        `settled` is given the indexes of the slots that hold a map. The maps
        are read back also when the list never shows the change in time.
        """
        loop = asyncio.get_running_loop()

        def held() -> set[int] | None:
            try:
                with self._map_read_lock:
                    slots = self._read_map_slots()
            except Exception as ex:
                _LOGGER.debug("Failed to read the map slots: %s", ex)
                return None
            return None if slots is None else {slot["index"] for slot in slots}

        try:
            for attempt in range(MAP_SLOTS_SETTLE_ATTEMPTS if self._online else 0):
                if attempt:
                    await asyncio.sleep(MAP_SLOTS_SETTLE_SECONDS)
                indexes = await loop.run_in_executor(None, held)
                if indexes is not None and settled(indexes):
                    break
        finally:
            await loop.run_in_executor(None, self.fetch_vector_map)

    def _read_deleted_maps(self) -> list[int]:
        """Read the mower's slots and return those keeping a deleted map's backup. Blocking."""
        with self._map_read_lock:
            self._read_map_slots()
        return self.deleted_maps

    def _current_map_index(self) -> int:
        map_id = self.current_map_id
        if map_id is None:
            raise ValueError("No map is in use")
        return self._map_index_from_id(map_id)

    def _add_ai_obstacle(self, value: Any) -> None:
        """Add an obstacle the camera recognised while mowing to the known ones."""
        if not isinstance(value, dict) or value.get("type") != "ai" or not isinstance(value.get("obs"), list):
            return
        added = [
            obstacle
            for obstacle in parse_ai_obstacles([value["obs"]])
            if not any(_same_obstacle(known, obstacle) for known in self._ai_obstacles)
        ]
        if added:
            self._ai_obstacles = [*self._ai_obstacles, *added]
            self._remember_ai_obstacles(added)
            self._notify_property_change("obstacles", self._obstacles + self._ai_obstacles)

    async def ignore_ai_obstacle(self, obstacle_id: int | str) -> None:
        """Have the mower forget an obstacle its camera recognised.

        The mower drops it from its list for good; there is no taking it back.
        Refused while the mower mows. Raises ValueError when the mower refuses.
        """
        robot = self.robot_state or {}
        if robot.get("main_state") == AI_OBSTACLE_MOWING_MAIN_STATE and robot.get("sub_state") == AI_OBSTACLE_MOWING_SUB_STATE:
            raise ValueError("An obstacle can only be ignored while the mower does not mow")
        # The mower is sent its own id as it gave it, a string or a number.
        known = next(
            (obstacle["id"] for obstacle in self._ai_obstacles if obstacle.get("ignorable") and str(obstacle["id"]) == str(obstacle_id)),
            obstacle_id,
        )
        result = await self._send_task_payload(
            "obstacle ignore", {"m": "s", "t": AI_OBSTACLES_KEY, "d": {"id": known, "type": "ignore"}}
        )
        out = result.get("out") if isinstance(result, dict) else None
        answer = out[0].get("obs") if isinstance(out, list) and out and isinstance(out[0], dict) else None
        if not isinstance(answer, dict) or answer.get("res") != 1:
            error = answer.get("error") if isinstance(answer, dict) else None
            if error == AI_OBSTACLE_UNKNOWN:
                raise ValueError("The mower does not know this obstacle (any more)")
            raise ValueError(f"The mower did not ignore the obstacle (error {error})")
        self._ai_obstacles = [
            obstacle
            for obstacle in self._ai_obstacles
            if not obstacle.get("ignorable") or str(obstacle["id"]) != str(obstacle_id)
        ]
        self._notify_property_change("obstacles", self._obstacles + self._ai_obstacles)

    def _photo_dir(self) -> str:
        """Where this mower's obstacle photos are kept."""
        return os.path.join(self._hass_config_dir, *AI_OBSTACLE_PHOTO_DIR, str(self._device_id))

    def _seen_path(self) -> str:
        return os.path.join(self._photo_dir(), AI_OBSTACLES_SEEN_FILE)

    def _seen(self) -> dict[str, dict[str, Any]]:
        """The recognised obstacles seen before, read from where they are kept."""
        if self._seen_ai_obstacles is None:
            content = _read_bytes(self._seen_path())
            seen: dict[str, dict[str, Any]] = {}
            try:
                for obstacle in json.loads(content) if content else []:
                    if (
                        isinstance(obstacle, dict)
                        and isinstance(obstacle.get("image"), str)
                        and all(isinstance(obstacle.get(key), (int, float)) for key in ("x", "y", "type"))
                    ):
                        seen[obstacle["image"]] = obstacle
            except (ValueError, TypeError) as ex:
                _LOGGER.warning("The obstacles seen before could not be read and start over: %s", ex)
            self._seen_ai_obstacles = seen
        return self._seen_ai_obstacles

    def _remember_ai_obstacles(self, obstacles: list[dict[str, Any]]) -> None:
        """Keep the recognised obstacles with a photo, the latest ones only."""
        with self._seen_lock:
            seen = self._seen()
            new = [obstacle for obstacle in obstacles if obstacle.get("image") and obstacle["image"] not in seen]
            if not new:
                return
            for obstacle in new:
                seen[obstacle["image"]] = dict(obstacle)
            while len(seen) > AI_OBSTACLES_SEEN_LIMIT:
                seen.pop(min(seen, key=_photo_time))
            _write_bytes(self._seen_path(), json.dumps(list(seen.values())).encode())

    def _ai_obstacles_seen_during(
        self, details: dict[str, Any], listed: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """The recognised obstacles seen while a task ran that its file leaves out."""
        start, end = details.get("start"), details.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            return []
        images = {obstacle.get("image") for obstacle in listed}
        with self._seen_lock:
            seen = list(self._seen().values())
        return [
            {"kind": "ai", **obstacle}
            for obstacle in seen
            if obstacle["image"] not in images and start <= _photo_time(obstacle["image"]) <= end
        ]

    def read_obstacle_photo(self, image: str) -> dict[str, Any] | None:
        """Fetch the photo the mower took of a recognised obstacle. Blocking.

        Only a photo of an obstacle the mower reports now, or of one in a task
        of the work log read before, is fetched. A photo fetched before is
        read back from where it was kept. Otherwise the mower sends it through
        the cloud over its own connection, so a try the cloud gave up on is
        repeated a few times. Returns the JPEG as base64, with the boxes around
        what was recognised, or None when the photo could not be had.
        """
        known = {obstacle.get("image") for obstacle in self._ai_obstacles} | self._work_log_photos
        if image not in known or not _PHOTO_NAME.fullmatch(image):
            raise ValueError("The mower reports no obstacle with this photo")
        kept = os.path.join(self._photo_dir(), f"{image}.jpg")
        # A photo kept before needs no wait for another one being fetched.
        photo = _read_bytes(kept)
        if photo is not None:
            return {"image": base64.b64encode(photo).decode("ascii"), **obstacle_photo_boxes(photo)}
        with self._photo_lock:
            photo = _read_bytes(kept)
            for attempt in range(AI_OBSTACLE_PHOTO_TRIES):
                if photo is not None:
                    break
                photo, again = self._cloud_device.get_device_file(
                    f"{image}.jpg", AI_OBSTACLE_PHOTO_KIND, AI_OBSTACLE_PHOTO_TIMEOUT
                )
                if photo is not None:
                    _write_bytes(kept, photo)
                elif not again:
                    return None
                else:
                    _LOGGER.debug("Photo %s not sent yet (try %s)", image, attempt + 1)
            if photo is None:
                return None
        return {"image": base64.b64encode(photo).decode("ascii"), **obstacle_photo_boxes(photo)}

    def _note_session_state(self) -> None:
        """Start a new trail when a mowing session starts.

        The trail's point numbers start over with every session, but a session
        that ended early leaves points the next one's numbers would only reach
        later, so the trail is cleared on the start itself. The first task
        status after a restart says nothing about a start: a session already
        running keeps the trail it is rebuilding.
        """
        active = self.mowing_session_active
        if active and self._session_was_active is False:
            self._pose_coverage_handler.clear_path_history()
        self._session_was_active = active

    def _resolved_vector_map(self) -> MowerVectorMap | None:
        """Return the geometry for the active map when multi-map batch data is available."""
        if self._vector_map is None:
            return None

        parsed_maps = getattr(self._vector_map, "maps", {})
        if not isinstance(parsed_maps, dict):
            return self._vector_map

        map_id = self.current_map_id
        if map_id is not None and map_id in parsed_maps:
            return parsed_maps[map_id]

        fallback_map_id = getattr(self._vector_map, "map_id", None)
        if isinstance(fallback_map_id, int) and fallback_map_id in parsed_maps:
            return parsed_maps[fallback_map_id]

        return self._vector_map

    @property
    def vector_map(self) -> MowerVectorMap | None:
        """Return the vector map of the current map."""
        return self._resolved_vector_map()

    @property
    def other_vector_maps(self) -> list[MowerVectorMap]:
        """Return the vector maps of every map but the current one."""
        current = self._resolved_vector_map()
        maps = getattr(self._vector_map, "maps", None) if self._vector_map is not None else None
        if not isinstance(maps, dict):
            return []
        return [vector_map for _map_id, vector_map in sorted(maps.items()) if vector_map is not current]

    @property
    def available_maps(self) -> list[dict[str, Any]]:
        """Return a descriptor for every map the mower holds."""
        if self._vector_map is None:
            return []

        return [
            {
                "id": map_entry.map_id,
                "index": map_entry.map_index,
                "name": map_entry.name,
                "area": map_entry.total_area,
                "has_backup": map_entry.map_index in self._map_backups,
            }
            for map_entry in self._vector_map.available_maps
        ]

    @property
    def current_map_id(self) -> int | None:
        """Return the currently selected map, if that state is known."""
        if self._current_map_id is not None:
            return self._current_map_id

        if self._vector_map is None:
            return None

        vector_map_current_id = getattr(self._vector_map, "current_map_id", None)
        if isinstance(vector_map_current_id, int) and not isinstance(vector_map_current_id, bool):
            return vector_map_current_id

        available_maps = getattr(self._vector_map, "available_maps", None)
        if isinstance(available_maps, list) and len(available_maps) == 1:
            map_id = getattr(available_maps[0], "map_id", None)
            if isinstance(map_id, int) and not isinstance(map_id, bool):
                return map_id

        return None

    @property
    def cutting_height(self) -> float | None:
        """Return the current map's cutting height in cm, if it has been read."""
        return self._cutting_height

    @property
    def zone_cutting_heights(self) -> dict[int, float]:
        """Return the per-zone cutting heights in cm known for the current map."""
        return dict(self._zone_cutting_heights)

    @property
    def edge_mowing_settings(self) -> dict[str, bool] | None:
        """Return the current map's edge mowing settings, if they have been read."""
        return None if self._edge_mowing_settings is None else dict(self._edge_mowing_settings)

    @property
    def zone_edge_mowing_settings(self) -> dict[int, dict[str, bool]]:
        """Return the per-zone edge mowing settings known for the current map."""
        return {zone_id: dict(settings) for zone_id, settings in self._zone_edge_mowing_settings.items()}

    @property
    def model(self) -> str | None:
        """Return the model identifier, once known."""
        return self._model

    @property
    def mowing_settings(self) -> dict[int, dict[str, Any]]:
        """Return every setting of the current map's records, by area id.

        Area 0 is the map-wide record; the others are the zones that hold one.
        """
        camera = has_camera(self._model)
        return {area_id: self._record_mowing_settings(record, camera) for area_id, record in self._mowing_records.items()}

    @property
    def mowing_direction(self) -> dict[str, int] | None:
        """Return the current map's mowing direction, if it has been read."""
        return None if self._mowing_direction is None else dict(self._mowing_direction)

    @property
    def zone_mowing_directions(self) -> dict[int, dict[str, int]]:
        """Return the per-zone mowing directions known for the current map."""
        return {zone_id: dict(direction) for zone_id, direction in self._zone_mowing_directions.items()}

    @property
    def mowing_preference_mode(self) -> MowingPreferenceMode | None:
        """Return whether the current map applies map-wide or per-zone preferences."""
        return self._mowing_preference_mode

    @property
    def schedules(self) -> list[dict[str, Any]] | None:
        """Return the current map's schedule slots, if they have been read."""
        if self._schedules is None:
            return None
        return [deepcopy(schedule) for schedule in self._schedules]

    @property
    def task_target_map_id(self) -> int | None:
        """Return the map identifier targeted by the active task, if present."""
        task_handler = self._scheduling_handler._task_handler
        if task_handler.region_id:
            return int(task_handler.region_id[0])

        return None

    def fetch_vector_map(self) -> bool:
        """Read the mower's maps.

        The MAP.* keys of the batch device data hold a copy of the maps that is
        only brought up to date from time to time, and keep a slot for every map
        the mower can hold, whether it holds one or not. The mower itself reports
        which slots hold a map and the hash of each, so a cached map is only used
        while its hash still matches, and any other is read from the mower. When
        the mower does not answer, the cached maps are used as they stand.

        Returns:
            True if map data was updated, False otherwise.
        """
        with self._map_read_lock:
            try:
                updated = self._read_vector_map()
            except Exception as ex:
                _LOGGER.warning("Failed to fetch the vector map: %s", ex)
                return False

        if not updated:
            return False

        if self._online:
            # Only the mower knows which of its maps is current.
            self.refresh_current_map_id()
        active_vector_map = self._resolved_vector_map() or self._vector_map
        if active_vector_map is not None:
            _LOGGER.debug(
                "Vector map updated: %d zones, %d paths, boundary=%s",
                len(active_vector_map.zones),
                len(active_vector_map.paths),
                active_vector_map.boundary,
            )
        self._notify_property_change("vector_map_updated", True)
        return True

    def load_stored_vector_map(self) -> bool:
        """Take the maps from the copy the cloud keeps, without asking the mower. Blocking.

        One request, so a mower on a slow link still shows its maps at once;
        fetch_vector_map brings them up to date from the mower afterwards.
        Returns True when maps were taken.
        """
        batch_data = self._cloud_device.get_batch_device_datas([]) or {}
        vector_map = parse_batch_map_data(batch_data)
        if vector_map is None:
            return False
        with self._map_read_lock:
            if self._vector_map is not None:
                # A read from the mower got there first; it is the newer one.
                return False
            self._vector_map = vector_map
        self._notify_property_change("vector_map_updated", True)
        return True

    def refresh_changed_vector_map(self) -> bool:
        """Read the mower's maps back only when one of them changed.

        The mower does not announce an edited map, so noticing one takes asking.
        The hash of every map comes out of a single read each, and the maps are
        only read back once one of the hashes, or the set of maps, moved.

        A switch of the active map made outside Home Assistant leaves every
        hash as it was, and the signs the mower gives of it do not name the
        new map. The slot read that carries the hashes also flags the active
        map, so that flag is applied even when nothing has to be read back.

        Returns:
            True if map data was read back and updated, False otherwise.
        """
        if not self._online:
            # An offline mower cannot be asked; it is checked again next time.
            return False

        with self._map_read_lock:
            try:
                slots = self._read_map_slots()
            except Exception as ex:
                _LOGGER.debug("Failed to read the map hashes: %s", ex)
                return False

        if slots is None:
            return False

        if self._map_hashes is not None and {
            slot["index"]: slot["hash"] for slot in slots
        } == self._map_hashes:
            for slot in slots:
                if slot["current"]:
                    self._apply_current_map_id(self._map_id_from_index(slot["index"]))
                    break
            return False

        return self.fetch_vector_map()

    def _read_vector_map(self) -> bool:
        """Read the maps, preferring the mower's own over the cloud copy."""
        batch_data = self._cloud_device.get_batch_device_datas([]) or {}
        slots = None
        if self._online:
            try:
                slots = self._read_map_slots()
            except Exception as ex:
                _LOGGER.debug("Failed to read the map slots: %s", ex)
        else:
            # An offline mower cannot be asked; its cloud copy has to do.
            _LOGGER.debug("Device %s is offline; using the stored copy of its maps", self._device_id)

        if slots is None:
            vector_map = parse_batch_map_data(batch_data)
            if vector_map is None:
                _LOGGER.debug("Failed to parse batch map data")
                return False

            self._vector_map = vector_map
            return True

        cached_maps = {vmap.map_index: vmap for vmap in parse_cached_maps(batch_data)}
        maps: list[MowerVectorMap] = []
        hashes: dict[int, str] = {}
        for slot in slots:
            map_index = slot["index"]
            cached = cached_maps.get(map_index)
            vmap: MowerVectorMap
            if cached is not None and cached.md5sum == slot["hash"] and self._apply_point_headings(cached, map_index, slot["hash"]):
                vmap = cached
                hashes[map_index] = slot["hash"]
            else:
                fresh = self._read_device_map(map_index)
                if fresh is not None:
                    vmap = fresh
                    hashes[map_index] = fresh.md5sum or slot["hash"]
                    self._point_headings[map_index] = (
                        hashes[map_index],
                        {point.point_id: point.heading for point in fresh.maintenance_points},
                    )
                elif cached is not None and has_map(cached):
                    # A stale map still beats none, and so does one lacking the
                    # headings of its maintenance points. Its own hash is kept,
                    # or none when only the headings are missing, so the next
                    # check reads the map again.
                    vmap = cached
                    hashes[map_index] = "" if cached.md5sum == slot["hash"] else cached.md5sum or ""
                else:
                    continue

            if has_map(vmap):
                maps.append(vmap)

        vector_map = assemble_vector_map(maps)
        if vector_map is None:
            if slots:
                _LOGGER.debug("None of the mower's maps could be read")
                return False

            # The mower holds no map at all, for instance once its last one was
            # deleted, so none is offered any longer.
            _LOGGER.debug("The mower reports no maps")

        self._vector_map = vector_map
        self._map_hashes = hashes
        return True

    def _apply_point_headings(self, vmap: MowerVectorMap, map_index: int, md5sum: str) -> bool:
        """Give a stored copy of a map the headings of its maintenance points.

        The stored copy leaves them out. They are taken from the mower's own
        copy of the same version of the map; False when none was read yet,
        so the map is to be read from the mower.
        """
        if not vmap.maintenance_points:
            return True
        known = self._point_headings.get(map_index)
        if known is None or known[0] != md5sum:
            return False
        for point in vmap.maintenance_points:
            point.heading = known[1].get(point.point_id)
        return True

    def _read_device_map(self, map_index: int) -> MowerVectorMap | None:
        """Read one map from the mower and parse it, or None when that fails."""
        read = self._read_map_document(map_index)
        if read is None:
            return None

        document, md5sum = read
        try:
            return parse_mower_map(convert_device_map(document, map_index, md5sum))
        except (KeyError, TypeError, ValueError, IndexError) as ex:
            _LOGGER.warning("Map index %s could not be parsed: %s", map_index, ex)
            return None

    def _read_map_slots(self) -> list[dict[str, Any]] | None:
        """Read the map slots that hold a map, with the hash of each and whether it is the active one.

        Returns None when the mower does not report its map slots.
        """
        result = self._cloud_device.action(
            SCHEDULING_TASK_PROPERTY.siid,
            SCHEDULING_TASK_PROPERTY.piid,
            [self._build_get_map_list_payload()],
        )
        status, rows = self._preference_response(result)
        if status not in (None, 0) or not isinstance(rows, list):
            _LOGGER.debug("Map list read returned no map slots: %s", result)
            return None

        slots: list[dict[str, Any]] = []
        backups: set[int] = set()
        for row in rows:
            # A slot row is [index, is current, holds a map, has a backup, ...].
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue

            try:
                map_index = int(row[0])
            except (TypeError, ValueError):
                continue

            if len(row) > 3 and row[3]:
                backups.add(map_index)

            if not row[2]:
                continue

            info = self._read_map_info(map_index)
            if info is None:
                return None

            slots.append({"index": map_index, "hash": info[0], "current": bool(row[1])})

        self._map_backups = backups
        self._held_map_slots = {slot["index"] for slot in slots}
        return slots

    def _read_map_info(self, map_index: int) -> tuple[str, int] | None:
        """Read the hash and byte length of one map.

        Naming the map is also what the data reads that follow continue from.
        """
        result = self._cloud_device.action(
            SCHEDULING_TASK_PROPERTY.siid,
            SCHEDULING_TASK_PROPERTY.piid,
            [self._build_get_map_info_payload(map_index)],
        )
        status, data = self._preference_response(result)
        if status not in (None, 0) or not isinstance(data, dict):
            _LOGGER.debug("Failed to read the info of map index %s: %s", map_index, result)
            return None

        try:
            return str(data["hash"]), int(data["size"])
        except (KeyError, TypeError, ValueError):
            _LOGGER.debug("Info of map index %s carries no hash and size: %s", map_index, data)
            return None

    def _read_map_document(self, map_index: int) -> tuple[dict[str, Any], str] | None:
        """Read one map document from the mower, alongside the hash it is held under.

        The mower counts the document in bytes, so the chunks are put back
        together as bytes and only read as text once the whole document is in.
        """
        info = self._read_map_info(map_index)
        if info is None:
            return None

        md5sum, length = info
        chunks: list[bytes] = []
        offset = 0
        while offset < length:
            result = self._cloud_device.action(
                SCHEDULING_TASK_PROPERTY.siid,
                SCHEDULING_TASK_PROPERTY.piid,
                [self._build_get_map_data_payload(offset, min(length - offset, MAP_CHUNK_SIZE))],
            )
            status, data = self._preference_response(result)
            if status not in (None, 0) or not isinstance(data, dict) or not isinstance(data.get("data"), str):
                _LOGGER.warning("Failed to read map index %s at byte %d: %s", map_index, offset, result)
                return None

            chunk = data["data"].encode("utf-8")
            # The mower reports how many bytes the chunk covers, which is what
            # the next read continues from.
            try:
                chunk_length = int(data["size"])
            except (KeyError, TypeError, ValueError):
                chunk_length = len(chunk)

            if chunk_length <= 0:
                _LOGGER.warning("Map index %s read at byte %d returned no bytes: %s", map_index, offset, data)
                return None

            chunks.append(chunk[:chunk_length])
            offset += chunk_length

        # The hash is that of the document itself, so it proves the chunks came
        # from the map named and add up to all of it: the data reads continue
        # whichever map was named last, by this client or any other.
        raw_document = b"".join(chunks)
        if hashlib.md5(raw_document).hexdigest() != md5sum:
            _LOGGER.warning("Map index %s did not read back intact", map_index)
            return None

        try:
            document = json.loads(raw_document.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as ex:
            _LOGGER.warning("Map index %s could not be read: %s", map_index, ex)
            return None

        if not isinstance(document, dict):
            _LOGGER.warning("Map index %s is not a map document: %s", map_index, document)
            return None

        return document, md5sum

    async def fetch_firmware_status(self) -> bool:
        """Fetch firmware update availability from the cloud OTA service.

        Queries checkDeviceVersion, which compares the installed firmware
        against the latest published version for the model and reports
        ``hasNewFirmware`` plus the available ``newVersion``. This is the
        authoritative source of update availability: the device's own 1:2
        property only flips once an OTA has actually been assigned to it, so it
        cannot surface a pending update on its own.

        Returns:
            True if the firmware status was fetched and applied, False otherwise.
        """
        try:
            data = await asyncio.get_event_loop().run_in_executor(
                None,
                self._cloud_device.check_device_version,
            )
        except Exception as ex:
            _LOGGER.warning("Failed to fetch firmware status: %s", ex)
            return False

        if not isinstance(data, dict):
            _LOGGER.debug("checkDeviceVersion returned no data: %r", data)
            return False

        available = bool(data.get("hasNewFirmware"))
        latest = str(data["newVersion"]) if available and data.get("newVersion") else None
        description = data.get("description")

        # The service reports the version the device runs now, which moves on
        # after an update even while the device list still names the old one.
        current = data.get("curVersion")
        if current and str(current) != self._firmware:
            self._firmware = str(current)
            self._notify_property_change(PROPERTY_FIRMWARE, self._firmware)

        self._firmware_status_checked = True
        self._firmware_latest_version = latest
        notes = str(description).strip() if available and description else ""
        self._firmware_release_notes = notes or None
        if self._firmware_new_available != available:
            self._firmware_new_available = available
            self._notify_property_change("firmware_update_available", available)
            _LOGGER.debug(
                "Firmware update available: %s (installed=%s, latest=%s)",
                available,
                data.get("curVersion"),
                latest,
            )
        return True

    async def start_firmware_update(self) -> bool:
        """Ask the cloud to push the available firmware update to the mower.

        The mower then downloads and installs it on its own and reports its
        progress on 1:2 and 1:3. It has to be at rest with enough charge left:
        waiting in standby or on the station, and at or above
        FIRMWARE_UPDATE_MIN_BATTERY_PERCENT.

        Raises:
            ValueError: No update is available, one is already running, or the
                mower is not in a state it can update from.
            DreameCommandError: The request did not reach the OTA service, or the
                service turned it down.
        """
        if not self._firmware_new_available:
            raise ValueError("No firmware update is available for the mower")
        if self.firmware_update_in_progress:
            raise ValueError("The mower is already updating its firmware")
        if not self._online:
            raise ValueError("The mower is offline")
        if self._status_code not in FIRMWARE_UPDATE_ALLOWED_STATUSES:
            raise ValueError("The mower can only update while in standby or on the charging station")
        if self._battery_percent < FIRMWARE_UPDATE_MIN_BATTERY_PERCENT:
            raise ValueError(
                f"The mower needs at least {FIRMWARE_UPDATE_MIN_BATTERY_PERCENT}% battery to update its firmware"
            )

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                self._cloud_device.manual_firmware_update,
            )
        except Exception as ex:
            raise DreameCommandError(f"Failed to request the firmware update: {ex}") from ex

        if not isinstance(response, dict):
            raise DreameCommandError("The firmware update request got no answer")
        if response.get("code") != 0:
            raise DreameCommandError(
                f"The firmware update was refused: {response.get('msg') or response.get('code')}"
            )

        _LOGGER.info("Requested firmware update to %s", self._firmware_latest_version)
        return True

    def _set_online(self, online: bool) -> None:
        """Update the cached online flag and notify listeners on change."""
        if online:
            # Any online signal clears the offline debounce immediately.
            self._offline_poll_count = 0
        if self._online == online:
            return
        self._online = online
        if online:
            _LOGGER.info("Device %s is back online", self._device_id)
        else:
            _LOGGER.info("Device %s reported offline by the cloud", self._device_id)
        self._notify_property_change("online", online)

    @staticmethod
    def _online_from_heartbeat(props: Any) -> bool | None:
        """Derive online state from a 1:1 connectivity heartbeat response.

        The connectivity uplink is encoded in the heartbeat byte array: the
        device is considered online while either byte 17 is non-zero or byte 18
        has its high bit set. Returns None when the response is malformed so the
        caller can retry instead of assuming the device is offline.
        """
        if not isinstance(props, list) or not props:
            return None
        entry = props[0]
        if not isinstance(entry, dict) or entry.get("code", -1) != 0:
            return None
        value = entry.get("value")
        if not isinstance(value, (list, tuple)) or len(value) <= 18:
            return None
        return int(value[17]) != 0 or int(value[18]) >= 128

    async def async_check_reachable(self) -> bool:
        """Return whether the device answers at all, asking it once.

        The cloud may list a device as connected that still does not answer:
        every command to it times out. One heartbeat read tells, and a device
        that does not answer it is taken as offline.
        """
        if not self._online:
            return False
        loop = asyncio.get_event_loop()
        try:
            props = await loop.run_in_executor(
                None,
                lambda: self._cloud_device.get_properties(
                    [{"siid": PROPERTY_1_1.siid, "piid": PROPERTY_1_1.piid}]
                ),
            )
        except (TimeoutError, ConnectionError, RuntimeError) as ex:
            _LOGGER.debug("Device %s does not answer: %s", self._device_id, ex)
            self._set_online(False)
            return False
        online = self._online_from_heartbeat(props)
        if online is False:
            self._set_online(False)
            return False
        # A malformed answer still is an answer.
        return True

    async def async_update_online_status(self) -> bool:
        """Poll the cloud connectivity heartbeat and update the online flag.

        Reads property 1:1 and inspects its connectivity bytes. A device that has
        dropped off the cloud either returns an offline error or reports stale
        connectivity bytes. Any online result marks the device back online at
        once; an offline result only flips the device offline after
        ONLINE_OFFLINE_DEBOUNCE_POLLS consecutive offline polls, so a single
        missed heartbeat does not flap entities to unavailable.
        """
        loop = asyncio.get_event_loop()
        online: bool | None = None
        # The cloud's device list says at once when the device is not connected
        # to it; reading the heartbeat of such a device only times out.
        try:
            device_info = await loop.run_in_executor(None, self._cloud_device.get_device_info)
        except Exception as ex:  # noqa: BLE001 - the heartbeat decides then
            _LOGGER.debug("Device list read failed: %s", ex)
            device_info = None
        listed_offline = isinstance(device_info, dict) and device_info.get("online") is False
        for _attempt in range(0 if listed_offline else 3):
            try:
                props = await loop.run_in_executor(
                    None,
                    lambda: self._cloud_device.get_properties(
                        [{"siid": PROPERTY_1_1.siid, "piid": PROPERTY_1_1.piid}]
                    ),
                )
            except (TimeoutError, ConnectionError, RuntimeError) as ex:
                _LOGGER.debug("Online heartbeat attempt failed: %s", ex)
                continue
            online = self._online_from_heartbeat(props)
            if online is not None:
                break

        if online:
            # The poll reads the same heartbeat the mower pushes, so its signal
            # bytes keep the link readings fresh between pushes.
            self._misc_handler.update_signal(props[0]["value"], self._notify_property_change)
            self._set_online(True)
            return True

        # Offline determination: debounce across consecutive polls so a
        # transient cloud hiccup doesn't briefly mark the device unavailable.
        self._offline_poll_count += 1
        if self._offline_poll_count >= ONLINE_OFFLINE_DEBOUNCE_POLLS:
            self._set_online(False)
        return False

    @property
    def device_id(self) -> str:
        """Return device ID."""
        return self._device_id

    @property
    def username(self) -> str:
        """Return username for authentication."""
        return self._username

    @property
    def account_type(self) -> str:
        """Return account type."""
        return self._account_type

    @property
    def country(self) -> str:
        """Return country."""
        return self._country

    @property
    def cloud_device(self) -> DreameMowerCloudDevice:
        """Return the cloud device instance."""
        return self._cloud_device

    def register_property_callback(self, callback: Callable[[str, Any], None]) -> None:
        """Register callback for property changes."""
        self._property_callbacks.append(callback)

    def unregister_property_callback(self, callback: Callable[[str, Any], None]) -> None:
        """Unregister a previously registered property change callback."""
        if callback in self._property_callbacks:
            self._property_callbacks.remove(callback)

    def _notify_property_change(self, property_name: str, value: Any) -> None:
        """Notify all registered callbacks of property changes."""
        if property_name == PROPERTY_1_1_TASK_STATUS_NAME:
            self._note_session_state()
        for callback in self._property_callbacks:
            try:
                callback(property_name, value)
            except Exception as ex:
                _LOGGER.exception("Error in property callback: %s", ex)

    async def fetch_device_info(self) -> dict[str, Any] | None:
        """Fetch device information from devices_list endpoint."""
        try:
            # Make REST API call to get device info from devices_list
            loop = asyncio.get_event_loop()
            device_info = await loop.run_in_executor(
                None,
                self._cloud_device.get_device_info
            )
            
            if device_info:
                # Update device state from devices_list response
                self._update_device_state_from_info(device_info)
                return device_info
            else:
                _LOGGER.warning("No device info returned for device %s", self._device_id)
                
        except Exception as ex:
            _LOGGER.error("Failed to fetch device info: %s", ex)
            
        return None

    def _update_device_state_from_info(self, device_info: dict[str, Any]) -> None:
        """Update internal device state from devices_list response.
        
        Args:
            device_info: Device information from devices_list endpoint
        """
        try:
            # Update firmware version
            old_firmware = self._firmware
            if "ver" in device_info:
                self._firmware = device_info["ver"]
                if old_firmware != self._firmware:
                    self._notify_property_change(PROPERTY_FIRMWARE, self._firmware)
            
            # Update battery percentage
            old_battery = self._battery_percent
            if "battery" in device_info:
                self._battery_percent = int(device_info["battery"])
                if old_battery != self._battery_percent:
                    self._notify_property_change(BATTERY_PROPERTY.name, self._battery_percent)
            
            # Update status from latestStatus enum
            old_status_code = self._status_code
            if "latestStatus" in device_info:
                status_code = device_info["latestStatus"]
                self._status_code = status_code
                if old_status_code != status_code:
                    self._notify_property_change(STATUS_PROPERTY.name, status_code)
            
            # The cloud says whether the device is connected to it. A device
            # that is not cannot answer commands, and every one sent to it only
            # times out.
            if isinstance(device_info.get("online"), bool):
                self._set_online(device_info["online"])

            # The model decides which device codes apply and which settings
            # the mower acts on.
            if model := device_info.get("model"):
                self._model = model
                self._device_code_handler.set_model(model)
            
            # Update last update timestamp
            self._last_update = datetime.now()
        except Exception as ex:
            _LOGGER.error("Failed to update device state from info: %s", ex)

    def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming MQTT messages from cloud device."""
        # Update last update timestamp
        self._last_update = datetime.now()

        # Any inbound message is proof the device is talking to the cloud, so
        # treat it as online immediately without waiting for the next poll.
        self._set_online(True)
        
        # Handle properties_changed method with params array
        if message.get("method") == "properties_changed" and "params" in message:
            params_list = message["params"]
            if isinstance(params_list, list):
                for param in params_list:
                    # Handle properties with values
                    if isinstance(param, dict) and "siid" in param and "piid" in param and "value" in param:
                        if (self._handle_mqtt_property_update(param)):
                            return # Property was handled
                    # Handle properties without values (like service1 flags)
                    elif isinstance(param, dict) and "siid" in param and "piid" in param:
                        if (self._handle_mqtt_property_update(param)):
                            return # Property was handled
        
        # Handle event_occurred method with params dict
        elif message.get("method") == "event_occured" and "params" in message:
            params = message["params"]
            if isinstance(params, dict) and "siid" in params and "eiid" in params:
                if self._handle_mqtt_event(params):
                    return  # Event was handled

        # Handle props method with simple key-value params
        elif message.get("method") == "props" and "params" in message:
            params = message["params"]
            if isinstance(params, dict):
                if self._handle_mqtt_props(params):
                    return  # Props were handled

        _LOGGER.info("📨 Unhandled MQTT message: %s", message)

    def _handle_mqtt_property_update(self, message: dict[str, Any]) -> bool:
        """Handle MQTT property updates with siid/piid format.
        
        Args:
            message: MQTT message with siid, piid, and optional value fields

        Returns:
            True if property was handled, False otherwise
        """
        try:
            siid = message["siid"]
            piid = message["piid"]
            
            if BATTERY_PROPERTY.matches(siid, piid):
                battery_value = int(message["value"])
                old_battery = self._battery_percent
                self._battery_percent = battery_value
                if old_battery != battery_value:
                    self._notify_property_change(BATTERY_PROPERTY.name, battery_value)
            elif STATUS_PROPERTY.matches(siid, piid):
                status_code = int(message["value"])
                old_status_code = self._status_code
                self._status_code = status_code
                if old_status_code != status_code:
                    # Reset mission completion flag when mowing starts (status 1)
                    if status_code == 1:  # 1 = mowing
                        self._pose_coverage_handler.reset_mission_completion()
                    self._notify_property_change(STATUS_PROPERTY.name, status_code)
            elif BLUETOOTH_PROPERTY.matches(siid, piid):
                bluetooth_value = bool(message["value"])
                old_bluetooth = self._bluetooth_connected
                self._bluetooth_connected = bluetooth_value
                if old_bluetooth != bluetooth_value:
                    self._notify_property_change(BLUETOOTH_PROPERTY.name, bluetooth_value)
            elif (SCHEDULING_TASK_PROPERTY.matches(siid, piid) or 
                  SCHEDULING_SUMMARY_PROPERTY.matches(siid, piid)):
                if SCHEDULING_TASK_PROPERTY.matches(siid, piid):
                    self._deliver_task_answer(message["value"])
                # Handle scheduling properties (2:50, 2:52) in unified handler
                if not self._scheduling_handler.handle_property_update(siid, piid, message["value"], self._notify_property_change):
                    return False  # Parsing failed - treat as unhandled property
                if SCHEDULING_TASK_PROPERTY.matches(siid, piid) and self._is_map_switch_echo(message["value"]):
                    _LOGGER.debug("Map switch announced on 2:50: %s", message["value"])
                    self._notify_property_change(MAP_SWITCH_ANNOUNCED_PROPERTY_NAME, None)
            elif POSE_COVERAGE_PROPERTY.matches(siid, piid):
                # Handle pose and coverage property (1:4) with mowing progress and coordinates
                try:
                    if not self._pose_coverage_handler.parse_value(message["value"]):
                        return False  # Parsing failed
                    
                    # Notify progress data changes
                    progress_data = self._pose_coverage_handler.get_progress_notification_data()
                    self._notify_property_change(POSE_COVERAGE_PROGRESS_PROPERTY_NAME, progress_data)
                    
                    # Notify coordinate data changes
                    coordinates_data = self._pose_coverage_handler.get_coordinates_notification_data()
                    self._notify_property_change(POSE_COVERAGE_COORDINATES_PROPERTY_NAME, coordinates_data)
                    
                except Exception as ex:
                    _LOGGER.error("Failed to parse pose coverage property: %s", ex)
                    return False
            elif FIRMWARE_INSTALL_STATE_PROPERTY.matches(siid, piid):
                # Handle firmware installation state property (1:2) - the over-the-air
                # update state, see FirmwareInstallState
                firmware_install_state = int(message["value"])
                if firmware_install_state not in FIRMWARE_INSTALL_STATE_MAPPING:
                    _LOGGER.warning("Unknown firmware installation state value: %s", firmware_install_state)
                    return False  # Report false to crowdsource more information
                old_state = self._firmware_install_state
                self._firmware_install_state = firmware_install_state
                if old_state != firmware_install_state:
                    state_description = FIRMWARE_INSTALL_STATE_MAPPING[firmware_install_state]
                    self._notify_property_change(FIRMWARE_INSTALL_STATE_PROPERTY.name, firmware_install_state)
                    _LOGGER.info("Firmware installation state updated: %s (%s)", firmware_install_state, state_description)
            elif FIRMWARE_DOWNLOAD_PROGRESS_PROPERTY.matches(siid, piid):
                # Handle firmware download progress property (1:3) - firmware update download progress
                # Value is percentage from 1 to 100 (see issue #110)
                firmware_download_progress = int(message["value"])
                if firmware_download_progress < 0 or firmware_download_progress > 100:
                    _LOGGER.warning("Invalid firmware download progress value: %s", firmware_download_progress)
                    return False  # Report false for invalid values
                old_progress = self._firmware_download_progress
                self._firmware_download_progress = firmware_download_progress
                if old_progress != firmware_download_progress:
                    self._notify_property_change(FIRMWARE_DOWNLOAD_PROGRESS_PROPERTY.name, firmware_download_progress)
                    _LOGGER.info("Firmware download progress updated: %s%%", firmware_download_progress)
            elif SERVICE1_PROPERTY_50.matches(siid, piid):
                # 1:50 carries no value; the mower sends it as a session starts
                # and when its active map is switched.
                self._notify_property_change(SERVICE1_PROPERTY_50.name, True)
            elif SERVICE1_PROPERTY_51.matches(siid, piid):
                # 1:51 carries no value; the mower sends it as a session starts.
                self._notify_property_change(SERVICE1_PROPERTY_51.name, True)
            elif CHARGING_STATUS_PROPERTY.matches(siid, piid):
                value = message["value"]
                try:
                    code = int(value)
                except Exception:
                    _LOGGER.warning("Invalid charging status value: %s", value)
                    return False

                if code not in CHARGING_STATUS_MAPPING:
                    _LOGGER.warning("Unknown charging status enum: %s", code)
                    return False

                status_text = CHARGING_STATUS_MAPPING[code]
                # Store and notify if changed
                old = self._charging_status
                self._charging_status = status_text
                if old != status_text:
                    self._notify_property_change(CHARGING_STATUS_PROPERTY.name, status_text)
            elif DEVICE_CODE_PROPERTY.matches(siid, piid):
                # Use handler to parse and update device code
                old_device_code = self._device_code_handler.device_code
                
                # Parse new value using handler
                value = message["value"]
                if self._device_code_handler.parse_value(value):
                    # Only notify if the device code actually changed
                    if old_device_code != self._device_code_handler.device_code:
                        self._notify_property_change(DEVICE_CODE_PROPERTY.name, self._device_code_handler.device_code)
                        
                        # Create specific notifications for error, warning, and info cards
                        notification_data = self._device_code_handler.get_notification_data()
                        
                        if self._device_code_handler.device_code_is_error:
                            self._notify_property_change(DEVICE_CODE_ERROR_PROPERTY_NAME, notification_data)
                        elif self._device_code_handler.device_code_is_warning:
                            self._notify_property_change(DEVICE_CODE_WARNING_PROPERTY_NAME, notification_data)
                        else:
                            self._notify_property_change(DEVICE_CODE_INFO_PROPERTY_NAME, notification_data)
                else:
                    _LOGGER.warning("Failed to parse device code value: %s", value)
                    return False
            elif POWER_STATE_PROPERTY.matches(siid, piid):
                # Handle power state property (2:57) - occurs when mower is turned off
                power_state_value = int(message["value"])
                if power_state_value == 1:
                    self._notify_property_change(POWER_STATE_PROPERTY.name, power_state_value)
                else:
                    return False  # Unexpected value, handle as unhandled property
            elif SERVICE2_PROPERTY_55.matches(siid, piid):
                # An obstacle the camera recognised just now: {"type": "ai",
                # "obs": <one entry of the AIOBS list>}.
                _LOGGER.debug("Service 2 property 55 (AI obstacle detection) received: %s", message.get("value"))
                self._add_ai_obstacle(message.get("value"))
            elif DEVICE_FILE_PATH_PROPERTY.matches(siid, piid) or DEVICE_FILE_PATH_PROPERTY_20.matches(siid, piid):
                # Handle file path properties (99:10, 99:20) - provide cloud file paths for:
                # - Firmware/OTA update packages (when firmware updates are available)
                # - Device log files (when user selects "Report logs" in the app)
                device_file_path = str(message["value"])
                old_device_file_path = self._device_file_path
                self._device_file_path = device_file_path
                if old_device_file_path != device_file_path:
                    self._notify_property_change(DEVICE_FILE_PATH_PROPERTY.name, device_file_path)
                    _LOGGER.info("Device file path updated: %s", device_file_path)
                    
                    # Attempt to download the file
                    result = download_file(
                        file_path=device_file_path,
                        get_download_url=self._cloud_device.get_file_download_url,
                        hass_config_dir=self._hass_config_dir,
                        timeout=60
                    )
                    
                    if result:
                        # Notify about successful download with metadata
                        self._notify_property_change("device_file_downloaded", result)
            elif MiscPropertyHandler.matches(siid, piid):
                # Handle miscellaneous properties (1:1, 2:51) in unified misc handler
                if not self._misc_handler.handle_property_update(siid, piid, message["value"], self._notify_property_change):
                    return False  # Parsing failed - treat as unhandled property
            elif any(prop.matches(siid, piid) for prop in IGNORED_PROPERTIES):
                _LOGGER.debug("Property %s:%s ignored: %s", siid, piid, message.get("value"))
            else:
                return False  # Property not handled
            
        except Exception as ex:
            _LOGGER.error("Failed to handle MQTT property update: %s", ex)

        return True  # Property was handled
    
    def _handle_mqtt_event(self, params: dict[str, Any]) -> bool:
        """Handle MQTT event messages."""
        try:
            siid = params.get("siid")
            eiid = params.get("eiid")
            arguments = params.get("arguments", [])
            
            if siid is None or eiid is None:
                _LOGGER.warning("Invalid event parameters: %s", params)
                return False
            
            # Handle firmware validation event (1:1)
            if FIRMWARE_VALIDATION_EVENT.matches(siid, eiid):
                _LOGGER.info("Firmware validation event received: siid=%d, eiid=%d", siid, eiid)
                self._notify_property_change(FIRMWARE_VALIDATION_EVENT.name, {
                    "siid": siid,
                    "eiid": eiid,
                    "timestamp": datetime.now().isoformat()
                })
                return True
            
            # Handle mission completion event (4:1)
            if MISSION_COMPLETION_EVENT.matches(siid, eiid):
                handled = self._mission_completion_handler.handle_event(siid, eiid, arguments, self._notify_property_change)
                if handled and self._mission_completion_handler.is_patrol:
                    # A patrol ends no mowing task: its progress stays as it was.
                    _LOGGER.debug("Patrol finished (status=%s)", self._mission_completion_handler.status)
                elif handled:
                    # Signal that mission is completed for stop-then-dock sequence
                    self._mission_completed_event.set()
                    
                    # Only cap progress at 100% when the mission completed normally.
                    # Uses status (piid 7): STATUS_FINISHED (1) = normal,
                    # STATUS_INTERRUPTED (3) = early stop (e.g. low battery).
                    if self._mission_completion_handler.is_complete:
                        self._pose_coverage_handler.mark_mission_completed()
                    else:
                        _LOGGER.debug(
                            "Mission ended early (status=%s, stop_reason=%s), not marking progress as 100%%",
                            self._mission_completion_handler.status,
                            self._mission_completion_handler.stop_reason,
                        )
                    
                    if self._mission_completion_handler.has_data_file:
                        self._mission_completion_handler.download_data_file(
                            self._cloud_device.get_file_download_url, self._hass_config_dir
                        )
                return handled

            _LOGGER.warning("Unhandled event %d:%d with arguments: %s", siid, eiid, arguments)
            return False
            
        except Exception as ex:
            _LOGGER.error("Failed to handle MQTT event: %s", ex)
            return False

    def _handle_mqtt_props(self, params: dict[str, Any]) -> bool:
        """Handle MQTT props messages with direct property updates.

        The mower reports the state and progress of an over-the-air update here
        as ota_state and ota_progress. An update is followed on 1:2 and 1:3, so
        these are only acknowledged.
        """
        handled_any = False
        for key, value in params.items():
            if key in ("ota_state", "ota_progress"):
                _LOGGER.debug("%s: %s", key, value)
                handled_any = True
            else:
                _LOGGER.debug("Unhandled props parameter: %s = %s", key, value)
        return handled_any

    def _cancel_transport_grace(self) -> None:
        """Cancel a pending transport grace timer and clear the drop time."""
        if self._transport_grace_timer is not None:
            self._transport_grace_timer.cancel()
            self._transport_grace_timer = None
        self._transport_down_since = None

    def _handle_connected(self) -> None:
        """Handle cloud device connection established."""
        down_since = self._transport_down_since
        if down_since is not None:
            _LOGGER.debug(
                "Cloud device %s reconnected after %.1fs",
                self._device_id, time.monotonic() - down_since,
            )
        self._cancel_transport_grace()
        self._last_update = datetime.now()
        self._notify_property_change("connected", True)

    def _handle_disconnected(self) -> None:
        """Handle cloud device disconnection.

        The drop is only reported once it outlasts the grace period; a reconnect
        within it cancels the report.
        """
        _LOGGER.debug("Cloud device transport dropped for %s", self._device_id)
        self._cancel_transport_grace()
        self._transport_down_since = time.monotonic()
        timer = threading.Timer(
            TRANSPORT_DISCONNECT_GRACE_SECONDS, self._transport_grace_expired
        )
        timer.daemon = True
        self._transport_grace_timer = timer
        timer.start()

    def _transport_grace_expired(self) -> None:
        """Report the disconnection if the transport is still down."""
        self._transport_grace_timer = None
        if self._cloud_device.connected:
            return
        self._transport_down_since = None
        _LOGGER.warning(
            "Cloud device disconnected for %s (no reconnect within %ss)",
            self._device_id, TRANSPORT_DISCONNECT_GRACE_SECONDS,
        )
        self._notify_property_change("connected", False)

    async def connect(self) -> bool:
        """Connect to the device."""
        try:
            # Connect to cloud device with required callbacks (run in executor to avoid blocking)
            loop = asyncio.get_event_loop()
            connected = await loop.run_in_executor(
                None,
                lambda: self._cloud_device.connect(
                    message_callback=self._handle_message,
                    connected_callback=self._handle_connected,
                    disconnected_callback=self._handle_disconnected
                )
            )
            
            if connected:
                self._last_update = datetime.now()
                
                # Fetch initial device information (battery, status, firmware) after successful connection
                try:
                    await self.fetch_device_info()
                except RuntimeError as ex:
                    if "no running event loop" in str(ex):
                        _LOGGER.warning("Skipping initial device info fetch - no event loop available")
                    else:
                        raise
            else:
                _LOGGER.error("Failed to connect to device %s", self._device_id)
                
            return connected
        except Exception as ex:
            _LOGGER.error("Error connecting to device %s: %s", self._device_id, ex)
            return False

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        try:
            # Run disconnect in executor to avoid blocking
            await asyncio.get_event_loop().run_in_executor(None, self._cloud_device.disconnect)
            self._cancel_transport_grace()
            self._notify_property_change("connected", False)
        except Exception as ex:
            _LOGGER.error("Error disconnecting from device %s: %s", self._device_id, ex)

    async def start_mowing_generic(self) -> bool:
        """Start mowing via the generic cloud action, letting the device pick the area.

        This mirrors the pre-map-aware behaviour: it sends the bare 5:1
        START_MOWING action and lets the robot run whatever is configured in the
        app. Used as an all-area fallback when the map-aware payload fails.
        """
        if not await self._send_action(ACTION_START_MOWING):
            _LOGGER.error("Failed to send START_MOWING command")
            return False
        
        # Reset mission completion flag for new mowing session
        self._pose_coverage_handler.reset_mission_completion()
        
        self._notify_property_change("activity", "mowing")
        return True

    async def resume(self) -> bool:
        """Resume mowing after pause (continueControl: embedded protocol {m:'a', p:0, o:5} via 2:50)."""
        result = await self._send_task_payload("resume", TASK_PAYLOAD_RESUME)
        if not result:
            _LOGGER.error("Failed to send RESUME command")
            return False
        self._notify_property_change("activity", "mowing")
        return True

    async def start_mowing(
        self,
        mode: MowingMode = MowingMode.ALL_AREA,
        *,
        map_id: int | None = None,
        zone_ids: list[int] | None = None,
        contour_ids: list[list[int]] | None = None,
        spot_area_ids: list[int] | None = None,
        from_stop_point: bool | None = None,
    ) -> bool:
        """Start mowing using the public mode-oriented entrypoint."""
        return await self.start_mowing_mode(
            mode,
            map_id=map_id,
            zone_ids=zone_ids,
            contour_ids=contour_ids,
            spot_area_ids=spot_area_ids,
            from_stop_point=from_stop_point,
        )

    def _validate_map_id(self, map_id: int) -> bool:
        """Return True when the requested map ID exists in the loaded vector map."""
        if map_id < 1:
            _LOGGER.error("Map IDs must be positive integers; got: %s", map_id)
            return False

        if self._vector_map is None:
            return True

        available_map_ids = {map_entry["id"] for map_entry in self.available_maps}
        if map_id not in available_map_ids:
            _LOGGER.error(
                "Requested unknown map ID %s; available maps: %s",
                map_id,
                sorted(available_map_ids),
            )
            return False

        return True

    def _map_index_from_id(self, map_id: int) -> int:
        """Translate the exposed map ID back to the device's map index."""
        if self._vector_map is not None:
            for map_entry in self._vector_map.available_maps:
                if map_entry.map_id == map_id:
                    return map_entry.map_index

        return map_id - 1

    def _map_id_from_index(self, map_index: int, fallback_position: int | None = None) -> int | None:
        """Translate a device map index back to the exposed map identifier."""
        if self._vector_map is not None:
            for map_entry in self._vector_map.available_maps:
                if map_entry.map_index == map_index:
                    return map_entry.map_id

            if fallback_position is not None and 0 <= fallback_position < len(self._vector_map.available_maps):
                return self._vector_map.available_maps[fallback_position].map_id

        if fallback_position is not None and fallback_position >= 0:
            return fallback_position + 1

        if map_index >= 0:
            return map_index + 1

        return None

    def _build_get_map_list_payload(self) -> dict[str, Any]:
        """Build the 2:50 getter payload for MAPL."""
        return {
            "m": "g",
            "t": MAP_LIST_KEY,
        }

    def _build_get_map_info_payload(self, map_index: int) -> dict[str, Any]:
        """Build the 2:50 getter payload for the hash and size of one map."""
        return {
            "m": "g",
            "t": MAP_INFO_KEY,
            "d": {
                "idx": int(map_index),
            },
        }

    def _build_get_map_data_payload(self, start: int, size: int) -> dict[str, Any]:
        """Build the 2:50 getter payload for one chunk of the map last named by an info read."""
        return {
            "m": "g",
            "t": MAP_DATA_KEY,
            "d": {
                "start": int(start),
                "size": int(size),
            },
        }

    def _build_get_consumable_payload(self) -> dict[str, Any]:
        """Build the getter payload for CMS consumable counters."""
        return {
            "m": "g",
            "t": "CMS",
        }

    def _build_set_consumable_payload(self, values: Sequence[int]) -> dict[str, Any]:
        """Build the setter payload for CMS consumable counters."""
        normalized_values = [int(value) for value in values]
        # The device expects the full counter array written back verbatim. It
        # reports at least the three known counters (blade/brush/robot) and may
        # include extra slots carrying a -1 sentinel ("not applicable"); those
        # must be preserved as-is or the device rejects/ignores the write.
        if len(normalized_values) < 3:
            raise ValueError(f"CMS values must contain at least 3 counters; got {normalized_values}")

        return {
            "m": "s",
            "t": "CMS",
            "d": {
                "value": normalized_values,
            },
        }

    def _build_get_device_settings_payload(self) -> dict[str, Any]:
        """Build the getter payload for the CFG settings record."""
        return {
            "m": "g",
            "t": "CFG",
        }

    def _build_get_device_information_payload(self) -> dict[str, Any]:
        """Build the getter payload for the DEV hardware information."""
        return {
            "m": "g",
            "t": "DEV",
        }

    def _build_set_charging_period_payload(
        self,
        enabled: bool,
        start_minutes: int,
        end_minutes: int,
    ) -> dict[str, Any]:
        """Build the setter payload for the custom charging period."""
        return {
            "m": "s",
            "t": DEVICE_SETTINGS_BATTERY_KEY,
            "d": {
                "type": "charging",
                "value": [int(enabled), int(start_minutes), int(end_minutes)],
            },
        }

    def _build_set_rain_protection_payload(
        self,
        enabled: bool,
        delay_hours: int,
        sensitivity: int,
    ) -> dict[str, Any]:
        """Build the setter payload for the rain protection settings."""
        return {
            "m": "s",
            "t": DEVICE_SETTINGS_RAIN_KEY,
            "d": {
                "value": int(enabled),
                "time": int(delay_hours),
                "sen": int(sensitivity),
            },
        }

    def _build_set_anti_theft_payload(self, record: Sequence[int]) -> dict[str, Any]:
        """Build the setter payload for the anti-theft settings."""
        return {
            "m": "s",
            "t": DEVICE_SETTINGS_ANTI_THEFT_KEY,
            "d": {
                "value": [int(value) for value in record],
            },
        }

    def _build_get_rain_protection_end_payload(self) -> dict[str, Any]:
        """Build the getter payload for the time rain protection releases the mower."""
        return {
            "m": "g",
            "t": "RPET",
        }

    def _build_get_schedule_info_payload(self, map_index: int) -> dict[str, Any]:
        """Build the getter payload for a map's schedule size and version."""
        return {
            "m": "g",
            "t": self._schedule_document_keys[0],
            "d": {
                "i": int(map_index),
            },
        }

    def _build_get_schedule_data_payload(self, start: int, size: int, version: int) -> dict[str, Any]:
        """Build the getter payload for one chunk of the schedule document."""
        return {
            "m": "g",
            "t": self._schedule_document_keys[1],
            "d": {
                "s": int(start),
                "l": int(size),
                "v": int(version),
            },
        }

    def _build_set_schedule_enabled_payload(
        self,
        map_index: int,
        version: int,
        enabled_flags: Sequence[bool],
    ) -> dict[str, Any]:
        """Build the setter payload for which schedule slots of a map are enabled."""
        return {
            "m": "s",
            "t": self._schedule_document_keys[2],
            "d": {
                "i": int(map_index),
                "v": int(version),
                "s": [int(bool(flag)) for flag in enabled_flags],
            },
        }

    def _build_get_schedule_tables_payload(self, table_ids: Sequence[int]) -> dict[str, Any]:
        """Build the getter payload for the state and task list of schedule tables."""
        return {
            "m": "g",
            "t": SCHEDULE_TABLE_INFO_KEY,
            "d": [int(table_id) for table_id in table_ids],
        }

    def _build_get_schedule_table_task_payload(self, table_id: int, task_id: int) -> dict[str, Any]:
        """Build the getter payload for one task of a schedule table."""
        return {
            "m": "g",
            "t": SCHEDULE_TABLE_TASK_KEY,
            "d": [int(table_id), int(task_id)],
        }

    def _build_set_schedule_table_enabled_payload(self, table_id: int, enabled: bool) -> dict[str, Any]:
        """Build the setter payload that switches one schedule table on or off."""
        return {
            "m": "s",
            "t": SCHEDULE_TABLE_ENABLE_KEY,
            "d": [int(table_id), int(bool(enabled))],
        }

    @staticmethod
    def _extract_custom_action_data(result: Any) -> dict[str, Any] | None:
        """Extract the first successful data payload from a custom action result."""
        if not isinstance(result, dict):
            return None

        if isinstance(result.get("value"), list):
            return result

        direct_data = result.get("d")
        if isinstance(direct_data, dict):
            return direct_data

        out_entries = result.get("out")
        if not isinstance(out_entries, list):
            return None

        for out_entry in out_entries:
            if not isinstance(out_entry, dict):
                continue

            if out_entry.get("r") not in (None, 0) and out_entry.get("code") not in (None, 0):
                continue

            data = out_entry.get("d")
            if isinstance(data, dict):
                return data

        return None

    @classmethod
    def _extract_consumable_values(cls, result: Any) -> list[int] | None:
        """Extract the CMS counter list from a custom action result."""
        data = cls._extract_custom_action_data(result)
        if not isinstance(data, dict):
            return None

        values = data.get("value")
        if not isinstance(values, list) or len(values) < 3:
            return None

        # Preserve the full counter array as reported by the device. Some models
        # report more than the three known counters (blade/brush/robot), and a
        # counter write must round-trip the entire array or the device ignores it.
        normalized_values: list[int] = []
        for value in values:
            try:
                normalized_values.append(int(value))
            except (TypeError, ValueError):
                return None

        return normalized_values

    @staticmethod
    def _normalize_consumable_item(item: str) -> str:
        """Normalize a consumable alias to the canonical CMS item name."""
        normalized_item = item.strip().lower()
        if normalized_item not in CONSUMABLE_COUNTER_INDEX:
            raise ValueError(f"Unknown consumable item: {item}")

        if normalized_item in ("blade", "blades"):
            return "blade"
        if normalized_item in ("brush", "cleaning_brush"):
            return "brush"
        return "robot"

    def _current_map_id_from_map_list_result(self, result: Any) -> int | None:
        """Extract the active exposed map ID from a MAPL action response."""
        if not isinstance(result, dict):
            return None

        if result.get("code") not in (None, 0):
            return None

        out_entries = result.get("out")
        if not isinstance(out_entries, list):
            return None

        for out_entry in out_entries:
            if not isinstance(out_entry, dict):
                continue

            if out_entry.get("r") not in (None, 0):
                continue

            map_entries = out_entry.get("d")
            if not isinstance(map_entries, list):
                continue

            for position, map_entry in enumerate(map_entries):
                if not isinstance(map_entry, (list, tuple)) or len(map_entry) < 2:
                    continue

                map_index = map_entry[0]
                is_current_map = map_entry[1]

                try:
                    normalized_index = int(map_index)
                except (TypeError, ValueError):
                    continue

                if bool(is_current_map):
                    return self._map_id_from_index(normalized_index, fallback_position=position)

        return None

    async def get_consumable_status(self) -> dict[str, Any]:
        """Fetch the raw CMS consumable counters and parsed values."""
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._cloud_device.action(
                SCHEDULING_TASK_PROPERTY.siid,
                SCHEDULING_TASK_PROPERTY.piid,
                [self._build_get_consumable_payload()],
            ),
        )
        return {
            "raw_result": result,
            "values": self._extract_consumable_values(result),
        }

    async def set_consumable_status(self, values: Sequence[int]) -> dict[str, Any]:
        """Write CMS consumable counters and return the parsed response."""
        payload = self._build_set_consumable_payload(values)
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._cloud_device.action(
                SCHEDULING_TASK_PROPERTY.siid,
                SCHEDULING_TASK_PROPERTY.piid,
                [payload],
            ),
        )
        return {
            "raw_result": result,
            "values": self._extract_consumable_values(result),
        }

    async def reset_consumable_counter(self, item: str) -> dict[str, Any]:
        """Reset one CMS consumable counter to zero and return before/after state."""
        normalized_item = self._normalize_consumable_item(item)
        current_status = await self.get_consumable_status()
        current_values = current_status["values"]
        if current_values is None:
            raise ValueError(f"Failed to parse CMS getter response: {current_status['raw_result']!r}")

        next_values = list(current_values)
        next_values[CONSUMABLE_COUNTER_INDEX[normalized_item]] = 0
        updated_status = await self.set_consumable_status(next_values)

        _LOGGER.info(
            "Reset consumable '%s': previous=%s requested=%s updated=%s set_response=%r",
            normalized_item,
            current_values,
            next_values,
            updated_status["values"],
            updated_status["raw_result"],
        )

        return {
            "item": normalized_item,
            "previous_values": current_values,
            "requested_values": next_values,
            "updated_values": updated_status["values"],
            "raw_get_result": current_status["raw_result"],
            "raw_set_result": updated_status["raw_result"],
        }

    async def get_device_settings(self) -> dict[str, Any] | None:
        """Read the whole settings record the device keeps, or None when unreadable.

        The record carries every setting the app exposes, keyed by its protocol
        name; values are returned exactly as the device reports them.
        """
        result = await self._send_task_payload("device settings read", self._build_get_device_settings_payload())
        settings = self._extract_custom_action_data(result)
        if settings is None:
            _LOGGER.error("Failed to read the device settings: %s", result)
            return None

        return settings

    async def set_device_setting(self, key: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Write one setting of the settings record, under its key, and return the
        mower's answer, or None when it refused the write or answered unreadably."""
        result = await self._send_task_payload(f"{key} setting write", {"m": "s", "t": key, "d": data})
        out = result.get("out") if isinstance(result, dict) else None
        entry = out[0] if isinstance(out, list) and out and isinstance(out[0], dict) else None
        if entry is None:
            answer = self._extract_custom_action_data(result)
        elif entry.get("r") not in (None, 0):
            answer = None
        else:
            # Some settings are confirmed without echoing anything back.
            answer = self._extract_custom_action_data(result) or {}
        if answer is None:
            _LOGGER.error("Failed to write the %s setting %s: %s", key, data, result)
            return None
        _LOGGER.info("The %s setting is now %s", key, answer)
        return answer

    async def get_device_information(self) -> dict[str, Any] | None:
        """Read the device's hardware information, or None when unreadable.

        Reports the serial number, Bluetooth MAC and the running firmware
        version as the device itself knows them.
        """
        result = await self._send_task_payload(
            "device information read",
            self._build_get_device_information_payload(),
        )
        information = self._extract_custom_action_data(result)
        if information is None:
            _LOGGER.error("Failed to read the device information: %s", result)
            return None

        return information

    @staticmethod
    def _normalize_battery_settings(data: Any) -> list[int] | None:
        """Coerce a settings value into a battery settings record."""
        if isinstance(data, dict):
            data = data.get("value")

        if not isinstance(data, list) or len(data) < BATTERY_SETTING_LENGTH:
            return None

        try:
            return [int(value) for value in data]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decode_battery_settings(record: Sequence[int]) -> dict[str, Any]:
        """Describe the battery and charging settings a record carries."""
        return {
            "recharge_battery_level": record[BATTERY_SETTING_RECHARGE_LEVEL_INDEX],
            "resume_battery_level": record[BATTERY_SETTING_RESUME_LEVEL_INDEX],
            "resume_after_charging": bool(record[BATTERY_SETTING_RESUME_AFTER_CHARGING_INDEX]),
            "charging_period_enabled": bool(record[BATTERY_SETTING_CHARGING_PERIOD_ENABLED_INDEX]),
            "charging_period_start_minutes": record[BATTERY_SETTING_CHARGING_PERIOD_START_INDEX],
            "charging_period_end_minutes": record[BATTERY_SETTING_CHARGING_PERIOD_END_INDEX],
            "raw": list(record),
        }

    def decode_charging_settings(self, settings: dict[str, Any]) -> dict[str, Any] | None:
        """Pick the battery and charging settings out of a settings record."""
        record = self._normalize_battery_settings(settings.get(DEVICE_SETTINGS_BATTERY_KEY))
        if record is None:
            _LOGGER.error("Device settings carry no battery record: %s", settings)
            return None

        return self._decode_battery_settings(record)

    async def get_charging_settings(self) -> dict[str, Any] | None:
        """Read the battery and charging settings, or None when unavailable."""
        settings = await self.get_device_settings()
        if settings is None:
            return None

        return self.decode_charging_settings(settings)

    @staticmethod
    def _validate_time_of_day(minutes: int, label: str) -> int:
        """Return a time of day in minutes since midnight, or raise."""
        try:
            normalized_minutes = int(minutes)
        except (TypeError, ValueError) as ex:
            raise ValueError(f"The charging period {label} must be a number of minutes; got {minutes!r}") from ex

        if not 0 <= normalized_minutes < MINUTES_PER_DAY:
            raise ValueError(
                f"The charging period {label} must be between 0 and {MINUTES_PER_DAY - 1} minutes; "
                f"got {normalized_minutes}"
            )

        return normalized_minutes

    async def set_charging_period(
        self,
        enabled: bool | None = None,
        start_minutes: int | None = None,
        end_minutes: int | None = None,
    ) -> dict[str, Any] | None:
        """Update the custom charging period and return the settings that took effect.

        Every unspecified part keeps the value the device currently holds, so the
        period can be switched on and off without restating its times. Returns
        None when the mower refused the write or answered unreadably.
        """
        current_settings = await self.get_charging_settings()
        if current_settings is None:
            return None

        next_enabled = current_settings["charging_period_enabled"] if enabled is None else bool(enabled)
        next_start = (
            current_settings["charging_period_start_minutes"]
            if start_minutes is None
            else self._validate_time_of_day(start_minutes, "start time")
        )
        next_end = (
            current_settings["charging_period_end_minutes"]
            if end_minutes is None
            else self._validate_time_of_day(end_minutes, "end time")
        )

        # The device keeps a period of zero length; it rejects such a window.
        if next_start == next_end:
            raise ValueError(
                f"The charging period start and end time must differ; both are {next_start} minutes"
            )

        result = await self._send_task_payload(
            "charging period write",
            self._build_set_charging_period_payload(next_enabled, next_start, next_end),
        )
        record = self._normalize_battery_settings(self._extract_custom_action_data(result))
        if record is None:
            _LOGGER.error(
                "Failed to write the charging period (enabled=%s start=%s end=%s): %s",
                next_enabled,
                next_start,
                next_end,
                result,
            )
            return None

        _LOGGER.info(
            "Charging period is now %s from %s to %s minutes",
            "enabled" if record[BATTERY_SETTING_CHARGING_PERIOD_ENABLED_INDEX] else "disabled",
            record[BATTERY_SETTING_CHARGING_PERIOD_START_INDEX],
            record[BATTERY_SETTING_CHARGING_PERIOD_END_INDEX],
        )
        return self._decode_battery_settings(record)

    @staticmethod
    def _normalize_rain_settings(data: Any) -> list[int] | None:
        """Coerce a settings value into a rain protection record."""
        if isinstance(data, dict):
            data = data.get("value")

        if not isinstance(data, list) or len(data) < RAIN_SETTING_MINIMUM_LENGTH:
            return None

        try:
            record = [int(value) for value in data]
        except (TypeError, ValueError):
            return None

        while len(record) < RAIN_SETTING_LENGTH:
            record.append(RAIN_SETTING_DEFAULT_SENSITIVITY)

        return record

    @staticmethod
    def _decode_rain_settings(record: Sequence[int]) -> dict[str, Any]:
        """Describe the rain protection settings a record carries."""
        return {
            "rain_protection_enabled": bool(record[RAIN_SETTING_ENABLED_INDEX]),
            "rain_delay_hours": record[RAIN_SETTING_DELAY_INDEX],
            "rain_sensitivity": record[RAIN_SETTING_SENSITIVITY_INDEX],
            "raw": list(record),
        }

    def decode_rain_settings(self, settings: dict[str, Any]) -> dict[str, Any] | None:
        """Pick the rain protection settings out of a settings record."""
        record = self._normalize_rain_settings(settings.get(DEVICE_SETTINGS_RAIN_KEY))
        if record is None:
            _LOGGER.error("Device settings carry no rain protection record: %s", settings)
            return None

        return self._decode_rain_settings(record)

    async def get_rain_settings(self) -> dict[str, Any] | None:
        """Read the rain protection settings, or None when unavailable."""
        settings = await self.get_device_settings()
        if settings is None:
            return None

        return self.decode_rain_settings(settings)

    @staticmethod
    def _validate_rain_delay(delay_hours: int) -> int:
        """Return an after-rain delay in whole hours, or raise."""
        try:
            normalized_delay = int(delay_hours)
        except (TypeError, ValueError) as ex:
            raise ValueError(
                f"The after-rain delay must be a number of hours; got {delay_hours!r}"
            ) from ex

        if not RAIN_DELAY_MIN_HOURS <= normalized_delay <= RAIN_DELAY_MAX_HOURS:
            raise ValueError(
                f"The after-rain delay must be between {RAIN_DELAY_MIN_HOURS} and "
                f"{RAIN_DELAY_MAX_HOURS} hours; got {normalized_delay}"
            )

        return normalized_delay

    async def set_rain_protection(
        self,
        enabled: bool | None = None,
        delay_hours: int | None = None,
    ) -> dict[str, Any] | None:
        """Update the rain protection settings and return the ones that took effect.

        Every unspecified part keeps the value the device currently holds, so
        rain protection can be switched without restating its delay. Returns None
        when the mower refused the write or answered unreadably.
        """
        current_settings = await self.get_rain_settings()
        if current_settings is None:
            return None

        next_enabled = (
            current_settings["rain_protection_enabled"] if enabled is None else bool(enabled)
        )
        next_delay = (
            current_settings["rain_delay_hours"]
            if delay_hours is None
            else self._validate_rain_delay(delay_hours)
        )

        result = await self._send_task_payload(
            "rain protection write",
            self._build_set_rain_protection_payload(
                next_enabled,
                next_delay,
                current_settings["rain_sensitivity"],
            ),
        )
        record = self._normalize_rain_settings(self._extract_custom_action_data(result))
        if record is None:
            _LOGGER.error(
                "Failed to write the rain protection settings (enabled=%s delay=%s): %s",
                next_enabled,
                next_delay,
                result,
            )
            return None

        if record[RAIN_SETTING_DELAY_INDEX] != next_delay:
            # The device only takes a new delay while rain protection is on; it
            # keeps the stored one otherwise and reports what it kept.
            _LOGGER.warning(
                "The device kept its after-rain delay of %s hours instead of the requested %s",
                record[RAIN_SETTING_DELAY_INDEX],
                next_delay,
            )

        _LOGGER.info(
            "Rain protection is now %s with an after-rain delay of %s hours",
            "enabled" if record[RAIN_SETTING_ENABLED_INDEX] else "disabled",
            record[RAIN_SETTING_DELAY_INDEX],
        )
        return self._decode_rain_settings(record)

    @staticmethod
    def _normalize_anti_theft_settings(data: Any) -> list[int] | None:
        """Coerce a settings value into an anti-theft record."""
        if isinstance(data, dict):
            data = data.get("value")

        if not isinstance(data, list) or len(data) < ANTI_THEFT_SETTING_LENGTH:
            return None

        try:
            # The record is written back in full, extra slots included: a model
            # that keeps more switches than the known ones loses them otherwise.
            return [int(value) for value in data]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decode_anti_theft_settings(record: Sequence[int]) -> dict[str, Any]:
        """Describe the anti-theft settings a record carries."""
        return {
            "lift_alarm_enabled": bool(record[ANTI_THEFT_SETTING_LIFT_ALARM_INDEX]),
            "off_map_alarm_enabled": bool(record[ANTI_THEFT_SETTING_OFF_MAP_ALARM_INDEX]),
            "location_reporting_enabled": bool(record[ANTI_THEFT_SETTING_LOCATION_INDEX]),
            "pin_check_enabled": (
                bool(record[ANTI_THEFT_SETTING_PIN_CHECK_INDEX])
                if len(record) > ANTI_THEFT_SETTING_PIN_CHECK_INDEX
                else None
            ),
            "raw": list(record),
        }

    def decode_anti_theft_settings(self, settings: dict[str, Any]) -> dict[str, Any] | None:
        """Pick the anti-theft settings out of a settings record."""
        record = self._normalize_anti_theft_settings(settings.get(DEVICE_SETTINGS_ANTI_THEFT_KEY))
        if record is None:
            _LOGGER.error("Device settings carry no anti-theft record: %s", settings)
            return None

        return self._decode_anti_theft_settings(record)

    async def get_anti_theft_settings(self) -> dict[str, Any] | None:
        """Read the anti-theft settings, or None when unavailable."""
        settings = await self.get_device_settings()
        if settings is None:
            return None

        return self.decode_anti_theft_settings(settings)

    async def set_anti_theft_settings(
        self,
        lift_alarm: bool | None = None,
        off_map_alarm: bool | None = None,
        location_reporting: bool | None = None,
        pin_check: bool | None = None,
    ) -> dict[str, Any] | None:
        """Update the anti-theft settings and return the ones that took effect.

        Every unspecified switch keeps the value the device currently holds, so
        one switch can be changed without restating the others. Returns None when
        the mower refused the write or answered unreadably.
        """
        if (off_map_alarm is not None or location_reporting is not None) and (
            self.link_module_installed is False
        ):
            raise ValueError(
                "The off-map alarm and the mower's location reports need a cellular "
                "module, and this mower reports none is fitted"
            )

        current_settings = await self.get_anti_theft_settings()
        if current_settings is None:
            return None

        if pin_check is not None and current_settings["pin_check_enabled"] is None:
            raise ValueError("This mower does not ask for a PIN code before it is switched off")

        next_record = list(current_settings["raw"])
        for index, requested in (
            (ANTI_THEFT_SETTING_LIFT_ALARM_INDEX, lift_alarm),
            (ANTI_THEFT_SETTING_OFF_MAP_ALARM_INDEX, off_map_alarm),
            (ANTI_THEFT_SETTING_LOCATION_INDEX, location_reporting),
            (ANTI_THEFT_SETTING_PIN_CHECK_INDEX, pin_check),
        ):
            if requested is not None:
                next_record[index] = int(bool(requested))

        result = await self._send_task_payload(
            "anti-theft settings write",
            self._build_set_anti_theft_payload(next_record),
        )
        record = self._normalize_anti_theft_settings(self._extract_custom_action_data(result))
        if record is None:
            _LOGGER.error(
                "Failed to write the anti-theft settings %s: %s",
                next_record,
                result,
            )
            return None

        updated_settings = self._decode_anti_theft_settings(record)
        _LOGGER.info(
            "Anti-theft settings are now lift alarm %s, off-map alarm %s, location reporting %s",
            "enabled" if updated_settings["lift_alarm_enabled"] else "disabled",
            "enabled" if updated_settings["off_map_alarm_enabled"] else "disabled",
            "enabled" if updated_settings["location_reporting_enabled"] else "disabled",
        )
        return updated_settings

    async def get_rain_protection_end_timestamp(self) -> int | None:
        """Read when rain protection lets the mower work again.

        Returns the end time as a Unix timestamp in seconds, zero while rain
        protection is not holding the mower back, and None when the read failed.
        The last two are told apart on purpose: a read that did not come through
        says nothing about the mower, whereas zero says it is free to work.
        """
        result = await self._send_task_payload(
            "rain protection end time read",
            self._build_get_rain_protection_end_payload(),
        )
        data = self._extract_custom_action_data(result)
        if not isinstance(data, dict) or "endTime" not in data:
            _LOGGER.error("Failed to read the rain protection end time: %s", result)
            return None

        try:
            end_timestamp = int(data["endTime"])
        except (TypeError, ValueError):
            _LOGGER.error("Rain protection end time is not a timestamp: %s", data)
            return None

        # The device reports zero whenever rain protection is not holding it back.
        return end_timestamp if end_timestamp > 0 else 0

    @staticmethod
    def _decode_schedule_tasks(payload: str) -> list[dict[str, Any]]:
        """Decode the tasks of one schedule plan.

        Every task is framed by a marker byte and its own length, so a task the
        mower encodes with fields this decode does not know still carries its
        length and does not throw the rest of the plan off. A frame that does not
        start with the marker ends the walk: the remaining bytes cannot be
        located without it.
        """
        blob = base64.b64decode(payload, validate=True)
        tasks: list[dict[str, Any]] = []
        offset = 0
        while offset + SCHEDULE_TASK_MINIMUM_LENGTH <= len(blob):
            if blob[offset] != SCHEDULE_TASK_START_MARKER:
                _LOGGER.debug("Schedule task at byte %d carries no start marker: %s", offset, blob.hex())
                break

            task_length = blob[offset + 1]
            if task_length < SCHEDULE_TASK_MINIMUM_LENGTH or offset + task_length > len(blob):
                _LOGGER.debug("Schedule task at byte %d claims %d bytes: %s", offset, task_length, blob.hex())
                break

            week_day_and_type = blob[offset + 2]
            # The start time is minutes since midnight, spread over the low byte
            # and the low nibble of the byte that follows it.
            start_time = ((blob[offset + 4] & 0x0F) << 8) | blob[offset + 3]
            elements = list(blob[offset + 6:offset + task_length - 1])

            task_type = week_day_and_type & 0x0F
            week_day = week_day_and_type >> 4
            task: dict[str, Any] = {
                "week_day": (
                    SCHEDULE_WEEK_DAYS[week_day] if week_day < len(SCHEDULE_WEEK_DAYS) else "unknown"
                ),
                "type": SCHEDULE_TASK_TYPE_MAPPING.get(task_type, "unknown"),
                "start_time": start_time,
            }
            if task_type == ScheduleTaskType.ZONE:
                task["zone_ids"] = elements
            elif task_type == ScheduleTaskType.EDGE:
                # Edge tasks carry the zone and the side of it to mow as a pair.
                task["edges"] = [list(pair) for pair in zip(elements[::2], elements[1::2])]

            tasks.append(task)
            offset += task_length

        return tasks

    @classmethod
    def _decode_schedule_plan(cls, plan: Any) -> dict[str, Any] | None:
        """Describe one schedule plan of a map, or None when it cannot be read."""
        if not isinstance(plan, (list, tuple)) or len(plan) <= SCHEDULE_PLAN_NAME_INDEX:
            _LOGGER.error("Schedule plan is not a plan record: %s", plan)
            return None

        try:
            slot = int(plan[SCHEDULE_PLAN_SLOT_INDEX])
            enabled = bool(plan[SCHEDULE_PLAN_ENABLED_INDEX])
        except (TypeError, ValueError):
            _LOGGER.error("Schedule plan carries no slot and state: %s", plan)
            return None

        name = plan[SCHEDULE_PLAN_NAME_INDEX]
        # A plan the mower stores tasks for is told apart from one that holds
        # none: only the mower knows what its tasks mean, so a blob this decode
        # cannot read still describes a plan there is something to run.
        tasks_stored = (
            len(plan) > SCHEDULE_PLAN_TASKS_INDEX
            and isinstance(plan[SCHEDULE_PLAN_TASKS_INDEX], str)
            and bool(plan[SCHEDULE_PLAN_TASKS_INDEX])
        )
        tasks: list[dict[str, Any]] = []
        if tasks_stored:
            try:
                tasks = cls._decode_schedule_tasks(plan[SCHEDULE_PLAN_TASKS_INDEX])
            except Exception as ex:
                # The tasks only describe the plan; the slot can still be switched
                # without them.
                _LOGGER.warning("Failed to decode the tasks of schedule slot %s: %s", slot, ex)

        return {
            "slot": slot,
            "enabled": enabled,
            "name": str(name) if isinstance(name, str) and name else None,
            "tasks": tasks,
            "tasks_stored": tasks_stored,
        }

    async def _get_schedule_info(self, map_index: int) -> tuple[int, int] | None:
        """Read the byte length and version of a map's schedule document."""
        result = await self._send_task_payload(
            "schedule info read",
            self._build_get_schedule_info_payload(map_index),
        )
        data = self._extract_custom_action_data(result)
        if not isinstance(data, dict):
            _LOGGER.error("Failed to read the schedule info of map index %s: %s", map_index, result)
            return None

        try:
            return int(data["l"]), int(data["v"])
        except (KeyError, TypeError, ValueError):
            _LOGGER.error("Schedule info of map index %s carries no size and version: %s", map_index, data)
            return None

    async def _get_schedule_document(self, length: int, version: int) -> Any | None:
        """Read a map's schedule document, one chunk at a time.

        The mower counts the document in bytes, and a plan name can carry
        characters that take more than one, so the chunks are put back together as
        bytes and only read as text once the whole document has come in.
        """
        chunks: list[bytes] = []
        offset = 0
        while offset < length:
            result = await self._send_task_payload(
                "schedule data read",
                self._build_get_schedule_data_payload(offset, min(length - offset, SCHEDULE_CHUNK_SIZE), version),
            )
            data = self._extract_custom_action_data(result)
            if not isinstance(data, dict) or not isinstance(data.get("d"), str):
                _LOGGER.error("Failed to read the schedule document at byte %d: %s", offset, result)
                return None

            chunk = data["d"].encode("utf-8")
            # The mower reports how many bytes the chunk covers, which is what the
            # next read has to continue from. Only those bytes are kept, so the
            # document cannot end up longer than the offsets say it is.
            try:
                chunk_length = int(data["l"])
            except (KeyError, TypeError, ValueError):
                chunk_length = len(chunk)

            if chunk_length <= 0:
                _LOGGER.error("Schedule document read at byte %d returned no bytes: %s", offset, data)
                return None

            chunks.append(chunk[:chunk_length])
            offset += chunk_length

        try:
            return json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as ex:
            _LOGGER.error("Schedule document could not be read: %s", ex)
            return None

    async def _read_schedules(self, map_index: int) -> tuple[list[dict[str, Any]], int] | None:
        """Read a map's schedule slots alongside the version they are held under."""
        info = await self._get_schedule_info(map_index)
        if info is None:
            return None

        length, version = info
        document = await self._get_schedule_document(length, version)
        if not isinstance(document, dict) or not isinstance(document.get("d"), list):
            _LOGGER.error("Schedule document of map index %s carries no plans: %s", map_index, document)
            return None

        schedules: list[dict[str, Any]] = []
        for plan in document["d"]:
            schedule = self._decode_schedule_plan(plan)
            if schedule is not None:
                schedules.append(schedule)

        schedules.sort(key=lambda schedule: schedule["slot"])
        self._update_schedule_cache(map_index, schedules, version)
        return schedules, version

    async def refresh_schedules(self, map_id: int | None = None) -> list[dict[str, Any]] | None:
        """Read a map's schedule slots, defaulting to the current map."""
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return None

        if self._keeps_schedule_tables:
            return await self._read_schedule_tables(map_index)

        read = await self._read_schedules(map_index)
        return None if read is None else read[0]

    async def refresh_changed_schedules(self, map_id: int | None = None) -> list[dict[str, Any]] | None:
        """Read a map's schedule slots only when the mower holds a new version.

        The mower does not announce a changed schedule, so noticing an edit made
        elsewhere takes asking. Its version comes out of a single read, which is
        cheap enough to ask for regularly, and the plans themselves are only read
        back once that version moved.
        """
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return None

        # A mower that keeps tables reports the version of every task in the
        # table read itself, and only a task that moved is read back, so a full
        # refresh is as cheap as the poll gets.
        if self._keeps_schedule_tables:
            return await self.refresh_schedules(map_id)

        # The version only says anything about the map it was read from: every
        # map counts its own, so the same number on another map means nothing.
        if self._schedules is not None and self._schedule_map_index == map_index:
            info = await self._get_schedule_info(map_index)
            if info is not None and info[1] == self._schedule_version:
                return self.schedules

        return await self.refresh_schedules(map_id)

    def _update_schedule_cache(
        self,
        map_index: int,
        schedules: Sequence[Mapping[str, Any]],
        version: int | None,
    ) -> None:
        """Cache the schedule slots of a map, which only describe the current one."""
        if not self._targets_current_map(map_index):
            return

        self._schedules = [deepcopy(dict(schedule)) for schedule in schedules]
        self._schedule_map_index = map_index
        self._schedule_version = version
        self._notify_property_change(SCHEDULES_PROPERTY_NAME, deepcopy(self._schedules))

    async def set_schedule_enabled(
        self,
        slot: int,
        enabled: bool,
        map_id: int | None = None,
    ) -> list[dict[str, Any]] | None:
        """Switch one schedule slot of a map on or off.

        The mower runs a single schedule at a time, so switching a slot on
        switches every other slot of that map off. Returns the slots that took
        effect, or None when the mower refused the write or answered unreadably.
        """
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return None

        if self._keeps_schedule_tables:
            return await self._write_schedule_table_state(map_index, slot, enabled)

        return await self._write_schedule_document_state(map_index, slot, enabled)

    async def _write_schedule_document_state(
        self,
        map_index: int,
        slot: int,
        enabled: bool,
    ) -> list[dict[str, Any]] | None:
        """Switch one schedule slot of a map on or off through the schedule document."""
        # The write has to quote the version the mower holds its schedules under,
        # so the slots are read back before every write. A write the mower rejects
        # for a stale version is taken once more against the version it reports
        # then, which is all a client can do about a schedule that changed
        # underneath it.
        for _ in range(2):
            read = await self._read_schedules(map_index)
            if read is None:
                return None

            schedules, version = read
            try:
                return await self._write_schedule_states(map_index, schedules, version, slot, enabled)
            except _StaleScheduleVersion:
                _LOGGER.debug(
                    "Schedule write of map index %s quoted a version the mower no longer holds",
                    map_index,
                )

        _LOGGER.error(
            "Failed to switch schedule slot %s of map index %s: the stored schedule keeps changing",
            slot,
            map_index,
        )
        return None

    async def _write_schedule_states(
        self,
        map_index: int,
        schedules: list[dict[str, Any]],
        version: int,
        slot: int,
        enabled: bool,
    ) -> list[dict[str, Any]] | None:
        """Write which schedule slots of a map are enabled, switching one of them.

        Raises _StaleScheduleVersion when the mower rejects the write because the
        stored schedule moved on from the version the write quotes.
        """
        target = next((schedule for schedule in schedules if schedule["slot"] == slot), None)
        if target is None:
            raise ValueError(f"This mower keeps no schedule in slot {slot}")

        if enabled and not target["tasks_stored"]:
            raise ValueError(f"The schedule in slot {slot} holds no tasks to run")

        # The mower addresses the slots by position, so the states are only
        # writable while every slot it reported is accounted for. A plan that
        # could not be read leaves a hole, and writing around it would move every
        # state that follows onto the wrong slot.
        if [schedule["slot"] for schedule in schedules] != list(range(len(schedules))):
            _LOGGER.error(
                "Refusing to switch schedule slot %s of map index %s: the mower reported the slots %s",
                slot,
                map_index,
                [schedule["slot"] for schedule in schedules],
            )
            return None

        flags = [
            (schedule["slot"] == slot) if enabled else (schedule["enabled"] and schedule["slot"] != slot)
            for schedule in schedules
        ]

        result = await self._send_task_payload(
            "schedule state write",
            self._build_set_schedule_enabled_payload(map_index, version, flags),
        )
        data = self._extract_custom_action_data(result)
        status = data.get("r") if isinstance(data, dict) else None
        if status == SCHEDULE_STATUS_VERSION_ERROR:
            raise _StaleScheduleVersion

        if status != SCHEDULE_STATUS_SUCCESS or not isinstance(data, dict):
            _LOGGER.error(
                "Failed to switch schedule slot %s of map index %s %s: %s",
                slot,
                map_index,
                "on" if enabled else "off",
                result,
            )
            return None

        for schedule, flag in zip(schedules, flags):
            schedule["enabled"] = flag

        # The mower moves the version on every write it accepts, and the next
        # write has to quote the one it reports here.
        try:
            version = int(data["v"])
        except (KeyError, TypeError, ValueError):
            _LOGGER.debug("Schedule write of map index %s reported no new version: %s", map_index, data)

        self._update_schedule_cache(map_index, schedules, version)
        _LOGGER.info(
            "Schedule slot %s of map index %s is now %s",
            slot,
            map_index,
            "enabled" if enabled else "disabled",
        )
        return schedules

    @property
    def _keeps_schedule_tables(self) -> bool:
        """Return whether the mower keeps its schedules as tables, not as a document."""
        return self._account_type == "mova" and not self._schedule_tables_unsupported

    @property
    def _schedule_document_keys(self) -> tuple[str, str, str]:
        """Return the info, data and enable keys of the schedule document."""
        if self._account_type == "mova":
            return SCHEDULE_MOVA_INFO_KEY, SCHEDULE_MOVA_DATA_KEY, SCHEDULE_MOVA_ENABLE_KEY
        return SCHEDULE_INFO_KEY, SCHEDULE_DATA_KEY, SCHEDULE_ENABLE_KEY

    @staticmethod
    def _refuses_schedule_tables(result: Any) -> bool:
        """Return whether a table read was answered by a mower that keeps no tables."""
        if not isinstance(result, dict) or result.get("code") not in (None, 0):
            return False

        out_entries = result.get("out")
        if not isinstance(out_entries, list):
            return False

        return any(
            isinstance(out_entry, dict)
            and "r" not in out_entry
            and out_entry.get("d") == SCHEDULE_TABLE_UNSUPPORTED_REPLY
            for out_entry in out_entries
        )

    @staticmethod
    def _decode_schedule_table_task(task: Any) -> list[dict[str, Any]]:
        """Decode one task of a schedule table into one entry per week day it runs on.

        A task the mower holds switched off does not run, so it yields nothing.
        """
        if not isinstance(task, (list, tuple)) or len(task) <= SCHEDULE_TABLE_TASK_REGIONS_INDEX:
            raise ValueError(f"not a task record: {task}")

        if not task[SCHEDULE_TABLE_TASK_ENABLED_INDEX]:
            return []

        task_type = int(task[SCHEDULE_TABLE_TASK_TYPE_INDEX])
        if task_type >= SCHEDULE_TABLE_CYCLIC_TYPE_OFFSET:
            task_type -= SCHEDULE_TABLE_CYCLIC_TYPE_OFFSET
        start_time = int(task[SCHEDULE_TABLE_TASK_START_INDEX])
        regions = task[SCHEDULE_TABLE_TASK_REGIONS_INDEX]
        if not isinstance(regions, list):
            regions = []

        entries: list[dict[str, Any]] = []
        for week_day in task[SCHEDULE_TABLE_TASK_DAYS_INDEX]:
            week_day = int(week_day)
            entry: dict[str, Any] = {
                "week_day": (
                    SCHEDULE_WEEK_DAYS[week_day] if 0 <= week_day < len(SCHEDULE_WEEK_DAYS) else "unknown"
                ),
                "type": SCHEDULE_TASK_TYPE_MAPPING.get(task_type, "unknown"),
                "start_time": start_time,
            }
            if task_type == ScheduleTaskType.ZONE:
                entry["zone_ids"] = [int(zone_id) for zone_id in regions]
            elif task_type == ScheduleTaskType.EDGE:
                entry["edges"] = [[int(value) for value in pair] for pair in regions]
            entries.append(entry)

        return entries

    async def _get_schedule_table_task(
        self,
        table_id: int,
        task_id: int,
        version: int,
    ) -> list[dict[str, Any]] | None:
        """Read and decode one task of a schedule table, reusing an unchanged one."""
        cached = self._schedule_table_tasks.get((table_id, task_id))
        if cached is not None and cached[0] == version:
            return deepcopy(cached[1])

        result = await self._send_task_payload(
            "schedule task read",
            self._build_get_schedule_table_task_payload(table_id, task_id),
        )
        status, data = self._preference_response(result)
        if status not in (None, 0) or not isinstance(data, list):
            _LOGGER.error("Failed to read task %s of schedule table %s: %s", task_id, table_id, result)
            return None

        try:
            entries = self._decode_schedule_table_task(data)
        except (TypeError, ValueError) as ex:
            _LOGGER.warning("Failed to decode task %s of schedule table %s: %s", task_id, table_id, ex)
            return None

        self._schedule_table_tasks[(table_id, task_id)] = (version, deepcopy(entries))
        return entries

    async def _decode_schedule_table(self, map_index: int, table: Any) -> dict[str, Any] | None:
        """Describe the schedule slot one table of a map stands for."""
        if not isinstance(table, (list, tuple)) or len(table) <= SCHEDULE_TABLE_TASKS_INDEX:
            _LOGGER.error("Schedule table is not a table record: %s", table)
            return None

        try:
            table_id = int(table[SCHEDULE_TABLE_ID_INDEX])
            enabled = bool(table[SCHEDULE_TABLE_ENABLED_INDEX])
        except (TypeError, ValueError):
            _LOGGER.error("Schedule table carries no number and state: %s", table)
            return None

        slot = table_id - map_index * SCHEDULE_SLOT_COUNT
        if not 0 <= slot < SCHEDULE_SLOT_COUNT:
            _LOGGER.error("Schedule table %s does not belong to map index %s", table_id, map_index)
            return None

        task_infos = table[SCHEDULE_TABLE_TASKS_INDEX]
        if not isinstance(task_infos, list):
            task_infos = []

        # As with the document, a table that holds tasks can be switched on even
        # when some of them could not be read: only the mower knows what they mean.
        tasks: list[dict[str, Any]] = []
        for task_info in task_infos:
            try:
                task_id, version = int(task_info[0]), int(task_info[1])
            except (IndexError, KeyError, TypeError, ValueError):
                _LOGGER.warning("Schedule table %s lists a task it does not identify: %s", table_id, task_info)
                continue

            entries = await self._get_schedule_table_task(table_id, task_id, version)
            if entries is not None:
                tasks.extend(entries)

        # Every task spans several week days, so the entries are put in the order
        # the week runs in, as the document lists them.
        def week_order(task: dict[str, Any]) -> tuple[int, int]:
            week_day = task["week_day"]
            day = SCHEDULE_WEEK_DAYS.index(week_day) if week_day in SCHEDULE_WEEK_DAYS else len(SCHEDULE_WEEK_DAYS)
            return day, int(task["start_time"])

        tasks.sort(key=week_order)
        name = table[SCHEDULE_TABLE_NAME_INDEX]
        return {
            "slot": slot,
            "enabled": enabled,
            "name": str(name) if isinstance(name, str) and name else None,
            "tasks": tasks,
            "tasks_stored": bool(task_infos),
        }

    async def _read_schedule_tables(self, map_index: int) -> list[dict[str, Any]] | None:
        """Read the schedule slots of a map from the tables that stand for them."""
        table_ids = [map_index * SCHEDULE_SLOT_COUNT + slot for slot in range(SCHEDULE_SLOT_COUNT)]
        result = await self._send_task_payload(
            "schedule table read",
            self._build_get_schedule_tables_payload(table_ids),
        )
        if self._refuses_schedule_tables(result):
            _LOGGER.info("This mower keeps no schedule tables, reading its schedules as a document instead")
            self._schedule_tables_unsupported = True
            read = await self._read_schedules(map_index)
            return None if read is None else read[0]

        status, data = self._preference_response(result)
        if status not in (None, 0) or not isinstance(data, list):
            _LOGGER.error("Failed to read the schedule tables of map index %s: %s", map_index, result)
            return None

        schedules: list[dict[str, Any]] = []
        for table in data:
            schedule = await self._decode_schedule_table(map_index, table)
            if schedule is not None:
                schedules.append(schedule)

        schedules.sort(key=lambda schedule: schedule["slot"])
        self._update_schedule_cache(map_index, schedules, None)
        return schedules

    async def _write_schedule_table_state(
        self,
        map_index: int,
        slot: int,
        enabled: bool,
    ) -> list[dict[str, Any]] | None:
        """Switch the table that stands for one schedule slot of a map on or off.

        The mower runs a single table of a map at a time and switches the other
        one off itself, so the slots are read back afterwards to report what took
        effect.
        """
        schedules = await self._read_schedule_tables(map_index)
        if schedules is None:
            return None

        # The read may just have found that the mower keeps a document instead.
        if not self._keeps_schedule_tables:
            return await self._write_schedule_document_state(map_index, slot, enabled)

        target = next((schedule for schedule in schedules if schedule["slot"] == slot), None)
        if target is None:
            raise ValueError(f"This mower keeps no schedule in slot {slot}")

        if enabled and not target["tasks_stored"]:
            raise ValueError(f"The schedule in slot {slot} holds no tasks to run")

        result = await self._send_task_payload(
            "schedule table state write",
            self._build_set_schedule_table_enabled_payload(map_index * SCHEDULE_SLOT_COUNT + slot, enabled),
        )
        status, _ = self._preference_response(result)
        if status != SCHEDULE_STATUS_SUCCESS:
            _LOGGER.error(
                "Failed to switch schedule slot %s of map index %s %s: %s",
                slot,
                map_index,
                "on" if enabled else "off",
                result,
            )
            return None

        _LOGGER.info(
            "Schedule slot %s of map index %s is now %s",
            slot,
            map_index,
            "enabled" if enabled else "disabled",
        )

        read_back = await self._read_schedule_tables(map_index)
        if read_back is not None:
            return read_back

        # The write took effect even though the read back did not come through.
        for schedule in schedules:
            if schedule["slot"] == slot:
                schedule["enabled"] = enabled
            elif enabled:
                schedule["enabled"] = False
        self._update_schedule_cache(map_index, schedules, None)
        return schedules

    def refresh_current_map_id(self) -> bool:
        """Refresh the current map by querying the MAPL getter."""
        try:
            result = self._cloud_device.action(
                SCHEDULING_TASK_PROPERTY.siid,
                SCHEDULING_TASK_PROPERTY.piid,
                [self._build_get_map_list_payload()],
            )
        except Exception as ex:
            _LOGGER.debug("Failed to query MAPL for current map: %s", ex)
            return False

        current_map_id = self._current_map_id_from_map_list_result(result)
        if current_map_id is None:
            _LOGGER.debug("MAPL response did not expose a current map: %s", result)
            return False

        self._apply_current_map_id(current_map_id)
        return True

    def _apply_current_map_id(self, current_map_id: int | None) -> None:
        """Take on the active map the mower reports, announcing it when it changed."""
        if current_map_id is None or self._current_map_id == current_map_id:
            return

        if self._current_map_id is not None:
            _LOGGER.info("Active map changed from map ID %s to %s", self._current_map_id, current_map_id)
        self._current_map_id = current_map_id
        self._reset_cutting_height_cache()
        self._notify_property_change(CURRENT_MAP_ID_PROPERTY_NAME, current_map_id)

    def _build_get_mowing_preference_payload(
        self,
        map_index: int,
        area_id: int = MOWING_PREFERENCE_GLOBAL_AREA_ID,
    ) -> dict[str, Any]:
        """Build the 2:50 getter payload for a mowing preference record."""
        return {
            "m": "g",
            "t": "PRE",
            "d": {
                "idx": map_index,
                "region": area_id,
            },
        }

    def _build_set_mowing_preference_payload(self, record: Sequence[int]) -> dict[str, Any]:
        """Build the 2:50 setter payload for a mowing preference record."""
        return {
            "m": "s",
            "t": "PRE",
            "d": [int(value) for value in record],
        }

    def _build_get_preference_info_payload(self, map_index: int) -> dict[str, Any]:
        """Build the 2:50 getter payload for a map's preference overview."""
        return {
            "m": "g",
            "t": "PREI",
            "d": {
                "idx": map_index,
            },
        }

    def _build_set_preference_mode_payload(
        self,
        map_index: int,
        mode: MowingPreferenceMode,
    ) -> dict[str, Any]:
        """Build the 2:50 setter payload for a map's preference mode."""
        return {
            "m": "s",
            "t": "PREP",
            "d": {
                "idx": map_index,
                "value": int(mode),
            },
        }

    @staticmethod
    def _preference_response(result: Any) -> tuple[int | None, Any]:
        """Split a preference response into its status and payload data.

        Either half is None when the response does not carry it: a write only
        reports a status, and a malformed response reports neither.
        """
        if not isinstance(result, dict):
            return None, None

        if result.get("code") not in (None, 0):
            return None, None

        out_entries = result.get("out")
        if not isinstance(out_entries, list):
            return None, None

        for out_entry in out_entries:
            if not isinstance(out_entry, dict):
                continue

            status = out_entry.get("r")
            normalized_status = status if isinstance(status, int) and not isinstance(status, bool) else None
            data = out_entry.get("d")

            if normalized_status is not None or data is not None:
                return normalized_status, data

        return None, None

    @staticmethod
    def _normalize_preference_record(data: Any) -> list[int] | None:
        """Coerce a response payload into a mowing preference record."""
        if not isinstance(data, list) or not data:
            return None

        try:
            return [int(value) for value in data]
        except (TypeError, ValueError):
            return None

    async def _get_mowing_preference(
        self,
        map_index: int,
        area_id: int = MOWING_PREFERENCE_GLOBAL_AREA_ID,
    ) -> list[int] | None:
        """Read one mowing preference record, or None when it is unavailable."""
        result = await self._send_task_payload(
            "mowing preference read",
            self._build_get_mowing_preference_payload(map_index, area_id),
        )
        status, data = self._preference_response(result)
        record = self._normalize_preference_record(data)
        if status not in (None, MOWING_PREFERENCE_STATUS_SUCCESS) or record is None:
            _LOGGER.error(
                "Failed to read the mowing preference for map index %s area %s: %s",
                map_index,
                area_id,
                result,
            )
            return None

        return record

    async def _get_preference_info(
        self,
        map_index: int,
    ) -> tuple[MowingPreferenceMode | None, list[int]]:
        """Read a map's preference mode and the area IDs it holds records for."""
        result = await self._send_task_payload(
            "mowing preference info",
            self._build_get_preference_info_payload(map_index),
        )
        status, data = self._preference_response(result)
        if status not in (None, MOWING_PREFERENCE_STATUS_SUCCESS) or not isinstance(data, dict):
            _LOGGER.error("Failed to read the preference info for map index %s: %s", map_index, result)
            return None, []

        mode: MowingPreferenceMode | None = None
        try:
            mode = MowingPreferenceMode(int(data["type"]))
        except (KeyError, TypeError, ValueError):
            _LOGGER.debug("Preference info for map index %s carries no known mode: %s", map_index, data)

        # Each entry of the version list pairs an area ID with the version of the
        # record the device holds for it.
        configured_area_ids: list[int] = []
        versions = data.get("ver")
        if isinstance(versions, list):
            for version_entry in versions:
                if not isinstance(version_entry, (list, tuple)) or not version_entry:
                    continue
                try:
                    configured_area_ids.append(int(version_entry[0]))
                except (TypeError, ValueError):
                    continue

        return mode, configured_area_ids

    async def _set_preference_mode(self, map_index: int, mode: MowingPreferenceMode) -> bool:
        """Write a map's preference mode."""
        result = await self._send_task_payload(
            "mowing preference mode write",
            self._build_set_preference_mode_payload(map_index, mode),
        )
        status, _ = self._preference_response(result)
        if not result or status not in (None, MOWING_PREFERENCE_STATUS_SUCCESS):
            _LOGGER.error(
                "Failed to set the preference mode of map index %s to %s: %s",
                map_index,
                mode.name,
                result,
            )
            return False

        return True

    async def _set_mowing_preference(
        self,
        record: Sequence[int],
        minimum_length: int = 0,
    ) -> bool:
        """Write a complete mowing preference record back to the device.

        A record the device rejects as too long is retried in the shorter legacy
        layout, unless that would cut off a slot the write has to carry.
        """
        result = await self._send_task_payload(
            "mowing preference write",
            self._build_set_mowing_preference_payload(record),
        )
        status, _ = self._preference_response(result)

        if (
            status == MOWING_PREFERENCE_STATUS_INVALID
            and minimum_length > MOWING_PREFERENCE_LEGACY_LENGTH
        ):
            _LOGGER.error(
                "Device rejected the mowing preference record and the setting it carries "
                "is not part of the shorter record it accepts",
            )
            return False

        if status == MOWING_PREFERENCE_STATUS_INVALID and len(record) > MOWING_PREFERENCE_LEGACY_LENGTH:
            _LOGGER.debug(
                "Device rejected the full mowing preference record; retrying with %d slots",
                MOWING_PREFERENCE_LEGACY_LENGTH,
            )
            result = await self._send_task_payload(
                "mowing preference write (short record)",
                self._build_set_mowing_preference_payload(record[:MOWING_PREFERENCE_LEGACY_LENGTH]),
            )
            status, _ = self._preference_response(result)

        if not result or status not in (None, MOWING_PREFERENCE_STATUS_SUCCESS):
            _LOGGER.error("Failed to write the mowing preference record %s: %s", list(record), result)
            return False

        return True

    def _preference_map_index(self, map_id: int | None) -> int | None:
        """Resolve the map index a per-map request targets."""
        if map_id is None:
            map_id = self.current_map_id

        if map_id is None:
            _LOGGER.error("No map is selected, so a per-map record cannot be addressed")
            return None

        if not self._validate_map_id(map_id):
            return None

        return self._map_index_from_id(map_id)

    def _zone_ids_for_map(self, map_id: int | None) -> list[int]:
        """Return the zone IDs known for a map, or an empty list when unknown."""
        if self._vector_map is None:
            return []

        if map_id is None:
            map_id = self.current_map_id

        parsed_maps = getattr(self._vector_map, "maps", None)
        map_geometry = parsed_maps.get(map_id) if isinstance(parsed_maps, dict) else None
        if map_geometry is None:
            if map_id is not None and map_id != self.current_map_id:
                return []
            map_geometry = self._resolved_vector_map()

        if map_geometry is None:
            return []

        return [int(zone.zone_id) for zone in map_geometry.zones]

    def _validate_preference_zone_id(self, zone_id: int, map_id: int | None) -> bool:
        """Return True when the zone exists on the targeted map."""
        available_zone_ids = self._zone_ids_for_map(map_id)
        if not available_zone_ids:
            # No geometry for that map is loaded, so the device has to decide.
            return True

        if zone_id not in available_zone_ids:
            _LOGGER.error(
                "Requested unknown zone ID %s; available zones: %s",
                zone_id,
                sorted(available_zone_ids),
            )
            return False

        return True

    def _targets_current_map(self, map_index: int) -> bool:
        """Return True when a map index addresses the currently selected map."""
        current_map_id = self.current_map_id
        return current_map_id is not None and self._map_index_from_id(current_map_id) == map_index

    def _reset_cutting_height_cache(self) -> None:
        """Drop the cached preferences, which only describe the current map."""
        self._cutting_height = None
        self._zone_cutting_heights = {}
        self._edge_mowing_settings = None
        self._zone_edge_mowing_settings = {}
        self._mowing_direction = None
        self._zone_mowing_directions = {}
        self._mowing_preference_mode = None
        self._mowing_records = {}
        # The schedules are stored per map too, so what is cached describes a map
        # that is no longer the current one.
        self._schedules = None
        self._schedule_map_index = None
        self._schedule_version = None

    def _update_cutting_height_cache(
        self,
        map_index: int,
        height_cm: float,
        zone_id: int | None = None,
    ) -> None:
        """Cache a cutting height when it belongs to the current map."""
        if not self._targets_current_map(map_index):
            return

        if zone_id is not None:
            if self._zone_cutting_heights.get(zone_id) != height_cm:
                self._zone_cutting_heights[zone_id] = height_cm
                self._notify_property_change(
                    ZONE_CUTTING_HEIGHTS_PROPERTY_NAME,
                    dict(self._zone_cutting_heights),
                )
            return

        if height_cm != self._cutting_height:
            self._cutting_height = height_cm
            self._notify_property_change(CUTTING_HEIGHT_PROPERTY_NAME, height_cm)

    def _update_edge_mowing_cache(
        self,
        map_index: int,
        settings: dict[str, bool],
        zone_id: int | None = None,
    ) -> None:
        """Cache edge mowing settings when they belong to the current map."""
        if not self._targets_current_map(map_index):
            return

        if zone_id is not None:
            if self._zone_edge_mowing_settings.get(zone_id) != settings:
                self._zone_edge_mowing_settings[zone_id] = dict(settings)
                self._notify_property_change(
                    ZONE_EDGE_MOWING_SETTINGS_PROPERTY_NAME,
                    self.zone_edge_mowing_settings,
                )
            return

        if settings != self._edge_mowing_settings:
            self._edge_mowing_settings = dict(settings)
            self._notify_property_change(EDGE_MOWING_SETTINGS_PROPERTY_NAME, dict(settings))

    def _update_mowing_direction_cache(
        self,
        map_index: int,
        direction: dict[str, int],
        zone_id: int | None = None,
    ) -> None:
        """Cache a mowing direction when it belongs to the current map."""
        if not self._targets_current_map(map_index):
            return

        if zone_id is not None:
            if self._zone_mowing_directions.get(zone_id) != direction:
                self._zone_mowing_directions[zone_id] = dict(direction)
                self._notify_property_change(
                    ZONE_MOWING_DIRECTIONS_PROPERTY_NAME,
                    self.zone_mowing_directions,
                )
            return

        if direction != self._mowing_direction:
            self._mowing_direction = dict(direction)
            self._notify_property_change(MOWING_DIRECTION_PROPERTY_NAME, dict(direction))

    def _update_preference_mode_cache(self, map_index: int, mode: MowingPreferenceMode) -> None:
        """Cache a preference mode when it belongs to the current map."""
        if not self._targets_current_map(map_index):
            return

        if mode != self._mowing_preference_mode:
            self._mowing_preference_mode = mode
            self._notify_property_change(MOWING_PREFERENCE_MODE_PROPERTY_NAME, mode)

    @staticmethod
    def _normalize_cutting_height(height_cm: float) -> float:
        """Snap a requested cutting height to a settable value in centimetres."""
        try:
            requested_height = float(height_cm)
        except (TypeError, ValueError) as ex:
            raise ValueError(f"Cutting height must be a number; got {height_cm!r}") from ex

        if not CUTTING_HEIGHT_MIN_CM <= requested_height <= CUTTING_HEIGHT_ABSOLUTE_MAX_CM:
            raise ValueError(
                f"Cutting height must be between {CUTTING_HEIGHT_MIN_CM} cm and "
                f"{CUTTING_HEIGHT_ABSOLUTE_MAX_CM} cm; got {requested_height}"
            )

        return round(requested_height / CUTTING_HEIGHT_STEP_CM) * CUTTING_HEIGHT_STEP_CM

    @staticmethod
    def _record_cutting_height(record: Sequence[int]) -> float | None:
        """Return the cutting height a record carries, in centimetres."""
        if len(record) <= MOWING_PREFERENCE_CUTTING_HEIGHT_INDEX:
            return None

        return record[MOWING_PREFERENCE_CUTTING_HEIGHT_INDEX] / 10.0

    @staticmethod
    def _record_edge_mowing_settings(record: Sequence[int]) -> dict[str, bool] | None:
        """Return the edge mowing settings a record carries.

        Settings the record is too short to carry are left out rather than
        reported as off, so a firmware that predates one is told apart from a
        device that has it switched off.
        """
        settings: dict[str, bool] = {}
        for key, index in (
            (EDGE_MOWING_AUTO_KEY, MOWING_PREFERENCE_EDGE_MOWING_AUTO_INDEX),
            (EDGE_BLADE_OFFSET_KEY, MOWING_PREFERENCE_EDGE_BLADE_OFFSET_INDEX),
            (EDGE_MOWING_SAFE_KEY, MOWING_PREFERENCE_EDGE_MOWING_SAFE_INDEX),
        ):
            if len(record) > index:
                settings[key] = bool(record[index])

        return settings or None

    @staticmethod
    def _edge_mowing_slots(
        record: Sequence[int],
        auto: bool | None,
        blade_offset: bool | None,
        safe: bool | None,
    ) -> dict[int, int]:
        """Return the record slots that switch the requested edge settings.

        Raises when the record does not reach a slot a request needs, which is
        how a firmware without that setting reports it.
        """
        slots: dict[int, int] = {}
        for value, index, name in (
            (auto, MOWING_PREFERENCE_EDGE_MOWING_AUTO_INDEX, "automatic edge mowing"),
            (blade_offset, MOWING_PREFERENCE_EDGE_BLADE_OFFSET_INDEX, "the edge blade offset"),
            (safe, MOWING_PREFERENCE_EDGE_MOWING_SAFE_INDEX, "safe edge mowing"),
        ):
            if value is None:
                continue
            if len(record) <= index:
                raise ValueError(f"This mower does not support {name}")
            slots[index] = int(value)

        # An offset blade disc needs more than one lap along the edge to cover it,
        # and the mower turns the setting down while it is told to mow one lap.
        if (
            blade_offset
            and len(record) > MOWING_PREFERENCE_EDGE_MOWING_LAPS_INDEX
            and record[MOWING_PREFERENCE_EDGE_MOWING_LAPS_INDEX] < MOWING_PREFERENCE_EDGE_BLADE_OFFSET_MIN_LAPS
        ):
            slots[MOWING_PREFERENCE_EDGE_MOWING_LAPS_INDEX] = MOWING_PREFERENCE_EDGE_BLADE_OFFSET_MIN_LAPS

        return slots

    @staticmethod
    def _record_mowing_settings(record: Sequence[int], camera: bool = True) -> dict[str, Any]:
        """Return every setting a record carries, under the setting keys.

        A setting the record is too short to carry is left out, and so is AI
        obstacle recognition on a mower without a camera, which carries the
        slot without acting on it.
        """

        def slot(index: int) -> int | None:
            return int(record[index]) if len(record) > index else None

        settings: dict[str, Any] = {}
        if (value := slot(MOWING_PREFERENCE_EFFICIENCY_INDEX)) is not None:
            settings[EFFICIENCY_KEY] = _enum_name(MowingEfficiency, value)
        if (value := slot(MOWING_PREFERENCE_CUTTING_HEIGHT_INDEX)) is not None:
            settings[CUTTING_HEIGHT_KEY] = value / 10.0
        if (value := slot(MOWING_PREFERENCE_DIRECTION_MODE_INDEX)) is not None:
            settings[DIRECTION_MODE_KEY] = _enum_name(MowingDirectionMode, value)
        if (value := slot(MOWING_PREFERENCE_DIRECTION_ANGLE_INDEX)) is not None:
            settings[DIRECTION_ANGLE_KEY] = value % MOWING_DIRECTION_ANGLE_PERIOD_DEGREES
        for key, index in (
            (EDGE_MOWING_AUTO_KEY, MOWING_PREFERENCE_EDGE_MOWING_AUTO_INDEX),
            (EDGE_OBSTACLE_AVOIDANCE_KEY, MOWING_PREFERENCE_EDGE_OBSTACLE_AVOIDANCE_INDEX),
            (EDGE_BLADE_OFFSET_KEY, MOWING_PREFERENCE_EDGE_BLADE_OFFSET_INDEX),
            (LIDAR_OBSTACLE_KEY, MOWING_PREFERENCE_LIDAR_OBSTACLE_INDEX),
            (EDGE_MOWING_SAFE_KEY, MOWING_PREFERENCE_EDGE_MOWING_SAFE_INDEX),
        ):
            if (value := slot(index)) is not None:
                settings[key] = bool(value)
        if (value := slot(MOWING_PREFERENCE_OBSTACLE_HEIGHT_INDEX)) is not None:
            settings[OBSTACLE_HEIGHT_KEY] = value
        if (value := slot(MOWING_PREFERENCE_OBSTACLE_DISTANCE_INDEX)) is not None:
            settings[OBSTACLE_DISTANCE_KEY] = value
        if camera and (value := slot(MOWING_PREFERENCE_AI_OBSTACLE_INDEX)) is not None:
            settings[AI_OBSTACLE_KEY] = [str(kind.name).lower() for kind in AiObstacleKind if value & kind]
        if (value := slot(MOWING_PREFERENCE_TURNING_METHOD_INDEX)) is not None:
            settings[TURNING_METHOD_KEY] = _enum_name(TurningMethod, value)
        return settings

    @classmethod
    def _mowing_settings_slots(
        cls, record: Sequence[int], settings: Mapping[str, Any], camera: bool = True
    ) -> dict[int, int]:
        """Return the record slots that carry the requested settings.

        Raises on a value a setting does not take, when the record does not
        reach a slot a request needs, which is how a firmware without that
        setting reports it, and on AI obstacle recognition for a mower without
        a camera.
        """
        slots: dict[int, int] = {}

        def put(index: int, value: int, name: str) -> None:
            if len(record) <= index:
                raise ValueError(f"This mower does not support {name}")
            slots[index] = value

        def choice(enum: type[IntEnum], key: str) -> int:
            try:
                return int(enum[str(settings[key]).upper()])
            except KeyError as ex:
                names = ", ".join(member.name.lower() for member in enum)
                raise ValueError(f"{key} must be one of {names}; got {settings[key]!r}") from ex

        def one_of(values: Sequence[int], key: str) -> int:
            value = int(settings[key])
            if value not in values:
                raise ValueError(f"{key} must be one of {', '.join(map(str, values))}; got {value}")
            return value

        if EFFICIENCY_KEY in settings:
            put(MOWING_PREFERENCE_EFFICIENCY_INDEX, choice(MowingEfficiency, EFFICIENCY_KEY), "the mowing efficiency")
        if CUTTING_HEIGHT_KEY in settings:
            height = cls._normalize_cutting_height(settings[CUTTING_HEIGHT_KEY])
            put(MOWING_PREFERENCE_CUTTING_HEIGHT_INDEX, int(round(height * 10)), "the cutting height")
        if DIRECTION_MODE_KEY in settings:
            put(MOWING_PREFERENCE_DIRECTION_MODE_INDEX, choice(MowingDirectionMode, DIRECTION_MODE_KEY), "the mowing direction")
        if DIRECTION_ANGLE_KEY in settings:
            angle = cls._normalize_mowing_direction_angle(settings[DIRECTION_ANGLE_KEY])
            put(MOWING_PREFERENCE_DIRECTION_ANGLE_INDEX, angle, "the mowing direction")
        if any(key in settings for key in (EDGE_MOWING_AUTO_KEY, EDGE_BLADE_OFFSET_KEY, EDGE_MOWING_SAFE_KEY)):
            slots.update(
                cls._edge_mowing_slots(
                    record,
                    settings.get(EDGE_MOWING_AUTO_KEY),
                    settings.get(EDGE_BLADE_OFFSET_KEY),
                    settings.get(EDGE_MOWING_SAFE_KEY),
                )
            )
        for key, index, name in (
            (EDGE_OBSTACLE_AVOIDANCE_KEY, MOWING_PREFERENCE_EDGE_OBSTACLE_AVOIDANCE_INDEX, "obstacle avoidance on edges"),
            (LIDAR_OBSTACLE_KEY, MOWING_PREFERENCE_LIDAR_OBSTACLE_INDEX, "LiDAR obstacle recognition"),
        ):
            if key in settings:
                put(index, int(bool(settings[key])), name)
        if OBSTACLE_HEIGHT_KEY in settings:
            put(MOWING_PREFERENCE_OBSTACLE_HEIGHT_INDEX, one_of(OBSTACLE_HEIGHTS_CM, OBSTACLE_HEIGHT_KEY), "the obstacle avoidance height")
        if OBSTACLE_DISTANCE_KEY in settings:
            put(MOWING_PREFERENCE_OBSTACLE_DISTANCE_INDEX, one_of(OBSTACLE_DISTANCES_CM, OBSTACLE_DISTANCE_KEY), "the obstacle avoidance distance")
        if AI_OBSTACLE_KEY in settings:
            if not camera:
                raise ValueError("This mower does not support AI obstacle recognition")
            mask = 0
            for name in settings[AI_OBSTACLE_KEY]:
                try:
                    mask |= AiObstacleKind[str(name).upper()]
                except KeyError as ex:
                    names = ", ".join(str(kind.name).lower() for kind in AiObstacleKind)
                    raise ValueError(f"{AI_OBSTACLE_KEY} takes {names}; got {name!r}") from ex
            put(MOWING_PREFERENCE_AI_OBSTACLE_INDEX, mask, "AI obstacle recognition")
        if TURNING_METHOD_KEY in settings:
            put(MOWING_PREFERENCE_TURNING_METHOD_INDEX, choice(TurningMethod, TURNING_METHOD_KEY), "the turning method")

        # Avoiding obstacles along the edges needs something that recognises
        # them, so it goes off once neither the LiDAR nor the camera does. A
        # mower without a camera only has the LiDAR, whatever its AI slot says.
        def after(index: int) -> int | None:
            if index in slots:
                return slots[index]
            return int(record[index]) if len(record) > index else None

        if (
            after(MOWING_PREFERENCE_EDGE_OBSTACLE_AVOIDANCE_INDEX)
            and after(MOWING_PREFERENCE_LIDAR_OBSTACLE_INDEX) == 0
            and (not camera or after(MOWING_PREFERENCE_AI_OBSTACLE_INDEX) in (0, None))
        ):
            slots[MOWING_PREFERENCE_EDGE_OBSTACLE_AVOIDANCE_INDEX] = 0

        return slots

    def _record_for_write(
        self,
        record: Sequence[int],
        map_index: int,
        area_id: int,
        slot_values: Mapping[int, int],
    ) -> list[int]:
        """Return a copy of a record addressed at an area and carrying new slots."""
        updated_record = list(record)
        updated_record[MOWING_PREFERENCE_VERSION_INDEX] = MOWING_PREFERENCE_WRITE_VERSION
        updated_record[MOWING_PREFERENCE_MAP_INDEX_INDEX] = map_index
        updated_record[MOWING_PREFERENCE_AREA_ID_INDEX] = area_id
        for index, value in slot_values.items():
            updated_record[index] = value
        return updated_record

    @staticmethod
    def _record_mowing_direction(record: Sequence[int]) -> dict[str, int] | None:
        """Return the mowing direction a record carries, or None where it has none.

        The angle is the one the app shows, folded into half a turn: a direction
        is a line, so anything beyond that names a line already in the range.
        """
        if len(record) <= MOWING_PREFERENCE_DIRECTION_ANGLE_INDEX:
            return None

        return {
            MOWING_DIRECTION_MODE_KEY: int(record[MOWING_PREFERENCE_DIRECTION_MODE_INDEX]),
            MOWING_DIRECTION_ANGLE_KEY: int(record[MOWING_PREFERENCE_DIRECTION_ANGLE_INDEX])
            % MOWING_DIRECTION_ANGLE_PERIOD_DEGREES,
        }

    @staticmethod
    def _mowing_direction_slots(
        record: Sequence[int],
        angle_degrees: int | None,
        mode: MowingDirectionMode | None,
    ) -> dict[int, int]:
        """Return the record slots that carry a mowing direction.

        Raises when the record does not reach the slots, which is how a firmware
        without the setting reports it.
        """
        slots: dict[int, int] = {}
        if angle_degrees is None and mode is None:
            return slots

        if len(record) <= MOWING_PREFERENCE_DIRECTION_ANGLE_INDEX:
            raise ValueError("This mower does not report a mowing direction")

        if angle_degrees is not None:
            slots[MOWING_PREFERENCE_DIRECTION_ANGLE_INDEX] = (
                int(angle_degrees) % MOWING_DIRECTION_ANGLE_PERIOD_DEGREES
            )
        if mode is not None:
            slots[MOWING_PREFERENCE_DIRECTION_MODE_INDEX] = int(mode)

        return slots

    @staticmethod
    def _normalize_mowing_direction_angle(angle_degrees: float) -> int:
        """Snap a requested mowing direction to a whole degree within half a turn."""
        try:
            requested_angle = float(angle_degrees)
        except (TypeError, ValueError) as ex:
            raise ValueError(f"Mowing direction must be a number; got {angle_degrees!r}") from ex

        return int(round(requested_angle)) % MOWING_DIRECTION_ANGLE_PERIOD_DEGREES

    @staticmethod
    def _cutting_height_slots(height_cm: float) -> dict[int, int]:
        """Return the record slots that carry a cutting height."""
        return {MOWING_PREFERENCE_CUTTING_HEIGHT_INDEX: int(round(height_cm * 10))}

    async def refresh_cutting_height(self, map_id: int | None = None) -> float | None:
        """Read the map-wide cutting height in cm, defaulting to the current map."""
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return None

        record = await self._refresh_map_wide_record(map_index)
        if record is None:
            return None

        return self._record_cutting_height(record)

    async def refresh_mowing_direction(self, map_id: int | None = None) -> dict[str, int] | None:
        """Read the map-wide mowing direction, defaulting to the current map."""
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return None

        record = await self._refresh_map_wide_record(map_index)
        if record is None:
            return None

        return self._record_mowing_direction(record)

    async def set_mowing_direction(
        self,
        angle_degrees: float | None = None,
        mode: MowingDirectionMode | None = None,
        map_id: int | None = None,
        zone_id: int | None = None,
    ) -> bool:
        """Set the direction the mower mows in, keeping the unspecified part as it is.

        Without a zone the direction of the whole map is set: the map-wide
        record, and the record of every zone of a map that follows its per-zone
        records, since such a map no longer reads the map-wide one. With a zone
        only that zone is changed, and the map is switched to its per-zone
        records so the change actually takes effect.
        """
        if angle_degrees is None and mode is None:
            return True

        normalized_angle = (
            None if angle_degrees is None else self._normalize_mowing_direction_angle(angle_degrees)
        )

        def build_slots(record: Sequence[int]) -> dict[int, int]:
            return self._mowing_direction_slots(record, normalized_angle, mode)

        described = []
        if normalized_angle is not None:
            described.append(f"{normalized_angle}°")
        if mode is not None:
            described.append(mode.name.lower())
        description = "Mowing direction set to " + ", ".join(described)

        if not await self._change_mowing_preference(map_id, zone_id, build_slots, description):
            return False

        if zone_id is not None:
            return True

        return await self._carry_map_wide_change_into_zones(map_id, build_slots, description)

    async def refresh_mowing_preferences(self, map_id: int | None = None) -> bool:
        """Read a map's map-wide record, updating every setting it carries."""
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return False

        return await self._refresh_map_wide_record(map_index) is not None

    async def _refresh_map_wide_record(self, map_index: int) -> list[int] | None:
        """Read a map's map-wide record and cache every setting it carries."""
        record = await self._get_mowing_preference(map_index)
        if record is None:
            return None

        self._cache_record_settings(map_index, record)
        return record

    def _cache_record_settings(
        self,
        map_index: int,
        record: Sequence[int],
        zone_id: int | None = None,
    ) -> None:
        """Cache every setting a mowing preference record carries."""
        if self._targets_current_map(map_index):
            self._mowing_records[MOWING_PREFERENCE_GLOBAL_AREA_ID if zone_id is None else zone_id] = list(record)

        height_cm = self._record_cutting_height(record)
        if height_cm is not None:
            self._update_cutting_height_cache(map_index, height_cm, zone_id=zone_id)

        edge_settings = self._record_edge_mowing_settings(record)
        if edge_settings is not None:
            self._update_edge_mowing_cache(map_index, edge_settings, zone_id=zone_id)

        direction = self._record_mowing_direction(record)
        if direction is not None:
            self._update_mowing_direction_cache(map_index, direction, zone_id=zone_id)

    async def refresh_zone_cutting_heights(self, map_id: int | None = None) -> dict[int, float]:
        """Read the per-zone cutting heights in cm, defaulting to the current map."""
        zone_records = await self.refresh_zone_mowing_preferences(map_id)
        zone_heights: dict[int, float] = {}
        for zone_id, record in zone_records.items():
            height_cm = self._record_cutting_height(record)
            if height_cm is not None:
                zone_heights[zone_id] = height_cm

        return zone_heights

    async def refresh_zone_mowing_preferences(self, map_id: int | None = None) -> dict[int, list[int]]:
        """Read the per-zone records of a map, defaulting to the current map.

        Only zones the device already holds a record for are reported; the rest
        follow the map-wide record until they are given one.
        """
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return {}

        mode, configured_area_ids = await self._get_preference_info(map_index)
        if mode is not None:
            self._update_preference_mode_cache(map_index, mode)

        zone_records: dict[int, list[int]] = {}
        for area_id in configured_area_ids:
            if area_id == MOWING_PREFERENCE_GLOBAL_AREA_ID:
                continue

            record = await self._get_mowing_preference(map_index, area_id)
            if record is not None:
                zone_records[area_id] = record

        self._replace_zone_caches(map_index, zone_records)
        return zone_records

    def _replace_zone_caches(self, map_index: int, zone_records: Mapping[int, Sequence[int]]) -> None:
        """Replace the per-zone caches with what a full read of a map reported."""
        if not self._targets_current_map(map_index):
            return

        self._mowing_records = {
            **{
                area_id: record
                for area_id, record in self._mowing_records.items()
                if area_id == MOWING_PREFERENCE_GLOBAL_AREA_ID
            },
            **{zone_id: list(record) for zone_id, record in zone_records.items()},
        }

        zone_heights: dict[int, float] = {}
        zone_edge_settings: dict[int, dict[str, bool]] = {}
        for zone_id, record in zone_records.items():
            height_cm = self._record_cutting_height(record)
            if height_cm is not None:
                zone_heights[zone_id] = height_cm

            edge_settings = self._record_edge_mowing_settings(record)
            if edge_settings is not None:
                zone_edge_settings[zone_id] = edge_settings

        if zone_heights != self._zone_cutting_heights:
            self._zone_cutting_heights = zone_heights
            self._notify_property_change(ZONE_CUTTING_HEIGHTS_PROPERTY_NAME, dict(zone_heights))

        if zone_edge_settings != self._zone_edge_mowing_settings:
            self._zone_edge_mowing_settings = zone_edge_settings
            self._notify_property_change(
                ZONE_EDGE_MOWING_SETTINGS_PROPERTY_NAME,
                self.zone_edge_mowing_settings,
            )

    async def set_mowing_preference_mode(
        self,
        mode: MowingPreferenceMode,
        map_id: int | None = None,
    ) -> bool:
        """Choose whether a map follows its map-wide record or its per-zone records.

        A zone that holds no record of its own is first given a copy of the
        map-wide record when the map turns to its per-zone records, so it keeps
        mowing as before instead of falling back to the device defaults.
        """
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return False

        if mode == MowingPreferenceMode.PER_ZONE:
            _, configured_area_ids = await self._get_preference_info(map_index)
            map_wide_record = await self._get_mowing_preference(map_index)
            if not await self._enable_per_zone_preferences(map_index, map_id, configured_area_ids, map_wide_record):
                return False
            _LOGGER.info("Map index %s now applies its %s mowing preferences", map_index, mode.name)
            return True

        if not await self._set_preference_mode(map_index, mode):
            return False

        _LOGGER.info("Map index %s now applies its %s mowing preferences", map_index, mode.name)
        self._update_preference_mode_cache(map_index, mode)
        return True

    async def _enable_per_zone_preferences(
        self,
        map_index: int,
        map_id: int | None,
        configured_area_ids: Sequence[int],
        map_wide_record: Sequence[int] | None,
    ) -> bool:
        """Switch a map to its per-zone records, leaving untouched zones as they were.

        A zone the device holds no record for has no settings of its own to fall
        back on once the map stops applying its map-wide record, so every such
        zone is first given a copy of that record.
        """
        map_wide_height = None if map_wide_record is None else self._record_cutting_height(map_wide_record)
        if map_wide_record is not None and map_wide_height is not None:
            already_configured = set(configured_area_ids)
            for zone_id in self._zone_ids_for_map(map_id):
                if zone_id in already_configured:
                    continue

                seeded_record = self._record_for_write(
                    map_wide_record,
                    map_index,
                    zone_id,
                    self._cutting_height_slots(map_wide_height),
                )
                # A zone the mower declines to seed keeps no record of its own and
                # falls back to the device defaults; that is worth a warning but
                # not worth abandoning the remaining zones over.
                if not await self._set_mowing_preference(seeded_record):
                    _LOGGER.warning(
                        "Zone %s keeps no mowing preference of its own; it may fall back to device defaults",
                        zone_id,
                    )

        if not await self._set_preference_mode(map_index, MowingPreferenceMode.PER_ZONE):
            return False

        self._update_preference_mode_cache(map_index, MowingPreferenceMode.PER_ZONE)
        return True

    async def _change_mowing_preference(
        self,
        map_id: int | None,
        zone_id: int | None,
        build_slots: Callable[[Sequence[int]], dict[int, int]],
        description: str,
    ) -> bool:
        """Change part of a mowing preference record, defaulting to the current map.

        Without a zone the map-wide record is changed. With a zone only that
        zone's record is, and the map is switched to its per-zone records so the
        change actually takes effect.

        A setting shares its record with every other mowing setting, so the
        record is read first and written back with only the requested slots
        changed. A zone that has no record of its own starts from a copy of the
        map-wide record.
        """
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return False

        if zone_id is not None and not self._validate_preference_zone_id(zone_id, map_id):
            return False

        map_wide_record = await self._get_mowing_preference(map_index)
        configured_area_ids: list[int] = []
        mode: MowingPreferenceMode | None = None
        base_record = map_wide_record

        if zone_id is not None:
            mode, configured_area_ids = await self._get_preference_info(map_index)
            if zone_id in configured_area_ids:
                base_record = await self._get_mowing_preference(map_index, zone_id) or map_wide_record

        if base_record is None:
            _LOGGER.error(
                "Cannot change the mowing settings of map index %s without its preference record",
                map_index,
            )
            return False

        slot_values = build_slots(base_record)
        if not slot_values:
            return True

        area_id = MOWING_PREFERENCE_GLOBAL_AREA_ID if zone_id is None else zone_id
        updated_record = self._record_for_write(base_record, map_index, area_id, slot_values)

        # Dropping the trailing slots of the record would drop the change itself
        # when it lives in one of them, so a write only falls back to the shorter
        # legacy record while it keeps every slot it changed.
        if not await self._set_mowing_preference(updated_record, max(slot_values) + 1):
            return False

        if zone_id is None:
            _LOGGER.info("%s for map index %s", description, map_index)
            self._cache_record_settings(map_index, updated_record)
            return True

        _LOGGER.info("%s for zone %s of map index %s", description, zone_id, map_index)
        self._cache_record_settings(map_index, updated_record, zone_id=zone_id)

        if mode != MowingPreferenceMode.PER_ZONE:
            await self._enable_per_zone_preferences(
                map_index,
                map_id,
                [*configured_area_ids, zone_id],
                map_wide_record,
            )

        return True

    async def set_cutting_height(
        self,
        height_cm: float,
        map_id: int | None = None,
        zone_id: int | None = None,
    ) -> bool:
        """Set a cutting height in cm, defaulting to the current map.

        Without a zone the map-wide height is set. With a zone only that zone is
        changed, and the map is switched to its per-zone records so the new
        height actually takes effect.
        """
        normalized_height = self._normalize_cutting_height(height_cm)

        def build_slots(record: Sequence[int]) -> dict[int, int]:
            if self._record_cutting_height(record) is None:
                raise ValueError("This mower does not report a cutting height")
            return self._cutting_height_slots(normalized_height)

        return await self._change_mowing_preference(
            map_id,
            zone_id,
            build_slots,
            f"Cutting height set to {normalized_height} cm",
        )

    async def set_edge_mowing_settings(
        self,
        auto: bool | None = None,
        blade_offset: bool | None = None,
        safe: bool | None = None,
        map_id: int | None = None,
        zone_id: int | None = None,
    ) -> bool:
        """Switch the edge mowing settings, keeping every unspecified one as it is.

        Without a zone the settings of the whole map are changed: the map-wide
        record, and the record of every zone of a map that follows its per-zone
        records, since such a map no longer reads the map-wide one. With a zone
        only that zone is changed, and the map is switched to its per-zone
        records so the change actually takes effect.
        """
        if auto is None and blade_offset is None and safe is None:
            return True

        def build_slots(record: Sequence[int]) -> dict[int, int]:
            return self._edge_mowing_slots(record, auto, blade_offset, safe)

        requested = {
            EDGE_MOWING_AUTO_KEY: auto,
            EDGE_BLADE_OFFSET_KEY: blade_offset,
            EDGE_MOWING_SAFE_KEY: safe,
        }
        description = "Edge mowing settings set to " + ", ".join(
            f"{key}={value}" for key, value in requested.items() if value is not None
        )

        if not await self._change_mowing_preference(map_id, zone_id, build_slots, description):
            return False

        if zone_id is not None:
            return True

        return await self._carry_map_wide_change_into_zones(map_id, build_slots, description)

    async def set_mowing_settings(
        self,
        settings: Mapping[str, Any],
        map_id: int | None = None,
        zone_id: int | None = None,
    ) -> bool:
        """Change any of the mowing settings at once, keeping the others as they are.

        `settings` holds the new values under the setting keys. Without a zone
        the settings of the whole map are changed: the map-wide record, and the
        record of every zone of a map that follows its per-zone records. With a
        zone only that zone is changed, and the map is switched to its per-zone
        records so the change actually takes effect.
        """
        if not settings:
            return True

        def build_slots(record: Sequence[int]) -> dict[int, int]:
            return self._mowing_settings_slots(record, settings, has_camera(self._model))

        description = "Mowing settings set to " + ", ".join(f"{key}={value}" for key, value in settings.items())

        if not await self._change_mowing_preference(map_id, zone_id, build_slots, description):
            return False

        if zone_id is not None:
            return True

        return await self._carry_map_wide_change_into_zones(map_id, build_slots, description)

    async def _carry_map_wide_change_into_zones(
        self,
        map_id: int | None,
        build_slots: Callable[[Sequence[int]], dict[int, int]],
        description: str,
    ) -> bool:
        """Repeat a map-wide change on the zones of a map that follows per-zone records.

        Such a map reads a zone's own record instead of the map-wide one, so a
        change meant for the map as a whole only reaches its zones by being
        written to each of them. Only the slots of the change are touched, so
        every other setting a zone keeps stays as it is. A map that still
        follows its map-wide record needs none of this.
        """
        map_index = self._preference_map_index(map_id)
        if map_index is None:
            return False

        mode, configured_area_ids = await self._get_preference_info(map_index)
        if mode != MowingPreferenceMode.PER_ZONE:
            return True

        # A zone the device holds no record for is included as well: it would
        # otherwise fall back to the device defaults rather than to the map-wide
        # record the change just went into.
        zone_ids = sorted(
            {area_id for area_id in configured_area_ids if area_id != MOWING_PREFERENCE_GLOBAL_AREA_ID}
            | set(self._zone_ids_for_map(map_id))
        )

        applied = True
        for zone_id in zone_ids:
            if not await self._change_mowing_preference(map_id, zone_id, build_slots, description):
                _LOGGER.warning(
                    "Zone %s of map index %s kept its own settings, so the map is no longer uniform",
                    zone_id,
                    map_index,
                )
                applied = False

        return applied

    def _build_all_area_task_payload(self, map_id: int, from_stop_point: bool | None = None) -> dict[str, Any]:
        """Build the 2:50 action payload for map-aware all-area mowing."""
        data: dict[str, Any] = {"region_id": [map_id], "area_id": []}
        if from_stop_point is not None:
            data[FROM_STOP_POINT_KEY] = from_stop_point
        return {"m": "a", "p": 0, "o": 100, "d": data}

    @staticmethod
    def _is_map_switch_echo(value: Any) -> bool:
        """Return whether a 2:50 task report is the echo of a map switch."""
        if not isinstance(value, dict) or value.get("t") != "TASK":
            return False
        data = value.get("d")
        return isinstance(data, dict) and data.get("o") == TASK_OPCODE_MAP_SWITCH

    def _build_set_current_map_payload(self, map_index: int) -> dict[str, Any]:
        """Build the 2:50 action payload for switching the active map."""
        return {
            "m": "a",
            "p": 0,
            "o": TASK_OPCODE_MAP_SWITCH,
            "d": {
                "idx": map_index,
            },
        }

    def _validate_zone_ids(self, zone_ids: list[int]) -> bool:
        """Return True when all requested zone IDs exist in the loaded map."""
        vector_map = self.vector_map
        if vector_map is None:
            return True

        available_zone_ids = {zone.zone_id for zone in vector_map.zones}
        invalid_zone_ids = [zone_id for zone_id in zone_ids if zone_id not in available_zone_ids]
        if invalid_zone_ids:
            _LOGGER.error(
                "Requested unknown zone IDs %s; available zones: %s",
                invalid_zone_ids,
                sorted(available_zone_ids),
            )
            return False

        return True

    def _build_zone_task_payload(self, zone_ids: list[int], from_stop_point: bool | None = None) -> dict[str, Any]:
        """Build the 2:50 action payload for a zone-selective mowing session."""
        data: dict[str, Any] = {"region": zone_ids}
        if from_stop_point is not None:
            data[FROM_STOP_POINT_KEY] = from_stop_point
        return {"m": "a", "p": 0, "o": 102, "d": data}

    def _validate_spot_area_ids(self, spot_area_ids: list[int]) -> bool:
        """Return True when all requested spot area IDs exist in the loaded map."""
        vector_map = self.vector_map
        if vector_map is None:
            return True

        available_spot_area_ids = {spot_area.area_id for spot_area in vector_map.spot_areas}
        invalid_spot_area_ids = [spot_area_id for spot_area_id in spot_area_ids if spot_area_id not in available_spot_area_ids]
        if invalid_spot_area_ids:
            _LOGGER.error(
                "Requested unknown spot area IDs %s; available spot areas: %s",
                invalid_spot_area_ids,
                sorted(available_spot_area_ids),
            )
            return False

        return True

    def _validate_maintenance_point_ids(self, point_ids: list[int]) -> bool:
        """Return True when every requested maintenance point exists on the active map."""
        vector_map = self.vector_map
        if vector_map is None:
            return True

        available_point_ids = {point.point_id for point in vector_map.maintenance_points}
        unknown_point_ids = [point_id for point_id in point_ids if point_id not in available_point_ids]
        if unknown_point_ids:
            _LOGGER.error(
                "Requested unknown maintenance point IDs %s; available points: %s",
                unknown_point_ids,
                sorted(available_point_ids),
            )
            return False

        return True

    def _build_maintenance_point_payload(self, point_ids: list[int]) -> dict[str, Any]:
        """Build the 2:50 action payload that sends the mower to maintenance points."""
        return {
            "m": "a",
            "p": 0,
            "o": 109,
            "d": {
                "point": point_ids,
            },
        }

    def _build_spot_task_payload(self, spot_area_ids: list[int]) -> dict[str, Any]:
        """Build the verified 2:50 action payload for spot mowing."""
        return {
            "m": "a",
            "p": 0,
            "o": 103,
            "d": {
                "area": spot_area_ids,
            },
        }

    async def start_mowing_all_area(self, map_id: int | None = None, *, from_stop_point: bool | None = None) -> bool:
        """Start all-area mowing, optionally targeting a specific map identifier.

        With `from_stop_point` the mower is told whether to mow only what an
        unfinished task left in its zones (True) or start them over (False);
        left out, it is not told.
        """
        if map_id is None:
            map_id = self.current_map_id

        if map_id is None:
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.refresh_current_map_id)
            except Exception as ex:
                _LOGGER.debug("Failed to refresh current map before all-area start fallback: %s", ex)

            map_id = self.current_map_id

        if map_id is None:
            if from_stop_point is not None:
                _LOGGER.error("All-area mowing needs the current map to say where to start from")
                return False
            _LOGGER.warning(
                "All-area mowing fell back to the generic START_MOWING action because no map_id was provided"
            )
            return await self.start_mowing_generic()

        if not self._validate_map_id(map_id):
            return False

        task_payload = self._build_all_area_task_payload(map_id, from_stop_point)
        result = await self._send_task_payload("all-area mowing", task_payload)
        if not result:
            _LOGGER.error("start_mowing_all_area command returned falsy result: %s", result)
            return False

        _LOGGER.info("All-area mowing started for map ID: %s", map_id)
        self._pose_coverage_handler.reset_mission_completion()
        self._notify_property_change("activity", "mowing")
        return True

    async def set_current_map(self, map_id: int) -> bool:
        """Switch the mower's current map using the map-switch payload.

        The mower only applies a map switch while no mowing task is in progress.
        With a task running it still acknowledges the command and then ignores
        it, so the switch is both refused up front and verified afterwards.
        """
        if not self._validate_map_id(map_id):
            return False

        if self.mowing_session_active:
            _LOGGER.error(
                "Cannot switch to map ID %s while a mowing task is in progress (task status: %s); "
                "finish or cancel the task first",
                map_id,
                self._misc_handler.task_status,
            )
            return False

        map_index = self._map_index_from_id(map_id)
        task_payload = self._build_set_current_map_payload(map_index)
        result = await self._send_task_payload("map switch", task_payload)
        if not result:
            _LOGGER.error("set_current_map command returned falsy result: %s", result)
            return False

        confirmed = await self._confirm_current_map(map_id)
        if confirmed is False:
            _LOGGER.error(
                "Map switch to map ID %s was acknowledged but the mower stayed on map ID %s; "
                "it only switches maps while no task is in progress",
                map_id,
                self._current_map_id,
            )
            return False

        if confirmed is None:
            _LOGGER.warning(
                "Could not read back the map list to confirm the switch to map ID %s; "
                "assuming the mower applied it",
                map_id,
            )
            self._current_map_id = map_id
            self._reset_cutting_height_cache()
            self._notify_property_change(CURRENT_MAP_ID_PROPERTY_NAME, map_id)

        _LOGGER.info("Current map switched to map ID %s (index %s)", map_id, map_index)
        return True

    async def _confirm_current_map(self, map_id: int) -> bool | None:
        """Re-read the map list until the mower reports the requested map.

        Returns True once the mower confirms the map, False when it keeps
        reporting a different one, and None when the map list stayed unreadable
        and the switch could therefore not be verified either way.
        """
        readable = False

        for attempt in range(MAP_SWITCH_VERIFY_ATTEMPTS):
            if attempt:
                await asyncio.sleep(MAP_SWITCH_VERIFY_DELAY_SECONDS)

            refreshed = await asyncio.get_event_loop().run_in_executor(None, self.refresh_current_map_id)
            if not refreshed:
                continue

            readable = True
            if self._current_map_id == map_id:
                return True

        return False if readable else None

    def _validate_contour_ids(self, contour_ids: list[list[int]]) -> bool:
        """Return True when all requested contour IDs are valid and available."""
        invalid_contour_ids: list[list[int]] = []

        for contour_id in contour_ids:
            if len(contour_id) != 2:
                invalid_contour_ids.append(contour_id)
                continue

            try:
                int(contour_id[0])
                int(contour_id[1])
            except (TypeError, ValueError):
                invalid_contour_ids.append(contour_id)

        if invalid_contour_ids:
            _LOGGER.error(
                "Contour IDs must be two-integer pairs such as [[1, 0]]; got: %s",
                invalid_contour_ids,
            )
            return False

        vector_map = self.vector_map
        if vector_map is None:
            return True

        available_contour_ids = {contour.contour_id for contour in vector_map.contours}
        unknown_contour_ids = [
            contour_id
            for contour_id in contour_ids
            if (contour_id[0], contour_id[1]) not in available_contour_ids
        ]
        if unknown_contour_ids:
            _LOGGER.error(
                "Requested unknown contour IDs %s; available contours: %s",
                unknown_contour_ids,
                [list(contour_id) for contour_id in sorted(available_contour_ids)],
            )
            return False

        return True

    def _build_edge_task_payload(self, contour_ids: list[list[int]]) -> dict[str, Any]:
        """Build the 2:50 action payload for an edge-mowing session."""
        return {
            "m": "a",
            "p": 0,
            "o": 101,
            "d": {
                "edge": contour_ids,
            },
        }

    async def _send_task_payload(self, task_name: str, task_payload: dict[str, Any]) -> Any:
        """Send a scheduling task payload via action 2:50.

        Raises DreameCommandError when the exchange does not complete, carrying
        the reason the connection gave. Callers therefore never have to tell a
        command the mower refused from one it never received: the first is a
        falsy return value, the second is this exception.
        """
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._cloud_device.action(
                    SCHEDULING_TASK_PROPERTY.siid,
                    SCHEDULING_TASK_PROPERTY.piid,
                    [task_payload],
                ),
            )
        except Exception as ex:
            raise DreameCommandError(f"Failed to send the {task_name} command: {ex}") from ex

    async def _send_action(self, action: ActionIdentifier) -> Any:
        """Run one of the mower's plain actions and return what it answered.

        The counterpart of _send_task_payload for the actions that carry no
        payload, and it answers a caller the same way: a falsy return value is
        the mower's own refusal, while a DreameCommandError means the exchange
        never completed and carries the reason the connection gave.
        """
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._cloud_device.action(action.siid, action.aiid),
            )
        except Exception as ex:
            raise DreameCommandError(f"Failed to send the {action.name} command: {ex}") from ex

    async def start_mowing_zones(self, zone_ids: list[int], *, from_stop_point: bool | None = None) -> bool:
        """Start mowing specific zones by their IDs; `from_stop_point` as for start_mowing_all_area."""
        if not zone_ids:
            _LOGGER.error("start_mowing_zones called with empty zone_ids")
            return False

        if not self._validate_zone_ids(zone_ids):
            return False

        task_payload = self._build_zone_task_payload(zone_ids, from_stop_point)
        result = await self._send_task_payload("zone mowing", task_payload)
        if not result:
            _LOGGER.error("start_mowing_zones command returned falsy result: %s", result)
            return False

        _LOGGER.info("Zone mowing started for zones: %s", zone_ids)
        self._pose_coverage_handler.reset_mission_completion()
        self._notify_property_change("activity", "mowing")
        return True

    async def start_mowing_edges(self, contour_ids: list[list[int]]) -> bool:
        """Start edge mowing for specific contours.

        Contour IDs are two-integer pairs such as [[1, 0], [2, 0]]: the zone and
        the index of one of its edges, as the contours of the map name them. In Home Assistant,
        these IDs are exposed in the mower entity's contours state attribute after
        the map has been fetched.
        """
        if not contour_ids:
            _LOGGER.error("start_mowing_edges called with empty contour_ids")
            return False

        if not self._validate_contour_ids(contour_ids):
            return False

        task_payload = self._build_edge_task_payload(contour_ids)
        result = await self._send_task_payload("edge mowing", task_payload)
        if not result:
            _LOGGER.error("start_mowing_edges command returned falsy result: %s", result)
            return False

        _LOGGER.info("Edge mowing started for contours: %s", contour_ids)
        self._pose_coverage_handler.reset_mission_completion()
        self._notify_property_change("activity", "mowing")
        return True

    async def start_mowing_spots(self, spot_area_ids: list[int]) -> bool:
        """Start spot mowing for one or more predefined spot areas."""
        if not spot_area_ids:
            _LOGGER.error("start_mowing_spots called with empty spot_area_ids")
            return False

        if not self._validate_spot_area_ids(spot_area_ids):
            return False

        task_payload = self._build_spot_task_payload(spot_area_ids)
        result = await self._send_task_payload("spot mowing", task_payload)
        if not result:
            _LOGGER.error("start_mowing_spots command returned falsy result: %s", result)
            return False

        _LOGGER.info("Spot mowing started for spot areas: %s", spot_area_ids)
        self._pose_coverage_handler.reset_mission_completion()
        self._notify_property_change("activity", "mowing")
        return True

    async def go_to_maintenance_point(self, point_ids: list[int]) -> bool:
        """Send the mower to one or more maintenance points of the active map.

        A maintenance point is a position on the map the mower drives to and
        waits at, which is where it is cleaned or serviced. The points belong to
        a map and are defined on the device itself.
        """
        if not point_ids:
            _LOGGER.error("go_to_maintenance_point called without a maintenance point")
            return False

        if not self._validate_maintenance_point_ids(point_ids):
            return False

        task_payload = self._build_maintenance_point_payload(point_ids)
        result = await self._send_task_payload("maintenance point run", task_payload)
        if not result:
            _LOGGER.error("go_to_maintenance_point command returned falsy result: %s", result)
            return False

        _LOGGER.info("Mower is on its way to maintenance points: %s", point_ids)
        return True

    async def start_mowing_mode(
        self,
        mode: MowingMode,
        *,
        map_id: int | None = None,
        zone_ids: list[int] | None = None,
        contour_ids: list[list[int]] | None = None,
        spot_area_ids: list[int] | None = None,
        from_stop_point: bool | None = None,
    ) -> bool:
        """Start mowing using an explicit mode-oriented API.

        Manual mode is represented explicitly so higher layers can model the full
        roadmap, but its outbound command format is still unverified.
        `from_stop_point` applies to all-area and zone mowing (see
        start_mowing_all_area).
        """
        if mode == MowingMode.ALL_AREA:
            return await self.start_mowing_all_area(map_id, from_stop_point=from_stop_point)

        if mode == MowingMode.ZONE:
            if not zone_ids:
                _LOGGER.error("Zone mowing requires at least one zone ID")
                return False
            return await self.start_mowing_zones(zone_ids, from_stop_point=from_stop_point)

        if mode == MowingMode.EDGE:
            if not contour_ids:
                _LOGGER.error("Edge mowing requires at least one contour ID")
                return False
            return await self.start_mowing_edges(contour_ids)

        if mode == MowingMode.SPOT:
            if not spot_area_ids:
                _LOGGER.error("Spot mowing requires at least one existing spot area ID")
                return False
            return await self.start_mowing_spots(spot_area_ids)

        if mode == MowingMode.MANUAL:
            _LOGGER.error("Manual mowing is not implemented yet; it appears to require Bluetooth")
            return False

        _LOGGER.error("Unsupported mowing mode requested: %s", mode)
        return False

    @property
    def zones(self) -> list[dict]:
        """Return available mowing zones from the vector map.

        Returns a list of dicts with keys: id, name, area.
        Returns empty list if vector map is not available.
        """
        vector_map = self.vector_map
        if vector_map is None:
            return []
        return [
            {"id": z.zone_id, "name": z.name, "area": z.area}
            for z in vector_map.zones
        ]

    @property
    def contours(self) -> list[list[int]]:
        """Return available edge-mowing contour IDs from the vector map."""
        vector_map = self.vector_map
        if vector_map is None:
            return []
        return [list(contour.contour_id) for contour in vector_map.contours]

    @property
    def maintenance_points(self) -> list[dict]:
        """Return the maintenance points of the active map, with their positions."""
        vector_map = self.vector_map
        if vector_map is None:
            return []
        return [
            {"id": point.point_id, "x": point.x, "y": point.y}
            for point in vector_map.maintenance_points
        ]

    async def pause(self) -> bool:
        """Pause current operation."""
        if not await self._send_action(ACTION_PAUSE):
            _LOGGER.error("Failed to send PAUSE command")
            return False
        self._notify_property_change("activity", "paused")
        return True

    async def end_task(self) -> bool:
        """End the running task; the mower stays where it is.

        The mower keeps where the task stopped in each zone, so the next task
        can continue from there.
        """
        if not await self._send_action(ACTION_STOP):
            _LOGGER.error("Failed to send STOP command")
            return False
        return True

    async def stop_returning(self) -> bool:
        """Stop the mower on its way back to the station; it stays where it is."""
        result = await self._send_task_payload("stop returning", TASK_PAYLOAD_STOP_RETURNING)
        if not result:
            _LOGGER.error("Failed to stop the return to the station")
            return False
        return True

    async def dock_without_stopping(self) -> bool:
        """Send mower to dock without stopping the active task.

        Sends ACTION_DOCK directly, leaving any in-progress task intact so it
        can be resumed later via resume().

        Returns:
            True if the dock command was sent successfully, False otherwise.
        """
        if not await self._send_action(ACTION_DOCK):
            _LOGGER.error("Failed to send DOCK command")
            return False

        self._notify_property_change("activity", "returning_to_charge")
        return True

    async def return_to_dock(self) -> bool:
        """Return mower to dock.
        
        Implements stop-then-dock sequence: first send STOP, wait for MISSION_COMPLETION 
        event (4:1), then send DOCK. Includes a 30-second timeout fallback.
        
        Returns:
            True if dock sequence completed successfully, False otherwise
        """
        # Clear any previous event state
        self._mission_completed_event.clear()
        
        # Send STOP command
        if not await self._send_action(ACTION_STOP):
            _LOGGER.error("Failed to send STOP command")
            return False
        
        self._notify_property_change("activity", "stopping")
        
        # Wait for MISSION_COMPLETION event (4:1) with 30-second timeout
        try:
            await asyncio.wait_for(self._mission_completed_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout waiting for mission completion event, sending DOCK anyway")
        
        # Send DOCK command
        if not await self._send_action(ACTION_DOCK):
            _LOGGER.error("Failed to send DOCK command")
            return False

        self._notify_property_change("activity", "docked")
        return True


class DreameSwbotDevice(DreameMowerDevice):
    """Device handler for Dreame pool robots (dreame.swbot.* series).

    The Z1 only exposes three MiOT properties via REST/MQTT:
      2:1  status  — 4 = cleaning, any other value = not cleaning
      3:1  battery
      1:1  heartbeat byte array (byte 9 bit 7 = charging flag, bits 0-6 = battery %)
    """

    # Status code reported by device when actively cleaning
    _SWBOT_STATUS_CLEANING = 4

    # Notification events reported by the pool robot (siid 20).
    # eiid 1 = cleaning task finished, eiid 2 = low battery.
    _SWBOT_EVENT_SIID = 20
    _SWBOT_EVENT_CLEAN_FINISH = 1
    _SWBOT_EVENT_LOW_BATTERY = 2

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._swbot_charging: bool | None = None

    @property
    def status(self) -> str:
        """Return pool robot status: cleaning / charging / idle."""
        if self._status_code == self._SWBOT_STATUS_CLEANING:
            return "cleaning"
        if self._swbot_charging:
            return "charging"
        return "idle"

    async def fetch_device_info(self) -> dict[str, Any] | None:
        """Fetch initial device state including charging flag from 1:1."""
        result = await super().fetch_device_info()
        # devices_list gives battery and status but not the charging flag.
        # Read 1:1 via get_properties to populate _swbot_charging immediately.
        try:
            loop = asyncio.get_event_loop()
            props = await loop.run_in_executor(
                None,
                lambda: self._cloud_device.get_properties(
                    [{"siid": PROPERTY_1_1.siid, "piid": PROPERTY_1_1.piid}]
                ),
            )
            if isinstance(props, list) and props:
                entry = props[0]
                if entry.get("code", -1) == 0:
                    self._decode_swbot_1_1(entry["value"])
        except Exception as ex:
            _LOGGER.warning("DreameSwbotDevice: failed to fetch initial 1:1 state: %s", ex)
        return result

    def _decode_swbot_1_1(self, value: list[int]) -> None:
        """Decode the 1:1 heartbeat byte array and update charging state.

        byte 9 bit 7 (0x80) = charging flag; bits 0-6 = battery percentage.
        """
        if not isinstance(value, (list, tuple)) or len(value) <= 9:
            return
        byte9 = int(value[9])
        charging = bool(byte9 & 0x80)
        battery = byte9 & 0x7F
        old_charging = self._swbot_charging
        self._swbot_charging = charging
        # Also update battery from heartbeat data if it looks valid (0-100)
        if 0 <= battery <= 100:
            old_battery = self._battery_percent
            self._battery_percent = battery
            if old_battery != battery:
                self._notify_property_change(BATTERY_PROPERTY.name, battery)
        if old_charging != charging:
            # Charging state change affects the derived status string
            self._notify_property_change(STATUS_PROPERTY.name, self._status_code)

    def _handle_mqtt_property_update(self, message: dict[str, Any]) -> bool:
        """Handle MQTT property updates for the pool robot."""
        try:
            siid = message["siid"]
            piid = message["piid"]

            if BATTERY_PROPERTY.matches(siid, piid):
                battery_value = int(message["value"])
                old_battery = self._battery_percent
                self._battery_percent = battery_value
                if old_battery != battery_value:
                    self._notify_property_change(BATTERY_PROPERTY.name, battery_value)
                return True

            if STATUS_PROPERTY.matches(siid, piid):
                status_code = int(message["value"])
                old_status_code = self._status_code
                self._status_code = status_code
                if old_status_code != status_code:
                    self._notify_property_change(STATUS_PROPERTY.name, status_code)
                    # The pool robot has no "cleaning started" event, so derive
                    # one from the status transition into the cleaning state.
                    if (status_code == self._SWBOT_STATUS_CLEANING
                            and old_status_code != self._SWBOT_STATUS_CLEANING):
                        self._notify_property_change(DEVICE_CODE_INFO_PROPERTY_NAME, {
                            "code": "CLEAN_START",
                            "name": "Cleaning Started",
                            "description": "The robot has started a cleaning task",
                            "timestamp": datetime.now().isoformat(),
                        })
                return True

            if PROPERTY_1_1.matches(siid, piid):
                self._decode_swbot_1_1(message["value"])
                return True

        except Exception as ex:
            _LOGGER.warning("DreameSwbotDevice: error handling property update: %s", ex)

        return False

    def _handle_mqtt_event(self, params: dict[str, Any]) -> bool:
        """Handle MQTT event messages for the pool robot.

        The pool robot does not expose a device code property; instead it
        reports user-facing notifications as MiOT events on siid 20:
          eiid 1 — cleaning task finished
          eiid 2 — low battery
        These are mapped onto the shared device-code notification pipeline so
        they surface as Home Assistant notifications like other devices.
        """
        # Event ids may arrive as ints or numeric strings; coerce defensively.
        siid: int | None
        eiid: int | None
        try:
            siid = int(params["siid"])
            eiid = int(params["eiid"])
        except (KeyError, TypeError, ValueError):
            siid = eiid = None

        if siid == self._SWBOT_EVENT_SIID:
            if eiid == self._SWBOT_EVENT_CLEAN_FINISH:
                self._notify_property_change(DEVICE_CODE_INFO_PROPERTY_NAME, {
                    "code": "CLEAN_FINISH",
                    "name": "Cleaning Complete",
                    "description": "The cleaning task has finished",
                    "timestamp": datetime.now().isoformat(),
                })
                return True

            if eiid == self._SWBOT_EVENT_LOW_BATTERY:
                self._notify_property_change(DEVICE_CODE_WARNING_PROPERTY_NAME, {
                    "code": "LOW_BATTERY",
                    "name": "Low Battery",
                    "description": "Battery is low, retrieve the robot and charge it",
                    "timestamp": datetime.now().isoformat(),
                })
                return True

        # Not a pool-robot notification event: fall back to the base handler
        # (firmware validation, mission completion, etc.).
        return super()._handle_mqtt_event(params)
