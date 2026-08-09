"""Number entities for Dreame Mower."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.const import (
    CUTTING_HEIGHT_MIN_CM,
    CUTTING_HEIGHT_STEP_CM,
    cutting_height_max_cm,
)
from .entity import DreameMowerEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower numbers from a config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    numbers: list[NumberEntity] = []

    if coordinator.supports_cutting_height:
        numbers.append(DreameMowerCuttingHeightNumber(coordinator))
    else:
        _LOGGER.debug(
            "Skipping the cutting height entity: model %s has no software-adjustable cutting height",
            coordinator.device_model,
        )

    if coordinator.supports_rain_protection:
        numbers.append(DreameMowerRainDelayNumber(coordinator))
    else:
        _LOGGER.debug(
            "Skipping the rain delay entity: device %s reported no rain settings",
            coordinator.device_name,
        )

    async_add_entities(numbers)


class DreameMowerCuttingHeightNumber(DreameMowerEntity, NumberEntity):
    """Number entity for the cutting height of the active map."""

    _attr_translation_key = "cutting_height"
    _attr_icon = "mdi:arrow-up-down"
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_native_min_value = CUTTING_HEIGHT_MIN_CM
    _attr_native_step = CUTTING_HEIGHT_STEP_CM

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the cutting height entity."""
        super().__init__(coordinator, "cutting_height")
        self._attr_native_max_value = cutting_height_max_cm(coordinator.device_model)

    @property
    def native_value(self) -> float | None:
        """Return the cutting height of the active map, if it is known."""
        return self.coordinator.cutting_height

    async def async_set_native_value(self, value: float) -> None:
        """Set the cutting height for the active map."""
        if not await self.coordinator.async_set_cutting_height(value):
            raise HomeAssistantError(f"Failed to set the cutting height to {value} cm")


class DreameMowerRainDelayNumber(DreameMowerEntity, NumberEntity):
    """Number entity for how long the mower waits after rain before it resumes.

    A delay of zero leaves the mower docked until it is started again. Models
    that navigate by camera accept one step beyond the hourly range, which makes
    them resume as soon as the rain stops instead of drying off first. A changed
    delay applies the next time rain protection triggers.

    The mower only takes a new delay while rain protection is on; with it off it
    keeps the delay it holds.
    """

    _attr_translation_key = "rain_delay"
    _attr_icon = "mdi:weather-rainy"
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_native_step = 1
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the rain delay entity."""
        super().__init__(coordinator, "rain_delay")
        self._attr_native_min_value = coordinator.rain_delay_min_hours
        self._attr_native_max_value = coordinator.rain_delay_max_hours

    @property
    def native_value(self) -> float | None:
        """Return the configured after-rain delay, if it is known."""
        return self.coordinator.rain_delay_hours

    async def async_set_native_value(self, value: float) -> None:
        """Set how long the mower waits after rain."""
        delay_hours = round(value)
        if not await self.coordinator.async_set_rain_protection(delay_hours=delay_hours):
            raise HomeAssistantError(f"Failed to set the after-rain delay to {delay_hours} h")

        if self.coordinator.rain_delay_hours != delay_hours:
            raise HomeAssistantError(
                f"The mower kept its after-rain delay of {self.coordinator.rain_delay_hours} h "
                f"instead of the requested {delay_hours} h; it only takes a new delay while "
                "rain protection is on"
            )
