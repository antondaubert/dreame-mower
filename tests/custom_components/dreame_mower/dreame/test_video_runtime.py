"""Tests for supervision of the live video helper."""

import json
import os
import platform
import stat
import sys
import time
from pathlib import Path

import pytest

from custom_components.dreame_mower.dreame.cloud.cloud_video import (
    DreameMowerVideoSession,
)
from custom_components.dreame_mower.dreame.video_runtime import (
    RUNTIME_SUBDIR,
    DreameMowerVideoRuntime,
    DreameMowerVideoRuntimeError,
    DreameMowerVideoRuntimeState,
    build_command,
    find_runtime,
)

SESSION = DreameMowerVideoSession(
    product_id="PID",
    device_name="DEVNAME",
    p2p_info="XP2Pabc",
    app_id="app-id",
    app_secret="app-secret",
)

# A stand-in for the helper: reads the request, then answers as it would.
FAKE_HELPER = '''#!{python}
import sys, time
request = {{}}
for line in sys.stdin:
    line = line.strip()
    if not line:
        break
    key, _, value = line.partition("=")
    request[key] = value
{behaviour}
'''

ANSWER_URL = '''
sys.stderr.write("starting\\n")
sys.stderr.flush()
print("URL=http://127.0.0.1:9/" + request["product_id"] + "/ipc.flv?quality=" + request["quality"])
sys.stdout.flush()
for _ in sys.stdin:      # hold until the caller closes the pipe
    pass
'''

ANSWER_ERROR = '''
print("ERROR=peer_link_timeout")
sys.stdout.flush()
'''

ANSWER_NOTHING = '''
sys.exit(3)
'''

ANSWER_IGNORE_STDIN_CLOSE = '''
print("URL=http://127.0.0.1:9/held")
sys.stdout.flush()
time.sleep(60)
'''


def install_fake(directory: Path, behaviour: str, **manifest_extra) -> Path:
    """Write a bundle whose helper behaves as asked."""
    directory.mkdir(parents=True, exist_ok=True)
    helper = directory / "xp2p-runner"
    helper.write_text(FAKE_HELPER.format(python=sys.executable, behaviour=behaviour))
    helper.chmod(helper.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    manifest = {
        "sdk_version": "v2.4.72",
        "arch": platform.machine(),
        "executable": "xp2p-runner",
        "loader": None,
    }
    manifest.update(manifest_extra)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


class TestFindRuntime:
    """Reporting what is installed."""

    def test_reports_nothing_installed(self, tmp_path):
        info = find_runtime(tmp_path)
        assert info.state is DreameMowerVideoRuntimeState.NOT_INSTALLED
        assert not info.available

    def test_reports_a_usable_bundle(self, tmp_path):
        install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_URL)
        info = find_runtime(tmp_path)
        assert info.state is DreameMowerVideoRuntimeState.READY
        assert info.available
        assert info.sdk_version == "v2.4.72"

    def test_reports_the_wrong_architecture(self, tmp_path):
        install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_URL, arch="some-other-arch")
        info = find_runtime(tmp_path)
        assert info.state is DreameMowerVideoRuntimeState.UNSUPPORTED_ARCHITECTURE
        assert "some-other-arch" in (info.detail or "")

    def test_reports_an_unreadable_manifest(self, tmp_path):
        directory = tmp_path / RUNTIME_SUBDIR
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text("{not json")
        assert find_runtime(tmp_path).state is DreameMowerVideoRuntimeState.DAMAGED

    def test_reports_a_missing_helper(self, tmp_path):
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_URL)
        (directory / "xp2p-runner").unlink()
        info = find_runtime(tmp_path)
        assert info.state is DreameMowerVideoRuntimeState.DAMAGED
        assert "helper is missing" in (info.detail or "")

    def test_reports_a_missing_loader(self, tmp_path):
        install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_URL, loader="lib/absent.so")
        info = find_runtime(tmp_path)
        assert info.state is DreameMowerVideoRuntimeState.DAMAGED
        assert "loader is missing" in (info.detail or "")


class TestBuildCommand:
    """Turning a bundle into a command."""

    def test_runs_the_helper_directly_without_a_loader(self, tmp_path):
        command = build_command(tmp_path, {"executable": "runner", "loader": None})
        assert command == [str(tmp_path / "runner")]

    def test_goes_through_the_loader_when_one_is_bundled(self, tmp_path):
        command = build_command(
            tmp_path, {"executable": "runner", "loader": "lib/ld.so"}
        )
        assert command == [
            str(tmp_path / "lib/ld.so"),
            "--library-path",
            str(tmp_path / "lib"),
            str(tmp_path / "runner"),
        ]


