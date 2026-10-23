"""Tests for the battery log: the course of the battery over mowing tasks."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dreame_mower import battery_log
from custom_components.dreame_mower.battery_log import (
    BatteryLog,
    _samples_between,
    _used_from_hours,
    used_percent,
)
from custom_components.dreame_mower.config_flow import CONF_MAC
from custom_components.dreame_mower.const import DOMAIN

MAC = "11:22:33:44:55:66"
START = 1_792_749_600


class Clock:
    def __init__(self) -> None:
        self.now = float(START)

    def __call__(self) -> float:
        return self.now


class Coordinator:
    """What the battery log reads of the coordinator: the mower and its updates."""

    def __init__(self) -> None:
        self.callbacks: list[Any] = []
        self.device = SimpleNamespace(
            mowing_session_active=False,
            battery_percent=100,
            robot_state={"main_state": 0},
            read_work_log_details=lambda file: None,
            register_property_callback=self.callbacks.append,
            unregister_property_callback=self.callbacks.remove,
        )
        self.listeners: list[Any] = []

    def async_add_listener(self, listener: Any) -> Any:
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def update(self, **values: Any) -> None:
        for key, value in values.items():
            setattr(self.device, key, value)
        for listener in list(self.listeners):
            listener()


@pytest.fixture
def clock() -> Any:
    clock = Clock()
    with patch.object(battery_log.time, "time", clock):
        yield clock


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Robo", data={CONF_MAC: MAC}, entry_id="battery_entry")
    entry.add_to_hass(hass)
    return entry


async def _log(hass: HomeAssistant, coordinator: Coordinator, entry: MockConfigEntry) -> BatteryLog:
    log = BatteryLog(hass, coordinator, entry)  # type: ignore[arg-type]
    await log.async_load()
    log.async_start()
    return log


def _task(start: int = START, area: float = 68.4, **values: Any) -> dict[str, Any]:
    return {"start": start, "duration": 75, "area": area, "file": "ali_dreame/task.json", **values}


async def test_a_task_is_recorded_with_its_recharge(hass: HomeAssistant, clock: Clock, entry: MockConfigEntry, hass_storage: dict[str, Any]) -> None:
    coordinator = Coordinator()
    log = await _log(hass, coordinator, entry)
    changed: list[bool] = []
    log.add_listener(lambda: changed.append(True))

    coordinator.update(mowing_session_active=True, battery_percent=100)
    for minutes, percent in ((10, 90), (58, 15), (100, 95), (118, 79)):
        clock.now = START + minutes * 60
        coordinator.update(battery_percent=percent)
    # The same level again is no new sample.
    coordinator.update(battery_percent=79)
    clock.now = START + 120 * 60
    coordinator.update(mowing_session_active=False)
    await hass.async_block_till_done()

    (course,) = log.courses
    assert course["samples"] == [[0, 100], [600, 90], [3480, 15], [6000, 95], [7080, 79]]
    assert course["end"] == START + 7080
    assert changed == [True]
    assert log.summary(_task(START + 60)) == {"used": 101.0, "per_sqm": 1.477, "source": "recorded"}
    # Another task is not this one.
    assert log.summary(_task(START + 600)) is None
    assert hass_storage[f"{DOMAIN}.battery.{entry.entry_id}"]["data"]["courses"] == [course]


async def test_a_task_cut_off_by_a_restart_goes_on(hass: HomeAssistant, clock: Clock, entry: MockConfigEntry, hass_storage: dict[str, Any]) -> None:
    hass_storage[f"{DOMAIN}.battery.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.battery.{entry.entry_id}",
        "data": {"courses": [{"start": START, "end": None, "source": "recorded", "samples": [[0, 100], [600, 90]]}], "backfilled": True},
    }
    coordinator = Coordinator()
    log = await _log(hass, coordinator, entry)

    clock.now = START + 1200
    coordinator.update(mowing_session_active=True, battery_percent=80)
    clock.now = START + 1800
    coordinator.update(mowing_session_active=False, battery_percent=75)

    (course,) = log.courses
    assert course["samples"] == [[0, 100], [600, 90], [1200, 80], [1800, 75]]
    assert course["end"] == START + 1800


async def test_a_restart_waits_for_the_mower_to_say_whether_a_task_runs(
    hass: HomeAssistant, clock: Clock, entry: MockConfigEntry, hass_storage: dict[str, Any]
) -> None:
    hass_storage[f"{DOMAIN}.battery.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.battery.{entry.entry_id}",
        "data": {"courses": [{"start": START, "end": None, "source": "recorded", "samples": [[0, 100], [600, 90]]}], "backfilled": True},
    }
    coordinator = Coordinator()
    # No heartbeat yet, and no level either.
    coordinator.device.robot_state = None
    log = await _log(hass, coordinator, entry)

    clock.now = START + 900
    coordinator.update(battery_percent=0)
    coordinator.update(robot_state={"main_state": 1}, mowing_session_active=True)
    clock.now = START + 1200
    coordinator.update(battery_percent=80)

    (course,) = log.courses
    assert course["end"] is None
    assert course["samples"] == [[0, 100], [600, 90], [1200, 80]]


async def test_another_task_after_a_long_gap_gets_a_course_of_its_own(
    hass: HomeAssistant, clock: Clock, entry: MockConfigEntry, hass_storage: dict[str, Any]
) -> None:
    hass_storage[f"{DOMAIN}.battery.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.battery.{entry.entry_id}",
        "data": {"courses": [{"start": START, "end": None, "source": "recorded", "samples": [[0, 100], [600, 90]]}], "backfilled": True},
    }
    coordinator = Coordinator()
    log = await _log(hass, coordinator, entry)

    clock.now = START + 600 + 2 * 3600
    coordinator.update(mowing_session_active=True, battery_percent=100)

    first, second = log.courses
    assert first["end"] == START + 600
    assert second["start"] == START + 600 + 2 * 3600


async def test_a_finished_task_ends_its_course(hass: HomeAssistant, clock: Clock, entry: MockConfigEntry) -> None:
    coordinator = Coordinator()
    log = await _log(hass, coordinator, entry)
    coordinator.update(mowing_session_active=True, battery_percent=100)
    clock.now = START + 600
    coordinator.update(battery_percent=90)

    # The mower reports the task done and starts the next without going idle.
    for notify in coordinator.callbacks:
        notify("mission_completion_event", {})
    await hass.async_block_till_done()
    clock.now = START + 700
    coordinator.update(battery_percent=89)

    first, second = log.courses
    assert first["end"] == START + 600
    assert second["start"] == START + 700
    log.async_stop()
    assert coordinator.callbacks == [] and coordinator.listeners == []


async def test_a_task_that_ended_during_a_restart_is_closed(hass: HomeAssistant, clock: Clock, entry: MockConfigEntry, hass_storage: dict[str, Any]) -> None:
    hass_storage[f"{DOMAIN}.battery.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.battery.{entry.entry_id}",
        "data": {"courses": [{"start": START, "end": None, "source": "recorded", "samples": [[0, 100], [600, 90]]}], "backfilled": True},
    }
    coordinator = Coordinator()
    log = await _log(hass, coordinator, entry)

    clock.now = START + 7200
    coordinator.update(battery_percent=100)
    clock.now = START + 9000
    coordinator.update(mowing_session_active=True, battery_percent=100)

    first, second = log.courses
    assert first["end"] == START + 600
    assert second["start"] == START + 9000


async def test_courses_older_than_kept_are_dropped(hass: HomeAssistant, clock: Clock, entry: MockConfigEntry) -> None:
    coordinator = Coordinator()
    log = await _log(hass, coordinator, entry)
    log.courses = [{"start": START - battery_log.KEEP_SECONDS - 1, "source": "statistics", "used": 40}]

    coordinator.update(mowing_session_active=True)
    coordinator.update(mowing_session_active=False)

    assert [course["start"] for course in log.courses] == [START]


def test_only_falls_of_the_level_count_as_used() -> None:
    assert used_percent([[0, 100], [10, 60], [20, 90], [30, 80]]) == 50
    assert used_percent([[0, 100]]) == 0


def test_the_course_of_a_task_starts_with_the_level_before_it() -> None:
    levels = [(START - 600, 100.0), (START + 60, 99.0), (START + 120, 99.0), (START + 600, 90.0), (START + 9000, 80.0)]

    assert _samples_between(levels, START, START + 3600) == [[0, 100.0], [60, 99.0], [600, 90.0]]


def test_hourly_statistics_tell_what_a_task_took() -> None:
    hour = START - START % 3600
    hours = {hour - 3600: (100.0, 100.0), hour: (61.0, 100.0), hour + 3600: (55.0, 70.0)}

    assert _used_from_hours(hours, hour + 60, hour + 3600 + 600) == 45.0
    assert _used_from_hours(hours, hour + 7 * 3600, hour + 8 * 3600) is None


async def test_tasks_from_before_are_filled_in_once_from_the_recorder(
    hass: HomeAssistant, clock: Clock, entry: MockConfigEntry, hass_storage: dict[str, Any]
) -> None:
    hass.config.components.add("recorder")
    er.async_get(hass).async_get_or_create("sensor", DOMAIN, f"{MAC}_battery", config_entry=entry, suggested_object_id="robo_battery")
    coordinator = Coordinator()
    coordinator.device.read_work_log_details = lambda file: {"end": START + 3000}
    log = await _log(hass, coordinator, entry)
    clock.now = START + 86400
    recent, old = _task(START), _task(START - 30 * 86400, duration=40)
    asked: list[str] = []

    class Recorder:
        keep_days = 10

        async def async_add_executor_job(self, target: Any, *args: Any) -> Any:
            asked.append(target.__name__)
            return target(*args)

    old_hour = old["start"] - old["start"] % 3600

    def levels(hass: HomeAssistant, entity_id: str, start: float, end: float) -> list[tuple[float, float]]:
        assert entity_id == "sensor.robo_battery"
        return [(START - 60, 100.0), (START + 600, 90.0), (START + 2400, 60.0), (START + 4000, 100.0)]

    def hourly(hass: HomeAssistant, entity_id: str, start: float, end: float) -> dict[int, tuple[float, float]]:
        return {old_hour - 3600: (100.0, 100.0), old_hour: (62.0, 100.0)}

    missed = _task(START + 7200)
    with (
        patch("homeassistant.helpers.recorder.get_instance", return_value=Recorder()),
        patch.object(battery_log, "_recorded_levels", levels),
        patch.object(battery_log, "_hourly_levels", hourly),
    ):
        await log.async_backfill([recent, old])
        await log.async_backfill([recent, old])
        # A task missed later is looked up in the detailed history, once; the
        # statistics are not read again.
        await log.async_backfill([missed, recent, old])
        await log.async_backfill([missed, recent, old])

    assert asked == ["levels", "hourly", "levels"]
    assert log.summary(recent) == {"used": 40.0, "per_sqm": 0.585, "source": "history"}
    assert log.details(recent)["samples"] == [[0, 100.0], [600, 90.0], [2400, 60.0]]
    assert log.summary(old) == {"used": 38.0, "per_sqm": 0.556, "source": "statistics"}
    assert log.details(old)["samples"] is None
    assert hass_storage[f"{DOMAIN}.battery.{entry.entry_id}"]["data"]["backfilled"] is True


async def test_hourly_statistics_leave_out_what_they_cannot_tell(
    hass: HomeAssistant, clock: Clock, entry: MockConfigEntry
) -> None:
    hass.config.components.add("recorder")
    er.async_get(hass).async_get_or_create("sensor", DOMAIN, f"{MAC}_battery", config_entry=entry, suggested_object_id="robo_battery")
    log = await _log(hass, Coordinator(), entry)
    clock.now = START
    day = START - 30 * 86400
    hour = day - day % 3600
    # Two short tasks in one hour, one in the hour after them, and a task
    # while the level stood still.
    first, second, still = _task(hour + 60, duration=5), _task(hour + 1800, duration=5), _task(hour + 86400, duration=40)
    after = _task(hour + 3600 + 300, duration=20)

    class Recorder:
        keep_days = 10

        async def async_add_executor_job(self, target: Any, *args: Any) -> Any:
            return target(*args)

    def hourly(hass: HomeAssistant, entity_id: str, start: float, end: float) -> dict[int, tuple[float, float]]:
        return {
            hour - 3600: (100.0, 100.0),
            hour: (80.0, 100.0),
            hour + 3600: (60.0, 80.0),
            hour + 86400 - 3600: (100.0, 100.0),
            hour + 86400: (100.0, 100.0),
        }

    with (
        patch("homeassistant.helpers.recorder.get_instance", return_value=Recorder()),
        patch.object(battery_log, "_hourly_levels", hourly),
    ):
        await log.async_backfill([first, second, after, still])

    assert log.courses == []


async def test_a_failing_recorder_is_told_once(
    hass: HomeAssistant, clock: Clock, entry: MockConfigEntry, caplog: pytest.LogCaptureFixture
) -> None:
    hass.config.components.add("recorder")
    er.async_get(hass).async_get_or_create("sensor", DOMAIN, f"{MAC}_battery", config_entry=entry, suggested_object_id="robo_battery")
    log = await _log(hass, Coordinator(), entry)

    with patch("homeassistant.helpers.recorder.get_instance", side_effect=RuntimeError("no database")):
        await log.async_backfill([_task()])
        await log.async_backfill([_task()])

    assert caplog.text.count("Traceback") == 1
    assert log.courses == []


async def test_nothing_is_filled_in_without_a_recorder(hass: HomeAssistant, clock: Clock, entry: MockConfigEntry) -> None:
    log = await _log(hass, Coordinator(), entry)

    await log.async_backfill([_task()])

    assert log.courses == []
