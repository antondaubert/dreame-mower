"""DataUpdateCoordinator for Dreame Mower Integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
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
from .dreame.device import DreameMowerDevice, DreameSwbotDevice
from .dreame.map_scene import stripe_angle
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
    DEVICE_SETTINGS_HUMAN_PRESENCE_KEY,
    DEVICE_SETTINGS_LANGUAGE_KEY,
    DEVICE_SETTINGS_LIGHT_KEY,
    DEVICE_SETTINGS_VOICE_PROMPTS_KEY,
    DEVICE_SETTINGS_VOLUME_KEY,
    HUMAN_PRESENCE_INTERVALS_MINUTES,
    HUMAN_PRESENCE_MODES,
    HUMAN_PRESENCE_SENSITIVITIES,
    LIGHT_SCENES,
    VOICE_LANGUAGES,
    VOICE_PROMPTS,
    DEVICE_SETTINGS_STOP_POINT_KEY,
    DEVICE_SETTINGS_TIME_ZONE_KEY,
    STOP_POINT_DAYS_RANGE,
    MAP_SWITCH_ANNOUNCED_PROPERTY_NAME,
    SERVICE1_PROPERTY_50,
    EDGE_MOWING_AUTO_KEY,
    FIRMWARE_INSTALL_STATE_PROPERTY,
    FirmwareInstallState,
    POSE_COVERAGE_PROPERTY,
    POWER_STATE_PROPERTY,
    SERVICE1_PROPERTY_51,
    RAIN_DEVICE_CODES,
    SCHEDULING_SUMMARY_PROPERTY,
    DeviceStatus,
    MOWING_DIRECTION_ANGLE_KEY,
    MOWING_PREFERENCE_GLOBAL_AREA_ID,
    MowingPreferenceMode,
    STATUS_PROPERTY,
    supports_cutting_height,
)
from .dreame.device import CONSUMABLE_COUNTER_TOTAL_MINUTES
from .dreame.property.property_misc import (
    PROPERTY_1_1_TASK_STATUS_NAME,
    PROPERTY_1_1_ACTIVE_CODES_NAME,
    SETTINGS_CHANGED_PROPERTY_NAME,
)

# How long a change the integration made itself keeps the device from triggering
# a re-read. The device announces every change, including the ones it was just
# told to make, and a write already knows what it wrote.
_SETTINGS_WRITE_ECHO_SECONDS = 5.0
# The map list is read back a moment after a switch is announced, once the
# mower has applied it.
_MAP_SWITCH_READ_BACK_DELAY_SECONDS = 2.0

# The two records the device announces changes to, each with its own echo window
# so a write to one does not suppress a re-read of the other.
_WRITE_DEVICE_SETTINGS = "device_settings"
_WRITE_MOWING_PREFERENCES = "mowing_preferences"

def zone_settings(coordinator: DreameMowerCoordinator) -> list[dict[str, Any]]:
    """The stripe angle and cutting height each zone of the active map is mowed with.

    A map that applies one record to all its zones gives every zone the
    map-wide values; otherwise each zone keeps its own.
    """
    per_zone = coordinator.mowing_preference_mode == MowingPreferenceMode.PER_ZONE
    map_direction = coordinator.mowing_direction
    map_height = coordinator.cutting_height
    zone_directions = coordinator.zone_mowing_directions
    zone_heights = coordinator.zone_cutting_heights
    settings = []
    for zone in coordinator.zones:
        zone_id = int(zone["id"])
        direction = zone_directions.get(zone_id) if per_zone else map_direction
        height = zone_heights.get(zone_id) if per_zone else map_height
        settings.append(
            {
                "id": zone_id,
                "stripe_angle": stripe_angle(direction[MOWING_DIRECTION_ANGLE_KEY] if direction else None),
                "height": height,
            }
        )
    return settings


# While the mower drives, the device only keeps reporting its position and
# trail when it is asked for them now and then.
POSE_COVERAGE_REQUEST_INTERVAL = timedelta(seconds=120)
# The station states of a mower on its way home.
_DRIVING_HOME = frozenset({"pause_docking", "finish_docking", "docking_in_base"})

# The kind of task the heartbeat's work mode stands for while the mower mows.
_SESSION_TASK_MODES = {0: "all_area", 1: "edge", 2: "zone", 3: "spot", 7: "patrol", 8: "patrol", 9: "patrol"}

_LOGGER = logging.getLogger(__name__)

class DreameMowerCoordinator(DataUpdateCoordinator[None]):
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
        self._consumable_values: list[int] | None = None
        self._charging_settings: dict[str, Any] | None = None
        self._rain_settings: dict[str, Any] | None = None
        self._anti_theft_settings: dict[str, Any] | None = None
        # The whole settings record as the mower last reported it, by key.
        self._device_settings: dict[str, Any] | None = None
        self._rain_protection_end_timestamp: int | None = None
        self._last_writes: dict[str, float] = {}
        self._map_switch_read_pending = False
        self._preference_refresh: asyncio.Task[bool] | None = None
        self._pose_keepalive: Callable[[], None] | None = None
        self._trail_read: asyncio.Task[None] | None = None
        # Entities that exist only for settings the mower turns out to offer
        # wait for the reads that tell.
        self._probed = False
        self._probe_cancelled = False
        self._probe_waiters: list[Callable[[], None]] = []
        # Set when setup skipped the reads of an offline mower: the entry is
        # set up again once the mower is back.
        self.reload_when_online = False
        # Called when the entry unloads, e.g. to tell open map cards.
        self.shutdown_callbacks: list[Callable[[], None]] = []
        # The running mowing session: when it became active and what kind of
        # task it runs, kept while the mower charges in between.
        self._session_started: datetime | None = None
        self._session_task_mode: str | None = None

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

    async def _async_update_data(self) -> None:
        """Nothing to fetch: the device pushes its state, and entities read it from here."""

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
    def supports_start_from_stop_point(self) -> bool:
        """Return whether a new task can be told to go on from where an unfinished one stopped.

        Dreame mowers take it with the start; others resume in their own way.
        """
        return self.device_type != DEVICE_TYPE_SWBOT and self.device_model.startswith("dreame.mower.")

    @property
    def device_serial(self) -> str:
        """Return device serial number from config entry."""
        return self.entry.data[CONF_SERIAL]

    @property
    def account_username(self) -> str:
        """Return the account the device is reached through, from config entry."""
        return self.entry.data[CONF_USERNAME]

    @property
    def account_type(self) -> str:
        """Return which cloud the account belongs to ('dreame' or 'mova')."""
        return self.entry.data[CONF_ACCOUNT_TYPE]

    @property
    def account_country(self) -> str:
        """Return the country the account is registered in, from config entry."""
        return self.entry.data[CONF_COUNTRY]

    @property
    def device_firmware(self) -> str:
        """Return device firmware version."""
        return self.device.firmware

    @property
    def device_latest_firmware(self) -> str | None:
        """Return the latest available firmware version, if any."""
        return self.device.firmware_latest_version

    @property
    def device_firmware_release_notes(self) -> str | None:
        """Return the release notes of the available firmware, if any."""
        return self.device.firmware_release_notes

    @property
    def device_firmware_status_checked(self) -> bool:
        """Return whether firmware update availability is known yet."""
        return self.device.firmware_status_checked

    @property
    def device_firmware_update_in_progress(self) -> bool:
        """Return whether the mower is downloading or installing a firmware update."""
        return self.device.firmware_update_in_progress

    @property
    def device_firmware_update_percentage(self) -> int | None:
        """Return how far a running firmware update has come, in percent."""
        return self.device.firmware_update_percentage

    @property
    def device_manufacturer(self) -> str:
        """Return device manufacturer."""
        return "Dreametech™"

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
    def zones(self) -> list[dict]:
        """Return available mowing zones (id, name, area) from vector map."""
        return self.device.zones

    @property
    def contours(self) -> list[list[int]]:
        """Return available edge-mowing contour IDs from vector map."""
        return self.device.contours

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

    async def async_fetch_zone_cutting_heights(self) -> dict[int, float]:
        """Read the current map's per-zone cutting heights from the device."""
        zone_heights = await self.device.refresh_zone_cutting_heights()
        self.async_update_listeners()
        return zone_heights

    async def async_set_cutting_height(
        self,
        height_cm: float,
        map_id: int | None = None,
        zone_id: int | None = None,
    ) -> bool:
        """Set a cutting height, defaulting to the current map and its map-wide record."""
        self._note_write(_WRITE_MOWING_PREFERENCES)
        updated = await self.device.set_cutting_height(height_cm, map_id, zone_id)
        self.async_update_listeners()
        return updated

    async def async_set_mowing_preference_mode(
        self,
        mode: MowingPreferenceMode,
        map_id: int | None = None,
    ) -> bool:
        """Choose whether a map follows its map-wide or its per-zone preferences."""
        self._note_write(_WRITE_MOWING_PREFERENCES)
        updated = await self.device.set_mowing_preference_mode(mode, map_id)
        self.async_update_listeners()
        return updated

    @property
    def supports_edge_mowing_settings(self) -> bool:
        """Return whether the device reported edge mowing settings."""
        return self.device.edge_mowing_settings is not None

    @property
    def mowing_direction(self) -> dict[str, int] | None:
        """Return the current map's mowing direction, if it is known."""
        return self.device.mowing_direction

    @property
    def zone_mowing_directions(self) -> dict[int, dict[str, int]]:
        """Return the per-zone mowing directions known for the current map."""
        return self.device.zone_mowing_directions

    @property
    def edge_mowing_auto(self) -> bool | None:
        """Return whether the mower mows the edges on its own, if it is known."""
        return self._edge_mowing_setting(EDGE_MOWING_AUTO_KEY)

    def _edge_mowing_setting(self, key: str) -> bool | None:
        """Return one edge mowing setting of the current map, if it is known."""
        settings = self.device.edge_mowing_settings
        if settings is None:
            return None
        return settings.get(key)

    async def async_fetch_mowing_preferences(self, *, after_change: bool = False) -> bool:
        """Read the current map's map-wide and per-zone mowing settings.

        The settings all live in the same records, so the cutting heights and the
        edge mowing settings come out of a single read each.

        A caller that asks while a read is already running joins that read rather
        than repeating it: the device answers one command at a time, so a second
        read of the same records would only make everything wait for it. A read
        that follows a change the device announced is the exception — it has to
        start after the announcement to be sure of seeing the change, so it waits
        the running read out and then takes its own.
        """
        refresh = self._preference_refresh
        if after_change and refresh is not None and not refresh.done():
            await asyncio.gather(refresh, return_exceptions=True)
            refresh = None

        if refresh is None or refresh.done():
            refresh = self.hass.async_create_task(self._async_read_mowing_preferences())
            self._preference_refresh = refresh

        return await refresh

    async def _async_read_mowing_preferences(self) -> bool:
        """Read every mowing preference record of the current map."""
        read = await self.device.refresh_mowing_preferences()
        await self.device.refresh_zone_mowing_preferences()
        self.async_update_listeners()
        return read

    @property
    def schedule_slots(self) -> list[int]:
        """Return the schedule slots the current map holds."""
        schedules = self.device.schedules
        return [] if schedules is None else [int(schedule["slot"]) for schedule in schedules]

    def schedule(self, slot: int) -> dict[str, Any] | None:
        """Return one schedule slot of the current map, if it is known."""
        for schedule in self.device.schedules or []:
            if int(schedule["slot"]) == slot:
                return schedule
        return None

    def schedule_enabled(self, slot: int) -> bool | None:
        """Return whether one schedule slot of the current map is on, if it is known."""
        schedule = self.schedule(slot)
        return None if schedule is None else bool(schedule["enabled"])

    async def async_fetch_schedules(self, *, changed_only: bool = False) -> bool:
        """Read the current map's schedule slots from the device.

        A poll only asks for the version the mower holds them under and reads the
        slots back when that moved; a full read is what decides whether the device
        offers schedules at all.
        """
        if changed_only:
            schedules = await self.device.refresh_changed_schedules()
        else:
            schedules = await self.device.refresh_schedules()

        self.async_update_listeners()
        return schedules is not None

    async def async_set_schedule_enabled(self, slot: int, enabled: bool) -> bool:
        """Switch one schedule slot of the current map on or off."""
        schedules = await self.device.set_schedule_enabled(slot, enabled)
        self.async_update_listeners()
        return schedules is not None

    @property
    def mowing_settings(self) -> dict[int, dict[str, Any]]:
        """Return every setting of the current map's records, by area id."""
        return self.device.mowing_settings

    def map_mowing_setting(self, key: str) -> Any:
        """Return one setting of the current map's map-wide record, if it is known."""
        return self.device.mowing_settings.get(MOWING_PREFERENCE_GLOBAL_AREA_ID, {}).get(key)

    def supports_mowing_setting(self, key: str) -> bool:
        """Return whether the current map's map-wide record carries a setting."""
        return key in self.device.mowing_settings.get(MOWING_PREFERENCE_GLOBAL_AREA_ID, {})

    async def async_set_mowing_settings(
        self,
        settings: dict[str, Any],
        map_id: int | None = None,
        zone_id: int | None = None,
    ) -> bool:
        """Change any of the mowing settings at once, keeping the others as they are."""
        self._note_write(_WRITE_MOWING_PREFERENCES)
        updated = await self.device.set_mowing_settings(settings, map_id=map_id, zone_id=zone_id)
        self.async_update_listeners()
        return updated

    async def async_set_edge_mowing_settings(
        self,
        auto: bool | None = None,
        blade_offset: bool | None = None,
        safe: bool | None = None,
        map_id: int | None = None,
        zone_id: int | None = None,
    ) -> bool:
        """Switch edge mowing settings, keeping every unspecified one as it is."""
        self._note_write(_WRITE_MOWING_PREFERENCES)
        updated = await self.device.set_edge_mowing_settings(
            auto=auto,
            blade_offset=blade_offset,
            safe=safe,
            map_id=map_id,
            zone_id=zone_id,
        )
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

    async def async_set_charging_period(
        self,
        enabled: bool | None = None,
        start_minutes: int | None = None,
        end_minutes: int | None = None,
    ) -> bool:
        """Update the custom charging period, keeping every unspecified part as is."""
        self._note_write(_WRITE_DEVICE_SETTINGS)
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

    @property
    def link_module_installed(self) -> bool | None:
        """Return whether the mower has a cellular module fitted, if it is known."""
        return self.device.link_module_installed

    @property
    def link_module_plan_valid(self) -> bool | None:
        """Return whether the cellular module's data plan is valid, if it is known."""
        return self.device.link_module_plan_valid

    @property
    def supports_anti_theft(self) -> bool:
        """Return whether the device reported anti-theft settings."""
        return self._anti_theft_settings is not None

    @property
    def supports_anti_theft_pin_check(self) -> bool:
        """Return whether the device asks for a PIN code before it is switched off."""
        return (
            self._anti_theft_settings is not None
            and self._anti_theft_settings["pin_check_enabled"] is not None
        )

    @property
    def lift_alarm_enabled(self) -> bool | None:
        """Return whether the alarm goes off when the mower is lifted, if it is known."""
        if self._anti_theft_settings is None:
            return None
        return bool(self._anti_theft_settings["lift_alarm_enabled"])

    @property
    def off_map_alarm_enabled(self) -> bool | None:
        """Return whether the alarm goes off when the mower leaves the map, if it is known."""
        if self._anti_theft_settings is None:
            return None
        return bool(self._anti_theft_settings["off_map_alarm_enabled"])

    @property
    def location_reporting_enabled(self) -> bool | None:
        """Return whether the mower reports its position, if it is known."""
        if self._anti_theft_settings is None:
            return None
        return bool(self._anti_theft_settings["location_reporting_enabled"])

    @property
    def anti_theft_pin_check_enabled(self) -> bool | None:
        """Return whether the mower asks for its PIN code before it is switched off."""
        if self._anti_theft_settings is None:
            return None
        pin_check_enabled = self._anti_theft_settings["pin_check_enabled"]
        return None if pin_check_enabled is None else bool(pin_check_enabled)

    async def async_set_anti_theft_settings(
        self,
        lift_alarm: bool | None = None,
        off_map_alarm: bool | None = None,
        location_reporting: bool | None = None,
        pin_check: bool | None = None,
    ) -> bool:
        """Update the anti-theft settings, keeping every unspecified switch as is."""
        self._note_write(_WRITE_DEVICE_SETTINGS)
        settings = await self.device.set_anti_theft_settings(
            lift_alarm=lift_alarm,
            off_map_alarm=off_map_alarm,
            location_reporting=location_reporting,
            pin_check=pin_check,
        )
        if settings is None:
            return False

        # The record the mower answers with is what it now holds, whether or not
        # it took the change, so it is kept either way. A mower that answers
        # with the old value has refused the write, and saying so is the only
        # way the switch does not report a change that never happened.
        self._anti_theft_settings = settings
        self.async_update_listeners()

        for key, requested in (
            ("lift_alarm_enabled", lift_alarm),
            ("off_map_alarm_enabled", off_map_alarm),
            ("location_reporting_enabled", location_reporting),
            ("pin_check_enabled", pin_check),
        ):
            if requested is None:
                continue
            if bool(settings[key]) != bool(requested):
                _LOGGER.warning(
                    "The mower did not apply %s: asked for %s, it reports %s",
                    key,
                    requested,
                    settings[key],
                )
                return False

        return True

    async def async_fetch_device_settings(self) -> None:
        """Read the settings record and everything that hangs off it.

        The charging, rain and anti-theft settings share one record, so one read
        serves them all, and it doubles as the probe that decides which of them
        the device offers at all. The time rain protection lets the mower work
        again is kept outside the record, so it is read after it and only when
        the device turns out to have rain protection.
        """
        await self.async_refresh_device_settings()

        if not self.supports_rain_protection:
            # A device with no rain settings has no protection that could expire.
            return

        await self.async_fetch_rain_protection_end()

    async def async_refresh_device_settings(self) -> None:
        """Re-read every setting the integration keeps from the device.

        The settings all live in one record, so the charging, rain and anti-theft
        settings come out of a single read.
        """
        settings = await self.device.get_device_settings()
        if settings is None:
            return

        self._device_settings = dict(settings)
        charging_settings = self.device.decode_charging_settings(settings)
        if charging_settings is not None:
            self._charging_settings = charging_settings

        rain_settings = self.device.decode_rain_settings(settings)
        if rain_settings is not None:
            self._rain_settings = rain_settings

        anti_theft_settings = self.device.decode_anti_theft_settings(settings)
        if anti_theft_settings is not None:
            self._anti_theft_settings = anti_theft_settings

        self.async_update_listeners()

    def supports_device_setting(self, key: str) -> bool:
        """Return whether the mower's settings record carries a setting as a
        single value, the form an on/off or choice setting takes.

        Some models keep a setting of the same key in another form; it is not
        offered rather than misread.
        """
        value = None if self._device_settings is None else self._device_settings.get(key)
        return isinstance(value, (bool, int))

    def device_setting(self, key: str) -> Any:
        """Return one setting of the mower's settings record as it reported it, if known."""
        return None if self._device_settings is None else self._device_settings.get(key)

    def time_window_setting(self, key: str) -> dict[str, Any] | None:
        """Return a setting with a time window, {enabled, start, end} in minutes
        after midnight, or None when the record does not carry it so."""
        value = self.device_setting(key)
        if not (isinstance(value, list) and len(value) >= 3 and all(isinstance(part, (bool, int)) for part in value[:3])):
            return None
        return {"enabled": bool(value[0]), "start": int(value[1]), "end": int(value[2])}

    async def async_set_time_window_setting(
        self, key: str, enabled: bool | None = None, start: int | None = None, end: int | None = None
    ) -> bool:
        """Change a setting with a time window, keeping what is left out as it is."""
        current = self.time_window_setting(key)
        if current is None:
            raise ValueError(f"This mower does not offer the {key} setting")
        on = current["enabled"] if enabled is None else bool(enabled)
        begin = current["start"] if start is None else int(start)
        finish = current["end"] if end is None else int(end)
        for minutes in (begin, finish):
            # The mower takes 00:01 to 23:59; midnight itself is not a time it keeps.
            if not 0 < minutes < 24 * 60:
                raise ValueError("A window starts and ends between 00:01 and 23:59")
        if begin == finish:
            raise ValueError("The window has to start and end at different times")
        return await self.async_set_device_setting(key, {"value": int(on), "time": [begin, finish]}, [int(on), begin, finish])

    @property
    def stop_point_setting(self) -> dict[str, Any] | None:
        """Return whether a task may go on from a stop point, and for how many days one is kept."""
        value = self.device_setting(DEVICE_SETTINGS_STOP_POINT_KEY)
        if not (isinstance(value, list) and len(value) >= 2 and all(isinstance(part, (bool, int)) for part in value[:2])):
            return None
        return {"enabled": bool(value[0]), "days": int(value[1])}

    async def async_set_stop_point_setting(self, enabled: bool | None = None, days: int | None = None) -> bool:
        """Change the stop point setting, keeping what is left out as it is.

        Switching it off clears the stop points the mower holds.
        """
        current = self.stop_point_setting
        if current is None:
            raise ValueError("This mower does not keep stop points")
        on = current["enabled"] if enabled is None else bool(enabled)
        keep = current["days"] if days is None else int(days)
        low, high = STOP_POINT_DAYS_RANGE
        if not low <= keep <= high:
            raise ValueError(f"A stop point is kept {low} to {high} days")
        updated = await self.async_set_device_setting(DEVICE_SETTINGS_STOP_POINT_KEY, {"on": on, "day": keep}, [int(on), keep])
        if updated:
            # The mower drops its stop points when the setting goes off.
            try:
                if await self.hass.async_add_executor_job(self.device.refresh_stop_points):
                    self.async_update_listeners()
            except Exception as ex:
                _LOGGER.debug("Reading the stop points back failed: %s", ex)
        return updated

    def _int_record(self, key: str, length: int) -> list[int] | None:
        """A record of at least `length` numbers, as integers, or None."""
        value = self.device_setting(key)
        if not (isinstance(value, list) and len(value) >= length and all(isinstance(part, (bool, int)) for part in value)):
            return None
        return [int(part) for part in value]

    @property
    def light_setting(self) -> dict[str, Any] | None:
        """Return the lights: whether they keep to a custom period, its window
        in minutes, and in which states they are on."""
        record = self._int_record(DEVICE_SETTINGS_LIGHT_KEY, 7)
        if record is None:
            return None
        setting: dict[str, Any] = {"custom_period": bool(record[0]), "start": record[1], "end": record[2]}
        setting.update({scene: bool(record[3 + index]) for index, scene in enumerate(LIGHT_SCENES)})
        return setting

    async def async_set_light_setting(self, **changes: Any) -> bool:
        """Change the lights, keeping what is left out as it is."""
        record = self._int_record(DEVICE_SETTINGS_LIGHT_KEY, 7)
        current = self.light_setting
        if record is None or current is None:
            raise ValueError("This mower does not offer light settings")
        setting = {**current, **{key: value for key, value in changes.items() if value is not None}}
        start, end = int(setting["start"]), int(setting["end"])
        # Only a period being changed is checked, so an odd stored one does not
        # block switching a light state.
        changing_period = changes.get("start") is not None or changes.get("end") is not None
        if changing_period and (not (0 <= start <= 24 * 60 and 0 <= end <= 24 * 60) or start == end):
            raise ValueError("The light period starts and ends at different times between 00:00 and 24:00")
        scenes = [int(bool(setting[scene])) for scene in LIGHT_SCENES]
        data: dict[str, Any] = {"value": int(bool(setting["custom_period"])), "time": [start, end], "light": scenes}
        new_record = [data["value"], start, end, *scenes, *record[7:]]
        if len(record) > 7:
            # The fill light, which this setting leaves as it is.
            data["fill"] = record[7]
        return await self.async_set_device_setting(DEVICE_SETTINGS_LIGHT_KEY, data, new_record)

    @property
    def human_presence_setting(self) -> dict[str, Any] | None:
        """Return the human presence alert: whether it is on, how sensitive,
        when it watches, how it reports and how often it alerts."""
        record = self._int_record(DEVICE_SETTINGS_HUMAN_PRESENCE_KEY, 8)
        if record is None:
            return None
        sensitivity = HUMAN_PRESENCE_SENSITIVITIES[record[1]] if 0 <= record[1] < len(HUMAN_PRESENCE_SENSITIVITIES) else None
        setting: dict[str, Any] = {"enabled": bool(record[0]), "sensitivity": sensitivity}
        setting.update({mode: bool(record[2 + index]) for index, mode in enumerate(HUMAN_PRESENCE_MODES)})
        setting.update(voice=bool(record[6]), photo=bool(record[7]), interval=record[8] if len(record) > 8 else None)
        return setting

    async def async_set_human_presence_setting(self, **changes: Any) -> bool:
        """Change the human presence alert, keeping what is left out as it is."""
        record = self._int_record(DEVICE_SETTINGS_HUMAN_PRESENCE_KEY, 8)
        current = self.human_presence_setting
        if record is None or current is None:
            raise ValueError("This mower does not offer a human presence alert")
        setting = {**current, **{key: value for key, value in changes.items() if value is not None}}
        # Only what is being changed is checked; a value left out is written
        # back as the mower holds it.
        sensitivity = record[1]
        if changes.get("sensitivity") is not None:
            if changes["sensitivity"] not in HUMAN_PRESENCE_SENSITIVITIES:
                raise ValueError(f"The sensitivity is one of {', '.join(HUMAN_PRESENCE_SENSITIVITIES)}")
            sensitivity = HUMAN_PRESENCE_SENSITIVITIES.index(changes["sensitivity"])
        report = [int(bool(setting["voice"])), int(bool(setting["photo"]))]
        if len(record) > 8:
            interval = record[8]
            if changes.get("interval") is not None:
                if int(changes["interval"]) not in HUMAN_PRESENCE_INTERVALS_MINUTES:
                    raise ValueError(f"The alert repeats every {', '.join(map(str, HUMAN_PRESENCE_INTERVALS_MINUTES))} minutes")
                interval = int(changes["interval"])
            report.append(interval)
        elif changes.get("interval") is not None:
            raise ValueError("This mower does not space its alerts")
        modes = [int(bool(setting[mode])) for mode in HUMAN_PRESENCE_MODES]
        data = {"value": int(bool(setting["enabled"])), "sen": sensitivity, "mode": modes, "report": report}
        new_record = [data["value"], sensitivity, *modes, *report, *record[2 + len(modes) + len(report):]]
        return await self.async_set_device_setting(DEVICE_SETTINGS_HUMAN_PRESENCE_KEY, data, new_record)

    @property
    def robot_voice_setting(self) -> dict[str, Any] | None:
        """Return the robot's voice: its volume, the prompts it speaks and its language."""
        volume = self.device_setting(DEVICE_SETTINGS_VOLUME_KEY)
        prompts = self._int_record(DEVICE_SETTINGS_VOICE_PROMPTS_KEY, 4)
        language = self._int_record(DEVICE_SETTINGS_LANGUAGE_KEY, 2)
        if not isinstance(volume, int) and prompts is None:
            return None
        return {
            "volume": volume if isinstance(volume, int) and not isinstance(volume, bool) else None,
            "prompts": None if prompts is None else {kind: bool(prompts[index]) for index, kind in enumerate(VOICE_PROMPTS)},
            "language": VOICE_LANGUAGES[language[1]] if language is not None and 0 <= language[1] < len(VOICE_LANGUAGES) else None,
        }

    async def async_set_robot_voice(self, volume: int | None = None, **prompts: bool | None) -> bool:
        """Change the robot's volume or the prompts it speaks, keeping the rest as it is."""
        changed = {kind: value for kind, value in prompts.items() if value is not None}
        record = self._int_record(DEVICE_SETTINGS_VOICE_PROMPTS_KEY, 4)
        # Both are checked before anything is written, so a call is never half applied.
        if volume is not None:
            if not isinstance((voice := self.robot_voice_setting), dict) or voice["volume"] is None:
                raise ValueError("This mower does not offer a volume setting")
            if not 0 <= int(volume) <= 100:
                raise ValueError("The volume runs from 0 to 100")
        if changed and record is None:
            raise ValueError("This mower does not offer voice prompt settings")
        updated = True
        if volume is not None:
            updated = await self.async_set_device_setting(DEVICE_SETTINGS_VOLUME_KEY, {"value": int(volume)})
        if changed and updated and record is not None:
            value = [int(bool(changed.get(kind, record[index]))) for index, kind in enumerate(VOICE_PROMPTS)]
            updated = await self.async_set_device_setting(DEVICE_SETTINGS_VOICE_PROMPTS_KEY, {"value": value}, value)
        return updated

    @property
    def time_zone(self) -> str | None:
        """Return the mower's time zone, if it is known."""
        value = self.device_setting(DEVICE_SETTINGS_TIME_ZONE_KEY)
        return value if isinstance(value, str) and value else None

    async def async_set_device_setting(self, key: str, data: dict[str, Any], record: Any = None) -> bool:
        """Write one setting of the settings record, then read the record back.

        `record` is what the record holds for the key once the write took;
        left out, the setting is a single value written as {"value": …}.
        False when the mower refused the write or answered with another single
        value than the one asked for. The written value stands even when
        reading the record back fails.
        """
        self._note_write(_WRITE_DEVICE_SETTINGS)
        answer = await self.device.set_device_setting(key, data)
        if answer is None:
            return False
        asked, answered = data.get("value"), answer.get("value")
        scalar = (bool, int)
        if isinstance(answered, list) and answered and isinstance(answered[0], scalar):
            # Some settings answer with the whole record, its first part being on/off.
            answered = answered[0]
        if isinstance(asked, scalar) and isinstance(answered, scalar) and int(answered) != int(asked):
            _LOGGER.warning("The mower kept %s at %s instead of %s", key, answered, asked)
            return False
        if record is None and isinstance(asked, scalar):
            record = answered if isinstance(answered, scalar) else asked
        if self._device_settings is not None and record is not None:
            self._device_settings[key] = record
            self.async_update_listeners()
        try:
            await self.async_refresh_device_settings()
        except Exception as ex:
            _LOGGER.debug("Reading the settings back after writing %s failed: %s", key, ex)
        return True

    async def async_set_rain_protection(
        self,
        enabled: bool | None = None,
        delay_hours: int | None = None,
    ) -> bool:
        """Update rain protection, keeping every unspecified part as is."""
        self._note_write(_WRITE_DEVICE_SETTINGS)
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

    async def async_go_to_maintenance_point(self, point_id: int) -> bool:
        """Send the mower to a maintenance point of the active map."""
        return await self.device.go_to_maintenance_point([point_id])

    def _handle_device_update(self, property_name: str, value: Any) -> None:
        """Handle device property updates and notify Home Assistant."""
        self._follow_session()
        if property_name == SETTINGS_CHANGED_PROPERTY_NAME:
            # The device announces that a setting changed without saying which,
            # so the settings are read back whenever it does.
            self.hass.create_task(self._async_refresh_settings_on_change())
        if property_name == SCHEDULING_SUMMARY_PROPERTY.name:
            # The device announces a changed mowing preference on this property,
            # again without saying which map or setting changed, so the records
            # are read back whenever it reports here.
            self.hass.create_task(self._async_refresh_preferences_on_change())
        if property_name == PROPERTY_1_1_ACTIVE_CODES_NAME and self.supports_rain_protection:
            if RAIN_DEVICE_CODES & value:
                # Rain just took the mower off the lawn, so it now knows when it
                # may resume.
                self.hass.create_task(self._async_refresh_rain_protection_end())
        if property_name == STATUS_PROPERTY.name and int(value) == DeviceStatus.CHARGING:
            self.hass.create_task(self._async_refresh_consumables_on_charging())
        if (
            property_name == FIRMWARE_INSTALL_STATE_PROPERTY.name
            and value == FirmwareInstallState.UPGRADE_SUCCESS
        ):
            # The installed version and whether anything newer is left both
            # change with a finished update, and neither is announced.
            self.hass.create_task(self._async_refresh_firmware_after_update())
        if property_name == CURRENT_MAP_ID_PROPERTY_NAME:
            # The mowing settings are stored per map, so they have to be re-read
            # whenever the active map changes.
            self.hass.create_task(self._async_refresh_preferences_on_map_change())
        if property_name == "online" and value and self.reload_when_online:
            self.reload_when_online = False
            _LOGGER.info("%s is back online; setting it up again", self.device_name)
            self.hass.add_job(self.hass.config_entries.async_schedule_reload, self.entry.entry_id)
        if property_name == SERVICE1_PROPERTY_51.name:
            # The mower sends 1:51 as a session starts; the station's position
            # is read again then.
            self.hass.create_task(self.async_refresh_map_extras(obstacles=False))
        if property_name == PROPERTY_1_1_TASK_STATUS_NAME and self.device.mowing_session_active:
            # The position reports carry only the newest points of the trail;
            # what came before (a session already running when Home Assistant
            # started) is read back from the mower.
            self.hass.add_job(self._async_schedule_trail_read)
        if property_name in (CURRENT_MAP_ID_PROPERTY_NAME, PROPERTY_1_1_TASK_STATUS_NAME):
            # The obstacles are kept per map and change while mowing.
            self.hass.create_task(self.async_refresh_map_extras(dock=False))
        if property_name in (MAP_SWITCH_ANNOUNCED_PROPERTY_NAME, SERVICE1_PROPERTY_50.name):
            # Neither the echo of a switch nor the session marker (1:50) that
            # comes with it says which map is now active, so the map list is
            # read back for it. The echo does not always arrive; the marker
            # comes with every switch. Both come within a second of each
            # other, so one read covers them.
            if not self._map_switch_read_pending:
                self._map_switch_read_pending = True
                self.hass.create_task(self._async_refresh_current_map_on_switch())

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

    async def _async_refresh_current_map_on_switch(self) -> None:
        """Re-read the active map after the mower announced a map switch."""
        await asyncio.sleep(_MAP_SWITCH_READ_BACK_DELAY_SECONDS)
        self._map_switch_read_pending = False
        try:
            await self.hass.async_add_executor_job(self.device.refresh_current_map_id)
        except Exception as ex:
            _LOGGER.warning("Active map refresh after a map switch failed: %s", ex)

    async def _async_refresh_preferences_on_map_change(self) -> None:
        """Re-read the mowing settings after the active map changed."""
        if not self.device_online:
            # An offline mower cannot answer; it is read again once it is back.
            return
        try:
            await self.async_fetch_mowing_preferences()
        except Exception as ex:
            _LOGGER.warning("Mowing preference refresh on map change failed: %s", ex)

        # The schedules are stored per map as well, so the new map's slots are
        # what the switches now stand for.
        try:
            await self.async_fetch_schedules()
        except Exception as ex:
            _LOGGER.warning("Schedule refresh on map change failed: %s", ex)

    async def _async_refresh_rain_protection_end(self) -> None:
        """Re-read the rain protection end time after the mower reported rain."""
        try:
            await self.async_fetch_rain_protection_end()
        except Exception as ex:
            _LOGGER.warning("Rain protection end time refresh failed: %s", ex)

    async def _async_refresh_preferences_on_change(self) -> None:
        """Re-read the mowing settings after the device announced one changed."""
        if self._write_was_ours(_WRITE_MOWING_PREFERENCES):
            _LOGGER.debug("Ignoring the echo of a mowing preference change this integration made")
            return

        if self.current_map_id is None:
            # Without a map there is no record to address the read at.
            return

        try:
            await self.async_fetch_mowing_preferences(after_change=True)
        except Exception as ex:
            _LOGGER.warning("Mowing preference refresh on change failed: %s", ex)

    async def _async_refresh_settings_on_change(self) -> None:
        """Re-read the settings after the device announced one of them changed."""
        if self._write_was_ours(_WRITE_DEVICE_SETTINGS):
            _LOGGER.debug("Ignoring the echo of a settings change this integration made")
            return

        try:
            await self.async_refresh_device_settings()
        except Exception as ex:
            _LOGGER.warning("Settings refresh on change failed: %s", ex)

    def _write_was_ours(self, record: str) -> bool:
        """Return whether the integration wrote to a record a moment ago."""
        last_write = self._last_writes.get(record)
        if last_write is None:
            return False
        return (time.monotonic() - last_write) < _SETTINGS_WRITE_ECHO_SECONDS

    def _note_write(self, record: str) -> None:
        """Remember that the integration just wrote to a record."""
        self._last_writes[record] = time.monotonic()

    async def _async_refresh_consumables_on_charging(self) -> None:
        """Fetch updated CMS counters when the device transitions to charging."""
        try:
            await self.async_fetch_consumable_data()
        except Exception as ex:
            _LOGGER.warning("Consumable refresh on charging failed: %s", ex)

    async def _async_refresh_firmware_after_update(self) -> None:
        """Re-check the firmware versions once the mower finished an update."""
        try:
            await self.async_fetch_firmware_status()
        except Exception as ex:
            _LOGGER.warning("Firmware status refresh after update failed: %s", ex)

    @callback
    def async_update_pose_keepalive(self) -> None:
        """Ask for the mower's position now and then while it drives.

        That is while a session runs, and outside one while the mower drives
        home or finds its position. The live map follows the mowing task, not
        the dock: a session paused at the station keeps it running.
        """
        robot = self.device.robot_state or {}
        active = self.device_type != DEVICE_TYPE_SWBOT and (
            self.device.mowing_session_active
            or (
                self.device_online
                and (robot.get("docking") in _DRIVING_HOME or robot.get("location") == "relocating")
            )
        )
        if active and self._pose_keepalive is None:
            self._pose_keepalive = async_track_time_interval(
                self.hass,
                self._async_request_pose_coverage,
                POSE_COVERAGE_REQUEST_INTERVAL,
                cancel_on_shutdown=True,
            )
            self.hass.async_create_task(self._async_request_pose_coverage())
        elif not active:
            self.async_stop_pose_keepalive()

    @callback
    def async_stop_pose_keepalive(self) -> None:
        """Stop asking for the mower's position."""
        if self._pose_keepalive is not None:
            self._pose_keepalive()
            self._pose_keepalive = None

    def _follow_session(self) -> None:
        """Note when a mowing session starts and what kind of task it runs.

        The heartbeat names the task only while the mower mows; the kind
        stays known while it charges or pauses in between. The session ends,
        and both are forgotten, once the task status leaves it.
        """
        device = self.device
        if not device.mowing_session_active:
            self._session_started = None
            self._session_task_mode = None
            return
        if self._session_started is None:
            self._session_started = dt_util.utcnow()
        work_mode = (device.robot_state or {}).get("work_mode")
        mode = _SESSION_TASK_MODES.get(work_mode) if isinstance(work_mode, int) else None
        if mode is not None:
            self._session_task_mode = mode

    @property
    def session_task_mode(self) -> str | None:
        """The kind of task the running session mows (all_area, edge, zone, spot or patrol), if known."""
        self._follow_session()
        return self._session_task_mode

    @property
    def session_minutes(self) -> int | None:
        """How many minutes the running session has been going, None without one.

        Counted from when the session was first seen active, so a session that
        was already running when Home Assistant started counts from then.
        """
        self._follow_session()
        if self._session_started is None:
            return None
        return int((dt_util.utcnow() - self._session_started).total_seconds() // 60)

    async def _async_request_pose_coverage(self, now: datetime | None = None) -> None:
        """Ask the device for the mower's position, which keeps the reports coming.

        The obstacles are read again too: the mower drops one it found gone
        when it passed by again, and announces only the ones it adds.
        """
        if not self.device_connected or not self.device.device_reachable:
            return
        if now is not None:
            self.hass.async_create_task(self.async_refresh_map_extras(dock=False, stop_points=False))
        parameters = [{"siid": POSE_COVERAGE_PROPERTY.siid, "piid": POSE_COVERAGE_PROPERTY.piid}]
        try:
            await self.hass.async_add_executor_job(
                lambda: self.device.cloud_device.get_properties(parameters, retry_count=1)
            )
        except TimeoutError:
            _LOGGER.debug("The mower did not answer the position request")
        except Exception as ex:
            _LOGGER.warning("Failed to request the mower's position: %s", ex)

    @callback
    def _async_schedule_trail_read(self) -> None:
        """Read the session's trail back, unless a read is already running."""
        if self._trail_read is not None and not self._trail_read.done():
            return
        self._trail_read = self.hass.async_create_task(self._async_refresh_trail())

    async def _async_refresh_trail(self) -> None:
        """Read the running session's trail back from the mower."""
        if self.device_type == DEVICE_TYPE_SWBOT or not self.device_online:
            return
        try:
            if await self.hass.async_add_executor_job(self.device.refresh_trail):
                self.async_update_listeners()
        except Exception as ex:
            _LOGGER.debug("Reading the session's trail failed: %s", ex)

    async def async_refresh_map_extras(
        self, *, dock: bool = True, obstacles: bool = True, stop_points: bool = True
    ) -> None:
        """Read where the station stands, the obstacles and the stop points of the active map."""
        if self.device_type == DEVICE_TYPE_SWBOT or not self.device_online:
            return
        for wanted, read, what in (
            (dock, self.device.refresh_dock_position, "station position"),
            (dock, self.device.refresh_mower_position, "mower position"),
            (obstacles, self.device.refresh_obstacles, "obstacles"),
            (obstacles and stop_points, self.device.refresh_stop_points, "stop points"),
        ):
            if not wanted:
                continue
            try:
                if await self.hass.async_add_executor_job(read):
                    self.async_update_listeners()
            except Exception as ex:
                _LOGGER.debug("Reading the %s failed: %s", what, ex)

    @callback
    def async_when_probed(self, add: Callable[[], None]) -> None:
        """Run `add` once the reads that decide what the mower offers are done."""
        if self._probe_cancelled:
            return
        if self._probed:
            add()
        else:
            self._probe_waiters.append(add)

    @callback
    def async_cancel_probe(self) -> None:
        """The entry goes away; entities waiting for the reads are not added."""
        self._probe_cancelled = True
        self._probe_waiters.clear()

    @callback
    def async_mark_probed(self) -> None:
        """The reads that decide what the mower offers are done."""
        if self._probe_cancelled:
            return
        self._probed = True
        waiters, self._probe_waiters = self._probe_waiters, []
        for add in waiters:
            add()

    @callback
    def async_shutdown_map_feeds(self) -> None:
        """Tell everything following the map that this entry goes away."""
        for shutdown in list(self.shutdown_callbacks):
            shutdown()
        self.shutdown_callbacks.clear()

    async def _async_handle_device_update(self) -> None:
        """Async handler for device updates."""
        self.async_update_pose_keepalive()
        try:
            # Get fresh data and update all entities
            self.async_set_updated_data(None)
        except Exception as ex:
            _LOGGER.exception("Error handling device update: %s", ex)
    
    @property
    def consumable_values(self) -> list[int] | None:
        """Return cached CMS consumable counters: [blade_min, brush_min, robot_min]."""
        return self._consumable_values

    @property
    def consumables(self) -> list[dict[str, Any]] | None:
        """Return how worn each consumable is: the blades, the station brush and
        the mower's own maintenance, with the hours used, left and in all, and
        the share left in percent. None until the counters have been read."""
        values = self._consumable_values
        if values is None:
            return None
        items = []
        for index, item in enumerate(("blade", "brush", "robot")):
            if len(values) <= index:
                break
            total = CONSUMABLE_COUNTER_TOTAL_MINUTES[item]
            used = max(0, min(int(values[index]), total))
            items.append(
                {
                    "item": item,
                    "health": round((total - used) / total * 100, 1),
                    "used_hours": round(used / 60, 1),
                    "remaining_hours": round((total - used) / 60, 1),
                    "total_hours": round(total / 60, 1),
                }
            )
        return items

    async def async_reset_consumable(self, item: str) -> None:
        """Start a consumable's count over, as after replacing it.

        The counters are read back afterwards; a reset the mower did not take
        raises ValueError, while a read-back that fails leaves the reset be.
        """
        await self.device.reset_consumable_counter(item)
        try:
            await self.async_fetch_consumable_data()
        except Exception as ex:
            _LOGGER.warning("Consumable refresh after reset failed: %s", ex)
            return
        for entry in self.consumables or []:
            if entry["item"] == item and entry["used_hours"] > 0:
                raise ValueError(f"The mower kept counting the {item} after the reset")

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
        self.async_set_updated_data(None)

    async def async_start_firmware_update(self) -> bool:
        """Ask the cloud to push the available firmware update to the mower."""
        return await self.device.start_firmware_update()

    async def async_update_online_status(self) -> None:
        """Poll the cloud connectivity heartbeat to detect if the device is offline."""
        await self.device.async_update_online_status()

    async def async_connect_device(self) -> bool:
        return await self.device.connect()

    async def async_disconnect_device(self) -> None:
        """Disconnect from the device."""
        await self.device.disconnect()