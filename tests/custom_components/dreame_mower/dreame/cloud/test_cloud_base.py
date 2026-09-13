"""Tests for the Dreame Mower cloud base module."""

import hashlib
import json
import logging
import queue
from typing import Any
from unittest.mock import Mock, patch
import pytest
import requests

from custom_components.dreame_mower.dreame.cloud.cloud_base import (
    DreameMowerCloudBase,
    REDACTED,
    redact_body,
    redact_headers,
)
# Use standard ConnectionError for cloud/device communication issues


class TestDreameMowerCloudBase:
    """Test DreameMowerCloudBase class."""

    # Test constants
    TEST_USERNAME = "test_user"
    TEST_PASSWORD = "test_pass"
    TEST_COUNTRY = "cn"
    TEST_ACCOUNT_TYPE = "dreame"

    @pytest.fixture
    def cloud_base(self):
        """Create a cloud base instance for testing."""
        return DreameMowerCloudBase(
            username=self.TEST_USERNAME,
            password=self.TEST_PASSWORD,
            country=self.TEST_COUNTRY,
            account_type=self.TEST_ACCOUNT_TYPE
        )

    def setup_successful_response_mock(self, status_code=200, response_data=None):
        """Helper method to create a successful response mock."""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.text = json.dumps(response_data) if response_data else '{"code": 0}'
        mock_response.content = json.dumps(response_data).encode() if response_data else b'{"code": 0}'
        return mock_response

    def setup_api_call_mock(self, cloud_base, return_value):
        """Helper method to setup _api_call mock."""
        cloud_base._api_call = Mock(return_value=return_value)
        return cloud_base._api_call

    # Initialization Tests
    def test_init(self):
        """Test cloud base initialization."""
        cloud_base = DreameMowerCloudBase(
            username="user",
            password="pass",
            country="us",
            account_type="mova"
        )
        assert cloud_base._username == "user"
        assert cloud_base._password == "pass"
        assert cloud_base._country == "us"
        assert cloud_base._location == "us"
        assert cloud_base.connected is False
        assert cloud_base._fail_count == 0

    def test_get_api_url(self, cloud_base):
        """Test get_api_url method."""
        url = cloud_base.get_api_url()
        assert url.startswith("https://")
        assert cloud_base._country in url
        assert ":" in url  # Should have port separator

    # Connected Property Tests
    def test_connected_property_not_logged_in(self, cloud_base):
        """Test connected property when not logged in."""
        # Default state - should be False
        assert cloud_base.connected is False
        
        # Only http connected but not logged in - should still be False
        cloud_base._DreameMowerCloudBase__http_api_connected = True
        assert cloud_base.connected is False

    def test_connected_property_logged_in_no_http(self, cloud_base):
        """Test connected property when logged in but no HTTP connection."""
        # Logged in but no HTTP connection - should be False
        cloud_base._DreameMowerCloudBase__logged_in = True
        cloud_base._DreameMowerCloudBase__http_api_connected = False
        assert cloud_base.connected is False

    def test_connected_property_fully_connected(self, cloud_base):
        """Test connected property when fully connected."""
        # Both logged in and HTTP connected - should be True
        cloud_base._DreameMowerCloudBase__logged_in = True
        cloud_base._DreameMowerCloudBase__http_api_connected = True
        assert cloud_base.connected is True

    # Login Tests
    @patch('custom_components.dreame_mower.dreame.cloud.cloud_base.requests.session')
    def test_connect_success_dreame(self, mock_session_class, cloud_base):
        """Test successful connection for dreame account."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        cloud_base._session = mock_session
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            cloud_base._api_strings[18]: "test_token",
            cloud_base._api_strings[19]: "test_refresh",
            cloud_base._api_strings[20]: 3600,
            "uid": "test_uid",
            cloud_base._api_strings[21]: "us",
            cloud_base._api_strings[22]: "test_ti"
        })
        mock_session.post.return_value = mock_response
        
        result = cloud_base.connect()
        
        assert result is True
        assert cloud_base.connected is True
        assert cloud_base._key == "test_token"
        assert cloud_base._secondary_key == "test_refresh"
        assert cloud_base._uuid == "test_uid"

    @patch('custom_components.dreame_mower.dreame.cloud.cloud_base.requests.session')
    def test_connect_failure_bad_credentials(self, mock_session_class, cloud_base):
        """Test failed connection with bad credentials."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = '{"error": "invalid credentials"}'
        mock_session.post.return_value = mock_response

        result = cloud_base.connect()

        assert result is False
        assert cloud_base.connected is False

    @patch('custom_components.dreame_mower.dreame.cloud.cloud_base.requests.session')
    def test_connect_timeout(self, mock_session_class, cloud_base):
        """Test connection with timeout."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.post.side_effect = requests.exceptions.Timeout()

        result = cloud_base.connect()

        assert result is False
        assert cloud_base.connected is False

    # Get Devices Tests
    @pytest.mark.parametrize("api_response,expected_result", [
        ({"code": 0, "data": [{"did": "123", "name": "test_device"}]}, [{"did": "123", "name": "test_device"}]),
        ({"code": 1, "message": "error"}, None),
        ({"code": -1, "message": "invalid"}, None),
    ])
    def test_get_devices_connected(self, cloud_base, api_response, expected_result):
        """Test get_devices with various responses when connected."""
        # Set up connected state
        cloud_base._DreameMowerCloudBase__logged_in = True
        cloud_base._DreameMowerCloudBase__http_api_connected = True
        
        self.setup_api_call_mock(cloud_base, api_response)
        
        result = cloud_base.get_devices()
        
        assert result == expected_result

    def test_get_devices_not_connected(self, cloud_base):
        """Test get_devices throws ConnectionError when not connected."""
        # Default state should be not connected
        
        with pytest.raises(ConnectionError, match="get_devices: Not connected. Call connect\\(\\) first."):
            cloud_base.get_devices()

    # API Call Tests
    @patch('custom_components.dreame_mower.dreame.cloud.cloud_base.requests.session')
    def test_api_call(self, mock_session, cloud_base):
        """Test _api_call method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"code": 0, "data": "test_data"}'
        
        cloud_base._session = mock_session
        cloud_base.request = Mock(return_value={"code": 0, "data": "test_data"})
        
        result = cloud_base._api_call("test_url", {"param": "value"})
        
        cloud_base.request.assert_called_once()
        assert result == {"code": 0, "data": "test_data"}

    def test_api_call_async(self, cloud_base):
        """Test _api_call_async method."""
        callback = Mock()
        
        # Mock the queue and thread - let the thread be created naturally
        cloud_base._queue = Mock()
        cloud_base._thread = None
        
        with patch('custom_components.dreame_mower.dreame.cloud.cloud_base.Thread') as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance
            
            cloud_base._api_call_async(callback, "test_url", {"param": "value"}, 2)
            
            # Should create thread if None
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()
            cloud_base._queue.put.assert_called_once()

    def test_api_task(self, cloud_base):
        """Test _api_task method."""
        # Create a real queue for testing
        test_queue: queue.Queue[Any] = queue.Queue()
        cloud_base._queue = test_queue
        cloud_base._api_call = Mock(return_value={"result": "success"})
        
        # Add a task and empty item to stop the loop
        callback = Mock()
        test_queue.put((callback, "url", "params", 2))
        test_queue.put([])  # Empty item to stop the loop
        
        # Run the task
        cloud_base._api_task()
        
        # Verify callback was called with the result
        callback.assert_called_once_with({"result": "success"})

    # Request Method Tests
    @patch('custom_components.dreame_mower.dreame.cloud.cloud_base.time.sleep')
    def test_request_with_key_expiration(self, mock_time, cloud_base):
        """Test request method with key expiration."""
        cloud_base._key_expire = 1000
        mock_time.return_value = 1001  # Expired
        cloud_base.connect = Mock(return_value=True)
        cloud_base._key = "test_key"
        cloud_base._ti = "test_ti"
        cloud_base._country = "cn"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"result": "success"}'
        
        cloud_base._session = Mock()
        cloud_base._session.post.return_value = mock_response
        
        result = cloud_base.request("http://test.com", "test_data")
        
        cloud_base.connect.assert_called_once()
        assert result == {"result": "success"}

    def test_request_timeout_retry(self, cloud_base):
        """Test request method with timeout and retry."""
        cloud_base._key = "test_key"
        cloud_base._DreameMowerCloudBase__http_api_connected = True
        
        cloud_base._session = Mock()
        cloud_base._session.post.side_effect = [
            requests.exceptions.Timeout(),
            Mock(status_code=200, text='{"success": true}')
        ]
        
        result = cloud_base.request("http://test.com", "test_data", retry_count=2)
        
        assert result == {"success": True}
        assert cloud_base._session.post.call_count == 2

    def test_request_401_with_refresh_token(self, cloud_base):
        """Test request method with 401 and refresh token."""
        cloud_base._key = "test_key"
        cloud_base._secondary_key = "refresh_key"
        cloud_base.connect = Mock(return_value=True)
        
        mock_response = Mock()
        mock_response.status_code = 401
        
        cloud_base._session = Mock()
        cloud_base._session.post.return_value = mock_response
        
        result = cloud_base.request("http://test.com", "test_data")
        
        cloud_base.connect.assert_called_once()
        assert result is None  # Should return None after 401

    def test_request_max_failures(self, cloud_base):
        """Test request method with max failures reached."""
        cloud_base._key = "test_key"
        cloud_base._fail_count = 5  # Set to 5 to trigger _http_api_connected = False
        cloud_base._DreameMowerCloudBase__http_api_connected = True
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        
        cloud_base._session = Mock()
        cloud_base._session.post.return_value = mock_response
        
        result = cloud_base.request("http://test.com", "test_data")
        
        assert result is None
        # When _fail_count == 5, _http_api_connected is set to False (no increment happens)
        assert cloud_base._fail_count == 5
        assert cloud_base._DreameMowerCloudBase__http_api_connected is False

    # Disconnect Tests
    def test_disconnect(self, cloud_base):
        """Test disconnect method."""
        cloud_base._session = Mock()
        cloud_base._thread = Mock()
        cloud_base._queue = Mock()
        cloud_base._DreameMowerCloudBase__http_api_connected = True
        cloud_base._DreameMowerCloudBase__logged_in = True
        
        cloud_base.disconnect()
        
        cloud_base._session.close.assert_called_once()
        cloud_base._queue.put.assert_called_once_with([])
        assert cloud_base._DreameMowerCloudBase__http_api_connected is False
        assert cloud_base.connected is False

    def test_disconnect_no_session(self, cloud_base):
        """Test disconnect method when session is None."""
        cloud_base._session = None
        cloud_base._thread = Mock()
        cloud_base._queue = Mock()
        cloud_base._DreameMowerCloudBase__http_api_connected = True
        
        # Should not raise exception
        cloud_base.disconnect()
        
        cloud_base._queue.put.assert_called_once_with([])
        assert cloud_base._DreameMowerCloudBase__http_api_connected is False

    # Integration-style Tests
    @patch('custom_components.dreame_mower.dreame.cloud.cloud_base.requests.session')
    def test_connect_to_get_devices_flow(self, mock_session_class, cloud_base):
        """Test the typical flow: login -> get_devices."""
        # Mock successful login
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        cloud_base._session = mock_session
        
        login_response = Mock()
        login_response.status_code = 200
        login_response.text = json.dumps({
            cloud_base._api_strings[18]: "test_token",
            cloud_base._api_strings[19]: "test_refresh",
            cloud_base._api_strings[20]: 3600,
            "uid": "test_uid"
        })
        mock_session.post.return_value = login_response
        
        # Connection should succeed
        assert cloud_base.connect() is True
        assert cloud_base.connected is True
        
        # Mock successful get_devices call
        devices_data = [{"did": "123", "name": "test_device"}]
        self.setup_api_call_mock(cloud_base, {"code": 0, "data": devices_data})
        
        # Get devices should succeed
        result = cloud_base.get_devices()
        assert result == devices_data
        
        # Disconnect should reset state
        cloud_base.disconnect()
        assert cloud_base.connected is False

    def test_connectivity_state_transitions(self, cloud_base):
        """Test various connectivity state transitions."""
        # Initially not connected
        assert cloud_base.connected is False
        
        # Only logged in - still not connected
        cloud_base._DreameMowerCloudBase__logged_in = True
        assert cloud_base.connected is False
        
        # Only HTTP connected - still not connected
        cloud_base._DreameMowerCloudBase__logged_in = False
        cloud_base._DreameMowerCloudBase__http_api_connected = True
        assert cloud_base.connected is False
        
        # Both connected - now connected
        cloud_base._DreameMowerCloudBase__logged_in = True
        assert cloud_base.connected is True
        
        # Disconnect HTTP - not connected
        cloud_base._DreameMowerCloudBase__http_api_connected = False
        assert cloud_base.connected is False
        
        # Disconnect login - still not connected
        cloud_base._DreameMowerCloudBase__logged_in = False
        assert cloud_base.connected is False

    # Core tests for raise_on_error functionality
    def test_request_raise_on_error_false_default_behavior(self, cloud_base):
        """Test request method with raise_on_error=False (default) returns None on failure."""
        cloud_base._key = "test_key"
        
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        
        cloud_base._session = Mock()
        cloud_base._session.post.return_value = mock_response
        
        # Default behavior - should return None on HTTP errors
        result = cloud_base.request("http://test.com", "test_data", raise_on_error=False)
        
        assert result is None
        assert cloud_base._fail_count == 1

    def test_request_raise_on_error_true_http_error(self, cloud_base):
        """Test request method with raise_on_error=True raises HTTPError on HTTP error."""
        cloud_base._key = "test_key"
        
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        # Make the mock response raise HTTPError when raise_for_status() is called
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error")
        
        cloud_base._session = Mock()
        cloud_base._session.post.return_value = mock_response
        
        # Should raise HTTPError when raise_on_error=True
        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            cloud_base.request("http://test.com", "test_data", raise_on_error=True)
        
        assert "404 Client Error" in str(exc_info.value)
        assert cloud_base._fail_count == 0  # No increment when exception is raised

    def test_request_raise_on_error_true_connection_error(self, cloud_base):
        """Test request method with raise_on_error=True re-raises original exception on request failure."""
        cloud_base._key = "test_key"
        
        # Mock session to raise requests.Timeout (which results in response=None)
        cloud_base._session = Mock()
        cloud_base._session.post.side_effect = requests.Timeout("Connection timeout")
        
        # Should re-raise the original Timeout exception when raise_on_error=True
        with pytest.raises(requests.Timeout) as exc_info:
            cloud_base.request("http://test.com", "test_data", raise_on_error=True)
        
        assert "Connection timeout" in str(exc_info.value)
        assert cloud_base._fail_count == 0  # No increment when exception is raised

    def test_request_successful_response_ignores_raise_on_error(self, cloud_base):
        """Test that successful requests work the same regardless of raise_on_error setting."""
        cloud_base._key = "test_key"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"code": 0, "result": "success"}'
        
        cloud_base._session = Mock()
        cloud_base._session.post.return_value = mock_response
        
        # Test with raise_on_error=False
        result_false = cloud_base.request("http://test.com", "test_data", raise_on_error=False)
        
        # Test with raise_on_error=True  
        result_true = cloud_base.request("http://test.com", "test_data", raise_on_error=True)
        
        # Both should return the same successful result
        expected_result = {"code": 0, "result": "success"}
        assert result_false == expected_result
        assert result_true == expected_result
        assert cloud_base._fail_count == 0  # No failures for successful requests

