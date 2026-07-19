"""Binary sensor platform for Dreame Mower Implementation."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .entity import DreameMowerEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower binary sensors from config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    async_add_entities([DreameMowerFirmwareUpdateSensor(coordinator)])


class DreameMowerFirmwareUpdateSensor(DreameMowerEntity, BinarySensorEntity):
    """Reports whether a newer firmware than the installed one is available."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the firmware update binary sensor."""
        super().__init__(coordinator, "firmware_update_available")
        self._attr_device_class = BinarySensorDeviceClass.UPDATE
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "firmware_update_available"

    @property
    def is_on(self) -> bool:
        """Return True if a firmware update is available."""
        return self.coordinator.device_update_available

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the installed and latest available firmware versions."""
        attrs: dict[str, Any] = {"installed_version": self.coordinator.device_firmware}
        latest = self.coordinator.device_latest_firmware
        if latest:
            attrs["latest_version"] = latest
        return attrs