@pytest.mark.asyncio
class TestDreameMowerVideoRuntime:
    """Running a session."""

    async def test_starts_and_returns_the_address(self, tmp_path):
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_URL)
        runtime = DreameMowerVideoRuntime(directory)
        try:
            url = await runtime.async_start(SESSION, quality="super")
            assert url == "http://127.0.0.1:9/PID/ipc.flv?quality=super"
            assert runtime.running
            assert runtime.url == url
        finally:
            await runtime.async_stop()

    async def test_reuses_a_session_already_running(self, tmp_path):
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_URL)
        runtime = DreameMowerVideoRuntime(directory)
        try:
            first = await runtime.async_start(SESSION)
            assert await runtime.async_start(SESSION) == first
        finally:
            await runtime.async_stop()

    async def test_stopping_ends_the_helper(self, tmp_path):
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_URL)
        runtime = DreameMowerVideoRuntime(directory)
        await runtime.async_start(SESSION)
        process = runtime._process
        await runtime.async_stop()
        assert not runtime.running
        assert runtime.url is None
        assert process is not None and process.returncode is not None

    async def test_kills_a_helper_that_ignores_the_closed_pipe(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "custom_components.dreame_mower.dreame.video_runtime.STOP_TIMEOUT", 0.5
        )
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_IGNORE_STDIN_CLOSE)
        runtime = DreameMowerVideoRuntime(directory)
        await runtime.async_start(SESSION)
        process = runtime._process
        await runtime.async_stop()
        assert process is not None and process.returncode is not None

    async def test_surfaces_a_refusal_from_the_mower(self, tmp_path):
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_ERROR)
        runtime = DreameMowerVideoRuntime(directory)
        with pytest.raises(DreameMowerVideoRuntimeError, match="peer_link_timeout"):
            await runtime.async_start(SESSION)
        assert not runtime.running

    async def test_surfaces_a_helper_that_says_nothing(self, tmp_path):
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_NOTHING)
        runtime = DreameMowerVideoRuntime(directory)
        with pytest.raises(DreameMowerVideoRuntimeError, match="without answering"):
            await runtime.async_start(SESSION)
        assert not runtime.running

    async def test_gives_up_on_a_helper_that_never_answers(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "custom_components.dreame_mower.dreame.video_runtime.START_TIMEOUT", 0.5
        )
        monkeypatch.setattr(
            "custom_components.dreame_mower.dreame.video_runtime.STOP_TIMEOUT", 0.5
        )
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_IGNORE_STDIN_CLOSE)
        (directory / "xp2p-runner").write_text(
            FAKE_HELPER.format(python=sys.executable, behaviour="time.sleep(30)")
        )
        os.chmod(directory / "xp2p-runner", 0o755)
        runtime = DreameMowerVideoRuntime(directory)
        with pytest.raises(DreameMowerVideoRuntimeError, match="did not answer in time"):
            await runtime.async_start(SESSION)
        assert not runtime.running

    async def test_abandons_a_helper_that_never_reached_a_session(self, tmp_path, monkeypatch):
        # A helper still negotiating is not watching stdin, so it must be
        # stopped directly rather than waiting out the full grace period.
        monkeypatch.setattr(
            "custom_components.dreame_mower.dreame.video_runtime.START_TIMEOUT", 0.5
        )
        monkeypatch.setattr(
            "custom_components.dreame_mower.dreame.video_runtime.STOP_TIMEOUT", 30.0
        )
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, "time.sleep(30)")
        runtime = DreameMowerVideoRuntime(directory)
        started = time.monotonic()
        with pytest.raises(DreameMowerVideoRuntimeError):
            await runtime.async_start(SESSION)
        assert time.monotonic() - started < 10.0
        assert not runtime.running

    async def test_reports_a_helper_that_cannot_be_started(self, tmp_path):
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_URL)
        (directory / "xp2p-runner").chmod(0o644)
        runtime = DreameMowerVideoRuntime(directory)
        with pytest.raises(DreameMowerVideoRuntimeError, match="could not be started"):
            await runtime.async_start(SESSION)

    async def test_sends_the_session_on_stdin_not_the_command_line(self, tmp_path):
        directory = install_fake(tmp_path / RUNTIME_SUBDIR, ANSWER_URL)
        runtime = DreameMowerVideoRuntime(directory)
        try:
            await runtime.async_start(SESSION)
            process = runtime._process
            assert process is not None
            command_line = " ".join(build_command(directory, {"executable": "xp2p-runner", "loader": None}))
            assert SESSION.app_secret not in command_line
            assert SESSION.p2p_info not in command_line
        finally:
            await runtime.async_stop()
