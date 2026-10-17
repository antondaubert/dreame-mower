"""Select entities for Dreame Mower."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.const import (
    DEVICE_SETTINGS_NAVIGATION_PATH_KEY,
    RAIN_DELAY_MAX_HOURS,
    RAIN_DELAY_MIN_HOURS,
)
from .entity import DreameMowerEntity, device_errors_as_ha_errors

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

    # These exist only on mowers that turn out to offer the setting.
    @callback
    def add_probed() -> None:
        probed: list[SelectEntity] = []
        if coordinator.supports_rain_protection:
            probed.append(DreameMowerRainDelaySelect(coordinator))
        if coordinator.supports_device_setting(DEVICE_SETTINGS_NAVIGATION_PATH_KEY):
            probed.append(DreameMowerNavigationPathSelect(coordinator))
        async_add_entities(probed)

    coordinator.async_when_probed(add_probed)


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

        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_rain_protection(delay_hours=delay_hours)

        if not updated:
            raise HomeAssistantError(f"Failed to set the after-rain delay to {option}")

        if self.coordinator.rain_delay_hours != delay_hours:
            raise HomeAssistantError(
                f"The mower kept its after-rain delay of "
                f"{_rain_delay_label(self.coordinator.rain_delay_hours or 0)} instead of "
                f"{option}; it only takes a new delay while rain protection is on"
            )


# How the mower drives between the station and the zones.
_NAVIGATION_PATH_LABELS = {0: "Direct path", 1: "Smart path"}


class DreameMowerNavigationPathSelect(DreameMowerEntity, SelectEntity):
    """Select for the way the mower drives between its station and the zones.

    The direct path is the shortest; the smart path varies the route so the
    lawn does not wear ruts.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        super().__init__(coordinator, "navigation_path")
        self._attr_translation_key = "navigation_path"
        self._attr_icon = "mdi:map-marker-path"

    @property
    def options(self) -> list[str]:
        return list(_NAVIGATION_PATH_LABELS.values())

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.device_setting(DEVICE_SETTINGS_NAVIGATION_PATH_KEY)
        return _NAVIGATION_PATH_LABELS.get(int(value)) if isinstance(value, (bool, int)) else None

    async def async_select_option(self, option: str) -> None:
        value = next((value for value, label in _NAVIGATION_PATH_LABELS.items() if label == option), None)
        if value is None:
            raise ValueError(f"Unknown navigation path: {option}")
        with device_errors_as_ha_errors():
            updated = await self.coordinator.async_set_device_setting(DEVICE_SETTINGS_NAVIGATION_PATH_KEY, {"value": value})
        if not updated:
            raise HomeAssistantError(f"The mower did not take the navigation path {option}")
