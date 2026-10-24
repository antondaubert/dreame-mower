"""Tests for how the work log rates the battery use of a task."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.dreame_mower.work_log_cache import rate_battery

DAY = 24 * 3600
START = 1_790_000_000


def _task(day: int, per_sqm: float | None, area: float = 68.5, mode: str = "all_area", result: str = "complete") -> dict[str, Any]:
    battery = None if per_sqm is None else {"used": round(per_sqm * area, 1), "per_sqm": per_sqm, "source": "recorded"}
    return {"start": START + day * DAY, "area": area, "mode": mode, "result": result, "battery": battery}


def _rate(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # The log keeps the newest first.
    entries = sorted(tasks, key=lambda task: task["start"], reverse=True)
    rate_battery(entries)
    return sorted(entries, key=lambda task: task["start"])


def test_a_task_is_rated_against_the_median_of_like_tasks_before_it() -> None:
    usual = [_task(day, per_sqm) for day, per_sqm in enumerate([0.50, 0.52, 0.54, 0.56, 0.58])]
    *_, normal, high, very_high = _rate([*usual, _task(10, 0.62), _task(11, 0.70), _task(12, 1.49)])

    assert normal["battery"]["usual"] == 0.54 and normal["battery"]["rating"] == "normal"
    # The normal one counts for the next ones: the median moves with it.
    assert high["battery"]["usual"] == 0.55 and high["battery"]["rating"] == "high"
    assert very_high["battery"]["rating"] == "very_high"


def test_a_task_needs_enough_like_tasks_before_it() -> None:
    rated = _rate([_task(day, 0.5) for day in range(5)])

    assert all("rating" not in task["battery"] for task in rated)


# Tasks that would outnumber the like ones if they counted.
@pytest.mark.parametrize(
    "other",
    [
        {"mode": "zone"},
        {"area": 40.0},
        {"result": "stopped"},
    ],
)
def test_unlike_tasks_do_not_count(other: dict[str, Any]) -> None:
    usual = [_task(day, 0.5) for day in range(5)]
    unlike = [_task(5 + day, 3.0, **other) for day in range(8)]

    rated = _rate([*usual, *unlike, _task(20, 0.5)])

    assert rated[-1]["battery"]["usual"] == 0.5


def test_tasks_from_two_months_before_do_not_count() -> None:
    rated = _rate([*[_task(day, 0.5) for day in range(5)], _task(70, 0.9)])

    assert "rating" not in rated[-1]["battery"]


def test_only_the_last_like_tasks_count() -> None:
    old = [_task(day, 2.0) for day in range(20)]
    recent = [_task(20 + day, 0.5) for day in range(10)]

    rated = _rate([*old, *recent, _task(40, 0.5)])

    # Fifteen tasks: the ten recent ones and five old ones.
    assert rated[-1]["battery"]["usual"] == 0.5


def test_a_task_that_did_not_finish_gets_no_rating() -> None:
    usual = [_task(day, 0.5) for day in range(5)]

    rated = _rate([*usual, _task(5, 2.0, result="stopped")])

    assert "rating" not in rated[-1]["battery"]


def test_a_small_task_gets_no_rating() -> None:
    usual = [_task(day, 0.5, area=8.0) for day in range(5)]

    rated = _rate([*usual, _task(5, 2.0, area=8.0)])

    assert "rating" not in rated[-1]["battery"]
