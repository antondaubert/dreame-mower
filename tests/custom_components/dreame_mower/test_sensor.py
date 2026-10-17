"""Test minimal sensor entities."""

from datetime import datetime, timezone

import pytest
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dreame_mower.const import DOMAIN
from custom_components.dreame_mower.coordinator import DreameMowerCoordinator
from custom_components.dreame_mower.sensor import (
    DreameMowerAccountSensor,
    DreameMowerBatterySensor,
    DreameMowerStatusSensor,
    DreameMowerProgressSensor,
    DreameMowerRainProtectionEndSensor,
)
from custom_components.dreame_mower.config_flow import (
    CONF_ACCOUNT_TYPE,
    CONF_COUNTRY,
    CONF_MAC,
    CONF_DID,
)
from custom_components.dreame_mower.dreame.const import DeviceStatus


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator for testing."""
    coordinator = MagicMock(spec=DreameMowerCoordinator)
    coordinator.device_connected = True
    coordinator.device_online = True
    coordinator.last_update_success = True
    coordinator.device_mac = "aa:bb:cc:dd:ee:ff"
    coordinator.device_battery_percent = 85  # Default battery level
    coordinator.device_status = "Charging complete"  # Default status
    coordinator.device_status_code = DeviceStatus.CHARGING_COMPLETE
    coordinator.mowing_progress_percent = None
    coordinator.current_area_sqm = None
    coordinator.total_area_sqm = None
    return coordinator


@pytest.fixture
def device_id():
    """Return a test device ID."""
    return "test_device_123"


async def test_battery_sensor_initialization(mock_coordinator, device_id):
    """Test battery sensor initialization."""
    sensor = DreameMowerBatterySensor(mock_coordinator)
    
    assert sensor.coordinator == mock_coordinator
    assert sensor._entity_description_key == "battery"
    assert sensor.unique_id == "aa:bb:cc:dd:ee:ff_battery"


async def test_battery_sensor_native_value_available(mock_coordinator, device_id):
    """Test battery sensor returns value when available."""
    mock_coordinator.device_connected = True
    mock_coordinator.last_update_success = True
    
    # Configure the mock to return the battery percentage
    mock_coordinator.device_battery_percent = 85
    
    sensor = DreameMowerBatterySensor(mock_coordinator)
    
    assert sensor.available is True
    assert sensor.native_value == 85


async def test_battery_sensor_native_value_unavailable(mock_coordinator, device_id):
    """Test battery sensor returns None when unavailable."""
    mock_coordinator.device_connected = False
    mock_coordinator.last_update_success = False
    
    # Configure the mock to return None for battery percentage
    mock_coordinator.device_battery_percent = None
    
    sensor = DreameMowerBatterySensor(mock_coordinator)
    
    assert sensor.available is False
    assert sensor.native_value is None


async def test_status_sensor_initialization(mock_coordinator, device_id):
    """Test status sensor initialization."""
    sensor = DreameMowerStatusSensor(mock_coordinator)
    
    assert sensor.coordinator == mock_coordinator
    assert sensor._entity_description_key == "status"
    assert sensor.unique_id == "aa:bb:cc:dd:ee:ff_status"


async def test_status_sensor_native_value_available(mock_coordinator, device_id):
    """Test status sensor returns status when available."""
    mock_coordinator.device_connected = True
    mock_coordinator.last_update_success = True
    
    sensor = DreameMowerStatusSensor(mock_coordinator)
    
    assert sensor.available is True
    assert sensor.native_value == "Charging complete"


async def test_status_sensor_is_unavailable_while_the_mower_is(mock_coordinator, device_id):
    """An unreachable mower leaves the status to Home Assistant's unavailable."""
    mock_coordinator.device_connected = False
    mock_coordinator.last_update_success = False
    
    sensor = DreameMowerStatusSensor(mock_coordinator)
    
    assert sensor.available is False


async def test_progress_sensor_value(mock_coordinator):
    """Test progress sensor returns rounded progress value."""
    mock_coordinator.mowing_progress_percent = 55.678
    mock_coordinator.current_area_sqm = 120.5
    mock_coordinator.total_area_sqm = 220.0

    sensor = DreameMowerProgressSensor(mock_coordinator)
    assert sensor.native_value == 55.7
    assert sensor.device_class is None
    assert sensor.native_unit_of_measurement == "%"
    assert sensor.extra_state_attributes == {
        "current_area_sqm": 120.5,
        "total_area_sqm": 220.0,
        "progress_percent": 55.7,
    }


async def test_progress_sensor_none(mock_coordinator):
    """Test progress sensor returns None when no progress data."""
    mock_coordinator.mowing_progress_percent = None
    sensor = DreameMowerProgressSensor(mock_coordinator)
    assert sensor.native_value is None



async def test_rain_protection_end_sensor_reports_when_mowing_resumes(mock_coordinator):
    """While rain holds the mower back the sensor names the time it may resume."""
    resumes_at = datetime(2026, 8, 8, 18, 0, tzinfo=timezone.utc)
    mock_coordinator.rain_protection_active = True
    mock_coordinator.rain_protection_end_time = resumes_at

    sensor = DreameMowerRainProtectionEndSensor(mock_coordinator)

    assert sensor.unique_id == "aa:bb:cc:dd:ee:ff_rain_protection_end"
    assert sensor.native_value == resumes_at


async def test_rain_protection_end_sensor_is_unknown_while_the_mower_is_free(mock_coordinator):
    """An end time that has passed must not linger as the sensor state."""
    mock_coordinator.rain_protection_active = False
    mock_coordinator.rain_protection_end_time = datetime(2026, 8, 8, 6, 0, tzinfo=timezone.utc)

    sensor = DreameMowerRainProtectionEndSensor(mock_coordinator)

    assert sensor.native_value is None


async def test_account_sensor_names_the_account_of_the_connection(mock_coordinator):
    """The sensor states which account the device is reached through."""
    mock_coordinator.account_username = "someone@example.com"
    mock_coordinator.account_type = "mova"
    mock_coordinator.account_country = "eu"

    sensor = DreameMowerAccountSensor(mock_coordinator)

    assert sensor.unique_id == "aa:bb:cc:dd:ee:ff_account"
    assert sensor.native_value == "someone@example.com"
    assert sensor.extra_state_attributes == {
        "account_type": "mova",
        "country": "eu",
    }


async def test_account_sensor_stays_available_while_the_device_is_not(mock_coordinator):
    """The account is known from the configuration, so an offline device keeps it readable."""
    mock_coordinator.device_connected = False
    mock_coordinator.device_online = False
    mock_coordinator.account_username = "someone@example.com"

    sensor = DreameMowerAccountSensor(mock_coordinator)

    assert sensor.available is True
    assert sensor.native_value == "someone@example.com"
