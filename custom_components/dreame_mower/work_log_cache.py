"""The work log of a mower, kept between Home Assistant restarts.

The card shows the tasks kept here at once and receives what a read of the
cloud adds meanwhile. Reads after the first one ask only for the tasks since
shortly before the newest one kept, and a task the mower reports as finished
is read soon after, so the log is usually current before anyone opens it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import datetime
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .battery_log import BatteryLog
from .const import DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.property.mission_completion import MISSION_COMPLETION_EVENT_PROPERTY_NAME

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# How far back the work log goes when the mower does not say since when it
# counts, in seconds.
FALLBACK_SECONDS = 180 * 24 * 3600
# How far before the newest kept task a read starts, in seconds: a task can
# still change after it was first listed.
OVERLAP_SECONDS = 7 * 24 * 3600
# How long after the mower reports a finished task its entry is read, in
# seconds, so the cloud has it by then.
COMPLETION_DELAY_SECONDS = 30

UNAVAILABLE = "The work log is not available right now"


def work_log_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Where the work log of an entry is kept."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.work_log.{entry_id}")


def merge_entries(kept: list[dict[str, Any]], read: list[dict[str, Any]], start: int | None) -> list[dict[str, Any]]:
    """The kept tasks updated with those just read, newest first; a task is
    known by its start. Tasks before the start of the log, when the mower
    says where it starts, are dropped."""
    by_start = {entry["start"]: entry for entry in kept}
    by_start.update((entry["start"], entry) for entry in read)
    return sorted(
        (entry for entry in by_start.values() if start is None or entry["start"] >= start),
        key=lambda entry: entry["start"],
        reverse=True,
    )


class WorkLogCache:
    """Keeps the work log of one mower and tells followers when it changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DreameMowerCoordinator,
        entry: ConfigEntry,
        battery: BatteryLog | None = None,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        # What the battery did over the tasks, where it is followed.
        self.battery = battery
        self._unsubscribe_battery: CALLBACK_TYPE | None = None
        self._store = work_log_store(hass, entry.entry_id)
        self.totals: dict[str, Any] | None = None
        self.entries: list[dict[str, Any]] = []
        # Whether a read of the cloud is under way, and why the last one failed.
        self.refreshing = False
        self.error: str | None = None
        # Since when the log was read in full, as a unix time.
        self._covered_since: int | None = None
        self._refresh: asyncio.Task[None] | None = None
        self._cancel_completion: CALLBACK_TYPE | None = None
        self._listeners: list[Callable[[], None]] = []
        self._closers: list[Callable[[], None]] = []
        self._stopped = False

    async def async_load(self) -> None:
        """Read the kept log; its tasks may be opened right away."""
        data = await self._store.async_load() or {}
        self.totals = data.get("totals")
        self.entries = list(data.get("entries") or [])
        self._covered_since = data.get("covered_since")
        self._coordinator.device.remember_work_log_files(_files(self.entries))

    @callback
    def async_start(self) -> None:
        """Follow the mower for finished tasks, and the battery over them."""
        self._coordinator.device.register_property_callback(self._on_property)
        if self.battery is not None:
            self._unsubscribe_battery = self.battery.add_listener(self._notify)

    @callback
    def async_stop(self) -> None:
        """Stop following the mower and close the followers."""
        self._stopped = True
        self._coordinator.device.unregister_property_callback(self._on_property)
        if self._unsubscribe_battery is not None:
            self._unsubscribe_battery()
            self._unsubscribe_battery = None
        if self._cancel_completion is not None:
            self._cancel_completion()
            self._cancel_completion = None
        if self._refresh is not None and not self._refresh.done():
            self._refresh.cancel()
        closers, self._closers = self._closers, []
        self._listeners.clear()
        for closer in closers:
            closer()

    @callback
    def add_listener(self, listener: Callable[[], None], on_close: Callable[[], None] | None = None) -> Callable[[], None]:
        """Call `listener` whenever the log changes, and `on_close` when it stops (an entry reload)."""
        self._listeners.append(listener)
        if on_close is not None:
            self._closers.append(on_close)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)
            if on_close is not None and on_close in self._closers:
                self._closers.remove(on_close)

        return remove

    @callback
    def async_request_refresh(self) -> asyncio.Task[None]:
        """Read the cloud for new tasks, unless a read is under way already."""
        if self._refresh is None or self._refresh.done():
            self.refreshing = True
            self.error = None
            self._notify()
            self._refresh = self._hass.async_create_task(self._async_refresh(), f"{DOMAIN} work log refresh")
        return self._refresh

    def _on_property(self, name: str, value: Any) -> None:
        # Called from the mower's connection, which need not be the event loop.
        if name == MISSION_COMPLETION_EVENT_PROPERTY_NAME and not self._stopped:
            self._hass.loop.call_soon_threadsafe(self._completion_reported)

    @callback
    def _completion_reported(self) -> None:
        if self._stopped:
            return
        if self._cancel_completion is not None:
            self._cancel_completion()
        self._cancel_completion = async_call_later(self._hass, COMPLETION_DELAY_SECONDS, self._completion_due)

    @callback
    def _completion_due(self, _now: datetime) -> None:
        self._cancel_completion = None
        self.async_request_refresh()

    async def _async_refresh(self) -> None:
        try:
            await self._async_read()
        except Exception:  # noqa: BLE001 - the kept log stays usable
            _LOGGER.exception("Reading the work log of %s failed", self._coordinator.entry.title)
            self.error = UNAVAILABLE
        finally:
            self.refreshing = False
            if not self._stopped:
                self._notify()

    async def _async_read(self) -> None:
        device = self._coordinator.device
        if self._coordinator.device_online:
            try:
                totals = await self._hass.async_add_executor_job(device.read_work_totals)
            except Exception as ex:  # noqa: BLE001 - the list is worth reading without the totals
                _LOGGER.debug("Work totals not available: %s", ex)
            else:
                if totals is not None:
                    self.totals = totals
        start = self._start()
        since = self._since(start)
        read = await self._hass.async_add_executor_job(device.read_work_log, since)
        if read is None:
            self.error = UNAVAILABLE
            return
        entries = merge_entries(self.entries, read, self.totals["start"] if self.totals else None)
        # Photos of a task can arrive, and its file be fetched, after it was read.
        await self._hass.async_add_executor_job(device.count_work_log_photos, entries)
        self.entries = entries
        if self._covered_since is None or since < self._covered_since:
            self._covered_since = since
        await self._store.async_save(
            {"totals": self.totals, "entries": self.entries, "covered_since": self._covered_since}
        )
        if self.battery is not None:
            # Tasks from before the battery was followed, filled in once.
            self._coordinator.entry.async_create_background_task(
                self._hass, self.battery.async_backfill(self.entries), f"{DOMAIN} battery backfill"
            )

    def entries_with_battery(self) -> list[dict[str, Any]]:
        """The kept tasks, each with what it took of the battery where known."""
        battery = self.battery
        if battery is None:
            return self.entries
        return [{**entry, "battery": battery.summary(entry)} for entry in self.entries]

    def _start(self) -> int:
        """Since when the log counts, as a unix time."""
        start: int = self.totals["start"] if self.totals else int(time.time()) - FALLBACK_SECONDS
        return start

    def _since(self, start: int) -> int:
        """Since when to read: from the start of the log while it was never read
        that far, and from shortly before the newest kept task after that."""
        if self._covered_since is None or start < self._covered_since or not self.entries:
            return start
        return max(start, self.entries[0]["start"] - OVERLAP_SECONDS)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()


def _files(entries: Iterable[dict[str, Any]]) -> set[str]:
    return {entry["file"] for entry in entries if entry.get("file")}


async def async_remove_work_log(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the kept work log of a removed entry."""
    await work_log_store(hass, entry_id).async_remove()
