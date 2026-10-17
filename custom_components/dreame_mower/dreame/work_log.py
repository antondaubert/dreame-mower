"""The mower's work log: one entry per mowing task, and the details of each.

The cloud keeps every task's completion event (4:1), which lists the tasks;
each event names a file holding the task's map, the lanes it mowed and its
result, which details one entry. Patrol tasks share the event and are left
out, the log covers mowing only.
"""

from __future__ import annotations

import json
import math
from typing import Any

from .map_data_parser import convert_device_map, parse_ai_obstacles, parse_mower_map, parse_obstacles
from .map_scene import map_geometry

# Arguments of the completion event.
_PIID_MODE = 1
_PIID_DURATION = 2
_PIID_AREA = 3
_PIID_STATUS = 7
_PIID_START = 8
_PIID_FILE = 9
_PIID_START_MODE = 11

# The mode argument carries the task mode offset by this much; a smaller value
# comes from older firmware, which reports the area in m² rather than in
# hundredths and swaps the meaning of status 0 and 3.
_MODE_OFFSET = 100

TASK_MODES = {0: "all_area", 1: "edge", 2: "zone", 3: "spot"}
# Task modes of patrols, which the work log leaves out.
_PATROL_MODES = frozenset({7, 8, 9})

# How a task ended: 1 finished; 2 left unfinished; 3 stopped; 0 never ran.
TASK_RESULTS = {0: "incomplete", 1: "complete", 2: "incomplete", 3: "stopped"}

START_MODES = {0: "app", 1: "schedule", 2: "control_panel"}
EFFICIENCIES = {0: "standard", 1: "efficient", 3: "rush"}

# How far a zone got: -1 unfinished, 0 being mowed, 1 failed, 2 finished,
# 3 its edges being mowed, 4 paused.
ZONE_RESULTS = {-1: "unfinished", 0: "mowing", 1: "failed", 2: "finished", 3: "edges", 4: "paused"}

# Map documents count in tenths of a map unit (mm).
_DOCUMENT_SCALE = 10
# Marks a break in a mowed track.
_TRACK_BREAK = 2147483647
# How far (mm) a track may stray from its drawing: points closer to the line
# than this add nothing to the lanes.
_TRACK_TOLERANCE_MM = 40


