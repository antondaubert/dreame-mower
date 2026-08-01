"""Basic tests for the DreameMowerDevice class."""

import asyncio
import logging
import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch, PropertyMock

from custom_components.dreame_mower.dreame.device import DreameMowerDevice, MowingMode
from custom_components.dreame_mower.dreame.const import (
    DeviceStatus,
    MowingPreferenceMode,
    ONLINE_OFFLINE_DEBOUNCE_POLLS,
)


def _run_online_polls(device, times):
    """Run async_update_online_status ``times`` times, returning the last result."""
    result = None
    for _ in range(times):
        result = asyncio.get_event_loop().run_until_complete(
            device.async_update_online_status()
        )
    return result


class MockCloudDevice:
    """Mock cloud device for testing."""
    
    def __init__(self):
        self._connected = False
        self._message_callback = None
        self._connected_callback = None
        self._disconnected_callback = None
        self.device_id = "test_device_123"  # Add device_id for execute_action method
        self.action_calls = []
        self.action_result = True
        self.set_property_calls = []
        self.batch_device_datas_result = None
        self.check_device_version_result = None
        # get_properties returns a value, or raises when set to an Exception.
        self.get_properties_result = None
    
    @property
    def connected(self) -> bool:
        """Mock connected property (read-only like the real implementation)."""
        return self._connected
    
    def connect(self, message_callback=None, connected_callback=None, disconnected_callback=None):
        self._message_callback = message_callback
        self._connected_callback = connected_callback
        self._disconnected_callback = disconnected_callback
        self._connected = True
        
        # Simulate connection callback
        if self._connected_callback:
            self._connected_callback()
        
        return True
    
    def disconnect(self):
        self._connected = False
        
        # Simulate disconnection callback
        if self._disconnected_callback:
            self._disconnected_callback()
    
    def get_device_info(self):
        """Mock device info from devices_list endpoint."""
        return {
            "battery": 90,
            "latestStatus": 13,  # Charging complete
            "ver": "1.5.0_test",
            "sn": "TEST123456",
            "mac": "AA:BB:CC:DD:EE:FF",
            "online": True
        }
    
    def simulate_message(self, message):
        """Helper method to simulate incoming messages for testing."""
        if self._message_callback:
            self._message_callback(message)
    
    def set_connected_state(self, connected: bool):
        """Helper method for tests to manually set connection state."""
        self._connected = connected

    def get_file_download_url(self, file_path: str) -> str | None:
        """Mock file download URL getter for testing."""
        # Return a mock URL for testing
        return f"https://mock.test.com/download/{file_path}"

    def action(self, siid: int, aiid: int, parameters=None, retry_count: int = 2):
        """Mock action call; return a boolean to indicate success."""
        if not self.connected:
            return False
        self.action_calls.append((siid, aiid, parameters, retry_count))
        if callable(self.action_result):
            return self.action_result(siid, aiid, parameters, retry_count)
        return self.action_result

    def get_batch_device_datas(self, props):
        """Mock batch device data getter used by vector map refresh."""
        return self.batch_device_datas_result

    def check_device_version(self):
        """Mock cloud OTA firmware-availability check."""
        return self.check_device_version_result

    def get_properties(self, parameters=None, retry_count: int = 1):
        """Mock get_properties used by the online heartbeat poll."""
        if isinstance(self.get_properties_result, Exception):
            raise self.get_properties_result
        return self.get_properties_result

    def execute_action(self, action) -> bool:
        """Mock execute_action method that uses action internally."""
        if not self.connected:
            return False
        return self.action(action.siid, action.aiid)

    def set_property(self, siid: int, piid: int, value=None, retry_count: int = 2):
        """Mock property write used by zone selection tests."""
        if not self.connected:
            return False
        self.set_property_calls.append((siid, piid, value, retry_count))
        return True


@pytest.fixture
def device():
    """Create a basic device instance for testing."""
    with patch('custom_components.dreame_mower.dreame.device.DreameMowerCloudDevice') as mock_cloud_device_class:
        with patch('custom_components.dreame_mower.dreame.utils.requests') as mock_requests:
            with patch('custom_components.dreame_mower.dreame.utils.os.makedirs') as mock_makedirs:
                with patch('builtins.open', create=True) as mock_open:
                    # Setup requests mock
                    mock_response = Mock()
                    mock_response.text = '{"mock": "data"}'
                    mock_response.content = b'{"mock": "data"}'
                    mock_response.ok = True
                    mock_response.raise_for_status.return_value = None
                    mock_requests.get.return_value = mock_response
                    
                    # Setup file operations mocks
                    mock_makedirs.return_value = None
                    mock_file = Mock()
                    mock_open.return_value.__enter__.return_value = mock_file
                    
                    mock_cloud_device = MockCloudDevice()
                    mock_cloud_device_class.return_value = mock_cloud_device
                    
                    device = DreameMowerDevice(
                        device_id="test_device_123",
                        username="test_user",
                        password="test_password",
                        account_type="dreame",
                        country="DE",
                        hass_config_dir="/tmp/test_config"
                    )
                    
                    # Ensure the mock is properly attached
                    device._cloud_device = mock_cloud_device
                    
                    return device


def test_device_initialization(device):
    """Test basic device initialization."""
    assert device.device_id == "test_device_123"
    assert device.username == "test_user"
    assert device.connected is False
    assert device.firmware == "Unknown"
    assert isinstance(device.last_update, datetime)


def test_device_properties(device):
    """Test device property access."""
    # Test initial state
    assert not device.connected
    assert device.firmware == "Unknown"
    
    # Test property updates
    device._firmware = "1.2.3"
    
    # Test connected property after mocking connection
    device._cloud_device.set_connected_state(True)
    assert device.connected is True
    
    assert device.firmware == "1.2.3"


def test_register_property_callback(device):
    """Test property callback registration."""
    callback_called = []
    
    def test_callback(prop_name, value):
        callback_called.append((prop_name, value))
    
    device.register_property_callback(test_callback)
    device._notify_property_change("test_prop", "test_value")
    
    assert len(callback_called) == 1
    assert callback_called[0] == ("test_prop", "test_value")


@pytest.mark.asyncio
async def test_connect(device):
    """Test device connection."""
    # Manually set connected state for mock
    device._cloud_device.set_connected_state(True)
    
    result = await device.connect()
    
    assert result is True
    assert device.connected is True


@pytest.mark.asyncio
async def test_disconnect(device):
    """Test device disconnection."""
    # First connect
    device._cloud_device.set_connected_state(True)
    await device.connect()
    assert device.connected is True
    
    # Then disconnect
    await device.disconnect()
    # Note: disconnect doesn't change mock connected state in current implementation
    # This tests the disconnect method runs without errors


@pytest.mark.asyncio
async def test_start_mowing_when_connected(device):
    """Test public start mowing when device is connected."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    
    result = await device.start_mowing()
    assert result is True


@pytest.mark.asyncio
async def test_start_mowing_when_disconnected(device):
    """Test public start mowing when device is disconnected."""
    result = await device.start_mowing()
    assert result is False


@pytest.mark.asyncio
async def test_start_mowing_delegates_to_selected_mode(device):
    """Public start_mowing should dispatch through the mode-based API."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    result = await device.start_mowing(MowingMode.ZONE, zone_ids=[1])

    assert result is True
    _, _, parameters, _ = device._cloud_device.action_calls[0]
    assert parameters == [{"m": "a", "p": 0, "o": 102, "d": {"region": [1]}}]


@pytest.mark.asyncio
async def test_start_mowing_all_area_logs_warning_when_falling_back_to_generic(device, caplog):
    """All-area without a map should warn before using the generic start action."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    with caplog.at_level(logging.WARNING):
        result = await device.start_mowing_all_area()

    assert result is True
    assert "fell back to the generic START_MOWING action" in caplog.text
    assert device._cloud_device.action_calls[0][2] == [{"m": "g", "t": "MAPL"}]
    siid, aiid, parameters, retry_count = device._cloud_device.action_calls[-1]
    assert (siid, aiid) == (5, 1)
    assert parameters is None


@pytest.mark.asyncio
async def test_start_mowing_all_area_uses_current_map_id_when_known(device, caplog):
    """All-area starts should prefer the known current map before any generic fallback."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._current_map_id = 2
    device._vector_map = SimpleNamespace(
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ]
    )

    with caplog.at_level(logging.WARNING):
        result = await device.start_mowing_all_area()

    assert result is True
    assert "fell back to the generic START_MOWING action" not in caplog.text
    siid, aiid, parameters, retry_count = device._cloud_device.action_calls[0]
    assert (siid, aiid) == (2, 50)
    assert parameters == [{"m": "a", "p": 0, "o": 100, "d": {"region_id": [2], "area_id": []}}]


@pytest.mark.asyncio
async def test_start_mowing_all_area_refreshes_current_map_before_generic_fallback(device, caplog):
    """All-area starts should try MAPL refresh before falling back to the generic action."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._vector_map = SimpleNamespace(
        current_map_id=None,
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ]
    )
    device._cloud_device.action_result = {
        "siid": 2,
        "aiid": 50,
        "code": 0,
        "out": [{"d": [[0, 0, 1, 1, 0], [1, 1, 1, 1, 0]], "m": "r", "q": 4778, "r": 0}],
    }

    with caplog.at_level(logging.WARNING):
        result = await device.start_mowing_all_area()

    assert result is True
    assert "fell back to the generic START_MOWING action" not in caplog.text
    assert len(device._cloud_device.action_calls) == 2
    assert device._cloud_device.action_calls[0][2] == [{"m": "g", "t": "MAPL"}]
    assert device._cloud_device.action_calls[1][2] == [
        {"m": "a", "p": 0, "o": 100, "d": {"region_id": [2], "area_id": []}}
    ]


@pytest.mark.asyncio
async def test_pause_when_connected(device):
    """Test pause when device is connected."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    
    result = await device.pause()
    assert result is True


