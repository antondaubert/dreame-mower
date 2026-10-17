"""Test the Dreame Mower coordinator."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.dreame_mower.coordinator import POSE_COVERAGE_REQUEST_INTERVAL, DreameMowerCoordinator
from custom_components.dreame_mower.const import DOMAIN
from custom_components.dreame_mower.config_flow import CONF_ACCOUNT_TYPE, CONF_COUNTRY, CONF_DID, CONF_MAC, CONF_MODEL, CONF_SERIAL
from custom_components.dreame_mower.dreame.const import (
    CURRENT_MAP_ID_PROPERTY_NAME,
    MAP_SWITCH_ANNOUNCED_PROPERTY_NAME,
    FIRMWARE_INSTALL_STATE_PROPERTY,
    FirmwareInstallState,
    SCHEDULING_SUMMARY_PROPERTY,
    MowingPreferenceMode,
)
from custom_components.dreame_mower.dreame.property.property_misc import (
    PROPERTY_1_1_ACTIVE_CODES_NAME,
    SETTINGS_CHANGED_PROPERTY_NAME,
)


@pytest.fixture
def minimal_config_entry():
    """Create a minimal config entry for testing."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Minimal Mower",
        data={
            CONF_NAME: "Test Mower",
            CONF_MAC: "11:22:33:44:55:66",
            CONF_MODEL: "dreame.mower.test789",
            CONF_SERIAL: "MIN123456",
            CONF_DID: "test_device_456",
            CONF_USERNAME: "test_user",
            CONF_PASSWORD: "test_password",
            CONF_ACCOUNT_TYPE: "dreame",
            CONF_COUNTRY: "DE",
        },
        entry_id="test_minimal_entry",
    )


async def test_coordinator_initialization(hass: HomeAssistant, minimal_config_entry):
    """Test that DreameMowerCoordinator initializes correctly with minimal config."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    
    # Check that coordinator is properly initialized
    assert coordinator is not None
    assert coordinator.entry == minimal_config_entry
    assert coordinator.name == DOMAIN
    assert coordinator.update_interval is None  # No polling by default


async def test_coordinator_holds_no_data_of_its_own(hass: HomeAssistant, minimal_config_entry):
    """The device pushes its state and the entities read it, so an update fetches nothing."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)

    assert await coordinator._async_update_data() is None


async def test_coordinator_rereads_the_active_map_when_the_mower_announces_a_switch(
    hass: HomeAssistant, minimal_config_entry
):
    """A switch made outside Home Assistant is announced without the map, so the map list is read."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device.refresh_current_map_id = MagicMock(return_value=True)

    with patch("custom_components.dreame_mower.coordinator._MAP_SWITCH_READ_BACK_DELAY_SECONDS", 0):
        coordinator._handle_device_update(MAP_SWITCH_ANNOUNCED_PROPERTY_NAME, None)
        await hass.async_block_till_done()

    coordinator.device.refresh_current_map_id.assert_called_once()


async def test_coordinator_rereads_the_active_map_on_the_marker_alone(
    hass: HomeAssistant, minimal_config_entry
):
    """The 1:50 marker comes with every switch, also when the echo does not."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device.refresh_current_map_id = MagicMock(return_value=True)

    with patch("custom_components.dreame_mower.coordinator._MAP_SWITCH_READ_BACK_DELAY_SECONDS", 0):
        coordinator._handle_device_update("service1_property_50", True)
        await hass.async_block_till_done()

    coordinator.device.refresh_current_map_id.assert_called_once()


async def test_coordinator_follows_every_later_switch_too(
    hass: HomeAssistant, minimal_config_entry
):
    """Once a read-back ran, the next switch is read back again."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device.refresh_current_map_id = MagicMock(return_value=True)

    with patch("custom_components.dreame_mower.coordinator._MAP_SWITCH_READ_BACK_DELAY_SECONDS", 0):
        coordinator._handle_device_update(MAP_SWITCH_ANNOUNCED_PROPERTY_NAME, None)
        await hass.async_block_till_done()
        coordinator._handle_device_update(MAP_SWITCH_ANNOUNCED_PROPERTY_NAME, None)
        await hass.async_block_till_done()

    assert coordinator.device.refresh_current_map_id.call_count == 2


async def test_coordinator_reads_the_map_list_once_for_echo_and_marker(
    hass: HomeAssistant, minimal_config_entry
):
    """The echo and the 1:50 marker of one switch cost a single read."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device.refresh_current_map_id = MagicMock(return_value=True)

    with patch("custom_components.dreame_mower.coordinator._MAP_SWITCH_READ_BACK_DELAY_SECONDS", 0):
        coordinator._handle_device_update("service1_property_50", True)
        coordinator._handle_device_update(MAP_SWITCH_ANNOUNCED_PROPERTY_NAME, None)
        await hass.async_block_till_done()

    coordinator.device.refresh_current_map_id.assert_called_once()


async def test_coordinator_refreshes_the_mowing_preferences_of_fixed_height_models(
    hass: HomeAssistant, minimal_config_entry
):
    """A model with a manual height dial still keeps the other mowing settings."""
    minimal_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        minimal_config_entry,
        data={**minimal_config_entry.data, CONF_MODEL: "mova.mower.g2405c"},
    )
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device.refresh_mowing_preferences = AsyncMock(return_value=True)
    coordinator.device.refresh_zone_mowing_preferences = AsyncMock(return_value={})

    coordinator._handle_device_update(CURRENT_MAP_ID_PROPERTY_NAME, 2)
    await hass.async_block_till_done()

    coordinator.device.refresh_mowing_preferences.assert_awaited_once()


async def test_coordinator_delegates_cutting_height_calls_to_the_device(
    hass: HomeAssistant, minimal_config_entry
):
    """Entity tests mock the coordinator, so its own wiring needs covering here."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    device = MagicMock()
    device.cutting_height = 4.0
    device.zone_cutting_heights = {1: 5.0}
    device.mowing_preference_mode = MowingPreferenceMode.PER_ZONE
    device.set_cutting_height = AsyncMock(return_value=True)
    device.set_mowing_preference_mode = AsyncMock(return_value=True)
    device.refresh_zone_cutting_heights = AsyncMock(return_value={1: 5.0})
    coordinator.device = device
    coordinator.async_update_listeners = MagicMock()

    assert coordinator.cutting_height == 4.0
    assert coordinator.zone_cutting_heights == {1: 5.0}
    assert coordinator.mowing_preference_mode is MowingPreferenceMode.PER_ZONE

    assert await coordinator.async_set_cutting_height(5.5, 2, 3) is True
    device.set_cutting_height.assert_awaited_once_with(5.5, 2, 3)

    assert await coordinator.async_set_mowing_preference_mode(MowingPreferenceMode.MAP_WIDE, 2) is True
    device.set_mowing_preference_mode.assert_awaited_once_with(MowingPreferenceMode.MAP_WIDE, 2)

    assert await coordinator.async_fetch_zone_cutting_heights() == {1: 5.0}
    assert device.refresh_zone_cutting_heights.await_count == 1

    # Every one of those calls has to push the new state to the entities.
    assert coordinator.async_update_listeners.call_count == 3


async def test_coordinator_cutting_height_defaults_to_the_current_map_and_whole_map(
    hass: HomeAssistant, minimal_config_entry
):
    """Omitted map and zone must reach the device as None, not be dropped."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_cutting_height = AsyncMock(return_value=True)

    await coordinator.async_set_cutting_height(6.0)

    coordinator.device.set_cutting_height.assert_awaited_once_with(6.0, None, None)


