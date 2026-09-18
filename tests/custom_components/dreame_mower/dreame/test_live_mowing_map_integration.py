"""Integration test: replay a captured mowing session through the full pipeline.

Feeds raw MQTT messages from a real mowing session (2026-03-22 16:01–16:50)
through DreameMowerDevice → CameraEntity and captures SVG snapshots at two
stages of the rendering pipeline:

  Stage 1 – **Device layer**: coordinates collected from device property
            callbacks, rendered directly via ``generate_svg_map_image`` with
            the historical map as base.  This validates parsing + SVG rendering
            in isolation.

  Stage 2 – **Camera layer**: the camera entity's ``_generate_live_image()``
            method, which mirrors the real HA camera path (map-source
            selection, coordinate accumulation, SVG generation).

Fixture data was extracted from dev/logs/20260322_132859 by the realtime monitor.
"""

import json
import re
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from custom_components.dreame_mower.camera import DreameMowerCameraEntity
from custom_components.dreame_mower.dreame.device import DreameMowerDevice
from custom_components.dreame_mower.dreame.map_data_parser import vector_map_to_map_data
from custom_components.dreame_mower.dreame.property.pose_coverage import (
    POSE_COVERAGE_COORDINATES_PROPERTY_NAME,
)
from custom_components.dreame_mower.dreame.svg_map_generator import generate_svg_map_image

TEST_DATA_DIR = Path(__file__).parent / "test_data"
FIXTURE_JSON = TEST_DATA_DIR / "live_mowing_session_20260322.json"

# Golden / actual file names per stage
DEVICE_GOLDEN_SVG = TEST_DATA_DIR / "live_mowing_session_20260322_device_golden.svg"
DEVICE_ACTUAL_SVG = TEST_DATA_DIR / "live_mowing_session_20260322_device_actual.svg"
CAMERA_GOLDEN_SVG = TEST_DATA_DIR / "live_mowing_session_20260322_camera_golden.svg"
CAMERA_ACTUAL_SVG = TEST_DATA_DIR / "live_mowing_session_20260322_camera_actual.svg"

