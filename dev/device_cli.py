#!/usr/bin/env python3
"""Command-line interface for interacting with the production mower device layer.

Examples:

  .venv/bin/python dev/device_cli.py status --fetch-map
    .venv/bin/python dev/device_cli.py current-map --fetch-map
  .venv/bin/python dev/device_cli.py maps --include-zones
    .venv/bin/python dev/device_cli.py maps --include-spots
    .venv/bin/python dev/device_cli.py spots
  .venv/bin/python dev/device_cli.py set-map --map-id 2 --watch-seconds 5
  .venv/bin/python dev/device_cli.py start-mode --mode zone --zone-id 3
    .venv/bin/python dev/device_cli.py start-mode --mode spot --spot-area-id 2
  .venv/bin/python dev/device_cli.py cutting-height
    .venv/bin/python dev/device_cli.py cutting-height --set 5.5 --map-id 2
    .venv/bin/python dev/device_cli.py cutting-height --set 4 --zone-id 3
    .venv/bin/python dev/device_cli.py cutting-height --mode map_wide
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
import getpass
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from custom_components.dreame_mower.dreame.const import MowingPreferenceMode
from custom_components.dreame_mower.dreame.device import DreameMowerDevice, MowingMode

VALID_COUNTRIES = ["eu", "cn", "us", "ru", "sg"]
VALID_ACCOUNT_TYPES = ["dreame", "mova"]

_LOGGER = logging.getLogger(__name__)


@dataclass
class EventRecorder:
    """Collect property change callbacks emitted by the device."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def handle(self, property_name: str, value: Any) -> None:
        """Store a serializable callback event."""
        self.events.append({"property": property_name, "value": value})


def _prompt_country() -> str:
    options = ", ".join(VALID_COUNTRIES)
    while True:
        value = input(f"Region [{options}] (default: eu): ").strip() or "eu"
        if value in VALID_COUNTRIES:
            return value
        print(f"Invalid region. Choose one of: {options}")


def _prompt_account_type() -> str:
    options = ", ".join(VALID_ACCOUNT_TYPES)
    while True:
        value = input(f"Account type [{options}] (default: dreame): ").strip() or "dreame"
        if value in VALID_ACCOUNT_TYPES:
            return value
        print(f"Invalid account type. Choose one of: {options}")


def load_creds_from_launch() -> dict[str, str] | None:
    """Load credentials from the first CLI-like VS Code launch configuration."""
    launch_path = ROOT_DIR / ".vscode" / "launch.json"
    try:
        raw = launch_path.read_text(encoding="utf-8")
        raw = re.sub(r"//[^\n]*", "", raw)
        config = json.loads(raw)
        configs = config.get("configurations", [])
        debug = next((cfg for cfg in configs if "CLI" in cfg.get("name", "")), None)
        if not debug:
            return None

        args = debug.get("args", [])

        def get_arg(flag: str, default: str = "") -> str:
            return args[args.index(flag) + 1] if flag in args else default

        username = get_arg("--username")
        password = get_arg("--password")
        device_id = get_arg("--device_id") or get_arg("--device-id")
        country = get_arg("--country", "eu") or "eu"
        account_type = get_arg("--account_type", "dreame") or get_arg("--account-type", "dreame") or "dreame"
        if username and password and device_id:
            return {
                "username": username,
                "password": password,
                "device_id": device_id,
                "country": country,
                "account_type": account_type,
            }
    except Exception:
        return None

    return None


def prompt_creds(existing: dict[str, str] | None = None) -> dict[str, str]:
    """Prompt for any missing connection credentials."""
    creds = dict(existing or {})
    if not creds.get("username"):
        creds["username"] = input("Username (email): ").strip()
    if not creds.get("password"):
        creds["password"] = getpass.getpass("Password: ")
    if not creds.get("device_id"):
        creds["device_id"] = input("Device ID: ").strip()
    if not creds.get("country"):
        creds["country"] = _prompt_country()
    if not creds.get("account_type"):
        creds["account_type"] = _prompt_account_type()
    return creds


