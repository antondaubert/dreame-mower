"""Tests for the Dreame Mower Camera Entity."""
import asyncio
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.dreame_mower.camera import DreameMowerCameraEntity
from custom_components.dreame_mower.coordinator import DreameMowerCoordinator
from custom_components.dreame_mower.dreame.const import POSE_COVERAGE_PROPERTY
from custom_components.dreame_mower.dreame.property.pose_coverage import POSE_COVERAGE_COORDINATES_PROPERTY_NAME
from custom_components.dreame_mower.dreame.property.property_misc import PROPERTY_1_1_TASK_STATUS_NAME


# Path to test data
TEST_DATA_DIR = Path(__file__).parent / "dreame" / "test_data"
GOLDEN_JSON_FILE = TEST_DATA_DIR / "test_svg_map_generator.json"
GOLDEN_SVG_FILE = TEST_DATA_DIR / "test_svg_map_generator_rotated_0_golden.svg"


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = Mock(spec=DreameMowerCoordinator)
    coordinator.hass = Mock()
    coordinator.hass.loop = asyncio.get_event_loop()
    coordinator.device = Mock()
    coordinator.device.name = "Test Mower"
    coordinator.device.status_code = 1  # Some default status
    coordinator.device.task_status = None
    coordinator.device.mowing_session_active = False
    coordinator.device.register_property_callback = Mock()
    coordinator.device.mower_coordinates = None  # No current position by default
    coordinator.device.cloud_device = Mock()
    coordinator.device.cloud_device.get_properties = Mock()
    coordinator.device_connected = True
    coordinator.device.device_reachable = True
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    config_entry = Mock(spec=pytest.importorskip("homeassistant.config_entries").ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    config_entry.options = {}
    return config_entry


@pytest.fixture
def camera_entity(mock_coordinator, mock_config_entry):
    """Create a camera entity instance."""
    with patch("custom_components.dreame_mower.camera.DreameMowerCameraEntity._refresh_historical_files_cache", new_callable=AsyncMock):
        entity = DreameMowerCameraEntity(mock_coordinator, mock_config_entry)
        # Mock the timer to avoid actual threading
        entity._pose_coverage_timer = Mock()
        return entity


@pytest.fixture
def golden_map_data():
    """Load the golden JSON test data."""
    with open(GOLDEN_JSON_FILE, 'r') as f:
        return json.load(f)


@pytest.fixture
def golden_svg():
    """Load the golden SVG expected output."""
    with open(GOLDEN_SVG_FILE, 'r') as f:
        return f.read()


class TestDreameMowerCameraEntity:
    """Test the DreameMowerCameraEntity class."""

    def test_initialization(self, camera_entity, mock_coordinator):
        """Test camera entity initialization."""
        assert camera_entity.coordinator == mock_coordinator
        assert camera_entity._attr_unique_id == "test_entry_id_map_camera"
        assert camera_entity._attr_translation_key == "map_camera"
        assert camera_entity.content_type == "image/svg+xml"
    
    def test_save_actual_svg_output(self, camera_entity, golden_map_data, golden_svg):
        """Generate and save the actual SVG output for comparison with golden file.
        
        It compares the actual output with the golden file, allowing only
        the timestamp in "Updated: YYYY-MM-DD HH:MM:SS" to differ.
        """
        # Generate SVG from golden data
        result = camera_entity._generate_map_image(golden_map_data)
        
        # Save to actual output file
        actual_svg_file = TEST_DATA_DIR / "test_svg_map_generator_rotated_0_actual.svg"
        with open(actual_svg_file, 'wb') as f:
            f.write(result)
        
        # Verify the file was written
        assert actual_svg_file.exists()
        assert actual_svg_file.stat().st_size > 0
        
        # Basic validation that it's valid SVG
        svg_output = result.decode('utf-8')
        assert svg_output.startswith('<?xml')
        assert '<svg' in svg_output
        assert '</svg>' in svg_output
        
        # Compare with golden file, normalizing timestamps
        # Pattern to match: "Updated: 2025-10-19 15:01:49" or similar
        timestamp_pattern = r'Updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
        
        # Normalize both SVGs by replacing timestamps with a placeholder
        actual_normalized = re.sub(timestamp_pattern, 'Updated: TIMESTAMP', svg_output)
        golden_normalized = re.sub(timestamp_pattern, 'Updated: TIMESTAMP', golden_svg)
        
        # Compare the normalized versions
        assert actual_normalized == golden_normalized, (
            "Generated SVG differs from golden file (excluding timestamp). "
            f"Actual file saved to: {actual_svg_file}"
        )

    @pytest.mark.asyncio
    async def test_request_pose_coverage_success(self, camera_entity, mock_coordinator):
        """Test successful pose coverage request."""
        mock_coordinator.device_connected = True
        mock_coordinator.device.device_reachable = True
        
        # Mock run_in_executor to execute the lambda immediately
        async def mock_run_in_executor(executor, func, *args):
            return func(*args)
            
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=mock_run_in_executor)
            
            await camera_entity._request_pose_coverage_property()
            
            # Verify get_properties was called
            mock_coordinator.device.cloud_device.get_properties.assert_called_once()
            args = mock_coordinator.device.cloud_device.get_properties.call_args[0][0]
            assert args[0]["siid"] == POSE_COVERAGE_PROPERTY.siid
            assert args[0]["piid"] == POSE_COVERAGE_PROPERTY.piid

    @pytest.mark.asyncio
    async def test_request_pose_coverage_skipped_if_disconnected(self, camera_entity, mock_coordinator):
        """Test request skipped if device not connected."""
        mock_coordinator.device_connected = False
        
        await camera_entity._request_pose_coverage_property()
        
        mock_coordinator.device.cloud_device.get_properties.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_pose_coverage_skipped_if_unreachable(self, camera_entity, mock_coordinator):
        """Test request skipped if device not reachable."""
        mock_coordinator.device_connected = True
        mock_coordinator.device.device_reachable = False
        
        await camera_entity._request_pose_coverage_property()
        
        mock_coordinator.device.cloud_device.get_properties.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_pose_coverage_handles_timeout(self, camera_entity, mock_coordinator):
        """Test handling of TimeoutError (device offline)."""
        mock_coordinator.device_connected = True
        mock_coordinator.device.device_reachable = True
        
        # Mock run_in_executor to raise TimeoutError
        async def mock_run_in_executor(*args, **kwargs):
            raise TimeoutError("Device offline")
            
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=mock_run_in_executor)
            
            # Setup timer mock
            timer_mock = Mock()
            camera_entity._pose_coverage_timer = timer_mock
            
            await camera_entity._request_pose_coverage_property()
            
            # Verify timer was cancelled (stopped)
            timer_mock.cancel.assert_called_once()
            assert camera_entity._pose_coverage_timer is None

    def test_handle_property_change_resumes_polling(self, camera_entity, mock_coordinator):
        """Test that property change resumes polling if device becomes reachable."""
        # Setup state: device reachable, session active, but timer stopped (e.g. after offline)
        mock_coordinator.device.device_reachable = True
        camera_entity._session_active = True
        camera_entity._pose_coverage_timer = None

        with patch.object(camera_entity, "_start_pose_coverage_timer") as mock_start:
            # Trigger property change
            camera_entity._handle_property_change("some_property", "value")

            # Verify timer started
            mock_start.assert_called_once()

    def test_handle_property_change_does_not_resume_if_session_inactive(self, camera_entity, mock_coordinator):
        """Test that polling does not resume when no mowing session is active."""
        mock_coordinator.device.device_reachable = True
        camera_entity._session_active = False
        camera_entity._pose_coverage_timer = None

        with patch.object(camera_entity, "_start_pose_coverage_timer") as mock_start:
            camera_entity._handle_property_change("some_property", "value")
            mock_start.assert_not_called()

    def test_handle_property_change_does_not_resume_if_unreachable(self, camera_entity, mock_coordinator):
        """Test that polling does not resume if device is still unreachable."""
        mock_coordinator.device.device_reachable = False
        camera_entity._session_active = True
        camera_entity._pose_coverage_timer = None

        with patch.object(camera_entity, "_start_pose_coverage_timer") as mock_start:
            camera_entity._handle_property_change("some_property", "value")
            mock_start.assert_not_called()

    def test_task_status_change_enters_live_mode(self, camera_entity, mock_coordinator):
        """A task-status change to an active session enters live mode and starts polling."""
        camera_entity._session_active = False
        mock_coordinator.device.mowing_session_active = True

        with patch.object(camera_entity, "_start_pose_coverage_timer") as mock_start, \
             patch.object(camera_entity, "_stop_pose_coverage_timer") as mock_stop:
            camera_entity._handle_property_change(PROPERTY_1_1_TASK_STATUS_NAME, "mowing")

        assert camera_entity._session_active is True
        mock_start.assert_called_once()
        mock_stop.assert_not_called()

    def test_task_status_change_ends_live_mode(self, camera_entity, mock_coordinator):
        """A task-status change to exit/idle ends live mode and clears live coordinates."""
        camera_entity._session_active = True
        camera_entity._live_coordinates = [[1, 2], [3, 4]]
        camera_entity.hass = Mock()
        # Close the scheduled coroutine so it doesn't leak as "never awaited".
        camera_entity.hass.create_task = Mock(side_effect=lambda coro: coro.close())
        mock_coordinator.device.mowing_session_active = False

        with patch.object(camera_entity, "_stop_pose_coverage_timer") as mock_stop, \
             patch.object(camera_entity, "_async_update_image") as mock_update:
            camera_entity._handle_property_change(PROPERTY_1_1_TASK_STATUS_NAME, "exit")

        assert camera_entity._session_active is False
        assert camera_entity._live_coordinates == []
        mock_stop.assert_called_once()
        camera_entity.hass.create_task.assert_called_once()
        mock_update.assert_called_once_with(force_refresh=True)

    def test_task_status_paused_keeps_live_mode(self, camera_entity, mock_coordinator):
        """A task that pauses at the dock stays in live mode (no teardown)."""
        camera_entity._session_active = True
        camera_entity._live_coordinates = [[1, 2]]
        mock_coordinator.device.mowing_session_active = True  # paused → still active

        with patch.object(camera_entity, "_stop_pose_coverage_timer") as mock_stop:
            camera_entity._handle_property_change(PROPERTY_1_1_TASK_STATUS_NAME, "paused")

        assert camera_entity._session_active is True
        assert camera_entity._live_coordinates == [[1, 2]]
        mock_stop.assert_not_called()


