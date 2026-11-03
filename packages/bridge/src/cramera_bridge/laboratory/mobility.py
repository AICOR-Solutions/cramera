"""
Moving the PR2 between its stands in the laboratory, tucking its arm in, and moving
hinged parts such as a door or a lid while the gripper holds them.

The laboratory's demos take the drive out of the controller while the arms work; a drive
hands it back for its own motion only, and lets the base come up to the edge of the
bench. What keeps the base where it stands while the arm works is the base hold of each
action: CRAM's tool actions hold it, and the tucking and the door and lid actions here
hold it too, so collision avoidance cannot push it away.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import List, Tuple, Type

import krrood.symbolic_math.symbolic_math as sm
from coraplex.plans.context_extensions import RobotAccess
from coraplex.robot_plans.actions.base import ParallelAction, SequentialAction
from coraplex.robot_plans.actions.core.robot_body import ParkArmsAction
from cramph.context import ContextExtension
from cramph.node import NodeArtifacts, StatechartNode, SucceedsOnObservingTrue
from giskardpy.motion_statechart.binding_policy import GoalBindingPolicy
from giskardpy.motion_statechart.goals.grasped_mechanism import (
    ArticulateGraspedMechanism,
)
from giskardpy.motion_statechart.tasks.cartesian_tasks import CartesianPose
from giskardpy.motion_statechart.tasks.joint_tasks import JointPositionList
from giskardpy.motion_statechart.weights import DefaultWeights
from krrood.ormatic.utils import classproperty
from krrood_spatial_math.spatial_types import Pose
from semantic_digital_twin.collision_checking.collision_matrix import CollisionRule
from semantic_digital_twin.collision_checking.collision_rules import (
    AllowCollisionBetweenGroups,
    AllowCollisionForEndEffector,
)
from semantic_digital_twin.datastructures.joint_state import JointState
from semantic_digital_twin.robots.robot_parts import Arm
from semantic_digital_twin.world_description.connections import ActiveConnection1DOF
from semantic_digital_twin.world_description.world_entity import Body

DRIVE_VELOCITY = 0.25
"""
How fast the base drives, in metres per second.
"""

DRIVE_POSITION_TOLERANCE = 0.002
"""
How far the base may stop from its stand, in metres.
"""

DRIVE_ORIENTATION_TOLERANCE = 0.005
"""
How far the base may stop turned from its stand's heading, in radians.
"""

# %% drive control


@dataclass(eq=False, repr=False, kw_only=True)
class DriveControl(SucceedsOnObservingTrue, StatechartNode):
    """
    A plan step between two motions that hands the robot's drive to the controller, or
    takes it back, when it starts, and succeeds once it did.

    The statechart then builds every node again, so the controller moves the drive from
    the next motion on, or no longer does.
    """

    controlled: bool = True
    """
    Whether the controller may move the drive after this step.
    """

    @classproperty
    def required_context_extensions(cls) -> Tuple[Type[ContextExtension], ...]:
        return super().required_context_extensions + (RobotAccess,)

    def build_artifacts(self) -> NodeArtifacts:
        return NodeArtifacts(observation=sm.Scalar.const_true())

    def on_start(self) -> None:
        super().on_start()
        world = self.context.world
        robot = self.context.require_extension(RobotAccess).robot
        with world.modify_world():
            world.set_dofs_has_hardware_interface(
                robot.drive.active_dofs, self.controlled
            )


# %% driving


@dataclass(eq=False, repr=False, kw_only=True)
class DriveAction(SequentialAction):
    """
    Drives the base straight to a stand, up to furniture's edge if the stand is there,
    while the controller may move its drive, and takes the drive back once it stands
    there.

    The base's own clearance is not kept from the environment while driving; the arms,
    the torso and the head still keep theirs.
    """

    target: Pose
    """
    Where the base stands at the end, facing along the pose's x axis.
    """

    linear_velocity: float = DRIVE_VELOCITY
    """
    How fast the base drives, in metres per second.
    """

    def base_bodies(self) -> List[Body]:
        """
        :return: The robot's colliding bodies that do not move with its torso.
        """
        lift = self.robot.torso.active_connections[0].child
        return [
            body
            for body in self.robot.bodies
            if body.has_collision() and not self.rides_on(body, lift)
        ]

    def rides_on(self, body: Body, carrier: Body) -> bool:
        """
        :param body: A body of the robot.
        :param carrier: Another body of the robot.
        :return: Whether the body hangs below the carrier in the robot's kinematic tree.
        """
        entity = body
        while entity is not self.robot.root:
            if entity is carrier:
                return True
            entity = entity.parent_connection.parent
        return False

    def create_temporary_collision_rules(self) -> List[CollisionRule]:
        """
        :return: An allowance for the base to come up to the environment while it
            drives.
        """
        environment = [
            body
            for body in self.world.bodies
            if body not in self.robot.bodies and body.has_collision()
        ]
        return [
            AllowCollisionBetweenGroups(
                body_group_a=self.base_bodies(), body_group_b=environment
            )
        ]

    def create_steps(self) -> List[StatechartNode]:
        return [
            DriveControl(controlled=True),
            CartesianPose(
                root_link=self.world.root,
                tip_link=self.robot.root,
                goal_pose=self.target,
                reference_linear_velocity=self.linear_velocity,
                translation_threshold=DRIVE_POSITION_TOLERANCE,
                orientation_threshold=DRIVE_ORIENTATION_TOLERANCE,
                binding_policy=GoalBindingPolicy.Bind_on_start,
                weight=DefaultWeights.WEIGHT_ABOVE_COLLISION_AVOIDANCE,
                name=type(self).__name__,
            ),
            DriveControl(controlled=False),
        ]


# %% mechanisms


@dataclass(eq=False, repr=False, kw_only=True)
class MechanismAction(ParallelAction):
    """
    Moves a door, a lid or another part on a joint of one degree of freedom to a
    position, while the gripper keeps its hold on the part and the base stands still.
    """

    part: Body
    """
    The part the gripper holds; its joint is the first joint of one degree of freedom
    above it.
    """

    arm: Arm
    """
    The arm whose gripper holds the part.
    """

    position: float
    """
    Where the joint ends, in its own unit.
    """

    @property
    def joint(self) -> ActiveConnection1DOF:
        """
        The joint the part moves on.
        """
        return self.part.get_first_parent_connection_of_type(ActiveConnection1DOF)

    def create_temporary_collision_rules(self) -> List[CollisionRule]:
        """
        :return: An allowance for the gripper on the part to touch it and its
            surroundings while it moves the part.
        """
        return [AllowCollisionForEndEffector(end_effector=self.arm.end_effector)]

    def create_steps(self) -> List[StatechartNode]:
        return [
            ArticulateGraspedMechanism(
                tip_link=self.arm.end_effector.tool_frame,
                environment_link=self.part,
                goal_joint_state=self.position,
                mechanism_weight=DefaultWeights.WEIGHT_BELOW_COLLISION_AVOIDANCE,
                name=type(self).__name__,
            ),
            *self.keep_base_still(),
        ]


# %% arms


@dataclass(eq=False, repr=False, kw_only=True)
class HeldBaseJointsAction(ParallelAction):
    """
    Moves named joints to their positions, with the base held where it stands so that
    collision avoidance cannot move it.
    """

    names: List[str]
    """
    The names of the joints moved.
    """

    positions: List[float]
    """
    Where each joint of :attr:`names` ends, in the order of :attr:`names`.
    """

    def create_steps(self) -> List[StatechartNode]:
        return [
            JointPositionList(
                goal_state=JointState.from_mapping(
                    {
                        self.world.get_connection_by_name(name): position
                        for name, position in zip(self.names, self.positions)
                    }
                )
            ),
            *self.keep_base_still(),
        ]


@dataclass(eq=False, repr=False, kw_only=True)
class TuckArmsAction(ParkArmsAction):
    """
    CRAM's parking of the arms, with the base held where it stands.
    """

    raise_torso: bool = False
    """
    Whether the torso is raised to the top of its travel as well.

    The controller moves the torso along with the arms to reach their goals, so it
    drifts over a long task; raising it where nothing is in the way gives the next
    station the same start.
    """

    def park_joint_state(self) -> JointState:
        """
        :return: CRAM's park positions of the arms, and the torso at the top of its
            travel if :attr:`raise_torso`.
        """
        park_state = super().park_joint_state()
        if not self.raise_torso:
            return park_state
        torso = self.robot.torso.active_connections
        return JointState(
            connections=[*park_state.connections, *torso],
            target_values=[
                *park_state.target_values,
                *(connection.dof.limits.upper.position for connection in torso),
            ],
        )

    def create_steps(self) -> List[StatechartNode]:
        return [*super().create_steps(), *self.keep_base_still()]