@pytest.mark.asyncio
async def test_pause_when_disconnected(device):
    """Test pause when device is disconnected."""
    result = await device.pause()
    assert result is False


@pytest.mark.asyncio
async def test_resume_when_connected_notifies_activity_mowing(device):
    """resume() should succeed and notify that the mower is mowing."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    property_changes = []
    device.register_property_callback(lambda name, value: property_changes.append((name, value)))

    result = await device.resume()

    assert result is True
    assert ("activity", "mowing") in property_changes


@pytest.mark.asyncio
async def test_resume_when_disconnected_returns_false(device):
    """Resume should fail gracefully when disconnected."""
    result = await device.resume()
    assert result is False


@pytest.mark.asyncio
async def test_start_mowing_zones_uses_zone_action_payload(device):
    """Zone mowing should use the zone action payload."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._status_code = DeviceStatus.CHARGING

    result = await device.start_mowing_zones([1])

    assert result is True
    assert len(device._cloud_device.action_calls) == 1
    assert len(device._cloud_device.set_property_calls) == 0

    siid, aiid, parameters, retry_count = device._cloud_device.action_calls[0]
    assert (siid, aiid) == (2, 50)
    assert parameters == [{"m": "a", "p": 0, "o": 102, "d": {"region": [1]}}]


@pytest.mark.asyncio
async def test_start_mowing_zones_does_not_reuse_elapsed_time(device):
    """Zone mowing should not add elapsed time to the action payload."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._status_code = DeviceStatus.MOWING
    device._scheduling_handler.handle_property_update(
        2,
        50,
        {"t": "TASK", "d": {"exe": True, "o": 6, "status": True, "time": 13197}},
        lambda *_: None,
    )

    result = await device.start_mowing_zones([1, 3])

    assert result is True
    assert len(device._cloud_device.action_calls) == 1
    assert len(device._cloud_device.set_property_calls) == 0

    _, _, parameters, _ = device._cloud_device.action_calls[0]
    assert parameters == [{"m": "a", "p": 0, "o": 102, "d": {"region": [1, 3]}}]


@pytest.mark.asyncio
async def test_start_mowing_zones_rejects_unknown_zone_ids(device):
    """Zone mowing should reject zone IDs that are not present in the loaded map."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._vector_map = Mock(zones=[Mock(zone_id=1), Mock(zone_id=2)])

    result = await device.start_mowing_zones([3])

    assert result is False
    assert len(device._cloud_device.action_calls) == 0
    assert len(device._cloud_device.set_property_calls) == 0


@pytest.mark.asyncio
async def test_start_mowing_edges_uses_edge_action_payload(device):
    """Edge mowing should use the edge action payload."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    result = await device.start_mowing_edges([[1, 0]])

    assert result is True
    assert len(device._cloud_device.action_calls) == 1

    siid, aiid, parameters, retry_count = device._cloud_device.action_calls[0]
    assert (siid, aiid) == (2, 50)
    assert parameters == [{"m": "a", "p": 0, "o": 101, "d": {"edge": [[1, 0]]}}]


@pytest.mark.asyncio
async def test_start_mowing_edges_rejects_unknown_contour_ids(device):
    """Edge mowing should reject contour IDs that are not present in the loaded map."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._vector_map = Mock(contours=[Mock(contour_id=(1, 0)), Mock(contour_id=(2, 0))])

    result = await device.start_mowing_edges([[3, 0]])

    assert result is False
    assert len(device._cloud_device.action_calls) == 0


@pytest.mark.asyncio
async def test_start_mowing_edges_rejects_invalid_contour_shape(device):
    """Edge mowing should reject contour IDs that are not two-integer pairs."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    result = await device.start_mowing_edges([[1]])

    assert result is False


@pytest.mark.asyncio
async def test_start_mowing_all_area_uses_map_task_payload(device):
    """Map-aware all-area mowing should use the verified map task payload."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._vector_map = Mock(available_maps=[Mock(map_id=1), Mock(map_id=2)])

    result = await device.start_mowing_all_area(2)

    assert result is True
    assert len(device._cloud_device.action_calls) == 1
    siid, aiid, parameters, retry_count = device._cloud_device.action_calls[0]
    assert (siid, aiid) == (2, 50)
    assert parameters == [{"m": "a", "p": 0, "o": 100, "d": {"region_id": [2], "area_id": []}}]


@pytest.mark.asyncio
async def test_set_current_map_uses_verified_map_switch_payload(device):
    """Map switching should use the verified 2:50 payload with o=200 and idx=mapIndex."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._vector_map = SimpleNamespace(
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ]
    )

    result = await device.set_current_map(2)

    assert result is True
    siid, aiid, parameters, retry_count = device._cloud_device.action_calls[0]
    assert (siid, aiid) == (2, 50)
    assert parameters == [{"m": "a", "p": 0, "o": 200, "d": {"idx": 1}}]
    assert device.current_map_id == 2


@pytest.mark.asyncio
async def test_set_current_map_rejects_unknown_map_id(device):
    """Map switching should reject unknown map IDs when map metadata is loaded."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._vector_map = SimpleNamespace(
        available_maps=[SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0)]
    )

    result = await device.set_current_map(2)

    assert result is False
    assert len(device._cloud_device.action_calls) == 0


@pytest.mark.asyncio
async def test_start_mowing_mode_delegates_to_verified_mode(device):
    """The mode-oriented API should delegate to the verified zone/edge/all-area flows."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    result = await device.start_mowing_mode(MowingMode.ZONE, zone_ids=[1])

    assert result is True
    _, _, parameters, _ = device._cloud_device.action_calls[0]
    assert parameters == [{"m": "a", "p": 0, "o": 102, "d": {"region": [1]}}]


@pytest.mark.asyncio
async def test_start_mowing_spots_uses_verified_spot_payload(device):
    """Spot mowing should use the verified 2:50 payload with o=103 and d.area."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    result = await device.start_mowing_spots([4])

    assert result is True
    _, _, parameters, _ = device._cloud_device.action_calls[0]
    assert parameters == [{"m": "a", "p": 0, "o": 103, "d": {"area": [4]}}]


@pytest.mark.asyncio
async def test_start_mowing_spots_rejects_unknown_spot_area_ids(device):
    """Spot mowing should reject spot area IDs that are not present in the loaded map."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._vector_map = Mock(spot_areas=[Mock(area_id=1), Mock(area_id=2)])

    result = await device.start_mowing_spots([3])

    assert result is False
    assert len(device._cloud_device.action_calls) == 0


@pytest.mark.asyncio
async def test_start_mowing_mode_delegates_to_verified_spot_mode(device):
    """The mode-oriented API should delegate to the verified spot flow."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    result = await device.start_mowing_mode(MowingMode.SPOT, spot_area_ids=[4])

    assert result is True
    _, _, parameters, _ = device._cloud_device.action_calls[0]
    assert parameters == [{"m": "a", "p": 0, "o": 103, "d": {"area": [4]}}]


@pytest.mark.asyncio
async def test_create_spot_area_creates_rectangle_and_returns_created_spot_id(device):
    """Rectangle spot creation should create the spot, apply it, and return the new spot area ID."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    device._vector_map = SimpleNamespace(
        spot_areas=[SimpleNamespace(area_id=1, path=[(-100, -100), (0, -100), (0, 0), (-100, 0)])],
        boundary=SimpleNamespace(x1=-500, y1=-500, x2=500, y2=500),
        zones=[],
        forbidden_areas=[],
        paths=[],
        contours=[],
    )

    def refresh_vector_map():
        device._vector_map = SimpleNamespace(
            spot_areas=[
                SimpleNamespace(area_id=1, path=[(-100, -100), (0, -100), (0, 0), (-100, 0)]),
                SimpleNamespace(area_id=2, path=[(100, 100), (300, 100), (300, 300), (100, 300)]),
            ],
            boundary=SimpleNamespace(x1=-500, y1=-500, x2=500, y2=500),
            zones=[],
            forbidden_areas=[],
            paths=[],
            contours=[],
        )
        return True

    device.fetch_vector_map = refresh_vector_map

    result = await device.create_spot_area({"x1": 1, "y1": 1, "x2": 3, "y2": 3})

    assert result == 2
    assert len(device._cloud_device.action_calls) == 2

    _, _, create_parameters, _ = device._cloud_device.action_calls[0]
    assert create_parameters == [{
        "m": "a",
        "p": 0,
        "o": 214,
        "d": {
            "id": -1,
            "points": [[3.0, 1.0], [1.0, 1.0], [1.0, 3.0], [3.0, 3.0]],
        },
    }]

    _, _, apply_parameters, _ = device._cloud_device.action_calls[1]
    assert apply_parameters == [{"m": "a", "p": 1, "o": 201}]


@pytest.mark.asyncio
async def test_start_mowing_mode_rejects_rectangle_spot_flow(device):
    """The mode-oriented API should not combine spot creation with spot mowing."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    result = await device.start_mowing_mode(
        MowingMode.SPOT,
        spot_rectangle={"x1": 0, "y1": 0, "x2": 2, "y2": 2},
    )

    assert result is False
    assert len(device._cloud_device.action_calls) == 0


