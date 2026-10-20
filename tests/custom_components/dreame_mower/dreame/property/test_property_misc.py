"""Tests for miscellaneous property handlers (property_misc module)."""

import pytest
from unittest.mock import patch, MagicMock, Mock

from custom_components.dreame_mower.dreame.property.property_misc import (
    Property11Handler,
    SettingsChangeHandler,
    MiscPropertyHandler,
    PROPERTY_1_1_ACTIVE_CODES_NAME,
    PROPERTY_1_1_SIGNAL_NAME,
    PROPERTY_1_1_TASK_STATUS_NAME,
    SETTINGS_CHANGED_PROPERTY_NAME,
)

# Raw heartbeat subState bytes (byte 13) for relevant task statuses.
_SUB_PAUSED = 36  # → "paused" (resting)
_SUB_DOCK = 40    # → "returning_to_dock" (transient)


def _heartbeat(main_state_byte: int = 0, sub_state: int = 0) -> list[int]:
    """Build a minimal 20-byte CE-sentinel heartbeat payload."""
    data = [206] + [0] * 18 + [206]
    data[12] = main_state_byte
    data[13] = sub_state
    return data


# byte12 values that produce the desired mainState after (byte12 & 0x0f) - 1
_MOWING_BYTE = 5  # → mainState == 4 (MOWING)
_IDLE_BYTE = 1    # → mainState == 0 (IDLE)
_SUB_WORKING = 35  # active mowing, no unfinished task


