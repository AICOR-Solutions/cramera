"""
A short task demo for the tests: raising a robot's torso takes a few seconds in
simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List

from coraplex.datastructures.dataclasses import Context
from coraplex.plans.factories import execute_single, sequential
from coraplex.plans.plan import Plan
from coraplex.plans.plan_node import PlanNode
from coraplex.robot_plans.actions.base import ActionDescription
from coraplex.robot_plans.actions.core.robot_body import MoveTorsoAction
from cramera_bridge.exceptions import TaskFailed
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_bridge.robot_task import RobotTaskDemo
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

    def build_plan(self, context: Context) -> Plan:
        return execute_single(MoveTorsoAction(self.torso_state), context=context).plan

    def measure(self, context: Context) -> AcceptanceMetrics:
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

    def build_plans(self, context: Context) -> List[Plan]:
        raised = execute_single(MoveTorsoAction(TorsoState.HIGH), context=context).plan
        return [raised, self.build_plan(context)]


@dataclass
class GroundedTorsoAction(ActionDescription):
    """
    Moves the torso by a move the plan grounds once it reaches it.
    """

    torso_state: TorsoState
    """
    The state the torso is moved to.
    """

    @property
    def _action_plan(self) -> PlanNode:
        return sequential([a(MoveTorsoAction)(torso_state=self.torso_state)])


@dataclass
class QueryingTorsoDemo(TorsoDemo):
    """
    Finds its robot with an entity query, and raises the torso by an action whose move
    the plan grounds.
    """

    def build_context(self, world: World) -> Context:
        robot = variable(PR2, world.semantic_annotations)
        return Context(world=world, robot=the(entity(robot)).first())

    def build_plan(self, context: Context) -> Plan:
        return execute_single(
            GroundedTorsoAction(self.torso_state), context=context
        ).plan
