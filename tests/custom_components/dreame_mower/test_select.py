"""Tests for Dreame Mower select entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.coordinator import DreameMowerCoordinator
from custom_components.dreame_mower.dreame.device import MowingMode
from custom_components.dreame_mower.select import (
    DreameMowerEdgeSelect,
    DreameMowerRainDelaySelect,
    DreameMowerMapSelect,
    DreameMowerMowingActionSelect,
    DreameMowerSpotSelect,
    DreameMowerZoneSelect,
)


def _make_coordinator():
    coordinator = MagicMock()
    coordinator.device_mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device_name = "Test Mower"
    coordinator.device_model = "dreame.mower.test"
    coordinator.device_serial = "SN123"
    coordinator.device_manufacturer = "Dreametech™"
    coordinator.device_firmware = "1.0.0"
    coordinator.device_connected = True
    coordinator.device = MagicMock()
    coordinator.device.set_current_map = AsyncMock(return_value=True)
    coordinator.available_maps = [
        {"id": 1, "index": 0, "name": "Front", "area": 25.0},
        {"id": 2, "index": 1, "name": "Back", "area": 30.5},
    ]
    coordinator.current_map_id = 2
    coordinator.zones = [
        {"id": 1, "name": "Front Lawn", "area": 12.5},
        {"id": 3, "name": "Back Lawn", "area": 9.7},
    ]
    coordinator.spot_areas = [
        {"id": 4, "name": "Tree", "area": 2.5},
        {"id": 5, "name": "Bench", "area": 1.2},
    ]
    coordinator.contours = [[1, 0], [2, 0]]
    coordinator.selected_mowing_mode = MowingMode.ALL_AREA
    coordinator.selectable_mowing_modes = [MowingMode.ALL_AREA, MowingMode.EDGE, MowingMode.ZONE, MowingMode.SPOT]
    coordinator.selected_contour_id = [2, 0]
    coordinator.selected_zone_id = 3
    coordinator.selected_spot_area_id = 5
    coordinator.async_set_selected_mowing_mode = AsyncMock()
    coordinator.async_set_selected_contour_id = AsyncMock()
    coordinator.async_set_selected_zone_id = AsyncMock()
    coordinator.async_set_selected_spot_area_id = AsyncMock()
    return coordinator


def _make_map_select(coordinator=None):
    entity = DreameMowerMapSelect.__new__(DreameMowerMapSelect)
    entity.coordinator = coordinator or _make_coordinator()
    entity._entity_description_key = "map_select"
    entity._attr_has_entity_name = True
    entity.hass = MagicMock()
    return entity


def _make_mowing_action_select(coordinator=None):
    entity = DreameMowerMowingActionSelect.__new__(DreameMowerMowingActionSelect)
    entity.coordinator = coordinator or _make_coordinator()
    entity._entity_description_key = "mowing_action"
    entity._attr_has_entity_name = True
    entity.hass = MagicMock()
    return entity


def _make_edge_select(coordinator=None):
    entity = DreameMowerEdgeSelect.__new__(DreameMowerEdgeSelect)
    entity.coordinator = coordinator or _make_coordinator()
    entity._entity_description_key = "edge_select"
    entity._attr_has_entity_name = True
    entity.hass = MagicMock()
    return entity


def _make_zone_select(coordinator=None):
    entity = DreameMowerZoneSelect.__new__(DreameMowerZoneSelect)
    entity.coordinator = coordinator or _make_coordinator()
    entity._entity_description_key = "zone_select"
    entity._attr_has_entity_name = True
    entity.hass = MagicMock()
    return entity


def _make_spot_select(coordinator=None):
    entity = DreameMowerSpotSelect.__new__(DreameMowerSpotSelect)
    entity.coordinator = coordinator or _make_coordinator()
    entity._entity_description_key = "spot_select"
    entity._attr_has_entity_name = True
    entity.hass = MagicMock()
    return entity


def _make_real_selection_coordinator():
    coordinator = DreameMowerCoordinator.__new__(DreameMowerCoordinator)
    coordinator.device = MagicMock()
    coordinator.device.zones = [
        {"id": 1, "name": "Front Lawn", "area": 12.5},
        {"id": 3, "name": "Back Lawn", "area": 9.7},
    ]
    coordinator.device.contours = [[1, 0], [2, 0]]
    coordinator.device.spot_areas = [
        {"id": 4, "name": "Tree", "area": 2.5},
        {"id": 5, "name": "Bench", "area": 1.2},
    ]
    coordinator._selected_mowing_mode = MowingMode.ALL_AREA
    coordinator._selected_contour_id = None
    coordinator._selected_zone_id = None
    coordinator._selected_spot_area_id = None
    return coordinator


def test_map_select_options_and_current_option():
    entity = _make_map_select()

    assert entity.options == ["Front (#1)", "Back (#2)"]
    assert entity.current_option == "Back (#2)"


@pytest.mark.asyncio
async def test_map_select_calls_device_set_current_map():
    coordinator = _make_coordinator()
    entity = _make_map_select(coordinator)

    await entity.async_select_option("Front (#1)")

    coordinator.device.set_current_map.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_map_select_explains_a_refused_switch_during_a_task():
    """A failed switch during a task should name the reason, not just fail."""
    coordinator = _make_coordinator()
    coordinator.device.set_current_map = AsyncMock(return_value=False)
    coordinator.device.mowing_session_active = True
    entity = _make_map_select(coordinator)

    with pytest.raises(HomeAssistantError, match="while a mowing task is in progress"):
        await entity.async_select_option("Front (#1)")


@pytest.mark.asyncio
async def test_map_select_reports_a_failed_switch_outside_a_task():
    """Any other failure keeps the generic message."""
    coordinator = _make_coordinator()
    coordinator.device.set_current_map = AsyncMock(return_value=False)
    coordinator.device.mowing_session_active = False
    entity = _make_map_select(coordinator)

    with pytest.raises(HomeAssistantError, match="Failed to select map option: Front"):
        await entity.async_select_option("Front (#1)")


def test_mowing_action_select_options_and_current_option():
    entity = _make_mowing_action_select()

    assert entity.options == ["All area", "Edge", "Zone", "Spot"]
    assert entity.current_option == "All area"


@pytest.mark.asyncio
async def test_mowing_action_select_updates_coordinator_mode():
    coordinator = _make_coordinator()
    entity = _make_mowing_action_select(coordinator)

    await entity.async_select_option("Edge")

    coordinator.async_set_selected_mowing_mode.assert_awaited_once_with(MowingMode.EDGE)


def test_edge_select_options_and_current_option():
    entity = _make_edge_select()

    assert entity.options == ["Front Lawn edge", "Edge (2, 0)"]
    assert entity.current_option == "Edge (2, 0)"


def test_edge_select_defaults_to_first_available_option_when_unset():
    coordinator = _make_real_selection_coordinator()
    entity = _make_edge_select(coordinator)

    assert entity.current_option == "Front Lawn edge"


@pytest.mark.asyncio
async def test_edge_select_updates_selected_contour_id():
    coordinator = _make_coordinator()
    entity = _make_edge_select(coordinator)

    await entity.async_select_option("Front Lawn edge")

    coordinator.async_set_selected_contour_id.assert_awaited_once_with([1, 0])


def test_zone_select_options_and_current_option():
    entity = _make_zone_select()

    assert entity.options == ["Front Lawn (#1)", "Back Lawn (#3)"]
    assert entity.current_option == "Back Lawn (#3)"


def test_zone_select_defaults_to_first_available_option_when_unset():
    coordinator = _make_real_selection_coordinator()
    entity = _make_zone_select(coordinator)

    assert entity.current_option == "Front Lawn (#1)"


@pytest.mark.asyncio
async def test_zone_select_updates_selected_zone_id():
    coordinator = _make_coordinator()
    entity = _make_zone_select(coordinator)

    await entity.async_select_option("Front Lawn (#1)")

    coordinator.async_set_selected_zone_id.assert_awaited_once_with(1)


def test_spot_select_options_and_current_option():
    entity = _make_spot_select()

    assert entity.options == ["Tree (#4)", "Bench (#5)"]
    assert entity.current_option == "Bench (#5)"


def test_spot_select_defaults_to_first_available_option_when_unset():
    coordinator = _make_real_selection_coordinator()
    entity = _make_spot_select(coordinator)

    assert entity.current_option == "Tree (#4)"


@pytest.mark.asyncio
async def test_spot_select_updates_selected_spot_area_id():
    coordinator = _make_coordinator()
    entity = _make_spot_select(coordinator)

    await entity.async_select_option("Tree (#4)")

    coordinator.async_set_selected_spot_area_id.assert_awaited_once_with(4)


def _make_rain_delay_coordinator(delay_hours=8):
    coordinator = _make_coordinator()
    coordinator.supports_rain_protection = True
    coordinator.rain_delay_hours = delay_hours
    coordinator.async_set_rain_protection = AsyncMock(return_value=True)
    return coordinator


def _make_rain_delay_select(coordinator=None):
    entity = DreameMowerRainDelaySelect(coordinator or _make_rain_delay_coordinator())
    entity.hass = MagicMock()
    return entity


def test_the_rain_delay_is_offered_as_whole_hours():
    """The options run from staying docked through each hour of the range."""
    options = _make_rain_delay_select().options

    assert options[0] == "Don't mow after rain"
    assert options[1] == "1 h"
    assert options[-1] == "24 h"
    assert len(options) == 25


def test_the_rain_delay_reports_the_configured_option():
    """The selected option should mirror the delay the coordinator holds."""
    assert _make_rain_delay_select().current_option == "8 h"
    assert _make_rain_delay_select(
        _make_rain_delay_coordinator(delay_hours=0)
    ).current_option == "Don't mow after rain"


def test_the_rain_delay_is_unknown_until_it_has_been_read():
    """An unread delay leaves the entity without a selection."""
    coordinator = _make_rain_delay_coordinator(delay_hours=None)

    assert _make_rain_delay_select(coordinator).current_option is None


@pytest.mark.asyncio
async def test_selecting_a_rain_delay_keeps_the_protection_switch():
    """Choosing a delay must not restate the switch, so the device keeps it."""
    coordinator = _make_rain_delay_coordinator()
    entity = _make_rain_delay_select(coordinator)
    coordinator.rain_delay_hours = 3

    await entity.async_select_option("3 h")

    coordinator.async_set_rain_protection.assert_awaited_once_with(delay_hours=3)


@pytest.mark.asyncio
async def test_selecting_the_docked_option_sends_a_delay_of_zero():
    """Staying docked after rain is a delay of zero, not a separate command."""
    coordinator = _make_rain_delay_coordinator(delay_hours=0)
    entity = _make_rain_delay_select(coordinator)

    await entity.async_select_option("Don't mow after rain")

    coordinator.async_set_rain_protection.assert_awaited_once_with(delay_hours=0)


@pytest.mark.asyncio
async def test_selecting_a_rain_delay_raises_when_the_mower_keeps_its_own():
    """A delay the mower declines while protection is off must not pass silently."""
    entity = _make_rain_delay_select(_make_rain_delay_coordinator(delay_hours=8))

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("3 h")


@pytest.mark.asyncio
async def test_selecting_an_unknown_rain_delay_is_rejected():
    """An option outside the offered range is not a delay the mower can take."""
    entity = _make_rain_delay_select()

    with pytest.raises(ValueError):
        await entity.async_select_option("99 h")