async def test_coordinator_delegates_edge_mowing_calls_to_the_device(
    hass: HomeAssistant, minimal_config_entry
):
    """Entity tests mock the coordinator, so its own wiring needs covering here."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    device = MagicMock()
    device.edge_mowing_settings = {
        "edge_mowing_auto": True,
        "edge_blade_offset": False,
        "edge_mowing_safe": True,
    }
    device.set_edge_mowing_settings = AsyncMock(return_value=True)
    coordinator.device = device
    coordinator.async_update_listeners = MagicMock()

    assert coordinator.supports_edge_mowing_settings is True
    assert coordinator.edge_mowing_auto is True

    assert await coordinator.async_set_edge_mowing_settings(safe=False, zone_id=2) is True
    device.set_edge_mowing_settings.assert_awaited_once_with(
        auto=None,
        blade_offset=None,
        safe=False,
        map_id=None,
        zone_id=2,
    )
    coordinator.async_update_listeners.assert_called_once()


async def test_coordinator_joins_a_preference_read_that_is_already_running(
    hass: HomeAssistant, minimal_config_entry
):
    """The device answers one command at a time, so a second read only delays it."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_refresh():
        started.set()
        await release.wait()
        return True

    coordinator.device.refresh_mowing_preferences = AsyncMock(side_effect=_slow_refresh)
    coordinator.device.refresh_zone_mowing_preferences = AsyncMock(return_value={})
    coordinator.async_update_listeners = MagicMock()

    first = asyncio.create_task(coordinator.async_fetch_mowing_preferences())
    await started.wait()
    second = asyncio.create_task(coordinator.async_fetch_mowing_preferences())
    await asyncio.sleep(0)
    release.set()

    assert await first is True
    assert await second is True
    coordinator.device.refresh_mowing_preferences.assert_awaited_once()


async def test_coordinator_reads_again_after_the_device_announced_a_change(
    hass: HomeAssistant, minimal_config_entry
):
    """A read started before the announcement could not have seen the change."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.current_map_id = 1
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_refresh():
        started.set()
        await release.wait()
        return True

    coordinator.device.refresh_mowing_preferences = AsyncMock(side_effect=_slow_refresh)
    coordinator.device.refresh_zone_mowing_preferences = AsyncMock(return_value={})
    coordinator.async_update_listeners = MagicMock()

    running = asyncio.create_task(coordinator.async_fetch_mowing_preferences())
    await started.wait()
    coordinator._handle_device_update(SCHEDULING_SUMMARY_PROPERTY.name, {})
    await asyncio.sleep(0)
    release.set()
    await running
    await hass.async_block_till_done()

    assert coordinator.device.refresh_mowing_preferences.await_count == 2


async def test_coordinator_reports_an_edge_setting_the_device_does_not_keep(
    hass: HomeAssistant, minimal_config_entry
):
    """A setting missing from the record is unknown."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.edge_mowing_settings = {"edge_mowing_safe": True}

    assert coordinator.supports_edge_mowing_settings is True
    assert coordinator.edge_mowing_auto is None


async def test_coordinator_reports_no_edge_settings_before_they_are_read(
    hass: HomeAssistant, minimal_config_entry
):
    """Until the record has been read there is nothing to build switches from."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.edge_mowing_settings = None

    assert coordinator.supports_edge_mowing_settings is False
    assert coordinator.edge_mowing_auto is None


async def _read_settings(coordinator, *, charging=None, rain=None, anti_theft=None):
    """Have the coordinator read a settings record holding the given sections."""
    coordinator.device.get_device_settings = AsyncMock(return_value={})
    coordinator.device.decode_charging_settings = MagicMock(return_value=charging)
    coordinator.device.decode_rain_settings = MagicMock(return_value=rain)
    coordinator.device.decode_anti_theft_settings = MagicMock(return_value=anti_theft)
    await coordinator.async_refresh_device_settings()


def _charging_settings(enabled=True, start=1320, end=360):
    """Build a charging settings payload as the device decodes it."""
    return {
        "recharge_battery_level": 20,
        "resume_battery_level": 80,
        "resume_after_charging": True,
        "charging_period_enabled": enabled,
        "charging_period_start_minutes": start,
        "charging_period_end_minutes": end,
        "raw": [20, 80, 1, int(enabled), start, end],
    }


async def test_coordinator_caches_the_charging_settings_it_reads(
    hass: HomeAssistant, minimal_config_entry
):
    """The entities read the cached settings, so a fetch has to fill the cache."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.async_update_listeners = MagicMock()

    assert coordinator.supports_charging_period is False
    assert coordinator.charging_period_enabled is None
    assert coordinator.charging_period_start_minutes is None
    assert coordinator.charging_period_end_minutes is None

    await _read_settings(coordinator, charging=_charging_settings())

    assert coordinator.supports_charging_period is True
    assert coordinator.charging_period_enabled is True
    assert coordinator.charging_period_start_minutes == 1320
    assert coordinator.charging_period_end_minutes == 360
    coordinator.async_update_listeners.assert_called_once()


async def test_coordinator_reports_a_device_without_charging_settings(
    hass: HomeAssistant, minimal_config_entry
):
    """A device that cannot report the settings must not claim to support them."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()

    await _read_settings(coordinator)

    assert coordinator.supports_charging_period is False


async def test_coordinator_caches_the_charging_period_it_writes(
    hass: HomeAssistant, minimal_config_entry
):
    """A write returns the settings that took effect; they become the new state."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_charging_period = AsyncMock(
        return_value=_charging_settings(enabled=False, start=60, end=420)
    )
    coordinator.async_update_listeners = MagicMock()

    assert await coordinator.async_set_charging_period(enabled=False) is True

    coordinator.device.set_charging_period.assert_awaited_once_with(
        enabled=False, start_minutes=None, end_minutes=None
    )
    assert coordinator.charging_period_enabled is False
    assert coordinator.charging_period_start_minutes == 60
    assert coordinator.charging_period_end_minutes == 420
    coordinator.async_update_listeners.assert_called_once()


async def test_coordinator_keeps_the_charging_period_when_a_write_is_rejected(
    hass: HomeAssistant, minimal_config_entry
):
    """A rejected write must not leave the entities showing the requested value."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_charging_period = AsyncMock(return_value=None)
    await _read_settings(coordinator, charging=_charging_settings())

    assert await coordinator.async_set_charging_period(start_minutes=0) is False

    assert coordinator.charging_period_start_minutes == 1320


def _rain_settings(enabled=True, delay_hours=8, sensitivity=0):
    """Build a rain settings payload as the device decodes it."""
    return {
        "rain_protection_enabled": enabled,
        "rain_delay_hours": delay_hours,
        "rain_sensitivity": sensitivity,
        "raw": [int(enabled), delay_hours, sensitivity],
    }


async def test_coordinator_caches_the_rain_settings_it_reads(
    hass: HomeAssistant, minimal_config_entry
):
    """The entities read the cached settings, so a fetch has to fill the cache."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.async_update_listeners = MagicMock()

    assert coordinator.supports_rain_protection is False
    assert coordinator.rain_protection_enabled is None
    assert coordinator.rain_delay_hours is None

    await _read_settings(coordinator, rain=_rain_settings())

    assert coordinator.supports_rain_protection is True
    assert coordinator.rain_protection_enabled is True
    assert coordinator.rain_delay_hours == 8
    coordinator.async_update_listeners.assert_called_once()


async def test_coordinator_reports_a_device_without_rain_settings(
    hass: HomeAssistant, minimal_config_entry
):
    """A device that cannot report the settings must not claim to support them."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()

    await _read_settings(coordinator)

    assert coordinator.supports_rain_protection is False


async def test_coordinator_caches_the_rain_settings_it_writes(
    hass: HomeAssistant, minimal_config_entry
):
    """A write returns the settings that took effect; they become the new state."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_rain_protection = AsyncMock(
        return_value=_rain_settings(enabled=False, delay_hours=3)
    )
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.async_update_listeners = MagicMock()

    assert await coordinator.async_set_rain_protection(enabled=False) is True

    coordinator.device.set_rain_protection.assert_awaited_once_with(
        enabled=False, delay_hours=None
    )
    assert coordinator.rain_protection_enabled is False
    assert coordinator.rain_delay_hours == 3
    coordinator.async_update_listeners.assert_called()
    # Switching protection off can release a mower rain was holding back.
    coordinator.device.get_rain_protection_end_timestamp.assert_awaited_once()


