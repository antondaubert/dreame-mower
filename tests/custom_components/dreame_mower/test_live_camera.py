"""Tests for the live camera entity."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.dreame_mower.dreame.cloud.cloud_video import (
    DreameMowerVideoError,
    DreameMowerVideoSession,
)
from custom_components.dreame_mower.dreame.video_runtime import (
    RUNTIME_SUBDIR,
    DreameMowerVideoRuntimeError,
    DreameMowerVideoRuntimeInfo,
    DreameMowerVideoRuntimeState,
)
from custom_components.dreame_mower.const import DATA_LIVE_CAMERA, DOMAIN
from custom_components.dreame_mower.live_camera import (
    DreameMowerLiveCameraEntity,
    create_live_camera,
)

SESSION = DreameMowerVideoSession("PID", "DEVNAME", "XP2Pabc", "app-id", "app-secret")
URL = "http://127.0.0.1:9/ipc.flv?action=live"


@pytest.fixture
def coordinator(tmp_path):
    coordinator = Mock()
    coordinator.hass = Mock()
    coordinator.hass.config.path.return_value = str(tmp_path)
    async def executor_job(func, *args):
        return func(*args)

    coordinator.hass.async_add_executor_job = AsyncMock(side_effect=executor_job)
    # Home Assistant hands back a real task; the tests drive the watcher
    # themselves, so the coroutine is closed rather than run twice.
    def background_task(coro, name):
        coro.close()
        return asyncio.get_running_loop().create_task(asyncio.sleep(0))

    coordinator.hass.async_create_background_task = background_task
    coordinator.device = Mock()
    coordinator.device.device_id = "did"
    coordinator.device.set_camera_stream = AsyncMock(return_value=True)
    coordinator.device.status_code = 1  # mowing
    coordinator.hass.data = {"dreame_mower": {"entry": {}}}
    return coordinator


@pytest.fixture
def entry():
    entry = Mock()
    entry.entry_id = "entry"
    return entry


def ready_info(tmp_path) -> DreameMowerVideoRuntimeInfo:
    return DreameMowerVideoRuntimeInfo(
        DreameMowerVideoRuntimeState.READY, tmp_path, sdk_version="v2.4.72"
    )


@pytest.fixture
def provision(monkeypatch):
    """Stand in for the cloud exchange, which has its own tests."""
    call = Mock(return_value=SESSION)
    monkeypatch.setattr(
        "custom_components.dreame_mower.live_camera.DreameMowerCloudVideo",
        lambda *_args, **_kwargs: Mock(provision=call),
    )
    return call


@pytest.fixture
def camera(coordinator, entry, tmp_path, monkeypatch, provision):
    monkeypatch.setattr(
        "custom_components.dreame_mower.entity.DreameMowerEntity.__init__",
        lambda self, coordinator, key: setattr(self, "coordinator", coordinator),
    )
    entity = DreameMowerLiveCameraEntity(coordinator, entry, ready_info(tmp_path))
    entity.hass = coordinator.hass
    entity.async_write_ha_state = Mock()
    entity._runtime = Mock()
    entity._runtime.running = True
    entity._runtime.async_start = AsyncMock(return_value=URL)
    entity._runtime.async_stop = AsyncMock()
    return entity


class TestCreation:
    """Whether the entity is offered at all."""

    def test_no_entity_without_the_helper(self, coordinator, entry, tmp_path):
        missing = DreameMowerVideoRuntimeInfo(
            DreameMowerVideoRuntimeState.NOT_INSTALLED, tmp_path
        )
        assert create_live_camera(coordinator, entry, missing) is None

    def test_an_entity_once_the_helper_is_installed(
        self, coordinator, entry, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "custom_components.dreame_mower.entity.DreameMowerEntity.__init__",
            lambda self, coordinator, key: setattr(self, "coordinator", coordinator),
        )
        camera = create_live_camera(coordinator, entry, ready_info(tmp_path))
        assert camera is not None

    def test_the_camera_is_registered_for_its_switch(
        self, coordinator, entry, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "custom_components.dreame_mower.entity.DreameMowerEntity.__init__",
            lambda self, coordinator, key: setattr(self, "coordinator", coordinator),
        )
        camera = create_live_camera(coordinator, entry, ready_info(tmp_path))
        stored = coordinator.hass.data[DOMAIN][entry.entry_id][DATA_LIVE_CAMERA]
        assert stored is camera


@pytest.mark.asyncio
class TestStreamSource:
    """The source must never wake the mower by itself."""

    async def test_no_source_without_a_session(self, camera):
        assert await camera.stream_source() is None
        camera.coordinator.device.set_camera_stream.assert_not_called()
        camera._runtime.async_start.assert_not_called()

    async def test_the_source_is_the_held_address(self, camera):
        await camera.async_turn_on()
        assert await camera.stream_source() == URL


@pytest.mark.asyncio
class TestTurningOn:
    """Opening a session."""

    async def test_asks_the_mower_to_publish_then_starts_the_helper(self, camera):
        await camera.async_turn_on()
        camera.coordinator.device.set_camera_stream.assert_awaited_once_with(True)
        camera._runtime.async_start.assert_awaited_once_with(SESSION)
        assert camera.session_active

    async def test_a_second_request_does_not_open_another_session(self, camera):
        await camera.async_turn_on()
        await camera.async_turn_on()
        camera._runtime.async_start.assert_awaited_once()

    async def test_a_mower_that_refuses_leaves_nothing_running(self, camera):
        camera.coordinator.device.set_camera_stream = AsyncMock(return_value=False)
        await camera.async_turn_on()
        assert not camera.session_active
        camera._runtime.async_start.assert_not_called()
        assert "would not start its camera" in camera.extra_state_attributes["last_error"]

    async def test_a_cloud_that_will_not_provision_leaves_nothing_running(
        self, camera, provision
    ):
        provision.side_effect = DreameMowerVideoError("not enabled for video")
        await camera.async_turn_on()
        assert not camera.session_active
        camera.coordinator.device.set_camera_stream.assert_not_called()
        assert "not enabled" in camera.extra_state_attributes["last_error"]

    async def test_a_helper_that_fails_switches_the_camera_back_off(self, camera):
        camera._runtime.async_start = AsyncMock(
            side_effect=DreameMowerVideoRuntimeError("did not answer in time")
        )
        await camera.async_turn_on()
        assert not camera.session_active
        camera.coordinator.device.set_camera_stream.assert_any_await(False)


@pytest.mark.asyncio
class TestTurningOff:
    """Releasing a session."""

    async def test_stops_the_helper_and_the_mower(self, camera):
        await camera.async_turn_on()
        camera.coordinator.device.set_camera_stream.reset_mock()
        await camera.async_turn_off()
        camera._runtime.async_stop.assert_awaited()
        camera.coordinator.device.set_camera_stream.assert_awaited_once_with(False)
        assert not camera.session_active
        assert await camera.stream_source() is None

    async def test_removal_never_leaves_the_mower_publishing(self, camera):
        await camera.async_turn_on()
        camera.coordinator.device.set_camera_stream.reset_mock()
        await camera.async_will_remove_from_hass()
        camera.coordinator.device.set_camera_stream.assert_awaited_once_with(False)
        assert not camera.session_active

    async def test_a_mower_that_will_not_switch_off_does_not_break_teardown(self, camera):
        await camera.async_turn_on()
        camera.coordinator.device.set_camera_stream = AsyncMock(
            side_effect=RuntimeError("offline")
        )
        await camera.async_turn_off()
        assert not camera.session_active


@pytest.mark.asyncio
class TestSettlingAfterARestart:
    """The mower does not report publishing, so its state is asserted."""

    async def test_tells_the_mower_to_stop_publishing_at_startup(
        self, camera, monkeypatch
    ):
        """A crash can leave the camera on with nothing left to stop it."""
        started = []

        def capture(coro, name):
            started.append(coro)
            return asyncio.get_running_loop().create_task(asyncio.sleep(0))

        camera.hass.async_create_background_task = capture
        monkeypatch.setattr(
            "custom_components.dreame_mower.live_camera.DreameMowerEntity"
            ".async_added_to_hass",
            AsyncMock(),
            raising=False,
        )

        await camera.async_added_to_hass()
        assert started, "expected the mower to be settled in the background"
        await started[0]

        camera.coordinator.device.set_camera_stream.assert_awaited_once_with(False)
        assert not camera.session_active

    async def test_startup_survives_a_mower_that_cannot_be_reached(self, camera):
        """An unreachable mower must not break adding the entity."""
        camera.coordinator.device.set_camera_stream = AsyncMock(
            side_effect=RuntimeError("offline")
        )

        await camera._async_clear_stale_session()

        assert not camera.session_active


@pytest.mark.asyncio
class TestTheStation:
    """The mower sends no video from its station."""

    async def test_refuses_to_start_at_the_station(self, camera):
        """Starting there would only ever produce a stream with no picture."""
        camera.coordinator.device.status_code = 6  # charging

        await camera.async_turn_on()

        assert not camera.session_active
        camera.coordinator.device.set_camera_stream.assert_not_called()
        camera._runtime.async_start.assert_not_called()
        assert "station" in camera.extra_state_attributes["last_error"]

    @pytest.mark.parametrize("status", [6, 13, 15, 16])
    async def test_every_station_state_refuses(self, camera, status):
        camera.coordinator.device.status_code = status
        await camera.async_turn_on()
        assert not camera.session_active

    async def test_retires_a_session_once_the_mower_docks(self, camera, monkeypatch):
        """A stream that has lost its picture must not be left running."""
        monkeypatch.setattr(
            "custom_components.dreame_mower.live_camera.IDLE_POLL_INTERVAL", 0.01
        )
        stream = Mock()
        stream.outputs.return_value = {"hls": Mock()}
        monkeypatch.setattr(
            type(camera), "stream", property(lambda self: stream), raising=False
        )

        await camera.async_turn_on()
        assert camera.session_active
        camera.coordinator.device.status_code = 6  # the mower docks

        await asyncio.wait_for(camera._async_watch(), timeout=2)

        assert not camera.session_active
        camera.coordinator.device.set_camera_stream.assert_any_await(False)

    async def test_an_unreadable_status_does_not_block_video(self, camera):
        """A mower that has not reported yet is not assumed to be docked."""
        camera.coordinator.device.status_code = None
        await camera.async_turn_on()
        assert camera.session_active
        await camera.async_turn_off()


@pytest.mark.asyncio
class TestStreamRequests:
    """A genuine stream request starts the session; nothing else does."""

    async def test_a_stream_request_starts_a_session(self, camera, monkeypatch):
        created = AsyncMock(return_value="stream")
        monkeypatch.setattr(
            "homeassistant.components.camera.Camera.async_create_stream",
            created,
        )
        try:
            assert await camera.async_create_stream() == "stream"
            assert camera.session_active
            camera.coordinator.device.set_camera_stream.assert_awaited_once_with(True)
        finally:
            await camera.async_turn_off()

    async def test_a_stream_request_reports_why_it_could_not_start(self, camera):
        camera.coordinator.device.set_camera_stream = AsyncMock(return_value=False)
        from homeassistant.exceptions import HomeAssistantError

        with pytest.raises(HomeAssistantError, match="Could not start live video"):
            await camera.async_create_stream()
        assert not camera.session_active

    async def test_an_existing_session_is_not_started_twice(self, camera, monkeypatch):
        created = AsyncMock(return_value="stream")
        monkeypatch.setattr(
            "homeassistant.components.camera.Camera.async_create_stream", created
        )
        try:
            await camera.async_turn_on()
            camera._runtime.async_start.reset_mock()
            await camera.async_create_stream()
            camera._runtime.async_start.assert_not_called()
        finally:
            await camera.async_turn_off()


@pytest.mark.asyncio
class TestStills:
    """Home Assistant asks for a snapshot whenever the camera is on a dashboard."""

    async def test_no_still_and_no_stream_while_off(self, camera):
        """Asking before anyone switches it on must not reach the mower."""
        assert camera.use_stream_for_stills is False
        assert await camera.async_camera_image() is None
        camera.coordinator.device.set_camera_stream.assert_not_called()
        camera._runtime.async_start.assert_not_called()

    async def test_stills_come_from_the_stream_once_on(self, camera):
        """The mower sends no separate image, so a still is a frame of the stream."""
        await camera.async_turn_on()
        assert camera.use_stream_for_stills is True


@pytest.mark.asyncio
class TestIdleWatcher:
    """Retiring a session nobody is watching."""

    async def test_retires_a_session_that_was_never_watched(self, camera, monkeypatch):
        monkeypatch.setattr(
            "custom_components.dreame_mower.live_camera.FIRST_VIEWER_GRACE", 0.0
        )
        monkeypatch.setattr(
            "custom_components.dreame_mower.live_camera.IDLE_POLL_INTERVAL", 0.01
        )
        await camera.async_turn_on()
        await camera._async_watch()
        assert not camera.session_active

    async def test_keeps_a_session_that_is_being_watched(self, camera, monkeypatch):
        monkeypatch.setattr(
            "custom_components.dreame_mower.live_camera.FIRST_VIEWER_GRACE", 0.0
        )
        monkeypatch.setattr(
            "custom_components.dreame_mower.live_camera.IDLE_POLL_INTERVAL", 0.01
        )
        stream = Mock()
        stream.outputs.return_value = {"hls": Mock()}
        monkeypatch.setattr(
            type(camera), "stream", property(lambda self: stream), raising=False
        )
        await camera.async_turn_on()
        watcher = asyncio.get_running_loop().create_task(camera._async_watch())
        await asyncio.sleep(0.1)
        assert camera.session_active
        watcher.cancel()
        with pytest.raises(asyncio.CancelledError):
            await watcher

    async def test_retires_a_session_once_the_viewers_leave(self, camera, monkeypatch):
        monkeypatch.setattr(
            "custom_components.dreame_mower.live_camera.IDLE_POLL_INTERVAL", 0.01
        )
        monkeypatch.setattr("custom_components.dreame_mower.live_camera.IDLE_GRACE", 0.0)
        viewers = {"hls": Mock()}
        stream = Mock()
        stream.outputs.side_effect = lambda: viewers
        monkeypatch.setattr(
            type(camera), "stream", property(lambda self: stream), raising=False
        )
        await camera.async_turn_on()
        watcher = asyncio.get_running_loop().create_task(camera._async_watch())
        await asyncio.sleep(0.05)
        assert camera.session_active
        viewers.clear()
        await asyncio.wait_for(watcher, timeout=2)
        assert not camera.session_active

    async def test_gives_up_when_the_helper_dies(self, camera, monkeypatch):
        monkeypatch.setattr(
            "custom_components.dreame_mower.live_camera.IDLE_POLL_INTERVAL", 0.01
        )
        stream = Mock()
        stream.outputs.return_value = {"hls": Mock()}
        monkeypatch.setattr(
            type(camera), "stream", property(lambda self: stream), raising=False
        )
        await camera.async_turn_on()
        camera._runtime.running = False
        await asyncio.wait_for(camera._async_watch(), timeout=2)
        assert not camera.session_active
