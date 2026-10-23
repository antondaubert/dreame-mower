"""The battery of a mower over its mowing tasks.

While a task runs, every change of the battery level is kept with its time,
recharges in between included, so the work log can tell how much of a charge
each task took and show its course. Tasks from before the log began are
filled in once from Home Assistant's recorder: those it still keeps every
change of with their course, older ones with what its hourly statistics hold.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .config_flow import CONF_MAC
from .const import DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.property.mission_completion import MISSION_COMPLETION_EVENT_PROPERTY_NAME

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
# How long the course of a task is kept, in seconds.
KEEP_SECONDS = 400 * 24 * 3600
# How far apart the start of a task in the work log and the start of a
# recorded course may be, in seconds: the two clocks are not the same.
MATCH_SECONDS = 180
# How long the stored log may wait for a save while a task runs, in seconds.
SAVE_DELAY_SECONDS = 60
# A course left unfinished by a restart goes on when the task still runs and
# its last level is no older than this, in seconds; after a longer gap it may
# be another task that runs.
RESUME_SECONDS = 3600
# How long after its mowing time a task is taken to end when nothing says,
# in seconds: the way back to the station.
END_SLACK_SECONDS = 10 * 60

SOURCE_RECORDED = "recorded"
SOURCE_HISTORY = "history"
SOURCE_STATISTICS = "statistics"


def battery_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Where the battery log of an entry is kept."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.battery.{entry_id}")


def used_percent(samples: list[list[float]]) -> float:
    """How much of a charge a course took: every fall of the level counts,
    a rise (charging) does not."""
    used = 0.0
    for (_, before), (_, after) in zip(samples, samples[1:]):
        if after < before:
            used += before - after
    return used


class BatteryLog:
    """Keeps the course of the battery over the mowing tasks of one mower."""

    def __init__(self, hass: HomeAssistant, coordinator: DreameMowerCoordinator, entry: ConfigEntry) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._entry = entry
        self._store = battery_store(hass, entry.entry_id)
        # Oldest first; each {start, end, source, samples: [[seconds, percent]]}
        # or, from hourly statistics, {start, source, used} without a course.
        self.courses: list[dict[str, Any]] = []
        # Whether the tasks older than the recorder's detailed history were
        # filled in from its statistics, which happens once.
        self._backfilled = False
        self._backfilling = False
        # Tasks the detailed history was asked about already, since startup.
        self._asked: set[int] = set()
        self._backfill_failed = False
        # The course being recorded, while a task runs.
        self._current: dict[str, Any] | None = None
        # A course a restart left unfinished, until it is known whether its
        # task still runs.
        self._unfinished: dict[str, Any] | None = None
        self._unsubscribe: CALLBACK_TYPE | None = None
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        """Read the kept log."""
        data = await self._store.async_load() or {}
        self.courses = list(data.get("courses") or [])
        self._backfilled = bool(data.get("backfilled"))
        last = self.courses[-1] if self.courses else None
        if last is not None and last.get("source") == SOURCE_RECORDED and last.get("end") is None:
            self._unfinished = last

    @callback
    def async_start(self) -> None:
        """Follow the mower's battery, and the end of each task."""
        self._unsubscribe = self._coordinator.async_add_listener(self._async_updated)
        self._coordinator.device.register_property_callback(self._on_property)

    @callback
    def async_stop(self) -> None:
        """Stop following the mower; what was recorded is saved."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._coordinator.device.unregister_property_callback(self._on_property)
        self._listeners.clear()
        if self._current is not None:
            self._store.async_delay_save(self._data, 0)

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call `listener` whenever what the log tells about a task changes."""
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def course_for(self, start: int) -> dict[str, Any] | None:
        """The course kept for the task of the work log that started then."""
        best: dict[str, Any] | None = None
        for course in self.courses:
            distance = abs(course["start"] - start)
            if distance <= MATCH_SECONDS and (best is None or distance < abs(best["start"] - start)):
                best = course
        return best

    def summary(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """How much of a charge a task of the work log took, and per m² of
        what it mowed; None when nothing is known."""
        course = self.course_for(entry["start"])
        if course is None:
            return None
        used = course["used"] if "samples" not in course else used_percent(course["samples"])
        area = entry.get("area")
        return {
            "used": round(used, 1),
            "per_sqm": round(used / area, 3) if isinstance(area, (int, float)) and area > 0 else None,
            "source": course["source"],
        }

    def details(self, task: dict[str, Any]) -> dict[str, Any] | None:
        """What a task took of the battery, with its course where one is
        kept: [seconds since the start, percent]."""
        summary = self.summary(task)
        if summary is None:
            return None
        course = self.course_for(task["start"])
        return {**summary, "samples": (course or {}).get("samples")}

    def _on_property(self, name: str, value: Any) -> None:
        # Called from the mower's connection, which need not be the event loop.
        if name == MISSION_COMPLETION_EVENT_PROPERTY_NAME:
            self._hass.loop.call_soon_threadsafe(self._task_completed)

    @callback
    def _task_completed(self) -> None:
        """A task ended: its course ends too, also where the next task starts
        without the mower going idle in between."""
        current = self._current
        if current is not None:
            self._current = None
            self._finish(current)

    @callback
    def _async_updated(self) -> None:
        device = self._coordinator.device
        # Until the mower's first heartbeat, whether a task runs is not known.
        if device.robot_state is None:
            return
        active = bool(device.mowing_session_active)
        percent = device.battery_percent
        now = time.time()
        unfinished = self._unfinished
        if unfinished is not None:
            self._unfinished = None
            if active and now - _last_seen(unfinished) <= RESUME_SECONDS:
                self._current = unfinished
            else:
                # Its task ended while Home Assistant was away.
                self._finish(unfinished)
        if active and self._current is None:
            self._current = {"start": int(now), "end": None, "source": SOURCE_RECORDED, "samples": []}
            self.courses.append(self._current)
        current = self._current
        if current is None:
            return
        samples = current["samples"]
        # A level of 0 is one the mower has not reported yet.
        if isinstance(percent, (int, float)) and percent > 0 and (not samples or samples[-1][1] != percent):
            samples.append([int(now - current["start"]), percent])
            self._store.async_delay_save(self._data, SAVE_DELAY_SECONDS)
        if not active:
            self._current = None
            self._finish(current)

    @callback
    def _finish(self, course: dict[str, Any]) -> None:
        samples = course["samples"]
        course["end"] = course["start"] + (samples[-1][0] if samples else 0)
        self._prune()
        self._hass.async_create_task(self._store.async_save(self._data()), f"{DOMAIN} battery log save")
        self._notify()

    def _prune(self) -> None:
        keep_from = time.time() - KEEP_SECONDS
        self.courses = [course for course in self.courses if course["start"] >= keep_from]

    def _data(self) -> dict[str, Any]:
        return {"courses": self.courses, "backfilled": self._backfilled}

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    async def async_backfill(self, entries: list[dict[str, Any]]) -> None:
        """Fill in the tasks of the work log without a course from the
        recorder: those it still keeps every level of, whenever one is missing
        (a restart at its start, say), and older ones once from its hourly
        statistics. Nothing happens without a recorder."""
        if self._backfilling or not entries or "recorder" not in self._hass.config.components:
            return
        entity_id = er.async_get(self._hass).async_get_entity_id(
            "sensor", DOMAIN, f"{self._entry.data[CONF_MAC]}_battery"
        )
        if entity_id is None:
            return
        self._backfilling = True
        try:
            changed = await self._async_backfill(entity_id, entries)
        except Exception:  # noqa: BLE001 - the tasks recorded from now on are worth having all the same
            # Told once; the next reads try again quietly.
            log = _LOGGER.debug if self._backfill_failed else _LOGGER.exception
            log("Reading the battery history of %s failed", self._entry.title)
            self._backfill_failed = True
            return
        finally:
            self._backfilling = False
        if not changed:
            return
        self._prune()
        self.courses.sort(key=lambda course: course["start"])
        await self._store.async_save(self._data())
        self._notify()

    async def _async_backfill(self, entity_id: str, entries: list[dict[str, Any]]) -> bool:
        """Returns whether the log changed."""
        from homeassistant.helpers.recorder import get_instance

        recorder = get_instance(self._hass)
        now = time.time()
        kept_from = now - recorder.keep_days * 24 * 3600
        todo = [
            entry
            for entry in entries
            if self.course_for(entry["start"]) is None and entry["start"] >= now - KEEP_SECONDS
        ]
        recent = [entry for entry in todo if entry["start"] >= kept_from and entry["start"] not in self._asked]
        older = [] if self._backfilled else [entry for entry in todo if entry["start"] < kept_from]
        changed = False

        if recent:
            first = min(entry["start"] for entry in recent)
            levels = await recorder.async_add_executor_job(_recorded_levels, self._hass, entity_id, first, now)
            for entry in recent:
                self._asked.add(entry["start"])
                end = await self._async_task_end(entry)
                samples = _samples_between(levels, entry["start"], end)
                if len(samples) >= 2:
                    self.courses.append({"start": entry["start"], "end": end, "source": SOURCE_HISTORY, "samples": samples})
                    changed = True

        if not self._backfilled:
            self._backfilled = changed = True
        if older:
            first = min(entry["start"] for entry in older)
            hours = await recorder.async_add_executor_job(_hourly_levels, self._hass, entity_id, first - 3600, now)
            spans = {entry["start"]: _hour_span(entry) for entry in entries}
            for entry in older:
                first_hour, last_hour = spans[entry["start"]]
                # An hour shared with another task, the hour before included
                # (it gives the level a task starts from), tells nothing.
                span = (first_hour - 3600, last_hour)
                if any(other != entry["start"] and _overlap(span, spans[other]) for other in spans):
                    continue
                used = _used_from_hours(hours, entry["start"], entry["start"] + (entry.get("duration") or 0) * 60)
                # Nothing used over a task means the level was not followed then.
                if used:
                    self.courses.append({"start": entry["start"], "source": SOURCE_STATISTICS, "used": used})
        return changed

    async def _async_task_end(self, entry: dict[str, Any]) -> int:
        """When a task ended, recharges included: its file says, where it can
        be had; otherwise its mowing time and the way back."""
        fallback = entry["start"] + int(entry.get("duration") or 0) * 60 + END_SLACK_SECONDS
        file = entry.get("file")
        if not file:
            return fallback
        try:
            details = await self._hass.async_add_executor_job(self._coordinator.device.read_work_log_details, file)
        except Exception:  # noqa: BLE001 - a task without its file still has its mowing time
            return fallback
        end = (details or {}).get("end")
        return end if isinstance(end, int) and end > entry["start"] else fallback


def _recorded_levels(hass: HomeAssistant, entity_id: str, start: float, end: float) -> list[tuple[float, float]]:
    """Every level the recorder kept between two unix times, with the one
    before. Runs in the recorder's executor."""
    from homeassistant.components.recorder import history

    states = history.state_changes_during_period(
        hass,
        datetime.fromtimestamp(start, timezone.utc),
        datetime.fromtimestamp(end, timezone.utc),
        entity_id,
        no_attributes=True,
        include_start_time_state=True,
    )
    levels = []
    for state in states.get(entity_id, []):
        try:
            level = float(state.state)
        except ValueError:
            continue
        # A level of 0 is one the mower had not reported yet.
        if level > 0:
            levels.append((state.last_changed.timestamp(), level))
    return levels


def _hourly_levels(hass: HomeAssistant, entity_id: str, start: float, end: float) -> dict[int, tuple[float, float]]:
    """The lowest and highest level of each hour between two unix times, by
    the hour's start. Runs in the recorder's executor."""
    from homeassistant.components.recorder.statistics import statistics_during_period

    rows = statistics_during_period(
        hass,
        datetime.fromtimestamp(start, timezone.utc),
        datetime.fromtimestamp(end, timezone.utc),
        {entity_id},
        "hour",
        None,
        {"min", "max"},
    )
    hours = {}
    for row in rows.get(entity_id, []):
        low, high = row.get("min"), row.get("max")
        if low is not None and high is not None:
            hours[int(row["start"])] = (low, high)
    return hours


def _samples_between(levels: list[tuple[float, float]], start: int, end: int) -> list[list[float]]:
    """The course of a task from the levels the recorder kept: the level it
    started with, then every change until it ended."""
    before = [level for at, level in levels if at <= start]
    samples = [[0, before[-1]]] if before else []
    for at, level in levels:
        if start < at <= end and (not samples or samples[-1][1] != level):
            samples.append([int(at - start), level])
    return samples


def _last_seen(course: dict[str, Any]) -> int:
    """When the last level of a course came, as a unix time."""
    samples = course["samples"]
    start: int = course["start"]
    return start + (samples[-1][0] if samples else 0)


def _hour_span(entry: dict[str, Any]) -> tuple[int, int]:
    """The first and the last hour a task mowed in, by their starts."""
    start = entry["start"]
    end = start + int(entry.get("duration") or 0) * 60
    return start - start % 3600, end - end % 3600


def _overlap(one: tuple[int, int], other: tuple[int, int]) -> bool:
    return one[0] <= other[1] and other[0] <= one[1]


def _used_from_hours(hours: dict[int, tuple[float, float]], start: int, end: int) -> float | None:
    """How much of a charge a task took, from hourly lows and highs: from the
    highest level of its first hour, or the hour before, down to the lowest
    level while it mowed. A recharge in between is not seen."""
    first = start - start % 3600
    span = [hour for hour in range(first, end + 1, 3600) if hour in hours]
    if not span:
        return None
    top = max(hours[span[0]][1], hours.get(first - 3600, (0.0, 0.0))[1])
    low = min(hours[hour][0] for hour in span)
    return max(0.0, top - low)
