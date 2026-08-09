"""Scheduling property handling for Dreame Mower Implementation.

This module provides parsing and handling for Service 2 scheduling properties:
- 2:50 - Mission task descriptor (TASK object with mission details)
- 2:52 - Mission completion summary (currently empty, future use)

These properties manage mission lifecycle and completion tracking.

The device also reports a changed mowing preference on 2:52, without naming the
map or the setting that changed. The payload is passed on as it arrives, and the
coordinator takes any report here as the cue to read the records back.
"""

from __future__ import annotations

import logging
from typing import Dict, Any
from enum import Enum
from ..const import SCHEDULING_TASK_PROPERTY, SCHEDULING_SUMMARY_PROPERTY

_LOGGER = logging.getLogger(__name__)

# Task data field constants
TASK_TYPE_FIELD = "type"
TASK_AREA_ID_FIELD = "area_id"
TASK_EXECUTION_FIELD = "execution_active"
TASK_COVERAGE_FIELD = "coverage_target"
TASK_REGION_ID_FIELD = "region_id"
TASK_STATUS_FIELD = "task_active"
TASK_TIME_FIELD = "elapsed_time"


class TaskType(Enum):
    """Task type enumeration."""
    TASK = "TASK"
    UNKNOWN = "UNKNOWN"


class TaskHandler:
    """Handler for mission task descriptor property (2:50)."""
    
    def __init__(self) -> None:
        """Initialize task handler."""
        self._task_type: TaskType | None = None
        self._area_id: list[int] | None = None
        self._execution_active: bool | None = None
        self._coverage_target: int | None = None
        self._region_id: list[int] | None = None
        self._task_active: bool | None = None
        self._elapsed_time: int | None = None
    
    def parse_value(self, value: Any) -> bool:
        """Parse task descriptor value."""
        try:
            if not isinstance(value, dict):
                _LOGGER.warning("Invalid task descriptor value type: %s", type(value))
                return False
            
            # Extract task type - required field
            task_type_str = value["t"]
            self._task_type = TaskType.TASK if task_type_str == "TASK" else TaskType.UNKNOWN
            
            # Extract task data from 'd' field - required
            task_data = value["d"]
            if not isinstance(task_data, dict):
                raise ValueError(f"Invalid task data format: {task_data}")
            
            # Extract required task fields - let KeyError bubble up for missing required fields
            self._execution_active = task_data["exe"]
            self._coverage_target = task_data["o"]
            self._task_active = task_data["status"]
            
            # Extract optional task fields (may not be present for paused/docked states)
            self._area_id = task_data.get("area_id")
            self._region_id = task_data.get("region_id")
            self._elapsed_time = task_data.get("time")
            
            _LOGGER.debug(
                "Task descriptor parsed: type=%s, regions=%s, elapsed=%s, active=%s, execution_active=%s",
                self._task_type, self._region_id, self._elapsed_time, self._task_active, self._execution_active
            )
            return True
            
        except (KeyError, ValueError) as ex:
            _LOGGER.error("Failed to parse task descriptor - missing or invalid field: %s", ex)
            return False
        except Exception as ex:
            _LOGGER.error("Failed to parse task descriptor: %s", ex)
            return False
    
    def get_notification_data(self) -> Dict[str, Any]:
        """Get task notification data for Home Assistant."""
        return {
            TASK_TYPE_FIELD: self._task_type.value if self._task_type else None,
            TASK_AREA_ID_FIELD: self._area_id,
            TASK_EXECUTION_FIELD: self._execution_active,
            TASK_COVERAGE_FIELD: self._coverage_target,
            TASK_REGION_ID_FIELD: self._region_id,
            TASK_STATUS_FIELD: self._task_active,
            TASK_TIME_FIELD: self._elapsed_time,
        }
    
    # Properties for direct access
    @property
    def task_type(self) -> TaskType | None:
        """Return task type."""
        return self._task_type
    
    @property
    def area_id(self) -> list[int] | None:
        """Return selected area IDs."""
        return self._area_id
    
    @property
    def execution_active(self) -> bool | None:
        """Return True if task execution is active."""
        return self._execution_active
    
    @property
    def coverage_target(self) -> int | None:
        """Return coverage target percentage or mode sentinel."""
        return self._coverage_target
    
    @property
    def region_id(self) -> list[int] | None:
        """Return working region IDs."""
        return self._region_id
    
    @property
    def task_active(self) -> bool | None:
        """Return True if task is active/accepted."""
        return self._task_active
    
    @property
    def elapsed_time(self) -> int | None:
        """Return elapsed time in seconds at snapshot."""
        return self._elapsed_time


