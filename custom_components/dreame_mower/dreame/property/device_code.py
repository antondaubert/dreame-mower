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
DEVICE_CODE_ERROR_PROPERTY_NAME = "device_code_error"
DEVICE_CODE_WARNING_PROPERTY_NAME = "device_code_warning"
DEVICE_CODE_INFO_PROPERTY_NAME = "device_code_info"

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
    """Device code definition with name, description, and type."""
    
    def __init__(self, name: str, description: str, code_type: DeviceCodeType) -> None:
        """Initialize device code definition."""
        self.name = name
        self.description = description
        self.code_type = code_type
    
    def is_error(self) -> bool:
        """Check if this device code represents an error."""
        return self.code_type == DeviceCodeType.ERROR
    
    def is_warning(self) -> bool:
        """Check if this device code represents a warning."""
        return self.code_type == DeviceCodeType.WARNING


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
    
    def set_model(self, model: str | None) -> None:
        """Update device model and switch to appropriate registry.
        
        Args:
            model: Device model identifier (e.g., "A1", "L10", etc.)
        """
        self._registry = get_device_code_registry(model)
    
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
    
    def is_problem(self, code: int) -> bool:
        """Return whether a code of this mower's model is an error or a warning."""
        return self._registry.is_error(code) or self._registry.is_warning(code)

    def is_error(self, code: int) -> bool:
        """Return whether a code of this mower's model is an error."""
        return self._registry.is_error(code)

    def describe(self, code: int) -> str:
        """Return the description of any code of this mower's model."""
        return self._registry.get_description(code)

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
        name="NO_DEVICE_CODE",  # Note, should rather be FAULT_HANGING
        description="No device code - normal operation",
        code_type=DeviceCodeType.INFO
    ),
    1: DeviceCodeDefinition(
        name="TILTED",
        description="Robot tilted",
        code_type=DeviceCodeType.ERROR
    ),
    2: DeviceCodeDefinition(
        name="TRAPPED",
        description="Mower got stuck and cannot continue",
        code_type=DeviceCodeType.ERROR
    ),
    3: DeviceCodeDefinition(
        name="NARROW_PATH_TO_STATION",
        description="Passable area near the docking station is too narrow",
        code_type=DeviceCodeType.ERROR
    ),
    4: DeviceCodeDefinition(
        name="LEFT_WHEEL",
        description="Left drive wheel error",
        code_type=DeviceCodeType.ERROR
    ),
    5: DeviceCodeDefinition(
        name="RIGHT_WHEEL",
        description="Right drive wheel error",
        code_type=DeviceCodeType.ERROR
    ),
    6: DeviceCodeDefinition(
        name="LIFT_MOTOR",
        description="Lift motor error",
        code_type=DeviceCodeType.ERROR
    ),
    7: DeviceCodeDefinition(
        name="CUTTER",
        description="Cutter disc cannot rotate",
        code_type=DeviceCodeType.ERROR
    ),
    8: DeviceCodeDefinition(
        name="SIDED_MOTOR",
        description="Side motor error",
        code_type=DeviceCodeType.ERROR
    ),
    9: DeviceCodeDefinition(
        name="CRASH_PLATE",
        description="Bumper error",
        code_type=DeviceCodeType.ERROR
    ),
    10: DeviceCodeDefinition(
        name="CHARGING",
        description="Charging error",
        code_type=DeviceCodeType.ERROR
    ),
    11: DeviceCodeDefinition(
        name="BATTERY_OVERHEAT",
        description="Battery temperature is too high",
        code_type=DeviceCodeType.ERROR
    ),
    12: DeviceCodeDefinition(
        name="LIDAR_COVERED",
        description="LiDAR is blocked",
        code_type=DeviceCodeType.ERROR
    ),
    13: DeviceCodeDefinition(
        name="LIDAR_OVERHEAT_WITHOUT_MAP",
        description="LiDAR overheated while operating without a map",
        code_type=DeviceCodeType.ERROR
    ),
    14: DeviceCodeDefinition(
        name="LIDAR_OVERHEAT_WITH_MAP",
        description="LiDAR overheated while operating with a map",
        code_type=DeviceCodeType.ERROR
    ),
    15: DeviceCodeDefinition(
        name="LIDAR_OVERHEAT",
        description="LiDAR overheated",
        code_type=DeviceCodeType.ERROR
    ),
    16: DeviceCodeDefinition(
        name="LIDAR_DIRTY",
        description="LiDAR sensor is dirty",
        code_type=DeviceCodeType.ERROR
    ),
    17: DeviceCodeDefinition(
        name="LIDAR_ABNORMAL",
        description="LiDAR sensor abnormal",
        code_type=DeviceCodeType.ERROR
    ),
    18: DeviceCodeDefinition(
        name="LOCATION_WEAK",
        description="Robot is out of map boundaries",
        code_type=DeviceCodeType.ERROR
    ),
    19: DeviceCodeDefinition(
        name="LOCATION_LOST",
        description="Robot is lost",
        code_type=DeviceCodeType.ERROR
    ),
    20: DeviceCodeDefinition(
        name="SENSOR",
        description="Sensor error",
        code_type=DeviceCodeType.ERROR
    ),
    21: DeviceCodeDefinition(
        name="IN_FORBIDDEN_AREA",
        description="The robot is stuck in a no-go zone",
        code_type=DeviceCodeType.ERROR
    ),
    22: DeviceCodeDefinition(
        name="OUT_OF_MAP",
        description="Robot is out of map boundaries",
        code_type=DeviceCodeType.ERROR
    ),
    23: DeviceCodeDefinition(
        name="EMERGENCY_STOP",
        description="Emergency stop button was pressed",
        code_type=DeviceCodeType.ERROR
    ),
    24: DeviceCodeDefinition(
        name="BATTERY_LOW",
        description="Battery is low, powering off",
        code_type=DeviceCodeType.ERROR
    ),
    25: DeviceCodeDefinition(
        name="MAP_FILE_CRACK",
        description="Map file is corrupted",
        code_type=DeviceCodeType.ERROR
    ),
    26: DeviceCodeDefinition(
        name="AWAY_FROM_MAP",
        description="Robot is too far from the mapped area",
        code_type=DeviceCodeType.ERROR
    ),
    27: DeviceCodeDefinition(
        name="HUMAN_DETECTED",
        description="Positioning failed",
        code_type=DeviceCodeType.ERROR
    ),
    # Codes 28-30 are consumable reminders: the part still works, it is worn
    # and due for replacement or service, so they are warnings and not faults.
    28: DeviceCodeDefinition(
        name="BLADE_WORN",
        description="Blades are severely worn. Replace them soon",
        code_type=DeviceCodeType.WARNING
    ),
    29: DeviceCodeDefinition(
        name="STATION_BRUSH_WORN",
        description="Docking station cleaning brush is severely worn. Replace it soon",
        code_type=DeviceCodeType.WARNING
    ),
    30: DeviceCodeDefinition(
        name="MAINTENANCE_TIME_REACHED",
        description="Robot maintenance time reached. Maintain the robot soon",
        code_type=DeviceCodeType.WARNING
    ),
    31: DeviceCodeDefinition(
        name="BACK_CHARGE_FAILED",
        description="Failed to return for charging",
        code_type=DeviceCodeType.WARNING
    ),
    32: DeviceCodeDefinition(
        name="DOCKING_FAILED",
        description="Failed to dock with the charging station",
        code_type=DeviceCodeType.WARNING
    ),
    33: DeviceCodeDefinition(
        name="LOCATING_FAILED_WITH_MAP",
        description="Positioning failed while using an existing map",
        code_type=DeviceCodeType.WARNING
    ),
    34: DeviceCodeDefinition(
        name="LOCATING_FAILED_WITHOUT_MAP",
        description="Positioning failed while operating without a map",
        code_type=DeviceCodeType.WARNING
    ),
    35: DeviceCodeDefinition(
        name="LOCATING_ABNORMAL",
        description="Positioning is abnormal",
        code_type=DeviceCodeType.WARNING
    ),
    36: DeviceCodeDefinition(
        name="TASK_START_FAILED",
        description="Task failed to start",
        code_type=DeviceCodeType.WARNING
    ),
    37: DeviceCodeDefinition(
        name="PATH_IMPASSABLE",
        description="The current passage is blocked and cannot be traversed",
        code_type=DeviceCodeType.ERROR
    ),
    38: DeviceCodeDefinition(
        name="LIDAR_DIRTY",
        description="LiDAR sensor is dirty",
        code_type=DeviceCodeType.WARNING
    ),
    39: DeviceCodeDefinition(
        name="CAM_DIRTY",
        description="Camera is dirty",
        code_type=DeviceCodeType.WARNING
    ),
    40: DeviceCodeDefinition(
        name="CAM_ABNORMAL",
        description="Camera abnormal",
        code_type=DeviceCodeType.WARNING
    ),
    41: DeviceCodeDefinition(
        name="CAM_COVER",
        description="Camera is covered",
        code_type=DeviceCodeType.WARNING
    ),
    42: DeviceCodeDefinition(
        name="BATTERY_OVERHEAT",
        description="Battery temperature is high",
        code_type=DeviceCodeType.WARNING
    ),
    43: DeviceCodeDefinition(
        name="BATTERY_TEMP_LOW",
        description="Charging paused: battery temperature is too low",
        code_type=DeviceCodeType.WARNING
    ),
    44: DeviceCodeDefinition(
        name="AUTOBUILD_BORDER",
        description="Automatic boundary building requires attention",
        code_type=DeviceCodeType.WARNING
    ),
    45: DeviceCodeDefinition(
        name="AUTOBUILD_SIDE",
        description="Automatic side building requires attention",
        code_type=DeviceCodeType.WARNING
    ),
    46: DeviceCodeDefinition(
        name="BORDER_FINISH",
        description="Boundary building completed",
        code_type=DeviceCodeType.INFO
    ),
    47: DeviceCodeDefinition(
        name="NEW_MAP",
        description="Robot is working, scheduled task cancelled",
        code_type=DeviceCodeType.INFO
    ),
    48: DeviceCodeDefinition(
        name="TASK_FINISH",
        description="Mowing task completed successfully",
        code_type=DeviceCodeType.INFO
    ),
    49: DeviceCodeDefinition(
        name="DESTINATION_NOT_REACHABLE",
        description="Mowing task started",
        code_type=DeviceCodeType.INFO
    ),
    50: DeviceCodeDefinition(
        name="TASK_START",
        description="Mowing operation started",
        code_type=DeviceCodeType.INFO
    ),
    51: DeviceCodeDefinition(
        name="CRUISE_START",
        description="Cruise task started",
        code_type=DeviceCodeType.INFO
    ),
    52: DeviceCodeDefinition(
        name="POINT_AND_GO_START",
        description="Point-and-go task started",
        code_type=DeviceCodeType.INFO
    ),
    53: DeviceCodeDefinition(
        name="SCHEDULE_START",
        description="Scheduled task started",
        code_type=DeviceCodeType.INFO
    ),
    54: DeviceCodeDefinition(
        name="BATTERY_LOW_RETURNING",
        description="Low battery, returning to dock",
        code_type=DeviceCodeType.INFO
    ),
    55: DeviceCodeDefinition(
        name="BATTERY_LOW_SCHEDULE_SUSPEND",
        description="Scheduled task suspended due to low battery",
        code_type=DeviceCodeType.INFO
    ),
    56: DeviceCodeDefinition(
        name="BAD_WEATHER_PROTECTING",
        description="Operation paused because of bad weather",
        code_type=DeviceCodeType.INFO
    ),
    57: DeviceCodeDefinition(
        name="RAIN_SCHEDULE_INTERUPTED",
        description="Scheduled task interrupted by rain",
        code_type=DeviceCodeType.INFO
    ),
    58: DeviceCodeDefinition(
        name="RAIN_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because of rain",
        code_type=DeviceCodeType.INFO
    ),
    59: DeviceCodeDefinition(
        name="FORZEN_RETURNING",
        description="Returning to dock because of freezing conditions",
        code_type=DeviceCodeType.INFO
    ),
    60: DeviceCodeDefinition(
        name="FROZEN_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because of freezing conditions",
        code_type=DeviceCodeType.INFO
    ),
    61: DeviceCodeDefinition(
        name="NOT_DISTURB_RETURNING",
        description="Do Not Disturb period started",
        code_type=DeviceCodeType.INFO
    ),
    62: DeviceCodeDefinition(
        name="NOT_DISTURB_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because of Do Not Disturb mode",
        code_type=DeviceCodeType.INFO
    ),
    63: DeviceCodeDefinition(
        name="WORKING_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because the mower is already working",
        code_type=DeviceCodeType.INFO
    ),
    64: DeviceCodeDefinition(
        name="REMOTE_CONTROLING_SCHEDULE_SUSPEND",
        description="Scheduled task suspended during remote control",
        code_type=DeviceCodeType.INFO
    ),
    65: DeviceCodeDefinition(
        name="EMERGENCY_STOPPED_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because emergency stop was triggered",
        code_type=DeviceCodeType.INFO
    ),
    66: DeviceCodeDefinition(
        name="TOP_COVER_OPEN_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because the top cover is open",
        code_type=DeviceCodeType.INFO
    ),
    67: DeviceCodeDefinition(
        name="FAULT_MODE_SCHEDULE_SUSPEND",
        description="Scheduled task suspended because the mower is in fault mode",
        code_type=DeviceCodeType.INFO
    ),
    68: DeviceCodeDefinition(
        name="SCHEDULE_TIMEOUT",
        description="Scheduled task timed out",
        code_type=DeviceCodeType.INFO
    ),
    69: DeviceCodeDefinition(
        name="STATION_NOT_CONNECTED_TO_WORKING_AREA",
        description="Docking station is not connected to the working area",
        code_type=DeviceCodeType.INFO
    ),
    70: DeviceCodeDefinition(
        name="CONTINUE_FROM_BREAKPOINT",
        description="Do Not Disturb period ended",
        code_type=DeviceCodeType.INFO
    ),
    71: DeviceCodeDefinition(
        name="IDLE_TIMEOUT_RETURNING",
        description="Returning to dock after idle timeout",
        code_type=DeviceCodeType.INFO
    ),
    72: DeviceCodeDefinition(
        name="PAUSE_TIMEOUT_RETURNING",
        description="Returning to dock after pause timeout",
        code_type=DeviceCodeType.INFO
    ),
    73: DeviceCodeDefinition(
        name="TOP_COVER_OPEN",
        description="Top cover is open",
        code_type=DeviceCodeType.ERROR
    ),
    74: DeviceCodeDefinition(
        name="CRUISE_TASK_FINISH",
        description="Cruise task completed",
        code_type=DeviceCodeType.INFO
    ),
    75: DeviceCodeDefinition(
        name="MAINTENANCE_POINT_REACHED",
        description="Arrived at the maintenance point",
        code_type=DeviceCodeType.INFO
    ),
    76: DeviceCodeDefinition(
        name="MAINTENANCE_POINT_UNREACHABLE",
        description="Unable to reach the maintenance point, task ended",
        code_type=DeviceCodeType.INFO
    ),
    77: DeviceCodeDefinition(
        name="ERROR_ON_WAY_TO_MAINTENANCE_POINT",
        description="Robot error on the way to the maintenance point, task ended",
        code_type=DeviceCodeType.INFO
    ),
    78: DeviceCodeDefinition(
        name="LOW_LIGHT_RETURNING",
        description="Outside the operating hours and insufficient light, returning to the station",
        code_type=DeviceCodeType.INFO
    ),
    80: DeviceCodeDefinition(
        name="LIDAR_COOLING",
        description="LiDAR is cooling down",
        code_type=DeviceCodeType.INFO
    ),
}
BASE_DEVICE_CODE_REGISTRY = DeviceCodeRegistry(BASE_DEVICE_CODES)