class TestProperty11Handler:
    """Test cases for Property11Handler."""

    def test_init(self):
        """Test handler initialization."""
        handler = Property11Handler()
        
        # Nothing is known before the first heartbeat
        assert handler.task_status is None
        assert handler.active_codes is None
        assert handler.robot_state is None
        assert handler.link_module_installed is None

    def test_parse_value_valid_data(self):
        """Test parsing valid property 1:1 data."""
        handler = Property11Handler()
        
        # Create test data with sentinels (206) and sample payload (18 bytes between sentinels)
        test_data = [
            206,  # Start sentinel (index 0)
            0,    # payload[0]
            0,    # payload[1]
            0,    # payload[2]
            0,    # payload[3]
            0,    # payload[4]
            0,    # payload[5]
            4,    # payload[6]
            0,    # payload[7]
            0,    # payload[8]
            0,    # payload[9]
            85,   # payload[10]
            33,   # payload[11]
            35,   # payload[12]
            133,  # payload[13]
            54,   # payload[14]
            0,    # payload[15]
            235,  # payload[16]
            68,   # payload[17]
            206   # End sentinel (index 19)
        ]
        
        result = handler.parse_value(test_data)
        
        # Should return True for successful parsing
        assert result is True

    def test_parse_value_unknown_length(self):
        """Test parsing with non-standard data lengths."""
        handler = Property11Handler()
        
        # 24-byte variant (mova.mower.g2405c firmware 4.3.6_0062, issue #18) - silently acknowledged
        result = handler.parse_value([1] + [0] * 22 + [0])
        assert result is True

        # 22-byte variant (dreame.mower.a3-awd-pro, issue #178) - silently acknowledged
        result = handler.parse_value(
            [206, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100, 193, 255, 0, 0, 128, 184, 196, 0, 0, 206]
        )
        assert result is True

        # Unknown sizes return False to surface new firmware variants
        result = handler.parse_value([206, 1, 2, 3])  # 4 bytes
        assert result is False
        
        result = handler.parse_value([206] * 25)  # 25 bytes
        assert result is False

    def test_parse_value_invalid_type(self):
        """Test parsing with invalid data type."""
        handler = Property11Handler()
        
        # Test with non-list input
        result = handler.parse_value("invalid")
        assert result is False

    def test_parse_value_unknown_sentinels(self):
        """Test parsing 20-byte arrays with non-standard sentinel values are silently accepted."""
        handler = Property11Handler()

        # Non-CE sentinels on 20-byte array (e.g. dreame.swbot.g2509) - silently accepted
        test_data = [100] + [0] * 18 + [206]
        result = handler.parse_value(test_data)
        assert result is True

        test_data = [206] + [0] * 18 + [100]
        result = handler.parse_value(test_data)
        assert result is True

    @patch('custom_components.dreame_mower.dreame.property.property_misc._LOGGER')
    def test_logging_on_invalid_format(self, mock_logger):
        """Test that proper warnings are logged for invalid data format."""
        handler = Property11Handler()
        
        # Test with invalid type
        handler.parse_value("not a list")
        mock_logger.warning.assert_called()

    def test_notify_not_called_when_status_unchanged(self):
        """Notify is not emitted when the decoded task status doesn't change."""
        handler = Property11Handler()
        notify = MagicMock()
        handler.parse_value(_heartbeat(_MOWING_BYTE, _SUB_PAUSED), notify)
        notify.reset_mock()
        # Same state again
        handler.parse_value(_heartbeat(_MOWING_BYTE, _SUB_PAUSED), notify)
        notify.assert_not_called()

    def test_notify_optional(self):
        """parse_value with no notify_callback does not raise."""
        handler = Property11Handler()
        assert handler.parse_value(_heartbeat(_MOWING_BYTE, _SUB_PAUSED)) is True
        assert handler.task_status == "paused"

    def test_task_status_initially_none(self):
        """task_status is None until a heartbeat is decoded."""
        assert Property11Handler().task_status is None

    @pytest.mark.parametrize(
        "sub_state, expected",
        [
            (33, "idle"),
            (34, "starting"),
            (35, "mowing"),
            (_SUB_PAUSED, "paused"),
            (37, "finished"),
            (38, "failed"),
            (39, "exit"),
            (_SUB_DOCK, "returning_to_dock"),
        ],
    )
    def test_task_status_mowing_substates(self, sub_state, expected):
        """While mowing, each subState maps to the matching task status."""
        handler = Property11Handler()
        notify = MagicMock()
        handler.parse_value(_heartbeat(_MOWING_BYTE, sub_state), notify)
        assert handler.task_status == expected
        notify.assert_any_call(PROPERTY_1_1_TASK_STATUS_NAME, expected)

    def test_task_status_idle_when_not_mowing(self):
        """Any non-mowing main state reports no active task ("idle")."""
        handler = Property11Handler()
        handler.parse_value(_heartbeat(_IDLE_BYTE, _SUB_DOCK))
        assert handler.task_status == "idle"

    def test_task_status_notify_only_on_change(self):
        """task_status notify is not re-emitted when the status is unchanged."""
        handler = Property11Handler()
        notify = MagicMock()
        handler.parse_value(_heartbeat(_MOWING_BYTE, _SUB_WORKING), notify)
        status_calls = [c.args for c in notify.call_args_list if c.args[0] == PROPERTY_1_1_TASK_STATUS_NAME]
        assert status_calls == [(PROPERTY_1_1_TASK_STATUS_NAME, "mowing")]
        notify.reset_mock()
        handler.parse_value(_heartbeat(_MOWING_BYTE, _SUB_WORKING), notify)
        assert not [c for c in notify.call_args_list if c.args[0] == PROPERTY_1_1_TASK_STATUS_NAME]

    def test_mowing_session_active_initially_false(self):
        """No session is active before the first heartbeat."""
        assert Property11Handler().mowing_session_active is False

    def test_mowing_session_active_follows_lifecycle(self):
        """The session stays active through paused/mowing and ends at exit/idle."""
        handler = Property11Handler()

        handler.parse_value(_heartbeat(_MOWING_BYTE, _SUB_WORKING))  # mowing
        assert handler.mowing_session_active is True

        handler.parse_value(_heartbeat(_MOWING_BYTE, _SUB_PAUSED))  # paused at dock
        assert handler.mowing_session_active is True

        handler.parse_value(_heartbeat(_MOWING_BYTE, _SUB_DOCK))  # returning_to_dock
        assert handler.mowing_session_active is True

        handler.parse_value(_heartbeat(_MOWING_BYTE, 39))  # exit
        assert handler.mowing_session_active is False

        handler.parse_value(_heartbeat(_IDLE_BYTE, 0))  # idle
        assert handler.mowing_session_active is False