@pytest.mark.asyncio
async def test_create_spot_area_rejects_too_small_rectangle(device):
    """Rectangle spot creation should reject rectangles smaller than 1m x 1m."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    result = await device.create_spot_area({"x1": 1, "y1": 1, "x2": 1.5, "y2": 2})

    assert result is None
    assert len(device._cloud_device.action_calls) == 0


@pytest.mark.asyncio
async def test_create_spot_area_rejects_rectangle_outside_map(device):
    """Rectangle spot creation should reject rectangles that do not overlap the map."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._vector_map = SimpleNamespace(
        spot_areas=[],
        boundary=SimpleNamespace(x1=-500, y1=-500, x2=500, y2=500),
        zones=[],
        forbidden_areas=[],
        paths=[],
        contours=[],
    )

    result = await device.create_spot_area({"x1": 6, "y1": 6, "x2": 8, "y2": 8})

    assert result is None
    assert len(device._cloud_device.action_calls) == 0


@pytest.mark.asyncio
async def test_start_mowing_spot_requires_existing_spot_ids(device):
    """Spot mowing should remain a pure start operation over existing spot IDs."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    result = await device.start_mowing_spot()

    assert result is False
    assert len(device._cloud_device.action_calls) == 0


def test_current_map_id_is_unknown_for_multi_map_batch_data(device):
    """Batch map data alone should not invent a current map for multi-map setups."""
    device._vector_map = SimpleNamespace(
        current_map_id=None,
        available_maps=[SimpleNamespace(map_id=1), SimpleNamespace(map_id=2)],
    )
    device._scheduling_handler.handle_property_update(
        2,
        50,
        {"t": "TASK", "d": {"area_id": [], "exe": True, "o": 100, "region_id": [2], "status": True, "time": 10}},
        lambda *_: None,
    )

    assert device.current_map_id is None
    assert device.task_target_map_id == 2


def test_current_map_id_falls_back_to_only_available_map(device):
    """Single-map setups can infer the current map without extra cloud state."""
    device._vector_map = SimpleNamespace(
        current_map_id=None,
        available_maps=[SimpleNamespace(map_id=1)],
    )

    assert device.current_map_id == 1


def test_available_maps_returns_serializable_map_entries(device):
    """Available maps should expose stable dicts for Home Assistant attributes."""
    device._vector_map = SimpleNamespace(
        current_map_id=None,
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ]
    )

    assert device.available_maps == [
        {"id": 1, "index": 0, "name": "Front", "area": 25.0},
        {"id": 2, "index": 1, "name": "Back", "area": 30.5},
    ]
    assert len(device._cloud_device.action_calls) == 0


def test_spot_areas_returns_serializable_entries(device):
    """Spot areas should expose stable dicts for higher layers."""
    device._vector_map = SimpleNamespace(
        spot_areas=[
            SimpleNamespace(area_id=4, name="Tree", area=2.5),
            SimpleNamespace(area_id=5, name="Bench", area=1.2),
        ]
    )

    assert device.spot_areas == [
        {"id": 4, "name": "Tree", "area": 2.5},
        {"id": 5, "name": "Bench", "area": 1.2},
    ]


def test_refresh_current_map_id_reads_active_map_from_mapl(device):
    """MAPL should authoritatively expose the current map via the isCurMap flag."""
    device._cloud_device.set_connected_state(True)
    property_changes = []
    device.register_property_callback(lambda name, value: property_changes.append((name, value)))
    device._vector_map = SimpleNamespace(
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ]
    )
    device._cloud_device.action_result = {
        "siid": 2,
        "aiid": 50,
        "code": 0,
        "out": [{"d": [[0, 0, 1, 1, 0], [1, 1, 1, 1, 0]], "m": "r", "q": 4778, "r": 0}],
    }

    result = device.refresh_current_map_id()

    assert result is True
    assert device.current_map_id == 2
    assert ("current_map_id", 2) in property_changes
    assert device._cloud_device.action_calls[-1][2] == [{"m": "g", "t": "MAPL"}]


@pytest.mark.asyncio
async def test_get_consumable_status_sends_cms_getter_payload(device):
    """CMS getter should send the CMS getter payload and parse d.value."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    device._cloud_device.action_result = {
        "code": 0,
        "out": [{"r": 0, "d": {"value": [120, 600, 30]}}],
    }

    result = await device.get_consumable_status()

    assert result["values"] == [120, 600, 30]
    assert device._cloud_device.action_calls[-1][2] == [{"m": "g", "t": "CMS"}]


def test_extract_consumable_values_accepts_direct_data_shape(device):
    """CMS parsing should tolerate already-unwrapped action data."""
    result = device._extract_consumable_values({"d": {"value": ["1", 2, 3]}})

    assert result == [1, 2, 3]


def test_extract_consumable_values_preserves_sentinel_slots(device):
    """CMS parsing must keep every slot the device reports, including -1 sentinels."""
    result = device._extract_consumable_values({"d": {"value": [120, 2809, 2809, -1]}})

    assert result == [120, 2809, 2809, -1]


@pytest.mark.asyncio
async def test_reset_consumable_counter_round_trips_full_array_with_sentinel(device):
    """Resetting must write back the whole array verbatim, preserving -1 sentinels."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    responses = iter(
        [
            {"code": 0, "out": [{"r": 0, "d": {"value": [120, 2809, 2809, -1]}}]},
            {"code": 0, "out": [{"r": 0, "d": {"value": [0, 2809, 2809, -1]}}]},
        ]
    )
    device._cloud_device.action_result = lambda *_args, **_kwargs: next(responses)

    await device.reset_consumable_counter("blade")

    assert device._cloud_device.action_calls[1][2] == [
        {"m": "s", "t": "CMS", "d": {"value": [0, 2809, 2809, -1]}}
    ]


@pytest.mark.asyncio
async def test_reset_consumable_counter_zeroes_selected_slot(device):
    """Resetting one consumable should preserve the others and send the CMS setter."""
    device._cloud_device.set_connected_state(True)
    await device.connect()

    responses = iter(
        [
            {"code": 0, "out": [{"r": 0, "d": {"value": [120, 600, 30]}}]},
            {"code": 0, "out": [{"r": 0, "d": {"value": [0, 600, 30]}}]},
        ]
    )
    device._cloud_device.action_result = lambda *_args, **_kwargs: next(responses)

    result = await device.reset_consumable_counter("blade")

    assert result["item"] == "blade"
    assert result["previous_values"] == [120, 600, 30]
    assert result["requested_values"] == [0, 600, 30]
    assert result["updated_values"] == [0, 600, 30]
    assert device._cloud_device.action_calls[0][2] == [{"m": "g", "t": "CMS"}]
    assert device._cloud_device.action_calls[1][2] == [
        {"m": "s", "t": "CMS", "d": {"value": [0, 600, 30]}}
    ]


def test_fetch_vector_map_updates_current_map_id_from_mapl(device):
    """Vector map refresh should also refresh current_map_id from MAPL."""
    device._cloud_device.set_connected_state(True)
    device._cloud_device.batch_device_datas_result = {"MAP.info": "2"}
    device._cloud_device.action_result = {
        "siid": 2,
        "aiid": 50,
        "code": 0,
        "out": [{"d": [[0, 0, 1, 1, 0], [1, 1, 1, 1, 0]], "m": "r", "q": 4778, "r": 0}],
    }
    vector_map = SimpleNamespace(
        current_map_id=None,
        zones=[],
        paths=[],
        boundary=None,
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ],
    )

    with patch("custom_components.dreame_mower.dreame.device.parse_batch_map_data", return_value=vector_map):
        result = device.fetch_vector_map()

    assert result is True
    assert device.vector_map is vector_map
    assert device.current_map_id == 2


def test_active_map_geometry_uses_current_map_id(device):
    """Zones and contours should resolve from the active map, not the first parsed map."""
    front_map = SimpleNamespace(
        zones=[SimpleNamespace(zone_id=1, name="Front zone", area=10.0)],
        contours=[SimpleNamespace(contour_id=(1, 0))],
        spot_areas=[],
        forbidden_areas=[],
        paths=[],
        boundary=None,
    )
    back_map = SimpleNamespace(
        zones=[SimpleNamespace(zone_id=7, name="Back zone", area=20.0)],
        contours=[SimpleNamespace(contour_id=(7, 1))],
        spot_areas=[],
        forbidden_areas=[],
        paths=[],
        boundary=None,
    )
    device._current_map_id = 2
    device._vector_map = SimpleNamespace(
        map_id=1,
        current_map_id=None,
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ],
        maps={1: front_map, 2: back_map},
    )

    assert device.vector_map is back_map
    assert device.zones == [{"id": 7, "name": "Back zone", "area": 20.0}]
    assert device.contours == [[7, 1]]


def test_refresh_current_map_id_keeps_existing_value_when_mapl_has_no_active_map(device):
    """Malformed or incomplete MAPL data should not clear a known current map."""
    device._current_map_id = 2
    device._vector_map = SimpleNamespace(
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ]
    )
    device._cloud_device.action_result = {
        "siid": 2,
        "aiid": 50,
        "code": 0,
        "out": [{"d": [[0, 0, 1, 1, 0], [1, 0, 1, 1, 0]], "m": "r", "q": 4778, "r": 0}],
    }

    result = device.refresh_current_map_id()

    assert result is False
    assert device.current_map_id == 2


@pytest.mark.asyncio
async def test_return_to_dock_when_connected(device):
    """Test return to dock when device is connected."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    
    # Patch the internal mission_completed_event.wait coroutine so the
    # return_to_dock sequence does not actually wait up to 30 seconds.
    # (Patching asyncio.wait_for directly previously caused an un-awaited
    # Event.wait() coroutine warning when raising TimeoutError immediately.)
    with patch.object(device._mission_completed_event, "wait", new=AsyncMock(return_value=True)):
        result = await device.return_to_dock()
        assert result is True


