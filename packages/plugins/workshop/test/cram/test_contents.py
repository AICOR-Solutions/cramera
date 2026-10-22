"""
The screw box's contents in the contact world while the native box is carried: coupled
before the plan, followed tick by tick, settled and checked at the end.
"""

from __future__ import annotations

import mujoco
import numpy as np
import pytest

from cramera_workshop.acceptance import ContentsModel
from cramera_workshop.collision_model import FREE_JOINT_SUFFIX
from cramera_workshop.physics import WorkshopPhysics
from cramera_workshop.robot.contents import (
    CouplingProblem,
    InvalidContentsCoupling,
    WorkshopContents,
)
from cramera_workshop.robot.world import WorkshopBody
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix

CONTROL_PERIOD = 0.02
"""
The simulated time of one native control tick, in seconds.
"""

OUTSIDE = 0.5
"""
How far above its box a test lifts an escaped screw, in metres.
"""

LIFT = 0.05
"""
How far the test lifts the native box, in metres.
"""


@pytest.fixture
def contents(workshop_world, environment, bundle) -> WorkshopContents:
    """
    :return: The screw box's contents, not yet coupled.
    """
    return WorkshopContents(
        world=workshop_world,
        physics=WorkshopPhysics(bundle),
        box=workshop_world.get_body_by_name(WorkshopBody.SCREW_BOX),
        contents=tuple(environment.screws(workshop_world)),
        control_period=CONTROL_PERIOD,
    )


def test_starting_puts_the_screws_below_the_box(contents):
    contents.start()
    contents.start()
    assert contents.active
    assert all(
        screw.parent_connection.parent is contents.box for screw in contents.contents
    )
    assert contents.measurements.contents_count == len(contents.contents)
    assert contents.measurements.model is ContentsModel.RELATIVE_CONTACT


def test_the_screws_follow_a_lifted_box_and_stay_in(contents):
    contents.start()
    connection = contents.box.parent_connection
    lifted = connection.origin.to_np().copy()
    lifted[2, 3] += LIFT
    connection.origin = HomogeneousTransformationMatrix(
        lifted, reference_frame=connection.parent, child_frame=contents.box
    )
    for _ in range(10):
        contents.on_motion_tick(None)
    contents.stop()
    assert contents.measurements.ticks > 10
    assert contents.measurements.retained_contents
    assert all(
        screw.parent_connection.parent is contents.world.root
        for screw in contents.contents
    )
    heights = [screw.global_pose.to_np()[2, 3] for screw in contents.contents]
    assert min(heights) > contents.box.global_pose.to_np()[2, 3]


def test_a_screw_outside_the_box_is_reported_as_escaped(contents):
    contents.start()
    contents.final_settle_seconds = 0.0
    escaped = contents.contents[0].name.name
    joint = contents.physics.world.model.joint(f"{escaped}{FREE_JOINT_SUFFIX}")
    contents.physics.world.data.qpos[joint.qposadr[0] + 2] += OUTSIDE
    mujoco.mj_forward(contents.physics.world.model, contents.physics.world.data)
    with pytest.raises(InvalidContentsCoupling) as refused:
        contents.stop()
    assert refused.value.problem is CouplingProblem.ESCAPED
    assert refused.value.escaped == (escaped,)
    assert escaped in str(refused.value)


def test_an_invalid_interval_is_refused(contents):
    contents.start()
    with pytest.raises(InvalidContentsCoupling) as refused:
        contents.advance(-1.0)
    assert refused.value.problem is CouplingProblem.INVALID_INTERVAL


def test_repeated_screws_are_refused(contents):
    contents.contents = (contents.contents[0], contents.contents[0])
    with pytest.raises(InvalidContentsCoupling) as refused:
        contents.start()
    assert refused.value.problem is CouplingProblem.REPEATED_SCREWS


def test_a_body_that_is_no_screw_is_refused(contents, workshop_world):
    contents.contents = (workshop_world.get_body_by_name(WorkshopBody.DRIVER),)
    with pytest.raises(InvalidContentsCoupling) as refused:
        contents.start()
    assert refused.value.problem is CouplingProblem.UNDECLARED_SCREW
    assert str(refused.value) == CouplingProblem.UNDECLARED_SCREW.value


def test_the_cavity_lies_inside_the_box(contents):
    cavity = contents.cavity_bounds()
    assert np.all(cavity.lower < cavity.upper)
    assert cavity.contains(cavity, 0.0)
