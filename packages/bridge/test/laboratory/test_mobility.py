"""
Driving the PR2 between its stands at the bench, in simulation with collision avoidance.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from coraplex.datastructures.enums import ExecutionType
from coraplex.execution_environment import ExecutionEnvironment
from coraplex.plans.factories import sequential
from cramera_bridge.laboratory.mobility import DriveAction
from cramera_bridge.laboratory.transfer import VesselTransferDemo
from semantic_digital_twin.spatial_types import Pose

STAND = (-0.22, -0.72, math.pi / 2)
"""
A stand at the bench's front edge, in front of the centrifuge.
"""


@pytest.fixture(scope="module")
def driven(laboratory_bundle):
    """
    :return: The context after the PR2 drove from its start to :data:`STAND`.
    """
    demo = VesselTransferDemo.at_the_bench(laboratory_bundle)
    context = demo.build_context(demo.build_world())
    x, y, heading = STAND
    target = Pose.from_xyz_rpy(x, y, yaw=heading, reference_frame=context.world.root)
    plan = sequential([DriveAction(target)], context=context).plan
    with ExecutionEnvironment(
        execution_type=ExecutionType.KINEMATICALLY_SIMULATED, collision_avoidance=True
    ):
        plan.perform()
    return context, target


def test_the_base_reaches_its_stand_at_the_bench_edge(driven):
    context, target = driven
    np.testing.assert_allclose(
        context.robot.root.global_pose.to_np(), target.to_np(), atol=0.003
    )


def test_the_drive_is_locked_again_after_driving(driven):
    context, _ = driven
    assert not context.robot.drive.has_hardware_interface