async def test_coordinator_keeps_the_rain_settings_when_a_write_is_rejected(
    hass: HomeAssistant, minimal_config_entry
):
    """A rejected write must not leave the entities showing the requested value."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_rain_protection = AsyncMock(return_value=None)
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    await _read_settings(coordinator, rain=_rain_settings())

    assert await coordinator.async_set_rain_protection(delay_hours=0) is False

    assert coordinator.rain_delay_hours == 8


async def test_coordinator_holds_the_mower_back_until_the_end_time_passes(
    hass: HomeAssistant, minimal_config_entry
):
    """Rain protection counts as active only while its end time is still ahead."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.async_update_listeners = MagicMock()

    ahead = int(dt_util.utcnow().timestamp()) + 3600
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=ahead)
    await coordinator.async_fetch_rain_protection_end()

    assert coordinator.rain_protection_active is True
    assert coordinator.rain_protection_end_time == datetime.fromtimestamp(ahead, tz=timezone.utc)

    behind = int(dt_util.utcnow().timestamp()) - 60
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=behind)
    await coordinator.async_fetch_rain_protection_end()

    assert coordinator.rain_protection_active is False


async def test_coordinator_has_no_end_time_while_rain_holds_nothing_back(
    hass: HomeAssistant, minimal_config_entry
):
    """Without an end time from the device there is nothing to report."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.async_update_listeners = MagicMock()

    await coordinator.async_fetch_rain_protection_end()

    assert coordinator.rain_protection_end_time is None
    assert coordinator.rain_protection_active is False


async def test_coordinator_rereads_the_end_time_when_rain_stops_the_mower(
    hass: HomeAssistant, minimal_config_entry
):
    """A rain code in the heartbeat is the cue that the mower knows when it may resume."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.async_update_listeners = MagicMock()
    await _read_settings(coordinator, rain=_rain_settings())
    coordinator.device.get_rain_protection_end_timestamp.reset_mock()

    coordinator._handle_device_update(PROPERTY_1_1_ACTIVE_CODES_NAME, frozenset({56}))
    await hass.async_block_till_done()

    coordinator.device.get_rain_protection_end_timestamp.assert_awaited()


async def test_coordinator_ignores_unrelated_device_codes_for_rain(
    hass: HomeAssistant, minimal_config_entry
):
    """Codes that have nothing to do with rain must not trigger a read."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.async_update_listeners = MagicMock()
    await _read_settings(coordinator, rain=_rain_settings())
    coordinator.device.get_rain_protection_end_timestamp.reset_mock()

    coordinator._handle_device_update(PROPERTY_1_1_ACTIVE_CODES_NAME, frozenset({48, 50}))
    await hass.async_block_till_done()

    coordinator.device.get_rain_protection_end_timestamp.assert_not_awaited()


async def test_coordinator_skips_the_end_time_without_rain_settings(
    hass: HomeAssistant, minimal_config_entry
):
    """A device with no rain settings has no protection to ask about."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.get_device_settings = AsyncMock(return_value={})
    coordinator.device.decode_charging_settings = MagicMock(return_value=None)
    coordinator.device.decode_rain_settings = MagicMock(return_value=None)
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=None)

    await coordinator.async_fetch_device_settings()

    coordinator.device.get_rain_protection_end_timestamp.assert_not_awaited()


async def test_coordinator_reads_the_settings_record_once_at_startup(
    hass: HomeAssistant, minimal_config_entry
):
    """The charging and the rain settings share a record, so one read serves both."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.get_device_settings = AsyncMock(return_value={"BAT": [], "WRP": []})
    coordinator.device.decode_charging_settings = MagicMock(return_value=_charging_settings())
    coordinator.device.decode_rain_settings = MagicMock(return_value=_rain_settings())
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)

    await coordinator.async_fetch_device_settings()

    coordinator.device.get_device_settings.assert_awaited_once()
    coordinator.device.get_rain_protection_end_timestamp.assert_awaited_once()
    assert coordinator.supports_charging_period is True
    assert coordinator.supports_rain_protection is True


async def test_coordinator_keeps_the_end_time_when_the_read_fails(
    hass: HomeAssistant, minimal_config_entry
):
    """A read that did not come through must not read as a mower free to work."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.async_update_listeners = MagicMock()

    ahead = int(dt_util.utcnow().timestamp()) + 3600
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=ahead)
    assert await coordinator.async_fetch_rain_protection_end() is True

    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=None)
    assert await coordinator.async_fetch_rain_protection_end() is False

    assert coordinator.rain_protection_active is True
    assert coordinator.rain_protection_end_time == datetime.fromtimestamp(ahead, tz=timezone.utc)


async def test_coordinator_clears_the_end_time_when_the_mower_is_free(
    hass: HomeAssistant, minimal_config_entry
):
    """Zero is the device saying it is free to work, so the time has to go."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.async_update_listeners = MagicMock()

    ahead = int(dt_util.utcnow().timestamp()) + 3600
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=ahead)
    await coordinator.async_fetch_rain_protection_end()

    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    assert await coordinator.async_fetch_rain_protection_end() is True

    assert coordinator.rain_protection_end_time is None
    assert coordinator.rain_protection_active is False


async def test_coordinator_rereads_the_settings_when_the_device_changes_one(
    hass: HomeAssistant, minimal_config_entry
):
    """The device says a setting changed without saying which, so all are re-read."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.get_device_settings = AsyncMock(return_value={"WRP": [1, 6, 0]})
    coordinator.device.decode_rain_settings = MagicMock(
        return_value=_rain_settings(delay_hours=6)
    )
    coordinator.device.decode_charging_settings = MagicMock(return_value=None)
    coordinator.async_update_listeners = MagicMock()

    coordinator._handle_device_update(SETTINGS_CHANGED_PROPERTY_NAME, {"value": [1, 6, 0]})
    await hass.async_block_till_done()

    coordinator.device.get_device_settings.assert_awaited_once()
    assert coordinator.rain_delay_hours == 6


async def test_coordinator_ignores_the_echo_of_its_own_settings_write(
    hass: HomeAssistant, minimal_config_entry
):
    """A write already knows what it wrote, so its own echo must not cost a read."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_rain_protection = AsyncMock(return_value=_rain_settings())
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.device.get_device_settings = AsyncMock(return_value={})
    coordinator.async_update_listeners = MagicMock()

    await coordinator.async_set_rain_protection(enabled=True)
    coordinator._handle_device_update(SETTINGS_CHANGED_PROPERTY_NAME, {"value": [1, 8, 0]})
    await hass.async_block_till_done()

    coordinator.device.get_device_settings.assert_not_awaited()


async def test_coordinator_rereads_the_preferences_when_the_device_changes_one(
    hass: HomeAssistant, minimal_config_entry
):
    """A mowing setting changed in the app has to reach the entities."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.current_map_id = 1
    coordinator.device.refresh_mowing_preferences = AsyncMock(return_value=True)
    coordinator.device.refresh_zone_mowing_preferences = AsyncMock(return_value={})
    coordinator.async_update_listeners = MagicMock()

    coordinator._handle_device_update(SCHEDULING_SUMMARY_PROPERTY.name, {})
    await hass.async_block_till_done()

    coordinator.device.refresh_mowing_preferences.assert_awaited_once()
    coordinator.device.refresh_zone_mowing_preferences.assert_awaited_once()


async def test_coordinator_ignores_the_echo_of_its_own_preference_write(
    hass: HomeAssistant, minimal_config_entry
):
    """A write already knows what it wrote, so its own echo must not cost a read."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.current_map_id = 1
    coordinator.device.set_edge_mowing_settings = AsyncMock(return_value=True)
    coordinator.device.refresh_mowing_preferences = AsyncMock(return_value=True)
    coordinator.async_update_listeners = MagicMock()

    await coordinator.async_set_edge_mowing_settings(safe=False)
    coordinator._handle_device_update(SCHEDULING_SUMMARY_PROPERTY.name, {})
    await hass.async_block_till_done()

    coordinator.device.refresh_mowing_preferences.assert_not_awaited()


async def test_coordinator_keeps_the_two_echo_windows_apart(
    hass: HomeAssistant, minimal_config_entry
):
    """Writing one record must not suppress a re-read of the other."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.current_map_id = 1
    coordinator.device.set_edge_mowing_settings = AsyncMock(return_value=True)
    coordinator.device.get_device_settings = AsyncMock(return_value={})
    coordinator.device.decode_rain_settings = MagicMock(return_value=None)
    coordinator.device.decode_charging_settings = MagicMock(return_value=None)
    coordinator.async_update_listeners = MagicMock()

    await coordinator.async_set_edge_mowing_settings(safe=False)
    coordinator._handle_device_update(SETTINGS_CHANGED_PROPERTY_NAME, {"value": [1, 8, 0]})
    await hass.async_block_till_done()

    coordinator.device.get_device_settings.assert_awaited_once()


