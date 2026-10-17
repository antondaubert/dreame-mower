"""Constants for Dreame Mower Device Implementation."""

from __future__ import annotations
from typing import NamedTuple
from enum import IntEnum, IntFlag
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

# Seconds the cloud transport (MQTT) may stay down before the device is reported
# disconnected. The cloud broker drops the link now and then and the client
# reconnects within a second or two; without this grace every such drop flips all
# entities to unavailable and back.
TRANSPORT_DISCONNECT_GRACE_SECONDS = 60

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

# Properties the mower reports that nothing here acts on. They are taken in
# silently rather than reported as unhandled.
IGNORED_PROPERTIES: tuple[PropertyIdentifier, ...] = (
    # A flag without a value, sent once a session ended.
    SERVICE1_COMPLETION_FLAG_PROPERTY,
    # Device metadata: active_time, expire_time, num and sn.
    SERVICE1_PROPERTY_54,
    # An integer of unknown meaning.
    SERVICE1_PROPERTY_55,
    # Unknown; 100 is the only value known for either.
    SERVICE2_PROPERTY_53,
    SERVICE2_PROPERTY_54,
    # The zones of the running task, {"status": [[zone_id, code], ...]}: -1
    # queued, 0 mowing, 2 completed, 4 paused.
    MOWER_CONTROL_STATUS_PROPERTY,
    # Integers of unknown meaning.
    SERVICE2_PROPERTY_60,
    SERVICE2_PROPERTY_62,
    # A negative code of unknown meaning, such as -33101 or -33001.
    SERVICE2_PROPERTY_63,
    # Work statistics: the current week (cw), full week (fw), position (p),
    # work range (wr/ws) and more.
    SERVICE2_PROPERTY_64,
    # What the mower navigates to or relocates for: dm::TASK_NAV_DOCK,
    # dm::TASK_NAV_DIVIDE_REGION, dm::TASK_NAV_CRUISE_POINT, TASK_NAV_CHECK,
    # dm::TASK_SLAM_RELOCATE (when stuck), dm::TASK_SLAM_RELOCATE_NEARDOCK,
    # dm::TASK_SLAM_RELOCATE_OFFDOCK and dm::TASK_SLAM_EXIT_ERASE.
    # TODO: Consider doing something useful with this property change later
    SERVICE2_PROPERTY_65,
    # Arrays of two and of four integers of unknown meaning; 2:67 follows a
    # finished task.
    SERVICE2_PROPERTY_66,
    SERVICE2_PROPERTY_67,
    # 5:100 an integer, possibly followed by " time_diff=<seconds>"; 5:101
    # "success"; 5:104 a task status code (7: a spot task left unfinished);
    # 5:107 an energy index; 5:105, 5:106 and 5:108 integers.
    SERVICE5_PROPERTY_100,
    SERVICE5_PROPERTY_101,
    TASK_STATUS_PROPERTY,
    SERVICE5_PROPERTY_105,
    SERVICE5_PROPERTY_106,
    SERVICE5_ENERGY_INDEX_PROPERTY,
    SERVICE5_PROPERTY_108,
    # An integer and a [bool, int] pair of unknown meaning.
    SERVICE6_PROPERTY_1,
    SERVICE6_PROPERTY_3,
)

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
# Stop the mower on its way back to the station; it stays where it is.
TASK_PAYLOAD_STOP_RETURNING = {"m": "a", "p": 2, "o": 13}

