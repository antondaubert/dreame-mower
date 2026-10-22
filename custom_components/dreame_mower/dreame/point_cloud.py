"""3D maps: the LiDAR point clouds the mower keeps for its maps.

The mower lists them on 2:50 with ``{"m": "g", "t": "OBJ", "d": {"type": "3dmap"}}``:
one cloud file name per map, by map index. The files carry a ``.bin`` name but
hold a PCD 0.7 point cloud (``x y z rgb``) that the cloud signs for download
like any other device file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

POINT_CLOUD_OBJECT_TYPE = "3dmap"
# A cloud of a large garden is a few megabytes; refuse anything far beyond.
POINT_CLOUD_MAX_BYTES = 64 * 1024 * 1024

_DATA_LINE = re.compile(rb"^DATA (\w+)\r?\n", re.MULTILINE)


class PointCloudError(Exception):
    """The downloaded file is not a point cloud the card can draw."""


def build_point_cloud_list_payload() -> dict[str, Any]:
    """Build the 2:50 getter payload that lists the stored point clouds."""
    return {"m": "g", "t": "OBJ", "d": {"type": POINT_CLOUD_OBJECT_TYPE}}


def point_cloud_names(result: Any) -> list[str | None]:
    """Return the cloud file name of each map index from an OBJ response.

    An empty or missing entry means that map has no stored cloud.
    """
    outputs = result.get("out") if isinstance(result, Mapping) else None
    if not isinstance(outputs, Sequence) or not outputs:
        return []
    first = outputs[0]
    data = first.get("d") if isinstance(first, Mapping) else None
    names = data.get("name") if isinstance(data, Mapping) else None
    if not isinstance(names, Sequence) or isinstance(names, (str, bytes)):
        return []
    return [name.strip() if isinstance(name, str) and name.strip() else None for name in names]


def validate_point_cloud(data: bytes) -> int:
    """Check that ``data`` is a complete PCD file and return its point count."""
    match = _DATA_LINE.search(data, 0, 4096)
    if match is None:
        raise PointCloudError("no PCD header")
    fields: dict[str, list[str]] = {}
    for line in data[: match.start()].decode("latin-1").splitlines():
        key, *values = line.split()
        if key and not key.startswith("#"):
            fields[key] = values
    names = fields.get("FIELDS", [])
    if not {"x", "y", "z"} <= set(names):
        raise PointCloudError("no x y z fields")
    try:
        points = int((fields.get("POINTS") or fields.get("WIDTH") or ["0"])[0])
        sizes = [int(size) for size in fields.get("SIZE", [])]
        counts = [int(count) for count in fields.get("COUNT", ["1"] * len(names))]
    except ValueError as ex:
        raise PointCloudError(f"bad header: {ex}") from ex
    mode = match.group(1).decode("ascii")
    if mode == "binary":
        if len(sizes) != len(names) or len(counts) != len(names):
            raise PointCloudError("SIZE or COUNT does not match FIELDS")
        stride = sum(size * count for size, count in zip(sizes, counts))
        if match.end() + stride * points > len(data):
            raise PointCloudError("truncated file")
    elif mode != "ascii":
        raise PointCloudError(f"unsupported PCD data {mode!r}")
    if points <= 0:
        raise PointCloudError("no points")
    return points
