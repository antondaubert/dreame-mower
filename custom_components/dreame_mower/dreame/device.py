from __future__ import annotations
import logging
import time
import json
import re
import copy
import zlib
import base64
import traceback
from datetime import datetime
from random import randrange
from threading import Timer
from typing import Any, Optional

from .types import (
    PIID,
    DIID,
    ACTION_AVAILABILITY,
    PROPERTY_AVAILABILITY,
    DreameMowerProperty,
    DreameMowerAutoSwitchProperty,
    DreameMowerStrAIProperty,
    DreameMowerAIProperty,
    DreameMowerPropertyMapping,
    DreameMowerAction,
    DreameMowerActionMapping,
    DreameMowerChargingStatus,
    DreameMowerTaskStatus,
    DreameMowerState,
    DreameMowerStateOld,
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
    DreameMowerTaskType,
    DreameMapRecoveryStatus,
    DreameMapBackupStatus,
    CleaningHistory,
    DreameMowerDeviceCapability,
    DirtyData,
    RobotType,
    MapData,
    Segment,
    Shortcut,
    ShortcutTask,
    ObstacleType,
    CleanupMethod,
    GoToZoneSettings,
    Path,
    PathType,
    Coordinate,
    ATTR_ACTIVE_AREAS,
    ATTR_ACTIVE_POINTS,
    ATTR_ACTIVE_SEGMENTS,
    ATTR_PREDEFINED_POINTS,
    ATTR_ACTIVE_CRUISE_POINTS,
)
from .const import (
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
    CLEANING_MODE_CODE_TO_NAME,
    CHARGING_STATUS_CODE_TO_NAME,
    RELOCATION_STATUS_CODE_TO_NAME,
    TASK_STATUS_CODE_TO_NAME,
    STATE_CODE_TO_STATE,
    ERROR_CODE_TO_ERROR_NAME,
    ERROR_CODE_TO_ERROR_DESCRIPTION,
    STATUS_CODE_TO_NAME,
    STREAM_STATUS_TO_NAME,
    WIDER_CORNER_COVERAGE_TO_NAME,
    SECOND_CLEANING_TO_NAME,
    CLEANING_ROUTE_TO_NAME,
    CLEANGENIUS_TO_NAME,
    FLOOR_MATERIAL_CODE_TO_NAME,
    FLOOR_MATERIAL_DIRECTION_CODE_TO_NAME,
    SEGMENT_VISIBILITY_CODE_TO_NAME,
    VOICE_ASSISTANT_LANGUAGE_TO_NAME,
    TASK_TYPE_TO_NAME,
    ERROR_CODE_TO_IMAGE_INDEX,
    CONSUMABLE_TO_LIFE_WARNING_DESCRIPTION,
    PROPERTY_TO_NAME,
    DEVICE_KEY,
    DREAME_MODEL_CAPABILITIES,
    ATTR_CHARGING,
    ATTR_MOWER_STATE,
    ATTR_DND,
    ATTR_SHORTCUTS,
    ATTR_CLEANING_SEQUENCE,
    ATTR_STARTED,
    ATTR_PAUSED,
    ATTR_RUNNING,
    ATTR_RETURNING_PAUSED,
    ATTR_RETURNING,
    ATTR_MAPPING,
    ATTR_MAPPING_AVAILABLE,
    ATTR_ZONES,
    ATTR_CURRENT_SEGMENT,
    ATTR_SELECTED_MAP,
    ATTR_ID,
    ATTR_NAME,
    ATTR_ICON,
    ATTR_ORDER,
    ATTR_STATUS,
    ATTR_DID,
    ATTR_CLEANING_MODE,
    ATTR_COMPLETED,
    ATTR_CLEANING_TIME,
    ATTR_TIMESTAMP,
    ATTR_CLEANED_AREA,
    ATTR_CLEANGENIUS,
    ATTR_CRUISING_TIME,
    ATTR_CRUISING_TYPE,
    ATTR_MAP_INDEX,
    ATTR_MAP_NAME,
    ATTR_NEGLECTED_SEGMENTS,
    ATTR_INTERRUPT_REASON,
    ATTR_CLEANUP_METHOD,
    ATTR_SEGMENT_CLEANING,
    ATTR_ZONE_CLEANING,
    ATTR_SPOT_CLEANING,
    ATTR_CRUSING,
    ATTR_HAS_SAVED_MAP,
    ATTR_HAS_TEMPORARY_MAP,
    ATTR_CAPABILITIES,
)
from .resources import ERROR_IMAGE
from .exceptions import (
    DeviceUpdateFailedException,
    InvalidActionException,
    InvalidValueException,
)
from .protocol import DreameMowerProtocol
from .map import DreameMapMowerMapManager, DreameMowerMapDecoder

_LOGGER = logging.getLogger(__name__)


