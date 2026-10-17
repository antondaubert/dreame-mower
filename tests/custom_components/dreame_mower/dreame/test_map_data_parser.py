"""Tests for the mower map data parser."""

import json
import pathlib

import pytest

from custom_components.dreame_mower.dreame.map_data_parser import (
    MowerMapBoundary,
    convert_device_map,
    has_map,
    parse_batch_map_data,
    parse_mower_map,
    reassemble_map_chunks,
    parse_ai_obstacles,
    parse_obstacles,
    resolve_zone_polygon,
)
from custom_components.dreame_mower.dreame.map_scene import map_geometry


# ---------------------------------------------------------------------------
# reassemble_map_chunks
# ---------------------------------------------------------------------------


def test_reassemble_chunks_concatenates_in_numeric_order():
    batch = {"MAP.2": "C", "MAP.0": "A", "MAP.1": "B"}
    assert reassemble_map_chunks(batch, "MAP") == "ABC"


def test_reassemble_chunks_skips_info_key():
    batch = {"MAP.0": "A", "MAP.info": "ignored"}
    assert reassemble_map_chunks(batch, "MAP") == "A"


def test_reassemble_chunks_returns_none_when_no_matching_keys():
    assert reassemble_map_chunks({"OTHER.0": "X"}, "MAP") is None


def test_reassemble_chunks_works_with_m_path_prefix():
    batch = {"M_PATH.1": "B", "M_PATH.0": "A"}
    assert reassemble_map_chunks(batch, "M_PATH") == "AB"


# ---------------------------------------------------------------------------
# MowerMapBoundary
# ---------------------------------------------------------------------------


def test_boundary_width_and_height():
    b = MowerMapBoundary(x1=10, y1=20, x2=110, y2=70)
    assert b.width == 100
    assert b.height == 50


# ---------------------------------------------------------------------------
# parse_mower_map
# ---------------------------------------------------------------------------


def _make_map_json(**overrides):
    data = {
        "mapIndex": 0,
        "name": "Garden",
        "totalArea": 50.0,
        "mowingAreas": {"dataType": "Map", "value": []},
        "forbiddenAreas": {"dataType": "Map", "value": []},
        "paths": {"dataType": "Map", "value": []},
    }
    data.update(overrides)
    return json.dumps(data)


def test_parse_mower_map_basic_fields():
    result = parse_mower_map(_make_map_json(mapIndex=0, name="Garden", totalArea=50.0))
    assert result.map_index == 0
    assert result.name == "Garden"
    assert result.total_area == 50.0


def test_parse_mower_map_zone_parsed():
    map_json = _make_map_json(
        mowingAreas={
            "dataType": "Map",
            "value": [
                [1, {"path": [{"x": 0, "y": 0}, {"x": 100, "y": 0}], "name": "Zone1", "area": 25.0}]
            ],
        }
    )
    result = parse_mower_map(map_json)
    assert len(result.zones) == 1
    assert result.zones[0].zone_id == 1
    assert result.zones[0].name == "Zone1"
    assert result.zones[0].path == [(0, 0), (100, 0)]
    assert result.zones[0].area == 25.0


def test_parse_mower_map_maintenance_point_parsed():
    """A maintenance point is one coordinate the mower can be sent to."""
    map_json = _make_map_json(
        cleanPoints={
            "dataType": "Map",
            "value": [[1, {"id": 1, "type": 6, "shapeType": 5, "path": [{"x": -2270, "y": 30}]}]],
        }
    )

    result = parse_mower_map(map_json)

    assert len(result.maintenance_points) == 1
    assert result.maintenance_points[0].point_id == 1
    assert (result.maintenance_points[0].x, result.maintenance_points[0].y) == (-2270, 30)


def test_parse_mower_map_maintenance_point_without_a_position_is_skipped():
    """A point with no coordinate is nowhere to drive to."""
    map_json = _make_map_json(
        cleanPoints={"dataType": "Map", "value": [[2, {"id": 2, "path": []}]]}
    )

    assert parse_mower_map(map_json).maintenance_points == []


