"""Tests for Dreame Mower switch entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.const import DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.switch import (
    DreameMowerAutomaticEdgeMowingSwitch,
    DreameMowerChargingPeriodSwitch,
    DreameMowerEdgeBladeOffsetSwitch,
    DreameMowerRainProtectionSwitch,
    DreameMowerSafeEdgeMowingSwitch,
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
    coordinator.supports_rain_protection = False
    coordinator.supports_edge_mowing_settings = False
    coordinator.supports_safe_edge_mowing = False
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


def _make_rain_coordinator(supported=True, enabled=True):
    coordinator = _make_coordinator()
    coordinator.supports_charging_period = False
    coordinator.supports_rain_protection = supported
    coordinator.rain_protection_enabled = enabled
    coordinator.async_set_rain_protection = AsyncMock(return_value=True)
    return coordinator


def _make_rain_switch(coordinator=None):
    entity = DreameMowerRainProtectionSwitch(coordinator or _make_rain_coordinator())
    entity.hass = MagicMock()
    return entity


@pytest.mark.asyncio
async def test_setup_adds_the_rain_protection_switch():
    """A device that reports rain settings gets the switch."""
    entities = await _setup_entry(_make_rain_coordinator())

    assert len(entities) == 1
    assert isinstance(entities[0], DreameMowerRainProtectionSwitch)


@pytest.mark.asyncio
async def test_setup_skips_devices_without_rain_settings():
    """Devices that never reported the settings must not get the switch."""
    assert await _setup_entry(_make_rain_coordinator(supported=False)) == []


def test_the_rain_switch_reports_whether_protection_is_on():
    """The switch state should mirror what the coordinator holds."""
    assert _make_rain_switch().is_on is True
    assert _make_rain_switch(_make_rain_coordinator(enabled=False)).is_on is False
    assert _make_rain_switch(_make_rain_coordinator(enabled=None)).is_on is None


@pytest.mark.asyncio
async def test_switching_rain_protection_keeps_the_configured_delay():
    """Toggling must not restate the delay, so the device keeps it."""
    coordinator = _make_rain_coordinator()
    entity = _make_rain_switch(coordinator)

    await entity.async_turn_on()
    coordinator.async_set_rain_protection.assert_awaited_once_with(enabled=True)

    coordinator.async_set_rain_protection.reset_mock()
    await entity.async_turn_off()
    coordinator.async_set_rain_protection.assert_awaited_once_with(enabled=False)


@pytest.mark.asyncio
async def test_switching_rain_protection_raises_when_the_device_rejects_it():
    """A rejected write should surface as an error instead of passing silently."""
    coordinator = _make_rain_coordinator()
    coordinator.async_set_rain_protection = AsyncMock(return_value=False)
    entity = _make_rain_switch(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()


def _make_edge_coordinator(supported=True, safe_supported=True, settings=None):
    coordinator = _make_coordinator()
    coordinator.supports_charging_period = False
    coordinator.supports_edge_mowing_settings = supported
    coordinator.supports_safe_edge_mowing = supported and safe_supported
    settings = {
        "edge_mowing_auto": True,
        "edge_blade_offset": False,
        "edge_mowing_safe": True,
    } if settings is None else settings
    coordinator.edge_mowing_auto = settings.get("edge_mowing_auto")
    coordinator.edge_blade_offset = settings.get("edge_blade_offset")
    coordinator.edge_mowing_safe = settings.get("edge_mowing_safe")
    coordinator.async_set_edge_mowing_settings = AsyncMock(return_value=True)
    return coordinator


@pytest.mark.asyncio
async def test_setup_adds_the_edge_mowing_switches():
    """A device that reports its mowing settings gets all three switches."""
    entities = await _setup_entry(_make_edge_coordinator())

    assert [type(entity) for entity in entities] == [
        DreameMowerAutomaticEdgeMowingSwitch,
        DreameMowerEdgeBladeOffsetSwitch,
        DreameMowerSafeEdgeMowingSwitch,
    ]


@pytest.mark.asyncio
async def test_setup_skips_safe_edge_mowing_when_the_device_has_no_such_setting():
    """Firmware without safe edge mowing must not get a switch that cannot write."""
    entities = await _setup_entry(_make_edge_coordinator(safe_supported=False))

    assert [type(entity) for entity in entities] == [
        DreameMowerAutomaticEdgeMowingSwitch,
        DreameMowerEdgeBladeOffsetSwitch,
    ]


@pytest.mark.asyncio
async def test_setup_skips_the_edge_switches_without_mowing_settings():
    """Devices whose mowing settings were never read must not get the switches."""
    assert await _setup_entry(_make_edge_coordinator(supported=False)) == []


def test_the_edge_switches_report_what_the_coordinator_holds():
    """Each switch state should mirror its own setting."""
    coordinator = _make_edge_coordinator()

    assert DreameMowerAutomaticEdgeMowingSwitch(coordinator).is_on is True
    assert DreameMowerEdgeBladeOffsetSwitch(coordinator).is_on is False
    assert DreameMowerSafeEdgeMowingSwitch(coordinator).is_on is True


def test_the_edge_switches_are_unknown_until_the_settings_have_been_read():
    """Unread settings leave the switches without a state."""
    coordinator = _make_edge_coordinator(settings={})

    assert DreameMowerAutomaticEdgeMowingSwitch(coordinator).is_on is None
    assert DreameMowerSafeEdgeMowingSwitch(coordinator).is_on is None


@pytest.mark.asyncio
async def test_each_edge_switch_only_states_its_own_setting():
    """Toggling one setting must leave the other two as the device holds them."""
    coordinator = _make_edge_coordinator()

    await DreameMowerSafeEdgeMowingSwitch(coordinator).async_turn_off()
    coordinator.async_set_edge_mowing_settings.assert_awaited_once_with(safe=False)

    coordinator.async_set_edge_mowing_settings.reset_mock()
    await DreameMowerAutomaticEdgeMowingSwitch(coordinator).async_turn_on()
    coordinator.async_set_edge_mowing_settings.assert_awaited_once_with(auto=True)

    coordinator.async_set_edge_mowing_settings.reset_mock()
    await DreameMowerEdgeBladeOffsetSwitch(coordinator).async_turn_on()
    coordinator.async_set_edge_mowing_settings.assert_awaited_once_with(blade_offset=True)


@pytest.mark.asyncio
async def test_switching_an_edge_setting_raises_when_the_device_rejects_it():
    """A rejected write should surface as an error instead of passing silently."""
    coordinator = _make_edge_coordinator()
    coordinator.async_set_edge_mowing_settings = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError):
        await DreameMowerAutomaticEdgeMowingSwitch(coordinator).async_turn_on()


@pytest.mark.asyncio
async def test_switching_an_unsupported_edge_setting_raises():
    """A setting the record cannot carry has to reach the user as an error."""
    coordinator = _make_edge_coordinator()
    coordinator.async_set_edge_mowing_settings = AsyncMock(
        side_effect=ValueError("This mower does not support safe edge mowing")
    )

    with pytest.raises(HomeAssistantError, match="safe edge mowing"):
        await DreameMowerSafeEdgeMowingSwitch(coordinator).async_turn_off()
