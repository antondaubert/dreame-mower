"""Supervision of the local helper that carries live video.

The camera transport is a native process the user installs separately, see
``custom_components/dreame_mower/xp2p/README.md``. This module finds it,
starts one session, hands back the local address the media can be read from,
and makes sure the process never outlives the session.

Session details are written to the helper's stdin rather than passed as
arguments, so they stay out of the process list, and the helper shuts itself
down as soon as that pipe closes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .cloud.cloud_video import DreameMowerVideoSession

_LOGGER = logging.getLogger(__name__)

# Directory the installer writes to, below the Home Assistant configuration.
RUNTIME_SUBDIR = "dreame_mower/xp2p"

MANIFEST_NAME = "manifest.json"

# The helper allows itself up to a minute to reach the mower, so allow a
# little more than that before giving up on it.
START_TIMEOUT = 75.0

# How long a helper gets to exit on its own once its stdin closes.
STOP_TIMEOUT = 10.0

# A helper that never reached a session is not yet watching its stdin, so
# closing the pipe cannot reach it and it is stopped directly instead.
ABANDON_TIMEOUT = 1.0


class DreameMowerVideoRuntimeState(Enum):
    """Why live video is or is not currently possible."""

    READY = "ready"
    NOT_INSTALLED = "not_installed"
    UNSUPPORTED_ARCHITECTURE = "unsupported_architecture"
    DAMAGED = "damaged"


class DreameMowerVideoRuntimeError(Exception):
    """Raised when a live video session cannot be started."""


@dataclass(frozen=True)
class DreameMowerVideoRuntimeInfo:
    """What was found where the helper is expected to be."""

    state: DreameMowerVideoRuntimeState
    directory: Path
    sdk_version: Optional[str] = None
    detail: Optional[str] = None

    @property
    def available(self) -> bool:
        """Return whether a session could be started."""
        return self.state is DreameMowerVideoRuntimeState.READY


def find_runtime(config_dir: str | Path) -> DreameMowerVideoRuntimeInfo:
    """Describe the helper installed below this configuration directory.

    Never raises: a missing or unusable helper is reported as a state, so the
    caller can present it rather than fail.
    """
    directory = Path(config_dir) / RUNTIME_SUBDIR
    manifest_path = directory / MANIFEST_NAME

    if not manifest_path.is_file():
        return DreameMowerVideoRuntimeInfo(
            DreameMowerVideoRuntimeState.NOT_INSTALLED, directory
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        return DreameMowerVideoRuntimeInfo(
            DreameMowerVideoRuntimeState.DAMAGED, directory, detail=str(err)
        )
    if not isinstance(manifest, dict):
        return DreameMowerVideoRuntimeInfo(
            DreameMowerVideoRuntimeState.DAMAGED, directory, detail="malformed manifest"
        )

    import platform

    machine = platform.machine()
    wanted = manifest.get("arch")
    if wanted and machine and wanted != machine:
        return DreameMowerVideoRuntimeInfo(
            DreameMowerVideoRuntimeState.UNSUPPORTED_ARCHITECTURE,
            directory,
            sdk_version=manifest.get("sdk_version"),
            detail=f"built for {wanted}, running on {machine}",
        )

    executable = manifest.get("executable")
    if not executable or not (directory / executable).is_file():
        return DreameMowerVideoRuntimeInfo(
            DreameMowerVideoRuntimeState.DAMAGED, directory, detail="helper is missing"
        )

    # A bundle carries its own loader when the host's C library differs from
    # the one the helper was built against.
    loader = manifest.get("loader")
    if loader and not (directory / loader).is_file():
        return DreameMowerVideoRuntimeInfo(
            DreameMowerVideoRuntimeState.DAMAGED, directory, detail="loader is missing"
        )

    return DreameMowerVideoRuntimeInfo(
        DreameMowerVideoRuntimeState.READY,
        directory,
        sdk_version=manifest.get("sdk_version"),
    )


def build_command(directory: Path, manifest: dict) -> list[str]:
    """Return the command that starts the helper from this bundle."""
    executable = str(directory / manifest["executable"])
    loader = manifest.get("loader")
    if not loader:
        return [executable]
    return [
        str(directory / loader),
        "--library-path",
        str(directory / "lib"),
        executable,
    ]


class DreameMowerVideoRuntime:
    """One live video session, owned for as long as it is needed."""

    def __init__(self, directory: Path) -> None:
        """Prepare to run the helper installed in this directory."""
        self._directory = directory
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._url: Optional[str] = None

    @property
    def running(self) -> bool:
        """Return whether a session is currently held open."""
        return self._process is not None and self._process.returncode is None

    @property
    def url(self) -> Optional[str]:
        """Return the local address the media can be read from."""
        return self._url if self.running else None

    async def async_start(
        self,
        session: DreameMowerVideoSession,
        quality: str = "high",
        channel: int = 0,
    ) -> str:
        """Start one session and return the address to read the media from."""
        if self.running:
            assert self._url is not None
            return self._url

        manifest = json.loads(
            (self._directory / MANIFEST_NAME).read_text(encoding="utf-8")
        )
        command = build_command(self._directory, manifest)
        _LOGGER.debug("Starting the video helper for %s", session.channel_id)

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as err:
            raise DreameMowerVideoRuntimeError(
                f"The video helper could not be started: {err}"
            ) from err

        self._process = process
        self._stderr_task = asyncio.create_task(self._drain_stderr(process))

        # A blank line ends the request; stdin then stays open to hold the
        # session, because the helper stops as soon as it closes.
        request = (
            f"product_id={session.product_id}\n"
            f"device_name={session.device_name}\n"
            f"p2p_info={session.p2p_info}\n"
            f"app_id={session.app_id}\n"
            f"app_secret={session.app_secret}\n"
            f"quality={quality}\n"
            f"channel={channel}\n"
            "\n"
        )
        try:
            assert process.stdin is not None
            process.stdin.write(request.encode("utf-8"))
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as err:
            await self.async_stop()
            raise DreameMowerVideoRuntimeError(
                "The video helper stopped before it was asked for a stream"
            ) from err

        try:
            url = await asyncio.wait_for(self._read_reply(process), START_TIMEOUT)
        except asyncio.TimeoutError:
            await self.async_stop()
            raise DreameMowerVideoRuntimeError(
                "The video helper did not answer in time"
            ) from None
        except DreameMowerVideoRuntimeError:
            await self.async_stop()
            raise

        self._url = url
        return url

    async def _read_reply(self, process: asyncio.subprocess.Process) -> str:
        """Wait for the helper's single answer and turn it into a result."""
        assert process.stdout is not None
        while True:
            raw = await process.stdout.readline()
            if not raw:
                raise DreameMowerVideoRuntimeError(
                    "The video helper stopped without answering"
                )
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("URL="):
                return line[len("URL=") :]
            if line.startswith("ERROR="):
                raise DreameMowerVideoRuntimeError(
                    f"The mower refused a video session: {line[len('ERROR='):]}"
                )

    async def _drain_stderr(self, process: asyncio.subprocess.Process) -> None:
        """Keep the helper's diagnostics flowing so it cannot block on a pipe."""
        assert process.stderr is not None
        try:
            while True:
                raw = await process.stderr.readline()
                if not raw:
                    return
                _LOGGER.debug("video helper: %s", raw.decode("utf-8", "replace").strip())
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - diagnostics must never break teardown
            return

    async def async_stop(self) -> None:
        """End the session and make sure nothing is left running."""
        process, self._process = self._process, None
        stderr_task, self._stderr_task = self._stderr_task, None
        started, self._url = self._url is not None, None

        if process is not None and process.returncode is None:
            # Closing stdin is the helper's cue to shut down on its own, but
            # only once it has a session to watch that pipe from.
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
            grace = STOP_TIMEOUT if started else ABANDON_TIMEOUT
            try:
                await asyncio.wait_for(process.wait(), grace)
            except asyncio.TimeoutError:
                if started:
                    _LOGGER.warning("The video helper did not stop; terminating it")
                else:
                    _LOGGER.debug("Stopping a video helper that never started")
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()

        if stderr_task is not None:
            stderr_task.cancel()
            try:
                await stderr_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
