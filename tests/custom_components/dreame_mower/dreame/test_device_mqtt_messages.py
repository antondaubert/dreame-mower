"""Test device MQTT message handling.

This test module focuses on testing the device-level integration of MQTT message handling.
It verifies that real-world MQTT messages (as reported in issues) are correctly processed
through the full device stack.

Key aspects tested:
- _handle_mqtt_property_update: Direct property update handling
- _handle_message: Full MQTT message flow including properties_changed wrapper
- Property notifications: Verifies callbacks are triggered correctly
- Parametrized tests: Easy to add new message types from future issues

When adding new message types, add them to the parametrized tests to ensure they
are properly handled.
"""

import pytest
from unittest.mock import Mock, patch

from custom_components.dreame_mower.dreame.device import DreameMowerDevice, DreameSwbotDevice


class TestDeviceMqttPropertyUpdate:
    """Test _handle_mqtt_property_update with real MQTT messages."""

    @pytest.fixture
    def device(self):
        """Create a device instance for testing."""
        with patch('custom_components.dreame_mower.dreame.device.DreameMowerCloudDevice'):
            device = DreameMowerDevice(
                device_id="test_device",
                username="test_user",
                password="test_pass",
                account_type="mi",
                country="de",
                hass_config_dir="/tmp"
            )
            return device

    @pytest.fixture
    def property_notifications(self):
        """Create a list to capture property notifications."""
        notifications = []
        
        def callback(property_name, value):
            notifications.append((property_name, value))
        
        return notifications, callback

    @pytest.mark.parametrize(
        "mqtt_message,expected_property,expected_value_check",
        [
            (# Battery update
                {
                    "id": 100,
                    "method": "properties_changed",
                    "params": [{"did": "-1******95", "piid": 1, "siid": 3, "value": 85}]
                },
                "battery_percent",
                lambda v: v == 85
            ),
            (# Status update
                {
                    "id": 101,
                    "method": "properties_changed",
                    "params": [{"did": "-1******95", "piid": 1, "siid": 2, "value": 13}]
                },
                "status",
                lambda v: v == 13
            ),
            (  # Issue #51: 1:4 13-byte pose format (mova.mower.g2529d fw 4.3.6_0169)
                {
                    "id": 244,
                    "method": "properties_changed",
                    "params": [{"did": "-1******76", "piid": 4, "siid": 1, "value": [206, 24, 253, 239, 251, 255, 116, 17, 253, 207, 252, 255, 206]}]
                },
                "mowing_coordinates",
                # 20-bit pose: x=-744, y=-66 (scaled by _POSE_SCALE=10)
                lambda v: v["x"] == -7440 and v["y"] == -660
            ),
            (  # Issue #50: 1:4 13-byte pose format (mova.mower.g2529d fw 4.3.6_0169)
                {
                    "id": 361,
                    "method": "properties_changed",
                    "params": [{"did": "-1******76", "piid": 4, "siid": 1, "value": [206, 152, 1, 224, 7, 0, 123, 149, 1, 192, 7, 0, 206]}]
                },
                "mowing_coordinates",
                # 20-bit pose: x=408, y=126 (scaled by _POSE_SCALE=10)
                lambda v: v["x"] == 4080 and v["y"] == 1260
            ),
            (  # Issue #49: 1:4 13-byte pose format (mova.mower.g2529d fw 4.3.6_0169)
                {
                    "id": 362,
                    "method": "properties_changed",
                    "params": [{"did": "-1******76", "piid": 4, "siid": 1, "value": [206, 123, 1, 224, 7, 0, 131, 131, 1, 224, 7, 0, 206]}]
                },
                "mowing_coordinates",
                # 20-bit pose: x=379, y=126 (scaled by _POSE_SCALE=10)
                lambda v: v["x"] == 3790 and v["y"] == 1260
            ),
            (  # Issue #40: 3:2 charging status 16 = charging paused low temperature (mova.mower.g2529b)
                {
                    "id": 200,
                    "method": "properties_changed",
                    "params": [{"did": "-1******54", "piid": 2, "siid": 3, "value": 16}]
                },
                "charging_status",
                lambda v: v == "charging_paused_low_temperature"
            ),
            (  # Issue #167: 2:1 device status 15 = charging paused high temperature (mova.mower.g2405c)
                {
                    "id": 201,
                    "method": "properties_changed",
                    "params": [{"did": "-1******55", "piid": 1, "siid": 2, "value": 15}]
                },
                "status",
                lambda v: v == 15
            ),
            (  # Issue #98: 1:2 firmware install state 4 = firmware_download_failed (dreame.mower.p2255 fw 4.3.6_1542)
                {
                    "id": 101,
                    "method": "properties_changed",
                    "params": [{"did": "-1******07", "piid": 2, "siid": 1, "value": 4}]
                },
                "firmware_install_state",
                lambda v: v == 4
            ),
        ],
    )
    def test_full_mqtt_messages_parametrized(
        self, device, property_notifications, mqtt_message, expected_property, expected_value_check
    ):
        """Test handling complete MQTT messages with properties_changed wrapper.
        
        This parametrized test covers real-world MQTT messages including:
        - Issue #135: Sixth variant obstacle avoidance setting
        - Battery updates
        - Status updates
        - DND schedule updates
        
        All tests use the complete MQTT message format as received from the device,
        including the id, method, and params wrapper.
        """
        notifications, callback = property_notifications
        device.register_property_callback(callback)
        
        # Process through the full message handler
        device._handle_message(mqtt_message)
        
        # Verify at least one notification was sent
        assert len(notifications) > 0, f"No notifications sent for message: {mqtt_message}"
        
        # Find the expected property in notifications
        property_names = [name for name, _ in notifications]
        assert expected_property in property_names, \
            f"Expected property '{expected_property}' not found in notifications: {property_names}"
        
        # Verify the value using the check function
        notify_dict = {name: value for name, value in notifications}
        value = notify_dict[expected_property]
        assert expected_value_check(value), \
            f"Value check failed for property '{expected_property}': {value}"


