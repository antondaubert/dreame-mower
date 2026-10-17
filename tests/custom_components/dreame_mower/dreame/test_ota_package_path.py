"""Tests for OTA package path property (99:10) handling."""

import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from custom_components.dreame_mower.dreame.device import DreameMowerDevice


@pytest.fixture
def device():
    """Create a test device instance that has no download URL to offer."""
    device = DreameMowerDevice(
        device_id="test_device",
        username="test_user",
        password="test_pass",
        account_type="dreame",
        country="DE",
        hass_config_dir="/tmp/test_config"
    )
    device._cloud_device.get_file_download_url = Mock(return_value=None)
    return device


def test_ota_package_path_handling(device):
    """Test device file path property (99:10) handling."""
    # Track property changes
    property_changes = []
    
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    # Test the specific message structure from the user's example
    message = {
        "siid": 99, 
        "piid": 10, 
        "value": "ali_dreame/2025/10/11/JU954***/-1*******1_210019111.0430.pack.tbz2"
    }
    
    # Handle the message
    assert device._handle_mqtt_property_update(message) is True
    
    assert device._device_file_path == "ali_dreame/2025/10/11/JU954***/-1*******1_210019111.0430.pack.tbz2"
    
    # Verify notification was sent
    assert ("device_file_path", "ali_dreame/2025/10/11/JU954***/-1*******1_210019111.0430.pack.tbz2") in property_changes


def test_ota_package_path_update_notification(device):
    """Test that changing device file path triggers notification."""
    property_changes = []
    
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    # First update
    message1 = {"siid": 99, "piid": 10, "value": "path/to/package1.pack.tbz2"}
    device._handle_mqtt_property_update(message1)
    
    # Second update with different value
    message2 = {"siid": 99, "piid": 10, "value": "path/to/package2.pack.tbz2"}
    device._handle_mqtt_property_update(message2)
    
    # Both should trigger notifications
    assert len(property_changes) == 2
    assert ("device_file_path", "path/to/package1.pack.tbz2") in property_changes
    assert ("device_file_path", "path/to/package2.pack.tbz2") in property_changes


def test_ota_package_path_no_duplicate_notification(device):
    """Test that same device file path value doesn't trigger duplicate notifications."""
    property_changes = []
    
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    
    device.register_property_callback(track_changes)
    
    # Send same value twice
    message = {"siid": 99, "piid": 10, "value": "path/to/package.pack.tbz2"}
    device._handle_mqtt_property_update(message)
    device._handle_mqtt_property_update(message)
    
    # Should only trigger one notification (first time)
    file_notifications = [pc for pc in property_changes if pc[0] == "device_file_path"]
    assert len(file_notifications) == 1


@patch('custom_components.dreame_mower.dreame.utils.requests.get')
def test_ota_package_download_success(mock_get, device):
    """Test successful firmware package download."""
    # Setup mock response
    mock_response = Mock()
    mock_response.content = b"fake_firmware_data"
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response
    
    # Mock the cloud device's get_file_download_url method
    device._cloud_device.get_file_download_url = Mock(return_value="https://example.com/package.tbz2")
    
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    device.register_property_callback(track_changes)
    
    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        device._hass_config_dir = tmpdir
        
        # Trigger download via property update
        message = {"siid": 99, "piid": 10, "value": "ali_dreame/2025/10/11/test/package.pack.tbz2"}
        device._handle_mqtt_property_update(message)
        
        # Verify file was downloaded (mirroring the directory structure)
        expected_path = os.path.join(tmpdir, "www", "dreame", "ali_dreame/2025/10/11/test/package.pack.tbz2")
        assert os.path.exists(expected_path)
        
        # Verify file content
        with open(expected_path, "rb") as f:
            assert f.read() == b"fake_firmware_data"
        
        # Verify download notification was sent
        download_notifications = [pc for pc in property_changes if pc[0] == "device_file_downloaded"]
        assert len(download_notifications) == 1
        assert download_notifications[0][1]["path"] == "ali_dreame/2025/10/11/test/package.pack.tbz2"
        assert download_notifications[0][1]["size_bytes"] == 18


