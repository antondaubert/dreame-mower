from __future__ import annotations
import base64

import math
import json
import time
from typing import Any, Dict, Final, List, Optional, OrderedDict
from enum import IntEnum, Enum
from dataclasses import dataclass, field
from datetime import datetime


SEGMENT_TYPE_CODE_TO_NAME: Final = {
    0: "Zone",
    1: "Living Zone",
    2: "Primary Bedzone",
    3: "Study",
    4: "Kitchen",
    5: "Dining Hall",
    6: "Bathzone",
    7: "Balcony",
    8: "Corridor",
    9: "Utility Zone",
    10: "Closet",
    11: "Meeting Zone",
    12: "Office",
    13: "Fitness Area",
    14: "Recreation Area",
    15: "Secondary Bedzone",
}

SEGMENT_TYPE_CODE_TO_HA_ICON: Final = {
    0: "mdi:home-outline",
    1: "mdi:sofa-outline",
    2: "mdi:bed-king-outline",
    3: "mdi:bookshelf",
    4: "mdi:chef-hat",
    5: "mdi:zone-service-outline",
    6: "mdi:toilet",
    7: "mdi:flower-outline",
    8: "mdi:foot-print",
    9: "mdi:archive-outline",
    10: "mdi:hanger",
    11: "mdi:presentation",
    12: "mdi:monitor-shimmer",
    13: "mdi:dumbbell",
    14: "mdi:gamepad-variant-outline",
    15: "mdi:bed-single-outline",
}

FURNITURE_TYPE_TO_DIMENSIONS: Final = {
    1: [1500, 2000],
    2: [1800, 2000],
    3: [800, 700],
    4: [1260, 800],
    5: [2340, 750],
    6: [1500, 800],
    7: [500, 400],
    8: [800, 400],
    9: [450, 690],
    10: [735, 990],
    11: [566, 865],
    12: [210, 378],
    13: [628, 936],
}

FURNITURE_V2_TYPE_TO_DIMENSIONS: Final = {
    1: [1000, 2000],
    2: [1500, 2000],
    3: [800, 700],
    4: [1400, 600],
    5: [2300, 700],
    6: [1200, 800],
    7: [500, 400],
    8: [800, 800],
    9: [400, 600],
    10: [300, 500],
    11: [500, 400],
    12: [400, 200],
    13: [400, 600],
    14: [600, 600],
    15: [600, 600],
    16: [300, 500],
    17: [400, 400],
    18: [1600, 300],
    19: [800, 300],
    20: [800, 400],
    21: [2000, 600],
    22: [300, 300],
    23: [1000, 400],
    24: [2800, 1700],
    25: [1000, 1000],
}

piid: Final = "piid"
siid: Final = "siid"
aiid: Final = "aiid"

ATTR_A: Final = "a"
ATTR_X: Final = "x"
ATTR_X0: Final = "x0"
ATTR_X1: Final = "x1"
ATTR_X2: Final = "x2"
ATTR_X3: Final = "x3"
ATTR_Y: Final = "y"
ATTR_Y0: Final = "y0"
ATTR_Y1: Final = "y1"
ATTR_Y2: Final = "y2"
ATTR_Y3: Final = "y3"
ATTR_CHARGER: Final = "charger_position"
ATTR_IS_EMPTY: Final = "is_empty"
ATTR_NO_GO_AREAS: Final = "no_go_areas"
ATTR_PREDEFINED_POINTS: Final = "predefined_points"
ATTR_VIRTUAL_WALLS: Final = "virtual_walls"
ATTR_PATHWAYS: Final = "pathways"
ATTR_ZONES: Final = "zones"
ATTR_ROBOT_POSITION: Final = "mower_position"
ATTR_MAP_ID: Final = "map_id"
ATTR_MAP_NAME: Final = "map_name"
ATTR_ROTATION: Final = "rotation"
ATTR_TIMESTAMP: Final = "timestamp"
ATTR_UPDATED: Final = "updated_at"
ATTR_ACTIVE_AREAS: Final = "active_areas"
ATTR_ACTIVE_POINTS: Final = "active_points"
ATTR_ACTIVE_CRUISE_POINTS: Final = "active_cruise_points"
ATTR_ACTIVE_SEGMENTS: Final = "active_segments"
ATTR_FRAME_ID: Final = "frame_id"
ATTR_MAP_INDEX: Final = "map_index"
ATTR_ZONE_ID: Final = "zone_id"
ATTR_ZONE_ICON: Final = "zone_icon"
ATTR_UNIQUE_ID: Final = "unique_id"
ATTR_FLOOR_MATERIAL: Final = "floor_material"
ATTR_FLOOR_MATERIAL_DIRECTION: Final = "floor_material_direction"
ATTR_VISIBILITY: Final = "visibility"
ATTR_NAME: Final = "name"
ATTR_OUTLINE: Final = "outline"
ATTR_CENTER: Final = "center"
ATTR_ORDER: Final = "order"
ATTR_CLEANING_TIMES: Final = "cleaning_times"
ATTR_CLEANING_MODE: Final = "cleaning_mode"
ATTR_CLEANING_ROUTE: Final = "cleaning_route"
ATTR_TYPE: Final = "type"
ATTR_INDEX: Final = "index"
ATTR_ICON: Final = "icon"
ATTR_COLOR_INDEX: Final = "color_index"
ATTR_OBSTACLES: Final = "obstacles"
ATTR_POSSIBILTY: Final = "possibility"
ATTR_PICTURE_STATUS: Final = "picture_status"
ATTR_IGNORE_STATUS: Final = "ignore_status"
ATTR_ZONE: Final = "zone"
ATTR_ROUTER_POSITION: Final = "router_position"
ATTR_FURNITURES: Final = "furnitures"
ATTR_STARTUP_METHOD: Final = "startup_method"
ATTR_RECOVERY_MAP_LIST: Final = "recovery_map_list"
ATTR_WIDTH: Final = "width"
ATTR_HEIGHT: Final = "height"
ATTR_SIZE_TYPE: Final = "size_type"
ATTR_ANGLE: Final = "angle"
ATTR_SCALE: Final = "scale"
ATTR_COMPLETED: Final = "completed"
ATTR_FIRMWARE_VERSION: Final = "firmware_version"
ATTR_AP: Final = "ap"
ATTR_COLOR_SCHEME: Final = "color_scheme"


class DreameMowerChargingStatus(IntEnum):
    """Dreame Mower charging status"""

    UNKNOWN = -1
    CHARGING = 1
    NOT_CHARGING = 2
    CHARGING_COMPLETED = 3
    RETURN_TO_CHARGE = 5


class DreameMowerErrorCode(IntEnum):
    """Dreame Mower error code"""

    UNKNOWN = -1
    NO_ERROR = 0
    DROP = 1
    CLIFF = 2
    BUMPER = 3
    GESTURE = 4
    BUMPER_REPEAT = 5
    DROP_REPEAT = 6
    OPTICAL_FLOW = 7
    BRUSH = 12
    SIDE_BRUSH = 13
    FAN = 14
    LEFT_WHEEL_MOTOR = 15
    RIGHT_WHEEL_MOTOR = 16
    TURN_SUFFOCATE = 17
    FORWARD_SUFFOCATE = 18
    CHARGER_GET = 19
    BATTERY_LOW = 20
    CHARGE_FAULT = 21
    BATTERY_PERCENTAGE = 22
    HEART = 23
    CAMERA_OCCLUSION = 24
    MOVE = 25
    FLOW_SHIELDING = 26
    INFRARED_SHIELDING = 27
    CHARGE_NO_ELECTRIC = 28
    BATTERY_FAULT = 29
    FAN_SPEED_ERROR = 30
    LEFTWHELL_SPEED = 31
    RIGHTWHELL_SPEED = 32
    BMI055_ACCE = 33
    BMI055_GYRO = 34
    XV7001 = 35
    LEFT_MAGNET = 36
    RIGHT_MAGNET = 37
    FLOW_ERROR = 38
    INFRARED_FAULT = 39
    CAMERA_FAULT = 40
    STRONG_MAGNET = 41
    RTC = 43
    AUTO_KEY_TRIG = 44
    P3V3 = 45
    CAMERA_IDLE = 46
    BLOCKED = 47
    LDS_ERROR = 48
    LDS_BUMPER = 49
    FILTER_BLOCKED = 51
    EDGE = 54
    LASER = 56
    EDGE_2 = 57
    ULTRASONIC = 58
    NO_GO_ZONE = 59
    ROUTE = 61
    ROUTE_2 = 62
    BLOCKED_2 = 63
    BLOCKED_3 = 64
    RESTRICTED = 65
    RESTRICTED_2 = 66
    RESTRICTED_3 = 67
    LOW_BATTERY_TURN_OFF = 75
    ROBOT_IN_HIDDEN_ZONE = 78
    STATION_DISCONNECTED = 117
    UNKNOWN_WARNING_2 = 122
    SELF_TEST_FAILED = 123
    RETURN_TO_CHARGE_FAILED = 1000


class DreameMowerState(IntEnum):
    """Dreame Mower state"""

    UNKNOWN = -1
    MOWING = 1
    IDLE = 2
    PAUSED = 3
    ERROR = 4
    RETURNING = 5
    CHARGING = 6
    BUILDING = 11
    CHARGING_COMPLETED = 13
    UPGRADING = 14
    CLEAN_SUMMON = 15
    STATION_RESET = 16
    REMOTE_CONTROL = 23
    SMART_CHARGING = 24
    SECOND_CLEANING = 25
    HUMAN_FOLLOWING = 26
    SPOT_CLEANING = 27
    WAITING_FOR_TASK = 29
    STATION_CLEANING = 30
    SHORTCUT = 97
    MONITORING = 98
    MONITORING_PAUSED = 99


class DreameMowerStateOld(IntEnum):
    """Dreame Mower old state"""

    UNKNOWN = -1
    MOWING = 1
    IDLE = 2
    PAUSED = 3
    ERROR = 4
    RETURNING = 5
    CHARGING = 6
    BUILDING = 11
    CHARGING_COMPLETED = 13
    UPGRADING = 14
    CLEAN_SUMMON = 15
    STATION_RESET = 16
    REMOTE_CONTROL = 19
    MONITORING = 21
    MONITORING_PAUSED = 21
    SMART_CHARGING = 26


class DreameMowerCleaningMode(IntEnum):
    """Dreame Mower cleaning mode"""

    UNKNOWN = -1
    MOWING = 0


class DreameMowerRelocationStatus(IntEnum):
    """Dreame Mower relocation status"""

    UNKNOWN = -1
    LOCATED = 0
    LOCATING = 1
    FAILED = 10
    SUCCESS = 11


class DreameMowerTaskStatus(IntEnum):
    """Dreame Mower task status"""

    UNKNOWN = -1
    COMPLETED = 0
    AUTO_CLEANING = 1
    ZONE_CLEANING = 2
    SEGMENT_CLEANING = 3
    SPOT_CLEANING = 4
    FAST_MAPPING = 5
    AUTO_CLEANING_PAUSED = 6
    ZONE_CLEANING_PAUSED = 7
    SEGMENT_CLEANING_PAUSED = 8
    SPOT_CLEANING_PAUSED = 9
    MAP_CLEANING_PAUSED = 10
    DOCKING_PAUSED = 11
    AUTO_DOCKING_PAUSED = 16
    SEGMENT_DOCKING_PAUSED = 17
    ZONE_DOCKING_PAUSED = 18
    CRUISING_PATH = 20
    CRUISING_PATH_PAUSED = 21
    CRUISING_POINT = 22
    CRUISING_POINT_PAUSED = 23
    SUMMON_CLEAN_PAUSED = 24


class DreameMowerStatus(IntEnum):
    """Dreame Mower status"""

    UNKNOWN = -1
    IDLE = 0
    PAUSED = 1
    CLEANING = 2
    BACK_HOME = 3
    PART_CLEANING = 4
    FOLLOW_WALL = 5
    CHARGING = 6
    OTA = 7
    FCT = 8
    WIFI_SET = 9
    POWER_OFF = 10
    FACTORY = 11
    ERROR = 12
    REMOTE_CONTROL = 13
    SLEEPING = 14
    SELF_REPAIR = 15
    FACTORY_FUNCION_TEST = 16
    STANDBY = 17
    SEGMENT_CLEANING = 18
    ZONE_CLEANING = 19
    SPOT_CLEANING = 20
    FAST_MAPPING = 21
    CRUISING_PATH = 22
    CRUISING_POINT = 23
    SUMMON_CLEAN = 24
    SHORTCUT = 25
    PERSON_FOLLOW = 26


class DreameMowerDustCollection(IntEnum):
    """Dreame Mower dust collection availability"""

    UNKNOWN = -1
    NOT_AVAILABLE = 0
    AVAILABLE = 1


class DreameMowerAutoEmptyStatus(IntEnum):
    """Dreame Mower dust collection status"""

    UNKNOWN = -1
    IDLE = 0
    ACTIVE = 1
    NOT_PERFORMED = 2


class DreameMowerSelfCleanArea(IntEnum):
    """Dreame Mower self clean area"""

    UNKNOWN = -1
    SINGLE_ZONE = 0
    FIVE_SQUARE_METERS = 5
    TEN_SQUARE_METERS = 10
    FIFTEEN_SQUARE_METERS = 15


class DreameMowerCleaningRoute(IntEnum):
    """Dreame Mower Cleaning route"""

    UNKNOWN = -1
    NOT_SET = 0
    STANDARD = 1
    INTENSIVE = 2
    DEEP = 3
    QUICK = 4


class DreameMowerWiderCornerCoverage(IntEnum):
    """Dreame Mower wider corner coverage"""

    UNKNOWN = -1
    OFF = 0
    HIGH_FREQUENCY = 1
    LOW_FREQUENCY = 7


