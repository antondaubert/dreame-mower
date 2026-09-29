"""Update platform for Dreame Mower Implementation."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .entity import DreameMowerEntity, device_errors_as_ha_errors

# The device reports this until it has told the cloud which firmware it runs.
_UNKNOWN_FIRMWARE = "Unknown"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dreame Mower firmware update entity from config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    async_add_entities([DreameMowerFirmwareUpdate(coordinator)])


class DreameMowerFirmwareUpdate(DreameMowerEntity, UpdateEntity):
    """The mower's firmware, with the newer release the cloud offers for it."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.PROGRESS
        | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the firmware update entity."""
        super().__init__(coordinator, "firmware")

    @property
    def installed_version(self) -> str | None:
        """Return the firmware version the mower runs."""
        firmware = self.coordinator.device_firmware
        if not firmware or firmware == _UNKNOWN_FIRMWARE:
            return None
        return firmware

    @property
    def latest_version(self) -> str | None:
        """Return the newest firmware for the mower.

        That is the installed one when the cloud has nothing newer, and unknown
        until the cloud has been asked.
        """
        if not self.coordinator.device_firmware_status_checked:
            return None
        return self.coordinator.device_latest_firmware or self.installed_version

    @property
    def in_progress(self) -> bool:
        """Return whether the mower is downloading or installing an update."""
        return self.coordinator.device_firmware_update_in_progress

    @property
    def update_percentage(self) -> int | None:
        """Return how far the running update has come, in percent."""
        return self.coordinator.device_firmware_update_percentage

    async def async_release_notes(self) -> str | None:
        """Return the release notes of the available firmware."""
        return self.coordinator.device_firmware_release_notes

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Have the mower download and install the available firmware."""
        with device_errors_as_ha_errors():
            if not await self.coordinator.async_start_firmware_update():
                raise HomeAssistantError("The firmware update could not be started")
