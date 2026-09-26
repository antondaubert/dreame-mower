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
from homeassistant.exceptions import HomeAssistantError

from .const import DATA_LIVE_CAMERA, DOMAIN
from .coordinator import DreameMowerCoordinator
from .dreame.const import DeviceStatus
from .dreame.cloud.cloud_video import (
    DreameMowerCloudVideo,
    DreameMowerVideoError,
    DreameMowerVideoSession,
)
from .dreame.video_runtime import (
    DreameMowerVideoRuntime,
    DreameMowerVideoRuntimeError,
    DreameMowerVideoRuntimeInfo,
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

# The mower does not publish video from its station, so a session started or
# held there produces a stream with no picture. These are the charging states
# rather than every state that reads as docked: a mower building a map is out
# on the lawn and sends video like any other run.
AT_STATION_MESSAGE = "The mower does not send video from its station"
DOCKED_STATUSES = frozenset(
    {
        DeviceStatus.CHARGING,
        DeviceStatus.CHARGING_COMPLETE,
        DeviceStatus.CHARGING_PAUSED_HIGH_TEMPERATURE,
        DeviceStatus.CHARGING_PAUSED_LOW_TEMPERATURE,
    }
)


def create_live_camera(
    coordinator: DreameMowerCoordinator,
    entry: ConfigEntry,
    info: DreameMowerVideoRuntimeInfo,
) -> Optional["DreameMowerLiveCameraEntity"]:
    """Return a live camera when the local helper is installed.

    Returns None when it is not, so mowers and hosts without live video gain
    no entity at all. The camera is also registered for its switch, which
    drives the same session rather than a second one.
    """
    if not info.available:
        return None

    _LOGGER.debug("Live video helper %s found in %s", info.sdk_version, info.directory)
    camera = DreameMowerLiveCameraEntity(coordinator, entry, info)
    coordinator.hass.data[DOMAIN][entry.entry_id][DATA_LIVE_CAMERA] = camera
    return camera


class DreameMowerLiveCameraEntity(DreameMowerEntity, Camera):
    """The mower's own camera, streamed through the local helper.

    The mower does not report whether it is publishing, so its state is
    asserted rather than read, the way the vendor app does it.
    """

    # Deliberately not ON_OFF: Home Assistant refuses a stream request on a
    # camera that reports itself off, and logs that refusal as an error even
    # though being off is a normal resting state. The session is started when
    # a stream is actually asked for instead, and the switch drives it
    # explicitly.
    _attr_supported_features = CameraEntityFeature.STREAM

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
        self._session_active = False

        self._runtime_info = runtime_info
        self._runtime = DreameMowerVideoRuntime(runtime_info.directory)
        self._session: Optional[DreameMowerVideoSession] = None
        self._url: Optional[str] = None
        self._error: Optional[str] = None
        self._lock = asyncio.Lock()
        self._watcher: Optional[asyncio.Task] = None

    @property
    def session_active(self) -> bool:
        """Return whether the mower is publishing for us right now."""
        return self._session_active

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

    @property
    def use_stream_for_stills(self) -> bool:
        """Take stills from the live stream.

        The mower publishes video but no separate still image, so a snapshot
        is a frame of the stream. While the camera is off there is no stream
        to take one from.
        """
        return self._session_active

    async def async_camera_image(
        self, width: Optional[int] = None, height: Optional[int] = None
    ) -> Optional[bytes]:
        """Return no image while the camera is off.

        Home Assistant asks for a still whenever the camera appears on a
        dashboard, including before anyone switches it on, and that must not
        reach the mower or raise.
        """
        return None

    async def stream_source(self) -> Optional[str]:
        """Return the address to read the media from, if one is being held.

        Home Assistant also calls this while working out what the camera can
        do, and while browsing media, so it must never start a session or
        reach the mower.
        """
        return self._url if self._session_active else None

    async def async_create_stream(self) -> Any:
        """Start a session, if needed, for a request that will really watch.

        Only a genuine stream request reaches this: stills come through
        use_stream_for_stills, which stays false until a session exists.
        """
        if not self._session_active:
            await self.async_turn_on()
            if not self._session_active:
                raise HomeAssistantError(
                    f"Could not start live video: {self._error}"
                    if self._error
                    else "Could not start live video"
                )
        return await super().async_create_stream()

    async def async_turn_on(self) -> None:
        """Provision a session, ask the mower to publish, and hold it open."""
        async with self._lock:
            if self._session_active:
                return
            if self._is_docked():
                # Expected rather than a failure, so it is reported to whoever
                # asked without an entry of its own in the log.
                _LOGGER.debug("Not starting live video: %s", AT_STATION_MESSAGE)
                self._error = AT_STATION_MESSAGE
                self.async_write_ha_state()
                return
            try:
                await self._async_open_session()
            except Exception as err:  # noqa: BLE001 - see below
                # Anything at all after the mower was told to publish would
                # otherwise leave it doing so with no session holding it, so
                # every failure tears down, including a cancellation.
                self._error = str(err) or type(err).__name__
                _LOGGER.error("Could not start live video: %s", err)
                await self._async_close_session()
                self.async_write_ha_state()
                if isinstance(err, asyncio.CancelledError):
                    raise
                return

            self._error = None
            self._session_active = True

        self._start_watcher()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Stop publishing and release everything the session held."""
        await self._async_cancel_watcher()
        async with self._lock:
            await self._async_close_session()
            self._session_active = False
        self.async_write_ha_state()

    def _is_docked(self) -> bool:
        """Return whether the mower is at its station."""
        try:
            return int(self.coordinator.device.status_code) in DOCKED_STATUSES
        except (TypeError, ValueError):
            return False

    async def _async_open_session(self) -> None:
        """Take every step needed before media can be read."""
        if self._is_docked():
            # Checked before anything is asked of the cloud or the mower: a
            # session here would only ever produce a picture-less stream.
            raise DreameMowerVideoError(AT_STATION_MESSAGE)

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

        # Home Assistant builds the stream once and keeps it, so a later
        # session on a different port has to be pointed at its new address or
        # the stream would go on reading the previous, dead one.
        if self.stream is not None:
            self.stream.update_source(self._url)

    async def _async_close_session(self) -> None:
        """Undo whatever part of a session was established.

        The mower is only forgotten once it confirms it has stopped, so a
        refused or unreachable stop is retried the next time round rather
        than leaving it publishing with nothing able to switch it off.
        """
        self._url = None
        await self._runtime.async_stop()
        if self._session is None:
            return

        try:
            stopped = await self.coordinator.device.set_camera_stream(False)
        except Exception as err:  # noqa: BLE001 - teardown must not raise
            _LOGGER.warning(
                "Could not tell the mower to stop publishing; it may still be "
                "using its camera: %s",
                err,
            )
            return

        if not stopped:
            _LOGGER.warning(
                "The mower would not stop publishing; it may still be using "
                "its camera"
            )
            return

        self._session = None

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
            while self._session_active:
                now = loop.time()
                if self._has_viewers():
                    if not seen_viewer:
                        _LOGGER.debug("Live video has a viewer")
                    seen_viewer = True
                    idle_since = None
                elif seen_viewer:
                    if idle_since is None:
                        idle_since = now
                        _LOGGER.debug(
                            "Live video has no viewers; retiring in %.0fs unless one returns",
                            IDLE_GRACE,
                        )
                    if now - idle_since >= IDLE_GRACE:
                        _LOGGER.debug("Live video is unwatched; retiring the session")
                        break
                elif now >= first_viewer_by:
                    _LOGGER.debug("Live video was never watched; retiring the session")
                    break

                if self._is_docked():
                    _LOGGER.info("The mower has docked; switching live video off")
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

        if self._session_active:
            await self.async_turn_off()

    async def async_added_to_hass(self) -> None:
        """Make the mower agree that it is not publishing.

        Publishing outlives Home Assistant, but the helper that read it does
        not, so after a restart the mower may still have its camera on with
        nothing left to consume or stop it. The mower cannot be asked, so it
        is told, once, in the background, so a slow or unreachable mower does
        not hold up startup.
        """
        await super().async_added_to_hass()
        self.hass.async_create_background_task(
            self._async_clear_stale_session(), "dreame_mower_live_camera_clear"
        )

    async def _async_clear_stale_session(self) -> None:
        """Switch the mower's camera off in case a previous run left it on."""
        try:
            settled = await self.coordinator.device.set_camera_stream(False)
        except Exception as err:  # noqa: BLE001 - startup must not break over this
            _LOGGER.debug("Could not settle the mower's camera at startup: %s", err)
            return
        # A refusal here is expected: the mower usually is not publishing.
        _LOGGER.debug("Mower camera settled at startup: %s", settled)

    async def async_will_remove_from_hass(self) -> None:
        """Never leave the mower publishing once the entity goes away."""
        await self._async_cancel_watcher()
        async with self._lock:
            await self._async_close_session()
            self._session_active = False
        await super().async_will_remove_from_hass()
