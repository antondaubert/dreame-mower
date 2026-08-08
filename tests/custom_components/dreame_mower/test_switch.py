"""Tests for Dreame Mower switch entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.const import DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.switch import (
    DreameMowerChargingPeriodSwitch,
    async_setup_entry,
)


def _make_coordinator(supported=True, enabled=True):
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
    coordinator.charging_period_enabled = enabled
    coordinator.async_set_charging_period = AsyncMock(return_value=True)
    return coordinator


def _make_switch(coordinator=None):
    entity = DreameMowerChargingPeriodSwitch(coordinator or _make_coordinator())
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
async def test_setup_adds_the_charging_period_switch():
    """A device that reports charging settings gets the switch."""
    entities = await _setup_entry(_make_coordinator())

    assert len(entities) == 1
    assert isinstance(entities[0], DreameMowerChargingPeriodSwitch)


@pytest.mark.asyncio
async def test_setup_skips_devices_without_charging_settings():
    """Devices that never reported the settings must not get the switch."""
    entities = await _setup_entry(_make_coordinator(supported=False))

    assert entities == []


def test_the_switch_reports_whether_the_period_is_on():
    """The switch state should mirror what the coordinator holds."""
    assert _make_switch().is_on is True
    assert _make_switch(_make_coordinator(enabled=False)).is_on is False


def test_the_switch_is_unknown_until_the_settings_have_been_read():
    """Unread settings leave the switch without a state."""
    assert _make_switch(_make_coordinator(enabled=None)).is_on is None


@pytest.mark.asyncio
async def test_switching_keeps_the_configured_times():
    """Toggling must not restate the window, so the device keeps its times."""
    coordinator = _make_coordinator()
    entity = _make_switch(coordinator)

    await entity.async_turn_on()
    coordinator.async_set_charging_period.assert_awaited_once_with(enabled=True)

    coordinator.async_set_charging_period.reset_mock()
    await entity.async_turn_off()
    coordinator.async_set_charging_period.assert_awaited_once_with(enabled=False)


@pytest.mark.asyncio
async def test_switching_raises_when_the_device_rejects_it():
    """A rejected write should surface as an error instead of passing silently."""
    coordinator = _make_coordinator()
    coordinator.async_set_charging_period = AsyncMock(return_value=False)
    entity = _make_switch(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()

    with pytest.raises(HomeAssistantError):
        await entity.async_turn_off()