class TestCameraCallbackLifecycle:
    """The camera only listens to the device while it lives in Home Assistant."""

    def test_no_registration_before_added_to_hass(self, camera_entity, mock_coordinator):
        """Constructing the entity must not subscribe to device updates."""
        mock_coordinator.device.register_property_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_registers_on_add_and_unregisters_on_remove(
        self, camera_entity, mock_coordinator, mock_config_entry
    ):
        """Being added subscribes; being removed unsubscribes again."""
        mock_coordinator.device.unregister_property_callback = Mock()
        mock_config_entry.add_update_listener = Mock(return_value=Mock())
        camera_entity.hass = Mock()
        camera_entity.hass.create_task = Mock(side_effect=lambda coro: coro.close())

        await camera_entity.async_added_to_hass()

        mock_coordinator.device.register_property_callback.assert_called_once_with(
            camera_entity._handle_property_change
        )

        # Home Assistant runs these when the entity is removed.
        camera_entity._call_on_remove_callbacks()

        mock_coordinator.device.unregister_property_callback.assert_called_once_with(
            camera_entity._handle_property_change
        )

    def test_timer_callback_without_hass_stops_timer(self, camera_entity):
        """A timer firing after removal stops instead of touching hass."""
        camera_entity.hass = None

        with patch.object(camera_entity, "_stop_pose_coverage_timer") as mock_stop, \
             patch.object(camera_entity, "_start_pose_coverage_timer") as mock_start:
            camera_entity._pose_coverage_timer_callback()

        mock_stop.assert_called_once()
        mock_start.assert_not_called()
