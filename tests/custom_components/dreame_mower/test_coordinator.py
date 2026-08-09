"""Test the Dreame Mower coordinator."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dreame_mower.coordinator import DreameMowerCoordinator
from custom_components.dreame_mower.const import DOMAIN
from custom_components.dreame_mower.config_flow import CONF_ACCOUNT_TYPE, CONF_COUNTRY, CONF_DID, CONF_MAC, CONF_MODEL, CONF_SERIAL
from custom_components.dreame_mower.dreame.const import (
    CURRENT_MAP_ID_PROPERTY_NAME,
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


async def test_coordinator_async_update_data(hass: HomeAssistant, minimal_config_entry):
    """Test coordinator's _async_update_data method returns expected structure."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    
    # Call the update data method directly
    data = await coordinator._async_update_data()
    
    # Verify returned data structure
    assert data is not None
    assert isinstance(data, dict)
    
    # Check all required fields are present
    required_fields = ["name", "connected", "last_update", "mac", "model", "serial", "firmware", "manufacturer"]
    for field in required_fields:
        assert field in data, f"Field {field} missing from coordinator data"
    
    # Verify data values from config entry
    assert data["name"] == "Test Mower"
    assert data["mac"] == "11:22:33:44:55:66"
    assert data["model"] == "dreame.mower.test789"
    assert data["serial"] == "MIN123456"
    assert data["manufacturer"] == "Dreametech™"
    
    # Verify default/placeholder values
    assert data["connected"] is False
    assert data["last_update"] is not None  # Should have a timestamp from device initialization
    assert data["firmware"] == "Unknown"


async def test_coordinator_initial_data_fetch(hass: HomeAssistant, minimal_config_entry):
    """Test coordinator can fetch initial data without errors."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)

    # Call _async_update_data directly to avoid the ConfigEntryState.SETUP_IN_PROGRESS
    coordinator.data = await coordinator._async_update_data()

    # Data should be available after first refresh
    assert coordinator.data is not None
    assert coordinator.data["name"] == "Test Mower"


async def test_coordinator_with_required_config_data(hass: HomeAssistant):
    """Test coordinator requires all essential config data."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Mower Required Data",
        data={
            "name": "Test Required Mower",
            CONF_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_MODEL: "dreame.mower.required123",
            CONF_SERIAL: "REQ123456",
            CONF_DID: "required_device_789",
            CONF_USERNAME: "test_required_user",
            CONF_PASSWORD: "test_required_password",
            CONF_ACCOUNT_TYPE: "dreame",
            CONF_COUNTRY: "US",
        },
        entry_id="test_required_entry",
    )
    
    coordinator = DreameMowerCoordinator(hass, entry=config_entry)
    data = await coordinator._async_update_data()
    
    # Should use provided name from config
    assert data["name"] == "Test Required Mower"

async def test_coordinator_refreshes_the_mowing_preferences_when_the_map_changes(
    hass: HomeAssistant, minimal_config_entry
):
    """The mowing settings are stored per map, so a map switch must re-read them."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device.refresh_mowing_preferences = AsyncMock(return_value=True)
    coordinator.device.refresh_zone_mowing_preferences = AsyncMock(return_value={})

    coordinator._handle_device_update(CURRENT_MAP_ID_PROPERTY_NAME, 2)
    await hass.async_block_till_done()

    coordinator.device.refresh_mowing_preferences.assert_awaited_once()
    coordinator.device.refresh_zone_mowing_preferences.assert_awaited_once()


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
    device.refresh_cutting_height = AsyncMock(return_value=4.0)
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
    await coordinator.async_fetch_cutting_height()
    assert device.refresh_cutting_height.await_count == 1
    assert device.refresh_zone_cutting_heights.await_count == 1

    # Every one of those calls has to push the new state to the entities.
    assert coordinator.async_update_listeners.call_count == 4


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
    device.zone_edge_mowing_settings = {2: {"edge_mowing_safe": False}}
    device.set_edge_mowing_settings = AsyncMock(return_value=True)
    coordinator.device = device
    coordinator.async_update_listeners = MagicMock()

    assert coordinator.supports_edge_mowing_settings is True
    assert coordinator.supports_safe_edge_mowing is True
    assert coordinator.edge_mowing_auto is True
    assert coordinator.edge_blade_offset is False
    assert coordinator.edge_mowing_safe is True
    assert coordinator.zone_edge_mowing_settings == {2: {"edge_mowing_safe": False}}

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


async def test_coordinator_reports_edge_settings_the_device_does_not_keep(
    hass: HomeAssistant, minimal_config_entry
):
    """A setting missing from the record is unknown, and gets no switch."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.edge_mowing_settings = {"edge_mowing_auto": True}

    assert coordinator.supports_edge_mowing_settings is True
    assert coordinator.supports_safe_edge_mowing is False
    assert coordinator.edge_mowing_safe is None


