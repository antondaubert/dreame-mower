"""Constants for Dreame Mower Device Implementation."""

from __future__ import annotations
from typing import NamedTuple
from enum import IntEnum
import logging

from homeassistant.components.lawn_mower import LawnMowerActivity  # type: ignore[attr-defined]

_LOGGER = logging.getLogger(__name__)

class PropertyIdentifier(NamedTuple):
    """Property identifier with siid, piid values and property name."""
    siid: int
    piid: int
    name: str
    
    def matches(self, siid: int, piid: int) -> bool:
        """Check if given siid and piid match this property identifier."""
        return self.siid == siid and self.piid == piid


class ActionIdentifier(NamedTuple):
    """Action identifier with siid, aiid values and action name."""
    siid: int
    aiid: int
    name: str

    def matches(self, siid: int, aiid: int) -> bool:
        """Check if given siid and aiid match this action identifier."""
        return self.siid == siid and self.aiid == aiid


class EventIdentifier(NamedTuple):
    """Event identifier with siid, eiid values and event name."""
    siid: int
    eiid: int
    name: str

    def matches(self, siid: int, eiid: int) -> bool:
        """Check if given siid and eiid match this event identifier."""
        return self.siid == siid and self.eiid == eiid


# Number of consecutive offline heartbeat polls required before the device is
# flipped to offline. Debounces a transient cloud hiccup so entities don't flap
# to unavailable and back on a single missed poll.
ONLINE_OFFLINE_DEBOUNCE_POLLS = 3

# Device property identifiers
PROPERTY_1_1 = PropertyIdentifier(siid=1, piid=1, name="property_1_1")
FIRMWARE_INSTALL_STATE_PROPERTY = PropertyIdentifier(siid=1, piid=2, name="firmware_install_state")
FIRMWARE_DOWNLOAD_PROGRESS_PROPERTY = PropertyIdentifier(siid=1, piid=3, name="firmware_download_progress")
POSE_COVERAGE_PROPERTY = PropertyIdentifier(siid=1, piid=4, name="pose_coverage")
SERVICE1_PROPERTY_50 = PropertyIdentifier(siid=1, piid=50, name="service1_property_50")
SERVICE1_PROPERTY_51 = PropertyIdentifier(siid=1, piid=51, name="service1_property_51")
SERVICE1_COMPLETION_FLAG_PROPERTY = PropertyIdentifier(siid=1, piid=52, name="service1_completion_flag")
BLUETOOTH_PROPERTY = PropertyIdentifier(siid=1, piid=53, name="bluetooth_connected")
SERVICE1_PROPERTY_54 = PropertyIdentifier(siid=1, piid=54, name="service1_property_54")
SERVICE1_PROPERTY_55 = PropertyIdentifier(siid=1, piid=55, name="service1_property_55")

STATUS_PROPERTY = PropertyIdentifier(siid=2, piid=1, name="status")
DEVICE_CODE_PROPERTY = PropertyIdentifier(siid=2, piid=2, name="device_code")
SCHEDULING_TASK_PROPERTY = PropertyIdentifier(siid=2, piid=50, name="scheduling_task")
SETTINGS_CHANGE_PROPERTY = PropertyIdentifier(siid=2, piid=51, name="settings_change")
SCHEDULING_SUMMARY_PROPERTY = PropertyIdentifier(siid=2, piid=52, name="scheduling_summary")
SERVICE2_PROPERTY_53 = PropertyIdentifier(siid=2, piid=53, name="service2_property_53")
SERVICE2_PROPERTY_54 = PropertyIdentifier(siid=2, piid=54, name="service2_property_54")
SERVICE2_PROPERTY_55 = PropertyIdentifier(siid=2, piid=55, name="service2_property_55")
MOWER_CONTROL_STATUS_PROPERTY = PropertyIdentifier(siid=2, piid=56, name="mower_control_status")
POWER_STATE_PROPERTY = PropertyIdentifier(siid=2, piid=57, name="power_state")
SERVICE2_PROPERTY_60 = PropertyIdentifier(siid=2, piid=60, name="service2_property_60")
SERVICE2_PROPERTY_62 = PropertyIdentifier(siid=2, piid=62, name="service2_property_62")
SERVICE2_PROPERTY_63 = PropertyIdentifier(siid=2, piid=63, name="service2_property_63")
SERVICE2_PROPERTY_64 = PropertyIdentifier(siid=2, piid=64, name="service2_property_64")
SERVICE2_PROPERTY_65 = PropertyIdentifier(siid=2, piid=65, name="service2_property_65")
SERVICE2_PROPERTY_66 = PropertyIdentifier(siid=2, piid=66, name="service2_property_66")
SERVICE2_PROPERTY_67 = PropertyIdentifier(siid=2, piid=67, name="service2_property_67")

