"""Parser for mower vector map data from the Dreame batch device data API.

The batch API returns map data split across numbered keys (MAP.0, MAP.1, ...).
These chunks must be concatenated in numeric order to form a complete JSON string.
The JSON contains polygon-based zone boundaries, navigation paths, and metadata.
"""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

# Zone/area shapeType values that need geometric expansion before rendering.
# Polygon shapes (0 and others) already carry their full vertex list.
_SHAPE_RECTANGLE = 2  # axis-aligned corners plus a rotation "angle" in degrees
_SHAPE_CIRCLE = 3     # two opposite bounding-box corners

# Number of segments used to approximate a circle/ellipse as a polygon.
_CIRCLE_SEGMENTS = 36


@dataclass
class MowerZone:
    """A mowing zone defined by a polygon boundary."""
    zone_id: int
    path: list[tuple[int, int]]
    name: str = ""
    shape_type: int = 0
    angle: float = 0.0
    area: float = 0


@dataclass
class MowerPath:
    """A navigation path between zones."""
    path_id: int
    path: list[tuple[int, int]]


@dataclass
class MowerContour:
    """A contour entry used for boundary or edge mowing."""
    contour_id: tuple[int, int]
    path: list[tuple[int, int]]
    shape_type: int = 0


@dataclass
class MowerSpotArea:
    """A spot-mowing area defined by a polygon boundary."""

    area_id: int
    path: list[tuple[int, int]]
    name: str = ""
    shape_type: int = 0
    area: float = 0


@dataclass
class MowerMaintenancePoint:
    """A point on the map the mower can be sent to for cleaning or servicing."""

    point_id: int
    x: int
    y: int
    # Which way the mower faces once there, in degrees; None when the map
    # does not say.
    heading: float | None = None


@dataclass
class MowerAvailableMap:
    """A discovered map entry that can be targeted by map-aware mowing tasks."""

    map_id: int
    map_index: int
    name: str = ""
    total_area: float = 0


@dataclass
class MowerMapBoundary:
    """Bounding box for the entire map."""
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


@dataclass
class MowerVectorMap:
    """Complete vector map data for a mower, fetched from batch API."""
    zones: list[MowerZone] = field(default_factory=list)
    spot_areas: list[MowerSpotArea] = field(default_factory=list)
    maintenance_points: list[MowerMaintenancePoint] = field(default_factory=list)
    forbidden_areas: list[MowerZone] = field(default_factory=list)
    # Areas the mower mows without avoiding obstacles in them.
    ignore_obstacle_areas: list[MowerZone] = field(default_factory=list)
    paths: list[MowerPath] = field(default_factory=list)
    contours: list[MowerContour] = field(default_factory=list)
    boundary: MowerMapBoundary | None = None
    total_area: float = 0
    name: str = ""
    map_id: int = 1
    map_index: int = 0
    # The hash the mower reports for this map: empty for a slot that holds none,
    # None when the source does not say.
    md5sum: str | None = None
    available_maps: list[MowerAvailableMap] = field(default_factory=list)
    current_map_id: int | None = None
    maps: dict[int, MowerVectorMap] = field(default_factory=dict, repr=False)


def _map_id_from_index(map_index: int) -> int:
    """Translate the batch map index into the task-level region identifier."""
    return map_index + 1


def reassemble_map_chunks(batch_data: dict, prefix: str) -> str | None:
    """Reassemble chunked data from batch API into a single string.

    Keys like MAP.0, MAP.1, ... MAP.N are concatenated in numeric order.
    The MAP.info key is skipped (it's metadata, not map content).

    Args:
        batch_data: dict from get_batch_device_datas response
        prefix: key prefix to match, e.g. "MAP"

    Returns:
        Concatenated string, or None if no matching keys found.
    """
    pattern = re.compile(rf"^{re.escape(prefix)}\.(\d+)$")
    chunks = []
    for key, value in batch_data.items():
        match = pattern.match(key)
        if match:
            chunks.append((int(match.group(1)), value))

    if not chunks:
        return None

    chunks.sort(key=lambda x: x[0])
    return "".join(value for _, value in chunks)