class TestDeviceMqttSilentlyAcknowledged:
    """Test properties that are silently acknowledged."""

    @pytest.fixture
    def device(self):
        """Create a device instance for testing."""
        with patch('custom_components.dreame_mower.dreame.device.DreameMowerCloudDevice'):
            device = DreameMowerDevice(
                device_id="test_device",
                username="test_user",
                password="test_pass",
                account_type="mi",
                country="de",
                hass_config_dir="/tmp"
            )
            return device

    @pytest.mark.parametrize(
        "mqtt_message,description",
        [
            (  # Issue #12: 2:63 error/status code on mova.mower.g2405a
                {
                    "id": 108,
                    "method": "properties_changed",
                    "params": [{"did": "-1******29", "piid": 63, "siid": 2, "value": -33101}]
                },
                "issue #12: 2:63 value -33101"
            ),
            (  # Issue #25: 2:54 unknown property, only value seen is 100
                {
                    "id": 109,
                    "method": "properties_changed",
                    "params": [{"did": "-1******29", "piid": 54, "siid": 2, "value": 100}]
                },
                "issue #25: 2:54 value 100"
            ),
            (  # Issue #32: 2:55 AI obstacle detection notification
                {
                    "id": 110,
                    "method": "properties_changed",
                    "params": [{"did": "-1******29", "piid": 55, "siid": 2, "value": {"type": "ai", "obs": [1, 2, 3, 4, 5]}}]
                },
                "issue #32: 2:55 AI obstacle detection"
            ),
            (  # 1:1 alt-sentinel 20-byte variant on dreame.swbot.g2509 fw 4.3.6_0603
                {
                    "id": 494595,
                    "method": "properties_changed",
                    "params": [{"piid": 1, "siid": 1, "value": [1,0,0,0,0,0,0,0,0,229,188,0,0,0,0,0,0,8,91,2]}]
                },
                "1:1 20-byte alt-sentinel variant (dreame.swbot.g2509)"
            ),
            (  # Issue #38 (also #34, #35): 2:67 4-integer array observed after MOWING_COMPLETED
                {
                    "id": 1767,
                    "method": "properties_changed",
                    "params": [{"did": "-1******61", "piid": 67, "siid": 2, "value": [0, 0, 0, 0]}]
                },
                "issue #38: 2:67 value [0, 0, 0, 0] after MOWING_COMPLETED (mova.mower.g2420a fw 4.3.6_0325)"
            ),
            (  # Issue #36: 2:67 non-zero 4-integer array variant after MOWING_COMPLETED
                {
                    "id": 1087,
                    "method": "properties_changed",
                    "params": [{"did": "-1******94", "piid": 67, "siid": 2, "value": [19, 5, 0, 0]}]
                },
                "issue #36: 2:67 value [19, 5, 0, 0] after MOWING_COMPLETED (mova.mower.g2529c fw 4.3.6_0169)"
            ),
            (  # Issue #48: 2:66 2-integer array on mova.mower.g2529d
                {
                    "id": 398,
                    "method": "properties_changed",
                    "params": [{"did": "-1******76", "piid": 66, "siid": 2, "value": [97, 220]}]
                },
                "issue #48: 2:66 value [97, 220] (mova.mower.g2529d fw 4.3.6_0169)"
            ),
            (  # Issue #52: 2:53 unknown property, only value seen is 100 (mova.mower.g2405a)
                {
                    "id": 981,
                    "method": "properties_changed",
                    "params": [{"did": "-1******45", "piid": 53, "siid": 2, "value": 100}]
                },
                "issue #52: 2:53 value 100 (mova.mower.g2405a fw 4.3.6_0450)"
            ),
            (  # Issue #64: 1:54 device metadata payload on dreame.mower.g2541e
                {
                    "id": 128,
                    "method": "properties_changed",
                    "params": [{
                        "did": "-1******21",
                        "piid": 54,
                        "siid": 1,
                        "value": {
                            "active_time": "2026-03-21 00:00:00",
                            "did": "-1******21",
                            "expire_time": "2029-03-21 00:00:00",
                            "num": "89****************10",
                            "sn": "G2**************32"
                        }
                    }]
                },
                "issue #64: 1:54 device metadata payload (dreame.mower.g2541e fw 4.3.6_0337)"
            ),
            (  # Issue #82: 1:55 integer value on dreame.mower.g2541e
                {
                    "id": 1189,
                    "method": "properties_changed",
                    "params": [{
                        "did": "-1******82",
                        "piid": 55,
                        "realTime": "2026-04-05 14:39:24.648403",
                        "siid": 1,
                        "value": 1
                    }]
                },
                "issue #82: 1:55 value 1 (dreame.mower.g2541e fw 4.3.6_0407)"
            ),
            (  # Issue #78: 6:3 [bool, int] array on dreame.mower.g2541e
                {
                    "id": 107,
                    "method": "properties_changed",
                    "params": [{
                        "did": "-1******82",
                        "piid": 3,
                        "realTime": "2026-04-02 00:29:29.547574",
                        "siid": 6,
                        "value": [False, -128]
                    }]
                },
                "issue #78: 6:3 value [False, -128] (dreame.mower.g2541e fw 4.3.6_0407)"
            ),
            (  # Issue #71: 6:1 integer on dreame.mower.g2541e
                {
                    "id": 1002,
                    "method": "properties_changed",
                    "params": [{
                        "did": "-1******82",
                        "piid": 1,
                        "realTime": "2026-04-01 15:25:25.264213",
                        "siid": 6,
                        "value": 200
                    }]
                },
                "issue #71: 6:1 value 200 (dreame.mower.g2541e fw 4.3.6_0407)"
            ),
            (  # 2:65 dm::TASK_SLAM_RELOCATE (mova.mower.g2420a fw 4.3.6_0325)
                {
                    "id": 2068,
                    "method": "properties_changed",
                    "params": [{"did": "-1******61", "piid": 65, "siid": 2, "value": "dm::TASK_SLAM_RELOCATE"}]
                },
                "2:65 dm::TASK_SLAM_RELOCATE (mova.mower.g2420a fw 4.3.6_0325)"
            ),
            (  # 2:65 dm::TASK_NAV_DIVIDE_REGION (dreame.mower.g2408 fw 4.3.6_0447)
                {
                    "id": 341,
                    "method": "properties_changed",
                    "params": [{"did": "-1******95", "piid": 65, "siid": 2, "value": "dm::TASK_NAV_DIVIDE_REGION"}]
                },
                "2:65 dm::TASK_NAV_DIVIDE_REGION (dreame.mower.g2408 fw 4.3.6_0447)"
            ),
            (  # 2:65 dm::TASK_NAV_CRUISE_POINT (mova.mower.g2529b fw 4.3.6_0169)
                {
                    "id": 201,
                    "method": "properties_changed",
                    "params": [{"did": "-1******36", "piid": 65, "siid": 2, "value": "dm::TASK_NAV_CRUISE_POINT"}]
                },
                "2:65 dm::TASK_NAV_CRUISE_POINT (mova.mower.g2529b fw 4.3.6_0169)"
            ),
            (  # 2:65 dm::TASK_SLAM_RELOCATE_OFFDOCK (dreame.mower.p2255 fw 4.3.6_1542)
                {
                    "id": 206,
                    "method": "properties_changed",
                    "params": [{"did": "-1******55", "piid": 65, "siid": 2, "value": "dm::TASK_SLAM_RELOCATE_OFFDOCK"}]
                },
                "2:65 dm::TASK_SLAM_RELOCATE_OFFDOCK (dreame.mower.p2255 fw 4.3.6_1542)"
            ),
            (  # 2:65 TASK_NAV_CHECK without dm:: prefix (dreame.mower.g2541e fw 4.3.6_0407)
                {
                    "id": 651,
                    "method": "properties_changed",
                    "params": [{"did": "-1******99", "piid": 65, "siid": 2, "value": "TASK_NAV_CHECK"}]
                },
                "2:65 TASK_NAV_CHECK without dm:: prefix (dreame.mower.g2541e fw 4.3.6_0407)"
            ),
            (  # 5:100 unknown property (dreame.mower.g2568a fw 4.3.6_0212)
                {
                    "id": 122,
                    "method": "properties_changed",
                    "params": [{"did": "-1******34", "piid": 100, "siid": 5, "value": 5}]
                },
                "5:100 unknown property (dreame.mower.g2568a fw 4.3.6_0212)"
            ),
            (  # 5:100 string value with time_diff suffix (mova.mower.g2529d fw 4.3.6_0231)
                {
                    "id": 299,
                    "method": "properties_changed",
                    "params": [{"did": "-1******76", "piid": 100, "siid": 5, "value": "6 time_diff=-0.995"}]
                },
                "5:100 string value with time_diff suffix (mova.mower.g2529d fw 4.3.6_0231)"
            ),
            (  # 2:56 multi-zone status array with inactive (-1) entries (mova.mower.g2529b fw 4.3.6_0169)
                {
                    "id": 325,
                    "method": "properties_changed",
                    "params": [{"did": "-1******39", "piid": 56, "siid": 2, "value": {"status": [[1,-1],[2,0],[3,-1],[4,-1]]}}]
                },
                "2:56 multi-zone status array with inactive (-1) entries (mova.mower.g2529b fw 4.3.6_0169)"
            ),
        ],
    )
    def test_silently_acknowledged_mqtt_messages(self, device, mqtt_message, description):
        """Verify silently-acknowledged properties count as handled."""
        for param in mqtt_message["params"]:
            assert device._handle_mqtt_property_update(param) is True, f"[{description}] not handled"