BATTERY_PROPERTY = PropertyIdentifier(siid=3, piid=1, name="battery_percent")
CHARGING_STATUS_PROPERTY = PropertyIdentifier(siid=3, piid=2, name="charging_status")

SERVICE5_PROPERTY_100 = PropertyIdentifier(siid=5, piid=100, name="service5_property_100")
SERVICE5_PROPERTY_101 = PropertyIdentifier(siid=5, piid=101, name="service5_property_101")
TASK_STATUS_PROPERTY = PropertyIdentifier(siid=5, piid=104, name="task_status")
SERVICE5_PROPERTY_105 = PropertyIdentifier(siid=5, piid=105, name="service5_property_105")
SERVICE5_PROPERTY_106 = PropertyIdentifier(siid=5, piid=106, name="service5_property_106")
SERVICE5_ENERGY_INDEX_PROPERTY = PropertyIdentifier(siid=5, piid=107, name="service5_energy_index")
SERVICE5_PROPERTY_108 = PropertyIdentifier(siid=5, piid=108, name="service5_property_108")

SERVICE6_PROPERTY_1 = PropertyIdentifier(siid=6, piid=1, name="service6_property_1")
SERVICE6_PROPERTY_3 = PropertyIdentifier(siid=6, piid=3, name="service6_property_3")

# Properties 99:10 and 99:20 provide file paths for downloadable files from the cloud, including:
# - Firmware/OTA update packages (when firmware updates are available)
# - Device log files (when user selects "Report logs" in the app)
# Files are automatically downloaded when these properties change
DEVICE_FILE_PATH_PROPERTY = PropertyIdentifier(siid=99, piid=10, name="device_file_path")
DEVICE_FILE_PATH_PROPERTY_20 = PropertyIdentifier(siid=99, piid=20, name="device_file_path_20")

# Device event identifiers
FIRMWARE_VALIDATION_EVENT = EventIdentifier(siid=1, eiid=1, name="firmware_validation")
MISSION_COMPLETION_EVENT = EventIdentifier(siid=4, eiid=1, name="mission_completion")

# Device action identifiers (siid 5)
ACTION_START_MOWING = ActionIdentifier(siid=5, aiid=1, name="start_mowing")
ACTION_STOP = ActionIdentifier(siid=5, aiid=2, name="stop")
ACTION_DOCK = ActionIdentifier(siid=5, aiid=3, name="dock")
ACTION_PAUSE = ActionIdentifier(siid=5, aiid=4, name="pause")

# Embedded protocol task payloads (sent via SCHEDULING_TASK_PROPERTY 2:50)
# Format: {m: 'a', p: <priority>, o: <opcode>, d?: <data>}
TASK_PAYLOAD_RESUME = {"m": "a", "p": 0, "o": 5}  # continueControl

