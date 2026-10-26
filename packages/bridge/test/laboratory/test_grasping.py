"""
Measuring the gripper's pads against the glass they hold.
"""

from __future__ import annotations

import numpy as np
import pytest

from cramera_bridge.laboratory.grasping import PadContact
from cramera_bridge.laboratory.workflow import LaboratoryWorkflowDemo
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix, Pose


@pytest.fixture(scope="module")
def held_vessel(laboratory_bundle):
    """
    :return: The world, the robot and a vessel hanging from the left gripper's tool
        frame where the demo's grasp holds it, the fingers closed on it as a pickup
        leaves them.
    """
    demo = LaboratoryWorkflowDemo.at_the_bench(laboratory_bundle)
    context = demo.build_context(demo.build_world())
    world, robot = context.world, context.robot
    tool = robot.left_arm.end_effector.tool_frame
    vessel = world.get_body_by_name(demo.handled()[0])
    grip = demo.top_grip
    vessel_T_tool = Pose.from_xyz_quaternion(
        0, 0, grip.height, *grip.orientation.to_np(), reference_frame=vessel
    ).to_np()
    vessel.parent_connection.origin = HomogeneousTransformationMatrix(
        tool.global_pose.to_np() @ np.linalg.inv(vessel_T_tool),
        reference_frame=world.root,
    )
    PadContact(world, robot.left_arm.end_effector, vessel).stop_position()
    world.move_branch(vessel, tool)
    return world, robot, vessel


def test_a_held_vessels_glass_clearances_do_not_depend_on_where_the_robot_faces(
    held_vessel,
):
    world, robot, vessel = held_vessel
    pads = PadContact(world, robot.left_arm.end_effector, vessel)
    before = pads.glass_clearances()
    assert pads.clearance <= before.smallest < pads.glass.radius
    held_at = vessel.global_pose.to_np()
    heading = next(
        dof for dof in robot.drive.active_dofs if dof.name.name.endswith("yaw")
    )
    world.state[heading.id].position += 0.002
    world.notify_state_change()
    after = pads.glass_clearances()
    assert not np.allclose(vessel.global_pose.to_np(), held_at, atol=1e-6)
    assert after.smallest == pytest.approx(before.smallest, abs=1e-9)
    assert after.largest == pytest.approx(before.largest, abs=1e-9)