class DreameMowerCleanGenius(IntEnum):
    """Dreame Mower CleanGenius mode"""

    UNKNOWN = -1
    OFF = 0
    ROUTINE_CLEANING = 1
    DEEP_CLEANING = 2


class DreameMowerSecondCleaning(IntEnum):
    """Dreame Mower Second Cleaning mode"""

    UNKNOWN = -1
    OFF = 0
    IN_DEEP_MODE = 1
    IN_ALL_MODES = 2


class DreameMowerFloorMaterial(IntEnum):
    """Dreame Mower floor material"""

    UNKNOWN = -1
    NONE = 0
    WOOD = 1
    TILE = 2


class DreameMowerFloorMaterialDirection(IntEnum):
    """Dreame Mower floor direction"""

    UNKNOWN = -1
    HORIZONTAL = 0
    VERTICAL = 90


class DreameMowerSegmentVisibility(IntEnum):
    """Dreame Mower segment visibility"""

    HIDDEN = 0
    VISIBLE = 1


class DreameMowerVoiceAssistantLanguage(str, Enum):
    """Dreame Mower assistant language"""

    DEFAULT = ""
    ENGLISH = "EN"
    GERMAN = "DE"
    CHINESE = "ZH"


class DreameMowerStreamStatus(IntEnum):
    """Dreame Mower stream status"""

    UNKNOWN = -1
    IDLE = 0
    VIDEO = 1
    AUDIO = 2
    RECORDING = 3


class DreameMowerTaskType(IntEnum):
    """Dreame Mower task type status"""

    UNKNOWN = -1
    IDLE = 0
    STANDARD = 1
    STANDARD_PAUSED = 2
    CUSTOM = 3
    CUSTOM_PAUSED = 4
    SHORTCUT = 5
    SHORTCUT_PAUSED = 6
    SCHEDULED = 7
    SCHEDULED_PAUSED = 8
    SMART = 9
    SMART_PAUSED = 10
    PARTIAL = 11
    PARTIAL_PAUSED = 12
    SUMMON = 13
    SUMMON_PAUSED = 14


class DreameMapRecoveryStatus(IntEnum):
    """Dreame Mower map recovery status"""

    UNKNOWN = -1
    IDLE = 0
    RUNNING = 2
    SUCCESS = 3
    FAIL = 4
    FAIL_2 = 5


class DreameMapBackupStatus(IntEnum):
    """Dreame Mower map backup status"""

    UNKNOWN = -1
    IDLE = 0
    RUNNING = 2
    SUCCESS = 3
    FAIL = 4


class DreameMowerProperty(IntEnum):
    """Dreame Mower properties"""

    STATE = 0
    ERROR = 1
    BATTERY_LEVEL = 2
    CHARGING_STATUS = 3
    OFF_PEAK_CHARGING = 4
    STATUS = 5
    CLEANING_TIME = 6
    CLEANED_AREA = 7
    TASK_STATUS = 11
    CLEANING_START_TIME = 12
    CLEAN_LOG_FILE_NAME = 13
    CLEANING_PROPERTIES = 14
    RESUME_CLEANING = 15
    CLEAN_LOG_STATUS = 17
    SERIAL_NUMBER = 18
    REMOTE_CONTROL = 19
    CLEANING_PAUSED = 21
    FAULTS = 22
    NATION_MATCHED = 23
    RELOCATION_STATUS = 24
    OBSTACLE_AVOIDANCE = 25
    AI_DETECTION = 26
    CLEANING_MODE = 27
    UPLOAD_MAP = 28
    CUSTOMIZED_CLEANING = 30
    CHILD_LOCK = 31
    CLEANING_CANCEL = 34
    Y_CLEAN = 35
    WARN_STATUS = 39
    CAPABILITY = 42
    MAP_INDEX = 46
    MAP_NAME = 47
    CRUISE_TYPE = 48
    SCHEDULED_CLEAN = 51
    SHORTCUTS = 52
    INTELLIGENT_RECOGNITION = 53
    AUTO_SWITCH_SETTINGS = 54
    NUMERIC_MESSAGE_PROMPT = 60
    MESSAGE_PROMPT = 61
    TASK_TYPE = 62
    PET_DETECTIVE = 63
    BACK_CLEAN_MODE = 66
    CLEANING_PROGRESS = 67
    DEVICE_CAPABILITY = 69
    DND = 70
    DND_START = 71
    DND_END = 72
    DND_TASK = 73
    MAP_DATA = 74
    FRAME_INFO = 75
    OBJECT_NAME = 76
    MAP_EXTEND_DATA = 77
    ROBOT_TIME = 78
    RESULT_CODE = 79
    MULTI_FLOOR_MAP = 80
    MAP_LIST = 81
    RECOVERY_MAP_LIST = 82
    MAP_RECOVERY = 83
    MAP_RECOVERY_STATUS = 84
    OLD_MAP_DATA = 85
    MAP_BACKUP_STATUS = 86
    WIFI_MAP = 87
    VOLUME = 88
    VOICE_PACKET_ID = 89
    VOICE_CHANGE_STATUS = 90
    VOICE_CHANGE = 91
    VOICE_ASSISTANT = 92
    VOICE_ASSISTANT_LANGUAGE = 93
    EMPTY_STAMP = 94
    CURRENT_CITY = 95
    VOICE_TEST = 96
    LISTEN_LANGUAGE = 97
    TIMEZONE = 98
    SCHEDULE = 99
    SCHEDULE_ID = 100
    SCHEDULE_CANCEL_REASON = 101
    CRUISE_SCHEDULE = 102
    BLADES_TIME_LEFT = 103
    BLADES_LEFT = 104
    SIDE_BRUSH_TIME_LEFT = 105
    SIDE_BRUSH_LEFT = 106
    FILTER_LEFT = 107
    FILTER_TIME_LEFT = 108
    FIRST_CLEANING_DATE = 109
    TOTAL_CLEANING_TIME = 110
    CLEANING_COUNT = 111
    TOTAL_CLEANED_AREA = 112
    TOTAL_RUNTIME = 113
    TOTAL_CRUISE_TIME = 114
    MAP_SAVING = 115
    SENSOR_DIRTY_LEFT = 120
    SENSOR_DIRTY_TIME_LEFT = 121
    TANK_FILTER_LEFT = 124
    TANK_FILTER_TIME_LEFT = 125
    SILVER_ION_TIME_LEFT = 126
    SILVER_ION_LEFT = 127
    LENSBRUSH_LEFT = 128
    LENSBRUSH_TIME_LEFT = 129
    SQUEEGEE_LEFT = 130
    SQUEEGEE_TIME_LEFT = 131
    LENSBRUSH_STATUS = 139
    AI_MAP_OPTIMIZATION_STATUS = 141
    SECOND_CLEANING_STATUS = 142
    ADD_CLEANING_AREA_STATUS = 144
    ADD_CLEANING_AREA_RESULT = 145
    CLEAN_EFFICIENCY = 150
    FACTORY_TEST_STATUS = 151
    FACTORY_TEST_RESULT = 152
    SELF_TEST_STATUS = 153
    LSD_TEST_STATUS = 154
    DEBUG_SWITCH = 155
    SERIAL = 156
    CALIBRATION_STATUS = 157
    VERSION = 158
    PERFORMANCE_SWITCH = 159
    AI_TEST_STATUS = 160
    PUBLIC_KEY = 161
    AUTO_PAIR = 162
    MCU_VERSION = 163
    PLATFORM_NETWORK = 165
    STREAM_STATUS = 166
    STREAM_AUDIO = 167
    STREAM_RECORD = 168
    TAKE_PHOTO = 169
    STREAM_KEEP_ALIVE = 170
    STREAM_FAULT = 171
    CAMERA_LIGHT_BRIGHTNESS = 172
    CAMERA_LIGHT = 173
    STEAM_HUMAN_FOLLOW = 174
    STREAM_CRUISE_POINT = 175
    STREAM_PROPERTY = 176
    STREAM_TASK = 177
    STREAM_UPLOAD = 178
    STREAM_CODE = 179
    STREAM_SET_CODE = 180
    STREAM_VERIFY_CODE = 181
    STREAM_RESET_CODE = 182
    STREAM_SPACE = 183


class DreameMowerAutoSwitchProperty(str, Enum):
    """Dreame Mower Auto Switch properties"""

    COLLISION_AVOIDANCE = "LessColl"
    FILL_LIGHT = "FillinLight"
    STAIN_AVOIDANCE = "StainIdentify"
    CLEANGENIUS = "SmartHost"
    WIDER_CORNER_COVERAGE = "MeticulousTwist"
    FLOOR_DIRECTION_CLEANING = "MaterialDirectionClean"
    PET_FOCUSED_CLEANING = "PetPartClean"
    AUTO_CHARGING = "SmartCharge"
    HUMAN_FOLLOW = "MonitorHumanFollow"
    CLEANING_ROUTE = "CleanRoute"
    GAP_CLEANING_EXTENSION = "LacuneMopScalable"
    STREAMING_VOICE_PROMPT = "MonitorPromptLevel"


class DreameMowerStrAIProperty(str, Enum):
    """Dreame Mower json AI obstacle detection properties"""

    AI_OBSTACLE_DETECTION = "obstacle_detect_switch"
    AI_OBSTACLE_IMAGE_UPLOAD = "obstacle_app_display_switch"
    AI_PET_DETECTION = "whether_have_pet"
    AI_HUMAN_DETECTION = "human_detect_switch"
    AI_FURNITURE_DETECTION = "furniture_detect_switch"
    AI_FLUID_DETECTION = "fluid_detect_switch"


class DreameMowerAIProperty(IntEnum):
    """Dreame Mower bitwise AI obstacle detection properties"""

    AI_FURNITURE_DETECTION = 1
    AI_OBSTACLE_DETECTION = 2
    AI_OBSTACLE_PICTURE = 4
    AI_FLUID_DETECTION = 8
    AI_PET_DETECTION = 16
    AI_OBSTACLE_IMAGE_UPLOAD = 32
    AI_IMAGE = 64
    AI_PET_AVOIDANCE = 128
    FUZZY_OBSTACLE_DETECTION = 256
    PET_PICTURE = 512
    PET_FOCUSED_DETECTION = 1024
    LARGE_PARTICLES_BOOST = 2048


class DreameMowerAction(IntEnum):
    """Dreame Mower actions"""

    START_MOWING = 1
    PAUSE = 2
    DOCK = 3
    START_CUSTOM = 4
    STOP = 5
    CLEAR_WARNING = 6
    GET_PHOTO_INFO = 8
    SHORTCUTS = 9
    REQUEST_MAP = 10
    UPDATE_MAP_DATA = 11
    BACKUP_MAP = 12
    WIFI_MAP = 13
    LOCATE = 14
    TEST_SOUND = 15
    DELETE_SCHEDULE = 16
    DELETE_CRUISE_SCHEDULE = 17
    RESET_BLADES = 18
    RESET_SIDE_BRUSH = 19
    RESET_FILTER = 20
    RESET_SENSOR = 21
    RESET_TANK_FILTER = 23
    RESET_SILVER_ION = 25
    RESET_LENSBRUSH = 26
    RESET_SQUEEGEE = 27
    STREAM_VIDEO = 30
    STREAM_AUDIO = 31
    STREAM_PROPERTY = 32
    STREAM_CODE = 33
    PULL_STATUS = 34