def _parse_polygon_list(data_map: dict) -> list:
    """Parse a dataType:Map structure containing polygon entries."""
    if not data_map or data_map.get("dataType") != "Map":
        return []
    return data_map.get("value", [])


def _extract_path_coords(path_list: list) -> list[tuple[int, int]]:
    """Convert [{"x": ..., "y": ...}, ...] to [(x, y), ...]."""
    return [(p["x"], p["y"]) for p in path_list]


def _circle_polygon(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Approximate a circle/ellipse (two opposite bounding-box corners) as a polygon.

    Everything downstream (the map card, rotation and bounds-fitting) works
    on point lists and carries no shape metadata.
    Expanding to a polygon here lets the circle flow through unchanged instead
    of threading a centre+radii descriptor through every stage.
    """
    (x1, y1), (x2, y2) = path[0], path[1]
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    rx, ry = abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0
    polygon = []
    for i in range(_CIRCLE_SEGMENTS):
        theta = 2.0 * math.pi * i / _CIRCLE_SEGMENTS
        polygon.append((round(cx + rx * math.cos(theta)), round(cy + ry * math.sin(theta))))
    return polygon


def _rotate_polygon(path: list[tuple[int, int]], angle_deg: float) -> list[tuple[int, int]]:
    """Rotate polygon vertices by ``angle_deg`` degrees around their centroid."""
    if not path:
        return []
    cx = sum(p[0] for p in path) / len(path)
    cy = sum(p[1] for p in path) / len(path)
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    rotated = []
    for x, y in path:
        dx, dy = x - cx, y - cy
        rotated.append((round(cx + dx * cos_t - dy * sin_t), round(cy + dx * sin_t + dy * cos_t)))
    return rotated


def resolve_zone_polygon(
    shape_type: int, angle: float, path: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Expand an encoded zone shape into a renderable polygon.

    Most shapes already store their full vertex list, but circles store only the
    two opposite corners of their bounding box, and rectangles store an
    axis-aligned outline with a separate rotation ``angle``. Both need expanding
    before they can be rendered as polygons.
    """
    if shape_type == _SHAPE_CIRCLE and len(path) >= 2:
        return _circle_polygon(path)
    if shape_type == _SHAPE_RECTANGLE and angle:
        # The device measures the rotation in its own coordinate frame, whose
        # Y axis points opposite to the rendered image; negate so the tilt
        # matches the direction shown in the app.
        return _rotate_polygon(path, -angle)
    return list(path)


def _extract_contour_id(raw_contour_id: str | list[int] | tuple[int, int]) -> tuple[int, int]:
    """Convert a contour identifier into a normalized two-integer tuple."""
    if isinstance(raw_contour_id, str):
        parts = [part.strip() for part in raw_contour_id.split(",")]
        if len(parts) != 2:
            raise ValueError(f"Invalid contour id: {raw_contour_id}")
        return (int(parts[0]), int(parts[1]))

    if len(raw_contour_id) != 2:
        raise ValueError(f"Invalid contour id: {raw_contour_id}")
    return (int(raw_contour_id[0]), int(raw_contour_id[1]))


def parse_mower_map(map_json: str | dict) -> MowerVectorMap:
    """Parse a single map into a MowerVectorMap.

    Args:
        map_json: one map, either as the JSON string held in the chunk array or
            as the object that string decodes to.

    Returns:
        MowerVectorMap with zones, paths, boundary, etc.
    """
    data = json.loads(map_json) if isinstance(map_json, str) else map_json
    vmap = MowerVectorMap()

    # Parse mowing area zones
    for entry in _parse_polygon_list(data.get("mowingAreas", {})):
        zone_id, zone_data = entry[0], entry[1]
        vmap.zones.append(MowerZone(
            zone_id=zone_id,
            path=_extract_path_coords(zone_data.get("path", [])),
            name=zone_data.get("name", ""),
            shape_type=zone_data.get("shapeType", 0),
            area=zone_data.get("area", 0),
        ))

    # Parse spot-mowing areas
    for entry in _parse_polygon_list(data.get("spotAreas", {})):
        area_id, area_data = entry[0], entry[1]
        vmap.spot_areas.append(MowerSpotArea(
            area_id=int(area_id),
            path=_extract_path_coords(area_data.get("path", [])),
            name=area_data.get("name", ""),
            shape_type=area_data.get("shapeType", 0),
            area=area_data.get("area", 0),
        ))

    # Parse the maintenance points the mower can be sent to. Each one is a
    # single coordinate rather than an area, so only the first path point
    # carries a position.
    for entry in _parse_polygon_list(data.get("cleanPoints", {})):
        point_id, point_data = entry[0], entry[1]
        path = _extract_path_coords(point_data.get("path", []))
        if not path:
            _LOGGER.debug("Maintenance point %s carries no position", point_id)
            continue
        heading = point_data.get("heading")
        vmap.maintenance_points.append(MowerMaintenancePoint(
            point_id=int(point_id),
            x=path[0][0],
            y=path[0][1],
            heading=float(heading) if isinstance(heading, (int, float)) else None,
        ))

    # Parse forbidden areas
    for entry in _parse_polygon_list(data.get("forbiddenAreas", {})):
        zone_id, zone_data = entry[0], entry[1]
        vmap.forbidden_areas.append(MowerZone(
            zone_id=zone_id,
            path=_extract_path_coords(zone_data.get("path", [])),
            name=zone_data.get("name", ""),
            shape_type=zone_data.get("shapeType", 0),
            angle=zone_data.get("angle", 0) or 0.0,
        ))

    # Parse the areas the mower mows without avoiding obstacles
    for entry in _parse_polygon_list(data.get("notObsAreas", {})):
        area_id, area_data = entry[0], entry[1]
        vmap.ignore_obstacle_areas.append(MowerZone(
            zone_id=int(area_id),
            path=_extract_path_coords(area_data.get("path", [])),
            shape_type=area_data.get("shapeType", 0),
            angle=area_data.get("angle", 0) or 0.0,
        ))

    # Parse navigation paths between zones
    for entry in _parse_polygon_list(data.get("paths", {})):
        path_id, path_data = entry[0], entry[1]
        vmap.paths.append(MowerPath(
            path_id=path_id,
            path=_extract_path_coords(path_data.get("path", [])),
        ))

    # Parse contours used by edge mowing
    for entry in _parse_polygon_list(data.get("contours", {})):
        contour_id, contour_data = entry[0], entry[1]
        vmap.contours.append(MowerContour(
            contour_id=_extract_contour_id(contour_id),
            path=_extract_path_coords(contour_data.get("path", [])),
            shape_type=contour_data.get("shapeType", 0),
        ))

    # Parse boundary
    boundary = data.get("boundary")
    if boundary:
        vmap.boundary = MowerMapBoundary(
            x1=boundary["x1"], y1=boundary["y1"],
            x2=boundary["x2"], y2=boundary["y2"],
        )

    vmap.total_area = data.get("totalArea", 0)
    vmap.name = data.get("name", "")
    vmap.map_index = data.get("mapIndex", 0)
    vmap.map_id = _map_id_from_index(vmap.map_index)
    md5sum = data.get("md5sum")
    vmap.md5sum = md5sum if isinstance(md5sum, str) else None

    return vmap


# Component types of the items in a map document the mower reports.
_ITEM_MOWING_AREA = 0
_ITEM_PATH = 1
_ITEM_FORBIDDEN_AREA = 2
_ITEM_SPOT_AREA = 3
_ITEM_CLEAN_POINT = 6
_ITEM_CRUISE_POINT = 8
_ITEM_NOT_OBSTACLE_AREA = 10
_ITEM_CONTOUR = 7

# A point the mower reports with this type is a maintenance point; any other
# type is a point it cruises to.
_POINT_TYPE_CLEAN = 1
# A point's heading counts hundredths of a half turn: 50 is 90 degrees.
_POINT_HEADING_DEGREES = 1.8

_SHAPE_POINT = 5
_SHAPE_SPOT_AREA = 7
_SHAPE_CIRCLE_PATTERN = 11

# Forbidden-area shapes the mower stores rotated: rectangles and the patterned
# shapes. Lines, circles and plain outlines carry no rotation.
_ROTATED_FORBIDDEN_SHAPES = frozenset({_SHAPE_RECTANGLE, 9, 10, *range(12, 35)})

# The mower reports coordinates in units ten times coarser than the map uses.
_DEVICE_COORDINATE_SCALE = 10


def _device_points_to_path(shape_type: int, points: list, radius: float | None) -> list[dict[str, float]]:
    """Scale the points of one map item to map coordinates.

    A circle is reported as its centre and radius, and is kept as the two
    opposite corners of its bounding box, the form resolve_zone_polygon expands.
    """
    scale = _DEVICE_COORDINATE_SCALE
    if shape_type in (_SHAPE_CIRCLE, _SHAPE_CIRCLE_PATTERN) and points:
        cx, cy = points[0][0], points[0][1]
        r = radius or 0
        return [
            {"x": (cx - r) * scale, "y": (cy - r) * scale},
            {"x": (cx + r) * scale, "y": (cy + r) * scale},
        ]
    return [{"x": point[0] * scale, "y": point[1] * scale} for point in points]


def _signed_angle(a: dict, b: dict, c: dict) -> float:
    """Return the angle at ``b`` from ``a`` to ``c`` in degrees, signed by turn direction."""
    bax, bay = a["x"] - b["x"], a["y"] - b["y"]
    bcx, bcy = c["x"] - b["x"], c["y"] - b["y"]
    lengths = math.hypot(bax, bay) * math.hypot(bcx, bcy)
    if lengths == 0:
        return 0.0
    cosine = max(-1.0, min(1.0, (bax * bcx + bay * bcy) / lengths))
    angle = math.degrees(math.acos(cosine))
    return -angle if bax * bcy - bay * bcx < 0 else angle


def _rotate_points(path: list[dict], center: tuple[float, float], angle_deg: float) -> list[dict]:
    """Rotate map points by ``angle_deg`` degrees around ``center``."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    cx, cy = center
    return [
        {
            "x": cx + (p["x"] - cx) * cos_t - (p["y"] - cy) * sin_t,
            "y": cy + (p["x"] - cx) * sin_t + (p["y"] - cy) * cos_t,
        }
        for p in path
    ]


def _unrotate_rectangle(path: list[dict]) -> tuple[list[dict], float]:
    """Turn a tilted rectangle into its axis-aligned outline plus a rotation angle.

    This is the form the map keeps rectangles in, and the one
    resolve_zone_polygon tilts back for rendering. A rectangle is reported either
    by all four corners or by two opposite ones; any other outline is kept as it
    is, without a rotation.
    """
    if len(path) == 4:
        p0, p1, p2 = path[0], path[1], path[2]
        angle = math.fmod(_signed_angle(p0, p1, {"x": p1["x"] + 1, "y": p1["y"]}), 180)
        center = ((p0["x"] + p2["x"]) / 2, (p0["y"] + p2["y"]) / 2)
    elif len(path) == 2:
        p0, p1 = path
        angle = 45 + _signed_angle(p0, p1, {"x": p1["x"], "y": p1["y"] - 1})
        center = ((p0["x"] + p1["x"]) / 2, (p0["y"] + p1["y"]) / 2)
    else:
        return path, 0.0
    return _rotate_points(path, center, angle), angle


def _as_map_value(items: dict) -> dict:
    """Wrap items the way the map keeps its keyed collections."""
    return {"dataType": "Map", "value": [[key, value] for key, value in items.items()]}


def convert_device_map(document: dict, map_index: int, md5sum: str) -> dict:
    """Convert a map document read from the mower into the stored map form.

    The mower reports a map as plain item lists in coarse coordinates. The form
    this returns is the one the MAP.* keys hold, so parse_mower_map reads both
    the same way. A zone the mower holds no name for is called "Zone<n>", n
    counting the zones in the order the mower lists them.
    """
    items: list[dict] = [*document.get("map", []), *document.get("spot", [])]
    for point in document.get("point", []):
        items.append({
            **point,
            "type": _ITEM_CLEAN_POINT if point.get("type") == _POINT_TYPE_CLEAN else _ITEM_CRUISE_POINT,
            "data": [list(point.get("point", [])[:2])],
        })
    items.extend({**area, "type": _ITEM_NOT_OBSTACLE_AREA} for area in document.get("semantic", []))

    taken_names = {item["name"] for item in items if item.get("name")}
    collections: dict[str, dict] = {
        name: {}
        for name in (
            "mowingAreas", "paths", "forbiddenAreas", "spotAreas",
            "cleanPoints", "cruisePoints", "notObsAreas",
        )
    }
    zone_count = 0
    for item in items:
        description = item.get("description") or {}
        shape_type = description.get("type", 0)
        item_type = item.get("type", _ITEM_MOWING_AREA)
        points = description.get("points", item.get("data")) or []
        entry: dict = {
            "id": item["id"],
            "type": item_type,
            "shapeType": shape_type,
            "path": _device_points_to_path(shape_type, points, description.get("radius")),
        }

        if item_type in (_ITEM_CLEAN_POINT, _ITEM_CRUISE_POINT):
            entry["shapeType"] = _SHAPE_POINT
            # The third value of a point is the heading, in hundredths of a half turn.
            position = item.get("point") or []
            if len(position) > 2 and isinstance(position[2], (int, float)) and not isinstance(position[2], bool):
                entry["heading"] = round(position[2] * _POINT_HEADING_DEGREES, 1) % 360
        elif len(entry["path"]) < 2:
            continue

        if item_type == _ITEM_MOWING_AREA:
            zone_count += 1
            default_name = f"Zone{zone_count}"
            if default_name in taken_names:
                default_name += "_"
            entry.update(
                name=item.get("name") or default_name,
                area=item.get("area"),
            )
            collections["mowingAreas"][item["id"]] = entry
        elif item_type == _ITEM_PATH:
            collections["paths"][item["id"]] = entry
        elif item_type == _ITEM_FORBIDDEN_AREA:
            if shape_type in _ROTATED_FORBIDDEN_SHAPES:
                entry["path"], entry["angle"] = _unrotate_rectangle(entry["path"])
            collections["forbiddenAreas"][item["id"]] = entry
        elif item_type == _ITEM_SPOT_AREA:
            # Spot areas keep the outline the mower reports: they are drawn
            # as they stand, without a separate rotation.
            entry.update(
                shapeType=_SHAPE_SPOT_AREA,
                name=item.get("name", ""),
                area=item.get("area"),
            )
            collections["spotAreas"][item["id"]] = entry
        elif item_type == _ITEM_CLEAN_POINT:
            collections["cleanPoints"][item["id"]] = entry
        elif item_type == _ITEM_CRUISE_POINT:
            collections["cruisePoints"][item["id"]] = entry
        elif item_type == _ITEM_NOT_OBSTACLE_AREA:
            entry["shapeType"] = _SHAPE_RECTANGLE
            entry["path"], entry["angle"] = _unrotate_rectangle(entry["path"])
            collections["notObsAreas"][item["id"]] = entry

    # A contour is keyed by its [zone, index] pair, which parse_mower_map reads
    # back as its contour ID.
    contours = [
        [
            contour["id"],
            {
                "id": contour["id"],
                "type": contour.get("type", _ITEM_CONTOUR),
                "shapeType": 0,
                "path": _device_points_to_path(0, contour.get("data") or [], None),
            },
        ]
        for contour in document.get("trajectory", [])
    ]

    # The bounding box covers what the mower drives in or must keep out of.
    bounded_points = [
        point
        for collection in ("mowingAreas", "paths", "forbiddenAreas")
        for entry in collections[collection].values()
        for point in entry["path"]
    ]
    boundary = (
        {
            "x1": min(point["x"] for point in bounded_points),
            "y1": min(point["y"] for point in bounded_points),
            "x2": max(point["x"] for point in bounded_points),
            "y2": max(point["y"] for point in bounded_points),
        }
        if bounded_points
        else {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
    )

    has_zones = bool(collections["mowingAreas"])
    converted: dict = {
        "mapIndex": map_index,
        "md5sum": md5sum if has_zones else "",
        "name": document.get("name") or "",
        "totalArea": document.get("total_area", 0),
        "boundary": boundary,
        "contours": {"dataType": "Map", "value": contours},
        "cut": document.get("cut_relation", []),
    }
    for collection, entries in collections.items():
        # A map without zones keeps none of its other areas either.
        converted[collection] = _as_map_value(entries if has_zones else {})
    return converted


def parse_obstacles(entries: list) -> list[dict]:
    """Turn the mower's list of obstacles it ran into into outlines on the map.

    An entry is ``{"id", "type", "data": [[x, y], ...]}`` in the map
    document's units; the result is in map units, placed at the centre of the
    outline.
    """
    obstacles: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("data"), list):
            continue
        try:
            points = [(int(x) * _DEVICE_COORDINATE_SCALE, int(y) * _DEVICE_COORDINATE_SCALE) for x, y in entry["data"]]
            if not points:
                continue
            obstacles.append({
                "id": int(entry.get("id", len(obstacles))),
                "type": int(entry.get("type", 0)),
                "x": round(sum(x for x, _ in points) / len(points)),
                "y": round(sum(y for _, y in points) / len(points)),
                "polygon": [value for point in points for value in point],
            })
        except (TypeError, ValueError):
            continue
    return obstacles


def _percent(value: object) -> int | None:
    """A confidence in percent, from a percentage or from a fraction of one."""
    if not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
        if isinstance(value, float) and number <= 1:
            number *= 100
        return round(number)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_ai_obstacles(entries: list) -> list[dict]:
    """Turn the mower's list of recognised obstacles into positions on the map.

    An entry is either ``[xs, ys, confidence, type, image, ignored, id]``, the
    outline of the obstacle in map units, or ``[x, y, confidence, type]``, a
    single point. An obstacle the user chose to ignore is left out; the rest
    are placed at the centre of their outline, with how sure the mower is of
    the kind (in percent) and the name of the photo it took, if any. An
    outline also gives the box around it, ``bounds`` [x0, y0, x1, y1], and the
    mower's own id, which an obstacle needs to be ignored (``ignorable``).
    """
    obstacles: list[dict] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, (list, tuple)) or len(entry) < 4:
            continue
        try:
            if isinstance(entry[0], (list, tuple)):
                xs = [float(value) for value in entry[0]]
                ys = [float(value) for value in entry[1]]
                if not xs or len(xs) != len(ys):
                    continue
                if len(entry) > 5 and entry[5]:
                    continue
                x, y = sum(xs) / len(xs), sum(ys) / len(ys)
                ignorable = len(entry) > 6 and isinstance(entry[6], (int, str)) and not isinstance(entry[6], bool) and entry[6] != ""
                obstacle_id = entry[6] if ignorable else index
                image = entry[4] if len(entry) > 4 and isinstance(entry[4], str) and entry[4] else None
                bounds: list[int] | None = [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]
            else:
                x, y = float(entry[0]), float(entry[1])
                image = entry[4] if len(entry) > 4 and isinstance(entry[4], str) and entry[4] else None
                obstacle_id = image or index
                ignorable = False
                bounds = None
            obstacles.append(
                {
                    "id": obstacle_id,
                    "type": int(entry[3]),
                    "x": round(x),
                    "y": round(y),
                    "confidence": _percent(entry[2]),
                    "image": image,
                    "bounds": bounds,
                    "ignorable": ignorable,
                }
            )
        except (TypeError, ValueError):
            continue
    return obstacles


def parse_cached_maps(batch_data: dict) -> list[MowerVectorMap]:
    """Parse every map slot held in the MAP.* keys of the batch device data.

    The slots are returned as they are stored, including any that hold no map;
    has_map tells those apart.
    """
    if not batch_data:
        return []

    raw_map = reassemble_map_chunks(batch_data, "MAP")
    if not raw_map:
        _LOGGER.debug("No MAP chunks found in batch data")
        return []

    # MAP.info holds the character length of the JSON array that carries every
    # map (one element per mapIndex). The keys are rewritten without removing
    # the higher-numbered ones a longer earlier write left behind, so anything
    # beyond that length is stale and only the array itself is parsed.
    map_info = batch_data.get("MAP.info", "")
    try:
        split_pos = int(map_info) if map_info.isdigit() else 0
    except (ValueError, AttributeError):
        split_pos = 0

    if split_pos > 0 and split_pos < len(raw_map):
        raw_map = raw_map[:split_pos]

    map_arrays = []
    primary = raw_map.strip()
    if primary:
        try:
            arr = json.loads(primary)
            if isinstance(arr, list):
                map_arrays.extend(arr)
        except json.JSONDecodeError:
            _LOGGER.debug("Failed to parse MAP array (len=%d)", len(primary))

    if not map_arrays:
        _LOGGER.warning("No valid MAP arrays found in batch data")
        return []

    parsed_maps: list[MowerVectorMap] = []
    for map_json_str in map_arrays:
        try:
            parsed_maps.append(parse_mower_map(map_json_str))
        except (json.JSONDecodeError, KeyError, TypeError) as ex:
            _LOGGER.warning("Failed to parse map entry: %s", ex)
            continue

    return parsed_maps


def has_map(vmap: MowerVectorMap) -> bool:
    """Return whether a map slot holds a map.

    Every mower keeps a fixed number of map slots, and a slot without a map,
    including one whose map was deleted, carries an empty hash and no zones.
    """
    return vmap.md5sum != "" or bool(vmap.zones)


def assemble_vector_map(parsed_maps: list[MowerVectorMap]) -> MowerVectorMap | None:
    """Combine the maps of a mower into the root entry the device works from.

    The root is the primary map (mapIndex 0), or the first map when there is
    none; every map is attached to it for active-map resolution.
    """
    if not parsed_maps:
        return None

    ordered_maps = sorted(parsed_maps, key=lambda item: item.map_id)
    primary_map = next((vmap for vmap in ordered_maps if vmap.map_index == 0), ordered_maps[0])

    available_maps = [
        MowerAvailableMap(
            map_id=vmap.map_id,
            map_index=vmap.map_index,
            name=vmap.name,
            total_area=vmap.total_area,
        )
        for vmap in ordered_maps
    ]

    parsed_maps_by_id = {vmap.map_id: vmap for vmap in ordered_maps}
    for vmap in ordered_maps:
        vmap.available_maps = available_maps

    primary_map.maps = parsed_maps_by_id
    return primary_map


def parse_batch_map_data(batch_data: dict) -> MowerVectorMap | None:
    """Parse complete batch device data response into a MowerVectorMap.

    The MAP.* keys are a copy of the mower's maps that is only brought up to
    date from time to time, so this reads them as they stand. It:
    1. Reassembles MAP.* chunks into a full JSON string
    2. Parses the JSON array (may contain multiple maps by mapIndex)
    3. Drops the slots that hold no map
    4. Returns the primary map (mapIndex 0) with all maps attached for active-map resolution

    Args:
        batch_data: Full response dict from get_batch_device_datas

    Returns:
        MowerVectorMap for the primary map, with all parsed maps attached for active-map resolution.
    """
    parsed_maps = [vmap for vmap in parse_cached_maps(batch_data) if has_map(vmap)]
    return assemble_vector_map(parsed_maps)