# Mowing preference ("PRE") records
#
# The device keeps one mowing preference record per map and mowing area. The
# record is a flat integer array whose slots carry the mowing settings shown in
# the app (efficiency mode, cutting height, mowing direction, edge and obstacle
# behaviour, ...). Area ID 0 addresses the map-wide record that applies to the
# whole map; positive area IDs address per-zone overrides.
#
# Which of the two a map actually uses is decided by the map's preference mode,
# read with "PREI" and written with "PREP". While a map is in MAP_WIDE mode the
# per-zone records are stored but ignored.
#
# Only the slots the integration touches are named here; every other slot must
# be written back unchanged, so a write is always a read-modify-write of the
# record the device currently holds.
MOWING_PREFERENCE_GLOBAL_AREA_ID = 0
MOWING_PREFERENCE_VERSION_INDEX = 0
MOWING_PREFERENCE_MAP_INDEX_INDEX = 1
MOWING_PREFERENCE_AREA_ID_INDEX = 2
MOWING_PREFERENCE_CUTTING_HEIGHT_INDEX = 4
# Edge mowing slots, all of them flags that are 1 while the behaviour is on:
#   auto         mow the edges on their own once an all-area or zone run finished
#   blade offset shift the blade disc sideways for the edge laps, which cuts
#                closer to the boundary than the centred disc reaches
#   safe         keep a small buffer from the boundary while mowing the edges
MOWING_PREFERENCE_EDGE_MOWING_AUTO_INDEX = 7
MOWING_PREFERENCE_EDGE_BLADE_OFFSET_INDEX = 10
MOWING_PREFERENCE_EDGE_MOWING_LAPS_INDEX = 11
MOWING_PREFERENCE_EDGE_MOWING_SAFE_INDEX = 16
# The offset blade disc only covers the edge over more than one lap, so the mower
# rejects the setting while it is told to mow the edges a single time.
MOWING_PREFERENCE_EDGE_BLADE_OFFSET_MIN_LAPS = 2
# Records are written with the version slot zeroed; the device assigns the
# resulting record version itself.
MOWING_PREFERENCE_WRITE_VERSION = 0
# Firmware that predates the trailing record slots rejects a full-length record
# with MOWING_PREFERENCE_STATUS_INVALID. Such a write is retried with the record
# truncated to the layout those firmware versions accept. Safe edge mowing is the
# first slot beyond that layout, so those firmware versions do not offer it.
MOWING_PREFERENCE_LEGACY_LENGTH = 16
# Per-request status reported in the "r" field of a 2:50 response.
MOWING_PREFERENCE_STATUS_SUCCESS = 0
MOWING_PREFERENCE_STATUS_INVALID = -3


class MowingPreferenceMode(IntEnum):
    """Which mowing preference records a map applies."""

    MAP_WIDE = 0  # One record (area 0) governs the whole map
    PER_ZONE = 1  # Each zone follows its own record

# Cutting height limits in centimetres. The record carries the height in
# millimetres, adjustable in half-centimetre steps.
CUTTING_HEIGHT_STEP_CM = 0.5
CUTTING_HEIGHT_MIN_CM = 3.0
# Tallest cut any known model offers; the protocol-level upper bound.
CUTTING_HEIGHT_ABSOLUTE_MAX_CM = 10.0
# Cut height most models top out at.
CUTTING_HEIGHT_DEFAULT_MAX_CM = 7.0
# Model codes that offer the extended cutting height range.
_EXTENDED_CUTTING_HEIGHT_MODELS = ("g2529", "g2541")
# Model codes whose cutting height is not adjustable from software.
_FIXED_CUTTING_HEIGHT_MODELS = ("g2405", "g2420", "g2552", "g2583", "yc2530")


def _model_code(model: str) -> str:
    """Return the bare model code of a full model identifier.

    Model identifiers look like ``dreame.mower.g2408`` or ``mova.mower.g2405c``;
    the trailing segment is the model code, optionally suffixed by a hardware
    variant letter.
    """
    return model.rsplit(".", 1)[-1].strip().lower()


def supports_cutting_height(model: str) -> bool:
    """Return True when the model's cutting height can be set over the protocol."""
    model_code = _model_code(model)
    return not model_code.startswith(_FIXED_CUTTING_HEIGHT_MODELS)


def cutting_height_max_cm(model: str) -> float:
    """Return the tallest cut the model supports, in centimetres."""
    if _model_code(model).startswith(_EXTENDED_CUTTING_HEIGHT_MODELS):
        return CUTTING_HEIGHT_ABSOLUTE_MAX_CM
    return CUTTING_HEIGHT_DEFAULT_MAX_CM

# Device settings ("CFG") record
#
# The device keeps its user-facing settings in a single record that is read as a
# whole; each setting is written back on its own with the setter that owns its
# key. Only the keys the integration understands are named here, every other key
# is passed through as the device reports it.
DEVICE_SETTINGS_BATTERY_KEY = "BAT"
DEVICE_SETTINGS_RAIN_KEY = "WRP"