# Dreame Mower property mapping
DreameMowerPropertyMapping = {
    DreameMowerProperty.STATE: {siid: 2, piid: 1},
    DreameMowerProperty.ERROR: {siid: 2, piid: 2},
    DreameMowerProperty.BATTERY_LEVEL: {siid: 3, piid: 1},
    DreameMowerProperty.CHARGING_STATUS: {siid: 3, piid: 2},
    DreameMowerProperty.OFF_PEAK_CHARGING: {siid: 3, piid: 3},
    DreameMowerProperty.STATUS: {siid: 4, piid: 1},
    DreameMowerProperty.CLEANING_TIME: {siid: 4, piid: 2},
    DreameMowerProperty.CLEANED_AREA: {siid: 4, piid: 3},
    DreameMowerProperty.TASK_STATUS: {siid: 4, piid: 7},
    DreameMowerProperty.CLEANING_START_TIME: {siid: 4, piid: 8},
    DreameMowerProperty.CLEAN_LOG_FILE_NAME: {siid: 4, piid: 9},
    DreameMowerProperty.CLEANING_PROPERTIES: {siid: 4, piid: 10},
    DreameMowerProperty.RESUME_CLEANING: {siid: 4, piid: 11},
    DreameMowerProperty.CLEAN_LOG_STATUS: {siid: 4, piid: 13},
    DreameMowerProperty.SERIAL_NUMBER: {siid: 4, piid: 14},
    DreameMowerProperty.REMOTE_CONTROL: {siid: 4, piid: 15},
    DreameMowerProperty.CLEANING_PAUSED: {siid: 4, piid: 17},
    DreameMowerProperty.FAULTS: {siid: 4, piid: 18},
    DreameMowerProperty.NATION_MATCHED: {siid: 4, piid: 19},
    DreameMowerProperty.RELOCATION_STATUS: {siid: 4, piid: 20},
    DreameMowerProperty.OBSTACLE_AVOIDANCE: {siid: 4, piid: 21},
    DreameMowerProperty.AI_DETECTION: {siid: 4, piid: 22},
    DreameMowerProperty.CLEANING_MODE: {siid: 4, piid: 23},
    DreameMowerProperty.UPLOAD_MAP: {siid: 4, piid: 24},
    DreameMowerProperty.CUSTOMIZED_CLEANING: {siid: 4, piid: 26},
    DreameMowerProperty.CHILD_LOCK: {siid: 4, piid: 27},
    DreameMowerProperty.CLEANING_CANCEL: {siid: 4, piid: 30},
    DreameMowerProperty.Y_CLEAN: {siid: 4, piid: 31},
    DreameMowerProperty.WARN_STATUS: {siid: 4, piid: 35},
    DreameMowerProperty.CAPABILITY: {siid: 4, piid: 38},
    DreameMowerProperty.MAP_INDEX: {siid: 4, piid: 42},
    DreameMowerProperty.MAP_NAME: {siid: 4, piid: 43},
    DreameMowerProperty.CRUISE_TYPE: {siid: 4, piid: 44},
    DreameMowerProperty.SCHEDULED_CLEAN: {siid: 4, piid: 47},
    DreameMowerProperty.SHORTCUTS: {siid: 4, piid: 48},
    DreameMowerProperty.INTELLIGENT_RECOGNITION: {siid: 4, piid: 49},
    DreameMowerProperty.NUMERIC_MESSAGE_PROMPT: {siid: 4, piid: 56},
    DreameMowerProperty.MESSAGE_PROMPT: {siid: 4, piid: 57},
    DreameMowerProperty.TASK_TYPE: {siid: 4, piid: 58},
    DreameMowerProperty.PET_DETECTIVE: {siid: 4, piid: 59},
    DreameMowerProperty.BACK_CLEAN_MODE: {siid: 4, piid: 62},
    DreameMowerProperty.CLEANING_PROGRESS: {siid: 4, piid: 63},
    DreameMowerProperty.DEVICE_CAPABILITY: {siid: 4, piid: 83},
    # DreameMowerProperty.COMBINED_DATA: {siid: 4, piid: 99},
    DreameMowerProperty.DND: {siid: 5, piid: 1},
    DreameMowerProperty.DND_START: {siid: 5, piid: 2},
    DreameMowerProperty.DND_END: {siid: 5, piid: 3},
    DreameMowerProperty.DND_TASK: {siid: 5, piid: 4},
    DreameMowerProperty.MAP_DATA: {siid: 6, piid: 1},
    DreameMowerProperty.FRAME_INFO: {siid: 6, piid: 2},
    DreameMowerProperty.OBJECT_NAME: {siid: 6, piid: 3},
    DreameMowerProperty.MAP_EXTEND_DATA: {siid: 6, piid: 4},
    DreameMowerProperty.ROBOT_TIME: {siid: 6, piid: 5},
    DreameMowerProperty.RESULT_CODE: {siid: 6, piid: 6},
    DreameMowerProperty.MULTI_FLOOR_MAP: {siid: 6, piid: 7},
    DreameMowerProperty.MAP_LIST: {siid: 6, piid: 8},
    DreameMowerProperty.RECOVERY_MAP_LIST: {siid: 6, piid: 9},
    DreameMowerProperty.MAP_RECOVERY: {siid: 6, piid: 10},
    DreameMowerProperty.MAP_RECOVERY_STATUS: {siid: 6, piid: 11},
    DreameMowerProperty.OLD_MAP_DATA: {siid: 6, piid: 13},
    DreameMowerProperty.MAP_BACKUP_STATUS: {siid: 6, piid: 14},
    DreameMowerProperty.WIFI_MAP: {siid: 6, piid: 15},
    DreameMowerProperty.VOLUME: {siid: 7, piid: 1},
    DreameMowerProperty.VOICE_PACKET_ID: {siid: 7, piid: 2},
    DreameMowerProperty.VOICE_CHANGE_STATUS: {siid: 7, piid: 3},
    DreameMowerProperty.VOICE_CHANGE: {siid: 7, piid: 4},
    DreameMowerProperty.VOICE_ASSISTANT: {siid: 7, piid: 5},
    DreameMowerProperty.EMPTY_STAMP: {siid: 7, piid: 6},
    DreameMowerProperty.CURRENT_CITY: {siid: 7, piid: 7},
    DreameMowerProperty.VOICE_TEST: {siid: 7, piid: 9},
    DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE: {siid: 7, piid: 10},
    DreameMowerProperty.LISTEN_LANGUAGE: {siid: 7, piid: 10},
    DreameMowerProperty.TIMEZONE: {siid: 8, piid: 1},
    DreameMowerProperty.SCHEDULE: {siid: 8, piid: 2},
    DreameMowerProperty.SCHEDULE_ID: {siid: 8, piid: 3},
    DreameMowerProperty.SCHEDULE_CANCEL_REASON: {siid: 8, piid: 4},
    DreameMowerProperty.CRUISE_SCHEDULE: {siid: 8, piid: 5},
    DreameMowerProperty.BLADES_TIME_LEFT: {siid: 9, piid: 1},
    DreameMowerProperty.BLADES_LEFT: {siid: 9, piid: 2},
    DreameMowerProperty.SIDE_BRUSH_TIME_LEFT: {siid: 10, piid: 1},
    DreameMowerProperty.SIDE_BRUSH_LEFT: {siid: 10, piid: 2},
    DreameMowerProperty.FILTER_LEFT: {siid: 11, piid: 1},
    DreameMowerProperty.FILTER_TIME_LEFT: {siid: 11, piid: 2},
    DreameMowerProperty.FIRST_CLEANING_DATE: {siid: 12, piid: 1},
    DreameMowerProperty.TOTAL_CLEANING_TIME: {siid: 12, piid: 2},
    DreameMowerProperty.CLEANING_COUNT: {siid: 12, piid: 3},
    DreameMowerProperty.TOTAL_CLEANED_AREA: {siid: 12, piid: 4},
    DreameMowerProperty.TOTAL_RUNTIME: {siid: 12, piid: 5},
    DreameMowerProperty.TOTAL_CRUISE_TIME: {siid: 12, piid: 6},
    DreameMowerProperty.MAP_SAVING: {siid: 13, piid: 1},
    DreameMowerProperty.SENSOR_DIRTY_LEFT: {siid: 16, piid: 1},
    DreameMowerProperty.SENSOR_DIRTY_TIME_LEFT: {siid: 16, piid: 2},
    DreameMowerProperty.TANK_FILTER_LEFT: {siid: 17, piid: 1},
    DreameMowerProperty.TANK_FILTER_TIME_LEFT: {siid: 17, piid: 2},
    DreameMowerProperty.SILVER_ION_TIME_LEFT: {siid: 19, piid: 1},
    DreameMowerProperty.SILVER_ION_LEFT: {siid: 19, piid: 2},
    DreameMowerProperty.LENSBRUSH_LEFT: {siid: 4, piid: 50},
    DreameMowerProperty.SQUEEGEE_LEFT: {siid: 24, piid: 1},
    DreameMowerProperty.SQUEEGEE_TIME_LEFT: {siid: 24, piid: 2},
    DreameMowerProperty.LENSBRUSH_STATUS: {siid: 27, piid: 4},
    DreameMowerProperty.AI_MAP_OPTIMIZATION_STATUS: {siid: 27, piid: 7},
    DreameMowerProperty.SECOND_CLEANING_STATUS: {siid: 27, piid: 8},
    DreameMowerProperty.ADD_CLEANING_AREA_STATUS: {siid: 27, piid: 10},
    DreameMowerProperty.ADD_CLEANING_AREA_RESULT: {siid: 27, piid: 11},
    DreameMowerProperty.CLEAN_EFFICIENCY: {siid: 28, piid: 9},
    DreameMowerProperty.FACTORY_TEST_STATUS: {siid: 99, piid: 1},
    DreameMowerProperty.FACTORY_TEST_RESULT: {siid: 99, piid: 3},
    DreameMowerProperty.SELF_TEST_STATUS: {siid: 99, piid: 8},
    DreameMowerProperty.LSD_TEST_STATUS: {siid: 99, piid: 9},
    DreameMowerProperty.DEBUG_SWITCH: {siid: 99, piid: 11},
    DreameMowerProperty.SERIAL: {siid: 99, piid: 14},
    DreameMowerProperty.CALIBRATION_STATUS: {siid: 99, piid: 15},
    DreameMowerProperty.VERSION: {siid: 99, piid: 17},
    DreameMowerProperty.PERFORMANCE_SWITCH: {siid: 99, piid: 24},
    DreameMowerProperty.AI_TEST_STATUS: {siid: 99, piid: 25},
    DreameMowerProperty.PUBLIC_KEY: {siid: 99, piid: 27},
    DreameMowerProperty.AUTO_PAIR: {siid: 99, piid: 28},
    DreameMowerProperty.MCU_VERSION: {siid: 99, piid: 31},
    DreameMowerProperty.PLATFORM_NETWORK: {siid: 99, piid: 95},
    DreameMowerProperty.STREAM_STATUS: {siid: 10001, piid: 1},
    DreameMowerProperty.STREAM_AUDIO: {siid: 10001, piid: 2},
    DreameMowerProperty.STREAM_RECORD: {siid: 10001, piid: 4},
    DreameMowerProperty.TAKE_PHOTO: {siid: 10001, piid: 5},
    DreameMowerProperty.STREAM_KEEP_ALIVE: {siid: 10001, piid: 6},
    DreameMowerProperty.STREAM_FAULT: {siid: 10001, piid: 7},
    DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS: {siid: 10001, piid: 9},
    DreameMowerProperty.CAMERA_LIGHT: {siid: 10001, piid: 10},
    DreameMowerProperty.STEAM_HUMAN_FOLLOW: {siid: 10001, piid: 110},
    DreameMowerProperty.STREAM_CRUISE_POINT: {siid: 10001, piid: 101},
    DreameMowerProperty.STREAM_PROPERTY: {siid: 10001, piid: 99},
    DreameMowerProperty.STREAM_TASK: {siid: 10001, piid: 103},
    DreameMowerProperty.STREAM_UPLOAD: {siid: 10001, piid: 1003},
    DreameMowerProperty.STREAM_CODE: {siid: 10001, piid: 1100},
    DreameMowerProperty.STREAM_SET_CODE: {siid: 10001, piid: 1101},
    DreameMowerProperty.STREAM_VERIFY_CODE: {siid: 10001, piid: 1102},
    DreameMowerProperty.STREAM_RESET_CODE: {siid: 10001, piid: 1103},
    DreameMowerProperty.STREAM_SPACE: {siid: 10001, piid: 2003},
}

# Dreame Mower action mapping
DreameMowerActionMapping = {
    DreameMowerAction.START_MOWING: {siid: 5, aiid: 1},
    DreameMowerAction.PAUSE: {siid: 5, aiid: 4},
    DreameMowerAction.DOCK: {siid: 5, aiid: 3},
    DreameMowerAction.STOP: {siid: 5, aiid: 2},
    DreameMowerAction.PULL_STATUS: {siid: 5, aiid: 10},
    DreameMowerAction.CLEAR_WARNING: {siid: 4, aiid: 3},
    DreameMowerAction.START_CUSTOM: {siid: 4, aiid: 1},
    DreameMowerAction.GET_PHOTO_INFO: {siid: 4, aiid: 6},
    DreameMowerAction.SHORTCUTS: {siid: 4, aiid: 8},
    DreameMowerAction.REQUEST_MAP: {siid: 6, aiid: 1},
    DreameMowerAction.UPDATE_MAP_DATA: {siid: 6, aiid: 2},
    DreameMowerAction.BACKUP_MAP: {siid: 6, aiid: 3},
    DreameMowerAction.WIFI_MAP: {siid: 6, aiid: 4},
    DreameMowerAction.LOCATE: {siid: 7, aiid: 1},
    DreameMowerAction.TEST_SOUND: {siid: 7, aiid: 2},
    DreameMowerAction.DELETE_SCHEDULE: {siid: 8, aiid: 1},
    DreameMowerAction.DELETE_CRUISE_SCHEDULE: {siid: 8, aiid: 2},
    DreameMowerAction.RESET_BLADES: {siid: 9, aiid: 1},
    DreameMowerAction.RESET_SIDE_BRUSH: {siid: 10, aiid: 1},
    DreameMowerAction.RESET_FILTER: {siid: 11, aiid: 1},
    DreameMowerAction.RESET_SENSOR: {siid: 16, aiid: 1},
    DreameMowerAction.RESET_TANK_FILTER: {siid: 17, aiid: 1},
    DreameMowerAction.RESET_SILVER_ION: {siid: 19, aiid: 1},
    DreameMowerAction.RESET_LENSBRUSH: {siid: 1, aiid: 3},
    DreameMowerAction.RESET_SQUEEGEE: {siid: 24, aiid: 1},
    DreameMowerAction.STREAM_VIDEO: {siid: 10001, aiid: 1},
    DreameMowerAction.STREAM_AUDIO: {siid: 10001, aiid: 2},
    DreameMowerAction.STREAM_PROPERTY: {siid: 10001, aiid: 3},
    DreameMowerAction.STREAM_CODE: {siid: 10001, aiid: 4},
}