def test_parse_mower_map_without_maintenance_points():
    """A map that carries none reports none."""
    assert parse_mower_map(_make_map_json()).maintenance_points == []


def test_parse_mower_map_boundary():
    map_json = _make_map_json(boundary={"x1": 10, "y1": 20, "x2": 110, "y2": 120})
    result = parse_mower_map(map_json)
    assert result.boundary is not None
    assert result.boundary.width == 100
    assert result.boundary.height == 100


def test_parse_mower_map_forbidden_area():
    map_json = _make_map_json(
        forbiddenAreas={
            "dataType": "Map",
            "value": [[2, {"path": [{"x": 5, "y": 5}], "name": "Forbidden"}]],
        }
    )
    result = parse_mower_map(map_json)
    assert len(result.forbidden_areas) == 1
    assert result.forbidden_areas[0].zone_id == 2


def test_parse_mower_map_forbidden_area_captures_shape_and_angle():
    map_json = _make_map_json(
        forbiddenAreas={
            "dataType": "Map",
            "value": [
                [3, {
                    "path": [{"x": 0, "y": 0}, {"x": 10, "y": 0},
                             {"x": 10, "y": 10}, {"x": 0, "y": 10}],
                    "shapeType": 2,
                    "angle": 30.0,
                }],
            ],
        }
    )
    result = parse_mower_map(map_json)
    fa = result.forbidden_areas[0]
    assert fa.shape_type == 2
    assert fa.angle == 30.0


def test_resolve_zone_polygon_polygon_unchanged():
    path = [(0, 0), (10, 0), (10, 10)]
    assert resolve_zone_polygon(0, 0.0, path) == path


def test_resolve_zone_polygon_circle_expands_bbox_to_polygon():
    # Two opposite corners of a 100x100 bounding box -> circle centred at (50, 50).
    polygon = resolve_zone_polygon(3, 0.0, [(0, 0), (100, 100)])
    assert len(polygon) == 36
    # Every vertex lies on the radius-50 circle centred at (50, 50).
    for x, y in polygon:
        assert abs((x - 50) ** 2 + (y - 50) ** 2 - 50 ** 2) <= 100


def test_resolve_zone_polygon_rotates_rectangle_by_angle():
    square = [(-10, -10), (10, -10), (10, 10), (-10, 10)]
    rotated = resolve_zone_polygon(2, 90.0, square)
    # The device angle is negated to match the rendered (Y-flipped) frame, so a
    # 90° rotation about the centroid (0, 0) maps (-10, -10) -> (-10, 10).
    assert rotated[0] == (-10, 10)
    # Centroid is preserved.
    assert (sum(p[0] for p in rotated), sum(p[1] for p in rotated)) == (0, 0)


def test_resolve_zone_polygon_rectangle_no_angle_unchanged():
    square = [(-10, -10), (10, -10), (10, 10), (-10, 10)]
    assert resolve_zone_polygon(2, 0.0, square) == square


def test_map_geometry_expands_forbidden_shapes():
    map_json = _make_map_json(
        forbiddenAreas={
            "dataType": "Map",
            "value": [
                [1, {"path": [{"x": 0, "y": 0}, {"x": 100, "y": 100}], "shapeType": 3}],
            ],
        }
    )
    vmap = parse_mower_map(map_json)
    geometry = map_geometry(vmap)
    assert geometry is not None
    assert len(geometry["no_go"]) == 1
    # Circle expanded to a 36-point polygon, stored as flat x, y pairs.
    assert len(geometry["no_go"][0]["polygon"]) == 72


