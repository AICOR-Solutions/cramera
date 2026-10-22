"""
The ideal thread: it is installed only for a seated blade and a screw at the pilot's
entrance, and turning divides the remaining travel into stages.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cramera_workshop.robot.screw_thread import (
    EngagementProblem,
    ScrewAssembly,
    ScrewEngagementFailed,
    ThreadDimensions,
    ThreadLimits,
    TurnScrewMotion,
)
from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import (
    Connection6DoF,
    FixedConnection,
    ScrewConnection,
)
from semantic_digital_twin.world_description.world_entity import Body

DIMENSIONS = ThreadDimensions(
    pitch=0.006, depth=0.11, mouth_height=0.14, slot_floor=0.122
)
"""
The workshop's thread dimensions.
"""

TILT = 0.2
"""
A tilt well beyond the angle tolerance, in radians.
"""

# %% world


class ThreadRig:
    """
    A workpiece, a screw on a free connection and a driver on a free connection below a
    world's root.
    """

    def __init__(self):
        self.world = World()
        root = Body(name=PrefixedName("map"))
        self.workpiece = Body(name=PrefixedName("workpiece"))
        self.screw = Body(name=PrefixedName("screw"))
        self.driver = Body(name=PrefixedName("driver"))
        with self.world.modify_world():
            self.world.add_kinematic_structure_entity(root)
            self.world.add_kinematic_structure_entity(self.workpiece)
            self.world.add_connection(
                FixedConnection(parent=root, child=self.workpiece)
            )
            for body in (self.screw, self.driver):
                self.world.add_kinematic_structure_entity(body)
                self.world.add_connection(
                    Connection6DoF.create_with_dofs(self.world, root, body)
                )
        self.place(self.screw, z=DIMENSIONS.mouth_height)
        self.place(self.driver, z=DIMENSIONS.mouth_height + DIMENSIONS.slot_floor)

    def place(self, body: Body, **pose: float) -> None:
        """
        :param body: The screw or the driver.
        :param pose: Its pose's coordinates in the workpiece, which sits at the root.
        """
        body.parent_connection.origin = HomogeneousTransformationMatrix.from_xyz_rpy(
            **pose, reference_frame=self.world.root, child_frame=body
        )

    def assembly(self, dimensions: ThreadDimensions = DIMENSIONS) -> ScrewAssembly:
        return ScrewAssembly(
            screw=self.screw,
            driver=self.driver,
            workpiece=self.workpiece,
            dimensions=dimensions,
        )


@pytest.fixture
def rig() -> ThreadRig:
    """
    :return: A screw at the entrance with the blade seated in its slot.
    """
    return ThreadRig()


# %% engagement


def test_a_seated_blade_installs_the_thread_where_the_screw_is(rig):
    before = rig.screw.global_pose.to_np()
    connection = rig.assembly().install(rig.world)
    assert isinstance(rig.screw.parent_connection, ScrewConnection)
    assert connection.parent is rig.workpiece
    np.testing.assert_allclose(rig.screw.global_pose.to_np(), before, atol=1e-9)
    turns = DIMENSIONS.depth * math.tau / DIMENSIONS.pitch
    assert connection.dof.limits.lower.position == pytest.approx(-turns)


@pytest.mark.parametrize(
    "body, pose, problem",
    [
        ("driver", {"z": 0.5}, EngagementProblem.BLADE_OFF_SLOT),
        ("driver", {"z": 0.262, "yaw": TILT}, EngagementProblem.BLADE_TURNED),
        ("screw", {"x": 0.01, "z": 0.14}, EngagementProblem.OFF_PILOT_AXIS),
        ("screw", {"z": 0.3}, EngagementProblem.NOT_AT_MOUTH),
    ],
)
def test_a_misaligned_blade_or_screw_is_refused(rig, body, pose, problem):
    target = rig.driver if body == "driver" else rig.screw
    rig.place(target, **pose)
    if target is rig.screw:
        screw_pose = rig.screw.global_pose.to_np()
        slot = (
            screw_pose
            @ HomogeneousTransformationMatrix.from_xyz_rpy(
                z=DIMENSIONS.slot_floor
            ).to_np()
        )
        rig.driver.parent_connection.origin = HomogeneousTransformationMatrix(
            slot, reference_frame=rig.world.root, child_frame=rig.driver
        )
    with pytest.raises(ScrewEngagementFailed) as refused:
        rig.assembly().install(rig.world)
    assert refused.value.problem is problem
    assert refused.value.error_message() == problem.value


def test_invalid_dimensions_are_refused(rig):
    dimensions = ThreadDimensions(
        pitch=0.0, depth=0.11, mouth_height=0.14, slot_floor=0.122
    )
    with pytest.raises(ScrewEngagementFailed) as refused:
        rig.assembly(dimensions).install(rig.world)
    assert refused.value.problem is EngagementProblem.INVALID_GEOMETRY


def test_a_threaded_screw_is_not_threaded_twice(rig):
    rig.assembly().install(rig.world)
    with pytest.raises(ScrewEngagementFailed) as refused:
        rig.assembly().install(rig.world)
    assert refused.value.problem is EngagementProblem.ALREADY_THREADED


# %% turning


def test_the_whole_thread_is_driven_in_bounded_stages(rig):
    connection = rig.assembly().install(rig.world)
    targets = TurnScrewMotion(screw=rig.screw, driver=rig.driver).joint_targets()
    final = connection.dof.limits.lower.position
    stage = ThreadLimits().maximum_turns_per_stage * math.tau
    assert targets[-1] == final
    steps = np.diff([0.0, *targets])
    assert np.all(np.abs(steps) <= stage + 1e-9)


def test_engagement_turns_once_by_the_given_amount(rig):
    rig.assembly().install(rig.world)
    motion = TurnScrewMotion(screw=rig.screw, driver=rig.driver, turns=0.25)
    assert motion.joint_targets() == [pytest.approx(-0.25 * math.tau)]


@pytest.mark.parametrize("turns", [0.0, math.inf])
def test_invalid_turns_are_refused(rig, turns):
    rig.assembly().install(rig.world)
    with pytest.raises(ScrewEngagementFailed) as refused:
        TurnScrewMotion(screw=rig.screw, driver=rig.driver, turns=turns).joint_targets()
    assert refused.value.problem is EngagementProblem.INVALID_TURNS


def test_an_unthreaded_screw_is_not_turned(rig):
    with pytest.raises(ScrewEngagementFailed) as refused:
        TurnScrewMotion(screw=rig.screw, driver=rig.driver).joint_targets()
    assert refused.value.problem is EngagementProblem.NOT_THREADED


def test_the_dimensions_come_from_the_workshop(bundle):
    dimensions = ThreadDimensions.of_workshop(bundle.workshop)
    screw = bundle.workshop.screw
    assert dimensions.pitch == screw.thread_pitch
    assert dimensions.slot_floor == screw.head_top - screw.slot_size.z
    assert dimensions.is_valid()
