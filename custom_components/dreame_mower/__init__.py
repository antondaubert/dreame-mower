"""The Dreame Mower Implementation.

This file serves as the main entry point for the integration.
It sets up the coordinator and forwards platform setup to dedicated modules.
To add new features, simply extend the PLATFORMS tuple - each platform
will automatically route to its corresponding module (e.g., switch.py, sensor.py).
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DATA_COORDINATOR,
    DATA_PLATFORMS,
    DATA_POINT_CLOUD,
    DOMAIN,
    FIRMWARE_POLL_INTERVAL_HOURS,
    ONLINE_POLL_INTERVAL_SECONDS,
    RAIN_POLL_INTERVAL_SECONDS,
    SCHEDULE_POLL_INTERVAL_SECONDS,
    MAP_POLL_INTERVAL_SECONDS,
)
from .coordinator import DreameMowerCoordinator
from .config_flow import DEVICE_TYPE_SWBOT
from .frontend import async_setup_frontend
from .point_cloud import PointCloudStore, async_remove_point_clouds, point_cloud_dir

_LOGGER = logging.getLogger(__name__)

_MOWER_PLATFORMS = (
    Platform.LAWN_MOWER,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TIME,
    Platform.UPDATE,
)
_SWBOT_PLATFORMS = (
    Platform.SENSOR,
)

# The keys of entities earlier versions created, removed from the registry.
_RETIRED_ENTITY_KEYS = (
    "firmware_update_available",
    "map_camera",
    "map_select",
    "mowing_action",
    "edge_select",
    "zone_select",
    "spot_select",
    "maintenance_point_select",
    "mowing_direction_mode",
    "mowing_efficiency",
    "turning_method",
    "cutting_height",
    "mowing_direction",
    "obstacle_height",
    "obstacle_distance",
    "edge_mowing_auto",
    "edge_mowing_safe",
    "edge_blade_offset",
    "lidar_obstacle_recognition",
    "edge_obstacle_avoidance",
    "ai_obstacle_humans",
    "ai_obstacle_animals",
    "ai_obstacle_objects",
    "reset_consumable_blade",
    "reset_consumable_brush",
    "reset_consumable_robot",
    "go_to_maintenance_point",
    "find_robot",
    "dock_without_stopping",
    "charging_status",
    "bluetooth_connection",
    "device_code",
    "current_task",
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dreame Mower from a config entry."""
    
    # Create coordinator
    coordinator = DreameMowerCoordinator(hass, entry=entry)
    
    platforms = (
        _SWBOT_PLATFORMS
        if coordinator.device_type == DEVICE_TYPE_SWBOT
        else _MOWER_PLATFORMS
    )
    
    # Connect to the device. A failure here (e.g. the cloud MQTT broker timing
    # out) is transient, so raise ConfigEntryNotReady to let Home Assistant retry
    # setup with exponential backoff instead of leaving the entry stuck.
    if not await coordinator.async_connect_device():
        raise ConfigEntryNotReady(
            f"Unable to connect to Dreame device {coordinator.name}"
        )

    # A mower that is offline, or that the cloud lists as connected but that
    # does not answer, lets every command sent to it time out after several
    # seconds. Its setup reads only what
    # the cloud keeps, and the entry is set up again once the mower is back so
    # the reads that decide which entities it gets are made then.
    reachable = coordinator.device_type == DEVICE_TYPE_SWBOT or await coordinator.device.async_check_reachable()
    if not reachable:
        _LOGGER.info("%s is offline; reading its device settings once it is back", coordinator.device_name)
        coordinator.reload_when_online = True

    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        # The cloud's copy of the maps comes in one request; reading them from
        # the mower takes many, and runs with the other reads after setup.
        try:
            await hass.async_add_executor_job(coordinator.device.load_stored_vector_map)
        except Exception as ex:
            _LOGGER.warning("Reading the stored maps failed: %s", ex)

        # The map card and the feed it draws from.
        await async_setup_frontend(hass)

    # Start coordinator updates (minimal - may not do anything initially)
    await coordinator.async_config_entry_first_refresh()

    # Trigger initial data update to reflect current device state
    await coordinator.async_request_refresh()

    # The reads that decide which settings a mower offers take a command each,
    # and a mower on a slow link answers every one only after seconds. They run
    # once setup is done, and the entities that depend on them are added as
    # they finish, so Home Assistant does not wait for them to start.
    if coordinator.device_type != DEVICE_TYPE_SWBOT and reachable:
        entry.async_create_background_task(
            hass, _async_read_device_settings(hass, coordinator), f"{DOMAIN} initial reads"
        )
    else:
        coordinator.async_mark_probed()

    # Store coordinator in hass data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_PLATFORMS: platforms,
    }
    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        hass.data[DOMAIN][entry.entry_id][DATA_POINT_CLOUD] = PointCloudStore(
            coordinator.device, point_cloud_dir(hass, entry.entry_id)
        )

    # While a mowing session runs, keep the position reports coming; open map
    # cards hear when the entry goes away.
    coordinator.async_update_pose_keepalive()
    entry.async_on_unload(coordinator.async_stop_pose_keepalive)
    entry.async_on_unload(coordinator.async_shutdown_map_feeds)

    # Home Assistant does not unload config entries when it stops, so the MQTT
    # client would keep handing pushes from a working mower to an event loop
    # that is already closed. Drop the cloud connection before that happens.
    async def _async_disconnect_on_stop(event: Event) -> None:
        await coordinator.async_disconnect_device()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_disconnect_on_stop)
    )

    # Periodically poll for firmware update availability (mowers only). The value
    # changes rarely and the device does not reliably push it, so poll on an interval.
    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        async def _async_poll_firmware(now=None) -> None:
            try:
                await coordinator.async_fetch_firmware_status()
            except Exception as ex:
                _LOGGER.warning("Firmware status poll failed: %s", ex)

        await _async_poll_firmware()
        entry.async_on_unload(
            async_track_time_interval(
                hass,
                _async_poll_firmware,
                timedelta(hours=FIRMWARE_POLL_INTERVAL_HOURS),
                cancel_on_shutdown=True,
            )
        )

        # Periodically poll the cloud connectivity heartbeat so entities go
        # unavailable when the robot itself drops off the cloud. The integration's
        # own MQTT link stays connected in that case, so it cannot detect the
        # device going offline on its own.
        async def _async_poll_online(now=None) -> None:
            try:
                await coordinator.async_update_online_status()
            except Exception as ex:
                _LOGGER.warning("Online status poll failed: %s", ex)

        await _async_poll_online()
        entry.async_on_unload(
            async_track_time_interval(
                hass,
                _async_poll_online,
                timedelta(seconds=ONLINE_POLL_INTERVAL_SECONDS),
                cancel_on_shutdown=True,
            )
        )

    # Retire a resume time that has passed: the mower reports the time it will
    # work again when rain stops it, but nothing when that time simply runs out.
    # Whether it offers rain protection is only known once the reads after
    # setup are done, so the poll asks each time.
    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        async def _async_poll_rain(now=None) -> None:
            if not coordinator.supports_rain_protection:
                return
            try:
                await coordinator.async_fetch_rain_protection_end()
            except Exception as ex:
                _LOGGER.warning("Rain protection poll failed: %s", ex)

        entry.async_on_unload(
            async_track_time_interval(
                hass,
                _async_poll_rain,
                timedelta(seconds=RAIN_POLL_INTERVAL_SECONDS),
                cancel_on_shutdown=True,
            )
        )

    # Keep the schedules in step with edits made elsewhere. The device announces
    # every settings change but says nothing about a changed schedule, so the poll
    # asks for the version it holds them under and only reads them back when that
    # version moved. It runs whether or not the read at startup came through: a
    # mower that was unreachable then is picked up by the next poll.
    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        async def _async_poll_schedules(now=None) -> None:
            try:
                await coordinator.async_fetch_schedules(changed_only=True)
            except Exception as ex:
                _LOGGER.warning("Schedule poll failed: %s", ex)

        entry.async_on_unload(
            async_track_time_interval(
                hass,
                _async_poll_schedules,
                timedelta(seconds=SCHEDULE_POLL_INTERVAL_SECONDS),
                cancel_on_shutdown=True,
            )
        )

    # Keep the maps in step with edits made elsewhere, such as a renamed zone or
    # a deleted map. Neither is announced, so the poll compares the hash of every
    # map and only reads the maps back when one moved.
    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        async def _async_poll_maps(now=None) -> None:
            try:
                await hass.async_add_executor_job(coordinator.device.refresh_changed_vector_map)
            except Exception as ex:
                _LOGGER.warning("Map poll failed: %s", ex)
            await coordinator.async_refresh_map_extras()

        entry.async_on_unload(
            async_track_time_interval(
                hass,
                _async_poll_maps,
                timedelta(seconds=MAP_POLL_INTERVAL_SECONDS),
                cancel_on_shutdown=True,
            )
        )

    # Drop the entities earlier versions created and this one no longer does, so
    # they do not linger as orphans: firmware updates used to be reported by a
    # binary sensor, which the update entity replaces, and the rest gave way to
    # the map card.
    retired_unique_ids = {f"{entry.entry_id}_map_camera"} | {
        f"{coordinator.device_mac}_{key}" for key in _RETIRED_ENTITY_KEYS
    }
    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity_entry.unique_id in retired_unique_ids:
            entity_registry.async_remove(entity_entry.entity_id)

    # Set up all platforms for this device/entry.
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def _async_read_device_settings(hass: HomeAssistant, coordinator: DreameMowerCoordinator) -> None:
    """Read what a mower offers, then let the platforms add what depends on it."""
    try:
        # The maps as the mower holds them, which may be newer than the copy.
        try:
            if await hass.async_add_executor_job(coordinator.device.fetch_vector_map):
                coordinator.async_update_listeners()
        except Exception as ex:
            _LOGGER.warning("Initial vector map fetch failed: %s", ex)

        # Where the station stands and the obstacles on the active map.
        await coordinator.async_refresh_map_extras()

        for what, read in (
            ("consumable data", coordinator.async_fetch_consumable_data),
            # The mowing preferences carry the cutting heights and the edge
            # mowing settings, and decide which of them the device offers.
            ("mowing preference", coordinator.async_fetch_mowing_preferences),
            # The settings record holds the charging period, rain protection
            # and the anti-theft settings, and decides which the device offers.
            ("device settings", coordinator.async_fetch_device_settings),
            # The schedules of the active map, and whether there are any.
            ("schedule", coordinator.async_fetch_schedules),
        ):
            try:
                await read()
            except Exception as ex:
                _LOGGER.warning("Initial %s fetch failed: %s", what, ex)
    finally:
        coordinator.async_mark_probed()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Disconnect device before unloading
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data[DATA_COORDINATOR]
    entry_platforms = entry_data[DATA_PLATFORMS]
    # Reads still running must not add entities to platforms about to go.
    coordinator.async_cancel_probe()
    await coordinator.async_disconnect_device()
    
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, entry_platforms):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete what the entry kept on disk."""
    await async_remove_point_clouds(hass, entry.entry_id)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)