@pytest.mark.asyncio
async def test_return_to_dock_when_disconnected(device):
    """Test return to dock when device is disconnected."""
    result = await device.return_to_dock()
    assert result is False


@pytest.mark.asyncio
async def test_message_callback(device):
    """Test handling of incoming messages."""
    # Connect device - this will fetch initial device info
    device._cloud_device.set_connected_state(True)
    await device.connect()
    
    # Check that initial device info was loaded
    assert device.firmware == "1.5.0_test"  # From mock get_device_info
    assert device.battery_percent == 90  # From mock get_device_info
    assert device.status == "charging_complete"  # From mock latestStatus 13
    
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    # Test MQTT message with properties_changed format (battery update)
    battery_message = {
        "id": 123,
        "method": "properties_changed",
        "params": [
            {
                "did": "test_device_123",
                "siid": 3,
                "piid": 1,
                "value": 75
            }
        ]
    }
    
    # Simulate MQTT message
    device._cloud_device.simulate_message(battery_message)
    
    # Check battery was updated via MQTT
    assert device.battery_percent == 75
    
    # Check property change notifications
    assert ("battery_percent", 75) in property_changes


def test_service1_session_start_properties():
    """Test handling of Service1 session start properties 1:50 and 1:51."""
    device = DreameMowerDevice(
        device_id="test_device_123",
        username="test_user", 
        password="test_password",
        account_type="dreame",
        country="DE",
        hass_config_dir="/tmp/test_config"
    )
    property_changes = []
    
    def property_change_callback(property_name, value):
        property_changes.append((property_name, value))
    
    device.register_property_callback(property_change_callback)
    
    # Initial state should be False
    assert device.service1_property_50 is False
    assert device.service1_property_51 is False
    assert device.service1_completion_flag is False
    
    # Simulate the exact MQTT messages from logs
    message_property_50 = {
        'id': 305, 
        'method': 'properties_changed', 
        'params': [{'did': '-1******95', 'piid': 50, 'siid': 1}]
    }
    
    message_property_51 = {
        'id': 306, 
        'method': 'properties_changed', 
        'params': [{'did': '-1******95', 'piid': 51, 'siid': 1}]
    }
    
    # Test property 50 handling
    device._handle_message(message_property_50)
    assert device.service1_property_50 is True
    assert ("service1_property_50", True) in property_changes
    
    # Test property 51 handling 
    device._handle_message(message_property_51)
    assert device.service1_property_51 is True
    assert ("service1_property_51", True) in property_changes
    
    # Verify completion flag is still False (different property)
    assert device.service1_completion_flag is False


def test_handle_mqtt_props_success(device):
    """Test _handle_mqtt_props with known parameter (success case)."""
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    # Test handling ota_state parameter
    assert device._handle_mqtt_props({"ota_state": "idle"}) is True
    assert device.ota_state == "idle"
    assert ("ota_state", "idle") in property_changes


def test_handle_mqtt_props_ota_progress(device):
    """Test _handle_mqtt_props handles ota_progress (issue #19)."""
    property_changes = []
    device.register_property_callback(lambda n, v: property_changes.append((n, v)))

    assert device._handle_mqtt_props({"ota_progress": 42}) is True
    assert device.ota_progress == 42
    assert ("ota_progress", 42) in property_changes


def test_handle_mqtt_props_failure(device):
    """Test _handle_mqtt_props with unknown parameters (failure case).""" 
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    assert device._handle_mqtt_props({"unknown_param": "some_value"}) is False
    assert len(property_changes) == 0


def test_service2_property_62_handling(device):
    """Test Service 2 property 62 (2:62) handling."""
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    # Test the specific message structure
    message = {"siid": 2, "piid": 62, "value": 0}
    
    assert device._handle_mqtt_property_update(message) is True
    assert ("service2_property_62", 0) in property_changes


def test_service2_property_55_handling(device):
    """Test Service 2 property 55 (2:55) AI obstacle detection handling (issue #32)."""
    property_changes = []
    device.register_property_callback(lambda n, v: property_changes.append((n, v)))

    # Real message structure from issue #32
    message = {
        "siid": 2,
        "piid": 55,
        "value": {
            "obs": [6125, 18425, 48, 5, "1773059052.181000_0"],
            "type": "ai",
        },
    }

    # Should be handled silently (no notification, no unhandled MQTT)
    assert device._handle_mqtt_property_update(message) is True
    assert len(property_changes) == 0


def test_service2_property_64_handling(device):
    """Test Service 2 property 64 (2:64) work statistics handling."""
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    # Test with a simplified version of the complex work statistics structure
    # from the issue report
    message = {
        "siid": 2, 
        "piid": 64, 
        "value": {
            "cw": {
                "cy": {
                    "ci": ["0.0", "0.0", "0.0", "0.0"],
                    "ct": "2025-10-02 12:27:17",
                    "p": ["0.0"] * 120  # Simplified array
                },
                "ow": {
                    "ci": ["801"],
                    "ct": "2025-10-02 12:27:17"
                }
            },
            "fw": {
                "xz": {
                    "bi": [],
                    "bt": "",
                    "fi": [0] * 48,
                    "wt": "2025-09-30T00:00:00+00:00"
                }
            },
            "p": [9.9, 53.6],
            "rt": "",
            "tz": "Europe/Berlin",
            "wr": "2025-10-02 12:22:56",
            "ws": "2025-10-02 12:27:15"
        }
    }
    
    assert device._handle_mqtt_property_update(message) is True
    # Verify the property change was notified
    assert any(name == "service2_property_64" for name, _ in property_changes)
    # Verify the value was passed through
    notified_value = next(value for name, value in property_changes if name == "service2_property_64")
    assert isinstance(notified_value, dict)
    assert "cw" in notified_value
    assert "fw" in notified_value


def test_service5_property_104_handling(device):
    """Test Service 5 property 104 (5:104) handling from issue #1616."""
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    # Test with value 7 (Task incomplete - spot mowing)
    message = {
        "siid": 5, 
        "piid": 104, 
        "value": 7
    }
    
    assert device._handle_mqtt_property_update(message) is True
    
    # Verify the property change was notified with new property name
    assert any(name == "task_status" for name, _ in property_changes)
    
    # Verify the value was passed through correctly
    notified_value = next(value for name, value in property_changes if name == "task_status")
    assert isinstance(notified_value, dict)
    assert "status_code" in notified_value
    assert notified_value["status_code"] == 7
    assert "status_description" in notified_value
    assert notified_value["status_description"] == "Task incomplete - spot mowing"
    
    # Also check that the individual state change notification was sent
    assert any(name == "task_status_code" for name, _ in property_changes)
    individual_value = next(value for name, value in property_changes if name == "task_status_code")
    assert individual_value == 7


def test_service5_property_104_unknown_value(device):
    """Test Service 5 property 104 (5:104) with unknown value from issue #1616."""
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    # Test with unknown value 13 (from original issue #1616)
    # Unknown values should still be handled with generic description
    message = {
        "siid": 5, 
        "piid": 104, 
        "value": 13
    }
    
    # Should return True - we handle it even if we don't know what it means yet
    assert device._handle_mqtt_property_update(message) is True
    
    # Should send notifications with generic "Unknown" description
    assert any(name == "task_status" for name, _ in property_changes)
    notified_value = next(value for name, value in property_changes if name == "task_status")
    assert notified_value["status_code"] == 13
    assert notified_value["status_description"] == "Unknown task status: 13"


def test_firmware_install_state_handling():
    """Test firmware installation state property (1:2) handling."""
    device = DreameMowerDevice(
        device_id="test_device_123",
        username="test_user",
        password="test_password",
        account_type="dreame",
        country="DE",
        hass_config_dir="/tmp/test_config"
    )
    property_changes = []
    
    def property_change_callback(property_name, value):
        property_changes.append((property_name, value))
    
    device.register_property_callback(property_change_callback)
    
    # Initial state should be None
    assert device.firmware_install_state is None
    
    # Test valid value 2
    message_value_2 = {
        'id': 104,
        'method': 'properties_changed',
        'params': [{'did': '-1******18', 'piid': 2, 'siid': 1, 'value': 2}]
    }
    device._handle_message(message_value_2)
    assert device.firmware_install_state == 2
    assert ("firmware_install_state", 2) in property_changes
    
    # Test valid value 3 (from the issue)
    message_value_3 = {
        'id': 105,
        'method': 'properties_changed',
        'params': [{'did': '-1******18', 'piid': 2, 'siid': 1, 'value': 3}]
    }
    device._handle_message(message_value_3)
    assert device.firmware_install_state == 3
    assert ("firmware_install_state", 3) in property_changes
    
    # Test valid value 4 (firmware_download_failed - issues #98, #134)
    message_value_4 = {
        'id': 106,
        'method': 'properties_changed',
        'params': [{'did': '-1******07', 'piid': 2, 'siid': 1, 'value': 4}]
    }
    device._handle_message(message_value_4)
    assert device.firmware_install_state == 4
    assert ("firmware_install_state", 4) in property_changes
    
    # Test invalid value - should be rejected
    property_changes.clear()
    message_invalid = {"siid": 1, "piid": 2, "value": 99}
    result = device._handle_mqtt_property_update(message_invalid)
    assert result is False  # Invalid value should return False
    assert device.firmware_install_state == 4  # State should remain unchanged
    assert len(property_changes) == 0  # No property change notification for invalid value


