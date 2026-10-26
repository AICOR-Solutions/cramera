"""
Build the PR2 laboratory workflow's plan without executing robot motion.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from coraplex.datastructures.enums import MovementType
from coraplex.plans.plan_node import MotionNode
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from coraplex.robot_plans.actions.core.placing import PlaceAction
from coraplex.robot_plans.motions.gripper import (
    MoveGripperMotion,
    MoveToolCenterPointMotion,
)
from cramera_bridge.exceptions import TaskFailed
from cramera_bridge.laboratory.grasping import (
    HeldToolGripperMotion,
    PadContactMotion,
)
from giskardpy.motion_statechart.tasks.cartesian_tasks import HoldPose
from cramera_bridge.laboratory.mobility import (
    DriveAction,
    DriveControlNode,
    MechanismMotion,
)
from cramera_bridge.laboratory.workflow import LaboratoryWorkflowDemo, Station


@pytest.fixture(scope="module")
def workflow_plan(laboratory_bundle):
    """
    :return: The workflow and its expanded native plan at the authored start state.
    """
    demo = LaboratoryWorkflowDemo.at_the_bench(laboratory_bundle)
    context = demo.build_context(demo.build_world())
    plan = demo.build_plan(context)
    plan.root.notify()
    return demo, context, plan


def leaves(node):
    """
    :param node: A plan node.
    :return: The node's leaves in execution order.
    """
    if not node.children:
        yield node
    for child in node.children:
        yield from leaves(child)


def tool_motions(node):
    """
    :param node: A plan node.
    :return: The tool motions below the node, in execution order.
    """
    return [
        leaf.designator
        for leaf in leaves(node)
        if isinstance(leaf, MotionNode)
        and isinstance(leaf.designator, MoveToolCenterPointMotion)
    ]


def expected_placements(demo, context):
    """
    :return: The vessel each placing of the workflow sets down, where its bottom ends
        and the station it ends at, from the bench's starting slots and the workflow's
        moves.
    """
    world = context.world
    occupied = {
        placement.slot: placement.key for placement in demo.laboratory.bench.tubes
    }
    placements = []
    for move in demo.moves:
        key = occupied.pop(move.source)
        if move.target.station is Station.RACK:
            occupied[move.target.identifier] = key
        placements.append(
            (key, move.target.pose(demo.laboratory, world), move.target.station)
        )
    return placements


def test_every_vessel_is_set_down_where_the_workflow_takes_it(workflow_plan):
    demo, context, plan = workflow_plan
    world = context.world
    placings = plan.get_nodes_by_designator_type(PlaceAction)
    expected = expected_placements(demo, context)
    assert [node.designator.object_designator.root.name.name for node in placings] == [
        key for key, _, _ in expected
    ]
    for node, (_, target, _) in zip(placings, expected):
        np.testing.assert_allclose(
            world.transform(
                node.designator.target_location.homogeneous_matrix, world.root
            ).to_np(),
            world.transform(target.homogeneous_matrix, world.root).to_np(),
            atol=1e-12,
        )


def test_the_workflow_fills_the_refrigerator_and_the_centrifuge(workflow_plan):
    demo, _, _ = workflow_plan
    assert {move.target.station for move in demo.moves} == set(Station)


def test_the_centrifuge_is_loaded_with_opposite_pairs(workflow_plan):
    demo, _, _ = workflow_plan
    opposite = {
        slot.identifier: slot.opposite
        for slot in demo.laboratory.bench.centrifuge.slots
    }
    loaded = {
        move.target.identifier
        for move in demo.moves
        if move.target.station is Station.CENTRIFUGE
    }
    assert loaded
    assert {opposite[holder] for holder in loaded} == loaded


def test_every_vessel_set_down_was_picked_up_by_the_pickup_before(workflow_plan):
    _, _, plan = workflow_plan
    picked = [
        node.designator.grasp.graspable.root
        for node in plan.get_nodes_by_designator_type(PickUpAction)
    ]
    placed = [
        node.designator.object_designator.root
        for node in plan.get_nodes_by_designator_type(PlaceAction)
    ]
    assert picked == placed


def test_each_grasp_approaches_the_way_its_target_opens(workflow_plan):
    demo, context, plan = workflow_plan
    world = context.world
    tilt = {
        Station.RACK: 0.0,
        Station.CENTRIFUGE: demo.loading_tilt,
        Station.REFRIGERATOR: math.pi / 2,
    }
    pickups = plan.get_nodes_by_designator_type(PickUpAction)
    for pickup, (_, _, station) in zip(
        pickups, expected_placements(demo, context), strict=True
    ):
        approach = tool_motions(pickup)[0].target
        rotation = world.transform(approach.homogeneous_matrix, world.root).to_np()
        axis = rotation[:3, 0]
        assert np.arccos(np.clip(-axis[2], -1.0, 1.0)) == pytest.approx(
            tilt[station], abs=1e-6
        )
        assert axis[1] >= -1e-9


def test_a_vessel_going_into_an_instrument_is_lifted_upright(workflow_plan):
    demo, context, plan = workflow_plan
    pickups = plan.get_nodes_by_designator_type(PickUpAction)
    for pickup, (_, _, station) in zip(
        pickups, expected_placements(demo, context), strict=True
    ):
        if station is Station.RACK:
            continue
        assert tool_motions(pickup)[-1].movement_type is MovementType.CARTESIAN


def test_a_vessel_going_into_an_instrument_is_taken_with_both_pads_clear(
    workflow_plan,
):
    demo, context, plan = workflow_plan
    pickups = plan.get_nodes_by_designator_type(PickUpAction)
    for pickup, (_, _, station) in zip(
        pickups, expected_placements(demo, context), strict=True
    ):
        if station is Station.RACK:
            continue
        pre_approach, approach = tool_motions(pickup)[:2]
        assert approach.resolved_position_threshold() < demo.pad_clearance
        assert pre_approach.resolved_position_threshold() >= demo.position_tolerance


def test_the_fingers_close_on_a_vessel_with_the_tool_held(workflow_plan):
    _, context, plan = workflow_plan
    tool = context.robot.left_arm.end_effector.tool_frame
    closings = plan.get_nodes_by_designator_type(PadContactMotion)
    assert closings
    for closing in closings:
        chart = closing.designator.motion_chart
        assert any(
            isinstance(node, HoldPose) and node.tip_link is tool for node in chart.nodes
        )


def test_the_fingers_let_go_of_a_vessel_with_the_tool_held(workflow_plan):
    _, _, plan = workflow_plan
    for placing in plan.get_nodes_by_designator_type(PlaceAction):
        openings = [
            leaf.designator
            for leaf in leaves(placing)
            if isinstance(leaf, MotionNode)
            and isinstance(leaf.designator, MoveGripperMotion)
        ]
        assert openings
        assert all(isinstance(opening, HeldToolGripperMotion) for opening in openings)


def test_every_drive_ends_at_a_stand_and_locks_the_drive_again(workflow_plan):
    demo, context, plan = workflow_plan
    stands = {
        stand.pose(context.world).to_np().tobytes() for stand in demo.stands(context)
    }
    drives = plan.get_nodes_by_designator_type(DriveAction)
    assert drives
    for drive in drives:
        assert drive.designator.target.to_np().tobytes() in stands
    switches = [
        leaf.controlled
        for leaf in leaves(plan.root)
        if isinstance(leaf, DriveControlNode)
    ]
    assert switches == [True, False] * len(drives)


def test_the_door_and_the_lid_are_opened_and_closed_again(workflow_plan):
    demo, context, plan = workflow_plan
    bench = demo.laboratory.bench
    door = context.world.get_connection_by_name(bench.refrigerator.door_joint)
    lid = context.world.get_connection_by_name(bench.centrifuge.lid_joint)
    positions = {door: [], lid: []}
    for node in plan.get_nodes_by_designator_type(MechanismMotion):
        positions[node.designator.joint].append(node.designator.position)
    assert positions[door] == [demo.door_open, 0.0]
    assert positions[lid] == [demo.lid_pulled, demo.lid_pushed, demo.lid_pulled, 0.0]


def test_an_unexecuted_plan_is_not_accepted(workflow_plan):
    demo, context, _ = workflow_plan
    with pytest.raises(TaskFailed):
        demo.require_success(context)
