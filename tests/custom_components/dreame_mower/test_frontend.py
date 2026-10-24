"""Tests for serving the map card and adding it to the dashboard resources."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.lovelace.const import MODE_STORAGE, MODE_YAML
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest

from custom_components.dreame_mower import frontend
from custom_components.dreame_mower.frontend import (
    CARD_PATH,
    CARD_URL,
    SECTION_3D_PATH,
    SECTION_3D_URL,
    THREE_PATH,
    THREE_URL,
    async_setup_frontend,
)

URL = f"{CARD_URL}?v=1.0.0.abcd1234"


def _resources(items: list[dict[str, Any]], loaded: bool = True) -> MagicMock:
    """Dashboard resources managed in storage, holding `items`."""
    resources = MagicMock(spec=ResourceStorageCollection)
    resources.loaded = loaded
    resources.async_items.return_value = items
    resources.async_load = AsyncMock()
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    resources.async_delete_item = AsyncMock()
    return resources


def _lovelace(hass: HomeAssistant, resources: Any, mode: str = MODE_STORAGE) -> None:
    hass.data["lovelace"] = SimpleNamespace(resources=resources, resource_mode=mode)


async def test_the_card_is_served_fed_and_added_once(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    resources = _resources([])
    _lovelace(hass, resources)
    with (
        patch.object(hass.http, "async_register_static_paths", AsyncMock()) as serve,
        patch.object(hass.http, "register_view") as view,
        patch.object(frontend, "async_register_command") as register,
    ):
        await async_setup_frontend(hass)
        await async_setup_frontend(hass)

    serve.assert_awaited_once()
    assert [(config.url_path, config.path, config.cache_headers) for config in serve.await_args.args[0]] == [
        (CARD_URL, str(CARD_PATH), True),
        (SECTION_3D_URL, str(SECTION_3D_PATH), True),
        (THREE_URL, str(THREE_PATH), True),
    ]
    assert CARD_PATH.is_file() and SECTION_3D_PATH.is_file() and THREE_PATH.is_file()
    assert [call.args[1].__name__ for call in register.call_args_list] == [
        "ws_subscribe_map",
        "ws_work_log",
        "ws_work_log_subscribe",
        "ws_work_log_details",
        "ws_obstacle_photo",
        "ws_point_clouds",
    ]
    view.assert_called_once()
    # The URL carries the version and a checksum of the file.
    resources.async_create_item.assert_awaited_once()
    url = resources.async_create_item.await_args.args[0]["url"]
    assert url.startswith(f"{CARD_URL}?v=")
    assert url.endswith(f".{frontend._card_checksum()}")
    assert resources.async_create_item.await_args.args[0]["res_type"] == "module"


async def test_the_3d_view_is_loaded_on_every_page(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    hass.config.components.add("frontend")
    with (
        patch.object(hass.http, "async_register_static_paths", AsyncMock()),
        patch.object(frontend, "async_register_command"),
        patch.object(frontend, "add_extra_js_url") as extra,
        patch.object(frontend, "_async_register_resource", AsyncMock()),
    ):
        await async_setup_frontend(hass)
    extra.assert_called_once_with(hass, f"{SECTION_3D_URL}?v={frontend._card_checksum(SECTION_3D_PATH)}")


async def test_a_failing_resource_leaves_the_card_served(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    assert await async_setup_component(hass, "http", {})
    with (
        patch.object(hass.http, "async_register_static_paths", AsyncMock()),
        patch.object(frontend, "async_register_command"),
        patch.object(frontend, "_async_register_resource", AsyncMock(side_effect=RuntimeError("broken"))),
    ):
        await async_setup_frontend(hass)
    assert hass.data[frontend._DATA_READY]
    assert "add /dreame_mower/dreame-mower-card.js by hand" in caplog.text


async def test_the_resource_is_added_when_missing(hass: HomeAssistant) -> None:
    resources = _resources([{"id": "other", "url": "/local/other.js"}], loaded=False)
    _lovelace(hass, resources)
    await frontend._async_register_resource(hass, URL)
    resources.async_load.assert_awaited_once()
    assert resources.loaded is True
    resources.async_create_item.assert_awaited_once_with({"res_type": "module", "url": URL})


async def test_an_older_resource_is_updated_and_extra_ones_go(hass: HomeAssistant) -> None:
    resources = _resources(
        [
            {"id": "a", "url": f"{CARD_URL}?v=0.9.0.00000000"},
            {"id": "b", "url": CARD_URL},
        ]
    )
    _lovelace(hass, resources)
    await frontend._async_register_resource(hass, URL)
    resources.async_create_item.assert_not_awaited()
    resources.async_update_item.assert_awaited_once_with("a", {"url": URL})
    resources.async_delete_item.assert_awaited_once_with("b")


async def test_a_current_resource_is_left_alone(hass: HomeAssistant) -> None:
    resources = _resources([{"id": "a", "url": URL}])
    _lovelace(hass, resources)
    await frontend._async_register_resource(hass, URL)
    resources.async_create_item.assert_not_awaited()
    resources.async_update_item.assert_not_awaited()
    resources.async_delete_item.assert_not_awaited()


async def test_resources_in_yaml_are_left_to_the_user(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    resources = _resources([])
    _lovelace(hass, resources, MODE_YAML)
    with caplog.at_level("INFO"):
        await frontend._async_register_resource(hass, URL)
    resources.async_create_item.assert_not_awaited()
    assert "add /dreame_mower/dreame-mower-card.js?v=" in caplog.text


async def test_without_dashboards_nothing_is_added(hass: HomeAssistant) -> None:
    hass.data.pop("lovelace", None)
    await frontend._async_register_resource(hass, URL)
