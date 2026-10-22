"""
The workshop's grasps: a screw is grasped the same way however far it rolled about its
shaft, the screwdriver along its handle, the screw box by its carry bar.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from coraplex.datastructures.enums import ApproachDirection, VerticalAlignment
from cramera_workshop.robot.grasps import (
    BoxHandleGrasp,
    DriverGrasp,
    ScrewGrasp,
    ShaftFrame,
)
from cramera_workshop.robot.world import WorkshopBody
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix, Pose

ROLL = 0.7
"""
How far a test screw rolled about its shaft, in radians.
"""


def lying_screw(roll: float) -> np.ndarray:
    """
    :param roll: The screw's roll about its shaft.
    :return: A screw lying along the world's x axis, rolled.
    """
    return (
        HomogeneousTransformationMatrix.from_xyz_rpy(1.0, 0.0, 1.0, pitch=math.pi / 2)
        @ HomogeneousTransformationMatrix.from_xyz_rpy(yaw=roll)
    ).to_np()


def test_the_shaft_frame_does_not_depend_on_the_roll():
    unrolled = ShaftFrame(lying_screw(0.0)).matrix()
    rolled = ShaftFrame(lying_screw(ROLL)).matrix()
    np.testing.assert_allclose(rolled, unrolled, atol=1e-12)
    np.testing.assert_allclose(unrolled, lying_screw(0.0), atol=1e-12)


def test_an_upright_screw_keeps_its_own_frame():
    upright = HomogeneousTransformationMatrix.from_xyz_rpy(z=1.0, yaw=ROLL).to_np()
    np.testing.assert_allclose(ShaftFrame(upright).matrix(), upright)


def grasp_of(grasp_class, context, hand, **fields):
    return grasp_class(
        ApproachDirection.FRONT, VerticalAlignment.NoAlignment, hand, **fields
    )


def test_a_screw_is_approached_and_lifted_straight_down_and_up(assembly_context):
    hand = assembly_context.robot.left_arm.end_effector
    grasp = grasp_of(ScrewGrasp, assembly_context, hand, manipulation_offset=0.12)
    screw = assembly_context.world.get_body_by_name(WorkshopBody.SCREW)
    before, at, after = (pose.to_np() for pose in grasp.grasp_pose_sequence(screw))
    np.testing.assert_allclose(before[:3, 3] - at[:3, 3], [0, 0, 0.12], atol=1e-9)
    np.testing.assert_allclose(after, before)
    reversed_sequence = grasp.pose_sequence(
        Pose(reference_frame=screw), screw, reverse=True
    )
    np.testing.assert_allclose(reversed_sequence[1].to_np(), at)


def test_the_screwdriver_is_grasped_along_its_handle(assembly_context):
    hand = assembly_context.robot.right_arm.end_effector
    grasp = grasp_of(DriverGrasp, assembly_context, hand)
    driver = assembly_context.world.get_body_by_name(WorkshopBody.DRIVER)
    before, at, after = (pose.to_np() for pose in grasp.grasp_pose_sequence(driver))
    np.testing.assert_allclose(
        np.linalg.norm(before[:3, 3] - at[:3, 3]), grasp.approach_clearance, atol=1e-9
    )
    assert after[2, 3] == pytest.approx(at[2, 3] + grasp.lift)


def test_the_box_is_grasped_by_its_carry_bar(assembly_context):
    hand = assembly_context.robot.left_arm.end_effector
    grasp = grasp_of(BoxHandleGrasp, assembly_context, hand)
    box = assembly_context.world.get_body_by_name(WorkshopBody.SCREW_BOX)
    before, at, after = (pose.to_np() for pose in grasp.grasp_pose_sequence(box))
    assert at[1, 3] - before[1, 3] == pytest.approx(grasp.withdrawal)
    assert after[2, 3] - at[2, 3] == pytest.approx(grasp.lift)
