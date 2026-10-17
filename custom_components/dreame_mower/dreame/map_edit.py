"""Changes to the mower's map that are drawn rather than driven.

Each change is a 2:50 action the mower confirms with a 2:50 "TASK" report
carrying the same "o": {"o", "status", "error", "id" | "ids"}. Changes to the
items of a map are made in the mower's edit mode, entered with EDIT_ENTER and
left with EDIT_EXIT; the mower does not move for any of them, but it refuses
them while it mows or returns to its station.

Positions go to the mower in metres, rounded to the centimetre; the map's own
unit is the millimetre.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

# The actions, by their "o".
EDIT_ENTER = 204
EDIT_EXIT = 201
RENAME_MAP = 210
DELETE_MAP = 207
BACKUP_MAP = 208
RESTORE_MAP = 209
SET_SPOT_AREA = 214
SET_NO_GO_ZONE = 215
DELETE_ITEM = 218
RENAME_ZONE = 219
SPLIT_ZONE = 220
MERGE_ZONES = 221
SET_MAINTENANCE_POINT = 224
SET_IGNORE_OBSTACLE_AREA = 234

# The kind of item a deletion names.
ITEM_KINDS = {
    "zone": 0,
    "path": 0,
    "no_go_zone": 0,
    "spot_area": 1,
    "maintenance_point": 3,
    "ignore_obstacle_area": 4,
}

# The shapes of a no-go zone.
NO_GO_SHAPES = {"line": 1, "rectangle": 2, "circle": 3}

# A new item is named by this id.
NEW_ITEM = -1

# What the mower answers when it refuses an item, by action.
_ERRORS: dict[int, dict[int, str]] = {
    SET_NO_GO_ZONE: {
        2: "The no-go zone lies outside the map",
        3: "The no-go zone covers the station's area",
        4: "The no-go zone overlaps another one",
        6: "The no-go zone must stay within one zone",
    },
    SET_MAINTENANCE_POINT: {
        2: "The maintenance point must lie within the map, keeping a safe distance from its boundary",
        3: "The maintenance point cannot lie in a no-go zone",
        4: "The maintenance point must lie outside the station's area",
    },
    SET_SPOT_AREA: {
        -2: "The spot area lies outside the map or in a no-go zone",
        -3: "The spot area must stay within one zone",
        -4: "The spot area overlaps a no-go zone",
    },
}

# A no-go zone that cuts a path is kept; the mower only reports it.
NO_GO_ZONE_BLOCKS_PATH = 1


def metres(value: float) -> float:
    """A map position in metres, to the centimetre."""
    return round(value / 1000, 2)


def rectangle_corners(rect: Sequence[float]) -> list[list[float]]:
    """The four corners of a rectangle [x0, y0, x1, y1] in map units, in metres."""
    x0, y0, x1, y1 = (float(value) for value in rect)
    left, right = min(x0, x1), max(x0, x1)
    bottom, top = min(y0, y1), max(y0, y1)
    return [
        [metres(right), metres(bottom)],
        [metres(left), metres(bottom)],
        [metres(left), metres(top)],
        [metres(right), metres(top)],
    ]


def action(operation: int, data: dict[str, Any] | None = None, *, p: int = 0) -> dict[str, Any]:
    """A 2:50 action."""
    payload: dict[str, Any] = {"m": "a", "p": p, "o": operation}
    if data is not None:
        payload["d"] = data
    return payload


def no_go_zone(item_id: int | None, shape: str, points: Sequence[Sequence[float]], radius: float | None) -> dict[str, Any]:
    """Draw or change a no-go zone.

    A line takes its two ends, a rectangle its two opposite corners, a circle
    its centre and a radius, all in map units.
    """
    if shape not in NO_GO_SHAPES:
        raise ValueError(f"A no-go zone is a {', '.join(NO_GO_SHAPES)}; got {shape!r}")
    data: dict[str, Any] = {"id": NEW_ITEM if item_id is None else item_id, "type": NO_GO_SHAPES[shape]}
    if shape == "rectangle":
        if len(points) != 2:
            raise ValueError("A rectangle takes two opposite corners")
        data["points"] = rectangle_corners([*points[0], *points[1]])
    elif shape == "line":
        if len(points) != 2:
            raise ValueError("A line takes its two ends")
        data["points"] = [[metres(x), metres(y)] for x, y in points]
    else:
        if len(points) != 1 or not radius or radius <= 0:
            raise ValueError("A circle takes its centre and a radius")
        data["points"] = [[metres(points[0][0]), metres(points[0][1])]]
        data["radius"] = metres(radius)
    return action(SET_NO_GO_ZONE, data)


def spot_area(item_id: int | None, rect: Sequence[float]) -> dict[str, Any]:
    return action(SET_SPOT_AREA, {"id": NEW_ITEM if item_id is None else item_id, "points": rectangle_corners(rect)})


def ignore_obstacle_area(item_id: int | None, rect: Sequence[float]) -> dict[str, Any]:
    return action(
        SET_IGNORE_OBSTACLE_AREA,
        {"id": NEW_ITEM if item_id is None else item_id, "type": 0, "points": rectangle_corners(rect)},
    )


def maintenance_point(item_id: int | None, x: float, y: float, heading: float) -> dict[str, Any]:
    """Place a maintenance point; the heading, in degrees, is sent in half turns."""
    return action(
        SET_MAINTENANCE_POINT,
        {"id": NEW_ITEM if item_id is None else item_id, "points": [metres(x), metres(y), round((heading % 360) / 180, 3)]},
    )


def delete_item(kind: str, item_id: int) -> dict[str, Any]:
    if kind not in ITEM_KINDS:
        raise ValueError(f"The kind of item is one of {', '.join(ITEM_KINDS)}; got {kind!r}")
    return action(DELETE_ITEM, {"id": item_id, "type": ITEM_KINDS[kind]})


def rename_zone(zone_id: int, name: str) -> dict[str, Any]:
    return action(RENAME_ZONE, {"region": zone_id, "name": checked_name(name)})


def split_zone(zone_id: int, line: Sequence[float]) -> dict[str, Any]:
    x0, y0, x1, y1 = line
    return action(SPLIT_ZONE, {"id": zone_id, "line_start": [metres(x0), metres(y0)], "line_end": [metres(x1), metres(y1)]})


def merge_zones(zone_ids: Sequence[int]) -> dict[str, Any]:
    if len(zone_ids) != 2 or zone_ids[0] == zone_ids[1]:
        raise ValueError("Two different neighbouring zones are merged at a time")
    return action(MERGE_ZONES, {"ids": [int(zone_id) for zone_id in zone_ids]})


def checked_name(name: str) -> str:
    """A name the mower takes: up to 24 characters, not empty."""
    name = name.strip()
    if not name or len(name) > 24:
        raise ValueError("A name has 1 to 24 characters")
    return name


def refusal(operation: int, answer: dict[str, Any]) -> str | None:
    """Why the mower refused an action, or None when it took it."""
    error = answer.get("error", 0)
    if operation == SET_NO_GO_ZONE and error == NO_GO_ZONE_BLOCKS_PATH:
        return None
    if answer.get("status") is False or error not in (0, None):
        return _ERRORS.get(operation, {}).get(error, f"The mower refused the change (error {error})")
    return None
