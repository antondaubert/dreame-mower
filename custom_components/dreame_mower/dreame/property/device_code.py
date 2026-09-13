"""Device code handling for Dreame Mower Implementation.

This module provides device code definitions, registry management, and parsing logic
for property siid:2, piid:2 (device codes). It supports both base device codes and
model-specific extensions.
"""

from __future__ import annotations

import logging
from typing import Dict, Any
from enum import IntEnum
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

# Notification property name constants
DEVICE_CODE_PROPERTY_NAME = "device_code"
DEVICE_CODE_ERROR_PROPERTY_NAME = "device_code_error"
DEVICE_CODE_WARNING_PROPERTY_NAME = "device_code_warning"
DEVICE_CODE_INFO_PROPERTY_NAME = "device_code_info"
DEVICE_CODE_NAME_PROPERTY_NAME = "device_code_name"
DEVICE_CODE_DESCRIPTION_PROPERTY_NAME = "device_code_description"
DEVICE_CODE_IS_ERROR_PROPERTY_NAME = "device_code_is_error"
DEVICE_CODE_IS_WARNING_PROPERTY_NAME = "device_code_is_warning"

# Notification data field constants
NOTIFICATION_CODE_FIELD = "code"
NOTIFICATION_NAME_FIELD = "name"
NOTIFICATION_DESCRIPTION_FIELD = "description"
NOTIFICATION_TIMESTAMP_FIELD = "timestamp"


class DeviceCodeType(IntEnum):
    """Device code types for categorization."""
    INFO = 0      # Informational status codes
    WARNING = 1   # Warning codes that require attention but not critical
    ERROR = 2     # Error/fault codes that are critical


class DeviceCodeDefinition:
    """Device code definition with value, name, description, and type."""
    
    def __init__(self, code: int, name: str, description: str, code_type: DeviceCodeType) -> None:
        """Initialize device code definition."""
        self.code = code
        self.name = name
        self.description = description
        self.code_type = code_type
    
    def is_error(self) -> bool:
        """Check if this device code represents an error."""
        return self.code_type == DeviceCodeType.ERROR
    
    def is_warning(self) -> bool:
        """Check if this device code represents a warning."""
        return self.code_type == DeviceCodeType.WARNING
    
    def is_info(self) -> bool:
        """Check if this device code represents informational status."""
        return self.code_type == DeviceCodeType.INFO


class DeviceCodeRegistry:
    """Registry for device codes with support for model-specific extensions."""
    
    def __init__(self, base_codes: Dict[int, DeviceCodeDefinition]) -> None:
        """Initialize registry with base device codes."""
        self._codes = base_codes.copy()
    
    def extend(self, additional_codes: Dict[int, DeviceCodeDefinition]) -> 'DeviceCodeRegistry':
        """Create a new registry extending current codes with additional ones.
        
        Args:
            additional_codes: Additional codes to merge (will override existing)
            
        Returns:
            New DeviceCodeRegistry instance with merged codes
        """
        merged_codes = self._codes.copy()
        merged_codes.update(additional_codes)
        return DeviceCodeRegistry(merged_codes)
    
    def get_code(self, code: int) -> DeviceCodeDefinition | None:
        """Get device code definition by code value."""
        return self._codes.get(code)
    
    def get_name(self, code: int) -> str:
        """Get device code name by code value, with fallback."""
        definition = self._codes.get(code)
        return definition.name if definition else f"Unknown Code {code}"
    
    def get_description(self, code: int) -> str:
        """Get device code description by code value, with fallback."""
        definition = self._codes.get(code)
        return definition.description if definition else f"Unknown device code: {code}"
    
    def is_error(self, code: int) -> bool:
        """Check if device code represents an error."""
        definition = self._codes.get(code)
        return definition.is_error() if definition else False
    
    def is_warning(self, code: int) -> bool:
        """Check if device code represents a warning."""
        definition = self._codes.get(code)
        return definition.is_warning() if definition else False
    
    def is_info(self, code: int) -> bool:
        """Check if device code represents informational status."""
        definition = self._codes.get(code)
        return definition.is_info() if definition else False
    
    def get_mapping(self) -> Dict[int, str]:
        """Get simple code-to-name mapping dictionary for compatibility."""
        return {code: definition.name for code, definition in self._codes.items()}


