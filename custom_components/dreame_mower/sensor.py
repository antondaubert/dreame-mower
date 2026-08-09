"""Minimal sensor platform for Dreame Mower Implementation."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfArea

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.property.property_misc import TASK_STATUS_OPTIONS
from .entity import DreameMowerEntity
from .config_flow import DEVICE_TYPE_SWBOT

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower sensors from config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    
    if coordinator.device_type == DEVICE_TYPE_SWBOT:
        sensors = [
            DreameMowerBatterySensor(coordinator),
            DreameMowerStatusSensor(coordinator),
        ]
    else:
        # Full mower sensor set
        sensors = [
            DreameMowerBatterySensor(coordinator),
            DreameMowerStatusSensor(coordinator),
            DreameMowerChargingStatusSensor(coordinator),
            DreameMowerBluetoothSensor(coordinator),
            DreameMowerDeviceCodeSensor(coordinator),
            DreameMowerTaskSensor(coordinator),
            DreameMowerProgressSensor(coordinator),
            DreameMowerConsumableHealthSensor(coordinator, "blade", 0, 6000, "mdi:scissors-cutting"),
            DreameMowerConsumableHealthSensor(coordinator, "brush", 1, 30000, "mdi:brush"),
            DreameMowerConsumableHealthSensor(coordinator, "robot", 2, 3600, "mdi:robot"),
        ]
        if coordinator.supports_rain_protection:
            sensors.append(DreameMowerRainProtectionEndSensor(coordinator))
        else:
            _LOGGER.debug(
                "Skipping the rain protection end sensor: device %s reported no rain settings",
                coordinator.device_name,
            )

    async_add_entities(sensors)


class DreameMowerBatterySensor(DreameMowerEntity, SensorEntity):
    """Battery level sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator, "battery")
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:battery"

    @property
    def native_value(self) -> int | None:
        """Return the battery level."""
        return self.coordinator.device_battery_percent


class DreameMowerStatusSensor(DreameMowerEntity, SensorEntity):
    """Status sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator, "status")
        self._attr_icon = "mdi:robot-mower"
        self._attr_translation_key = "status"

    @property
    def native_value(self) -> str | None:
        """Return the mower status."""
        if not self.available:
            return "offline"
        return self.coordinator.device_status


class DreameMowerChargingStatusSensor(DreameMowerEntity, SensorEntity):
    """Charging status sensor for Dreame Mower (3:2)."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the charging status sensor."""
        super().__init__(coordinator, "charging_status")
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "charging_status"

    @property
    def native_value(self) -> str | None:
        """Return the charging status mapped text."""
        return self.coordinator.device_charging_status


class DreameMowerBluetoothSensor(DreameMowerEntity, SensorEntity):
    """Bluetooth connection sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the Bluetooth sensor."""
        super().__init__(coordinator, "bluetooth_connection")
        self._attr_icon = "mdi:bluetooth"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "bluetooth_connection"

    @property
    def native_value(self) -> bool | None:
        """Return the Bluetooth connection status."""
        return self.coordinator.device_bluetooth_connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "bluetooth_connected": self.coordinator.device_bluetooth_connected,
        }


class DreameMowerDeviceCodeSensor(DreameMowerEntity, SensorEntity):
    """Device code sensor (2:2) - shows current device status/error codes."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the device code sensor."""
        super().__init__(coordinator, "device_code")
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "device_code"

    @property
    def native_value(self) -> int | None:
        """Return the current device code."""
        return self.coordinator.device_code

    @property
    def icon(self) -> str:
        """Return icon based on device code type."""
        if self.coordinator.device_code_is_error:
            return "mdi:alert-circle"
        elif self.coordinator.device_code_is_warning:
            return "mdi:alert"
        else:
            return "mdi:information-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes: dict[str, Any] = {}
        
        # Add device code details
        if self.coordinator.device_code is not None:
            attributes["code"] = self.coordinator.device_code
            attributes["name"] = self.coordinator.device_code_name
            attributes["description"] = self.coordinator.device_code_description
            
            # Determine type based on priority: error > warning > info
            if self.coordinator.device_code_is_error:
                attributes["type"] = "error"
            elif self.coordinator.device_code_is_warning:
                attributes["type"] = "warning"
            else:
                attributes["type"] = "info"
        
        return attributes


