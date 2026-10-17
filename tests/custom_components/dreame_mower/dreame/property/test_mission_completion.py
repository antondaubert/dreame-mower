"""Tests for MissionCompletionEventHandler class."""

from typing import Any
from unittest.mock import Mock, patch

from custom_components.dreame_mower.dreame.property.mission_completion import (
    MissionCompletionEventHandler,
    MISSION_COMPLETION_EVENT_PROPERTY_NAME,
    TASK_MODE_FIELD,
    DURATION_FIELD,
    AREA_FIELD,
    STATUS_FIELD,
    STATUS_FINISHED,
    STATUS_INTERRUPTED,
    START_TIMESTAMP_FIELD,
    DATA_FILE_PATH_FIELD,
    SCHEDULED_FIELD,
    CHARGING_EVENTS_FIELD,
    PLANNED_AREA_FIELD,
    UNKNOWN_FIELD_15,
    STOP_REASON_FIELD,
    MAP_NAME_FIELD,
)

EMPTY_EVENT = {
    TASK_MODE_FIELD: None,
    DURATION_FIELD: None,
    AREA_FIELD: None,
    STATUS_FIELD: None,
    START_TIMESTAMP_FIELD: None,
    DATA_FILE_PATH_FIELD: None,
    SCHEDULED_FIELD: None,
    CHARGING_EVENTS_FIELD: None,
    PLANNED_AREA_FIELD: None,
    UNKNOWN_FIELD_15: None,
    STOP_REASON_FIELD: None,
    MAP_NAME_FIELD: None,
}