# A1 and A1 Pro model variations
A1_DEVICE_CODES: Dict[int, DeviceCodeDefinition] = {
    19: DeviceCodeDefinition(
        name="EMERGENCY_STOP_PRESSED",
        description="Emergency stop pressed",
        code_type=DeviceCodeType.ERROR
    ),
    53: DeviceCodeDefinition(
        name="MOWING_STARTED",
        description="Mowing operation started",
        code_type=DeviceCodeType.INFO
    ),
    70: DeviceCodeDefinition(
        name="MOWING_RESUMED_AFTER_CHARGING",
        description="Mower resumed mowing after recharge",
        code_type=DeviceCodeType.INFO
    ),
    73: DeviceCodeDefinition(
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
        name="ROBOT_LIFTED",
        description="Robot lifted",
        code_type=DeviceCodeType.ERROR
    ),
    1: DeviceCodeDefinition(
        name="ROBOT_TILTED",
        description="Robot tilted",
        code_type=DeviceCodeType.ERROR
    ),
    4: DeviceCodeDefinition(
        name="LEFT_DRIVE_WHEEL_ERROR",
        description="Left drive wheel error",
        code_type=DeviceCodeType.ERROR
    ),
    5: DeviceCodeDefinition(
        name="RIGHT_DRIVE_WHEEL_ERROR",
        description="Right drive wheel error",
        code_type=DeviceCodeType.ERROR
    ),
    12: DeviceCodeDefinition(
        name="LIDAR_IS_BLOCKED",
        description="Lidar is blocked",
        code_type=DeviceCodeType.ERROR
    ),
    55: DeviceCodeDefinition(
        name="ROBOT_CANT_START_LOW_BATTERY",
        description="Robot can't start due to low battery",
        code_type=DeviceCodeType.ERROR
    ),
    70: DeviceCodeDefinition(
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
