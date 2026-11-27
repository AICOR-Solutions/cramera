"""
Build the current CRAM transfer without executing robot motion.
"""

import pytest
import numpy as np

from coraplex.robot_plans.actions.base import Action
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from coraplex.robot_plans.actions.core.placing import PlaceAction
from cramera_bridge.laboratory.grasping import (
    PadContactAction,
    PadContactGoal,
    VesselReachAction,
    tool_goal_of,
)
from cramera_bridge.laboratory.transfer import VesselTransferDemo
from cramera_bridge.exceptions import TaskFailed
from cramph.data_types import LifeCycleValues
from cramph.world_modification_nodes import MoveBranch
from giskardpy.motion_statechart.goals.gripper import MoveFingers
from krrood_spatial_math.spatial_types import Pose


@pytest.fixture(scope="module")
def transfer_plan(laboratory_bundle, expand):
    """
    :return: The transfer and the statechart its expanded plan joined, at the authored
        start state.
    """
    demo = VesselTransferDemo.at_the_bench(laboratory_bundle)
    context = demo.build_context(demo.build_world())
    statechart = expand(demo.build_plan(context), context)
    return demo, statechart


def test_the_transfer_picks_and_places_the_same_vessel(transfer_plan):
    demo, statechart = transfer_plan
    [pickup] = statechart.get_nodes_by_type(PickUpAction)
    [placing] = statechart.get_nodes_by_type(PlaceAction)
    assert pickup.grasp.graspable.root is demo.observation.body
    assert placing.object_designator.root is demo.observation.body
    assert pickup.arm is demo.observation.context.robot.left_arm
    assert not demo.observation.context.robot.drive.has_hardware_interface


def test_the_finger_stop_is_found_after_the_approach_then_the_vessel_attached(
    transfer_plan,
):
    demo, statechart = transfer_plan
    [pickup] = statechart.get_nodes_by_type(PickUpAction)
    reach, closing, attach, _ = pickup.nodes
    assert isinstance(reach, VesselReachAction)
    first, opening, final = reach.nodes
    assert tool_goal_of(first).tip_link is pickup.arm.end_effector.tool_frame
    assert isinstance(opening, MoveFingers)
    assert tool_goal_of(final).tip_link is pickup.arm.end_effector.tool_frame
    assert isinstance(closing, PadContactAction)
    assert closing.object_designator is demo.observation.body
    [contact] = statechart.get_nodes_by_type(PadContactGoal)
    assert contact.parent_node is closing
    assert contact.goal is None and not contact.nodes
    assert isinstance(attach, MoveBranch)
    assert attach.branch_root is demo.observation.body
    assert (
        attach.new_parent
        is demo.observation.context.robot.left_arm.end_effector.tool_frame
    )


def test_the_grasp_candidate_preserves_the_calibrated_tool_pose(transfer_plan):
    demo, statechart = transfer_plan
    [reach] = statechart.get_nodes_by_type(VesselReachAction)
    approach, grasp = [
        tool_goal_of(step).goal_pose for step in (reach.nodes[0], reach.nodes[-1])
    ]
    expected = Pose.from_xyz_quaternion(
        0,
        0,
        demo.laboratory.vessels.grasp_height,
        *demo.tool_orientation.to_np(),
        reference_frame=demo.observation.body,
    )
    np.testing.assert_allclose(grasp.to_np(), expected.to_np(), atol=1e-12)
    expected_approach = expected.to_np().copy()
    expected_approach[:3, 3] -= (
        demo.laboratory.vessels.outer_radius + demo.approach_margin
    ) * expected_approach[:3, 0]
    np.testing.assert_allclose(approach.to_np(), expected_approach, atol=1e-12)
    [pickup] = statechart.get_nodes_by_type(PickUpAction)
    poses = pickup.grasp_pose_sequence(
        pickup.grasp.grasp_pose, pickup.arm.end_effector, pickup.grasp
    )
    np.testing.assert_allclose(
        poses.retreat.to_np()[:3, 3] - poses.grasp.to_np()[:3, 3],
        [0, 0, demo.lift],
        atol=1e-12,
    )


def test_an_unexecuted_plan_is_not_accepted(transfer_plan):
    demo, _ = transfer_plan
    with pytest.raises(TaskFailed):
        demo.require_success(demo.observation.context)


@pytest.mark.parametrize(
    "status", [LifeCycleValues.NOT_STARTED, LifeCycleValues.FAILED]
)
def test_one_unfinished_action_refuses_the_transfers_success(transfer_plan, status):
    demo, statechart = transfer_plan
    actions = statechart.get_nodes_by_type(Action)
    assert actions
    try:
        for action in actions:
            statechart.life_cycle_state[action] = LifeCycleValues.SUCCEEDED
        demo.require_success(demo.observation.context)
        statechart.life_cycle_state[actions[-1]] = status
        with pytest.raises(TaskFailed):
            demo.require_success(demo.observation.context)
    finally:
        for action in actions:
            statechart.life_cycle_state[action] = LifeCycleValues.NOT_STARTED


def test_a_plan_that_joined_no_statechart_refuses_success(transfer_plan):
    demo, _ = transfer_plan
    unexpanded = VesselTransferDemo.at_the_bench(demo.laboratory.directory)
    unexpanded.build_plan(demo.observation.context)
    with pytest.raises(TaskFailed):
        unexpanded.require_success(demo.observation.context)