# Opcode of a switch of the active map. The mower may echo it on 2:50 after a
# switch, whoever made it, but without saying which map is now active.
TASK_OPCODE_MAP_SWITCH = 200

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
# How fast the mower works: 0 standard, 1 efficient (faster, with less care
# around obstacles).
MOWING_PREFERENCE_EFFICIENCY_INDEX = 3
MOWING_PREFERENCE_CUTTING_HEIGHT_INDEX = 4
# Mowing direction slots:
#   mode   how the direction carries from one session to the next
#   angle  the direction itself, in degrees, as the app shows it
MOWING_PREFERENCE_DIRECTION_MODE_INDEX = 5
MOWING_PREFERENCE_DIRECTION_ANGLE_INDEX = 6
# Edge mowing slots, all of them flags that are 1 while the behaviour is on:
#   auto         mow the edges on their own once an all-area or zone run finished
#   blade offset shift the blade disc sideways for the edge laps, which cuts
#                closer to the boundary than the centred disc reaches
#   safe         keep a small buffer from the boundary while mowing the edges
MOWING_PREFERENCE_EDGE_MOWING_AUTO_INDEX = 7
MOWING_PREFERENCE_EDGE_BLADE_OFFSET_INDEX = 10
MOWING_PREFERENCE_EDGE_MOWING_LAPS_INDEX = 11
MOWING_PREFERENCE_EDGE_MOWING_SAFE_INDEX = 16
# Obstacle avoidance slots:
#   edge       steer around obstacles along the edges too, which may leave grass
#              uncut there; it needs something that detects obstacles
#   lidar      recognise obstacles with the LiDAR, 1 while on
#   height     the lowest obstacle avoided, in cm (OBSTACLE_HEIGHTS_CM)
#   distance   how far obstacles are kept away, in cm (OBSTACLE_DISTANCES_CM)
#   ai         the obstacle kinds the camera recognises, a mask of AiObstacleKind
MOWING_PREFERENCE_EDGE_OBSTACLE_AVOIDANCE_INDEX = 9
MOWING_PREFERENCE_LIDAR_OBSTACLE_INDEX = 12
MOWING_PREFERENCE_OBSTACLE_HEIGHT_INDEX = 13
MOWING_PREFERENCE_OBSTACLE_DISTANCE_INDEX = 14
MOWING_PREFERENCE_AI_OBSTACLE_INDEX = 15
# How the mower turns at the end of a lane: 0 efficient, 1 lawn care (wider
# turns that spare the lawn). Only firmware with the full record carries it.
MOWING_PREFERENCE_TURNING_METHOD_INDEX = 19
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


class MowingDirectionMode(IntEnum):
    """How the mowing direction carries from one session to the next."""

    FIXED = 0  # Every session mows in the set direction
    CRISSCROSS = 1  # Each session turns 45 degrees against the last one
    CHEQUERBOARD = 2  # Each session turns 90 degrees against the last one


# A mowing direction describes a line rather than a heading, so a direction and
# the one half a turn away from it are the same. Directions are therefore kept
# within half a turn, and angles beyond it fold back into that range.
MOWING_DIRECTION_ANGLE_PERIOD_DEGREES = 180


class MowingEfficiency(IntEnum):
    """How fast the mower works."""

    STANDARD = 0
    EFFICIENT = 1  # Faster, with less care around obstacles


class TurningMethod(IntEnum):
    """How the mower turns at the end of a lane."""

    EFFICIENT = 0
    LAWN_CARE = 1  # Wider turns that spare the lawn


class AiObstacleKind(IntFlag):
    """The obstacle kinds the camera can be told to recognise."""

    HUMANS = 1
    ANIMALS = 2
    OBJECTS = 4


