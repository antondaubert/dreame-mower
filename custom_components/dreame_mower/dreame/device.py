"""Device communication layer for Dreame Mower Implementation.

This module provides the device abstraction for communicating with the Dreame Mower.
It handles MQTT/Cloud API connections and device state management.

TODO: Add error handling for network failures
TODO: Implement connection retry logic
"""

from __future__ import annotations

import asyncio
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
    SERVICE2_PROPERTY_54,
    SERVICE2_PROPERTY_55,
    SERVICE2_PROPERTY_60,
    SERVICE2_PROPERTY_62,
    SERVICE2_PROPERTY_63,
    SERVICE2_PROPERTY_64,
    SERVICE2_PROPERTY_65,
    SERVICE2_PROPERTY_67,
    FIRMWARE_INSTALL_STATE_PROPERTY,
    FIRMWARE_DOWNLOAD_PROGRESS_PROPERTY,
    POSE_COVERAGE_PROPERTY,
    SERVICE1_PROPERTY_50,
    SERVICE1_PROPERTY_51,
    SERVICE1_COMPLETION_FLAG_PROPERTY,
    STATUS_MAPPING,
    PROPERTY_FIRMWARE,
    CHARGING_STATUS_PROPERTY,
    CHARGING_STATUS_MAPPING,
    TASK_STATUS_PROPERTY,
    FIRMWARE_INSTALL_STATE_MAPPING,
    SERVICE5_PROPERTY_100,
    SERVICE5_PROPERTY_105,
    SERVICE5_PROPERTY_106,
    SERVICE5_ENERGY_INDEX_PROPERTY,
    SERVICE5_PROPERTY_108,
    DEVICE_FILE_PATH_PROPERTY,
    DEVICE_FILE_PATH_PROPERTY_20,
    FIRMWARE_VALIDATION_EVENT,
    MISSION_COMPLETION_EVENT,
    ACTION_START_MOWING,
    ACTION_PAUSE,
    ACTION_STOP,
    ACTION_DOCK,
    DEVICE_CODE_PROPERTY,
    PROPERTY_1_1,
)

_LOGGER = logging.getLogger(__name__)


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
    def mower_heading(self) -> int | None:
        """Return current mower heading/state value."""
        return self._pose_coverage_handler.heading

    @property
    def mowing_path_history(self) -> list[dict[str, Any]]:
        """Return path history for visualization."""
        return self._pose_coverage_handler.path_history

    @property
    def vector_map(self) -> MowerVectorMap | None:
        """Return the current vector map data from batch API."""
        return self._vector_map

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
            _LOGGER.debug(
                "Vector map updated: %d zones, %d paths, boundary=%s",
                len(vector_map.zones),
                len(vector_map.paths),
                vector_map.boundary,
            )
            self._notify_property_change("vector_map_updated", True)
            return True

        except Exception as ex:
            _LOGGER.warning("Failed to fetch vector map from batch API: %s", ex)
            return False

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
                  SERVICE5_PROPERTY_105.matches(siid, piid) or 
                  SERVICE5_PROPERTY_106.matches(siid, piid) or 
                  SERVICE5_ENERGY_INDEX_PROPERTY.matches(siid, piid) or
                  SERVICE5_PROPERTY_108.matches(siid, piid)):
                # Handle all Service 5 properties (5:100, 5:104, 5:105, 5:106, 5:107, 5:108) in unified handler
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
                # TODO: Consider doing something useful with this property change later
                property_value_str = str(message["value"])
                if property_value_str in ("dm::TASK_NAV_DOCK", "dm::TASK_SLAM_RELOCATE"):
                    self._notify_property_change(SERVICE2_PROPERTY_65.name, property_value_str)
                    _LOGGER.debug("2:65 value: %s", property_value_str)
                else:
                    _LOGGER.debug("Unrecognized 2:65 value: %s", property_value_str)
                    return False  # Report false for unrecognized values
            elif SERVICE2_PROPERTY_67.matches(siid, piid):
                # Handle Service 2 property 67 (2:67) - 4-integer array, observed after MOWING_COMPLETED
                # Meaning unknown; silently acknowledge to suppress unhandled MQTT notifications (issues #34, #35, #36, #38)
                _LOGGER.debug("Service 2 property 67 received: %s", message.get("value"))
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
                    
                    # Mark mission as completed in pose coverage handler to cap progress at 100%
                    self._pose_coverage_handler.mark_mission_completed()
                    
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

    async def start_mowing(self) -> bool:
        """Start mowing operation."""
        if not await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._cloud_device.execute_action(ACTION_START_MOWING)
        ):
            _LOGGER.error("Failed to send START_MOWING command")
            return False
        
        # Reset mission completion flag for new mowing session
        self._pose_coverage_handler.reset_mission_completion()
        
        self._notify_property_change("activity", "mowing")
        return True

    async def pause(self) -> bool:
        """Pause current operation."""
        if not await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._cloud_device.execute_action(ACTION_PAUSE)
        ):
            _LOGGER.error("Failed to send PAUSE command")
            return False
        self._notify_property_change("activity", "paused")
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
      2:1  status
      3:1  battery
      1:1  capability array (pushed every ~60 s, not yet decoded)

    Everything else (scheduling, device-codes, OTA, maps …) is mower-specific
    and returns code=-1 on this hardware, so we simply skip it.
    """

    def _handle_mqtt_property_update(self, message: dict[str, Any]) -> bool:
        """Handle MQTT property updates — only battery, status, and 1:1 are supported."""
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
                return True

            if PROPERTY_1_1.matches(siid, piid):
                # Capability array pushed every ~60 s — route through shared handler for logging
                return self._misc_handler.handle_property_update(siid, piid, message["value"], self._notify_property_change)

        except Exception as ex:
            _LOGGER.warning("DreameSwbotDevice: error handling property update: %s", ex)

        return False
