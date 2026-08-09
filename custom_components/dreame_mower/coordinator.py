"""DataUpdateCoordinator for Dreame Mower Integration."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME

from .const import DOMAIN, CONF_NOTIFY
from .config_flow import (
    CONF_ACCOUNT_TYPE, 
    CONF_COUNTRY, 
    CONF_DID, 
    CONF_MAC, 
    CONF_MODEL, 
    CONF_SERIAL, 
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_SWBOT,
    NOTIFICATION_INFORMATION,
    NOTIFICATION_WARNING,
    NOTIFICATION_ERROR,
)
from .dreame.device import DreameMowerDevice, DreameSwbotDevice, MowingMode
from .dreame.property import (
    DEVICE_CODE_ERROR_PROPERTY_NAME,
    DEVICE_CODE_WARNING_PROPERTY_NAME,
    DEVICE_CODE_INFO_PROPERTY_NAME,
    NOTIFICATION_CODE_FIELD,
    NOTIFICATION_NAME_FIELD,
    NOTIFICATION_DESCRIPTION_FIELD,
)
from .dreame.const import (
    CURRENT_MAP_ID_PROPERTY_NAME,
    POWER_STATE_PROPERTY,
    RAIN_DEVICE_CODES,
    DeviceStatus,
    MowingPreferenceMode,
    STATUS_PROPERTY,
    supports_cutting_height,
)
from .dreame.property.property_misc import (
    PROPERTY_1_1_ACTIVE_CODES_NAME,
    SETTINGS_CHANGED_PROPERTY_NAME,
)

# How long a settings change the integration made itself keeps the device from
# triggering a re-read. The device announces every change, including the ones it
# was just told to make, and a write already knows what it wrote.
_SETTINGS_WRITE_ECHO_SECONDS = 5.0

_LOGGER = logging.getLogger(__name__)

class DreameMowerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Dreame Mower implementation."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry: ConfigEntry,
    ) -> None:
        """Initialize Dreame Mower coordinator."""
        self.entry = entry

        device_cls = (
            DreameSwbotDevice
            if entry.data.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_SWBOT
            else DreameMowerDevice
        )
        self.device = device_cls(
            entry.data[CONF_DID],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data[CONF_ACCOUNT_TYPE],
            entry.data[CONF_COUNTRY],
            hass.config.config_dir)
        self._selected_mowing_mode = MowingMode.ALL_AREA
        self._selected_contour_id: tuple[int, int] | None = None
        self._selected_zone_id: int | None = None
        self._selected_spot_area_id: int | None = None
        self._consumable_values: list[int] | None = None
        self._charging_settings: dict[str, Any] | None = None
        self._rain_settings: dict[str, Any] | None = None
        self._rain_protection_end_timestamp: int | None = None
        self._last_settings_write: float | None = None

        # Initialize coordinator with no automatic polling (device will push updates)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # No polling - use real-time updates from device
            config_entry=entry,  # Required for async_config_entry_first_refresh
        )
        
        # Register callback to receive device property updates
        self.device.register_property_callback(self._handle_device_update)
        


    async def _async_update_data(self) -> dict[str, Any]:
        """Update data. This method is required by DataUpdateCoordinator."""
        return {
            "name": self.device_name,
            "connected": self.device_connected,
            "online": self.device_online,
            "last_update": self.last_update,
            "mac": self.device_mac,
            "model": self.device_model,
            "serial": self.device_serial,
            "firmware": self.device_firmware,
            "manufacturer": self.device_manufacturer,
            "battery_percent": self.device_battery_percent,
            "status": self.device_status,
            "bluetooth_connected": self.device_bluetooth_connected,
            "charging_status": self.device_charging_status,
            "current_task_data": self.current_task_data,
            "task_status": self.device_task_status,
            "mowing_progress_percent": self.mowing_progress_percent,
            "current_area_sqm": self.current_area_sqm,
            "total_area_sqm": self.total_area_sqm,
            "mower_coordinates": self.mower_coordinates,
            "current_segment": self.current_segment,
            "mower_heading": self.mower_heading,
            "mowing_path_history": self.mowing_path_history,
        }

    @property
    def device_type(self) -> str:
        """Return device type ('mower' or 'swbot')."""
        return self.entry.data.get(CONF_DEVICE_TYPE, "mower")

    @property
    def device_mac(self) -> str:
        """Return device MAC address for device identification from config entry."""
        return self.entry.data[CONF_MAC]

    @property
    def device_connected(self) -> bool:
        """Return device connection status."""
        return self.device.connected

    @property
    def device_online(self) -> bool:
        """Return whether the device itself is online per the cloud heartbeat."""
        return self.device.online

    @property
    def device_name(self) -> str:
        """Return device name for display purposes from config entry."""
        return self.entry.data[CONF_NAME]

    @property
    def device_model(self) -> str:
        """Return device model identifier from config entry."""
        return self.entry.data[CONF_MODEL]

    @property
    def device_serial(self) -> str:
        """Return device serial number from config entry."""
        return self.entry.data[CONF_SERIAL]

    @property
    def device_firmware(self) -> str:
        """Return device firmware version."""
        return self.device.firmware

    @property
    def device_update_available(self) -> bool:
        """Return whether a firmware update is available."""
        return self.device.firmware_update_available

    @property
    def device_latest_firmware(self) -> str | None:
        """Return the latest available firmware version, if any."""
        return self.device.firmware_latest_version

    @property
    def device_manufacturer(self) -> str:
        """Return device manufacturer."""
        return "Dreametech™"

    @property
    def last_update(self) -> str:
        """Return last update timestamp."""
        return self.device.last_update.isoformat()

    @property
    def device_battery_percent(self) -> int | None:
        """Return device battery percentage."""
        return self.device.battery_percent

    @property
    def device_status(self) -> str | None:
        """Return device status."""
        return self.device.status
    
    @property 
    def device_status_code(self) -> int:
        """Return raw device status code."""
        return self.device.status_code

    @property
    def device_bluetooth_connected(self) -> bool | None:
        """Return Bluetooth connection status."""
        return self.device.bluetooth_connected

    @property
    def device_charging_status(self) -> str | None:
        """Return charging status (mapped text)."""
        return self.device.charging_status

    @property
    def current_task_data(self) -> dict | None:
        """Return current task data from TaskHandler."""
        return self.device.current_task_data

    @property
    def device_task_status(self) -> str | None:
        """Return the current mowing task status decoded from the heartbeat."""
        return self.device.task_status

    @property
    def device_code(self) -> int | None:
        """Return current device code (2:2)."""
        return self.device.device_code

    @property
    def device_code_name(self) -> str | None:
        """Return device code name."""
        return self.device.device_code_name

    @property
    def device_code_description(self) -> str | None:
        """Return device code description."""
        return self.device.device_code_description

    @property
    def device_code_is_error(self) -> bool | None:
        """Return True if device code represents an error."""
        return self.device.device_code_is_error

    @property
    def device_code_is_warning(self) -> bool | None:
        """Return True if device code represents a warning."""
        return self.device.device_code_is_warning

    @property
    def mowing_progress_percent(self) -> float | None:
        """Return current mowing progress percentage."""
        return self.device.mowing_progress_percent

    @property
    def current_area_sqm(self) -> float | None:
        """Return current mowed area in square meters."""
        return self.device.current_area_sqm

    @property
    def total_area_sqm(self) -> float | None:
        """Return total planned area in square meters."""
        return self.device.total_area_sqm

    @property
    def mower_coordinates(self) -> tuple[int, int] | None:
        """Return current mower coordinates as (x, y) tuple."""
        return self.device.mower_coordinates

    @property
    def current_segment(self) -> int | None:
        """Return current mowing segment/lane index."""
        return self.device.current_segment

    @property
    def mower_heading(self) -> float | None:
        """Return current mower heading in degrees."""
        return self.device.mower_heading

    @property
    def mowing_path_history(self) -> list[list[int]]:
        """Return path history for visualization (list of [x, y] in map units)."""
        return self.device.mowing_path_history

    @property
    def zones(self) -> list[dict]:
        """Return available mowing zones (id, name, area) from vector map."""
        return self.device.zones

    @property
    def contours(self) -> list[list[int]]:
        """Return available edge-mowing contour IDs from vector map."""
        return self.device.contours

    @property
    def spot_areas(self) -> list[dict]:
        """Return available spot-mowing areas from vector map."""
        return self.device.spot_areas

    @property
    def available_maps(self) -> list[dict[str, Any]]:
        """Return the maps currently known from vector map data."""
        return self.device.available_maps

    @property
    def current_map_id(self) -> int | None:
        """Return the currently selected map, if known."""
        return self.device.current_map_id

    @property
    def supports_cutting_height(self) -> bool:
        """Return whether this model's cutting height can be set from software."""
        return supports_cutting_height(self.device_model)

    @property
    def cutting_height(self) -> float | None:
        """Return the current map's cutting height in cm, if known."""
        return self.device.cutting_height

    @property
    def zone_cutting_heights(self) -> dict[int, float]:
        """Return the per-zone cutting heights in cm known for the current map."""
        return self.device.zone_cutting_heights

    @property
    def mowing_preference_mode(self) -> MowingPreferenceMode | None:
        """Return whether the current map applies map-wide or per-zone preferences."""
        return self.device.mowing_preference_mode

    async def async_fetch_cutting_height(self) -> None:
        """Read the current map's cutting height from the device."""
        await self.device.refresh_cutting_height()
        self.async_update_listeners()

    async def async_fetch_zone_cutting_heights(self) -> dict[int, float]:
        """Read the current map's per-zone cutting heights from the device."""
        zone_heights = await self.device.refresh_zone_cutting_heights()
        self.async_update_listeners()
        return zone_heights

    async def async_fetch_cutting_heights(self) -> None:
        """Read the current map's map-wide and per-zone cutting heights."""
        await self.device.refresh_cutting_height()
        await self.device.refresh_zone_cutting_heights()
        self.async_update_listeners()

    async def async_set_cutting_height(
        self,
        height_cm: float,
        map_id: int | None = None,
        zone_id: int | None = None,
    ) -> bool:
        """Set a cutting height, defaulting to the current map and its map-wide record."""
        updated = await self.device.set_cutting_height(height_cm, map_id, zone_id)
        self.async_update_listeners()
        return updated

    async def async_set_mowing_preference_mode(
        self,
        mode: MowingPreferenceMode,
        map_id: int | None = None,
    ) -> bool:
        """Choose whether a map follows its map-wide or its per-zone preferences."""
        updated = await self.device.set_mowing_preference_mode(mode, map_id)
        self.async_update_listeners()
        return updated

    @property
    def supports_charging_period(self) -> bool:
        """Return whether the device reported a custom charging period."""
        return self._charging_settings is not None

    @property
    def charging_period_enabled(self) -> bool | None:
        """Return whether the custom charging period is on, if it is known."""
        if self._charging_settings is None:
            return None
        return bool(self._charging_settings["charging_period_enabled"])

    @property
    def charging_period_start_minutes(self) -> int | None:
        """Return the start of the charging period in minutes since midnight."""
        if self._charging_settings is None:
            return None
        return int(self._charging_settings["charging_period_start_minutes"])

    @property
    def charging_period_end_minutes(self) -> int | None:
        """Return the end of the charging period in minutes since midnight."""
        if self._charging_settings is None:
            return None
        return int(self._charging_settings["charging_period_end_minutes"])

    async def async_fetch_charging_settings(self) -> bool:
        """Read the battery and charging settings from the device."""
        settings = await self.device.get_charging_settings()
        if settings is None:
            return False

        self._charging_settings = settings
        self.async_update_listeners()
        return True

    async def async_set_charging_period(
        self,
        enabled: bool | None = None,
        start_minutes: int | None = None,
        end_minutes: int | None = None,
    ) -> bool:
        """Update the custom charging period, keeping every unspecified part as is."""
        self._note_settings_write()
        settings = await self.device.set_charging_period(
            enabled=enabled,
            start_minutes=start_minutes,
            end_minutes=end_minutes,
        )
        if settings is None:
            return False

        self._charging_settings = settings
        self.async_update_listeners()
        return True

    @property
    def supports_rain_protection(self) -> bool:
        """Return whether the device reported rain protection settings."""
        return self._rain_settings is not None

    @property
    def rain_protection_enabled(self) -> bool | None:
        """Return whether rain protection is on, if it is known."""
        if self._rain_settings is None:
            return None
        return bool(self._rain_settings["rain_protection_enabled"])

    @property
    def rain_delay_hours(self) -> int | None:
        """Return how long the mower waits after rain, in whole hours."""
        if self._rain_settings is None:
            return None
        return int(self._rain_settings["rain_delay_hours"])

    @property
    def rain_protection_end_time(self) -> datetime | None:
        """Return when rain protection lets the mower work again, if it is holding it back."""
        if self._rain_protection_end_timestamp is None:
            return None
        return datetime.fromtimestamp(self._rain_protection_end_timestamp, tz=timezone.utc)

    @property
    def rain_protection_active(self) -> bool:
        """Return whether rain is currently keeping the mower from working.

        The device leaves the end time it last reported in place, so a time that
        has passed says nothing about the mower being held back any more.
        """
        end_time = self.rain_protection_end_time
        return end_time is not None and end_time > dt_util.utcnow()

    async def async_fetch_rain_settings(self) -> bool:
        """Read the rain protection settings from the device."""
        settings = await self.device.get_rain_settings()
        if settings is None:
            return False

        self._rain_settings = settings
        self.async_update_listeners()
        return True

    async def async_fetch_rain_protection_end(self) -> bool:
        """Read when rain protection lets the mower work again.

        A read that did not come through leaves the known end time in place: it
        is the state the entities report on, and dropping it would read as the
        mower being free to work.
        """
        end_timestamp = await self.device.get_rain_protection_end_timestamp()
        if end_timestamp is None:
            return False

        self._rain_protection_end_timestamp = end_timestamp or None
        self.async_update_listeners()
        return True

    async def async_refresh_rain_state(self) -> None:
        """Re-read both the rain protection settings and its end time."""
        if not await self.async_fetch_rain_settings():
            # A device with no rain settings has no protection that could expire.
            return

        await self.async_fetch_rain_protection_end()

    async def async_refresh_device_settings(self) -> None:
        """Re-read every setting the integration keeps from the device.

        The settings all live in one record, so both the charging and the rain
        settings come out of a single read.
        """
        settings = await self.device.get_device_settings()
        if settings is None:
            return

        charging_settings = self.device.decode_charging_settings(settings)
        if charging_settings is not None:
            self._charging_settings = charging_settings

        rain_settings = self.device.decode_rain_settings(settings)
        if rain_settings is not None:
            self._rain_settings = rain_settings

        self.async_update_listeners()

    async def async_set_rain_protection(
        self,
        enabled: bool | None = None,
        delay_hours: int | None = None,
    ) -> bool:
        """Update rain protection, keeping every unspecified part as is."""
        self._note_settings_write()
        settings = await self.device.set_rain_protection(
            enabled=enabled,
            delay_hours=delay_hours,
        )
        if settings is None:
            return False

        self._rain_settings = settings
        self.async_update_listeners()

        # Switching protection off releases a mower rain is holding back, so the
        # end time it reported no longer stands.
        await self.async_fetch_rain_protection_end()
        return True

    @property
    def task_target_map_id(self) -> int | None:
        """Return the map targeted by the active task, if known."""
        return self.device.task_target_map_id

    @property
    def selected_mowing_mode(self) -> MowingMode:
        """Return the user-selected default mowing mode for the main start action."""
        return self._selected_mowing_mode

    @property
    def selectable_mowing_modes(self) -> list[MowingMode]:
        """Return mowing modes that can be driven by the main start action."""
        modes = [MowingMode.ALL_AREA]
        if self.contours:
            modes.append(MowingMode.EDGE)
        if self.zones:
            modes.append(MowingMode.ZONE)
        if self.spot_areas:
            modes.append(MowingMode.SPOT)
        return modes

    @property
    def selected_contour_id(self) -> list[int] | None:
        """Return the selected contour ID, defaulting to the first available edge."""
        self._normalize_selection_state()
        if self._selected_contour_id is None:
            return None
        return [self._selected_contour_id[0], self._selected_contour_id[1]]

    async def async_set_selected_mowing_mode(self, mode: MowingMode) -> None:
        """Update the user-selected default mowing mode."""
        self._normalize_selection_state()

        if mode not in self.selectable_mowing_modes:
            raise ValueError(f"Unsupported selectable mowing mode: {mode}")

        if self._selected_mowing_mode == mode:
            return

        self._selected_mowing_mode = mode
        data = await self._async_update_data()
        self.async_set_updated_data(data)

    async def async_set_selected_contour_id(self, contour_id: list[int] | None) -> None:
        """Update the currently selected single contour ID."""
        normalized_contour_id: tuple[int, int] | None = None
        if contour_id is not None:
            if len(contour_id) != 2:
                raise ValueError(f"Unsupported contour ID: {contour_id}")
            normalized_contour_id = (int(contour_id[0]), int(contour_id[1]))
            if normalized_contour_id not in {(int(c[0]), int(c[1])) for c in self.contours}:
                raise ValueError(f"Unsupported contour ID: {contour_id}")

        if self._selected_contour_id == normalized_contour_id:
            return

        self._selected_contour_id = normalized_contour_id
        data = await self._async_update_data()
        self.async_set_updated_data(data)

    @property
    def selected_zone_id(self) -> int | None:
        """Return the selected zone ID, defaulting to the first available zone."""
        self._normalize_selection_state()
        return self._selected_zone_id

    @property
    def selected_spot_area_id(self) -> int | None:
        """Return the selected spot-area ID, defaulting to the first available spot."""
        self._normalize_selection_state()
        return self._selected_spot_area_id

    async def async_set_selected_zone_id(self, zone_id: int | None) -> None:
        """Update the currently selected single zone ID."""
        if zone_id is not None and zone_id not in {int(zone["id"]) for zone in self.zones}:
            raise ValueError(f"Unsupported zone ID: {zone_id}")

        if self._selected_zone_id == zone_id:
            return

        self._selected_zone_id = zone_id
        data = await self._async_update_data()
        self.async_set_updated_data(data)

    async def async_set_selected_spot_area_id(self, spot_area_id: int | None) -> None:
        """Update the currently selected single spot area ID."""
        if spot_area_id is not None and spot_area_id not in {int(spot_area["id"]) for spot_area in self.spot_areas}:
            raise ValueError(f"Unsupported spot area ID: {spot_area_id}")

        if self._selected_spot_area_id == spot_area_id:
            return

        self._selected_spot_area_id = spot_area_id
        data = await self._async_update_data()
        self.async_set_updated_data(data)

    def _normalize_selection_state(self) -> None:
        """Keep selections valid and default them to the first available option."""
        available_contour_ids = [(int(contour[0]), int(contour[1])) for contour in self.contours]
        if not available_contour_ids:
            self._selected_contour_id = None
        elif self._selected_contour_id not in available_contour_ids:
            self._selected_contour_id = available_contour_ids[0]

        available_zone_ids = [int(zone["id"]) for zone in self.zones]
        if not available_zone_ids:
            self._selected_zone_id = None
        elif self._selected_zone_id not in available_zone_ids:
            self._selected_zone_id = available_zone_ids[0]

        available_spot_area_ids = [int(spot_area["id"]) for spot_area in self.spot_areas]
        if not available_spot_area_ids:
            self._selected_spot_area_id = None
        elif self._selected_spot_area_id not in available_spot_area_ids:
            self._selected_spot_area_id = available_spot_area_ids[0]

        if self._selected_mowing_mode not in self.selectable_mowing_modes:
            self._selected_mowing_mode = MowingMode.ALL_AREA

    def _handle_device_update(self, property_name: str, value: Any) -> None:
        """Handle device property updates and notify Home Assistant."""
        if property_name == SETTINGS_CHANGED_PROPERTY_NAME:
            # The device announces that a setting changed without saying which,
            # so the settings are read back whenever it does.
            self.hass.create_task(self._async_refresh_settings_on_change())
        if property_name == PROPERTY_1_1_ACTIVE_CODES_NAME and self.supports_rain_protection:
            if RAIN_DEVICE_CODES & value:
                # Rain just took the mower off the lawn, so it now knows when it
                # may resume.
                self.hass.create_task(self._async_refresh_rain_protection_end())
        if property_name == STATUS_PROPERTY.name and int(value) == DeviceStatus.CHARGING:
            self.hass.create_task(self._async_refresh_consumables_on_charging())
        if property_name == CURRENT_MAP_ID_PROPERTY_NAME and self.supports_cutting_height:
            # The cutting height is stored per map, so it has to be re-read
            # whenever the active map changes.
            self.hass.create_task(self._async_refresh_cutting_height_on_map_change())
        self._normalize_selection_state()

        # Handle device code error notifications
        notify_options = self.entry.options.get(CONF_NOTIFY, [])
        if property_name == DEVICE_CODE_ERROR_PROPERTY_NAME and isinstance(value, dict):
            if NOTIFICATION_ERROR in notify_options:
                code = value[NOTIFICATION_CODE_FIELD]
                name = value[NOTIFICATION_NAME_FIELD]
                desc = value[NOTIFICATION_DESCRIPTION_FIELD]
                self.hass.create_task(self._notify(
                    f"dreame_mower_device_error_{code}",
                    f"\U0001f6a8 {self.device_name}: {name}",
                    f"**Description:** {desc}\n\n**Error Code:** {code}\n**Device:** {self.device_name} ({self.device_model}) — Firmware {self.device_firmware}",
                ))

        elif property_name == DEVICE_CODE_WARNING_PROPERTY_NAME and isinstance(value, dict):
            if NOTIFICATION_WARNING in notify_options:
                code = value[NOTIFICATION_CODE_FIELD]
                name = value[NOTIFICATION_NAME_FIELD]
                desc = value[NOTIFICATION_DESCRIPTION_FIELD]
                self.hass.create_task(self._notify(
                    f"dreame_mower_device_warning_{code}",
                    f"\u26a0\ufe0f {self.device_name}: {name}",
                    f"**Description:** {desc}\n\n**Warning Code:** {code}\n**Device:** {self.device_name} ({self.device_model}) — Firmware {self.device_firmware}",
                ))

        elif property_name == DEVICE_CODE_INFO_PROPERTY_NAME and isinstance(value, dict):
            if NOTIFICATION_INFORMATION in notify_options:
                code = value[NOTIFICATION_CODE_FIELD]
                name = value[NOTIFICATION_NAME_FIELD]
                desc = value[NOTIFICATION_DESCRIPTION_FIELD]
                self.hass.create_task(self._notify(
                    f"dreame_mower_device_info_{code}",
                    f"\u2139\ufe0f {self.device_name}: {name}",
                    f"**Description:** {desc}\n\n**Info Code:** {code}\n**Device:** {self.device_name} ({self.device_model}) — Firmware {self.device_firmware}",
                ))

        elif property_name == POWER_STATE_PROPERTY.name and value == 1:
            if NOTIFICATION_INFORMATION in notify_options:
                self.hass.create_task(self._notify(
                    "dreame_mower_device_info_power_off",
                    f"\u2139\ufe0f {self.device_name}: Mower Powered Off",
                    f"**Description:** The mower has been powered off\n\n**Device:** {self.device_name} ({self.device_model}) — Firmware {self.device_firmware}",
                ))
        
        
        # Schedule a coordinator update to notify all entities
        # Use async_set_updated_data to trigger entity updates
        self.hass.create_task(self._async_handle_device_update())
    
    async def _notify(self, notification_id: str, title: str, message: str) -> None:
        """Create a persistent notification in Home Assistant."""
        await self.hass.services.async_call(
            "persistent_notification", "create",
            {"notification_id": notification_id, "title": title, "message": message},
        )

    async def _async_refresh_cutting_height_on_map_change(self) -> None:
        """Re-read the cutting heights after the active map changed."""
        try:
            await self.async_fetch_cutting_heights()
        except Exception as ex:
            _LOGGER.warning("Cutting height refresh on map change failed: %s", ex)

    async def _async_refresh_rain_protection_end(self) -> None:
        """Re-read the rain protection end time after the mower reported rain."""
        try:
            await self.async_fetch_rain_protection_end()
        except Exception as ex:
            _LOGGER.warning("Rain protection end time refresh failed: %s", ex)

    async def _async_refresh_settings_on_change(self) -> None:
        """Re-read the settings after the device announced one of them changed."""
        if self._settings_write_was_ours():
            _LOGGER.debug("Ignoring the echo of a settings change this integration made")
            return

        try:
            await self.async_refresh_device_settings()
        except Exception as ex:
            _LOGGER.warning("Settings refresh on change failed: %s", ex)

    def _settings_write_was_ours(self) -> bool:
        """Return whether the integration wrote a setting a moment ago."""
        if self._last_settings_write is None:
            return False
        return (time.monotonic() - self._last_settings_write) < _SETTINGS_WRITE_ECHO_SECONDS

    def _note_settings_write(self) -> None:
        """Remember that the integration just wrote a setting."""
        self._last_settings_write = time.monotonic()

    async def _async_refresh_consumables_on_charging(self) -> None:
        """Fetch updated CMS counters when the device transitions to charging."""
        try:
            await self.async_fetch_consumable_data()
        except Exception as ex:
            _LOGGER.warning("Consumable refresh on charging failed: %s", ex)

    async def _async_handle_device_update(self) -> None:
        """Async handler for device updates."""
        try:
            # Get fresh data and update all entities
            data = await self._async_update_data()
            self.async_set_updated_data(data)
        except Exception as ex:
            _LOGGER.exception("Error handling device update: %s", ex)
    
    def register_property_callback(self, property_key: str, callback) -> None:
        """Register callback for property changes.
        
        Args:
            property_key: Property identifier for callback registration
            callback: Callback function to register
        """
        self.device.register_property_callback(callback)

    @property
    def consumable_values(self) -> list[int] | None:
        """Return cached CMS consumable counters: [blade_min, brush_min, robot_min]."""
        return self._consumable_values

    async def async_fetch_consumable_data(self) -> None:
        """Fetch CMS consumable counters from the device and cache them."""
        result = await self.device.get_consumable_status()
        self._consumable_values = result.get("values")
        # Push the refreshed counters to the health sensors immediately (e.g. so a
        # reset is reflected without waiting for the next coordinator update).
        self.async_update_listeners()

    async def async_fetch_firmware_status(self) -> None:
        """Fetch firmware update availability from the device."""
        await self.device.fetch_firmware_status()
        data = await self._async_update_data()
        self.async_set_updated_data(data)

    async def async_update_online_status(self) -> None:
        """Poll the cloud connectivity heartbeat to detect if the device is offline."""
        await self.device.async_update_online_status()

    async def async_connect_device(self) -> bool:
        return await self.device.connect()

    async def async_disconnect_device(self) -> None:
        """Disconnect from the device."""
        await self.device.disconnect()