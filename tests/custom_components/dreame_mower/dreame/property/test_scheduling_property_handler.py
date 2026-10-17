"""Test the scheduling property handler."""

import pytest
from unittest.mock import Mock

from custom_components.dreame_mower.dreame.const import (
    SCHEDULING_TASK_PROPERTY,
    SCHEDULING_SUMMARY_PROPERTY,
)
from custom_components.dreame_mower.dreame.property.scheduling import (
    SchedulingPropertyHandler,
    TaskHandler,
    SummaryHandler,
    TaskType,
)


class TestTaskHandler:
    """Test TaskHandler for property 2:50."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = TaskHandler()

    def test_parse_task_dict_format(self):
        """Test parsing task descriptor from dict format."""
        task_data = {
            'd': {'area_id': [], 'exe': True, 'o': 100, 'region_id': [1], 'status': True, 'time': 2323}, 
            't': 'TASK'
        }
        
        result = self.handler.parse_value(task_data)
        
        assert result is True
        assert self.handler.task_type == TaskType.TASK
        assert self.handler.region_id == [1]
        assert self.handler.get_notification_data() == {
            'type': 'TASK',
            'area_id': [],
            'execution_active': True,
            'coverage_target': 100,
            'region_id': [1],
            'task_active': True,
            'elapsed_time': 2323,
        }

    def test_parse_task_dict_format_multi_area(self):
        """Test parsing task descriptor from dict format with multiple areas."""
        task_data = {
            'd': {'area_id': [2, 3], 'exe': False, 'o': 80, 'region_id': [2, 3], 'status': False, 'time': 1800}, 
            't': 'TASK'
        }
        
        result = self.handler.parse_value(task_data)
        
        assert result is True
        assert self.handler.task_type == TaskType.TASK
        assert self.handler.region_id == [2, 3]
        assert self.handler.get_notification_data() == {
            'type': 'TASK',
            'area_id': [2, 3],
            'execution_active': False,
            'coverage_target': 80,
            'region_id': [2, 3],
            'task_active': False,
            'elapsed_time': 1800,
        }

    def test_parse_task_unknown_type(self):
        """Test parsing task with unknown type."""
        task_data = {
            'd': {'area_id': [], 'exe': True, 'o': 100, 'region_id': [1], 'status': True, 'time': 2323}, 
            't': 'UNKNOWN'
        }
        
        result = self.handler.parse_value(task_data)
        
        assert result is True
        assert self.handler.task_type == TaskType.UNKNOWN

    def test_parse_task_invalid_format(self):
        """Test parsing invalid task format."""
        result = self.handler.parse_value("invalid string")
        assert result is False
        
        result = self.handler.parse_value(123)
        assert result is False

    def test_parse_task_paused_docked_state(self):
        """Test parsing task descriptor for paused/docked state (minimal fields)."""
        # This is the real-world case from the error log
        task_data = {'d': {'exe': True, 'o': 4, 'status': True}, 't': 'TASK'}
        
        result = self.handler.parse_value(task_data)
        
        assert result is True
        assert self.handler.task_type == TaskType.TASK
        # Optional fields should have default values
        assert self.handler.region_id is None
        assert self.handler.get_notification_data() == {
            'type': 'TASK',
            'area_id': None,
            'execution_active': True,
            'coverage_target': 4,
            'region_id': None,
            'task_active': True,
            'elapsed_time': None,
        }

    def test_get_notification_data(self):
        """Test getting notification data."""
        task_data = {
            'd': {'area_id': [1, 2], 'exe': True, 'o': 75, 'region_id': [1], 'status': True, 'time': 1500}, 
            't': 'TASK'
        }
        self.handler.parse_value(task_data)
        
        notification = self.handler.get_notification_data()
        
        expected = {
            'type': 'TASK',
            'area_id': [1, 2],
            'execution_active': True,
            'coverage_target': 75,
            'region_id': [1],
            'task_active': True,
            'elapsed_time': 1500,
        }
        assert notification == expected


class TestSummaryHandler:
    """Test SummaryHandler for property 2:52."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = SummaryHandler()

    def test_parse_empty_summary(self):
        """Test parsing empty summary (current behavior)."""
        result = self.handler.parse_value({})
        
        assert result is True
        assert self.handler.is_empty is True
        assert self.handler.get_notification_data() == {}

    def test_parse_future_summary_data(self):
        """Test parsing future summary data with content."""
        summary_data = {
            'area': 150.5,
            'covered_area': 148.2,
            'duration': 3600,
            'result': 'completed',
            'zones': [1, 2],
            'energy_used': 25.5
        }
        
        result = self.handler.parse_value(summary_data)
        
        assert result is True
        assert self.handler.is_empty is False
        assert self.handler.get_notification_data() == summary_data

    def test_parse_invalid_format(self):
        """Test parsing invalid summary format."""
        result = self.handler.parse_value("not a dict")
        assert result is False

    def test_get_notification_data(self):
        """Test getting notification data."""
        summary_data = {'area': 100, 'duration': 1800}
        self.handler.parse_value(summary_data)
        
        notification = self.handler.get_notification_data()
        assert notification == summary_data