def test_firmware_download_progress_handling():
    """Test firmware download progress property (1:3) handling."""
    device = DreameMowerDevice(
        device_id="test_device_123",
        username="test_user",
        password="test_password",
        account_type="dreame",
        country="DE",
        hass_config_dir="/tmp/test_config"
    )
    property_changes = []
    
    def property_change_callback(property_name, value):
        property_changes.append((property_name, value))
    
    device.register_property_callback(property_change_callback)
    
    # Initial state should be None
    assert device.firmware_download_progress is None
    
    # Test progress values from the issue (1 to 100)
    test_values = [1, 8, 14, 18, 23, 28, 33, 38, 42, 45, 47, 49, 53, 57, 61, 66, 72, 79, 87, 93, 98, 100]
    
    for progress in test_values:
        message = {
            'id': 132 + progress,
            'method': 'properties_changed',
            'params': [{'did': '-1******96', 'piid': 3, 'siid': 1, 'value': progress}]
        }
        device._handle_message(message)
        assert device.firmware_download_progress == progress
        assert ("firmware_download_progress", progress) in property_changes
    
    # Test edge cases
    # Test 0% (edge case)
    property_changes.clear()
    message_zero = {"siid": 1, "piid": 3, "value": 0}
    result = device._handle_mqtt_property_update(message_zero)
    assert result is True
    assert device.firmware_download_progress == 0
    assert ("firmware_download_progress", 0) in property_changes
    
    # Test invalid negative value - should be rejected
    property_changes.clear()
    message_negative = {"siid": 1, "piid": 3, "value": -1}
    result = device._handle_mqtt_property_update(message_negative)
    assert result is False  # Invalid value should return False
    assert device.firmware_download_progress == 0  # State should remain unchanged
    assert len(property_changes) == 0  # No property change notification for invalid value
    
    # Test invalid value > 100 - should be rejected
    property_changes.clear()
    message_over_100 = {"siid": 1, "piid": 3, "value": 101}
    result = device._handle_mqtt_property_update(message_over_100)
    assert result is False  # Invalid value should return False
    assert device.firmware_download_progress == 0  # State should remain unchanged
    assert len(property_changes) == 0  # No property change notification for invalid value


def test_firmware_validation_event_handling():
    """Test firmware validation event (1:1) handling."""
    device = DreameMowerDevice(
        device_id="test_device_123",
        username="test_user",
        password="test_password",
        account_type="dreame",
        country="DE",
        hass_config_dir="/tmp/test_config"
    )
    property_changes = []
    
    def property_change_callback(property_name, value):
        property_changes.append((property_name, value))
    
    device.register_property_callback(property_change_callback)
    
    # Test firmware validation event message from the issue
    message = {
        'id': 158,
        'method': 'event_occured',
        'params': {'did': '-1******18', 'eiid': 1, 'siid': 1}
    }
    
    device._handle_message(message)
    
    # Check that event was handled and notification was sent
    firmware_validation_changes = [change for change in property_changes if change[0] == "firmware_validation"]
    assert len(firmware_validation_changes) == 1
    
    # Verify notification data structure
    event_data = firmware_validation_changes[0][1]
    assert event_data["siid"] == 1
    assert event_data["eiid"] == 1
    assert "timestamp" in event_data


def test_service2_property_63_handling():
    """Test Service 2 property 63 (2:63) handling - observed in issue #134."""
    device = DreameMowerDevice(
        device_id="test_device_123",
        username="test_user",
        password="test_password",
        account_type="dreame",
        country="DE",
        hass_config_dir="/tmp/test_config"
    )
    property_changes = []
    
    def property_change_callback(property_name, value):
        property_changes.append((property_name, value))
    
    device.register_property_callback(property_change_callback)
    
    # Test the message from issue #134 with value -33001
    message = {
        'id': 107,
        'method': 'properties_changed',
        'params': [{'did': '-1******73', 'piid': 63, 'siid': 2, 'value': -33001}]
    }
    
    # This should return False to enable crowdsourcing
    device._handle_message(message)
    
    # Verify that no property change notification was sent (returns False for crowdsourcing)
    service2_63_changes = [change for change in property_changes if change[0] == "service2_property_63"]
    assert len(service2_63_changes) == 0  # Should not notify since we return False


@pytest.mark.asyncio
async def test_mission_completion_caps_progress_at_100_percent(device):
    """Test that mission completion event caps progress at 100% (issue #47)."""
    property_changes = []
    
    def property_change_callback(name, value):
        property_changes.append((name, value))
    
    device.register_property_callback(property_change_callback)
    
    # First, simulate progress at 96% via pose coverage property (1:4)
    # Full 33-byte payload: [CE] pose(6) trace(15) task(10) [CE]
    # Pose: x=0, y=0, angle=0 (all zeros)
    # Trace: zeros (no deltas)
    # Task at raw[22:32]:
    #   [22]=region_id=0  [23]=task_id=0
    #   [24:26]=percent uint16 LE=9600 (96.0%)  -> 0x80, 0x25
    #   [26:29]=total uint24 LE=10000 (100 sqm) -> 0x10, 0x27, 0x00
    #   [29:32]=finish uint24 LE=9600 (96 sqm)  -> 0x80, 0x25, 0x00
    progress_message = {
        'method': 'properties_changed',
        'params': [{
            'siid': 1, 
            'piid': 4,
            'value': [
                0xCE,
                0, 0, 0, 0, 0, 0,                     # pose (6 bytes)
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # trace (15 bytes)
                0, 0, 0x80, 0x25, 0x10, 0x27, 0x00, 0x80, 0x25, 0x00,  # task (10 bytes)
                0xCE
            ]
        }]
    }
    
    device._handle_message(progress_message)
    
    # Verify progress is 96%
    assert device.mowing_progress_percent == 96.0
    
    # Now simulate mission completion event (4:1) with 96% in the event
    completion_event = {
        'method': 'event_occured',
        'params': {
            'siid': 4,
            'eiid': 1,
            'arguments': [
                {'piid': 1, 'value': 96},  # Progress percent
                {'piid': 2, 'value': 45},  # Duration minutes
                {'piid': 3, 'value': 9600},  # Area (96.00 sqm in centi-sqm)
                {'piid': 8, 'value': 1729000000},  # Start timestamp
            ]
        }
    }
    
    device._handle_message(completion_event)
    
    # After mission completion, progress should be capped at 100%
    assert device.mowing_progress_percent == 100.0
    
    # Verify mission completion event was processed
    completion_events = [change for change in property_changes if change[0] == "mission_completion_event"]
    assert len(completion_events) > 0


@pytest.mark.asyncio
async def test_mission_completion_partial_does_not_cap_progress(device):
    """Test that a partial mission (e.g. low battery return to dock) does not cap progress at 100%.

    Regression test for issue #58: mower returned to dock after mowing ~4% of the
    planned area but progress was shown as 100% because mark_mission_completed() was
    called unconditionally on every 4:1 event.
    """
    property_changes = []

    def property_change_callback(name, value):
        property_changes.append((name, value))

    device.register_property_callback(property_change_callback)

    # Simulate progress at 4% via pose coverage property (1:4)
    # Task bytes: percent=400 (4.00%), total=147500 centi-sqm (1475 m²), finish=6341 centi-sqm (63.41 m²)
    # percent uint16 LE: 400 = 0x90, 0x01
    # total uint24 LE: 147500 = 0xEC, 0x40, 0x02
    # finish uint24 LE: 6341 = 0xC5, 0x18, 0x00
    progress_message = {
        'method': 'properties_changed',
        'params': [{
            'siid': 1,
            'piid': 4,
            'value': [
                0xCE,
                0, 0, 0, 0, 0, 0,                                          # pose (6 bytes)
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,              # trace (15 bytes)
                1, 1, 0x90, 0x01, 0xEC, 0x40, 0x02, 0xC5, 0x18, 0x00,     # task (10 bytes)
                0xCE
            ]
        }]
    }
    device._handle_message(progress_message)
    assert device.mowing_progress_percent == pytest.approx(4.0, abs=0.1)

    # Simulate mission completion event (4:1) with status=3 (STATUS_INTERRUPTED) and
    # stop_reason=101 (low battery). The device sends status=INTERRUPTED when it returns
    # to dock early — is_complete uses piid 7 (status) to detect early termination.
    completion_event = {
        'method': 'event_occured',
        'params': {
            'siid': 4,
            'eiid': 1,
            'arguments': [
                {'piid': 1, 'value': 100},          # Coverage target mode (not actual %)
                {'piid': 2, 'value': 46},            # Duration minutes
                {'piid': 3, 'value': 6341},          # Actual area (centi-sqm)
                {'piid': 7, 'value': 3},             # STATUS_INTERRUPTED: mission was cut short
                {'piid': 8, 'value': 1775991797},    # Start timestamp
                {'piid': 14, 'value': 1475},         # Planned area (m²)
                {'piid': 60, 'value': 101},          # stop_reason: low battery / return to dock
            ]
        }
    }
    device._handle_message(completion_event)

    # Progress should NOT have been capped at 100% — the mower only did ~4%
    assert device.mowing_progress_percent == pytest.approx(4.0, abs=0.1)
    assert device._pose_coverage_handler._mission_completed is False

    # Mission completion event should still have been processed and notified
    completion_events = [change for change in property_changes if change[0] == "mission_completion_event"]
    assert len(completion_events) > 0


