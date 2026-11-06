"""
Driving the PR2 between its stands at the bench, in simulation with collision avoidance.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cramera_bridge.laboratory.mobility import DriveAction
from cramera_bridge.laboratory.transfer import VesselTransferDemo
from cramera_bridge.performing import PlanPerformance
from cramph.data_types import LifeCycleValues
from krrood_spatial_math.spatial_types import Pose

STAND = (-0.22, -0.72, math.pi / 2)
"""
A stand at the bench's front edge, in front of the centrifuge.
"""


@pytest.fixture(scope="module")
def driven(laboratory_bundle):
    """
    :return: The context after the PR2 drove from its start to :data:`STAND`, the stand
        and the drive.
    """
    demo = VesselTransferDemo.at_the_bench(laboratory_bundle)
    context = demo.build_context(demo.build_world())
    x, y, heading = STAND
    target = Pose.from_xyz_rpy(x, y, yaw=heading, reference_frame=context.world.root)
    drive = DriveAction(target=target)
    PlanPerformance(collision_avoidance=True).perform(drive, context)
    return context, target, drive


def test_the_base_reaches_its_stand_at_the_bench_edge(driven):
    context, target, drive = driven
    assert drive.life_cycle_state is LifeCycleValues.SUCCEEDED
    np.testing.assert_allclose(
        context.robot.root.global_pose.to_np(), target.to_np(), atol=0.003
    )


def test_the_drive_is_locked_again_after_driving(driven):
    context, _, _ = driven
    assert not context.robot.drive.has_hardware_interface
