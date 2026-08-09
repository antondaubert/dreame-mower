"""Tests for Dreame Mower number entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.const import DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.number import (
    DreameMowerCuttingHeightNumber,
    DreameMowerRainDelayNumber,
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
    coordinator.supports_rain_protection = False
    return coordinator


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

    assert len(entities) == 1
    assert isinstance(entities[0], DreameMowerCuttingHeightNumber)


@pytest.mark.asyncio
async def test_setup_skips_models_without_an_adjustable_cutting_height():
    """Models whose height is set by hand should not get the entity."""
    entities = await _setup_entry(_make_coordinator("mova.mower.g2405c"))

    assert entities == []


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


def _make_rain_coordinator(model="dreame.mower.g2408", delay_hours=8):
    coordinator = _make_coordinator(model)
    coordinator.supports_cutting_height = False
    coordinator.supports_rain_protection = True
    coordinator.rain_delay_hours = delay_hours
    coordinator.rain_delay_min_hours = 0
    coordinator.rain_delay_max_hours = 25 if model == "dreame.mower.g2408" else 24
    coordinator.async_set_rain_protection = AsyncMock(return_value=True)
    return coordinator


def _make_rain_delay_number(coordinator=None):
    entity = DreameMowerRainDelayNumber(coordinator or _make_rain_coordinator())
    entity.hass = MagicMock()
    return entity


@pytest.mark.asyncio
async def test_setup_adds_the_rain_delay_entity():
    """A device that reports rain settings gets the delay entity."""
    entities = await _setup_entry(_make_rain_coordinator())

    assert len(entities) == 1
    assert isinstance(entities[0], DreameMowerRainDelayNumber)


@pytest.mark.asyncio
async def test_setup_skips_devices_without_rain_settings():
    """Devices that never reported the settings must not get the entity."""
    coordinator = _make_rain_coordinator()
    coordinator.supports_rain_protection = False

    assert await _setup_entry(coordinator) == []


def test_rain_delay_reports_the_coordinator_value():
    """The entity state should mirror the delay the coordinator holds."""
    assert _make_rain_delay_number().native_value == 8
    assert _make_rain_delay_number(_make_rain_coordinator(delay_hours=None)).native_value is None


def test_rain_delay_range_follows_the_model():
    """Camera models offer the extra step that resumes as soon as the rain stops."""
    assert _make_rain_delay_number().native_max_value == 25
    assert _make_rain_delay_number(
        _make_rain_coordinator("dreame.mower.g2405")
    ).native_max_value == 24

    entity = _make_rain_delay_number()
    assert entity.native_min_value == 0
    assert entity.native_step == 1


@pytest.mark.asyncio
async def test_setting_the_rain_delay_keeps_the_protection_switch():
    """Writing the delay must not restate the switch, so the device keeps it."""
    coordinator = _make_rain_coordinator()
    entity = _make_rain_delay_number(coordinator)

    coordinator.rain_delay_hours = 3

    await entity.async_set_native_value(3.0)

    coordinator.async_set_rain_protection.assert_awaited_once_with(delay_hours=3)


@pytest.mark.asyncio
async def test_setting_the_rain_delay_raises_when_the_device_rejects_it():
    """A rejected write should surface as an error instead of passing silently."""
    coordinator = _make_rain_coordinator()
    coordinator.async_set_rain_protection = AsyncMock(return_value=False)
    entity = _make_rain_delay_number(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(3.0)


@pytest.mark.asyncio
async def test_setting_the_rain_delay_raises_when_the_mower_keeps_its_own():
    """A delay the mower declines while protection is off must not pass silently."""
    coordinator = _make_rain_coordinator(delay_hours=8)
    entity = _make_rain_delay_number(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(3.0)