@pytest.mark.asyncio
async def test_status_change_to_mowing_resets_mission_completion(device):
    """Test that status change to mowing resets mission completion flag."""
    property_changes = []
    
    def property_change_callback(name, value):
        property_changes.append((name, value))
    
    device.register_property_callback(property_change_callback)
    
    # First, complete a mission with 96% progress
    device._pose_coverage_handler._progress_percent = 96.0
    device._pose_coverage_handler.mark_mission_completed()
    assert device.mowing_progress_percent == 100.0
    assert device._pose_coverage_handler._mission_completed is True
    
    # Now simulate status change to mowing (status code 1)
    status_message = {
        'method': 'properties_changed',
        'params': [{'siid': 2, 'piid': 1, 'value': 1}]  # Status = 1 (mowing)
    }
    
    device._handle_message(status_message)
    
    # Mission completion flag should be reset
    assert device._pose_coverage_handler._mission_completed is False
    
    # Verify status change was notified
    status_changes = [change for change in property_changes if change[0] == "status"]
    assert len(status_changes) > 0
    assert status_changes[-1][1] == 1


@pytest.mark.asyncio
async def test_start_mowing_resets_mission_completion_flag(device):
    """Test that start_mowing resets mission completion flag for new mission."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    
    # Simulate completed mission
    device._pose_coverage_handler._progress_percent = 96.0
    device._pose_coverage_handler.mark_mission_completed()
    assert device.mowing_progress_percent == 100.0
    assert device._pose_coverage_handler._mission_completed is True
    
    # Start new mowing session
    result = await device.start_mowing()
    assert result is True
    
    # Mission completion flag should be reset
    assert device._pose_coverage_handler._mission_completed is False


@pytest.mark.asyncio
async def test_full_mission_lifecycle_workflow(device):
    """Test complete mission lifecycle: start -> progress -> complete -> start new."""
    property_changes = []
    
    def property_change_callback(name, value):
        property_changes.append((name, value))
    
    device.register_property_callback(property_change_callback)
    device._cloud_device.set_connected_state(True)
    await device.connect()
    
    # Step 1: Start mowing
    await device.start_mowing()
    assert device._pose_coverage_handler._mission_completed is False
    
    # Step 2: Simulate progress updates during mowing (50%, then 96%)
    # Task layout: [region_id, task_id, percent_lo, percent_hi, total(3), finish(3)]
    progress_50 = {
        'method': 'properties_changed',
        'params': [{
            'siid': 1, 'piid': 4,
            'value': [
                0xCE,
                0, 0, 0, 0, 0, 0,                     # pose
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # trace
                0, 0, 0x88, 0x13, 0x10, 0x27, 0x00, 0x88, 0x13, 0x00,  # task: 5000=>50%, total=10000, finish=5000
                0xCE
            ]
        }]
    }
    device._handle_message(progress_50)
    assert device.mowing_progress_percent == 50.0
    
    progress_96 = {
        'method': 'properties_changed',
        'params': [{
            'siid': 1, 'piid': 4,
            'value': [
                0xCE,
                0, 0, 0, 0, 0, 0,                     # pose
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # trace
                0, 0, 0x80, 0x25, 0x10, 0x27, 0x00, 0x80, 0x25, 0x00,  # task: 9600=>96%, total=10000, finish=9600
                0xCE
            ]
        }]
    }
    device._handle_message(progress_96)
    assert device.mowing_progress_percent == 96.0
    
    # Step 3: Mission completes - receive completion event
    completion_event = {
        'method': 'event_occured',
        'params': {
            'siid': 4, 'eiid': 1,
            'arguments': [
                {'piid': 1, 'value': 96},
                {'piid': 2, 'value': 45},
                {'piid': 3, 'value': 9600},
                {'piid': 8, 'value': 1729000000},
            ]
        }
    }
    device._handle_message(completion_event)
    
    # Progress should now be capped at 100%
    assert device.mowing_progress_percent == 100.0
    assert device._pose_coverage_handler._mission_completed is True
    
    # Step 4: Status changes to docked (charging complete = 13)
    docked_message = {
        'method': 'properties_changed',
        'params': [{'siid': 2, 'piid': 1, 'value': 13}]
    }
    device._handle_message(docked_message)
    
    # Mission completion flag should still be True
    assert device._pose_coverage_handler._mission_completed is True
    
    # Step 5: Start new mission
    await device.start_mowing()
    
    # Mission completion flag should be reset
    assert device._pose_coverage_handler._mission_completed is False
    
    # Step 6: New mission progress should not be capped
    progress_30 = {
        'method': 'properties_changed',
        'params': [{
            'siid': 1, 'piid': 4,
            'value': [
                0xCE,
                0, 0, 0, 0, 0, 0,                     # pose
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # trace
                0, 0, 0xB8, 0x0B, 0x10, 0x27, 0x00, 0xB8, 0x0B, 0x00,  # task: 3000=>30%, total=10000, finish=3000
                0xCE
            ]
        }]
    }
    device._handle_message(progress_30)

    # Should show actual progress, not capped
    assert device.mowing_progress_percent == 30.0


def test_fetch_firmware_status_up_to_date(device):
    """hasNewFirmware=False means firmware is up to date (no update)."""
    device._cloud_device.set_connected_state(True)
    device._cloud_device.check_device_version_result = {
        "curVersion": "4.3.6_0550",
        "hasNewFirmware": False,
    }

    result = asyncio.get_event_loop().run_until_complete(device.fetch_firmware_status())

    assert result is True
    assert device.firmware_update_available is False
    assert device.firmware_latest_version is None


def test_fetch_firmware_status_update_available(device):
    """hasNewFirmware=True surfaces the available newVersion."""
    device._cloud_device.set_connected_state(True)
    device._cloud_device.check_device_version_result = {
        "curVersion": "4.3.6_0550",
        "newVersion": "4.3.6_0625",
        "hasNewFirmware": True,
    }

    result = asyncio.get_event_loop().run_until_complete(device.fetch_firmware_status())

    assert result is True
    assert device.firmware_update_available is True
    assert device.firmware_latest_version == "4.3.6_0625"


def test_fetch_firmware_status_clears_stale_availability(device):
    """A subsequent up-to-date response clears a previously-available update."""
    device._cloud_device.set_connected_state(True)
    device._firmware_new_available = True
    device._firmware_latest_version = "4.3.6_0625"
    device._cloud_device.check_device_version_result = {
        "curVersion": "4.3.6_0625",
        "hasNewFirmware": False,
    }

    result = asyncio.get_event_loop().run_until_complete(device.fetch_firmware_status())

    assert result is True
    assert device.firmware_update_available is False
    assert device.firmware_latest_version is None


def test_fetch_firmware_status_no_data(device):
    """A response without data should be a no-op failure."""
    device._cloud_device.set_connected_state(True)
    device._cloud_device.check_device_version_result = None

    result = asyncio.get_event_loop().run_until_complete(device.fetch_firmware_status())

    assert result is False
    assert device.firmware_update_available is False


def test_fetch_firmware_status_notifies_on_change(device):
    """A newly-available update should fire a property-change callback."""
    device._cloud_device.set_connected_state(True)
    device._cloud_device.check_device_version_result = {
        "curVersion": "4.3.6_0550",
        "newVersion": "4.3.6_0625",
        "hasNewFirmware": True,
    }

    notified: list[tuple[str, object]] = []
    device.register_property_callback(lambda name, value: notified.append((name, value)))

    asyncio.get_event_loop().run_until_complete(device.fetch_firmware_status())

    assert ("firmware_update_available", True) in notified



def _heartbeat_props(byte17: int, byte18: int, code: int = 0):
    """Build a get_properties response for property 1:1 with the given bytes."""
    value = [0] * 22
    value[17] = byte17
    value[18] = byte18
    return [{"siid": 1, "piid": 1, "code": code, "value": value}]


def test_online_defaults_to_true(device):
    """A freshly created device is considered online until a poll proves otherwise."""
    assert device.online is True


def test_update_online_status_online_from_heartbeat(device):
    """A heartbeat with an active uplink byte keeps the device online."""
    device._cloud_device.get_properties_result = _heartbeat_props(byte17=1, byte18=0)
    result = asyncio.get_event_loop().run_until_complete(device.async_update_online_status())
    assert result is True
    assert device.online is True


def test_update_online_status_online_from_high_bit(device):
    """Byte 18 with its high bit set also indicates an online device."""
    device._cloud_device.get_properties_result = _heartbeat_props(byte17=0, byte18=128)
    result = asyncio.get_event_loop().run_until_complete(device.async_update_online_status())
    assert result is True
    assert device.online is True


def test_update_online_status_offline_when_bytes_clear(device):
    """Stale connectivity bytes mark the device offline and notify listeners."""
    notified: list[tuple[str, object]] = []
    device.register_property_callback(lambda name, value: notified.append((name, value)))

    device._cloud_device.get_properties_result = _heartbeat_props(byte17=0, byte18=0)
    result = _run_online_polls(device, ONLINE_OFFLINE_DEBOUNCE_POLLS)

    assert result is False
    assert device.online is False
    assert ("online", False) in notified


def test_update_online_status_offline_when_call_fails(device):
    """Repeated cloud failures (device offline) flip the device offline."""
    device._cloud_device.get_properties_result = TimeoutError("Device offline")
    result = _run_online_polls(device, ONLINE_OFFLINE_DEBOUNCE_POLLS)
    assert result is False
    assert device.online is False


def test_update_online_status_offline_is_debounced(device):
    """A single offline poll must not flip the device offline (debounce)."""
    notified: list[tuple[str, object]] = []
    device.register_property_callback(lambda name, value: notified.append((name, value)))

    device._cloud_device.get_properties_result = _heartbeat_props(byte17=0, byte18=0)

    # Fewer than the debounce threshold: still considered online.
    for _ in range(ONLINE_OFFLINE_DEBOUNCE_POLLS - 1):
        result = asyncio.get_event_loop().run_until_complete(
            device.async_update_online_status()
        )
        assert result is False
        assert device.online is True

    # The threshold-th consecutive offline poll finally flips it offline.
    result = asyncio.get_event_loop().run_until_complete(
        device.async_update_online_status()
    )
    assert result is False
    assert device.online is False
    assert ("online", False) in notified


def test_update_online_status_debounce_resets_on_online(device):
    """An intervening online poll resets the debounce so the count restarts."""
    # Rack up offline polls just short of the threshold.
    device._cloud_device.get_properties_result = _heartbeat_props(byte17=0, byte18=0)
    for _ in range(ONLINE_OFFLINE_DEBOUNCE_POLLS - 1):
        asyncio.get_event_loop().run_until_complete(device.async_update_online_status())
    assert device.online is True

    # A single online heartbeat clears the accumulated offline count.
    device._cloud_device.get_properties_result = _heartbeat_props(byte17=1, byte18=0)
    asyncio.get_event_loop().run_until_complete(device.async_update_online_status())
    assert device.online is True

    # One more offline poll must not be enough on its own to flip offline.
    device._cloud_device.get_properties_result = _heartbeat_props(byte17=0, byte18=0)
    asyncio.get_event_loop().run_until_complete(device.async_update_online_status())
    assert device.online is True


def test_incoming_message_restores_online(device):
    """Any inbound MQTT message immediately marks the device back online."""
    device._online = False
    notified: list[tuple[str, object]] = []
    device.register_property_callback(lambda name, value: notified.append((name, value)))

    device._handle_message({"method": "properties_changed", "params": []})

    assert device.online is True
    assert ("online", True) in notified


# A full mowing preference record as reported for a map-wide (area 0) entry.
# Slot 4 carries the cutting height in millimeters, so this record is 6 cm.
_MOWING_PREFERENCE_RECORD = [3, 0, 0, 1, 60, 0, 180, 1, 0, 1, 1, 1, 1, 20, 20, 7, 1]


def _mowing_preference_responder(record=None, *, reject_full_record=False):
    """Build an action responder that serves mowing preference reads and writes."""
    served_record = list(_MOWING_PREFERENCE_RECORD if record is None else record)
    writes: list[list[int]] = []

    def responder(siid, aiid, parameters, retry_count):
        payload = parameters[0]
        if payload["m"] == "g":
            return {"code": 0, "out": [{"r": 0, "d": list(served_record)}]}

        writes.append(list(payload["d"]))
        if reject_full_record and len(writes) == 1:
            return {"code": 0, "out": [{"r": -3}]}
        return {"code": 0, "out": [{"r": 0}]}

    return responder, writes


def _load_two_map_vector_map(device):
    """Attach a two-map vector map and make map 1 the current map."""
    device._vector_map = SimpleNamespace(
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ]
    )
    device._current_map_id = 1


@pytest.mark.asyncio
async def test_refresh_cutting_height_reads_the_map_wide_record(device):
    """Reading the height should query area 0 of the current map's record."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_two_map_vector_map(device)
    device._cloud_device.action_result, _ = _mowing_preference_responder()

    height = await device.refresh_cutting_height()

    assert height == 6.0
    assert device.cutting_height == 6.0
    _, _, parameters, _ = device._cloud_device.action_calls[0]
    assert parameters == [{"m": "g", "t": "PRE", "d": {"idx": 0, "region": 0}}]