class DeviceCodeHandler:
    """Handler for device code property (siid:2, piid:2) with model-specific support."""
    
    def __init__(self, model: str | None = None) -> None:
        """Initialize device code handler.
        
        Args:
            model: Device model identifier (e.g., "A1", "L10", etc.)
        """
        self._device_code: int | None = None
        self._device_code_name: str | None = None
        self._device_code_description: str | None = None
        self._device_code_is_error: bool | None = None
        self._device_code_is_warning: bool | None = None
        
        # Set up device code registry based on model
        self._registry = get_device_code_registry(model)
        self._model = model
    
    def set_model(self, model: str | None) -> None:
        """Update device model and switch to appropriate registry.
        
        Args:
            model: Device model identifier (e.g., "A1", "L10", etc.)
        """
        self._registry = get_device_code_registry(model)
        self._model = model
    
    def parse_value(self, value: Any) -> bool:
        """Parse device code value and update internal state.
        
        Args:
            value: Device code value from MQTT (should be int or convertible to int)
            
        Returns:
            True if parsing succeeded, False otherwise
        """
        try:
            # Convert value to integer
            code = int(value)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid device code value: %s", value)
            return False

        # Get device code definition from registry
        definition = self._registry.get_code(code)
        
        # Update device code properties
        self._device_code = code
        self._device_code_name = definition.name if definition else f"Unknown Code {code}"
        self._device_code_description = definition.description if definition else f"Unknown device code: {code}"
        self._device_code_is_error = definition.is_error() if definition else False
        self._device_code_is_warning = definition.is_warning() if definition else False
        
        return True
    
    def get_notification_data(self) -> Dict[str, Any]:
        """Get notification data dictionary for Home Assistant cards.
        
        Returns:
            Dictionary with device code notification data
        """
        return {
            NOTIFICATION_CODE_FIELD: self._device_code,
            NOTIFICATION_NAME_FIELD: self._device_code_name,
            NOTIFICATION_DESCRIPTION_FIELD: self._device_code_description,
            NOTIFICATION_TIMESTAMP_FIELD: datetime.now().isoformat()
        }
    
    @property
    def device_code(self) -> int | None:
        """Return current device code (2:2)."""
        return self._device_code
    
    @property
    def device_code_name(self) -> str | None:
        """Return device code name."""
        return self._device_code_name
    
    @property
    def device_code_description(self) -> str | None:
        """Return device code description."""
        return self._device_code_description
    
    @property
    def device_code_is_error(self) -> bool | None:
        """Return True if device code represents an error."""
        return self._device_code_is_error
    
    @property
    def device_code_is_warning(self) -> bool | None:
        """Return True if device code represents a warning."""
        return self._device_code_is_warning