class DreameMowerDevice:
    """Support for Dreame Mower"""

    property_mapping: dict[DreameMowerProperty, dict[str, int]] = DreameMowerPropertyMapping
    action_mapping: dict[DreameMowerAction, dict[str, int]] = DreameMowerActionMapping

    def __init__(
        self,
        name: str,
        host: str,
        token: str,
        mac: str = None,
        username: str = None,
        password: str = None,
        country: str = None,
        prefer_cloud: bool = True,
        account_type: str = "dreame",
        device_id: str = None,
    ) -> None:
        # Used for easy filtering the device from cloud device list and generating unique ids
        self.info = None
        self.mac: str = None
        self.token: str = None  # Local api token
        self.host: str = None  # IP address or host name of the device
        # Dictionary for storing the current property values
        self.data: dict[DreameMowerProperty, Any] = {}
        self.auto_switch_data: dict[DreameMowerAutoSwitchProperty, Any] = None
        self.ai_data: dict[DreameMowerStrAIProperty | DreameMowerAIProperty, Any] = None
        self.available: bool = False  # Last update is successful or not
        self.disconnected: bool = False

        self._update_running: bool = False  # Update is running
        self._previous_cleaning_mode: DreameMowerCleaningMode = None
        # Device do not request properties that returned -1 as result. This property used for overriding that behavior at first connection
        self._ready: bool = False
        # Last settings properties requested time
        self._last_settings_request: float = 0
        self._last_map_list_request: float = 0  # Last map list property requested time
        self._last_map_request: float = 0  # Last map request trigger time
        self._last_change: float = 0  # Last property change time
        self._last_update_failed: float = 0  # Last update failed time
        self._cleaning_history_update: float = 0  # Cleaning history update time
        self._update_fail_count: int = 0  # Update failed counter
        self._map_select_time: float = None
        # Map Manager object. Only available when cloud connection is present
        self._map_manager: DreameMapMowerMapManager = None
        self._update_callback = None  # External update callback for device
        self._error_callback = None  # External update failed callback
        # External update callbacks for specific device property
        self._property_update_callback = {}
        self._update_timer: Timer = None  # Update schedule timer
        # Used for requesting consumable properties after reset action otherwise they will only requested when cleaning completed
        self._consumable_change: bool = False
        self._remote_control: bool = False
        self._dirty_data: dict[DreameMowerProperty, DirtyData] = {}
        self._dirty_auto_switch_data: dict[DreameMowerAutoSwitchProperty, DirtyData] = {}
        self._dirty_ai_data: dict[DreameMowerStrAIProperty | DreameMowerAIProperty, Any] = None
        self._discard_timeout = 5
        self._restore_timeout = 15

        self._name = name
        self.mac = mac
        self.token = token
        self.host = host
        self.two_factor_url = None
        self.account_type = account_type
        self.status = DreameMowerDeviceStatus(self)
        self.capability = DreameMowerDeviceCapability(self)

        # Remove write only and response only properties from default list
        self._default_properties = [
            DreameMowerProperty.STATE,
            DreameMowerProperty.ERROR,
            DreameMowerProperty.BATTERY_LEVEL,
            DreameMowerProperty.CHARGING_STATUS,
            DreameMowerProperty.STATUS,
        ]
        self._discarded_properties = [
            DreameMowerProperty.ERROR,
            DreameMowerProperty.STATE,
            DreameMowerProperty.STATUS,
            DreameMowerProperty.TASK_STATUS,
            DreameMowerProperty.ERROR,
            DreameMowerProperty.AUTO_SWITCH_SETTINGS,
            DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS,
            DreameMowerProperty.AI_DETECTION,
            DreameMowerProperty.SHORTCUTS,
            DreameMowerProperty.MAP_BACKUP_STATUS,
            DreameMowerProperty.MAP_RECOVERY_STATUS,
            DreameMowerProperty.OFF_PEAK_CHARGING,
        ]
        self._read_write_properties = [
            DreameMowerProperty.RESUME_CLEANING,
            DreameMowerProperty.OBSTACLE_AVOIDANCE,
            DreameMowerProperty.AI_DETECTION,
            DreameMowerProperty.CLEANING_MODE,
            DreameMowerProperty.INTELLIGENT_RECOGNITION,
            DreameMowerProperty.CUSTOMIZED_CLEANING,
            DreameMowerProperty.CHILD_LOCK,
            DreameMowerProperty.DND_TASK,
            DreameMowerProperty.MULTI_FLOOR_MAP,
            DreameMowerProperty.VOLUME,
            DreameMowerProperty.VOICE_PACKET_ID,
            DreameMowerProperty.TIMEZONE,
            DreameMowerProperty.MAP_SAVING,
            DreameMowerProperty.AUTO_SWITCH_SETTINGS,
            DreameMowerProperty.SHORTCUTS,
            DreameMowerProperty.VOICE_ASSISTANT,
            DreameMowerProperty.CRUISE_SCHEDULE,
            DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS,
            DreameMowerProperty.STREAM_PROPERTY,
            DreameMowerProperty.STREAM_SPACE,
            DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE,
            DreameMowerProperty.OFF_PEAK_CHARGING,
        ]

        self.listen(self._task_status_changed, DreameMowerProperty.TASK_STATUS)
        self.listen(self._status_changed, DreameMowerProperty.STATUS)
        self.listen(self._charging_status_changed, DreameMowerProperty.CHARGING_STATUS)
        self.listen(self._cleaning_mode_changed, DreameMowerProperty.CLEANING_MODE)
        self.listen(self._ai_obstacle_detection_changed, DreameMowerProperty.AI_DETECTION)
        self.listen(
            self._auto_switch_settings_changed,
            DreameMowerProperty.AUTO_SWITCH_SETTINGS,
        )
        self.listen(self._dnd_task_changed, DreameMowerProperty.DND_TASK)
        self.listen(self._stream_status_changed, DreameMowerProperty.STREAM_STATUS)
        self.listen(self._shortcuts_changed, DreameMowerProperty.SHORTCUTS)
        self.listen(
            self._voice_assistant_language_changed,
            DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE,
        )
        self.listen(self._off_peak_charging_changed, DreameMowerProperty.OFF_PEAK_CHARGING)
        self.listen(self._error_changed, DreameMowerProperty.ERROR)
        self.listen(
            self._map_recovery_status_changed,
            DreameMowerProperty.MAP_RECOVERY_STATUS,
        )

        self._protocol = DreameMowerProtocol(
            self.host,
            self.token,
            username,
            password,
            country,
            prefer_cloud,
            account_type,
            device_id,
        )
        if self._protocol.cloud:
            self._map_manager = DreameMapMowerMapManager(self._protocol)

            self.listen(self._map_list_changed, DreameMowerProperty.MAP_LIST)
            self.listen(self._recovery_map_list_changed, DreameMowerProperty.RECOVERY_MAP_LIST)
            self.listen(self._battery_level_changed, DreameMowerProperty.BATTERY_LEVEL)
            self.listen(self._map_property_changed, DreameMowerProperty.CUSTOMIZED_CLEANING)
            self.listen(self._map_property_changed, DreameMowerProperty.STATE)
            self.listen(
                self._map_backup_status_changed,
                DreameMowerProperty.MAP_BACKUP_STATUS,
            )
            self._map_manager.listen(self._map_changed, self._property_changed)
            self._map_manager.listen_error(self._update_failed)

    def _connected_callback(self):
        if not self._ready:
            return
        _LOGGER.info("Requesting properties after connect")
        self.schedule_update(2, True)

    def _message_callback(self, message):
        if not self._ready:
            return

        _LOGGER.debug("Message Callback: %s", message)

        if "method" in message:
            self.available = True
            if message["method"] == "properties_changed" and "params" in message:
                params = []
                map_params = []
                for param in message["params"]:
                    properties = [prop for prop in DreameMowerProperty]
                    for prop in properties:
                        if prop in self.property_mapping:
                            mapping = self.property_mapping[prop]
                            _LOGGER.debug("Mapping: %s", mapping)
                            if (
                                "aiid" not in mapping
                                and param["siid"] == mapping["siid"]
                                and param["piid"] == mapping["piid"]
                            ):
                                if prop in self._default_properties:
                                    param["did"] = str(prop.value)
                                    param["code"] = 0
                                    params.append(param)
                                else:
                                    if (
                                        prop is DreameMowerProperty.OBJECT_NAME
                                        or prop is DreameMowerProperty.MAP_DATA
                                        or prop is DreameMowerProperty.ROBOT_TIME
                                        or prop is DreameMowerProperty.OLD_MAP_DATA
                                    ):
                                        map_params.append(param)
                                break
                if len(map_params) and self._map_manager:
                    self._map_manager.handle_properties(map_params)

                self._handle_properties(params)

    def _handle_properties(self, properties) -> bool:
        changed = False
        callbacks = []
        for prop in properties:
            if not isinstance(prop, dict):
                continue
            did = int(prop["did"])
            if prop["code"] == 0 and "value" in prop:
                value = prop["value"]
                if did in self._dirty_data:
                    if (
                        self._dirty_data[did].value != value
                        and time.time() - self._dirty_data[did].update_time < self._discard_timeout
                    ):
                        _LOGGER.info(
                            "Property %s Value Discarded: %s <- %s",
                            DreameMowerProperty(did).name,
                            self._dirty_data[did].value,
                            value,
                        )
                        del self._dirty_data[did]
                        continue
                    del self._dirty_data[did]

                current_value = self.data.get(did)

                if current_value != value:
                    # Do not call external listener when map and json properties changed
                    if not (
                        did == DreameMowerProperty.MAP_LIST.value
                        or did == DreameMowerProperty.RECOVERY_MAP_LIST.value
                        or did == DreameMowerProperty.MAP_DATA.value
                        or did == DreameMowerProperty.OBJECT_NAME.value
                        or did == DreameMowerProperty.AUTO_SWITCH_SETTINGS.value
                        or did == DreameMowerProperty.AI_DETECTION.value
                        # or did == DreameMowerProperty.SELF_TEST_STATUS.value
                    ):
                        changed = True
                    custom_property = (
                        did == DreameMowerProperty.AUTO_SWITCH_SETTINGS.value
                        or did == DreameMowerProperty.AI_DETECTION.value
                        or did == DreameMowerProperty.MAP_LIST.value
                        or did == DreameMowerProperty.SERIAL_NUMBER.value
                    )
                    if not custom_property:
                        if current_value is not None:
                            _LOGGER.debug(
                                "Property %s Changed: %s -> %s",
                                DreameMowerProperty(did).name,
                                current_value,
                                value,
                            )
                        else:
                            _LOGGER.debug(
                                "Property %s Added: %s",
                                DreameMowerProperty(did).name,
                                value,
                            )
                    self.data[did] = value
                    if did in self._property_update_callback:
                        _LOGGER.debug("Property %s Callbacks: %s", DreameMowerProperty(did).name, self._property_update_callback[did])
                        for callback in self._property_update_callback[did]:
                            if not self._ready and custom_property:
                                callback(current_value)
                            else:
                                callbacks.append([callback, current_value])
            else:
                _LOGGER.debug("Property %s Not Available", DreameMowerProperty(did).name)

        if not self._ready:
            self.capability.refresh(
                json.loads(zlib.decompress(base64.b64decode(DREAME_MODEL_CAPABILITIES), zlib.MAX_WBITS | 32))
            )

        for callback in callbacks:
            callback[0](callback[1])

        if changed:
            self._last_change = time.time()
            if self._ready:
                self._property_changed()

        if not self._ready:
            if self._protocol.dreame_cloud:
                self._discard_timeout = 5

            self.status.segment_cleaning_mode_list = self.status.cleaning_mode_list.copy()

            if self.capability.cleaning_route:
                if (
                    self.status.cleaning_mode == DreameMowerCleaningMode.MOWING
                ):
                    new_list = CLEANING_ROUTE_TO_NAME.copy()
                    new_list.pop(DreameMowerCleaningRoute.DEEP)
                    new_list.pop(DreameMowerCleaningRoute.INTENSIVE)
                    self.status.cleaning_route_list = {v: k for k, v in new_list.items()}
                    new_list = CLEANING_ROUTE_TO_NAME.copy()
                    if self.capability.segment_slow_clean_route:
                        new_list.pop(DreameMowerCleaningRoute.QUICK)
                    self.status.segment_cleaning_route_list = {v: k for k, v in new_list.items()}

            for p in dir(self.capability):
                if not p.startswith("__") and not callable(getattr(self.capability, p)):
                    val = getattr(self.capability, p)
                    if isinstance(val, bool) and val:
                        _LOGGER.debug("Capability %s", p.upper())

        return changed

    def _request_properties(self, properties: list[DreameMowerProperty] = None) -> bool:
        """Request properties from the device."""
        if not properties:
            properties = self._default_properties

        property_list = []
        for prop in properties:
            if prop in self.property_mapping:
                mapping = self.property_mapping[prop]
                # Do not include properties that are not exists on the device
                if "aiid" not in mapping and (not self._ready or prop.value in self.data):
                    property_list.append({"did": str(prop.value), **mapping})

        results = self._protocol.get_properties(property_list)
        return self._handle_properties(results)

    def _update_status(self, task_status: DreameMowerTaskStatus, status: DreameMowerStatus) -> None:
        """Update status properties on memory for map renderer to update the image before action is sent to the device."""
        if task_status is not DreameMowerTaskStatus.COMPLETED:
            new_state = DreameMowerState.MOWING
            self._update_property(DreameMowerProperty.STATE, new_state.value)

        self._update_property(DreameMowerProperty.STATUS, status.value)
        self._update_property(DreameMowerProperty.TASK_STATUS, task_status.value)

    def _update_property(self, prop: DreameMowerProperty, value: Any) -> Any:
        """Update device property on memory and notify listeners."""
        if prop in self.property_mapping:
            if (
                not self.capability.new_state
                and prop == DreameMowerProperty.STATE
                and int(value) > 18
                and value in DreameMowerState._value2member_map_
            ):
                old_state = DreameMowerStateOld[DreameMowerState(value).name]
                if old_state:
                    value = int(old_state)
            current_value = self.get_property(prop)
            if current_value != value:
                did = prop.value
                self.data[did] = value
                if did in self._property_update_callback:
                    for callback in self._property_update_callback[did]:
                        callback(current_value)

                self._property_changed()
                return current_value if current_value is not None else value
        return None

    def _map_property_changed(self, previous_property: Any = None) -> None:
        """Update last update time of the map when a property associated with rendering map changed."""
        if self._map_manager and previous_property is not None:
            self._map_manager.editor.refresh_map()

    def _map_list_changed(self, previous_map_list: Any = None) -> None:
        """Update map list object name on map manager map list property when changed"""
        if self._map_manager:
            map_list = self.get_property(DreameMowerProperty.MAP_LIST)
            if map_list and map_list != "":
                try:
                    map_list = json.loads(map_list)
                    object_name = map_list.get("object_name")
                    if object_name is None:
                        object_name = map_list.get("obj_name")
                    if object_name and object_name != "":
                        _LOGGER.info("Property MAP_LIST Changed: %s", object_name)
                        self._map_manager.set_map_list_object_name(object_name, map_list.get("md5"))
                    else:
                        self._last_map_list_request = 0
                except:
                    pass

    def _recovery_map_list_changed(self, previous_recovery_map_list: Any = None) -> None:
        """Update recovery list object name on map manager recovery list property when changed"""
        if self._map_manager:
            map_list = self.get_property(DreameMowerProperty.RECOVERY_MAP_LIST)
            if map_list and map_list != "":
                try:
                    map_list = json.loads(map_list)
                    object_name = map_list.get("object_name")
                    if object_name is None:
                        object_name = map_list.get("obj_name")
                    if object_name and object_name != "":
                        self._map_manager.set_recovery_map_list_object_name(object_name)
                    else:
                        self._last_map_list_request = 0
                except:
                    pass

    def _map_recovery_status_changed(self, previous_map_recovery_status: Any = None) -> None:
        if previous_map_recovery_status and self.status.map_recovery_status:
            if self.status.map_recovery_status == DreameMapRecoveryStatus.SUCCESS.value:
                if not self._protocol.dreame_cloud:
                    self._last_map_list_request = 0
                self._map_manager.request_next_map()
                self._map_manager.request_next_recovery_map_list()

            if self.status.map_recovery_status != DreameMapRecoveryStatus.RUNNING.value:
                self._request_properties([DreameMowerProperty.MAP_RECOVERY_STATUS])

    def _map_backup_status_changed(self, previous_map_backup_status: Any = None) -> None:
        if previous_map_backup_status and self.status.map_backup_status:
            if self.status.map_backup_status == DreameMapBackupStatus.SUCCESS.value:
                if not self._protocol.dreame_cloud:
                    self._last_map_list_request = 0
                self._map_manager.request_next_recovery_map_list()
            if self.status.map_backup_status != DreameMapBackupStatus.RUNNING.value:
                self._request_properties([DreameMowerProperty.MAP_BACKUP_STATUS])

    def _cleaning_mode_changed(self, previous_cleaning_mode: Any = None) -> None:
        value = self.get_property(DreameMowerProperty.CLEANING_MODE)
        new_cleaning_mode = None

        if previous_cleaning_mode is not None and self.status.go_to_zone:
            self.status.go_to_zone.cleaning_mode = None

        if self.status.cleaning_mode != new_cleaning_mode:
            self.status.cleaning_mode = new_cleaning_mode

            if self._ready and self.capability.cleaning_route:
                new_list = CLEANING_ROUTE_TO_NAME.copy()
                if (
                    self.status.cleaning_mode == DreameMowerCleaningMode.MOWING
                ):
                    new_list.pop(DreameMowerCleaningRoute.DEEP)
                    new_list.pop(DreameMowerCleaningRoute.INTENSIVE)
                self.status.cleaning_route_list = {v: k for k, v in new_list.items()}

                if self.status.cleaning_route and self.status.cleaning_route not in self.status.cleaning_route_list:
                    self.set_auto_switch_property(
                        DreameMowerAutoSwitchProperty.CLEANING_ROUTE,
                        DreameMowerCleaningRoute.STANDARD.value,
                    )

    def _task_status_changed(self, previous_task_status: Any = None) -> None:
        """Task status is a very important property and must be listened to trigger necessary actions when a task started or ended"""
        if previous_task_status is not None:
            if previous_task_status in DreameMowerTaskStatus._value2member_map_:
                previous_task_status = DreameMowerTaskStatus(previous_task_status)

            task_status = self.get_property(DreameMowerProperty.TASK_STATUS)
            if task_status in DreameMowerTaskStatus._value2member_map_:
                task_status = DreameMowerTaskStatus(task_status)

            if previous_task_status is DreameMowerTaskStatus.COMPLETED:
                # as implemented on the app
                self._update_property(DreameMowerProperty.CLEANING_TIME, 0)
                self._update_property(DreameMowerProperty.CLEANED_AREA, 0)

            if self._map_manager is not None:
                # Update map data for renderer to update the map image according to the new task status
                if previous_task_status is DreameMowerTaskStatus.COMPLETED:
                    if (
                        task_status is DreameMowerTaskStatus.AUTO_CLEANING
                        or task_status is DreameMowerTaskStatus.ZONE_CLEANING
                        or task_status is DreameMowerTaskStatus.SEGMENT_CLEANING
                        or task_status is DreameMowerTaskStatus.SPOT_CLEANING
                        or task_status is DreameMowerTaskStatus.CRUISING_PATH
                        or task_status is DreameMowerTaskStatus.CRUISING_POINT
                    ):
                        # Clear path on current map on cleaning start as implemented on the app
                        self._map_manager.editor.clear_path()
                    elif task_status is DreameMowerTaskStatus.FAST_MAPPING:
                        # Clear current map on mapping start as implemented on the app
                        self._map_manager.editor.reset_map()
                    else:
                        self._map_manager.editor.refresh_map()
                else:
                    self._map_manager.editor.refresh_map()

            if task_status is DreameMowerTaskStatus.COMPLETED:
                if (
                    previous_task_status is DreameMowerTaskStatus.CRUISING_PATH
                    or previous_task_status is DreameMowerTaskStatus.CRUISING_POINT
                    or self.status.go_to_zone
                ):
                    if self._map_manager is not None:
                        # Get the new map list from cloud
                        self._map_manager.editor.set_cruise_points([])
                        self._map_manager.request_next_map_list()
                    self._cleaning_history_update = time.time()
                elif previous_task_status is DreameMowerTaskStatus.FAST_MAPPING:
                    # as implemented on the app
                    self._update_property(DreameMowerProperty.CLEANING_TIME, 0)
                    if self._map_manager is not None:
                        # Mapping is completed, get the new map list from cloud
                        self._map_manager.request_next_map_list()
                elif (
                    self.status.cleanup_started
                    and not self.status.cleanup_completed
                    and (self.status.status is DreameMowerStatus.BACK_HOME or not self.status.running)
                ):
                    self.status.cleanup_started = False
                    self.status.cleanup_completed = True
                    self._cleaning_history_update = time.time()
            else:
                self.status.cleanup_started = not (
                    self.status.fast_mapping
                    or self.status.cruising
                    or (
                        task_status is DreameMowerTaskStatus.DOCKING_PAUSED
                        and previous_task_status is DreameMowerTaskStatus.COMPLETED
                    )
                )
                self.status.cleanup_completed = False

            if self.status.go_to_zone is not None and not (
                task_status is DreameMowerTaskStatus.ZONE_CLEANING
                or task_status is DreameMowerTaskStatus.ZONE_CLEANING_PAUSED
                or task_status is DreameMowerTaskStatus.ZONE_DOCKING_PAUSED
                or task_status is DreameMowerTaskStatus.CRUISING_POINT
                or task_status is DreameMowerTaskStatus.CRUISING_POINT_PAUSED
            ):
                self._restore_go_to_zone()

            if self._map_manager:
                self._map_manager.editor.refresh_map()

            if (
                task_status is DreameMowerTaskStatus.COMPLETED
                or previous_task_status is DreameMowerTaskStatus.COMPLETED
            ):
                # Get properties that only changes when task status is changed
                properties = [
                    DreameMowerProperty.BLADES_TIME_LEFT,
                    DreameMowerProperty.BLADES_LEFT,
                    DreameMowerProperty.SIDE_BRUSH_TIME_LEFT,
                    DreameMowerProperty.SIDE_BRUSH_LEFT,
                    DreameMowerProperty.FILTER_LEFT,
                    DreameMowerProperty.FILTER_TIME_LEFT,
                    DreameMowerProperty.TANK_FILTER_LEFT,
                    DreameMowerProperty.TANK_FILTER_TIME_LEFT,
                    DreameMowerProperty.SILVER_ION_TIME_LEFT,
                    DreameMowerProperty.SILVER_ION_LEFT,
                    DreameMowerProperty.LENSBRUSH_TIME_LEFT,
                    DreameMowerProperty.LENSBRUSH_LEFT,
                    DreameMowerProperty.SQUEEGEE_TIME_LEFT,
                    DreameMowerProperty.SQUEEGEE_LEFT,
                    DreameMowerProperty.TOTAL_CLEANING_TIME,
                    DreameMowerProperty.CLEANING_COUNT,
                    DreameMowerProperty.TOTAL_CLEANED_AREA,
                    DreameMowerProperty.TOTAL_RUNTIME,
                    DreameMowerProperty.TOTAL_CRUISE_TIME,
                    DreameMowerProperty.FIRST_CLEANING_DATE,
                    DreameMowerProperty.SCHEDULE,
                    DreameMowerProperty.SCHEDULE_CANCEL_REASON,
                    DreameMowerProperty.CRUISE_SCHEDULE,
                ]

                if not self.capability.disable_sensor_cleaning:
                    properties.extend(
                        [
                            DreameMowerProperty.SENSOR_DIRTY_LEFT,
                            DreameMowerProperty.SENSOR_DIRTY_TIME_LEFT,
                        ]
                    )

                if self._map_manager is not None:
                    properties.extend(
                        [
                            DreameMowerProperty.MAP_LIST,
                            DreameMowerProperty.RECOVERY_MAP_LIST,
                        ]
                    )
                    self._last_map_list_request = time.time()

                try:
                    self._request_properties(properties)
                except Exception as ex:
                    pass

                if self._protocol.prefer_cloud and self._protocol.dreame_cloud:
                    self.schedule_update(1, True)

    def _status_changed(self, previous_status: Any = None) -> None:
        if previous_status is not None:
            if previous_status in DreameMowerStatus._value2member_map_:
                previous_status = DreameMowerStatus(previous_status)

            status = self.get_property(DreameMowerProperty.STATUS)
            if (
                self._remote_control
                and status != DreameMowerStatus.REMOTE_CONTROL.value
                and previous_status != DreameMowerStatus.REMOTE_CONTROL.value
            ):
                self._remote_control = False

            if (
                not self.capability.cruising
                and status == DreameMowerStatus.BACK_HOME
                and previous_status == DreameMowerStatus.ZONE_CLEANING
                and self.status.started
            ):
                self.status.cleanup_started = False
                self.status.cleanup_completed = False
                self.status.go_to_zone.stop = True
                self._restore_go_to_zone(True)
            elif (
                not self.status.started
                and self.status.cleanup_started
                and not self.status.cleanup_completed
                and (self.status.status is DreameMowerStatus.BACK_HOME or not self.status.running)
            ):
                self.status.cleanup_started = False
                self.status.cleanup_completed = True
                self._cleaning_history_update = time.time()

                did = DreameMowerProperty.TASK_STATUS.value
                if did in self._property_update_callback:
                    for callback in self._property_update_callback[did]:
                        callback(self.status.task_status.value)
                self._property_changed()
            elif status == DreameMowerStatus.CHARGING.value and previous_status == DreameMowerStatus.BACK_HOME.value:
                self._cleaning_history_update = time.time()

            if previous_status == DreameMowerStatus.OTA.value:
                self._ready = False
                self.connect_device()

            if self._map_manager:
                self._map_manager.editor.refresh_map()

    def _charging_status_changed(self, previous_charging_status: Any = None) -> None:
        self._remote_control = False
        if previous_charging_status is not None:
            if self._map_manager:
                self._map_manager.editor.refresh_map()

            if (
                self._protocol.dreame_cloud
                and self.status.charging_status != DreameMowerChargingStatus.CHARGING_COMPLETED
            ):
                self.schedule_update(2, True)

    def _ai_obstacle_detection_changed(self, previous_ai_obstacle_detection: Any = None) -> None:
        """AI Detection property returns multiple values as json or int this function parses and sets the sub properties to memory"""
        ai_value = self.get_property(DreameMowerProperty.AI_DETECTION)
        changed = False
        if isinstance(ai_value, str):
            settings = json.loads(ai_value)
            if settings and self.ai_data is None:
                self.ai_data = {}

            for prop in DreameMowerStrAIProperty:
                if prop.value in settings:
                    value = settings[prop.value]
                    if prop.value in self._dirty_ai_data:
                        if (
                            self._dirty_ai_data[prop.name].value != value
                            and time.time() - self._dirty_ai_data[prop.name].update_time < self._discard_timeout
                        ):
                            _LOGGER.info(
                                "AI Property %s Value Discarded: %s <- %s",
                                prop.name,
                                self._dirty_ai_data[prop.name].value,
                                value,
                            )
                            del self._dirty_ai_data[prop.name]
                            continue
                        del self._dirty_ai_data[prop.name]

                    current_value = self.ai_data.get(prop.name)
                    if current_value != value:
                        if current_value is not None:
                            _LOGGER.info(
                                "AI Property %s Changed: %s -> %s",
                                prop.name,
                                current_value,
                                value,
                            )
                        else:
                            _LOGGER.info("AI Property %s Added: %s", prop.name, value)
                        changed = True
                        self.ai_data[prop.name] = value
        elif isinstance(ai_value, int):
            if self.ai_data is None:
                self.ai_data = {}

            for prop in DreameMowerAIProperty:
                bit = int(prop.value)
                value = (ai_value & bit) == bit
                if prop.name in self._dirty_ai_data:
                    if (
                        self._dirty_ai_data[prop.name].value != value
                        and time.time() - self._dirty_ai_data[prop.name].update_time < self._discard_timeout
                    ):
                        _LOGGER.info(
                            "AI Property %s Value Discarded: %s <- %s",
                            prop.name,
                            self._dirty_ai_data[prop.name].value,
                            value,
                        )
                        del self._dirty_ai_data[prop.name]
                        continue
                    del self._dirty_ai_data[prop.name]

                current_value = self.ai_data.get(prop.name)
                if current_value != value:
                    if current_value is not None:
                        _LOGGER.info(
                            "AI Property %s Changed: %s -> %s",
                            prop.name,
                            current_value,
                            value,
                        )
                    else:
                        _LOGGER.info("AI Property %s Added: %s", prop.name, value)
                    changed = True
                    self.ai_data[prop.name] = value

        if changed:
            self._last_change = time.time()
            if self._ready:
                self._property_changed()

        self.status.ai_policy_accepted = bool(
            self.status.ai_policy_accepted or self.status.ai_obstacle_detection or self.status.ai_obstacle_picture
        )

    def _auto_switch_settings_changed(self, previous_auto_switch_settings: Any = None) -> None:
        value = self.get_property(DreameMowerProperty.AUTO_SWITCH_SETTINGS)
        if isinstance(value, str) and len(value) > 2:
            cleangenius_changed = False
            try:
                settings = json.loads(value)
                settings_dict = {}

                if isinstance(settings, list):
                    for setting in settings:
                        settings_dict[setting["k"]] = setting["v"]
                elif "k" in settings:
                    settings_dict[settings["k"]] = settings["v"]

                if settings_dict and self.auto_switch_data is None:
                    self.auto_switch_data = {}

                changed = False
                for prop in DreameMowerAutoSwitchProperty:
                    if prop.value in settings_dict:
                        value = settings_dict[prop.value]

                        if prop.name in self._dirty_auto_switch_data:
                            if (
                                self._dirty_auto_switch_data[prop.name].value != value
                                and time.time() - self._dirty_auto_switch_data[prop.name].update_time
                                < self._discard_timeout
                            ):
                                _LOGGER.info(
                                    "Property %s Value Discarded: %s <- %s",
                                    prop.name,
                                    self._dirty_auto_switch_data[prop.name].value,
                                    value,
                                )
                                del self._dirty_auto_switch_data[prop.name]
                                continue
                            del self._dirty_auto_switch_data[prop.name]

                        current_value = self.auto_switch_data.get(prop.name)
                        if current_value != value:
                            if prop == DreameMowerAutoSwitchProperty.CLEANGENIUS:
                                cleangenius_changed = True

                            if current_value is not None:
                                _LOGGER.info(
                                    "Property %s Changed: %s -> %s",
                                    prop.name,
                                    current_value,
                                    value,
                                )
                            else:
                                _LOGGER.info("Property %s Added: %s", prop.name, value)
                            changed = True
                            self.auto_switch_data[prop.name] = value

                if changed:
                    self._last_change = time.time()
                    if self._ready and previous_auto_switch_settings is not None:
                        self._property_changed()
            except Exception as ex:
                _LOGGER.error("Failed to parse auto switch settings: %s", ex)

            if cleangenius_changed and self._map_manager and self._ready and previous_auto_switch_settings is not None:
                self._map_manager.editor.refresh_map()

    def _dnd_task_changed(self, previous_dnd_task: Any = None) -> None:
        dnd_tasks = self.get_property(DreameMowerProperty.DND_TASK)
        if dnd_tasks and dnd_tasks != "":
            self.status.dnd_tasks = json.loads(dnd_tasks)

    def _stream_status_changed(self, previous_stream_status: Any = None) -> None:
        stream_status = self.get_property(DreameMowerProperty.STREAM_STATUS)
        if stream_status and stream_status != "" and stream_status != "null":
            stream_status = json.loads(stream_status)
            if stream_status and stream_status.get("result") == 0:
                self.status.stream_session = stream_status.get("session")
                operation_type = stream_status.get("operType")
                operation = stream_status.get("operation")
                if operation_type:
                    if operation_type == "end" or operation == "end":
                        self.status.stream_status = DreameMowerStreamStatus.IDLE
                    elif operation_type == "start" or operation == "start":
                        if operation:
                            if operation == "monitor" or operation_type == "monitor":
                                self.status.stream_status = DreameMowerStreamStatus.VIDEO
                            elif operation == "intercom" or operation_type == "intercom":
                                self.status.stream_status = DreameMowerStreamStatus.AUDIO
                            elif operation == "recordVideo" or operation_type == "recordVideo":
                                self.status.stream_status = DreameMowerStreamStatus.RECORDING

    def _shortcuts_changed(self, previous_shortcuts: Any = None) -> None:
        shortcuts = self.get_property(DreameMowerProperty.SHORTCUTS)
        if shortcuts and shortcuts != "":
            shortcuts = json.loads(shortcuts)
            if shortcuts:
                # response = self.call_shortcut_action("GET_COMMANDS")
                new_shortcuts = {}
                for shortcut in shortcuts:
                    id = shortcut["id"]
                    running = (
                        False
                        if "state" not in shortcut
                        else bool(shortcut["state"] == "0" or shortcut["state"] == "1")
                    )
                    name = base64.decodebytes(shortcut["name"].encode("utf8")).decode("utf-8")
                    tasks = None
                    # response = self.call_shortcut_action("GET_COMMAND_BY_ID", {"id": id})
                    # if response and "out" in response:
                    #    data = response["out"]
                    #    if data and len(data):
                    #        if "value" in data[0] and data[0]["value"] != "":
                    #            tasks = []
                    #            for task in json.loads(data[0]["value"]):
                    #                segments = []
                    #                for segment in task:
                    #                    segments.append(ShortcutTask(segment_id=segment[0], suction_level=segment[1], water_volume=segment[2], cleaning_times=segment[3], cleaning_mode=segment[4]))
                    #                tasks.append(segments)
                    new_shortcuts[id] = Shortcut(id=id, name=name, running=running, tasks=tasks)
                self.status.shortcuts = new_shortcuts

    def _voice_assistant_language_changed(self, previous_voice_assistant_language: Any = None) -> None:
        value = self.get_property(DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE)
        language_list = self.status.voice_assistant_language_list
        if value and len(value):
            language_list = VOICE_ASSISTANT_LANGUAGE_TO_NAME.copy()
            language_list.pop(DreameMowerVoiceAssistantLanguage.DEFAULT)
            language_list = {v: k for k, v in language_list.items()}
        elif DreameMowerVoiceAssistantLanguage.DEFAULT.value not in language_list:
            language_list = {v: k for k, v in VOICE_ASSISTANT_LANGUAGE_TO_NAME.items()}
        self.status.voice_assistant_language_list = language_list

    def _off_peak_charging_changed(self, previous_off_peak_charging: Any = None) -> None:
        off_peak_charging = self.get_property(DreameMowerProperty.OFF_PEAK_CHARGING)
        if off_peak_charging and off_peak_charging != "":
            self.status.off_peak_charging_config = json.loads(off_peak_charging)

    def _error_changed(self, previous_error: Any = None) -> None:
        if previous_error is not None and self.status.go_to_zone and self.status.has_error:
            self._restore_go_to_zone(True)

        if self._map_manager and previous_error is not None:
            self._map_manager.editor.refresh_map()

    def _battery_level_changed(self, previous_battery_level: Any = None) -> None:
        if self._map_manager and previous_battery_level is not None and self.status.battery_level == 100:
            self._map_manager.editor.refresh_map()

    def _property_changed(self) -> None:
        """Call external listener when a property changed"""
        if self._update_callback:
            self._update_callback()

    def _map_changed(self) -> None:
        """Call external listener when a map changed"""
        map_data = self.status.current_map
        if self._map_select_time:
            self._map_select_time = None
        if map_data and self.status.started:
            if self.status.go_to_zone is None and not self.status._capability.cruising and self.status.zone_cleaning:
                if map_data.active_areas and len(map_data.active_areas) == 1:
                    area = map_data.active_areas[0]
                    size = map_data.dimensions.grid_size
                    if area.check_size(size):
                        new_cleaning_mode = DreameMowerCleaningMode.MOWING.value

                        size = int(map_data.dimensions.grid_size / 2)
                        self.status.go_to_zone = GoToZoneSettings(
                            x=area.x0 + size,
                            y=area.y0 + size,
                            stop=bool(not self._map_manager.ready),
                            size=size,
                            cleaning_mode=new_cleaning_mode,
                        )
                        self._map_manager.editor.set_active_areas([])
                    else:
                        self.status.go_to_zone = False
                else:
                    self.status.go_to_zone = False

            if self.status.go_to_zone:
                position = map_data.robot_position
                if position:
                    size = self.status.go_to_zone.size
                    x = self.status.go_to_zone.x
                    y = self.status.go_to_zone.y
                    if (
                        position.x >= x - size
                        and position.x <= x + size
                        and position.y >= y - size
                        and position.y <= y + size
                    ):
                        self._restore_go_to_zone(True)

            if self.status.docked != map_data.docked and self._protocol.prefer_cloud:
                self.schedule_update(self._update_interval, True)

        if self._map_manager.ready:
            self._property_changed()

    def _update_failed(self, ex) -> None:
        """Call external listener when update failed"""
        if self._error_callback:
            self._error_callback(ex)

    def _action_update_task(self) -> None:
        self._update_task(True)

    def _update_task(self, force_request_properties=False) -> None:
        """Timer task for updating properties periodically"""
        self._update_timer = None
        try:
            self.update(force_request_properties)
            if self._ready:
                self.available = True
            self._update_fail_count = 0
        except Exception as ex:
            self._update_fail_count = self._update_fail_count + 1
            if self.available:
                self._last_update_failed = time.time()
                if self._update_fail_count <= 3:
                    _LOGGER.debug(
                        "Update failed, retrying %s: %s",
                        self._update_fail_count,
                        str(ex),
                    )
                elif self._ready:
                    _LOGGER.warning("Update Failed: %s", str(ex))
                    self.available = False
                    self._update_failed(ex)

        if not self.disconnected:
            self.schedule_update(self._update_interval)

    def _set_go_to_zone(self, x, y, size):
        current_cleaning_mode = int(self.status.cleaning_mode.value)

        new_cleaning_mode = None

        cleaning_mode = DreameMowerCleaningMode.MOWING.value

        if current_cleaning_mode != cleaning_mode:
            new_cleaning_mode = cleaning_mode
            current_cleaning_mode = DreameMowerCleaningMode.MOWING.value

        self.status.go_to_zone = GoToZoneSettings(
            x=x,
            y=y,
            stop=True,
            cleaning_mode=current_cleaning_mode,
            size=size,
        )

    def _restore_go_to_zone(self, stop=False):
        if self.status.go_to_zone is not None:
            if self.status.go_to_zone:
                stop = stop and self.status.go_to_zone.stop
                cleaning_mode = self.status.go_to_zone.cleaning_mode
                self.status.go_to_zone = None
                if stop:
                    self.schedule_update(10, True)
                    try:
                        mapping = self.action_mapping[DreameMowerAction.STOP]
                        self._protocol.action(mapping["siid"], mapping["aiid"])
                    except:
                        pass

                try:
                    self._cleaning_history_update = time.time()
                    if cleaning_mode is not None and self.status.cleaning_mode.value != cleaning_mode:
                        self._update_cleaning_mode(cleaning_mode)

                    if stop and self.status.started:
                        self._update_status(DreameMowerTaskStatus.COMPLETED, DreameMowerStatus.STANDBY)
                except:
                    pass

                if self._protocol.dreame_cloud:
                    self.schedule_update(3, True)
            else:
                self.status.go_to_zone = None

    @staticmethod
    def split_group_value(value: int, mop_pad_lifting: bool = False) -> list[int]:
        if value is not None:
            value_list = []
            value_list.append((value & 3) if mop_pad_lifting else (value & 1))
            byte1 = value >> 8
            byte1 = byte1 & -769
            value_list.append(byte1)
            value_list.append(value >> 16)
            return value_list

    @staticmethod
    def combine_group_value(values: list[int]) -> int:
        if values and len(values) == 3:
            return ((((0 ^ values[2]) << 8) ^ values[1]) << 8) ^ values[0]

    def connect_device(self) -> None:
        """Connect to the device api."""
        _LOGGER.debug("Connecting to device")
        info = self._protocol.connect(self._message_callback, self._connected_callback)
        if info:
            self.info = DreameMowerDeviceInfo(info)
            if self.mac is None:
                self.mac = self.info.mac_address
            _LOGGER.info(
                "Connected to device: %s %s",
                self.info.model,
                self.info.firmware_version,
            )

            self._last_settings_request = time.time()
            self._last_map_list_request = self._last_settings_request
            self._dirty_data = {}
            self._dirty_auto_switch_data = {}
            self._dirty_ai_data = {}
            self._request_properties()
            self._last_update_failed = None

            if self.device_connected and self._protocol.cloud is not None and (not self._ready or not self.available):
                if self._map_manager:
                    model = self.info.model.split(".")
                    if len(model) == 3:
                        for k, v in json.loads(
                            zlib.decompress(base64.b64decode(DEVICE_KEY), zlib.MAX_WBITS | 32)
                        ).items():
                            if model[2] in v:
                                self._map_manager.set_aes_iv(k)
                                break
                    self._map_manager.set_capability(self.capability)
                    self._map_manager.set_update_interval(self._map_update_interval)
                    self._map_manager.set_device_running(
                        self.status.running,
                        self.status.docked and not self.status.started,
                    )

                    if self.status.current_map is None:
                        self._map_manager.schedule_update(15)
                        try:
                            self._map_manager.update()
                            self._last_map_request = self._last_settings_request
                        except Exception as ex:
                            _LOGGER.error("Initial map update failed! %s", str(ex))
                        self._map_manager.schedule_update()
                    else:
                        self.update_map()

                if self.cloud_connected:
                    self._cleaning_history_update = -1
                    if (self.capability.ai_detection and not self.status.ai_policy_accepted) or True:
                        try:
                            prop = "prop.s_ai_config"
                            response = self._protocol.cloud.get_batch_device_datas([prop])
                            if response and prop in response and response[prop]:
                                value = json.loads(response[prop])
                                self.status.ai_policy_acepted = (
                                    value.get("privacyAuthed")
                                    if "privacyAuthed" in value
                                    else value.get("aiPrivacyAuthed")
                                )
                        except:
                            pass

            if not self.available:
                self.available = True

            if not self._ready:
                self._ready = True
            else:
                self._property_changed()

    def connect_cloud(self) -> None:
        """Connect to the cloud api."""
        if self._protocol.cloud and not self._protocol.cloud.logged_in:
            self._protocol.cloud.login()
            if self._protocol.cloud.logged_in is False:
                if self._protocol.cloud.two_factor_url:
                    self.two_factor_url = self._protocol.cloud.two_factor_url
                    self._property_changed()
                self._map_manager.schedule_update(-1)
            elif self._protocol.cloud.logged_in:
                if self.two_factor_url:
                    self.two_factor_url = None
                    self._property_changed()

                if self._protocol.connected:
                    self._map_manager.schedule_update(5)

                self.token, self.host = self._protocol.cloud.get_info(self.mac)
                if not self._protocol.dreame_cloud:
                    self._protocol.set_credentials(self.host, self.token, self.mac, self.account_type)

    def disconnect(self) -> None:
        """Disconnect from device and cancel timers"""
        _LOGGER.info("Disconnect")
        self.disconnected = True
        self.schedule_update(-1)
        self._protocol.disconnect()
        if self._map_manager:
            self._map_manager.disconnect()
        self._property_changed()

    def listen(self, callback, property: DreameMowerProperty = None) -> None:
        """Set callback functions for external listeners"""
        if callback is None:
            self._update_callback = None
            self._property_update_callback = {}
            return

        if property is None:
            self._update_callback = callback
        else:
            if property.value not in self._property_update_callback:
                self._property_update_callback[property.value] = []
            self._property_update_callback[property.value].append(callback)

    def listen_error(self, callback) -> None:
        """Set error callback function for external listeners"""
        self._error_callback = callback

    def schedule_update(self, wait: float = None, force_request_properties=False) -> None:
        """Schedule a device update for future"""
        if wait == None:
            wait = self._update_interval

        if self._update_timer is not None:
            self._update_timer.cancel()
            del self._update_timer
            self._update_timer = None

        if wait >= 0:
            self._update_timer = Timer(
                wait, self._action_update_task if force_request_properties else self._update_task
            )
            self._update_timer.start()

    def get_property(
        self,
        prop: (
            DreameMowerProperty | DreameMowerAutoSwitchProperty | DreameMowerStrAIProperty | DreameMowerAIProperty
        ),
    ) -> Any:
        """Get a device property from memory"""
        if isinstance(prop, DreameMowerAutoSwitchProperty):
            return self.get_auto_switch_property(prop)
        if isinstance(prop, DreameMowerStrAIProperty) or isinstance(prop, DreameMowerAIProperty):
            return self.get_ai_property(prop)
        if prop is not None and prop.value in self.data:
            return self.data[prop.value]
        return None

    def get_auto_switch_property(self, prop: DreameMowerAutoSwitchProperty) -> int:
        """Get a device auto switch property from memory"""
        if self.capability.auto_switch_settings and self.auto_switch_data:
            if prop is not None and prop.name in self.auto_switch_data:
                return int(self.auto_switch_data[prop.name])
        return None

    def get_ai_property(self, prop: DreameMowerStrAIProperty | DreameMowerAIProperty) -> bool:
        """Get a device AI property from memory"""
        if self.capability.ai_detection and self.ai_data:
            if prop is not None and prop.name in self.ai_data:
                return bool(self.ai_data[prop.name])
        return None

    def set_property_value(self, prop: str, value: Any):
        if prop is not None and value is not None:
            set_fn = "set_" + prop.lower()
            if hasattr(self, set_fn):
                set_fn = getattr(self, set_fn)
            else:
                set_fn = None

            prop = prop.upper()
            if prop in DreameMowerProperty.__members__:
                prop = DreameMowerProperty(DreameMowerProperty[prop])
                if prop not in self._read_write_properties:
                    raise InvalidActionException("Invalid property")
            elif prop in DreameMowerAutoSwitchProperty.__members__:
                prop = DreameMowerAutoSwitchProperty(DreameMowerAutoSwitchProperty[prop])
            elif prop in DreameMowerAIProperty.__members__:
                prop = DreameMowerAIProperty(DreameMowerAIProperty[prop])
            elif prop in DreameMowerStrAIProperty.__members__:
                prop = DreameMowerStrAIProperty(DreameMowerStrAIProperty[prop])
            elif set_fn is None:
                raise InvalidActionException("Invalid property")

            if set_fn is None and self.get_property(prop) is None:
                raise InvalidActionException("Invalid property")

            prop_name = prop.lower() if isinstance(prop, str) else prop.name

            if (
                (
                    self.status.started
                    or not (
                        prop is DreameMowerProperty.CLEANING_MODE
                        or prop is DreameMowerAutoSwitchProperty.CLEANING_ROUTE
                    )
                )
                and prop_name in PROPERTY_AVAILABILITY
                and not PROPERTY_AVAILABILITY[prop_name](self)
            ):
                raise InvalidActionException("Property unavailable")

            def get_int_value(enum, value, enum_list=None):
                if isinstance(value, str):
                    value = value.upper()
                    if value.isnumeric():
                        value = int(value)
                    elif value in enum.__members__:
                        value = enum[value].value
                        if enum_list is None:
                            return value

                if isinstance(value, int):
                    if enum_list is None:
                        if value in enum._value2member_map_:
                            return value
                    elif value in enum_list.values():
                        return value

            if prop is DreameMowerProperty.CLEANING_MODE:
                value = get_int_value(DreameMowerCleaningMode, value)
            elif prop is DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE:
                value = get_int_value(
                    DreameMowerVoiceAssistantLanguage, value, self.status.voice_assistant_language_list
                )
            elif prop is DreameMowerAutoSwitchProperty.WIDER_CORNER_COVERAGE:
                value = get_int_value(DreameMowerWiderCornerCoverage, value)
            elif prop is DreameMowerAutoSwitchProperty.CLEANING_ROUTE:
                value = get_int_value(DreameMowerCleaningRoute, value, self.status.cleaning_route_list)
            elif prop is DreameMowerAutoSwitchProperty.CLEANGENIUS:
                value = get_int_value(DreameMowerCleanGenius, value)
            elif isinstance(value, bool):
                value = int(value)
            elif isinstance(value, str):
                value = value.upper()
                if value == "TRUE" or value == "1":
                    value = 1
                elif value == "FALSE" or value == "0":
                    value = 0
                elif value.isnumeric():
                    value = int(value)
                else:
                    value = None

            if value is None or not isinstance(value, int):
                raise InvalidActionException("Invalid value")

            if prop == DreameMowerProperty.VOLUME:
                if value < 0 or value > 100:
                    value = None
            elif prop == DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS:
                if value < 40 or value > 100:
                    value = None

            if value is None:
                raise InvalidActionException("Invalid value")

            if not self.device_connected:
                raise InvalidActionException("Device unavailable")

            if set_fn:
                return set_fn(value)

            if self.get_property(prop) == value or self.set_property(prop, value):
                return
            raise InvalidActionException("Property not updated")
        raise InvalidActionException("Invalid property or value")

    def call_action_value(self, action: str):
        if action is not None:
            if hasattr(self, action):
                action_fn = getattr(self, action)
            else:
                action_fn = None

            action = action.upper()
            if action in DreameMowerAction.__members__:
                action = DreameMowerAction(DreameMowerAction[action])
            elif action_fn is None:
                raise InvalidActionException("Invalid action")

            action_name = action.lower() if isinstance(action, str) else action.name

            if action_name in ACTION_AVAILABILITY and not ACTION_AVAILABILITY[action_name](self):
                raise InvalidActionException("Action unavailable")

            if not self.device_connected:
                raise InvalidActionException("Device unavailable")

            if action_fn:
                return action_fn()

            result = self.call_action(action)
            if result and result.get("code") == 0:
                return
            raise InvalidActionException("Unable to call action")
        raise InvalidActionException("Invalid action")

    def set_property(
        self,
        prop: (
            DreameMowerProperty | DreameMowerAutoSwitchProperty | DreameMowerStrAIProperty | DreameMowerAIProperty
        ),
        value: Any,
    ) -> bool:
        """Sets property value using the existing property mapping and notify listeners
        Property must be set on memory first and notify its listeners because device does not return new value immediately.
        """
        if value is None:
            return False

        if isinstance(prop, DreameMowerAutoSwitchProperty):
            return self.set_auto_switch_property(prop, value)
        if isinstance(prop, DreameMowerStrAIProperty) or isinstance(prop, DreameMowerAIProperty):
            return self.set_ai_property(prop, value)

        self.schedule_update(10)
        current_value = self._update_property(prop, value)
        if current_value is not None:
            if prop not in self._discarded_properties:
                self._dirty_data[prop.value] = DirtyData(value, current_value, time.time())

            self._last_change = time.time()
            self._last_settings_request = 0

            try:
                mapping = self.property_mapping[prop]
                result = self._protocol.set_property(mapping["siid"], mapping["piid"], value)

                if result is None or result[0]["code"] != 0:
                    _LOGGER.error(
                        "Property not updated: %s: %s -> %s",
                        prop.name,
                        current_value,
                        value,
                    )
                    self._update_property(prop, current_value)
                    if prop.value in self._dirty_data:
                        del self._dirty_data[prop.value]
                    self._property_changed()

                    self.schedule_update(2)
                    return False
                else:
                    _LOGGER.info("Update Property: %s: %s -> %s", prop.name, current_value, value)
                    if prop.value in self._dirty_data:
                        self._dirty_data[prop.value].update_time = time.time()

                    self.schedule_update(2)
                    return True
            except Exception as ex:
                self._update_property(prop, current_value)
                if prop.value in self._dirty_data:
                    del self._dirty_data[prop.value]
                self.schedule_update(1)
                raise DeviceUpdateFailedException("Set property failed %s: %s", prop.name, ex) from None

        self.schedule_update(1)
        return False

    def get_map_for_render(self, map_data: MapData) -> MapData | None:
        """Makes changes on map data for device related properties for renderer.
        Map manager does not need any device property for parsing and storing map data but map renderer does.
        """
        if map_data:
            if map_data.need_optimization:
                map_data = self._map_manager.optimizer.optimize(
                    map_data,
                    self._map_manager.selected_map if map_data.saved_map_status == 2 else None,
                )
                map_data.need_optimization = False

            render_map_data = copy.deepcopy(map_data)
            if (
                not self.capability.lidar_navigation
                and self.status.docked
                and not self.status.started
                and map_data.saved_map_status == 1
            ):
                saved_map_data = self._map_manager.selected_map
                render_map_data.segments = copy.deepcopy(saved_map_data.segments)
                render_map_data.data = copy.deepcopy(saved_map_data.data)
                render_map_data.pixel_type = copy.deepcopy(saved_map_data.pixel_type)
                render_map_data.dimensions = copy.deepcopy(saved_map_data.dimensions)
                render_map_data.charger_position = copy.deepcopy(saved_map_data.charger_position)
                render_map_data.no_go_areas = saved_map_data.no_go_areas
                render_map_data.virtual_walls = saved_map_data.virtual_walls
                render_map_data.robot_position = render_map_data.charger_position
                render_map_data.docked = True
                render_map_data.path = None
                render_map_data.need_optimization = False
                render_map_data.saved_map_status = 2
                render_map_data.optimized_pixel_type = None
                render_map_data.optimized_charger_position = None

            if render_map_data.optimized_pixel_type is not None:
                render_map_data.pixel_type = render_map_data.optimized_pixel_type
                render_map_data.dimensions = render_map_data.optimized_dimensions
                if render_map_data.optimized_charger_position is not None:
                    render_map_data.charger_position = render_map_data.optimized_charger_position

                # if not self.status.started and render_map_data.docked and render_map_data.robot_position and render_map_data.charger_position:
                #    render_map_data.charger_position = copy.deepcopy(render_map_data.robot_position)

            if render_map_data.combined_pixel_type is not None:
                render_map_data.pixel_type = render_map_data.combined_pixel_type
                render_map_data.dimensions = render_map_data.combined_dimensions

            offset = render_map_data.dimensions.grid_size / (1 if self.capability.map_object_offset else 2)
            render_map_data.dimensions.left = render_map_data.dimensions.left - offset
            render_map_data.dimensions.top = render_map_data.dimensions.top + offset

            if render_map_data.wifi_map:
                return render_map_data

            if render_map_data.furniture_version == 1 and self.capability.new_furnitures:
                render_map_data.furniture_version = 2

            if not render_map_data.history_map:
                if self.status.started and not (
                    self.status.zone_cleaning
                    or self.status.go_to_zone
                    or (
                        render_map_data.active_areas
                        and self.status.task_status is DreameMowerTaskStatus.DOCKING_PAUSED
                    )
                ):
                    # Map data always contains last active areas
                    render_map_data.active_areas = None

                if self.status.started and not self.status.spot_cleaning:
                    # Map data always contains last active points
                    render_map_data.active_points = None

                if not self.status.segment_cleaning:
                    # Map data always contains last active segments
                    render_map_data.active_segments = None

                if not self.status.cruising:
                    # Map data always contains last active path points
                    render_map_data.active_cruise_points = None

                if self.capability.camera_streaming and render_map_data.predefined_points is None:
                    render_map_data.predefined_points = []
            else:
                if not self.capability.camera_streaming:
                    if render_map_data.active_areas and len(render_map_data.active_areas) == 1:
                        area = render_map_data.active_areas[0]
                        size = render_map_data.dimensions.grid_size
                        if area.check_size(size):
                            x = area.x0 + int(size / 2)
                            y = area.y0 + int(size / 2)
                            render_map_data.task_cruise_points = {
                                1: Coordinate(
                                    x,
                                    y,
                                    False,
                                    0,
                                )
                            }

                            if render_map_data.completed == False:
                                if render_map_data.robot_position:
                                    render_map_data.completed = bool(
                                        render_map_data.robot_position.x >= x - size
                                        and render_map_data.robot_position.x <= x + size
                                        and render_map_data.robot_position.y >= y - size
                                        and render_map_data.robot_position.y <= y + size
                                    )
                                else:
                                    render_map_data.completed = True

                            render_map_data.active_areas = None

                if render_map_data.active_areas or render_map_data.active_points:
                    render_map_data.segments = None

                if render_map_data.customized_cleaning != 1:
                    render_map_data.cleanset = None

                if (
                    render_map_data.cleanup_method is None
                    or render_map_data.cleanup_method != CleanupMethod.CUSTOMIZED_CLEANING
                ):
                    render_map_data.cleanset = None

                if render_map_data.task_cruise_points:
                    render_map_data.active_cruise_points = render_map_data.task_cruise_points.copy()
                    render_map_data.task_cruise_points = True
                    render_map_data.active_areas = None
                    render_map_data.path = None
                    render_map_data.cleanset = None
                    if render_map_data.furnitures is not None:
                        render_map_data.furnitures = {}

                if render_map_data.segments:
                    if render_map_data.task_cruise_points or (
                        render_map_data.cleanup_method is not None
                        and render_map_data.cleanup_method == CleanupMethod.CLEANGENIUS
                    ):
                        for k, v in render_map_data.segments.items():
                            render_map_data.segments[k].order = None
                    elif render_map_data.active_segments:
                        order = 1
                        for segment_id in list(
                            sorted(
                                render_map_data.segments,
                                key=lambda segment_id: (
                                    render_map_data.segments[segment_id].order
                                    if render_map_data.segments[segment_id].order
                                    else 99
                                ),
                            )
                        ):
                            if (
                                len(render_map_data.active_segments) > 1
                                and render_map_data.segments[segment_id].order
                                and segment_id in render_map_data.active_segments
                            ):
                                render_map_data.segments[segment_id].order = order
                                order = order + 1
                            else:
                                render_map_data.segments[segment_id].order = None

                return render_map_data

            if not render_map_data.saved_map and not render_map_data.recovery_map:
                if not self.status._capability.cruising:
                    if self.status.go_to_zone:
                        render_map_data.active_cruise_points = {
                            1: Coordinate(
                                self.status.go_to_zone.x,
                                self.status.go_to_zone.y,
                                False,
                                0,
                            )
                        }
                        render_map_data.active_areas = None
                        render_map_data.path = None

                    if render_map_data.active_areas and len(render_map_data.active_areas) == 1:
                        area = render_map_data.active_areas[0]
                        if area.check_size(render_map_data.dimensions.grid_size):
                            if self.status.started and not self.status.go_to_zone and self.status.zone_cleaning:
                                render_map_data.active_cruise_points = {
                                    1: Coordinate(
                                        area.x0 + int(render_map_data.dimensions.grid_size / 2),
                                        area.y0 + int(render_map_data.dimensions.grid_size / 2),
                                        False,
                                        0,
                                    )
                                }
                            render_map_data.active_areas = None
                            render_map_data.path = None

                if not self.status.go_to_zone and (
                    (self.status.zone_cleaning and render_map_data.active_areas)
                    or (self.status.spot_cleaning and render_map_data.active_points)
                ):
                    # App does not render segments when zone or spot cleaning
                    render_map_data.segments = None

                # App does not render pet obstacles when pet detection turned off
                if render_map_data.obstacles and self.status.ai_pet_detection == 0:
                    obstacles = copy.deepcopy(render_map_data.obstacles)
                    for k, v in obstacles.items():
                        if v.type == ObstacleType.PET:
                            del render_map_data.obstacles[k]

                if render_map_data.furnitures and self.status.ai_furniture_detection == 0:
                    render_map_data.furnitures = {}

                # App adds robot position to paths as last line when map data is line to robot
                if render_map_data.line_to_robot and render_map_data.path and render_map_data.robot_position:
                    render_map_data.path.append(
                        Path(
                            render_map_data.robot_position.x,
                            render_map_data.robot_position.y,
                            PathType.LINE,
                        )
                    )

            if not self.status.customized_cleaning or self.status.cruising or self.status.cleangenius_cleaning:
                # App does not render customized cleaning settings on saved map list
                render_map_data.cleanset = None
            elif (
                not render_map_data.saved_map
                and not render_map_data.recovery_map
                and render_map_data.cleanset is None
                and self.status.customized_cleaning
            ):
                DreameMowerMapDecoder.set_segment_cleanset(render_map_data, {}, self.capability)
                render_map_data.cleanset = True

            if render_map_data.segments:
                if (
                    not self.status.custom_order
                    or self.status.cleangenius_cleaning
                    or render_map_data.saved_map
                    or render_map_data.recovery_map
                ):
                    for k, v in render_map_data.segments.items():
                        render_map_data.segments[k].order = None

            # Device currently may not be docked but map data can be old and still showing when robot is docked
            render_map_data.docked = bool(render_map_data.docked or self.status.docked)

            if (
                not self.capability.lidar_navigation
                and not render_map_data.saved_map
                and not render_map_data.recovery_map
                and render_map_data.saved_map_status == 1
                and render_map_data.docked
            ):
                # For correct scaling of vslam saved map
                render_map_data.saved_map_status = 2

            if (
                render_map_data.charger_position == None
                and render_map_data.docked
                and render_map_data.robot_position
                and not render_map_data.saved_map
                and not render_map_data.recovery_map
            ):
                render_map_data.charger_position = copy.deepcopy(render_map_data.robot_position)
                render_map_data.charger_position.a = render_map_data.robot_position.a + 180

            if render_map_data.saved_map or render_map_data.recovery_map:
                if not render_map_data.recovery_map:
                    render_map_data.virtual_walls = None
                    render_map_data.no_go_areas = None
                    render_map_data.pathways = None
                render_map_data.active_areas = None
                render_map_data.active_points = None
                render_map_data.active_segments = None
                render_map_data.active_cruise_points = None
                render_map_data.path = None
                render_map_data.cleanset = None
            elif render_map_data.charger_position and render_map_data.docked and not self.status.fast_mapping:
                if not render_map_data.robot_position:
                    render_map_data.robot_position = copy.deepcopy(render_map_data.charger_position)
            return render_map_data
        return map_data

    def get_map(self, map_index: int) -> MapData | None:
        """Get stored map data by index from map manager."""
        if self._map_manager:
            if self.status.multi_map:
                return self._map_manager.get_map(map_index)
            if map_index == 1:
                return self._map_manager.selected_map
            if map_index == 0:
                return self.status.current_map

    def update_map(self) -> None:
        """Trigger a map update.
        This function is used for requesting map data when a image request has been made to renderer
        """

        self._last_change = time.time()
        if self._map_manager:
            now = time.time()
            if now - self._last_map_request > 120:
                self._last_map_request = now
                self._map_manager.set_update_interval(self._map_update_interval)
                self._map_manager.schedule_update(0.01)

    def update(self, force_request_properties=False) -> None:
        """Get properties from the device."""
        _LOGGER.debug("Device update: %s", self._update_interval)

        if self._update_running:
            return

        if not self.cloud_connected:
            self.connect_cloud()
            self.connect_device()

        # Read-only properties
        properties = [
            DreameMowerProperty.STATE,
            DreameMowerProperty.ERROR,
            DreameMowerProperty.BATTERY_LEVEL,
            DreameMowerProperty.CHARGING_STATUS,
            DreameMowerProperty.STATUS,
            DreameMowerProperty.TASK_STATUS,
            DreameMowerProperty.WARN_STATUS,
            DreameMowerProperty.RELOCATION_STATUS,
            DreameMowerProperty.CLEANING_PAUSED,
            DreameMowerProperty.CLEANING_CANCEL,
            DreameMowerProperty.SCHEDULED_CLEAN,
            DreameMowerProperty.TASK_TYPE,
            DreameMowerProperty.MAP_RECOVERY_STATUS,
        ]

        if self.capability.backup_map:
            properties.append(DreameMowerProperty.MAP_BACKUP_STATUS)

        now = time.time()
        if self.status.active:
            # Only changed when robot is active
            properties.extend([DreameMowerProperty.CLEANED_AREA, DreameMowerProperty.CLEANING_TIME])

        if self._consumable_change:
            # Consumable properties
            properties.extend(
                [
                    DreameMowerProperty.BLADES_TIME_LEFT,
                    DreameMowerProperty.BLADES_LEFT,
                    DreameMowerProperty.SIDE_BRUSH_TIME_LEFT,
                    DreameMowerProperty.SIDE_BRUSH_LEFT,
                    DreameMowerProperty.FILTER_LEFT,
                    DreameMowerProperty.FILTER_TIME_LEFT,
                    DreameMowerProperty.LENSBRUSH_LEFT,
                    DreameMowerProperty.LENSBRUSH_TIME_LEFT,
                    DreameMowerProperty.SQUEEGEE_LEFT,
                    DreameMowerProperty.SQUEEGEE_TIME_LEFT,
                    DreameMowerProperty.SILVER_ION_LEFT,
                    DreameMowerProperty.SILVER_ION_TIME_LEFT,
                    DreameMowerProperty.TANK_FILTER_LEFT,
                    DreameMowerProperty.TANK_FILTER_TIME_LEFT,
                ]
            )

            if not self.capability.disable_sensor_cleaning:
                properties.extend(
                    [
                        DreameMowerProperty.SENSOR_DIRTY_LEFT,
                        DreameMowerProperty.SENSOR_DIRTY_TIME_LEFT,
                    ]
                )

        if now - self._last_settings_request > 9.5:
            self._last_settings_request = now

            if not self._consumable_change:
                properties.extend(
                    [
                        DreameMowerProperty.LENSBRUSH_LEFT,
                        DreameMowerProperty.LENSBRUSH_TIME_LEFT,
                        DreameMowerProperty.SQUEEGEE_LEFT,
                        DreameMowerProperty.SQUEEGEE_TIME_LEFT,
                    ]
                )

            properties.extend(self._read_write_properties)

            if not self.capability.dnd_task:
                properties.extend(
                    [
                        DreameMowerProperty.DND,
                        DreameMowerProperty.DND_START,
                        DreameMowerProperty.DND_END,
                    ]
                )

        if self._map_manager and not self.status.running and now - self._last_map_list_request > 60:
            properties.extend([DreameMowerProperty.MAP_LIST, DreameMowerProperty.RECOVERY_MAP_LIST])
            self._last_map_list_request = time.time()

        try:
            if self._protocol.dreame_cloud and (not self.device_connected or not self.cloud_connected):
                force_request_properties = True

            if not self._protocol.dreame_cloud or force_request_properties:
                self._request_properties(properties)
            elif self.status.map_backup_status:
                self._request_properties([DreameMowerProperty.MAP_BACKUP_STATUS])
            elif self.status.map_recovery_status:
                self._request_properties([DreameMowerProperty.MAP_RECOVERY_STATUS])
        except Exception as ex:
            self._update_running = False
            raise DeviceUpdateFailedException(ex) from None

        if self._dirty_data:
            for k, v in copy.deepcopy(self._dirty_data).items():
                if time.time() - v.update_time >= self._restore_timeout:
                    if v.previous_value is not None:
                        value = self.data.get(k)
                        if value is None or v.value == value:
                            _LOGGER.info(
                                "Property %s Value Restored: %s <- %s",
                                DreameMowerProperty(k).name,
                                v.previous_value,
                                value,
                            )
                            self.data[k] = v.previous_value
                            if k in self._property_update_callback:
                                for callback in self._property_update_callback[k]:
                                    callback(v.previous_value)

                            self._property_changed()
                            self.schedule_update(1, True)
                    del self._dirty_data[k]

        if self._dirty_auto_switch_data:
            for k, v in copy.deepcopy(self._dirty_auto_switch_data).items():
                if time.time() - v.update_time >= self._restore_timeout:
                    if v.previous_value is not None:
                        value = self.auto_switch_data.get(k)
                        ## TODO
                        # if value is None or v.value == value:
                        #    _LOGGER.info(
                        #        "Property %s Value Restored: %s <- %s",
                        #        k,
                        #        v.previous_value,
                        #        value,
                        #    )
                        #    self.auto_switch_data[k] = v.previous_value
                        #    self._property_changed()
                        #    self.schedule_update(1, True)
                    del self._dirty_auto_switch_data[k]

        if self._dirty_ai_data:
            for k, v in copy.deepcopy(self._dirty_ai_data).items():
                if time.time() - v.update_time >= self._restore_timeout:
                    if v.previous_value is not None:
                        value = self.ai_data.get(k)
                        ## TODO
                        # if value is None or v.value == value:
                        #    _LOGGER.info(
                        #        "AI Property %s Value Restored: %s <- %s",
                        #        k,
                        #        v.previous_value,
                        #        value,
                        #    )
                        #    self.ai_data[k] = v.previous_value
                        #    self._property_changed()
                        #    self.schedule_update(1, True)
                    del self._dirty_ai_data[k]

        if self._consumable_change:
            self._consumable_change = False

        if self._map_manager:
            self._map_manager.set_update_interval(self._map_update_interval)
            self._map_manager.set_device_running(self.status.running, self.status.docked and not self.status.started)

        self._update_running = False

    def call_stream_audio_action(self, property: DreameMowerProperty, parameters=None):
        return self.call_stream_action(DreameMowerAction.STREAM_AUDIO, property, parameters)

    def call_stream_video_action(self, property: DreameMowerProperty, parameters=None):
        return self.call_stream_action(DreameMowerAction.STREAM_VIDEO, property, parameters)

    def call_stream_property_action(self, property: DreameMowerProperty, parameters=None):
        return self.call_stream_action(DreameMowerAction.STREAM_PROPERTY, property, parameters)

    def call_stream_action(
        self,
        action: DreameMowerAction,
        property: DreameMowerProperty,
        parameters=None,
    ):
        params = {"session": self.status.stream_session}
        if parameters:
            params.update(parameters)
        return self.call_action(
            action,
            [
                {
                    "piid": PIID(property),
                    "value": str(json.dumps(params, separators=(",", ":"))).replace(" ", ""),
                }
            ],
        )

    def call_shortcut_action(self, command: str, parameters={}):
        return self.call_action(
            DreameMowerAction.SHORTCUTS,
            [
                {
                    "piid": PIID(DreameMowerProperty.CLEANING_PROPERTIES),
                    "value": str(
                        json.dumps(
                            {"cmd": command, "params": parameters},
                            separators=(",", ":"),
                        )
                    ).replace(" ", ""),
                }
            ],
        )

    def call_action(self, action: DreameMowerAction, parameters: dict[str, Any] = None) -> dict[str, Any] | None:
        """Call an action."""
        if action not in self.action_mapping:
            raise InvalidActionException(f"Unable to find {action} in the action mapping")

        mapping = self.action_mapping[action]
        if "siid" not in mapping or "aiid" not in mapping:
            raise InvalidActionException(f"{action} is not an action (missing siid or aiid)")

        map_action = bool(action is DreameMowerAction.REQUEST_MAP or action is DreameMowerAction.UPDATE_MAP_DATA)

        if not map_action:
            self.schedule_update(10, True)

        cleaning_action = bool(
            action
            in [
                DreameMowerAction.START_MOWING,
                DreameMowerAction.PAUSE,
                DreameMowerAction.DOCK,
            ]
        )

        if not cleaning_action:
            available_fn = ACTION_AVAILABILITY.get(action.name)
            if available_fn and not available_fn(self):
                raise InvalidActionException("Action unavailable")
        elif self._map_select_time:
            elapsed = time.time() - self._map_select_time
            self._map_select_time = None
            if elapsed < 5:
                time.sleep(5 - elapsed)

        # Reset consumable on memory
        if action is DreameMowerAction.RESET_BLADES:
            self._consumable_change = True
            self._update_property(DreameMowerProperty.BLADES_LEFT, 100)
            self._update_property(DreameMowerProperty.BLADES_TIME_LEFT, 300)
        elif action is DreameMowerAction.RESET_SIDE_BRUSH:
            self._consumable_change = True
            self._update_property(DreameMowerProperty.SIDE_BRUSH_LEFT, 100)
            self._update_property(DreameMowerProperty.SIDE_BRUSH_TIME_LEFT, 200)
        elif action is DreameMowerAction.RESET_FILTER:
            self._consumable_change = True
            self._update_property(DreameMowerProperty.FILTER_LEFT, 100)
            self._update_property(DreameMowerProperty.FILTER_TIME_LEFT, 150)
        elif action is DreameMowerAction.RESET_SENSOR:
            self._consumable_change = True
            self._update_property(DreameMowerProperty.SENSOR_DIRTY_LEFT, 100)
            self._update_property(DreameMowerProperty.SENSOR_DIRTY_TIME_LEFT, 30)
        elif action is DreameMowerAction.RESET_TANK_FILTER:
            self._consumable_change = True
            self._update_property(DreameMowerProperty.TANK_FILTER_LEFT, 100)
            self._update_property(DreameMowerProperty.TANK_FILTER_TIME_LEFT, 30)
        elif action is DreameMowerAction.RESET_SILVER_ION:
            self._consumable_change = True
            self._update_property(DreameMowerProperty.SILVER_ION_LEFT, 100)
            self._update_property(DreameMowerProperty.SILVER_ION_TIME_LEFT, 365)
        elif action is DreameMowerAction.RESET_LENSBRUSH:
            parameters['in'] = {
                "CMS": {
                    "type": "set",
                    "value": [
                        1,
                        0,
                        1
                    ]
                }
            }
            self._consumable_change = True
            self._update_property(DreameMowerProperty.LENSBRUSH_LEFT, 100)
            self._update_property(DreameMowerProperty.LENSBRUSH_TIME_LEFT, 18)
        elif action is DreameMowerAction.RESET_SQUEEGEE:
            self._consumable_change = True
            self._update_property(DreameMowerProperty.SQUEEGEE_LEFT, 100)
            self._update_property(DreameMowerProperty.SQUEEGEE_TIME_LEFT, 100)
        elif action is DreameMowerAction.CLEAR_WARNING:
            self._update_property(DreameMowerProperty.ERROR, DreameMowerErrorCode.NO_ERROR.value)

        # Update listeners
        if cleaning_action or self._consumable_change:
            self._property_changed()

        try:
            result = self._protocol.action(mapping["siid"], mapping["aiid"], parameters)
        except Exception as ex:
            _LOGGER.error("Send action failed %s: %s", action.name, ex)
            self.schedule_update(1, True)
            return

        # Schedule update for retrieving new properties after action sent
        self.schedule_update(6, bool(not map_action and self._protocol.dreame_cloud))
        if result and result.get("code") == 0:
            _LOGGER.info("Send action %s %s", action.name, parameters)
            self._last_change = time.time()
            if not map_action:
                self._last_settings_request = 0
        else:
            _LOGGER.error("Send action failed %s (%s): %s", action.name, parameters, result)

        return result

    def send_command(self, command: str, parameters: dict[str, Any] = None) -> dict[str, Any] | None:
        """Send a raw command to the device. This is mostly useful when trying out
        commands which are not implemented by a given device instance. (Not likely)"""

        if command == "":
            raise InvalidActionException(f"Invalid Command: ({command}).")

        self.schedule_update(10, True)
        response = self._protocol.send(command, parameters, 3)
        if response:
            _LOGGER.info("Send command response: %s", response)
        self.schedule_update(2, True)

    def set_cleaning_mode(self, cleaning_mode: int) -> bool:
        """Set cleaning mode."""
        if self.status.cleaning_mode is None:
            raise InvalidActionException("Cleaning mode is not supported on this device")

        if self.status.cruising:
            raise InvalidActionException("Cannot set cleaning mode when cruising")

        if self.status.scheduled_clean or self.status.shortcut_task:
            raise InvalidActionException("Cannot set cleaning mode when scheduled cleaning or shortcut task")

        if (
            self.status.started
            and self.capability.custom_cleaning_mode
            and (self.status.customized_cleaning and not (self.status.zone_cleaning or self.status.spot_cleaning))
        ):
            raise InvalidActionException("Cannot set cleaning mode when customized cleaning is enabled")

        cleaning_mode = int(cleaning_mode)

        if self.status.started and not PROPERTY_AVAILABILITY[DreameMowerProperty.CLEANING_MODE.name](self):
            raise InvalidActionException("Cleaning mode unavailable")

        return self._update_cleaning_mode(cleaning_mode)


    def set_dnd_task(self, enabled: bool, dnd_start: str, dnd_end: str) -> bool:
        """Set do not disturb task"""
        if dnd_start is None or dnd_start == "":
            dnd_start = "22:00"

        if dnd_end is None or dnd_end == "":
            dnd_end = "08:00"

        time_pattern = re.compile("([0-1][0-9]|2[0-3]):[0-5][0-9]$")
        if not re.match(time_pattern, dnd_start):
            raise InvalidValueException("DnD start time is not valid: (%s).", dnd_start)
        if not re.match(time_pattern, dnd_end):
            raise InvalidValueException("DnD end time is not valid: (%s).", dnd_end)
        if dnd_start == dnd_end:
            raise InvalidValueException(
                "DnD Start time must be different from DnD end time: (%s == %s).",
                dnd_start,
                dnd_end,
            )

        if self.status.dnd_tasks is None:
            self.status.dnd_tasks = []

        if len(self.status.dnd_tasks) == 0:
            self.status.dnd_tasks.append(
                {
                    "id": 1,
                    "en": enabled,
                    "st": dnd_start,
                    "et": dnd_end,
                    "wk": 127,
                    "ss": 0,
                }
            )
        else:
            self.status.dnd_tasks[0]["en"] = enabled
            self.status.dnd_tasks[0]["st"] = dnd_start
            self.status.dnd_tasks[0]["et"] = dnd_end
        return self.set_property(
            DreameMowerProperty.DND_TASK,
            str(json.dumps(self.status.dnd_tasks, separators=(",", ":"))).replace(" ", ""),
        )

    def set_dnd(self, enabled: bool) -> bool:
        """Set do not disturb function"""
        return (
            self.set_property(DreameMowerProperty.DND, bool(enabled))
            if not self.capability.dnd_task
            else self.set_dnd_task(bool(enabled), self.status.dnd_start, self.status.dnd_end)
        )

    def set_dnd_start(self, dnd_start: str) -> bool:
        """Set do not disturb function"""
        return (
            self.set_property(DreameMowerProperty.DND_START, dnd_start)
            if not self.capability.dnd_task
            else self.set_dnd_task(self.status.dnd, str(dnd_start), self.status.dnd_end)
        )

    def set_dnd_end(self, dnd_end: str) -> bool:
        """Set do not disturb function"""
        if not self.capability.dnd_task:
            return self.set_property(DreameMowerProperty.DND_END, dnd_end)
        return self.set_dnd_task(self.status.dnd, self.status.dnd_start, str(dnd_end))

    def set_off_peak_charging_config(self, enabled: bool, start: str, end: str) -> bool:
        """Set of peak charging config"""
        if start is None or start == "":
            start = "22:00"

        if end is None or end == "":
            end = "08:00"

        time_pattern = re.compile("([0-1][0-9]|2[0-3]):[0-5][0-9]$")
        if not re.match(time_pattern, start):
            raise InvalidValueException("Start time is not valid: (%s).", start)
        if not re.match(time_pattern, end):
            raise InvalidValueException("End time is not valid: (%s).", end)
        if start == end:
            raise InvalidValueException("Start time must be different from end time: (%s == %s).", start, end)

        self.status.off_peak_charging_config = {
            "enable": enabled,
            "startTime": start,
            "endTime": end,
        }
        return self.set_property(
            DreameMowerProperty.OFF_PEAK_CHARGING,
            str(json.dumps(self.status.off_peak_charging_config, separators=(",", ":"))).replace(" ", ""),
        )

    def set_off_peak_charging(self, enabled: bool) -> bool:
        """Set off peak charging function"""
        return self.set_off_peak_charging_config(
            bool(enabled),
            self.status.off_peak_charging_start,
            self.status.off_peak_charging_end,
        )

    def set_off_peak_charging_start(self, off_peak_charging_start: str) -> bool:
        """Set off peak charging function"""
        return self.set_off_peak_charging_config(
            self.status.off_peak_charging,
            str(off_peak_charging_start),
            self.status.off_peak_charging_end,
        )

    def set_off_peak_charging_end(self, off_peak_charging_end: str) -> bool:
        """Set off peak charging function"""
        return self.set_off_peak_charging_config(
            self.status.off_peak_charging,
            self.status.off_peak_charging_start,
            str(off_peak_charging_end),
        )

    def set_voice_assistant_language(self, voice_assistant_language: str) -> bool:
        if (
            self.get_property(DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE) is None
            or voice_assistant_language is None
            or len(voice_assistant_language) < 2
            or voice_assistant_language.upper() not in DreameMowerVoiceAssistantLanguage.__members__
        ):
            raise InvalidActionException(f"Voice assistant language ({voice_assistant_language}) is not supported")
        return self.set_property(
            DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE,
            DreameMowerVoiceAssistantLanguage[voice_assistant_language.upper()],
        )

    def locate(self) -> dict[str, Any] | None:
        """Locate the mower cleaner."""
        return self.call_action(DreameMowerAction.LOCATE)

    def start_mowing(self) -> dict[str, Any] | None:
        """Start or resume the cleaning task."""
        if self.status.fast_mapping_paused:
            return self.start_custom(DreameMowerStatus.FAST_MAPPING.value)

        if self.status.returning_paused:
            return self.return_to_base()

        if self.capability.cruising:
            if self.status.cruising_paused:
                return self.start_custom(self.status.status.value)
        elif not self.status.paused:
            self._restore_go_to_zone()


        self.schedule_update(10, True)

        if not self.status.started:
            self._update_status(DreameMowerTaskStatus.AUTO_CLEANING, DreameMowerStatus.CLEANING)
        elif (
            self.status.paused
            and not self.status.cleaning_paused
            and not self.status.cruising
            and not self.status.scheduled_clean
        ):
            self._update_property(DreameMowerProperty.STATUS, DreameMowerStatus.CLEANING.value)
            if self.status.task_status is not DreameMowerTaskStatus.COMPLETED:
                new_state = DreameMowerState.MOWING
                self._update_property(DreameMowerProperty.STATE, new_state.value)

        if self._map_manager:
            if not self.status.started:
                self._map_manager.editor.clear_path()
            self._map_manager.editor.refresh_map()

        return self.call_action(DreameMowerAction.START_MOWING)

    def start(self) -> dict[str, Any] | None:
        """Start or resume the cleaning task."""
        if self.status.fast_mapping_paused:
            return self.start_custom(DreameMowerStatus.FAST_MAPPING.value)

        if self.status.returning_paused:
            return self.return_to_base()

        if self.capability.cruising:
            if self.status.cruising_paused:
                return self.start_custom(self.status.status.value)
        elif not self.status.paused:
            self._restore_go_to_zone()


        self.schedule_update(10, True)

        if not self.status.started:
            self._update_status(DreameMowerTaskStatus.AUTO_CLEANING, DreameMowerStatus.CLEANING)
        elif (
            self.status.paused
            and not self.status.cleaning_paused
            and not self.status.cruising
            and not self.status.scheduled_clean
        ):
            self._update_property(DreameMowerProperty.STATUS, DreameMowerStatus.CLEANING.value)
            if self.status.task_status is not DreameMowerTaskStatus.COMPLETED:
                new_state = DreameMowerState.MOWING
                self._update_property(DreameMowerProperty.STATE, new_state.value)

        if self._map_manager:
            if not self.status.started:
                self._map_manager.editor.clear_path()
            self._map_manager.editor.refresh_map()

        return self.call_action(DreameMowerAction.START_MOWING)

    def start_custom(self, status, parameters: dict[str, Any] = None) -> dict[str, Any] | None:
        """Start custom cleaning task."""
        if not self.capability.cruising and status != DreameMowerStatus.ZONE_CLEANING.value:
            self._restore_go_to_zone()

        if status is not DreameMowerStatus.FAST_MAPPING.value and self.status.fast_mapping:
            raise InvalidActionException("Cannot start cleaning while fast mapping")

        payload = [
            {
                "piid": PIID(DreameMowerProperty.STATUS, self.property_mapping),
                "value": status,
            }
        ]

        if parameters is not None:
            payload.append(
                {
                    "piid": PIID(DreameMowerProperty.CLEANING_PROPERTIES, self.property_mapping),
                    "value": parameters,
                }
            )

        return self.call_action(DreameMowerAction.START_CUSTOM, payload)

    def stop(self) -> dict[str, Any] | None:
        """Stop the mower cleaner."""
        if self.status.fast_mapping:
            return self.return_to_base()


        self.schedule_update(10, True)

        response = None
        if self.status.go_to_zone:
            response = self.call_action(DreameMowerAction.STOP)

        if self.status.started:
            self._update_status(DreameMowerTaskStatus.COMPLETED, DreameMowerStatus.STANDBY)

            # Clear active segments on current map data
            if self._map_manager:
                if self.status.go_to_zone:
                    self._map_manager.editor.set_active_areas([])
                self._map_manager.editor.set_cruise_points([])
                self._map_manager.editor.set_active_segments([])

        if response:
            return response

        return self.call_action(DreameMowerAction.STOP)

    def pause(self) -> dict[str, Any] | None:
        """Pause the cleaning task."""


        self.schedule_update(10, True)

        if not self.status.paused and self.status.started:
            if self.status.cruising and not self.capability.cruising:
                self._update_property(
                    DreameMowerProperty.STATE,
                    DreameMowerState.MONITORING_PAUSED.value,
                )
            else:
                self._update_property(DreameMowerProperty.STATE, DreameMowerState.PAUSED.value)
            self._update_property(DreameMowerProperty.STATUS, DreameMowerStatus.PAUSED.value)
            if self.status.go_to_zone:
                self._update_property(
                    DreameMowerProperty.TASK_STATUS,
                    DreameMowerTaskStatus.CRUISING_POINT_PAUSED.value,
                )

        return self.call_action(DreameMowerAction.PAUSE)

    def return_to_base(self) -> dict[str, Any] | None:
        """Set the mower cleaner to return to the dock."""
        if self._map_manager:
            self._map_manager.editor.set_cruise_points([])

        # if self.status.started:
        if not self.status.docked:
            self._update_property(DreameMowerProperty.STATUS, DreameMowerStatus.BACK_HOME.value)
            self._update_property(DreameMowerProperty.STATE, DreameMowerState.RETURNING.value)

        # Clear active segments on current map data
        # if self._map_manager:
        #    self._map_manager.editor.set_active_segments([])

        if not self.capability.cruising:
            self._restore_go_to_zone()
        return self.call_action(DreameMowerAction.DOCK)

    def dock(self) -> dict[str, Any] | None:
        """Set the mower cleaner to return to the dock."""
        if self._map_manager:
            self._map_manager.editor.set_cruise_points([])

        # if self.status.started:
        if not self.status.docked:
            self._update_property(DreameMowerProperty.STATUS, DreameMowerStatus.BACK_HOME.value)
            self._update_property(DreameMowerProperty.STATE, DreameMowerState.RETURNING.value)

        # Clear active segments on current map data
        # if self._map_manager:
        #    self._map_manager.editor.set_active_segments([])

        if not self.capability.cruising:
            self._restore_go_to_zone()
        return self.call_action(DreameMowerAction.DOCK)

    def start_pause(self) -> dict[str, Any] | None:
        """Start or resume the cleaning task."""
        if (
            not self.status.started
            or self.status.state is DreameMowerState.PAUSED
            or self.status.status is DreameMowerStatus.BACK_HOME
        ):
            return self.start()
        return self.pause()

    def clean_zone(
        self,
        zones: list[int] | list[list[int]],
        cleaning_times: int | list[int],
    ) -> dict[str, Any] | None:
        """Clean selected area."""

        if not isinstance(zones, list) or not zones:
            raise InvalidActionException(f"Invalid zone coordinates: %s", zones)

        if not isinstance(zones[0], list):
            zones = [zones]

        if cleaning_times is None or cleaning_times == "":
            cleaning_times = 1

        cleanlist = []
        index = 0
        for zone in zones:
            if not isinstance(zone, list) or len(zone) != 4:
                raise InvalidActionException(f"Invalid zone coordinates: %s", zone)

            if isinstance(cleaning_times, list):
                if index < len(cleaning_times):
                    repeat = cleaning_times[index]
                else:
                    repeat = 1
            else:
                repeat = cleaning_times

            index = index + 1

            x_coords = sorted([zone[0], zone[2]])
            y_coords = sorted([zone[1], zone[3]])

            grid_size = self.status.current_map.dimensions.grid_size if self.status.current_map else 50
            w = (x_coords[1] - x_coords[0]) / grid_size
            h = (y_coords[1] - y_coords[0]) / grid_size

            if h <= 1.0 or w <= 1.0:
                raise InvalidActionException(f"Zone {index} is smaller than minimum zone size ({h}, {w})")

            cleanlist.append(
                [
                    int(round(zone[0])),
                    int(round(zone[1])),
                    int(round(zone[2])),
                    int(round(zone[3])),
                    max(1, repeat),
                ]
            )

        self.schedule_update(10, True)
        if not self.capability.cruising:
            self._restore_go_to_zone()
        if not self.status.started or self.status.paused:
            self._update_status(DreameMowerTaskStatus.ZONE_CLEANING, DreameMowerStatus.ZONE_CLEANING)

            if self._map_manager:
                # Set active areas on current map data is implemented on the app
                if not self.status.started:
                    self._map_manager.editor.clear_path()
                self._map_manager.editor.set_active_areas(zones)

        return self.start_custom(
            DreameMowerStatus.ZONE_CLEANING.value,
            str(json.dumps({"areas": cleanlist}, separators=(",", ":"))).replace(" ", ""),
        )

    def clean_segment(
        self,
        selected_segments: int | list[int],
        cleaning_times: int | list[int] | None = None,
        timestamp: int | None = None,
    ) -> dict[str, Any] | None:
        """Clean selected segment using id."""

        if self.status.current_map and not self.status.has_saved_map:
            raise InvalidActionException("Cannot clean segments on current map")

        if not isinstance(selected_segments, list):
            selected_segments = [selected_segments]

        if cleaning_times is None or cleaning_times == "":
            cleaning_times = 1

        cleanlist = []
        index = 0
        segments = self.status.current_segments

        for segment_id in selected_segments:
            if isinstance(cleaning_times, list):
                if index < len(cleaning_times):
                    repeat = cleaning_times[index]
                else:
                    if segments and segment_id in segments and self.status.customized_cleaning:
                        repeat = segments[segment_id].cleaning_times
                    else:
                        repeat = 1
            else:
                repeat = cleaning_times


            index = index + 1
            cleanlist.append([segment_id, max(1, repeat), index])

        self.schedule_update(10, True)
        if not self.status.started or self.status.paused:
            self._update_status(
                DreameMowerTaskStatus.SEGMENT_CLEANING,
                DreameMowerStatus.SEGMENT_CLEANING,
            )

            if self._map_manager:
                if not self.status.started:
                    self._map_manager.editor.clear_path()

                # Set active segments on current map data is implemented on the app
                self._map_manager.editor.set_active_segments(selected_segments)

        data = {"selects": cleanlist}
        if timestamp is not None:
            data["timestamp"] = timestamp

        return self.start_custom(
            DreameMowerStatus.SEGMENT_CLEANING.value,
            str(json.dumps(data, separators=(",", ":"))).replace(" ", ""),
        )

    def clean_spot(
        self,
        points: list[int] | list[list[int]],
        cleaning_times: int | list[int] | None,
    ) -> dict[str, Any] | None:
        """Clean 1.5 square meters area of selected points."""

        if not isinstance(points, list) or not points:
            raise InvalidActionException(f"Invalid point coordinates: %s", points)

        if not isinstance(points[0], list):
            points = [points]

        if cleaning_times is None or cleaning_times == "":
            cleaning_times = 1

        cleanlist = []
        index = 0
        for point in points:
            if isinstance(cleaning_times, list):
                if index < len(cleaning_times):
                    repeat = cleaning_times[index]
                else:
                    repeat = 1
            else:
                repeat = cleaning_times


            index = index + 1

            if self.status.current_map and not self.status.current_map.check_point(point[0], point[1]):
                raise InvalidActionException(f"Coordinate ({point[0]}, {point[1]}) is not inside the map")

            cleanlist.append(
                [
                    int(round(point[0])),
                    int(round(point[1])),
                    repeat,
                ]
            )

        self.schedule_update(10, True)
        if not self.status.started or self.status.paused:
            self._update_status(DreameMowerTaskStatus.SPOT_CLEANING, DreameMowerStatus.SPOT_CLEANING)

            if self._map_manager:
                if not self.status.started:
                    self._map_manager.editor.clear_path()

                # Set active points on current map data is implemented on the app
                self._map_manager.editor.set_active_points(points)

        return self.start_custom(
            DreameMowerStatus.SPOT_CLEANING.value,
            str(json.dumps({"points": cleanlist}, separators=(",", ":"))).replace(" ", ""),
        )

    def go_to(self, x, y) -> dict[str, Any] | None:
        """Go to a point and take pictures around."""
        if self.status.current_map and not self.status.current_map.check_point(x, y):
            raise InvalidActionException("Coordinate is not inside the map")

        if self.status.battery_level < 15:
            raise InvalidActionException(
                "Low battery capacity. Please start the robot for working after it being fully charged."
            )

        if not self.capability.cruising:
            size = self.status.current_map.dimensions.grid_size if self.status.current_map else 50
            if self.status.current_map and self.status.current_map.robot_position:
                position = self.status.current_map.robot_position
                if abs(x - position.x) <= size and abs(y - position.y) <= size:
                    raise InvalidActionException(f"Robot is already on selected coordinate")
            self._set_go_to_zone(x, y, size)
            zone = [
                x - int(size / 2),
                y - int(size / 2),
                x + int(size / 2),
                y + int(size / 2),
            ]

        if not (self.status.started or self.status.paused):
            self._update_property(DreameMowerProperty.STATE, DreameMowerState.MONITORING.value)
            self._update_property(DreameMowerProperty.STATUS, DreameMowerStatus.CRUISING_POINT.value)
            self._update_property(
                DreameMowerProperty.TASK_STATUS,
                DreameMowerTaskStatus.CRUISING_POINT.value,
            )

            if self._map_manager:
                # Set active cruise points on current map data is implemented on the app
                self._map_manager.editor.set_cruise_points([[x, y, 0, 0]])

        if self.capability.cruising:
            return self.start_custom(
                DreameMowerStatus.CRUISING_POINT.value,
                str(
                    json.dumps(
                        {"tpoint": [[x, y, 0, 0]]},
                        separators=(",", ":"),
                    )
                ).replace(" ", ""),
            )
        else:
            cleanlist = [
                int(round(zone[0])),
                int(round(zone[1])),
                int(round(zone[2])),
                int(round(zone[3])),
                1,
                0,
                1,
            ]

            response = self.start_custom(
                DreameMowerStatus.ZONE_CLEANING.value,
                str(json.dumps({"areas": [cleanlist]}, separators=(",", ":"))).replace(" ", ""),
            )
            if not response:
                self._restore_go_to_zone()

            return response

    def follow_path(self, points: list[int] | list[list[int]]) -> dict[str, Any] | None:
        """Start a survaliance job."""
        if not self.capability.cruising:
            raise InvalidActionException("Follow path is supported on this device")

        if self.status.stream_status != DreameMowerStreamStatus.IDLE:
            raise InvalidActionException(f"Follow path only works with live camera streaming")

        if self.status.battery_level < 15:
            raise InvalidActionException(
                "Low battery capacity. Please start the robot for working after it being fully charged."
            )

        if not points:
            points = []

        if points and not isinstance(points[0], list):
            points = [points]

        if self.status.current_map:
            for point in points:
                if not self.status.current_map.check_point(point[0], point[1]):
                    raise InvalidActionException(f"Coordinate ({point[0]}, {point[1]}) is not inside the map")

        path = []
        for point in points:
            path.append([int(round(point[0])), int(round(point[1])), 0, 1])

        predefined_points = []
        if self.status.current_map and self.status.current_map.predefined_points:
            for point in self.status.current_map.predefined_points.values():
                predefined_points.append([int(round(point.x)), int(round(point.y)), 0, 1])

        if len(path) == 0:
            path.extend(predefined_points)

        if len(path) == 0:
            raise InvalidActionException("At least one valid or saved coordinate is required")

        if not self.status.started or self.status.paused:
            self._update_property(DreameMowerProperty.STATE, DreameMowerState.MONITORING.value)
            self._update_property(DreameMowerProperty.STATUS, DreameMowerStatus.CRUISING_PATH.value)
            self._update_property(
                DreameMowerProperty.TASK_STATUS,
                DreameMowerTaskStatus.CRUISING_PATH.value,
            )

            if self._map_manager:
                # Set active cruise points on current map data is implemented on the app
                self._map_manager.editor.set_cruise_points(path[:20])

        return self.start_custom(
            DreameMowerStatus.CRUISING_PATH.value,
            str(
                json.dumps(
                    {"tpoint": path[:20]},
                    separators=(",", ":"),
                )
            ).replace(" ", ""),
        )

    def start_shortcut(self, shortcut_id: int) -> dict[str, Any] | None:
        """Start shortcut job."""

        if not self.status.started:
            if self.status.status is DreameMowerStatus.STANDBY:
                self._update_property(DreameMowerProperty.STATE, DreameMowerState.IDLE.value)

            self._update_property(DreameMowerProperty.STATUS, DreameMowerStatus.SEGMENT_CLEANING.value)
            self._update_property(
                DreameMowerProperty.TASK_STATUS,
                DreameMowerTaskStatus.SEGMENT_CLEANING.value,
            )

        if self.status.shortcuts and shortcut_id in self.status.shortcuts:
            self.status.shortcuts[shortcut_id].running = True

        return self.start_custom(
            DreameMowerStatus.SHORTCUT.value,
            str(shortcut_id),
        )

    def start_fast_mapping(self) -> dict[str, Any] | None:
        """Fast map."""
        if self.status.fast_mapping:
            return

        if self.status.battery_level < 15:
            raise InvalidActionException(
                "Low battery capacity. Please start the robot for working after it being fully charged."
            )

        self.schedule_update(10, True)
        self._update_status(DreameMowerTaskStatus.FAST_MAPPING, DreameMowerStatus.FAST_MAPPING)

        if self._map_manager:
            self._map_manager.editor.refresh_map()

        return self.start_custom(DreameMowerStatus.FAST_MAPPING.value)

    def start_mapping(self) -> dict[str, Any] | None:
        """Create a new map by cleaning whole floor."""
        self.schedule_update(10, True)
        if self._map_manager:
            self._update_status(DreameMowerTaskStatus.AUTO_CLEANING, DreameMowerStatus.CLEANING)
            self._map_manager.editor.reset_map()

        return self.start_custom(DreameMowerStatus.CLEANING.value, "3")

    def clear_warning(self) -> dict[str, Any] | None:
        """Clear warning error code from the mower cleaner."""
        if self.status.has_warning:
            return self.call_action(
                DreameMowerAction.CLEAR_WARNING,
                [
                    {
                        "piid": PIID(
                            DreameMowerProperty.CLEANING_PROPERTIES,
                            self.property_mapping,
                        ),
                        "value": f"[{self.status.error.value}]",
                    }
                ],
            )

    def remote_control_move_step(
        self, rotation: int = 0, velocity: int = 0, prompt: bool | None = None
    ) -> dict[str, Any] | None:
        """Send remote control command to device."""
        if self.status.fast_mapping:
            raise InvalidActionException("Cannot remote control mower while fast mapping")

        payload = '{"spdv":%(velocity)d,"spdw":%(rotation)d,"audio":"%(audio)s","random":%(random)d}' % {
            "velocity": velocity,
            "rotation": rotation,
            "audio": (
                "true"
                if prompt == True
                else (
                    "false"
                    if prompt == False or self._remote_control or self.status.status is DreameMowerStatus.SLEEPING
                    else "true"
                )
            ),
            "random": randrange(65535),
        }
        self._remote_control = True
        mapping = self.property_mapping[DreameMowerProperty.REMOTE_CONTROL]
        return self._protocol.set_property(mapping["siid"], mapping["piid"], payload, 1)

    def install_voice_pack(self, lang_id: int, url: str, md5: str, size: int) -> dict[str, Any] | None:
        """install a custom language pack"""
        payload = '{"id":"%(lang_id)s","url":"%(url)s","md5":"%(md5)s","size":%(size)d}' % {
            "lang_id": lang_id,
            "url": url,
            "md5": md5,
            "size": size,
        }
        mapping = self.property_mapping[DreameMowerProperty.VOICE_CHANGE]
        return self._protocol.set_property(mapping["siid"], mapping["piid"], payload, 3)

    def obstacle_image(self, index):
        if self.capability.map:
            map_data = self.status.current_map
            if map_data:
                return self._map_manager.get_obstacle_image(map_data, index)
        return (None, None)

    def obstacle_history_image(self, index, history_index, cruising=False):
        if self.capability.map:
            map_data = self.history_map(history_index, cruising)
            if map_data:
                return self._map_manager.get_obstacle_image(map_data, index)
        return (None, None)

    def history_map(self, index, cruising=False):
        if self.capability.map and index and str(index).isnumeric():
            item = None
            if cruising:
                if self.status._cruising_history and len(self.status._cruising_history) > int(index) - 1:
                    item = self.status._cruising_history[int(index) - 1]
            else:
                if self.status._cleaning_history and len(self.status._cleaning_history) > int(index) - 1:
                    item = self.status._cleaning_history[int(index) - 1]
            if item and item.object_name:
                if item.object_name not in self.status._history_map_data:
                    map_data = self._map_manager.get_history_map(item.object_name, item.key)
                    if map_data is None:
                        return None
                    map_data.last_updated = item.date.timestamp()
                    map_data.completed = item.completed
                    map_data.neglected_segments = item.neglected_segments
                    map_data.second_cleaning = item.second_cleaning
                    map_data.cleaned_area = item.cleaned_area
                    map_data.cleaning_time = item.cleaning_time
                    if item.cleanup_method is not None:
                        map_data.cleanup_method = item.cleanup_method
                    if map_data.cleaning_map_data:
                        map_data.cleaning_map_data.last_updated = item.date.timestamp()
                        map_data.cleaning_map_data.completed = item.completed
                        map_data.cleaning_map_data.neglected_segments = item.neglected_segments
                        map_data.cleaning_map_data.second_cleaning = item.second_cleaning
                        map_data.cleaning_map_data.cleaned_area = item.cleaned_area
                        map_data.cleaning_map_data.cleaning_time = item.cleaning_time
                        map_data.cleaning_map_data.cleanup_method = map_data.cleanup_method
                    self.status._history_map_data[item.object_name] = map_data
                return self.status._history_map_data[item.object_name]

    def recovery_map(self, map_id, index):
        if self.capability.map and map_id and index and str(index).isnumeric():
            if (map_id is None or map_id == "") and self.status.selected_map:
                map_id = self.status.selected_map.map_id

            return self._map_manager.get_recovery_map(map_id, index)

    def recovery_map_file(self, map_id, index):
        if self.capability.map and map_id and index and str(index).isnumeric():
            if (map_id is None or map_id == "") and self.status.selected_map:
                map_id = self.status.selected_map.map_id

            return self._map_manager.get_recovery_map_file(map_id, index)

    def set_ai_detection(self, settings: dict[str, bool] | int) -> dict[str, Any] | None:
        """Send ai detection parameters to the device."""
        if self.capability.ai_detection:
            if (self.status.ai_obstacle_detection or self.status.ai_obstacle_image_upload) and (
                self._protocol.cloud and not self.status.ai_policy_accepted
            ):
                prop = "prop.s_ai_config"
                response = self._protocol.cloud.get_batch_device_datas([prop])
                if response and prop in response and response[prop]:
                    try:
                        self.status.ai_policy_accepted = json.loads(response[prop]).get("privacyAuthed")
                    except:
                        pass

                if not self.status.ai_policy_accepted:
                    if self.status.ai_obstacle_detection:
                        self.status.ai_obstacle_detection = False

                    if self.status.ai_obstacle_image_upload:
                        self.status.ai_obstacle_image_upload = False

                    self._property_changed()

                    raise InvalidActionException(
                        "You need to accept privacy policy from the App before enabling AI obstacle detection feature"
                    )
            mapping = self.property_mapping[DreameMowerProperty.AI_DETECTION]
            if isinstance(settings, int):
                return self._protocol.set_property(mapping["siid"], mapping["piid"], settings, 3)
            return self._protocol.set_property(
                mapping["siid"],
                mapping["piid"],
                str(json.dumps(settings, separators=(",", ":"))).replace(" ", ""),
                3,
            )

    def set_ai_property(
        self, prop: DreameMowerStrAIProperty | DreameMowerAIProperty, value: bool
    ) -> dict[str, Any] | None:
        if self.capability.ai_detection:
            if prop.name not in self.ai_data:
                raise InvalidActionException("Not supported")
            current_value = self.get_ai_property(prop)

            self._dirty_ai_data[prop.name] = DirtyData(value, current_value, time.time())
            self.ai_data[prop.name] = value
            ai_value = self.get_property(DreameMowerProperty.AI_DETECTION)
            self._property_changed()
            try:
                if isinstance(ai_value, int):
                    bit = DreameMowerAIProperty[prop.name].value
                    result = self.set_ai_detection((ai_value | bit) if value else (ai_value & -(bit + 1)))
                else:
                    result = self.set_ai_detection({DreameMowerStrAIProperty[prop.name].value: bool(value)})

                if result is None or result[0]["code"] != 0:
                    _LOGGER.error(
                        "AI Property not updated: %s: %s -> %s",
                        prop.name,
                        current_value,
                        value,
                    )
                    if prop.name in self._dirty_ai_data:
                        del self._dirty_ai_data[prop.name]
                    self.ai_data[prop.name] = current_value
                    self._property_changed()
            except:
                if prop.name in self._dirty_ai_data:
                    del self._dirty_ai_data[prop.name]
                self.ai_data[prop.name] = current_value
                self._property_changed()
            return result

    def set_auto_switch_settings(self, settings) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            mapping = self.property_mapping[DreameMowerProperty.AUTO_SWITCH_SETTINGS]
            return self._protocol.set_property(
                mapping["siid"],
                mapping["piid"],
                str(json.dumps(settings, separators=(",", ":"))).replace(" ", ""),
                1,
            )

    def set_auto_switch_property(self, prop: DreameMowerAutoSwitchProperty, value: int) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            if prop.name not in self.auto_switch_data:
                raise InvalidActionException("Not supported")
            current_value = self.get_auto_switch_property(prop)
            if current_value != value:
                self._dirty_auto_switch_data[prop.name] = DirtyData(value, current_value, time.time())
                self.auto_switch_data[prop.name] = value
                self._property_changed()
                try:
                    result = self.set_auto_switch_settings({"k": prop.value, "v": int(value)})
                    if result is None or result[0]["code"] != 0:
                        _LOGGER.error(
                            "Auto Switch Property not updated: %s: %s -> %s",
                            prop.name,
                            current_value,
                            value,
                        )
                        if prop.name in self._dirty_auto_switch_data:
                            del self._dirty_auto_switch_data[prop.name]
                        self.auto_switch_data[prop.name] = current_value
                        self._property_changed()
                    else:
                        _LOGGER.info("Update Property: %s: %s -> %s", prop.name, current_value, value)
                        if prop.name in self._dirty_auto_switch_data:
                            self._dirty_auto_switch_data[prop.name].update_time = time.time()
                except:
                    if prop.name in self._dirty_auto_switch_data:
                        del self._dirty_auto_switch_data[prop.name]
                    self.auto_switch_data[prop.name] = current_value
                    self._property_changed()
                return result

    def set_camera_light_brightness(self, brightness: int) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            if brightness < 40:
                brightness = 40
            current_value = self.status.camera_light_brightness
            self._update_property(DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS, str(brightness))
            result = self.call_stream_property_action(
                DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS, {"value": str(brightness)}
            )
            if result is None or result.get("code") != 0:
                self._update_property(DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS, str(current_value))
            return result

    def set_wider_corner_coverage(self, value: int) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            current_value = self.get_auto_switch_property(DreameMowerAutoSwitchProperty.WIDER_CORNER_COVERAGE)
            if current_value is not None and current_value > 0 and value <= 0:
                value = -current_value
            return self.set_auto_switch_property(DreameMowerAutoSwitchProperty.WIDER_CORNER_COVERAGE, value)

    def set_resume_cleaning(self, value: int) -> dict[str, Any] | None:
        if self.capability.auto_charging and bool(value):
            value = 2
        return self.set_property(DreameMowerProperty.RESUME_CLEANING, value)

    def set_multi_floor_map(self, enabled: bool) -> bool:
        if self.set_property(DreameMowerProperty.MULTI_FLOOR_MAP, int(enabled)):
            if (
                self.capability.auto_switch_settings
                and not enabled
                and self.get_property(DreameMowerProperty.INTELLIGENT_RECOGNITION) == 1
            ):
                self.set_property(DreameMowerProperty.INTELLIGENT_RECOGNITION, 0)
            return True
        return False

    def rename_shortcut(self, shortcut_id: int, shortcut_name: str = "") -> dict[str, Any] | None:
        """Rename a shortcut"""
        if self.status.started:
            raise InvalidActionException("Cannot rename a shortcut while mower is running")

        if not self.capability.shortcuts or not self.status.shortcuts:
            raise InvalidActionException("Shortcuts are not supported on this device")

        if shortcut_id not in self.status.shortcuts:
            raise InvalidActionException(f"Shortcut {shortcut_id} not found")

        if shortcut_name and len(shortcut_name) > 0:
            current_name = self.status.shortcuts[shortcut_id]
            if current_name != shortcut_name:
                counter = 1
                for id, shortcut in self.status.shortcuts.items():
                    if shortcut.name == shortcut_name and shortcut.id != shortcut_id:
                        counter = counter + 1

                if counter > 1:
                    shortcut_name = f"{shortcut_name}{counter}"

                self.status.shortcuts[shortcut_id].name = shortcut_name
                shortcut_name = base64.b64encode(shortcut_name.encode("utf-8")).decode("utf-8")
                shortcuts = self.get_property(DreameMowerProperty.SHORTCUTS)
                if shortcuts and shortcuts != "":
                    shortcuts = json.loads(shortcuts)
                    if shortcuts:
                        for shortcut in shortcuts:
                            if shortcut["id"] == shortcut_id:
                                shortcut["name"] = shortcut_name
                                break
                self._update_property(
                    DreameMowerProperty.SHORTCUTS,
                    str(json.dumps(shortcuts, separators=(",", ":"))).replace(" ", ""),
                )
                self._property_changed()

                success = False
                response = self.call_shortcut_action(
                    "EDIT_COMMAND",
                    {"id": shortcut_id, "name": shortcut_name, "type": 3},
                )
                if response and "out" in response:
                    data = response["out"]
                    if data and len(data):
                        if "value" in data[0] and data[0]["value"] != "":
                            success = data[0]["value"] == "0"
                if not success:
                    self.status.shortcuts[shortcut_id].name = current_name
                    self._property_changed()
                return response

    def set_obstacle_ignore(self, x, y, obstacle_ignored) -> dict[str, Any] | None:
        if not self.capability.ai_detection:
            raise InvalidActionException("Obstacle detection is not available on this device")

        if not self._map_manager:
            raise InvalidActionException("Obstacle ignore requires cloud connection")

        if self.status.started:
            raise InvalidActionException("Cannot set obstacle ignore status while mower is running")

        if not self.status.current_map and not self.status.current_map.obstacles:
            raise InvalidActionException("Obstacle not found")

        if self.status.current_map.obstacles is None or (
            len(self.status.current_map.obstacles)
            and next(iter(self.status.current_map.obstacles.values())).ignore_status is None
        ):
            raise InvalidActionException("Obstacle ignore is not supported on this device")

        found = False
        obstacle_type = 142
        for k, v in self.status.current_map.obstacles.items():
            if int(v.x) == int(x) and int(v.y) == int(y):
                if v.ignore_status.value == 2:
                    raise InvalidActionException("Cannot ignore a dynamically ignored obstacle")
                obstacle_type = v.type.value
                found = True
                break

        if not found:
            raise InvalidActionException("Obstacle not found")

        self._map_manager.editor.set_obstacle_ignore(x, y, obstacle_ignored)
        return self.update_map_data_async(
            {
                "obstacleignore": [
                    int(x),
                    int(y),
                    obstacle_type,
                    1 if bool(obstacle_ignored) else 0,
                ]
            }
        )

    def set_router_position(self, x, y):
        if not self.capability.wifi_map:
            raise InvalidActionException("WiFi map is not available on this device")

        if self.status.started:
            raise InvalidActionException("Cannot set router position while mower is running")

        if self._map_manager:
            self._map_manager.editor.set_router_position(x, y)
        return self.update_map_data_async({"wrp": [int(x), int(y)]})

    def request_map(self) -> dict[str, Any] | None:
        """Send map request action to the device.
        Device will upload a new map on cloud after this command if it has a saved map on memory.
        Otherwise this action will timeout when device is spot cleaning or a restored map exists on memory.
        """

        if self._map_manager:
            return self._map_manager.request_new_map()
        return self.call_action(
            DreameMowerAction.REQUEST_MAP,
            [
                {
                    "piid": PIID(DreameMowerProperty.FRAME_INFO, self.property_mapping),
                    "value": '{"frame_type":"I"}',
                }
            ],
        )

    def update_map_data_async(self, parameters: dict[str, Any]):
        """Send update map action to the device."""
        if self._map_manager:
            self._map_manager.schedule_update(10)
            self._property_changed()
            self._last_map_request = time.time()

        parameters = [
            {
                "piid": PIID(DreameMowerProperty.MAP_EXTEND_DATA, self.property_mapping),
                "value": str(json.dumps(parameters, separators=(",", ":"))).replace(" ", ""),
            }
        ]

        def callback(result):
            if result and result.get("code") == 0:
                _LOGGER.info("Send action UPDATE_MAP_DATA async %s", parameters)
                self._last_change = time.time()
            else:
                _LOGGER.error(
                    "Send action failed UPDATE_MAP_DATA async (%s): %s",
                    parameters,
                    result,
                )

            self.schedule_update(5)

            if self._map_manager:
                if self._protocol.dreame_cloud:
                    self._map_manager.schedule_update(3)
                else:
                    self._map_manager.request_next_map()
                    self._last_map_list_request = 0

        mapping = self.action_mapping[DreameMowerAction.UPDATE_MAP_DATA]
        self._protocol.action_async(callback, mapping["siid"], mapping["aiid"], parameters)

    def update_map_data(self, parameters: dict[str, Any]) -> dict[str, Any] | None:
        """Send update map action to the device."""
        if self._map_manager:
            self._map_manager.schedule_update(10)
            self._property_changed()
            self._last_map_request = time.time()

        response = self.call_action(
            DreameMowerAction.UPDATE_MAP_DATA,
            [
                {
                    "piid": PIID(DreameMowerProperty.MAP_EXTEND_DATA, self.property_mapping),
                    "value": str(json.dumps(parameters, separators=(",", ":"))).replace(" ", ""),
                }
            ],
        )

        self.schedule_update(5, True)

        if self._map_manager:
            if self._protocol.dreame_cloud:
                self._map_manager.schedule_update(3)
            else:
                self._map_manager.request_next_map()
                self._last_map_list_request = 0

        return response

    def rename_map(self, map_id: int, map_name: str = "") -> dict[str, Any] | None:
        """Set custom name for a map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot rename a map when temporary map is present")

        if map_name != "":
            map_name = map_name.replace(" ", "-")
            if self._map_manager:
                self._map_manager.editor.set_map_name(map_id, map_name)
            return self.update_map_data_async({"nrism": {map_id: {"name": map_name}}})

    def set_map_rotation(self, rotation: int, map_id: int = None) -> dict[str, Any] | None:
        """Set rotation of a map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot rotate a map when temporary map is present")

        if rotation is not None:
            rotation = int(rotation)
            if rotation > 270 or rotation < 0:
                rotation = 0

            if self._map_manager:
                if map_id is None:
                    map_id = self.status.selected_map.map_id
                self._map_manager.editor.set_rotation(map_id, rotation)

            if map_id is not None:
                return self.update_map_data_async({"smra": {map_id: {"ra": rotation}}})

    def set_restricted_zone(self, walls=[], zones=[], no_mops=[]) -> dict[str, Any] | None:
        """Set restricted zones on current saved map."""
        if walls == "":
            walls = []
        if zones == "":
            zones = []
        if no_mops == "":
            no_mops = []

        if self._map_manager:
            self._map_manager.editor.set_zones(walls, zones, no_mops)
        return self.update_map_data_async({"vw": {"line": walls, "rect": zones, "mop": no_mops}})

    def set_pathway(self, pathways=[]) -> dict[str, Any] | None:
        """Set pathways on current saved map."""
        if pathways == "":
            pathways = []

        if self._map_manager:
            if self.status.current_map and not (
                self.status.current_map.pathways is not None or self.capability.floor_material
            ):
                raise InvalidActionException("Pathways are not supported on this device")

            if self.status.current_map and not self.status.has_saved_map:
                raise InvalidActionException("Cannot edit pathways on current map")
            self._map_manager.editor.set_pathways(pathways)

        return self.update_map_data_async({"vws": {"vwsl": pathways}})

    def set_predefined_points(self, points=[]) -> dict[str, Any] | None:
        """Set predefined points on current saved map."""
        if points == "":
            points = []

        if not self.capability.cruising:
            raise InvalidActionException("Predefined points are not supported on this device")

        if self.status.started:
            raise InvalidActionException("Cannot set predefined points while mower is running")

        if self.status.current_map:
            for point in points:
                if not self.status.current_map.check_point(point[0], point[1]):
                    raise InvalidActionException(f"Coordinate ({point[0]}, {point[1]}) is not inside the map")

        predefined_points = []
        for point in points:
            predefined_points.append([point[0], point[1], 0, 1])

        if self._map_manager:
            if self.status.current_map and not self.status.has_saved_map:
                raise InvalidActionException("Cannot edit predefined points on current map")
            self._map_manager.editor.set_predefined_points(predefined_points[:20])

        return self.update_map_data_async({"spoint": predefined_points[:20], "tpoint": []})

    def set_selected_map(self, map_id: int) -> dict[str, Any] | None:
        """Change currently selected map when multi floor map is enabled."""
        if self.status.multi_map:
            self._map_select_time = time.time()
            if self._map_manager:
                self._map_manager.editor.set_selected_map(map_id)
            return self.update_map_data({"sm": {}, "mapid": map_id})

    def delete_map(self, map_id: int = None) -> dict[str, Any] | None:
        """Delete a map."""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot delete a map when temporary map is present")

        if self.status.started:
            raise InvalidActionException("Cannot delete a map while mower is running")

        if self._map_manager:
            if map_id == 0:
                map_id = None

            # Device do not deletes saved maps when you disable multi floor map feature
            # but it deletes all maps if you delete any map when multi floor map is disabled.
            if self.status.multi_map:
                if not map_id and self._map_manager.selected_map:
                    map_id = self._map_manager.selected_map.map_id
            else:
                if self._map_manager.selected_map and map_id == self._map_manager.selected_map.map_id:
                    self._map_manager.editor.delete_map()
                else:
                    self._map_manager.editor.delete_map(map_id)
        parameters = {"cm": {}}
        if map_id:
            parameters["mapid"] = map_id
        return self.update_map_data(parameters)

    def save_temporary_map(self) -> dict[str, Any] | None:
        """Replace new map with an old one when multi floor map is disabled."""
        if self.status.has_temporary_map:
            if self._map_manager:
                self._map_manager.editor.save_temporary_map()
            return self.update_map_data({"cw": 5})

    def discard_temporary_map(self) -> dict[str, Any] | None:
        """Discard new map when device have reached maximum number of maps it can store."""
        if self.status.has_temporary_map:
            if self._map_manager:
                self._map_manager.editor.discard_temporary_map()
            return self.update_map_data({"cw": 0})

    def replace_temporary_map(self, map_id: int = None) -> dict[str, Any] | None:
        """Replace new map with an old one when device have reached maximum number of maps it can store."""
        if self.status.has_temporary_map:
            if self.status.multi_map:
                raise InvalidActionException("Cannot replace a map when multi floor map is disabled")

            if self._map_manager:
                self._map_manager.editor.replace_temporary_map(map_id)
            parameters = {"cw": 1}
            if map_id:
                parameters["mapid"] = map_id
            return self.update_map_data(parameters)

    def restore_map_from_file(self, map_url: int, map_id: int = None) -> dict[str, Any] | None:
        map_recovery_status = self.status.map_recovery_status
        if map_recovery_status is None:
            raise InvalidActionException("Map recovery is not supported on this device")

        if map_recovery_status == DreameMapRecoveryStatus.RUNNING.value:
            raise InvalidActionException("Map recovery in progress")

        if map_id is None or map_id == "":
            if self.status.selected_map is None:
                raise InvalidActionException("Map ID is required")

            map_id = self.status.selected_map.map_id

        if self.status.map_data_list and not (map_id in self.status.map_data_list):
            raise InvalidActionException("Map not found")

        if self.status.started:
            raise InvalidActionException("Cannot set restore a map while mower is running")

        self.schedule_update(15)
        if self._map_manager:
            self._last_map_request = time.time()
            self._map_manager.schedule_update(15)

        self._update_property(
            DreameMowerProperty.MAP_RECOVERY_STATUS,
            DreameMapRecoveryStatus.RUNNING.value,
        )
        mapping = self.property_mapping[DreameMowerProperty.MAP_RECOVERY]
        response = self._protocol.set_property(
            mapping["siid"],
            mapping["piid"],
            str(json.dumps({"map_id": map_id, "map_url": map_url}, separators=(",", ":"))).replace(" ", ""),
        )
        if not response or response[0]["code"] != 0:
            self._update_property(DreameMowerProperty.MAP_RECOVERY_STATUS, map_recovery_status)
            raise InvalidActionException("Map recovery failed with error code %s", response[0]["code"])
        self._map_manager.schedule_update(5)
        self.schedule_update(1)
        return response

    def restore_map(self, recovery_map_index: int, map_id: int = None) -> dict[str, Any] | None:
        """Replace a map with previously saved version by device."""
        map_recovery_status = self.status.map_recovery_status
        if map_recovery_status is None:
            raise InvalidActionException("Map recovery is not supported on this device")

        if not self._map_manager:
            raise InvalidActionException("Map recovery requires cloud connection")

        if map_recovery_status == DreameMapRecoveryStatus.RUNNING.value:
            raise InvalidActionException("Map recovery in progress")

        if self.status.started:
            raise InvalidActionException("Cannot set restore a map while mower is running")

        if self.status.has_temporary_map:
            raise InvalidActionException("Restore a map when temporary map is present")

        if (map_id is None or map_id == "") and self.status.selected_map:
            map_id = self.status.selected_map.map_id

        if not map_id or map_id not in self.status.map_data_list:
            raise InvalidActionException("Map not found")

        if len(self.status.map_data_list[map_id].recovery_map_list) <= int(recovery_map_index) - 1:
            raise InvalidActionException("Invalid recovery map index")

        recovery_map_info = self.status.map_data_list[map_id].recovery_map_list[int(recovery_map_index) - 1]
        object_name = recovery_map_info.object_name
        if object_name and object_name != "":
            file, map_url, object_name = self.recovery_map_file(map_id, recovery_map_index)
            if map_url == None:
                raise InvalidActionException("Failed get recovery map file url: %s", object_name)

            if file == None:
                raise InvalidActionException("Failed to download recovery map file: %s", map_url)

            response = self.restore_map_from_file(map_url, map_id)
            if response and response[0]["code"] == 0:
                self._map_manager.editor.restore_map(recovery_map_info)
            return response
        raise InvalidActionException("Invalid recovery map object name")

    def backup_map(self, map_id: int = None) -> dict[str, Any] | None:
        """Save a map map to cloud for later use of restoring."""
        if not self.capability.backup_map:
            raise InvalidActionException("Map backup is not supported on this device")

        if self.status.map_backup_status == DreameMapBackupStatus.RUNNING.value:
            raise InvalidActionException("Map backup in progress")

        if map_id is None or map_id == "":
            if self.status.selected_map is None:
                raise InvalidActionException("Map ID is required")

            map_id = self.status.selected_map.map_id

        if self.status.map_data_list and not (map_id in self.status.map_data_list):
            raise InvalidActionException("Map not found")

        response = self.call_action(
            DreameMowerAction.BACKUP_MAP,
            [
                {
                    "piid": PIID(DreameMowerProperty.MAP_EXTEND_DATA, self.property_mapping),
                    "value": str(map_id),
                }
            ],
        )
        self.schedule_update(3, True)
        if response and response.get("code") == 0:
            self._update_property(
                DreameMowerProperty.MAP_BACKUP_STATUS,
                DreameMapBackupStatus.RUNNING.value,
            )
        return response

    def merge_segments(self, map_id: int, segments: list[int]) -> dict[str, Any] | None:
        """Merge segments on a map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if segments:
            if map_id == "":
                map_id = None

            if self._map_manager:
                if not map_id:
                    if self.capability.lidar_navigation and self._map_manager.selected_map:
                        map_id = self._map_manager.selected_map.map_id
                    else:
                        map_id = 0
                self._map_manager.editor.merge_segments(map_id, segments)

            if not map_id and self.capability.lidar_navigation:
                raise InvalidActionException("Map ID is required")

            data = {"msr": [segments[0], segments[1]]}
            if map_id:
                data["mapid"] = map_id
            return self.update_map_data(data)

    def split_segments(self, map_id: int, segment: int, line: list[int]) -> dict[str, Any] | None:
        """Split segments on a map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if segment and line is not None:
            if map_id == "":
                map_id = None

            if self._map_manager:
                if not map_id:
                    if self.capability.lidar_navigation and self._map_manager.selected_map:
                        map_id = self._map_manager.selected_map.map_id
                    else:
                        map_id = 0
                self._map_manager.editor.split_segments(map_id, segment, line)

            if not map_id and self.capability.lidar_navigation:
                raise InvalidActionException("Map ID is required")

            line.append(segment)
            data = {"dsrid": line}
            if map_id:
                data["mapid"] = map_id
            return self.update_map_data(data)

    def set_cleaning_sequence(self, cleaning_sequence: list[int]) -> dict[str, Any] | None:
        """Set cleaning sequence on current map.
        Device will use this order even you specify order in segment cleaning."""

        if not self.capability.customized_cleaning:
            raise InvalidActionException("Cleaning sequence is not supported on this device")

        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if self.status.started:
            raise InvalidActionException("Cannot set cleaning sequence while mower is running")

        if cleaning_sequence == "" or not cleaning_sequence:
            cleaning_sequence = []

        if self._map_manager:
            if cleaning_sequence and self.status.segments:
                for k in cleaning_sequence:
                    if int(k) not in self.status.segments.keys():
                        raise InvalidValueException("Segment not found! (%s)", k)

            map_data = self.status.current_map
            if map_data and map_data.segments and not map_data.temporary_map:
                if not cleaning_sequence:
                    current = self._map_manager.cleaning_sequence
                    if current and len(current):
                        self.status._previous_cleaning_sequence[map_data.map_id] = current
                    elif map_data.map_id in self.status._previous_cleaning_sequence:
                        del self.status._previous_cleaning_sequence[map_data.map_id]

                cleaning_sequence = self._map_manager.editor.set_cleaning_sequence(cleaning_sequence)

        return self.update_map_data_async({"cleanOrder": cleaning_sequence})

    def set_cleanset(self, cleanset: dict[str, list[int]]) -> dict[str, Any] | None:
        """Set customized cleaning settings on current map.
        Device will use these settings even you pass another setting for custom segment cleaning.
        """

        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if cleanset is not None:
            return self.update_map_data_async({"customeClean": cleanset})

    def set_custom_cleaning(
        self,
        segment_id: list[int],
        cleaning_times: list[int],
        cleaning_mode: list[int] = None,
    ) -> dict[str, Any] | None:
        """Set customized cleaning settings on current map.
        Device will use these settings even you pass another setting for custom segment cleaning.
        """

        if not self.capability.customized_cleaning:
            raise InvalidActionException("Customized cleaning is not supported on this device")

        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit customized cleaning parameters when temporary map is present")

        if self.status.started:
            raise InvalidActionException("Cannot edit customized cleaning parameters while mower is running")

        if cleaning_times:
            for v in cleaning_times:
                if int(v) < 1 or int(v) > 3:
                    raise InvalidActionException("Invalid cleaning times: %s", v)

        if cleaning_mode:
            for v in cleaning_mode:
                if int(v) < 0 or int(v) > 2:
                    raise InvalidActionException("Invalid cleaning mode: %s", v)

        if self.capability.map:
            if not self.status.has_saved_map:
                raise InvalidActionException("Cannot edit customized cleaning parameters on current map")

            current_map = self.status.current_map
            if current_map:
                segments = self.status.segments
                index = 0
                for k in segment_id:
                    id = int(k)
                    if not segments or id not in segments:
                        raise InvalidActionException("Invalid Segment ID: %s", id)
                    self._map_manager.editor.set_segment_cleaning_times(id, int(cleaning_times[index]), False)
                    if self.capability.custom_cleaning_mode:
                        self._map_manager.editor.set_segment_cleaning_mode(id, int(cleaning_mode[index]), False)
                    index = index + 1
                self._map_manager.editor.refresh_map()
                return self.set_cleanset(self._map_manager.editor.cleanset(current_map))

        custom_cleaning_mode = self.capability.custom_cleaning_mode
        has_cleaning_mode = cleaning_mode != "" and cleaning_mode is not None
        if (
            segment_id != ""
            and segment_id
            and cleaning_times != ""
            and cleaning_times is not None
        ):
            if has_cleaning_mode and not custom_cleaning_mode:
                raise InvalidActionException(
                    "Setting custom cleaning mode for segments is not supported by the device!"
                )
            elif not has_cleaning_mode and custom_cleaning_mode:
                raise InvalidActionException("Cleaning mode is required")

            if segments:
                count = len(segments.items())
                if (
                    len(segment_id) != count
                    or len(cleaning_times) != count
                    or (custom_cleaning_mode and len(cleaning_mode) != count)
                ):
                    raise InvalidActionException("Parameter count mismatch!")

            custom_cleaning = []
            index = 0

            for id in segment_id:
                values = [
                    id,
                    cleaning_times[index],
                ]
                if custom_cleaning_mode:
                    values.append(cleaning_mode[index])
                    if segments:
                        if id not in segments:
                            raise InvalidActionException("Invalid Segment ID: %s", id)

                custom_cleaning.append(values)
                index = index + 1

            return self.set_cleanset(custom_cleaning)

        raise InvalidActionException("Missing parameters!")

    def set_hidden_segments(self, invisible_segments: list[int]):
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if self.status.started:
            raise InvalidActionException("Cannot set room visibility while mower is running")

        if invisible_segments == "" or not invisible_segments:
            invisible_segments = []

        if self._map_manager:
            if invisible_segments and self.status.segments:
                for k in invisible_segments:
                    if int(k) not in self.status.segments.keys():
                        raise InvalidValueException("Segment not found! (%s)", k)

            # invisible_segments = self._map_manager.editor.set_invisible_segments(invisible_segments)

        return self.update_map_data_async({"delsr": invisible_segments})

    def set_segment_name(self, segment_id: int, segment_type: int, custom_name: str = None) -> dict[str, Any] | None:
        """Update name of a segment on current map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segment when temporary map is present")

        if self._map_manager:
            segment_info = self._map_manager.editor.set_segment_name(segment_id, segment_type, custom_name)
            if segment_info:
                data = {"nsr": segment_info}
                if self.status.current_map:
                    data["mapid"] = self.status.current_map.map_id
                if self.capability.auto_rename_segment:
                    data["autonsr"] = True
                return self.update_map_data_async(data)

    def set_segment_order(self, segment_id: int, order: int) -> dict[str, Any] | None:
        """Update cleaning order of a segment on current map"""
        if self._map_manager and not self.status.has_temporary_map:
            if order is None or (isinstance(order, str) and not order.isnumeric()):
                order = 0

            cleaning_order = self._map_manager.editor.set_segment_order(segment_id, order)

            return self.update_map_data_async({"cleanOrder": cleaning_order})

    def set_segment_cleaning_mode(self, segment_id: int, cleaning_mode: int) -> dict[str, Any] | None:
        """Update mop pad humidity of a segment on current map"""
        if self._map_manager and not self.status.has_temporary_map:
            return self.set_cleanset(self._map_manager.editor.set_segment_cleaning_mode(segment_id, cleaning_mode))

    def set_segment_cleaning_route(self, segment_id: int, cleaning_route: int) -> dict[str, Any] | None:
        """Update cleaning route of a segment on current map"""
        if (
            self.capability.cleaning_route
            and self._map_manager
            and not self.status.has_temporary_map
        ):
            return self.set_cleanset(self._map_manager.editor.set_segment_cleaning_route(segment_id, cleaning_route))

    def set_segment_cleaning_times(self, segment_id: int, cleaning_times: int) -> dict[str, Any] | None:
        """Update cleaning times of a segment on current map."""
        if self.status.started:
            raise InvalidActionException("Cannot set room cleaning times while mower is running")

        if self._map_manager and not self.status.has_temporary_map:
            return self.set_cleanset(self._map_manager.editor.set_segment_cleaning_times(segment_id, cleaning_times))

    def set_segment_floor_material(
        self, segment_id: int, floor_material: int, direction: int = None
    ) -> dict[str, Any] | None:
        """Update floor material of a segment on current map"""
        if self._map_manager and not self.status.has_temporary_map:
            if not self.capability.floor_direction_cleaning:
                direction = None
            else:
                if floor_material != 1:
                    direction = None
                elif direction is None:
                    segment = self.status.segments[segment_id]
                    direction = (
                        segment.floor_material_rotated_direction
                        if segment.floor_material_rotated_direction is not None
                        else (
                            0
                            if self.status.current_map.rotation == 0 or self.status.current_map.rotation == 90
                            else 90
                        )
                    )

            data = {"nsm": self._map_manager.editor.set_segment_floor_material(segment_id, floor_material, direction)}
            if self.status.selected_map:
                data["map_id"] = self.status.selected_map.map_id
            return self.update_map_data_async(data)

    def set_segment_floor_material_direction(
        self, segment_id: int, floor_material_direction: int
    ) -> dict[str, Any] | None:
        """Update floor material direction of a segment on current map"""
        if self.capability.floor_direction_cleaning and self._map_manager and not self.status.has_temporary_map:
            data = {
                "nsm": self._map_manager.editor.set_segment_floor_material(segment_id, 1, floor_material_direction)
            }
            if self.status.selected_map:
                data["map_id"] = self.status.selected_map.map_id
            return self.update_map_data_async(data)

    def set_segment_visibility(self, segment_id: int, visibility: int) -> dict[str, Any] | None:
        """Update visibility a segment on current map"""
        if self.capability.segment_visibility and self._map_manager and not self.status.has_temporary_map:
            data = {"delsr": self._map_manager.editor.set_segment_visibility(segment_id, int(visibility))}
            # if self.status.selected_map:
            #    data["map_id"] = self.status.selected_map.map_id
            return self.update_map_data_async(data)

    @property
    def _update_interval(self) -> float:
        """Dynamic update interval of the device for the timer."""
        now = time.time()
        if self.status.map_backup_status or self.status.map_recovery_status:
            return 2
        if self._last_update_failed:
            return 5 if now - self._last_update_failed <= 60 else 10 if now - self._last_update_failed <= 300 else 30
        if not -self._last_change <= 60:
            return 3 if self.status.active else 5
        if self.status.active or self.status.started:
            return 3 if self.status.running else 5
        if self._map_manager:
            return min(self._map_update_interval, 10)
        return 10

    @property
    def _map_update_interval(self) -> float:
        """Dynamic map update interval for the map manager."""
        if self._map_manager:
            if self._protocol.dreame_cloud:
                return 10 if self.status.active else 30
            now = time.time()
            if now - self._last_map_request <= 120 or now - self._last_change <= 60:
                return 2.5 if self.status.active or self.status.started else 5
            return 3 if self.status.running else 10 if self.status.active else 30
        return -1

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def device_connected(self) -> bool:
        """Return connection status of the device."""
        return self._protocol.connected

    @property
    def cloud_connected(self) -> bool:
        """Return connection status of the device."""
        return (
            self._protocol.cloud
            and self._protocol.cloud.connected
        )


class DreameMowerDeviceStatus:
    """Helper class for device status and int enum type properties.
    This class is used for determining various states of the device by its properties.
    Determined states are used by multiple validation and rendering condition checks.
    Almost of the rules are extracted from mobile app that has a similar class with same purpose.
    """

    def __init__(self, device):
        self._device: DreameMowerDevice = device
        self._cleaning_history = None
        self._cleaning_history_attrs = None
        self._last_cleaning_time = None
        self._cruising_history = None
        self._cruising_history_attrs = None
        self._last_cruising_time = None
        self._history_map_data: dict[str, MapData] = {}
        self._previous_cleaning_sequence: dict[int, list[int]] = {}

        self.cleaning_mode_list = {v: k for k, v in CLEANING_MODE_CODE_TO_NAME.items()}
        self.wider_corner_coverage_list = {v: k for k, v in WIDER_CORNER_COVERAGE_TO_NAME.items()}
        self.second_cleaning_list = {v: k for k, v in SECOND_CLEANING_TO_NAME.items()}
        self.cleaning_route_list = {v: k for k, v in CLEANING_ROUTE_TO_NAME.items()}
        self.cleangenius_list = {v: k for k, v in CLEANGENIUS_TO_NAME.items()}
        self.floor_material_list = {v: k for k, v in FLOOR_MATERIAL_CODE_TO_NAME.items()}
        self.floor_material_direction_list = {v: k for k, v in FLOOR_MATERIAL_DIRECTION_CODE_TO_NAME.items()}
        self.visibility_list = {v: k for k, v in SEGMENT_VISIBILITY_CODE_TO_NAME.items()}
        self.voice_assistant_language_list = {v: k for k, v in VOICE_ASSISTANT_LANGUAGE_TO_NAME.items()}
        self.segment_cleaning_mode_list = {}
        self.segment_cleaning_route_list = {}
        self.warning_codes = [
            DreameMowerErrorCode.BLOCKED,
            DreameMowerErrorCode.STATION_DISCONNECTED,
            DreameMowerErrorCode.SELF_TEST_FAILED,
            DreameMowerErrorCode.LOW_BATTERY_TURN_OFF,
            DreameMowerErrorCode.UNKNOWN_WARNING_2,
        ]

        self.cleaning_mode = None
        self.ai_policy_accepted = False
        self.go_to_zone: GoToZoneSettings = None
        self.cleanup_completed: bool = False
        self.cleanup_started: bool = False

        self.stream_status = None
        self.stream_session = None

        self.dnd_tasks = None
        self.off_peak_charging_config = None
        self.shortcuts = None

    def _get_property(self, prop: DreameMowerProperty) -> Any:
        """Helper function for accessing a property from device"""
        _LOGGER.debug("Getting property: %s", prop)
        result = self._device.get_property(prop)
        _LOGGER.debug("Result: %s", result)
        return result

    @property
    def _capability(self) -> DreameMowerDeviceCapability:
        """Helper property for accessing device capabilities"""
        return self._device.capability

    @property
    def _map_manager(self) -> DreameMapMowerMapManager | None:
        """Helper property for accessing map manager from device"""
        return self._device._map_manager

    @property
    def _device_connected(self) -> bool:
        """Helper property for accessing device connection status"""
        return self._device.device_connected

    @property
    def battery_level(self) -> int:
        """Return battery level of the device."""
        return self._get_property(DreameMowerProperty.BATTERY_LEVEL)

    @property
    def cleaning_mode_name(self) -> str:
        """Return cleaning mode as string for translation."""
        return CLEANING_MODE_CODE_TO_NAME.get(self.cleaning_mode, STATE_UNKNOWN)

    @property
    def status(self) -> DreameMowerStatus:
        """Return status of the device."""
        value = self._get_property(DreameMowerProperty.STATUS)
        if value is not None and value in DreameMowerStatus._value2member_map_:
            if self.go_to_zone and value == DreameMowerStatus.ZONE_CLEANING.value:
                return DreameMowerStatus.CRUISING_POINT
            if value == DreameMowerStatus.CHARGING.value and not self.charging:
                return DreameMowerStatus.IDLE
            return DreameMowerStatus(value)
        if value is not None:
            _LOGGER.debug("STATUS not supported: %s", value)
        return DreameMowerStatus.UNKNOWN

    @property
    def status_name(self) -> str:
        """Return status as string for translation."""
        return STATUS_CODE_TO_NAME.get(self.status, STATE_UNKNOWN)

    @property
    def task_status(self) -> DreameMowerTaskStatus:
        """Return task status of the device."""
        value = self._get_property(DreameMowerProperty.TASK_STATUS)
        if value is not None and value in DreameMowerTaskStatus._value2member_map_:
            if self.go_to_zone:
                if value == DreameMowerTaskStatus.ZONE_CLEANING.value:
                    return DreameMowerTaskStatus.CRUISING_POINT
                if value == DreameMowerTaskStatus.ZONE_CLEANING_PAUSED.value:
                    return DreameMowerTaskStatus.CRUISING_POINT_PAUSED
            return DreameMowerTaskStatus(value)
        if value is not None:
            _LOGGER.debug("TASK_STATUS not supported: %s", value)
        return DreameMowerTaskStatus.UNKNOWN

    @property
    def task_status_name(self) -> str:
        """Return task status as string for translation."""
        return TASK_STATUS_CODE_TO_NAME.get(self.task_status, STATE_UNKNOWN)

    @property
    def charging_status(self) -> DreameMowerChargingStatus:
        """Return charging status of the device."""
        value = self._get_property(DreameMowerProperty.CHARGING_STATUS)
        if value is not None and value in DreameMowerChargingStatus._value2member_map_:
            value = DreameMowerChargingStatus(value)
            # Charging status complete is not present on older firmwares
            if value is DreameMowerChargingStatus.CHARGING and self.battery_level == 100:
                return DreameMowerChargingStatus.CHARGING_COMPLETED
            return value
        if value is not None:
            _LOGGER.debug("CHARGING_STATUS not supported: %s", value)
        return DreameMowerChargingStatus.UNKNOWN

    @property
    def charging_status_name(self) -> str:
        """Return charging status as string for translation."""
        return CHARGING_STATUS_CODE_TO_NAME.get(self.charging_status, STATE_UNKNOWN)

    @property
    def relocation_status(self) -> DreameMowerRelocationStatus:
        """Return relocation status of the device."""
        value = self._get_property(DreameMowerProperty.RELOCATION_STATUS)
        if value is not None and value in DreameMowerRelocationStatus._value2member_map_:
            return DreameMowerRelocationStatus(value)
        if value is not None:
            _LOGGER.debug("RELOCATION_STATUS not supported: %s", value)
        return DreameMowerRelocationStatus.UNKNOWN

    @property
    def relocation_status_name(self) -> str:
        """Return relocation status as string for translation."""
        return RELOCATION_STATUS_CODE_TO_NAME.get(self.relocation_status, STATE_UNKNOWN)

    @property
    def state(self) -> DreameMowerState:
        """Return state of the device."""
        value = self._get_property(DreameMowerProperty.STATE)
        if (
            value is not None
            and int(value) > 18
            and not self._capability.new_state
            and value in DreameMowerStateOld._value2member_map_
        ):
            value = DreameMowerState[DreameMowerStateOld(value).name].value

        if value is not None and value in DreameMowerState._value2member_map_:
            if self.go_to_zone and (
                value == DreameMowerState.IDLE
                or value == DreameMowerState.MOWING.value
            ):
                if self.paused:
                    return DreameMowerState.MONITORING_PAUSED
                return DreameMowerState.MONITORING
            mower_state = DreameMowerState(value)

            ## Determine state as implemented on the app
            if mower_state is DreameMowerState.IDLE:
                if self.started or self.cleaning_paused or self.fast_mapping_paused:
                    return DreameMowerState.PAUSED
                elif self.docked:
                    if self.charging:
                        return DreameMowerState.CHARGING
                    ## This is for compatibility with various lovelace mower cards
                    ## Device will report idle when charging is completed and mower card will display return to dock icon even when robot is docked
                    if self.charging_status is DreameMowerChargingStatus.CHARGING_COMPLETED:
                        return DreameMowerState.CHARGING_COMPLETED
            return mower_state
        if value is not None:
            _LOGGER.debug("STATE not supported: %s", value)
        return DreameMowerState.UNKNOWN

    @property
    def state_name(self) -> str:
        """Return state as string for translation."""
        return STATE_CODE_TO_STATE.get(self.state, STATE_UNKNOWN)

    @property
    def stream_status_name(self) -> str:
        """Return camera stream status as string for translation."""
        return STREAM_STATUS_TO_NAME.get(self.stream_status, STATE_UNKNOWN)

    @property
    def wider_corner_coverage(self) -> DreameMowerWiderCornerCoverage:
        value = self._device.get_auto_switch_property(DreameMowerAutoSwitchProperty.WIDER_CORNER_COVERAGE)
        if value is not None and value < 0:
            value = 0
        if value is not None and value in DreameMowerWiderCornerCoverage._value2member_map_:
            return DreameMowerWiderCornerCoverage(value)
        if value is not None:
            _LOGGER.debug("WIDER_CORNER_COVERAGE not supported: %s", value)
        return DreameMowerWiderCornerCoverage.UNKNOWN

    @property
    def wider_corner_coverage_name(self) -> str:
        """Return wider corner coverage as string for translation."""
        wider_corner_coverage = 0 if self.wider_corner_coverage < 0 else self.wider_corner_coverage
        if (
            wider_corner_coverage is not None
            and wider_corner_coverage in DreameMowerWiderCornerCoverage._value2member_map_
        ):
            return WIDER_CORNER_COVERAGE_TO_NAME.get(
                DreameMowerWiderCornerCoverage(wider_corner_coverage), STATE_UNKNOWN
            )
        return STATE_UNKNOWN

    @property
    def cleaning_route(self) -> DreameMowerCleaningRoute:
        if self._capability.cleaning_route:
            value = self._device.get_auto_switch_property(DreameMowerAutoSwitchProperty.CLEANING_ROUTE)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameMowerCleaningRoute._value2member_map_:
                return DreameMowerCleaningRoute(value)
            if value is not None:
                _LOGGER.debug("CLEANING_ROUTE not supported: %s", value)
            return DreameMowerCleaningRoute.UNKNOWN

    @property
    def cleaning_route_name(self) -> str:
        """Return cleaning route as string for translation."""
        cleaning_route = 0 if self.cleaning_route < 0 else self.cleaning_route
        if cleaning_route is not None and cleaning_route in DreameMowerCleaningRoute._value2member_map_:
            return CLEANING_ROUTE_TO_NAME.get(DreameMowerCleaningRoute(cleaning_route), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def cleangenius(self) -> DreameMowerCleanGenius:
        if self._capability.cleangenius:
            value = self._device.get_auto_switch_property(DreameMowerAutoSwitchProperty.CLEANGENIUS)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameMowerCleanGenius._value2member_map_:
                return DreameMowerCleanGenius(value)
            if value is not None:
                _LOGGER.debug("CLEANGENIUS not supported: %s", value)
        return DreameMowerCleanGenius.UNKNOWN

    @property
    def cleangenius_name(self) -> str:
        """Return CleanGenius as string for translation."""
        cleangenius = 0 if not self.cleangenius or self.cleangenius < 0 else self.cleangenius
        if cleangenius is not None and cleangenius in DreameMowerCleanGenius._value2member_map_:
            return CLEANGENIUS_TO_NAME.get(DreameMowerCleanGenius(cleangenius), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def voice_assistant_language(self) -> DreameMowerVoiceAssistantLanguage:
        """Return voice assistant language of the device."""
        value = self._get_property(DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE)
        if value is not None and value in DreameMowerVoiceAssistantLanguage._value2member_map_:
            return DreameMowerVoiceAssistantLanguage(value)
        if value is not None:
            _LOGGER.debug("VOICE_ASSISTANT_LANGUAGE not supported: %s", value)
        return DreameMowerVoiceAssistantLanguage.DEFAULT

    @property
    def voice_assistant_language_name(self) -> str:
        """Return voice assistant language as string for translation."""
        return VOICE_ASSISTANT_LANGUAGE_TO_NAME.get(self.voice_assistant_language, STATE_UNKNOWN)

    @property
    def task_type(self) -> DreameMowerTaskType:
        """Return drainage status of the device."""
        value = self._get_property(DreameMowerProperty.TASK_TYPE)
        if value is not None and value in DreameMowerTaskType._value2member_map_:
            return DreameMowerTaskType(value)
        if value is not None:
            _LOGGER.debug("TASK_TYPE not supported: %s", value)
        return DreameMowerTaskType.UNKNOWN

    @property
    def task_type_name(self) -> str:
        """Return drainage status as string for translation."""
        return TASK_TYPE_TO_NAME.get(self.task_type, STATE_UNKNOWN)

    @property
    def faults(self) -> str:
        faults = self._get_property(DreameMowerProperty.FAULTS)
        return 0 if faults == "" or faults == " " else faults

    @property
    def error(self) -> DreameMowerErrorCode:
        """Return error of the device."""
        value = self._get_property(DreameMowerProperty.ERROR)
        if value is not None and value in DreameMowerErrorCode._value2member_map_:
            if (
                value == DreameMowerErrorCode.LOW_BATTERY_TURN_OFF.value
                or value == DreameMowerErrorCode.UNKNOWN_WARNING_2.value
            ):
                return DreameMowerErrorCode.NO_ERROR
            return DreameMowerErrorCode(value)
        if value is not None:
            _LOGGER.debug("ERROR_CODE not supported: %s", value)
        return DreameMowerErrorCode.UNKNOWN

    @property
    def error_name(self) -> str:
        """Return error as string for translation."""
        if not self.has_error and not self.has_warning:
            return ERROR_CODE_TO_ERROR_NAME.get(DreameMowerErrorCode.NO_ERROR)
        return ERROR_CODE_TO_ERROR_NAME.get(self.error, STATE_UNKNOWN)

    @property
    def error_description(self) -> str:
        """Return error description of the device."""
        return ERROR_CODE_TO_ERROR_DESCRIPTION.get(self.error, [STATE_UNKNOWN, ""])

    @property
    def error_image(self) -> str:
        """Return error image of the device as base64 string."""
        if not self.has_error:
            return None
        return ERROR_IMAGE.get(ERROR_CODE_TO_IMAGE_INDEX.get(self.error, 19))

    @property
    def robot_status(self) -> int:  # TODO: Convert to enum
        """Device status for robot icon rendering."""
        value = 0
        if self.running and not self.returning and not self.fast_mapping and not self.cruising:
            value = 1
        elif self.charging:
            value = 2
        elif self.sleeping:
            value = 3
        if self.has_error:
            value += 10
        return value

    @property
    def has_error(self) -> bool:
        """Returns true when an error is present."""
        error = self.error
        return bool(error.value > 0 and not self.has_warning and error is not DreameMowerErrorCode.BATTERY_LOW)

    @property
    def has_warning(self) -> bool:
        """Returns true when a warning is present and available for dismiss."""
        error = self.error
        return bool(error.value > 0 and error in self.warning_codes)

    @property
    def scheduled_clean(self) -> bool:
        if self.started:
            value = self._get_property(DreameMowerProperty.SCHEDULED_CLEAN)
            return bool(value == 1 or value == 2 or value == 4)
        return False

    @property
    def camera_light_brightness(self) -> int:
        if self._capability.camera_streaming:
            brightness = self._get_property(DreameMowerProperty.CAMERA_LIGHT_BRIGHTNESS)
            if brightness and str(brightness).isnumeric():
                return int(brightness)

    @property
    def dnd_remaining(self) -> bool:
        """Returns remaining seconds to DND period to end."""
        if self.dnd:
            dnd_start = self.dnd_start
            dnd_end = self.dnd_end
            if dnd_start and dnd_end:
                end_time = dnd_end.split(":")
                if len(end_time) == 2:
                    now = datetime.now()
                    hour = now.hour
                    minute = now.minute
                    if minute < 10:
                        minute = f"0{minute}"

                    time = int(f"{hour}{minute}")
                    start = int(dnd_start.replace(":", ""))
                    end = int(dnd_end.replace(":", ""))
                    current_seconds = hour * 3600 + int(minute) * 60
                    end_seconds = int(end_time[0]) * 3600 + int(end_time[1]) * 60

                    if (
                        start < end
                        and start < time
                        and time < end
                        or end < start
                        and (2400 > time and time > start or end > time and time > 0)
                        or time == start
                        or time == end
                    ):
                        return (
                            (end_seconds + 86400 - current_seconds)
                            if current_seconds > end_seconds
                            else (end_seconds - current_seconds)
                        )
                return 0
        return None

    @property
    def located(self) -> bool:
        """Returns true when robot knows its position on current map."""
        relocation_status = self.relocation_status
        return bool(
            relocation_status is DreameMowerRelocationStatus.LOCATED
            or relocation_status is DreameMowerRelocationStatus.UNKNOWN
            or self.fast_mapping
        )

    @property
    def sweeping(self) -> bool:
        """Returns true when cleaning mode is sweeping."""
        cleaning_mode = self.cleaning_mode
        return 1

    @property
    def zone_cleaning(self) -> bool:
        """Returns true when device is currently performing a zone cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameMowerTaskStatus.ZONE_CLEANING
                or task_status is DreameMowerTaskStatus.ZONE_CLEANING_PAUSED
                or task_status is DreameMowerTaskStatus.ZONE_DOCKING_PAUSED
            )
        )

    @property
    def spot_cleaning(self) -> bool:
        """Returns true when device is currently performing a spot cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameMowerTaskStatus.SPOT_CLEANING
                or task_status is DreameMowerTaskStatus.SPOT_CLEANING_PAUSED
                or self.status is DreameMowerStatus.SPOT_CLEANING
            )
        )

    @property
    def segment_cleaning(self) -> bool:
        """Returns true when device is currently performing a custom segment cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameMowerTaskStatus.SEGMENT_CLEANING
                or task_status is DreameMowerTaskStatus.SEGMENT_CLEANING_PAUSED
                or task_status is DreameMowerTaskStatus.SEGMENT_DOCKING_PAUSED
            )
        )

    @property
    def auto_cleaning(self) -> bool:
        """Returns true when device is currently performing a complete map cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameMowerTaskStatus.AUTO_CLEANING
                or task_status is DreameMowerTaskStatus.AUTO_CLEANING_PAUSED
                or task_status is DreameMowerTaskStatus.AUTO_DOCKING_PAUSED
            )
        )

    @property
    def fast_mapping(self) -> bool:
        """Returns true when device is creating a new map."""
        return bool(
            self._device_connected
            and (
                self.task_status is DreameMowerTaskStatus.FAST_MAPPING
                or self.status is DreameMowerStatus.FAST_MAPPING
                or self.fast_mapping_paused
            )
        )

    @property
    def fast_mapping_paused(self) -> bool:
        """Returns true when creating a new map paused by user.
        Used for resuming fast cleaning on start because standard start action can not be used for resuming fast mapping.
        """

        state = self._get_property(DreameMowerProperty.STATE)
        task_status = self.task_status
        return bool(
            (
                task_status is DreameMowerTaskStatus.FAST_MAPPING
                or task_status is DreameMowerTaskStatus.MAP_CLEANING_PAUSED
            )
            and (
                state == DreameMowerState.PAUSED.value
                or state == DreameMowerState.ERROR.value
                or state == DreameMowerState.IDLE.value
            )
        )

    @property
    def cruising(self) -> bool:
        """Returns true when device is cruising."""
        if self._capability.cruising:
            task_status = self.task_status
            status = self.status
            return bool(
                task_status is DreameMowerTaskStatus.CRUISING_PATH
                or task_status is DreameMowerTaskStatus.CRUISING_POINT
                or task_status is DreameMowerTaskStatus.CRUISING_PATH_PAUSED
                or task_status is DreameMowerTaskStatus.CRUISING_POINT_PAUSED
                or status is DreameMowerStatus.CRUISING_PATH
                or status is DreameMowerStatus.CRUISING_POINT
            )
        return bool(self.go_to_zone)

    @property
    def cruising_paused(self) -> bool:
        """Returns true when cruising paused."""
        if self._capability.cruising:
            task_status = self.task_status
            return bool(
                task_status is DreameMowerTaskStatus.CRUISING_PATH_PAUSED
                or task_status is DreameMowerTaskStatus.CRUISING_POINT_PAUSED
            )
        if self.go_to_zone:
            status = self.status
            if self.started and (
                status is DreameMowerStatus.PAUSED
                or status is DreameMowerStatus.SLEEPING
                or status is DreameMowerStatus.IDLE
                or status is DreameMowerStatus.STANDBY
            ):
                return True
        return False

    @property
    def resume_cleaning(self) -> bool:
        """Returns true when resume_cleaning is enabled."""
        return bool(
            self._get_property(DreameMowerProperty.RESUME_CLEANING) == (2 if self._capability.auto_charging else 1)
        )

    @property
    def cleaning_paused(self) -> bool:
        """Returns true when device battery is too low for resuming its task and needs to be charged before continuing."""
        return bool(self._get_property(DreameMowerProperty.CLEANING_PAUSED))

    @property
    def charging(self) -> bool:
        """Returns true when device is currently charging."""
        return bool(self.charging_status is DreameMowerChargingStatus.CHARGING)

    @property
    def docked(self) -> bool:
        """Returns true when device is docked."""
        return bool(
            (
                self.charging
                or self.charging_status is DreameMowerChargingStatus.CHARGING_COMPLETED
            )
            and not (self.running and not self.returning and not self.fast_mapping and not self.cruising)
        )

    @property
    def sleeping(self) -> bool:
        """Returns true when device is sleeping."""
        return bool(self.status is DreameMowerStatus.SLEEPING)

    @property
    def returning_paused(self) -> bool:
        """Returns true when returning to dock is paused."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and task_status is DreameMowerTaskStatus.DOCKING_PAUSED
            or task_status is DreameMowerTaskStatus.AUTO_DOCKING_PAUSED
            or task_status is DreameMowerTaskStatus.SEGMENT_DOCKING_PAUSED
            or task_status is DreameMowerTaskStatus.ZONE_DOCKING_PAUSED
        )

    @property
    def returning(self) -> bool:
        """Returns true when returning to dock for charging."""
        return bool(self._device_connected and (self.status is DreameMowerStatus.BACK_HOME))

    @property
    def started(self) -> bool:
        """Returns true when device has an active task.
        Used for preventing updates on settings that relates to currently performing task.
        """
        status = self.status
        return bool(
            (
                self.task_status is not DreameMowerTaskStatus.COMPLETED
                and self.task_status is not DreameMowerTaskStatus.DOCKING_PAUSED
            )
            or self.cleaning_paused
            or status is DreameMowerStatus.CLEANING
            or status is DreameMowerStatus.SEGMENT_CLEANING
            or status is DreameMowerStatus.ZONE_CLEANING
            or status is DreameMowerStatus.SPOT_CLEANING
            or status is DreameMowerStatus.PART_CLEANING
            or status is DreameMowerStatus.FAST_MAPPING
            or status is DreameMowerStatus.CRUISING_PATH
            or status is DreameMowerStatus.CRUISING_POINT
            or status is DreameMowerStatus.SHORTCUT
        )

    @property
    def paused(self) -> bool:
        """Returns true when device has an active paused task."""
        status = self.status
        return bool(
            self.cleaning_paused
            or self.cruising_paused
            or (
                self.started
                and (
                    status is DreameMowerStatus.PAUSED
                    or status is DreameMowerStatus.SLEEPING
                    or status is DreameMowerStatus.IDLE
                    or status is DreameMowerStatus.STANDBY
                )
            )
        )

    @property
    def active(self) -> bool:
        """Returns true when device is moving or not sleeping."""
        return self.status is DreameMowerStatus.STANDBY or self.running

    @property
    def running(self) -> bool:
        """Returns true when device is moving."""
        status = self.status
        return bool(
            not (
                self.charging
                or self.charging_status is DreameMowerChargingStatus.CHARGING_COMPLETED
            )
            and (
                status is DreameMowerStatus.CLEANING
                or status is DreameMowerStatus.BACK_HOME
                or status is DreameMowerStatus.PART_CLEANING
                or status is DreameMowerStatus.FOLLOW_WALL
                or status is DreameMowerStatus.REMOTE_CONTROL
                or status is DreameMowerStatus.SEGMENT_CLEANING
                or status is DreameMowerStatus.ZONE_CLEANING
                or status is DreameMowerStatus.SPOT_CLEANING
                or status is DreameMowerStatus.PART_CLEANING
                or status is DreameMowerStatus.FAST_MAPPING
                or status is DreameMowerStatus.CRUISING_PATH
                or status is DreameMowerStatus.CRUISING_POINT
                or status is DreameMowerStatus.SUMMON_CLEAN
                or status is DreameMowerStatus.SHORTCUT
                or status is DreameMowerStatus.PERSON_FOLLOW
            )
        )

    @property
    def shortcut_task(self) -> bool:
        """Returns true when device has an active shortcut task."""
        if self.started and self.shortcuts:
            for k, v in self.shortcuts.items():
                if v.running:
                    return True
        return False

    @property
    def customized_cleaning(self) -> bool:
        """Returns true when customized cleaning feature is enabled."""
        return bool(
            self._get_property(DreameMowerProperty.CUSTOMIZED_CLEANING)
            and self.has_saved_map
            and not self.cleangenius_cleaning
        )

    @property
    def cleangenius_cleaning(self) -> bool:
        """Returns true when CleanGenius feature is enabled."""
        return bool(
            self._capability.cleangenius
            and self._get_property(DreameMowerAutoSwitchProperty.CLEANGENIUS)
            and not self.zone_cleaning
            and not self.spot_cleaning
        )

    @property
    def max_suction_power(self) -> bool:
        """Returns true when max suction power feature is enabled."""
        return bool(
            self._capability.max_suction_power and self._get_property(DreameMowerAutoSwitchProperty.MAX_SUCTION_POWER)
        )

    @property
    def multi_map(self) -> bool:
        """Returns true when multi floor map feature is enabled."""
        return bool(self._get_property(DreameMowerProperty.MULTI_FLOOR_MAP))

    @property
    def last_cleaning_time(self) -> datetime | None:
        if self._cleaning_history:
            return self._last_cleaning_time

    @property
    def last_cruising_time(self) -> datetime | None:
        if self._cruising_history:
            return self._last_cruising_time

    @property
    def cleaning_history(self) -> dict[str, Any] | None:
        """Returns the cleaning history list as dict."""
        if self._cleaning_history:
            if self._cleaning_history_attrs is None:
                list = {}
                for history in self._cleaning_history:
                    date = time.strftime("%m-%d %H:%M", time.localtime(history.date.timestamp()))
                    list[date] = {
                        ATTR_TIMESTAMP: history.date.timestamp(),
                        ATTR_CLEANING_TIME: f"{history.cleaning_time} min",
                        ATTR_CLEANED_AREA: f"{history.cleaned_area} m²",
                    }
                    if history.status is not None:
                        list[date][ATTR_STATUS] = (
                            STATUS_CODE_TO_NAME.get(history.status, STATE_UNKNOWN).replace("_", " ").capitalize()
                        )
                    if history.completed is not None:
                        list[date][ATTR_COMPLETED] = history.completed
                    if history.neglected_segments:
                        list[date][ATTR_NEGLECTED_SEGMENTS] = {
                            k: v.name.replace("_", " ").capitalize() for k, v in history.neglected_segments.items()
                        }
                    if history.cleanup_method is not None:
                        list[date][ATTR_CLEANUP_METHOD] = history.cleanup_method.name.replace("_", " ").capitalize()
                    if history.task_interrupt_reason is not None:
                        list[date][ATTR_INTERRUPT_REASON] = history.task_interrupt_reason.name.replace(
                            "_", " "
                        ).capitalize()
                self._cleaning_history_attrs = list
            return self._cleaning_history_attrs

    @property
    def cruising_history(self) -> dict[str, Any] | None:
        """Returns the cruising history list as dict."""
        if self._cruising_history:
            if self._cruising_history_attrs is None:
                list = {}
                for history in self._cruising_history:
                    date = time.strftime("%m-%d %H:%M", time.localtime(history.date.timestamp()))
                    list[date] = {
                        ATTR_CRUISING_TIME: f"{history.cleaning_time} min",
                    }
                    if history.status is not None:
                        list[date][ATTR_STATUS] = (
                            STATUS_CODE_TO_NAME.get(history.status, STATE_UNKNOWN).replace("_", " ").capitalize()
                        )
                    if history.cruise_type is not None:
                        list[date][ATTR_CRUISING_TYPE] = history.cruise_type
                    if history.map_index is not None:
                        list[date][ATTR_MAP_INDEX] = history.map_index
                    if history.map_name is not None and len(history.map_name) > 1:
                        list[date][ATTR_MAP_NAME] = history.map_name
                    if history.completed is not None:
                        list[date][ATTR_COMPLETED] = history.completed
                self._cruising_history_attrs = list
            return self._cruising_history_attrs

    @property
    def maximum_maps(self) -> int:
        return (
            1 if not self._capability.lidar_navigation or not self.multi_map else 4 if self._capability.wifi_map else 3
        )

    @property
    def mapping_available(self) -> bool:
        """Returns true when creating a new map is possible."""
        return bool(
            not self.started
            and not self.fast_mapping
            and (not self._device.capability.map or self.maximum_maps > len(self.map_list))
        )

    @property
    def second_cleaning_available(self) -> bool:
        if self._cleaning_history and self.current_map:
            history = self._cleaning_history[0]
            if history.object_name:
                map_data = self._history_map_data.get(history.object_name)
                return bool(
                    (map_data is not None and self.current_map.map_id == map_data.map_id)
                    and (
                        bool(history.neglected_segments)
                        or bool(
                            history.cleanup_method.value == 2
                            and map_data.cleaned_segments
                            and map_data.cleaning_map_data is not None
                            and map_data.cleaning_map_data.has_dirty_area
                        )
                    )
                )
        return False

    @property
    def blades_life(self) -> int:
        """Returns blade remaining life in percent."""
        return self._get_property(DreameMowerProperty.BLADES_LEFT)

    @property
    def side_brush_life(self) -> int:
        """Returns side brush remaining life in percent."""
        return self._get_property(DreameMowerProperty.SIDE_BRUSH_LEFT)

    @property
    def filter_life(self) -> int:
        """Returns filter remaining life in percent."""
        return self._get_property(DreameMowerProperty.FILTER_LEFT)

    @property
    def sensor_dirty_life(self) -> int:
        """Returns sensor clean remaining time in percent."""
        return self._get_property(DreameMowerProperty.SENSOR_DIRTY_LEFT)

    @property
    def tank_filter_life(self) -> int:
        """Returns tank filter remaining life in percent."""
        return self._get_property(DreameMowerProperty.TANK_FILTER_LEFT)

    @property
    def silver_ion_life(self) -> int:
        """Returns silver-ion life in percent."""
        return self._get_property(DreameMowerProperty.SILVER_ION_LEFT)

    @property
    def lensbrush_life(self) -> int:
        """Returns lensbrush life in percent."""
        return 30000 - self._get_property(DreameMowerProperty.LENSBRUSH_LEFT)['CMS'][0]

    @property
    def squeegee_life(self) -> int:
        """Returns squeegee life in percent."""
        return self._get_property(DreameMowerProperty.SQUEEGEE_LEFT)

    @property
    def dnd(self) -> bool | None:
        """Returns DND is enabled."""
        if self._capability.dnd:
            return (
                bool(self._get_property(DreameMowerProperty.DND))
                if not self._capability.dnd_task
                else self.dnd_tasks[0].get("en") if self.dnd_tasks and len(self.dnd_tasks) else False
            )

    @property
    def dnd_start(self) -> str | None:
        """Returns DND start time."""
        if self._capability.dnd:
            return (
                self._get_property(DreameMowerProperty.DND_START)
                if not self._capability.dnd_task
                else self.dnd_tasks[0].get("st") if self.dnd_tasks and len(self.dnd_tasks) else "22:00"
            )

    @property
    def dnd_end(self) -> str | None:
        """Returns DND end time."""
        if self._capability.dnd:
            return (
                self._get_property(DreameMowerProperty.DND_END)
                if not self._capability.dnd_task
                else self.dnd_tasks[0].get("et") if self.dnd_tasks and len(self.dnd_tasks) else "08:00"
            )

    @property
    def off_peak_charging(self) -> bool | None:
        """Returns Off-Peak charging is enabled."""
        if self._capability.off_peak_charging:
            return bool(
                self._capability.off_peak_charging
                and len(self.off_peak_charging_config)
                and self.off_peak_charging_config.get("enable")
            )

    @property
    def off_peak_charging_start(self) -> str | None:
        """Returns Off-Peak charging start time."""
        if self._capability.off_peak_charging:
            return (
                self.off_peak_charging_config.get("startTime")
                if self.off_peak_charging_config and len(self.off_peak_charging_config)
                else "22:00"
            )

    @property
    def off_peak_charging_end(self) -> str | None:
        """Returns Off-Peak charging end time."""
        if self._capability.off_peak_charging:
            return (
                self.off_peak_charging_config.get("endTime")
                if self.off_peak_charging_config and len(self.off_peak_charging_config)
                else "08:00"
            )

    @property
    def ai_obstacle_detection(self) -> bool:
        return self._device.get_ai_property(DreameMowerAIProperty.AI_OBSTACLE_DETECTION)

    @property
    def ai_obstacle_image_upload(self) -> bool:
        return self._device.get_ai_property(DreameMowerAIProperty.AI_OBSTACLE_IMAGE_UPLOAD)

    @property
    def ai_pet_detection(self) -> bool:
        return self._device.get_ai_property(DreameMowerAIProperty.AI_PET_DETECTION)

    @property
    def ai_furniture_detection(self) -> bool:
        return self._device.get_ai_property(DreameMowerAIProperty.AI_FURNITURE_DETECTION)

    @property
    def ai_fluid_detection(self) -> bool:
        return self._device.get_ai_property(DreameMowerAIProperty.AI_FLUID_DETECTION)

    @property
    def ai_obstacle_picture(self) -> bool:
        return self._device.get_ai_property(DreameMowerAIProperty.AI_OBSTACLE_PICTURE)

    @property
    def fill_light(self) -> bool:
        return self._device.get_auto_switch_property(DreameMowerAutoSwitchProperty.FILL_LIGHT)

    @property
    def stain_avoidance(self) -> bool:
        return bool(self._device.get_auto_switch_property(DreameMowerAutoSwitchProperty.STAIN_AVOIDANCE) == 2)

    @property
    def pet_focused_cleaning(self) -> bool:
        return self._device.get_auto_switch_property(DreameMowerAutoSwitchProperty.PET_FOCUSED_CLEANING)

    @property
    def map_backup_status(self) -> int | None:
        return self._get_property(DreameMowerProperty.MAP_BACKUP_STATUS)

    @property
    def map_recovery_status(self) -> int | None:
        return self._get_property(DreameMowerProperty.MAP_RECOVERY_STATUS)

    @property
    def custom_order(self) -> bool:
        """Returns true when custom cleaning sequence is set."""
        if self.cleangenius_cleaning:
            return False
        segments = self.current_segments
        if segments:
            for v in segments.values():
                if v.order:
                    return True
        return False

    @property
    def segment_order(self) -> list[int] | None:
        """Returns cleaning order list."""
        segments = self.current_segments
        if segments:
            return (
                list(
                    sorted(
                        segments,
                        key=lambda segment_id: segments[segment_id].order if segments[segment_id].order else 99,
                    )
                )
                if self.custom_order
                else None
            )
        return [] if self.custom_order else None

    @property
    def has_saved_map(self) -> bool:
        """Returns true when device has saved map and knowns its location on saved map."""
        if self._map_manager is None:
            return True

        current_map = self.current_map
        return bool(
            current_map is not None
            and current_map.saved_map_status == 2
            and not self.has_temporary_map
            and not self.has_new_map
            and not current_map.empty_map
        )

    @property
    def has_temporary_map(self) -> bool:
        """Returns true when device cannot store the newly created map and waits prompt for restoring or discarding it."""
        if self._map_manager is None:
            return False

        current_map = self.current_map
        return bool(current_map is not None and current_map.temporary_map and not current_map.empty_map)

    @property
    def has_new_map(self) -> bool:
        """Returns true when fast mapping from empty map."""
        if self._map_manager is None:
            return False

        current_map = self.current_map
        return bool(
            current_map is not None
            and not current_map.temporary_map
            and not current_map.empty_map
            and current_map.new_map
        )

    @property
    def selected_map(self) -> MapData | None:
        """Return the selected map data"""
        if self._map_manager and not self.has_temporary_map and not self.has_new_map:
            return self._map_manager.selected_map

    @property
    def current_map(self) -> MapData | None:
        """Return the current map data"""
        if self._map_manager:
            return self._map_manager.get_map()

    @property
    def map_list(self) -> list[int] | None:
        """Return the saved map id list if multi floor map is enabled"""
        if self._map_manager:
            if self.multi_map:
                return self._map_manager.map_list

            selected_map = self._map_manager.selected_map
            if selected_map:
                return [selected_map.map_id]
        return []

    @property
    def map_data_list(self) -> dict[int, MapData] | None:
        """Return the saved map data list if multi floor map is enabled"""
        if self._map_manager:
            if self.multi_map:
                return self._map_manager.map_data_list
            selected_map = self.selected_map
            if selected_map:
                return {selected_map.map_id: selected_map}
        return {}

    @property
    def current_segments(self) -> dict[int, Segment] | None:
        """Return the segments of current map"""
        current_map = self.current_map
        if current_map and current_map.segments and not current_map.empty_map:
            return current_map.segments
        return {}

    @property
    def segments(self) -> dict[int, Segment] | None:
        """Return the segments of selected map"""
        current_map = self.selected_map
        if current_map and current_map.segments and not current_map.empty_map:
            return current_map.segments
        return {}

    @property
    def current_zone(self) -> Segment | None:
        """Return the segment that device is currently on"""
        if self._capability.lidar_navigation:
            current_map = self.current_map
            if current_map and current_map.segments and current_map.robot_segment and not current_map.empty_map:
                return current_map.segments[current_map.robot_segment]

    @property
    def cleaning_sequence(self) -> list[int] | None:
        """Returns custom segment cleaning sequence list."""
        if self._map_manager:
            return self._map_manager.cleaning_sequence

    @property
    def previous_cleaning_sequence(self):
        if self.current_map and self.current_map.map_id in self._previous_cleaning_sequence:
            return self._previous_cleaning_sequence[self.current_map.map_id]

    @property
    def active_segments(self) -> list[int] | None:
        map_data = self.current_map
        if map_data and self.started and not self.fast_mapping:
            if self.segment_cleaning:
                if map_data.active_segments:
                    return map_data.active_segments
            elif (
                not self.zone_cleaning
                and not self.spot_cleaning
                and map_data.segments
                and not self.docked
                and not self.returning
                and not self.returning_paused
            ):
                return list(map_data.segments.keys())
            return []

    @property
    def job(self) -> dict[str, Any] | None:
        attributes = {
            ATTR_STATUS: self.status.name,
        }
        if self._device._protocol.cloud:
            attributes[ATTR_DID] = self._device._protocol.cloud.device_id
        if self._capability.custom_cleaning_mode:
            attributes[ATTR_CLEANING_MODE] = self.cleaning_mode.name

        if self.cleanup_completed:
            attributes.update(
                {
                    ATTR_CLEANED_AREA: self._get_property(DreameMowerProperty.CLEANED_AREA),
                    ATTR_CLEANING_TIME: self._get_property(DreameMowerProperty.CLEANING_TIME),
                    ATTR_COMPLETED: True,
                }
            )
        else:
            attributes[ATTR_COMPLETED] = False

        map_data = self.current_map
        if map_data:
            if map_data.active_segments:
                attributes[ATTR_ACTIVE_SEGMENTS] = map_data.active_segments
            elif map_data.active_areas is not None:
                if self.go_to_zone:
                    attributes[ATTR_ACTIVE_CRUISE_POINTS] = {
                        1: Coordinate(self.go_to_zone.x, self.go_to_zone.y, False, 0)
                    }
                else:
                    attributes[ATTR_ACTIVE_AREAS] = map_data.active_areas
            elif map_data.active_points is not None:
                attributes[ATTR_ACTIVE_POINTS] = map_data.active_points
            elif map_data.predefined_points is not None:
                attributes[ATTR_PREDEFINED_POINTS] = map_data.predefined_points
            elif map_data.active_cruise_points is not None:
                attributes[ATTR_ACTIVE_CRUISE_POINTS] = map_data.active_cruise_points
        return attributes

    @property
    def attributes(self) -> dict[str, Any] | None:
        """Return the attributes of the device."""
        properties = [
            DreameMowerProperty.STATUS,
            DreameMowerProperty.CLEANING_MODE,
            DreameMowerProperty.ERROR,
            DreameMowerProperty.CLEANING_TIME,
            DreameMowerProperty.CLEANED_AREA,
            DreameMowerProperty.VOICE_PACKET_ID,
            DreameMowerProperty.TIMEZONE,
            DreameMowerProperty.BLADES_TIME_LEFT,
            DreameMowerProperty.BLADES_LEFT,
            DreameMowerProperty.SIDE_BRUSH_TIME_LEFT,
            DreameMowerProperty.SIDE_BRUSH_LEFT,
            DreameMowerProperty.FILTER_LEFT,
            DreameMowerProperty.FILTER_TIME_LEFT,
            DreameMowerProperty.TANK_FILTER_LEFT,
            DreameMowerProperty.TANK_FILTER_TIME_LEFT,
            DreameMowerProperty.SILVER_ION_LEFT,
            DreameMowerProperty.SILVER_ION_TIME_LEFT,
            DreameMowerProperty.LENSBRUSH_LEFT,
            DreameMowerProperty.LENSBRUSH_TIME_LEFT,
            DreameMowerProperty.SQUEEGEE_LEFT,
            DreameMowerProperty.SQUEEGEE_TIME_LEFT,
            DreameMowerProperty.TOTAL_CLEANED_AREA,
            DreameMowerProperty.TOTAL_CLEANING_TIME,
            DreameMowerProperty.CLEANING_COUNT,
            DreameMowerProperty.CUSTOMIZED_CLEANING,
            DreameMowerProperty.SERIAL_NUMBER,
            DreameMowerProperty.NATION_MATCHED,
            DreameMowerProperty.TOTAL_RUNTIME,
            DreameMowerProperty.TOTAL_CRUISE_TIME,
            DreameMowerProperty.CLEANING_PROGRESS,
            DreameMowerProperty.INTELLIGENT_RECOGNITION,
            DreameMowerProperty.MULTI_FLOOR_MAP,
            DreameMowerProperty.SCHEDULED_CLEAN,
            DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE,
        ]

        if not self._capability.disable_sensor_cleaning:
            properties.extend(
                [
                    DreameMowerProperty.SENSOR_DIRTY_LEFT,
                    DreameMowerProperty.SENSOR_DIRTY_TIME_LEFT,
                ]
            )

        if not self._capability.dnd_task:
            properties.extend(
                [
                    DreameMowerProperty.DND_START,
                    DreameMowerProperty.DND_END,
                ]
            )

        attributes = {}

        for prop in properties:
            value = self._get_property(prop)
            if value is not None:
                prop_name = PROPERTY_TO_NAME.get(prop.name)
                if prop_name:
                    prop_name = prop_name[0]
                else:
                    prop_name = prop.name.lower()

                if prop is DreameMowerProperty.ERROR:
                    value = self.error_name.replace("_", " ").capitalize()
                elif prop is DreameMowerProperty.STATUS:
                    value = self.status_name.replace("_", " ").capitalize()
                elif prop is DreameMowerProperty.CLEANING_MODE:
                    value = self.cleaning_mode_name.replace("_", " ").capitalize()
                    attributes[f"{prop_name}_list"] = (
                        [v.replace("_", " ").capitalize() for v in self.cleaning_mode_list.keys()]
                        if PROPERTY_AVAILABILITY[prop.name](self._device)
                        else []
                    )
                elif prop is DreameMowerProperty.VOICE_ASSISTANT_LANGUAGE:
                    if not self._capability.voice_assistant:
                        continue
                    value = self.voice_assistant_language_name.replace("_", " ").capitalize()
                    attributes[f"{prop_name}_list"] = [
                        v.replace("_", " ").capitalize() for v in self.voice_assistant_language_list.keys()
                    ]
                elif prop is DreameMowerAutoSwitchProperty.CLEANING_ROUTE:
                    value = self.cleaning_route_name.replace("_", " ").capitalize()
                    attributes[f"{prop_name}_list"] = (
                        [v.replace("_", " ").capitalize() for v in self.cleaning_route_list.keys()]
                        if PROPERTY_AVAILABILITY[prop.name](self._device)
                        else []
                    )
                elif prop is DreameMowerAutoSwitchProperty.CLEANGENIUS:
                    value = self.cleangenius_name.replace("_", " ").capitalize()
                    attributes[f"{prop_name}_list"] = (
                        [v.replace("_", " ").capitalize() for v in self.cleangenius_list.keys()]
                        if PROPERTY_AVAILABILITY[prop.name](self._device)
                        else []
                    )
                elif prop is DreameMowerProperty.CUSTOMIZED_CLEANING:
                    value = value and not self.zone_cleaning and not self.spot_cleaning
                elif prop is DreameMowerProperty.SCHEDULED_CLEAN:
                    value = bool(value == 1 or value == 2 or value == 4)
                elif (
                    prop is DreameMowerProperty.MULTI_FLOOR_MAP
                    or prop is DreameMowerProperty.INTELLIGENT_RECOGNITION
                ):
                    value = bool(value > 0)
                attributes[prop_name] = value

        if self._capability.dnd_task and self.dnd_tasks is not None:
            attributes[ATTR_DND] = {}
            for dnd_task in self.dnd_tasks:
                attributes[ATTR_DND][dnd_task["id"]] = {
                    "enabled": dnd_task.get("en"),
                    "start": dnd_task.get("st"),
                    "end": dnd_task.get("et"),
                }
        if self._capability.shortcuts and self.shortcuts is not None:
            attributes[ATTR_SHORTCUTS] = {}
            for id, shortcut in self.shortcuts.items():
                attributes[ATTR_SHORTCUTS][id] = {
                    "name": shortcut.name,
                    "running": shortcut.running,
                    "tasks": shortcut.tasks,
                }

        attributes[ATTR_CLEANING_SEQUENCE] = self.segment_order
        attributes[ATTR_CHARGING] = self.docked
        attributes[ATTR_STARTED] = self.started
        attributes[ATTR_PAUSED] = self.paused
        attributes[ATTR_RUNNING] = self.running
        attributes[ATTR_RETURNING_PAUSED] = self.returning_paused
        attributes[ATTR_RETURNING] = self.returning
        attributes[ATTR_SEGMENT_CLEANING] = self.segment_cleaning
        attributes[ATTR_ZONE_CLEANING] = self.zone_cleaning
        attributes[ATTR_SPOT_CLEANING] = self.spot_cleaning
        attributes[ATTR_CRUSING] = self.cruising
        attributes[ATTR_MOWER_STATE] = self.state_name.lower()
        attributes[ATTR_HAS_SAVED_MAP] = self._map_manager is not None and self.has_saved_map
        attributes[ATTR_HAS_TEMPORARY_MAP] = self.has_temporary_map

        if self._capability.lidar_navigation:
            attributes[ATTR_MAPPING] = self.fast_mapping
            attributes[ATTR_MAPPING_AVAILABLE] = self.mapping_available

        if self._capability.cleangenius:
            attributes[ATTR_CLEANGENIUS] = bool(self.cleangenius_cleaning)

        if self.map_list:
            attributes[ATTR_ACTIVE_SEGMENTS] = self.active_segments
            if self._capability.lidar_navigation:
                attributes[ATTR_CURRENT_SEGMENT] = self.current_zone.segment_id if self.current_zone else 0
            attributes[ATTR_SELECTED_MAP] = self.selected_map.map_name if self.selected_map else None
            attributes[ATTR_ZONES] = {}
            for k, v in self.map_data_list.items():
                attributes[ATTR_ZONES][v.map_name] = [
                    {ATTR_ID: j, ATTR_NAME: s.name, ATTR_ICON: s.icon} for (j, s) in sorted(v.segments.items())
                ]
        attributes[ATTR_CAPABILITIES] = self._capability.list
        return attributes

    def consumable_life_warning_description(self, consumable_property) -> str:
        description = CONSUMABLE_TO_LIFE_WARNING_DESCRIPTION.get(consumable_property)
        if description:
            value = self._get_property(consumable_property)
            if value is not None and value >= 0 and value <= 5:
                if value != 0 and len(description) > 1:
                    return description[1]
                return description[0]

    def segment_order_list(self, segment) -> list[int] | None:
        order = []
        if self.current_segments:
            order = [
                v.order
                for k, v in sorted(
                    self.current_segments.items(),
                    key=lambda s: s[1].order if s[1].order != None else 0,
                )
                if v.order
            ]
            if not segment.order and len(order):
                order = order + [max(order) + 1]
        return list(map(str, order))


