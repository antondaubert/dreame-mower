"""Mission completion event handling for Dreame Mower Implementation.

This module provides parsing and handling for Service 4 mission completion events:
- 4:1 - Mission completion event with comprehensive session summary

The event provides detailed information about completed mowing sessions including:
- The kind of task (all-area, edge, zone, spot, or a patrol)
- How it was started (in the app or by a schedule)
- Duration 
- Area covered
- Timestamps
- Mission data file path
- Success status
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Callable

from ..utils import download_file

_LOGGER = logging.getLogger(__name__)

# Event name constants for notifications
MISSION_COMPLETION_EVENT_PROPERTY_NAME = "mission_completion_event"

# Mission completion event field constants
TASK_MODE_FIELD = "task_mode"  # piid 1: all_area, edge, zone, spot, point_patrol, edge_patrol, ...
DURATION_FIELD = "duration_minutes"
AREA_FIELD = "area_sqm"
STATUS_FIELD = "status"  # Task status (piid 7); 1=FINISHED, 2=UNFINISHED, 3=INTERRUPTED
START_TIMESTAMP_FIELD = "start_timestamp"
DATA_FILE_PATH_FIELD = "data_file_path"
SCHEDULED_FIELD = "scheduled"  # piid 11: True when a schedule started the task
CHARGING_EVENTS_FIELD = "charging_events"
PLANNED_AREA_FIELD = "planned_area_sqm"  # Planned mowing area for the session in m²
UNKNOWN_FIELD_15 = "unknown_field_15"
STOP_REASON_FIELD = "stop_reason"  # Why the mission ended (piid 60); 101 = low battery / returned to dock early
MAP_NAME_FIELD = "map_name"

# The task mode (piid 1) is offset by this much; older firmware reports it
# without the offset.
TASK_MODE_OFFSET = 100
TASK_MODES = {
    0: "all_area",
    1: "edge",
    2: "zone",
    3: "spot",
    7: "point_patrol",
    8: "edge_patrol",
    9: "point_patrol",
}
# How a task was started (piid 11).
START_MODE_SCHEDULE = 1

# Task status codes (piid 7); 2 is a mission that did not finish
STATUS_FINISHED = 1     # Mission completed normally
STATUS_INTERRUPTED = 3  # Mission was interrupted (e.g. low battery)


class MissionCompletionEventHandler:
    """Handler for mission completion event (4:1) with detailed session data."""
    
    def __init__(self) -> None:
        """Initialize mission completion event handler."""
        
        # Mission completion data
        self._task_mode: str | None = None
        self._duration_minutes: int | None = None
        self._area_sqm: float | None = None
        self._status: int | None = None  # piid 7: STATUS_FINISHED/UNFINISHED/INTERRUPTED
        self._start_timestamp: int | None = None
        self._data_file_path: str | None = None
        self._scheduled: bool | None = None
        self._stop_reason: int | None = None  # Why the mission ended (piid 60); 101 = low battery
        # Charging events during mission: list of [timestamp, duration_minutes] pairs
        # Each entry represents a charging session that occurred during the mowing mission
        self._charging_events: list | None = None
        self._planned_area_sqm: int | None = None  # Planned mowing area for the session in m²
        self._unknown_field_15: int | None = None  # Purpose unknown - observed values: -1, 2
        self._map_name: str | None = None  # Map identifier the mission was performed on (e.g. "map1")
        
    
    def handle_event(self, siid: int, eiid: int, arguments: List[Dict[str, Any]], notify_callback) -> bool:
        """Handle mission completion event.
        
        Args:
            siid: Service instance ID
            eiid: Event instance ID
            arguments: Event arguments with piid/value pairs
            notify_callback: Callback function for event notifications
            
        Returns:
            True if event was handled successfully, False otherwise
        """
        from ..const import MISSION_COMPLETION_EVENT
        
        try:
            # Check if this is the mission completion event
            if not MISSION_COMPLETION_EVENT.matches(siid, eiid):
                return False
            
            return self._parse_mission_completion_event(arguments, notify_callback)
                
        except Exception as ex:
            _LOGGER.error("Failed to handle mission completion event %d:%d: %s", siid, eiid, ex)
            return False
    
    def _parse_mission_completion_event(self, arguments: List[Dict[str, Any]], notify_callback) -> bool:
        """Parse mission completion event arguments."""
        try:
            # Reset previous values
            self._reset_values()
            # Older firmware reports the task mode without its offset, the
            # area in whole m² and status 0 and 3 the other way round; which
            # firmware sent the event is only known once the mode was read.
            older_firmware = False
            
            # Parse each argument
            for arg in arguments:
                piid = arg['piid']  # Will raise KeyError if missing
                value = arg['value']  # Will raise KeyError if missing
                
                # Parse known fields based on piid
                if piid == 1:  # Task mode, offset by TASK_MODE_OFFSET on current firmware
                    mode = int(value)
                    older_firmware = mode < TASK_MODE_OFFSET
                    if not older_firmware:
                        mode -= TASK_MODE_OFFSET
                    self._task_mode = TASK_MODES.get(mode, f"mode_{mode}")
                elif piid == 2:  # Duration in minutes
                    self._duration_minutes = int(value)
                elif piid == 3:  # Area (divide by 100 to get m²)
                    self._area_sqm = float(value) / 100.0  # Convert to m²
                elif piid == 7:  # Task completion status (FINISHED=1, UNFINISHED=2, INTERRUPTED=3)
                    self._status = int(value)
                elif piid == 8:  # Start timestamp
                    self._start_timestamp = int(value)
                elif piid == 9:  # Data file path
                    self._data_file_path = str(value)
                elif piid == 11:  # How the task was started: 0 in the app, 1 by a schedule
                    self._scheduled = int(value) == START_MODE_SCHEDULE
                elif piid == 13:  # Charging events during mission
                    # List of [timestamp, duration_minutes] pairs for charging sessions
                    # Example: [[1759318403, 24], [1759328060, 24]]
                    self._charging_events = value
                elif piid == 14:  # Planned area for the mowing session in m²
                    self._planned_area_sqm = int(value)
                elif piid == 15:  # Unknown field 15
                    self._unknown_field_15 = int(value)
                elif piid == 60:  # Stop reason (101 = low battery / returned to dock early)
                    self._stop_reason = int(value)
                elif piid == 16:  # Map name/identifier
                    self._map_name = str(value)
                else:
                    # Patrols and newer firmware report more; what is not
                    # read here does not spoil the rest.
                    _LOGGER.debug("Mission completion event piid %s not read: %r", piid, value)
            
            if older_firmware:
                if self._area_sqm is not None:
                    self._area_sqm *= 100
                if self._status in (0, STATUS_INTERRUPTED):
                    self._status = STATUS_INTERRUPTED - self._status

            # Create notification data
            event_data = self._get_notification_data()
            notify_callback(MISSION_COMPLETION_EVENT_PROPERTY_NAME, event_data)
            return True
            
        except Exception as ex:
            _LOGGER.error("Failed to parse mission completion event: %s", ex)
            return False
    
    def _reset_values(self) -> None:
        """Reset all stored values."""
        self._task_mode = None
        self._duration_minutes = None
        self._area_sqm = None
        self._status = None
        self._start_timestamp = None
        self._data_file_path = None
        self._scheduled = None
        self._charging_events = None
        self._planned_area_sqm = None
        self._unknown_field_15 = None
        self._stop_reason = None
        self._map_name = None
    
    def _get_notification_data(self) -> Dict[str, Any]:
        """Get mission completion notification data for Home Assistant."""
        return {
            TASK_MODE_FIELD: self._task_mode,
            DURATION_FIELD: self._duration_minutes,
            AREA_FIELD: self._area_sqm,
            STATUS_FIELD: self._status,
            START_TIMESTAMP_FIELD: self._start_timestamp,
            DATA_FILE_PATH_FIELD: self._data_file_path,
            SCHEDULED_FIELD: self._scheduled,
            CHARGING_EVENTS_FIELD: self._charging_events,
            PLANNED_AREA_FIELD: self._planned_area_sqm,
            UNKNOWN_FIELD_15: self._unknown_field_15,
            STOP_REASON_FIELD: self._stop_reason,
            MAP_NAME_FIELD: self._map_name,
        }
   
    # Properties for direct access
    @property
    def status(self) -> int | None:
        """Return task completion status (piid 7): 1=FINISHED, 2=UNFINISHED, 3=INTERRUPTED."""
        return self._status

    @property
    def is_patrol(self) -> bool:
        """Return whether the task was a patrol rather than mowing."""
        return bool(self._task_mode and self._task_mode.endswith("_patrol"))

    @property
    def stop_reason(self) -> int | None:
        """Return why the mission ended (piid 60); 101 = low battery / returned to dock early."""
        return self._stop_reason

    @property
    def has_data_file(self) -> bool:
        """Return True if mission data file path is available."""
        return self._data_file_path is not None and self._data_file_path != ""
    
    @property
    def is_complete(self) -> bool | None:
        """Return True if the mission completed normally (not interrupted).

        Uses status (piid 7) as the primary signal:
        STATUS_FINISHED (1) → True; unfinished (2) or STATUS_INTERRUPTED (3) → False.
        Returns True when status is absent — assume normal completion.
        """
        if self._status is not None:
            return self._status == STATUS_FINISHED
        return True
    
    def download_data_file(self, get_file_download_url: Callable[[str], str | None], hass_config_dir: str) -> bool:
        """Download the mission data file and save it to the HA config directory.

        The file is saved mirroring the directory structure of its path, where
        the work log details read it from.

        Args:
            get_file_download_url: A function that takes a file path and returns a download URL.
            hass_config_dir: The path to the Home Assistant configuration directory.

        Returns:
            True if the file was downloaded, False otherwise.
        """
        if not self.has_data_file or self._data_file_path is None:
            _LOGGER.warning("No mission data file path available to download.")
            return False

        result = download_file(
            file_path=self._data_file_path,
            get_download_url=get_file_download_url,
            hass_config_dir=hass_config_dir,
            timeout=15
        )
        return bool(result)
