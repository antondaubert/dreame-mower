"""Tests for DreameMowerLawnMower entity."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.components.lawn_mower import LawnMowerActivity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from custom_components.dreame_mower.const import DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.dreame.device import DreameCommandError, MowingMode
from custom_components.dreame_mower.lawn_mower import DreameMowerLawnMower, async_setup_entry
from custom_components.dreame_mower.dreame.const import (
    STATUS_PROPERTY,
    DeviceStatus,
    MowingPreferenceMode,
)


def _make_coordinator(connected=True, status_code=0):
    coordinator = MagicMock()
    coordinator.device_mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device_name = "Test Mower"
    coordinator.device_model = "dreame.mower.test"
    coordinator.device_serial = "SN123"
    coordinator.device_manufacturer = "Dreametech™"
    coordinator.device_firmware = "1.0.0"
    coordinator.device_connected = connected
    coordinator.device_status_code = status_code
    coordinator.device = MagicMock()
    coordinator.device.register_property_callback = MagicMock()
    coordinator.device.start_mowing = AsyncMock(return_value=True)
    coordinator.device.pause = AsyncMock(return_value=True)
    coordinator.device.return_to_dock = AsyncMock(return_value=True)
    coordinator.zones = []
    coordinator.contours = []
    coordinator.available_maps = []
    coordinator.device.start_mowing_zones = AsyncMock(return_value=True)
    coordinator.device.start_mowing_edges = AsyncMock(return_value=True)
    coordinator.device.start_mowing_spots = AsyncMock(return_value=True)
    coordinator.device.start_mowing_generic = AsyncMock(return_value=True)
    coordinator.device.mowing_session_active = False
    coordinator.supports_cutting_height = True
    coordinator.async_set_mowing_preference_mode = AsyncMock(return_value=True)
    coordinator.async_set_mowing_settings = AsyncMock(return_value=True)
    return coordinator


def _make_entity(coordinator=None):
    """Bypass DreameMowerLawnMower.__init__ to avoid device registration side-effects."""
    if coordinator is None:
        coordinator = _make_coordinator()
    entity = DreameMowerLawnMower.__new__(DreameMowerLawnMower)
    entity.coordinator = coordinator
    entity._entity_description_key = "lawn_mower"
    entity._attr_has_entity_name = True
    entity._attr_activity = LawnMowerActivity.DOCKED
    entity.hass = MagicMock()
    return entity


def test_activity_returns_none_when_unavailable():
    entity = _make_entity(_make_coordinator(connected=False))
    assert entity.activity is None


def test_activity_returns_current_when_available():
    entity = _make_entity(_make_coordinator(connected=True))
    entity._attr_activity = LawnMowerActivity.MOWING
    assert entity.activity == LawnMowerActivity.MOWING


def test_on_property_change_ignores_non_status_property():
    entity = _make_entity()
    entity.schedule_update_ha_state = MagicMock()
    entity._attr_activity = LawnMowerActivity.DOCKED

    entity._on_property_change("some_other_property", 1)

    assert entity._attr_activity == LawnMowerActivity.DOCKED
    entity.schedule_update_ha_state.assert_not_called()


def test_on_property_change_updates_activity_to_mowing():
    entity = _make_entity()
    entity.schedule_update_ha_state = MagicMock()

    entity._on_property_change(STATUS_PROPERTY.name, DeviceStatus.MOWING)

    assert entity._attr_activity == LawnMowerActivity.MOWING
    entity.schedule_update_ha_state.assert_called_once()


def test_on_property_change_does_not_schedule_update_when_activity_unchanged():
    entity = _make_entity()
    entity._attr_activity = LawnMowerActivity.DOCKED
    entity.schedule_update_ha_state = MagicMock()

    # CHARGING also maps to DOCKED, so activity won't change
    entity._on_property_change(STATUS_PROPERTY.name, DeviceStatus.CHARGING)

    entity.schedule_update_ha_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_start_mowing_without_a_task_mows_the_whole_map():
    entity = _make_entity()
    await entity.async_start_mowing()
    entity.coordinator.device.start_mowing.assert_awaited_once_with(mode=MowingMode.ALL_AREA)
    entity.coordinator.device.resume.assert_not_called()


@pytest.mark.asyncio
async def test_async_start_zone_mowing_calls_device_zone_start():
    entity = _make_entity()

    await entity.async_start_zone_mowing([1, 3])

    entity.coordinator.device.start_mowing_zones.assert_awaited_once_with([1, 3], from_stop_point=None)


@pytest.mark.asyncio
async def test_async_start_edge_mowing_calls_device_edge_start():
    entity = _make_entity()

    await entity.async_start_edge_mowing([[1, 0], [2, 0]])

    entity.coordinator.device.start_mowing_edges.assert_awaited_once_with([[1, 0], [2, 0]])


@pytest.mark.asyncio
async def test_async_start_edge_mowing_raises_on_failure():
    coordinator = _make_coordinator()
    coordinator.device.start_mowing_edges = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_start_edge_mowing([[1, 0]])


@pytest.mark.asyncio
async def test_async_start_spot_mowing_calls_device_spot_start():
    entity = _make_entity()

    await entity.async_start_spot_mowing([4, 5])

    entity.coordinator.device.start_mowing_spots.assert_awaited_once_with([4, 5])


@pytest.mark.asyncio
async def test_async_start_mowing_resumes_when_session_active():
    coordinator = _make_coordinator()
    coordinator.device.resume = AsyncMock(return_value=True)
    coordinator.device.mowing_session_active = True
    entity = _make_entity(coordinator)
    entity._attr_activity = LawnMowerActivity.PAUSED

    await entity.async_start_mowing()

    coordinator.device.resume.assert_awaited_once()
    coordinator.device.start_mowing.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_start_mowing_starts_fresh_when_not_paused():
    coordinator = _make_coordinator()
    coordinator.device.resume = AsyncMock(return_value=True)
    entity = _make_entity(coordinator)
    entity._attr_activity = LawnMowerActivity.DOCKED

    await entity.async_start_mowing()

    coordinator.device.start_mowing.assert_awaited_once_with(mode=MowingMode.ALL_AREA)
    coordinator.device.resume.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_start_mowing_resumes_when_docked_with_active_session():
    """When docked but a mowing session is still active (paused at dock), resume."""
    coordinator = _make_coordinator()
    coordinator.device.resume = AsyncMock(return_value=True)
    coordinator.device.mowing_session_active = True
    entity = _make_entity(coordinator)
    entity._attr_activity = LawnMowerActivity.DOCKED  # robot returned to dock after pause

    await entity.async_start_mowing()

    coordinator.device.resume.assert_awaited_once()
    coordinator.device.start_mowing.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_area_start_failure_falls_back_to_generic():
    """When the map-aware all-area start returns False, fall back to generic."""
    coordinator = _make_coordinator()
    coordinator.device.start_mowing = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)
    entity._attr_activity = LawnMowerActivity.DOCKED

    await entity.async_start_mowing()

    coordinator.device.start_mowing_generic.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_all_area_start_command_error_falls_back_to_generic():
    """When the map-aware all-area start never reaches the mower, fall back to generic."""
    coordinator = _make_coordinator()
    coordinator.device.start_mowing = AsyncMock(side_effect=DreameCommandError("offline"))
    entity = _make_entity(coordinator)
    entity._attr_activity = LawnMowerActivity.DOCKED

    await entity.async_start_mowing()

    coordinator.device.start_mowing_generic.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_pause_calls_device():
    entity = _make_entity()
    await entity.async_pause()
    entity.coordinator.device.pause.assert_called_once()


@pytest.mark.asyncio
async def test_async_dock_calls_device():
    entity = _make_entity()
    await entity.async_dock()
    entity.coordinator.device.return_to_dock.assert_called_once()


def test_extra_state_attributes_include_zones_contours_maps_and_the_active_map():
    coordinator = _make_coordinator()
    coordinator.zones = [{"id": 1, "name": "Front", "area": 12.5}]
    coordinator.contours = [[1, 0], [2, 0]]
    coordinator.available_maps = [{"id": 1, "index": 0, "name": "Front", "area": 12.5}]
    coordinator.current_map_id = 1
    entity = _make_entity(coordinator)

    assert entity.extra_state_attributes == {
        "zones": [{"id": 1, "name": "Front", "area": 12.5}],
        "contours": [[1, 0], [2, 0]],
        "maps": [{"id": 1, "index": 0, "name": "Front", "area": 12.5}],
        "current_map_id": 1,
    }


@pytest.mark.asyncio
async def test_set_mowing_preference_mode_service_maps_the_name_to_the_mode():
    """The service takes a readable mode name and forwards the enum."""
    coordinator = _make_coordinator()
    entity = _make_entity(coordinator)

    await entity.async_set_mowing_preference_mode("map_wide", map_id=2)

    coordinator.async_set_mowing_preference_mode.assert_awaited_once_with(
        MowingPreferenceMode.MAP_WIDE, 2
    )


@pytest.mark.asyncio
async def test_set_mowing_preference_mode_service_rejects_fixed_height_models():
    """Models without adjustable settings should report a clear error."""
    coordinator = _make_coordinator()
    coordinator.supports_cutting_height = False
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_set_mowing_preference_mode("per_zone")

    coordinator.async_set_mowing_preference_mode.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_mowing_preference_mode_service_raises_when_the_switch_fails():
    """A rejected mode switch should surface as an error."""
    coordinator = _make_coordinator()
    coordinator.async_set_mowing_preference_mode = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_set_mowing_preference_mode("per_zone")


async def _registered_services(hass):
    """Run platform setup and report the entity services it registered."""
    registrations: list[tuple[str, Any]] = []
    platform = MagicMock()
    platform.async_register_entity_service = lambda name, schema, method, **options: registrations.append(
        (name, schema)
    )

    entry = MagicMock()
    entry.entry_id = "entry_id"
    hass.data = {DOMAIN: {"entry_id": {DATA_COORDINATOR: _make_coordinator()}}}

    with patch(
        "custom_components.dreame_mower.lawn_mower.entity_platform.async_get_current_platform",
        return_value=platform,
    ), patch.object(DreameMowerLawnMower, "__init__", return_value=None):
        await async_setup_entry(hass, entry, MagicMock())

    return registrations


@pytest.mark.asyncio
async def test_every_service_registers_with_an_entity_service_schema(hass):
    """Home Assistant refuses a schema it cannot recognise as an entity one."""
    registrations = await _registered_services(hass)

    assert registrations
    for name, schema in registrations:
        # A plain dict is wrapped by Home Assistant itself; anything else has to
        # be built around cv.make_entity_service_schema to be accepted.
        assert isinstance(schema, dict) or cv.is_entity_service_schema(schema), name


def test_lawn_mower_does_not_register_callback_on_init():
    """Constructing the entity must not subscribe to device updates."""
    coordinator = _make_coordinator()
    DreameMowerLawnMower(coordinator)
    coordinator.device.register_property_callback.assert_not_called()


@pytest.mark.asyncio
async def test_lawn_mower_registers_on_add_and_unregisters_on_remove():
    """Being added subscribes to device updates; being removed unsubscribes."""
    coordinator = _make_coordinator()
    entity = DreameMowerLawnMower(coordinator)
    entity.hass = MagicMock()

    await entity.async_added_to_hass()

    coordinator.device.register_property_callback.assert_called_once_with(
        entity._on_property_change
    )

    # Home Assistant runs these when the entity is removed.
    entity._call_on_remove_callbacks()

    coordinator.device.unregister_property_callback.assert_called_once_with(
        entity._on_property_change
    )


@pytest.mark.asyncio
async def test_select_map_switches_the_mower_map():
    coordinator = _make_coordinator()
    coordinator.available_maps = [{"id": 1, "name": "Front"}, {"id": 2, "name": "Back"}]
    coordinator.device.set_current_map = AsyncMock(return_value=True)
    entity = _make_entity(coordinator)

    await entity.async_select_map(2)

    coordinator.device.set_current_map.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_select_map_rejects_an_unknown_map():
    coordinator = _make_coordinator()
    coordinator.available_maps = [{"id": 1, "name": "Front"}]
    coordinator.device.set_current_map = AsyncMock(return_value=True)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="no map with ID 5"):
        await entity.async_select_map(5)

    coordinator.device.set_current_map.assert_not_awaited()


@pytest.mark.asyncio
async def test_select_map_explains_a_refusal_during_a_task():
    coordinator = _make_coordinator()
    coordinator.available_maps = [{"id": 1, "name": "Front"}, {"id": 2, "name": "Back"}]
    coordinator.device.set_current_map = AsyncMock(return_value=False)
    coordinator.device.mowing_session_active = True
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="mowing task is in progress"):
        await entity.async_select_map(2)


@pytest.mark.asyncio
async def test_select_map_reports_a_failed_switch():
    coordinator = _make_coordinator()
    coordinator.available_maps = [{"id": 1, "name": "Front"}, {"id": 2, "name": "Back"}]
    coordinator.device.set_current_map = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="Failed to switch to map 2"):
        await entity.async_select_map(2)


@pytest.mark.asyncio
async def test_start_all_area_mowing_continues_a_running_session():
    coordinator = _make_coordinator()
    coordinator.device.resume = AsyncMock(return_value=True)
    coordinator.device.mowing_session_active = True
    entity = _make_entity(coordinator)

    await entity.async_start_all_area_mowing()

    coordinator.device.resume.assert_awaited_once()
    coordinator.device.start_mowing.assert_not_awaited()


@pytest.mark.asyncio
async def test_recharge_keeps_the_running_task():
    coordinator = _make_coordinator()
    coordinator.device.dock_without_stopping = AsyncMock(return_value=True)
    entity = _make_entity(coordinator)

    await entity.async_recharge()

    coordinator.device.dock_without_stopping.assert_awaited_once_with()
    coordinator.device.return_to_dock.assert_not_awaited()


@pytest.mark.asyncio
async def test_recharge_reports_a_failure():
    coordinator = _make_coordinator()
    coordinator.device.dock_without_stopping = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="station"):
        await entity.async_recharge()


@pytest.mark.asyncio
async def test_end_task_stops_without_docking():
    coordinator = _make_coordinator()
    coordinator.device.end_task = AsyncMock(return_value=True)
    entity = _make_entity(coordinator)

    await entity.async_end_task()

    coordinator.device.end_task.assert_awaited_once_with()
    coordinator.device.return_to_dock.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_returning_reports_a_failure():
    coordinator = _make_coordinator()
    coordinator.device.stop_returning = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="return"):
        await entity.async_stop_returning()


@pytest.mark.asyncio
async def test_end_task_reports_a_failure():
    coordinator = _make_coordinator()
    coordinator.device.end_task = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="end the mowing task"):
        await entity.async_end_task()


@pytest.mark.asyncio
async def test_set_mowing_settings_service_forwards_the_settings_by_their_keys():
    """The action's fields reach the coordinator as the settings they name."""
    coordinator = _make_coordinator()
    entity = _make_entity(coordinator)

    await entity.async_set_mowing_settings(
        automatic_edge_mowing=False,
        obstacle_height=10,
        ai_obstacle_recognition=["humans"],
        zone_id=3,
    )

    coordinator.async_set_mowing_settings.assert_awaited_once_with(
        {"edge_mowing_auto": False, "obstacle_height": 10, "ai_obstacle_recognition": ["humans"]},
        map_id=None,
        zone_id=3,
    )


