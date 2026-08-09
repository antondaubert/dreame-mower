"""Tests for the Dreame Mower protocol module."""

import json
import time
from threading import Thread
from unittest.mock import Mock, patch, PropertyMock
import pytest
import requests

from custom_components.dreame_mower.dreame.cloud.cloud_device import (
    DreameMowerCloudDevice,
)
# Use standard ConnectionError for cloud/device communication issues


class TestDreameMowerCloudDevice:
    """Test DreameMowerCloudDevice class."""

    # Test constants
    TEST_USERNAME = "test_user"
    TEST_PASSWORD = "test_pass" 
    TEST_COUNTRY = "cn"
    TEST_DID = "12345"
    TEST_ACCOUNT_TYPE = "dreame"
    TEST_HOST = "test.host.com"
    SUCCESS_CODE = 0
    TIMEOUT_ERROR_CODE = 80001

    @pytest.fixture
    def protocol(self):
        """Create a protocol instance for testing."""
        return DreameMowerCloudDevice(
            username=self.TEST_USERNAME,
            password=self.TEST_PASSWORD,
            country=self.TEST_COUNTRY,
            account_type=self.TEST_ACCOUNT_TYPE,
            device_id=self.TEST_DID
        )

    def setup_api_call_mock(self, protocol, return_value):
        """Helper method to setup _api_call mock."""
        protocol._cloud_base._api_call = Mock(return_value=return_value)
        return protocol._cloud_base._api_call

    def setup_successful_response_mock(self, status_code=200, response_data=None):
        """Helper method to create a successful response mock."""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.text = json.dumps(response_data) if response_data else '{"code": 0}'
        mock_response.content = json.dumps(response_data).encode() if response_data else b'{"code": 0}'
        return mock_response

    def setup_protocol_for_send_tests(self, protocol):
        """Helper method to setup protocol for send-related tests."""
        protocol._host = self.TEST_HOST
        protocol._device_id = self.TEST_DID
        protocol._cloud_base._id = 1
        return protocol


    def test_init(self):
        """Test protocol initialization."""
        protocol = DreameMowerCloudDevice(
            username="user",
            password="pass",
            country="us",
            device_id="123",
            account_type="mova"
        )
        assert protocol._cloud_base._username == "user"
        assert protocol._cloud_base._password == "pass"
        assert protocol._cloud_base._country == "us"
        assert protocol._device_id == "123"
        assert protocol.connected is False
        assert protocol.device_reachable is True

    def test_device_id_property(self, protocol):
        """Test device_id property."""
        assert protocol.device_id == "12345"

    def test_connected_property(self, protocol):
        """Test connected property integration of cloud base + MQTT connectivity.
        
        The protocol's connected property should return True only when both:
        1. The cloud base HTTP API is connected (connected is True)
        2. The MQTT client is connected (_mqtt_client_connected is True)
        """
        # Mock the base connected property
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock) as mock_base_connected:
            # HTTP not connected - should be False regardless of MQTT state
            mock_base_connected.return_value = False
            protocol._mqtt_client_connected = True
            assert protocol.connected is False
            
            # HTTP connected but MQTT not connected - should be False  
            mock_base_connected.return_value = True
            protocol._mqtt_client_connected = False
            assert protocol.connected is False
            
            # Both HTTP and MQTT connected - should be True
            protocol._mqtt_client_connected = True
            assert protocol.connected is True

    def test_object_name_property(self, protocol):
        """Test object_name property."""
        protocol._model = "test_model"
        protocol._uid = "test_uid"
        protocol._device_id = "test_did"
        expected = "test_model/test_uid/test_did/0"
        assert protocol.object_name == expected

    def test_get_api_url(self, protocol):
        """Test get_api_url method."""
        # The method should return a properly formatted URL with the protocol's country and API strings
        url = protocol._cloud_base.get_api_url()
        assert url.startswith("https://")
        assert protocol._cloud_base._country in url
        assert ":" in url  # Should have port separator

    def test_get_random_agent_id(self):
        """Test get_random_agent_id static method."""
        agent_id = DreameMowerCloudDevice.get_random_agent_id()
        assert len(agent_id) == 13
        assert all(c in "ABCDEF" for c in agent_id)

    def test_initialize_sets_fields_from_base_info(self, protocol):
        """Initializer should set core fields from base device info."""
        protocol._device_id = "test_did"
        s = protocol._cloud_base._api_strings
        info = {
            s[8]: "test_uid",
            "did": "test_did",
            s[35]: "test_model",
            s[9]: "test_host:8883",
            s[10]: json.dumps({}),
        }
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            protocol._cloud_base._api_call = Mock(return_value={"code": 0, "data": info})
            assert protocol._initialize_mqtt_connection_state() is True
        assert protocol._uid == "test_uid"
        assert protocol._device_id == "test_did"
        assert protocol._model == "test_model"
        assert protocol._host == "test_host:8883"

    # Stream key not used in current flow; no dedicated test



    def test_refresh_mqtt_credentials_different(self, protocol):
        """Test _refresh_mqtt_credentials when keys are different."""
        protocol._mqtt_client_key = "old_key"
        protocol._cloud_base._key = "new_key"
        protocol._cloud_base._uuid = "test_uuid"
        protocol._mqtt_client = Mock()
        
        result = protocol._refresh_mqtt_credentials()
        
        assert result is True
        assert protocol._mqtt_client_key == "new_key"
        protocol._mqtt_client.username_pw_set.assert_called_once_with("test_uuid", "new_key")

    def test_refresh_mqtt_credentials_same(self, protocol):
        """Test _refresh_mqtt_credentials when keys are same."""
        protocol._mqtt_client_key = "same_key"
        protocol._cloud_base._key = "same_key"
        protocol._mqtt_client = Mock()
        
        result = protocol._refresh_mqtt_credentials()
        
        assert result is False
        protocol._mqtt_client.username_pw_set.assert_not_called()

    def test_on_mqtt_client_connect_success(self, protocol):
        """Test _on_mqtt_client_connect static method with successful connection."""
        protocol._mqtt_client_connecting = True
        protocol._mqtt_client_connected = False
        protocol._mqtt_connected_callback = Mock()
        
        mock_client = Mock()
        
        DreameMowerCloudDevice._on_mqtt_client_connect(mock_client, protocol, None, 0)
        
        assert protocol._mqtt_client_connecting is False
        assert protocol._mqtt_client_connected is True
        mock_client.subscribe.assert_called_once()
        protocol._mqtt_connected_callback.assert_called_once()

    def test_on_mqtt_client_connect_failure(self, protocol):
        """Test _on_mqtt_client_connect static method with failed connection."""
        protocol._mqtt_client_connecting = True
        protocol._mqtt_client_connected = True
        protocol._refresh_mqtt_credentials = Mock(return_value=False)
        
        mock_client = Mock()
        
        DreameMowerCloudDevice._on_mqtt_client_connect(mock_client, protocol, None, 1)
        
        assert protocol._mqtt_client_connecting is False
        assert protocol._mqtt_client_connected is False

    def test_on_mqtt_client_disconnect_with_reconnect(self, protocol):
        """Test _on_mqtt_client_disconnect static method."""
        protocol._mqtt_client_connected = True
        protocol._mqtt_client_connecting = False
        protocol._refresh_mqtt_credentials = Mock(return_value=False)
        protocol._mqtt_reconnect_timer_cancel = Mock()
        protocol._mqtt_reconnect_timer = None
        
        mock_client = Mock()
        # Add reconnect method to mock client
        mock_client.reconnect = Mock()
        # Ensure protocol has reference so _on_mqtt_client_disconnect sees client
        protocol._mqtt_client = mock_client
        
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_device.Timer') as mock_timer:
            mock_timer_instance = Mock()
            mock_timer.return_value = mock_timer_instance

            DreameMowerCloudDevice._on_mqtt_client_disconnect(mock_client, protocol, 1)

            # New logic sets _mqtt_client_connecting True then attempts immediate reconnect
            # After disconnect handler, we expect reconnect attempt; connecting flag True
            assert protocol._mqtt_client_connecting is True
            mock_client.reconnect.assert_called_once()
            mock_timer.assert_called_once_with(10, protocol._mqtt_reconnect_timer_task)
            mock_timer_instance.start.assert_called_once()

    def test_on_mqtt_client_disconnect_callback_invoked(self, protocol):
        """Test that disconnected callback is invoked when MQTT disconnects."""
        protocol._mqtt_client_connected = True  # Was connected
        protocol._mqtt_client_connecting = False
        protocol._refresh_mqtt_credentials = Mock(return_value=False)
        protocol._mqtt_reconnect_timer_cancel = Mock()
        protocol._mqtt_reconnect_timer = None
        
        # Set up disconnected callback
        disconnected_callback = Mock()
        protocol._mqtt_disconnected_callback = disconnected_callback
        
        mock_client = Mock()
        mock_client.reconnect = Mock()
        protocol._mqtt_client = mock_client
        
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_device.Timer'):
            DreameMowerCloudDevice._on_mqtt_client_disconnect(mock_client, protocol, 1)

            # Verify disconnected callback was called
            disconnected_callback.assert_called_once()
            assert protocol._mqtt_client_connected is False

    def test_on_mqtt_client_disconnect_no_callback_when_not_connected(self, protocol):
        """Test that disconnected callback is NOT invoked if already disconnected."""
        protocol._mqtt_client_connected = False  # Already disconnected
        protocol._mqtt_client_connecting = False
        protocol._refresh_mqtt_credentials = Mock(return_value=False)
        protocol._mqtt_reconnect_timer_cancel = Mock()
        protocol._mqtt_reconnect_timer = None
        
        # Set up disconnected callback
        disconnected_callback = Mock()
        protocol._mqtt_disconnected_callback = disconnected_callback
        
        mock_client = Mock()
        mock_client.reconnect = Mock()
        protocol._mqtt_client = mock_client
        
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_device.Timer'):
            DreameMowerCloudDevice._on_mqtt_client_disconnect(mock_client, protocol, 1)

            # Verify disconnected callback was NOT called (wasn't connected before)
            disconnected_callback.assert_not_called()

    def test_on_mqtt_client_disconnect_callback_error_handling(self, protocol):
        """Test that callback errors are handled gracefully."""
        protocol._mqtt_client_connected = True
        protocol._mqtt_client_connecting = False
        protocol._refresh_mqtt_credentials = Mock(return_value=False)
        protocol._mqtt_reconnect_timer_cancel = Mock()
        protocol._mqtt_reconnect_timer = None
        
        # Set up callback that raises an exception
        disconnected_callback = Mock(side_effect=Exception("Callback error"))
        protocol._mqtt_disconnected_callback = disconnected_callback
        
        mock_client = Mock()
        mock_client.reconnect = Mock()
        protocol._mqtt_client = mock_client
        
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_device.Timer'):
            # Should not raise exception, even though callback does
            DreameMowerCloudDevice._on_mqtt_client_disconnect(mock_client, protocol, 1)

            # Verify callback was attempted and disconnect processing continued
            disconnected_callback.assert_called_once()
            assert protocol._mqtt_client_connected is False

    def test_on_mqtt_client_message_success(self, protocol):
        """Test _on_mqtt_client_message static method with valid message."""
        protocol._mqtt_message_callback = Mock()
        
        mock_message = Mock()
        mock_message.payload.decode.return_value = '{"data": {"test": "value"}}'
        
        DreameMowerCloudDevice._on_mqtt_client_message(None, protocol, mock_message)
        
        protocol._mqtt_message_callback.assert_called_once_with({"test": "value"})

    def test_on_mqtt_client_message_invalid_json(self, protocol):
        """Test _on_mqtt_client_message static method with invalid JSON."""
        protocol._mqtt_message_callback = Mock()
        
        mock_message = Mock()
        mock_message.payload.decode.return_value = 'invalid json'
        
        # Should not raise exception, should handle gracefully
        DreameMowerCloudDevice._on_mqtt_client_message(None, protocol, mock_message)
        
        protocol._mqtt_message_callback.assert_not_called()

    def test_mqtt_reconnect_timer_cancel(self, protocol):
        """Test _mqtt_reconnect_timer_cancel method."""
        mock_timer = Mock()
        protocol._mqtt_reconnect_timer = mock_timer
        
        protocol._mqtt_reconnect_timer_cancel()
        
        mock_timer.cancel.assert_called_once()
        assert protocol._mqtt_reconnect_timer is None

    def test_mqtt_reconnect_timer_task(self, protocol):
        """Test _mqtt_reconnect_timer_task method."""
        protocol._mqtt_client_connecting = True
        protocol._mqtt_client_connected = False  # simulate disconnected state
        protocol._mqtt_reconnect_timer_cancel = Mock()
        mock_client = Mock()
        protocol._mqtt_client = mock_client

        protocol._mqtt_reconnect_timer_task()

        protocol._mqtt_reconnect_timer_cancel.assert_called_once()
        mock_client.reconnect.assert_called_once()

    def test_get_device_info_success(self, protocol):
        """Test get_device_info (public API) with successful response."""
        protocol._device_id = "123"
        
        # Mock the cloud base connected property to return True
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            # Mock get_devices response with richer data
            device_data = {"did": "123", "name": "test", "battery": 85, "sn": "TEST123", "featureCode": -1}
            
            protocol._cloud_base.get_devices = Mock(return_value={
                protocol._cloud_base._api_strings[34]: {
                    protocol._cloud_base._api_strings[36]: [device_data]
                }
            })
            
            result = protocol.get_device_info()
            
            # The public API should NOT call _handle_device_info (no side effects)
            # Should return the rich device data from get_devices()
            assert result == device_data

    def test_initialize_mqtt_connection_state_success(self, protocol):
        """Initializer returns True on valid base info and sets fields."""
        protocol._device_id = "123"
        s = protocol._cloud_base._api_strings
        device_data = {
            s[8]: "uid123",
            "did": "123",
            s[35]: "m123",
            s[9]: "host.example:8883",
            s[10]: "",
        }
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            protocol._cloud_base._api_call = Mock(return_value={"code": 0, "data": device_data})
            result = protocol._initialize_mqtt_connection_state()
        assert result is True
        assert protocol._uid == "uid123"
        assert protocol._host == "host.example:8883"

    def test_get_device_info_device_not_found(self, protocol):
        """Test get_device_info (public API) when device is not in the devices list."""
        protocol._device_id = "123"
        
        # Mock the cloud base connected property to return True
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            # Mock get_devices to return a list without our device
            protocol._cloud_base.get_devices = Mock(return_value={
                protocol._cloud_base._api_strings[34]: {
                    protocol._cloud_base._api_strings[36]: [{"did": "456", "name": "other_device"}]
                }
            })
            
            result = protocol.get_device_info()
            
            assert result is None

    def test_initialize_mqtt_connection_state_no_data(self, protocol):
        """Returns False when base info is empty dict."""
        protocol._device_id = "123"
        
        # Mock the cloud base connected property to return True
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            protocol._cloud_base._api_call = Mock(return_value={"code": 0, "data": {}})  # missing required fields
            result = protocol._initialize_mqtt_connection_state()
            assert result is False

    def test_initialize_mqtt_connection_state_incomplete_data_keyerror(self, protocol):
        """Non-empty but incomplete base info should yield False without setting fields."""
        protocol._device_id = "123"

        # Mock the cloud base connected property to return True
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            s = protocol._cloud_base._api_strings
            incomplete = {"did": "123", s[35]: "m"}  # missing uid, host, property
            protocol._cloud_base._api_call = Mock(return_value={"code": 0, "data": incomplete})
            result = protocol._initialize_mqtt_connection_state()
            assert result is False
            assert protocol._uid is None

    def test_get_device_info_not_logged_in(self, protocol):
        """Test get_device_info (public API) returns None when unable to connect after attempting connection."""
        protocol._device_id = "123"

        # Patch both connected and connect() to avoid real socket calls
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=False), \
             patch.object(protocol._cloud_base, 'connect', return_value=False):
            result = protocol.get_device_info()
            assert result is None

    def test_initialize_mqtt_connection_state_not_logged_in(self, protocol):
        """Test _initialize_mqtt_connection_state returns False when unable to connect after attempting connection."""
        protocol._device_id = "123"

        # Patch both connected and connect() to avoid real socket calls
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=False), \
             patch.object(protocol._cloud_base, 'connect', return_value=False):
            assert protocol._initialize_mqtt_connection_state() is False

    # send_async removed in current implementation; covered in legacy tests

    def test_send_success(self, protocol):
        """Test send method with successful response."""
        self.setup_protocol_for_send_tests(protocol)
        
        # Start with unreachable
        protocol._device_reachable = False
        
        self.setup_api_call_mock(protocol, {
            "code": 0,
            "data": {"result": "success"}
        })
        
        result = protocol.send("test_method", {"param": "value"})
        
        assert result == "success"
        assert protocol._cloud_base._id == 2
        assert protocol.device_reachable is True

    def test_send_serializes_concurrent_commands(self, protocol):
        """Overlapping commands would take the same request ID and cross replies."""
        self.setup_protocol_for_send_tests(protocol)

        in_flight = 0
        overlapped = False
        request_ids: list[int] = []

        def _api_call(url, params=None, retry_count=2):
            nonlocal in_flight, overlapped
            in_flight += 1
            overlapped = overlapped or in_flight > 1
            request_ids.append(params["id"])
            # Long enough for a second thread to reach the request ID it reads.
            time.sleep(0.02)
            in_flight -= 1
            return {"code": 0, "data": {"result": "success"}}

        protocol._cloud_base._api_call = _api_call

        threads = [
            Thread(target=lambda: protocol.send("test_method", {"param": "value"}))
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert overlapped is False
        assert sorted(request_ids) == [1, 2, 3, 4]

    def test_send_timeout_error_80001(self, protocol):
        """Test send method with timeout error code 80001.
        
        Verifies that send method throws TimeoutError for device offline scenarios
        and updates device_reachable state.
        """
        protocol._host = "test.host.com"
        protocol._device_id = "123"
        protocol._cloud_base._id = 1
        
        response = {"code": 80001, "msg": "Device offline"}
        protocol._cloud_base._api_call = Mock(return_value=response)
        
        with pytest.raises(TimeoutError, match="Device offline"):
            protocol.send("test_method", {"param": "value"})
            
        assert protocol.device_reachable is False

    @pytest.mark.parametrize("error_code,error_message", [
        (500, "server error"),  # Generic server error
        (403, "forbidden"),  # Forbidden error
        (404, "not found"),  # Not found error
        (1001, "custom error"),  # Custom error
    ])
    def test_send_runtime_error_codes(self, protocol, error_code, error_message):
        """Test send method with various error codes.
        
        Verifies that send method throws RuntimeError for non-timeout error codes.
        """
        protocol._host = "test.host.com"
        protocol._device_id = "123"
        protocol._cloud_base._id = 1
        
        response = {"code": error_code, "msg": error_message}
        protocol._cloud_base._api_call = Mock(return_value=response)
        
        with pytest.raises(RuntimeError, match=f"Cloud API error {error_code}: {error_message}"):
            protocol.send("test_method", {"param": "value"})

    def test_mqtt_message_updates_reachable(self, protocol):
        """Test that receiving an MQTT message marks device as reachable."""
        protocol._device_reachable = False
        
        # Create a mock message
        mock_message = Mock()
        mock_message.payload = b'{"data": {"some": "data"}}'
        
        # Call the static method (need to pass self explicitly as it's static but uses self)
        DreameMowerCloudDevice._on_mqtt_client_message(None, protocol, mock_message)
        
        assert protocol.device_reachable is True

    def test_send_missing_data_field_returns_none(self, protocol):
        """Test send method with successful response but missing data field.
        
        Verifies that send method returns None for successful but empty responses.
        """
        protocol._host = "test.host.com"
        protocol._device_id = "123"
        protocol._cloud_base._id = 1
        
        # Successful response (code=0) but no data field
        response = {"code": 0}
        protocol._cloud_base._api_call = Mock(return_value=response)
        
        result = protocol.send("test_method", {"param": "value"})
        assert result is None

    def test_send_missing_result_field_returns_none(self, protocol):
        """Test send method with successful response but missing result field in data.
        
        Verifies that send method returns None for successful but empty results.
        """
        protocol._host = "test.host.com"
        protocol._device_id = "123"
        protocol._cloud_base._id = 1
        
        # Successful response with data but no result field
        response = {"code": 0, "data": {}}
        protocol._cloud_base._api_call = Mock(return_value=response)
        
        result = protocol.send("test_method", {"param": "value"})
        assert result is None

    def test_get_batch_device_datas_success(self, protocol):
        """Test get_batch_device_datas with successful response."""
        protocol._device_id = "123"
        
        # Mock the cloud base connected property to return True
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            protocol._cloud_base._api_call = Mock(return_value={
                "code": 0,
                "data": {"batch_key": "batch_value"}
            })
            
            result = protocol.get_batch_device_datas(["prop1", "prop2"])
            
            assert result == {"batch_key": "batch_value"}

    def test_set_batch_device_datas_success(self, protocol):
        """Test set_batch_device_datas with successful response."""
        protocol._device_id = "123"
        
        # Mock the cloud base connected property to return True
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            protocol._cloud_base._api_call = Mock(return_value={
                "result": {"success": True}
            })
            
            result = protocol.set_batch_device_datas(["prop1", "prop2"])
            
            assert result == {"success": True}

    @patch('custom_components.dreame_mower.dreame.cloud.cloud_device.mqtt_client.Client')
    def test_connect_success(self, mock_mqtt_client, protocol):
        """Test connect method with successful connection."""
        # Mock the cloud base connected property to return True
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            protocol._initialize_mqtt_connection_state = Mock(return_value=True)
            protocol._host = "mqtt.test.com:8883"
            protocol._uid = "test_uid"
            protocol._refresh_mqtt_credentials = Mock(return_value=True)
            
            mock_client = Mock()
            mock_mqtt_client.return_value = mock_client
            
            message_callback = Mock()
            connected_callback = Mock()
            disconnected_callback = Mock()
            
            result = protocol.connect(message_callback, connected_callback, disconnected_callback)

            assert result is True
            assert protocol._mqtt_message_callback == message_callback
            assert protocol._mqtt_connected_callback == connected_callback
            assert protocol._mqtt_disconnected_callback == disconnected_callback
            mock_client.connect.assert_called_once_with("mqtt.test.com", 8883, 50)

    def test_connect_not_logged_in(self, protocol):
        """Test connect method when not logged in."""
        # Mock the cloud base connected property to return False and connection to fail
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=False):
            protocol._cloud_base.connect = Mock(return_value=False)
            # Must provide required callbacks; expect False due to failed login
            result = protocol.connect(Mock(), Mock(), Mock())
            assert result is False
            protocol._cloud_base.connect.assert_called_once()

    def test_connect_no_callbacks_raises(self, protocol):
        """connect must raise when required callbacks are missing or None."""
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.DreameMowerCloudBase.connected', new_callable=PropertyMock, return_value=True):
            protocol._initialize_mqtt_connection_state = Mock(return_value=True)
            # Missing positional args -> TypeError
            with pytest.raises(TypeError):
                protocol.connect()
            # Passing None explicitly -> ValueError from runtime check
            with pytest.raises(ValueError):
                protocol.connect(Mock(), None, Mock())

    def test_disconnect(self, protocol):
        """Test disconnect method."""
        protocol._cloud_base.disconnect = Mock()
        mock_client = Mock()
        protocol._mqtt_client = mock_client
        protocol._mqtt_client_connected = True
        protocol._mqtt_client_connecting = True
        
        # Set up callbacks to verify they are cleaned up
        protocol._mqtt_message_callback = Mock()
        protocol._mqtt_connected_callback = Mock()
        protocol._mqtt_disconnected_callback = Mock()
        
        protocol.disconnect()
        
        # Verify MQTT cleanup operations
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()
        
        # Verify MQTT state cleanup
        assert protocol._mqtt_client is None
        assert protocol._mqtt_client_connected is False
        assert protocol._mqtt_client_connecting is False
        
        # Verify callback cleanup
        assert protocol._mqtt_message_callback is None
        assert protocol._mqtt_connected_callback is None
        assert protocol._mqtt_disconnected_callback is None
        
        # Verify cloud base disconnect was called
        protocol._cloud_base.disconnect.assert_called_once()
        
        # Verify that the connected property returns False after disconnect
        assert protocol.connected is False

    def test_disconnect_no_client(self, protocol):
        """Test disconnect method when client is None."""
        protocol._cloud_base.disconnect = Mock()
        protocol._mqtt_client = None  # No client
        
        protocol.disconnect()
        
        # Verify cloud base disconnect was called
        protocol._cloud_base.disconnect.assert_called_once()
        
        # Verify that the connected property returns False after disconnect
        assert protocol.connected is False

    # send_async removed in current implementation; covered in legacy tests

    # send_async removed in current implementation; covered in legacy tests

    # send_async removed in current implementation; covered in legacy tests

    # send_async removed in current implementation; covered in legacy tests

    # send_async removed in current implementation; covered in legacy tests

    def test_get_properties(self, protocol):
        """Test get_properties method."""
        protocol.send = Mock(return_value={"1.1": "value1"})

        result = protocol.get_properties(["1.1", "1.2"])

        protocol.send.assert_called_once_with(
            "get_properties", parameters=["1.1", "1.2"], retry_count=1
        )
        assert result == {"1.1": "value1"}

    def test_set_property_dreame_cloud(self, protocol):
        """Test set_property method with dreame cloud."""
        with patch.object(type(protocol), 'device_id', new_callable=PropertyMock, return_value="123"):
            protocol.set_properties = Mock(return_value="success")
            
            result = protocol.set_property(1, 2, "test_value")
            
            expected_params = [{
                "did": "123",
                "siid": 1,
                "piid": 2,
                "value": "test_value"
            }]
            protocol.set_properties.assert_called_once_with(expected_params, retry_count=2)
            assert result == "success"

    def test_set_properties(self, protocol):
        """Test set_properties method."""
        protocol.send = Mock(return_value="success")
        
        params = [{"siid": 1, "piid": 2, "value": "test"}]
        result = protocol.set_properties(params)

        protocol.send.assert_called_once_with(
            "set_properties", parameters=params, retry_count=2
        )
        assert result == "success"

    # action_async removed in current implementation; covered in legacy tests

    # action_async removed in current implementation; covered in legacy tests

    def test_action_dreame_cloud(self, protocol):
        """Test action method with dreame cloud."""
        with patch.object(type(protocol), 'device_id', new_callable=PropertyMock, return_value="123"):
            protocol.send = Mock(return_value="action_result")
            
            result = protocol.action(1, 2, ["param1"])
            
            expected_params = {
                "did": "123",
                "siid": 1,
                "aiid": 2,
                "in": ["param1"]
            }
            protocol.send.assert_called_once_with(
                "action", parameters=expected_params, retry_count=2
            )
            assert result == "action_result"

    def test_action_none_parameters(self, protocol):
        """Test action method with None parameters."""
        with patch.object(type(protocol), 'device_id', new_callable=PropertyMock, return_value="123"):
            protocol.send = Mock(return_value="action_result")
            
            result = protocol.action(1, 2, None)
            
            expected_params = {
                "did": "123",
                "siid": 1,
                "aiid": 2,
                "in": []
            }
            protocol.send.assert_called_once_with(
                "action", parameters=expected_params, retry_count=2
            )
            assert result == "action_result"

    def test_action_send_exception(self, protocol):
        """Test action method when send raises an exception."""
        with patch.object(type(protocol), 'device_id', new_callable=PropertyMock, return_value="123"):
            # Test different exception types that should be propagated
            for exception_type in [TimeoutError, RuntimeError, ConnectionError]:
                protocol.send = Mock(side_effect=exception_type("Test error"))
                
                with pytest.raises(exception_type, match="Test error"):
                    protocol.action(1, 2, ["param1"])
                
                expected_params = {
                    "did": "123",
                    "siid": 1,
                    "aiid": 2,
                    "in": ["param1"]
                }
                protocol.send.assert_called_with(
                    "action", parameters=expected_params, retry_count=2
                )
