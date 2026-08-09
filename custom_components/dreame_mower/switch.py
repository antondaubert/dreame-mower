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

    switches: list[SwitchEntity] = []

    if coordinator.supports_charging_period:
        switches.append(DreameMowerChargingPeriodSwitch(coordinator))
    else:
        _LOGGER.debug(
            "Skipping the charging period switch: device %s reported no charging settings",
            coordinator.device_name,
        )

    if coordinator.supports_rain_protection:
        switches.append(DreameMowerRainProtectionSwitch(coordinator))
    else:
        _LOGGER.debug(
            "Skipping the rain protection switch: device %s reported no rain settings",
            coordinator.device_name,
        )

    async_add_entities(switches)


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


class DreameMowerRainProtectionSwitch(DreameMowerEntity, SwitchEntity):
    """Switch entity for rain protection.

    While it is on the mower returns to its station when it detects rain and
    waits out the configured delay before it picks the task back up.
    """

    _attr_translation_key = "rain_protection"
    _attr_icon = "mdi:weather-rainy"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the rain protection switch."""
        super().__init__(coordinator, "rain_protection")

    @property
    def is_on(self) -> bool | None:
        """Return whether rain protection is on, if it is known."""
        return self.coordinator.rain_protection_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Turn rain protection on."""
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn rain protection off."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Switch rain protection, keeping the configured delay as it is."""
        if not await self.coordinator.async_set_rain_protection(enabled=enabled):
            raise HomeAssistantError(
                f"Failed to turn rain protection {'on' if enabled else 'off'}"
            )