@pytest.mark.asyncio
async def test_set_mowing_settings_service_names_the_zone_when_it_fails():
    coordinator = _make_coordinator()
    coordinator.async_set_mowing_settings = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="zone 3"):
        await entity.async_set_mowing_settings(efficiency="standard", zone_id=3)


@pytest.mark.asyncio
async def test_a_drawn_no_go_zone_answers_with_its_id_and_redraws_the_map():
    coordinator = _make_coordinator()
    coordinator.device.set_no_go_zone = AsyncMock(return_value=101)
    coordinator.async_update_listeners = MagicMock()
    entity = _make_entity(coordinator)

    result = await entity.async_set_no_go_zone("rectangle", [[0, 0], [100, 100]])

    assert result == {"id": 101}
    coordinator.device.set_no_go_zone.assert_awaited_once_with("rectangle", [[0, 0], [100, 100]], None, None)
    coordinator.async_update_listeners.assert_called_once()


@pytest.mark.asyncio
async def test_a_map_change_the_mower_refuses_says_why():
    coordinator = _make_coordinator()
    coordinator.device.set_spot_area = AsyncMock(side_effect=ValueError("The spot area must stay within one zone"))
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="within one zone"):
        await entity.async_set_spot_area([0, 0, 100, 100])


@pytest.mark.asyncio
async def test_the_map_edit_services_check_their_shapes(hass):
    services = dict(await _registered_services(hass))
    no_go = vol.Schema(services["set_no_go_zone"])
    spot = vol.Schema(services["set_spot_area"])
    merge = vol.Schema(services["merge_zones"])

    assert no_go({"shape": "rectangle", "points": [["1", 2], [3, 4]]})["points"] == [[1.0, 2.0], [3.0, 4.0]]
    assert spot({"rect": [0, 0, 1, 1]})["rect"] == [0.0, 0.0, 1.0, 1.0]
    for schema, invalid in (
        (no_go, {"shape": "star", "points": [[0, 0]]}),
        (no_go, {"shape": "line", "points": [[0, 0, 1]]}),
        (spot, {"rect": [0, 0, 1]}),
        (merge, {"zone_ids": [1, 2, 3]}),
    ):
        with pytest.raises(vol.Invalid):
            schema(invalid)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session,docking,resumed,docked",
    [(True, "out_of_station", True, False), (False, "out_of_station", False, True), (False, "in_station", False, False)],
)
async def test_clearing_an_error_lets_the_mower_go_on(session, docking, resumed, docked):
    coordinator = _make_coordinator()
    device = coordinator.device
    device.clear_errors = AsyncMock(return_value=True)
    device.resume = AsyncMock(return_value=True)
    device.return_to_dock = AsyncMock(return_value=True)
    device.mowing_session_active = session
    device.robot_state = {"docking": docking}
    coordinator.async_update_listeners = MagicMock()
    entity = _make_entity(coordinator)

    await entity.async_clear_error()

    device.clear_errors.assert_awaited_once()
    assert device.resume.await_count == int(resumed)
    assert device.return_to_dock.await_count == int(docked)