def work_log_entry(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One task of the log from the arguments of its completion event.

    Returns None for a patrol, and for an event that names no start time.
    """
    values = {item.get("piid"): item.get("value") for item in history if isinstance(item, dict)}
    start = values.get(_PIID_START)
    raw_mode = values.get(_PIID_MODE)
    if not isinstance(start, int) or not isinstance(raw_mode, int):
        return None

    current = raw_mode >= _MODE_OFFSET
    mode = raw_mode - _MODE_OFFSET if current else raw_mode
    if mode in _PATROL_MODES:
        return None

    status = values.get(_PIID_STATUS)
    if not current and status in (0, 3):
        status = 3 - status
    area = values.get(_PIID_AREA)
    if isinstance(area, (int, float)) and current:
        area = area / 100
    file = values.get(_PIID_FILE)
    return {
        "start": start,
        "duration": values.get(_PIID_DURATION),
        "area": round(area, 2) if isinstance(area, (int, float)) else None,
        "mode": TASK_MODES.get(mode, "other"),
        "result": TASK_RESULTS.get(status, "incomplete") if isinstance(status, int) else "incomplete",
        "scheduled": values.get(_PIID_START_MODE) == 1,
        "file": file if isinstance(file, str) and file else None,
    }


def work_log_entries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The tasks of the log, newest first, from the cloud's event records.

    A record whose arguments do not parse is skipped, and a task reported
    twice is listed once.
    """
    entries: dict[int, dict[str, Any]] = {}
    for record in records:
        history = record.get("history") if isinstance(record, dict) else None
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except ValueError:
                continue
        if not isinstance(history, list):
            continue
        entry = work_log_entry(history)
        if entry is not None:
            entries[entry["start"]] = entry
    return [entries[start] for start in sorted(entries, reverse=True)]


def _simplify(points: list[list[int]], tolerance: float) -> list[list[int]]:
    """Drop the points of a line that stray less than `tolerance` from it.

    Keeps the corners, so lanes and the turns between them stay as mowed.
    """
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (ax, ay), (bx, by) = points[first], points[last]
        length = math.hypot(bx - ax, by - ay)
        farthest, index = 0.0, -1
        for k in range(first + 1, last):
            px, py = points[k]
            if length:
                distance = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / length
            else:
                distance = math.hypot(px - ax, py - ay)
            if distance > farthest:
                farthest, index = distance, k
        if index >= 0 and farthest > tolerance:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [point for point, kept in zip(points, keep) if kept]


def _track(points: list[Any]) -> list[list[int] | None]:
    """A mowed track in map units, None at each break, without the points
    that add nothing to its shape."""
    track: list[list[int] | None] = []
    run: list[list[int]] = []

    def close_run() -> None:
        if run:
            if track:
                track.append(None)
            track.extend(_simplify(run, _TRACK_TOLERANCE_MM))
            run.clear()

    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        if point[0] == _TRACK_BREAK or point[1] == _TRACK_BREAK:
            close_run()
            continue
        current = [int(point[0]) * _DOCUMENT_SCALE, int(point[1]) * _DOCUMENT_SCALE]
        if not run or run[-1] != current:
            run.append(current)
    close_run()
    return track


def work_log_details(document: dict[str, Any]) -> dict[str, Any]:
    """The details of one task from its file: what happened and where."""
    pref_value = document.get("pref")
    pref: list[Any] = pref_value if isinstance(pref_value, list) else []
    result = document.get("result")
    start_mode = document.get("start_mode")
    mode = document.get("mode")
    if isinstance(mode, int) and mode >= _MODE_OFFSET:
        mode -= _MODE_OFFSET
    geometry = None
    try:
        geometry = map_geometry(parse_mower_map(convert_device_map(document, 0, str(document.get("md5", "")))))
    except (KeyError, TypeError, ValueError, IndexError):
        geometry = None
    tracks = [
        _track(item["track"])
        for item in document.get("map", [])
        if isinstance(item, dict) and isinstance(item.get("track"), list)
    ]
    dock = document.get("dock")
    return {
        "start": document.get("start"),
        "end": document.get("end"),
        "duration": document.get("time"),
        "area": document.get("areas"),
        "map_area": document.get("map_area"),
        "mode": TASK_MODES.get(mode, "other") if isinstance(mode, int) else None,
        "result": TASK_RESULTS.get(result, "incomplete") if isinstance(result, int) else None,
        "start_mode": START_MODES.get(start_mode) if isinstance(start_mode, int) else None,
        "height": pref[0] / 10 if pref and isinstance(pref[0], (int, float)) else None,
        "efficiency": EFFICIENCIES.get(pref[1]) if len(pref) > 1 else None,
        "per_zone": document.get("pre_type") == 1,
        "zones": [
            {"id": zone[0], "result": ZONE_RESULTS.get(zone[1])}
            for zone in document.get("region_status", [])
            if isinstance(zone, (list, tuple)) and len(zone) >= 2
        ],
        "faults": [
            {"time": fault[0], "code": fault[1]}
            for fault in document.get("faults", [])
            if isinstance(fault, (list, tuple)) and len(fault) >= 2
        ],
        "geometry": geometry,
        "tracks": [track for track in tracks if track],
        "obstacles": [
            *({"kind": "obstacle", **obstacle} for obstacle in parse_obstacles(document.get("obstacle", []))),
            *({"kind": "ai", **obstacle} for obstacle in parse_ai_obstacles(document.get("ai_obstacle", []))),
        ],
        "dock": {"x": dock[0] * _DOCUMENT_SCALE, "y": dock[1] * _DOCUMENT_SCALE, "angle": dock[2] / 10}
        if isinstance(dock, list) and len(dock) >= 3
        else None,
    }
