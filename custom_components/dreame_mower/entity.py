"""Minimal entity base for Dreame Mower Implementation."""

from __future__ import annotations

import logging

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DreameMowerCoordinator

_LOGGER = logging.getLogger(__name__)


class DreameMowerEntity(CoordinatorEntity[DreameMowerCoordinator]):
    """Minimal base entity for Dreame Mower implementation."""

    def __init__(
        self,
        coordinator: DreameMowerCoordinator,
        entity_description_key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._entity_description_key = entity_description_key
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this mower device."""
        device_info = DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self.coordinator.device_mac)},
            identifiers={(DOMAIN, self.coordinator.device_mac)},
            name=self.coordinator.device_name,
            manufacturer=self.coordinator.device_manufacturer,
            model=self.coordinator.device_model,
            serial_number=self.coordinator.device_serial,
            suggested_area="Garden",
        )
        
        # Add firmware version if available
        if self.coordinator.device_firmware:
            device_info["sw_version"] = self.coordinator.device_firmware
            
        return device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # For real-time updates via MQTT, we only need device connection
        # last_update_success is not reliable since we don't use polling.
        # The transport link stays up even when the robot drops off the cloud,
        # so also require the device to be reported online by the heartbeat.
        return self.coordinator.device_connected and self.coordinator.device_online

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return f"{self.coordinator.device_mac or 'unknown'}_{self._entity_description_key}"