@pytest.mark.asyncio
async def test_clearing_only_leaves_the_mower_where_it_is():
    coordinator = _make_coordinator()
    device = coordinator.device
    device.clear_errors = AsyncMock(return_value=True)
    device.resume = AsyncMock(return_value=True)
    device.mowing_session_active = True
    coordinator.async_update_listeners = MagicMock()

    await _make_entity(coordinator).async_clear_error(continue_task=False)

    device.resume.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("cleared,resumed", [(False, True), (True, False)])
async def test_an_error_the_mower_keeps_or_a_task_it_does_not_resume_is_reported(cleared, resumed):
    coordinator = _make_coordinator()
    device = coordinator.device
    device.clear_errors = AsyncMock(return_value=cleared)
    device.resume = AsyncMock(return_value=resumed)
    device.mowing_session_active = True
    coordinator.async_update_listeners = MagicMock()

    with pytest.raises(HomeAssistantError):
        await _make_entity(coordinator).async_clear_error()
    assert device.resume.await_count == int(cleared)


@pytest.mark.asyncio
@pytest.mark.parametrize("cleared", [True, False])
async def test_rain_protection_is_cleared_for_the_next_task(cleared):
    coordinator = _make_coordinator()
    coordinator.device.suppress_code = AsyncMock(return_value=cleared)
    coordinator.async_update_listeners = MagicMock()
    entity = _make_entity(coordinator)

    if cleared:
        await entity.async_clear_rain_protection()
    else:
        with pytest.raises(HomeAssistantError):
            await entity.async_clear_rain_protection()
    coordinator.device.suppress_code.assert_awaited_once_with(56)