class TestDreameSwbotDeviceMqtt:
    """Tests for DreameSwbotDevice MQTT message handling (dreame.swbot.* series)."""

    @pytest.fixture
    def pool_device(self):
        """Create a DreameSwbotDevice instance for testing."""
        with patch('custom_components.dreame_mower.dreame.device.DreameMowerCloudDevice'):
            device = DreameSwbotDevice(
                device_id="test_swbot",
                username="test_user",
                password="test_pass",
                account_type="mi",
                country="de",
                hass_config_dir="/tmp"
            )
            return device

    @pytest.mark.parametrize(
        "mqtt_message,description",
        [
            (  # dreame.swbot.g2509 fw 4.3.6_0603 — capability array pushed every ~60s
                {
                    "id": 494846,
                    "method": "properties_changed",
                    "params": [{"piid": 1, "siid": 1, "value": [1, 0, 0, 0, 0, 0, 0, 0, 0, 229, 188, 0, 0, 0, 0, 0, 0, 8, 91, 2]}]
                },
                "1:1 capability array (dreame.swbot.g2509)"
            ),
            (  # Battery update
                {
                    "id": 100,
                    "method": "properties_changed",
                    "params": [{"piid": 1, "siid": 3, "value": 85}]
                },
                "battery 85%"
            ),
            (  # Status update
                {
                    "id": 101,
                    "method": "properties_changed",
                    "params": [{"piid": 1, "siid": 2, "value": 13}]
                },
                "status 13"
            ),
        ],
    )
    def test_pool_robot_silently_handled(self, pool_device, mqtt_message, description):
        """Verify DreameSwbotDevice handles known messages."""
        for param in mqtt_message["params"]:
            assert pool_device._handle_mqtt_property_update(param) is True, f"[{description}] not handled"

    def test_pool_robot_battery_value(self, pool_device):
        """Verify battery value is correctly extracted from 3:1 property."""
        notifications = []
        pool_device.register_property_callback(lambda name, value: notifications.append((name, value)))

        pool_device._handle_message({
            "id": 100,
            "method": "properties_changed",
            "params": [{"piid": 1, "siid": 3, "value": 72}]
        })

        assert pool_device.battery_percent == 72
        assert ("battery_percent", 72) in notifications

    def test_pool_robot_status_value(self, pool_device):
        """Verify status value is correctly extracted from 2:1 property."""
        notifications = []
        pool_device.register_property_callback(lambda name, value: notifications.append((name, value)))

        pool_device._handle_message({
            "id": 101,
            "method": "properties_changed",
            "params": [{"piid": 1, "siid": 2, "value": 6}]
        })

        assert pool_device.status_code == 6
        assert ("status", 6) in notifications

    def test_pool_robot_1_1_decodes_charging_and_notifies(self, pool_device):
        """Verify 1:1 heartbeat decodes charging flag from byte 9 and emits status notification."""
        notifications = []
        pool_device.register_property_callback(lambda name, value: notifications.append((name, value)))

        # data[9] = 202 (0b11001010): bit7=1 → charging, bits0-6=74 → battery 74%
        pool_device._handle_message({
            "id": 494846,
            "method": "properties_changed",
            "params": [{"piid": 1, "siid": 1, "value": [1, 0, 0, 0, 0, 0, 0, 0, 0, 202, 191, 0, 0, 0, 0, 0, 0, 8, 189, 2]}]
        })

        assert pool_device._swbot_charging is True
        assert pool_device.battery_percent == 74
        assert pool_device.status == "charging"
        # Battery and status notifications emitted
        assert ("battery_percent", 74) in notifications
        assert ("status", pool_device.status_code) in notifications

    def test_pool_robot_1_1_discharging(self, pool_device):
        """Verify 1:1 with bit 7 clear → not charging, status = idle."""
        # data[9] = 74 (0b01001010): bit7=0 → not charging, bits0-6=74 → battery 74%
        pool_device._handle_message({
            "id": 1,
            "method": "properties_changed",
            "params": [{"piid": 1, "siid": 1, "value": [1, 0, 0, 0, 0, 0, 0, 0, 0, 74, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}]
        })

        assert pool_device._swbot_charging is False
        assert pool_device.status == "idle"

    def test_pool_robot_status_cleaning(self, pool_device):
        """Status code 4 means cleaning regardless of charging flag."""
        # First set charging=True via 1:1
        pool_device._handle_message({
            "id": 1,
            "method": "properties_changed",
            "params": [{"piid": 1, "siid": 1, "value": [1, 0, 0, 0, 0, 0, 0, 0, 0, 202, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}]
        })
        assert pool_device._swbot_charging is True

        # Then set status=4 via 2:1
        pool_device._handle_message({
            "id": 2,
            "method": "properties_changed",
            "params": [{"piid": 1, "siid": 2, "value": 4}]
        })

        assert pool_device.status_code == 4
        assert pool_device.status == "cleaning"

    def test_pool_robot_status_idle_when_no_charging_info(self, pool_device):
        """Status defaults to idle when no 1:1 data received yet and not cleaning."""
        # Fresh device has _swbot_charging=None and status_code=0
        assert pool_device._swbot_charging is None
        assert pool_device.status == "idle"

    def test_pool_robot_event_clean_finish(self, pool_device):
        """siid 20 / eiid 1 (CLEAN_FINISH) raises an info notification."""
        notifications = []
        pool_device.register_property_callback(lambda name, value: notifications.append((name, value)))

        pool_device._handle_message({
            "id": 200,
            "method": "event_occured",
            "params": {"siid": 20, "piid": 0, "eiid": 1, "arguments": []},
        })

        info = [v for name, v in notifications if name == "device_code_info"]
        assert len(info) == 1
        assert info[0]["code"] == "CLEAN_FINISH"

    def test_pool_robot_event_low_battery(self, pool_device):
        """siid 20 / eiid 2 (LOW_BATTERY) raises a warning notification."""
        notifications = []
        pool_device.register_property_callback(lambda name, value: notifications.append((name, value)))

        pool_device._handle_message({
            "id": 201,
            "method": "event_occured",
            "params": {"siid": 20, "piid": 0, "eiid": 2, "arguments": []},
        })

        warnings = [v for name, v in notifications if name == "device_code_warning"]
        assert len(warnings) == 1
        assert warnings[0]["code"] == "LOW_BATTERY"

    def test_pool_robot_event_string_siid_eiid(self, pool_device):
        """Event ids arriving as strings are coerced and still handled (defensive)."""
        notifications = []
        pool_device.register_property_callback(lambda name, value: notifications.append((name, value)))

        pool_device._handle_message({
            "id": 202,
            "method": "event_occured",
            "params": {"siid": "20", "piid": "0", "eiid": "1"},
        })

        assert any(name == "device_code_info" for name, _ in notifications)

    def test_pool_robot_status_cleaning_raises_started(self, pool_device):
        """A status transition into cleaning (4) derives a 'started' info notification."""
        notifications = []
        pool_device.register_property_callback(lambda name, value: notifications.append((name, value)))

        pool_device._handle_message({
            "id": 400,
            "method": "properties_changed",
            "params": [{"piid": 1, "siid": 2, "value": 4}],
        })

        info = [v for name, v in notifications if name == "device_code_info"]
        assert len(info) == 1
        assert info[0]["code"] == "CLEAN_START"

    def test_pool_robot_started_not_repeated_while_cleaning(self, pool_device):
        """The 'started' notification only fires on entry to cleaning, not on later cleaning updates."""
        notifications = []
        pool_device.register_property_callback(lambda name, value: notifications.append((name, value)))

        cleaning = {
            "id": 401,
            "method": "properties_changed",
            "params": [{"piid": 1, "siid": 2, "value": 4}],
        }
        idle = {
            "id": 402,
            "method": "properties_changed",
            "params": [{"piid": 1, "siid": 2, "value": 1}],
        }
        pool_device._handle_message(cleaning)
        pool_device._handle_message(cleaning)  # repeated, no transition
        pool_device._handle_message(idle)
        pool_device._handle_message(cleaning)  # re-entry, fires again

        starts = [v for name, v in notifications if name == "device_code_info" and v["code"] == "CLEAN_START"]
        assert len(starts) == 2
