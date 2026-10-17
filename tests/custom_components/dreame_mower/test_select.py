"""Tests for Dreame Mower select entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.select import DreameMowerRainDelaySelect


def _make_coordinator():
    coordinator = MagicMock()
    coordinator.supports_device_setting = lambda key: False
    coordinator.device_mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device_name = "Test Mower"
    coordinator.device_model = "dreame.mower.test"
    coordinator.device_serial = "SN123"
    coordinator.device_manufacturer = "Dreametech™"
    coordinator.device_firmware = "1.0.0"
    coordinator.device_connected = True
    return coordinator


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

