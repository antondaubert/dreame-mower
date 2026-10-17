"""Tests for the changes to the map that are drawn rather than driven."""

from __future__ import annotations

import pytest

from custom_components.dreame_mower.dreame import map_edit


def test_a_rectangle_goes_out_as_its_four_corners_in_metres():
    payload = map_edit.no_go_zone(None, "rectangle", [[-3400, -5600], [-3800, -6000]], None)

    assert payload == {
        "m": "a",
        "p": 0,
        "o": 215,
        "d": {"id": -1, "type": 2, "points": [[-3.4, -6.0], [-3.8, -6.0], [-3.8, -5.6], [-3.4, -5.6]]},
    }


def test_a_line_and_a_circle():
    assert map_edit.no_go_zone(7, "line", [[0, 0], [1234, 5678]], None)["d"] == {
        "id": 7,
        "type": 1,
        "points": [[0.0, 0.0], [1.23, 5.68]],
    }
    assert map_edit.no_go_zone(None, "circle", [[1000, 2000]], 500)["d"] == {
        "id": -1,
        "type": 3,
        "points": [[1.0, 2.0]],
        "radius": 0.5,
    }


@pytest.mark.parametrize(
    "shape,points,radius",
    [("square", [[0, 0], [1, 1]], None), ("rectangle", [[0, 0]], None), ("circle", [[0, 0]], None), ("line", [[0, 0]], None)],
)
def test_a_no_go_zone_needs_its_shape(shape, points, radius):
    with pytest.raises(ValueError):
        map_edit.no_go_zone(None, shape, points, radius)


def test_the_other_items():
    assert map_edit.spot_area(None, [0, 0, 1000, 500])["d"]["points"] == [[1.0, 0.0], [0.0, 0.0], [0.0, 0.5], [1.0, 0.5]]
    assert map_edit.ignore_obstacle_area(3, [0, 0, 1000, 500])["d"]["type"] == 0
    assert map_edit.maintenance_point(None, 1000, 2000, 90)["d"] == {"id": -1, "points": [1.0, 2.0, 0.5]}
    # A full turn is no turn.
    assert map_edit.maintenance_point(1, 1000, 2000, 360)["d"]["points"][2] == 0.0
    assert map_edit.maintenance_point(1, 1000, 2000, 270)["d"]["points"][2] == 1.5
    assert map_edit.delete_item("maintenance_point", 2)["d"] == {"id": 2, "type": 3}
    assert map_edit.rename_zone(1, "  Front ")["d"] == {"region": 1, "name": "Front"}
    assert map_edit.split_zone(1, [0, 0, 1000, 0])["d"] == {"id": 1, "line_start": [0.0, 0.0], "line_end": [1.0, 0.0]}
    assert map_edit.merge_zones([1, 2])["d"] == {"ids": [1, 2]}


@pytest.mark.parametrize("call", [
    lambda: map_edit.delete_item("lawn", 1),
    lambda: map_edit.rename_zone(1, ""),
    lambda: map_edit.rename_zone(1, "x" * 25),
    lambda: map_edit.merge_zones([1, 1]),
])
def test_what_the_mower_would_not_take_is_refused_before(call):
    with pytest.raises(ValueError):
        call()


def test_the_mowers_refusals_are_told():
    assert map_edit.refusal(215, {"status": True, "error": 0}) is None
    # A no-go zone across a path is kept.
    assert map_edit.refusal(215, {"status": True, "error": 1}) is None
    assert map_edit.refusal(215, {"status": False, "error": 2}) == "The no-go zone lies outside the map"
    assert map_edit.refusal(214, {"status": False, "error": -3}) == "The spot area must stay within one zone"
    assert "error 9" in map_edit.refusal(219, {"status": False, "error": 9})



def test_a_misplaced_maintenance_point_is_explained():
    assert "safe distance" in map_edit.refusal(map_edit.SET_MAINTENANCE_POINT, {"status": False, "error": 2})
    assert "no-go zone" in map_edit.refusal(map_edit.SET_MAINTENANCE_POINT, {"status": False, "error": 3})
    assert "station" in map_edit.refusal(map_edit.SET_MAINTENANCE_POINT, {"status": False, "error": 4})
