"""Serve the map card and register it with the dashboards.

The card is one JavaScript module shipped with the integration. It is
served from a fixed path, added to the dashboard resources (where those
are managed in storage) and fed through the map websocket command. All of
that happens once per Home Assistant instance, when the first entry is set
up.
"""

from __future__ import annotations

import logging
from pathlib import Path
import zlib

from homeassistant.components.http import StaticPathConfig  # type: ignore[attr-defined,unused-ignore]
from homeassistant.components.lovelace.const import MODE_STORAGE
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.components.websocket_api import async_register_command
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .map_api import ws_obstacle_photo, ws_subscribe_map, ws_work_log, ws_work_log_details

_LOGGER = logging.getLogger(__name__)

CARD_FILE = "dreame-mower-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILE}"
CARD_PATH = Path(__file__).parent / "frontend" / CARD_FILE
_DATA_READY = f"{DOMAIN}_frontend_ready"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve the card, register the dashboard resource and the map feed."""
    if hass.data.get(_DATA_READY):
        return
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=True)])
    async_register_command(hass, ws_subscribe_map)
    async_register_command(hass, ws_work_log)
    async_register_command(hass, ws_work_log_details)
    async_register_command(hass, ws_obstacle_photo)
    hass.data[_DATA_READY] = True
    # The card is served and fed either way; without the resource it only has
    # to be added to the dashboards by hand.
    try:
        version = (await async_get_integration(hass, DOMAIN)).version
        checksum = await hass.async_add_executor_job(_card_checksum)
        await _async_register_resource(hass, f"{CARD_URL}?v={version}.{checksum}")
    except Exception:  # noqa: BLE001 - the mower works without the card
        _LOGGER.exception("Adding the map card to the dashboard resources failed; add %s by hand", CARD_URL)


def _card_checksum() -> str:
    return f"{zlib.crc32(CARD_PATH.read_bytes()):08x}"


async def _async_register_resource(hass: HomeAssistant, url: str) -> None:
    """Add the card to the dashboard resources, or replace an older version of it.

    Browsers cache the file for a long time, so the URL carries the version
    and a checksum of the file: any change to the card gets a new URL.
    """
    # The dashboards keep their state under their domain; older Home Assistant
    # releases keep it in a shape this does not know, and then the card has to
    # be added by hand like in YAML mode.
    data = hass.data.get("lovelace")
    if data is None:
        return
    resources = getattr(data, "resources", None)
    if getattr(data, "resource_mode", None) != MODE_STORAGE or not isinstance(resources, ResourceStorageCollection):
        _LOGGER.info("Dashboard resources are not managed in the UI; add %s as a module resource to use the map card", url)
        return
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    ours = [item for item in resources.async_items() if str(item.get("url", "")).split("?")[0] == CARD_URL]
    if not ours:
        await resources.async_create_item({"res_type": "module", "url": url})
        return
    if ours[0]["url"] != url:
        await resources.async_update_item(ours[0]["id"], {"url": url})
    # The module must load once; any further entry for it goes.
    for extra in ours[1:]:
        await resources.async_delete_item(extra["id"])
