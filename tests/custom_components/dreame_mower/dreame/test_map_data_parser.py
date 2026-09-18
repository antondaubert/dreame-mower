"""Tests for the mower map data parser."""

import json
import pathlib

import pytest

from custom_components.dreame_mower.dreame.map_data_parser import (
    MowerMapBoundary,
    parse_batch_map_data,
    parse_mow_paths,
    parse_mower_map,
    reassemble_map_chunks,
    resolve_zone_polygon,
    vector_map_to_map_data,
)


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
    assert result.last_updated is not None


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


def test_vector_map_to_map_data_expands_forbidden_shapes():
    map_json = _make_map_json(
        forbiddenAreas={
            "dataType": "Map",
            "value": [
                [1, {"path": [{"x": 0, "y": 0}, {"x": 100, "y": 100}], "shapeType": 3}],
            ],
        }
    )
    vmap = parse_mower_map(map_json)
    data = vector_map_to_map_data(vmap)
    assert len(data["obstacle"]) == 1
    # Circle expanded to a 36-point renderable polygon (svg_polygon needs >= 3).
    assert len(data["obstacle"][0]["data"]) == 36


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
# parse_mow_paths
# ---------------------------------------------------------------------------


def test_parse_mow_paths_segments_split_on_sentinel():
    raw = "[[10,20],[30,40],[32767,-32768],[50,60]]"
    result = parse_mow_paths({"M_PATH.0": raw})
    assert len(result) == 1
    assert len(result[0].segments) == 2
    # Coordinates are scaled by 10
    assert result[0].segments[0][0] == (100, 200)
    assert result[0].segments[1][0] == (500, 600)


def test_parse_mow_paths_empty_input():
    assert parse_mow_paths({}) == []


def test_parse_mow_paths_empty_array():
    assert parse_mow_paths({"M_PATH.0": "[]"}) == []


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


def test_parse_batch_map_data_attaches_mow_paths():
    map_data = {
        "mapIndex": 0,
        "name": "Main",
        "totalArea": 0,
        "mowingAreas": {"dataType": "Map", "value": []},
        "forbiddenAreas": {"dataType": "Map", "value": []},
        "paths": {"dataType": "Map", "value": []},
    }
    chunk = json.dumps([json.dumps(map_data)])
    batch = {
        "MAP.0": chunk,
        "M_PATH.0": "[[1,2],[3,4]]",
    }
    result = parse_batch_map_data(batch)
    assert result is not None
    assert len(result.mow_paths) == 1


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