async def test_coordinator_skips_the_preference_reread_without_a_map(
    hass: HomeAssistant, minimal_config_entry
):
    """Without a map there is no record the read could be addressed at."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.current_map_id = None
    coordinator.device.refresh_mowing_preferences = AsyncMock(return_value=False)
    coordinator.async_update_listeners = MagicMock()

    coordinator._handle_device_update(SCHEDULING_SUMMARY_PROPERTY.name, {})
    await hass.async_block_till_done()

    coordinator.device.refresh_mowing_preferences.assert_not_awaited()


async def test_coordinator_keeps_a_setting_it_could_not_decode(
    hass: HomeAssistant, minimal_config_entry
):
    """A record missing one section must not wipe what is known about the other."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.async_update_listeners = MagicMock()
    await _read_settings(coordinator, rain=_rain_settings())

    await _read_settings(coordinator)

    assert coordinator.rain_delay_hours == 8


async def test_coordinator_sends_the_mower_to_a_maintenance_point(
    hass: HomeAssistant, minimal_config_entry
):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.go_to_maintenance_point = AsyncMock(return_value=True)

    assert await coordinator.async_go_to_maintenance_point(2) is True

    coordinator.device.go_to_maintenance_point.assert_awaited_once_with([2])


def _anti_theft_settings(lift=False, off_map=False, location=True, pin_check=None):
    """Build an anti-theft settings payload as the device decodes it."""
    raw = [int(lift), int(off_map), int(location)]
    if pin_check is not None:
        raw.append(int(pin_check))
    return {
        "lift_alarm_enabled": lift,
        "off_map_alarm_enabled": off_map,
        "location_reporting_enabled": location,
        "pin_check_enabled": pin_check,
        "raw": raw,
    }


async def test_coordinator_caches_the_anti_theft_settings_it_reads(
    hass: HomeAssistant, minimal_config_entry
):
    """The switches read the cached settings, so a fetch has to fill the cache."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.async_update_listeners = MagicMock()

    assert coordinator.supports_anti_theft is False
    assert coordinator.lift_alarm_enabled is None

    await _read_settings(coordinator, anti_theft=_anti_theft_settings())

    assert coordinator.supports_anti_theft is True
    assert coordinator.lift_alarm_enabled is False
    assert coordinator.off_map_alarm_enabled is False
    assert coordinator.location_reporting_enabled is True
    coordinator.async_update_listeners.assert_called_once()


async def test_coordinator_reports_a_device_without_anti_theft_settings(
    hass: HomeAssistant, minimal_config_entry
):
    """A device that cannot report the settings must not claim to support them."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()

    await _read_settings(coordinator)

    assert coordinator.supports_anti_theft is False
    assert coordinator.supports_anti_theft_pin_check is False


async def test_coordinator_reports_a_mower_without_a_pin_check(
    hass: HomeAssistant, minimal_config_entry
):
    """Only a record that names the PIN switch may offer it as a control."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.async_update_listeners = MagicMock()
    await _read_settings(coordinator, anti_theft=_anti_theft_settings())

    assert coordinator.supports_anti_theft_pin_check is False
    assert coordinator.anti_theft_pin_check_enabled is None

    await _read_settings(coordinator, anti_theft=_anti_theft_settings(pin_check=True))

    assert coordinator.supports_anti_theft_pin_check is True
    assert coordinator.anti_theft_pin_check_enabled is True


async def test_coordinator_caches_the_anti_theft_settings_it_writes(
    hass: HomeAssistant, minimal_config_entry
):
    """A write returns the settings that took effect; they become the new state."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_anti_theft_settings = AsyncMock(
        return_value=_anti_theft_settings(lift=True)
    )
    coordinator.async_update_listeners = MagicMock()

    assert await coordinator.async_set_anti_theft_settings(lift_alarm=True) is True

    coordinator.device.set_anti_theft_settings.assert_awaited_once_with(
        lift_alarm=True,
        off_map_alarm=None,
        location_reporting=None,
        pin_check=None,
    )
    assert coordinator.lift_alarm_enabled is True
    coordinator.async_update_listeners.assert_called()


async def test_coordinator_keeps_the_anti_theft_settings_when_a_write_is_rejected(
    hass: HomeAssistant, minimal_config_entry
):
    """A rejected write must not leave the switches showing the requested value."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_anti_theft_settings = AsyncMock(return_value=None)
    coordinator.async_update_listeners = MagicMock()
    await _read_settings(coordinator, anti_theft=_anti_theft_settings())

    assert await coordinator.async_set_anti_theft_settings(lift_alarm=True) is False

    assert coordinator.lift_alarm_enabled is False


async def test_coordinator_reports_an_anti_theft_write_the_mower_ignored(
    hass: HomeAssistant, minimal_config_entry
):
    """A mower that answers with the setting unchanged has not taken the write."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    # The mower answers with the off-map alarm still off, and with position
    # reports off as well: the record it holds, not the one that was asked for.
    coordinator.device.set_anti_theft_settings = AsyncMock(
        return_value=_anti_theft_settings(off_map=False, location=False)
    )
    coordinator.async_update_listeners = MagicMock()

    assert await coordinator.async_set_anti_theft_settings(off_map_alarm=True) is False

    # What the mower reports is still what the switches show afterwards.
    assert coordinator.off_map_alarm_enabled is False
    assert coordinator.location_reporting_enabled is False


async def test_coordinator_accepts_an_anti_theft_write_the_mower_took(
    hass: HomeAssistant, minimal_config_entry
):
    """Only the setting that was asked for has to come back changed."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_anti_theft_settings = AsyncMock(
        return_value=_anti_theft_settings(off_map=True, location=True)
    )
    coordinator.async_update_listeners = MagicMock()

    assert await coordinator.async_set_anti_theft_settings(off_map_alarm=True) is True


async def test_coordinator_reads_the_anti_theft_settings_from_the_shared_record(
    hass: HomeAssistant, minimal_config_entry
):
    """The anti-theft settings live in the same record as the charging ones."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.get_device_settings = AsyncMock(return_value={"ATA": [1, 0, 1]})
    coordinator.device.decode_charging_settings = MagicMock(return_value=None)
    coordinator.device.decode_rain_settings = MagicMock(return_value=None)
    coordinator.device.decode_anti_theft_settings = MagicMock(
        return_value=_anti_theft_settings(lift=True)
    )
    coordinator.async_update_listeners = MagicMock()

    await coordinator.async_refresh_device_settings()

    coordinator.device.get_device_settings.assert_awaited_once()
    assert coordinator.supports_anti_theft is True
    assert coordinator.lift_alarm_enabled is True