class SummaryHandler:
    """Handler for mission completion summary property (2:52)."""
    
    def __init__(self) -> None:
        """Initialize summary handler."""
        self._summary_data: Dict[str, Any] = {}
    
    def parse_value(self, value: Any) -> bool:
        """Parse mission summary value."""
        try:
            if isinstance(value, dict):
                self._summary_data = value.copy()
            elif value == {}:
                # Empty dict is valid (current behavior)
                self._summary_data = {}
            else:
                _LOGGER.warning("Invalid summary value type: %s", type(value))
                return False
            
            _LOGGER.debug("Mission summary parsed: %s", self._summary_data)
            return True
            
        except Exception as ex:
            _LOGGER.error("Failed to parse mission summary: %s", ex)
            return False
    
    def get_notification_data(self) -> Dict[str, Any]:
        """Get summary notification data for Home Assistant."""
        # Return raw data for now, add specific field extraction when populated
        return self._summary_data.copy()
    
    @property
    def summary_data(self) -> Dict[str, Any]:
        """Return raw summary data."""
        return self._summary_data.copy()
    
    @property
    def is_empty(self) -> bool:
        """Return True if summary is empty."""
        return len(self._summary_data) == 0


class SchedulingPropertyHandler:
    """Combined handler for scheduling properties (2:50, 2:52)."""
    
    def __init__(self) -> None:
        """Initialize scheduling property handler."""
        self._task_handler = TaskHandler()
        self._summary_handler = SummaryHandler()
    
    def handle_property_update(self, siid: int, piid: int, value: Any, notify_callback) -> bool:
        """Handle scheduling property update with unified logic."""
        try:
            # Handle task descriptor (2:50)
            if SCHEDULING_TASK_PROPERTY.matches(siid, piid):
                return self._handle_task_property(value, notify_callback)
            
            # Handle summary (2:52)
            elif SCHEDULING_SUMMARY_PROPERTY.matches(siid, piid):
                return self._handle_summary_property(value, notify_callback)
            
            else:
                # Not a scheduling property
                return False
                
        except Exception as ex:
            _LOGGER.error("Failed to handle scheduling property %d:%d: %s", siid, piid, ex)
            return False
    
    def _handle_task_property(self, value: Any, notify_callback) -> bool:
        """Handle mission task descriptor (2:50)."""
        if self._task_handler.parse_value(value):
            task_data = self._task_handler.get_notification_data()
            notify_callback(SCHEDULING_TASK_PROPERTY.name, task_data)
            _LOGGER.info("Mission task started: %s", task_data)
            return True
        else:
            _LOGGER.warning("Failed to parse task descriptor value: %s", value)
            return False
    
    def _handle_summary_property(self, value: Any, notify_callback) -> bool:
        """Handle mission completion summary (2:52)."""
        if self._summary_handler.parse_value(value):
            summary_data = self._summary_handler.get_notification_data()
            notify_callback(SCHEDULING_SUMMARY_PROPERTY.name, summary_data)
            
            if not self._summary_handler.is_empty:
                _LOGGER.info("Mission completed: %s", summary_data)
            else:
                _LOGGER.debug("Mission completion marker received (empty summary)")
            
            return True
        else:
            _LOGGER.warning("Failed to parse summary value: %s", value)
            return False
