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
    DreameMowerBatterySensor,
    DreameMowerStatusSensor,
    DreameMowerChargingStatusSensor,
    DreameMowerBluetoothSensor,
    DreameMowerDeviceCodeSensor,
    DreameMowerTaskSensor,
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
    coordinator.device_charging_status = "Charging"  # Default charging status
    coordinator.device_bluetooth_connected = True
    coordinator.device_code = 0
    coordinator.device_code_is_error = False
    coordinator.device_code_is_warning = False
    coordinator.device_code_name = "No error"
    coordinator.device_code_description = "OK"
    coordinator.current_task_data = None
    coordinator.device_task_status = None
    coordinator.device_status_code = DeviceStatus.CHARGING_COMPLETE
    coordinator.mowing_progress_percent = None
    coordinator.current_area_sqm = None
    coordinator.total_area_sqm = None
    coordinator.mower_coordinates = None
    coordinator.current_segment = None
    coordinator.mower_heading = None
    coordinator.mowing_path_history = []
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


async def test_status_sensor_native_value_unavailable(mock_coordinator, device_id):
    """Test status sensor returns offline when unavailable."""
    mock_coordinator.device_connected = False
    mock_coordinator.last_update_success = False
    
    sensor = DreameMowerStatusSensor(mock_coordinator)
    
    assert sensor.available is False
    assert sensor.native_value == "offline"


async def test_charging_status_sensor_initialization(mock_coordinator, device_id):
    """Test charging status sensor initialization."""
    sensor = DreameMowerChargingStatusSensor(mock_coordinator)
    
    assert sensor.coordinator == mock_coordinator
    assert sensor._entity_description_key == "charging_status"
    assert sensor.unique_id == "aa:bb:cc:dd:ee:ff_charging_status"


async def test_charging_status_sensor_native_value_available(mock_coordinator, device_id):
    """Test charging status sensor returns value when available."""
    mock_coordinator.device_connected = True
    mock_coordinator.last_update_success = True
    
    mock_coordinator.device_charging_status = "Charging"
    
    sensor = DreameMowerChargingStatusSensor(mock_coordinator)
    
    assert sensor.available is True
    assert sensor.native_value == "Charging"


async def test_charging_status_sensor_native_value_unavailable(mock_coordinator, device_id):
    """Test charging status sensor returns None when unavailable."""
    mock_coordinator.device_connected = False
    mock_coordinator.last_update_success = False
    
    mock_coordinator.device_charging_status = None
    
    sensor = DreameMowerChargingStatusSensor(mock_coordinator)
    
    assert sensor.available is False
    assert sensor.native_value is None


async def test_bluetooth_sensor_value(mock_coordinator):
    """Test Bluetooth sensor returns connection status."""
    mock_coordinator.device_bluetooth_connected = True
    sensor = DreameMowerBluetoothSensor(mock_coordinator)
    assert sensor.native_value is True
    assert sensor.unique_id == "aa:bb:cc:dd:ee:ff_bluetooth_connection"
    assert sensor.extra_state_attributes == {"bluetooth_connected": True}


async def test_device_code_sensor_value_and_attributes(mock_coordinator):
    """Test device code sensor native value and extra attributes."""
    mock_coordinator.device_code = 5
    mock_coordinator.device_code_is_error = True
    mock_coordinator.device_code_is_warning = False
    mock_coordinator.device_code_name = "Blade error"
    mock_coordinator.device_code_description = "Check blades"

    sensor = DreameMowerDeviceCodeSensor(mock_coordinator)
    assert sensor.native_value == 5
    assert sensor.icon == "mdi:alert-circle"
    attrs = sensor.extra_state_attributes
    assert attrs["type"] == "error"
    assert attrs["name"] == "Blade error"
    assert attrs["description"] == "Check blades"


async def test_device_code_sensor_warning_icon(mock_coordinator):
    """Test device code sensor uses warning icon when code is a warning."""
    mock_coordinator.device_code = 3
    mock_coordinator.device_code_is_error = False
    mock_coordinator.device_code_is_warning = True
    sensor = DreameMowerDeviceCodeSensor(mock_coordinator)
    assert sensor.icon == "mdi:alert"
    assert sensor.extra_state_attributes["type"] == "warning"


async def test_task_sensor_mowing(mock_coordinator):
    """Test task sensor reflects the heartbeat-decoded task status."""
    mock_coordinator.device_task_status = "mowing"
    sensor = DreameMowerTaskSensor(mock_coordinator)
    assert sensor.native_value == "mowing"


async def test_task_sensor_paused(mock_coordinator):
    """Test task sensor returns paused when the heartbeat reports a paused task."""
    mock_coordinator.device_task_status = "paused"
    sensor = DreameMowerTaskSensor(mock_coordinator)
    assert sensor.native_value == "paused"


async def test_task_sensor_returning_to_dock(mock_coordinator):
    """Test task sensor surfaces the transient return-to-dock status."""
    mock_coordinator.device_task_status = "returning_to_dock"
    sensor = DreameMowerTaskSensor(mock_coordinator)
    assert sensor.native_value == "returning_to_dock"


async def test_task_sensor_unknown(mock_coordinator):
    """Test task sensor returns None until a heartbeat is decoded."""
    mock_coordinator.device_task_status = None
    sensor = DreameMowerTaskSensor(mock_coordinator)
    assert sensor.native_value is None


async def test_task_sensor_attributes(mock_coordinator):
    """Test task sensor exposes the task descriptor details as attributes."""
    mock_coordinator.current_task_data = {
        "type": "TASK",
        "coverage_target": 1,
        "area_id": [3],
        "region_id": [1, 2],
        "elapsed_time": 120,
    }
    sensor = DreameMowerTaskSensor(mock_coordinator)
    attrs = sensor.extra_state_attributes
    assert attrs["task_type"] == "TASK"
    assert attrs["coverage_target"] == 1
    assert attrs["region_id"] == [1, 2]
    assert attrs["elapsed_time"] == 120


async def test_task_sensor_attributes_empty_without_descriptor(mock_coordinator):
    """Test task sensor reports no attributes when no descriptor is cached."""
    mock_coordinator.current_task_data = None
    sensor = DreameMowerTaskSensor(mock_coordinator)
    assert sensor.extra_state_attributes == {}


async def test_progress_sensor_value(mock_coordinator):
    """Test progress sensor returns rounded progress value."""
    mock_coordinator.mowing_progress_percent = 55.678
    mock_coordinator.current_area_sqm = 120.5
    mock_coordinator.total_area_sqm = 220.0
    mock_coordinator.mower_coordinates = (10.1, 20.2)
    mock_coordinator.current_segment = 1
    mock_coordinator.mower_heading = 90
    mock_coordinator.mowing_path_history = [(0, 0), (1, 1)]

    sensor = DreameMowerProgressSensor(mock_coordinator)
    assert sensor.native_value == 55.7
    attrs = sensor.extra_state_attributes
    assert attrs["progress_percent"] == 55.7
    assert attrs["x"] == 10.1
    assert attrs["path_points"] == 2


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
