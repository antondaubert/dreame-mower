"""Tests for the line that says what the mower is doing."""

from __future__ import annotations

import pytest

from custom_components.dreame_mower.dreame.status_text import status_text


def _state(**changes):
    state = {
        "main_state": 0,
        "sub_state": 255,
        "location": "idle",
        "docking": "in_station",
        "leaving_station": False,
        "work_mode": None,
        "scheduled": None,
        "charging": False,
    }
    state.update(changes)
    return state


@pytest.mark.parametrize(
    "online,state,codes,text",
    [
        (False, _state(), set(), "Offline"),
        (True, None, set(), None),
        (True, _state(), set(), "Standby"),
        (True, _state(charging=True), set(), "Charging"),
        (True, _state(location="relocating", docking="out_of_station"), set(), "Repositioning"),
        (True, _state(docking="finish_docking"), set(), "Returning to the station"),
        (True, _state(docking="finish_docking"), {56}, "Rain protection activated. Returning to the station"),
        (True, _state(charging=True), {56}, "Rain protection is activated"),
        (True, _state(main_state=4, sub_state=36, docking="out_of_station"), {56}, "Rain protection is on. Task paused"),
        (True, _state(main_state=4, sub_state=35, work_mode=0, docking="out_of_station"), set(), "All-area mowing ongoing"),
        (True, _state(main_state=4, sub_state=35, work_mode=2, scheduled=True, docking="out_of_station"), set(), "Scheduled zone mowing ongoing"),
        (True, _state(main_state=4, sub_state=34, work_mode=0, docking="out_of_station"), set(), "Starting all-area mowing"),
        (True, _state(main_state=4, sub_state=36, work_mode=1, docking="pause_docking"), set(), "Edge mowing paused. Returning to the station"),
        (True, _state(main_state=4, sub_state=37, work_mode=0, docking="finish_docking"), set(), "Mowing completed. Returning to the station"),
        (True, _state(main_state=4, sub_state=35, work_mode=8), set(), "Patrolling"),
        (True, _state(docking="pause_docking"), {54}, "Battery is low. Returning to charge"),
        (True, _state(main_state=3), {56}, "Mapping"),
    ],
)
def test_the_mower_is_described_like_its_app_does(online, state, codes, text):
    assert status_text(online, state, frozenset(codes)) == text
