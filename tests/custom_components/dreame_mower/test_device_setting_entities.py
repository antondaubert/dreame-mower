"""Tests for the entities of the on/off and choice settings of the mower's settings record."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.const import DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.select import DreameMowerNavigationPathSelect
from custom_components.dreame_mower.select import async_setup_entry as setup_selects
from custom_components.dreame_mower.switch import DreameMowerDeviceSettingSwitch
from custom_components.dreame_mower.switch import async_setup_entry as setup_switches

# The settings record of a mower with these settings.
_RECORD = {"FDP": 1, "PATH": False, "STUN": 0, "AOP": 1, "CLS": 0, "PROT": 0}


def _coordinator(record=None):
    record = dict(_RECORD) if record is None else record
    coordinator = MagicMock()
    coordinator.device_mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device_name = "Test Mower"
    coordinator.device_model = "dreame.mower.g2408"
    coordinator.device_serial = "SN123"
    coordinator.device_manufacturer = "Dreametech™"
    coordinator.device_firmware = "1.0.0"
    coordinator.device_setting = record.get
    coordinator.supports_device_setting = lambda key: key in record
    coordinator.supports_mowing_setting = lambda key: False
    coordinator.async_set_device_setting = AsyncMock(return_value=True)
    for flag in (
        "supports_charging_period",
        "supports_rain_protection",
        "supports_anti_theft",
        "supports_edge_mowing_settings",
        "supports_mowing_direction",
    ):
        setattr(coordinator, flag, False)
    coordinator.schedule_slots = [0]
    coordinator.async_when_probed = lambda add: add()
    return coordinator


async def _added(setup, coordinator):
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry"
    hass.data = {DOMAIN: {"entry": {DATA_COORDINATOR: coordinator}}}
    added = []
    await setup(hass, entry, added.extend)
    return added


@pytest.mark.asyncio
async def test_each_setting_the_record_carries_gets_its_entity():
    switches = [entity for entity in await _added(setup_switches, _coordinator()) if isinstance(entity, DreameMowerDeviceSettingSwitch)]
    assert sorted(entity._key for entity in switches) == ["AOP", "CLS", "FDP", "PATH", "STUN"]
    selects = await _added(setup_selects, _coordinator())
    assert any(isinstance(entity, DreameMowerNavigationPathSelect) for entity in selects)


@pytest.mark.asyncio
async def test_a_record_without_the_settings_gets_none_of_them():
    switches = await _added(setup_switches, _coordinator({}))
    assert not any(isinstance(entity, DreameMowerDeviceSettingSwitch) for entity in switches)
    selects = await _added(setup_selects, _coordinator({}))
    assert not any(isinstance(entity, DreameMowerNavigationPathSelect) for entity in selects)


def test_the_switches_show_the_record():
    coordinator = _coordinator()

    assert DreameMowerDeviceSettingSwitch(coordinator, "FDP", "frost_protection", "mdi:x").is_on is True
    # The mower reports this one as a boolean.
    assert DreameMowerDeviceSettingSwitch(coordinator, "PATH", "path_obstacle_avoidance", "mdi:x").is_on is False
    assert DreameMowerDeviceSettingSwitch(_coordinator({}), "CLS", "child_lock", "mdi:x").is_on is None


@pytest.mark.asyncio
async def test_a_switch_writes_its_setting_as_a_number():
    coordinator = _coordinator()

    await DreameMowerDeviceSettingSwitch(coordinator, "CLS", "child_lock", "mdi:x").async_turn_on()
    coordinator.async_set_device_setting.assert_awaited_with("CLS", {"value": 1})
    await DreameMowerDeviceSettingSwitch(coordinator, "PATH", "path_obstacle_avoidance", "mdi:x").async_turn_off()
    coordinator.async_set_device_setting.assert_awaited_with("PATH", {"value": 0})

    coordinator.async_set_device_setting = AsyncMock(return_value=False)
    with pytest.raises(HomeAssistantError):
        await DreameMowerDeviceSettingSwitch(coordinator, "CLS", "child_lock", "mdi:x").async_turn_on()


@pytest.mark.asyncio
async def test_the_navigation_path_is_one_of_two():
    coordinator = _coordinator()
    select = DreameMowerNavigationPathSelect(coordinator)

    assert select.options == ["Direct path", "Smart path"]
    assert select.current_option == "Direct path"
    await select.async_select_option("Smart path")
    coordinator.async_set_device_setting.assert_awaited_once_with("PROT", {"value": 1})
    with pytest.raises(ValueError):
        await select.async_select_option("Scenic route")



@pytest.mark.parametrize("value,shown", [(1, "Smart path"), (True, "Smart path"), (2, None), ([0, 1], None)])
def test_the_navigation_path_shows_only_what_it_knows(value, shown):
    assert DreameMowerNavigationPathSelect(_coordinator(dict(_RECORD, PROT=value))).current_option == shown


def test_the_new_entities_carry_the_translation_keys_the_card_looks_for():
    assert DreameMowerNavigationPathSelect(_coordinator()).translation_key == "navigation_path"
    assert DreameMowerDeviceSettingSwitch(_coordinator(), "CLS", "child_lock", "mdi:x").translation_key == "child_lock"
