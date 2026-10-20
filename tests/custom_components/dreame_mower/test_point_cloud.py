"""Tests for the 3D maps (point clouds) and the endpoint that serves them."""

import struct
from unittest.mock import Mock, patch

import pytest

from homeassistant.components import websocket_api
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dreame_mower.const import DATA_COORDINATOR, DATA_POINT_CLOUD, DOMAIN
from custom_components.dreame_mower.dreame.point_cloud import (
    PointCloudError,
    build_point_cloud_list_payload,
    point_cloud_names,
    validate_point_cloud,
)
from custom_components.dreame_mower.point_cloud import (
    DreameMowerPointCloudView,
    PointCloudStore,
    point_cloud_url,
    ws_point_clouds,
)


def _pcd(points: list[tuple[float, float, float, int]], declared: int | None = None) -> bytes:
    """Build a binary PCD 0.7 file like the ones the mower stores."""
    count = len(points) if declared is None else declared
    header = (
        "# .PCD v0.7 - Point Cloud Data file format\n"
        "VERSION 0.7\nFIELDS x y z rgb\nSIZE 4 4 4 4\nTYPE F F F U\nCOUNT 1 1 1 1\n"
        f"WIDTH {count}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {count}\nDATA binary\n"
    ).encode()
    return header + b"".join(struct.pack("<fffI", *p) for p in points)


CLOUD = _pcd([(1.0, 2.0, 0.1, 0x00FF00), (-3.5, 4.0, 2.5, 0x0000FF)])
OBJ_RESPONSE = {
    "aiid": 50,
    "code": 0,
    "out": [{"d": {"name": ["ali_dreame/a/map0.bin", "ali_dreame/a/map1.bin"]}, "m": "r", "q": 79, "r": 0}],
    "siid": 2,
}


class TestPointCloudNames:
    def test_payload_asks_for_the_3d_maps(self):
        assert build_point_cloud_list_payload() == {"m": "g", "t": "OBJ", "d": {"type": "3dmap"}}

    def test_names_by_map_index(self):
        assert point_cloud_names(OBJ_RESPONSE) == ["ali_dreame/a/map0.bin", "ali_dreame/a/map1.bin"]

    def test_an_empty_slot_has_no_cloud(self):
        response = {"out": [{"d": {"name": ["", "ali_dreame/a/map1.bin"]}}]}
        assert point_cloud_names(response) == [None, "ali_dreame/a/map1.bin"]

    @pytest.mark.parametrize("response", [None, {}, {"out": []}, {"out": [{"d": {}}]}, {"out": [{"d": {"name": "x"}}]}])
    def test_unexpected_shapes_list_nothing(self, response):
        assert point_cloud_names(response) == []


class TestValidatePointCloud:
    def test_counts_the_points_of_a_binary_cloud(self):
        assert validate_point_cloud(CLOUD) == 2

    def test_accepts_an_ascii_cloud(self):
        data = b"VERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nPOINTS 1\nDATA ascii\n1 2 3\n"
        assert validate_point_cloud(data) == 1

    def test_rejects_a_truncated_cloud(self):
        with pytest.raises(PointCloudError, match="truncated"):
            validate_point_cloud(_pcd([(1.0, 2.0, 3.0, 0)], declared=5))

    def test_rejects_compressed_data(self):
        with pytest.raises(PointCloudError, match="unsupported"):
            validate_point_cloud(CLOUD.replace(b"DATA binary", b"DATA binary_compressed"))

    def test_rejects_a_file_without_coordinates(self):
        with pytest.raises(PointCloudError, match="x y z"):
            validate_point_cloud(CLOUD.replace(b"FIELDS x y z rgb", b"FIELDS a b c rgb"))

    def test_rejects_something_else(self):
        with pytest.raises(PointCloudError, match="header"):
            validate_point_cloud(b"<html>Access denied</html>")


def _device(names: list[str | None]) -> Mock:
    device = Mock()
    device.read_point_cloud_names = Mock(return_value=names)
    device.download_point_cloud = Mock(return_value=CLOUD)
    return device


