"""Tests for the station, the recognised obstacles and the session trail the device keeps."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

from custom_components.dreame_mower.dreame.device import DreameMowerDevice
from custom_components.dreame_mower.dreame.map_data_parser import MowerVectorMap
from custom_components.dreame_mower.dreame.property.property_misc import PROPERTY_1_1_TASK_STATUS_NAME

DEVICE_ID = "-100000001"
_TWO_MAPS = json.loads(
    (Path(__file__).parent / "fixtures" / "batch_map_two_maps.json").read_text()
)


def _device(config_dir: Path) -> DreameMowerDevice:
    with patch("custom_components.dreame_mower.dreame.device.DreameMowerCloudDevice"):
        return DreameMowerDevice(
            device_id=DEVICE_ID,
            username="user",
            password="password",
            account_type="dreame",
            country="DE",
            hass_config_dir=str(config_dir),
        )


def _answer(device: DreameMowerDevice, data: dict | list) -> Mock:
    action = Mock(return_value={"code": 0, "out": [{"d": data, "m": "r", "q": 1, "r": 0}]})
    device._cloud_device.action = action
    return action


def test_station_position_and_heading_come_from_the_mower(tmp_path):
    device = _device(tmp_path)
    changes = Mock()
    device.register_property_callback(changes)
    action = _answer(device, {"dock": {"connect_status": 1, "x": 125, "y": -6, "yaw": 3580}})

    assert device.refresh_dock_position() is True

    assert action.call_args.args[2] == [{"m": "g", "t": "DOCK"}]
    assert device.dock_position == (1250, -60)
    assert device.dock_angle == 358.0
    changes.assert_any_call("dock_position", (1250, -60))
    # Reading the same position again changes nothing.
    assert device.refresh_dock_position() is False


def test_station_unknown_when_the_mower_does_not_say(tmp_path):
    device = _device(tmp_path)
    _answer(device, {})

    assert device.refresh_dock_position() is False
    assert device.dock_position is None


def _answers(device: DreameMowerDevice, by_key: dict) -> Mock:
    def action(siid, aiid, params, *args, **kwargs):
        data = by_key.get(params[0]["t"])
        if data is None:
            return {"code": 0, "out": [{"m": "r", "q": 1, "r": -3}]}
        return {"code": 0, "out": [{"d": data, "m": "r", "q": 1, "r": 0}]}

    mock = Mock(side_effect=action)
    device._cloud_device.action = mock
    return mock


def test_obstacles_of_the_active_map_both_kinds(tmp_path):
    device = _device(tmp_path)
    changes = Mock()
    device.register_property_callback(changes)
    action = _answers(
        device,
        {
            "OBS": {"idx": 0, "obstacle": [{"data": [[-692, -492], [-712, -482], [-707, -462], [-682, -467]], "id": 1, "type": 0}]},
            "AIOBS": {"idx": 0, "obs": [[[100, 200, 200, 100], [0, 0, 100, 100], 0.9, 99, "img", 0, 7]]},
        },
    )

    assert device.refresh_obstacles() is True

    sent = [call.args[2][0] for call in action.call_args_list]
    assert sent == [{"m": "g", "t": "OBS", "d": {"idx": 0}}, {"m": "g", "t": "AIOBS", "d": {"idx": 0}}]
    assert device.obstacles == [
        {"id": 1, "type": 0, "x": -6982, "y": -4758, "polygon": [-6920, -4920, -7120, -4820, -7070, -4620, -6820, -4670]}
    ]
    assert device.ai_obstacles == [
        {"id": 7, "type": 99, "x": 150, "y": 50, "confidence": 90, "image": "img", "bounds": [100, 0, 200, 100], "ignorable": True}
    ]
    assert any(call.args[0] == "obstacles" for call in changes.call_args_list)
    # The same answers again change nothing.
    assert device.refresh_obstacles() is False


def test_failed_obstacle_read_keeps_the_known_ones(tmp_path):
    device = _device(tmp_path)
    _answers(device, {"OBS": {"idx": 0, "obstacle": [{"data": [[1, 2]], "id": 4, "type": 0}]}, "AIOBS": {"idx": 0, "obs": []}})
    device.refresh_obstacles()
    _answers(device, {})

    assert device.refresh_obstacles() is False
    assert device.obstacles == [{"id": 4, "type": 0, "x": 10, "y": 20, "polygon": [10, 20]}]


def test_docked_by_charging_state_or_else_by_status(tmp_path):
    device = _device(tmp_path)
    device._charging_status = None
    device._status_code = 13  # charging complete
    assert device.docked is True
    device._status_code = 1  # mowing
    assert device.docked is False
    device._charging_status = "charging"
    assert device.docked is True
    device._charging_status = "charging_paused_high_temperature"
    assert device.docked is True
    device._charging_status = "not_docked"
    assert device.docked is False
    # "Not charging" comes on and off the station alike; the status decides.
    device._charging_status = "not_charging"
    device._status_code = 1  # mowing
    assert device.docked is False
    device._status_code = 13  # charging complete
    assert device.docked is True


# --- The trail starts afresh with every session ---


def _session(device: DreameMowerDevice, active: bool) -> None:
    with patch.object(type(device), "mowing_session_active", new_callable=PropertyMock, return_value=active):
        device._notify_property_change(PROPERTY_1_1_TASK_STATUS_NAME, "running" if active else "idle")


def _trail(device: DreameMowerDevice, points: list[list[int]]) -> None:
    device._pose_coverage_handler._apply_track(0, points)


def test_session_start_clears_the_last_trail(tmp_path):
    device = _device(tmp_path)
    _session(device, False)
    # A short session that ended at point 9; the next one restarts at 0 with
    # padding, which must not leave the old points 1..9 behind.
    _trail(device, [[i, i] for i in range(10)])

    _session(device, True)
    _trail(device, [[100, 100], [2147483647, 2147483647]])

    assert device.mowing_path_history == [[100, 100]]


def test_first_task_status_keeps_the_trail_of_a_running_session(tmp_path):
    device = _device(tmp_path)
    _trail(device, [[1, 1], [2, 2]])

    _session(device, True)

    assert device.mowing_path_history == [[1, 1], [2, 2]]


def test_session_end_keeps_its_trail(tmp_path):
    device = _device(tmp_path)
    _session(device, True)
    _trail(device, [[1, 1], [2, 2]])

    _session(device, False)

    assert device.mowing_path_history == [[1, 1], [2, 2]]


# --- A mower the cloud reports offline ---


def test_device_list_says_whether_the_mower_is_online(tmp_path):
    device = _device(tmp_path)

    device._update_device_state_from_info({"online": False})
    assert device.online is False

    device._update_device_state_from_info({"online": True})
    assert device.online is True


def test_offline_mower_maps_come_from_the_stored_copy(tmp_path):
    device = _device(tmp_path)
    device._update_device_state_from_info({"online": False})
    device._cloud_device.get_batch_device_datas = Mock(return_value={})
    device._cloud_device.action = Mock()

    device._cloud_device.get_batch_device_datas = Mock(return_value=_TWO_MAPS)
    assert device.fetch_vector_map() is True

    # Neither the maps nor which of them is current are asked of the mower.
    device._cloud_device.action.assert_not_called()
    device._cloud_device.get_batch_device_datas.assert_called_once()


async def test_online_poll_skips_the_heartbeat_of_a_listed_offline_mower(tmp_path):
    device = _device(tmp_path)
    device._cloud_device.get_device_info = Mock(return_value={"online": False})
    device._cloud_device.get_properties = Mock()

    assert await device.async_update_online_status() is False

    device._cloud_device.get_properties.assert_not_called()


async def test_online_poll_reads_the_heartbeat_of_a_listed_online_mower(tmp_path):
    device = _device(tmp_path)
    device._cloud_device.get_device_info = Mock(return_value={"online": True})
    heartbeat = [0] * 17 + [1, 0]
    device._cloud_device.get_properties = Mock(return_value=[{"code": 0, "value": heartbeat}])

    assert await device.async_update_online_status() is True

    device._cloud_device.get_properties.assert_called_once()


async def test_reachability_check_of_an_answering_mower(tmp_path):
    device = _device(tmp_path)
    device._cloud_device.get_properties = Mock(return_value=[{"code": 0, "value": [0] * 17 + [1, 0]}])

    assert await device.async_check_reachable() is True
    assert device.online is True


async def test_listed_mower_that_does_not_answer_is_offline(tmp_path):
    device = _device(tmp_path)
    device._cloud_device.get_properties = Mock(side_effect=TimeoutError)

    assert await device.async_check_reachable() is False
    assert device.online is False
    device._cloud_device.get_properties.assert_called_once()


async def test_reachability_check_does_not_ask_an_offline_mower(tmp_path):
    device = _device(tmp_path)
    device._update_device_state_from_info({"online": False})
    device._cloud_device.get_properties = Mock()

    assert await device.async_check_reachable() is False
    device._cloud_device.get_properties.assert_not_called()


async def test_heartbeat_saying_offline_marks_the_mower_offline(tmp_path):
    device = _device(tmp_path)
    changes = Mock()
    device.register_property_callback(changes)
    device._cloud_device.get_properties = Mock(return_value=[{"code": 0, "value": [0] * 19}])

    assert await device.async_check_reachable() is False
    assert device.online is False
    changes.assert_any_call("online", False)


def test_map_poll_does_not_ask_an_offline_mower(tmp_path):
    device = _device(tmp_path)
    device._update_device_state_from_info({"online": False})
    device._cloud_device.action = Mock()

    assert device.refresh_changed_vector_map() is False
    device._cloud_device.action.assert_not_called()


# --- The session's trail read back from the mower ---


def _track(points: list[tuple[int, int]]) -> str:
    import base64

    raw = bytearray()
    for x, y in points:
        x &= 0xFFFFF
        y &= 0xFFFFF
        raw += bytes([x & 0xFF, (x >> 8) & 0xFF, ((x >> 16) & 0x0F) | ((y & 0x0F) << 4), (y >> 4) & 0xFF, (y >> 12) & 0xFF])
    return base64.b64encode(bytes(raw)).decode()


def test_trail_is_read_back_page_by_page(tmp_path):
    device = _device(tmp_path)
    first = [(i, -i) for i in range(60)]
    second = [(100, 200), (32767, -32768), (300, -400)]
    pages = {0: _track(first), 60: _track(second)}

    def action(siid, aiid, params, *args, **kwargs):
        start = params[0]["d"]["idx"]
        assert params[0]["t"] == "MITRC" and params[0]["d"]["size"] == 60
        return {"code": 0, "out": [{"d": {"idx": start, "track": pages.get(start, "")}, "m": "r", "q": 1, "r": 0}]}

    device._cloud_device.action = Mock(side_effect=action)
    changes = Mock()
    device.register_property_callback(changes)

    assert device.refresh_trail() is True

    history = device.mowing_path_history
    assert len(history) == 63
    assert history[1] == [10, -10]
    assert history[60:] == [[1000, 2000], [2147483647, 2147483647], [3000, -4000]]
    # The short second page ends the read.
    assert device._cloud_device.action.call_count == 2
    assert any(call.args[0] == "trail" for call in changes.call_args_list)


def test_trail_read_without_a_session_changes_nothing(tmp_path):
    device = _device(tmp_path)
    device._cloud_device.action = Mock(return_value={"code": 0, "out": [{"d": {"idx": 0, "track": ""}, "m": "r", "r": 0}]})

    assert device.refresh_trail() is False
    assert device.mowing_path_history == []


# --- Where an unfinished task left off ---


def test_stop_points_of_the_active_map(tmp_path):
    device = _device(tmp_path)
    changes = Mock()
    device.register_property_callback(changes)
    action = _answer(device, [{"bp_ts": "2026.10.12", "bp_ts_utc": 1791842400, "pro": 3021, "rg_id": 1}, {"pro": 5}])

    assert device.refresh_stop_points() is True

    assert action.call_args.args[2] == [{"m": "g", "t": "RGBPSTA", "d": {"idx": 0}}]
    # An entry without a zone is left out.
    assert device.stop_points == [{"zone_id": 1, "progress": 30.21, "date": "2026.10.12", "day_end": 1791842400}]
    changes.assert_any_call("stop_points", device.stop_points)
    assert device.refresh_stop_points() is False


def test_no_stop_points_once_a_task_finished(tmp_path):
    device = _device(tmp_path)
    _answer(device, [{"bp_ts": "2026.10.12", "pro": 3021, "rg_id": 1}])
    device.refresh_stop_points()
    # Without the end of its day a stop point still counts.
    assert device.stop_points[0]["day_end"] is None
    _answer(device, [])

    assert device.refresh_stop_points() is True
    assert device.stop_points == []


def test_complete_trail_is_not_read_again(tmp_path):
    device = _device(tmp_path)
    device._pose_coverage_handler.merge_trail(0, [(1, 1), (2, 2)])
    device._cloud_device.action = Mock()

    assert device.refresh_trail() is False
    device._cloud_device.action.assert_not_called()


def test_trail_read_starts_at_the_first_gap(tmp_path):
    device = _device(tmp_path)
    device._pose_coverage_handler.merge_trail(0, [(1, 1), (2, 2)])
    device._pose_coverage_handler.merge_trail(5, [(6, 6)])
    device._cloud_device.action = Mock(
        return_value={"code": 0, "out": [{"d": {"idx": 2, "track": _track([(3, 3), (4, 4), (5, 5)])}, "m": "r", "r": 0}]}
    )

    assert device.refresh_trail() is True

    assert device._cloud_device.action.call_args.args[2][0]["d"] == {"idx": 2, "size": 60}
    assert device.mowing_path_history[2:5] == [[30, 30], [40, 40], [50, 50]]


def test_broken_trail_page_ends_the_read(tmp_path):
    device = _device(tmp_path)
    device._cloud_device.action = Mock(
        return_value={"code": 0, "out": [{"d": {"idx": 0, "track": "AAAA"}, "m": "r", "r": 0}]}
    )

    assert device.refresh_trail() is False
    device._cloud_device.action.assert_called_once()


def test_standing_mower_is_placed_by_asking_it(tmp_path):
    device = _device(tmp_path)
    action = _answer(device, {"x": -12, "y": 106, "yaw": 193})

    assert device.refresh_mower_position() is True

    assert action.call_args.args[2] == [{"m": "g", "t": "MPOS"}]
    assert device.mower_coordinates == (-120, 1060)
    assert round(device.mower_heading) == 272
    assert device.refresh_mower_position() is False


def test_mower_without_a_position_keeps_the_known_one(tmp_path):
    device = _device(tmp_path)
    _answer(device, {"x": -12, "y": 106, "yaw": 193})
    device.refresh_mower_position()
    _answer(device, {"x": 0, "y": 0, "yaw": 0})

    assert device.refresh_mower_position() is False
    assert device.mower_coordinates == (-120, 1060)


def test_mower_in_a_session_is_not_asked_for_its_position(tmp_path):
    device = _device(tmp_path)
    device._cloud_device.action = Mock()
    with patch.object(type(device), "mowing_session_active", new_callable=PropertyMock, return_value=True):
        assert device.refresh_mower_position() is False

    device._cloud_device.action.assert_not_called()


def test_stored_maps_are_taken_without_asking_the_mower(tmp_path):
    device = _device(tmp_path)
    device._cloud_device.get_batch_device_datas = Mock(return_value=_TWO_MAPS)
    device._cloud_device.action = Mock()

    assert device.load_stored_vector_map() is True

    assert device.vector_map is not None
    device._cloud_device.action.assert_not_called()


def test_stored_maps_never_replace_maps_read_from_the_mower(tmp_path):
    device = _device(tmp_path)
    first = MowerVectorMap(map_id=1, name="Read from the mower")
    device._vector_map = first
    device._cloud_device.get_batch_device_datas = Mock(return_value=_TWO_MAPS)

    assert device.load_stored_vector_map() is False
    assert device._vector_map is first
