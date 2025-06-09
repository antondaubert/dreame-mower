from typing import Final
from .types import (
    DreameMowerChargingStatus,
    DreameMowerTaskStatus,
    DreameMowerState,
    DreameMowerStatus,
    DreameMowerErrorCode,
    DreameMowerRelocationStatus,
    DreameMowerCleaningMode,
    DreameMowerStreamStatus,
    DreameMowerVoiceAssistantLanguage,
    DreameMowerWiderCornerCoverage,
    DreameMowerSecondCleaning,
    DreameMowerCleaningRoute,
    DreameMowerCleanGenius,
    DreameMowerFloorMaterial,
    DreameMowerFloorMaterialDirection,
    DreameMowerSegmentVisibility,
    DreameMowerTaskType,
    DreameMowerProperty,
    DreameMowerAIProperty,
    DreameMowerStrAIProperty,
    DreameMowerAutoSwitchProperty,
    DreameMowerAction,
)


CLEANING_MODE_MOWING: Final = "sweeping"


STATE_NOT_SET: Final = "not_set"
STATE_UNKNOWN: Final = "unknown"
STATE_MOWING: Final = "mowing"
STATE_IDLE: Final = "idle"
STATE_PAUSED: Final = "paused"
STATE_RETURNING: Final = "returning"
STATE_CHARGING: Final = "charging"
STATE_ERROR: Final = "error"
STATE_BUILDING: Final = "building"
STATE_CHARGING_COMPLETED: Final = "charging_completed"
STATE_UPGRADING: Final = "upgrading"
STATE_CLEAN_SUMMON: Final = "clean_summon"
STATE_STATION_RESET: Final = "station_reset"
STATE_REMOTE_CONTROL: Final = "remote_control"
STATE_SMART_CHARGING: Final = "smart_charging"
STATE_SECOND_CLEANING: Final = "second_cleaning"
STATE_HUMAN_FOLLOWING: Final = "human_following"
STATE_SPOT_CLEANING: Final = "spot_cleaning"
STATE_WAITING_FOR_TASK: Final = "waiting_for_task"
STATE_STATION_CLEANING: Final = "station_cleaning"
STATE_SHORTCUT: Final = "shortcut"
STATE_MONITORING: Final = "monitoring"
STATE_MONITORING_PAUSED: Final = "monitoring_paused"
STATE_UNAVAILABLE: Final = "unavailable"
STATE_OFF: Final = "off"

TASK_STATUS_COMPLETED: Final = "completed"
TASK_STATUS_AUTO_CLEANING: Final = "cleaning"
TASK_STATUS_ZONE_CLEANING: Final = "zone_cleaning"
TASK_STATUS_SEGMENT_CLEANING: Final = "zone_cleaning"
TASK_STATUS_SPOT_CLEANING: Final = "spot_cleaning"
TASK_STATUS_FAST_MAPPING: Final = "fast_mapping"
TASK_STATUS_AUTO_CLEANING_PAUSE: Final = "cleaning_paused"
TASK_STATUS_SEGMENT_CLEANING_PAUSE: Final = "zone_cleaning_paused"
TASK_STATUS_ZONE_CLEANING_PAUSE: Final = "zone_cleaning_paused"
TASK_STATUS_SPOT_CLEANING_PAUSE: Final = "spot_cleaning_paused"
TASK_STATUS_MAP_CLEANING_PAUSE: Final = "map_cleaning_paused"
TASK_STATUS_DOCKING_PAUSE: Final = "docking_paused"
TASK_STATUS_CRUISING_PATH: Final = "curising_path"
TASK_STATUS_CRUISING_PATH_PAUSED: Final = "curising_path_paused"
TASK_STATUS_CRUISING_POINT: Final = "curising_point"
TASK_STATUS_CRUISING_POINT_PAUSED: Final = "curising_point_paused"
TASK_STATUS_SUMMON_CLEAN_PAUSED: Final = "summon_clean_paused"

STATUS_CLEANING: Final = "cleaning"
STATUS_FOLLOW_WALL: Final = "follow_wall_cleaning"
STATUS_CHARGING: Final = "charging"
STATUS_OTA: Final = "ota"
STATUS_FCT: Final = "fct"
STATUS_WIFI_SET: Final = "wifi_set"
STATUS_POWER_OFF: Final = "power_off"
STATUS_FACTORY: Final = "factory"
STATUS_ERROR: Final = "error"
STATUS_REMOTE_CONTROL: Final = "remote_control"
STATUS_SLEEP: Final = "sleeping"
STATUS_SELF_REPAIR: Final = "self_repair"
STATUS_FACTORY_FUNC_TEST: Final = "factory_test"
STATUS_STANDBY: Final = "standby"
STATUS_SEGMENT_CLEANING: Final = "zone_cleaning"
STATUS_ZONE_CLEANING: Final = "zone_cleaning"
STATUS_SPOT_CLEANING: Final = "spot_cleaning"
STATUS_FAST_MAPPING: Final = "fast_mapping"
STATUS_CRUISING_PATH: Final = "curising_path"
STATUS_CRUISING_POINT: Final = "curising_point"
STATUS_SUMMON_CLEAN: Final = "summon_clean"
STATUS_SHORTCUT: Final = "shortcut"
STATUS_PERSON_FOLLOW: Final = "person_follow"

RELOCATION_STATUS_LOCATED: Final = "located"
RELOCATION_STATUS_LOCATING: Final = "locating"
RELOCATION_STATUS_FAILED: Final = "failed"
RELOCATION_STATUS_SUCESS: Final = "success"

CHARGING_STATUS_CHARGING: Final = "charging"
CHARGING_STATUS_NOT_CHARGING: Final = "not_charging"
CHARGING_STATUS_RETURN_TO_CHARGE: Final = "return_to_charge"
CHARGING_STATUS_CHARGING_COMPLETED: Final = "charging_completed"

STREAM_STATUS_VIDEO: Final = "video"
STREAM_STATUS_AUDIO: Final = "audio"
STREAM_STATUS_RECORDING: Final = "recording"

VOICE_ASSISTANT_LANGUAGE_DEFAULT: Final = "default"
VOICE_ASSISTANT_LANGUAGE_ENGLISH: Final = "english"
VOICE_ASSISTANT_LANGUAGE_GERMAN: Final = "german"
VOICE_ASSISTANT_LANGUAGE_CHINESE: Final = "chinese"

WIDER_CORNER_COVERAGE_LOW_FREQUENCY: Final = "low_frequency"
WIDER_CORNER_COVERAGE_HIGH_FREQUENCY: Final = "high_frequency"

SECOND_CLEANING_IN_DEEP_MODE: Final = "in_deep_mode"
SECOND_CLEANING_IN_ALL_MODES: Final = "in_all_modes"

ROUTE_QUICK: Final = "quick"
ROUTE_STANDARD: Final = "standard"
ROUTE_INTENSIVE: Final = "intensive"
ROUTE_DEEP: Final = "deep"
ROUTE_OFF: Final = "off"

CLEANGENIUS_ROUTINE_CLEANING: Final = "routine_cleaning"
CLEANGENIUS_DEEP_CLEANING: Final = "deep_cleaning"

FLOOR_MATERIAL_NONE: Final = "none"
FLOOR_MATERIAL_TILE: Final = "tile"
FLOOR_MATERIAL_WOOD: Final = "wood"

FLOOR_MATERIAL_DIRECTION_VERTICAL: Final = "vertical"
FLOOR_MATERIAL_DIRECTION_HORIZONTAL: Final = "horizontal"

SEGMENT_VISIBILITY_VISIBLE: Final = "visible"
SEGMENT_VISIBILITY_HIDDEN: Final = "hidden"

TASK_TYPE_IDLE: Final = "idle"
TASK_TYPE_STANDARD: Final = "standard"
TASK_TYPE_STANDARD_PAUSED: Final = "standard_paused"
TASK_TYPE_CUSTOM: Final = "custom"
TASK_TYPE_CUSTOM_PAUSED: Final = "custom_paused"
TASK_TYPE_SHORTCUT: Final = "shortcut"
TASK_TYPE_SHORTCUT_PAUSED: Final = "shortcut_paused"
TASK_TYPE_SCHEDULED: Final = "scheduled"
TASK_TYPE_SCHEDULED_PAUSED: Final = "scheduled_paused"
TASK_TYPE_SMART: Final = "smart"
TASK_TYPE_SMART_PAUSED: Final = "smart_paused"
TASK_TYPE_PARTIAL: Final = "partial"
TASK_TYPE_PARTIAL_PAUSED: Final = "partial_paused"
TASK_TYPE_SUMMON: Final = "summon"
TASK_TYPE_SUMMON_PAUSED: Final = "summon_paused"

