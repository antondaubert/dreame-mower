"""Tests for Dreame Mower button entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.button import DreameMowerGoToMaintenancePointButton
from custom_components.dreame_mower.dreame.device import DreameCommandError


def _make_coordinator():
    coordinator = MagicMock()
    coordinator.device_mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device_name = "Test Mower"
    coordinator.device_model = "dreame.mower.test"
    coordinator.device_serial = "SN123"
    coordinator.device_manufacturer = "Dreametech™"
    coordinator.device_firmware = "1.0.0"
    coordinator.device_connected = True
    coordinator.async_go_to_maintenance_point = AsyncMock(return_value=True)
    return coordinator


def _make_button(coordinator=None):
    """Build the entity without the base initializer's registration side-effects."""
    entity = DreameMowerGoToMaintenancePointButton.__new__(DreameMowerGoToMaintenancePointButton)
    entity.coordinator = coordinator or _make_coordinator()
    entity._entity_description_key = "go_to_maintenance_point"
    entity._attr_has_entity_name = True
    entity.hass = MagicMock()
    return entity


@pytest.mark.asyncio
async def test_pressing_sends_the_mower_to_the_maintenance_point():
    """One press is one run to the point the select holds."""
    coordinator = _make_coordinator()
    entity = _make_button(coordinator)

    await entity.async_press()

    coordinator.async_go_to_maintenance_point.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_a_refused_run_raises():
    """A mower that does not set off must not pass as a press that worked."""
    coordinator = _make_coordinator()
    coordinator.async_go_to_maintenance_point = AsyncMock(return_value=False)
    entity = _make_button(coordinator)

    with pytest.raises(HomeAssistantError):
        await entity.async_press()


@pytest.mark.asyncio
async def test_a_map_without_a_point_says_so():
    """The reason a press cannot work reaches the interface."""
    coordinator = _make_coordinator()
    coordinator.async_go_to_maintenance_point = AsyncMock(
        side_effect=ValueError("This map has no maintenance point to drive to")
    )
    entity = _make_button(coordinator)

    with pytest.raises(HomeAssistantError, match="no maintenance point"):
        await entity.async_press()


@pytest.mark.asyncio
async def test_a_command_the_mower_refused_keeps_its_reason():
    """A refusal from the mower is reported with what it said."""
    coordinator = _make_coordinator()
    coordinator.async_go_to_maintenance_point = AsyncMock(
        side_effect=DreameCommandError("Device is offline")
    )
    entity = _make_button(coordinator)

    with pytest.raises(HomeAssistantError, match="offline"):
        await entity.async_press()
