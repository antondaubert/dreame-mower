"""Select entities for Dreame Mower."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.const import RAIN_DELAY_MAX_HOURS, RAIN_DELAY_MIN_HOURS
from .dreame.device import MowingMode
from .entity import DreameMowerEntity

_MOWING_MODE_LABELS: dict[MowingMode, str] = {
    MowingMode.ALL_AREA: "All area",
    MowingMode.EDGE: "Edge",
    MowingMode.ZONE: "Zone",
    MowingMode.SPOT: "Spot",
}

# The after-rain delay is offered as whole hours, led by the option to stay
# docked, which is a behaviour rather than a duration.
_RAIN_DELAY_DO_NOT_RESUME_LABEL = "Don't mow after rain"


def _rain_delay_label(hours: int) -> str:
    """Return the label the after-rain delay of the given length is offered as."""
    if hours == RAIN_DELAY_MIN_HOURS:
        return _RAIN_DELAY_DO_NOT_RESUME_LABEL
    return f"{hours} h"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower selects from a config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    selects: list[SelectEntity] = [
        DreameMowerMapSelect(coordinator),
        DreameMowerMowingActionSelect(coordinator),
        DreameMowerEdgeSelect(coordinator),
        DreameMowerZoneSelect(coordinator),
        DreameMowerSpotSelect(coordinator),
    ]

    if coordinator.supports_rain_protection:
        selects.append(DreameMowerRainDelaySelect(coordinator))

    async_add_entities(selects)


class DreameMowerMapSelect(DreameMowerEntity, SelectEntity):
    """Select entity for the active map."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the map select entity."""
        super().__init__(coordinator, "map_select")
        self._attr_name = "Map"
        self._attr_icon = "mdi:map-marker-path"

    @property
    def options(self) -> list[str]:
        """Return the available map options."""
        return [self._option_label(map_entry) for map_entry in self.coordinator.available_maps]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected map option."""
        current_map_id = self.coordinator.current_map_id
        if current_map_id is None:
            return None

        for map_entry in self.coordinator.available_maps:
            if map_entry["id"] == current_map_id:
                return self._option_label(map_entry)

        return None

    async def async_select_option(self, option: str) -> None:
        """Select the active map on the mower."""
        map_id = self._map_id_from_option(option)
        if map_id is None:
            raise HomeAssistantError(f"Unknown map option: {option}")

        if await self.coordinator.device.set_current_map(map_id):
            return

        if self.coordinator.device.mowing_session_active:
            raise HomeAssistantError(
                f"Cannot switch to {option} while a mowing task is in progress. "
                "Finish or cancel the task, then try again."
            )

        raise HomeAssistantError(f"Failed to select map option: {option}")

    def _option_label(self, map_entry: dict[str, Any]) -> str:
        """Return the label shown for a map option."""
        name = map_entry.get("name") or f"Map {map_entry['id']}"
        return f"{name} (#{map_entry['id']})"

    def _map_id_from_option(self, option: str) -> int | None:
        """Resolve a select option back to its map ID."""
        for map_entry in self.coordinator.available_maps:
            if self._option_label(map_entry) == option:
                return int(map_entry["id"])
        return None


class DreameMowerMowingActionSelect(DreameMowerEntity, SelectEntity):
    """Select entity for the default start-mowing action."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the mowing action select entity."""
        super().__init__(coordinator, "mowing_action")
        self._attr_name = "Mowing Action"
        self._attr_icon = "mdi:play-box-multiple"

    @property
    def options(self) -> list[str]:
        """Return selectable default mowing actions."""
        return [_MOWING_MODE_LABELS[mode] for mode in self.coordinator.selectable_mowing_modes]

    @property
    def current_option(self) -> str:
        """Return the selected default mowing action."""
        return _MOWING_MODE_LABELS[self.coordinator.selected_mowing_mode]

    async def async_select_option(self, option: str) -> None:
        """Update the default mowing action used by the start button."""
        for mode, label in _MOWING_MODE_LABELS.items():
            if label == option:
                await self.coordinator.async_set_selected_mowing_mode(mode)
                return

        raise ValueError(f"Unknown mowing action option: {option}")


class DreameMowerEdgeSelect(DreameMowerEntity, SelectEntity):
    """Select entity for a single target edge contour."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the edge select entity."""
        super().__init__(coordinator, "edge_select")
        self._attr_name = "Edge"
        self._attr_icon = "mdi:vector-polyline"

    @property
    def options(self) -> list[str]:
        """Return the available edge-contour options."""
        return [self._option_label(contour) for contour in self.coordinator.contours]

    @property
    def current_option(self) -> str | None:
        """Return the selected edge-contour option."""
        selected_contour_id = self.coordinator.selected_contour_id
        if selected_contour_id is None:
            return None

        for contour in self.coordinator.contours:
            if contour == selected_contour_id:
                return self._option_label(contour)

        return None

    async def async_select_option(self, option: str) -> None:
        """Select a single target edge contour for edge mowing."""
        contour_id = self._id_from_option(option)
        if contour_id is None:
            raise ValueError(f"Unknown edge option: {option}")

        await self.coordinator.async_set_selected_contour_id(contour_id)

    def _option_label(self, contour: list[int]) -> str:
        """Return the label shown for an edge-contour option."""
        zone_id = contour[0]
        for zone in self.coordinator.zones:
            if int(zone["id"]) == zone_id:
                name = zone.get("name") or f"Zone {zone_id}"
                return f"{name} edge"
        return f"Edge ({contour[0]}, {contour[1]})"

    def _id_from_option(self, option: str) -> list[int] | None:
        """Resolve a select option back to its contour ID."""
        for contour in self.coordinator.contours:
            if self._option_label(contour) == option:
                return contour
        return None