def _parse(handler: MissionCompletionEventHandler, arguments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Parse an event and return what it announced, or None when it failed."""
    notify_callback = Mock()
    if not handler._parse_mission_completion_event(arguments, notify_callback):
        notify_callback.assert_not_called()
        return None
    notify_callback.assert_called_once()
    name, data = notify_callback.call_args.args
    assert name == MISSION_COMPLETION_EVENT_PROPERTY_NAME
    return data


class TestMissionCompletionEventHandler:
    """Test cases for MissionCompletionEventHandler."""

    def test_init(self):
        """Test handler initialization."""
        handler = MissionCompletionEventHandler()

        assert handler.status is None
        assert handler.stop_reason is None
        assert handler.has_data_file is False
        assert handler.is_patrol is False

    def test_parse_mission_completion_event_full_data(self):
        """Test parsing a complete mission completion event with all fields."""
        handler = MissionCompletionEventHandler()

        # Mission completed normally - status=FINISHED (1), stop_reason=-1
        event = _parse(handler, [
            {"piid": 1, "value": 100},  # All-area mowing
            {"piid": 2, "value": 127},  # Duration in minutes
            {"piid": 3, "value": 6820},  # Area value (68.20 m² when divided by 100)
            {"piid": 7, "value": 1},  # STATUS_FINISHED: mission completed normally
            {"piid": 8, "value": 1725643523},  # Start timestamp
            {"piid": 9, "value": "/tmp/mowing_session_analysis_20240906_203203_extended.json"},  # Data file path
            {"piid": 11, "value": 1},  # Started by a schedule
            {"piid": 13, "value": []},  # Charging events
            {"piid": 14, "value": 70},  # Planned area in m²
            {"piid": 15, "value": 2},  # Unknown field 15
            {"piid": 60, "value": -1},  # stop_reason: -1 = normal completion
        ])

        assert event == {
            TASK_MODE_FIELD: "all_area",
            DURATION_FIELD: 127,
            AREA_FIELD: 68.20,
            STATUS_FIELD: STATUS_FINISHED,
            START_TIMESTAMP_FIELD: 1725643523,
            DATA_FILE_PATH_FIELD: "/tmp/mowing_session_analysis_20240906_203203_extended.json",
            SCHEDULED_FIELD: True,
            CHARGING_EVENTS_FIELD: [],
            PLANNED_AREA_FIELD: 70,
            UNKNOWN_FIELD_15: 2,
            STOP_REASON_FIELD: -1,
            MAP_NAME_FIELD: None,
        }
        assert handler.status == STATUS_FINISHED
        assert handler.stop_reason == -1
        assert handler.has_data_file is True
        assert handler.is_complete is True  # status=FINISHED (1) → complete

    def test_parse_mission_completion_event_partial_data(self):
        """Test parsing mission completion event with only some fields."""
        handler = MissionCompletionEventHandler()

        event = _parse(handler, [
            {"piid": 1, "value": 102},  # Zone mowing
            {"piid": 2, "value": 95},  # Duration in minutes
        ])

        assert event == {**EMPTY_EVENT, TASK_MODE_FIELD: "zone", DURATION_FIELD: 95}
        assert handler.has_data_file is False
        assert handler.is_complete is True  # No status → assume normal completion

    def test_parse_mission_completion_event_unknown_piid(self):
        """A field the parser does not know is skipped; the rest still counts."""
        handler = MissionCompletionEventHandler()

        event = _parse(handler, [
            {"piid": 1, "value": 100},
            {"piid": 999, "value": "unknown_field"},  # Unknown piid
        ])

        assert event is not None
        assert event[TASK_MODE_FIELD] == "all_area"

    def test_a_patrol_event_parses(self):
        """A patrol reports whether it looked for people and found any."""
        handler = MissionCompletionEventHandler()

        event = _parse(
            handler,
            [{"piid": 1, "value": 108}, {"piid": 10, "value": 1}, {"piid": 12, "value": 0}, {"piid": 7, "value": 1}],
        )

        assert event is not None
        assert event[TASK_MODE_FIELD] == "edge_patrol"
        assert handler.is_patrol is True
        assert handler.is_complete is True

    def test_older_firmware_reports_the_task_mode_without_the_offset(self):
        handler = MissionCompletionEventHandler()

        event = _parse(handler, [{"piid": 1, "value": 3}])

        assert event is not None
        assert event[TASK_MODE_FIELD] == "spot"

    def test_parse_mission_completion_event_invalid_arguments(self):
        """Test parsing with malformed arguments should fail."""
        handler = MissionCompletionEventHandler()

        # Missing value in the first argument
        assert _parse(handler, [{"piid": 1}, {"piid": 2, "value": 50}]) is None
        assert handler.status is None

    def test_parse_mission_completion_event_missing_piid(self):
        """Test parsing with missing piid should fail."""
        handler = MissionCompletionEventHandler()

        assert _parse(handler, [{"value": 100}]) is None

    def test_handle_event_correct_service_event(self):
        """Test handle_event with correct Service 4:1 event."""
        handler = MissionCompletionEventHandler()
        notify_callback = Mock()

        result = handler.handle_event(4, 1, [{"piid": 1, "value": 100}, {"piid": 7, "value": 3}], notify_callback)

        assert result is True
        assert handler.status == STATUS_INTERRUPTED
        notify_callback.assert_called_once()

    def test_handle_event_wrong_service_event(self):
        """Test handle_event with wrong service/event ID."""
        handler = MissionCompletionEventHandler()
        notify_callback = Mock()

        result = handler.handle_event(2, 1, [{"piid": 7, "value": 1}], notify_callback)

        assert result is False
        assert handler.status is None  # Should not be set
        notify_callback.assert_not_called()

    def test_area_conversion_precision(self):
        """Test area conversion (divide by 100 to get m²) with various values."""
        handler = MissionCompletionEventHandler()

        for area_value, expected_m_squared in [(100, 1.0), (6820, 68.20), (5000, 50.0), (1, 0.01)]:
            event = _parse(handler, [{"piid": 3, "value": area_value}])

            assert event is not None
            assert event[AREA_FIELD] == expected_m_squared

    def test_a_new_event_forgets_the_last(self):
        """Every event starts from nothing, so no field carries over."""
        handler = MissionCompletionEventHandler()
        _parse(handler, [{"piid": 7, "value": 1}, {"piid": 60, "value": 101}, {"piid": 9, "value": "a.json"}])

        event = _parse(handler, [{"piid": 2, "value": 5}])

        assert event == {**EMPTY_EVENT, DURATION_FIELD: 5}
        assert handler.status is None
        assert handler.stop_reason is None
        assert handler.has_data_file is False

    def test_an_interrupted_mission_is_not_complete(self):
        handler = MissionCompletionEventHandler()

        _parse(handler, [{"piid": 7, "value": STATUS_INTERRUPTED}, {"piid": 60, "value": 101}])

        assert handler.status == STATUS_INTERRUPTED
        assert handler.stop_reason == 101  # low battery / returned to dock early
        assert handler.is_complete is False

    def test_edge_case_empty_arguments(self):
        """Test parsing with empty arguments list."""
        handler = MissionCompletionEventHandler()

        assert _parse(handler, []) == EMPTY_EVENT

    def test_data_file_path_variations(self):
        """Test various data file path formats."""
        handler = MissionCompletionEventHandler()

        for path in [
            "/tmp/mowing_session_analysis_20240906_203203.json",
            "/tmp/mowing_session_analysis_20240906_203203_extended.json",
            "session_data.json",
            "",  # Empty string
        ]:
            event = _parse(handler, [{"piid": 9, "value": path}])

            assert event is not None
            assert event[DATA_FILE_PATH_FIELD] == path
            assert handler.has_data_file == (path != "")

    def test_parse_mission_completion_event_with_charging_events(self):
        """Charging sessions during the mission come as [timestamp, minutes] pairs."""
        handler = MissionCompletionEventHandler()

        event = _parse(handler, [
            {"piid": 1, "value": 100},  # All-area mowing
            {"piid": 2, "value": 183},  # Duration in minutes (3h 3min)
            {"piid": 3, "value": 25339},  # Area value (253.39 m² when divided by 100)
            {"piid": 7, "value": 1},  # STATUS_FINISHED: mission completed normally
            {"piid": 8, "value": 1759314580},  # Start timestamp (2025-10-01)
            {"piid": 9, "value": "ali_dreame/2025/10/01/Nxxxxxx4/-1xxxxxxx8_162243699.0430.json"},  # Data file path
            {"piid": 11, "value": 0},  # Started in the app
            {"piid": 60, "value": -1},  # stop_reason: -1 = normal completion
            {"piid": 13, "value": [[1759318403, 24], [1759328060, 24]]},  # Two charging sessions
            {"piid": 14, "value": 270},  # Planned area in m²
            {"piid": 15, "value": -1},  # Unknown field 15
        ])

        assert event == {
            TASK_MODE_FIELD: "all_area",
            DURATION_FIELD: 183,
            AREA_FIELD: 253.39,
            STATUS_FIELD: STATUS_FINISHED,
            START_TIMESTAMP_FIELD: 1759314580,
            DATA_FILE_PATH_FIELD: "ali_dreame/2025/10/01/Nxxxxxx4/-1xxxxxxx8_162243699.0430.json",
            SCHEDULED_FIELD: False,
            CHARGING_EVENTS_FIELD: [[1759318403, 24], [1759328060, 24]],
            PLANNED_AREA_FIELD: 270,
            UNKNOWN_FIELD_15: -1,
            STOP_REASON_FIELD: -1,
            MAP_NAME_FIELD: None,
        }
        assert handler.is_complete is True

    def test_parse_mission_completion_event_with_map_name(self):
        """Test parsing mission completion event with piid 16 (map_name)."""
        handler = MissionCompletionEventHandler()

        event = _parse(handler, [
            {"piid": 1, "value": 102},   # Zone mowing
            {"piid": 2, "value": 23},    # Duration minutes
            {"piid": 3, "value": 774},   # Area (7.74 m²)
            {"piid": 7, "value": 2},  # Unfinished
            {"piid": 8, "value": 1772956800},  # Start timestamp
            {"piid": 9, "value": "ali_dreame/2026/03/08/HJxxxxxx4/-1xxxxxxx4_082338835.0169.json"},
            {"piid": 11, "value": 1},
            {"piid": 60, "value": 224},
            {"piid": 13, "value": []},
            {"piid": 14, "value": 107},
            {"piid": 15, "value": 0},
            {"piid": 16, "value": "map1"},  # Map name/identifier
        ])

        assert event == {
            TASK_MODE_FIELD: "zone",
            DURATION_FIELD: 23,
            AREA_FIELD: 7.74,
            STATUS_FIELD: 2,
            START_TIMESTAMP_FIELD: 1772956800,
            DATA_FILE_PATH_FIELD: "ali_dreame/2026/03/08/HJxxxxxx4/-1xxxxxxx4_082338835.0169.json",
            SCHEDULED_FIELD: True,
            CHARGING_EVENTS_FIELD: [],
            PLANNED_AREA_FIELD: 107,
            UNKNOWN_FIELD_15: 0,
            STOP_REASON_FIELD: 224,
            MAP_NAME_FIELD: "map1",
        }
        assert handler.is_complete is False


def test_older_firmware_reports_the_area_in_square_metres_and_swaps_the_status():
    """Its task mode has no offset, which only shows once the mode was read."""
    handler = MissionCompletionEventHandler()

    # The area comes before the mode it is read by.
    event = _parse(handler, [{"piid": 3, "value": 120}, {"piid": 7, "value": 0}, {"piid": 1, "value": 0}])

    assert event is not None
    assert event[AREA_FIELD] == 120
    assert handler.status == 3
    assert event[TASK_MODE_FIELD] == "all_area"

    event = _parse(handler, [{"piid": 3, "value": 12000}, {"piid": 7, "value": 3}, {"piid": 1, "value": 100}])

    assert event is not None
    assert event[AREA_FIELD] == 120
    assert handler.status == 3


def test_the_data_file_is_downloaded_to_the_config_directory():
    handler = MissionCompletionEventHandler()
    _parse(handler, [{"piid": 9, "value": "ali_dreame/2026/03/08/task.json"}])
    get_url = Mock()

    with patch(
        "custom_components.dreame_mower.dreame.property.mission_completion.download_file",
        return_value={"local_path": "/config/www/dreame/ali_dreame/2026/03/08/task.json"},
    ) as download:
        assert handler.download_data_file(get_url, "/config") is True

    download.assert_called_once_with(
        file_path="ali_dreame/2026/03/08/task.json",
        get_download_url=get_url,
        hass_config_dir="/config",
        timeout=15,
    )


def test_no_data_file_means_nothing_to_download():
    handler = MissionCompletionEventHandler()
    _parse(handler, [{"piid": 9, "value": ""}])

    with patch("custom_components.dreame_mower.dreame.property.mission_completion.download_file") as download:
        assert handler.download_data_file(Mock(), "/config") is False

    download.assert_not_called()