def test_parse_mower_map_ignore_obstacle_areas():
    map_json = _make_map_json(
        notObsAreas={
            "dataType": "Map",
            "value": [
                [101, {"id": 101, "type": 10, "shapeType": 2, "path": [
                    {"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 50}, {"x": 0, "y": 50},
                ], "angle": 0}],
            ],
        }
    )
    vmap = parse_mower_map(map_json)
    assert len(vmap.ignore_obstacle_areas) == 1
    area = vmap.ignore_obstacle_areas[0]
    assert area.zone_id == 101
    assert area.path == [(0, 0), (100, 0), (100, 50), (0, 50)]
    geometry = map_geometry(vmap)
    assert geometry["ignore_obstacles"] == [
        {"id": 101, "polygon": [0, 0, 100, 0, 100, 50, 0, 50], "shape": "rectangle", "rect": [0, 0, 100, 50]}
    ]


def test_device_map_semantic_areas_become_ignore_obstacle_areas():
    document = {
        "map": [{"id": 1, "type": 0, "data": [[0, 0], [100, 0], [100, 100]], "name": "Lawn"}],
        "semantic": [{"id": 101, "type": 10, "data": [[52, -962], [-1212, -962], [-1212, -862], [52, -862]]}],
    }
    vmap = parse_mower_map(convert_device_map(document, 0, "hash"))
    assert [area.zone_id for area in vmap.ignore_obstacle_areas] == [101]
    polygon = map_geometry(vmap)["ignore_obstacles"][0]["polygon"]
    corners = sorted(zip(polygon[0::2], polygon[1::2]))
    assert corners == [(-12120, -9620), (-12120, -8620), (520, -9620), (520, -8620)]


def test_parse_obstacles_scales_to_map_units():
    entries = [
        {"data": [[0, 0], [10, 0], [10, 10], [0, 10]], "id": 2, "type": 0},
        {"id": 3},  # no outline
        "junk",
    ]
    assert parse_obstacles(entries) == [
        {"id": 2, "type": 0, "x": 50, "y": 50, "polygon": [0, 0, 100, 0, 100, 100, 0, 100]}
    ]


def test_parse_ai_obstacles_outline_form():
    entries = [
        [[100, 200, 200, 100], [0, 0, 100, 100], 95, 99, "img1", 0, 7],
        [[0, 10], [0, 10], 80, 2, "img2", 1, 8],  # ignored by the user
        [[0, 10], [0, 10], 60, 0, "", 0, 9],  # no photo taken
    ]
    assert parse_ai_obstacles(entries) == [
        {"id": 7, "type": 99, "x": 150, "y": 50, "confidence": 95, "image": "img1", "bounds": [100, 0, 200, 100], "ignorable": True},
        {"id": 9, "type": 0, "x": 5, "y": 5, "confidence": 60, "image": None, "bounds": [0, 0, 10, 10], "ignorable": True},
    ]


def test_parse_ai_obstacles_point_form_and_junk():
    assert parse_ai_obstacles([[1000, -2000, 0.7, 6], "junk", [1, 2]]) == [
        {"id": 0, "type": 6, "x": 1000, "y": -2000, "confidence": 70, "image": None, "bounds": None, "ignorable": False}
    ]


@pytest.mark.parametrize("entry", [[[0, 10], [0, 10], 80, 2, "img"], [[0, 10], [0, 10], 80, 2, "img", 0, ""], [[0, 10], [0, 10], 80, 2, "img", 0, True]])
def test_an_outline_without_the_mowers_id_cannot_be_ignored(entry):
    (obstacle,) = parse_ai_obstacles([entry])
    assert obstacle["ignorable"] is False
    assert obstacle["id"] == 0


def test_parse_mower_map_contours():
    map_json = _make_map_json(
        contours={
            "dataType": "Map",
            "value": [
                [[1, 0], {"path": [{"x": 5, "y": 6}], "type": 7, "shapeType": 0}],
            ],
        }
    )
    result = parse_mower_map(map_json)
    assert len(result.contours) == 1
    assert result.contours[0].contour_id == (1, 0)
    assert result.contours[0].path == [(5, 6)]


def test_parse_mower_map_contours_accepts_string_ids():
    map_json = _make_map_json(
        contours={
            "dataType": "Map",
            "value": [
                ["1,0", {"path": [{"x": 5, "y": 6}], "type": 7, "shapeType": 0}],
            ],
        }
    )
    result = parse_mower_map(map_json)
    assert len(result.contours) == 1
    assert result.contours[0].contour_id == (1, 0)
    assert result.contours[0].path == [(5, 6)]


def test_parse_mower_map_spot_areas():
    map_json = _make_map_json(
        spotAreas={
            "dataType": "Map",
            "value": [
                [4, {"path": [{"x": 7, "y": 8}], "name": "Tree", "area": 2.5, "shapeType": 1}],
            ],
        }
    )
    result = parse_mower_map(map_json)
    assert len(result.spot_areas) == 1
    assert result.spot_areas[0].area_id == 4
    assert result.spot_areas[0].path == [(7, 8)]
    assert result.spot_areas[0].name == "Tree"


# ---------------------------------------------------------------------------
# parse_batch_map_data
# ---------------------------------------------------------------------------


def test_parse_batch_map_data_returns_none_on_empty():
    assert parse_batch_map_data({}) is None


def test_parse_batch_map_data_returns_none_when_no_map_keys():
    assert parse_batch_map_data({"OTHER.0": "data"}) is None


def test_parse_batch_map_data_happy_path():
    map_data = {
        "mapIndex": 0,
        "name": "Main",
        "totalArea": 100.0,
        "mowingAreas": {"dataType": "Map", "value": []},
        "forbiddenAreas": {"dataType": "Map", "value": []},
        "paths": {"dataType": "Map", "value": []},
    }
    chunk = json.dumps([json.dumps(map_data)])
    result = parse_batch_map_data({"MAP.0": chunk})
    assert result is not None
    assert result.name == "Main"
    assert result.total_area == 100.0


def test_parse_batch_map_data_tracks_available_maps_and_active_map():
    first_map = {
        "mapIndex": 0,
        "name": "Front",
        "totalArea": 42.0,
        "mowingAreas": {"dataType": "Map", "value": []},
        "forbiddenAreas": {"dataType": "Map", "value": []},
        "paths": {"dataType": "Map", "value": []},
    }
    second_map = {
        "mapIndex": 1,
        "name": "Back",
        "totalArea": 21.0,
        "mowingAreas": {"dataType": "Map", "value": []},
        "forbiddenAreas": {"dataType": "Map", "value": []},
        "paths": {"dataType": "Map", "value": []},
    }
    chunk = json.dumps([json.dumps(first_map), json.dumps(second_map)])

    result = parse_batch_map_data({"MAP.0": chunk})

    assert result is not None
    assert result.map_id == 1
    assert result.current_map_id is None
    assert [(entry.map_id, entry.map_index, entry.name) for entry in result.available_maps] == [
        (1, 0, "Front"),
        (2, 1, "Back"),
    ]
    assert sorted(result.maps) == [1, 2]
    assert result.maps[2].name == "Back"


# ---------------------------------------------------------------------------
# Real-device payloads (captured fixtures)
# ---------------------------------------------------------------------------

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with (FIXTURES_DIR / name).open() as fh:
        return json.load(fh)


def test_parse_batch_map_data_real_two_map_payload():
    """A real multi-chunk batch response with two maps parses both maps.

    The reassembled MAP stream is a single JSON array (length given by
    MAP.info) followed by trailing auxiliary data. Both maps must be
    recovered from the primary array.
    """
    batch = _load_fixture("batch_map_two_maps.json")

    result = parse_batch_map_data(batch)

    assert result is not None
    # Primary map is mapIndex 0.
    assert result.map_index == 0
    assert result.name == "Zuhause"
    assert result.total_area == 71
    # Both maps are tracked.
    assert [(e.map_index, e.name) for e in result.available_maps] == [
        (0, "Zuhause"),
        (1, "Keller"),
    ]
    assert sorted(result.maps) == [1, 2]
    # Geometry parsed for both maps.
    assert result.maps[1].zones[0].name == "Zone1"
    assert result.maps[1].boundary == MowerMapBoundary(
        x1=-11910, y1=-9210, x2=520, y2=3890
    )
    assert result.maps[2].name == "Keller"
    assert result.maps[2].boundary == MowerMapBoundary(
        x1=-2810, y1=-1870, x2=630, y2=640
    )


def test_parse_batch_map_data_real_large_two_map_payload():
    """A larger real payload (45 chunks, two maps) parses both maps.

    Exercises a different device with a bigger primary array
    (MAP.info=30147) and trailing auxiliary data.
    """
    batch = _load_fixture("batch_map_jardin_terrain.json")

    result = parse_batch_map_data(batch)

    assert result is not None
    assert result.map_index == 0
    assert result.name == "Jardin"
    assert [(e.map_index, e.name) for e in result.available_maps] == [
        (0, "Jardin"),
        (1, "Terrain"),
    ]
    assert sorted(result.maps) == [1, 2]
    assert result.maps[1].boundary == MowerMapBoundary(
        x1=-26090, y1=-13100, x2=2020, y2=32730
    )
    assert result.maps[2].name == "Terrain"
    assert result.maps[2].boundary == MowerMapBoundary(
        x1=-40720, y1=-6300, x2=0, y2=31290
    )


def test_parse_batch_map_data_drops_slots_that_hold_no_map():
    """A slot without a map is stored with an empty hash and no zones.

    Every mower keeps a fixed number of map slots, so a mower with a single map
    still stores a second, empty one. Listing it offers a map that does not
    exist.
    """
    batch = _load_fixture("batch_map_circles_tilted_rect.json")

    result = parse_batch_map_data(batch)

    assert result is not None
    assert [(e.map_index, e.name) for e in result.available_maps] == [(0, "Map1")]
    assert sorted(result.maps) == [1]


def test_has_map_keeps_a_map_whose_source_carries_no_hash():
    """Only an explicitly empty hash marks an empty slot."""
    assert has_map(parse_mower_map({"mapIndex": 0}))
    assert not has_map(parse_mower_map({"mapIndex": 1, "md5sum": ""}))


# ---------------------------------------------------------------------------
# convert_device_map
# ---------------------------------------------------------------------------


def _as_comparable(stored_map: dict) -> dict:
    """Reduce a stored map to what parse_mower_map reads, with rounded points."""
    comparable = {}
    for key, value in stored_map.items():
        if isinstance(value, dict) and value.get("dataType") == "Map":
            comparable[key] = {
                str(item_key): {
                    field: (
                        [(round(p["x"], 3), round(p["y"], 3)) for p in item[field]]
                        if field == "path"
                        else item[field]
                    )
                    for field in item
                    # Only the mower's own map says which way a point faces;
                    # the times are not read.
                    if field not in ("heading", "time", "etime")
                }
                for item_key, item in value["value"]
            }
        else:
            comparable[key] = value
    return comparable


@pytest.mark.parametrize("map_position", [0, 1])
def test_convert_device_map_matches_the_stored_copy_of_the_same_map(map_position):
    """A map read from the mower converts to the form the MAP.* keys store it in.

    The stored copy of each map was written for the same hash the mower reports,
    so the two must agree on every field the stored form carries.
    """
    fixture = _load_fixture("device_map_two_maps.json")
    device_map = fixture["maps"][map_position]
    stored = _as_comparable(fixture["cache"][map_position])

    converted = _as_comparable(
        convert_device_map(
            device_map["document"],
            fixture["map_list"][map_position][0],
            device_map["info"]["hash"],
        )
    )

    for key, value in converted.items():
        assert value == stored[key], key


def test_convert_device_map_names_unnamed_zones_by_their_position():
    """A zone without a name is called Zone<n>, n counting zones in order."""
    document = {
        "map": [
            {"id": 7, "type": 0, "name": "", "data": [[0, 0], [10, 0], [10, 10]]},
            {"id": 3, "type": 0, "name": "Front lawn", "data": [[0, 0], [5, 0], [5, 5]]},
            {"id": 9, "type": 0, "data": [[0, 0], [2, 0], [2, 2]]},
        ],
    }

    vmap = parse_mower_map(convert_device_map(document, 0, "abc"))

    assert [(zone.zone_id, zone.name) for zone in vmap.zones] == [
        (7, "Zone1"),
        (3, "Front lawn"),
        (9, "Zone3"),
    ]


def test_convert_device_map_keeps_a_default_name_apart_from_a_taken_one():
    """A default name another zone already carries gets a trailing underscore."""
    document = {
        "map": [
            {"id": 1, "type": 0, "name": "", "data": [[0, 0], [10, 0], [10, 10]]},
            {"id": 2, "type": 0, "name": "Zone1", "data": [[0, 0], [5, 0], [5, 5]]},
        ],
    }

    vmap = parse_mower_map(convert_device_map(document, 0, "abc"))

    assert [zone.name for zone in vmap.zones] == ["Zone1_", "Zone1"]


def test_convert_device_map_without_zones_holds_no_map():
    """A map with no zones is stored as an empty slot, like a deleted one."""
    document = {
        "name": "Back",
        "map": [{"id": 4, "type": 2, "data": [[0, 0], [1, 0], [1, 1]]}],
    }

    vmap = parse_mower_map(convert_device_map(document, 1, "abc"))

    assert vmap.md5sum == ""
    assert vmap.forbidden_areas == []
    assert not has_map(vmap)


def test_convert_device_map_scales_points_and_sorts_items_by_type():
    """Coordinates are scaled to map units and each item lands in its collection."""
    document = {
        "name": "Garden",
        "total_area": 12.5,
        "map": [
            {"id": 1, "type": 0, "name": "Lawn", "area": 12.5, "time": 30, "data": [[0, 0], [20, 0], [20, 10], [0, 10]]},
            {"id": 5, "type": 1, "data": [[0, 0], [-4, 3]]},
        ],
        "spot": [{"id": 11, "type": 3, "name": "Corner", "data": [[1, 1], [2, 1], [2, 2]]}],
        "point": [
            {"id": 1, "type": 1, "point": [3, 4, 0]},
            {"id": 2, "type": 2, "point": [5, 6, 0]},
        ],
        "trajectory": [{"id": [1, 0], "data": [[0, 0], [20, 0]]}],
    }

    vmap = parse_mower_map(convert_device_map(document, 0, "abc"))

    assert vmap.name == "Garden"
    assert vmap.total_area == 12.5
    assert vmap.md5sum == "abc"
    assert vmap.zones[0].path == [(0, 0), (200, 0), (200, 100), (0, 100)]
    assert vmap.zones[0].area == 12.5
    assert vmap.paths[0].path == [(0, 0), (-40, 30)]
    assert vmap.spot_areas[0].name == "Corner"
    assert vmap.spot_areas[0].path == [(10, 10), (20, 10), (20, 20)]
    # Only a point of type 1 is a maintenance point.
    assert [(p.point_id, p.x, p.y) for p in vmap.maintenance_points] == [(1, 30, 40)]
    assert vmap.contours[0].contour_id == (1, 0)
    assert vmap.contours[0].path == [(0, 0), (200, 0)]
    # The boundary spans zones and paths, not spot areas or points.
    assert vmap.boundary == MowerMapBoundary(x1=-40, y1=0, x2=200, y2=100)


def test_convert_device_map_keeps_a_circle_as_its_bounding_box():
    """A circular no-go area is reported by centre and radius."""
    document = {
        "map": [
            {"id": 1, "type": 0, "data": [[0, 0], [20, 0], [20, 10]]},
            {"id": 2, "type": 2, "data": [[5, 5]], "description": {"type": 3, "points": [[5, 5]], "radius": 2}},
        ],
    }

    vmap = parse_mower_map(convert_device_map(document, 0, "abc"))

    assert vmap.forbidden_areas[0].shape_type == 3
    assert vmap.forbidden_areas[0].path == [(30, 30), (70, 70)]


def test_convert_device_map_stores_a_tilted_rectangle_the_way_it_renders():
    """A tilted rectangular no-go area renders back at the corners it was reported at."""
    corners = [(10.0, 0.0), (18.660254, 5.0), (13.660254, 13.660254), (5.0, 8.660254)]
    document = {
        "map": [
            {"id": 1, "type": 0, "data": [[0, 0], [20, 0], [20, 20]]},
            {"id": 2, "type": 2, "data": [list(c) for c in corners], "description": {"type": 2}},
        ],
    }

    vmap = parse_mower_map(convert_device_map(document, 0, "abc"))
    area = vmap.forbidden_areas[0]
    rendered = resolve_zone_polygon(area.shape_type, area.angle, area.path)

    assert area.angle != 0
    # Stored axis-aligned: two distinct x and two distinct y values.
    assert len({round(x, 3) for x, _ in area.path}) == 2
    assert len({round(y, 3) for _, y in area.path}) == 2
    assert sorted(rendered) == sorted((round(x * 10), round(y * 10)) for x, y in corners)




def test_parse_ai_obstacles_without_a_usable_confidence():
    entries = [[[0, 10], [0, 10], None, 0, "img", 0, 1], [[0, 10], [0, 10], "high", 1, "img2", 0, 2]]

    assert [obstacle["confidence"] for obstacle in parse_ai_obstacles(entries)] == [None, None]


def test_areas_come_in_the_form_they_are_edited_in():
    from custom_components.dreame_mower.dreame.map_scene import _editable_shape

    assert _editable_shape(1, 0, [(0, 0), (100, 50)]) == {"shape": "line", "line": [0, 0, 100, 50]}
    assert _editable_shape(2, 0, [(100, 0), (0, 0), (0, 50), (100, 50)]) == {"shape": "rectangle", "rect": [0, 0, 100, 50]}
    assert _editable_shape(3, 0, [(0, 0), (100, 100)]) == {"shape": "circle", "circle": [50, 50, 50]}
    # A turned rectangle or a decorative shape can only be deleted.
    assert _editable_shape(2, 30, [(100, 0), (0, 0), (0, 50), (100, 50)]) == {"shape": "polygon"}
    assert _editable_shape(12, 0, [(0, 0), (100, 0), (50, 80)]) == {"shape": "polygon"}


@pytest.mark.parametrize("stored,heading", [(50, 90.0), (150, 270.0), (0, 0.0)])
def test_a_maintenance_point_keeps_the_way_it_faces(stored, heading):
    """A point's third value is its heading, in hundredths of a half turn."""
    document = {
        "map": [{"id": 1, "type": 0, "data": [[0, 0], [500, 0], [500, 500]]}],
        "point": [{"id": 1, "point": [-227, 3, stored], "time": 60, "type": 1}],
    }

    (point,) = parse_mower_map(convert_device_map(document, 0, "abc")).maintenance_points

    assert (point.x, point.y, point.heading) == (-2270, 30, heading)


def test_a_maintenance_point_without_a_heading_has_none():
    document = {
        "map": [{"id": 1, "type": 0, "data": [[0, 0], [500, 0], [500, 500]]}],
        "point": [{"id": 1, "point": [-227, 3], "time": 60, "type": 1}],
    }

    (point,) = parse_mower_map(convert_device_map(document, 0, "abc")).maintenance_points

    assert point.heading is None
