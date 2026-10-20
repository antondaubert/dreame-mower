"""Minimal sensor platform for Dreame Mower Implementation."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.device import CONSUMABLE_COUNTER_TOTAL_MINUTES
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
            DreameMowerAccountSensor(coordinator),
        ]
    else:
        # Full mower sensor set
        sensors = [
            DreameMowerBatterySensor(coordinator),
            DreameMowerStatusSensor(coordinator),
            DreameMowerAccountSensor(coordinator),
            DreameMowerSignalSensor(coordinator, "wifi_signal", "mdi:wifi"),
            DreameMowerSignalSensor(coordinator, "cellular_signal", "mdi:signal-cellular-3"),
            DreameMowerProgressSensor(coordinator),
            DreameMowerConsumableHealthSensor(coordinator, "blade", 0, CONSUMABLE_COUNTER_TOTAL_MINUTES["blade"], "mdi:scissors-cutting"),
            DreameMowerConsumableHealthSensor(coordinator, "brush", 1, CONSUMABLE_COUNTER_TOTAL_MINUTES["brush"], "mdi:brush"),
            DreameMowerConsumableHealthSensor(coordinator, "robot", 2, CONSUMABLE_COUNTER_TOTAL_MINUTES["robot"], "mdi:robot"),
        ]

        # The rain protection end exists only on mowers that offer rain protection.
        @callback
        def add_rain_end() -> None:
            if coordinator.supports_rain_protection:
                async_add_entities([DreameMowerRainProtectionEndSensor(coordinator)])
            else:
                _LOGGER.debug(
                    "Skipping the rain protection end sensor: device %s reported no rain settings",
                    coordinator.device_name,
                )

        coordinator.async_when_probed(add_rain_end)

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
        return self.coordinator.device_status


class DreameMowerAccountSensor(DreameMowerEntity, SensorEntity):
    """The account the device is reached through.

    A device can be reached through either a Dreamehome or a MOVAhome account,
    and a household often has more than one account to choose from. The sensor
    names the one this device is set up with, which is also the account whose
    app shows the same changes as the integration.
    """

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the account sensor."""
        super().__init__(coordinator, "account")
        self._attr_icon = "mdi:account"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "account"

    @property
    def available(self) -> bool:
        """Return True regardless of the connection.

        The account is what the connection was set up with, so it is known even
        while the device is unreachable — which is when it is worth reading.
        """
        return True

    @property
    def native_value(self) -> str:
        """Return the account the connection was established with."""
        return self.coordinator.account_username

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return which cloud the account belongs to and where it is registered."""
        return {
            "account_type": self.coordinator.account_type,
            "country": self.coordinator.account_country,
        }


class DreameMowerSignalSensor(DreameMowerEntity, SensorEntity):
    """Signal strength of one of the mower's links, from its heartbeat.

    Recorded alongside the mower's position (the mowing progress sensor's x and
    y), it shows where on the lawn each link weakens.
    """

    def __init__(self, coordinator: DreameMowerCoordinator, key: str, icon: str) -> None:
        """Initialize the signal sensor for the "wifi_signal" or "cellular_signal" link."""
        super().__init__(coordinator, key)
        self._key = key
        self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = icon
        self._attr_translation_key = key

    @property
    def native_value(self) -> int | None:
        """Return the signal strength in dBm."""
        if self._key == "wifi_signal":
            return self.coordinator.wifi_signal_dbm
        return self.coordinator.cellular_signal_dbm


class DreameMowerProgressSensor(DreameMowerEntity, SensorEntity):
    """Mowing progress sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the progress sensor."""
        super().__init__(coordinator, "mowing_progress")
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
        return {
            "current_area_sqm": self.coordinator.current_area_sqm,
            "total_area_sqm": self.coordinator.total_area_sqm,
            "progress_percent": round(progress, 1) if progress is not None else None,
        }


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

