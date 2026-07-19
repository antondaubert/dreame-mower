"""Device communication layer for Dreame Mower Implementation.

This module provides the device abstraction for communicating with the Dreame Mower.
It handles MQTT/Cloud API connections and device state management.

TODO: Add error handling for network failures
TODO: Implement connection retry logic
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from enum import Enum
import json
import logging
import os
from typing import Any, Callable
from datetime import datetime

from .cloud.cloud_device import DreameMowerCloudDevice
from .map_data_parser import MowerVectorMap, parse_batch_map_data
from .utils import download_file
from .property import (
    MiscPropertyHandler,
    DeviceCodeHandler,
    SchedulingPropertyHandler,
    MowerControlPropertyHandler,
    Service5PropertyHandler,
    MissionCompletionEventHandler,
    PoseCoveragePropertyHandler,
    DEVICE_CODE_ERROR_PROPERTY_NAME,
    DEVICE_CODE_WARNING_PROPERTY_NAME,
    DEVICE_CODE_INFO_PROPERTY_NAME,
    POSE_COVERAGE_PROGRESS_PROPERTY_NAME,
    POSE_COVERAGE_COORDINATES_PROPERTY_NAME,
)
from .const import (
    BATTERY_PROPERTY,
    STATUS_PROPERTY,
    BLUETOOTH_PROPERTY,
    SCHEDULING_TASK_PROPERTY,
    SCHEDULING_SUMMARY_PROPERTY,
    MOWER_CONTROL_STATUS_PROPERTY,
    POWER_STATE_PROPERTY,
    SERVICE2_PROPERTY_53,
    SERVICE2_PROPERTY_54,
    SERVICE2_PROPERTY_55,
    SERVICE2_PROPERTY_60,
    SERVICE2_PROPERTY_62,
    SERVICE2_PROPERTY_63,
    SERVICE2_PROPERTY_64,
    SERVICE2_PROPERTY_65,
    SERVICE2_PROPERTY_66,
    SERVICE2_PROPERTY_67,
    FIRMWARE_INSTALL_STATE_PROPERTY,
    FIRMWARE_DOWNLOAD_PROGRESS_PROPERTY,
    POSE_COVERAGE_PROPERTY,
    SERVICE1_PROPERTY_50,
    SERVICE1_PROPERTY_51,
    SERVICE1_COMPLETION_FLAG_PROPERTY,
    SERVICE1_PROPERTY_54,
    SERVICE1_PROPERTY_55,
    STATUS_MAPPING,
    PROPERTY_FIRMWARE,
    CHARGING_STATUS_PROPERTY,
    CHARGING_STATUS_MAPPING,
    TASK_STATUS_PROPERTY,
    FIRMWARE_INSTALL_STATE_MAPPING,
    SERVICE5_PROPERTY_100,
    SERVICE5_PROPERTY_101,
    SERVICE5_PROPERTY_105,
    SERVICE5_PROPERTY_106,
    SERVICE5_ENERGY_INDEX_PROPERTY,
    SERVICE5_PROPERTY_108,
    SERVICE6_PROPERTY_1,
    SERVICE6_PROPERTY_3,
    DEVICE_FILE_PATH_PROPERTY,
    DEVICE_FILE_PATH_PROPERTY_20,
    FIRMWARE_VALIDATION_EVENT,
    MISSION_COMPLETION_EVENT,
    ACTION_START_MOWING,
    ACTION_PAUSE,
    ACTION_STOP,
    ACTION_DOCK,
    TASK_PAYLOAD_RESUME,
    DEVICE_CODE_PROPERTY,
    PROPERTY_1_1,
    DeviceStatus,
)

_LOGGER = logging.getLogger(__name__)

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
    """

    def __init__(
        self,
        device_id: str,
        username: str,
        password: str,
        account_type: str,
        country: str,
        hass_config_dir: str,
    ) -> None:
        """Initialize the device handler.
        
        Args:
            device_id: Unique device identifier
            username: Username for device authentication
            password: Password for device authentication
            account_type: Account type for cloud authentication
            country: Country for cloud authentication
            hass_config_dir: The path to the Home Assistant configuration directory.
        """
        self._device_id = device_id
        self._username = username
        self._password = password
        self._account_type = account_type
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
        
        # MQTT properties
        self._bluetooth_connected: bool | None = None
        self._charging_status: str | None = None
        self._ota_state: str | None = None
        self._ota_progress: int | None = None
        self._device_file_path: str | None = None
        self._firmware_install_state: int | None = None
        self._firmware_download_progress: int | None = None
        self._firmware_new_available: bool = False
        self._firmware_latest_version: str | None = None
        self._service1_property_50: bool = False
        self._service1_property_51: bool = False
        self._service1_completion_flag: bool = False
        
        # Property handlers
        self._misc_handler = MiscPropertyHandler()
        self._device_code_handler = DeviceCodeHandler()
        self._scheduling_handler = SchedulingPropertyHandler()
        self._mower_control_handler = MowerControlPropertyHandler()
        self._service5_handler = Service5PropertyHandler()
        self._mission_completion_handler = MissionCompletionEventHandler()
        self._pose_coverage_handler = PoseCoveragePropertyHandler()
        
        # Vector map from batch API
        self._vector_map: MowerVectorMap | None = None
        self._current_map_id: int | None = None

        # Property change callbacks
        self._property_callbacks: list[Callable[[str, Any], None]] = []
        
        # Stop-then-dock sequence - wait for mission completion event
        self._mission_completed_event: asyncio.Event = asyncio.Event()

    @property
    def connected(self) -> bool:
        """Return True if device is connected."""
        return self._cloud_device.connected

    @property
    def device_reachable(self) -> bool:
        """Return True if device is reachable via cloud API."""
        return self._cloud_device.device_reachable

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
    def task_status(self) -> str | None:
        """Return the current mowing task status decoded from the heartbeat."""
        return self._misc_handler.task_status

    @property
    def mowing_session_active(self) -> bool:
        """Return True while a mowing session is in progress (used by the live map)."""
        return self._misc_handler.mowing_session_active

    @property
    def bluetooth_connected(self) -> bool | None:
        """Return Bluetooth connection status."""
        return self._bluetooth_connected
    
    @property
    def firmware_install_state(self) -> int | None:
        """Return firmware installation state (1:2)."""
        return self._firmware_install_state
    
    @property
    def firmware_download_progress(self) -> int | None:
        """Return firmware download progress in percent (1:3)."""
        return self._firmware_download_progress

    @property
    def firmware_update_available(self) -> bool:
        """Return whether the cloud reports a newer firmware than installed."""
        return self._firmware_new_available

    @property
    def firmware_latest_version(self) -> str | None:
        """Return the latest available firmware version, if any."""
        return self._firmware_latest_version
    
    @property
    def service1_property_50(self) -> bool:
        """Return Service 1 property 50 status (1:50) - session start indicator."""
        return self._service1_property_50
    
    @property
    def service1_property_51(self) -> bool:
        """Return Service 1 property 51 status (1:51) - session start indicator."""
        return self._service1_property_51
    
    @property
    def service1_completion_flag(self) -> bool:
        """Return Service 1 completion flag status (1:52)."""
        return self._service1_completion_flag

    @property
    def ota_state(self) -> str | None:
        """Return Over-The-Air update state."""
        return self._ota_state

    @property
    def ota_progress(self) -> int | None:
        """Return Over-The-Air update progress (0-100)."""
        return self._ota_progress

    @property
    def device_file_path(self) -> str | None:
        """Return device file path (firmware packages or log files)."""
        return self._device_file_path

    @property
    def ota_package_path(self) -> str | None:
        """Return device file path (backward compatibility alias)."""
        return self._device_file_path

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
    def service5_property_105(self) -> int | None:
        """Return Service 5 property 105 value."""
        return self._service5_handler.property_105_value
    
    @property
    def energy_index(self) -> int | None:
        """Return energy/discharge index (5:107)."""
        return self._service5_handler.energy_index
    
    @property
    def service5_property_108(self) -> int | None:
        """Return Service 5 property 108 value."""
        return self._service5_handler.property_108_value

    @property
    def device_code(self) -> int | None:
        """Return current device code (2:2)."""
        return self._device_code_handler.device_code

    @property
    def device_code_name(self) -> str | None:
        """Return device code name."""
        return self._device_code_handler.device_code_name

    @property
    def device_code_description(self) -> str | None:
        """Return device code description."""
        return self._device_code_handler.device_code_description

    @property
    def device_code_is_error(self) -> bool | None:
        """Return True if device code represents an error."""
        return self._device_code_handler.device_code_is_error

    @property
    def device_code_is_warning(self) -> bool | None:
        """Return True if device code represents a warning."""
        return self._device_code_handler.device_code_is_warning

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
        """Return path history for visualization (list of [x, y] in map units)."""
        return self._pose_coverage_handler.path_history

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
        """Return the current vector map data from batch API."""
        return self._resolved_vector_map()

    @property
    def available_maps(self) -> list[dict[str, Any]]:
        """Return map descriptors discovered in batch map data."""
        if self._vector_map is None:
            return []

        return [
            {
                "id": map_entry.map_id,
                "index": map_entry.map_index,
                "name": map_entry.name,
                "area": map_entry.total_area,
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
    def task_target_map_id(self) -> int | None:
        """Return the map identifier targeted by the active task, if present."""
        task_handler = self._scheduling_handler._task_handler
        if task_handler.region_id:
            return int(task_handler.region_id[0])

        return None

    def fetch_vector_map(self) -> bool:
        """Fetch vector map data from the batch device data API.

        Requests all keys from the cloud batch API and parses
        MAP.* and M_PATH.* into a MowerVectorMap.

        Returns:
            True if map data was updated, False otherwise.
        """
        try:
            # Pass empty list to get all available keys (MAP.*, M_PATH.*, etc.)
            # The API returns all keys when no specific keys are requested.
            # M_PATH can have 28+ chunks depending on path history size.
            batch_data = self._cloud_device.get_batch_device_datas([])
            if not batch_data:
                _LOGGER.debug("No batch data returned from cloud API")
                return False

            vector_map = parse_batch_map_data(batch_data)
            if vector_map is None:
                _LOGGER.debug("Failed to parse batch map data")
                return False

            self._vector_map = vector_map
            self.refresh_current_map_id()
            active_vector_map = self._resolved_vector_map() or vector_map
            _LOGGER.debug(
                "Vector map updated: %d zones, %d paths, boundary=%s",
                len(active_vector_map.zones),
                len(active_vector_map.paths),
                active_vector_map.boundary,
            )
            self._notify_property_change("vector_map_updated", True)
            return True

        except Exception as ex:
            _LOGGER.warning("Failed to fetch vector map from batch API: %s", ex)
            return False

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

        self._firmware_latest_version = latest
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

    def _notify_property_change(self, property_name: str, value: Any) -> None:
        """Notify all registered callbacks of property changes."""
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
            
            # Extract and set device model for device code handler
            if "model" in device_info:
                model = device_info["model"]
                self._device_code_handler.set_model(model)
            
            # Update last update timestamp
            self._last_update = datetime.now()
        except Exception as ex:
            _LOGGER.error("Failed to update device state from info: %s", ex)

    def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming MQTT messages from cloud device."""
        # Update last update timestamp
        self._last_update = datetime.now()
        
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

        # Create notification for unhandled message types with raw message
        _LOGGER.info("📨 Unhandled MQTT message: %s", message)
        self._notify_property_change(
            "unhandled_mqtt",
            {
                "type": "message",
                "raw_message": message,
                "event_time": datetime.now().isoformat()
            }
        )

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
                # Handle scheduling properties (2:50, 2:52) in unified handler
                if not self._scheduling_handler.handle_property_update(siid, piid, message["value"], self._notify_property_change):
                    return False  # Parsing failed - treat as unhandled property
            elif MOWER_CONTROL_STATUS_PROPERTY.matches(siid, piid):
                # Handle mower control status property (2:56)
                if not self._mower_control_handler.handle_property_update(siid, piid, message["value"], self._notify_property_change):
                    return False  # Parsing failed - treat as unhandled property
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
                # Handle firmware installation state property (1:2) - firmware update status
                # Values: 2 = New Firmware Available, 3 = Installing firmware after download
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
                # Handle Service 1 property 50 (1:50) - appears at beginning of session
                # Note: This property typically has no value field, just presence indicates start event
                self._service1_property_50 = True
                self._notify_property_change(SERVICE1_PROPERTY_50.name, True)
                _LOGGER.debug("Service 1 property 50 triggered - session start indicator")
            elif SERVICE1_PROPERTY_51.matches(siid, piid):
                # Handle Service 1 property 51 (1:51) - appears at beginning of session
                # Note: This property typically has no value field, just presence indicates start event
                self._service1_property_51 = True
                self._notify_property_change(SERVICE1_PROPERTY_51.name, True)
                _LOGGER.debug("Service 1 property 51 triggered - session start indicator")
            elif SERVICE1_COMPLETION_FLAG_PROPERTY.matches(siid, piid):
                # Handle Service 1 completion flag (1:52) - appears after mission completion
                # Note: This property typically has no value field, just presence indicates completion
                self._service1_completion_flag = True
                self._notify_property_change(SERVICE1_COMPLETION_FLAG_PROPERTY.name, True)
            elif SERVICE1_PROPERTY_54.matches(siid, piid):
                # Handle Service 1 property 54 (1:54) - device metadata payload containing identifiers
                # Observed fields include active_time, expire_time, num, and sn (issue #64).
                # Silently acknowledge to suppress unhandled MQTT notifications.
                _LOGGER.debug("Service 1 property 54 received: %s", message.get("value"))
            elif SERVICE1_PROPERTY_55.matches(siid, piid):
                # Handle Service 1 property 55 (1:55) - integer value.
                # Observed on dreame.mower.g2541e fw 4.3.6_0407 with value 1 (issue #82).
                # Meaning unknown; silently acknowledge to suppress unhandled MQTT notifications.
                _LOGGER.debug("Service 1 property 55 received: %s", message.get("value"))
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
            elif (TASK_STATUS_PROPERTY.matches(siid, piid) or
                  SERVICE5_PROPERTY_100.matches(siid, piid) or
                  SERVICE5_PROPERTY_101.matches(siid, piid) or
                  SERVICE5_PROPERTY_105.matches(siid, piid) or 
                  SERVICE5_PROPERTY_106.matches(siid, piid) or 
                  SERVICE5_ENERGY_INDEX_PROPERTY.matches(siid, piid) or
                  SERVICE5_PROPERTY_108.matches(siid, piid)):
                # Handle all Service 5 properties (5:100, 5:101, 5:104, 5:105, 5:106, 5:107, 5:108) in unified handler
                if not self._service5_handler.handle_property_update(siid, piid, message["value"], self._notify_property_change):
                    return False  # Parsing failed - treat as unhandled property
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
            elif SERVICE2_PROPERTY_60.matches(siid, piid):
                # Handle Service 2 property 60 (2:60) - simple integer value
                property_value = int(message["value"])
                self._notify_property_change(SERVICE2_PROPERTY_60.name, property_value)
                _LOGGER.debug("Service 2 property 60 updated: %s", property_value)
            elif SERVICE2_PROPERTY_62.matches(siid, piid):
                # Handle Service 2 property 62 (2:62) - simple integer value
                property_value = int(message["value"])
                self._notify_property_change(SERVICE2_PROPERTY_62.name, property_value)
                _LOGGER.debug("Service 2 property 62 updated: %s", property_value)
            elif SERVICE2_PROPERTY_63.matches(siid, piid):
                # Handle Service 2 property 63 (2:63) - negative integer error/status code (see issue #12)
                # Observed values: -33101 (mova.mower.g2405a fw 4.3.6_0430), -33001 — meaning unknown.
                # Silently acknowledge to suppress unhandled MQTT notifications.
                _LOGGER.debug("Service 2 property 63 received: %s", message.get("value"))
            elif SERVICE2_PROPERTY_53.matches(siid, piid):
                # Handle Service 2 property 53 (2:53) - meaning unknown, only value seen so far is 100
                # Silently acknowledge to suppress unhandled MQTT notifications (see issue #52)
                _LOGGER.debug("Service 2 property 53 received: %s", message.get("value"))
            elif SERVICE2_PROPERTY_54.matches(siid, piid):
                # Handle Service 2 property 54 (2:54) - meaning unknown, only value seen so far is 100
                # Silently acknowledge to suppress unhandled MQTT notifications (see issue #25)
                _LOGGER.debug("Service 2 property 54 received: %s", message.get("value"))
            elif SERVICE2_PROPERTY_55.matches(siid, piid):
                # Handle Service 2 property 55 (2:55) - likely AI obstacle detection notification
                # Value contains {"type": "ai", "obs": [x, y, w, class_id, timestamp]}
                # Silently acknowledge to suppress unhandled MQTT notifications (see issue #32)
                _LOGGER.debug("Service 2 property 55 (AI obstacle detection) received: %s", message.get("value"))
            elif SERVICE2_PROPERTY_64.matches(siid, piid):
                # Handle Service 2 property 64 (2:64) - work statistics
                # Contains complex data about current week (cw), full week (fw), position (p), work range (wr/ws), etc.
                # For now, just acknowledge receipt to prevent unhandled MQTT notifications
                property_value = message["value"]
                self._notify_property_change(SERVICE2_PROPERTY_64.name, property_value)
                _LOGGER.debug("Service 2 property 64 (work statistics) updated")
            elif SERVICE2_PROPERTY_65.matches(siid, piid):
                # Handle Service 2 property 65 (2:65) - task navigation/SLAM status
                # Known values: dm::TASK_NAV_DOCK (returning to dock), dm::TASK_SLAM_RELOCATE (mower relocating after getting stuck, issue #37)
                #               dm::TASK_NAV_DIVIDE_REGION (region division navigation)
                #               dm::TASK_SLAM_RELOCATE_NEARDOCK (mower relocating near dock, issue #54)
                #               dm::TASK_NAV_CRUISE_POINT (navigation to cruise point, issue #68)
                #               dm::TASK_SLAM_EXIT_ERASE (SLAM exit erase, issue #60)
                #               dm::TASK_SLAM_RELOCATE_OFFDOCK (mower relocating off dock, issue #93)
                #               TASK_NAV_CHECK (navigation check, no dm:: prefix, issue #81)
                # TODO: Consider doing something useful with this property change later
                property_value_str = str(message["value"])
                if property_value_str in ("dm::TASK_NAV_DOCK", "dm::TASK_SLAM_RELOCATE", "dm::TASK_NAV_DIVIDE_REGION", "dm::TASK_SLAM_RELOCATE_NEARDOCK", "dm::TASK_NAV_CRUISE_POINT", "dm::TASK_SLAM_EXIT_ERASE", "dm::TASK_SLAM_RELOCATE_OFFDOCK", "TASK_NAV_CHECK"):
                    self._notify_property_change(SERVICE2_PROPERTY_65.name, property_value_str)
                    _LOGGER.debug("2:65 value: %s", property_value_str)
                else:
                    _LOGGER.debug("Unrecognized 2:65 value: %s", property_value_str)
                    return False  # Report false for unrecognized values
            elif SERVICE2_PROPERTY_66.matches(siid, piid):
                # Handle Service 2 property 66 (2:66) - 2-integer array, reported on mova.mower.g2529d fw 4.3.6_0169
                # Meaning unknown; silently acknowledge to suppress unhandled MQTT notifications (issue #48)
                _LOGGER.debug("Service 2 property 66 received: %s", message.get("value"))
            elif SERVICE2_PROPERTY_67.matches(siid, piid):
                # Handle Service 2 property 67 (2:67) - 4-integer array, observed after MOWING_COMPLETED
                # Meaning unknown; silently acknowledge to suppress unhandled MQTT notifications (issues #34, #35, #36, #38)
                _LOGGER.debug("Service 2 property 67 received: %s", message.get("value"))
            elif SERVICE6_PROPERTY_1.matches(siid, piid):
                # Handle Service 6 property 1 (6:1) - integer value.
                # Observed on dreame.mower.g2541e fw 4.3.6_0407 with value 200 (issue #71).
                # Meaning is still unknown; silently acknowledge to suppress repeated issue noise.
                _LOGGER.debug("Service 6 property 1 received: %s", message.get("value"))
            elif SERVICE6_PROPERTY_3.matches(siid, piid):
                # Handle Service 6 property 3 (6:3) - 2-item [bool, int] array.
                # Observed on dreame.mower.g2541e fw 4.3.6_0407 with value [False, -128] (issue #78).
                # Meaning is still unknown; silently acknowledge to suppress repeated issue noise.
                _LOGGER.debug("Service 6 property 3 received: %s", message.get("value"))
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
                if handled:
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
                        self._mission_completion_handler.download_and_set_data_file(
                            self._cloud_device.get_file_download_url, self._hass_config_dir
                        )
                return handled

            _LOGGER.warning("Unhandled event %d:%d with arguments: %s", siid, eiid, arguments)
            return False
            
        except Exception as ex:
            _LOGGER.error("Failed to handle MQTT event: %s", ex)
            return False

    def _handle_mqtt_props(self, params: dict[str, Any]) -> bool:
        """Handle MQTT props messages with direct property updates."""
        handled_any = False
        
        try:
            # Handle individual properties in the params dict
            for key, value in params.items():
                if key == "ota_state":
                    # Handle OTA state updates
                    old_ota_state = getattr(self, '_ota_state', None)
                    self._ota_state = value
                    if old_ota_state != value:
                        self._notify_property_change("ota_state", value)
                        _LOGGER.debug("OTA state updated: %s", value)
                    handled_any = True
                elif key == "ota_progress":
                    # Handle OTA download progress (0-100) - see issue #19
                    old_progress = self._ota_progress
                    self._ota_progress = int(value)
                    if old_progress != self._ota_progress:
                        self._notify_property_change("ota_progress", self._ota_progress)
                        _LOGGER.debug("OTA progress updated: %s%%", self._ota_progress)
                    handled_any = True
                else:
                    # Log unhandled properties for future implementation
                    _LOGGER.debug("Unhandled props parameter: %s = %s", key, value)
            
            return handled_any
            
        except Exception as ex:
            _LOGGER.error("Failed to handle MQTT props: %s", ex)
            return False

    def _handle_connected(self) -> None:
        """Handle cloud device connection established."""
        self._last_update = datetime.now()
        self._notify_property_change("connected", True)

    def _handle_disconnected(self) -> None:
        """Handle cloud device disconnection."""
        _LOGGER.warning("Cloud device disconnected for %s", self._device_id)
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
            self._notify_property_change("connected", False)
        except Exception as ex:
            _LOGGER.error("Error disconnecting from device %s: %s", self._device_id, ex)

    async def start_mowing_generic(self) -> bool:
        """Start mowing via the generic cloud action, letting the device pick the area.

        This mirrors the pre-map-aware behaviour: it sends the bare 5:1
        START_MOWING action and lets the robot run whatever is configured in the
        app. Used as an all-area fallback when the map-aware payload fails.
        """
        if not await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._cloud_device.execute_action(ACTION_START_MOWING)
        ):
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
        spot_rectangle: dict[str, int | float] | None = None,
    ) -> bool:
        """Start mowing using the public mode-oriented entrypoint."""
        return await self.start_mowing_mode(
            mode,
            map_id=map_id,
            zone_ids=zone_ids,
            contour_ids=contour_ids,
            spot_area_ids=spot_area_ids,
            spot_rectangle=spot_rectangle,
        )

    def supports_mowing_mode(self, mode: MowingMode) -> bool:
        """Return whether a mowing mode has a outbound command path."""
        return mode in {
            MowingMode.ALL_AREA,
            MowingMode.EDGE,
            MowingMode.SPOT,
            MowingMode.ZONE,
        }

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
            "t": "MAPL",
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

        if self._current_map_id != current_map_id:
            self._current_map_id = current_map_id
            self._notify_property_change("current_map_id", current_map_id)

        return True

    def _build_all_area_task_payload(self, map_id: int) -> dict[str, Any]:
        """Build the 2:50 action payload for map-aware all-area mowing."""
        return {
            "m": "a",
            "p": 0,
            "o": 100,
            "d": {
                "region_id": [map_id],
                "area_id": [],
            },
        }

    def _build_set_current_map_payload(self, map_index: int) -> dict[str, Any]:
        """Build the 2:50 action payload for switching the active map."""
        return {
            "m": "a",
            "p": 0,
            "o": 200,
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

    def _build_zone_task_payload(self, zone_ids: list[int]) -> dict[str, Any]:
        """Build the 2:50 action payload for a zone-selective mowing session."""
        return {
            "m": "a",
            "p": 0,
            "o": 102,
            "d": {
                "region": zone_ids,
            },
        }

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

    def _build_spot_rectangle_payload(
        self,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
    ) -> dict[str, Any]:
        """Build the 2:50 action payload for defining a rectangular spot area."""
        return {
            "m": "a",
            "p": 0,
            "o": 214,
            "d": {
                "id": -1,
                "points": [
                    [round(x_max, 2), round(y_min, 2)],
                    [round(x_min, 2), round(y_min, 2)],
                    [round(x_min, 2), round(y_max, 2)],
                    [round(x_max, 2), round(y_max, 2)],
                ],
            },
        }

    def _build_apply_spot_selection_payload(self) -> dict[str, Any]:
        """Build the 2:50 action payload for applying a prepared spot selection."""
        return {
            "m": "a",
            "p": 1,
            "o": 201,
        }

    def _map_bounds_in_meters(self) -> tuple[float, float, float, float] | None:
        """Return map bounds in meters when vector-map geometry is available."""
        vector_map = self.vector_map
        if vector_map is None:
            return None

        if vector_map.boundary is not None:
            return (
                vector_map.boundary.x1 / 100.0,
                vector_map.boundary.y1 / 100.0,
                vector_map.boundary.x2 / 100.0,
                vector_map.boundary.y2 / 100.0,
            )

        all_paths: Sequence[Iterable[tuple[int, int]]] = [
            zone.path for zone in vector_map.zones
        ] + [
            zone.path for zone in vector_map.forbidden_areas
        ] + [
            path.path for path in vector_map.paths
        ] + [
            contour.path for contour in vector_map.contours
        ] + [
            spot_area.path for spot_area in vector_map.spot_areas
        ]

        points = [point for path in all_paths for point in path]
        if not points:
            return None

        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]
        return (
            min(x_values) / 100.0,
            min(y_values) / 100.0,
            max(x_values) / 100.0,
            max(y_values) / 100.0,
        )

    def _normalize_spot_rectangle(
        self,
        spot_rectangle: dict[str, int | float],
    ) -> tuple[float, float, float, float] | None:
        """Validate and normalize a spot rectangle expressed in meters."""
        required_keys = ("x1", "y1", "x2", "y2")
        missing_keys = [key for key in required_keys if key not in spot_rectangle]
        if missing_keys:
            _LOGGER.error(
                "Spot rectangle is missing required keys %s: %s",
                missing_keys,
                spot_rectangle,
            )
            return None

        try:
            x1 = float(spot_rectangle["x1"])
            y1 = float(spot_rectangle["y1"])
            x2 = float(spot_rectangle["x2"])
            y2 = float(spot_rectangle["y2"])
        except (TypeError, ValueError) as ex:
            _LOGGER.error("Spot rectangle must contain numeric coordinates %s: %s", spot_rectangle, ex)
            return None

        x_min, x_max = sorted((x1, x2))
        y_min, y_max = sorted((y1, y2))

        if x_max - x_min < 1.0 or y_max - y_min < 1.0:
            _LOGGER.error(
                "Spot rectangle must be at least 1m x 1m; got %.2fm x %.2fm: %s",
                x_max - x_min,
                y_max - y_min,
                spot_rectangle,
            )
            return None

        map_bounds = self._map_bounds_in_meters()
        if map_bounds is not None:
            map_x_min, map_y_min, map_x_max, map_y_max = map_bounds
            overlaps_map = (
                x_max > map_x_min
                and x_min < map_x_max
                and y_max > map_y_min
                and y_min < map_y_max
            )
            if not overlaps_map:
                _LOGGER.error(
                    "Spot rectangle must overlap the known map extent %s; got: %s",
                    map_bounds,
                    spot_rectangle,
                )
                return None

        return (x_min, y_min, x_max, y_max)

    def _spot_area_matches_rectangle(
        self,
        spot_area: Any,
        rectangle_bounds: tuple[float, float, float, float],
        tolerance_m: float = 0.15,
    ) -> bool:
        """Return True when a spot area's geometry matches the requested rectangle."""
        if not getattr(spot_area, "path", None):
            return False

        x_values = [point[0] / 100.0 for point in spot_area.path]
        y_values = [point[1] / 100.0 for point in spot_area.path]
        spot_bounds = (min(x_values), min(y_values), max(x_values), max(y_values))

        return all(
            abs(actual - expected) <= tolerance_m
            for actual, expected in zip(spot_bounds, rectangle_bounds)
        )

    def _resolve_spot_area_id_from_rectangle(
        self,
        previous_spot_area_ids: set[int],
        rectangle_bounds: tuple[float, float, float, float],
    ) -> int | None:
        """Resolve the spot-area ID created from a rectangle after a map refresh."""
        vector_map = self.vector_map
        if vector_map is None:
            return None

        new_spot_areas = [
            spot_area
            for spot_area in vector_map.spot_areas
            if spot_area.area_id not in previous_spot_area_ids
        ]
        if len(new_spot_areas) == 1:
            return int(new_spot_areas[0].area_id)

        matching_new_spot_areas = [
            spot_area
            for spot_area in new_spot_areas
            if self._spot_area_matches_rectangle(spot_area, rectangle_bounds)
        ]
        if len(matching_new_spot_areas) == 1:
            return int(matching_new_spot_areas[0].area_id)

        matching_spot_areas = [
            spot_area
            for spot_area in vector_map.spot_areas
            if self._spot_area_matches_rectangle(spot_area, rectangle_bounds)
        ]
        if len(matching_spot_areas) == 1:
            return int(matching_spot_areas[0].area_id)

        return None

    async def start_mowing_all_area(self, map_id: int | None = None) -> bool:
        """Start all-area mowing, optionally targeting a specific map identifier."""
        if map_id is None:
            map_id = self.current_map_id

        if map_id is None:
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.refresh_current_map_id)
            except Exception as ex:
                _LOGGER.debug("Failed to refresh current map before all-area start fallback: %s", ex)

            map_id = self.current_map_id

        if map_id is None:
            _LOGGER.warning(
                "All-area mowing fell back to the generic START_MOWING action because no map_id was provided"
            )
            return await self.start_mowing_generic()

        if not self._validate_map_id(map_id):
            return False

        task_payload = self._build_all_area_task_payload(map_id)
        try:
            result = await self._send_task_payload("all-area mowing", task_payload)
        except Exception as ex:
            _LOGGER.error("Failed to send start_mowing_all_area command: %s", ex)
            return False

        if not result:
            _LOGGER.error("start_mowing_all_area command returned falsy result: %s", result)
            return False

        _LOGGER.info("All-area mowing started for map ID: %s", map_id)
        self._pose_coverage_handler.reset_mission_completion()
        self._notify_property_change("activity", "mowing")
        return True

    async def set_current_map(self, map_id: int) -> bool:
        """Switch the mower's current map using the map-switch payload."""
        if not self._validate_map_id(map_id):
            return False

        map_index = self._map_index_from_id(map_id)
        task_payload = self._build_set_current_map_payload(map_index)
        try:
            result = await self._send_task_payload("map switch", task_payload)
        except Exception as ex:
            _LOGGER.error("Failed to send set_current_map command: %s", ex)
            return False

        if not result:
            _LOGGER.error("set_current_map command returned falsy result: %s", result)
            return False

        self._current_map_id = map_id
        _LOGGER.info("Current map switched to map ID %s (index %s)", map_id, map_index)
        self._notify_property_change("current_map_id", map_id)
        return True

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
        """Send a scheduling task payload via action 2:50."""
        _LOGGER.debug(
            "Sending %s action %s:%s with payload: %s",
            task_name,
            SCHEDULING_TASK_PROPERTY.siid,
            SCHEDULING_TASK_PROPERTY.piid,
            task_payload,
        )
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._cloud_device.action(
                SCHEDULING_TASK_PROPERTY.siid,
                SCHEDULING_TASK_PROPERTY.piid,
                [task_payload],
            ),
        )

    async def start_mowing_zones(self, zone_ids: list[int]) -> bool:
        """Start mowing specific zones by their IDs."""
        if not zone_ids:
            _LOGGER.error("start_mowing_zones called with empty zone_ids")
            return False

        if not self._validate_zone_ids(zone_ids):
            return False

        task_payload = self._build_zone_task_payload(zone_ids)
        try:
            result = await self._send_task_payload("zone mowing", task_payload)
        except Exception as ex:
            _LOGGER.error("Failed to send start_mowing_zones command: %s", ex)
            return False

        if not result:
            _LOGGER.error("start_mowing_zones command returned falsy result: %s", result)
            return False

        _LOGGER.info("Zone mowing started for zones: %s", zone_ids)
        self._pose_coverage_handler.reset_mission_completion()
        self._notify_property_change("activity", "mowing")
        return True

    async def start_mowing_edges(self, contour_ids: list[list[int]]) -> bool:
        """Start edge mowing for specific contours.

        Contour IDs are two-integer pairs such as [[1, 0], [2, 0]]. They match
        entries in the batch map device data under MAP.* -> contours.value, where
        each contour entry is keyed by an ID pair like [1, 0]. In Home Assistant,
        these IDs are exposed in the mower entity's contours state attribute after
        the map has been fetched.
        """
        if not contour_ids:
            _LOGGER.error("start_mowing_edges called with empty contour_ids")
            return False

        if not self._validate_contour_ids(contour_ids):
            return False

        task_payload = self._build_edge_task_payload(contour_ids)
        try:
            result = await self._send_task_payload("edge mowing", task_payload)
        except Exception as ex:
            _LOGGER.error("Failed to send start_mowing_edges command: %s", ex)
            return False

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
        try:
            result = await self._send_task_payload("spot mowing", task_payload)
        except Exception as ex:
            _LOGGER.error("Failed to send start_mowing_spots command: %s", ex)
            return False

        if not result:
            _LOGGER.error("start_mowing_spots command returned falsy result: %s", result)
            return False

        _LOGGER.info("Spot mowing started for spot areas: %s", spot_area_ids)
        self._pose_coverage_handler.reset_mission_completion()
        self._notify_property_change("activity", "mowing")
        return True

    async def create_spot_area(self, spot_rectangle: dict[str, int | float]) -> int | None:
        """Create a spot area from a rectangle and return its resolved area id."""
        normalized_rectangle = self._normalize_spot_rectangle(spot_rectangle)
        if normalized_rectangle is None:
            return None

        previous_spot_area_ids = (
            {spot_area.area_id for spot_area in self.vector_map.spot_areas}
            if self.vector_map is not None
            else set()
        )

        create_payload = self._build_spot_rectangle_payload(*normalized_rectangle)
        try:
            create_result = await self._send_task_payload("spot area create", create_payload)
        except Exception as ex:
            _LOGGER.error("Failed to send spot area create command: %s", ex)
            return None

        if not create_result:
            _LOGGER.error("spot area create command returned falsy result: %s", create_result)
            return None

        apply_payload = self._build_apply_spot_selection_payload()
        try:
            apply_result = await self._send_task_payload("spot area apply", apply_payload)
        except Exception as ex:
            _LOGGER.error("Failed to send spot area apply command: %s", ex)
            return None

        if not apply_result:
            _LOGGER.error("spot area apply command returned falsy result: %s", apply_result)
            return None

        created_spot_area_id = None
        for _ in range(3):
            await asyncio.get_event_loop().run_in_executor(None, self.fetch_vector_map)
            created_spot_area_id = self._resolve_spot_area_id_from_rectangle(
                previous_spot_area_ids,
                normalized_rectangle,
            )
            if created_spot_area_id is not None:
                _LOGGER.info(
                    "Spot area created from rectangle %s with resolved area id %s",
                    spot_rectangle,
                    created_spot_area_id,
                )
                return created_spot_area_id
            await asyncio.sleep(0.5)

        _LOGGER.error(
            "Spot rectangle was prepared successfully, but the created spot area ID could not be resolved from refreshed map data: %s",
            spot_rectangle,
        )
        return None

    async def start_mowing_spot(self, spot_area_ids: list[int] | None = None) -> bool:
        """Start spot mowing for one or more existing spot areas."""
        if not spot_area_ids:
            _LOGGER.error("Spot mowing requires at least one existing spot area ID")
            return False

        return await self.start_mowing_spots(spot_area_ids)

    async def start_mowing_mode(
        self,
        mode: MowingMode,
        *,
        map_id: int | None = None,
        zone_ids: list[int] | None = None,
        contour_ids: list[list[int]] | None = None,
        spot_area_ids: list[int] | None = None,
        spot_rectangle: dict[str, int | float] | None = None,
    ) -> bool:
        """Start mowing using an explicit mode-oriented API.

        Manual mode is represented explicitly so higher layers can model the full
        roadmap, but its outbound command format is still unverified.
        """
        if mode == MowingMode.ALL_AREA:
            return await self.start_mowing_all_area(map_id)

        if mode == MowingMode.ZONE:
            if not zone_ids:
                _LOGGER.error("Zone mowing requires at least one zone ID")
                return False
            return await self.start_mowing_zones(zone_ids)

        if mode == MowingMode.EDGE:
            if not contour_ids:
                _LOGGER.error("Edge mowing requires at least one contour ID")
                return False
            return await self.start_mowing_edges(contour_ids)

        if mode == MowingMode.SPOT:
            if spot_rectangle is not None:
                _LOGGER.error(
                    "Spot rectangle creation is separate from spot mowing; create the spot area first, then call spot mowing with spot_area_ids"
                )
                return False
            return await self.start_mowing_spot(
                spot_area_ids=spot_area_ids,
            )

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
    def spot_areas(self) -> list[dict]:
        """Return available spot-mowing area IDs from the vector map."""
        vector_map = self.vector_map
        if vector_map is None:
            return []
        return [
            {"id": spot_area.area_id, "name": spot_area.name, "area": spot_area.area}
            for spot_area in vector_map.spot_areas
        ]

    async def pause(self) -> bool:
        """Pause current operation."""
        if not await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._cloud_device.execute_action(ACTION_PAUSE)
        ):
            _LOGGER.error("Failed to send PAUSE command")
            return False
        self._notify_property_change("activity", "paused")
        return True

    async def dock_without_stopping(self) -> bool:
        """Send mower to dock without stopping the active task.

        Sends ACTION_DOCK directly, leaving any in-progress task intact so it
        can be resumed later via resume().

        Returns:
            True if the dock command was sent successfully, False otherwise.
        """
        if not await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._cloud_device.execute_action(ACTION_DOCK)
        ):
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
        if not await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._cloud_device.execute_action(ACTION_STOP)
        ):
            _LOGGER.error("Failed to send STOP command")
            return False
        
        self._notify_property_change("activity", "stopping")
        
        # Wait for MISSION_COMPLETION event (4:1) with 30-second timeout
        try:
            await asyncio.wait_for(self._mission_completed_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout waiting for mission completion event, sending DOCK anyway")
        
        # Send DOCK command
        if not await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._cloud_device.execute_action(ACTION_DOCK)
        ):
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