@pytest.mark.asyncio
async def test_an_obstacle_the_mower_refuses_to_ignore_is_reported():
    coordinator = _make_coordinator()
    coordinator.device.ignore_ai_obstacle = AsyncMock(side_effect=ValueError("The mower does not know this obstacle (any more)"))
    coordinator.async_update_listeners = MagicMock()

    with pytest.raises(HomeAssistantError, match="does not know"):
        await _make_entity(coordinator).async_ignore_obstacle(5)
    coordinator.device.ignore_ai_obstacle.assert_awaited_once_with(5)


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", [None, 3])
async def test_restoring_takes_the_current_map_or_a_deleted_one(slot):
    coordinator = _make_coordinator()
    device = coordinator.device
    device.restore_map = AsyncMock()
    device.restore_deleted_map = AsyncMock()
    coordinator.async_update_listeners = MagicMock()

    await _make_entity(coordinator).async_restore_map(slot)

    if slot is None:
        device.restore_map.assert_awaited_once_with()
        device.restore_deleted_map.assert_not_called()
    else:
        device.restore_deleted_map.assert_awaited_once_with(3)
        device.restore_map.assert_not_called()


@pytest.mark.asyncio
async def test_a_moved_point_without_a_heading_leaves_it_to_the_device():
    coordinator = _make_coordinator()
    coordinator.device.set_maintenance_point = AsyncMock(return_value=1)
    coordinator.async_update_listeners = MagicMock()

    await _make_entity(coordinator).async_set_maintenance_point(x=-2000, y=30, point_id=1)

    coordinator.device.set_maintenance_point.assert_awaited_once_with(-2000, 30, None, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [True, False])
