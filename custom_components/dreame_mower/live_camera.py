"""Live camera entity for mowers that can publish video.

The mower only publishes while it is asked to, and doing so costs battery, so
the stream is not started on the integration's own initiative. Turning the
entity on provisions a session, asks the mower to publish and starts the local
helper; turning it off, removing the entity or leaving the stream unwatched
takes all of that back down.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry

from .coordinator import DreameMowerCoordinator
from .dreame.cloud.cloud_video import (
    DreameMowerCloudVideo,
    DreameMowerVideoError,
    DreameMowerVideoSession,
)
from .dreame.video_runtime import (
    DreameMowerVideoRuntime,
    DreameMowerVideoRuntimeError,
    DreameMowerVideoRuntimeInfo,
    find_runtime,
)
from .entity import DreameMowerEntity

_LOGGER = logging.getLogger(__name__)

# How often the idle watcher looks at the stream.
IDLE_POLL_INTERVAL = 5.0

# How long the session may stay up after the last viewer leaves.
IDLE_GRACE = 30.0

# How long to wait for a first viewer before concluding that the stream was
# only being inspected rather than watched.
FIRST_VIEWER_GRACE = 60.0

# A session is never held longer than this, so a forgotten camera cannot keep
# the mower's own camera running.
MAX_SESSION_SECONDS = 30 * 60


async def async_create_live_camera(
    coordinator: DreameMowerCoordinator, entry: ConfigEntry
) -> Optional["DreameMowerLiveCameraEntity"]:
    """Return a live camera when the local helper is installed.

    Returns None when it is not, so mowers and hosts without live video gain
    no entity at all. The reason is logged once, since the helper is installed
    deliberately and its absence is the normal case.
    """
    # Looking for the bundle touches the filesystem, so keep it off the
    # event loop.
    config_dir = coordinator.hass.config.path()
    info = await coordinator.hass.async_add_executor_job(find_runtime, config_dir)
    if not info.available:
        _LOGGER.debug(
            "Live video is unavailable (%s%s); see custom_components/dreame_mower/xp2p",
            info.state.value,
            f": {info.detail}" if info.detail else "",
        )
        return None

    _LOGGER.debug("Live video helper %s found in %s", info.sdk_version, info.directory)
    return DreameMowerLiveCameraEntity(coordinator, entry, info)


class DreameMowerLiveCameraEntity(DreameMowerEntity, Camera):
    """The mower's own camera, streamed through the local helper."""

    _attr_supported_features = CameraEntityFeature.STREAM | CameraEntityFeature.ON_OFF

    def __init__(
        self,
        coordinator: DreameMowerCoordinator,
        config_entry: ConfigEntry,
        runtime_info: DreameMowerVideoRuntimeInfo,
    ) -> None:
        """Initialize the live camera in its resting, switched-off state."""
        DreameMowerEntity.__init__(self, coordinator, "live_camera")
        Camera.__init__(self)

        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_live_camera"
        self._attr_translation_key = "live_camera"
        self._attr_is_on = False

        self._runtime_info = runtime_info
        self._runtime = DreameMowerVideoRuntime(runtime_info.directory)
        self._session: Optional[DreameMowerVideoSession] = None
        self._url: Optional[str] = None
        self._error: Optional[str] = None
        self._lock = asyncio.Lock()
        self._watcher: Optional[asyncio.Task] = None

    @property
    def is_on(self) -> bool:
        """Return whether a session is currently being held open."""
        return bool(self._attr_is_on)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Explain what the camera is doing, and why when it is not."""
        attributes: dict[str, Any] = {
            "helper_version": self._runtime_info.sdk_version,
            "streaming": self._runtime.running,
        }
        if self._error:
            attributes["last_error"] = self._error
        return attributes

    async def stream_source(self) -> Optional[str]:
        """Return the address to read the media from, if one is being held.

        Home Assistant also calls this while working out what the camera can
        do, so it must never start a session or reach the mower.
        """
        return self._url if self.is_on else None

    async def async_turn_on(self) -> None:
        """Provision a session, ask the mower to publish, and hold it open."""
        async with self._lock:
            if self._attr_is_on:
                return
            try:
                await self._async_open_session()
            except (DreameMowerVideoError, DreameMowerVideoRuntimeError) as err:
                self._error = str(err)
                _LOGGER.error("Could not start live video: %s", err)
                await self._async_close_session()
                self.async_write_ha_state()
                return

            self._error = None
            self._attr_is_on = True

        self._start_watcher()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Stop publishing and release everything the session held."""
        await self._async_cancel_watcher()
        async with self._lock:
            await self._async_close_session()
            self._attr_is_on = False
        self.async_write_ha_state()

    async def _async_open_session(self) -> None:
        """Take every step needed before media can be read."""
        device = self.coordinator.device
        cloud = DreameMowerCloudVideo(
            device.cloud_device._cloud_base, str(device.device_id)
        )
        session = await self.hass.async_add_executor_job(cloud.provision)
        self._session = session

        if not await device.set_camera_stream(True):
            raise DreameMowerVideoRuntimeError(
                "The mower would not start its camera; it may be docked or returning"
            )

        self._url = await self._runtime.async_start(session)

    async def _async_close_session(self) -> None:
        """Undo whatever part of a session was established."""
        self._url = None
        await self._runtime.async_stop()
        if self._session is not None:
            self._session = None
            try:
                await self.coordinator.device.set_camera_stream(False)
            except Exception as err:  # noqa: BLE001 - teardown must not raise
                _LOGGER.debug("Could not switch the mower's camera off: %s", err)

    def _start_watcher(self) -> None:
        """Watch the stream so an unwatched session does not stay up."""
        if self._watcher is not None and not self._watcher.done():
            return
        self._watcher = self.hass.async_create_background_task(
            self._async_watch(), "dreame_mower_live_camera_idle"
        )

    async def _async_cancel_watcher(self) -> None:
        """Stop the watcher without cancelling the task doing the stopping."""
        watcher, self._watcher = self._watcher, None
        if watcher is None or watcher is asyncio.current_task():
            return
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass

    def _has_viewers(self) -> bool:
        """Return whether Home Assistant is serving this stream to anyone."""
        stream = self.stream
        if stream is None:
            return False
        try:
            return bool(stream.outputs())
        except Exception:  # noqa: BLE001 - a stream being torn down counts as idle
            return False

    async def _async_watch(self) -> None:
        """Retire a session once nobody is watching it any more."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + MAX_SESSION_SECONDS
        first_viewer_by = loop.time() + FIRST_VIEWER_GRACE
        seen_viewer = False
        idle_since: Optional[float] = None

        try:
            while self._attr_is_on:
                now = loop.time()
                if self._has_viewers():
                    seen_viewer = True
                    idle_since = None
                elif seen_viewer:
                    idle_since = idle_since if idle_since is not None else now
                    if now - idle_since >= IDLE_GRACE:
                        _LOGGER.debug("Live video is unwatched; retiring the session")
                        break
                elif now >= first_viewer_by:
                    _LOGGER.debug("Live video was never watched; retiring the session")
                    break

                if now >= deadline:
                    _LOGGER.info("Live video reached its time limit; switching it off")
                    break

                if not self._runtime.running:
                    _LOGGER.warning("The video helper stopped; switching the camera off")
                    break

                await asyncio.sleep(IDLE_POLL_INTERVAL)
        except asyncio.CancelledError:
            raise

        if self._attr_is_on:
            await self.async_turn_off()

    async def async_will_remove_from_hass(self) -> None:
        """Never leave the mower publishing once the entity goes away."""
        await self._async_cancel_watcher()
        async with self._lock:
            await self._async_close_session()
            self._attr_is_on = False
        await super().async_will_remove_from_hass()