class TestPointCloudStore:
    def test_downloads_a_cloud_once(self, tmp_path):
        device = _device(["ali_dreame/a/map0.bin"])
        store = PointCloudStore(device, str(tmp_path))
        assert store.get(0) == (CLOUD, "ali_dreame/a/map0.bin")
        assert store.get(0) == (CLOUD, "ali_dreame/a/map0.bin")
        device.download_point_cloud.assert_called_once_with("ali_dreame/a/map0.bin")
        device.read_point_cloud_names.assert_called_once()

    def test_a_machine_that_has_just_booted_reads_the_list(self, tmp_path):
        device = _device(["ali_dreame/a/map0.bin"])
        with patch("custom_components.dreame_mower.point_cloud.time.monotonic", return_value=5.0):
            assert PointCloudStore(device, str(tmp_path)).get(0) == (CLOUD, "ali_dreame/a/map0.bin")

    def test_a_restart_reuses_the_file_on_disk(self, tmp_path):
        PointCloudStore(_device(["ali_dreame/a/map0.bin"]), str(tmp_path)).get(0)
        device = _device(["ali_dreame/a/map0.bin"])
        assert PointCloudStore(device, str(tmp_path)).get(0) == (CLOUD, "ali_dreame/a/map0.bin")
        device.download_point_cloud.assert_not_called()

    def test_a_new_cloud_name_is_downloaded_again(self, tmp_path):
        device = _device(["ali_dreame/a/map0.bin"])
        store = PointCloudStore(device, str(tmp_path))
        store.get(0)
        device.read_point_cloud_names.return_value = ["ali_dreame/b/map0.bin"]
        store._names_read_at = None  # the list is out of date
        assert store.get(0) == (CLOUD, "ali_dreame/b/map0.bin")
        assert device.download_point_cloud.call_count == 2

    @pytest.mark.parametrize("names,index", [([None, "ali_dreame/a/map1.bin"], 0), (["ali_dreame/a/map0.bin"], 3)])
    def test_a_map_without_cloud_gives_none(self, tmp_path, names, index):
        device = _device(names)
        assert PointCloudStore(device, str(tmp_path)).get(index) is None
        device.download_point_cloud.assert_not_called()


class TestPointCloudView:
    @pytest.fixture
    async def client(self, hass, hass_client):
        assert await async_setup_component(hass, "http", {})
        hass.http.register_view(DreameMowerPointCloudView())
        store = Mock()
        store.get = Mock(side_effect=lambda index: (CLOUD, "ali_dreame/a/map0.bin") if index == 0 else None)
        hass.data.setdefault(DOMAIN, {})["entry1"] = {DATA_POINT_CLOUD: store}
        return await hass_client()

    async def test_serves_the_cloud_with_an_etag(self, client):
        response = await client.get(point_cloud_url("entry1", 0))
        assert response.status == 200
        assert await response.read() == CLOUD
        etag = response.headers["ETag"]
        again = await client.get(point_cloud_url("entry1", 0), headers={"If-None-Match": etag})
        assert again.status == 304

    async def test_a_map_without_cloud_is_not_found(self, client):
        assert (await client.get(point_cloud_url("entry1", 1))).status == 404
        assert (await client.get(point_cloud_url("other", 0))).status == 404

    async def test_a_failed_download_is_a_bad_gateway(self, hass, client):
        hass.data[DOMAIN]["entry1"][DATA_POINT_CLOUD].get.side_effect = PointCloudError("truncated file")
        assert (await client.get(point_cloud_url("entry1", 0))).status == 502

    async def test_requires_a_signed_in_user(self, hass, hass_client_no_auth):
        assert await async_setup_component(hass, "http", {})
        hass.http.register_view(DreameMowerPointCloudView())
        client = await hass_client_no_auth()
        assert (await client.get(point_cloud_url("entry1", 0))).status == 401


class TestPointCloudsCommand:
    """The card asks for the maps of its mower over the WebSocket API."""

    @pytest.fixture
    async def ws(self, hass, hass_ws_client):
        assert await async_setup_component(hass, "websocket_api", {})
        websocket_api.async_register_command(hass, ws_point_clouds)
        entry = MockConfigEntry(domain=DOMAIN, entry_id="entry1")
        entry.add_to_hass(hass)
        registry = er.async_get(hass)
        registry.async_get_or_create("lawn_mower", DOMAIN, "AA:BB_mower", config_entry=entry, suggested_object_id="shaun")
        registry.async_get_or_create("lawn_mower", "other", "x", suggested_object_id="other")
        coordinator = Mock()
        coordinator.device_mac = "AA:BB"
        coordinator.device.available_maps = [
            {"id": 1, "index": 0, "name": "Lawn", "area": 300},
            {"id": 2, "index": 1, "name": "Meadow", "area": 900},
        ]
        coordinator.device.current_map_id = 2
        hass.data.setdefault(DOMAIN, {})["entry1"] = {DATA_COORDINATOR: coordinator, DATA_POINT_CLOUD: Mock()}
        return await hass_ws_client(hass)

    async def test_lists_the_maps_and_the_active_one(self, ws):
        await ws.send_json({"id": 1, "type": "dreame_mower/point_clouds", "entity_id": "lawn_mower.shaun"})
        msg = await ws.receive_json()
        assert msg["success"]
        assert msg["result"] == {
            "maps": [
                {"index": 0, "name": "Lawn", "url": "/api/dreame_mower/entry1/point_cloud/0"},
                {"index": 1, "name": "Meadow", "url": "/api/dreame_mower/entry1/point_cloud/1"},
            ],
            "active_index": 1,
        }

    @pytest.mark.parametrize("entity_id", ["lawn_mower.other", "lawn_mower.missing"])
    async def test_other_entities_are_refused(self, ws, entity_id):
        await ws.send_json({"id": 1, "type": "dreame_mower/point_clouds", "entity_id": entity_id})
        msg = await ws.receive_json()
        assert not msg["success"]
        assert msg["error"]["code"] == "not_found"