PROPERTY_AVAILABILITY: Final = {
    DreameMowerProperty.CUSTOMIZED_CLEANING.name: lambda device: not device.status.started
    and (device.status.has_saved_map or device.status.current_map is None)
    and not device.status.cleangenius_cleaning,
    DreameMowerProperty.MULTI_FLOOR_MAP.name: lambda device: not device.status.has_temporary_map and not device.status.started,
    DreameMowerProperty.CLEANING_MODE.name: lambda device: (
        not device.status.started
    )
    and not device.status.fast_mapping
    and not device.status.scheduled_clean
    and not device.status.cruising
    and (not device.status.customized_cleaning or not device.capability.custom_cleaning_mode)
    and not device.status.cleangenius_cleaning
    and not device.status.returning
    and not device.status.shortcut_task,
    DreameMowerProperty.CLEANING_TIME.name: lambda device: not device.status.fast_mapping
    and not device.status.cruising,
    DreameMowerProperty.CLEANED_AREA.name: lambda device: not device.status.fast_mapping
    and not device.status.cruising,
    DreameMowerProperty.RELOCATION_STATUS.name: lambda device: not device.status.fast_mapping,
    DreameMowerProperty.INTELLIGENT_RECOGNITION.name: lambda device: device.status.multi_map,
    DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE.name: lambda device: bool(
        device.get_property(DreameMowerProperty.VOICE_ASSISTANT) == 1
    ),
    DreameMowerProperty.STREAM_STATUS.name: lambda device: bool(
        device.get_property(DreameMowerProperty.STREAM_STATUS) is not None
    ),
    DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS.name: lambda device: bool(
        device.status.camera_light_brightness
        and device.status.camera_light_brightness != 101
        and device.status.stream_session is not None
    ),
    DreameMowerProperty.TASK_TYPE.name: lambda device: device.status.task_type.value > 0,
    DreameMowerProperty.CLEANING_PROGRESS.name: lambda device: bool(
        device.status.started and not device.status.cruising
    ),
    DreameMowerAutoSwitchProperty.WIDER_CORNER_COVERAGE.name: lambda device: not device.status.started
    and not device.status.fast_mapping,
    DreameMowerAutoSwitchProperty.STAIN_AVOIDANCE.name: lambda device: device.status.ai_fluid_detection,
    DreameMowerAutoSwitchProperty.CLEANGENIUS.name: lambda device: not device.status.started
    and not device.status.fast_mapping
    and not device.status.cruising
    and not device.status.spot_cleaning
    and not device.status.zone_cleaning,
    DreameMowerAutoSwitchProperty.FLOOR_DIRECTION_CLEANING.name: lambda device: device.status.floor_direction_cleaning_available,
    DreameMowerStrAIProperty.AI_HUMAN_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameMowerAIProperty.AI_OBSTACLE_IMAGE_UPLOAD.name: lambda device: device.status.ai_obstacle_detection,
    DreameMowerAIProperty.AI_OBSTACLE_PICTURE.name: lambda device: device.status.ai_obstacle_detection,
    DreameMowerAIProperty.AI_PET_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameMowerAIProperty.AI_FURNITURE_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameMowerAIProperty.AI_FLUID_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameMowerAIProperty.FUZZY_OBSTACLE_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameMowerAIProperty.AI_PET_AVOIDANCE.name: lambda device: device.status.ai_obstacle_detection
    and device.status.ai_pet_detection,
    DreameMowerAIProperty.PET_PICTURE.name: lambda device: device.status.ai_obstacle_detection
    and device.status.ai_pet_detection,
    DreameMowerAIProperty.PET_FOCUSED_DETECTION.name: lambda device: device.status.ai_obstacle_detection
    and device.status.ai_pet_detection,
    DreameMowerAutoSwitchProperty.CLEANING_ROUTE.name: lambda device: not device.status.has_temporary_map
    and device.status.segments
    and device.status.cleaning_route.value > 0
    and not device.status.fast_mapping
    and not device.status.started
    and (not device.status.customized_cleaning or not device.capability.custom_cleaning_mode)
    and not device.status.cleangenius_cleaning,
    DreameMowerProperty.FIRST_CLEANING_DATE.name: lambda device: device.get_property(
        DreameMowerProperty.FIRST_CLEANING_DATE
    ),
    "map_rotation": lambda device: bool(
        device.status.selected_map is not None
        and device.status.selected_map.rotation is not None
        and not device.status.fast_mapping
        and device.status.has_saved_map
    ),
    "selected_map": lambda device: bool(
        device.status.multi_map
        and not device.status.fast_mapping
        and device.status.map_list
        and device.status.selected_map
        and device.status.selected_map.map_name
        and device.status.selected_map.map_id in device.status.map_list
    ),
    "current_zone": lambda device: device.status.current_zone is not None and not device.status.fast_mapping,
    "cleaning_history": lambda device: bool(device.status.last_cleaning_time is not None),
    "cruising_history": lambda device: bool(device.status.last_cruising_time is not None),
    "cleaning_sequence": lambda device: not device.status.started
    and device.status.has_saved_map
    and device.status.current_segments
    and not device.status.cleangenius_cleaning
    and next(iter(device.status.current_segments.values())).order is not None,
    "camera_light_brightness_auto": lambda device: device.status.camera_light_brightness
    and device.status.stream_session is not None,
    "dnd_start": lambda device: device.status.dnd,
    "dnd_end": lambda device: device.status.dnd,
    "off_peak_charging_start": lambda device: device.status.off_peak_charging,
    "off_peak_charging_end": lambda device: device.status.off_peak_charging,
}

ACTION_AVAILABILITY: Final = {
    DreameMowerAction.RESET_BLADES.name: lambda device: bool(device.status.blades_life < 100),
    DreameMowerAction.RESET_SIDE_BRUSH.name: lambda device: bool(device.status.side_brush_life < 100),
    DreameMowerAction.RESET_FILTER.name: lambda device: bool(device.status.filter_life < 100),
    DreameMowerAction.RESET_SENSOR.name: lambda device: bool(device.status.sensor_dirty_life < 100),
    DreameMowerAction.RESET_TANK_FILTER.name: lambda device: bool(device.status.tank_filter_life < 100),
    DreameMowerAction.RESET_SILVER_ION.name: lambda device: bool(device.status.silver_ion_life < 100),
    DreameMowerAction.RESET_LENSBRUSH.name: lambda device: bool(device.status.lensbrush_life < 100),
    DreameMowerAction.RESET_SQUEEGEE.name: lambda device: bool(device.status.squeegee_life < 100),
    DreameMowerAction.CLEAR_WARNING.name: lambda device: device.status.has_warning,
    DreameMowerAction.START_MOWING.name: lambda device: not (
        device.status.started
    )
    or device.status.paused
    or device.status.returning
    or device.status.returning_paused,
    DreameMowerAction.DOCK.name: lambda device: not device.status.docked and not device.status.returning,
    DreameMowerAction.PAUSE.name: lambda device: device.status.started
    and not (
        device.status.returning_paused
        or device.status.paused
    ),
    DreameMowerAction.STOP.name: lambda device: (
        device.status.started
        or device.status.returning
        or device.status.paused
    ),
    "start_fast_mapping": lambda device: device.status.mapping_available,
    "start_mapping": lambda device: device.status.mapping_available,
    "start_recleaning": lambda device: not device.status.started and device.status.second_cleaning_available,
}


def PIID(property: DreameMowerProperty, mapping=DreameMowerPropertyMapping) -> int | None:
    if property in mapping:
        return mapping[property][piid]


def DIID(property: DreameMowerProperty, mapping=DreameMowerPropertyMapping) -> str | None:
    if property in mapping:
        return f"{mapping[property][siid]}.{mapping[property][piid]}"


class RobotType(IntEnum):
    LIDAR = 0
    VSLAM = 1


class PathType(str, Enum):
    LINE = "L"
    SWEEP = "S"


class ObstacleType(IntEnum):
    UNKNOWN = 0
    BASE = 128
    SCALE = 129
    THREAD = 130
    WIRE = 131
    TOY = 132
    SHOES = 133
    SOCK = 134
    POO = 135
    TRASH_CAN = 136
    FABRIC = 137
    POWER_STRIP = 138
    STAIN = 139
    OBSTACLE = 142
    PET = 158
    CLEANING_TOOLS = 163
    NEGLECTED_ZONE = 200
    EASY_TO_STUCK_FURNITURE = 201


class ObstacleIgnoreStatus(IntEnum):
    UNKNOWN = -1
    NOT_IGNORED = 0
    MANUALLY_IGNORED = 1
    AUTOMATICALLY_IGNORED = 2


class ObstaclePictureStatus(IntEnum):
    UNKNOWN = -1
    DISABLED = 0
    UPLOADING = 1
    UPLOADED = 2
    UPLOAD_FAILED = 3


class SegmentNeglectReason(IntEnum):
    BLOCKED_BY_VIRTUAL_WALL = 2
    BLOCKED_BY_DOOR = 3
    BLOCKED_BY_TRESHOLD = 4
    BLOCKED_BY_OBSTACLE = 5
    BLOCKED_BY_HIDDEN_OBSTACLE = 8
    BLOCKED_BY_DYNAMIC_OBSTACLE = 9
    PASSAGE_TOO_LOW = 10
    STEP_TOO_LOW = 27


class TaskInterruptReason(IntEnum):
    UNKNOWN = -1
    TASK_COMPLETED = 0
    ROBOT_LIFTED = 11
    ROBOT_FALLEN = 12
    CLIFF_SENSOR_ERROR = 13
    BRUSH_ENTANGLED_BY_OBSTACLE = 21
    BRUSH_ENTANGLED_BY_OBJECT = 23
    LASER_DISTANCE_SENSOR_ERROR = 24
    ROBOT_IS_STUCK_ON_STEP = 25
    ROBOT_IS_STUCK_ON_OBSTACLE = 26
    BASE_STATION_POWERED_OFF = 27
    ABNORMAL_DOCKING = 101
    CANNOT_FIND_BASE_STATION = 102


class FurnitureType(IntEnum):
    SINGLE_BED = 1
    DOUBLE_BED = 2
    ARM_CHAIR = 3
    TWO_SEAT_SOFA = 4
    THREE_SEAT_SOFA = 5
    DINING_TABLE = 6
    NIGHTSTANT = 7
    COFFEE_TABLE = 8
    TOILET = 9
    LITTER_BOX = 10
    PET_BED = 11
    FOOD_BOWL = 12
    PET_TOILET = 13
    REFRIGERATOR = 14
    WASHING_MACHINE = 15
    ENCLOSED_LITTER_BOX = 16
    AIR_CONDITIONER = 17
    TV_CABINET = 18
    BOOKSHELF = 19
    SHOE_CABINET = 20
    WARDROBE = 21
    GREENERY = 22
    FLOOR_MIRROR = 23
    L_SHAPED_SOFA = 24
    ROUND_COFFEE_TABLE = 25


class CleansetType(IntEnum):
    NONE = 0
    DEFAULT = 1
    CLEANING_MODE = 2
    CLEANING_ROUTE = 4


class DeviceCapability(IntEnum):
    OBSTACLE_IMAGE_CROP = 5
    FLOOR_DIRECTION_CLEANING = 10
    LARGE_PARTICLES_BOOST = 11
    SEGMENT_VISIBILITY = 12
    PET_FURNITURE = 16
    CLEANING_ROUTE = 17
    SEGMENT_SLOW_CLEAN_ROUTE = 19
    TASK_TYPE = 21
    EXTENDED_FURNITURES = 23
    CLEANGENIUS = 25
    CLEANGENIUS_AUTO = 26
    FLUID_DETECTION = 27
    AUTO_RENAME_SEGMENT = 31
    DISABLE_SENSOR_CLEANING = 32
    FLOOR_MATERIAL = 33
    GEN5 = 34
    NEW_FURNITURES = 35
    SAVED_FURNITURES = 36
    OBSTACLES = 37
    NEW_STATE = 45
    CAMERA_STREAMING = 46
    LENSBRUSH = 47


