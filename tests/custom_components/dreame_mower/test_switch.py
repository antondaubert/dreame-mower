"""Tests for Dreame Mower switch entities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.const import DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.dreame.device import DreameCommandError
from custom_components.dreame_mower.switch import (
    DreameMowerAntiTheftPinCheckSwitch,
    DreameMowerAutomaticEdgeMowingSwitch,
    DreameMowerChargingPeriodSwitch,
    DreameMowerEdgeBladeOffsetSwitch,
    DreameMowerLiftAlarmSwitch,
    DreameMowerLocationReportingSwitch,
    DreameMowerOffMapAlarmSwitch,
    DreameMowerRainProtectionSwitch,
    DreameMowerSafeEdgeMowingSwitch,
    DreameMowerScheduleSwitch,
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
    coordinator.supports_anti_theft = False
    coordinator.supports_anti_theft_pin_check = False
    coordinator.supports_edge_mowing_settings = False
    coordinator.supports_safe_edge_mowing = False
    coordinator.supports_schedules = False
    coordinator.schedule_slots = []
    coordinator.schedule = lambda slot: None
    coordinator.schedule_enabled = lambda slot: None
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


async def _setup_entry_without_schedules(coordinator):
    """Set up the platform and drop the schedule switches every mower gets."""
    return [
        entity
        for entity in await _setup_entry(coordinator)
        if not isinstance(entity, DreameMowerScheduleSwitch)
    ]


@pytest.mark.asyncio
async def test_setup_adds_the_charging_period_switch():
    """A device that reports charging settings gets the switch."""
    entities = await _setup_entry_without_schedules(_make_coordinator())

    assert len(entities) == 1
    assert isinstance(entities[0], DreameMowerChargingPeriodSwitch)


@pytest.mark.asyncio
async def test_setup_skips_devices_without_charging_settings():
    """Devices that never reported the settings must not get the switch."""
    entities = await _setup_entry_without_schedules(_make_coordinator(supported=False))

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
    entities = await _setup_entry_without_schedules(_make_rain_coordinator())

    assert len(entities) == 1
    assert isinstance(entities[0], DreameMowerRainProtectionSwitch)


@pytest.mark.asyncio
async def test_setup_skips_devices_without_rain_settings():
    """Devices that never reported the settings must not get the switch."""
    assert await _setup_entry_without_schedules(_make_rain_coordinator(supported=False)) == []


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
    entities = await _setup_entry_without_schedules(_make_edge_coordinator())

    assert [type(entity) for entity in entities] == [
        DreameMowerAutomaticEdgeMowingSwitch,
        DreameMowerEdgeBladeOffsetSwitch,
        DreameMowerSafeEdgeMowingSwitch,
    ]


@pytest.mark.asyncio
async def test_setup_skips_safe_edge_mowing_when_the_device_has_no_such_setting():
    """Firmware without safe edge mowing must not get a switch that cannot write."""
    entities = await _setup_entry_without_schedules(_make_edge_coordinator(safe_supported=False))

    assert [type(entity) for entity in entities] == [
        DreameMowerAutomaticEdgeMowingSwitch,
        DreameMowerEdgeBladeOffsetSwitch,
    ]


@pytest.mark.asyncio
async def test_setup_skips_the_edge_switches_without_mowing_settings():
    """Devices whose mowing settings were never read must not get the switches."""
    assert await _setup_entry_without_schedules(_make_edge_coordinator(supported=False)) == []


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


def _make_anti_theft_coordinator(supported=True, pin_check_supported=False, settings=None):
    coordinator = _make_coordinator()
    coordinator.supports_charging_period = False
    coordinator.supports_anti_theft = supported
    coordinator.supports_anti_theft_pin_check = pin_check_supported
    state = {
        "lift_alarm_enabled": False,
        "off_map_alarm_enabled": False,
        "location_reporting_enabled": True,
        "anti_theft_pin_check_enabled": None,
        **(settings or {}),
    }
    coordinator.lift_alarm_enabled = state["lift_alarm_enabled"]
    coordinator.off_map_alarm_enabled = state["off_map_alarm_enabled"]
    coordinator.location_reporting_enabled = state["location_reporting_enabled"]
    coordinator.anti_theft_pin_check_enabled = state["anti_theft_pin_check_enabled"]
    coordinator.async_set_anti_theft_settings = AsyncMock(return_value=True)
    coordinator.link_module_plan_valid = True
    return coordinator


@pytest.mark.asyncio
async def test_setup_adds_the_anti_theft_switches():
    """A device that reports anti-theft settings gets a switch per setting."""
    entities = await _setup_entry_without_schedules(_make_anti_theft_coordinator())

    assert [type(entity) for entity in entities] == [
        DreameMowerLiftAlarmSwitch,
        DreameMowerOffMapAlarmSwitch,
        DreameMowerLocationReportingSwitch,
    ]


@pytest.mark.asyncio
async def test_setup_adds_the_pin_check_switch_where_the_mower_keeps_one():
    """Only a mower that asks for a PIN before power-off gets that switch."""
    entities = await _setup_entry_without_schedules(
        _make_anti_theft_coordinator(
            pin_check_supported=True,
            settings={"anti_theft_pin_check_enabled": True},
        )
    )

    assert isinstance(entities[-1], DreameMowerAntiTheftPinCheckSwitch)
    assert entities[-1].is_on is True


@pytest.mark.asyncio
async def test_setup_skips_devices_without_anti_theft_settings():
    """Devices that never reported the settings must not get the switches."""
    assert await _setup_entry_without_schedules(_make_anti_theft_coordinator(supported=False)) == []


@pytest.mark.asyncio
async def test_the_anti_theft_switches_report_their_own_setting():
    """Each switch has to read the setting it drives, not one of the others."""
    entities = await _setup_entry_without_schedules(
        _make_anti_theft_coordinator(settings={"lift_alarm_enabled": True})
    )

    assert [entity.is_on for entity in entities] == [True, False, True]


@pytest.mark.asyncio
async def test_the_anti_theft_switches_are_unknown_until_the_settings_are_read():
    """Unread settings leave the switches without a state."""
    coordinator = _make_anti_theft_coordinator(
        settings={
            "lift_alarm_enabled": None,
            "off_map_alarm_enabled": None,
            "location_reporting_enabled": None,
        }
    )

    assert [
        entity.is_on for entity in await _setup_entry_without_schedules(coordinator)
    ] == [None, None, None]


@pytest.mark.asyncio
async def test_switching_an_anti_theft_setting_leaves_the_others_alone():
    """A switch names only its own setting, so the device keeps the others."""
    coordinator = _make_anti_theft_coordinator()
    entity = DreameMowerOffMapAlarmSwitch(coordinator)
    entity.hass = MagicMock()

    await entity.async_turn_on()
    coordinator.async_set_anti_theft_settings.assert_awaited_once_with(off_map_alarm=True)

    coordinator.async_set_anti_theft_settings.reset_mock()
    await entity.async_turn_off()
    coordinator.async_set_anti_theft_settings.assert_awaited_once_with(off_map_alarm=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("switch_class", [
    DreameMowerOffMapAlarmSwitch,
    DreameMowerLocationReportingSwitch,
])
async def test_a_rejected_write_names_the_module_the_setting_needs(switch_class):
    """Without a usable cellular module, that is the first thing to check."""
    coordinator = _make_anti_theft_coordinator()
    coordinator.async_set_anti_theft_settings = AsyncMock(return_value=False)
    coordinator.link_module_plan_valid = False
    entity = switch_class(coordinator)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="cellular module"):
        await entity.async_turn_on()


@pytest.mark.asyncio
async def test_a_rejected_write_stays_quiet_about_a_module_that_is_fine():
    """A mower with a usable module was refused for some other reason."""
    coordinator = _make_anti_theft_coordinator()
    coordinator.async_set_anti_theft_settings = AsyncMock(return_value=False)
    entity = DreameMowerOffMapAlarmSwitch(coordinator)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError) as error:
        await entity.async_turn_on()

    assert "cellular module" not in str(error.value)


@pytest.mark.asyncio
async def test_a_rejected_lift_alarm_write_never_mentions_the_module():
    """The lift alarm works on the mower itself, module or not."""
    coordinator = _make_anti_theft_coordinator()
    coordinator.async_set_anti_theft_settings = AsyncMock(return_value=False)
    coordinator.link_module_plan_valid = False
    entity = DreameMowerLiftAlarmSwitch(coordinator)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError) as error:
        await entity.async_turn_on()

    assert "cellular module" not in str(error.value)


@pytest.mark.asyncio
async def test_switching_an_anti_theft_setting_raises_when_the_device_rejects_it():
    """A rejected write should surface as an error instead of passing silently."""
    coordinator = _make_anti_theft_coordinator()
    coordinator.async_set_anti_theft_settings = AsyncMock(return_value=False)
    entity = DreameMowerLiftAlarmSwitch(coordinator)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()


@pytest.mark.asyncio
async def test_switching_an_anti_theft_setting_raises_when_the_mower_lacks_it():
    """A setting the mower does not keep must surface as an error, not a silent pass."""
    coordinator = _make_anti_theft_coordinator(pin_check_supported=True)
    coordinator.async_set_anti_theft_settings = AsyncMock(
        side_effect=ValueError("This mower does not ask for a PIN code before it is switched off")
    )
    entity = DreameMowerAntiTheftPinCheckSwitch(coordinator)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()

def _make_schedule_coordinator(schedules=None):
    coordinator = _make_coordinator()
    coordinator.supports_charging_period = False
    served_schedules = [
        {"slot": 0, "enabled": True, "name": "Summer", "tasks": [{"week_day": "monday", "type": "all_area", "start_time": 480}]},
        {"slot": 1, "enabled": False, "name": None, "tasks": []},
    ] if schedules is None else schedules
    coordinator.supports_schedules = True
    coordinator.schedule_slots = [schedule["slot"] for schedule in served_schedules]
    coordinator.schedules = served_schedules
    coordinator.schedule = lambda slot: next(
        (schedule for schedule in served_schedules if schedule["slot"] == slot), None
    )
    coordinator.schedule_enabled = lambda slot: (
        None if coordinator.schedule(slot) is None else bool(coordinator.schedule(slot)["enabled"])
    )
    coordinator.current_map_id = 1
    coordinator.async_set_schedule_enabled = AsyncMock(return_value=True)
    return coordinator


@pytest.mark.asyncio
async def test_setup_adds_a_switch_per_schedule_slot():
    """Every schedule slot the map holds gets its own switch."""
    entities = await _setup_entry(_make_schedule_coordinator())

    assert [type(entity) for entity in entities] == [
        DreameMowerScheduleSwitch,
        DreameMowerScheduleSwitch,
    ]
    assert [entity.unique_id for entity in entities] == [
        "AA:BB:CC:DD:EE:FF_schedule_1",
        "AA:BB:CC:DD:EE:FF_schedule_2",
    ]
    assert [entity.translation_placeholders for entity in entities] == [
        {"number": "1"},
        {"number": "2"},
    ]


@pytest.mark.asyncio
async def test_setup_adds_the_schedule_switches_before_they_could_be_read():
    """Every mower keeps schedules, so a failed read must not cost the switches.

    They report unavailable until a read lands, which the poll takes care of
    without the user having to reload the integration.
    """
    entities = await _setup_entry(_make_coordinator(supported=False))

    assert [type(entity) for entity in entities] == [
        DreameMowerScheduleSwitch,
        DreameMowerScheduleSwitch,
    ]
    assert [entity.is_on for entity in entities] == [None, None]
    assert [entity.available for entity in entities] == [False, False]


@pytest.mark.asyncio
async def test_the_schedule_switches_report_which_schedule_is_on():
    """Each switch mirrors the state of the slot it stands for."""
    entities = await _setup_entry(_make_schedule_coordinator())

    assert [entity.is_on for entity in entities] == [True, False]


@pytest.mark.asyncio
async def test_the_schedule_switch_reports_the_name_and_the_tasks():
    """The attributes describe what the schedule holds."""
    entity = DreameMowerScheduleSwitch(_make_schedule_coordinator(), 0)

    assert entity.extra_state_attributes == {
        "schedule_name": "Summer",
        "map_id": 1,
        "tasks": [{"week_day": "monday", "type": "all_area", "start_time": 480}],
    }


@pytest.mark.asyncio
async def test_a_schedule_switch_of_a_slot_the_map_lost_goes_unavailable():
    """A map that holds fewer slots leaves the switches of the missing ones without state."""
    coordinator = _make_schedule_coordinator(
        schedules=[{"slot": 0, "enabled": False, "name": None, "tasks": []}]
    )
    entity = DreameMowerScheduleSwitch(coordinator, 1)

    assert entity.available is False
    assert entity.extra_state_attributes == {}


@pytest.mark.asyncio
async def test_switching_a_schedule_names_its_own_slot():
    """A switch only ever addresses the slot it stands for."""
    coordinator = _make_schedule_coordinator()
    entity = DreameMowerScheduleSwitch(coordinator, 1)
    entity.hass = MagicMock()

    await entity.async_turn_on()
    coordinator.async_set_schedule_enabled.assert_awaited_once_with(1, True)

    coordinator.async_set_schedule_enabled.reset_mock()
    await entity.async_turn_off()
    coordinator.async_set_schedule_enabled.assert_awaited_once_with(1, False)


@pytest.mark.asyncio
async def test_switching_a_schedule_raises_when_the_device_rejects_it():
    """A rejected write should surface as an error instead of passing silently."""
    coordinator = _make_schedule_coordinator()
    coordinator.async_set_schedule_enabled = AsyncMock(return_value=False)
    entity = DreameMowerScheduleSwitch(coordinator, 0)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="schedule 1"):
        await entity.async_turn_on()


@pytest.mark.asyncio
async def test_switching_on_an_empty_schedule_raises():
    """A schedule without tasks has nothing to run, which must not pass silently."""
    coordinator = _make_schedule_coordinator()
    coordinator.async_set_schedule_enabled = AsyncMock(
        side_effect=ValueError("The schedule in slot 1 holds no tasks to run")
    )
    entity = DreameMowerScheduleSwitch(coordinator, 1)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="no tasks"):
        await entity.async_turn_on()


# The entity name falls back to the translated one, which only resolves once the
# entity sits on a platform holding the translations.
_SCHEDULE_NAME_KEY = "component.dreame_mower.entity.switch.schedule.name"

# Home Assistant keeps the user's language for the displayed name and English for
# the entity ID, so the two differ here on purpose.
_SCHEDULE_NAME_TRANSLATIONS = {_SCHEDULE_NAME_KEY: "Zeitplan {number}"}
_SCHEDULE_OBJECT_ID_TRANSLATIONS = {_SCHEDULE_NAME_KEY: "Schedule {number}"}


def _on_platform(entity):
    """Attach an entity to a stub platform so its translated name resolves."""
    entity.platform_data = SimpleNamespace(
        platform_name="dreame_mower",
        domain="switch",
        platform_translations=_SCHEDULE_NAME_TRANSLATIONS,
        object_id_platform_translations=_SCHEDULE_OBJECT_ID_TRANSLATIONS,
        component_translations={},
    )
    return entity


def test_a_schedule_switch_is_named_after_the_schedule():
    """The name the mower stores is what the schedule is called in the app."""
    coordinator = _make_schedule_coordinator()

    entity = _on_platform(DreameMowerScheduleSwitch(coordinator, 0))

    assert entity.name == "Summer"


def test_an_unnamed_schedule_switch_falls_back_to_its_slot():
    """A map the mower holds no saved schedule for leaves the slot to stand in."""
    entities = [
        _on_platform(DreameMowerScheduleSwitch(_make_schedule_coordinator(), slot))
        for slot in (0, 1)
    ]

    # Slot 0 carries a name, slot 1 does not.
    assert [entity.name for entity in entities] == ["Summer", "Zeitplan 2"]


def test_a_schedule_switch_of_a_missing_slot_falls_back_to_its_slot():
    """A switch whose slot the active map lost still has to answer with a name."""
    coordinator = _make_schedule_coordinator(
        schedules=[{"slot": 0, "enabled": False, "name": None, "tasks": []}]
    )

    entity = _on_platform(DreameMowerScheduleSwitch(coordinator, 1))

    assert entity.name == "Zeitplan 2"


def test_the_schedule_entity_id_follows_the_slot_not_the_name():
    """The entity ID has to stay put when the schedule is renamed or the app differs.

    Home Assistant builds it from the entity name unless told otherwise, and that
    name is whatever language the schedule was saved in.
    """
    entity = _on_platform(DreameMowerScheduleSwitch(_make_schedule_coordinator(), 0))

    assert entity.name == "Summer"
    assert entity.suggested_object_id == "Schedule 1"


def test_an_unnamed_schedule_keeps_the_same_entity_id():
    """A slot with no stored name must land on the same entity ID as a named one."""
    coordinator = _make_schedule_coordinator()

    assert _on_platform(DreameMowerScheduleSwitch(coordinator, 1)).suggested_object_id == "Schedule 2"


def test_the_schedule_tasks_are_kept_out_of_the_recorder():
    """The tasks are a nested structure with nothing worth recording over time."""
    assert "tasks" in DreameMowerScheduleSwitch._unrecorded_attributes


@pytest.mark.asyncio
async def test_switching_an_anti_theft_setting_reports_why_it_never_reached_the_mower():
    """A command that never completed reaches the interface with the reason it gave."""
    coordinator = _make_anti_theft_coordinator()
    coordinator.async_set_anti_theft_settings = AsyncMock(
        side_effect=DreameCommandError(
            "Failed to send the anti-theft settings write command: Device offline"
        )
    )
    entity = DreameMowerLiftAlarmSwitch(coordinator)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="Device offline"):
        await entity.async_turn_on()


@pytest.mark.asyncio
async def test_switching_a_schedule_reports_why_it_never_reached_the_mower():
    """A schedule that could not be switched says why rather than only that it failed."""
    coordinator = _make_schedule_coordinator()
    coordinator.async_set_schedule_enabled = AsyncMock(
        side_effect=DreameCommandError(
            "Failed to send the schedule state write command: Cloud API error 5: timeout"
        )
    )
    entity = DreameMowerScheduleSwitch(coordinator, 0)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="Cloud API error 5: timeout"):
        await entity.async_turn_off()


@pytest.mark.asyncio
async def test_switching_the_charging_period_reports_why_it_never_reached_the_mower():
    """The charging period switch passes the reason on like the other switches do."""
    coordinator = _make_coordinator()
    coordinator.async_set_charging_period = AsyncMock(
        side_effect=DreameCommandError(
            "Failed to send the charging period write command: No response from cloud API"
        )
    )
    entity = DreameMowerChargingPeriodSwitch(coordinator)
    entity.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="No response from cloud API"):
        await entity.async_turn_on()
