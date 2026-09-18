"""Number entities for Dreame Mower."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEGREE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.const import (
    CUTTING_HEIGHT_MIN_CM,
    CUTTING_HEIGHT_STEP_CM,
    MOWING_DIRECTION_ANGLE_PERIOD_DEGREES,
    cutting_height_max_cm,
)
from .entity import DreameMowerEntity, device_errors_as_ha_errors

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower numbers from a config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities: list[NumberEntity] = []

    if coordinator.supports_cutting_height:
        entities.append(DreameMowerCuttingHeightNumber(coordinator))
    else:
        _LOGGER.debug(
            "Skipping the cutting height entity: model %s has no software-adjustable cutting height",
            coordinator.device_model,
        )

    if coordinator.supports_mowing_direction:
        entities.append(DreameMowerMowingDirectionNumber(coordinator))
    else:
        _LOGGER.debug(
            "Skipping the mowing direction entity: device %s reported no direction",
            coordinator.device_name,
        )

    async_add_entities(entities)


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
        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_cutting_height(value)

        if not updated:
            raise HomeAssistantError(f"Failed to set the cutting height to {value} cm")


class DreameMowerMowingDirectionNumber(DreameMowerEntity, NumberEntity):
    """Number entity for the direction the active map is mowed in.

    A direction is a line rather than a heading, so it runs up to half a turn:
    179° and 359° name the same lanes, and the mower is given the first of them.
    """

    _attr_translation_key = "mowing_direction"
    _attr_icon = "mdi:compass-outline"
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = DEGREE
    _attr_native_min_value = 0
    _attr_native_max_value = MOWING_DIRECTION_ANGLE_PERIOD_DEGREES - 1
    _attr_native_step = 1

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the mowing direction entity."""
        super().__init__(coordinator, "mowing_direction")

    @property
    def native_value(self) -> float | None:
        """Return the direction the active map is mowed in, if it is known."""
        return self.coordinator.mowing_direction_angle

    async def async_set_native_value(self, value: float) -> None:
        """Set the mowing direction for the active map."""
        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_mowing_direction(angle_degrees=value)

        if not updated:
            raise HomeAssistantError(f"The mower did not take the mowing direction {value}°")
