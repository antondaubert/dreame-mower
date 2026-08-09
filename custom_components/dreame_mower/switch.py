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

    if coordinator.supports_edge_mowing_settings:
        switches.append(DreameMowerAutomaticEdgeMowingSwitch(coordinator))
        switches.append(DreameMowerEdgeBladeOffsetSwitch(coordinator))
        if coordinator.supports_safe_edge_mowing:
            switches.append(DreameMowerSafeEdgeMowingSwitch(coordinator))
        else:
            _LOGGER.debug(
                "Skipping the safe edge mowing switch: device %s keeps no such setting",
                coordinator.device_name,
            )
    else:
        _LOGGER.debug(
            "Skipping the edge mowing switches: device %s reported no mowing settings",
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


class DreameMowerEdgeMowingSwitch(DreameMowerEntity, SwitchEntity):
    """Base switch for one edge mowing setting of the active map.

    The settings are stored per map, and per zone once a map follows its per-zone
    settings. These switches always address the active map as a whole; a single
    zone is changed with the set_edge_mowing_settings action.
    """

    _attr_entity_category = EntityCategory.CONFIG
    # Name of the set_edge_mowing_settings argument the switch drives, alongside
    # how the setting reads in an error message.
    _setting: str
    _setting_description: str

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the setting on."""
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the setting off."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Switch the setting for the active map, keeping the other settings as they are."""
        try:
            updated = await self.coordinator.async_set_edge_mowing_settings(**{self._setting: enabled})
        except ValueError as ex:
            raise HomeAssistantError(str(ex)) from ex

        if not updated:
            raise HomeAssistantError(
                f"Failed to turn {self._setting_description} {'on' if enabled else 'off'}"
            )


class DreameMowerAutomaticEdgeMowingSwitch(DreameMowerEdgeMowingSwitch):
    """Switch entity for automatic edge mowing.

    While it is on the mower mows the edges of the map on its own once an
    all-area or zone run has finished.
    """

    _attr_translation_key = "edge_mowing_auto"
    _attr_icon = "mdi:vector-square"
    _setting = "auto"
    _setting_description = "automatic edge mowing"

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the automatic edge mowing switch."""
        super().__init__(coordinator, "edge_mowing_auto")

    @property
    def is_on(self) -> bool | None:
        """Return whether the mower mows the edges on its own, if it is known."""
        return self.coordinator.edge_mowing_auto


class DreameMowerSafeEdgeMowingSwitch(DreameMowerEdgeMowingSwitch):
    """Switch entity for safe edge mowing.

    While it is on the mower keeps a small buffer from the lawn boundary as it
    mows the edges, which spares the boundary at the cost of leaving a strip of
    uncut grass along it.
    """

    _attr_translation_key = "edge_mowing_safe"
    _attr_icon = "mdi:shield-outline"
    _setting = "safe"
    _setting_description = "safe edge mowing"

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the safe edge mowing switch."""
        super().__init__(coordinator, "edge_mowing_safe")

    @property
    def is_on(self) -> bool | None:
        """Return whether the mower keeps a buffer from the boundary, if it is known."""
        return self.coordinator.edge_mowing_safe


class DreameMowerEdgeBladeOffsetSwitch(DreameMowerEdgeMowingSwitch):
    """Switch entity for the offset blade disc used along the edges.

    While it is on the blade disc shifts sideways for the edge laps so the mower
    cuts closer to the boundary than the centred disc reaches. The offset disc
    needs more than one lap to cover the edge, so switching it on also raises a
    single edge lap to two.
    """

    _attr_translation_key = "edge_blade_offset"
    _attr_icon = "mdi:circle-half-full"
    _setting = "blade_offset"
    _setting_description = "the edge blade offset"

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the edge blade offset switch."""
        super().__init__(coordinator, "edge_blade_offset")

    @property
    def is_on(self) -> bool | None:
        """Return whether the blade disc shifts sideways for the edges, if it is known."""
        return self.coordinator.edge_blade_offset