# Battery and charging settings ("BAT")
#
# The record holds the battery levels that drive docking and resuming, followed
# by the custom charging period. While that period is enabled the mower only
# keeps a safe battery level when idle and fully charges inside the period.
# Both times are minutes since midnight; an end time below the start time means
# the period runs past midnight into the next day.
BATTERY_SETTING_RECHARGE_LEVEL_INDEX = 0
BATTERY_SETTING_RESUME_LEVEL_INDEX = 1
BATTERY_SETTING_RESUME_AFTER_CHARGING_INDEX = 2
BATTERY_SETTING_CHARGING_PERIOD_ENABLED_INDEX = 3
BATTERY_SETTING_CHARGING_PERIOD_START_INDEX = 4
BATTERY_SETTING_CHARGING_PERIOD_END_INDEX = 5
BATTERY_SETTING_LENGTH = 6

# Rain protection settings ("WRP")
#
# The record holds the rain protection switch, the delay the mower waits after
# rain before it picks an interrupted task back up, and how much water it takes
# for the mower to consider it raining. The delay is in whole hours and only
# takes effect the next time rain protection triggers.
#
# Older firmware reports the record without the sensitivity slot; the slot is
# then assumed to be the least sensitive setting so the record can still be
# written back in full.
RAIN_SETTING_ENABLED_INDEX = 0
RAIN_SETTING_DELAY_INDEX = 1
RAIN_SETTING_SENSITIVITY_INDEX = 2
RAIN_SETTING_LENGTH = 3
RAIN_SETTING_MINIMUM_LENGTH = 2
RAIN_SETTING_DEFAULT_SENSITIVITY = 0

# The code the device reports while rain protection is keeping it off the lawn.
# It shows up both as a one-off announcement on the device code property and as
# a live bit in the heartbeat.
DEVICE_CODE_BAD_WEATHER_PROTECTING = 56
# Codes the device reports around rain, any of which means its plans changed
# because of the weather.
RAIN_DEVICE_CODES = frozenset({
    DEVICE_CODE_BAD_WEATHER_PROTECTING,
    57,  # a scheduled task was interrupted by rain
    58,  # a scheduled task was suspended because of rain
})

# A delay of zero means the mower stays docked after rain until it is started
# again, and is offered ahead of the hourly delays rather than after them.
RAIN_DELAY_MIN_HOURS = 0
RAIN_DELAY_MAX_HOURS = 24


# Times inside the settings record are minutes since midnight.
MINUTES_PER_DAY = 1440

# Device status mapping for STATUS_PROPERTY (2:1)
# 
# Charging State Refinement (via correlation with CHARGING_STATUS_PROPERTY 3:2):
# State 6 (charging) correlates with 3:2=1 (active_charging) - top-off/current flowing pulses
# State 13 (charging_complete) correlates with 3:2=2 (maintain) - balance/trickle plateau
# This refinement enables duty cycle metrics and distinguishes active vs maintenance charging.
# Contingency analysis shows >99.99% purity for these mappings across multi-hour sessions.
#
# State progression during charging:
#   State 5 (returning) → State 6 (active charging, 3:2=1) → State 13 (maintain, 3:2=2)
#
class DeviceStatus(IntEnum):
    """Device status codes for STATUS_PROPERTY (2:1)."""
    NO_STATUS = 0
    MOWING = 1
    STANDBY = 2
    PAUSED = 3
    PAUSED_DUE_TO_ERRORS = 4
    RETURNING_TO_CHARGE = 5
    CHARGING = 6
    MAPPING = 11
    CHARGING_COMPLETE = 13
    UPDATING = 14
    CHARGING_PAUSED_HIGH_TEMPERATURE = 15  # Charging paused: battery temperature too high (issue #167)
    CHARGING_PAUSED_LOW_TEMPERATURE = 16  # Charging paused: battery temperature too low (issue #40)
    MAINTENANCE_PAUSED = 75  # Paused at the maintenance point (issue #162)