@pytest.mark.asyncio
async def test_set_cutting_height_writes_back_the_record_with_only_the_height_changed(device):
    """Setting the height must preserve every other slot of the record."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_two_map_vector_map(device)
    device._cloud_device.action_result, writes = _mowing_preference_responder()

    result = await device.set_cutting_height(4.5)

    assert result is True
    assert len(writes) == 1
    expected_record = list(_MOWING_PREFERENCE_RECORD)
    expected_record[0] = 0  # version is zeroed on write
    expected_record[1] = 0  # map index of map ID 1
    expected_record[2] = 0  # map-wide area ID
    expected_record[4] = 45
    assert writes[0] == expected_record
    assert device.cutting_height == 4.5


@pytest.mark.asyncio
async def test_set_cutting_height_targets_the_requested_map(device):
    """An explicit map ID should address that map without touching the cached height."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_two_map_vector_map(device)
    device._cloud_device.action_result, writes = _mowing_preference_responder()

    result = await device.set_cutting_height(7, map_id=2)

    assert result is True
    _, _, read_parameters, _ = device._cloud_device.action_calls[0]
    assert read_parameters == [{"m": "g", "t": "PRE", "d": {"idx": 1, "region": 0}}]
    assert writes[0][1] == 1
    assert writes[0][4] == 70
    assert device.cutting_height is None


@pytest.mark.asyncio
async def test_set_cutting_height_retries_with_the_short_record(device):
    """A record the firmware rejects should be retried without its trailing slots."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_two_map_vector_map(device)
    device._cloud_device.action_result, writes = _mowing_preference_responder(reject_full_record=True)

    result = await device.set_cutting_height(5)

    assert result is True
    assert len(writes) == 2
    assert len(writes[0]) == 17
    assert writes[1] == writes[0][:16]
    assert device.cutting_height == 5.0


@pytest.mark.asyncio
async def test_set_cutting_height_fails_when_the_record_cannot_be_read(device):
    """Without the current record there is nothing safe to write back."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_two_map_vector_map(device)
    device._cloud_device.action_result = {"code": 0, "out": [{"r": -1}]}

    result = await device.set_cutting_height(5)

    assert result is False
    assert len(device._cloud_device.action_calls) == 1
    assert device.cutting_height is None


@pytest.mark.asyncio
async def test_set_cutting_height_rejects_heights_outside_the_supported_range(device):
    """Heights the protocol cannot carry should be rejected before any request."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_two_map_vector_map(device)
    device._cloud_device.action_result, _ = _mowing_preference_responder()

    with pytest.raises(ValueError):
        await device.set_cutting_height(2.5)
    with pytest.raises(ValueError):
        await device.set_cutting_height(12)

    assert len(device._cloud_device.action_calls) == 0


@pytest.mark.asyncio
async def test_set_cutting_height_rejects_unknown_map_ids(device):
    """An unknown map ID should be rejected instead of writing to another map."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_two_map_vector_map(device)
    device._cloud_device.action_result, _ = _mowing_preference_responder()

    result = await device.set_cutting_height(5, map_id=9)

    assert result is False
    assert len(device._cloud_device.action_calls) == 0


@pytest.mark.asyncio
async def test_set_cutting_height_snaps_to_half_centimeter_steps(device):
    """Heights between steps should snap to the nearest settable value."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_two_map_vector_map(device)
    device._cloud_device.action_result, writes = _mowing_preference_responder()

    result = await device.set_cutting_height(5.3)

    assert result is True
    assert writes[0][4] == 55
    assert device.cutting_height == 5.5


@pytest.mark.asyncio
async def test_cutting_height_change_notifies_property_callbacks(device):
    """A changed height should be pushed to registered property callbacks."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_two_map_vector_map(device)
    device._cloud_device.action_result, _ = _mowing_preference_responder()
    notified = []
    device.register_property_callback(lambda name, value: notified.append((name, value)))

    await device.refresh_cutting_height()

    assert ("cutting_height", 6.0) in notified


def _preference_responder(
    *,
    mode=0,
    configured_area_ids=(0,),
    records=None,
    reject_full_record=False,
):
    """Build an action responder that serves the full preference protocol.

    Reads of an area without a record fail the way the device reports a missing
    record, and writes are collected so tests can assert on them.
    """
    stored_records = {0: list(_MOWING_PREFERENCE_RECORD)}
    stored_records.update({int(k): list(v) for k, v in (records or {}).items()})
    available_area_ids = set(configured_area_ids)
    calls: dict[str, list] = {"writes": [], "modes": []}

    def responder(siid, aiid, parameters, retry_count):
        payload = parameters[0]
        if payload.get("t") not in ("PRE", "PREI", "PREP"):
            return {"code": 0, "out": [{"r": 0}]}

        if payload["t"] == "PREI":
            return {
                "code": 0,
                "out": [{"r": 0, "d": {"type": mode, "ver": [[area_id, 1] for area_id in sorted(available_area_ids)]}}],
            }

        if payload["t"] == "PREP":
            calls["modes"].append(payload["d"])
            return {"code": 0, "out": [{"r": 0}]}

        if payload["m"] == "g":
            area_id = payload["d"]["region"]
            if area_id not in available_area_ids:
                return {"code": 0, "out": [{"r": -1}]}
            return {"code": 0, "out": [{"r": 0, "d": list(stored_records[area_id])}]}

        record = list(payload["d"])
        calls["writes"].append(record)
        if reject_full_record and len(calls["writes"]) == 1:
            return {"code": 0, "out": [{"r": -3}]}
        stored_records[record[2]] = record
        available_area_ids.add(record[2])
        return {"code": 0, "out": [{"r": 0}]}

    return responder, calls


