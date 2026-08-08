"""Tests for Dreame Mower time entities."""

from datetime import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.const import DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.time import (
    DreameMowerChargingPeriodEndTime,
    DreameMowerChargingPeriodStartTime,
    async_setup_entry,
    minutes_to_time,
    time_to_minutes,
)


def _make_coordinator(supported=True):
    coordinator = MagicMock()
    coordinator.device_mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device_name = "Test Mower"
    coordinator.device_model = "dreame.mower.g2408"
    coordinator.device_serial = "SN123"
    coordinator.device_manufacturer = "Dreametech™"
    coordinator.device_firmware = "1.0.0"
    coordinator.device_connected = True
    coordinator.device_online = True
    coordinator.supports_charging_period = supported
    coordinator.charging_period_start_minutes = 1320
    coordinator.charging_period_end_minutes = 360
    coordinator.async_set_charging_period = AsyncMock(return_value=True)
    return coordinator


def _make_entity(entity_cls, coordinator=None):
    entity = entity_cls(coordinator or _make_coordinator())
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


def test_minutes_convert_to_a_time_of_day_and_back():
    """The device counts minutes since midnight; entities speak clock times."""
    assert minutes_to_time(0) == time(0, 0)
    assert minutes_to_time(1320) == time(22, 0)
    assert minutes_to_time(1439) == time(23, 59)
    assert minutes_to_time(None) is None

    assert time_to_minutes(time(22, 0)) == 1320
    assert time_to_minutes(time(0, 0)) == 0
    # Seconds have no place in the device's record and must not shift the value.
    assert time_to_minutes(time(6, 30, 45)) == 390


@pytest.mark.asyncio
async def test_setup_adds_both_ends_of_the_charging_period():
    """A device that reports charging settings gets a start and an end entity."""
    entities = await _setup_entry(_make_coordinator())

    assert [type(entity) for entity in entities] == [
        DreameMowerChargingPeriodStartTime,
        DreameMowerChargingPeriodEndTime,
    ]


@pytest.mark.asyncio
async def test_setup_skips_devices_without_charging_settings():
    """Devices that never reported the settings must not get the entities."""
    entities = await _setup_entry(_make_coordinator(supported=False))

    assert entities == []


def test_the_entities_report_the_configured_window():
    """Both ends should mirror what the coordinator holds."""
    assert _make_entity(DreameMowerChargingPeriodStartTime).native_value == time(22, 0)
    assert _make_entity(DreameMowerChargingPeriodEndTime).native_value == time(6, 0)


def test_the_entities_are_unknown_until_the_settings_have_been_read():
    """An unread window leaves both entities without a value."""
    coordinator = _make_coordinator()
    coordinator.charging_period_start_minutes = None
    coordinator.charging_period_end_minutes = None

    assert _make_entity(DreameMowerChargingPeriodStartTime, coordinator).native_value is None
    assert _make_entity(DreameMowerChargingPeriodEndTime, coordinator).native_value is None


@pytest.mark.asyncio
async def test_writing_one_end_leaves_the_other_untouched():
    """Each entity writes only its own end of the window."""
    coordinator = _make_coordinator()

    await _make_entity(DreameMowerChargingPeriodStartTime, coordinator).async_set_value(time(23, 30))
    coordinator.async_set_charging_period.assert_awaited_once_with(start_minutes=1410)

    coordinator.async_set_charging_period.reset_mock()
    await _make_entity(DreameMowerChargingPeriodEndTime, coordinator).async_set_value(time(5, 15))
    coordinator.async_set_charging_period.assert_awaited_once_with(end_minutes=315)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_cls",
    [DreameMowerChargingPeriodStartTime, DreameMowerChargingPeriodEndTime],
)
async def test_writing_raises_when_the_device_rejects_it(entity_cls):
    """A rejected write should surface as an error instead of passing silently."""
    coordinator = _make_coordinator()
    coordinator.async_set_charging_period = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError):
        await _make_entity(entity_cls, coordinator).async_set_value(time(7, 0))