# The values the obstacle avoidance height and distance take, in cm.
OBSTACLE_HEIGHTS_CM = (5, 10, 15, 20)
OBSTACLE_DISTANCES_CM = (10, 15, 20)


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
DEVICE_SETTINGS_ANTI_THEFT_KEY = "ATA"
# On/off settings of the record, each written as {"value": 0 | 1}:
#   FDP   frost protection: back to the station at 6 °C or less
#   PATH  steer around obstacles on the paths between zones
#   STUN  back to the station after an hour paused or idle outside it
#   AOP   photograph the obstacles the camera recognises
#   CLS   child lock: the control panel locks after five idle minutes
DEVICE_SETTINGS_FROST_PROTECTION_KEY = "FDP"
DEVICE_SETTINGS_PATH_OBSTACLE_AVOIDANCE_KEY = "PATH"
DEVICE_SETTINGS_AUTO_RECHARGE_KEY = "STUN"
DEVICE_SETTINGS_AI_OBSTACLE_PHOTOS_KEY = "AOP"
DEVICE_SETTINGS_CHILD_LOCK_KEY = "CLS"
# Settings with a time window, [on, start, end] in minutes after midnight; a
# window that ends before it starts runs over midnight:
#   DND  Do Not Disturb: no task starts, and a running one pauses and the mower
#        returns to its station
#   LOW  the mower drives slowly at night
DEVICE_SETTINGS_DO_NOT_DISTURB_KEY = "DND"
DEVICE_SETTINGS_LOW_SPEED_AT_NIGHT_KEY = "LOW"
# Going on from where an unfinished task stopped: [on, days a stop point is
# kept]; written as {"on": true | false, "day": days}. Switching it off clears
# the stop points the mower holds.
DEVICE_SETTINGS_STOP_POINT_KEY = "BP"
STOP_POINT_DAYS_RANGE = (1, 7)
# The lights: [custom period on, start, end (minutes, 0 to 1440), in standby,
# while working, while charging, on errors (, fill light)]; written as
# {"value", "time": [start, end], "light": [four scenes] (, "fill")}.
DEVICE_SETTINGS_LIGHT_KEY = "LIT"
LIGHT_SCENES = ("standby", "working", "charging", "error")
# Human presence alert: [on, sensitivity, in standby, while mowing, while
# returning, while patrolling, voice and notification, photo (, minutes
# between alerts)]; written as {"value", "sen", "mode": [four], "report":
# [voice, photo (, minutes)]}.
DEVICE_SETTINGS_HUMAN_PRESENCE_KEY = "REC"
HUMAN_PRESENCE_MODES = ("standby", "mowing", "returning", "patrolling")
HUMAN_PRESENCE_SENSITIVITIES = ("low", "medium", "high")
HUMAN_PRESENCE_INTERVALS_MINUTES = (3, 10, 20)
# The robot's voice: its volume (0 to 100), the kinds of prompt it speaks
# [regular notifications, work status, special status, errors], and
# [text language, voice language] by index into VOICE_LANGUAGES.
DEVICE_SETTINGS_VOLUME_KEY = "VOL"
DEVICE_SETTINGS_VOICE_PROMPTS_KEY = "VOICE"
DEVICE_SETTINGS_LANGUAGE_KEY = "LANG"
VOICE_PROMPTS = ("regular", "work_status", "special_status", "error_status")
VOICE_LANGUAGES = (
    "English", "Chinese", "German", "French", "Italian", "Spanish", "Portuguese", "Norwegian",
    "Swedish", "Danish", "Finnish", "Dutch", "Turkish", "Polish", "Russian", "Lithuanian",
)
# The mower's time zone, an IANA name.
DEVICE_SETTINGS_TIME_ZONE_KEY = "TIME"
# How the mower drives between the station and the zones: 0 the direct way,
# 1 a route that varies, to spare the lawn from ruts.
DEVICE_SETTINGS_NAVIGATION_PATH_KEY = "PROT"

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

# Anti-theft settings ("ATA")
#
# The record holds one slot per anti-theft switch: the alarm that goes off when
# the mower is lifted, the alarm that goes off when it leaves the map, and
# whether the mower reports its position while it is away. Models that ask for
# the PIN code before the mower may be switched off carry that switch as a
# fourth slot; every other model reports the record without it.
#
# Locking the mower and raising an alarm is all the mower does on its own. The
# off-map alarm and the position reports need the cellular module, and stay
# without effect on a mower that has none.
ANTI_THEFT_SETTING_LIFT_ALARM_INDEX = 0
ANTI_THEFT_SETTING_OFF_MAP_ALARM_INDEX = 1
ANTI_THEFT_SETTING_LOCATION_INDEX = 2
ANTI_THEFT_SETTING_PIN_CHECK_INDEX = 3
ANTI_THEFT_SETTING_LENGTH = 3