class DreameMowerDeviceCapability:
    def __init__(self, device) -> None:
        self.list = None
        self.lidar_navigation = True
        self.multi_floor_map = True
        self.ai_detection = False
        self.customized_cleaning = False
        self.auto_switch_settings = False
        self.wifi_map = False
        self.backup_map = False
        self.dnd = False
        self.dnd_task = False
        self.shortcuts = False
        self.fill_light = False
        self.voice_assistant = False
        self.pet_detective = False
        self.off_peak_charging = False
        self.max_suction_power = False
        self.obstacle_image_crop = False
        self.map_object_offset = True
        self.robot_type = RobotType.LIDAR
        self.floor_material = False
        self.floor_direction_cleaning = False
        self.segment_visibility = False
        self.cleangenius = False
        self.cleangenius_auto = False
        self.large_particles_boost = False
        self.fluid_detection = False
        self.cleaning_route = False
        self.segment_slow_clean_route = True
        self.pet_furniture = False
        self.task_type = False
        self.disable_sensor_cleaning = False
        self.auto_rename_segment = False
        self.saved_furnitures = False
        self.extended_furnitures = False
        self.new_furnitures = False
        self.pet_furnitures = False
        self.obstacles = False
        self.auto_charging = False
        self.new_state = False
        self.camera_streaming = False
        self.gen5 = False
        self.lensbrush = False
        self._custom_cleaning_mode = False
        self._device = device

    def refresh(self, device_capabilities):
        self.lidar_navigation = bool(self._device.get_property(
            DreameMowerProperty.MAP_SAVING) is None)
        self.multi_floor_map = bool(
            self._device.get_property(
                DreameMowerProperty.MULTI_FLOOR_MAP) is not None and self.lidar_navigation
        )
        self.ai_detection = bool(self._device.get_property(
            DreameMowerProperty.AI_DETECTION) is not None)
        self.customized_cleaning = bool(
            self._device.get_property(
                DreameMowerProperty.CUSTOMIZED_CLEANING) is not None
        )
        self.auto_switch_settings = bool(
            self._device.get_property(
                DreameMowerProperty.AUTO_SWITCH_SETTINGS) is not None
        )
        self.wifi_map = bool(self._device.get_property(
            DreameMowerProperty.WIFI_MAP) is not None)
        self.backup_map = bool(self._device.get_property(
            DreameMowerProperty.MAP_BACKUP_STATUS) is not None)
        self.dnd_task = bool(self._device.get_property(
            DreameMowerProperty.DND_TASK) is not None)
        self.dnd = bool(self.dnd_task or self._device.get_property(
            DreameMowerProperty.DND) is not None)
        self.shortcuts = bool(self._device.get_property(
            DreameMowerProperty.SHORTCUTS) is not None)
        self.off_peak_charging = bool(self._device.get_property(
            DreameMowerProperty.OFF_PEAK_CHARGING) is not None)
        camera_light = self._device.get_property(
            DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS)
        self.voice_assistant = bool(self._device.get_property(
            DreameMowerProperty.VOICE_ASSISTANT) is not None)

        model = ""
        if self._device.info and self._device.info.model:
            model = self._device.info.model.replace("mower.", "").replace(
                "dreame.", "").replace("xiaomi.", "")
            device_capability = device_capabilities.get(model)
            while device_capability and isinstance(device_capability, str):
                device_capability = device_capabilities.get(device_capability)
            if device_capability:
                version = self._device.info.version if self._device.info.version else 1
                for v in device_capability:
                    capability = v[0]
                    if capability in DeviceCapability._value2member_map_:
                        capability = DeviceCapability(capability)
                        param = capability.name.lower()
                        if param and hasattr(self, param):
                            setattr(self, param, bool(version >= v[1]))

        # self.camera_streaming = bool(
        #    self.camera_streaming and (camera_light is not None or self._device.get_property(DreameMowerProperty.CRUISE_SCHEDULE) is not None)
        # )
        self.lensbrush = bool(self.lensbrush or self._device.get_property(
            DreameMowerProperty.LENSBRUSH_LEFT))
        self.fill_light = bool(
            self.camera_streaming
            and camera_light is not None
            and len(camera_light) < 5
            and str(camera_light).isnumeric()
        )
        self.pet_detective = bool(
            self.pet_detective and self._device.get_property(
                DreameMowerProperty.PET_DETECTIVE) is not None
        )
        self.task_type = bool(self.task_type and self._device.get_property(
            DreameMowerProperty.TASK_TYPE) is not None)
        if not self.cleaning_route:
            self.segment_slow_clean_route = False
        self.disable_sensor_cleaning = (
            self.disable_sensor_cleaning
            or not self.lidar_navigation
            or self._device.get_property(DreameMowerProperty.SENSOR_DIRTY_LEFT) is None
            or (
                not self.camera_streaming
                and self._device.get_property(DreameMowerProperty.OBSTACLE_AVOIDANCE) is None
            )
        )
        self.lensbrush = bool(
            "p2255" in model
        )
        self.map_object_offset = bool(self.lidar_navigation and "p20" in model)
        self.robot_type = RobotType.LIDAR

        self.list = [
            key
            for key, value in self.__dict__.items()
            if not callable(value) and not key.startswith("_") and value == True
        ]
        if self.custom_cleaning_mode:
            self.list.append("custom_cleaning_mode")
        if self.cruising:
            self.list.append("cruising")
        if self.map:
            self.list.append("map")

    @property
    def map(self) -> bool:
        """Returns true when mapping feature is available."""
        return bool(self._device._map_manager is not None)

    @property
    def custom_cleaning_mode(self) -> bool:
        """Returns true if customized cleaning mode can be set to segments."""
        if self.auto_switch_settings:
            return True
        segments = self._device.status.current_segments
        if not self._custom_cleaning_mode:
            if segments:
                if next(iter(segments.values())).cleaning_mode is not None:
                    self._custom_cleaning_mode = True
                    return True
        return self._custom_cleaning_mode and (not segments or next(iter(segments.values())).cleaning_mode is not None)

    @property
    def cruising(self) -> bool:
        if not self.lidar_navigation:
            return False
        return bool(
            (self._device.status.current_map and self._device.status.current_map.predefined_points is not None)
            or self._device.get_property(DreameMowerProperty.CRUISE_SCHEDULE) is not None
            or self._device.status.fill_light is not None
        )


class Point:
    def __init__(self, x: float, y: float, a=None) -> None:
        self.x = x
        self.y = y
        self.a = a

    def __str__(self) -> str:
        if self.a is None:
            return f"({self.x}, {self.y})"
        return f"({self.x}, {self.y}, a = {self.a})"

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self: Point, other: Point) -> bool:
        return other is not None and self.x == other.x and self.y == other.y and self.a == other.a

    def as_dict(self) -> Dict[str, Any]:
        if self.a is None:
            return {ATTR_X: self.x, ATTR_Y: self.y}
        return {ATTR_X: self.x, ATTR_Y: self.y, ATTR_A: self.a}

    def to_img(self, image_dimensions, offset=True) -> Point:
        return image_dimensions.to_img(self, offset)

    def to_coord(self, image_dimensions, offset=True) -> Point:
        return image_dimensions.to_coord(self, offset)

    def rotated(self, image_dimensions, degree) -> Point:
        w = int(
            (image_dimensions.width * image_dimensions.scale)
            + image_dimensions.padding[0]
            + image_dimensions.padding[2]
            - image_dimensions.crop[0]
            - image_dimensions.crop[2]
        )
        h = int(
            (image_dimensions.height * image_dimensions.scale)
            + image_dimensions.padding[1]
            + image_dimensions.padding[3]
            - image_dimensions.crop[1]
            - image_dimensions.crop[3]
        )
        x = self.x
        y = self.y
        while degree > 0:
            tmp = y
            y = w - x
            x = tmp
            tmp = h
            h = w
            w = tmp
            degree = degree - 90
        return Point(x, y)

    def __mul__(self, other) -> Point:
        return Point(self.x * other, self.y * other, self.a)

    def __truediv__(self, other) -> Point:
        return Point(self.x / other, self.y / other, self.a)


class Path(Point):
    def __init__(self, x: float, y: float, path_type: PathType) -> None:
        super().__init__(x, y)
        self.path_type = path_type

    def as_dict(self) -> Dict[str, Any]:
        attributes = {**super().as_dict()}
        if self.path_type:
            attributes[ATTR_TYPE] = self.path_type.value
        return attributes


class Obstacle(Point):
    def __init__(
        self,
        x: float,
        y: float,
        type: int,
        possibility: int,
        object_id: int = None,
        file_name: str = None,
        key: int = None,
        pos_x: float = None,
        pos_y: float = None,
        width: float = None,
        height: float = None,
        picture_status: int = 0,
        ignore_status: int = 0,
    ) -> None:
        super().__init__(x, y)
        self.type = ObstacleType(
            type) if type in ObstacleType._value2member_map_ else ObstacleType.UNKNOWN
        self.possibility = possibility
        self.object_id = object_id
        self.key = key
        self.file_name = file_name
        self.object_name = file_name
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.height = height
        self.width = width
        self.picture_status = (
            ObstaclePictureStatus(picture_status)
            if picture_status in ObstaclePictureStatus._value2member_map_
            else ObstaclePictureStatus.UNKNOWN
        )
        self.ignore_status = (
            ObstacleIgnoreStatus(ignore_status)
            if ignore_status in ObstacleIgnoreStatus._value2member_map_
            else ObstacleIgnoreStatus.UNKNOWN
        )
        self.id = str(
            self.object_id) if self.object_id else f"0{int(self.x)}0{int(self.y)}"

        if file_name and "/" in file_name:
            self.object_name = file_name.split("/")[-1]
            if "-" in self.object_name:
                self.object_name = self.object_name.split("-")[0]
        if id:
            self.object_name = f"{id}-{self.object_name}"

        self.segment = None

    def set_segment(self, map_data):
        if map_data and map_data.segments and map_data.pixel_type is not None:
            x = int((self.x - map_data.dimensions.left) /
                    map_data.dimensions.grid_size)
            y = int((self.y - map_data.dimensions.top) /
                    map_data.dimensions.grid_size)
            if x >= 0 and x < map_data.dimensions.width and y >= 0 and y < map_data.dimensions.height:
                obstacle_pixel = map_data.pixel_type[x, y]

                if obstacle_pixel not in map_data.segments:
                    for k, v in map_data.segments.items():
                        if v.check_point(self.x, self.y, map_data.dimensions.grid_size * 4):
                            self.segment = v.name
                            break
                else:
                    self.segment = map_data.segments[obstacle_pixel].name

    def as_dict(self) -> Dict[str, Any]:
        attributes = super().as_dict()
        attributes[ATTR_TYPE] = self.type.name.replace("_", " ").title()
        if self.possibility is not None:
            attributes[ATTR_POSSIBILTY] = self.possibility
        if self.picture_status is not None:
            attributes[ATTR_PICTURE_STATUS] = self.picture_status.name.replace(
                "_", " ").title()
        if self.ignore_status is not None:
            attributes[ATTR_IGNORE_STATUS] = self.ignore_status.name.replace(
                "_", " ").title()
        if self.segment is not None:
            attributes[ATTR_ZONE] = self.segment
        return attributes

    def __eq__(self: Obstacle, other: Obstacle) -> bool:
        return not (
            other is None
            or self.x != other.x
            or self.y != other.y
            or self.type != other.type
            or self.possibility != other.possibility
            or self.key != other.key
            or self.file_name != other.file_name
            or self.pos_x != other.pos_x
            or self.pos_y != other.pos_y
            or self.height != other.height
            or self.width != other.width
            or self.picture_status != other.picture_status
            or self.ignore_status != other.ignore_status
        )


