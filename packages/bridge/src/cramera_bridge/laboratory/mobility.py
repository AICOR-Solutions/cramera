"""
Moving the PR2 between its stands in the laboratory, tucking its arm in, and moving
hinged parts such as a door or a lid while the gripper holds them.

The laboratory's demos take the drive out of the controller while the arms work; a drive
hands it back for its own motion only, and lets the base come up to the edge of the
bench. What keeps the base where it stands while the arm works is the base hold of each
motion: CRAM's tool motions hold it, and the tucking and the door and lid motions here
hold it too, so collision avoidance cannot push it away.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import List

from coraplex.plans.executables import Executable
from coraplex.plans.factories import execute_single, sequential
from coraplex.plans.plan_node import ExecutionBoundaryNode, PlanNode
from coraplex.robot_plans.actions.base import ActionDescription
from coraplex.robot_plans.actions.core.robot_body import ParkArmsAction
from coraplex.robot_plans.motions.base import BaseMotion
from coraplex.robot_plans.motions.robot_body import MoveJointsMotion
from giskardpy.motion_statechart.binding_policy import GoalBindingPolicy
from giskardpy.motion_statechart.data_types import DefaultWeights
from giskardpy.motion_statechart.goals.collision_avoidance import (
    UpdateTemporaryCollisionRules,
)
from giskardpy.motion_statechart.goals.open_close import Close, Open
from giskardpy.motion_statechart.goals.templates import Parallel
from giskardpy.motion_statechart.graph_node import MotionStatechartNode
from giskardpy.motion_statechart.tasks.cartesian_tasks import CartesianPose
from semantic_digital_twin.collision_checking.collision_rules import (
    AllowCollisionBetweenGroups,
)
from semantic_digital_twin.robots.robot_parts import Arm
from semantic_digital_twin.spatial_types import Pose
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


@dataclass
class DriveControl(Executable):
    """
    Hands the robot's drive to the controller, or takes it back.
    """

    controlled: bool = True
    """
    Whether the controller may move the drive from now on.
    """

    def execute(self) -> None:
        world = self.context.world
        with world.modify_world():
            world.set_dofs_has_hardware_interface(
                self.context.robot.drive.active_dofs, self.controlled
            )


@dataclass(eq=False, repr=False)
class DriveControlNode(ExecutionBoundaryNode):
    """
    A plan step between two motions that hands the drive to the controller or takes it
    back.
    """

    controlled: bool = True
    """
    Whether the controller may move the drive after this step.
    """

    def notify(self) -> None:
        """
        This step has no children to expand.
        """

    def parse(self) -> DriveControl:
        """
        :return: The executable that changes who moves the drive.
        """
        return DriveControl(context=self.context, controlled=self.controlled)


# %% driving


@dataclass
class DriveMotion(BaseMotion):
    """
    Drives the base straight to a stand, up to furniture's edge if the stand is there.

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

    def perform(self) -> None:
        return

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

    @property
    def _motion_chart(self) -> MotionStatechartNode:
        environment = [
            body
            for body in self.world.bodies
            if body not in self.robot.bodies and body.has_collision()
        ]
        return Parallel(
            [
                CartesianPose(
                    root_link=self.world.root,
                    tip_link=self.robot.root,
                    goal_pose=self.target,
                    reference_linear_velocity=self.linear_velocity,
                    translation_threshold=DRIVE_POSITION_TOLERANCE,
                    orientation_threshold=DRIVE_ORIENTATION_TOLERANCE,
                    binding_policy=GoalBindingPolicy.Bind_on_start,
                    weight=DefaultWeights.WEIGHT_ABOVE_COLLISION_AVOIDANCE,
                    name=self.__class__.__name__,
                ),
                UpdateTemporaryCollisionRules(
                    temporary_rules=[
                        AllowCollisionBetweenGroups(
                            body_group_a=self.base_bodies(),
                            body_group_b=environment,
                        )
                    ]
                ),
            ],
            name=self.__class__.__name__,
        )


@dataclass
class DriveAction(ActionDescription):
    """
    Drives the robot to a stand while the controller may move its drive, and takes the
    drive back once it stands there.
    """

    target: Pose
    """
    Where the base stands at the end, facing along the pose's x axis.
    """

    @property
    def _action_plan(self) -> PlanNode:
        return sequential(
            [
                DriveControlNode(controlled=True),
                DriveMotion(self.target),
                DriveControlNode(controlled=False),
            ]
        )


# %% mechanisms


@dataclass
class MechanismMotion(BaseMotion):
    """
    Moves a door, a lid or another part on a joint of one degree of freedom to a
    position, while the gripper keeps its hold on the part.
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

    def perform(self) -> None:
        return

    @property
    def joint(self) -> ActiveConnection1DOF:
        """
        The joint the part moves on.
        """
        return self.part.get_first_parent_connection_of_type(ActiveConnection1DOF)

    @property
    def _motion_chart(self) -> MotionStatechartNode:
        goal = Open if self.position >= self.joint.position else Close
        return Parallel(
            [
                goal(
                    tip_link=self.arm.end_effector.tool_frame,
                    environment_link=self.part,
                    goal_joint_state=self.position,
                    mechanism_weight=DefaultWeights.WEIGHT_BELOW_COLLISION_AVOIDANCE,
                    name=self.__class__.__name__,
                ),
                *self.keep_base_still(),
            ],
            name=self.__class__.__name__,
        )


# %% arms


@dataclass
class HeldBaseJointsMotion(MoveJointsMotion):
    """
    CRAM's motion of named joints, with the base held where it stands so that collision
    avoidance cannot move it.
    """

    @property
    def _motion_chart(self) -> MotionStatechartNode:
        return Parallel(
            [super()._motion_chart, *self.keep_base_still()],
            name=self.__class__.__name__,
        )


@dataclass
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

    @property
    def _action_plan(self) -> PlanNode:
        names, positions = self.get_joint_poses()
        if self.raise_torso:
            for connection in self.robot.torso.active_connections:
                names.append(connection.name.name)
                positions.append(connection.dof.limits.upper.position)
        return execute_single(
            HeldBaseJointsMotion(
                names=names,
                positions=positions,
                max_joint_velocity=self.max_joint_velocity,
            )
        )
