"""
Joint values recovered from the poses of a joint's bodies, and the motion a value makes.
"""

from __future__ import annotations

import numpy
import pytest
from scipy.spatial.transform import Rotation
from typing_extensions import Optional

from cramera_usd.geometry.transforms import FULL_TURN, RigidTransform, TransformTrack
from cramera_usd.scene.kinematics import AllowedMotion, Joint, JointKind

Z_AXIS = numpy.array([0.0, 0.0, 1.0])
"""
The axis of the test hinges.
"""

# %% helpers


def hinge(lower: Optional[float], upper: Optional[float]) -> Joint:
    """
    :param lower: The lowest angle in radians, or None.
    :param upper: The highest angle in radians, or None.
    :return: A hinge about Z between two bodies whose joint frames are their own.
    """
    kind = JointKind.REVOLUTE if lower is not None else JointKind.CONTINUOUS
    return Joint(
        name="Hinge",
        path="/World/Hinge",
        motion=AllowedMotion(kind, Z_AXIS, lower, upper),
    )


def turned(angle: float) -> RigidTransform:
    """
    :param angle: An angle in radians.
    :return: A body turned about Z.
    """
    return RigidTransform.from_rotation(
        Rotation.from_rotvec(Z_AXIS * angle).as_matrix()
    )


def turns(angles: numpy.ndarray) -> TransformTrack:
    """
    :param angles: Angles in radians.
    :return: One turn about Z per frame.
    """
    return TransformTrack.of_parts(
        Rotation.from_rotvec(numpy.outer(angles, Z_AXIS)).as_matrix(),
        numpy.zeros((len(angles), 3)),
    )


# %% values


def test_angle_past_half_a_turn_is_taken_within_the_limits():
    assert hinge(0.0, 4.0).value_between(RigidTransform(), turned(3.5)) == (
        pytest.approx(3.5)
    )


def test_angle_of_a_joint_without_limits_lies_within_half_a_turn():
    assert hinge(None, None).value_between(RigidTransform(), turned(3.5)) == (
        pytest.approx(3.5 - FULL_TURN)
    )


def test_one_value_and_a_track_of_values_agree():
    joint = hinge(0.0, 4.0)
    angles = numpy.array([0.5, 2.0, 3.5])
    assert joint.motion.values_of(turns(angles)) == pytest.approx(
        [joint.value_between(RigidTransform(), turned(angle)) for angle in angles]
    )


def test_angle_of_a_joint_turning_more_than_once_has_no_jumps():
    angles = numpy.radians(numpy.arange(0.0, 351.0, 50.0))
    joint = hinge(numpy.radians(-400.0), numpy.radians(400.0))
    assert joint.motion.values_of(turns(angles)) == pytest.approx(angles)


def test_motion_at_a_value_turns_the_child_about_the_axis():
    assert hinge(0.0, 4.0).motion.transform(3.5).is_close(turned(3.5))


def test_slide_value_is_the_distance_along_its_axis():
    motion = AllowedMotion(JointKind.PRISMATIC, numpy.array([1.0, 0.0, 0.0]))
    distance = 0.25
    moved = motion.transforms(numpy.array([distance]))
    assert motion.values_of(moved) == pytest.approx([distance])


def test_fixed_joint_stays_at_zero():
    motion = AllowedMotion(JointKind.FIXED)
    assert motion.values_of(turns(numpy.array([1.0]))).tolist() == [0.0]
    assert motion.transform(1.0).is_close(RigidTransform())


def test_reversed_motion_turns_the_other_way():
    motion = hinge(0.0, 1.0).motion
    assert motion.reversed().transform(0.5).is_close(turned(-0.5))