async def test_coordinator_keeps_the_anti_theft_settings_it_could_not_decode(
    hass: HomeAssistant, minimal_config_entry
):
    """A record the device could not decode must not wipe what is known."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.async_update_listeners = MagicMock()
    await _read_settings(coordinator, anti_theft=_anti_theft_settings())

    await _read_settings(coordinator)

    assert coordinator.supports_anti_theft is True
    assert coordinator.location_reporting_enabled is True


def _schedules(first_enabled=True, second_enabled=False):
    """Build the schedule slots of a map as the device decodes them."""
    return [
        {
            "slot": 0,
            "enabled": first_enabled,
            "name": "Summer",
            "tasks": [{"week_day": "monday", "type": "all_area", "start_time": 480}],
        },
        {"slot": 1, "enabled": second_enabled, "name": None, "tasks": []},
    ]


async def test_coordinator_reads_the_schedules_from_the_device(
    hass: HomeAssistant, minimal_config_entry
):
    """The switches read the slots the device caches, so a fetch has to take them."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.schedules = None
    coordinator.async_update_listeners = MagicMock()

    assert coordinator.schedule_slots == []

    async def _serve_schedules():
        coordinator.device.schedules = _schedules()
        return coordinator.device.schedules

    coordinator.device.refresh_schedules = AsyncMock(side_effect=_serve_schedules)

    assert await coordinator.async_fetch_schedules() is True

    assert coordinator.schedule_slots == [0, 1]
    assert coordinator.schedule_enabled(0) is True
    assert coordinator.schedule_enabled(1) is False
    assert coordinator.schedule(0)["name"] == "Summer"
    coordinator.async_update_listeners.assert_called_once()


async def test_coordinator_reports_a_device_without_schedules(
    hass: HomeAssistant, minimal_config_entry
):
    """A device that cannot report its schedules must not claim to have any."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.schedules = None
    coordinator.device.refresh_schedules = AsyncMock(return_value=None)
    coordinator.async_update_listeners = MagicMock()

    assert await coordinator.async_fetch_schedules() is False
    assert coordinator.schedule_slots == []
    assert coordinator.schedule(0) is None
    assert coordinator.schedule_enabled(0) is None


async def test_coordinator_polls_the_schedules_by_version(
    hass: HomeAssistant, minimal_config_entry
):
    """A poll only asks the device to read the slots back once they changed."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.schedules = _schedules()
    coordinator.device.refresh_changed_schedules = AsyncMock(return_value=_schedules())
    coordinator.device.refresh_schedules = AsyncMock(return_value=_schedules())
    coordinator.async_update_listeners = MagicMock()

    assert await coordinator.async_fetch_schedules(changed_only=True) is True

    coordinator.device.refresh_changed_schedules.assert_awaited_once()
    coordinator.device.refresh_schedules.assert_not_awaited()


async def test_coordinator_switches_a_schedule_on_the_device(
    hass: HomeAssistant, minimal_config_entry
):
    """Switching a slot is delegated to the device, which reports what took effect."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.schedules = _schedules()
    coordinator.device.set_schedule_enabled = AsyncMock(
        return_value=_schedules(first_enabled=False, second_enabled=True)
    )
    coordinator.async_update_listeners = MagicMock()

    assert await coordinator.async_set_schedule_enabled(1, True) is True

    coordinator.device.set_schedule_enabled.assert_awaited_once_with(1, True)
    coordinator.async_update_listeners.assert_called()


async def test_coordinator_reports_a_rejected_schedule_write(
    hass: HomeAssistant, minimal_config_entry
):
    """A rejected write must not read as a switch that took effect."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.schedules = _schedules()
    coordinator.device.set_schedule_enabled = AsyncMock(return_value=None)
    coordinator.async_update_listeners = MagicMock()

    assert await coordinator.async_set_schedule_enabled(1, True) is False


async def test_coordinator_refreshes_the_schedules_when_the_map_changes(
    hass: HomeAssistant, minimal_config_entry
):
    """The schedules are stored per map, so a map switch must re-read them."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.schedules = _schedules()
    coordinator.device.refresh_mowing_preferences = AsyncMock(return_value=True)
    coordinator.device.refresh_zone_mowing_preferences = AsyncMock(return_value={})
    coordinator.device.refresh_schedules = AsyncMock(return_value=_schedules())

    coordinator._handle_device_update(CURRENT_MAP_ID_PROPERTY_NAME, 2)
    await hass.async_block_till_done()

    coordinator.device.refresh_schedules.assert_awaited_once()


@pytest.mark.parametrize(
    ("install_state", "rechecked"),
    [
        (FirmwareInstallState.UPGRADE_SUCCESS, True),
        (FirmwareInstallState.UPGRADING, False),
        (FirmwareInstallState.UPGRADE_FAILED, False),
    ],
)
async def test_coordinator_rechecks_the_firmware_once_an_update_finished(
    hass: HomeAssistant, minimal_config_entry, install_state, rechecked
):
    """A finished update changes the installed version without announcing it."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device.fetch_firmware_status = AsyncMock(return_value=True)

    coordinator._handle_device_update(FIRMWARE_INSTALL_STATE_PROPERTY.name, install_state)
    await hass.async_block_till_done()

    assert coordinator.device.fetch_firmware_status.await_count == (1 if rechecked else 0)


# --- Keeping the position reports coming during a session ---


def _keepalive_coordinator(hass, entry, *, session_active: bool) -> DreameMowerCoordinator:
    coordinator = DreameMowerCoordinator(hass, entry=entry)
    coordinator.device = MagicMock()
    coordinator.device.mowing_session_active = session_active
    coordinator.device.connected = True
    coordinator.device.device_reachable = True
    coordinator.device.cloud_device.get_properties = MagicMock(return_value=None)
    return coordinator


async def test_session_starts_asking_for_the_position(hass: HomeAssistant, minimal_config_entry):
    """A running session asks for the position at once and then every interval."""
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=True)

    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()

    coordinator.device.cloud_device.get_properties.assert_called_once()
    parameters = coordinator.device.cloud_device.get_properties.call_args.args[0]
    assert parameters == [{"siid": 1, "piid": 4}]

    async_fire_time_changed(hass, dt_util.utcnow() + POSE_COVERAGE_REQUEST_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert coordinator.device.cloud_device.get_properties.call_count == 2

    # Asking again while it already runs starts nothing new.
    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()
    assert coordinator.device.cloud_device.get_properties.call_count == 2
    coordinator.async_stop_pose_keepalive()


async def test_a_running_session_reads_the_obstacles_again_now_and_then(hass: HomeAssistant, minimal_config_entry):
    """The mower drops an obstacle it found gone without announcing it."""
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=True)
    coordinator.async_refresh_map_extras = AsyncMock()

    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()
    coordinator.async_refresh_map_extras.assert_not_called()

    async_fire_time_changed(hass, dt_util.utcnow() + POSE_COVERAGE_REQUEST_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done()

    coordinator.async_refresh_map_extras.assert_awaited_once_with(dock=False, stop_points=False)
    coordinator.async_stop_pose_keepalive()


async def test_session_end_stops_asking_for_the_position(hass: HomeAssistant, minimal_config_entry):
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=True)
    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()

    coordinator.device.mowing_session_active = False
    coordinator.async_update_pose_keepalive()
    async_fire_time_changed(hass, dt_util.utcnow() + POSE_COVERAGE_REQUEST_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done()

    coordinator.device.cloud_device.get_properties.assert_called_once()


async def test_no_session_does_not_ask_for_the_position(hass: HomeAssistant, minimal_config_entry):
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=False)

    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()

    coordinator.device.cloud_device.get_properties.assert_not_called()


async def test_unreachable_mower_is_not_asked_for_the_position(hass: HomeAssistant, minimal_config_entry):
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=True)
    coordinator.device.device_reachable = False

    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()

    coordinator.device.cloud_device.get_properties.assert_not_called()
    coordinator.async_stop_pose_keepalive()


async def test_unanswered_position_request_keeps_asking(hass: HomeAssistant, minimal_config_entry):
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=True)
    coordinator.device.cloud_device.get_properties.side_effect = TimeoutError

    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + POSE_COVERAGE_REQUEST_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done()

    assert coordinator.device.cloud_device.get_properties.call_count == 2
    coordinator.async_stop_pose_keepalive()


# --- The running session ---