# Schedules
#
# Every map holds a fixed set of schedule slots, each a named plan of weekly
# mowing tasks. Only one slot runs at a time: switching one on switches the
# others off, which is how the mower keeps one plan per season.
#
# The plans of a map are read in three steps. An info read reports the byte
# length of the plan document and the version the mower currently holds, the
# document itself is then read in chunks of that many bytes, and the version has
# to be quoted in every following read or write so the mower can tell that the
# document has not changed underneath. A write that quotes a stale version is
# rejected and has to be taken again after a fresh read.
SCHEDULE_INFO_KEY = "SCHDIV3"
SCHEDULE_DATA_KEY = "SCHDDV3"
SCHEDULE_ENABLE_KEY = "SCHDSV3"

# MOVA mowers that refuse the table reads below keep their plans as the same
# document, one generation back. They do not answer the keys above at all, so
# only these reach them.
SCHEDULE_MOVA_INFO_KEY = "SCHDIV2"
SCHEDULE_MOVA_DATA_KEY = "SCHDDV2"
SCHEDULE_MOVA_ENABLE_KEY = "SCHDSV2"

# The maps of a mower are read from the mower itself in three steps. The map
# list reports which of its fixed map slots hold a map and which one is
# current, an info read reports the hash and byte length of one map, and the
# map document is then read in chunks. A data read carries no map index: it
# continues the map the info read before it named.
MAP_LIST_KEY = "MAPL"
MAP_INFO_KEY = "MAPI"
MAP_DATA_KEY = "MAPD"

# Bytes requested per chunk of a map document.
MAP_CHUNK_SIZE = 400

# Where the charging station stands is its own read: x and y in the map
# document's units (ten map units each) and its heading in tenths of a degree.
DOCK_KEY = "DOCK"
DOCK_POSITION_SCALE = 10
DOCK_YAW_SCALE = 10

# The trail of the running session is read back in pages of this many points,
# each five bytes: x and y as 20-bit signed values in pose units, as in the
# position reports. A page past the end comes back empty.
TRAIL_KEY = "MITRC"
TRAIL_PAGE_SIZE = 60
# A long session stays well below this many pages.
TRAIL_MAX_PAGES = 400

# Where the mower stands: x and y in pose units, its heading in 1/255 of a turn.
POSITION_KEY = "MPOS"

# Where an unfinished task left off in each zone of one map, by map index: the
# zone, how far it got in hundredths of a percent, and the day it stopped.
STOP_POINTS_KEY = "RGBPSTA"

# The totals of the work log: the area mowed in m², the time in minutes, the
# number of tasks, and since when (unix time) they are counted.
WORK_TOTALS_KEY = "MIHIS"
# The most tasks one read of the work log lists.
WORK_LOG_LIMIT = 500

# The kind of file a photo of a recognised obstacle is, when it is fetched
# from the mower.
AI_OBSTACLE_PHOTO_KIND = "ai_obs"
# Where the photos are kept once fetched, within the configuration directory,
# a folder per mower. Not below www: what lies there is served to anyone who
# asks.
AI_OBSTACLE_PHOTO_DIR = ("dreame_mower", "obstacle_photos")
# The recognised obstacles seen while mowing are kept there too, so a task's
# details still show one the mower dropped before the task ended; the latest
# this many are kept.
AI_OBSTACLES_SEEN_FILE = "seen.json"
AI_OBSTACLES_SEEN_LIMIT = 1000
# How often a photo is asked for before giving up: the mower sends it over its
# own connection, which can take longer than the cloud waits for one try.
AI_OBSTACLE_PHOTO_TRIES = 5
# How long one try waits for the cloud's answer, in seconds; the cloud itself
# gives up on the mower sooner.
AI_OBSTACLE_PHOTO_TIMEOUT = 20

# The obstacles the mower ran into on one map, by map index, as outlines in the
# map document's units; and the ones its camera recognised, in map units.
OBSTACLES_KEY = "OBS"
AI_OBSTACLES_KEY = "AIOBS"