STATUS_MAPPING: dict[int, str] = {
    DeviceStatus.NO_STATUS: "no_status",
    DeviceStatus.MOWING: "mowing",
    DeviceStatus.STANDBY: "standby",
    DeviceStatus.PAUSED: "paused",
    DeviceStatus.PAUSED_DUE_TO_ERRORS: "paused_due_to_errors",
    DeviceStatus.RETURNING_TO_CHARGE: "returning_to_station_to_charge",
    DeviceStatus.CHARGING: "charging",
    DeviceStatus.MAPPING: "mapping",
    DeviceStatus.CHARGING_COMPLETE: "charging_complete",
    DeviceStatus.UPDATING: "updating",
    DeviceStatus.CHARGING_PAUSED_HIGH_TEMPERATURE: "charging_paused_high_temperature",
    DeviceStatus.CHARGING_PAUSED_LOW_TEMPERATURE: "charging_paused_low_temperature",
    DeviceStatus.MAINTENANCE_PAUSED: "maintenance_paused"
}

def map_status_to_activity(status: int) -> LawnMowerActivity:
    """Map device status code to LawnMowerActivity.

    Keep mapping logic colocated with STATUS_MAPPING so behaviour is consistent
    across the integration.
    """
    if status in [DeviceStatus.MOWING]:
        return LawnMowerActivity.MOWING
    elif status in [DeviceStatus.STANDBY, DeviceStatus.PAUSED, DeviceStatus.MAINTENANCE_PAUSED]:
        return LawnMowerActivity.PAUSED
    elif status in [DeviceStatus.PAUSED_DUE_TO_ERRORS]:
        return LawnMowerActivity.ERROR
    elif status in [DeviceStatus.RETURNING_TO_CHARGE]:
        return LawnMowerActivity.RETURNING
    elif status in [
        DeviceStatus.CHARGING,
        DeviceStatus.MAPPING,
        DeviceStatus.CHARGING_COMPLETE,
        DeviceStatus.UPDATING,
        DeviceStatus.CHARGING_PAUSED_HIGH_TEMPERATURE,
        DeviceStatus.CHARGING_PAUSED_LOW_TEMPERATURE,
    ]:
        return LawnMowerActivity.DOCKED
    else:
        _LOGGER.warning("Unknown status %s, defaulting to DOCKED", status)
        return LawnMowerActivity.DOCKED

# Charging status mapping for CHARGING_STATUS_PROPERTY
CHARGING_STATUS_MAPPING: dict[int, str] = {
    0: "not_docked",
    1: "charging",
    2: "not_charging",
    3: "charging_completed",
    5: "return_to_charge",
    15: "charging_paused_high_temperature",  # Charging paused: battery temperature too high (issue #167)
    16: "charging_paused_low_temperature",  # Charging paused: battery temperature too low (issue #40)
}

# Firmware install state values for FIRMWARE_INSTALL_STATE_PROPERTY
FIRMWARE_INSTALL_STATE_NEW_AVAILABLE = 2

# Firmware install state mapping for FIRMWARE_INSTALL_STATE_PROPERTY
FIRMWARE_INSTALL_STATE_MAPPING: dict[int, str] = {
    1: "up_to_date",  # Idle / firmware is current (no update available)
    FIRMWARE_INSTALL_STATE_NEW_AVAILABLE: "new_firmware_available",
    3: "installing_firmware_after_download",
    4: "firmware_download_failed",  # Observed in issues #98, #134
}

# Individual property names
PROPERTY_FIRMWARE = "firmware"
PROPERTY_TEMPERATURE = "temperature"

# Derived state names reported through the device property callbacks
CURRENT_MAP_ID_PROPERTY_NAME = "current_map_id"
CUTTING_HEIGHT_PROPERTY_NAME = "cutting_height"
ZONE_CUTTING_HEIGHTS_PROPERTY_NAME = "zone_cutting_heights"
MOWING_PREFERENCE_MODE_PROPERTY_NAME = "mowing_preference_mode"
EDGE_MOWING_SETTINGS_PROPERTY_NAME = "edge_mowing_settings"
ZONE_EDGE_MOWING_SETTINGS_PROPERTY_NAME = "zone_edge_mowing_settings"

# Keys the edge mowing settings of one mowing preference record are reported
# under. Safe edge mowing is missing from the record of firmware that predates
# it, and is then absent from the settings rather than reported as off.
EDGE_MOWING_AUTO_KEY = "edge_mowing_auto"
EDGE_BLADE_OFFSET_KEY = "edge_blade_offset"
EDGE_MOWING_SAFE_KEY = "edge_mowing_safe"