ERROR_NO_ERROR: Final = "no_error"
ERROR_DROP: Final = "drop"
ERROR_CLIFF: Final = "cliff"
ERROR_BUMPER: Final = "bumper"
ERROR_GESTURE: Final = "gesture"
ERROR_BUMPER_REPEAT: Final = "bumper_repeat"
ERROR_DROP_REPEAT: Final = "drop_repeat"
ERROR_OPTICAL_FLOW: Final = "optical_flow"
ERROR_BRUSH: Final = "brush"
ERROR_SIDE_BRUSH: Final = "side_brush"
ERROR_FAN: Final = "fan"
ERROR_LEFT_WHEEL_MOTOR: Final = "left_wheel_motor"
ERROR_RIGHT_WHEEL_MOTOR: Final = "right_wheel_motor"
ERROR_TURN_SUFFOCATE: Final = "turn_suffocate"
ERROR_FORWARD_SUFFOCATE: Final = "forward_suffocate"
ERROR_CHARGER_GET: Final = "charger_get"
ERROR_BATTERY_LOW: Final = "battery_low"
ERROR_CHARGE_FAULT: Final = "charge_fault"
ERROR_BATTERY_PERCENTAGE: Final = "battery_percentage"
ERROR_HEART: Final = "heart"
ERROR_CAMERA_OCCLUSION: Final = "camera_occlusion"
ERROR_MOVE: Final = "move"
ERROR_FLOW_SHIELDING: Final = "flow_shielding"
ERROR_INFRARED_SHIELDING: Final = "infrared_shielding"
ERROR_CHARGE_NO_ELECTRIC: Final = "charge_no_electric"
ERROR_BATTERY_FAULT: Final = "battery_fault"
ERROR_FAN_SPEED_ERROR: Final = "fan_speed_error"
ERROR_LEFTWHELL_SPEED: Final = "left_wheell_speed"
ERROR_RIGHTWHELL_SPEED: Final = "right_wheell_speed"
ERROR_BMI055_ACCE: Final = "bmi055_acce"
ERROR_BMI055_GYRO: Final = "bmi055_gyro"
ERROR_XV7001: Final = "xv7001"
ERROR_LEFT_MAGNET: Final = "left_magnet"
ERROR_RIGHT_MAGNET: Final = "right_magnet"
ERROR_FLOW_ERROR: Final = "flow_error"
ERROR_INFRARED_FAULT: Final = "infrared_fault"
ERROR_CAMERA_FAULT: Final = "camera_fault"
ERROR_STRONG_MAGNET: Final = "strong_magnet"
ERROR_RTC: Final = "rtc"
ERROR_AUTO_KEY_TRIG: Final = "auto_key_trig"
ERROR_P3V3: Final = "p3v3"
ERROR_CAMERA_IDLE: Final = "camera_idle"
ERROR_BLOCKED: Final = "blocked"
ERROR_LDS_ERROR: Final = "lds_error"
ERROR_LDS_BUMPER: Final = "lds_bumper"
ERROR_FILTER_BLOCKED: Final = "filter_blocked"
ERROR_EDGE: Final = "edge"
ERROR_LASER: Final = "laser"
ERROR_ULTRASONIC: Final = "ultrasonic"
ERROR_NO_GO_ZONE: Final = "no_go_zone"
ERROR_ROUTE: Final = "route"
ERROR_RESTRICTED: Final = "restricted"
ERROR_LOW_BATTERY_TURN_OFF: Final = "low_battery_turn_off"
ERROR_ROBOT_IN_HIDDEN_ZONE: Final = "robot_in_hidden_zone"
ERROR_STATION_DISCONNECTED: Final = "station_disconnected"
ERROR_SELF_TEST_FAILED: Final = "self_test_failed"
ERROR_RETURN_TO_CHARGE_FAILED: Final = "return_to_charge_failed"

ATTR_VALUE: Final = "value"
ATTR_CHARGING: Final = "charging"
ATTR_STARTED: Final = "started"
ATTR_PAUSED: Final = "paused"
ATTR_RUNNING: Final = "running"
ATTR_RETURNING_PAUSED: Final = "returning_paused"
ATTR_RETURNING: Final = "returning"
ATTR_MAPPING: Final = "mapping"
ATTR_MAPPING_AVAILABLE: Final = "mapping_available"
ATTR_ZONES: Final = "zones"
ATTR_CURRENT_SEGMENT: Final = "current_segment"
ATTR_SELECTED_MAP: Final = "selected_map"
ATTR_ID: Final = "id"
ATTR_NAME: Final = "name"
ATTR_ICON: Final = "icon"
ATTR_ORDER: Final = "order"
ATTR_DID: Final = "did"
ATTR_STATUS: Final = "status"
ATTR_CLEANING_MODE: Final = "cleaning_mode"
ATTR_COMPLETED: Final = "completed"
ATTR_TIMESTAMP: Final = "timestamp"
ATTR_CLEANING_TIME: Final = "cleaning_time"
ATTR_CLEANED_AREA: Final = "cleaned_area"
ATTR_CLEANING_SEQUENCE: Final = "cleaning_sequence"
ATTR_CLEANGENIUS: Final = "cleangenius_cleaning"
ATTR_MOWER_STATE: Final = "mower_state"
ATTR_DND: Final = "dnd"
ATTR_SHORTCUTS: Final = "shortcuts"
ATTR_CRUISING_TIME: Final = "cruising_time"
ATTR_CRUISING_TYPE: Final = "cruising_type"
ATTR_MAP_INDEX: Final = "map_index"
ATTR_MAP_NAME: Final = "map_name"
ATTR_CALIBRATION: Final = "calibration_points"
ATTR_SELECTED: Final = "selected"
ATTR_CLEANING_HISTORY_PICTURE: Final = "cleaning_history_picture"
ATTR_CRUISING_HISTORY_PICTURE: Final = "cruising_history_picture"
ATTR_OBSTACLE_PICTURE: Final = "obstacle_picture"
ATTR_RECOVERY_MAP_PICTURE: Final = "recovery_map_picture"
ATTR_RECOVERY_MAP_FILE: Final = "recovery_map_file"
ATTR_WIFI_MAP_PICTURE: Final = "wifi_map_picture"
ATTR_NEGLECTED_SEGMENTS: Final = "neglected_zones"
ATTR_INTERRUPT_REASON: Final = "interrupt_reason"
ATTR_CLEANUP_METHOD: Final = "cleanup_method"
ATTR_SEGMENT_CLEANING: Final = "segment_cleaning"
ATTR_ZONE_CLEANING: Final = "zone_cleaning"
ATTR_SPOT_CLEANING: Final = "spot_cleaning"
ATTR_CRUSING: Final = "cruising"
ATTR_HAS_SAVED_MAP: Final = "has_saved_map"
ATTR_HAS_TEMPORARY_MAP: Final = "has_temporary_map"
ATTR_CAPABILITIES: Final = "capabilities"

MAP_PARAMETER_NAME: Final = "name"
MAP_PARAMETER_VALUE: Final = "value"
MAP_PARAMETER_TIME: Final = "time"
MAP_PARAMETER_CODE: Final = "code"
MAP_PARAMETER_OUT: Final = "out"
MAP_PARAMETER_MAP: Final = "map"
MAP_PARAMETER_ANGLE: Final = "angle"
MAP_PARAMETER_MAPSTR: Final = "mapstr"
MAP_PARAMETER_CURR_ID: Final = "curr_id"
MAP_PARAMETER_MOWER: Final = "mower"
MAP_PARAMETER_URL: Final = "url"
MAP_PARAMETER_EXPIRES_TIME: Final = "expires_time"

MAP_REQUEST_PARAMETER_MAP_ID: Final = "map_id"
MAP_REQUEST_PARAMETER_FRAME_ID: Final = "frame_id"
MAP_REQUEST_PARAMETER_FRAME_TYPE: Final = "frame_type"
MAP_REQUEST_PARAMETER_REQ_TYPE: Final = "req_type"
MAP_REQUEST_PARAMETER_FORCE_TYPE: Final = "force_type"
MAP_REQUEST_PARAMETER_TYPE: Final = "type"
MAP_REQUEST_PARAMETER_INDEX: Final = "index"
MAP_REQUEST_PARAMETER_ZONE_ID: Final = "zoneID"

MAP_DATA_JSON_CLASS: Final = "ValetudoMap"
MAP_DATA_JSON_PARAMETER_CLASS: Final = "__class"
MAP_DATA_JSON_PARAMETER_SIZE: Final = "size"
MAP_DATA_JSON_PARAMETER_X: Final = "x"
MAP_DATA_JSON_PARAMETER_Y: Final = "y"
MAP_DATA_JSON_PARAMETER_PIXEL_SIZE: Final = "pixelSize"
MAP_DATA_JSON_PARAMETER_LAYERS: Final = "layers"
MAP_DATA_JSON_PARAMETER_ENTITIES: Final = "entities"
MAP_DATA_JSON_PARAMETER_META_DATA: Final = "metaData"
MAP_DATA_JSON_PARAMETER_VERSION: Final = "version"
MAP_DATA_JSON_PARAMETER_ROTATION: Final = "rotation"
MAP_DATA_JSON_PARAMETER_TYPE: Final = "type"
MAP_DATA_JSON_PARAMETER_POINTS: Final = "points"
MAP_DATA_JSON_PARAMETER_PIXELS: Final = "pixels"
MAP_DATA_JSON_PARAMETER_SEGMENT_ID: Final = "segmentId"
MAP_DATA_JSON_PARAMETER_ACTIVE: Final = "active"
MAP_DATA_JSON_PARAMETER_NAME: Final = "name"
MAP_DATA_JSON_PARAMETER_DIMENSIONS: Final = "dimensions"
MAP_DATA_JSON_PARAMETER_MIN: Final = "min"
MAP_DATA_JSON_PARAMETER_MAX: Final = "max"
MAP_DATA_JSON_PARAMETER_MID: Final = "mid"
MAP_DATA_JSON_PARAMETER_AVG: Final = "avg"
MAP_DATA_JSON_PARAMETER_PIXEL_COUNT: Final = "pixelCount"
MAP_DATA_JSON_PARAMETER_COMPRESSED_PIXELS: Final = "compressedPixels"
MAP_DATA_JSON_PARAMETER_ROBOT_POSITION: Final = "robot_position"
MAP_DATA_JSON_PARAMETER_CHARGER_POSITION: Final = "charger_location"
MAP_DATA_JSON_PARAMETER_NO_GO_AREA: Final = "no_go_area"
MAP_DATA_JSON_PARAMETER_ACTIVE_ZONE: Final = "active_zone"
MAP_DATA_JSON_PARAMETER_VIRTUAL_WALL: Final = "virtual_wall"
MAP_DATA_JSON_PARAMETER_PATH: Final = "path"
MAP_DATA_JSON_PARAMETER_FLOOR: Final = "floor"
MAP_DATA_JSON_PARAMETER_WALL: Final = "wall"
MAP_DATA_JSON_PARAMETER_SEGMENT: Final = "segment"