async def test_session_kind_and_duration_follow_the_session(hass: HomeAssistant, minimal_config_entry, freezer):
    """The kind of task stays known while the mower charges; both go once the session ends."""
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=False)
    coordinator.device.robot_state = {"main_state": 0, "work_mode": None}
    assert coordinator.session_task_mode is None
    assert coordinator.session_minutes is None

    coordinator.device.mowing_session_active = True
    coordinator.device.robot_state = {"main_state": 4, "work_mode": 2}
    coordinator._handle_device_update("property_1_1_task_status", "mowing")
    assert coordinator.session_task_mode == "zone"
    assert coordinator.session_minutes == 0

    # Charging in between: the heartbeat no longer names the task.
    freezer.tick(timedelta(minutes=38, seconds=30))
    coordinator.device.robot_state = {"main_state": 5, "work_mode": None}
    assert coordinator.session_task_mode == "zone"
    assert coordinator.session_minutes == 38

    coordinator.device.mowing_session_active = False
    assert coordinator.session_task_mode is None
    assert coordinator.session_minutes is None

    # The next session counts from its own start.
    coordinator.device.mowing_session_active = True
    coordinator.device.robot_state = {"main_state": 4, "work_mode": 0}
    assert coordinator.session_task_mode == "all_area"
    assert coordinator.session_minutes == 0