class Zone:
    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1

    def __str__(self) -> str:
        return f"[{self.x0}, {self.y0}, {self.x1}, {self.y1}]"

    def __eq__(self: Zone, other: Zone) -> bool:
        return (
            other is not None
            and self.x0 == other.x0
            and self.y0 == other.y0
            and self.x1 == other.x1
            and self.y1 == other.y1
        )

    def __repr__(self) -> str:
        return self.__str__()

    def as_dict(self) -> Dict[str, Any]:
        return {ATTR_X0: self.x0, ATTR_Y0: self.y0, ATTR_X1: self.x1, ATTR_Y1: self.y1}

    def as_area(self) -> Area:
        return Area(self.x0, self.y0, self.x0, self.y1, self.x1, self.y1, self.x1, self.y0)

    def to_img(self, image_dimensions, offset=True) -> Zone:
        p0 = Point(self.x0, self.y0).to_img(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_img(image_dimensions, offset)
        return Zone(p0.x, p0.y, p1.x, p1.y)

    def to_coord(self, image_dimensions, offset=True) -> Zone:
        p0 = Point(self.x0, self.y0).to_coord(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_coord(image_dimensions, offset)
        return Zone(p0.x, p0.y, p1.x, p1.y)

    def check_point(self, x, y, size) -> bool:
        return self.as_area().check_point(x, y, size)


class Segment(Zone):
    def __init__(
        self,
        segment_id: int,
        x0: Optional[float] = None,
        y0: Optional[float] = None,
        x1: Optional[float] = None,
        y1: Optional[float] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
        name: str = None,
        custom_name: str = None,
        index: int = 0,
        type: int = 0,
        icon: str = None,
        neighbors: List[int] = [],
        cleaning_times: int = None,
        cleaning_mode: int = None,
        order: int = None,
    ) -> None:
        super().__init__(x0, y0, x1, y1)
        self.segment_id = segment_id
        self.unique_id = None
        self.x = x
        self.y = y
        self.name = name
        self.custom_name = custom_name
        self.type = type
        self.index = index
        self.icon = icon
        self.neighbors = neighbors
        self.order = order
        self.cleaning_times = cleaning_times
        self.cleaning_route = None
        self.color_index = None
        self.floor_material = None
        self.floor_material_direction = None
        self.floor_material_rotated_direction = None
        self.visibility = None
        self.cleanset_type = CleansetType.NONE
        self.set_name()

    @property
    def outline(self) -> List[List[int]]:
        return [
            [self.x0, self.y0],
            [self.x0, self.y1],
            [self.x1, self.y1],
            [self.x1, self.y0],
        ]

    @property
    def center(self) -> List[int]:
        return [self.x, self.y]

    @property
    def letter(self) -> str:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return (
            f"{letters[((self.segment_id % 26) - 1)]}{math.floor(self.segment_id / 26)}"
            if self.segment_id > 26
            else letters[self.segment_id - 1]
        )

    def set_name(self) -> None:
        if self.type != 0 and SEGMENT_TYPE_CODE_TO_NAME.get(self.type):
            self.name = SEGMENT_TYPE_CODE_TO_NAME[self.type]
            if self.index > 0:
                self.name = f"{self.name} {self.index + 1}"
        elif self.custom_name is not None:
            self.name = self.custom_name
        else:
            self.name = f"Zone {self.segment_id}"
        self.icon = SEGMENT_TYPE_CODE_TO_HA_ICON.get(
            self.type, "mdi:home-outline")

    def next_type_index(self, type, segments) -> int:
        index = 0
        if type > 0:
            for segment_id in sorted(segments, key=lambda segment_id: segments[segment_id].index):
                if (
                    segment_id != self.segment_id
                    and segments[segment_id].type == type
                    and segments[segment_id].index == index
                ):
                    index = index + 1
        return index

    def name_list(self, segments) -> dict[int, str]:
        list = {}
        for k, v in SEGMENT_TYPE_CODE_TO_NAME.items():
            index = self.next_type_index(k, segments)
            name = f"{v}"
            if index > 0:
                name = f"{name} {index + 1}"

            list[k] = name

        name = f"Zone {self.segment_id}"
        if self.type == 0:
            name = f"{self.name}"
        list[0] = name
        if self.type != 0:  # and self.index > 0:
            list[self.type] = self.name

        return {v: k for k, v in list.items()}

    def as_dict(self) -> Dict[str, Any]:
        attributes = {**super(Segment, self).as_dict()}
        if self.segment_id:
            attributes[ATTR_ZONE_ID] = self.segment_id
        if self.name is not None:
            attributes[ATTR_NAME] = self.name
        if self.order is not None:
            attributes[ATTR_ORDER] = self.order
        if self.cleaning_times is not None:
            attributes[ATTR_CLEANING_TIMES] = self.cleaning_times
        if self.cleaning_mode is not None and self.cleanset_type != CleansetType.DEFAULT:
            attributes[ATTR_CLEANING_MODE] = self.cleaning_mode
        if self.type is not None:
            attributes[ATTR_TYPE] = self.type
        if self.index is not None:
            attributes[ATTR_INDEX] = self.index
        if self.icon is not None:
            attributes[ATTR_ICON] = self.icon
        if self.color_index is not None:
            attributes[ATTR_COLOR_INDEX] = self.color_index
        if self.unique_id is not None:
            attributes[ATTR_UNIQUE_ID] = self.unique_id
        if self.floor_material is not None:
            attributes[ATTR_FLOOR_MATERIAL] = self.floor_material
        if self.floor_material_rotated_direction is not None:
            attributes[ATTR_FLOOR_MATERIAL_DIRECTION] = DreameMowerFloorMaterialDirection(
                self.floor_material_rotated_direction
            ).name.title()
        if self.visibility is not None:
            attributes[ATTR_VISIBILITY] = DreameMowerSegmentVisibility(
                int(self.visibility)).name.title()
        if self.x is not None and self.y is not None:
            attributes[ATTR_X] = self.x
            attributes[ATTR_Y] = self.y

        return attributes

    def __eq__(self: Segment, other: Segment) -> bool:
        return not (
            other is None
            or self.x0 != other.x0
            or self.y0 != other.y0
            or self.x1 != other.x1
            or self.y1 != other.y1
            or self.x != other.x
            or self.y != other.y
            or self.name != other.name
            or self.index != other.index
            or self.type != other.type
            or self.color_index != other.color_index
            or self.icon != other.icon
            or self.neighbors != other.neighbors
            or self.order != other.order
            or self.cleaning_times != other.cleaning_times
            or self.cleaning_mode != other.cleaning_mode
            or self.floor_material != other.floor_material
            or self.floor_material_direction != other.floor_material_direction
            or self.floor_material_rotated_direction != other.floor_material_rotated_direction
            or self.visibility != other.visibility
        )

    def __str__(self) -> str:
        return f"{{zone_id: {self.segment_id}, outline: {self.outline}}}"

    def __repr__(self) -> str:
        return self.__str__()


class Wall:
    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1

    def __eq__(self: Wall, other: Wall) -> bool:
        return (
            other is not None
            and self.x0 == other.x0
            and self.y0 == other.y0
            and self.x1 == other.x1
            and self.y1 == other.y1
        )

    def __str__(self) -> str:
        return f"[{self.x0}, {self.y0}, {self.x1}, {self.y1}]"

    def __repr__(self) -> str:
        return self.__str__()

    def as_dict(self) -> Dict[str, Any]:
        return {ATTR_X0: self.x0, ATTR_Y0: self.y0, ATTR_X1: self.x1, ATTR_Y1: self.y1}

    def to_img(self, image_dimensions, offset=True) -> Wall:
        p0 = Point(self.x0, self.y0).to_img(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_img(image_dimensions, offset)
        return Wall(p0.x, p0.y, p1.x, p1.y)

    def to_coord(self, image_dimensions, offset=True) -> Wall:
        p0 = Point(self.x0, self.y0).to_coord(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_coord(image_dimensions, offset)
        return Wall(p0.x, p0.y, p1.x, p1.y)

    def as_list(self) -> List[float]:
        return [self.x0, self.y0, self.x1, self.y1]


class Area:
    def __init__(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
    ) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.x3 = x3
        self.y3 = y3

    def __eq__(self: Area, other: Area) -> bool:
        return (
            other is not None
            and self.x0 == other.x0
            and self.y0 == other.y0
            and self.x1 == other.x1
            and self.y1 == other.y1
            and self.x2 == other.x2
            and self.y2 == other.y2
            and self.x3 == other.x3
            and self.y3 == other.y3
        )

    def __str__(self) -> str:
        return f"[{self.x0}, {self.y0}, {self.x1}, {self.y1}, {self.x2}, {self.y2}, {self.x3}, {self.y3}]"

    def __repr__(self) -> str:
        return self.__str__()

    def as_dict(self) -> Dict[str, Any]:
        return {
            ATTR_X0: self.x0,
            ATTR_Y0: self.y0,
            ATTR_X1: self.x1,
            ATTR_Y1: self.y1,
            ATTR_X2: self.x2,
            ATTR_Y2: self.y2,
            ATTR_X3: self.x3,
            ATTR_Y3: self.y3,
        }

    def as_list(self) -> List[float]:
        return [self.x0, self.y0, self.x1, self.y1, self.x2, self.y2, self.x3, self.y3]

    def to_img(self, image_dimensions, offset=True) -> Area:
        p0 = Point(self.x0, self.y0).to_img(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_img(image_dimensions, offset)
        p2 = Point(self.x2, self.y2).to_img(image_dimensions, offset)
        p3 = Point(self.x3, self.y3).to_img(image_dimensions, offset)
        return Area(p0.x, p0.y, p1.x, p1.y, p2.x, p2.y, p3.x, p3.y)

    def to_coord(self, image_dimensions, offset=True) -> Area:
        p0 = Point(self.x0, self.y0).to_coord(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_coord(image_dimensions, offset)
        p2 = Point(self.x2, self.y2).to_coord(image_dimensions, offset)
        p3 = Point(self.x3, self.y3).to_coord(image_dimensions, offset)
        return Area(p0.x, p0.y, p1.x, p1.y, p2.x, p2.y, p3.x, p3.y)

    def check_size(self, size) -> bool:
        return self.x2 - self.x0 == size and self.y2 - self.y1 == size

    def check_point(self, x, y, size) -> bool:
        x_coords = [self.x0, self.x1, self.x2, self.x3]
        y_coords = [self.y0, self.y1, self.y2, self.y3]

        min_x = min(x_coords)
        max_x = max(x_coords)
        min_y = min(y_coords)
        max_y = max(y_coords)
        return x >= min_x - size and x <= max_x + size and y >= min_y - size and y <= max_y + size


class Furniture(Point):
    def __init__(
        self,
        x: float,
        y: float,
        x0: float,
        y0: float,
        width: float,
        height: float,
        type: FurnitureType,
        size_type: int,
        angle: float = 0,
        scale: float = 1.0,
        furniture_id: int = None,
        segment_id: int = None,
    ) -> None:
        super().__init__(x, y)
        self.x0 = x0
        self.y0 = y0
        self.width = width
        self.height = height
        if x0 and y0 and width and height:
            self.x1 = x0 + width
            self.y1 = y0
            self.x2 = x0 + width
            self.y2 = y0 + height
            self.x3 = x0
            self.y3 = y0 + height
        else:
            self.x1 = None
            self.y1 = None
            self.x2 = None
            self.y2 = None
            self.x3 = None
            self.y3 = None
        self.type = type
        self.size_type = size_type
        self.angle = angle
        self.scale = scale
        self.furniture_id = furniture_id
        self.segment_id = segment_id

    def as_dict(self) -> Dict[str, Any]:
        attributes = super().as_dict()
        attributes[ATTR_TYPE] = self.type.name.replace("_", " ").title()
        if self.x0 is not None and self.y0 is not None:
            attributes[ATTR_X0] = self.x0
            attributes[ATTR_Y0] = self.y0
        if self.x1 is not None and self.y1 is not None:
            attributes[ATTR_X1] = self.x1
            attributes[ATTR_Y1] = self.y1
        if self.x2 is not None and self.y2 is not None:
            attributes[ATTR_X2] = self.x2
            attributes[ATTR_Y2] = self.y2
        if self.x3 is not None and self.y3 is not None:
            attributes[ATTR_X3] = self.x3
            attributes[ATTR_Y3] = self.y3
        if self.width and self.height:
            attributes[ATTR_WIDTH] = self.width
            attributes[ATTR_HEIGHT] = self.height
        if self.segment_id:
            attributes[ATTR_ZONE_ID] = self.segment_id
        attributes[ATTR_SIZE_TYPE] = self.size_type
        attributes[ATTR_ANGLE] = self.angle
        attributes[ATTR_SCALE] = self.scale
        return attributes

    def __eq__(self: Furniture, other: Furniture) -> bool:
        return not (
            other is None
            or self.x != other.x
            or self.y != other.y
            or self.x0 != other.x0
            or self.y0 != other.y0
            or self.width != other.width
            or self.height != other.height
            or self.type != other.type
            or self.size_type != other.size_type
            or self.angle != other.angle
            or self.scale != other.scale
        )


class Coordinate(Point):
    def __init__(self, x: float, y: float, completed: bool, type: int) -> None:
        super().__init__(x, y)
        self.type = type
        self.completed = completed

    def as_dict(self) -> Dict[str, Any]:
        attributes = {**super().as_dict()}
        if self.type is not None:
            attributes[ATTR_TYPE] = self.type
        if self.completed is not None:
            attributes[ATTR_COMPLETED] = self.completed
        return attributes

    def __eq__(self: Coordinate, other: Coordinate) -> bool:
        return not (
            other is None
            or self.x != other.x
            or self.y != other.y
            or self.type != other.type
            or self.completed != other.completed
        )


class MapImageDimensions:
    def __init__(self, top: int, left: int, height: int, width: int, grid_size: int) -> None:
        self.top = top
        self.left = left
        self.height = height
        self.width = width
        self.grid_size = grid_size
        self.scale = 1
        self.padding = [0, 0, 0, 0]
        self.crop = [0, 0, 0, 0]
        self.bounds = None

    def to_img(self, point: Point, offset=True) -> Point:
        left = self.left
        top = self.top
        if not offset and (left % self.grid_size != 0 or top % self.grid_size != 0):
            left = left + (self.grid_size / 2)
            top = top - (self.grid_size / 2)

        return Point(
            ((point.x - left) / self.grid_size) *
            self.scale + self.padding[0] - self.crop[0],
            (((self.height - 1) * self.grid_size -
             (point.y - top)) / self.grid_size) * self.scale
            + self.padding[1]
            - self.crop[1],
        )

    def to_coord(self, point: Point, offset=True) -> Point:
        left = self.left
        top = self.top
        if not offset and (left % self.grid_size != 0 or top % self.grid_size != 0):
            left = left + (self.grid_size / 2)
            top = top - (self.grid_size / 2)

        return Point(
            ((point.x - left) / self.grid_size),
            (((self.height - 1) * self.grid_size - (point.y - top)) / self.grid_size),
        )

    def __eq__(self: MapImageDimensions, other: MapImageDimensions) -> bool:
        return (
            other is not None
            and self.top == other.top
            and self.left == other.left
            and self.height == other.height
            and self.width == other.width
            and self.grid_size == other.grid_size
        )


class CleaningHistory:
    def __init__(self, history_data, property_mapping) -> None:
        self.date: datetime = None
        self.status: DreameMowerStatus = None
        self.cleaning_time: int = 0
        self.cleaned_area: int = 0
        self.file_name: str = None
        self.key = None
        self.object_name = None
        self.completed: bool = None
        self.map_index: int = None
        self.map_name: str = None
        self.cruise_type: int = None
        self.cleanup_method: CleanupMethod = None
        self.second_cleaning: int = None
        self.multiple_cleaning_time: str = None
        self.pet_focused_cleaning: int = None
        self.task_interrupt_reason: TaskInterruptReason = None
        self.neglected_segments: Dict[int, int] = None
        self.clean_again: int = None

        for history_data_item in history_data:
            pid = history_data_item[piid]
            value = history_data_item["value"] if "value" in history_data_item else history_data_item["val"]

            if pid == PIID(DreameMowerProperty.STATUS, property_mapping):
                if value in DreameMowerStatus._value2member_map_:
                    self.status = DreameMowerStatus(value)
                else:
                    self.status = DreameMowerStatus.UNKNOWN
            elif pid == PIID(DreameMowerProperty.CLEANING_TIME, property_mapping):
                self.cleaning_time = value
            elif pid == PIID(DreameMowerProperty.CLEANED_AREA, property_mapping):
                self.cleaned_area = value
            elif pid == PIID(DreameMowerProperty.CLEANING_START_TIME, property_mapping):
                self.date = datetime.fromtimestamp(value)
            elif pid == PIID(DreameMowerProperty.CLEAN_LOG_FILE_NAME, property_mapping):
                self.file_name = value
                if len(self.file_name) > 1:
                    if "," in self.file_name:
                        values = self.file_name.split(",")
                        self.object_name = values[0]
                        self.key = values[1]
                    else:
                        self.object_name = self.file_name
            elif pid == PIID(DreameMowerProperty.CLEAN_LOG_STATUS, property_mapping):
                self.completed = bool(value)
            elif pid == PIID(DreameMowerProperty.MAP_INDEX, property_mapping):
                self.map_index = value
            elif pid == PIID(DreameMowerProperty.MAP_NAME, property_mapping):
                self.map_name = value
            elif pid == PIID(DreameMowerProperty.CRUISE_TYPE, property_mapping):
                self.cruise_type = value
            elif pid == PIID(DreameMowerProperty.CLEANING_PROPERTIES, property_mapping):
                props = json.loads(value)
                if "cmc" in props:
                    value = props["cmc"]
                    self.cleanup_method = (
                        CleanupMethod(
                            value) if value in CleanupMethod._value2member_map_ else CleanupMethod.OTHER
                    )
                if "abnormal_end" in props:
                    values = json.loads(props["abnormal_end"])
                    self.task_interrupt_reason = (
                        TaskInterruptReason(values[0])
                        if values[0] in TaskInterruptReason._value2member_map_
                        else TaskInterruptReason.UNKNOWN
                    )
                self.second_cleaning = props.get("ismultiple")
                self.multiple_cleaning_time = props.get("multime")
                self.pet_focused_cleaning = props.get("pet")
                self.neglected_segments = props.get("area_clean_detail")
                self.clean_again = props.get("cleanagain")
                if "area_clean_detail" in props:
                    values = props["area_clean_detail"]
                    if len(values) > 1:
                        values = json.loads(values)
                        if values:
                            self.neglected_segments = {
                                v[0]: SegmentNeglectReason(v[1])
                                for v in values
                                if v[1] in SegmentNeglectReason._value2member_map_
                            }


class RecoveryMapInfo:
    def __init__(self, map_id, map_info) -> None:
        self.date = map_info.get("time")
        self.raw_map: str = map_info.get("thb")
        self.object_name: str = map_info.get("objname")
        self.map_data: MapData = None
        self.map_id: int = map_id

        map_type = map_info.get("first", -1)
        self.map_type = (
            RecoveryMapType(
                map_type) if map_type in RecoveryMapType._value2member_map_ else RecoveryMapType.UNKNOWN
        )

        if self.date:
            self.date = datetime.fromtimestamp(self.date)

    def as_dict(self):
        return {
            "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.date.timestamp())),
            "map_type": self.map_type.name.replace("_", " ").title(),
            "object_name": self.object_name,
        }


class MapFrameType(IntEnum):
    I = 73
    P = 80
    # T = ??
    W = 87


class MapPixelType(IntEnum):
    OUTSIDE = 0
    WIFI_WALL = 2
    WIFI_UNREACHED = 10
    WIFI_POOR = 11
    WIFI_LOW = 12
    WIFI_HIGH = 13
    WIFI_EXCELLENT = 14
    WALL = 255
    FLOOR = 254
    NEW_SEGMENT = 253
    UNKNOWN = 252
    OBSTACLE_WALL = 251
    NEW_SEGMENT_UNKNOWN = 250
    HIDDEN_WALL = 249
    CLEAN_AREA = 248
    DIRTY_AREA = 247


class RecoveryMapType(IntEnum):
    UNKNOWN = -1
    EDITED = 0
    ORIGINAL = 1
    BACKUP = 2


class StartupMethod(IntEnum):
    OTHER = -1
    BY_BUTTON = 0
    THROUGH_APP = 1
    SCHEDULED_ACTIVATION = 2
    THROUGH_VOICE = 3


class CleanupMethod(IntEnum):
    OTHER = -1
    DEFAULT_MODE = 0
    CUSTOMIZED_CLEANING = 1
    CLEANGENIUS = 2


class TaskEndType(IntEnum):
    OTHER = 0
    MANUAL_DOCKING = 1
    NORMAL_RECHARGING = 2
    ABNORMAL_DOCKING = 3
    INTERRUPTION_ENDED = 4


class MapDataPartial:
    def __init__(self) -> None:
        self.map_id: Optional[int] = None  # Map header: map_id
        self.frame_id: Optional[int] = None  # Map header: frame_id
        self.frame_type: Optional[int] = None  # Map header: frame_type
        self.timestamp_ms: Optional[int] = None  # Data json: timestamp_ms
        self.raw: Optional[bytes] = None  # Unzipped raw map
        self.data_json: Optional[object] = {}  # Data json


class MapData:
    def __init__(self) -> None:
        # Header
        self.map_id: Optional[int] = None  # Map header: map_id
        self.frame_id: Optional[int] = None  # Map header: frame_id
        self.frame_type: Optional[int] = None  # Map header: frame_type
        # Map header: robot x, robot y, robot angle
        self.robot_position: Optional[Point] = None
        # Map header: charger x, charger y, charger angle
        self.charger_position: Optional[Point] = None
        self.optimized_charger_position: Optional[Point] = None
        self.router_position: Optional[Point] = None  # Data json: whmp
        # Map header: top, left, height, width, grid_size
        self.dimensions: Optional[MapImageDimensions] = None
        self.optimized_dimensions: Optional[MapImageDimensions] = None
        self.combined_dimensions: Optional[MapImageDimensions] = None
        self.data: Optional[Any] = None  # Raw image data for handling P frames
        # Data json
        self.timestamp_ms: Optional[int] = None  # Data json: timestamp_ms
        self.rotation: Optional[int] = None  # Data json: mra
        self.no_go_areas: Optional[List[Area]] = None  # Data json: vw.rect
        self.virtual_walls: Optional[List[Wall]] = None  # Data json: vw.line
        self.pathways: Optional[List[Wall]] = None  # Data json: vws.vwsl
        self.path: Optional[Path] = None  # Data json: tr
        self.active_segments: Optional[int] = None  # Data json: sa
        self.active_areas: Optional[List[Area]] = None  # Data json: da2
        self.active_points: Optional[List[Point]] = None  # Data json: sp
        # Data json: rism.map_header.map_id
        self.saved_map_id: Optional[int] = None
        self.saved_map_status: Optional[int] = None  # Data json: ris
        self.restored_map: Optional[bool] = None  # Data json: rpur
        self.frame_map: Optional[bool] = None  # Data json: fsm
        self.docked: Optional[bool] = None  # Data json: oc
        self.clean_log: Optional[bool] = None  # Data json: iscleanlog
        self.cleanset: Optional[Dict[str, List[int]]
                                ] = None  # Data json: cleanset
        self.line_to_robot: Optional[bool] = None  # Data json: l2r
        self.temporary_map: Optional[int] = None  # Data json: suw
        self.cleaned_area: Optional[int] = None  # Data json: cs
        self.cleaning_time: Optional[int] = None  # Data json: ct
        self.completed: Optional[bool] = None  # Data json: cf
        self.neglected_segments: Optional[List[int]] = None  #
        self.second_cleaning: Optional[bool] = None  #
        # Data json: clean_finish_remain_electricity
        self.remaining_battery: Optional[int] = None
        self.work_status: Optional[int] = None  # Data json: wm
        self.recovery_map: Optional[bool] = None  # Data json: us
        # Generated from recovery map list json
        self.recovery_map_type: Optional[RecoveryMapType] = None
        self.obstacles: Optional[Dict[int, Obstacle]
                                 ] = None  # Data json: ai_obstacle
        # Data json: ai_furniture
        self.furnitures: Optional[Dict[int, Furniture]] = None
        # Data json: furniture_info
        self.saved_furnitures: Optional[Dict[int, Furniture]] = None
        self.new_map: Optional[bool] = None  # Data json: risp
        self.startup_method: Optional[StartupMethod] = None  # Data json: smd
        self.task_end_type: Optional[TaskEndType] = None  # Data json: ctyi
        self.cleanup_method: Optional[CleanupMethod] = None  #
        # Data json: customeclean
        self.customized_cleaning: Optional[int] = None
        # Data json: CleanArea (from dirty map data)
        self.cleaned_segments: Optional[List[Any]] = None
        self.multiple_cleaning_time: Optional[int] = None  # Data json: multime
        self.dos: Optional[int] = None  # Data json: dos
        # Generated
        self.custom_name: Optional[str] = None  # Map list json: name
        self.map_index: Optional[int] = None  # Generated from saved map list
        self.map_name: Optional[str] = None  # Generated map name for map list
        # Generated pixel map for rendering colors
        self.pixel_type: Optional[Any] = None
        self.optimized_pixel_type: Optional[Any] = None
        self.combined_pixel_type: Optional[Any] = None
        # Generated segments from pixel_type
        self.segments: Optional[Dict[int, Segment]] = None
        # Generated from seg_inf.material
        self.floor_material: Optional[Dict[int, int]] = None
        self.saved_map: Optional[bool] = None  # Generated for rism map
        self.empty_map: Optional[bool] = None  # Generated from pixel_type
        self.wifi_map_data: Optional[MapData] = None  # Generated from whm
        self.wifi_map: Optional[bool] = None  #
        # Generated from decmap
        self.cleaning_map_data: Optional[MapData] = None
        self.cleaning_map: Optional[bool] = None  #
        self.has_cleaned_area: Optional[bool] = None  #
        self.has_dirty_area: Optional[bool] = None  #
        self.history_map: Optional[bool] = None  #
        self.furniture_version: Optional[bool] = None  #
        # Generated from recovery map list
        self.recovery_map_list: Optional[List[RecoveryMapInfo]] = None
        # Data json: pointinfo.tpoint
        self.active_cruise_points: Optional[List[Coordinate]] = None
        # Data json: pointinfo.spoint
        self.predefined_points: Optional[Dict[int, Coordinate]] = None
        # Data json: tpointinfo
        self.task_cruise_points: Optional[List[Coordinate]] = None
        # Generated from pixel_type and robot poisiton
        self.hidden_segments: Optional[int] = None  # Data json: delsr
        self.robot_segment: Optional[int] = None
        # For renderer to detect changes
        self.last_updated: Optional[float] = None
        # For vslam map rendering optimization
        self.need_optimization: Optional[bool] = None
        # 3D Map Properties
        self.ai_outborders_user: Optional[Any] = None
        self.ai_outborders: Optional[Any] = None
        self.ai_outborders_new: Optional[Any] = None
        self.ai_outborders_2d: Optional[Any] = None
        self.ai_furniture_warning: Optional[Any] = None
        self.walls_info: Optional[Any] = None
        self.walls_info_new: Optional[Any] = None

    def __eq__(self: MapData, other: MapData) -> bool:
        if other is None:
            return False

        if self.map_id != other.map_id:
            return False

        if self.custom_name != other.custom_name:
            return False

        if self.rotation != other.rotation:
            return False

        if self.work_status != other.work_status:
            return False

        if self.robot_position != other.robot_position:
            return False

        if self.charger_position != other.charger_position:
            return False

        if self.no_go_areas != other.no_go_areas:
            return False

        if self.virtual_walls != other.virtual_walls:
            return False

        if self.pathways != other.pathways:
            return False

        if self.docked != other.docked:
            return False

        if self.active_segments != other.active_segments:
            return False

        if self.active_areas != other.active_areas:
            return False

        if self.active_points != other.active_points:
            return False

        if self.active_cruise_points != other.active_cruise_points:
            return False

        if self.clean_log != other.clean_log:
            return False

        if self.saved_map_status != other.saved_map_status:
            return False

        if self.restored_map != other.restored_map:
            return False

        if self.frame_map != other.frame_map:
            return False

        if self.temporary_map != other.temporary_map:
            return False

        if self.saved_map != other.saved_map:
            return False

        if self.new_map != other.new_map:
            return False

        if self.cleanset != other.cleanset:
            return False

        if self.furnitures != other.furnitures:
            return False

        if self.saved_furnitures != other.saved_furnitures:
            return False

        if self.obstacles != other.obstacles:
            return False

        if self.predefined_points != other.predefined_points:
            return False

        if self.router_position != other.router_position:
            return False

        if self.hidden_segments != other.hidden_segments:
            return False

        return True

    def as_dict(self) -> Dict[str, Any]:
        attributes_list = {}
        if self.charger_position is not None:
            attributes_list[ATTR_CHARGER] = (
                self.optimized_charger_position
                if self.optimized_charger_position is not None
                else self.charger_position
            )
        if self.segments is not None and (self.saved_map or self.saved_map_status == 2 or self.restored_map):
            attributes_list[ATTR_ZONES] = {
                k: v.as_dict() for k, v in sorted(self.segments.items())}
        if not self.saved_map and self.robot_position is not None:
            attributes_list[ATTR_ROBOT_POSITION] = self.robot_position
        if self.map_id:
            attributes_list[ATTR_MAP_ID] = self.map_id
        if self.map_name is not None:
            attributes_list[ATTR_MAP_NAME] = self.map_name
        if self.rotation is not None:
            attributes_list[ATTR_ROTATION] = self.rotation
        if self.last_updated is not None:
            attributes_list[ATTR_UPDATED] = datetime.fromtimestamp(
                self.last_updated)
        if not self.saved_map and self.active_areas is not None:
            attributes_list[ATTR_ACTIVE_AREAS] = self.active_areas
        if not self.saved_map and self.active_segments is not None:
            attributes_list[ATTR_ACTIVE_SEGMENTS] = self.active_segments
        if not self.saved_map and self.active_points is not None:
            attributes_list[ATTR_ACTIVE_POINTS] = self.active_points
        if not self.saved_map and self.active_cruise_points is not None:
            attributes_list[ATTR_ACTIVE_CRUISE_POINTS] = self.active_cruise_points
        if self.predefined_points:
            attributes_list[ATTR_PREDEFINED_POINTS] = list(
                self.predefined_points.values())
        if self.virtual_walls is not None:
            attributes_list[ATTR_VIRTUAL_WALLS] = self.virtual_walls
        if self.pathways is not None:
            attributes_list[ATTR_PATHWAYS] = self.pathways
        if self.no_go_areas is not None:
            attributes_list[ATTR_NO_GO_AREAS] = self.no_go_areas
        if self.empty_map is not None:
            attributes_list[ATTR_IS_EMPTY] = self.empty_map
        if self.frame_id:
            attributes_list[ATTR_FRAME_ID] = self.frame_id
        if self.map_index:
            attributes_list[ATTR_MAP_INDEX] = self.map_index
        if self.obstacles:
            attributes_list[ATTR_OBSTACLES] = self.obstacles
        if self.saved_furnitures and self.saved_map:
            attributes_list[ATTR_FURNITURES] = list(
                self.saved_furnitures.values())
        elif self.furnitures:
            attributes_list[ATTR_FURNITURES] = list(self.furnitures.values())
        if self.router_position:
            attributes_list[ATTR_ROUTER_POSITION] = self.router_position
        if self.startup_method:
            attributes_list[ATTR_STARTUP_METHOD] = self.startup_method.name.replace(
                "_", " ").title()
        if self.recovery_map_list:
            attributes_list[ATTR_RECOVERY_MAP_LIST] = [
                v.as_dict() for v in reversed(self.recovery_map_list)]
        return attributes_list

    def check_point(self, x, y, absolute=False) -> bool:
        if not absolute:
            x = int((x - self.dimensions.left) / self.dimensions.grid_size)
            y = int((y - self.dimensions.top) / self.dimensions.grid_size)
        if x < 0 or x >= self.dimensions.width or y < 0 or y >= self.dimensions.height:
            return False
        value = int(self.pixel_type[x, y])
        return value > 0 and value != 255


@dataclass
class DirtyData:
    value: Any = None
    previous_value: Any = None
    update_time: float = None


@dataclass
class Shortcut:
    id: int = -1
    name: str = None
    map_id: int = None
    running: bool = False
    tasks: list[list[ShortcutTask]] = None


@dataclass
class ShortcutTask:
    segment_id: int = None
    cleaning_times: int = None
    cleaning_mode: int = None


@dataclass
class DNDTask:
    id: int = -1
    start_time: str = None
    end_time: str = None
    enabled: bool = False
    weekdays: int = 127
    st: int = 0


@dataclass
class GoToZoneSettings:
    x: int = None
    y: int = None
    stop: bool = False
    cleaning_mode: int = None
    size: int = 50


@dataclass
class MapRendererConfig:
    color: bool = True
    icon: bool = True
    name: bool = True
    name_background: bool = True
    order: bool = True
    cleaning_times: bool = True
    cleaning_mode: bool = True
    path: bool = True
    no_go: bool = True
    no_mop: bool = True
    virtual_wall: bool = True
    pathway: bool = True
    active_area: bool = True
    active_point: bool = True
    charger: bool = True
    robot: bool = True
    cleaning_direction: bool = True
    obstacle: bool = True
    pet: bool = True
    material: bool = True
    furniture: bool = True
    cruise_point: bool = True


@dataclass
class MapRendererColorScheme:
    floor: tuple[int] = (221, 221, 221, 255)
    outside: tuple[int] = (0, 0, 0, 0)
    wall: tuple[int] = (159, 159, 159, 255)
    passive_segment: tuple[int] = (200, 200, 200, 255)
    hidden_segment: tuple[int] = (226, 226, 226, 255)
    new_segment: tuple[int] = (153, 191, 255, 255)
    cleaned_area: tuple[int] = (158, 240, 117, 255)
    dirty_area: tuple[int] = (247, 135, 106, 255)
    clean_area: tuple[int] = (156, 202, 250, 255)
    second_clean_area: tuple[int] = (123, 148, 172, 255)
    neglected_segment: tuple[int] = (255, 159, 10, 110)
    no_go: tuple[int] = (177, 0, 0, 50)
    no_go_outline: tuple[int] = (199, 0, 0, 200)
    virtual_wall: tuple[int] = (199, 0, 0, 200)
    pathway: tuple[int] = (23, 111, 244, 200)
    active_area: tuple[int] = (255, 255, 255, 80)
    active_area_outline: tuple[int] = (
        34, 109, 242, 255)  # (103, 156, 244, 200)
    active_point: tuple[int] = (255, 255, 255, 80)
    active_point_outline: tuple[int] = (
        34, 109, 242, 255)  # (103, 156, 244, 200)
    path: tuple[int] = (255, 255, 255, 255)
    segment: tuple[list[tuple[int]]] = (
        [(171, 199, 248, 255), (121, 170, 255, 255)],
        [(249, 224, 125, 255), (255, 211, 38, 255)],
        [(184, 227, 255, 255), (141, 210, 255, 255)],
        [(184, 217, 141, 255), (150, 217, 141, 255)],
    )
    obstacle_bg: tuple[int] = (34, 109, 242, 255)
    icon_background: tuple[int] = (0, 0, 0, 100)
    settings_background: tuple[int] = (255, 255, 255, 175)
    settings_icon_background: tuple[int] = (255, 255, 255, 205)
    material_color: tuple[int] = (0, 0, 0, 20)
    text: tuple[int] = (255, 255, 255, 255)
    order: tuple[int] = (255, 255, 255, 255)
    text_stroke: tuple[int] = (240, 240, 240, 200)
    invert: bool = False
    dark: bool = False


MAP_COLOR_SCHEME_LIST: Final = {
    "Dreame Light": MapRendererColorScheme(),
    "Dreame Dark": MapRendererColorScheme(
        floor=(110, 110, 110, 255),
        wall=(64, 64, 64, 255),
        passive_segment=(100, 100, 100, 255),
        hidden_segment=(116, 116, 116, 255),
        new_segment=(0, 91, 244, 255),
        no_go=(133, 0, 0, 128),
        no_go_outline=(149, 0, 0, 200),
        virtual_wall=(133, 0, 0, 200),
        active_area=(200, 200, 200, 70),
        active_area_outline=(28, 81, 176, 255),  # (9, 54, 129, 200),
        active_point=(200, 200, 200, 80),
        active_point_outline=(28, 81, 176, 255),  # (9, 54, 129, 200),
        path=(200, 200, 200, 255),
        segment=(
            [(13, 64, 155, 255), (0, 55, 150, 255)],
            [(143, 75, 7, 255), (117, 53, 0, 255)],
            [(0, 106, 176, 255), (0, 96, 158, 255)],
            [(76, 107, 36, 255), (44, 107, 36, 255)],
        ),
        obstacle_bg=(28, 81, 176, 255),
        material_color=(255, 255, 255, 20),
        settings_icon_background=(255, 255, 255, 195),
        dark=True,
    ),
    "Mijia Light": MapRendererColorScheme(
        new_segment=(131, 178, 255, 255),
        virtual_wall=(255, 45, 45, 200),
        no_go=(230, 30, 30, 128),
        no_go_outline=(255, 45, 45, 200),
        segment=(
            [(131, 178, 255, 255), (105, 142, 204, 255)],
            [(245, 201, 66, 255), (196, 161, 53, 255)],
            [(103, 207, 229, 255), (82, 165, 182, 255)],
            [(255, 155, 101, 255), (204, 124, 81, 255)],
        ),
        obstacle_bg=(131, 178, 255, 255),
    ),
    "Mijia Dark": MapRendererColorScheme(
        floor=(150, 150, 150, 255),
        wall=(119, 133, 153, 255),
        new_segment=(99, 148, 230, 255),
        passive_segment=(100, 100, 100, 255),
        hidden_segment=(116, 116, 116, 255),
        no_go=(133, 0, 0, 128),
        no_go_outline=(149, 0, 0, 200),
        virtual_wall=(133, 0, 0, 200),
        active_area=(200, 200, 200, 70),
        active_area_outline=(9, 54, 129, 200),
        active_point=(200, 200, 200, 80),
        active_point_outline=(9, 54, 129, 200),
        path=(200, 200, 200, 255),
        segment=(
            [(108, 141, 195, 255), (76, 99, 137, 255)],
            [(188, 157, 62, 255), (133, 111, 44, 255)],
            [(88, 161, 176, 255), (62, 113, 123, 255)],
            [(195, 125, 87, 255), (138, 89, 62, 255)],
        ),
        obstacle_bg=(108, 141, 195, 255),
        material_color=(255, 255, 255, 35),
        settings_icon_background=(255, 255, 255, 195),
        dark=True,
    ),
    "Grayscale": MapRendererColorScheme(
        floor=(100, 100, 100, 255),
        wall=(40, 40, 40, 255),
        passive_segment=(50, 50, 50, 255),
        hidden_segment=(55, 55, 55, 255),
        new_segment=(80, 80, 80, 255),
        no_go=(133, 0, 0, 128),
        no_go_outline=(149, 0, 0, 200),
        virtual_wall=(133, 0, 0, 200),
        active_area=(221, 221, 221, 60),
        active_area_outline=(22, 103, 238, 200),
        active_point=(221, 221, 221, 80),
        active_point_outline=(22, 103, 238, 200),
        path=(200, 200, 200, 255),
        segment=(
            [(90, 90, 90, 255), (95, 95, 95, 255)],
            [(80, 80, 80, 255), (85, 85, 85, 255)],
            [(70, 70, 70, 255), (75, 75, 75, 255)],
            [(60, 60, 60, 255), (65, 65, 65, 255)],
        ),
        obstacle_bg=(90, 90, 90, 255),
        material_color=(255, 255, 255, 20),
        icon_background=(200, 200, 200, 200),
        settings_icon_background=(255, 255, 255, 205),
        text=(0, 0, 0, 255),
        text_stroke=(0, 0, 0, 100),
        invert=True,
        dark=True,
    ),
    "Transparent": MapRendererColorScheme(
        floor=(0, 0, 0, 0),
        wall=(0, 0, 0, 0),
        passive_segment=(0, 0, 0, 0),
        hidden_segment=(0, 0, 0, 0),
        new_segment=(0, 0, 0, 0),
        path=(255, 255, 255, 200),
        segment=(
            [(0, 0, 0, 0), (121, 170, 255, 255)],
            [(0, 0, 0, 0), (255, 211, 38, 255)],
            [(0, 0, 0, 0), (141, 210, 255, 255)],
            [(0, 0, 0, 0), (150, 217, 141, 255)],
        ),
    ),
}

MAP_ICON_SET_LIST: Final = {"Dreame": 0,
                            "Dreame Old": 1, "Mijia": 2, "Material": 3}


class MapRendererLayer(IntEnum):
    IMAGE = 0
    OBJECTS = 1
    PATH = 2
    PATH_MASK = 3
    NO_GO = 5
    WALL = 6
    PATHWAY = 7
    ACTIVE_AREA = 8
    ACTIVE_POINT = 9
    FURNITURES = 10
    FURNITURE = 11
    SEGMENTS = 12
    SEGMENT = 13
    CHARGER = 14
    ROBOT = 15
    ROUTER = 16
    OBSTACLES = 17
    OBSTACLE = 18
    CRUISE_POINTS = 19
    CRUISE_POINT = 20


@dataclass
class Line:
    x: int | List[int] = None
    y: int | List[int] = None
    ishorizontal: bool = False
    direction: int = 0


@dataclass
class CLine(Line):
    length: int = 0
    findEnd: bool = False


@dataclass
class ALine:
    p0: Line = field(default_factory=lambda: Line(0, 0, False, 0))
    p1: Line = field(default_factory=lambda: Line(0, 0, False, 0))
    length: int = 0


@dataclass
class Paths:
    clines: List[CLine] = field(default_factory=lambda: [])
    alines: List[ALine] = field(default_factory=lambda: [])
    length: int = 0


@dataclass
class Angle:
    lines: List[ALine] = field(default_factory=lambda: [])
    horizontalDir: int = 0
    verticalDir: int = 0


@dataclass
class MapRendererResources:
    renderer: str = ""
    icon_set: int = 0
    robot_type: int = 0
    robot: str = None
    charger: str = None
    charging: str = None
    cleaning: str = None
    warning: str = None
    sleeping: str = None
    cleaning_direction: str = None
    selected_segment: str = None
    cruise_point_background: str = None
    segment: Dict[int, Dict[str, str]] = None
    default_map_image: str = None
    font: str = None
    repeats: list[str] = None
    cleaning_mode: list[str] = None
    cleaning_route: list[str] = None
    emptying: str = None
    cruise_path_point_background: str = None
    obstacle_background: str = None
    obstacle_hidden_background: str = None
    obstacle: Dict[int, Dict[str, str]] = None
    furniture: Dict[int, Dict[str, str]] = None
    rotate: str = None
    delete: str = None
    resize: str = None
    move: str = None
    problem: str = None
    wifi: str = None
    version: int = 1


@dataclass
class MapRendererData:
    data: Dict[int, list[int]]
    size: list[int] = None
    frame_id: int = 0
    saved_map: bool = False
    wifi_map: bool = False
    history_map: bool = False
    recovery_map: bool = False
    segments: Dict[int, list[int | str]] | None = None
    active_segments: list[int] = field(default_factory=lambda: [])
    active_areas: list[list[int]] = field(default_factory=lambda: [])
    active_points: list[list[int]] = field(default_factory=lambda: [])
    active_cruise_points: list[list[int]] = field(default_factory=lambda: [])
    task_cruise_points: bool = False
    predefined_points: list[list[int]] | None = None
    no_mop: list[list[int]] = field(default_factory=lambda: [])
    no_go: list[list[int]] = field(default_factory=lambda: [])
    virtual_walls: list[list[int]] = field(default_factory=lambda: [])
    pathways: list[list[int]] | None = None
    obstacles: list[list[int | float]] = field(default_factory=lambda: [])
    furnitures: list[list[int | float]] | None = None
    path: list[list[int]] = field(default_factory=lambda: [])
    floor_material: Dict[int, list[int]] | None = None
    hidden_segments: Dict[int, list[int]] | None = None
    neglected_segments: Dict[int, list[int]] | None = None
    robot_position: list[int] | None = None
    charger_position: list[int] | None = None
    router_position: list[int] | None = None
    ai_outborders_user: list[list[int]] | None = None
    ai_outborders: list[list[int]] | None = None
    ai_outborders_new: list[list[int]] | None = None
    ai_outborders_2d: list[list[int]] | None = None
    second_cleaning: int | None = None
    multiple_cleaning_time: int | None = None
    dos: int | None = None
    ai_furniture_warning: int | None = None
    walls_info: Any | None = None
    walls_info_new: Any | None = None
    furniture_version: int | None = None
    startup_method: str | None = None
    cleanup_method: str | None = None
    cleaned_area: int | None = None
    cleaning_time: int | None = None
    robot_status: int | None = None
    station_status: int | None = None
    completed: bool | None = None
    remaining_battery: int | None = None
    cleanset: bool = False
    docked: bool = True
    work_status: int = 0
    resources: MapRendererResources = None
    version: int = 1