# DEVICE_KEY: Final = (
#     "H4sIAAAAAAAACj2TyZLaMBCGXyXl8xwsqW1LubGUhwmYxSEkJJUDmwEDXgYYZpLKu0dWd/v0f3K3elP7r1fHw8Nb2anTeD7NhuPQ+/zpl/cqpW+830/eJP42Opl5qaI63f5YKrYK33vyNsKXm4Jgf278t8U2nak/utPL+9t+Urb+omzM4/RRdPMgvo6n++54PW/N0kZpNEBVpIFiXTNsGLYMF4Ybw53hgRBSmKjVlQPl2nDafsBEFjC+hR1DxrAnwHBKhKwVgsJ2lNKsFD6gfAH2p0I6hz5WqkJBnmGEGpFnRGdNZx2Qo4EWqD4DOcOJ4cxwZcAZKYMlgi9Q6SWAerKK4S3g5C0cGAoESXclkNJdekUAQzHAYEEQ+PhoQIOAkNKG1BZonC1Qv6Cxf9BUr6GcRtIFI/HlwLgbRmFHVl1oq646q2zHqowS5IitW8UGGzgRROhKU7LqOjQg8QpI3Ww3XHtvaia7t/X3RfelK9vtDt3yl/n7c1HuB9nivssW2TubwW+sKvbzI9yzbrIaiPkhaa28ZLRTghpWNiduAu2Q9l8JaERYXKOrJkGRqZ9HmdQ67wedzuTCCexOWmt8KbLVi6zWu4t/ioJba6WFtFASRAh2KqjAqwgBboai/80qbzNuhlX6oLkLLblq9tW0PZFo6nqkH36QLUezL0k6CJO8rQsaazqeQKWCtZwNV+XboOeslRRg3MTDaXwcTZfJYPRxrqI0ZbNwZThwfrouvpptvZ+rXlU970QbphmtU/IHv2ZofnUHNsK//+u61l1HBQAA"
# )
# DREAME_STRINGS: Final = (
#     "H4sICAAAAAAEAGNsb3VkX3N0cmluZ3MuanNvbgBdUltv2jAU/iuoUtEmjZCEljBVPDAQgu0hK5eudJrQwXaIV18y24yyX79jm45tebDPd67f+ZyvVwnXLqGGgWSJY6S+eneV9fJ+gfdidBKb8XUll5+a4nr1A12TkLhdSjCu1pJ1s+Q2uX3fesM/11qxuxYvl62sn6R3rSUBwbq9JE3f+p5kkO56xaDY5Xm/XxT9HaHkZpBVvYIOKrjJd5Cl0EuhGmTQp1Unw6IPYDlpPc0+is2XTDzm0yOZbV7K5+n9o1zk97NmtM6mTw+qLsvJfogFafjQsA7cwaIhwTpm1pyiveOKTrQErhA0RjfMuBOaqMCcepcAV2kjh/Ny2bYE40MQor03oNzWnRBikmGVYbbeOv3MVPsf5MMNWHvUhrYPlhkFMtS0X70BhE5AiD4oh7gbxe/AwdVdHc7QDUOYxKyNzS+j/2D20nB0bHkM7rn2hmPK8w0bn1t7Lh3cMu7qkZcioqjUJULBga9kPzlhaAhu3UPu46rSMVCuxvMItCPeCnsbkPacH/DeV0tNmQjsCK5vL5RwWodo6Z+KKTrWUsIro4oLX+ovL+D5rXytVw6vGkdo419uz9wkEJ1E1vY/PInDRigqorWXYbRnyl1CC0EQ+ARt+C9wUcNV0LAT/oqxVo4hWMXh0DSCk5DY/W5DdrPFY3umo49KaKBrI6KjtDajf3u//QbhJuZXdAMAAA=="
# )
# DREAME_MODEL_CAPABILITIES: Final = (
#     "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"
# )
DEVICE_KEY: Final = "H4sIAAAAAAAACj2UzXbaQAyFX6WHdRaeP3umu0AOIQ0QcGnatKcLwBgCwYaEkKQ9fffKoyuv7mdrRqORNPrbOfZvN+f68pj3Z5Pydpx2Pn/61XnWOgmd3xedu/634S7MapMd8+LHgxGrSjoXnaVK9LICrJ8YMpKCvllMtBdKJctN46+oinxq/vjL3vaquBrVrT9VN+Zx/lZ1t67/Mp6su+PFrDU37hp1rAbqjOhCYClQCOwFTgKvAm8MKdxkrc4jmHjNqO0PPoiA/ROsBEqBNYDdGZWKHhgMX8cYLwr3Duc5vp9J8Z0mHKlJFVamGWuGlRm+Pb69w8JgW0B8wW4FdgJN8SK8CHCOTOAQbaJE2R3BRoCXWhTJ4rqkWKpSLgoB9qi0YtBwqy0Ue3WGvTrDXp09MyB5Fj1gDd/cWriynHVrA1zYwNe0LuFWsEivTeEqRbIIEGAqm9ESpJwZ6/EDibYex3skygdRePCBW4YAzr0E5APnnYB7kwDJDLhN0HATNNwEzeWzgSNwCefOJfjW3DTOYCsBH+ykzxxu5TJsRRe5LKY/GK42aUwQaVxHGteR8uWCUVjItSflmjcQz2xgB+CSBrQSKR9mVcxYsBw3KexanQDs3Go+HU3S6Dsg5j5YAw+GwyXlIAjODNwkpFzxBuJjDeiJYDOs8DiE60uKM+hB0KCyL72zmeruafH9vnvT1e2gSuMcq7fv11W9HpT3r6vyvnwXs00aq+kn20f7WnZH84GabUatVeYFxoNCAQ3fjx41xoFP+C0YaTrOUKPybKRbHEpOgO5z1H0URFWan496dPTbK3d5ebeXIGgEkbW/r8r5jT4sVvtkl7lTa8XzJ6gBGQPVlxWpbYBPNBivpDK8DD9/k3L/kcLi5cpeYzZ5LXeV3d6ICcOCSkYhv+UfiSsfhtMvo3yQjrZtyLax5uM7ezBuoae38/o86EXrQSsbYsHSSf9xOHkYDYYfT4csz8WsYmAR4jp/rL6G4riemd7hcL1SrZumMlGx3iZHgWboRyAP//4DjoPk2nEHAAA="
DREAME_STRINGS: Final = "H4sICAAAAAAEAGNsb3VkX3N0cmluZ3MuanNvbgBdUltv2jAU/iuoUtEmjZCEljBVPDAQgu0hK5eudJrQwXaIV18y24yyX79jm45tebDPd67f+ZyvVwnXLqGGgWSJY6S+eneV9fJ+gfdidBKb8XUll5+a4nr1A12TkLhdSjCu1pJ1s+Q2uX3fesM/11qxuxYvl62sn6R3rSUBwbq9JE3f+p5kkO56xaDY5Xm/XxT9HaHkZpBVvYIOKrjJd5Cl0EuhGmTQp1Unw6IPYDlpPc0+is2XTDzm0yOZbV7K5+n9o1zk97NmtM6mTw+qLsvJfogFafjQsA7cwaIhwTpm1pyiveOKTrQErhA0RjfMuBOaqMCcepcAV2kjh/Ny2bYE40MQor03oNzWnRBikmGVYbbeOv3MVPsf5MMNWHvUhrYPlhkFMtS0X70BhE5AiD4oh7gbxe/AwdVdHc7QDUOYxKyNzS+j/2D20nB0bHkM7rn2hmPK8w0bn1t7Lh3cMu7qkZcioqjUJULBga9kPzlhaAhu3UPu46rSMVCuxvMItCPeCnsbkPacH/DeV0tNmQjsCK5vL5RwWodo6Z+KKTrWUsIro4oLX+ovL+D5rXytVw6vGkdo419uz9wkEJ1E1vY/PInDRigqorWXYbRnyl1CC0EQ+ARt+C9wUcNV0LAT/oqxVo4hWMXh0DSCk5DY/W5DdrPFY3umo49KaKBrI6KjtDajf3u//QbhJuZXdAMAAA=="
DREAME_MODEL_CAPABILITIES: Final = "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"

