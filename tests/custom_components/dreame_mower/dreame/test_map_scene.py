"""Tests for the map geometry the map card draws from."""

from __future__ import annotations

from custom_components.dreame_mower.dreame.map_data_parser import (
    MowerMaintenancePoint,
    MowerVectorMap,
    MowerZone,
)
from custom_components.dreame_mower.dreame.map_scene import (
    SEGMENT_BREAK,
    map_geometry,
    map_outline,
    trail_points,
)

BREAK = [SEGMENT_BREAK, SEGMENT_BREAK]


def _square_map(**kwargs) -> MowerVectorMap:
    zone = MowerZone(zone_id=1, path=[(0, 0), (10000, 0), (10000, 10000), (0, 10000)], name="Lawn")
    return MowerVectorMap(zones=[zone], **kwargs)


def test_geometry_of_no_map_is_none():
    assert map_geometry(None) is None


def test_geometry_lists_zones_as_flat_polygons_with_bounds():
    geometry = map_geometry(_square_map(map_id=2, name="Front"))

    assert geometry is not None
    assert geometry["map_id"] == 2
    assert geometry["name"] == "Front"
    assert geometry["zones"] == [
        {"id": 1, "name": "Lawn", "area": 0, "polygon": [0, 0, 10000, 0, 10000, 10000, 0, 10000]}
    ]
    assert geometry["bounds"] == [0, 0, 10000, 10000]


def test_geometry_names_unnamed_zones():
    vector_map = MowerVectorMap(zones=[MowerZone(zone_id=3, path=[(0, 0), (1, 0), (1, 1)])])

    assert map_geometry(vector_map)["zones"][0]["name"] == "Zone 3"


def test_geometry_says_which_way_a_maintenance_point_faces():
    vector_map = _square_map(maintenance_points=[MowerMaintenancePoint(point_id=1, x=100, y=200, heading=90.0)])

    assert map_geometry(vector_map)["maintenance_points"] == [{"id": 1, "x": 100, "y": 200, "heading": 90.0}]


def test_outline_keeps_only_the_zones_and_their_bounds():
    outline = map_outline(_square_map(map_id=2, name="Back"))

    assert outline == {
        "map_id": 2,
        "zones": [{"id": 1, "polygon": [0, 0, 10000, 0, 10000, 10000, 0, 10000]}],
        "bounds": [0, 0, 10000, 10000],
    }


def test_outline_of_a_map_without_zones_has_no_bounds():
    assert map_outline(MowerVectorMap(map_id=3))["bounds"] is None


def test_trail_points_mark_breaks_with_none():
    points = [[1, 2], BREAK, BREAK, [3, 4], [5, 6], BREAK]

    assert trail_points(points) == [[1, 2], None, [3, 4], [5, 6]]


def test_trail_points_drop_leading_breaks():
    assert trail_points([BREAK, [1, 2]]) == [[1, 2]]
