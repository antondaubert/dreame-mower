"""Tests for the served map card and the map feed it draws from."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator, WebSocketGenerator

from custom_components.dreame_mower.config_flow import (
    CONF_ACCOUNT_TYPE,
    CONF_COUNTRY,
    CONF_DID,
    CONF_MAC,
    CONF_MODEL,
    CONF_SERIAL,
)
from custom_components.dreame_mower.const import CONF_MAP_ROTATION, DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.coordinator import DreameMowerCoordinator, zone_settings
from custom_components.dreame_mower.dreame.const import MowingPreferenceMode
from custom_components.dreame_mower.dreame.map_data_parser import MowerVectorMap, MowerZone
from custom_components.dreame_mower.dreame.map_scene import SEGMENT_BREAK, stripe_angle
from custom_components.dreame_mower.frontend import CARD_3D_URL, CARD_URL, async_setup_frontend
from custom_components.dreame_mower.map_api import WS_OBSTACLE_PHOTO, WS_SUBSCRIBE_MAP, WS_WORK_LOG, WS_WORK_LOG_DETAILS, path_payload

ENTITY_ID = "lawn_mower.robo"


def _vector_map(map_id: int = 1, name: str = "Front") -> MowerVectorMap:
    zone = MowerZone(zone_id=4, path=[(0, 0), (1000, 0), (1000, 1000)], name="Lawn")
    return MowerVectorMap(zones=[zone], map_id=map_id, name=name)


def _device() -> SimpleNamespace:
    return SimpleNamespace(
        connected=True,
        online=True,
        vector_map=_vector_map(),
        other_vector_maps=[_vector_map(map_id=2, name="Back")],
        zones=[{"id": 4, "name": "Lawn"}],
        mowing_preference_mode=MowingPreferenceMode.MAP_WIDE,
        mowing_direction={"mode": 0, "angle": 90},
        mowing_settings={0: {"cutting_height": 4.5, "efficiency": "standard"}},
        robot_state={"main_state": 0, "sub_state": 255, "location": "idle", "docking": "in_station", "leaving_station": False, "work_mode": None, "scheduled": None, "charging": True},
        active_codes=frozenset({56}),
        current_problem=None,
        deleted_maps=[3],
        link_module_installed=True,
        link_module_plan_valid=True,
        cutting_height=4.5,
        zone_mowing_directions={},
        zone_cutting_heights={},
        dock_angle=358.0,
        docked=True,
        obstacles=[{"id": 1, "type": 0, "x": 100, "y": 100, "polygon": [0, 0, 200, 0, 200, 200]}],
        ai_obstacles=[{"id": 3, "type": 99, "x": 500, "y": 600}],
        stop_points=[{"zone_id": 4, "progress": 30.21, "date": "2026.10.12"}],
        current_map_id=1,
        available_maps=[
            {"id": 1, "index": 0, "name": "Front", "area": 120.0},
            {"id": 2, "index": 1, "name": "", "area": 80.0, "has_backup": True},
        ],
        trail_revision=0,
        mowing_path_history=[],
        mower_coordinates=(100, 200),
        mower_heading=90.0,
        dock_position=(-500, 0),
        current_segment=4,
        mowing_session_active=False,
        status="Charging",
        battery_percent=80,
        charging_status="charging",
        mowing_progress_percent=None,
        current_area_sqm=None,
        total_area_sqm=None,
        device_code_description=None,
        device_code_is_error=False,
    )


@pytest.fixture
async def coordinator(hass: HomeAssistant) -> DreameMowerCoordinator:
    """A loaded mower entry whose device is a plain stand-in, with the card set up."""
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Robo",
        data={
            CONF_NAME: "Robo",
            CONF_MAC: "11:22:33:44:55:66",
            CONF_MODEL: "dreame.mower.test",
            CONF_SERIAL: "SN1",
            CONF_DID: "did1",
            CONF_USERNAME: "user",
            CONF_PASSWORD: "password",
            CONF_ACCOUNT_TYPE: "dreame",
            CONF_COUNTRY: "eu",
        },
        options={CONF_MAP_ROTATION: 90},
        entry_id="feed_entry",
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = DreameMowerCoordinator(hass, entry=entry)
    coordinator.device = _device()  # type: ignore[assignment]
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_COORDINATOR: coordinator}
    er.async_get(hass).async_get_or_create(
        "lawn_mower", DOMAIN, "robo_lawn_mower", config_entry=entry, suggested_object_id="robo"
    )
    await async_setup_frontend(hass)
    return coordinator


async def _subscribe(hass: HomeAssistant, hass_ws_client: WebSocketGenerator, entity_id: str = ENTITY_ID) -> Any:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": WS_SUBSCRIBE_MAP, "entity_id": entity_id})
    result = await client.receive_json()
    assert result["success"], result
    return client


async def _events(client: Any, count: int) -> list[dict[str, Any]]:
    events = []
    for _ in range(count):
        message = await asyncio.wait_for(client.receive_json(), 5)
        assert message["type"] == "event", message
        events.append(message["event"])
    return events


async def _changed(hass: HomeAssistant, coordinator: DreameMowerCoordinator) -> None:
    coordinator.async_update_listeners()
    await hass.async_block_till_done()


# --- The served card ---


async def test_card_is_served(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_client: ClientSessionGenerator
) -> None:
    client = await hass_client()
    response = await client.get(CARD_URL)

    assert response.status == 200
    assert "javascript" in response.content_type
    body = await response.text()
    assert "customElements.define" in body and "dreame-mower-card" in body
    assert "max-age" in response.headers.get("Cache-Control", "")


async def test_card_resource_is_registered_and_updated(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_load()
    resources.loaded = True
    await resources.async_create_item({"res_type": "module", "url": f"{CARD_URL}?v=0.1"})
    await resources.async_create_item({"res_type": "module", "url": CARD_URL})
    await resources.async_create_item({"res_type": "module", "url": "/local/other.js"})

    await async_setup_frontend(hass)

    urls = sorted(item["url"] for item in resources.async_items())
    assert len(urls) == 3
    assert urls[0].startswith(f"{CARD_3D_URL}?v=")
    assert urls[1].startswith(f"{CARD_URL}?v=") and urls[1] != f"{CARD_URL}?v=0.1"
    assert urls[2] == "/local/other.js"


async def test_failing_resource_registration_still_serves_the_card(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, caplog: pytest.LogCaptureFixture
) -> None:
    assert await async_setup_component(hass, "http", {})
    with patch(
        "custom_components.dreame_mower.frontend._async_register_resource", side_effect=OSError("storage broken")
    ):
        await async_setup_frontend(hass)

    assert "Adding the map card to the dashboard resources failed" in caplog.text
    response = await (await hass_client()).get(CARD_URL)
    assert response.status == 200


async def test_card_resource_is_created_when_missing(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "lovelace", {})

    await async_setup_frontend(hass)

    resources = hass.data[LOVELACE_DATA].resources
    assert [item["url"].split("?")[0] for item in resources.async_items()] == [CARD_URL, CARD_3D_URL]


async def test_yaml_resources_are_left_alone(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "lovelace", {"lovelace": {"resource_mode": "yaml"}})

    await async_setup_frontend(hass)

    assert "add /dreame_mower/dreame-mower-card.js" in caplog.text


# --- The feed ---


async def test_subscription_sends_geometry_then_status(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    client = await _subscribe(hass, hass_ws_client)
    geometry, path, status = await _events(client, 3)

    # The trail always goes out first, even an empty one, so a card that
    # subscribes again drops a trail it still holds.
    assert path == {"type": "path", "keep": 0, "points": []}
    assert geometry == {
        "type": "geometry",
        "map_id": 1,
        "name": "Front",
        "zones": [{"id": 4, "name": "Lawn", "area": 0, "polygon": [0, 0, 1000, 0, 1000, 1000]}],
        "total_area": 0,
        "no_go": [],
        "ignore_obstacles": [],
        "paths": [],
        "contours": [],
        "spots": [],
        "maintenance_points": [],
        "bounds": [0, 0, 1000, 1000],
        "other_maps": [
            {
                "map_id": 2,
                "zones": [{"id": 4, "polygon": [0, 0, 1000, 0, 1000, 1000]}],
                "bounds": [0, 0, 1000, 1000],
            }
        ],
    }
    assert status["type"] == "status"
    assert status["rotation"] == 90
    assert status["model"] == "dreame.mower.test"
    assert status["maps"] == [
        {"id": 1, "name": "Front", "area": 120.0, "selected": True, "has_backup": False},
        {"id": 2, "name": "Map 2", "area": 80.0, "selected": False, "has_backup": True},
    ]
    assert status["mower"] == {"x": 100, "y": 200, "heading": 90.0}
    assert status["dock"] == {"x": -500, "y": 0, "angle": 358.0}
    assert status["docked"] is True
    assert status["obstacles"] == [
        {"kind": "obstacle", "id": 1, "type": 0, "x": 100, "y": 100, "polygon": [0, 0, 200, 0, 200, 200]},
        {"kind": "ai", "id": 3, "type": 99, "x": 500, "y": 600},
    ]
    # A mowing direction of 90° lays the stripes across it, at 90° too.
    assert status["zones"] == [{"id": 4, "stripe_angle": 90.0, "height": 4.5}]
    assert status["stop_points"] == [{"zone_id": 4, "progress": 30.21, "date": "2026.10.12"}]
    # The settings of each record, keyed by area id as JSON keys are strings.
    assert status["settings"] == {
        "mode": "map_wide",
        "height_max": 7.0,
        "areas": {"0": {"cutting_height": 4.5, "efficiency": "standard"}},
    }
    # Without a session there is no zone being mowed and no progress.
    assert status["current_zone"] is None
    assert status["state"]["task_mode"] is None
    assert status["state"]["session_minutes"] is None
    assert status["state"]["battery"] == 80
    assert status["state"]["progress"] is None
    assert status["state"]["available"] is True
    # What the mower does, said the way its app says it.
    assert status["state"]["text"] == "Rain protection is activated"
    assert status["state"]["docking"] == "in_station"
    assert status["state"]["codes"] == [56]
    assert status["state"]["error"] is None
    assert status["deleted_maps"] == [3]
    assert "stop_point_start" in status
    assert status["link_module"] == {"plan_valid": True}
    assert status["consumables"] is None  # not read yet
    # The settings record has not been read yet either.
    assert (status["light"], status["human_presence"], status["robot_voice"]) == (None, None, None)
    assert status["state"]["location"] == "idle"
    assert status["state"]["leaving_station"] is False


async def test_session_trail_arrives_as_changes(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    device = coordinator.device
    device.mowing_session_active = True
    device.mowing_progress_percent = 12.5
    device.trail_revision = 1
    device.mowing_path_history = [[0, 0], [10, 0]]
    client = await _subscribe(hass, hass_ws_client)
    _geometry, path, status = await _events(client, 3)

    assert path == {"type": "path", "keep": 0, "points": [[0, 0], [10, 0]]}
    assert status["current_zone"] == 4
    assert status["state"]["progress"] == 12.5
    # The heartbeat says the mower is idle, so the kind of task is not known yet.
    assert status["state"]["task_mode"] is None
    assert status["state"]["session_minutes"] == 0

    # The trail grows: only the new points go out.
    device.trail_revision = 2
    device.mowing_path_history = [[0, 0], [10, 0], [SEGMENT_BREAK, SEGMENT_BREAK], [20, 0]]
    await _changed(hass, coordinator)
    (path,) = await _events(client, 1)
    assert path == {"type": "path", "keep": 2, "points": [None, [20, 0]]}

    # The newest point is filled in: the card replaces it.
    device.trail_revision = 3
    device.mowing_path_history = [[0, 0], [10, 0], [SEGMENT_BREAK, SEGMENT_BREAK], [25, 0]]
    await _changed(hass, coordinator)
    (path,) = await _events(client, 1)
    assert path == {"type": "path", "keep": 3, "points": [[25, 0]]}


async def test_session_says_its_kind_and_how_long_it_runs(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator, freezer
) -> None:
    device = coordinator.device
    device.mowing_session_active = True
    device.robot_state = {**device.robot_state, "main_state": 4, "sub_state": 35, "work_mode": 2, "scheduled": False}
    client = await _subscribe(hass, hass_ws_client)
    _geometry, _path, status = await _events(client, 3)
    assert status["state"]["task_mode"] == "zone"
    assert status["state"]["session_minutes"] == 0

    freezer.tick(600)
    await _changed(hass, coordinator)
    (status,) = await _events(client, 1)
    assert status["state"]["task_mode"] == "zone"
    assert status["state"]["session_minutes"] == 10


async def test_changes_send_only_what_changed(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    client = await _subscribe(hass, hass_ws_client)
    await _events(client, 3)

    coordinator.device.mower_coordinates = (300, 200)
    await _changed(hass, coordinator)
    (status,) = await _events(client, 1)
    assert status["type"] == "status"
    assert status["mower"]["x"] == 300

    # Nothing changed: nothing is sent, so the next event is the map switch.
    await _changed(hass, coordinator)
    coordinator.device.vector_map = _vector_map(map_id=2, name="Back")
    coordinator.device.current_map_id = 2
    await _changed(hass, coordinator)
    geometry, status = await _events(client, 2)
    assert geometry["type"] == "geometry" and geometry["map_id"] == 2
    assert [entry["selected"] for entry in status["maps"]] == [False, True]


async def test_feed_without_a_map(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    coordinator.device.vector_map = None
    client = await _subscribe(hass, hass_ws_client)
    geometry, _path, status = await _events(client, 3)

    assert geometry["type"] == "geometry" and geometry["map_id"] is None
    assert status["type"] == "status"


async def test_unknown_entity_is_an_error(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": WS_SUBSCRIBE_MAP, "entity_id": "lawn_mower.other"})
    result = await client.receive_json()

    assert not result["success"]
    assert result["error"]["code"] == "not_found"


async def test_unsubscribing_stops_the_feed(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    client = await _subscribe(hass, hass_ws_client)
    await _events(client, 3)
    assert coordinator.shutdown_callbacks

    await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": 1})
    result = await client.receive_json()
    assert result["success"], result

    assert coordinator.shutdown_callbacks == []
    assert not coordinator._listeners


async def test_unloading_the_entry_closes_the_feed(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    client = await _subscribe(hass, hass_ws_client)
    await _events(client, 3)

    coordinator.async_shutdown_map_feeds()

    (closed,) = await _events(client, 1)
    assert closed == {"type": "closed"}
    assert not coordinator._listeners


async def test_a_failing_update_keeps_the_feed_alive(
    hass: HomeAssistant,
    coordinator: DreameMowerCoordinator,
    hass_ws_client: WebSocketGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = await _subscribe(hass, hass_ws_client)
    await _events(client, 3)

    coordinator.device.available_maps = None  # not iterable: the status cannot be built
    await _changed(hass, coordinator)
    assert "Sending the map of Robo failed" in caplog.text

    coordinator.device.available_maps = []
    await _changed(hass, coordinator)
    (status,) = await _events(client, 1)
    assert status["maps"] == []


# --- Trail changes ---


def test_path_payload_unchanged_is_none():
    assert path_payload([[1, 2]], [[1, 2]]) is None
    assert path_payload([], []) is None


def test_path_payload_keeps_the_common_start():
    assert path_payload([[1, 2], [3, 4]], [[1, 2], [5, 6], [7, 8]]) == {
        "type": "path",
        "keep": 1,
        "points": [[5, 6], [7, 8]],
    }


def test_path_payload_of_a_new_trail_keeps_nothing():
    assert path_payload([[1, 2], [3, 4]], [[9, 9]]) == {"type": "path", "keep": 0, "points": [[9, 9]]}


def test_path_payload_of_a_cleared_trail():
    assert path_payload([[1, 2]], []) == {"type": "path", "keep": 0, "points": []}


# --- What each zone is mowed with ---


def test_zone_settings_follow_the_map_wide_record():
    coordinator = SimpleNamespace(
        zones=[{"id": 1}, {"id": 2}],
        mowing_preference_mode=MowingPreferenceMode.MAP_WIDE,
        mowing_direction={"mode": 0, "angle": 0},
        cutting_height=3.0,
        zone_mowing_directions={1: {"mode": 0, "angle": 45}},
        zone_cutting_heights={1: 6.0},
    )

    assert zone_settings(coordinator) == [
        {"id": 1, "stripe_angle": 0.0, "height": 3.0},
        {"id": 2, "stripe_angle": 0.0, "height": 3.0},
    ]


def test_zone_settings_follow_each_zone_in_per_zone_mode():
    coordinator = SimpleNamespace(
        zones=[{"id": 1}, {"id": 2}],
        mowing_preference_mode=MowingPreferenceMode.PER_ZONE,
        mowing_direction={"mode": 0, "angle": 0},
        cutting_height=3.0,
        zone_mowing_directions={1: {"mode": 0, "angle": 45}},
        zone_cutting_heights={1: 6.0},
    )

    assert zone_settings(coordinator) == [
        {"id": 1, "stripe_angle": 135.0, "height": 6.0},
        {"id": 2, "stripe_angle": None, "height": None},
    ]


def test_stripe_angle_counts_the_other_way_round():
    assert stripe_angle(None) is None
    assert stripe_angle(180) == 0.0
    assert stripe_angle(0) == 0.0
    assert stripe_angle(90) == 90.0
    assert stripe_angle(30) == 150.0



# --- The work log ---


async def _ask(hass: HomeAssistant, hass_ws_client: WebSocketGenerator, message: dict[str, Any]) -> dict[str, Any]:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(message)
    return await client.receive_json()


async def test_work_log_lists_the_tasks_since_the_totals_start(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    totals = {"area": 17469, "time": 12850, "count": 356, "start": 1704038400}
    entries = [{"start": 1791540000, "mode": "all_area", "result": "complete", "file": "ali_dreame/a.json"}]
    asked: list[int] = []
    coordinator.device.read_work_totals = lambda: totals
    coordinator.device.read_work_log = lambda since: asked.append(since) or entries

    result = await _ask(hass, hass_ws_client, {"type": WS_WORK_LOG, "entity_id": ENTITY_ID})

    assert result["success"], result
    assert result["result"] == {"totals": totals, "entries": entries}
    assert asked == [1704038400]


async def test_work_log_reports_a_cloud_that_does_not_answer(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    coordinator.device.read_work_totals = lambda: None
    coordinator.device.read_work_log = lambda since: None

    result = await _ask(hass, hass_ws_client, {"type": WS_WORK_LOG, "entity_id": ENTITY_ID})

    assert not result["success"]


async def test_work_log_details_refuse_a_task_the_log_did_not_list(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    def details(file: str) -> dict[str, Any]:
        if file != "ali_dreame/a.json":
            raise ValueError("This task is not in the work log")
        return {"result": "complete"}

    coordinator.device.read_work_log_details = details

    listed = await _ask(hass, hass_ws_client, {"type": WS_WORK_LOG_DETAILS, "entity_id": ENTITY_ID, "file": "ali_dreame/a.json"})
    other = await _ask(hass, hass_ws_client, {"type": WS_WORK_LOG_DETAILS, "entity_id": ENTITY_ID, "file": "../secrets.yaml"})

    assert listed["success"] and listed["result"] == {"result": "complete"}
    assert not other["success"]
    assert other["error"]["code"] == "not_found"


async def test_work_log_goes_back_half_a_year_without_totals(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    asked: list[int] = []
    coordinator.device.read_work_totals = lambda: None
    coordinator.device.read_work_log = lambda since: asked.append(since) or []

    with patch("custom_components.dreame_mower.map_api.time.time", return_value=1_800_000_000):
        result = await _ask(hass, hass_ws_client, {"type": WS_WORK_LOG, "entity_id": ENTITY_ID})

    assert result["success"]
    assert result["result"] == {"totals": None, "entries": []}
    assert asked == [1_800_000_000 - 180 * 24 * 3600]



async def test_obstacle_photo_answers_with_the_photo_or_why_not(
    hass: HomeAssistant, coordinator: DreameMowerCoordinator, hass_ws_client: WebSocketGenerator
) -> None:
    def photo(image: str) -> dict[str, Any] | None:
        if image == "unknown":
            raise ValueError("The mower reports no obstacle with this photo")
        return None if image == "slow" else {"image": "abc", "boxes": [], "width": 640, "height": 360}

    coordinator.device.read_obstacle_photo = photo

    sent = await _ask(hass, hass_ws_client, {"type": WS_OBSTACLE_PHOTO, "entity_id": ENTITY_ID, "image": "p"})
    slow = await _ask(hass, hass_ws_client, {"type": WS_OBSTACLE_PHOTO, "entity_id": ENTITY_ID, "image": "slow"})
    unknown = await _ask(hass, hass_ws_client, {"type": WS_OBSTACLE_PHOTO, "entity_id": ENTITY_ID, "image": "unknown"})

    assert sent["success"] and sent["result"]["image"] == "abc"
    assert not slow["success"] and "weak" in slow["error"]["message"]
    assert not unknown["success"] and unknown["error"]["code"] == "not_found"
