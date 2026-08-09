"""Tests for Dreame Mower integration setup."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dreame_mower import async_setup_entry
from custom_components.dreame_mower.config_flow import (
    CONF_ACCOUNT_TYPE,
    CONF_COUNTRY,
    CONF_DID,
    CONF_MAC,
    CONF_MODEL,
    CONF_SERIAL,
    DEVICE_TYPE_SWBOT,
)
from custom_components.dreame_mower.const import (
    DATA_COORDINATOR,
    DOMAIN,
    RAIN_POLL_INTERVAL_SECONDS,
)


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Mower",
        data={
            CONF_NAME: "Test Mower",
            CONF_MAC: "11:22:33:44:55:66",
            CONF_MODEL: "dreame.mower.test789",
            CONF_SERIAL: "MIN123456",
            CONF_DID: "test_device_456",
            CONF_USERNAME: "test_user",
            CONF_PASSWORD: "test_password",
            CONF_ACCOUNT_TYPE: "dreame",
            CONF_COUNTRY: "eu",
        },
        entry_id="test_init_entry",
    )


def _make_coordinator() -> MagicMock:
    """Build a mower coordinator stub whose awaited calls are real coroutines.

    Every method setup awaits has to be an AsyncMock: a bare MagicMock would
    raise TypeError, which setup swallows, so the assertions below would pass
    without the call ever having happened.
    """
    coordinator = MagicMock()
    coordinator.device_type = "mower"
    coordinator.supports_cutting_height = True
    coordinator.device = MagicMock()
    coordinator.device.fetch_vector_map = MagicMock(return_value=True)
    coordinator.async_connect_device = AsyncMock(return_value=True)
    coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)
    coordinator.async_request_refresh = AsyncMock(return_value=None)
    coordinator.async_fetch_consumable_data = AsyncMock(return_value=None)
    coordinator.async_fetch_mowing_preferences = AsyncMock(return_value=True)
    coordinator.async_fetch_device_settings = AsyncMock(return_value=None)
    coordinator.supports_rain_protection = True
    coordinator.async_fetch_firmware_status = AsyncMock(return_value=None)
    coordinator.async_update_online_status = AsyncMock(return_value=None)
    return coordinator


async def test_async_setup_entry_fetches_vector_map_for_mowers(hass):
    """Mower setup should preload vector map data before entity setup."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    coordinator = _make_coordinator()

    with patch("custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=None),
    ) as forward_entry_setups:
        assert await async_setup_entry(hass, entry) is True

    coordinator.async_connect_device.assert_awaited_once()
    coordinator.device.fetch_vector_map.assert_called_once_with()
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    coordinator.async_request_refresh.assert_awaited_once()
    coordinator.async_fetch_mowing_preferences.assert_awaited_once()
    coordinator.async_fetch_device_settings.assert_awaited_once()
    forward_entry_setups.assert_awaited_once()
    assert hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR] is coordinator


async def test_async_setup_entry_reads_the_preferences_of_fixed_height_models(hass):
    """A model with a manual height dial still keeps the other mowing settings."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    coordinator = _make_coordinator()
    coordinator.supports_cutting_height = False

    with patch("custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=None),
    ):
        assert await async_setup_entry(hass, entry) is True

    coordinator.async_fetch_mowing_preferences.assert_awaited_once()


async def test_async_setup_entry_raises_not_ready_on_connect_failure(hass):
    """A failed device connection should raise ConfigEntryNotReady so HA retries."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.device_type = "mower"
    coordinator.name = "Test Mower"
    coordinator.async_connect_device = AsyncMock(return_value=False)
    coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)

    with patch(
        "custom_components.dreame_mower.DreameMowerCoordinator",
        return_value=coordinator,
    ), pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    coordinator.async_connect_device.assert_awaited_once()
    coordinator.async_config_entry_first_refresh.assert_not_awaited()
    assert DOMAIN not in hass.data or entry.entry_id not in hass.data.get(DOMAIN, {})

async def _setup_with(hass, coordinator):
    """Run setup with a stubbed coordinator and report the registered intervals."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None)
    ), patch(
        "custom_components.dreame_mower.async_track_time_interval"
    ) as track_time_interval:
        assert await async_setup_entry(hass, entry) is True

    return [call.args[2] for call in track_time_interval.call_args_list]


async def test_async_setup_entry_polls_the_rain_state(hass):
    """Neither the settings nor the resume time are pushed, so setup has to poll."""
    intervals = await _setup_with(hass, _make_coordinator())

    assert timedelta(seconds=RAIN_POLL_INTERVAL_SECONDS) in intervals


async def test_async_setup_entry_skips_the_rain_poll_when_unsupported(hass):
    """A device with no rain protection must not be polled about it."""
    coordinator = _make_coordinator()
    coordinator.supports_rain_protection = False

    intervals = await _setup_with(hass, coordinator)

    assert timedelta(seconds=RAIN_POLL_INTERVAL_SECONDS) not in intervals


async def test_async_setup_entry_skips_the_settings_fetch_for_swbot(hass):
    """Sweeping robots keep none of the settings this record carries."""
    coordinator = _make_coordinator()
    coordinator.device_type = DEVICE_TYPE_SWBOT
    coordinator.supports_rain_protection = False

    await _setup_with(hass, coordinator)

    coordinator.async_fetch_device_settings.assert_not_awaited()