async def test_a_start_can_go_on_from_the_stop_point_or_start_over(resume):
    coordinator = _make_coordinator()
    entity = _make_entity(coordinator)

    await entity.async_start_all_area_mowing(from_stop_point=resume)
    await entity.async_start_zone_mowing([1, 3], from_stop_point=resume)

    coordinator.device.start_mowing.assert_awaited_once_with(mode=MowingMode.ALL_AREA, from_stop_point=resume)
    coordinator.device.start_mowing_zones.assert_awaited_once_with([1, 3], from_stop_point=resume)


@pytest.mark.asyncio
async def test_a_mower_that_resumes_otherwise_is_not_told_where_to_start():
    coordinator = _make_coordinator()
    coordinator.supports_start_from_stop_point = False
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="cannot be told"):
        await entity.async_start_all_area_mowing(from_stop_point=True)
    with pytest.raises(HomeAssistantError, match="cannot be told"):
        await entity.async_start_zone_mowing([1], from_stop_point=False)
    coordinator.device.start_mowing.assert_not_called()
    coordinator.device.start_mowing_zones.assert_not_called()


@pytest.mark.asyncio
async def test_a_start_told_where_to_begin_does_not_fall_back_to_the_generic_one():
    """The generic start cannot say where to begin, so it is not tried."""
    coordinator = _make_coordinator()
    coordinator.device.mowing_session_active = False
    coordinator.device.start_mowing = AsyncMock(return_value=False)
    coordinator.device.start_mowing_generic = AsyncMock(return_value=True)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="Failed to start all-area mowing"):
        await entity.async_start_all_area_mowing(from_stop_point=False)
    coordinator.device.start_mowing_generic.assert_not_called()


