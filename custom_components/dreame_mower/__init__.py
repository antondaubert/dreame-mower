"""The Dreame Mower Implementation.

This file serves as the main entry point for the integration.
It sets up the coordinator and forwards platform setup to dedicated modules.
To add new features, simply extend the PLATFORMS tuple - each platform
will automatically route to its corresponding module (e.g., switch.py, button.py).
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DATA_COORDINATOR,
    DATA_PLATFORMS,
    DOMAIN,
    FIRMWARE_POLL_INTERVAL_HOURS,
    ONLINE_POLL_INTERVAL_SECONDS,
    RAIN_POLL_INTERVAL_SECONDS,
)
from .coordinator import DreameMowerCoordinator
from .config_flow import DEVICE_TYPE_SWBOT

_LOGGER = logging.getLogger(__name__)

_MOWER_PLATFORMS = (
    Platform.LAWN_MOWER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.TIME,
)
_SWBOT_PLATFORMS = (
    Platform.SENSOR,
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

    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        try:
            await hass.async_add_executor_job(coordinator.device.fetch_vector_map)
        except Exception as ex:
            _LOGGER.warning("Initial vector map fetch failed: %s", ex)
    
    # Start coordinator updates (minimal - may not do anything initially)
    await coordinator.async_config_entry_first_refresh()
    
    # Trigger initial data update to reflect current device state
    await coordinator.async_request_refresh()

    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        try:
            await coordinator.async_fetch_consumable_data()
        except Exception as ex:
            _LOGGER.warning("Initial consumable data fetch failed: %s", ex)

    if coordinator.device_type != DEVICE_TYPE_SWBOT and coordinator.supports_cutting_height:
        try:
            await coordinator.async_fetch_cutting_heights()
        except Exception as ex:
            _LOGGER.warning("Initial cutting height fetch failed: %s", ex)

    # Read the charging settings once: they double as the probe that decides
    # whether the device exposes a custom charging period at all.
    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        try:
            await coordinator.async_fetch_charging_settings()
        except Exception as ex:
            _LOGGER.warning("Initial charging settings fetch failed: %s", ex)

    # Read the rain protection settings once: they double as the probe that
    # decides whether the device offers rain protection at all.
    if coordinator.device_type != DEVICE_TYPE_SWBOT:
        try:
            await coordinator.async_refresh_rain_state()
        except Exception as ex:
            _LOGGER.warning("Initial rain protection fetch failed: %s", ex)

    # Store coordinator in hass data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_PLATFORMS: platforms,
    }

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
    if coordinator.supports_rain_protection:
        async def _async_poll_rain(now=None) -> None:
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

    # Set up all platforms for this device/entry.
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Disconnect device before unloading
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data[DATA_COORDINATOR]
    entry_platforms = entry_data[DATA_PLATFORMS]
    await coordinator.async_disconnect_device()
    
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, entry_platforms):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)