"""Tests for Dreame Mower number entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.const import DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.number import (
    DreameMowerCuttingHeightNumber,
    DreameMowerMowingDirectionNumber,
    async_setup_entry,
)


def _make_coordinator(model="dreame.mower.g2408"):
    coordinator = MagicMock()
    coordinator.device_mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device_name = "Test Mower"
    coordinator.device_model = model
    coordinator.device_serial = "SN123"
    coordinator.device_manufacturer = "Dreametech™"
    coordinator.device_firmware = "1.0.0"
    coordinator.device_connected = True
    coordinator.device_online = True
    coordinator.supports_cutting_height = model != "mova.mower.g2405c"
    coordinator.cutting_height = 5.5
    coordinator.async_set_cutting_height = AsyncMock(return_value=True)
    coordinator.supports_mowing_direction = True
    coordinator.mowing_direction_angle = 45
    coordinator.async_set_mowing_direction = AsyncMock(return_value=True)
    return coordinator


def _make_mowing_direction_number(coordinator=None):
    coordinator = coordinator or _make_coordinator()
    entity = DreameMowerMowingDirectionNumber(coordinator)
    entity.hass = MagicMock()
    return entity


def _make_cutting_height_number(coordinator=None):
    coordinator = coordinator or _make_coordinator()
    entity = DreameMowerCuttingHeightNumber(coordinator)
    entity.hass = MagicMock()
    return entity


async def _setup_entry(coordinator):
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry_id": {DATA_COORDINATOR: coordinator}}}
    entry = MagicMock()
    entry.entry_id = "entry_id"
    added_entities = []
    await async_setup_entry(hass, entry, added_entities.extend)
    return added_entities


@pytest.mark.asyncio
async def test_setup_adds_the_cutting_height_entity_for_adjustable_models():
    """Models with an adjustable cutting height should get the entity."""
    entities = await _setup_entry(_make_coordinator())

    assert isinstance(entities[0], DreameMowerCuttingHeightNumber)


@pytest.mark.asyncio
async def test_setup_skips_models_without_an_adjustable_cutting_height():
    """Models whose height is set by hand should not get the entity."""
    entities = await _setup_entry(_make_coordinator("mova.mower.g2405c"))

    assert not any(isinstance(entity, DreameMowerCuttingHeightNumber) for entity in entities)


def test_cutting_height_reports_the_coordinator_value():
    """The entity state should mirror the height the coordinator holds."""
    entity = _make_cutting_height_number()

    assert entity.native_value == 5.5


def test_cutting_height_is_unknown_until_it_has_been_read():
    """An unread height leaves the entity without a value."""
    coordinator = _make_coordinator()
    coordinator.cutting_height = None
    entity = _make_cutting_height_number(coordinator)

    assert entity.native_value is None


def test_cutting_height_range_follows_the_model():
    """The selectable range should match what the model supports."""
    assert _make_cutting_height_number().native_max_value == 7.0
    assert _make_cutting_height_number(
        _make_coordinator("dreame.mower.g2541e")
    ).native_max_value == 10.0

    entity = _make_cutting_height_number()
    assert entity.native_min_value == 3.0
    assert entity.native_step == 0.5


@pytest.mark.asyncio
async def test_setting_the_cutting_height_delegates_to_the_coordinator():
    """Writing the entity should forward the height to the coordinator."""
    coordinator = _make_coordinator()
    entity = _make_cutting_height_number(coordinator)

    await entity.async_set_native_value(4.0)

    coordinator.async_set_cutting_height.assert_awaited_once_with(4.0)


@pytest.mark.asyncio
async def test_setting_the_cutting_height_raises_when_the_device_rejects_it():
    """A rejected write should surface as an error instead of passing silently."""
    coordinator = _make_coordinator()
    coordinator.async_set_cutting_height = AsyncMock(return_value=False)
    entity = _make_cutting_height_number(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(4.0)


@pytest.mark.asyncio
async def test_setting_a_height_the_record_cannot_carry_raises():
    """A record without a height slot has to reach the user as an error."""
    coordinator = _make_coordinator()
    coordinator.async_set_cutting_height = AsyncMock(
        side_effect=ValueError("This mower does not report a cutting height")
    )
    entity = _make_cutting_height_number(coordinator)

    with pytest.raises(HomeAssistantError, match="cutting height"):
        await entity.async_set_native_value(5.0)


@pytest.mark.asyncio
async def test_setup_adds_the_mowing_direction_entity_when_the_mower_reports_one():
    """A mower that keeps a mowing direction gets the entity for it."""
    entities = await _setup_entry(_make_coordinator())

    assert any(isinstance(entity, DreameMowerMowingDirectionNumber) for entity in entities)


@pytest.mark.asyncio
async def test_setup_skips_the_mowing_direction_entity_without_one():
    """A mower that reported no direction must not get the entity."""
    coordinator = _make_coordinator()
    coordinator.supports_mowing_direction = False

    entities = await _setup_entry(coordinator)

    assert not any(isinstance(entity, DreameMowerMowingDirectionNumber) for entity in entities)


def test_mowing_direction_reports_the_coordinator_value():
    """The entity state should mirror the direction the coordinator holds."""
    assert _make_mowing_direction_number().native_value == 45


def test_mowing_direction_is_unknown_until_it_has_been_read():
    """An unread direction leaves the entity without a value."""
    coordinator = _make_coordinator()
    coordinator.mowing_direction_angle = None

    assert _make_mowing_direction_number(coordinator).native_value is None


def test_mowing_direction_covers_half_a_turn():
    """A direction is a line, so the range stops where the lanes repeat."""
    entity = _make_mowing_direction_number()

    assert entity.native_min_value == 0
    assert entity.native_max_value == 179
    assert entity.native_step == 1


@pytest.mark.asyncio
async def test_setting_the_mowing_direction_writes_it():
    """The entity sets the direction of the active map."""
    coordinator = _make_coordinator()
    entity = _make_mowing_direction_number(coordinator)

    await entity.async_set_native_value(90)

    coordinator.async_set_mowing_direction.assert_awaited_once_with(angle_degrees=90)


@pytest.mark.asyncio
async def test_a_refused_mowing_direction_raises():
    """A direction the mower did not take must not pass as set."""
    coordinator = _make_coordinator()
    coordinator.async_set_mowing_direction = AsyncMock(return_value=False)
    entity = _make_mowing_direction_number(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(90)