class DreameMowerTaskSensor(DreameMowerEntity, SensorEntity):
    """Current mowing-task status for Dreame Mower.

    The value is decoded from the device heartbeat (prop 1:1). It reflects 
    whether a task is in progress, paused, or interrupted by docking — and
    therefore whether pressing start will resume an unfinished task or
    begin a new one.
    """

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the task sensor."""
        super().__init__(coordinator, "current_task")
        self._attr_icon = "mdi:clipboard-play"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "current_task"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = list(TASK_STATUS_OPTIONS)

    @property
    def native_value(self) -> str | None:
        """Return the current mowing task status."""
        return self.coordinator.device_task_status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return supplementary task details from the device task descriptor.

        These come from the task descriptor (2:50) rather than the heartbeat;
        the device omits the optional fields (area/region/elapsed) while a task
        is paused or docked, so they may be ``None`` in those states.
        """
        attributes: dict[str, Any] = {}
        task_data = self.coordinator.current_task_data
        if task_data:
            attributes.update({
                "task_type": task_data.get("type"),
                "coverage_target": task_data.get("coverage_target"),
                "area_id": task_data.get("area_id"),
                "region_id": task_data.get("region_id"),
                "elapsed_time": task_data.get("elapsed_time"),
            })
        return attributes


class DreameMowerProgressSensor(DreameMowerEntity, SensorEntity):
    """Mowing progress sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the progress sensor."""
        super().__init__(coordinator, "mowing_progress")
        self._attr_device_class = SensorDeviceClass.POWER_FACTOR
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:percent"
        self._attr_translation_key = "mowing_progress"

    @property
    def native_value(self) -> float | None:
        """Return the mowing progress percentage."""
        progress = self.coordinator.mowing_progress_percent
        if progress is not None:
            return round(progress, 1)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        progress = self.coordinator.mowing_progress_percent
        attributes: dict[str, Any] = {
            "current_area_sqm": self.coordinator.current_area_sqm,
            "total_area_sqm": self.coordinator.total_area_sqm,
            "progress_percent": round(progress, 1) if progress is not None else None,
        }
        
        # Add mower coordinates data
        coordinates = self.coordinator.mower_coordinates
        if coordinates:
            attributes["coordinates"] = f"{coordinates[0]}, {coordinates[1]}"
            attributes["x"] = coordinates[0]
            attributes["y"] = coordinates[1]
        else:
            attributes["coordinates"] = None
            attributes["x"] = None
            attributes["y"] = None
            
        attributes["segment"] = self.coordinator.current_segment
        attributes["heading"] = self.coordinator.mower_heading
        
        # Add path history summary
        path_history = self.coordinator.mowing_path_history
        attributes["path_points"] = len(path_history)
        
        return attributes


class DreameMowerRainProtectionEndSensor(DreameMowerEntity, SensorEntity):
    """When rain protection lets the mower work again.

    The mower only reports a time while rain protection is holding it back; the
    sensor is unknown at any other time.
    """

    _attr_translation_key = "rain_protection_end"
    _attr_icon = "mdi:weather-sunny-alert"

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the rain protection end sensor."""
        super().__init__(coordinator, "rain_protection_end")
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return when the mower may resume, or None while rain is not holding it back."""
        if not self.coordinator.rain_protection_active:
            return None
        return self.coordinator.rain_protection_end_time


_CONSUMABLE_ITEM_INDEX = {"blade": 0, "brush": 1, "robot": 2}


class DreameMowerConsumableHealthSensor(DreameMowerEntity, SensorEntity):
    """Remaining-life health sensor for one CMS consumable item."""

    def __init__(
        self,
        coordinator: DreameMowerCoordinator,
        item: str,
        index: int,
        total_minutes: int,
        icon: str,
    ) -> None:
        super().__init__(coordinator, f"consumable_{item}_health")
        self._item = item
        self._index = index
        self._total_minutes = total_minutes
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = icon
        self._attr_translation_key = f"consumable_{item}_health"

    def _used_minutes(self) -> int | None:
        values = self.coordinator.consumable_values
        if values is None or len(values) <= self._index:
            return None
        return max(0, min(int(values[self._index]), self._total_minutes))

    @property
    def native_value(self) -> float | None:
        used = self._used_minutes()
        if used is None:
            return None
        remaining = self._total_minutes - used
        return round((remaining / self._total_minutes) * 100, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        used = self._used_minutes()
        if used is None:
            return {}
        remaining = self._total_minutes - used
        return {
            "used_hours": round(used / 60, 1),
            "remaining_hours": round(remaining / 60, 1),
            "total_hours": round(self._total_minutes / 60, 1),
        }
