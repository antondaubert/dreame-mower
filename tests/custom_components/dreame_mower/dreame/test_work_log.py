"""Tests for reading the work log: the list of tasks and the details of one."""

from __future__ import annotations

import json

from custom_components.dreame_mower.dreame.work_log import work_log_details, work_log_entries, work_log_entry


def _history(**values: object) -> list[dict[str, object]]:
    piids = {"mode": 1, "duration": 2, "area": 3, "status": 7, "start": 8, "file": 9, "start_mode": 11}
    return [{"piid": piids[name], "value": value} for name, value in values.items()]


def test_an_entry_reads_the_completion_event():
    entry = work_log_entry(
        _history(mode=102, duration=40, area=6819, status=1, start=1791540000, file="ali_dreame/a.json", start_mode=1)
    )

    assert entry == {
        "start": 1791540000,
        "duration": 40,
        "area": 68.19,
        "mode": "zone",
        "result": "complete",
        "scheduled": True,
        "file": "ali_dreame/a.json",
    }


def test_an_entry_of_older_firmware_counts_whole_square_metres_and_swaps_the_status():
    entry = work_log_entry(_history(mode=0, duration=5, area=12, status=0, start=1, file=""))

    assert entry is not None
    assert entry["mode"] == "all_area"
    assert entry["area"] == 12
    assert entry["result"] == "stopped"
    assert entry["file"] is None


def test_patrols_are_left_out():
    assert work_log_entry(_history(mode=107, start=1)) is None
    assert work_log_entry(_history(mode=108, start=1)) is None


def test_entries_are_newest_first_and_listed_once():
    records = [
        {"history": json.dumps(_history(mode=100, status=1, start=100))},
        {"history": json.dumps(_history(mode=100, status=3, start=300))},
        {"history": json.dumps(_history(mode=100, status=1, start=100))},
        {"history": "not json"},
        {"history": json.dumps(_history(mode=107, start=200))},
    ]

    assert [entry["start"] for entry in work_log_entries(records)] == [300, 100]


def test_details_read_the_task_file():
    lane = [[0, 0], [0, 1], [0, 2], [0, 100], [5, 100], [5, 0]]
    document = {
        "start": 10,
        "end": 70,
        "time": 1,
        "areas": 0.5,
        "map_area": 75,
        "mode": 100,
        "result": 3,
        "start_mode": 1,
        "pref": [35, 1],
        "pre_type": 0,
        "region_status": [[1, 2]],
        "faults": [[20, 56]],
        "dock": [127, -1, 3597],
        "map": [
            {
                "id": 1,
                "type": 0,
                "area": 75.4,
                "data": [[0, 0], [100, 0], [100, 100], [0, 100]],
                "track": [*lane, [2147483647, 2147483647], [9, 9], [9, 9]],
            }
        ],
        "obstacle": [],
        "ai_obstacle": [],
    }

    details = work_log_details(document)

    assert details["mode"] == "all_area"
    assert details["result"] == "stopped"
    assert details["start_mode"] == "schedule"
    assert details["height"] == 3.5
    assert details["efficiency"] == "efficient"
    assert details["zones"] == [{"id": 1, "result": "finished"}]
    assert details["faults"] == [{"time": 20, "code": 56}]
    assert details["dock"] == {"x": 1270, "y": -10, "angle": 359.7}
    assert details["geometry"]["zones"][0]["id"] == 1
    # Points along a lane are dropped, its corners kept, and a break splits
    # the track; repeated points count once.
    assert details["tracks"] == [[[0, 0], [0, 1000], [50, 1000], [50, 0], None, [90, 90]]]


def test_an_entry_without_a_status_counts_as_incomplete():
    entry = work_log_entry(_history(mode=100, start=1))

    assert entry is not None
    assert entry["result"] == "incomplete"
