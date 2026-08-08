"""Time entities for Dreame Mower."""

from __future__ import annotations

from datetime import time
import logging

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .entity import DreameMowerEntity

_LOGGER = logging.getLogger(__name__)


def minutes_to_time(minutes: int | None) -> time | None:
    """Turn minutes since midnight into a time of day."""
    if minutes is None:
        return None
    return time(hour=minutes // 60, minute=minutes % 60)


def time_to_minutes(value: time) -> int:
    """Turn a time of day into minutes since midnight."""
    return value.hour * 60 + value.minute


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower times from a config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    if not coordinator.supports_charging_period:
        _LOGGER.debug(
            "Skipping the charging period entities: device %s reported no charging settings",
            coordinator.device_name,
        )
        return

    async_add_entities(
        [
            DreameMowerChargingPeriodStartTime(coordinator),
            DreameMowerChargingPeriodEndTime(coordinator),
        ]
    )


class DreameMowerChargingPeriodTime(DreameMowerEntity, TimeEntity):
    """Base entity for one end of the custom charging period."""

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> time | None:
        """Return this end of the charging period, if it is known."""
        return minutes_to_time(self._minutes)

    @property
    def _minutes(self) -> int | None:
        """Return this end of the charging period in minutes since midnight."""
        raise NotImplementedError


class DreameMowerChargingPeriodStartTime(DreameMowerChargingPeriodTime):
    """Time entity for the start of the custom charging period."""

    _attr_translation_key = "charging_period_start"
    _attr_icon = "mdi:clock-start"

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the charging period start entity."""
        super().__init__(coordinator, "charging_period_start")

    @property
    def _minutes(self) -> int | None:
        """Return the start of the charging period in minutes since midnight."""
        return self.coordinator.charging_period_start_minutes

    async def async_set_value(self, value: time) -> None:
        """Set the start of the charging period."""
        if not await self.coordinator.async_set_charging_period(start_minutes=time_to_minutes(value)):
            raise HomeAssistantError(
                f"Failed to set the charging period start time to {value.strftime('%H:%M')}"
            )


class DreameMowerChargingPeriodEndTime(DreameMowerChargingPeriodTime):
    """Time entity for the end of the custom charging period."""

    _attr_translation_key = "charging_period_end"
    _attr_icon = "mdi:clock-end"

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the charging period end entity."""
        super().__init__(coordinator, "charging_period_end")

    @property
    def _minutes(self) -> int | None:
        """Return the end of the charging period in minutes since midnight."""
        return self.coordinator.charging_period_end_minutes

    async def async_set_value(self, value: time) -> None:
        """Set the end of the charging period."""
        if not await self.coordinator.async_set_charging_period(end_minutes=time_to_minutes(value)):
            raise HomeAssistantError(
                f"Failed to set the charging period end time to {value.strftime('%H:%M')}"
            )