MOVA_STRINGS: Final = "H4sIAAAAAAAAA11Sa2/aMBT9K6hS0SYtIQktYar6gYEQ3TRlLdC1nabo4jjEqx+ZbUrZr5+vY7p2+eDcc+772D9OYqZsLNQTRJaSJiZKnHzonaTDbJSjcTM58PvpaS2WX9r8dPUbua8uulwK0LZRgg7S+Dw+/9h7x741StKLHiuWvXQUJxe9JQFOB8M4Sd77omScbIb5ON9k2WiU56MNqcjZOK2HeTWu4SzbQJrAMIF6nMKoqqMUsz6BYaT3sPjM77+n/C6b78ni/rl4nF/fiZvsetFO1un84VY2RTHbXmJGgl+GlrFgdwYtAcZSvWYVgg2T1UwJYBJRq1VLtT2g7cS48iEtB1srLS6vimXfEBdxCZz3txqkLe3BQYzStNbUNKVVj1T23yDvb8GYvdJVf2eoliC6rP6R7pCvBoSonbRIDCpNXWgEO9sMlD99RfS5MGpM+YLftESCPrfMMSUL7i1T3rJU4uTd/qEBDhW5jcPiCFGZAP9pF3wVWPDZ9IkRihZnxt56oZmsVfAVq+lVQMqSo9mCBmGOSR2z9UWEqijvhiVOE/NqQNc4Cg/SUFlNlRDwMl/NuM/HP0p7vEpfADXFf+OaKe2vdkvtzE8+C3uY/4lZ13XiFEe4RnkmW9rdSnDecIIIY5Rmf8AGfVde36h7PFMlnd42WoUpoG05Iz528Mt0CW2JZ3mcTO0lV1CtNQ9MYUxavaZ//gW/B6/rrAMAAA=="
PROPERTY_TO_NAME: Final = {
    DreameMowerProperty.STATE.name: ["state", "State"],
    DreameMowerProperty.ERROR.name: ["error", "Error"],
    DreameMowerProperty.BATTERY_LEVEL.name: ["battery_level", "Battery Level"],
    DreameMowerProperty.CHARGING_STATUS.name: ["charging_status", "Charging Status"],
    DreameMowerProperty.OFF_PEAK_CHARGING.name: [
        "off_peak_charging",
        "Off-Peak Charging",
    ],
    DreameMowerProperty.STATUS.name: ["status", "Status"],
    DreameMowerProperty.CLEANING_TIME.name: ["cleaning_time", "Cleaning Time"],
    DreameMowerProperty.CLEANED_AREA.name: ["cleaned_area", "Cleaned Area"],
    DreameMowerProperty.TASK_STATUS.name: ["task_status", "Task Status"],
    DreameMowerProperty.RESUME_CLEANING.name: ["resume_cleaning", "Resume Cleaning"],
    DreameMowerProperty.REMOTE_CONTROL.name: ["remote_control", "Remote Control"],
    DreameMowerProperty.CLEANING_PAUSED.name: ["cleaning_paused", "Cleaning Paused"],
    DreameMowerProperty.FAULTS.name: ["faults", "Faults"],
    DreameMowerProperty.RELOCATION_STATUS.name: [
        "relocation_status",
        "Relocation Status",
    ],
    DreameMowerProperty.OBSTACLE_AVOIDANCE.name: [
        "obstacle_avoidance",
        "Obstacle Avoidance",
    ],
    DreameMowerProperty.AI_DETECTION.name: [
        "ai_obstacle_detection",
        "AI Obstacle Detection",
    ],
    DreameMowerProperty.CLEANING_MODE.name: ["cleaning_mode", "Cleaning Mode"],
    DreameMowerProperty.CUSTOMIZED_CLEANING.name: [
        "customized_cleaning",
        "Customized Cleaning",
    ],
    DreameMowerProperty.CHILD_LOCK.name: ["child_lock", "Child Lock"],
    DreameMowerProperty.CLEANING_CANCEL.name: ["cleaning_cancel", "Cleaning Cancel"],
    DreameMowerProperty.WARN_STATUS.name: ["warn_status", "Warn Status"],
    DreameMowerProperty.MULTI_FLOOR_MAP.name: ["multi_floor_map", "Multi Floor Map"],
    DreameMowerProperty.MAP_LIST.name: ["map_list", "Map List"],
    DreameMowerProperty.RECOVERY_MAP_LIST.name: [
        "recovery_map_list",
        "Recovery Map List",
    ],
    DreameMowerProperty.MAP_RECOVERY.name: ["map_recovery", "Map Recovery"],
    DreameMowerProperty.MAP_RECOVERY_STATUS.name: [
        "map_recovery_status",
        "Map Recovery Status",
    ],
    DreameMowerProperty.VOLUME.name: ["volume", "Volume"],
    DreameMowerProperty.VOICE_ASSISTANT.name: ["voice_assistant", "Voice Assistant"],
    DreameMowerProperty.SCHEDULE.name: ["schedule", "Schedule"],
    DreameMowerProperty.MAP_SAVING.name: [
        "map_saving",
        "Map Saving",
    ],
    DreameMowerProperty.SERIAL_NUMBER.name: ["serial_number", "Serial Number"],
    DreameMowerProperty.VOICE_PACKET_ID.name: ["voice_packet_id", "Voice Packet Id"],
    DreameMowerProperty.TIMEZONE.name: ["timezone", "Timezone"],
    DreameMowerProperty.BLADES_TIME_LEFT.name: [
        "blades_time_left",
        "Main Brush  Time Left",
    ],
    DreameMowerProperty.BLADES_LEFT.name: ["blades_left", "Main Brush Left"],
    DreameMowerProperty.SIDE_BRUSH_TIME_LEFT.name: [
        "side_brush_time_left",
        "Side Brush Time Left",
    ],
    DreameMowerProperty.SIDE_BRUSH_LEFT.name: ["side_brush_left", "Side Brush Left"],
    DreameMowerProperty.FILTER_LEFT.name: ["filter_left", "Filter Left"],
    DreameMowerProperty.FILTER_TIME_LEFT.name: [
        "filter_time_left",
        "Filter Time Left",
    ],
    DreameMowerProperty.FIRST_CLEANING_DATE.name: [
        "first_cleaning_date",
        "First Cleaning Date",
    ],
    DreameMowerProperty.TOTAL_CLEANING_TIME.name: [
        "total_cleaning_time",
        "Total Cleaning Time",
    ],
    DreameMowerProperty.CLEANING_COUNT.name: ["cleaning_count", "Cleaning Count"],
    DreameMowerProperty.TOTAL_CLEANED_AREA.name: [
        "total_cleaned_area",
        "Total Cleaned Area",
    ],
    DreameMowerProperty.TOTAL_RUNTIME.name: [
        "total_runtime",
        "Total Runtime",
    ],
    DreameMowerProperty.TOTAL_CRUISE_TIME.name: [
        "total_cruise_time",
        "Total Cruise Time",
    ],
    DreameMowerProperty.SENSOR_DIRTY_LEFT.name: [
        "sensor_dirty_left",
        "Sensor Dirty Left",
    ],
    DreameMowerProperty.SENSOR_DIRTY_TIME_LEFT.name: [
        "sensor_dirty_time_left",
        "Sensor Dirty Time Left",
    ],
    DreameMowerProperty.TANK_FILTER_LEFT.name: [
        "tank_filter_left",
        "Tank Filter Left",
    ],
    DreameMowerProperty.TANK_FILTER_TIME_LEFT.name: [
        "tank_filter_time_left",
        "Tank Filter Time Left",
    ],
    DreameMowerProperty.SILVER_ION_LEFT.name: ["silver_ion_left", "Silver-ion Left"],
    DreameMowerProperty.SILVER_ION_TIME_LEFT.name: [
        "silver_ion_time_left",
        "Silver-ion Time Left",
    ],
    DreameMowerProperty.LENSBRUSH_LEFT.name: ["lensbrush_left", "Lens brush Left"],
    DreameMowerProperty.LENSBRUSH_TIME_LEFT.name: [
        "lensbrush_time_left",
        "Lens brush Time Left",
    ],
    DreameMowerProperty.SQUEEGEE_LEFT.name: ["squeegee_left", "Squeegee Left"],
    DreameMowerProperty.SQUEEGEE_TIME_LEFT.name: [
        "squeegee_time_left",
        "Squeegee Time Left",
    ],
    DreameMowerAIProperty.AI_FURNITURE_DETECTION.name: [
        "ai_furniture_detection",
        "AI Furniture Detection",
    ],
    DreameMowerAIProperty.AI_OBSTACLE_DETECTION.name: [
        "ai_obstacle_detection",
        "AI Obstacle Detection",
    ],
    DreameMowerAIProperty.AI_OBSTACLE_PICTURE.name: [
        "ai_obstacle_picture",
        "AI Obstacle Picture",
    ],
    DreameMowerAIProperty.AI_FLUID_DETECTION.name: [
        "ai_fluid_detection",
        "AI Fluid Detection",
    ],
    DreameMowerAIProperty.AI_PET_DETECTION.name: [
        "ai_pet_detection",
        "AI Pet Detection",
    ],
    DreameMowerAIProperty.AI_OBSTACLE_IMAGE_UPLOAD.name: [
        "ai_obstacle_image_upload",
        "AI Obstacle Image Upload",
    ],
    DreameMowerAIProperty.AI_IMAGE.name: ["ai_image", "AI Image"],
    DreameMowerAIProperty.AI_PET_AVOIDANCE.name: [
        "ai_pet_avoidance",
        "AI Pet Avoidance",
    ],
    DreameMowerAIProperty.FUZZY_OBSTACLE_DETECTION.name: [
        "fuzzy_obstacle_detection",
        "Fuzzy Obstacle Detection",
    ],
    DreameMowerAIProperty.PET_PICTURE.name: ["pet_picture", "Pet Picture"],
    DreameMowerAIProperty.PET_FOCUSED_DETECTION.name: [
        "pet_focused_detection",
        "Pet Focused Detection",
    ],
    DreameMowerAIProperty.LARGE_PARTICLES_BOOST.name: [
        "large_particles_boost",
        "Large Particles Boost",
    ],
    DreameMowerStrAIProperty.AI_HUMAN_DETECTION.name: [
        "ai_human_detection",
        "AI Human Detection",
    ],
    DreameMowerAutoSwitchProperty.COLLISION_AVOIDANCE.name: [
        "collision_avoidance",
        "Collision Avoidance",
    ],
    DreameMowerAutoSwitchProperty.FILL_LIGHT.name: ["fill_light", "Fill Light"],
    DreameMowerAutoSwitchProperty.STAIN_AVOIDANCE.name: [
        "stain_avoidance",
        "Stain Avoidance",
    ],
    DreameMowerAutoSwitchProperty.CLEANGENIUS.name: [
        "cleangenius",
        "CleanGenius",
    ],
    DreameMowerAutoSwitchProperty.WIDER_CORNER_COVERAGE.name: [
        "wider_corner_coverage",
        "Wider Corner Coverage",
    ],
    DreameMowerAutoSwitchProperty.FLOOR_DIRECTION_CLEANING.name: [
        "floor_direction_cleaning",
        "Floor Direction Cleaning",
    ],
    DreameMowerAutoSwitchProperty.PET_FOCUSED_CLEANING.name: [
        "pet_focused_cleaning",
        "Pet Focused Cleaning",
    ],
}