class TestSettingsChangeHandler:
    """Test SettingsChangeHandler for property 2:51."""

    def test_parse_dict_format(self):
        """Test parsing settings change from dict format."""
        handler = SettingsChangeHandler()
        settings_data = {'start': 855, 'end': 858, 'value': 1}
        notify = Mock()
        assert handler.parse_value(settings_data, notify) is True
        notify.assert_called_once_with(SETTINGS_CHANGED_PROPERTY_NAME, settings_data)

    def test_parse_timezone_format(self):
        """Test parsing settings change with timezone data."""
        handler = SettingsChangeHandler()
        settings_data = {'time': '1234567890', 'tz': 'Europe/Berlin'}
        notify = Mock()
        assert handler.parse_value(settings_data, notify) is True
        notify.assert_called_once_with(SETTINGS_CHANGED_PROPERTY_NAME, {'time': '1234567890', 'tz': 'Europe/Berlin'})

    def test_parse_invalid_format(self):
        """Test parsing invalid settings change format."""
        handler = SettingsChangeHandler()
        assert handler.parse_value(123) is False
        assert handler.parse_value("invalid string") is False


class TestMiscPropertyHandler:
    """Test MiscPropertyHandler routing."""

    def test_matches_property_1_1(self):
        """Test that 1:1 is recognised as a misc property."""
        assert MiscPropertyHandler.matches(1, 1) is True

    def test_matches_settings_change(self):
        """Test that 2:51 is recognised as a misc property."""
        assert MiscPropertyHandler.matches(2, 51) is True

    def test_does_not_match_other_properties(self):
        """Test that unrelated properties are not matched."""
        assert MiscPropertyHandler.matches(3, 1) is False
        assert MiscPropertyHandler.matches(2, 50) is False

    def test_handle_property_1_1(self):
        """Test that 1:1 update is handled successfully."""
        handler = MiscPropertyHandler()
        notify = MagicMock()
        result = handler.handle_property_update(1, 1, [206] + [0] * 18 + [206], notify)
        assert result is True
        # A non-mowing heartbeat reports the initial task_status ("idle").
        notify.assert_any_call(PROPERTY_1_1_TASK_STATUS_NAME, "idle")

    def test_handle_property_1_1_task_status_notifies(self):
        """Test that 1:1 update emits notification when task_status changes."""
        handler = MiscPropertyHandler()
        notify = MagicMock()
        result = handler.handle_property_update(
            1, 1, _heartbeat(_MOWING_BYTE, _SUB_PAUSED), notify
        )
        assert result is True
        notify.assert_any_call(PROPERTY_1_1_TASK_STATUS_NAME, "paused")
        assert handler.task_status == "paused"

    def test_handle_settings_change(self):
        """A settings change is announced so the settings can be read back."""
        handler = MiscPropertyHandler()
        notify = MagicMock()
        result = handler.handle_property_update(2, 51, {'value': 1}, notify)
        assert result is True
        notify.assert_called_once_with(SETTINGS_CHANGED_PROPERTY_NAME, {'value': 1})

    def test_handle_unknown_property_returns_false(self):
        """Test that an unknown property returns False."""
        handler = MiscPropertyHandler()
        notify = MagicMock()
        result = handler.handle_property_update(5, 99, 42, notify)
        assert result is False

    def test_task_status_initially_none(self):
        """MiscPropertyHandler.task_status is None by default."""
        assert MiscPropertyHandler().task_status is None