def resolve_creds(args: argparse.Namespace) -> dict[str, str]:
    """Resolve credentials from launch.json, CLI args, and interactive prompts."""
    creds = load_creds_from_launch() or {}
    if args.username:
        creds["username"] = args.username
    if args.password:
        creds["password"] = args.password
    if args.device_id:
        creds["device_id"] = args.device_id
    if args.country:
        creds["country"] = args.country
    if args.account_type:
        creds["account_type"] = args.account_type
    return prompt_creds(creds)


def parse_contour_id(value: str) -> list[int]:
    """Parse a contour pair formatted as "x,y"."""
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("Contour IDs must be formatted as x,y")

    try:
        return [int(parts[0]), int(parts[1])]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Contour IDs must contain integers") from exc


def serialize_spot_areas(device: DreameMowerDevice) -> list[dict[str, Any]]:
    """Return spot areas with polygon paths in a JSON-serializable shape."""
    if device.vector_map is None:
        return []

    return [
        {
            "id": spot_area.area_id,
            "name": spot_area.name,
            "area": spot_area.area,
            "path": [list(point) for point in spot_area.path],
        }
        for spot_area in device.vector_map.spot_areas
    ]


def build_device_snapshot(
    device: DreameMowerDevice,
    *,
    include_zones: bool = False,
    include_contours: bool = False,
    include_spots: bool = False,
) -> dict[str, Any]:
    """Build a serializable snapshot of the current device state."""
    snapshot: dict[str, Any] = {
        "device_id": device.device_id,
        "connected": device.connected,
        "device_reachable": device.device_reachable,
        "firmware": device.firmware,
        "battery_percent": device.battery_percent,
        "status": device.status,
        "status_code": device.status_code,
        "bluetooth_connected": device.bluetooth_connected,
        "current_map_id": device.current_map_id,
        "cutting_height_cm": device.cutting_height,
        "zone_cutting_heights_cm": device.zone_cutting_heights,
        "task_target_map_id": device.task_target_map_id,
        "maps": device.available_maps,
        "task_data": device.current_task_data,
        "last_update": device.last_update.isoformat(),
        "vector_map_loaded": device.vector_map is not None,
    }

    if include_zones:
        snapshot["zones"] = device.zones
    if include_contours:
        snapshot["contours"] = device.contours
    if include_spots:
        snapshot["spot_areas"] = serialize_spot_areas(device)

    return snapshot


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add shared connection and runtime arguments to a subcommand parser."""
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--device-id", default=None)
    parser.add_argument("--country", default=None, choices=VALID_COUNTRIES)
    parser.add_argument("--account-type", default=None, choices=VALID_ACCOUNT_TYPES)
    parser.add_argument("--hass-config-dir", default=str(ROOT_DIR / ".tmp" / "device_cli"))
    parser.add_argument("--watch-seconds", type=float, default=0.0)
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="CLI for the production Dreame mower device layer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show the current device state")
    add_common_args(status_parser)
    status_parser.add_argument("--fetch-map", action="store_true", help="Fetch vector map data before printing state")
    status_parser.add_argument("--include-zones", action="store_true")
    status_parser.add_argument("--include-contours", action="store_true")

    maps_parser = subparsers.add_parser("maps", help="Fetch vector map data and show map metadata")
    add_common_args(maps_parser)
    maps_parser.add_argument("--include-zones", action="store_true")
    maps_parser.add_argument("--include-contours", action="store_true")
    maps_parser.add_argument("--include-spots", action="store_true")

    spots_parser = subparsers.add_parser("spots", help="Fetch vector map data and list existing spot areas")
    add_common_args(spots_parser)

    current_map_parser = subparsers.add_parser(
        "current-map",
        help="Resolve the current map via the verified MAPL getter",
    )
    add_common_args(current_map_parser)
    current_map_parser.add_argument(
        "--fetch-map",
        action="store_true",
        help="Fetch vector map metadata before resolving the current map",
    )

    set_map_parser = subparsers.add_parser("set-map", help="Switch the current map using the verified map action")
    add_common_args(set_map_parser)
    set_map_parser.add_argument("--map-id", type=int, required=True)
    set_map_parser.add_argument("--skip-map-fetch", action="store_true", help="Do not load vector map metadata before switching")

    start_parser = subparsers.add_parser("start", help="Send the default start command")
    add_common_args(start_parser)

    start_mode_parser = subparsers.add_parser("start-mode", help="Start mowing with the explicit mode API")
    add_common_args(start_mode_parser)
    start_mode_parser.add_argument("--mode", choices=[mode.value for mode in MowingMode], required=True)
    start_mode_parser.add_argument("--map-id", type=int, default=None)
    start_mode_parser.add_argument("--zone-id", type=int, action="append", default=[])
    start_mode_parser.add_argument("--contour-id", type=parse_contour_id, action="append", default=[])
    start_mode_parser.add_argument("--spot-area-id", type=int, action="append", default=[])

    cutting_height_parser = subparsers.add_parser(
        "cutting-height",
        help="Read or set the map-wide cutting height",
    )
    add_common_args(cutting_height_parser)
    cutting_height_parser.add_argument(
        "--set",
        dest="height",
        type=float,
        default=None,
        help="Cutting height in cm to write; omit to only read the current value",
    )
    cutting_height_parser.add_argument("--map-id", type=int, default=None)
    cutting_height_parser.add_argument(
        "--zone-id",
        type=int,
        default=None,
        help="Target a single zone instead of the whole map",
    )
    cutting_height_parser.add_argument(
        "--mode",
        choices=[mode.name.lower() for mode in MowingPreferenceMode],
        default=None,
        help="Switch the map between its map-wide and per-zone preferences",
    )
    cutting_height_parser.add_argument(
        "--skip-map-fetch",
        action="store_true",
        help="Do not load vector map metadata before addressing the map",
    )

    pause_parser = subparsers.add_parser("pause", help="Pause the mower")
    add_common_args(pause_parser)

    dock_parser = subparsers.add_parser("dock", help="Run the stop-then-dock flow")
    add_common_args(dock_parser)

    return parser


async def fetch_vector_map_async(device: DreameMowerDevice) -> bool:
    """Fetch vector map data without blocking the event loop."""
    return await asyncio.get_event_loop().run_in_executor(None, device.fetch_vector_map)


async def run_command(device: DreameMowerDevice, args: argparse.Namespace) -> dict[str, Any]:
    """Run the selected CLI command against a connected device."""
    if args.command == "status":
        if args.fetch_map:
            fetched = await fetch_vector_map_async(device)
        else:
            fetched = None
        return {
            "ok": True,
            "command": args.command,
            "map_fetched": fetched,
            "state": build_device_snapshot(
                device,
                include_zones=args.include_zones,
                include_contours=args.include_contours,
            ),
        }

    if args.command == "maps":
        fetched = await fetch_vector_map_async(device)
        return {
            "ok": fetched,
            "command": args.command,
            "map_fetched": fetched,
            "state": build_device_snapshot(
                device,
                include_zones=args.include_zones,
                include_contours=args.include_contours,
                include_spots=args.include_spots,
            ),
        }

    if args.command == "spots":
        fetched = await fetch_vector_map_async(device)
        return {
            "ok": fetched,
            "command": args.command,
            "map_fetched": fetched,
            "current_map_id": device.current_map_id,
            "spot_areas": serialize_spot_areas(device),
            "state": build_device_snapshot(device, include_spots=True),
        }

    if args.command == "current-map":
        fetched = await fetch_vector_map_async(device) if args.fetch_map else None
        refreshed = await asyncio.get_event_loop().run_in_executor(None, device.refresh_current_map_id)
        return {
            "ok": refreshed,
            "command": args.command,
            "map_fetched": fetched,
            "map_refreshed": refreshed,
            "current_map_id": device.current_map_id,
            "state": build_device_snapshot(device),
        }

    if args.command == "set-map":
        fetched_before = None if args.skip_map_fetch else await fetch_vector_map_async(device)
        success = await device.set_current_map(args.map_id)
        return {
            "ok": success,
            "command": args.command,
            "requested_map_id": args.map_id,
            "map_fetched_before": fetched_before,
            "state": build_device_snapshot(device),
        }

    if args.command == "start":
        success = await device.start_mowing()
        return {"ok": success, "command": args.command, "state": build_device_snapshot(device)}

    if args.command == "start-mode":
        success = await device.start_mowing_mode(
            MowingMode(args.mode),
            map_id=args.map_id,
            zone_ids=args.zone_id or None,
            contour_ids=args.contour_id or None,
            spot_area_ids=args.spot_area_id or None,
        )
        return {
            "ok": success,
            "command": args.command,
            "mode": args.mode,
            "state": build_device_snapshot(device),
        }

    if args.command == "cutting-height":
        fetched_before = None if args.skip_map_fetch else await fetch_vector_map_async(device)
        applied = None
        if args.mode is not None:
            applied = await device.set_mowing_preference_mode(
                MowingPreferenceMode[args.mode.upper()], args.map_id
            )
        if args.height is not None:
            applied = await device.set_cutting_height(args.height, args.map_id, args.zone_id)
        current_height = await device.refresh_cutting_height(args.map_id)
        zone_heights = await device.refresh_zone_cutting_heights(args.map_id)
        mode = device.mowing_preference_mode
        return {
            "ok": applied if applied is not None else current_height is not None,
            "command": args.command,
            "map_fetched_before": fetched_before,
            "requested_map_id": args.map_id,
            "requested_zone_id": args.zone_id,
            "requested_height_cm": args.height,
            "cutting_height_cm": current_height,
            "zone_cutting_heights_cm": zone_heights,
            "mowing_preference_mode": mode.name.lower() if mode is not None else None,
            "state": build_device_snapshot(device),
        }

    if args.command == "pause":
        success = await device.pause()
        return {"ok": success, "command": args.command, "state": build_device_snapshot(device)}

    if args.command == "dock":
        success = await device.return_to_dock()
        return {"ok": success, "command": args.command, "state": build_device_snapshot(device)}

    raise RuntimeError(f"Unsupported command: {args.command}")


def _create_device(args: argparse.Namespace, creds: dict[str, str]) -> DreameMowerDevice:
    """Construct the production device wrapper for CLI use."""
    return DreameMowerDevice(
        device_id=creds["device_id"],
        username=creds["username"],
        password=creds["password"],
        account_type=creds["account_type"],
        country=creds["country"],
        hass_config_dir=args.hass_config_dir,
    )


async def async_main(args: argparse.Namespace) -> int:
    """Connect, run the command, optionally watch for post-command events, then disconnect."""
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s:%(name)s:%(message)s")
    creds = resolve_creds(args)
    device = _create_device(args, creds)
    recorder = EventRecorder()
    device.register_property_callback(recorder.handle)

    connected = await device.connect()
    if not connected:
        print(json.dumps({"ok": False, "error": "Failed to connect to device"}, indent=2))
        return 1

    try:
        result = await run_command(device, args)
        if args.watch_seconds > 0:
            await asyncio.sleep(args.watch_seconds)
        if recorder.events:
            result["events"] = recorder.events
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    finally:
        await device.disconnect()


def main() -> None:
    """Entrypoint for the device CLI."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(async_main(args)))
    except KeyboardInterrupt:
        _LOGGER.warning("Interrupted by user")
        raise SystemExit(130)


if __name__ == "__main__":
    main()