# Patterns that change on every run and must be normalised before comparison
_TIMESTAMP_RE = re.compile(r"Updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_DISTANCE_RE = re.compile(r"Distance: [\d.]+m")


class _MockCloudDevice:
    """Minimal mock for DreameMowerCloudDevice used by the device under test."""

    connected = False
    device_reachable = False
    device_id = "test_integration"

    def connect(self, **kwargs):
        return True

    def disconnect(self):
        pass

    def get_batch_device_datas(self, keys):
        return None


@pytest.fixture()
def session_fixture():
    """Load the captured mowing session fixture."""
    with open(FIXTURE_JSON, "r") as f:
        return json.load(f)


def _make_device() -> DreameMowerDevice:
    """Create a DreameMowerDevice wired to a mock cloud device."""
    with patch(
        "custom_components.dreame_mower.dreame.device.DreameMowerCloudDevice"
    ) as cls:
        cls.return_value = _MockCloudDevice()
        dev = DreameMowerDevice(
            device_id="integration_test",
            username="u",
            password="p",
            account_type="dreame",
            country="DE",
            hass_config_dir="/tmp/test",
        )
        dev._cloud_device = cls.return_value
        return dev


def _normalise_svg(svg_text: str) -> str:
    """Strip run-dependent fields so golden comparison is stable."""
    svg_text = _TIMESTAMP_RE.sub("Updated: TIMESTAMP", svg_text)
    svg_text = _DISTANCE_RE.sub("Distance: Xm", svg_text)
    return svg_text


def _assert_svg_matches_golden(
    svg_bytes: bytes,
    actual_path: Path,
    golden_path: Path,
    stage_label: str,
) -> None:
    """Write *actual*, bootstrap or compare against *golden*."""
    actual_path.write_bytes(svg_bytes)

    if not golden_path.exists():
        golden_path.write_bytes(svg_bytes)
        return  # first run – nothing to compare against yet

    golden_text = _normalise_svg(golden_path.read_text(encoding="utf-8"))
    actual_text = _normalise_svg(svg_bytes.decode("utf-8"))

    assert actual_text == golden_text, (
        f"[{stage_label}] Rendered SVG differs from golden reference.\n"
        f"Actual saved to: {actual_path}\n"
        f"If the change is intentional, update the golden file:\n"
        f"  cp {actual_path} {golden_path}"
    )


def _replay_mqtt(device: DreameMowerDevice, messages: list[dict]) -> None:
    """Feed raw MQTT messages through the device's message handler."""
    for msg in messages:
        device._handle_message({
            "id": 1,
            "method": "properties_changed",
            "params": [{
                "siid": msg["siid"],
                "piid": msg["piid"],
                "value": msg["value"],
            }],
        })


class TestLiveMowingMapIntegration:
    """Replay captured MQTT through device + camera, compare golden SVGs."""

    def test_replay_mowing_session(self, session_fixture):
        """Feed MQTT messages through the full pipeline and snapshot each stage.

        A single MQTT replay drives both snapshots:

        1. **Device-layer SVG** – rendered directly via
           ``generate_svg_map_image`` with the coordinates collected by a
           plain property callback and the historical map as base.

        2. **Camera-layer SVG** – produced by the camera entity's
           ``_generate_live_image()`` method, which mirrors the real HA
           camera path (vector-map source selection, coordinate
           accumulation, SVG generation).
        """

        # ── Setup ──────────────────────────────────────────────────────
        cam_device = _make_device()

        cam_coordinator = Mock()
        cam_coordinator.device = cam_device
        cam_coordinator.device_connected = True

        config_entry = Mock()
        config_entry.entry_id = "test_entry"
        config_entry.options = {}
        config_entry.add_update_listener = Mock(return_value=lambda: None)

        with patch.object(
            DreameMowerCameraEntity,
            "_refresh_historical_files_cache",
        ):
            camera = DreameMowerCameraEntity(cam_coordinator, config_entry)

        camera._pose_coverage_timer = None
        camera.hass = Mock()
        # The real hass schedules these coroutines on the event loop; here we
        # just close them so they don't leak as "never awaited" warnings.
        camera.hass.create_task = lambda coro: coro.close()
        # Prevent _handle_property_change from spawning real Timer threads
        # during MQTT replay — they would outlive the test and hang the process.
        camera._start_pose_coverage_timer = lambda: None
        # The real entity registers this when Home Assistant adds it.
        cam_device.register_property_callback(camera._handle_property_change)

        # Mock the batch API to return the captured response so
        # fetch_vector_map() parses it into a real MowerVectorMap.
        cam_device._cloud_device.get_batch_device_datas = (
            lambda keys: session_fixture["batch_api_response"]
        )
        cam_device.fetch_vector_map()

        # Also collect coordinates for the device-layer snapshot,
        # converting to [x, y] lists the same way camera.py does.
        live_coordinates: list[list[int]] = []

        def _collect_coords(name, value):
            if name == POSE_COVERAGE_COORDINATES_PROPERTY_NAME:
                x = value.get("x")
                y = value.get("y")
                if x is not None and y is not None:
                    live_coordinates.append([int(x), int(y)])

        cam_device.register_property_callback(_collect_coords)

        # ── Replay ─────────────────────────────────────────────────────
        _replay_mqtt(cam_device, session_fixture["mqtt_messages"])

        assert live_coordinates, "No live coordinates collected from MQTT replay"
        assert camera._live_coordinates, (
            "Camera collected no live coordinates from MQTT replay"
        )

        # ── Snapshot 1: device layer ───────────────────────────────────
        # Use vector map data (same coordinate system as live pose data)
        vector_map = cam_device.vector_map
        device_map_data = vector_map_to_map_data(vector_map) if vector_map and vector_map.boundary else {}
        device_svg = generate_svg_map_image(
            device_map_data,
            None,
            cam_coordinator,
            rotation=0,
            live_coordinates=live_coordinates,
        )
        _assert_svg_matches_golden(
            device_svg, DEVICE_ACTUAL_SVG, DEVICE_GOLDEN_SVG, "device-layer",
        )

        # ── Snapshot 2: camera layer ───────────────────────────────────
        camera_svg = camera._generate_live_image()

        _assert_svg_matches_golden(
            camera_svg, CAMERA_ACTUAL_SVG, CAMERA_GOLDEN_SVG, "camera-layer",
        )
