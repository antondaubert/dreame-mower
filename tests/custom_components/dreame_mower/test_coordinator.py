"""Test the Dreame Mower coordinator."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dreame_mower.coordinator import DreameMowerCoordinator
from custom_components.dreame_mower.const import DOMAIN
from custom_components.dreame_mower.config_flow import CONF_ACCOUNT_TYPE, CONF_COUNTRY, CONF_DID, CONF_MAC, CONF_MODEL, CONF_SERIAL
from custom_components.dreame_mower.dreame.const import (
    CURRENT_MAP_ID_PROPERTY_NAME,
    MowingPreferenceMode,
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

async def test_coordinator_refreshes_the_cutting_height_when_the_map_changes(
    hass: HomeAssistant, minimal_config_entry
):
    """The height is stored per map, so a map switch must re-read it."""
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device.refresh_cutting_height = AsyncMock(return_value=5.0)

    coordinator._handle_device_update(CURRENT_MAP_ID_PROPERTY_NAME, 2)
    await hass.async_block_till_done()

    coordinator.device.refresh_cutting_height.assert_awaited_once()


async def test_coordinator_skips_the_cutting_height_refresh_for_fixed_height_models(
    hass: HomeAssistant, minimal_config_entry
):
    """Models without an adjustable height should not be queried for it."""
    minimal_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        minimal_config_entry,
        data={**minimal_config_entry.data, CONF_MODEL: "mova.mower.g2405c"},
    )
    coordinator = DreameMowerCoordinator(hass, entry=minimal_config_entry)
    coordinator.device.refresh_cutting_height = AsyncMock(return_value=None)

    coordinator._handle_device_update(CURRENT_MAP_ID_PROPERTY_NAME, 2)
    await hass.async_block_till_done()

    coordinator.device.refresh_cutting_height.assert_not_awaited()


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
    await coordinator.async_fetch_cutting_heights()
    assert device.refresh_cutting_height.await_count == 1
    assert device.refresh_zone_cutting_heights.await_count == 2

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