async def test_map_feeds_hear_when_the_entry_goes(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    closed = MagicMock()
    coordinator.shutdown_callbacks.append(closed)

    coordinator.async_shutdown_map_feeds()

    closed.assert_called_once_with()
    assert coordinator.shutdown_callbacks == []


# --- The station and the recognised obstacles ---


async def test_map_extras_are_read_and_announced(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.refresh_dock_position = MagicMock(return_value=True)
    coordinator.device.refresh_mower_position = MagicMock(return_value=False)
    coordinator.device.refresh_obstacles = MagicMock(return_value=False)
    coordinator.device.refresh_stop_points = MagicMock(return_value=False)
    listener = MagicMock()
    coordinator.async_add_listener(listener)

    await coordinator.async_refresh_map_extras()

    coordinator.device.refresh_dock_position.assert_called_once_with()
    coordinator.device.refresh_mower_position.assert_called_once_with()
    coordinator.device.refresh_obstacles.assert_called_once_with()
    coordinator.device.refresh_stop_points.assert_called_once_with()
    listener.assert_called_once_with()


async def test_map_extras_read_only_what_is_asked(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()

    await coordinator.async_refresh_map_extras(dock=False)

    coordinator.device.refresh_dock_position.assert_not_called()
    coordinator.device.refresh_obstacles.assert_called_once_with()


async def test_failing_map_extras_do_not_raise(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.refresh_dock_position = MagicMock(side_effect=TimeoutError)

    await coordinator.async_refresh_map_extras()

    coordinator.device.refresh_obstacles.assert_called_once_with()


async def test_mower_back_online_sets_the_entry_up_again(hass: HomeAssistant, minimal_config_entry):
    """Setup skipped the reads of an offline mower; they are made once it is back."""
    minimal_config_entry.add_to_hass(hass)
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.reload_when_online = True

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        coordinator._handle_device_update("online", True)
        coordinator._handle_device_update("online", True)
        await hass.async_block_till_done()

    schedule_reload.assert_called_once_with(minimal_config_entry.entry_id)
    assert coordinator.reload_when_online is False


async def test_mower_online_without_skipped_reads_is_left_alone(hass: HomeAssistant, minimal_config_entry):
    minimal_config_entry.add_to_hass(hass)
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        coordinator._handle_device_update("online", True)
        await hass.async_block_till_done()

    schedule_reload.assert_not_called()


async def test_offline_mower_is_not_asked_for_map_extras(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.online = False

    await coordinator.async_refresh_map_extras()
    await coordinator._async_refresh_preferences_on_map_change()

    coordinator.device.refresh_dock_position.assert_not_called()
    coordinator.device.refresh_obstacles.assert_not_called()
    coordinator.device.refresh_mowing_preferences.assert_not_called()


async def test_station_and_obstacles_are_read_again_when_the_mower_says_so(
    hass: HomeAssistant, minimal_config_entry
):
    from custom_components.dreame_mower.dreame.const import SERVICE1_PROPERTY_51
    from custom_components.dreame_mower.dreame.property.property_misc import PROPERTY_1_1_TASK_STATUS_NAME

    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.online = True
    coordinator.device.mowing_session_active = False
    coordinator.async_refresh_map_extras = AsyncMock()

    coordinator._handle_device_update(SERVICE1_PROPERTY_51.name, True)
    await hass.async_block_till_done()
    coordinator.async_refresh_map_extras.assert_awaited_once_with(obstacles=False)

    coordinator.async_refresh_map_extras.reset_mock()
    coordinator._handle_device_update(PROPERTY_1_1_TASK_STATUS_NAME, "idle")
    await hass.async_block_till_done()
    coordinator.async_refresh_map_extras.assert_awaited_once_with(dock=False)

    coordinator.async_refresh_map_extras.reset_mock()
    coordinator._handle_device_update(CURRENT_MAP_ID_PROPERTY_NAME, 2)
    await hass.async_block_till_done()
    coordinator.async_refresh_map_extras.assert_any_await(dock=False)


async def test_running_session_reads_the_trail_back(hass: HomeAssistant, minimal_config_entry):
    from custom_components.dreame_mower.dreame.property.property_misc import PROPERTY_1_1_TASK_STATUS_NAME

    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.online = True
    coordinator.device.mowing_session_active = True
    coordinator.device.refresh_trail = MagicMock(return_value=True)
    coordinator.async_refresh_map_extras = AsyncMock()

    coordinator._handle_device_update(PROPERTY_1_1_TASK_STATUS_NAME, "paused")
    await hass.async_block_till_done()
    coordinator.device.refresh_trail.assert_called_once_with()

    coordinator.device.refresh_trail.reset_mock()
    coordinator.device.mowing_session_active = False
    coordinator._handle_device_update(PROPERTY_1_1_TASK_STATUS_NAME, "idle")
    await hass.async_block_till_done()
    coordinator.device.refresh_trail.assert_not_called()


async def test_only_one_trail_read_runs_at_a_time(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    pending = hass.loop.create_future()
    coordinator._trail_read = pending  # a read still running
    coordinator._async_refresh_trail = AsyncMock()

    coordinator._async_schedule_trail_read()
    await hass.async_block_till_done()
    coordinator._async_refresh_trail.assert_not_called()

    pending.set_result(None)
    coordinator._async_schedule_trail_read()
    await hass.async_block_till_done()
    coordinator._async_refresh_trail.assert_called_once_with()


async def test_no_trail_read_for_a_robot_without_a_lawn(hass: HomeAssistant, minimal_config_entry):
    from custom_components.dreame_mower.config_flow import DEVICE_TYPE_SWBOT

    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.online = True
    with patch.object(type(coordinator), "device_type", new=DEVICE_TYPE_SWBOT):
        await coordinator._async_refresh_trail()

    coordinator.device.refresh_trail.assert_not_called()


async def test_entities_waiting_for_the_reads_are_added_once_they_are_done(
    hass: HomeAssistant, minimal_config_entry
):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    early = MagicMock()
    coordinator.async_when_probed(early)
    early.assert_not_called()

    coordinator.async_mark_probed()
    early.assert_called_once_with()

    # Platforms set up after the reads add their entities at once.
    late = MagicMock()
    coordinator.async_when_probed(late)
    late.assert_called_once_with()


async def test_entities_waiting_for_the_reads_are_dropped_when_the_entry_goes(
    hass: HomeAssistant, minimal_config_entry
):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    waiting = MagicMock()
    coordinator.async_when_probed(waiting)

    coordinator.async_cancel_probe()
    coordinator.async_mark_probed()
    coordinator.async_when_probed(waiting)

    waiting.assert_not_called()


def _asked_for_position(coordinator) -> int:
    return sum(
        call.args[0] == [{"siid": 1, "piid": 4}] for call in coordinator.device.cloud_device.get_properties.call_args_list
    )


@pytest.mark.parametrize(
    "robot_state,online,asked",
    [
        ({"docking": "finish_docking", "location": "located"}, True, True),
        ({"docking": "pause_docking", "location": "located"}, True, True),
        ({"docking": "out_of_station", "location": "relocating"}, True, True),
        ({"docking": "out_of_station", "location": "located"}, True, False),
        ({"docking": "in_station", "location": "idle"}, True, False),
        ({"docking": "finish_docking", "location": "located"}, False, False),
        (None, True, False),
    ],
)
async def test_the_position_keeps_coming_while_the_mower_drives_without_a_task(
    hass: HomeAssistant, minimal_config_entry, robot_state, online, asked
):
    """Outside a task the mower reports its position on its way home or while it finds it, when asked to."""
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=False)
    coordinator.device.robot_state = robot_state
    coordinator.device.online = online

    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()

    assert _asked_for_position(coordinator) == int(asked)
    assert (coordinator._pose_keepalive is not None) == asked
    coordinator.async_stop_pose_keepalive()


async def test_back_in_the_station_the_position_is_no_longer_asked_for(hass: HomeAssistant, minimal_config_entry):
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=False)
    coordinator.device.robot_state = {"docking": "finish_docking", "location": "located"}
    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()

    coordinator.device.robot_state = {"docking": "in_station", "location": "idle"}
    coordinator.async_update_pose_keepalive()
    async_fire_time_changed(hass, dt_util.utcnow() + POSE_COVERAGE_REQUEST_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done()

    assert _asked_for_position(coordinator) == 1
    assert coordinator._pose_keepalive is None


async def test_a_mower_going_offline_on_its_way_home_is_no_longer_asked(hass: HomeAssistant, minimal_config_entry):
    coordinator = _keepalive_coordinator(hass, minimal_config_entry, session_active=False)
    coordinator.device.robot_state = {"docking": "finish_docking", "location": "located"}
    coordinator.async_update_pose_keepalive()
    await hass.async_block_till_done()

    # Its last state stays while it is gone.
    coordinator.device.online = False
    coordinator.async_update_pose_keepalive()
    async_fire_time_changed(hass, dt_util.utcnow() + POSE_COVERAGE_REQUEST_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done()

    assert _asked_for_position(coordinator) == 1
    assert coordinator._pose_keepalive is None


def test_the_map_wide_mowing_settings_are_read_from_area_zero(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.mowing_settings = {0: {"obstacle_height": 10}, 3: {"obstacle_height": 20, "turning_method": "efficient"}}

    assert coordinator.map_mowing_setting("obstacle_height") == 10
    assert coordinator.supports_mowing_setting("obstacle_height") is True
    assert coordinator.supports_mowing_setting("turning_method") is False
    assert coordinator.map_mowing_setting("turning_method") is None


@pytest.mark.parametrize("model,supported", [("dreame.mower.g2408", True), ("mova.mower.g2529d", False)])
def test_only_dreame_mowers_are_told_where_to_start(hass: HomeAssistant, minimal_config_entry, model, supported):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    with patch.object(type(coordinator), "device_model", new_callable=PropertyMock, return_value=model):
        assert coordinator.supports_start_from_stop_point is supported


def test_the_consumables_tell_how_worn_each_part_is(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    assert coordinator.consumables is None

    # Minutes used: blades 56.5 h of 100 h, brush 103.3 h of 500 h, maintenance 1 h of 60 h.
    coordinator._consumable_values = [3390, 6198, 60]

    assert coordinator.consumables == [
        {"item": "blade", "health": 43.5, "used_hours": 56.5, "remaining_hours": 43.5, "total_hours": 100.0},
        {"item": "brush", "health": 79.3, "used_hours": 103.3, "remaining_hours": 396.7, "total_hours": 500.0},
        {"item": "robot", "health": 98.3, "used_hours": 1.0, "remaining_hours": 59.0, "total_hours": 60.0},
    ]


def test_a_worn_out_part_counts_as_no_life_left(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator._consumable_values = [9000, 0, 60]

    assert coordinator.consumables[0]["health"] == 0
    assert coordinator.consumables[0]["remaining_hours"] == 0
    assert coordinator.consumables[1]["health"] == 100


async def test_resetting_a_consumable_reads_the_counters_again(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.reset_consumable_counter = AsyncMock()
    coordinator.device.get_consumable_status = AsyncMock(return_value={"values": [0, 6198, 60]})

    await coordinator.async_reset_consumable("blade")

    coordinator.device.reset_consumable_counter.assert_awaited_once_with("blade")
    assert coordinator.consumables[0]["health"] == 100


async def test_a_reset_the_mower_did_not_take_is_reported(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.reset_consumable_counter = AsyncMock()
    coordinator.device.get_consumable_status = AsyncMock(return_value={"values": [3390, 6198, 60]})

    with pytest.raises(ValueError, match="kept counting the blade"):
        await coordinator.async_reset_consumable("blade")


async def test_a_reset_stands_when_reading_the_counters_back_fails(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.reset_consumable_counter = AsyncMock()
    coordinator.device.get_consumable_status = AsyncMock(side_effect=TimeoutError("slow link"))

    await coordinator.async_reset_consumable("brush")

    coordinator.device.reset_consumable_counter.assert_awaited_once_with("brush")


async def test_a_setting_is_written_and_the_record_read_back(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.get_device_settings = AsyncMock(return_value={"CLS": 0, "FDP": 1})
    coordinator.device.decode_charging_settings = MagicMock(return_value=None)
    coordinator.device.decode_rain_settings = MagicMock(return_value=None)
    coordinator.device.decode_anti_theft_settings = MagicMock(return_value=None)
    await coordinator.async_refresh_device_settings()
    assert coordinator.supports_device_setting("CLS") and not coordinator.supports_device_setting("LIT")

    coordinator.device.set_device_setting = AsyncMock(return_value={"value": 1})
    coordinator.device.get_device_settings = AsyncMock(return_value={"CLS": 1, "FDP": 1})
    assert await coordinator.async_set_device_setting("CLS", {"value": 1}) is True
    coordinator.device.set_device_setting.assert_awaited_once_with("CLS", {"value": 1})
    assert coordinator.device_setting("CLS") == 1

    coordinator.device.set_device_setting = AsyncMock(return_value=None)
    assert await coordinator.async_set_device_setting("CLS", {"value": 0}) is False


def test_a_setting_kept_in_another_form_is_not_offered(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator._device_settings = {"PROT": [0, 1], "PATH": False, "CLS": 0}

    assert coordinator.supports_device_setting("PROT") is False
    assert coordinator.supports_device_setting("PATH") is True
    assert coordinator.supports_device_setting("CLS") is True
    assert coordinator.supports_device_setting("LIT") is False



async def test_a_setting_the_mower_kept_is_reported(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.set_device_setting = AsyncMock(return_value={"value": 0})

    assert await coordinator.async_set_device_setting("CLS", {"value": 1}) is False


async def test_a_written_setting_stands_when_reading_the_record_back_fails(hass: HomeAssistant, minimal_config_entry):
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator._device_settings = {"CLS": 0}
    coordinator.device.set_device_setting = AsyncMock(return_value={"value": 1})
    coordinator.device.get_device_settings = AsyncMock(side_effect=TimeoutError("slow link"))

    assert await coordinator.async_set_device_setting("CLS", {"value": 1}) is True
    assert coordinator.device_setting("CLS") == 1


def _settings_coordinator(hass, entry, record):
    coordinator = DreameMowerCoordinator(hass, entry=entry)
    coordinator.device = MagicMock()
    coordinator._device_settings = dict(record)
    coordinator.device.set_device_setting = AsyncMock(return_value={})
    coordinator.device.get_device_settings = AsyncMock(return_value=None)
    return coordinator


async def test_a_time_window_keeps_what_is_left_out(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"DND": [0, 1080, 480]})
    assert coordinator.time_window_setting("DND") == {"enabled": False, "start": 1080, "end": 480}

    assert await coordinator.async_set_time_window_setting("DND", enabled=True) is True
    coordinator.device.set_device_setting.assert_awaited_once_with("DND", {"value": 1, "time": [1080, 480]})
    assert coordinator.device_setting("DND") == [1, 1080, 480]

    await coordinator.async_set_time_window_setting("DND", start=1260)
    coordinator.device.set_device_setting.assert_awaited_with("DND", {"value": 1, "time": [1260, 480]})


async def test_a_time_window_must_start_and_end_apart(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"LOW": [0, 1320, 480]})

    with pytest.raises(ValueError, match="different times"):
        await coordinator.async_set_time_window_setting("LOW", start=480)
    with pytest.raises(ValueError, match="does not offer"):
        await coordinator.async_set_time_window_setting("DND", enabled=True)
    coordinator.device.set_device_setting.assert_not_called()


async def test_the_stop_point_setting_is_written_as_the_mower_takes_it(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"BP": [1, 3]})
    coordinator.device.refresh_stop_points = MagicMock(return_value=True)
    assert coordinator.stop_point_setting == {"enabled": True, "days": 3}

    assert await coordinator.async_set_stop_point_setting(days=5) is True
    coordinator.device.set_device_setting.assert_awaited_once_with("BP", {"on": True, "day": 5})
    assert coordinator.device_setting("BP") == [1, 5]
    # Switching it off drops the mower's stop points, so they are read again.
    coordinator.device.refresh_stop_points.assert_called_once()

    with pytest.raises(ValueError, match="1 to 7 days"):
        await coordinator.async_set_stop_point_setting(days=9)


def test_the_time_zone_is_read_from_the_record(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"TIME": "Europe/Berlin"})
    assert coordinator.time_zone == "Europe/Berlin"
    coordinator._device_settings = {"TIME": ""}
    assert coordinator.time_zone is None



@pytest.mark.parametrize("start", [0, 1440])
async def test_a_window_does_not_start_at_midnight(hass: HomeAssistant, minimal_config_entry, start):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"DND": [0, 1080, 480]})

    with pytest.raises(ValueError, match="00:01 and 23:59"):
        await coordinator.async_set_time_window_setting("DND", start=start)


async def test_a_setting_answered_with_its_whole_record_is_checked_by_its_first_part(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"LOW": [0, 1320, 480]})
    coordinator.device.set_device_setting = AsyncMock(return_value={"value": [1, 1320, 480]})
    assert await coordinator.async_set_time_window_setting("LOW", enabled=True) is True

    coordinator.device.set_device_setting = AsyncMock(return_value={"value": [0, 1320, 480]})
    assert await coordinator.async_set_time_window_setting("LOW", enabled=True) is False


async def test_the_lights_keep_what_is_left_out_and_the_fill_light(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"LIT": [0, 0, 1440, 0, 1, 0, 1, 1]})
    assert coordinator.light_setting == {
        "custom_period": False, "start": 0, "end": 1440,
        "standby": False, "working": True, "charging": False, "error": True,
    }

    assert await coordinator.async_set_light_setting(charging=True) is True
    coordinator.device.set_device_setting.assert_awaited_once_with(
        "LIT", {"value": 0, "time": [0, 1440], "light": [0, 1, 1, 1], "fill": 1}
    )
    assert coordinator.device_setting("LIT") == [0, 0, 1440, 0, 1, 1, 1, 1]

    await coordinator.async_set_light_setting(custom_period=True, start=1200, end=360)
    coordinator.device.set_device_setting.assert_awaited_with(
        "LIT", {"value": 1, "time": [1200, 360], "light": [0, 1, 1, 1], "fill": 1}
    )

    with pytest.raises(ValueError, match="different times"):
        await coordinator.async_set_light_setting(start=360)


async def test_a_light_record_without_a_fill_light_is_written_without_one(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"LIT": [1, 1200, 360, 1, 1, 1, 1]})
    await coordinator.async_set_light_setting(error=False)
    coordinator.device.set_device_setting.assert_awaited_once_with(
        "LIT", {"value": 1, "time": [1200, 360], "light": [1, 1, 1, 0]}
    )

    coordinator._device_settings = {}
    assert coordinator.light_setting is None
    with pytest.raises(ValueError, match="does not offer"):
        await coordinator.async_set_light_setting(error=True)


async def test_the_human_presence_alert_keeps_what_is_left_out(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"REC": [0, 1, 1, 1, 1, 1, 1, 0, 3]})
    assert coordinator.human_presence_setting == {
        "enabled": False, "sensitivity": "medium",
        "standby": True, "mowing": True, "returning": True, "patrolling": True,
        "voice": True, "photo": False, "interval": 3,
    }

    assert await coordinator.async_set_human_presence_setting(enabled=True, sensitivity="high", returning=False, interval=10) is True
    coordinator.device.set_device_setting.assert_awaited_once_with(
        "REC", {"value": 1, "sen": 2, "mode": [1, 1, 0, 1], "report": [1, 0, 10]}
    )
    assert coordinator.device_setting("REC") == [1, 2, 1, 1, 0, 1, 1, 0, 10]

    with pytest.raises(ValueError, match="sensitivity"):
        await coordinator.async_set_human_presence_setting(sensitivity="extreme")
    with pytest.raises(ValueError, match="minutes"):
        await coordinator.async_set_human_presence_setting(interval=5)


async def test_a_mower_without_an_alert_interval_gets_none(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"REC": [1, 0, 1, 0, 0, 0, 1, 1]})
    assert coordinator.human_presence_setting["interval"] is None

    await coordinator.async_set_human_presence_setting(photo=False)
    coordinator.device.set_device_setting.assert_awaited_once_with(
        "REC", {"value": 1, "sen": 0, "mode": [1, 0, 0, 0], "report": [1, 0]}
    )
    with pytest.raises(ValueError, match="does not space"):
        await coordinator.async_set_human_presence_setting(interval=10)


async def test_the_robot_voice_writes_the_volume_and_the_prompts(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"VOL": 10, "VOICE": [0, 0, 1, 1], "LANG": [1, 2]})
    assert coordinator.robot_voice_setting == {
        "volume": 10,
        "prompts": {"regular": False, "work_status": False, "special_status": True, "error_status": True},
        "language": "German",
    }

    assert await coordinator.async_set_robot_voice(volume=40) is True
    coordinator.device.set_device_setting.assert_awaited_once_with("VOL", {"value": 40})

    coordinator.device.set_device_setting.reset_mock()
    assert await coordinator.async_set_robot_voice(regular=True) is True
    coordinator.device.set_device_setting.assert_awaited_once_with("VOICE", {"value": [1, 0, 1, 1]})
    assert coordinator.device_setting("VOICE") == [1, 0, 1, 1]

    with pytest.raises(ValueError, match="0 to 100"):
        await coordinator.async_set_robot_voice(volume=120)


async def test_the_prompts_wait_for_a_volume_the_mower_refused(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"VOL": 10, "VOICE": [0, 0, 1, 1]})
    coordinator.device.set_device_setting = AsyncMock(return_value={"value": 10})

    assert await coordinator.async_set_robot_voice(volume=40, regular=True) is False
    coordinator.device.set_device_setting.assert_awaited_once_with("VOL", {"value": 40})


async def test_an_odd_stored_value_does_not_block_other_changes(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {
        "REC": [0, 7, 1, 1, 1, 1, 1, 0, 0, 5], "LIT": [0, 0, 0, 0, 1, 0, 1, 1],
    })

    assert await coordinator.async_set_human_presence_setting(enabled=True) is True
    coordinator.device.set_device_setting.assert_awaited_once_with(
        "REC", {"value": 1, "sen": 7, "mode": [1, 1, 1, 1], "report": [1, 0, 0]}
    )
    # A slot past the known ones is kept.
    assert coordinator.device_setting("REC") == [1, 7, 1, 1, 1, 1, 1, 0, 0, 5]

    assert await coordinator.async_set_light_setting(charging=True) is True
    with pytest.raises(ValueError, match="different times"):
        await coordinator.async_set_light_setting(end=0)


async def test_the_robot_voice_refuses_before_writing_anything(hass: HomeAssistant, minimal_config_entry):
    coordinator = _settings_coordinator(hass, minimal_config_entry, {"VOL": 10})
    with pytest.raises(ValueError, match="voice prompt"):
        await coordinator.async_set_robot_voice(volume=40, regular=True)

    coordinator._device_settings = {"VOICE": [0, 0, 1, 1]}
    with pytest.raises(ValueError, match="volume setting"):
        await coordinator.async_set_robot_voice(volume=40)
    coordinator.device.set_device_setting.assert_not_called()