# Schedule slots every map is known to hold. The mower reports the slots it
# keeps, so this only stands in while they have not been read yet.
SCHEDULE_SLOT_COUNT = 2

# Bytes the mower returns per chunk of the plan document.
SCHEDULE_CHUNK_SIZE = 100

# Status the mower reports on a write it accepted, alongside the one it reports
# for a write that quoted a version it no longer holds.
SCHEDULE_STATUS_SUCCESS = 0
SCHEDULE_STATUS_VERSION_ERROR = 1

# Layout of one plan inside the document: the slot it occupies, whether it is
# enabled, the name it was given, and the base64 encoded tasks. A plan without
# tasks is reported without that last field.
SCHEDULE_PLAN_SLOT_INDEX = 0
SCHEDULE_PLAN_ENABLED_INDEX = 1
SCHEDULE_PLAN_NAME_INDEX = 2
SCHEDULE_PLAN_TASKS_INDEX = 3

# Task layout inside the decoded tasks blob. Every task is framed by a marker
# byte and its own length, so the tasks can be walked without knowing how many
# there are:
#
#   0xaa | length | week day + type | start time and element count | elements | 0xed
#
# The start time is minutes since midnight spread over three nibbles, and the
# element count over the remaining three. The elements are the zones a zone task
# covers, or the (zone, side) pairs an edge task covers, and the length counts the
# whole frame, so a task without elements is the shortest one there can be.
SCHEDULE_TASK_START_MARKER = 0xAA
SCHEDULE_TASK_MINIMUM_LENGTH = 7

# MOVA mowers keep their schedules as tables instead of a single document, and
# refuse the document reads above. Every schedule slot of every map is a table
# of its own, numbered across the maps: map index * SCHEDULE_SLOT_COUNT + slot.
# A table read reports each table's state, its name and the tasks it holds as
# (task id, version) pairs, and every task is then read on its own. A task's
# version moves whenever it is edited, so an unchanged one need not be read
# again. A table is switched on or off on its own, by its number.
SCHEDULE_TABLE_INFO_KEY = "SCHDI"
SCHEDULE_TABLE_TASK_KEY = "SCHDC"
SCHEDULE_TABLE_ENABLE_KEY = "SCHDS"

# A mower that does not keep tables answers the table read with this value and
# no status, where a table it keeps comes with a zero status.
SCHEDULE_TABLE_UNSUPPORTED_REPLY = 7

# Layout of one table as the table read reports it.
SCHEDULE_TABLE_ID_INDEX = 0
SCHEDULE_TABLE_ENABLED_INDEX = 1
SCHEDULE_TABLE_NAME_INDEX = 3
SCHEDULE_TABLE_TASKS_INDEX = 4

# Layout of one task of a table: its id, whether it is enabled, its type, its
# start time in minutes since midnight, the week days it runs on, and the zones
# or (zone, side) edge pairs it covers.
SCHEDULE_TABLE_TASK_ENABLED_INDEX = 1
SCHEDULE_TABLE_TASK_TYPE_INDEX = 2
SCHEDULE_TABLE_TASK_START_INDEX = 3
SCHEDULE_TABLE_TASK_DAYS_INDEX = 4
SCHEDULE_TABLE_TASK_REGIONS_INDEX = 5

# Task types from this offset on are the cyclic variants of the ones below it.
SCHEDULE_TABLE_CYCLIC_TYPE_OFFSET = 8


class ScheduleTaskType(IntEnum):
    """What a scheduled task tells the mower to do."""
    ALL_AREA = 0
    ZONE = 1
    EDGE = 2
    PATROL = 3


SCHEDULE_TASK_TYPE_MAPPING: dict[int, str] = {
    ScheduleTaskType.ALL_AREA: "all_area",
    ScheduleTaskType.ZONE: "zone",
    ScheduleTaskType.EDGE: "edge",
    ScheduleTaskType.PATROL: "patrol",
}

