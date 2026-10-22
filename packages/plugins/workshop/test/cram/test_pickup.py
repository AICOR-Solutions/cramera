"""
Picking up a screw from the box: the approach is aimed at the screw where it lies when
the pick-up runs, which is after the box was carried to the bench.
"""

from __future__ import annotations

import numpy as np

from coraplex.plans.factories import sequential
from coraplex.plans.plan_node import MotionNode
from cramera_workshop.robot.world import WorkshopBody
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix

SHIFT = 0.3
"""
How far the test moves the screw after the plan was built, in metres.
"""


def test_the_screw_is_approached_where_it_is_when_the_pick_up_runs(insertion_demo):
    context = insertion_demo.build_context(insertion_demo.build_world())
    screw = context.world.get_body_by_name(WorkshopBody.SCREW)
    action = insertion_demo.screw_pickup(context, screw)
    plan = sequential([action], context=context).plan
    plan.root.notify()
    approach = next(
        node.designator
        for node in plan.root.descendants
        if isinstance(node, MotionNode)
    )
    connection = screw.parent_connection
    moved = connection.origin.to_np().copy()
    moved[0, 3] -= SHIFT
    connection.origin = HomogeneousTransformationMatrix(
        moved, reference_frame=connection.parent, child_frame=screw
    )
    expected = action.grasp_description.grasp_pose_sequence(screw)[0]
    np.testing.assert_allclose(approach.target.to_np(), expected.to_np(), atol=1e-9)
