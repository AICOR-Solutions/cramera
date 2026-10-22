"""
Number arrays, boxes and floor rectangles.
"""

from __future__ import annotations

import pytest

from cramera_protocol.exceptions import InvalidDocumentValue
from cramera_protocol.geometry import (
    Bounds,
    FloorRectangle,
    Pose,
    RectangleKey,
    Vector3,
)


def test_a_pose_keeps_position_and_quaternion_order():
    pose = Pose.from_json([1, 2, 3, 0.1, 0.2, 0.3, 0.9])
    assert (pose.x, pose.y, pose.z) == (1.0, 2.0, 3.0)
    assert (pose.qx, pose.qy, pose.qz, pose.qw) == (0.1, 0.2, 0.3, 0.9)
    assert pose.to_json() == [1.0, 2.0, 3.0, 0.1, 0.2, 0.3, 0.9]


@pytest.mark.parametrize(
    "data", [[0, 0], [0, 0, 0, 0], [0, 0, "z"], [0, 0, True], "0 0 0", None]
)
def test_a_vector_needs_exactly_three_numbers(data):
    with pytest.raises(InvalidDocumentValue):
        Vector3.from_json(data)


def test_bounds_are_two_corners():
    bounds = Bounds.from_json([[-1, -2, 0], [1, 2, 3]])
    assert bounds.minimum == Vector3(-1.0, -2.0, 0.0)
    assert bounds.maximum == Vector3(1.0, 2.0, 3.0)
    assert bounds.to_json() == [[-1.0, -2.0, 0.0], [1.0, 2.0, 3.0]]


@pytest.mark.parametrize("data", [[[0, 0, 0]], {"min": [0, 0, 0]}, [[0, 0, 0], [1, 1]]])
def test_bounds_need_two_corners_of_three_numbers(data):
    with pytest.raises(InvalidDocumentValue):
        Bounds.from_json(data)


def test_a_floor_rectangle_round_trips():
    data = {
        RectangleKey.MIN_X: -1,
        RectangleKey.MAX_X: 1,
        RectangleKey.MIN_Y: -2,
        RectangleKey.MAX_Y: 2,
    }
    rectangle = FloorRectangle.from_json(data)
    assert (rectangle.min_x, rectangle.max_y) == (-1.0, 2.0)
    assert rectangle.to_json() == {key: float(value) for key, value in data.items()}
