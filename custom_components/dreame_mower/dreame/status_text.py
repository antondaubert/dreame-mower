"""One line saying what the mower is doing, from its heartbeat.

The heartbeat says what the mower does (main and sub state), where it stands
(whether it knows its position, its way to or from the station) and which
codes it reports. What matters most comes first: the mower losing its
position, then the conditions that send it home (rain, temperature, quiet
hours, a low battery), then what it is working on.
"""

from __future__ import annotations

from typing import Any

_MAIN_REMOTE_CONTROL = 2
_MAIN_MAPPING = 3
_MAIN_MOWING = 4

# The task's status is the sub state counted from here, while it mows.
_TASK_STATUS_BASE = 33
_STARTING, _WORKING, _PAUSED, _FINISHED = 1, 2, 3, 4

_MODES = {0: "all-area", 1: "edge", 2: "zone", 3: "spot"}
_PATROL_MODES = frozenset({7, 8, 9})

_RETURNING = frozenset({"pause_docking", "finish_docking"})

CODE_RETURN_FAILED = frozenset({31, 32})
CODE_RAIN = 56
CODE_BATTERY_COLD = 59
CODE_BATTERY_HOT = 11
CODE_QUIET_HOURS = 61
CODE_BATTERY_LOW = 54
CODE_REMOTE_CONTROL = 64
CODE_CHARGING_HOT = 42
CODE_CHARGING_COLD = 43


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def status_text(online: bool, state: dict[str, Any] | None, codes: frozenset[int] | set[int]) -> str | None:
    """What the mower is doing, as one line; None before its first heartbeat."""
    if not online:
        return "Offline"
    if state is None:
        return None
    main = state.get("main_state")
    returning = state.get("docking") in _RETURNING
    task = (state.get("sub_state") or 0) - _TASK_STATUS_BASE if main == _MAIN_MOWING else None
    paused = task == _PAUSED

    if main == _MAIN_REMOTE_CONTROL:
        return "Remote control"
    if main == _MAIN_MAPPING:
        return "Mapping"
    if state.get("location") == "relocating":
        return "Repositioning"
    if codes & CODE_RETURN_FAILED:
        return "Failed to return to the station"
    if CODE_RAIN in codes:
        if returning:
            return "Rain protection activated. Returning to the station"
        return "Rain protection is on. Task paused" if paused else "Rain protection is activated"
    if CODE_BATTERY_COLD in codes:
        return "Battery temperature is too low. Returning to the station"
    if CODE_BATTERY_HOT in codes:
        return "Battery temperature is too high. Returning to the station"
    if CODE_QUIET_HOURS in codes:
        if returning:
            return "Do Not Disturb is on. Returning to the station"
        return "Do Not Disturb is on. Task paused" if paused else "Do Not Disturb is on"
    if CODE_BATTERY_LOW in codes:
        return "Battery is low. Returning to charge" if returning else "Low battery. Task paused"
    if CODE_REMOTE_CONTROL in codes:
        return "Under remote control. Scheduled task cancelled"
    if CODE_CHARGING_HOT in codes:
        return "Charging paused: battery temperature is too high"
    if CODE_CHARGING_COLD in codes:
        return "Charging paused: battery temperature is too low"
    if state.get("charging"):
        return "Charging"
    if main == _MAIN_MOWING:
        mode_number = state.get("work_mode")
        if mode_number in _PATROL_MODES:
            return "Patrolling"
        mode = _MODES.get(mode_number, "") if isinstance(mode_number, int) else ""
        scheduled = "scheduled " if state.get("scheduled") else ""
        mowing = f"{scheduled}{mode} mowing".replace("  ", " ").strip()
        if task == _FINISHED:
            return "Mowing completed. Returning to the station"
        if state.get("docking") == "finish_docking":
            return _sentence(f"{mowing} complete. Returning to the station")
        if state.get("docking") == "pause_docking":
            return _sentence(f"{mowing} paused. Returning to the station")
        if task == _STARTING:
            return _sentence(f"starting {mowing}")
        if task == _WORKING:
            return _sentence(f"{mowing} ongoing")
        if paused:
            return _sentence(f"{mowing} paused")
    if returning:
        return "Returning to the station"
    return "Standby"
