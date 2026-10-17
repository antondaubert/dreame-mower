"""Pose and Coverage property handling for Dreame Mower Implementation.

This module provides parsing and handling for Service 1, Property 4 (1:4) which
contains robot pose (position and heading) encoded as 20-bit overlapping signed
values, mowing track deltas relative to the robot pose, and mowing progress data.

Payload structure (with 0xCE sentinel framing)::

    33-byte raw (full):  [CE] [pose:6] [trace:15] [task:10] [CE]
    44-byte raw (ext):   [CE] [pose:6] [trace1:15] [task:10] [trace2:11] [CE]
    22-byte raw:         [CE] [pose:6] [trace:15]
    13-byte raw:         [CE] [pose:6] [extra:5]
    11-byte raw (alt):   [task:10] [CE]  (no leading sentinel)

Pose encoding (6 bytes)::

    X = 20-bit signed from bytes 0-2 (byte 2 low nibble)
    Y = 20-bit signed from bytes 2-4 (byte 2 high nibble)
    Angle = byte 5 mapped to 0-360 degrees

Track encoding (11 or 15 bytes)::

    Bytes 0-2: 24-bit LE start index
    Then pairs of int16 LE (dx, dy) deltas from the robot pose.
    Sentinel: |dx| > 32766 AND |dy| > 32766 marks a segment break.

The track is the trail of the running session, one numbered point per turn.
Each message repeats the newest few points from the start index on, padding
the ones not reached yet with segment breaks, so the trail is kept by point
number: a later message fills in what an earlier one padded. The numbers start
again from zero with every session.

Robot coordinates are in "pose units".  Multiplying by 10 converts them to the
same unit system as the batch-API zone / M_PATH coordinates.
"""

from __future__ import annotations

import logging
import struct
from typing import Dict, Any, List

_LOGGER = logging.getLogger(__name__)

# Property name constants for notifications
POSE_COVERAGE_PROGRESS_PROPERTY_NAME = "mowing_progress"
POSE_COVERAGE_COORDINATES_PROPERTY_NAME = "mowing_coordinates"

# Progress data field constants
PROGRESS_CURRENT_AREA_FIELD = "current_area_sqm"
PROGRESS_TOTAL_AREA_FIELD = "total_area_sqm"
PROGRESS_PERCENT_FIELD = "progress_percent"

# Coordinates data field constants
COORDINATES_X_FIELD = "x"
COORDINATES_Y_FIELD = "y"
COORDINATES_SEGMENT_FIELD = "segment"
COORDINATES_HEADING_FIELD = "heading"

# Frame delimiter
SENTINEL_BYTE = 0xCE  # 206

# Pose units -> map units multiplier
_POSE_SCALE = 10

# Track delta sentinel threshold
_TRACK_SENTINEL_THRESHOLD = 32766

# Sentinel coordinate value used for segment breaks in track data
_SEGMENT_BREAK = 2147483647

# How far the track numbers may step back before they count as a new session.
# Within a session they only grow; a message may still repeat a few older ones.
_TRAIL_RESTART_MARGIN = 16

# The most trail points kept; the oldest go first. A long session on a large
# lawn stays well below this.
MAX_TRAIL_POINTS = 50000


def decode_pose_point(raw: bytes) -> tuple[int, int]:
    """Decode x and y of one five-byte point, packed like the pose (pose units)."""
    x, y, _angle = _parse_pose([*raw, 0], offset=0)
    return x, y