# Week days as the mower numbers them, starting at Sunday.
SCHEDULE_WEEK_DAYS = (
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
)


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

class FirmwareInstallState(IntEnum):
    """Over-the-air update states reported on FIRMWARE_INSTALL_STATE_PROPERTY (1:2)."""
    UNDEFINED = 0
    IDLE = 1
    UPGRADING = 2
    UPGRADE_SUCCESS = 3
    UPGRADE_FAILED = 4
    CANNOT_UPGRADE = 5


FIRMWARE_INSTALL_STATE_MAPPING: dict[int, str] = {
    FirmwareInstallState.UNDEFINED: "undefined",
    FirmwareInstallState.IDLE: "idle",
    FirmwareInstallState.UPGRADING: "upgrading",
    FirmwareInstallState.UPGRADE_SUCCESS: "upgrade_success",
    FirmwareInstallState.UPGRADE_FAILED: "upgrade_failed",
    FirmwareInstallState.CANNOT_UPGRADE: "cannot_upgrade",
}

# A firmware update is only started from a mower that is at rest: waiting in
# standby or sitting on the station. It is refused below this battery level, as
# the mower has to stay powered through the download and the install.
FIRMWARE_UPDATE_ALLOWED_STATUSES: frozenset[int] = frozenset({
    DeviceStatus.STANDBY,
    DeviceStatus.CHARGING,
    DeviceStatus.CHARGING_COMPLETE,
})
FIRMWARE_UPDATE_MIN_BATTERY_PERCENT = 20

# Individual property names
PROPERTY_FIRMWARE = "firmware"

# Derived state names reported through the device property callbacks
CURRENT_MAP_ID_PROPERTY_NAME = "current_map_id"
MAP_SWITCH_ANNOUNCED_PROPERTY_NAME = "map_switch_announced"
CUTTING_HEIGHT_PROPERTY_NAME = "cutting_height"
ZONE_CUTTING_HEIGHTS_PROPERTY_NAME = "zone_cutting_heights"
MOWING_PREFERENCE_MODE_PROPERTY_NAME = "mowing_preference_mode"
EDGE_MOWING_SETTINGS_PROPERTY_NAME = "edge_mowing_settings"
ZONE_EDGE_MOWING_SETTINGS_PROPERTY_NAME = "zone_edge_mowing_settings"
MOWING_DIRECTION_PROPERTY_NAME = "mowing_direction"
ZONE_MOWING_DIRECTIONS_PROPERTY_NAME = "zone_mowing_directions"
SCHEDULES_PROPERTY_NAME = "schedules"

# Keys the edge mowing settings of one mowing preference record are reported
# under. Safe edge mowing is missing from the record of firmware that predates
# it, and is then absent from the settings rather than reported as off.
EDGE_MOWING_AUTO_KEY = "edge_mowing_auto"
EDGE_BLADE_OFFSET_KEY = "edge_blade_offset"
EDGE_MOWING_SAFE_KEY = "edge_mowing_safe"

# Keys the mowing direction of one mowing preference record is reported under.
MOWING_DIRECTION_ANGLE_KEY = "angle"
MOWING_DIRECTION_MODE_KEY = "mode"

# Keys every setting of one mowing preference record is reported and changed
# under, the edge mowing keys above among them. A setting the record is too
# short to carry is left out.
EFFICIENCY_KEY = "efficiency"
CUTTING_HEIGHT_KEY = "cutting_height"
DIRECTION_ANGLE_KEY = "mowing_direction"
DIRECTION_MODE_KEY = "mowing_direction_mode"
EDGE_OBSTACLE_AVOIDANCE_KEY = "edge_obstacle_avoidance"
LIDAR_OBSTACLE_KEY = "lidar_obstacle_recognition"
OBSTACLE_HEIGHT_KEY = "obstacle_height"
OBSTACLE_DISTANCE_KEY = "obstacle_distance"
AI_OBSTACLE_KEY = "ai_obstacle_recognition"
TURNING_METHOD_KEY = "turning_method"