async def test_coordinator_reports_no_edge_settings_before_they_are_read(
    hass: HomeAssistant, minimal_config_entry
):
    """Until the record has been read there is nothing to build switches from."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device = MagicMock()
    coordinator.device.edge_mowing_settings = None

    assert coordinator.supports_edge_mowing_settings is False
    assert coordinator.supports_safe_edge_mowing is False
    assert coordinator.edge_mowing_auto is None


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
    coordinator.device.get_charging_settings = AsyncMock(return_value=_charging_settings())
    coordinator.async_update_listeners = MagicMock()

    assert coordinator.supports_charging_period is False
    assert coordinator.charging_period_enabled is None
    assert coordinator.charging_period_start_minutes is None
    assert coordinator.charging_period_end_minutes is None

    assert await coordinator.async_fetch_charging_settings() is True

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
    coordinator.device.get_charging_settings = AsyncMock(return_value=None)

    assert await coordinator.async_fetch_charging_settings() is False
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
    coordinator.device.get_charging_settings = AsyncMock(return_value=_charging_settings())
    coordinator.device.set_charging_period = AsyncMock(return_value=None)
    await coordinator.async_fetch_charging_settings()

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
    coordinator.device.get_rain_settings = AsyncMock(return_value=_rain_settings())
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.async_update_listeners = MagicMock()

    assert coordinator.supports_rain_protection is False
    assert coordinator.rain_protection_enabled is None
    assert coordinator.rain_delay_hours is None

    assert await coordinator.async_fetch_rain_settings() is True

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
    coordinator.device.get_rain_settings = AsyncMock(return_value=None)

    assert await coordinator.async_fetch_rain_settings() is False
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
    coordinator.device.get_rain_settings = AsyncMock(return_value=_rain_settings())
    coordinator.device.set_rain_protection = AsyncMock(return_value=None)
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    await coordinator.async_fetch_rain_settings()

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
    coordinator.device.get_rain_settings = AsyncMock(return_value=_rain_settings())
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.async_update_listeners = MagicMock()
    await coordinator.async_fetch_rain_settings()
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
    coordinator.device.get_rain_settings = AsyncMock(return_value=_rain_settings())
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.async_update_listeners = MagicMock()
    await coordinator.async_fetch_rain_settings()
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
    coordinator.device.get_rain_settings = AsyncMock(return_value=_rain_settings())
    coordinator.device.get_rain_protection_end_timestamp = AsyncMock(return_value=0)
    coordinator.async_update_listeners = MagicMock()
    await coordinator.async_fetch_rain_settings()

    coordinator.device.get_device_settings = AsyncMock(return_value={"BAT": []})
    coordinator.device.decode_rain_settings = MagicMock(return_value=None)
    coordinator.device.decode_charging_settings = MagicMock(return_value=None)

    await coordinator.async_refresh_device_settings()

    assert coordinator.rain_delay_hours == 8