def _parse_pose(data: List[int], offset: int) -> tuple[int, int, float]:
    """Extract robot pose from 6 bytes using 20-bit overlapping encoding."""
    b0 = data[offset]
    b1 = data[offset + 1]
    b2 = data[offset + 2]
    b3 = data[offset + 3]
    b4 = data[offset + 4]
    b5 = data[offset + 5]

    # 20-bit signed X from b0, b1, low nibble of b2
    # JS: x = (b2 << 28 | b1 << 20 | b0 << 12) >> 12
    raw_x = (b2 << 28) | (b1 << 20) | (b0 << 12)
    raw_x &= 0xFFFFFFFF  # constrain to 32-bit unsigned
    if raw_x & 0x80000000:
        raw_x -= 0x100000000  # convert to signed
    x = raw_x >> 12

    # 20-bit signed Y from high nibble of b2, b3, b4
    # JS: y = (b4 << 24 | b3 << 16 | b2 << 8) >> 12
    raw_y = (b4 << 24) | (b3 << 16) | (b2 << 8)
    raw_y &= 0xFFFFFFFF
    if raw_y & 0x80000000:
        raw_y -= 0x100000000
    y = raw_y >> 12

    angle = b5 / 255.0 * 360.0

    return x, y, angle


def _parse_track_deltas(
    data: List[int],
    offset: int,
    length: int,
    base_x: int,
    base_y: int,
) -> tuple[int, list[list[int]]]:
    """Extract track points from a trace chunk.

    Args:
        data: Raw byte list (full message including sentinels).
        offset: Start offset of the trace chunk within data.
        length: Number of bytes in the trace chunk.
        base_x: Robot X in map units (pose_x * _POSE_SCALE).
        base_y: Robot Y in map units (pose_y * _POSE_SCALE).

    Returns:
        (start_index, points) where points is a list of [x, y] in map units.
        Segment-break sentinels are represented as [_SEGMENT_BREAK, _SEGMENT_BREAK].
    """
    if length < 7:
        return 0, []

    # 24-bit LE start index
    start_index = data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16)

    num_pairs = (length - 3) // 4
    points: list[list[int]] = []

    for i in range(num_pairs):
        pair_off = offset + 3 + i * 4
        dx = struct.unpack_from("<h", bytes(data[pair_off : pair_off + 2]))[0]
        dy = struct.unpack_from("<h", bytes(data[pair_off + 2 : pair_off + 4]))[0]

        if abs(dx) > _TRACK_SENTINEL_THRESHOLD and abs(dy) > _TRACK_SENTINEL_THRESHOLD:
            points.append([_SEGMENT_BREAK, _SEGMENT_BREAK])
        else:
            # Deltas are relative to the *unscaled* pose.  base_x/base_y are already
            # pose * _POSE_SCALE, so scale deltas by the same factor.
            points.append([base_x + dx * _POSE_SCALE, base_y + dy * _POSE_SCALE])

    return start_index, points


def _parse_task(data: List[int], offset: int) -> dict[str, Any]:
    """Extract mowing task/progress from 10 bytes.

    Layout (relative to offset)::

        [0] region_id  [1] task_id
        [2:4] percent (uint16 LE, value * 100, range 0–10000)
        [4:7] total area (uint24 LE, centi-sqm)
        [7:10] finished area (uint24 LE, centi-sqm)
    """
    region_id = data[offset]
    task_id = data[offset + 1]
    raw_percent = data[offset + 2] | (data[offset + 3] << 8)
    total = data[offset + 4] | (data[offset + 5] << 8) | (data[offset + 6] << 16)
    finish = data[offset + 7] | (data[offset + 8] << 8) | (data[offset + 9] << 16)

    total_sqm = total / 100.0 if total else 0.0
    finish_sqm = finish / 100.0 if finish else 0.0
    progress = min(100.0, raw_percent / 100.0) if raw_percent else 0.0

    return {
        "region_id": region_id,
        "task_id": task_id,
        "current_area_sqm": finish_sqm,
        "total_area_sqm": total_sqm,
        "progress_percent": progress,
    }


