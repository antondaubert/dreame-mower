"""Switch entities for Dreame Mower."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .entity import DreameMowerEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower switches from a config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    if not coordinator.supports_charging_period:
        _LOGGER.debug(
            "Skipping the charging period switch: device %s reported no charging settings",
            coordinator.device_name,
        )
        return

    async_add_entities([DreameMowerChargingPeriodSwitch(coordinator)])


class DreameMowerChargingPeriodSwitch(DreameMowerEntity, SwitchEntity):
    """Switch entity for the custom charging period.

    While the period is on the mower only keeps a safe battery level when idle
    and fully charges inside the configured window.
    """

    _attr_translation_key = "charging_period"
    _attr_icon = "mdi:battery-clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the charging period switch."""
        super().__init__(coordinator, "charging_period")

    @property
    def is_on(self) -> bool | None:
        """Return whether the custom charging period is on, if it is known."""
        return self.coordinator.charging_period_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the custom charging period on."""
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the custom charging period off."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Switch the charging period, keeping the configured times as they are."""
        if not await self.coordinator.async_set_charging_period(enabled=enabled):
            raise HomeAssistantError(
                f"Failed to turn the charging period {'on' if enabled else 'off'}"
            )