class TestCredentialRedaction:
    """Credentials must never reach the Home Assistant log."""

    USERNAME = "mario@example.de"
    PASSWORD_HASH = "5f4dcc3b5aa765d61d8327deb882cf99"

    def test_password_grant_body_is_redacted(self):
        body = (
            "platform=IOS&scope=all&grant_type=password"
            f"&username={self.USERNAME}&password={self.PASSWORD_HASH}"
            "&type=account"
        )

        result = redact_body(body)

        assert self.USERNAME not in result
        assert self.PASSWORD_HASH not in result
        assert f"username={REDACTED}" in result
        assert f"password={REDACTED}" in result
        # The grant type stays readable so a failed login is still diagnosable.
        assert "grant_type=password" in result

    def test_refresh_token_body_is_redacted(self):
        result = redact_body(
            "platform=IOS&scope=all&grant_type=refresh_token&refresh_token=tok_secret"
        )

        assert "tok_secret" not in result
        assert f"refresh_token={REDACTED}" in result
        assert "grant_type=refresh_token" in result

    @pytest.mark.parametrize("body", ['{"did": "123", "cmd": "start"}', "", None, 42])
    def test_non_credential_body_is_unchanged(self, body):
        assert redact_body(body) == body

    def test_headers_are_redacted(self):
        headers = {
            "User-Agent": "Dreame_Smarthome/1.5.59",
            "Authorization": "Basic ZHJlYW1lX2FwcHYxOkFQ",
            "Tenant-Id": "000000",
            "Dreame-Auth": "tok_secret",
            "Dreame-Rlc": "1c80b3787b22",
        }

        result = redact_headers(headers)

        assert result["Authorization"] == REDACTED
        assert result["Dreame-Auth"] == REDACTED
        assert result["Dreame-Rlc"] == REDACTED
        # Non-credential headers stay intact for debugging.
        assert result["User-Agent"] == "Dreame_Smarthome/1.5.59"
        assert result["Tenant-Id"] == "000000"

    @patch('custom_components.dreame_mower.dreame.cloud.cloud_base.requests.session')
    def test_failed_login_does_not_log_credentials(self, mock_session_class, caplog):
        """A rejected login must not leak the account into the log."""
        cloud_base = DreameMowerCloudBase(
            username="secret_user",
            password="secret_pass",
            country="cn",
            account_type="dreame",
        )
        password_hash = hashlib.md5(
            ("secret_pass" + cloud_base._api_strings[2]).encode("utf-8")
        ).hexdigest()

        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = '{"error": "invalid_grant"}'
        mock_session.post.return_value = mock_response

        with caplog.at_level(logging.ERROR):
            cloud_base.connect()

        assert "Login failed" in caplog.text
        assert "secret_user" not in caplog.text
        assert password_hash not in caplog.text
        assert cloud_base._api_strings[5] not in caplog.text  # Authorization header

    @patch('custom_components.dreame_mower.dreame.cloud.cloud_base.requests.session')
    def test_non_json_login_error_does_not_log_credentials(self, mock_session_class, caplog):
        """A non-JSON error response leaves the request body in `data`, which holds the password."""
        cloud_base = DreameMowerCloudBase(
            username="secret_user",
            password="secret_pass",
            country="cn",
            account_type="dreame",
        )
        password_hash = hashlib.md5(
            ("secret_pass" + cloud_base._api_strings[2]).encode("utf-8")
        ).hexdigest()

        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.status_code = 502
        mock_response.text = "<html><body>Bad Gateway</body></html>"
        mock_session.post.return_value = mock_response

        with caplog.at_level(logging.ERROR):
            cloud_base.connect()

        assert "Login failed" in caplog.text
        assert "secret_user" not in caplog.text
        assert password_hash not in caplog.text
        assert f"username={REDACTED}" in caplog.text
        assert f"password={REDACTED}" in caplog.text