class PoseCoverageHandler:
    """Handler for pose and coverage telemetry property (1:4)."""
    
    def __init__(self) -> None:
        """Initialize pose coverage handler."""
        # Progress tracking
        self._current_area_sqm: float | None = None
        self._total_area_sqm: float | None = None
        self._progress_percent: float | None = None
        self._mission_completed: bool = False
        
        # Robot pose (in map units = pose * _POSE_SCALE)
        self._x_coordinate: int | None = None
        self._y_coordinate: int | None = None
        self._heading: float | None = None
        self._segment: int | None = None

        # Newly accumulated track points (list of [x, y] in map units)
        self._new_track_points: list[list[int]] = []
        # The session's trail by point number, and how often it changed.
        self._trail: dict[int, list[int]] = {}
        self._trail_last_index = -1
        self._trail_revision = 0
    
    def parse_value(self, value: Any) -> bool:
        """Parse pose coverage value from the raw IoT property byte array.

        Handles multiple payload lengths as observed across device firmware
        versions.
        """
        try:
            if not isinstance(value, list):
                _LOGGER.warning("Invalid pose coverage value type: %s", type(value))
                return False
            
            n = len(value)
            if n < 8:
                _LOGGER.warning("Pose coverage payload too short: %d bytes", n)
                return False

            # Clear new track points for this update
            self._new_track_points = []

            # Dispatch based on framing:
            #   payload[0] != 0xCE AND payload[-1] == 0xCE -> alt format (task only)
            #   payload[0] == 0xCE AND payload[-1] == 0xCE -> standard sentinel-framed
            if value[0] != SENTINEL_BYTE and value[-1] == SENTINEL_BYTE:
                return self._parse_alt_format(value)

            if value[0] != SENTINEL_BYTE or value[-1] != SENTINEL_BYTE:
                _LOGGER.warning(
                    "Invalid sentinel bytes: start=0x%02X, end=0x%02X",
                    value[0], value[-1],
                )
                return False

            if n == 33:
                # [CE] pose(6) trace(15) task(10) [CE]
                return self._parse_full_format(value)
            elif n == 44:
                # [CE] pose(6) trace1(15) task(10) trace2(11) [CE]
                return self._parse_extended_format(value)
            elif n == 22:
                # [CE] pose(6) trace(15)
                return self._parse_pose_trace_format(value)
            elif n in (13, 8):
                # [CE] pose(6) extra(5), or [CE] pose(6) [CE]: the pose alone,
                # as the mower reports it while it drives without mowing.
                return self._parse_pose_short_format(value)
            else:
                _LOGGER.debug("Unrecognised pose coverage payload length: %d", n)
                return self._parse_fallback(value)

        except Exception as ex:
            _LOGGER.error("Failed to parse pose coverage data: %s", ex)
            return False
    
    # ------------------------------------------------------------------
    # Notification data accessors
    # ------------------------------------------------------------------

    def get_progress_notification_data(self) -> Dict[str, Any]:
        """Get progress notification data for Home Assistant."""
        return {
            PROGRESS_CURRENT_AREA_FIELD: self._current_area_sqm,
            PROGRESS_TOTAL_AREA_FIELD: self._total_area_sqm,
            PROGRESS_PERCENT_FIELD: self._progress_percent,
        }
    
    def get_coordinates_notification_data(self) -> Dict[str, Any]:
        """Get coordinates notification data for Home Assistant.

        The returned dict includes a ``track_points`` key with any newly
        extracted track points from this parse cycle (list of [x, y] in map units).
        """
        return {
            COORDINATES_X_FIELD: self._x_coordinate,
            COORDINATES_Y_FIELD: self._y_coordinate,
            COORDINATES_SEGMENT_FIELD: self._segment,
            COORDINATES_HEADING_FIELD: self._heading,
            "track_points": self._new_track_points,
        }
    
    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_area_sqm(self) -> float | None:
        return self._current_area_sqm
    
    @property
    def total_area_sqm(self) -> float | None:
        return self._total_area_sqm
    
    @property
    def progress_percent(self) -> float | None:
        return self._progress_percent
    
    @property
    def x_coordinate(self) -> int | None:
        return self._x_coordinate
    
    @property
    def y_coordinate(self) -> int | None:
        return self._y_coordinate
    
    @property
    def segment(self) -> int | None:
        return self._segment
    
    @property
    def heading(self) -> float | None:
        return self._heading
    
    @property
    def path_history(self) -> list[list[int]]:
        """Return the session's trail in order, [x, y] in map units.

        A segment break is a point with both coordinates set to the break
        sentinel. Breaks the device used as padding past the newest point are
        left out.
        """
        # One copy first: the trail grows on the thread the reports arrive on.
        points = [point for _index, point in sorted(list(self._trail.items()))]
        while points and points[-1][0] == _SEGMENT_BREAK:
            points.pop()
        return points

    def set_position(self, x_raw: int, y_raw: int, angle: float) -> None:
        """Take the mower's position as read from it, in pose units and degrees."""
        self._new_track_points = []
        self._apply_pose(x_raw, y_raw, angle)

    def first_missing_trail_index(self) -> int | None:
        """Return the first point number the trail lacks, or None when it has them all.

        An empty trail lacks its very first point.
        """
        known = list(self._trail)
        if not known:
            return 0
        present = set(known)
        for index in range(max(known) + 1):
            if index not in present:
                return index
        return None

    def merge_trail(self, start_index: int, points: list[tuple[int, int]]) -> bool:
        """Take in a stretch of the session's trail read back from the mower.

        `points` are numbered on from `start_index` in pose units, a segment
        break being a point with both coordinates out of range. They fill in
        or replace what the trail holds under the same numbers; a break never
        replaces a known point. Returns True when the trail changed.
        """
        changed = False
        for offset, (x, y) in enumerate(points):
            index = start_index + offset
            if abs(x) > _TRACK_SENTINEL_THRESHOLD and abs(y) > _TRACK_SENTINEL_THRESHOLD:
                if index in self._trail:
                    continue
                point = [_SEGMENT_BREAK, _SEGMENT_BREAK]
            else:
                point = [x * _POSE_SCALE, y * _POSE_SCALE]
            if self._trail.get(index) != point:
                self._trail[index] = point
                changed = True
        if points:
            self._trail_last_index = max(self._trail_last_index, start_index + len(points) - 1)
        if changed:
            self._trail_revision += 1
        return changed

    @property
    def trail_revision(self) -> int:
        """Return a number that changes whenever the trail changed."""
        return self._trail_revision

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def clear_path_history(self) -> None:
        """Clear the path history (e.g., when a new mowing session starts)."""
        self._trail.clear()
        self._trail_last_index = -1
        self._trail_revision += 1
        _LOGGER.debug("Path history cleared")
    
    def mark_mission_completed(self) -> None:
        """Mark the current mission as completed.
        
        Caps progress at 100% even if the calculated value is slightly less.
        """
        self._mission_completed = True
        if self._progress_percent is not None and self._progress_percent > 0:
            self._progress_percent = 100.0
        _LOGGER.debug("Mission marked as completed, progress set to 100%%")
    
    def reset_mission_completion(self) -> None:
        """Reset the mission completion flag for a new mission."""
        self._mission_completed = False
        _LOGGER.debug("Mission completion flag reset")

    # ------------------------------------------------------------------
    # Private: apply parsed data
    # ------------------------------------------------------------------

    def _apply_pose(self, x_raw: int, y_raw: int, angle: float) -> tuple[int, int]:
        """Scale raw pose to map units and store."""
        mx = x_raw * _POSE_SCALE
        my = y_raw * _POSE_SCALE
        self._x_coordinate = mx
        self._y_coordinate = my
        self._heading = round(angle, 2)
        return mx, my

    def _apply_task(self, task: dict[str, Any]) -> None:
        """Store task/progress data."""
        self._current_area_sqm = task["current_area_sqm"]
        self._total_area_sqm = task["total_area_sqm"]
        self._progress_percent = task["progress_percent"]
        self._segment = task.get("region_id")
        if self._mission_completed and self._progress_percent and self._progress_percent > 0:
            self._progress_percent = 100.0

    def _apply_track(self, start_index: int, points: list[list[int]]) -> None:
        """Store track points by their number in the session's trail."""
        if not points:
            return
        self._new_track_points.extend(points)
        if start_index < self._trail_last_index - _TRAIL_RESTART_MARGIN:
            # The numbers started over: this is the next session's trail.
            self._trail.clear()
            self._trail_last_index = -1
        self._trail_last_index = max(self._trail_last_index, start_index + len(points) - 1)
        changed = False
        for offset, point in enumerate(points):
            index = start_index + offset
            if point[0] == _SEGMENT_BREAK and index in self._trail:
                # Padding never replaces a point that is already known.
                continue
            if self._trail.get(index) != point:
                self._trail[index] = point
                changed = True
        if len(self._trail) > MAX_TRAIL_POINTS:
            # Trim a tenth at once, so this sort runs only now and then.
            keep = MAX_TRAIL_POINTS - MAX_TRAIL_POINTS // 10
            for index in sorted(self._trail)[: len(self._trail) - keep]:
                del self._trail[index]
        if changed:
            self._trail_revision += 1

    # ------------------------------------------------------------------
    # Private: format handlers
    # ------------------------------------------------------------------

    def _parse_full_format(self, raw: List[int]) -> bool:
        """33 raw bytes: [CE] pose(6) trace(15) task(10) [CE]."""
        x, y, angle = _parse_pose(raw, offset=1)
        mx, my = self._apply_pose(x, y, angle)

        idx, pts = _parse_track_deltas(raw, offset=7, length=15, base_x=mx, base_y=my)
        self._apply_track(idx, pts)

        task = _parse_task(raw, offset=22)
        self._apply_task(task)
        return True

    def _parse_extended_format(self, raw: List[int]) -> bool:
        """44 raw bytes: [CE] pose(6) trace1(15) task(10) trace2(11) [CE]."""
        x, y, angle = _parse_pose(raw, offset=1)
        mx, my = self._apply_pose(x, y, angle)

        idx1, pts1 = _parse_track_deltas(raw, offset=7, length=15, base_x=mx, base_y=my)
        self._apply_track(idx1, pts1)

        task = _parse_task(raw, offset=22)
        self._apply_task(task)

        idx2, pts2 = _parse_track_deltas(raw, offset=32, length=11, base_x=mx, base_y=my)
        self._apply_track(idx2, pts2)
        return True

    def _parse_pose_trace_format(self, raw: List[int]) -> bool:
        """22 raw bytes: [CE] pose(6) trace(15)."""
        x, y, angle = _parse_pose(raw, offset=1)
        mx, my = self._apply_pose(x, y, angle)

        idx, pts = _parse_track_deltas(raw, offset=7, length=15, base_x=mx, base_y=my)
        self._apply_track(idx, pts)
        return True

    def _parse_pose_short_format(self, raw: List[int]) -> bool:
        """13 or 8 raw bytes: [CE] pose(6) and maybe extra(5) — pose only."""
        x, y, angle = _parse_pose(raw, offset=1)
        self._apply_pose(x, y, angle)
        return True

    def _parse_alt_format(self, raw: List[int]) -> bool:
        """11/22 raw bytes without leading sentinel: task(10) [CE] [+ trace]."""
        if len(raw) >= 11:
            task = _parse_task(raw, offset=0)
            self._apply_task(task)
        return True

    def _parse_fallback(self, raw: List[int]) -> bool:
        """Best-effort: try to extract at least the pose."""
        if len(raw) >= 8:  # sentinel + 6 pose bytes + sentinel minimum
            x, y, angle = _parse_pose(raw, offset=1)
            self._apply_pose(x, y, angle)
            return True
        return False
