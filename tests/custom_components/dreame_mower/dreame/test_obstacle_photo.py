"""Tests for the boxes a photo of a recognised obstacle carries."""

from __future__ import annotations

import base64
import json

from custom_components.dreame_mower.dreame.obstacle_photo import obstacle_photo_boxes


def _jpeg(*comments: bytes) -> bytes:
    segments = b"".join(b"\xff\xfe" + (len(c) + 2).to_bytes(2, "big") + c for c in comments)
    app0 = b"\xff\xe0\x00\x04ab"
    return b"\xff\xd8" + app0 + segments + b"\xff\xda\x00\x02" + b"\xff\xfe\x00\x05zzz" + b"\xff\xd9"


def test_the_boxes_come_from_the_comment():
    boxes = {"d": [{"x": 10, "y": 20, "w": 30, "h": 40}, {"x": "bad"}]}
    photo = _jpeg(base64.b64encode(json.dumps(boxes).encode()))

    assert obstacle_photo_boxes(photo) == {"boxes": [{"x": 10, "y": 20, "w": 30, "h": 40}], "width": 640, "height": 360}


def test_a_photo_without_boxes_has_none():
    assert obstacle_photo_boxes(_jpeg(b"not base64 json"))["boxes"] == []
    assert obstacle_photo_boxes(b"not a jpeg")["boxes"] == []
