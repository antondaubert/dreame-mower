"""Tests for DreameMowerLawnMower entity."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.lawn_mower import LawnMowerActivity
from homeassistant.exceptions import HomeAssistantError
from custom_components.dreame_mower.dreame.device import MowingMode
from custom_components.dreame_mower.lawn_mower import DreameMowerLawnMower
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
    coordinator.current_map_id = None
    coordinator.task_target_map_id = None
    coordinator.selected_mowing_mode = MowingMode.ALL_AREA
    coordinator.selected_contour_id = None
    coordinator.selected_zone_id = None
    coordinator.selected_spot_area_id = None
    coordinator.spot_areas = []
    coordinator.device.start_mowing_zones = AsyncMock(return_value=True)
    coordinator.device.start_mowing_edges = AsyncMock(return_value=True)
    coordinator.device.start_mowing_spots = AsyncMock(return_value=True)
    coordinator.device.start_mowing_generic = AsyncMock(return_value=True)
    coordinator.device.mowing_session_active = False
    coordinator.supports_cutting_height = True
    coordinator.cutting_height = None
    coordinator.zone_cutting_heights = {}
    coordinator.mowing_preference_mode = None
    coordinator.async_set_cutting_height = AsyncMock(return_value=True)
    coordinator.async_set_mowing_preference_mode = AsyncMock(return_value=True)
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
async def test_async_start_mowing_calls_device():
    entity = _make_entity()
    await entity.async_start_mowing()
    entity.coordinator.device.start_mowing.assert_awaited_once_with(mode=MowingMode.ALL_AREA)


@pytest.mark.asyncio
async def test_async_start_mowing_uses_selected_edge_mode_with_contours():
    coordinator = _make_coordinator()
    coordinator.selected_mowing_mode = MowingMode.EDGE
    coordinator.selected_contour_id = [2, 0]
    entity = _make_entity(coordinator)

    await entity.async_start_mowing()

    entity.coordinator.device.start_mowing.assert_awaited_once_with(
        mode=MowingMode.EDGE,
        contour_ids=[[2, 0]],
    )


@pytest.mark.asyncio
async def test_async_start_mowing_raises_when_edge_mode_has_no_selected_edge():
    coordinator = _make_coordinator()
    coordinator.selected_mowing_mode = MowingMode.EDGE
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="No edge is selected"):
        await entity.async_start_mowing()


@pytest.mark.asyncio
async def test_async_start_mowing_uses_selected_zone_mode_with_zone_id():
    coordinator = _make_coordinator()
    coordinator.selected_mowing_mode = MowingMode.ZONE
    coordinator.selected_zone_id = 3
    entity = _make_entity(coordinator)

    await entity.async_start_mowing()

    entity.coordinator.device.start_mowing.assert_awaited_once_with(
        mode=MowingMode.ZONE,
        zone_ids=[3],
    )


@pytest.mark.asyncio
async def test_async_start_mowing_uses_selected_spot_mode_with_spot_id():
    coordinator = _make_coordinator()
    coordinator.selected_mowing_mode = MowingMode.SPOT
    coordinator.selected_spot_area_id = 5
    entity = _make_entity(coordinator)

    await entity.async_start_mowing()

    entity.coordinator.device.start_mowing.assert_awaited_once_with(
        mode=MowingMode.SPOT,
        spot_area_ids=[5],
    )


@pytest.mark.asyncio
async def test_async_start_mowing_raises_when_zone_mode_has_no_selected_zone():
    coordinator = _make_coordinator()
    coordinator.selected_mowing_mode = MowingMode.ZONE
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="No zone is selected"):
        await entity.async_start_mowing()


@pytest.mark.asyncio
async def test_async_start_mowing_raises_when_spot_mode_has_no_selected_spot():
    coordinator = _make_coordinator()
    coordinator.selected_mowing_mode = MowingMode.SPOT
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="No spot is selected"):
        await entity.async_start_mowing()


@pytest.mark.asyncio
async def test_async_start_zone_mowing_calls_device_zone_start():
    entity = _make_entity()

    await entity.async_start_zone_mowing([1, 3])

    entity.coordinator.device.start_mowing_zones.assert_awaited_once_with([1, 3])


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
    coordinator.selected_mowing_mode = MowingMode.ALL_AREA
    coordinator.device.start_mowing = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)
    entity._attr_activity = LawnMowerActivity.DOCKED

    await entity.async_start_mowing()

    coordinator.device.start_mowing_generic.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_all_area_start_exception_falls_back_to_generic():
    """When the map-aware all-area start raises, fall back to generic."""
    coordinator = _make_coordinator()
    coordinator.selected_mowing_mode = MowingMode.ALL_AREA
    coordinator.device.start_mowing = AsyncMock(side_effect=RuntimeError("boom"))
    entity = _make_entity(coordinator)
    entity._attr_activity = LawnMowerActivity.DOCKED

    await entity.async_start_mowing()

    coordinator.device.start_mowing_generic.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_zone_start_failure_does_not_fall_back_to_generic():
    """A failed zone start must not trigger the all-area-only generic fallback."""
    coordinator = _make_coordinator()
    coordinator.selected_mowing_mode = MowingMode.ZONE
    coordinator.selected_zone_id = 1
    coordinator.device.start_mowing = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)
    entity._attr_activity = LawnMowerActivity.DOCKED

    await entity.async_start_mowing()

    coordinator.device.start_mowing_generic.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_zone_selection_raises_without_generic_fallback():
    """A selection HomeAssistantError propagates and skips the generic fallback."""
    coordinator = _make_coordinator()
    coordinator.selected_mowing_mode = MowingMode.ZONE
    coordinator.selected_zone_id = None
    entity = _make_entity(coordinator)
    entity._attr_activity = LawnMowerActivity.DOCKED

    with pytest.raises(HomeAssistantError):
        await entity.async_start_mowing()

    coordinator.device.start_mowing_generic.assert_not_awaited()


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


def test_extra_state_attributes_include_zones_and_contours():
    coordinator = _make_coordinator()
    coordinator.zones = [{"id": 1, "name": "Front", "area": 12.5}]
    coordinator.contours = [[1, 0], [2, 0]]
    coordinator.spot_areas = [{"id": 4, "name": "Tree", "area": 2.5}]
    coordinator.available_maps = [{"id": 1, "index": 0, "name": "Front", "area": 12.5}]
    coordinator.current_map_id = 1
    coordinator.task_target_map_id = 2
    coordinator.selected_contour_id = [2, 0]
    coordinator.selected_zone_id = 1
    coordinator.selected_spot_area_id = 4
    entity = _make_entity(coordinator)

    assert entity.extra_state_attributes == {
        "zones": [{"id": 1, "name": "Front", "area": 12.5}],
        "contours": [[1, 0], [2, 0]],
        "maps": [{"id": 1, "index": 0, "name": "Front", "area": 12.5}],
        "current_map_id": 1,
        "task_target_map_id": 2,
        "cutting_height": None,
        "zone_cutting_heights": {},
        "mowing_preference_mode": None,
        "selected_mowing_mode": "all_area",
        "selected_contour_id": [2, 0],
        "selected_zone_id": 1,
        "selected_spot_area_id": 4,
    }


@pytest.mark.asyncio
async def test_set_cutting_height_service_delegates_to_the_coordinator():
    """The service should forward the height and optional map to the coordinator."""
    coordinator = _make_coordinator()
    entity = _make_entity(coordinator)

    await entity.async_set_cutting_height(4.5, map_id=2)

    coordinator.async_set_cutting_height.assert_awaited_once_with(4.5, 2, None)


@pytest.mark.asyncio
async def test_set_cutting_height_service_defaults_to_the_active_map():
    """Omitting the map should let the device layer use the active map."""
    coordinator = _make_coordinator()
    entity = _make_entity(coordinator)

    await entity.async_set_cutting_height(6)

    coordinator.async_set_cutting_height.assert_awaited_once_with(6, None, None)


@pytest.mark.asyncio
async def test_set_cutting_height_service_rejects_fixed_height_models():
    """Models without an adjustable height should report a clear error."""
    coordinator = _make_coordinator()
    coordinator.supports_cutting_height = False
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_set_cutting_height(5)

    coordinator.async_set_cutting_height.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_cutting_height_service_raises_when_the_write_fails():
    """A failed write should surface as an error instead of passing silently."""
    coordinator = _make_coordinator()
    coordinator.async_set_cutting_height = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_set_cutting_height(5)


@pytest.mark.asyncio
async def test_set_cutting_height_service_reports_out_of_range_heights():
    """A height the device layer rejects should surface as an error."""
    coordinator = _make_coordinator()
    coordinator.async_set_cutting_height = AsyncMock(side_effect=ValueError("out of range"))
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_set_cutting_height(99)


@pytest.mark.asyncio
async def test_set_cutting_height_service_forwards_the_zone_id():
    """A zone ID should reach the coordinator so only that zone changes."""
    coordinator = _make_coordinator()
    entity = _make_entity(coordinator)

    await entity.async_set_cutting_height(5.0, zone_id=3)

    coordinator.async_set_cutting_height.assert_awaited_once_with(5.0, None, 3)


@pytest.mark.asyncio
async def test_set_cutting_height_service_names_the_zone_when_it_fails():
    """A failed zone write should say which zone it was."""
    coordinator = _make_coordinator()
    coordinator.async_set_cutting_height = AsyncMock(return_value=False)
    entity = _make_entity(coordinator)

    with pytest.raises(HomeAssistantError, match="zone 3"):
        await entity.async_set_cutting_height(5.0, zone_id=3)


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


def test_attributes_expose_the_cutting_heights_and_mode():
    """Automations need the zone IDs and the mode to use the service."""
    coordinator = _make_coordinator()
    coordinator.cutting_height = 4.0
    coordinator.zone_cutting_heights = {1: 5.0, 3: 6.5}
    coordinator.mowing_preference_mode = MowingPreferenceMode.PER_ZONE
    entity = _make_entity(coordinator)

    attributes = entity.extra_state_attributes

    assert attributes["cutting_height"] == 4.0
    assert attributes["zone_cutting_heights"] == {1: 5.0, 3: 6.5}
    assert attributes["mowing_preference_mode"] == "per_zone"


def test_attributes_omit_the_cutting_height_for_fixed_height_models():
    """Models without an adjustable height should not advertise one."""
    coordinator = _make_coordinator()
    coordinator.supports_cutting_height = False
    entity = _make_entity(coordinator)

    attributes = entity.extra_state_attributes

    assert "cutting_height" not in attributes
    assert "zone_cutting_heights" not in attributes
    assert "mowing_preference_mode" not in attributes