ACTION_TO_NAME: Final = {
    DreameMowerAction.START_MOWING: ["start_mowing", "Start"],
    DreameMowerAction.PAUSE: ["pause", "Pause"],
    DreameMowerAction.DOCK: ["dock", "Charge"],
    DreameMowerAction.START_CUSTOM: ["start_custom", "Start Custom"],
    DreameMowerAction.STOP: ["stop", "Stop"],
    DreameMowerAction.CLEAR_WARNING: ["clear_warning", "Clear Warning"],
    DreameMowerAction.REQUEST_MAP: ["request_map", "Request Map"],
    DreameMowerAction.UPDATE_MAP_DATA: ["update_map_data", "Update Map Data"],
    DreameMowerAction.LOCATE: ["locate", "Locate"],
    DreameMowerAction.TEST_SOUND: ["test_sound", "Test Sound"],
    DreameMowerAction.RESET_BLADES: ["reset_blades", "Reset Main Brush"],
    DreameMowerAction.RESET_SIDE_BRUSH: ["reset_side_brush", "Reset Side Brush"],
    DreameMowerAction.RESET_FILTER: ["reset_filter", "Reset Filter"],
    DreameMowerAction.RESET_SENSOR: ["reset_sensor", "Reset Sensor"],
    DreameMowerAction.RESET_SILVER_ION: ["reset_silver_ion", "Reset Silver-ion"],
    DreameMowerAction.RESET_LENSBRUSH: ["reset_lensbrush", "Reset Lens brush"],
}

STATE_CODE_TO_STATE: Final = {
    DreameMowerState.UNKNOWN: STATE_UNKNOWN,
    DreameMowerState.MOWING: STATE_MOWING,
    DreameMowerState.IDLE: STATE_IDLE,
    DreameMowerState.PAUSED: STATE_PAUSED,
    DreameMowerState.ERROR: STATE_ERROR,
    DreameMowerState.RETURNING: STATE_RETURNING,
    DreameMowerState.CHARGING: STATE_CHARGING,
    DreameMowerState.BUILDING: STATE_BUILDING,
    DreameMowerState.CHARGING_COMPLETED: STATE_CHARGING_COMPLETED,
    DreameMowerState.UPGRADING: STATE_UPGRADING,
    DreameMowerState.CLEAN_SUMMON: STATE_CLEAN_SUMMON,
    DreameMowerState.STATION_RESET: STATE_STATION_RESET,
    DreameMowerState.REMOTE_CONTROL: STATE_REMOTE_CONTROL,
    DreameMowerState.SMART_CHARGING: STATE_SMART_CHARGING,
    DreameMowerState.SECOND_CLEANING: STATE_SECOND_CLEANING,
    DreameMowerState.HUMAN_FOLLOWING: STATE_HUMAN_FOLLOWING,
    DreameMowerState.SPOT_CLEANING: STATE_SPOT_CLEANING,
    DreameMowerState.WAITING_FOR_TASK: STATE_WAITING_FOR_TASK,
    DreameMowerState.STATION_CLEANING: STATE_STATION_CLEANING,
    DreameMowerState.SHORTCUT: STATE_SHORTCUT,
    DreameMowerState.MONITORING: STATE_MONITORING,
    DreameMowerState.MONITORING_PAUSED: STATE_MONITORING_PAUSED,
}

# Dreame Mower cleaning mode names
CLEANING_MODE_CODE_TO_NAME: Final = {
    DreameMowerCleaningMode.MOWING: CLEANING_MODE_MOWING,
}

FLOOR_MATERIAL_CODE_TO_NAME: Final = {
    DreameMowerFloorMaterial.NONE: FLOOR_MATERIAL_NONE,
    DreameMowerFloorMaterial.TILE: FLOOR_MATERIAL_TILE,
    DreameMowerFloorMaterial.WOOD: FLOOR_MATERIAL_WOOD,
}

FLOOR_MATERIAL_DIRECTION_CODE_TO_NAME: Final = {
    DreameMowerFloorMaterialDirection.VERTICAL: FLOOR_MATERIAL_DIRECTION_VERTICAL,
    DreameMowerFloorMaterialDirection.HORIZONTAL: FLOOR_MATERIAL_DIRECTION_HORIZONTAL,
}

SEGMENT_VISIBILITY_CODE_TO_NAME: Final = {
    DreameMowerSegmentVisibility.VISIBLE: SEGMENT_VISIBILITY_VISIBLE,
    DreameMowerSegmentVisibility.HIDDEN: SEGMENT_VISIBILITY_HIDDEN,
}

TASK_STATUS_CODE_TO_NAME: Final = {
    DreameMowerTaskStatus.UNKNOWN: STATE_UNKNOWN,
    DreameMowerTaskStatus.COMPLETED: TASK_STATUS_COMPLETED,
    DreameMowerTaskStatus.AUTO_CLEANING: TASK_STATUS_AUTO_CLEANING,
    DreameMowerTaskStatus.ZONE_CLEANING: TASK_STATUS_ZONE_CLEANING,
    DreameMowerTaskStatus.SEGMENT_CLEANING: TASK_STATUS_SEGMENT_CLEANING,
    DreameMowerTaskStatus.SPOT_CLEANING: TASK_STATUS_SPOT_CLEANING,
    DreameMowerTaskStatus.FAST_MAPPING: TASK_STATUS_FAST_MAPPING,
    DreameMowerTaskStatus.AUTO_CLEANING_PAUSED: TASK_STATUS_AUTO_CLEANING_PAUSE,
    DreameMowerTaskStatus.SEGMENT_CLEANING_PAUSED: TASK_STATUS_SEGMENT_CLEANING_PAUSE,
    DreameMowerTaskStatus.ZONE_CLEANING_PAUSED: TASK_STATUS_ZONE_CLEANING_PAUSE,
    DreameMowerTaskStatus.SPOT_CLEANING_PAUSED: TASK_STATUS_SPOT_CLEANING_PAUSE,
    DreameMowerTaskStatus.MAP_CLEANING_PAUSED: TASK_STATUS_MAP_CLEANING_PAUSE,
    DreameMowerTaskStatus.DOCKING_PAUSED: TASK_STATUS_DOCKING_PAUSE,
    DreameMowerTaskStatus.AUTO_DOCKING_PAUSED: TASK_STATUS_DOCKING_PAUSE,
    DreameMowerTaskStatus.ZONE_DOCKING_PAUSED: TASK_STATUS_DOCKING_PAUSE,
    DreameMowerTaskStatus.SEGMENT_DOCKING_PAUSED: TASK_STATUS_DOCKING_PAUSE,
    DreameMowerTaskStatus.CRUISING_PATH: TASK_STATUS_CRUISING_PATH,
    DreameMowerTaskStatus.CRUISING_PATH_PAUSED: TASK_STATUS_CRUISING_PATH_PAUSED,
    DreameMowerTaskStatus.CRUISING_POINT: TASK_STATUS_CRUISING_POINT,
    DreameMowerTaskStatus.CRUISING_POINT_PAUSED: TASK_STATUS_CRUISING_POINT_PAUSED,
    DreameMowerTaskStatus.SUMMON_CLEAN_PAUSED: TASK_STATUS_SUMMON_CLEAN_PAUSED,
}