# Base device code definitions (siid:2, piid:2), based on the Dreame A2 (g2408)
#
# These entries are the shared subset across multiple devices, with model-specific
# overrides layered on top where the same numeric code has different semantics.
BASE_DEVICE_CODES: Dict[int, DeviceCodeDefinition] = {
    0: DeviceCodeDefinition(
        code=0,
        name="NO_DEVICE_CODE",  # Note, should rather be FAULT_HANGING
        description="No device code - normal operation",
        code_type=DeviceCodeType.INFO
    ),
    1: DeviceCodeDefinition(
        code=1,
        name="TILTED",
        description="Robot tilted",
        code_type=DeviceCodeType.ERROR
    ),
    2: DeviceCodeDefinition(
        code=2,
        name="TRAPPED",
        description="Mower got stuck and cannot continue",
        code_type=DeviceCodeType.ERROR
    ),
    3: DeviceCodeDefinition(
        code=3,
        name="NARROW_PATH_TO_STATION",
        description="Passable area near the docking station is too narrow",
        code_type=DeviceCodeType.ERROR
    ),
    4: DeviceCodeDefinition(
        code=4,
        name="LEFT_WHEEL",
        description="Left drive wheel error",
        code_type=DeviceCodeType.ERROR
    ),
    5: DeviceCodeDefinition(
        code=5,
        name="RIGHT_WHEEL",
        description="Right drive wheel error",
        code_type=DeviceCodeType.ERROR
    ),
    6: DeviceCodeDefinition(
        code=6,
        name="LIFT_MOTOR",
        description="Lift motor error",
        code_type=DeviceCodeType.ERROR
    ),
    7: DeviceCodeDefinition(
        code=7,
        name="CUTTER",
        description="Cutter disc cannot rotate",
        code_type=DeviceCodeType.ERROR
    ),
    8: DeviceCodeDefinition(
        code=8,
        name="SIDED_MOTOR",
        description="Side motor error",
        code_type=DeviceCodeType.ERROR
    ),
    9: DeviceCodeDefinition(
        code=9,
        name="CRASH_PLATE",
        description="Bumper error",
        code_type=DeviceCodeType.ERROR
    ),
    10: DeviceCodeDefinition(
        code=10,
        name="CHARGING",
        description="Charging error",
        code_type=DeviceCodeType.ERROR
    ),
    11: DeviceCodeDefinition(
        code=11,
        name="BATTERY_OVERHEAT",
        description="Battery temperature is too high",
        code_type=DeviceCodeType.ERROR
    ),
    12: DeviceCodeDefinition(
        code=12,
        name="LIDAR_COVERED",
        description="LiDAR is blocked",
        code_type=DeviceCodeType.ERROR
    ),
    13: DeviceCodeDefinition(
        code=13,
        name="LIDAR_OVERHEAT_WITHOUT_MAP",
        description="LiDAR overheated while operating without a map",
        code_type=DeviceCodeType.ERROR
    ),
    14: DeviceCodeDefinition(
        code=14,
        name="LIDAR_OVERHEAT_WITH_MAP",
        description="LiDAR overheated while operating with a map",
        code_type=DeviceCodeType.ERROR
    ),
    15: DeviceCodeDefinition(
        code=15,
        name="LIDAR_OVERHEAT",
        description="LiDAR overheated",
        code_type=DeviceCodeType.ERROR
    ),
    16: DeviceCodeDefinition(
        code=16,
        name="LIDAR_DIRTY",
        description="LiDAR sensor is dirty",
        code_type=DeviceCodeType.ERROR
    ),
    17: DeviceCodeDefinition(
        code=17,
        name="LIDAR_ABNORMAL",
        description="LiDAR sensor abnormal",
        code_type=DeviceCodeType.ERROR
    ),
    18: DeviceCodeDefinition(
        code=18,
        name="LOCATION_WEAK",
        description="Robot is out of map boundaries",
        code_type=DeviceCodeType.ERROR
    ),
    19: DeviceCodeDefinition(
        code=19,
        name="LOCATION_LOST",
        description="Robot is lost",
        code_type=DeviceCodeType.ERROR
    ),
    20: DeviceCodeDefinition(
        code=20,
        name="SENSOR",
        description="Sensor error",
        code_type=DeviceCodeType.ERROR
    ),
    21: DeviceCodeDefinition(
        code=21,
        name="IN_FORBIDDEN_AREA",
        description="The robot is stuck in a no-go zone",
        code_type=DeviceCodeType.ERROR
    ),
    22: DeviceCodeDefinition(
        code=22,
        name="OUT_OF_MAP",
        description="Robot is out of map boundaries",
        code_type=DeviceCodeType.ERROR
    ),
    23: DeviceCodeDefinition(
        code=23,
        name="EMERGENCY_STOP",
        description="Emergency stop button was pressed",
        code_type=DeviceCodeType.ERROR
    ),
    24: DeviceCodeDefinition(
        code=24,
        name="BATTERY_LOW",
        description="Battery is low, powering off",
        code_type=DeviceCodeType.ERROR
    ),
    25: DeviceCodeDefinition(
        code=25,
        name="MAP_FILE_CRACK",
        description="Map file is corrupted",
        code_type=DeviceCodeType.ERROR
    ),
    26: DeviceCodeDefinition(
        code=26,
        name="AWAY_FROM_MAP",
        description="Robot is too far from the mapped area",
        code_type=DeviceCodeType.ERROR
    ),
    27: DeviceCodeDefinition(
        code=27,
        name="HUMAN_DETECTED",
        description="Positioning failed",
        code_type=DeviceCodeType.ERROR
    ),
    28: DeviceCodeDefinition(
        code=28,
        name="BLADE_LOSS",
        description="Blades lost or worn out",
        code_type=DeviceCodeType.ERROR
    ),  
    29: DeviceCodeDefinition(
        code=29,
        name="STATION_LOSS",
        description="Docking station signal lost",
        code_type=DeviceCodeType.ERROR
    ),
    30: DeviceCodeDefinition(
        code=30,
        name="MAINTAIN_LOSS",
        description="Maintenance reminder requires attention",
        code_type=DeviceCodeType.ERROR
    ),
    31: DeviceCodeDefinition(
        code=31,
        name="BACK_CHARGE_FAILED",
        description="Failed to return for charging",
        code_type=DeviceCodeType.WARNING
    ),
    32: DeviceCodeDefinition(
        code=32,
        name="DOCKING_FAILED",
        description="Failed to dock with the charging station",
        code_type=DeviceCodeType.WARNING
    ),
    33: DeviceCodeDefinition(
        code=33,
        name="LOCATING_FAILED_WITH_MAP",
        description="Positioning failed while using an existing map",
        code_type=DeviceCodeType.WARNING
    ),
    34: DeviceCodeDefinition(
        code=34,
        name="LOCATING_FAILED_WITHOUT_MAP",
        description="Positioning failed while operating without a map",
        code_type=DeviceCodeType.WARNING
    ),
    35: DeviceCodeDefinition(
        code=35,
        name="LOCATING_ABNORMAL",
        description="Positioning is abnormal",
        code_type=DeviceCodeType.WARNING
    ),
    36: DeviceCodeDefinition(
        code=36,
        name="TASK_START_FAILED",
        description="Task failed to start",
        code_type=DeviceCodeType.WARNING
    ),
    37: DeviceCodeDefinition(
        code=37,
        name="PATH_IMPASSABLE",
        description="The current passage is blocked and cannot be traversed",
        code_type=DeviceCodeType.ERROR
    ),
    38: DeviceCodeDefinition(
        code=38,
        name="LIDAR_DIRTY",
        description="LiDAR sensor is dirty",
        code_type=DeviceCodeType.WARNING
    ),
    39: DeviceCodeDefinition(
        code=39,
        name="CAM_DIRTY",
        description="Camera is dirty",
        code_type=DeviceCodeType.WARNING
    ),
    40: DeviceCodeDefinition(
        code=40,
        name="CAM_ABNORMAL",
        description="Camera abnormal",
        code_type=DeviceCodeType.WARNING
    ),
    41: DeviceCodeDefinition(
        code=41,
        name="CAM_COVER",
        description="Camera is covered",
        code_type=DeviceCodeType.WARNING
    ),
    42: DeviceCodeDefinition(
        code=42,
        name="BATTERY_OVERHEAT",
        description="Battery temperature is high",
        code_type=DeviceCodeType.WARNING
    ),
    43: DeviceCodeDefinition(
        code=43,
        name="BATTERY_TEMP_LOW",
        description="Charging paused: battery temperature is too low",
        code_type=DeviceCodeType.WARNING
    ),
    44: DeviceCodeDefinition(
        code=44,
        name="AUTOBUILD_BORDER",
        description="Automatic boundary building requires attention",
        code_type=DeviceCodeType.WARNING
    ),
    45: DeviceCodeDefinition(
        code=45,
        name="AUTOBUILD_SIDE",
        description="Automatic side building requires attention",
        code_type=DeviceCodeType.WARNING
    ),
    46: DeviceCodeDefinition(
        code=46,
        name="BORDER_FINISH",
        description="Boundary building completed",
        code_type=DeviceCodeType.INFO
    ),
    47: DeviceCodeDefinition(
        code=47,
        name="NEW_MAP",
        description="Robot is working, scheduled task cancelled",
        code_type=DeviceCodeType.INFO
    ),
    48: DeviceCodeDefinition(
        code=48,
        name="TASK_FINISH",
        description="Mowing task completed successfully",
        code_type=DeviceCodeType.INFO
    ),
    49: DeviceCodeDefinition(
        code=49,
        name="DESTINATION_NOT_REACHABLE",
        description="Mowing task started",
        code_type=DeviceCodeType.INFO
    ),
    50: DeviceCodeDefinition(
        code=50,
        name="TASK_START",
        description="Mowing operation started",
        code_type=DeviceCodeType.INFO
    ),
    51: DeviceCodeDefinition(
        code=51,
        name="CRUISE_START",
        description="Cruise task started",
        code_type=DeviceCodeType.INFO
    ),
    52: DeviceCodeDefinition(
        code=52,
        name="POINT_AND_GO_START",
        description="Point-and-go task started",
        code_type=DeviceCodeType.INFO
    ),
    53: DeviceCodeDefinition(
        code=53,
        name="SCHEDULE_START",
        description="Scheduled task started",
        code_type=DeviceCodeType.INFO
    ),
    54: DeviceCodeDefinition(
        code=54,
        name="BATTERY_LOW_RETURNING",
        description="Low battery, returning to dock",
        code_type=DeviceCodeType.INFO
    ),
    55: DeviceCodeDefinition(
        code=55,
        name="BATTERY_LOW_SCHEDULE_SUSPEND",
        description="Scheduled task suspended due to low battery",
        code_type=DeviceCodeType.INFO
    ),
    56: DeviceCodeDefinition(
        code=56,
        name="BAD_WEATHER_PROTECTING",
        description="Operation paused because of bad weather",
        code_type=DeviceCodeType.INFO
    ),
    57: DeviceCodeDefinition(
        code=57,
        name="RAIN_SCHEDULE_INTERUPTED",
        description="Scheduled task interrupted by rain",
        code_type=DeviceCodeType.INFO
    ),
    58: DeviceCodeDefinition(
        code=58,
        name="RAIN_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because of rain",
        code_type=DeviceCodeType.INFO
    ),
    59: DeviceCodeDefinition(
        code=59,
        name="FORZEN_RETURNING",
        description="Returning to dock because of freezing conditions",
        code_type=DeviceCodeType.INFO
    ),
    60: DeviceCodeDefinition(
        code=60,
        name="FROZEN_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because of freezing conditions",
        code_type=DeviceCodeType.INFO
    ),
    61: DeviceCodeDefinition(
        code=61,
        name="NOT_DISTURB_RETURNING",
        description="Do Not Disturb period started",
        code_type=DeviceCodeType.INFO
    ),
    62: DeviceCodeDefinition(
        code=62,
        name="NOT_DISTURB_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because of Do Not Disturb mode",
        code_type=DeviceCodeType.INFO
    ),
    63: DeviceCodeDefinition(
        code=63,
        name="WORKING_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because the mower is already working",
        code_type=DeviceCodeType.INFO
    ),
    64: DeviceCodeDefinition(
        code=64,
        name="REMOTE_CONTROLING_SCHEDULE_SUSPEND",
        description="Scheduled task suspended during remote control",
        code_type=DeviceCodeType.INFO
    ),
    65: DeviceCodeDefinition(
        code=65,
        name="EMERGENCY_STOPPED_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because emergency stop was triggered",
        code_type=DeviceCodeType.INFO
    ),
    66: DeviceCodeDefinition(
        code=66,
        name="TOP_COVER_OPEN_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because the top cover is open",
        code_type=DeviceCodeType.INFO
    ),
    67: DeviceCodeDefinition(
        code=67,
        name="FAULT_MODE_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because the mower is in fault mode",
        code_type=DeviceCodeType.INFO
    ),
    68: DeviceCodeDefinition(
        code=68,
        name="SCHEDULE_TIMEOUT",
        description="Scheduled task timed out",
        code_type=DeviceCodeType.INFO
    ),
    69: DeviceCodeDefinition(
        code=69,
        name="STATION_NOT_CONNECTED_TO_WORKING_AREA",
        description="Docking station is not connected to the working area",
        code_type=DeviceCodeType.INFO
    ),
    70: DeviceCodeDefinition(
        code=70,
        name="CONTINUE_FROM_BREAKPOINT",
        description="Do Not Disturb period ended",
        code_type=DeviceCodeType.INFO
    ),
    71: DeviceCodeDefinition(
        code=71,
        name="IDLE_TIMEOUT_RETURNING",
        description="Returning to dock after idle timeout",
        code_type=DeviceCodeType.INFO
    ),
    72: DeviceCodeDefinition(
        code=72,
        name="PAUSE_TIMEOUT_RETURNING",
        description="Returning to dock after pause timeout",
        code_type=DeviceCodeType.INFO
    ),
    73: DeviceCodeDefinition(
        code=73,
        name="TOP_COVER_OPEN",
        description="Top cover is open",
        code_type=DeviceCodeType.ERROR
    ),
}
BASE_DEVICE_CODE_REGISTRY = DeviceCodeRegistry(BASE_DEVICE_CODES)