class TestActiveCodes:
    """The heartbeat reports the conditions the device is under right now."""

    @staticmethod
    def _with_codes(*codes: int) -> list[int]:
        """Build a heartbeat whose bitmask carries the given codes."""
        data = _heartbeat(_IDLE_BYTE, 0)
        for code in codes:
            data[1 + code // 8] |= 1 << (code % 8)
        return data

    def test_active_codes_initially_unknown(self):
        """Nothing is known about the device until a heartbeat arrives."""
        assert Property11Handler().active_codes is None

    def test_decodes_the_codes_the_bitmask_carries(self):
        """Each set bit stands for the code at its position."""
        handler = Property11Handler()
        handler.parse_value(self._with_codes(56, 24))

        assert handler.active_codes == frozenset({24, 56})

    def test_ignores_the_bit_every_heartbeat_sets(self):
        """Bit 79 is set regardless of what the device reports and means nothing."""
        handler = Property11Handler()
        handler.parse_value(self._with_codes(79))

        assert handler.active_codes == frozenset()

    def test_a_code_clears_when_the_device_stops_reporting_it(self):
        """The bitmask is live state, so a cleared bit has to drop the code."""
        handler = Property11Handler()
        handler.parse_value(self._with_codes(56))
        handler.parse_value(self._with_codes())

        assert handler.active_codes == frozenset()

    def test_announces_the_codes_when_they_change(self):
        """A change in what the device reports is announced once."""
        handler = Property11Handler()
        notify = MagicMock()
        handler.parse_value(self._with_codes(56), notify)

        notify.assert_any_call(PROPERTY_1_1_ACTIVE_CODES_NAME, frozenset({56}))

    def test_does_not_announce_unchanged_codes(self):
        """Every heartbeat repeats the bitmask; only changes are worth announcing."""
        handler = Property11Handler()
        notify = MagicMock()
        handler.parse_value(self._with_codes(56), notify)
        notify.reset_mock()
        handler.parse_value(self._with_codes(56), notify)

        code_calls = [
            call for call in notify.call_args_list
            if call.args[0] == PROPERTY_1_1_ACTIVE_CODES_NAME
        ]
        assert code_calls == []

    def test_a_docked_heartbeat_decodes_to_the_reported_conditions(self):
        """A heartbeat as the device sends it decodes to the codes it stands for."""
        handler = Property11Handler()
        # Sent while the device is docked after finishing a task: it reports
        # the task having started and finished, plus the ever-present bit 79.
        handler.parse_value(
            [206, 0, 0, 0, 0, 0, 0, 5, 0, 0, 128, 100, 129, 255, 0, 0, 128, 189, 186, 206]
        )

        assert handler.active_codes == frozenset({48, 50})


class TestLinkModuleState:
    """The heartbeat's byte 18 tells whether the cellular module can be used."""

    def test_unknown_until_a_heartbeat_arrives(self):
        """Nothing is claimed about a module before the mower reports one."""
        handler = Property11Handler()

        assert handler.link_module_installed is None
        assert handler.link_module_plan_valid is None

    @pytest.mark.parametrize("rssi,installed,plan_valid", [
        (127, False, False),  # no module fitted
        (0, True, False),     # fitted, data plan no longer valid
        (100, True, False),   # fitted, data plan no longer valid
        (128, True, True),    # fitted, data plan valid
        (200, True, True),    # fitted, data plan valid
    ])
    def test_decodes_the_module_state(self, rssi, installed, plan_valid):
        """The signal byte doubles as the module's fitted and plan state."""
        handler = Property11Handler()
        payload = _heartbeat()
        payload[18] = rssi

        assert handler.parse_value(payload) is True
        assert handler.link_module_installed is installed
        assert handler.link_module_plan_valid is plan_valid


def test_the_heartbeat_says_where_the_mower_stands():
    """Byte 14: position (bits 0-1), way to the station (bits 2-4), leaving (bit 6)."""
    from custom_components.dreame_mower.dreame.property.property_misc import PROPERTY_1_1_ROBOT_STATE_NAME

    handler = Property11Handler()
    notify = MagicMock()
    data = _heartbeat(_MOWING_BYTE, _SUB_WORKING)
    data[11] = 0x80 | 90  # charging, 90 %
    data[14] = 1 | (1 << 2) | 0x40  # relocating, out of the station, leaving it
    data[15] = (2 << 1) | 1  # zone mowing, started by a schedule

    assert handler.parse_value(data, notify)

    assert handler.robot_state == {
        "main_state": 4,
        "sub_state": _SUB_WORKING,
        "location": "relocating",
        "docking": "out_of_station",
        "leaving_station": True,
        "work_mode": 2,
        "scheduled": True,
        "charging": True,
    }
    notify.assert_any_call(PROPERTY_1_1_ROBOT_STATE_NAME, handler.robot_state)

    # The same state again announces nothing.
    notify.reset_mock()
    handler.parse_value(data, notify)
    assert not any(call.args[0] == PROPERTY_1_1_ROBOT_STATE_NAME for call in notify.call_args_list)


def test_a_heartbeat_describing_no_real_state_is_passed_over():
    handler = Property11Handler()
    data = _heartbeat(_IDLE_BYTE, 0x28)
    data[14] = 7

    handler.parse_value(data, MagicMock())

    assert handler.robot_state is None


# Heartbeat read from a dreame.mower.g2541e (A3 AWD Pro) mowing far from the
# access point: Wi-Fi at -87 dBm (byte 17), cellular at -70 dBm (byte 18).
_A3_HEARTBEAT = [206, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 53, 229, 36, 135, 0, 128, 169, 186, 0, 128, 206]


class TestLinkSignal:
    """Bytes 17 and 18 carry the Wi-Fi and cellular signal strengths."""

    def test_unknown_until_a_heartbeat_arrives(self):
        """No reading is claimed before the mower reports one."""
        handler = Property11Handler()

        assert handler.wifi_signal_dbm is None
        assert handler.cellular_signal_dbm is None

    def test_decodes_both_links_from_the_heartbeat(self):
        """Signed bytes below zero are the signal strengths in dBm."""
        handler = Property11Handler()
        payload = _heartbeat()
        payload[17] = 190
        payload[18] = 200

        assert handler.parse_value(payload) is True
        assert handler.wifi_signal_dbm == -66
        assert handler.cellular_signal_dbm == -56

    def test_decodes_the_22_byte_variant(self):
        """The A3 AWD Pro heartbeat carries the signal bytes at the same offsets."""
        handler = Property11Handler()

        assert handler.parse_value(list(_A3_HEARTBEAT)) is True
        assert handler.wifi_signal_dbm == -87
        assert handler.cellular_signal_dbm == -70
        assert handler.link_module_installed is True
        assert handler.link_module_plan_valid is True

    @pytest.mark.parametrize("wifi,cellular", [
        (0, 127),    # off Wi-Fi, no module fitted
        (0, 100),    # off Wi-Fi, module fitted but its plan expired
    ])
    def test_links_without_a_reading(self, wifi, cellular):
        """A byte that carries no signal reads as unknown, not as a strength."""
        handler = Property11Handler()
        payload = _heartbeat()
        payload[17] = wifi
        payload[18] = cellular

        assert handler.parse_value(payload) is True
        assert handler.wifi_signal_dbm is None
        assert handler.cellular_signal_dbm is None

    def test_notifies_only_when_a_reading_changes(self):
        """Listeners hear about a new reading once, not on every heartbeat."""
        handler = Property11Handler()
        notify = MagicMock()

        handler.update_signal(list(_A3_HEARTBEAT), notify)
        handler.update_signal(list(_A3_HEARTBEAT), notify)
        weaker = list(_A3_HEARTBEAT)
        weaker[17] = 166
        handler.update_signal(weaker, notify)

        assert [c.args for c in notify.call_args_list] == [
            (PROPERTY_1_1_SIGNAL_NAME, (-87, -70)),
            (PROPERTY_1_1_SIGNAL_NAME, (-90, -70)),
        ]

    @pytest.mark.parametrize("value", [
        None,
        [0] * 22,                         # no sentinels
        [206] + [0] * 22 + [206],         # unknown length
    ])
    def test_ignores_what_is_not_a_heartbeat(self, value):
        """Only a framed heartbeat of a known length updates the readings."""
        handler = Property11Handler()

        assert handler.update_signal(value, None) is False
        assert handler.wifi_signal_dbm is None