def _load_zoned_vector_map(device):
    """Attach a vector map with two maps, the current one carrying three zones."""
    device._vector_map = SimpleNamespace(
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ],
        zones=[
            SimpleNamespace(zone_id=1, name="Lawn", area=12.5),
            SimpleNamespace(zone_id=2, name="Orchard", area=8.0),
            SimpleNamespace(zone_id=3, name="Slope", area=5.0),
        ],
    )
    device._current_map_id = 1


@pytest.mark.asyncio
async def test_set_zone_cutting_height_writes_a_record_for_that_zone(device):
    """A zone height should be written to the zone's own record."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    device._cloud_device.action_result, calls = _preference_responder()

    result = await device.set_cutting_height(4.0, zone_id=2)

    assert result is True
    zone_write = next(write for write in calls["writes"] if write[2] == 2)
    assert zone_write[4] == 40
    assert zone_write[1] == 0  # map index of the current map
    assert device.zone_cutting_heights == {2: 4.0}
    assert device.cutting_height is None


@pytest.mark.asyncio
async def test_set_zone_cutting_height_starts_from_the_zone_record_when_it_exists(device):
    """An existing zone record must be preserved rather than replaced wholesale."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    zone_record = list(_MOWING_PREFERENCE_RECORD)
    zone_record[3] = 0  # a zone-specific efficiency mode
    zone_record[13] = 5  # a zone-specific obstacle setting
    device._cloud_device.action_result, calls = _preference_responder(
        mode=1,
        configured_area_ids=(0, 2),
        records={2: zone_record},
    )

    result = await device.set_cutting_height(6.5, zone_id=2)

    assert result is True
    assert len(calls["writes"]) == 1
    assert calls["writes"][0][3] == 0
    assert calls["writes"][0][13] == 5
    assert calls["writes"][0][4] == 65


@pytest.mark.asyncio
async def test_set_zone_cutting_height_switches_the_map_to_per_zone_preferences(device):
    """A zone height has no effect while the map applies its map-wide record."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    device._cloud_device.action_result, calls = _preference_responder(mode=0)

    result = await device.set_cutting_height(4.0, zone_id=2)

    assert result is True
    assert calls["modes"] == [{"idx": 0, "value": 1}]
    assert device.mowing_preference_mode == MowingPreferenceMode.PER_ZONE


@pytest.mark.asyncio
async def test_switching_to_per_zone_preferences_seeds_untouched_zones(device):
    """Zones without a record of their own must keep the map-wide settings."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    device._cloud_device.action_result, calls = _preference_responder(mode=0)

    await device.set_cutting_height(4.0, zone_id=2)

    seeded_area_ids = {write[2] for write in calls["writes"]}
    assert seeded_area_ids == {1, 2, 3}
    for write in calls["writes"]:
        if write[2] == 2:
            continue
        assert write[4] == _MOWING_PREFERENCE_RECORD[4]


@pytest.mark.asyncio
async def test_set_zone_cutting_height_leaves_an_already_per_zone_map_alone(device):
    """A map already using its per-zone records needs no mode change or seeding."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    device._cloud_device.action_result, calls = _preference_responder(mode=1)

    result = await device.set_cutting_height(4.0, zone_id=2)

    assert result is True
    assert calls["modes"] == []
    assert [write[2] for write in calls["writes"]] == [2]


@pytest.mark.asyncio
async def test_set_zone_cutting_height_rejects_unknown_zone_ids(device):
    """An unknown zone should be rejected instead of creating a stray record."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    device._cloud_device.action_result, calls = _preference_responder()

    result = await device.set_cutting_height(4.0, zone_id=9)

    assert result is False
    assert calls["writes"] == []


@pytest.mark.asyncio
async def test_refresh_zone_cutting_heights_reads_every_configured_zone(device):
    """Reading should report the height of each zone that has its own record."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    zone_one = list(_MOWING_PREFERENCE_RECORD)
    zone_one[4] = 35
    zone_three = list(_MOWING_PREFERENCE_RECORD)
    zone_three[4] = 70
    device._cloud_device.action_result, _ = _preference_responder(
        mode=1,
        configured_area_ids=(0, 1, 3),
        records={1: zone_one, 3: zone_three},
    )

    zone_heights = await device.refresh_zone_cutting_heights()

    assert zone_heights == {1: 3.5, 3: 7.0}
    assert device.zone_cutting_heights == {1: 3.5, 3: 7.0}
    assert device.mowing_preference_mode == MowingPreferenceMode.PER_ZONE


@pytest.mark.asyncio
async def test_set_mowing_preference_mode_switches_back_to_the_map_wide_record(device):
    """Switching back should send the mode command and cache the new mode."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    device._cloud_device.action_result, calls = _preference_responder(mode=1)

    result = await device.set_mowing_preference_mode(MowingPreferenceMode.MAP_WIDE)

    assert result is True
    assert calls["modes"] == [{"idx": 0, "value": 0}]
    assert device.mowing_preference_mode == MowingPreferenceMode.MAP_WIDE


@pytest.mark.asyncio
async def test_switching_the_current_map_drops_the_cached_heights(device):
    """The cached heights describe one map, so a map switch must clear them."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    device._cloud_device.action_result, _ = _preference_responder(mode=1)
    await device.refresh_cutting_height()
    await device.set_cutting_height(4.0, zone_id=2)
    assert device.cutting_height is not None
    assert device.zone_cutting_heights

    await device.set_current_map(2)

    assert device.cutting_height is None
    assert device.zone_cutting_heights == {}
    assert device.mowing_preference_mode is None


def _load_multi_zone_vector_map(device):
    """Attach geometry where each map carries its own distinct set of zones."""
    map_one = SimpleNamespace(zones=[SimpleNamespace(zone_id=1, name="Lawn", area=12.5)])
    map_two = SimpleNamespace(zones=[SimpleNamespace(zone_id=7, name="Cellar", area=4.0)])
    device._vector_map = SimpleNamespace(
        available_maps=[
            SimpleNamespace(map_id=1, map_index=0, name="Front", total_area=25.0),
            SimpleNamespace(map_id=2, map_index=1, name="Back", total_area=30.5),
        ],
        zones=map_one.zones,
        maps={1: map_one, 2: map_two},
    )
    device._current_map_id = 1


@pytest.mark.asyncio
async def test_refresh_mowing_preference_mode_reads_and_caches_the_mode(device):
    """The mode decides which heights apply, so it must be readable on its own."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    device._cloud_device.action_result, _ = _preference_responder(mode=1)

    mode = await device.refresh_mowing_preference_mode()

    assert mode == MowingPreferenceMode.PER_ZONE
    assert device.mowing_preference_mode == MowingPreferenceMode.PER_ZONE
    _, _, parameters, _ = device._cloud_device.action_calls[0]
    assert parameters == [{"m": "g", "t": "PREI", "d": {"idx": 0}}]


@pytest.mark.asyncio
async def test_refresh_mowing_preference_mode_does_not_cache_another_map(device):
    """The cache describes the current map, so another map's mode must not land in it."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_zoned_vector_map(device)
    device._cloud_device.action_result, _ = _preference_responder(mode=1)

    mode = await device.refresh_mowing_preference_mode(map_id=2)

    assert mode == MowingPreferenceMode.PER_ZONE
    assert device.mowing_preference_mode is None
    _, _, parameters, _ = device._cloud_device.action_calls[0]
    assert parameters == [{"m": "g", "t": "PREI", "d": {"idx": 1}}]


@pytest.mark.asyncio
async def test_set_zone_cutting_height_validates_against_the_targeted_map(device):
    """Zone validation must use the target map's zones, not the active map's."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_multi_zone_vector_map(device)
    device._cloud_device.action_result, calls = _preference_responder(mode=1)

    assert await device.set_cutting_height(4.0, map_id=2, zone_id=7) is True
    assert [write[2] for write in calls["writes"]] == [7]
    assert calls["writes"][0][1] == 1  # map index of map ID 2

    # Zone 1 exists on the active map but not on map 2.
    assert await device.set_cutting_height(4.0, map_id=2, zone_id=1) is False
    assert len(calls["writes"]) == 1


@pytest.mark.asyncio
async def test_set_zone_cutting_height_defers_when_the_map_geometry_is_unknown(device):
    """Without geometry for a map the device has to be the one to reject the zone."""
    device._cloud_device.set_connected_state(True)
    await device.connect()
    _load_multi_zone_vector_map(device)
    del device._vector_map.maps[2]
    device._cloud_device.action_result, calls = _preference_responder(mode=1)

    assert await device.set_cutting_height(4.0, map_id=2, zone_id=99) is True
    assert [write[2] for write in calls["writes"]] == [99]