@pytest.mark.asyncio
async def test_a_consumable_is_reset_through_the_coordinator():
    coordinator = _make_coordinator()
    coordinator.async_reset_consumable = AsyncMock()

    await _make_entity(coordinator).async_reset_consumable("blade")

    coordinator.async_reset_consumable.assert_awaited_once_with("blade")


@pytest.mark.asyncio
async def test_the_mower_is_sent_to_a_maintenance_point():
    coordinator = _make_coordinator()
    coordinator.async_go_to_maintenance_point = AsyncMock(return_value=True)
    entity = _make_entity(coordinator)

    await entity.async_go_to_maintenance_point(2)
    coordinator.async_go_to_maintenance_point.assert_awaited_once_with(2)

    coordinator.async_go_to_maintenance_point = AsyncMock(return_value=False)
    with pytest.raises(HomeAssistantError, match="did not head"):
        await entity.async_go_to_maintenance_point(2)


@pytest.mark.asyncio
async def test_going_to_a_maintenance_point_needs_the_point(hass):
    schema = await _schema(hass, "go_to_maintenance_point")

    assert schema({"entity_id": "lawn_mower.mower", "point_id": "2"})["point_id"] == 2
    with pytest.raises(vol.Invalid):
        schema({"entity_id": "lawn_mower.mower"})