STATUS_CODE_TO_NAME: Final = {
    DreameMowerStatus.UNKNOWN: STATE_UNKNOWN,
    DreameMowerStatus.IDLE: STATE_IDLE,
    DreameMowerStatus.PAUSED: STATE_PAUSED,
    DreameMowerStatus.CLEANING: STATUS_CLEANING,
    DreameMowerStatus.BACK_HOME: STATE_RETURNING,
    DreameMowerStatus.PART_CLEANING: STATUS_SPOT_CLEANING,
    DreameMowerStatus.FOLLOW_WALL: STATUS_FOLLOW_WALL,
    DreameMowerStatus.CHARGING: STATUS_CHARGING,
    DreameMowerStatus.OTA: STATUS_OTA,
    DreameMowerStatus.FCT: STATUS_FCT,
    DreameMowerStatus.WIFI_SET: STATUS_WIFI_SET,
    DreameMowerStatus.POWER_OFF: STATUS_POWER_OFF,
    DreameMowerStatus.FACTORY: STATUS_FACTORY,
    DreameMowerStatus.ERROR: STATUS_ERROR,
    DreameMowerStatus.REMOTE_CONTROL: STATUS_REMOTE_CONTROL,
    DreameMowerStatus.SLEEPING: STATUS_SLEEP,
    DreameMowerStatus.SELF_REPAIR: STATUS_SELF_REPAIR,
    DreameMowerStatus.FACTORY_FUNCION_TEST: STATUS_FACTORY_FUNC_TEST,
    DreameMowerStatus.STANDBY: STATUS_STANDBY,
    DreameMowerStatus.SEGMENT_CLEANING: STATUS_SEGMENT_CLEANING,
    DreameMowerStatus.ZONE_CLEANING: STATUS_ZONE_CLEANING,
    DreameMowerStatus.SPOT_CLEANING: STATUS_SPOT_CLEANING,
    DreameMowerStatus.FAST_MAPPING: STATUS_FAST_MAPPING,
    DreameMowerStatus.CRUISING_PATH: STATUS_CRUISING_PATH,
    DreameMowerStatus.CRUISING_POINT: STATUS_CRUISING_POINT,
    DreameMowerStatus.SUMMON_CLEAN: STATUS_SUMMON_CLEAN,
    DreameMowerStatus.SHORTCUT: STATUS_SHORTCUT,
    DreameMowerStatus.PERSON_FOLLOW: STATUS_PERSON_FOLLOW,
}

RELOCATION_STATUS_CODE_TO_NAME: Final = {
    DreameMowerRelocationStatus.UNKNOWN: STATE_UNKNOWN,
    DreameMowerRelocationStatus.LOCATED: RELOCATION_STATUS_LOCATED,
    DreameMowerRelocationStatus.LOCATING: RELOCATION_STATUS_LOCATING,
    DreameMowerRelocationStatus.FAILED: RELOCATION_STATUS_FAILED,
    DreameMowerRelocationStatus.SUCCESS: RELOCATION_STATUS_SUCESS,
}

CHARGING_STATUS_CODE_TO_NAME: Final = {
    DreameMowerChargingStatus.UNKNOWN: STATE_UNKNOWN,
    DreameMowerChargingStatus.CHARGING: CHARGING_STATUS_CHARGING,
    DreameMowerChargingStatus.NOT_CHARGING: CHARGING_STATUS_NOT_CHARGING,
    DreameMowerChargingStatus.CHARGING_COMPLETED: CHARGING_STATUS_CHARGING_COMPLETED,
    DreameMowerChargingStatus.RETURN_TO_CHARGE: CHARGING_STATUS_RETURN_TO_CHARGE,
}

ERROR_CODE_TO_ERROR_NAME: Final = {
    DreameMowerErrorCode.UNKNOWN: STATE_UNKNOWN,
    DreameMowerErrorCode.NO_ERROR: ERROR_NO_ERROR,
    DreameMowerErrorCode.DROP: ERROR_DROP,
    DreameMowerErrorCode.CLIFF: ERROR_CLIFF,
    DreameMowerErrorCode.BUMPER: ERROR_BUMPER,
    DreameMowerErrorCode.GESTURE: ERROR_GESTURE,
    DreameMowerErrorCode.BUMPER_REPEAT: ERROR_BUMPER_REPEAT,
    DreameMowerErrorCode.DROP_REPEAT: ERROR_DROP_REPEAT,
    DreameMowerErrorCode.OPTICAL_FLOW: ERROR_OPTICAL_FLOW,
    DreameMowerErrorCode.BRUSH: ERROR_BRUSH,
    DreameMowerErrorCode.SIDE_BRUSH: ERROR_SIDE_BRUSH,
    DreameMowerErrorCode.FAN: ERROR_FAN,
    DreameMowerErrorCode.LEFT_WHEEL_MOTOR: ERROR_LEFT_WHEEL_MOTOR,
    DreameMowerErrorCode.RIGHT_WHEEL_MOTOR: ERROR_RIGHT_WHEEL_MOTOR,
    DreameMowerErrorCode.TURN_SUFFOCATE: ERROR_TURN_SUFFOCATE,
    DreameMowerErrorCode.FORWARD_SUFFOCATE: ERROR_FORWARD_SUFFOCATE,
    DreameMowerErrorCode.CHARGER_GET: ERROR_CHARGER_GET,
    DreameMowerErrorCode.BATTERY_LOW: ERROR_BATTERY_LOW,
    DreameMowerErrorCode.CHARGE_FAULT: ERROR_CHARGE_FAULT,
    DreameMowerErrorCode.BATTERY_PERCENTAGE: ERROR_BATTERY_PERCENTAGE,
    DreameMowerErrorCode.HEART: ERROR_HEART,
    DreameMowerErrorCode.CAMERA_OCCLUSION: ERROR_CAMERA_OCCLUSION,
    DreameMowerErrorCode.MOVE: ERROR_MOVE,
    DreameMowerErrorCode.FLOW_SHIELDING: ERROR_FLOW_SHIELDING,
    DreameMowerErrorCode.INFRARED_SHIELDING: ERROR_INFRARED_SHIELDING,
    DreameMowerErrorCode.CHARGE_NO_ELECTRIC: ERROR_CHARGE_NO_ELECTRIC,
    DreameMowerErrorCode.BATTERY_FAULT: ERROR_BATTERY_FAULT,
    DreameMowerErrorCode.FAN_SPEED_ERROR: ERROR_FAN_SPEED_ERROR,
    DreameMowerErrorCode.LEFTWHELL_SPEED: ERROR_LEFTWHELL_SPEED,
    DreameMowerErrorCode.RIGHTWHELL_SPEED: ERROR_RIGHTWHELL_SPEED,
    DreameMowerErrorCode.BMI055_ACCE: ERROR_BMI055_ACCE,
    DreameMowerErrorCode.BMI055_GYRO: ERROR_BMI055_GYRO,
    DreameMowerErrorCode.XV7001: ERROR_XV7001,
    DreameMowerErrorCode.LEFT_MAGNET: ERROR_LEFT_MAGNET,
    DreameMowerErrorCode.RIGHT_MAGNET: ERROR_RIGHT_MAGNET,
    DreameMowerErrorCode.FLOW_ERROR: ERROR_FLOW_ERROR,
    DreameMowerErrorCode.INFRARED_FAULT: ERROR_INFRARED_FAULT,
    DreameMowerErrorCode.CAMERA_FAULT: ERROR_CAMERA_FAULT,
    DreameMowerErrorCode.STRONG_MAGNET: ERROR_STRONG_MAGNET,
    DreameMowerErrorCode.RTC: ERROR_RTC,
    DreameMowerErrorCode.AUTO_KEY_TRIG: ERROR_AUTO_KEY_TRIG,
    DreameMowerErrorCode.P3V3: ERROR_P3V3,
    DreameMowerErrorCode.CAMERA_IDLE: ERROR_CAMERA_IDLE,
    DreameMowerErrorCode.BLOCKED: ERROR_BLOCKED,
    DreameMowerErrorCode.LDS_ERROR: ERROR_LDS_ERROR,
    DreameMowerErrorCode.LDS_BUMPER: ERROR_LDS_BUMPER,
    DreameMowerErrorCode.FILTER_BLOCKED: ERROR_FILTER_BLOCKED,
    DreameMowerErrorCode.EDGE: ERROR_EDGE,
    DreameMowerErrorCode.LASER: ERROR_LASER,
    DreameMowerErrorCode.EDGE_2: ERROR_EDGE,
    DreameMowerErrorCode.ULTRASONIC: ERROR_ULTRASONIC,
    DreameMowerErrorCode.NO_GO_ZONE: ERROR_NO_GO_ZONE,
    DreameMowerErrorCode.ROUTE: ERROR_ROUTE,
    DreameMowerErrorCode.ROUTE_2: ERROR_ROUTE,
    DreameMowerErrorCode.BLOCKED_2: ERROR_BLOCKED,
    DreameMowerErrorCode.BLOCKED_3: ERROR_BLOCKED,
    DreameMowerErrorCode.RESTRICTED: ERROR_RESTRICTED,
    DreameMowerErrorCode.RESTRICTED_2: ERROR_RESTRICTED,
    DreameMowerErrorCode.RESTRICTED_3: ERROR_RESTRICTED,
    DreameMowerErrorCode.LOW_BATTERY_TURN_OFF: ERROR_LOW_BATTERY_TURN_OFF,
    DreameMowerErrorCode.ROBOT_IN_HIDDEN_ZONE: ERROR_ROBOT_IN_HIDDEN_ZONE,
    DreameMowerErrorCode.STATION_DISCONNECTED: ERROR_STATION_DISCONNECTED,
    DreameMowerErrorCode.SELF_TEST_FAILED: ERROR_SELF_TEST_FAILED,
    DreameMowerErrorCode.UNKNOWN_WARNING_2: STATE_UNKNOWN,
    DreameMowerErrorCode.RETURN_TO_CHARGE_FAILED: ERROR_RETURN_TO_CHARGE_FAILED,
}