# A1 and A1 Pro model variations
A1_DEVICE_CODES: Dict[int, DeviceCodeDefinition] = {
    19: DeviceCodeDefinition(
        code=19,
        name="EMERGENCY_STOP_PRESSED",
        description="Emergency stop pressed",
        code_type=DeviceCodeType.ERROR
    ),
    53: DeviceCodeDefinition(
        code=53,
        name="MOWING_STARTED",
        description="Mowing operation started",
        code_type=DeviceCodeType.INFO
    ),
    70: DeviceCodeDefinition(
        code=70,
        name="MOWING_RESUMED_AFTER_CHARGING",
        description="Mower resumed mowing after recharge",
        code_type=DeviceCodeType.INFO
    ),
    73: DeviceCodeDefinition(
        code=73,
        name="ROBOT_LIFTED",
        description="Robot was lifted",
        code_type=DeviceCodeType.ERROR
    ),
}
A1_DEVICE_CODE_REGISTRY = BASE_DEVICE_CODE_REGISTRY.extend(A1_DEVICE_CODES)

# MOVA 600 and MOVA 1000 model variations
MOVA_DEVICE_CODES: Dict[int, DeviceCodeDefinition] = {
    # MOVA-specific device codes
    0: DeviceCodeDefinition(
        code=0,
        name="ROBOT_LIFTED",
        description="Robot lifted",
        code_type=DeviceCodeType.ERROR
    ),
    1: DeviceCodeDefinition(
        code=1,
        name="ROBOT_TILTED",
        description="Robot tilted",
        code_type=DeviceCodeType.ERROR
    ),
    4: DeviceCodeDefinition(
        code=4,
        name="LEFT_DRIVE_WHEEL_ERROR",
        description="Left drive wheel error",
        code_type=DeviceCodeType.ERROR
    ),
    5: DeviceCodeDefinition(
        code=5,
        name="RIGHT_DRIVE_WHEEL_ERROR",
        description="Right drive wheel error",
        code_type=DeviceCodeType.ERROR
    ),
    12: DeviceCodeDefinition(
        code=12,
        name="LIDAR_IS_BLOCKED",
        description="Lidar is blocked",
        code_type=DeviceCodeType.ERROR
    ),
    30: DeviceCodeDefinition(
        code=30,
        name="MAINTENANCE_TIME_REACHED",
        description="Robot maintenance time reached. Maintain the robot soon",
        code_type=DeviceCodeType.WARNING
    ),
    55: DeviceCodeDefinition(
        code=55,
        name="ROBOT_CANT_START_LOW_BATTERY",
        description="Robot can't start due to low battery",
        code_type=DeviceCodeType.ERROR
    ),
    70: DeviceCodeDefinition(
        code=70,
        name="CONTINUE_UNFINISHED_TASK",
        description="Robot will continue the unfinished task",
        code_type=DeviceCodeType.INFO
    ),
}
MOVA_DEVICE_CODE_REGISTRY = BASE_DEVICE_CODE_REGISTRY.extend(MOVA_DEVICE_CODES)


def get_device_code_registry(model: str | None = None) -> DeviceCodeRegistry:
    """Get device code registry for specific model."""
    if model is None:
        return BASE_DEVICE_CODE_REGISTRY

    if model in ["dreame.mower.p2255", "dreame.mower.g2422"]:  # A1 and A1 Pro models
        return A1_DEVICE_CODE_REGISTRY
    elif model.startswith("mova.mower."):  # MOVA models
        return MOVA_DEVICE_CODE_REGISTRY
    
    return BASE_DEVICE_CODE_REGISTRY