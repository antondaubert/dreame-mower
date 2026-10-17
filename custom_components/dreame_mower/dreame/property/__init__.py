"""Property handling module for Dreame Mower."""

from .property_misc import MiscPropertyHandler
from .device_code import (
    DeviceCodeHandler,
    DEVICE_CODE_ERROR_PROPERTY_NAME,
    DEVICE_CODE_WARNING_PROPERTY_NAME,
    DEVICE_CODE_INFO_PROPERTY_NAME,
    NOTIFICATION_CODE_FIELD,
    NOTIFICATION_NAME_FIELD,
    NOTIFICATION_DESCRIPTION_FIELD,
)
from .scheduling import SchedulingPropertyHandler
from .pose_coverage import (
    PoseCoverageHandler,
    POSE_COVERAGE_PROGRESS_PROPERTY_NAME,
    POSE_COVERAGE_COORDINATES_PROPERTY_NAME,
)
from .mission_completion import MissionCompletionEventHandler

__all__ = [
    "MiscPropertyHandler",
    "DeviceCodeHandler",
    "DEVICE_CODE_ERROR_PROPERTY_NAME",
    "DEVICE_CODE_WARNING_PROPERTY_NAME",
    "DEVICE_CODE_INFO_PROPERTY_NAME",
    "NOTIFICATION_CODE_FIELD",
    "NOTIFICATION_NAME_FIELD",
    "NOTIFICATION_DESCRIPTION_FIELD",
    "SchedulingPropertyHandler",
    "PoseCoverageHandler",
    "POSE_COVERAGE_PROGRESS_PROPERTY_NAME",
    "POSE_COVERAGE_COORDINATES_PROPERTY_NAME",
    "MissionCompletionEventHandler",
]
