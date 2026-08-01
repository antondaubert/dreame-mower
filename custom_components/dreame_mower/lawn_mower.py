"""Minimal Lawn Mower Entity for Dreame Mower Implementation."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.lawn_mower import (  # type: ignore[attr-defined]
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.device import MowingMode
from .entity import DreameMowerEntity
from .dreame.const import (
    CUTTING_HEIGHT_ABSOLUTE_MAX_CM,
    CUTTING_HEIGHT_MIN_CM,
    MowingPreferenceMode,
    STATUS_PROPERTY,
    map_status_to_activity,
)

_LOGGER = logging.getLogger(__name__)

# Service-facing names for the mowing preference modes, e.g. "map_wide".
_MOWING_PREFERENCE_MODES = {mode.name.lower(): mode for mode in MowingPreferenceMode}

# Basic feature support for minimal implementation
MINIMAL_SUPPORT_FEATURES = (
    LawnMowerEntityFeature.START_MOWING
    | LawnMowerEntityFeature.PAUSE
    | LawnMowerEntityFeature.DOCK
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower lawn mower entity from a config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "start_zone_mowing",
        {vol.Required("zone_ids"): [vol.Coerce(int)]},
        "async_start_zone_mowing",
    )
    platform.async_register_entity_service(
        "start_edge_mowing",
        {vol.Required("contour_ids"): [vol.All([vol.Coerce(int)], vol.Length(min=2, max=2))]},
        "async_start_edge_mowing",
    )
    platform.async_register_entity_service(
        "start_spot_mowing",
        {vol.Required("spot_area_ids"): [vol.Coerce(int)]},
        "async_start_spot_mowing",
    )
    platform.async_register_entity_service(
        "set_cutting_height",
        {
            vol.Required("height"): vol.All(
                vol.Coerce(float),
                vol.Range(min=CUTTING_HEIGHT_MIN_CM, max=CUTTING_HEIGHT_ABSOLUTE_MAX_CM),
            ),
            vol.Optional("map_id"): vol.Coerce(int),
            vol.Optional("zone_id"): vol.Coerce(int),
        },
        "async_set_cutting_height",
    )
    platform.async_register_entity_service(
        "set_mowing_preference_mode",
        {
            vol.Required("mode"): vol.In(_MOWING_PREFERENCE_MODES),
            vol.Optional("map_id"): vol.Coerce(int),
        },
        "async_set_mowing_preference_mode",
    )

    entity = DreameMowerLawnMower(coordinator)
    async_add_entities([entity])


class DreameMowerLawnMower(DreameMowerEntity, LawnMowerEntity):
    """Minimal Dreame Mower lawn mower entity."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the minimal lawn mower entity."""
        super().__init__(coordinator, "lawn_mower")
        
        self._attr_device_class = DOMAIN
        self._attr_supported_features = MINIMAL_SUPPORT_FEATURES
        self._attr_activity = LawnMowerActivity.DOCKED
        self._attr_icon = "mdi:robot-mower"
        self._attr_name = None  # Fix "A2 None" issue - set explicit name to None so HA uses just device name

        # Register listener for status changes
        self.coordinator.device.register_property_callback(self._on_property_change)
        
        # Initialize activity based on current device status
        self._initialize_activity()
    
    def _initialize_activity(self) -> None:
        """Initialize activity based on current device status."""
        try:
            current_status_code = self.coordinator.device_status_code
            if current_status_code is not None:
                self._attr_activity = map_status_to_activity(current_status_code)
        except Exception as ex:
            _LOGGER.exception("Error initializing activity: %s", ex)

    @property
    def available(self) -> bool:
        """Return True if the mower is available."""
        # Inherit base availability logic and add mower-specific checks
        return super().available

    @property
    def activity(self) -> LawnMowerActivity | None:
        """Return the current activity of the mower."""
        if not self.available:
            return None
        return self._attr_activity
    
    def _on_property_change(self, property_name: str, value: Any) -> None:
        """Handle property changes from the device."""
        if property_name == STATUS_PROPERTY.name:
            new_activity = map_status_to_activity(value)
            if new_activity != self._attr_activity:
                self._attr_activity = new_activity
                self.schedule_update_ha_state()

    async def async_start_mowing(self) -> None:
        """Start or resume mowing."""
        mode = self.coordinator.selected_mowing_mode
        try:
            # While a mowing session is already in progress (mowing, paused, or
            # returning to dock), resume/continue it instead of starting a new
            # task. Only when no session is active do we dispatch a fresh start
            # using the configured map and mowing action.
            if self.coordinator.device.mowing_session_active:
                if not await self.coordinator.device.resume():
                    _LOGGER.error("Failed to resume mowing")
                return

            start_kwargs: dict[str, Any] = {"mode": mode}
            if mode == MowingMode.EDGE:
                selected_contour_id = self.coordinator.selected_contour_id
                if selected_contour_id is None:
                    raise HomeAssistantError("No edge is selected for edge mowing")
                start_kwargs["contour_ids"] = [selected_contour_id]
            elif mode == MowingMode.ZONE:
                selected_zone_id = self.coordinator.selected_zone_id
                if selected_zone_id is None:
                    raise HomeAssistantError("No zone is selected for zone mowing")
                start_kwargs["zone_ids"] = [selected_zone_id]
            elif mode == MowingMode.SPOT:
                selected_spot_area_id = self.coordinator.selected_spot_area_id
                if selected_spot_area_id is None:
                    raise HomeAssistantError("No spot is selected for spot mowing")
                start_kwargs["spot_area_ids"] = [selected_spot_area_id]

            if not await self.coordinator.device.start_mowing(**start_kwargs):
                _LOGGER.error("Failed to start mowing")
                if mode == MowingMode.ALL_AREA:
                    await self._start_all_area_generic_fallback()
        except HomeAssistantError:
            raise
        except Exception as ex:
            _LOGGER.error("Exception while starting mowing: %s", ex)
            if mode == MowingMode.ALL_AREA:
                await self._start_all_area_generic_fallback()

    async def _start_all_area_generic_fallback(self) -> None:
        """Fall back to the generic device-decides START_MOWING action.

        Only used for all-area mowing: when the map-aware start payload is
        rejected or raises, the bare 5:1 action lets the robot run whatever is
        configured in the app. For zone/edge/spot modes this would mow the wrong
        area, so the fallback is deliberately limited to all-area starts.
        """
        _LOGGER.warning("All-area start failed; falling back to generic START_MOWING action")
        if not await self.coordinator.device.start_mowing_generic():
            _LOGGER.error("Generic START_MOWING fallback also failed")

    async def async_start_zone_mowing(self, zone_ids: list[int]) -> None:
        """Start mowing for one or more explicit zone IDs."""
        if not await self.coordinator.device.start_mowing_zones(zone_ids):
            raise HomeAssistantError(f"Failed to start zone mowing for zone IDs: {zone_ids}")

    async def async_start_edge_mowing(self, contour_ids: list[list[int]]) -> None:
        """Start edge mowing for one or more explicit contour IDs."""
        if not await self.coordinator.device.start_mowing_edges(contour_ids):
            raise HomeAssistantError(f"Failed to start edge mowing for contour IDs: {contour_ids}")

    async def async_start_spot_mowing(self, spot_area_ids: list[int]) -> None:
        """Start mowing for one or more explicit spot-area IDs."""
        if not await self.coordinator.device.start_mowing_spots(spot_area_ids):
            raise HomeAssistantError(f"Failed to start spot mowing for spot IDs: {spot_area_ids}")

    async def async_set_cutting_height(
        self,
        height: float,
        map_id: int | None = None,
        zone_id: int | None = None,
    ) -> None:
        """Set the cutting height for a map, or for a single zone of it."""
        self._assert_cutting_height_supported()

        try:
            updated = await self.coordinator.async_set_cutting_height(height, map_id, zone_id)
        except ValueError as ex:
            raise HomeAssistantError(str(ex)) from ex

        if not updated:
            target = "the map" if zone_id is None else f"zone {zone_id}"
            raise HomeAssistantError(f"Failed to set the cutting height of {target} to {height} cm")

    async def async_set_mowing_preference_mode(self, mode: str, map_id: int | None = None) -> None:
        """Choose whether a map follows one set of mowing settings or per-zone ones."""
        self._assert_cutting_height_supported()

        if not await self.coordinator.async_set_mowing_preference_mode(
            _MOWING_PREFERENCE_MODES[mode], map_id
        ):
            raise HomeAssistantError(f"Failed to switch the mowing preferences to {mode}")

    def _assert_cutting_height_supported(self) -> None:
        """Raise when the model has no software-adjustable cutting height."""
        if not self.coordinator.supports_cutting_height:
            raise HomeAssistantError(
                f"{self.coordinator.device_model} has no software-adjustable cutting height"
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes including available zones and contours."""
        attributes: dict[str, Any] = {}
        zones = self.coordinator.zones
        contours = self.coordinator.contours
        available_maps = self.coordinator.available_maps
        current_map_id = self.coordinator.current_map_id
        task_target_map_id = self.coordinator.task_target_map_id
        if zones:
            attributes["zones"] = zones
        if contours:
            attributes["contours"] = contours
        if available_maps:
            attributes["maps"] = available_maps
        if current_map_id is not None:
            attributes["current_map_id"] = current_map_id
        if task_target_map_id is not None:
            attributes["task_target_map_id"] = task_target_map_id
        if self.coordinator.supports_cutting_height:
            # Exposed so automations can read back what set_cutting_height did and
            # tell whether the map-wide height is the one currently in effect.
            attributes["cutting_height"] = self.coordinator.cutting_height
            attributes["zone_cutting_heights"] = self.coordinator.zone_cutting_heights
            mowing_preference_mode = self.coordinator.mowing_preference_mode
            attributes["mowing_preference_mode"] = (
                None if mowing_preference_mode is None else mowing_preference_mode.name.lower()
            )
        attributes["selected_mowing_mode"] = self.coordinator.selected_mowing_mode.value
        if self.coordinator.selected_contour_id is not None:
            attributes["selected_contour_id"] = self.coordinator.selected_contour_id
        if self.coordinator.selected_zone_id is not None:
            attributes["selected_zone_id"] = self.coordinator.selected_zone_id
        if self.coordinator.selected_spot_area_id is not None:
            attributes["selected_spot_area_id"] = self.coordinator.selected_spot_area_id
        return attributes

    async def async_pause(self) -> None:
        """Pause mowing."""
        try:
            if not await self.coordinator.device.pause():
                _LOGGER.error("Failed to pause mowing")
        except Exception as ex:
            _LOGGER.error("Exception while pausing mowing: %s", ex)

    async def async_dock(self) -> None:
        """Return to dock."""
        try:
            if not await self.coordinator.device.return_to_dock():
                _LOGGER.error("Failed to dock")
        except Exception as ex:
            _LOGGER.error("Exception while docking: %s", ex)