@pytest.mark.asyncio
async def test_a_window_is_set_in_minutes_after_midnight():
    from datetime import time as dt_time

    coordinator = _make_coordinator()
    coordinator.async_set_time_window_setting = AsyncMock(return_value=True)
    entity = _make_entity(coordinator)

    await entity.async_set_do_not_disturb(enabled=True, start=dt_time(21, 30), end=dt_time(7, 0))
    coordinator.async_set_time_window_setting.assert_awaited_once_with("DND", True, 1290, 420)

    await entity.async_set_low_speed_at_night(start=dt_time(22, 0))
    coordinator.async_set_time_window_setting.assert_awaited_with("LOW", None, 1320, None)

    coordinator.async_set_time_window_setting = AsyncMock(return_value=False)
    with pytest.raises(HomeAssistantError, match="did not take"):
        await entity.async_set_do_not_disturb(enabled=False)


@pytest.mark.asyncio
async def test_the_stop_point_setting_goes_through_the_coordinator():
    coordinator = _make_coordinator()
    coordinator.async_set_stop_point_setting = AsyncMock(return_value=True)

    await _make_entity(coordinator).async_set_start_from_stop_point(enabled=False)

    coordinator.async_set_stop_point_setting.assert_awaited_once_with(False, None)


@pytest.mark.asyncio
async def test_the_light_period_is_set_in_minutes_after_midnight():
    from datetime import time as dt_time

    coordinator = _make_coordinator()
    coordinator.async_set_light_setting = AsyncMock(return_value=True)
    entity = _make_entity(coordinator)

    await entity.async_set_light(custom_period=True, start=dt_time(20, 0), end=dt_time(6, 30), working=False)
    coordinator.async_set_light_setting.assert_awaited_once_with(start=1200, end=390, custom_period=True, working=False)

    coordinator.async_set_light_setting = AsyncMock(return_value=False)
    with pytest.raises(HomeAssistantError, match="did not take"):
        await entity.async_set_light(error=True)


@pytest.mark.asyncio
async def test_the_alert_and_the_voice_go_through_the_coordinator():
    coordinator = _make_coordinator()
    coordinator.async_set_human_presence_setting = AsyncMock(return_value=True)
    coordinator.async_set_robot_voice = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    await entity.async_set_human_presence_alert(enabled=True, sensitivity="low")
    coordinator.async_set_human_presence_setting.assert_awaited_once_with(enabled=True, sensitivity="low")

    with pytest.raises(HomeAssistantError, match="did not take"):
        await entity.async_set_robot_voice(volume=30, regular=True)
    coordinator.async_set_robot_voice.assert_awaited_once_with(30, regular=True)


async def _schema(hass, name):
    schema = dict(await _registered_services(hass))[name]
    return cv.make_entity_service_schema(schema) if isinstance(schema, dict) else schema


@pytest.mark.asyncio
async def test_the_settings_schemas_validate_their_input(hass):
    """Times arrive as times, the interval and the volume as numbers, and values out of range are refused."""
    from datetime import time as dt_time

    light = await _schema(hass, "set_light")
    validated = light({"entity_id": "lawn_mower.mower", "start": "20:00", "end": "06:30:00", "charging": "on"})
    assert (validated["start"], validated["end"], validated["charging"]) == (dt_time(20, 0), dt_time(6, 30), True)

    alert = await _schema(hass, "set_human_presence_alert")
    assert alert({"entity_id": "lawn_mower.mower", "interval": "10"})["interval"] == 10
    voice = await _schema(hass, "set_robot_voice")
    assert voice({"entity_id": "lawn_mower.mower", "volume": "40"})["volume"] == 40

    for schema, invalid in (
        (alert, {"interval": 5}),
        (alert, {"sensitivity": "extreme"}),
        (voice, {"volume": 120}),
        (light, {"start": "25:00"}),
    ):
        with pytest.raises(vol.Invalid):
            schema({"entity_id": "lawn_mower.mower", **invalid})


@pytest.mark.asyncio
@pytest.mark.parametrize("called", [True, False])
async def test_the_mower_is_called_to_be_found(called):
    coordinator = _make_coordinator()
    coordinator.device.find_robot = AsyncMock(return_value=called)
    entity = _make_entity(coordinator)

    if called:
        await entity.async_find_robot()
    else:
        with pytest.raises(HomeAssistantError, match="did not call out"):
            await entity.async_find_robot()
    coordinator.device.find_robot.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_find_robot_is_registered(hass):
    assert "find_robot" in dict(await _registered_services(hass))