class DreameMowerZoneSelect(DreameMowerEntity, SelectEntity):
    """Select entity for a single target zone."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the zone select entity."""
        super().__init__(coordinator, "zone_select")
        self._attr_name = "Zone"
        self._attr_icon = "mdi:texture-box"

    @property
    def options(self) -> list[str]:
        """Return the available zone options."""
        return [self._option_label(zone) for zone in self.coordinator.zones]

    @property
    def current_option(self) -> str | None:
        """Return the selected zone option."""
        selected_zone_id = self.coordinator.selected_zone_id
        if selected_zone_id is None:
            return None

        for zone in self.coordinator.zones:
            if int(zone["id"]) == selected_zone_id:
                return self._option_label(zone)

        return None

    async def async_select_option(self, option: str) -> None:
        """Select a single target zone for zone mowing."""
        zone_id = self._id_from_option(option)
        if zone_id is None:
            raise ValueError(f"Unknown zone option: {option}")

        await self.coordinator.async_set_selected_zone_id(zone_id)

    def _option_label(self, zone: dict[str, Any]) -> str:
        """Return the label shown for a zone option."""
        name = zone.get("name") or f"Zone {zone['id']}"
        return f"{name} (#{zone['id']})"

    def _id_from_option(self, option: str) -> int | None:
        """Resolve a select option back to its zone ID."""
        for zone in self.coordinator.zones:
            if self._option_label(zone) == option:
                return int(zone["id"])
        return None


class DreameMowerSpotSelect(DreameMowerEntity, SelectEntity):
    """Select entity for a single target spot area."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the spot select entity."""
        super().__init__(coordinator, "spot_select")
        self._attr_name = "Spot"
        self._attr_icon = "mdi:map-marker-radius"

    @property
    def options(self) -> list[str]:
        """Return the available spot-area options."""
        return [self._option_label(spot_area) for spot_area in self.coordinator.spot_areas]

    @property
    def current_option(self) -> str | None:
        """Return the selected spot-area option."""
        selected_spot_area_id = self.coordinator.selected_spot_area_id
        if selected_spot_area_id is None:
            return None

        for spot_area in self.coordinator.spot_areas:
            if int(spot_area["id"]) == selected_spot_area_id:
                return self._option_label(spot_area)

        return None

    async def async_select_option(self, option: str) -> None:
        """Select a single target spot area for spot mowing."""
        spot_area_id = self._id_from_option(option)
        if spot_area_id is None:
            raise ValueError(f"Unknown spot option: {option}")

        await self.coordinator.async_set_selected_spot_area_id(spot_area_id)

    def _option_label(self, spot_area: dict[str, Any]) -> str:
        """Return the label shown for a spot-area option."""
        name = spot_area.get("name") or f"Spot {spot_area['id']}"
        return f"{name} (#{spot_area['id']})"

    def _id_from_option(self, option: str) -> int | None:
        """Resolve a select option back to its spot-area ID."""
        for spot_area in self.coordinator.spot_areas:
            if self._option_label(spot_area) == option:
                return int(spot_area["id"])
        return None


class DreameMowerRainDelaySelect(DreameMowerEntity, SelectEntity):
    """Select entity for how long the mower waits after rain before it resumes.

    The mower offers whole hours, preceded by the option to stay docked until it
    is started again.

    A changed delay applies the next time rain protection triggers, and the mower
    only takes a new delay while rain protection is on; with it off it keeps the
    delay it holds.
    """

    _attr_translation_key = "rain_delay"
    _attr_icon = "mdi:weather-rainy"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the after-rain delay entity."""
        super().__init__(coordinator, "rain_delay")
        self._hours_by_label = {
            _rain_delay_label(hours): hours
            for hours in range(RAIN_DELAY_MIN_HOURS, RAIN_DELAY_MAX_HOURS + 1)
        }

    @property
    def options(self) -> list[str]:
        """Return every after-rain delay the model offers."""
        return list(self._hours_by_label)

    @property
    def current_option(self) -> str | None:
        """Return the configured after-rain delay, if it is known."""
        delay_hours = self.coordinator.rain_delay_hours
        if delay_hours is None:
            return None
        return _rain_delay_label(delay_hours)

    async def async_select_option(self, option: str) -> None:
        """Set how long the mower waits after rain."""
        delay_hours = self._hours_by_label.get(option)
        if delay_hours is None:
            raise ValueError(f"Unknown after-rain delay option: {option}")

        if not await self.coordinator.async_set_rain_protection(delay_hours=delay_hours):
            raise HomeAssistantError(f"Failed to set the after-rain delay to {option}")

        if self.coordinator.rain_delay_hours != delay_hours:
            raise HomeAssistantError(
                f"The mower kept its after-rain delay of "
                f"{_rain_delay_label(self.coordinator.rain_delay_hours or 0)} instead of "
                f"{option}; it only takes a new delay while rain protection is on"
            )