class DreameMowerDeviceInfo:
    """Container of device information."""

    def __init__(self, data):
        self.data = data
        self.version = 0
        firmware_version = self.firmware_version
        if firmware_version is not None:
            firmware_version = firmware_version.split("_")
            if len(firmware_version) == 2:
                self.version = int(firmware_version[1])

    def __repr__(self):
        return "%s v%s (%s) @ %s - token: %s" % (
            self.model,
            self.version,
            self.mac,
            self.network_interface["localIp"] if self.network_interface else "",
        )

    @property
    def network_interface(self) -> str:
        """Information about network configuration."""
        if "netif" in self.data:
            return self.data["netif"]
        return None

    @property
    def model(self) -> Optional[str]:
        """Model string if available."""
        if "model" in self.data:
            return self.data["model"]
        return None

    @property
    def firmware_version(self) -> Optional[str]:
        """Firmware version if available."""
        if "fw_ver" in self.data and self.data["fw_ver"] is not None:
            return self.data["fw_ver"]
        if "ver" in self.data and self.data["ver"] is not None:
            return self.data["ver"]
        return None

    @property
    def hardware_version(self) -> Optional[str]:
        """Hardware version if available."""
        if "hw_ver" in self.data:
            return self.data["hw_ver"]
        return "Linux"

    @property
    def mac_address(self) -> Optional[str]:
        """MAC address if available."""
        if "mac" in self.data:
            return self.data["mac"]
        return None

    @property
    def manufacturer(self) -> str:
        """Manufacturer name."""
        return "Dreametech™"

    @property
    def raw(self) -> dict[str, Any]:
        """Raw data as returned by the device."""
        return self.data