STREAM_STATUS_TO_NAME: Final = {
    DreameMowerStreamStatus.UNKNOWN: STATE_UNKNOWN,
    DreameMowerStreamStatus.IDLE: STATE_IDLE,
    DreameMowerStreamStatus.VIDEO: STREAM_STATUS_VIDEO,
    DreameMowerStreamStatus.AUDIO: STREAM_STATUS_AUDIO,
    DreameMowerStreamStatus.RECORDING: STREAM_STATUS_RECORDING,
}

VOICE_ASSISTANT_LANGUAGE_TO_NAME: Final = {
    DreameMowerVoiceAssistantLanguage.DEFAULT: VOICE_ASSISTANT_LANGUAGE_DEFAULT,
    DreameMowerVoiceAssistantLanguage.ENGLISH: VOICE_ASSISTANT_LANGUAGE_ENGLISH,
    DreameMowerVoiceAssistantLanguage.GERMAN: VOICE_ASSISTANT_LANGUAGE_GERMAN,
    DreameMowerVoiceAssistantLanguage.CHINESE: VOICE_ASSISTANT_LANGUAGE_CHINESE,
}

WIDER_CORNER_COVERAGE_TO_NAME: Final = {
    DreameMowerWiderCornerCoverage.OFF: STATE_OFF,
    DreameMowerWiderCornerCoverage.LOW_FREQUENCY: WIDER_CORNER_COVERAGE_LOW_FREQUENCY,
    DreameMowerWiderCornerCoverage.HIGH_FREQUENCY: WIDER_CORNER_COVERAGE_HIGH_FREQUENCY,
}

SECOND_CLEANING_TO_NAME: Final = {
    DreameMowerSecondCleaning.OFF: STATE_OFF,
    DreameMowerSecondCleaning.IN_DEEP_MODE: SECOND_CLEANING_IN_DEEP_MODE,
    DreameMowerSecondCleaning.IN_ALL_MODES: SECOND_CLEANING_IN_ALL_MODES,
}

CLEANING_ROUTE_TO_NAME: Final = {
    DreameMowerCleaningRoute.QUICK: ROUTE_QUICK,
    DreameMowerCleaningRoute.STANDARD: ROUTE_STANDARD,
    DreameMowerCleaningRoute.INTENSIVE: ROUTE_INTENSIVE,
    DreameMowerCleaningRoute.DEEP: ROUTE_DEEP,
}

CLEANGENIUS_TO_NAME = {
    DreameMowerCleanGenius.OFF: STATE_OFF,
    DreameMowerCleanGenius.ROUTINE_CLEANING: CLEANGENIUS_ROUTINE_CLEANING,
    DreameMowerCleanGenius.DEEP_CLEANING: CLEANGENIUS_DEEP_CLEANING,
}

TASK_TYPE_TO_NAME: Final = {
    DreameMowerTaskType.UNKNOWN: STATE_UNKNOWN,
    DreameMowerTaskType.IDLE: TASK_TYPE_IDLE,
    DreameMowerTaskType.STANDARD: TASK_TYPE_STANDARD,
    DreameMowerTaskType.STANDARD_PAUSED: TASK_TYPE_STANDARD_PAUSED,
    DreameMowerTaskType.CUSTOM: TASK_TYPE_CUSTOM,
    DreameMowerTaskType.CUSTOM_PAUSED: TASK_TYPE_CUSTOM_PAUSED,
    DreameMowerTaskType.SHORTCUT: TASK_TYPE_SHORTCUT,
    DreameMowerTaskType.SHORTCUT_PAUSED: TASK_TYPE_SHORTCUT_PAUSED,
    DreameMowerTaskType.SCHEDULED: TASK_TYPE_SCHEDULED,
    DreameMowerTaskType.SCHEDULED_PAUSED: TASK_TYPE_SCHEDULED_PAUSED,
    DreameMowerTaskType.SMART: TASK_TYPE_SMART,
    DreameMowerTaskType.SMART_PAUSED: TASK_TYPE_SMART_PAUSED,
    DreameMowerTaskType.PARTIAL: TASK_TYPE_PARTIAL,
    DreameMowerTaskType.PARTIAL_PAUSED: TASK_TYPE_PARTIAL_PAUSED,
    DreameMowerTaskType.SUMMON: TASK_TYPE_SUMMON,
    DreameMowerTaskType.SUMMON_PAUSED: TASK_TYPE_SUMMON_PAUSED,
}

ERROR_CODE_TO_IMAGE_INDEX: Final = {
    DreameMowerErrorCode.BUMPER: 1,
    DreameMowerErrorCode.BUMPER_REPEAT: 1,
    DreameMowerErrorCode.DROP: 2,
    DreameMowerErrorCode.DROP_REPEAT: 2,
    DreameMowerErrorCode.CLIFF: 3,
    DreameMowerErrorCode.GESTURE: 15,
    DreameMowerErrorCode.BRUSH: 4,
    DreameMowerErrorCode.SIDE_BRUSH: 5,
    DreameMowerErrorCode.LEFT_WHEEL_MOTOR: 6,
    DreameMowerErrorCode.RIGHT_WHEEL_MOTOR: 6,
    DreameMowerErrorCode.LEFTWHELL_SPEED: 6,
    DreameMowerErrorCode.RIGHTWHELL_SPEED: 6,
    DreameMowerErrorCode.TURN_SUFFOCATE: 7,
    DreameMowerErrorCode.FORWARD_SUFFOCATE: 7,
    DreameMowerErrorCode.FILTER_BLOCKED: 9,
    DreameMowerErrorCode.CHARGE_FAULT: 12,
    DreameMowerErrorCode.CHARGE_NO_ELECTRIC: 16,
    DreameMowerErrorCode.BATTERY_LOW: 20,
    DreameMowerErrorCode.BATTERY_FAULT: 29,
    DreameMowerErrorCode.INFRARED_FAULT: 39,
    DreameMowerErrorCode.LDS_ERROR: 48,
    DreameMowerErrorCode.LDS_BUMPER: 49,
    DreameMowerErrorCode.EDGE: 54,
    DreameMowerErrorCode.EDGE_2: 54,
    DreameMowerErrorCode.ULTRASONIC: 58,
    DreameMowerErrorCode.ROUTE: 61,
    DreameMowerErrorCode.ROUTE_2: 62,
    DreameMowerErrorCode.BLOCKED: 63,
    DreameMowerErrorCode.BLOCKED_2: 63,
    DreameMowerErrorCode.BLOCKED_3: 64,
    DreameMowerErrorCode.RESTRICTED: 65,
    DreameMowerErrorCode.RESTRICTED_2: 65,
    DreameMowerErrorCode.RESTRICTED_3: 65,
    DreameMowerErrorCode.STATION_DISCONNECTED: 117,
    DreameMowerErrorCode.SELF_TEST_FAILED: 999,
    DreameMowerErrorCode.RETURN_TO_CHARGE_FAILED: 1000,
}

