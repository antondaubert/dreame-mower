"""Number entities for Dreame Mower."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
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

    if not coordinator.supports_cutting_height:
        _LOGGER.debug(
            "Skipping the cutting height entity: model %s has no software-adjustable cutting height",
            coordinator.device_model,
        )
        return

    async_add_entities([DreameMowerCuttingHeightNumber(coordinator)])


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

