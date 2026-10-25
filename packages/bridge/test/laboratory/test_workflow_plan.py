"""
Build the PR2 laboratory workflow's plan without executing robot motion.
"""

from __future__ import annotations

import numpy as np
import pytest

from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from coraplex.robot_plans.actions.core.placing import PlaceAction
from cramera_bridge.exceptions import TaskFailed
from cramera_bridge.laboratory.mobility import (
    DriveAction,
    DriveControlNode,
    MechanismMotion,
)
from cramera_bridge.laboratory.workflow import LaboratoryWorkflowDemo


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


def expected_placements(demo, context):
    """
    :return: The vessel each placing of the workflow sets down, and where its bottom
        ends, from the bench's starting slots and the workflow's rack moves.
    """
    world = context.world
    laboratory = demo.laboratory
    occupied = {placement.slot: placement.key for placement in laboratory.bench.tubes}
    placements = []
    for move in demo.rack_moves:
        key = occupied.pop(move.source)
        occupied[move.target] = key
        placements.append((key, laboratory.slot_pose(move.target, world)))
    return placements


def test_every_vessel_is_set_down_where_the_workflow_takes_it(workflow_plan):
    demo, context, plan = workflow_plan
    world = context.world
    placings = plan.get_nodes_by_designator_type(PlaceAction)
    expected = expected_placements(demo, context)
    assert [node.designator.object_designator.root.name.name for node in placings] == [
        key for key, _ in expected
    ]
    for node, (_, target) in zip(placings, expected):
        np.testing.assert_allclose(
            world.transform(
                node.designator.target_location.homogeneous_matrix, world.root
            ).to_np(),
            world.transform(target.homogeneous_matrix, world.root).to_np(),
            atol=1e-12,
        )


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


def test_every_drive_ends_at_a_stand_and_locks_the_drive_again(workflow_plan):
    demo, context, plan = workflow_plan
    stands = {stand.pose(context.world).to_np().tobytes() for stand in demo.stands()}
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