# Dreame Mower error descriptions
ERROR_CODE_TO_ERROR_DESCRIPTION: Final = {
    DreameMowerErrorCode.NO_ERROR: ["No error", ""],
    DreameMowerErrorCode.DROP: [
        "Wheels are suspended",
        "Please reposition the robot and restart.",
    ],
    DreameMowerErrorCode.CLIFF: [
        "Cliff sensor error",
        "Please wipe the cliff sensor and start the cleanup away from the stairs.",
    ],
    DreameMowerErrorCode.BUMPER: [
        "Collision sensor is stuck",
        "Please clean and gently tap the collision sensor.",
    ],
    DreameMowerErrorCode.GESTURE: [
        "Robot is tilted",
        "Please move the robot to a level surface and start again.",
    ],
    DreameMowerErrorCode.BUMPER_REPEAT: [
        "Collision sensor is stuck",
        "Please clean and gently tap the collision sensor.",
    ],
    DreameMowerErrorCode.DROP_REPEAT: [
        "Wheels are suspended",
        "Please reposition the robot and restart.",
    ],
    DreameMowerErrorCode.OPTICAL_FLOW: [
        "Optical flow sensor error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.BRUSH: [
        "The main brush wrapped",
        "Please remove the main brush and clean its bristles and bearings.",
    ],
    DreameMowerErrorCode.SIDE_BRUSH: [
        "The side brush wrapped",
        "Please remove and clean the side brush.",
    ],
    DreameMowerErrorCode.FAN: [
        "The filter not dry or blocked",
        "Please check whether the filter has dried or needs to be cleaned.",
    ],
    DreameMowerErrorCode.LEFT_WHEEL_MOTOR: [
        "The robot is stuck, or its left wheel may be blocked by foreign objects",
        "Check whether there is any object stuck in the main wheels and start the robot in a new position.",
    ],
    DreameMowerErrorCode.RIGHT_WHEEL_MOTOR: [
        "The robot is stuck, or its right wheel may be blocked by foreign objects",
        "Check whether there is any object stuck in the main wheels and start the robot in a new position.",
    ],
    DreameMowerErrorCode.TURN_SUFFOCATE: [
        "The robot is stuck, or cannot turn",
        "The robot may be blocked or stuck.",
    ],
    DreameMowerErrorCode.FORWARD_SUFFOCATE: [
        "The robot is stuck, or cannot go forward",
        "The robot may be blocked or stuck.",
    ],
    DreameMowerErrorCode.CHARGER_GET: [
        "Cannot find base",
        "Please check whether the power cord is plugged in correctly.",
    ],
    DreameMowerErrorCode.BATTERY_LOW: [
        "Low battery",
        "Battery level is too low. Please charge.",
    ],
    DreameMowerErrorCode.CHARGE_FAULT: [
        "Charging error",
        "Please use a dry cloth to wipe charging contacts of the robot and auto-empty base.",
    ],
    DreameMowerErrorCode.BATTERY_PERCENTAGE: ["", ""],
    DreameMowerErrorCode.HEART: [
        "Internal error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.CAMERA_OCCLUSION: [
        "Visual positioning sensor error",
        "Please clean the visual positioning sensor.",
    ],
    DreameMowerErrorCode.MOVE: [
        "Move sensor error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.FLOW_SHIELDING: [
        "Optical sensor error",
        "Please wipe the optical sensor clean and restart.",
    ],
    DreameMowerErrorCode.INFRARED_SHIELDING: [
        "Infrared shielding error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.CHARGE_NO_ELECTRIC: [
        "The charging dock is not powered on",
        "The charging dock is not powered on. Please check whether the power cord is plugged in correctly.",
    ],
    DreameMowerErrorCode.BATTERY_FAULT: [
        "Battery temperature error",
        "Please wait until the battery temperature returns to normal.",
    ],
    DreameMowerErrorCode.FAN_SPEED_ERROR: [
        "Fan speed sensor error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.LEFTWHELL_SPEED: [
        "Left wheel may be blocked by foreign objects",
        "Check whether there is any object stuck in the main wheels and start the robot in a new position.",
    ],
    DreameMowerErrorCode.RIGHTWHELL_SPEED: [
        "Right wheel may be blocked by foreign objects",
        "Check whether there is any object stuck in the main wheels and start the robot in a new position.",
    ],
    DreameMowerErrorCode.BMI055_ACCE: [
        "Accelerometer error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.BMI055_GYRO: [
        "Gyro error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.XV7001: [
        "Gyro error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.LEFT_MAGNET: [
        "Left magnet sensor error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.RIGHT_MAGNET: [
        "Right magnet sensor error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.FLOW_ERROR: [
        "Flow sensor error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.INFRARED_FAULT: [
        "Infrared error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.CAMERA_FAULT: [
        "Camera error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.STRONG_MAGNET: [
        "Strong magnetic field detected",
        "Strong magnetic field detected. Please start away from the virtual wall.",
    ],
    DreameMowerErrorCode.RTC: ["RTC error", "Please try to restart the mower-mop."],
    DreameMowerErrorCode.AUTO_KEY_TRIG: [
        "Internal error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.P3V3: [
        "Internal error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.CAMERA_IDLE: [
        "Internal error",
        "Please try to restart the mower-mop.",
    ],
    DreameMowerErrorCode.BLOCKED: [
        "The robot may be blocked or stuck.",
        "Cleanup route is blocked, returning to the dock.",
    ],
    DreameMowerErrorCode.LDS_ERROR: [
        "Laser distance sensor error",
        "Please check whether the laser distance sensor has any jammed items",
    ],
    DreameMowerErrorCode.LDS_BUMPER: [
        "Laser distance sensor bumper error",
        "Please check whether the laser distance sensor bumper is jammed",
    ],
    DreameMowerErrorCode.FILTER_BLOCKED: [
        "The filter not dry or blocked",
        "Please check whether the filter has dried or needs to be cleaned",
    ],
    DreameMowerErrorCode.EDGE: [
        "Edge sensor error",
        "Edge sensor error. Please check and clean it.",
    ],
    DreameMowerErrorCode.LASER: [
        "The 3D obstacle avoidance sensor is malfunctioning.",
        "Please try to clean the 3D obstacle avoidance sensor.",
    ],
    DreameMowerErrorCode.EDGE_2: [
        "Edge sensor error",
        "Edge sensor error. Please check and clean it.",
    ],
    DreameMowerErrorCode.ULTRASONIC: [
        "The ultrasonic sensor is malfunctioning.",
        "Please restart the robot and try it again.",
    ],
    DreameMowerErrorCode.NO_GO_ZONE: [
        "No-Go zone or virtual wall detected.",
        "Please move the robot away from the area and restart.",
    ],
    DreameMowerErrorCode.ROUTE: [
        "Unable to reach the specified area.",
        "Please ensure that all doors in the home are open and clear any obstacles along the path.",
    ],
    DreameMowerErrorCode.ROUTE_2: [
        "Unable to reach the specified area.",
        "Please try to delete the restricted area in the path.",
    ],
    DreameMowerErrorCode.BLOCKED_2: [
        "Cleanup route is blocked.",
        "Please ensure that all doors in the home are open and clear any obstacles around the mower-mop.",
    ],
    DreameMowerErrorCode.BLOCKED_3: [
        "Cleanup route is blocked.",
        "Please try to delete the restricted area or move the mower-mop out of this area.",
    ],
    DreameMowerErrorCode.RESTRICTED: [
        "Detected that the mower-mop is in a restricted area.",
        "Please move the mower-mop out of this area.",
    ],
    DreameMowerErrorCode.RESTRICTED_2: [
        "Detected that the mower-mop is in a restricted area.",
        "Please move the mower-mop out of this area.",
    ],
    DreameMowerErrorCode.RESTRICTED_3: [
        "Detected that the mower-mop is in a restricted area.",
        "Please move the mower-mop out of this area.",
    ],
    DreameMowerErrorCode.LOW_BATTERY_TURN_OFF: [
        "Low battery. Robot will shut down soon.",
        "",
    ],
    DreameMowerErrorCode.ROBOT_IN_HIDDEN_ZONE: [
        "Hidden area. Please move the robot to the appropriate area and retry.",
        "The area has been hidden. To reuse it, please go to the specific map and click the gray area to manually recover the hidden area.",
    ],
    DreameMowerErrorCode.STATION_DISCONNECTED: [
        "Base station not powered on.",
        "Please check whether the power is off or the power switch is on in your home, and re-plug both ends of the base station power supply.",
    ],
    DreameMowerErrorCode.RETURN_TO_CHARGE_FAILED: [
        "Failed to return to charge.",
        "Please check the base station.\n1. Check if the ramp extension plate is installed down to the base station;\n2. Check if the base station is powered on;\n3. Make sure there is no obstacle in front of the base station.",
    ],
}


CONSUMABLE_TO_LIFE_WARNING_DESCRIPTION: Final = {
    DreameMowerProperty.BLADES_LEFT: [
        [
            "Main brush must be replaced",
            "The blades are worn out. Please replace it in time and reset the counter.",
        ],
        [
            "Main brush needs to be replaced soon",
            "The blades are nearly worn out. Please replace it in time.",
        ],
    ],
    DreameMowerProperty.SIDE_BRUSH_LEFT: [
        [
            "Side brush must be replaced",
            "The side brush is worn out. Please replace it and reset the counter.",
        ],
        [
            "Side brush needs to be replaced soon",
            "The side brush is nearly worn out. Please replace it as soon as possible.",
        ],
    ],
    DreameMowerProperty.FILTER_LEFT: [
        [
            "Filter must be replaced",
            "The filter is worn out. Please replace it in time and reset the counter.",
        ],
        [
            "Filter needs to be replaced soon",
            "The filter is nearly worn out. Please replace it in time.",
        ],
    ],
    DreameMowerProperty.SENSOR_DIRTY_LEFT: [
        ["Sensors must be cleaned", "Please clean the sensors and reset the counter"]
    ],
    DreameMowerProperty.TANK_FILTER_LEFT: [
        [
            "Tank filter must be replaced",
            "The tank filter is worn out. Please replace it in time and reset the counter.",
        ],
        [
            "Tank filter needs to be replaced soon",
            "The tank filter is nearly worn out. Please replace it in time.",
        ],
    ],
    DreameMowerProperty.SILVER_ION_LEFT: [
        [
            "Silver Ion Sterilizer Deteriorated",
            "Please replace the silver ion sterilizer and reset the counter.",
        ],
        [
            "Silver Ion Sterilizer Near to Deterioration",
            "Please replace the silver ion sterilizer timely.",
        ],
    ],
    DreameMowerProperty.LENSBRUSH_LEFT: [
        [
            "The lensbrush is used up",
            "Please replace the lensbrush cartridge it and reset the counter.",
        ],
        [
            "The lensbrush is about to be used up",
            "The lensbrush is about to be used up, please replace it in time.",
        ],
    ],
    DreameMowerProperty.SQUEEGEE_LEFT: [
        ["Squeegee Worn Out", "Please replace the squeegee and reset the counter."],
        ["Squeegee Nearly Worn Out", "Please replace the squeegee timely."],
    ],
}
