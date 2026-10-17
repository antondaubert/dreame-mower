"""The boxes a photo of a recognised obstacle marks around what was seen.

The mower writes them into the JPEG's comment segment as base64 encoded JSON:
{"d": [{"x", "y", "w", "h"}, ...]}, in pixels of a frame of PHOTO_WIDTH by
PHOTO_HEIGHT.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

PHOTO_WIDTH = 640
PHOTO_HEIGHT = 360

_MARKER = 0xFF
_START_OF_IMAGE = 0xD8
_START_OF_SCAN = 0xDA
_COMMENT = 0xFE


def _comments(photo: bytes) -> list[bytes]:
    """The comment segments of a JPEG, read up to where the image data starts."""
    comments: list[bytes] = []
    if len(photo) < 4 or photo[0] != _MARKER or photo[1] != _START_OF_IMAGE:
        return comments
    position = 2
    while position + 4 <= len(photo):
        if photo[position] != _MARKER:
            break
        marker = photo[position + 1]
        if marker == _MARKER:
            position += 1
            continue
        if marker == _START_OF_SCAN:
            break
        length = int.from_bytes(photo[position + 2 : position + 4], "big")
        if length < 2:
            break
        if marker == _COMMENT:
            comments.append(photo[position + 4 : position + 2 + length])
        position += 2 + length
    return comments


def obstacle_photo_boxes(photo: bytes) -> dict[str, Any]:
    """The boxes around what was recognised, and the frame they are given in."""
    boxes: list[dict[str, int]] = []
    for comment in _comments(photo):
        try:
            data = json.loads(base64.b64decode(comment.strip(), validate=False))
        except (ValueError, binascii.Error):
            continue
        entries = data.get("d") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            continue
        for entry in entries:
            try:
                boxes.append({key: int(entry[key]) for key in ("x", "y", "w", "h")})
            except (KeyError, TypeError, ValueError):
                continue
    return {"boxes": boxes, "width": PHOTO_WIDTH, "height": PHOTO_HEIGHT}
