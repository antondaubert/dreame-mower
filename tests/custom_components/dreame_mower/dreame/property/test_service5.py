"""Test the Service 5 property handler."""

import pytest
from unittest.mock import Mock

from custom_components.dreame_mower.dreame.property.service5 import (
    Service5PropertyHandler,
    TASK_STATUS_PROPERTY_NAME,
    TASK_STATUS_DESCRIPTION_FIELD,
    TASK_STATUS_MAPPING,
    SERVICE5_PROPERTY_100_PROPERTY_NAME,
    SERVICE5_PROPERTY_105_PROPERTY_NAME,
    SERVICE5_PROPERTY_106_PROPERTY_NAME,
    SERVICE5_ENERGY_INDEX_PROPERTY_NAME,
    SERVICE5_PROPERTY_108_PROPERTY_NAME,
    TASK_STATUS_CODE_FIELD,
    PROPERTY_100_VALUE_FIELD,
    PROPERTY_105_VALUE_FIELD,
    PROPERTY_106_VALUE_FIELD,
    ENERGY_INDEX_VALUE_FIELD,
    PROPERTY_108_VALUE_FIELD,
)


class TestService5PropertyHandler:
    """Test Service5PropertyHandler for task status property 5:104."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = Service5PropertyHandler()
        self.notifications = []
        
        def mock_notify(property_name, value):
            self.notifications.append((property_name, value))
        
        self.notify_callback = mock_notify

    def test_handle_task_status_value_7(self):
        """Test handling task status value 7 - Task incomplete - spot mowing."""
        result = self.handler.handle_property_update(5, 104, 7, self.notify_callback)
        
        assert result is True
        assert self.handler.task_status_code == 7
        assert self.handler.task_status_description == "Task incomplete - spot mowing"
        
        # Check notifications
        assert len(self.notifications) == 2
        
        # First notification should be the task_status with full data
        assert self.notifications[0][0] == TASK_STATUS_PROPERTY_NAME
        assert self.notifications[0][1][TASK_STATUS_CODE_FIELD] == 7
        assert self.notifications[0][1][TASK_STATUS_DESCRIPTION_FIELD] == "Task incomplete - spot mowing"
        
        # Second notification should be the backward compatibility notification
        assert self.notifications[1][0] == "task_status_code"
        assert self.notifications[1][1] == 7

    def test_handle_task_status_unknown_value(self):
        """Test handling unknown task status value."""
        result = self.handler.handle_property_update(5, 104, 99, self.notify_callback)
        
        # Unknown values should return False to trigger unhandled_mqtt notification
        assert result is False
        # State should not be updated for unknown values
        assert self.handler.task_status_code is None
        # Should not send notifications for unknown values
        assert len(self.notifications) == 0

    def test_handle_task_status_invalid_value(self):
        """Test handling invalid task status value (not an integer)."""
        result = self.handler.handle_property_update(5, 104, "invalid", self.notify_callback)
        
        assert result is False
        assert self.handler.task_status_code is None

    def test_handle_task_status_state_change(self):
        """Test that only changed status codes trigger individual notifications."""
        # First update
        self.handler.handle_property_update(5, 104, 7, self.notify_callback)
        assert len(self.notifications) == 2
        
        # Clear notifications
        self.notifications.clear()
        
        # Same value - should still send full notification but individual notification only if changed
        self.handler.handle_property_update(5, 104, 7, self.notify_callback)
        assert len(self.notifications) == 1  # Only the main notification, no individual change notification
        assert self.notifications[0][0] == TASK_STATUS_PROPERTY_NAME

    def test_handle_wrong_siid_piid(self):
        """Test that wrong siid/piid combination returns False."""
        result = self.handler.handle_property_update(2, 104, 7, self.notify_callback)
        assert result is False
        
        result = self.handler.handle_property_update(5, 999, 7, self.notify_callback)
        assert result is False

    def test_task_status_property_getters(self):
        """Test property getters for task status."""
        # Initially None
        assert self.handler.task_status_code is None
        assert self.handler.task_status_description is None
        
        # After update
        self.handler.handle_property_update(5, 104, 7, self.notify_callback)
        assert self.handler.task_status_code == 7
        assert self.handler.task_status_description == "Task incomplete - spot mowing"

    def test_task_status_mapping_completeness(self):
        """Test that task status mapping contains expected values."""
        assert 7 in TASK_STATUS_MAPPING
        assert TASK_STATUS_MAPPING[7] == "Task incomplete - spot mowing"

    def test_handle_property_100_integer_value(self):
        """Test handling property 5:100 with integer value (from issue report, value=5)."""
        result = self.handler.handle_property_update(5, 100, 5, self.notify_callback)

        assert result is True
        assert self.handler.property_100_value == 5

        assert len(self.notifications) == 2
        assert self.notifications[0][0] == SERVICE5_PROPERTY_100_PROPERTY_NAME
        assert self.notifications[0][1][PROPERTY_100_VALUE_FIELD] == 5
        assert self.notifications[1][0] == "service5_property_100_value"
        assert self.notifications[1][1] == 5

    def test_handle_property_100_string_value(self):
        """Test handling property 5:100 with string value that can be converted to int."""
        result = self.handler.handle_property_update(5, 100, "3", self.notify_callback)

        assert result is True
        assert self.handler.property_100_value == 3

    def test_handle_property_100_invalid_value(self):
        """Test handling property 5:100 with invalid value."""
        result = self.handler.handle_property_update(5, 100, "invalid", self.notify_callback)

        assert result is False
        assert self.handler.property_100_value is None

    def test_handle_property_100_same_value_no_individual_notification(self):
        """Test that same value doesn't trigger individual notification for 5:100."""
        self.handler.handle_property_update(5, 100, 5, self.notify_callback)
        self.notifications.clear()

        result = self.handler.handle_property_update(5, 100, 5, self.notify_callback)

        assert result is True
        assert len(self.notifications) == 1  # Only main notification, no individual state change
        assert self.notifications[0][0] == SERVICE5_PROPERTY_100_PROPERTY_NAME

    def test_handle_property_100_from_issue_report(self):
        """Test handling property 5:100 with the exact message from the issue report.

        Issue message:
        {'id': 122, 'method': 'properties_changed',
         'params': [{'did': '-1******34', 'piid': 100, 'siid': 5, 'value': 5}]}
        """
        result = self.handler.handle_property_update(5, 100, 5, self.notify_callback)

        assert result is True
        assert self.handler.property_100_value == 5

        notification_names = [notif[0] for notif in self.notifications]
        assert SERVICE5_PROPERTY_100_PROPERTY_NAME in notification_names
        assert "service5_property_100_value" in notification_names

    def test_handle_property_105_integer_value(self):
        """Test handling property 5:105 with integer value."""
        result = self.handler.handle_property_update(5, 105, 1, self.notify_callback)
        
        assert result is True
        assert self.handler.property_105_value == 1
        
        # Verify notifications were called
        assert len(self.notifications) == 2
        
        # Check notification data
        assert self.notifications[0][0] == SERVICE5_PROPERTY_105_PROPERTY_NAME
        assert self.notifications[0][1][PROPERTY_105_VALUE_FIELD] == 1
        assert self.notifications[1][0] == "service5_property_105_value"
        assert self.notifications[1][1] == 1

    def test_handle_property_105_string_value(self):
        """Test handling property 5:105 with string value that can be converted to int."""
        result = self.handler.handle_property_update(5, 105, "42", self.notify_callback)
        
        assert result is True
        assert self.handler.property_105_value == 42

    def test_handle_property_105_invalid_value(self):
        """Test handling property 5:105 with invalid value."""
        result = self.handler.handle_property_update(5, 105, "invalid", self.notify_callback)
        
        assert result is False
        assert self.handler.property_105_value is None

    def test_handle_property_106(self):
        """Test handling property 5:106."""
        result = self.handler.handle_property_update(5, 106, 3, self.notify_callback)
        
        assert result is True
        assert self.handler.property_106_value == 3
        
        # Verify notifications
        assert len(self.notifications) == 2
        assert self.notifications[0][0] == SERVICE5_PROPERTY_106_PROPERTY_NAME
        assert self.notifications[0][1][PROPERTY_106_VALUE_FIELD] == 3
        assert self.notifications[1][0] == "service5_property_106_value"
        assert self.notifications[1][1] == 3

    def test_handle_energy_index_property(self):
        """Test handling energy index property 5:107."""
        result = self.handler.handle_property_update(5, 107, 150, self.notify_callback)
        
        assert result is True
        assert self.handler.energy_index == 150
        
        # Verify notifications
        assert len(self.notifications) == 2
        assert self.notifications[0][0] == SERVICE5_ENERGY_INDEX_PROPERTY_NAME
        assert self.notifications[0][1][ENERGY_INDEX_VALUE_FIELD] == 150

    def test_handle_energy_index_delta_calculation(self):
        """Test energy delta calculation when energy index changes."""
        # Set initial value
        self.handler.handle_property_update(5, 107, 100, self.notify_callback)
        self.notifications.clear()
        
        # Update to new value
        result = self.handler.handle_property_update(5, 107, 150, self.notify_callback)
        
        assert result is True
        assert self.handler.energy_index == 150
        
        # Verify delta notification was sent
        delta_call = [notif for notif in self.notifications if notif[0] == "energy_delta"]
        assert len(delta_call) == 1
        assert delta_call[0][1] == 50  # 150 - 100 = 50

    def test_handle_property_108_integer_value(self):
        """Test handling property 5:108 with integer value."""
        result = self.handler.handle_property_update(5, 108, 1, self.notify_callback)
        
        assert result is True
        assert self.handler.property_108_value == 1
        
        # Verify notifications were called
        assert len(self.notifications) == 2
        
        # Check notification data
        assert self.notifications[0][0] == SERVICE5_PROPERTY_108_PROPERTY_NAME
        assert self.notifications[0][1][PROPERTY_108_VALUE_FIELD] == 1
        assert self.notifications[1][0] == "service5_property_108_value"
        assert self.notifications[1][1] == 1

    def test_handle_property_108_from_issue_report(self):
        """Test handling property 5:108 with value from the issue report.
        
        This tests the exact message from the issue:
        {'id': 1467, 'method': 'properties_changed', 
         'params': [{'did': '-1******73', 'piid': 108, 'siid': 5, 'value': 1}]}
        """
        result = self.handler.handle_property_update(5, 108, 1, self.notify_callback)
        
        assert result is True
        assert self.handler.property_108_value == 1
        
        # Verify we got the expected notifications
        notification_names = [notif[0] for notif in self.notifications]
        assert SERVICE5_PROPERTY_108_PROPERTY_NAME in notification_names
        assert "service5_property_108_value" in notification_names

    def test_handle_property_108_string_value(self):
        """Test handling property 5:108 with string value that can be converted to int."""
        result = self.handler.handle_property_update(5, 108, "2", self.notify_callback)
        
        assert result is True
        assert self.handler.property_108_value == 2

    def test_handle_property_108_invalid_value(self):
        """Test handling property 5:108 with invalid value."""
        result = self.handler.handle_property_update(5, 108, "not_a_number", self.notify_callback)
        
        assert result is False
        assert self.handler.property_108_value is None

    def test_handle_property_108_value_change(self):
        """Test property 5:108 value change notification."""
        # Set initial value
        self.handler.handle_property_update(5, 108, 0, self.notify_callback)
        self.notifications.clear()
        
        # Update to new value
        result = self.handler.handle_property_update(5, 108, 1, self.notify_callback)
        
        assert result is True
        assert self.handler.property_108_value == 1
        
        # Verify individual state change notification was sent
        state_change_call = [notif for notif in self.notifications if notif[0] == "service5_property_108_value"]
        assert len(state_change_call) == 1
        assert state_change_call[0][1] == 1

    def test_handle_property_108_same_value_no_individual_notification(self):
        """Test that same value doesn't trigger individual notification for 5:108."""
        # Set initial value
        self.handler.handle_property_update(5, 108, 1, self.notify_callback)
        self.notifications.clear()
        
        # Update to same value
        result = self.handler.handle_property_update(5, 108, 1, self.notify_callback)
        
        assert result is True
        
        # Main notification should be called but not individual state change
        assert self.notifications[0][0] == SERVICE5_PROPERTY_108_PROPERTY_NAME
        assert len(self.notifications) == 1  # Only main notification, no individual state change

    def test_handle_unknown_property(self):
        """Test handling unknown property returns False."""
        result = self.handler.handle_property_update(5, 999, 1, self.notify_callback)
        
        assert result is False
        assert len(self.notifications) == 0

    def test_handle_wrong_siid(self):
        """Test handling property with wrong siid returns False."""
        result = self.handler.handle_property_update(3, 105, 1, self.notify_callback)
        
        assert result is False
        assert len(self.notifications) == 0

    def test_initial_state(self):
        """Test initial state of handler."""
        assert self.handler.property_100_value is None
        assert self.handler.task_status_code is None
        assert self.handler.property_105_value is None
        assert self.handler.property_106_value is None
        assert self.handler.energy_index is None
        assert self.handler.property_108_value is None
        assert self.handler.has_energy_tracking is False

    def test_has_energy_tracking_property(self):
        """Test has_energy_tracking property."""
        assert self.handler.has_energy_tracking is False
        
        self.handler.handle_property_update(5, 107, 100, self.notify_callback)
        
        assert self.handler.has_energy_tracking is True