@patch('custom_components.dreame_mower.dreame.utils.requests.get')
def test_ota_package_download_no_url(mock_get, device):
    """Test device file download when no URL is available."""
    # Mock the cloud device to return None (no URL available)
    device._cloud_device.get_file_download_url = Mock(return_value=None)
    
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    device.register_property_callback(track_changes)
    
    # Trigger property update
    message = {"siid": 99, "piid": 10, "value": "ali_dreame/2025/10/11/test/package.pack.tbz2"}
    device._handle_mqtt_property_update(message)
    
    # Verify no download notification (download failed)
    download_notifications = [pc for pc in property_changes if pc[0] == "device_file_downloaded"]
    assert len(download_notifications) == 0
    
    # Property update notification should still be sent
    path_notifications = [pc for pc in property_changes if pc[0] == "device_file_path"]
    assert len(path_notifications) == 1


@patch('custom_components.dreame_mower.dreame.utils.requests.get')
def test_ota_package_download_request_failure(mock_get, device):
    """Test device file download when HTTP request fails."""
    # Setup mock to raise exception
    import requests
    mock_get.side_effect = requests.exceptions.RequestException("Network error")
    
    # Mock the cloud device's get_file_download_url method
    device._cloud_device.get_file_download_url = Mock(return_value="https://example.com/package.tbz2")
    
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    device.register_property_callback(track_changes)
    
    # Trigger property update
    message = {"siid": 99, "piid": 10, "value": "ali_dreame/2025/10/11/test/package.pack.tbz2"}
    device._handle_mqtt_property_update(message)
    
    # Verify no download notification (download failed)
    download_notifications = [pc for pc in property_changes if pc[0] == "device_file_downloaded"]
    assert len(download_notifications) == 0
    
    # Property update notification should still be sent
    path_notifications = [pc for pc in property_changes if pc[0] == "device_file_path"]
    assert len(path_notifications) == 1


@patch('custom_components.dreame_mower.dreame.utils.requests.get')
def test_log_file_download_success(mock_get, device):
    """Test successful log file download (reported via app)."""
    # Setup mock response for log file
    mock_response = Mock()
    mock_response.content = b"fake_log_data_content"
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response
    
    # Mock the cloud device's get_file_download_url method
    device._cloud_device.get_file_download_url = Mock(return_value="https://example.com/logs.tbz2")
    
    # Track property changes
    property_changes = []
    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))
    device.register_property_callback(track_changes)
    
    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        device._hass_config_dir = tmpdir
        
        # Trigger download via property update with log file path
        # This simulates the message from the issue: user selected "Report logs" in app
        message = {
            "siid": 99, 
            "piid": 10, 
            "value": "ali_dreame/2025/10/11/JU954/-1*******1_210019111.0430.pack.tbz2"
        }
        device._handle_mqtt_property_update(message)
        
        # Verify file was downloaded (mirroring the directory structure)
        expected_path = os.path.join(tmpdir, "www", "dreame", "ali_dreame/2025/10/11/JU954/-1*******1_210019111.0430.pack.tbz2")
        assert os.path.exists(expected_path)
        
        # Verify file content
        with open(expected_path, "rb") as f:
            assert f.read() == b"fake_log_data_content"
        
        # Verify download notification was sent
        download_notifications = [pc for pc in property_changes if pc[0] == "device_file_downloaded"]
        assert len(download_notifications) == 1
        assert download_notifications[0][1]["path"] == "ali_dreame/2025/10/11/JU954/-1*******1_210019111.0430.pack.tbz2"
        assert download_notifications[0][1]["size_bytes"] == 21


def test_device_file_path_piid_20_handled(device):
    """Test that siid:99, piid:20 is handled the same as piid:10 (issue #26)."""
    property_changes = []

    def track_changes(prop_name, value):
        property_changes.append((prop_name, value))

    device.register_property_callback(track_changes)

    message = {
        "siid": 99,
        "piid": 20,
        "value": "ali_dreame/2026/03/03/HT6*****/-1*******3_013****99.0473.bin",
    }

    assert device._handle_mqtt_property_update(message) is True
    assert device._device_file_path == "ali_dreame/2026/03/03/HT6*****/-1*******3_013****99.0473.bin"
    assert ("device_file_path", "ali_dreame/2026/03/03/HT6*****/-1*******3_013****99.0473.bin") in property_changes
