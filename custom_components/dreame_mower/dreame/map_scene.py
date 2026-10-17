"""What a map shows, in the form the map card draws from.

The vector map is turned into plain lists in map units (y up): the zones,
no-go areas, paths and spot areas as polygons, the maintenance points, and
the trail the mower left behind. The map feed sends it to the card as it is.
"""

from __future__ import annotations

from typing import Any

from .map_data_parser import MowerVectorMap, resolve_zone_polygon

# Marks a break in a trail: the mower stopped mowing between two points.
SEGMENT_BREAK = 2147483647


def _flat(points: list[tuple[int, int]]) -> list[int]:
    return [int(value) for point in points for value in point]


def map_geometry(vector_map: MowerVectorMap | None) -> dict[str, Any] | None:
    """The parts of a map that only change when the map itself does."""
    if vector_map is None:
        return None

    zones = [
        {
            "id": zone.zone_id,
            "name": zone.name or f"Zone {zone.zone_id}",
            "area": zone.area,
            "polygon": _flat(resolve_zone_polygon(zone.shape_type, zone.angle, zone.path)),
        }
        for zone in vector_map.zones
    ]
    no_go = [
        {
            "id": area.zone_id,
            "polygon": _flat(resolve_zone_polygon(area.shape_type, area.angle, area.path)),
            **_editable_shape(area.shape_type, area.angle, area.path),
        }
        for area in vector_map.forbidden_areas
    ]
    ignore_obstacles = [
        {
            "id": area.zone_id,
            "polygon": _flat(resolve_zone_polygon(area.shape_type, area.angle, area.path)),
            **_editable_shape(_SHAPE_RECTANGLE, area.angle, area.path),
        }
        for area in vector_map.ignore_obstacle_areas
    ]
    paths = [{"id": path.path_id, "points": _flat(path.path)} for path in vector_map.paths]
    contours = [
        {"id": [contour.contour_id[0], contour.contour_id[1]], "points": _flat(contour.path)}
        for contour in vector_map.contours
        if len(contour.path) > 1
    ]
    spots = [
        {
            "id": spot.area_id,
            "name": spot.name or f"Spot {spot.area_id}",
            "polygon": _flat(resolve_zone_polygon(spot.shape_type, 0.0, spot.path)),
            **_editable_shape(_SHAPE_RECTANGLE, 0.0, spot.path),
        }
        for spot in vector_map.spot_areas
    ]
    maintenance_points = [
        {"id": point.point_id, "x": point.x, "y": point.y, "heading": point.heading} for point in vector_map.maintenance_points
    ]

    geometry: dict[str, Any] = {
        "map_id": vector_map.map_id,
        "name": vector_map.name,
        "zones": zones,
        "total_area": vector_map.total_area,
        "no_go": no_go,
        "ignore_obstacles": ignore_obstacles,
        "paths": paths,
        "contours": contours,
        "spots": spots,
        "maintenance_points": maintenance_points,
    }
    geometry["bounds"] = _bounds(geometry)
    return geometry


# How an area is drawn, as the map keeps it.
_SHAPE_LINE = 1
_SHAPE_RECTANGLE = 2
_SHAPE_CIRCLE = 3


def _editable_shape(shape_type: int, angle: float, path: list[tuple[int, int]]) -> dict[str, Any]:
    """An area in the form the map card edits it in.

    A line as its two ends, an upright rectangle as two opposite corners, a
    circle as its centre and radius. Anything else, a turned rectangle or a
    decorative shape, is "polygon": it can be deleted, not reshaped.
    """
    xs = [point[0] for point in path]
    ys = [point[1] for point in path]
    if shape_type == _SHAPE_LINE and len(path) == 2:
        return {"shape": "line", "line": [xs[0], ys[0], xs[1], ys[1]]}
    if shape_type == _SHAPE_CIRCLE and len(path) >= 2:
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        return {"shape": "circle", "circle": [round((x0 + x1) / 2), round((y0 + y1) / 2), round(max(x1 - x0, y1 - y0) / 2)]}
    upright = len(path) == 4 and len(set(xs)) == 2 and len(set(ys)) == 2
    if shape_type == _SHAPE_RECTANGLE and not angle and upright:
        return {"shape": "rectangle", "rect": [min(xs), min(ys), max(xs), max(ys)]}
    return {"shape": "polygon"}


def _bounds(geometry: dict[str, Any]) -> list[int] | None:
    """The smallest box around everything drawn, as [x1, y1, x2, y2]."""
    xs: list[int] = []
    ys: list[int] = []

    def add(flat: list[int]) -> None:
        xs.extend(flat[0::2])
        ys.extend(flat[1::2])

    for key in ("zones", "no_go", "ignore_obstacles", "spots"):
        for item in geometry[key]:
            add(item["polygon"])
    for path in geometry["paths"]:
        add(path["points"])
    for point in geometry["maintenance_points"]:
        add([point["x"], point["y"]])
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def map_outline(vector_map: MowerVectorMap) -> dict[str, Any]:
    """A map reduced to its zones, as a small preview of a map that is not active."""
    zones: list[dict[str, Any]] = [
        {"id": zone.zone_id, "polygon": _flat(resolve_zone_polygon(zone.shape_type, zone.angle, zone.path))}
        for zone in vector_map.zones
    ]
    points: list[int] = [value for zone in zones for value in zone["polygon"]]
    xs, ys = points[0::2], points[1::2]
    return {
        "map_id": vector_map.map_id,
        "zones": zones,
        "bounds": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
    }


def stripe_angle(direction: int | None) -> float | None:
    """The angle the lawn stripes run at, counter-clockwise from the map's x axis.

    The mower's mowing direction counts the other way round from the opposite
    side, so a direction of 180° gives stripes along the x axis.
    """
    if direction is None:
        return None
    return float((180 - direction) % 180)


def trail_points(points: list[list[int]]) -> list[list[int] | None]:
    """A trail as [x, y] points, with None where it breaks."""
    out: list[list[int] | None] = []
    for point in points:
        if point[0] == SEGMENT_BREAK or point[1] == SEGMENT_BREAK:
            if out and out[-1] is not None:
                out.append(None)
        else:
            out.append([int(point[0]), int(point[1])])
    while out and out[-1] is None:
        out.pop()
    return out

