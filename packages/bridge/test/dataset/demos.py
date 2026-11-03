"""
A short task demo for the tests: raising a robot's torso takes a few seconds in
simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List

from coraplex.robot_plans.actions.base import SequentialAction
from coraplex.robot_plans.actions.core.robot_body import MoveTorsoAction
from cramera_bridge.exceptions import TaskFailed
from cramera_bridge.performing import TaskContext
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_bridge.robot_task import RobotTaskDemo
from cramph.node import StatechartNode
from krrood.entity_query_language.factories import a, entity, the, variable
from semantic_digital_twin.datastructures.definitions import TorsoState
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.world import World

TORSO_TOLERANCE = 0.01
"""
How far, in metres, the torso may stop from its target height.
"""

# %% demo


class TorsoMeasurement(StrEnum):
    """
    What the torso demo measures.
    """

    TORSO_ERROR = "torsoError"
    """
    The distance between the torso joint and its target value.
    """


@dataclass
class TorsoDemo(RobotTaskDemo):
    """
    Raises the robot's torso to the given state.
    """

    torso_state: TorsoState = TorsoState.HIGH
    """
    The state the torso is moved to.
    """

    def build_plan(self, context: TaskContext) -> StatechartNode:
        return MoveTorsoAction(torso_state=self.torso_state)

    def measure(self, context: TaskContext) -> AcceptanceMetrics:
        joint_state = context.robot.get_torso().get_joint_state_by_type(
            self.torso_state
        )
        error = max(
            abs(connection.position - target)
            for connection, target in zip(
                joint_state.connections, joint_state.target_values
            )
        )
        if error > TORSO_TOLERANCE:
            raise TaskFailed(f"the torso stopped {error:.3f} m from its target")
        return AcceptanceMetrics(
            measurements={TorsoMeasurement.TORSO_ERROR.value: error}
        )


@dataclass
class RaisedThenMovedTorsoDemo(TorsoDemo):
    """
    Raises the robot's torso in a plan of its own, then moves it to the given state in a
    second plan.
    """

    torso_state: TorsoState = TorsoState.LOW
    """
    The state the second plan moves the torso to.
    """

    def build_plans(self, context: TaskContext) -> List[StatechartNode]:
        raised = MoveTorsoAction(torso_state=TorsoState.HIGH)
        return [raised, self.build_plan(context)]


@dataclass(eq=False, repr=False, kw_only=True)
class GroundedTorsoAction(SequentialAction):
    """
    Moves the torso by a move the plan grounds once it reaches it.
    """

    torso_state: TorsoState
    """
    The state the torso is moved to.
    """

    def create_steps(self) -> List[StatechartNode]:
        return [a(MoveTorsoAction)(torso_state=self.torso_state)]


@dataclass
class QueryingTorsoDemo(TorsoDemo):
    """
    Finds its robot with an entity query, and raises the torso by an action whose move
    the plan grounds.
    """

    def build_context(self, world: World) -> TaskContext:
        robot = variable(PR2, world.semantic_annotations)
        return TaskContext(world=world, robot=the(entity(robot)).first())

    def build_plan(self, context: TaskContext) -> StatechartNode:
        return GroundedTorsoAction(torso_state=self.torso_state)