class TestSchedulingPropertyHandler:
    """Test unified SchedulingPropertyHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = SchedulingPropertyHandler()
        self.notifications = []
        
        def mock_notify(property_name, value):
            self.notifications.append((property_name, value))
        
        self.notify_callback = mock_notify

    def test_handle_task_property_mqtt_message(self):
        """Test handling task property from MQTT message format."""
        # Real MQTT message: {'id': 1119, 'method': 'properties_changed', 'params': [{'did': '-1xxxxxxx5', 'piid': 50, 'siid': 2, 'value': {'d': {'exe': True, 'o': 4, 'status': True}, 't': 'TASK'}}]}
        task_value = {
            'd': {'area_id': [], 'exe': True, 'o': 100, 'region_id': [1], 'status': True, 'time': 2323}, 
            't': 'TASK'
        }
        
        result = self.handler.handle_property_update(2, 50, task_value, self.notify_callback)
        
        assert result is True
        assert len(self.notifications) == 1
        assert self.notifications[0][0] == SCHEDULING_TASK_PROPERTY.name
        task_data = self.notifications[0][1]
        assert task_data['type'] == 'TASK'
        assert task_data['execution_active'] is True
        assert task_data['coverage_target'] == 100

    def test_handle_summary_property_mqtt_message(self):
        """Test handling summary property from MQTT message format."""
        # Real MQTT message: {'id': 1109, 'method': 'properties_changed', 'params': [{'did': '-1xxxxxxx5', 'piid': 52, 'siid': 2, 'value': {}}]}
        summary_value = {}
        
        result = self.handler.handle_property_update(2, 52, summary_value, self.notify_callback)
        
        assert result is True
        assert len(self.notifications) == 1
        assert self.notifications[0][0] == SCHEDULING_SUMMARY_PROPERTY.name
        assert self.notifications[0][1] == {}

    def test_handle_non_scheduling_property(self):
        """Test handling non-scheduling property returns False."""
        # Battery property (3:1)
        result = self.handler.handle_property_update(3, 1, 85, self.notify_callback)
        
        assert result is False
        assert len(self.notifications) == 0

    def test_error_handling(self):
        """Test error handling for invalid data."""
        # Invalid task data
        result = self.handler.handle_property_update(2, 50, "invalid json", self.notify_callback)
        assert result is False
        
        # Non-scheduling property is not handled
        result = self.handler.handle_property_update(2, 51, 12345, self.notify_callback)
        assert result is False
        
        # Invalid summary data
        result = self.handler.handle_property_update(2, 52, "not a dict", self.notify_callback)
        assert result is False


def test_a_confirmed_map_action_leaves_the_task_alone():
    """The 2:50 report also confirms changes to the map; those are no task."""
    handler = SchedulingPropertyHandler()
    notify = Mock()

    handled = handler.handle_property_update(
        SCHEDULING_TASK_PROPERTY.siid,
        SCHEDULING_TASK_PROPERTY.piid,
        {"t": "TASK", "d": {"o": 215, "exe": True, "status": True, "error": 0, "id": 101}},
        notify,
    )

    assert handled is True
    notify.assert_not_called()

    handler.handle_property_update(
        SCHEDULING_TASK_PROPERTY.siid,
        SCHEDULING_TASK_PROPERTY.piid,
        {"t": "TASK", "d": {"o": 100, "exe": True, "status": True}},
        notify,
    )
    notify.assert_called_once()
