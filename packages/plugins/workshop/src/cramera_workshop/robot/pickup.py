"""
The PR2 picks up the workshop's small bodies: a screw among its neighbours in a box, the
screwdriver from its cradle, and the screw box by its carry bar.

The fingers close until they stall on the body, as CRAM's pick-up allows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from typing_extensions import ClassVar, Optional

from coraplex.datastructures.enums import Arms
from coraplex.datastructures.grasp import GraspDescription
from coraplex.plans.attachment_nodes import AttachNode
from coraplex.plans.factories import sequential
from coraplex.plans.plan_node import PlanNode
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from coraplex.robot_plans.motions.base import BaseMotion
from coraplex.robot_plans.motions.gripper import (
    MoveGripperMotion,
    MoveToolCenterPointMotion,
)
from coraplex.view_manager import ViewManager
from giskardpy.motion_statechart.context import MotionStatechartContext
from giskardpy.motion_statechart.data_types import DefaultWeights
from giskardpy.motion_statechart.goals.templates import Parallel, Sequence
from giskardpy.motion_statechart.graph_node import MotionStatechartNode
from giskardpy.motion_statechart.tasks.cartesian_tasks import (
    CartesianOrientation,
    CartesianPositionStraight,
)
from cramera_workshop.robot.gaze import (
    AnchoredToolCenterPointMotion,
    ManipulationWithGaze,
)
from semantic_digital_twin.datastructures.definitions import GripperState
from semantic_digital_twin.datastructures.joint_state import JointState
from semantic_digital_twin.robots.robot_parts import EndEffector
from semantic_digital_twin.spatial_types import Pose
from semantic_digital_twin.world_description.connections import ActiveConnection1DOF
from semantic_digital_twin.world_description.world_entity import Body

INHERITED_FIELD_TYPES = (Arms, Body, GraspDescription, Optional)
"""
The types the pick-up actions' inherited fields are annotated with; CRAM resolves a
designator's field annotations in the module of its class, so they must be bound here.
"""

# %% fingers


@dataclass(frozen=True)
class FingerJoint:
    """
    The joint every finger of a two-finger gripper follows.
    """

    gripper: EndEffector
    """
    The gripper.
    """

    def connection(self) -> ActiveConnection1DOF:
        """
        :return: The connection owning the degree of freedom the fingers share.
        """
        finger = self.gripper.fingers[0].root.parent_connection
        return self.gripper._world.get_connection_by_name(finger.raw_dof.name)

    def opened_to(self, position: float) -> JointState:
        """
        :param position: The joint position.
        :return: The fingers at that position.
        """
        return JointState.from_mapping({self.connection(): position})


# %% grasp stages


class GraspStage(IntEnum):
    """
    The poses of a grasp, in the order of the grasp's pose sequence.
    """

    APPROACH = 0
    """
    Above the body, before coming down.
    """

    GRASP = 1
    """
    At the body, where the fingers close.
    """

    LIFT = 2
    """
    Above where the body was, after lifting it.
    """


@dataclass(eq=False, repr=False)
class GraspStageGoal(Sequence):
    """
    Resolves a grasp pose from the body's pose once the motions before it have run.
    """

    motion: GraspStageMotion = field(kw_only=True)
    """
    The motion whose target is resolved.
    """

    def expand(self, context: MotionStatechartContext) -> None:
        self.nodes = [self.motion.resolved_motion().motion_chart]
        super().expand(context)


@dataclass
class GraspStageMotion(BaseMotion):
    """
    Moves the hand to one pose of a grasp, computed from where the body is when the
    motion runs rather than where it was when the plan started.
    """

    arm: Arms
    """
    The arm that grasps.
    """

    body: Body
    """
    The body grasped.
    """

    grasp_description: GraspDescription
    """
    How the body is grasped.
    """

    stage: GraspStage
    """
    The pose of the grasp to reach.
    """

    max_linear_velocity: Optional[float] = None
    """
    The hand's largest linear speed, in metres per second, or None for no limit.
    """

    max_angular_velocity: Optional[float] = None
    """
    The hand's largest angular speed, in radians per second, or None for no limit.
    """

    requires_individual_execution: ClassVar[bool] = True
    """
    The target is resolved only after the motions before it ran.
    """

    @property
    def target(self) -> Pose:
        """
        :return: The hand's pose for the stage, from the body's current pose.
        """
        return self.grasp_description.grasp_pose_sequence(self.body)[self.stage]

    @property
    def _motion_chart(self) -> MotionStatechartNode:
        return GraspStageGoal(motion=self)

    def resolved_motion(self) -> MoveToolCenterPointMotion:
        """
        :return: The tool motion to the stage's pose, from the body's current pose.
        """
        motion = MoveToolCenterPointMotion(
            self.target,
            self.arm,
            max_linear_velocity=self.max_linear_velocity,
            max_angular_velocity=self.max_angular_velocity,
        )
        motion.plan_node = self.plan_node
        return motion


# %% screws


@dataclass
class PickUpScrewAction(PickUpAction):
    """
    Picks up a screw; the fingers close until they stall on its shaft.
    """

    tolerate_grasp_stall: bool = True
    """
    The fingers stop where the shaft stops them.
    """


@dataclass
class PickUpLooseScrewAction(PickUpScrewAction):
    """
    Picks up a screw lying among others: the fingers open only as far as the screw's
    head needs above the box, and the screw is lifted without turning.
    """

    approach_finger_position: float = field(default=0.20, kw_only=True)
    """
    The finger joint's position while the hand comes down, in radians.
    """

    lift_angular_velocity: float = field(default=0.3, kw_only=True)
    """
    The hand's largest angular speed while lifting, in radians per second.
    """

    @property
    def _action_plan(self) -> PlanNode:
        hand = ViewManager.get_end_effector_view(self.arm, self.robot)
        return sequential(
            [
                self.stage_motion(
                    GraspStage.APPROACH,
                    max_linear_velocity=self.pre_approach_linear_velocity,
                ),
                MoveGripperMotion(
                    GripperState.OPEN,
                    self.arm,
                    goal_state=FingerJoint(hand).opened_to(
                        self.approach_finger_position
                    ),
                ),
                self.stage_motion(
                    GraspStage.GRASP,
                    max_linear_velocity=self.final_approach_linear_velocity,
                ),
                self.create_grasp_motion(),
                AttachNode(body=self.object_designator, new_parent=hand.tool_frame),
                self.stage_motion(
                    GraspStage.LIFT,
                    max_linear_velocity=self.lift_linear_velocity,
                    max_angular_velocity=self.lift_angular_velocity,
                ),
            ]
        )

    def stage_motion(
        self,
        stage: GraspStage,
        max_linear_velocity: float,
        max_angular_velocity: Optional[float] = None,
    ) -> GraspStageMotion:
        """
        :param stage: The pose of the grasp to reach.
        :param max_linear_velocity: The hand's largest linear speed, in metres per
            second.
        :param max_angular_velocity: The hand's largest angular speed, in radians per
            second, or None for no limit.
        :return: The motion to that pose, aimed where the screw is when it runs.
        """
        return GraspStageMotion(
            self.arm,
            self.object_designator,
            self.grasp_description,
            stage,
            max_linear_velocity=max_linear_velocity,
            max_angular_velocity=max_angular_velocity,
        )


# %% screwdriver


@dataclass
class StraightLiftMotion(AnchoredToolCenterPointMotion):
    """
    Lifts a held tool along a straight line with its orientation kept, so the blade
    clears its cradle's guides before moving sideways.
    """

    @property
    def _motion_chart(self) -> ManipulationWithGaze:
        chart = super()._motion_chart
        tool = ViewManager.get_end_effector_view(self.arm, self.robot).tool_frame
        chart.nodes[0] = Parallel(
            [
                CartesianPositionStraight(
                    root_link=self.world.root,
                    tip_link=tool,
                    goal_point=self.target.to_position(),
                    reference_velocity=self.max_linear_velocity,
                    threshold=self.resolved_position_threshold(),
                ),
                CartesianOrientation(
                    root_link=self.world.root,
                    tip_link=tool,
                    goal_orientation=self.target.to_rotation_matrix(),
                    reference_velocity=self.max_angular_velocity,
                    threshold=self.resolved_orientation_threshold(),
                    weight=DefaultWeights.WEIGHT_ABOVE_COLLISION_AVOIDANCE,
                ),
            ]
        )
        return chart


@dataclass
class PickUpDriverAction(PickUpScrewAction):
    """
    Opens the hand before coming to the cradle, grasps the handle and lifts the
    screwdriver straight out with its orientation kept.
    """

    grasp_position_tolerance: float = field(default=0.001, kw_only=True)
    """
    How far the hand may stop from its approach and grasp poses, in metres.
    """

    lift_angular_velocity: float = field(default=0.3, kw_only=True)
    """
    The hand's largest angular speed while lifting, in radians per second.
    """

    @property
    def _action_plan(self) -> PlanNode:
        before, target, after = self.grasp_description.grasp_pose_sequence(
            self.object_designator
        )
        hand = ViewManager.get_end_effector_view(self.arm, self.robot)
        return sequential(
            [
                MoveGripperMotion(GripperState.OPEN, self.arm),
                MoveToolCenterPointMotion(
                    before,
                    self.arm,
                    position_threshold=self.grasp_position_tolerance,
                    max_linear_velocity=self.pre_approach_linear_velocity,
                ),
                MoveToolCenterPointMotion(
                    target,
                    self.arm,
                    position_threshold=self.grasp_position_tolerance,
                    max_linear_velocity=self.final_approach_linear_velocity,
                ),
                self.create_grasp_motion(),
                AttachNode(body=self.object_designator, new_parent=hand.tool_frame),
                StraightLiftMotion(
                    after,
                    self.arm,
                    max_linear_velocity=self.lift_linear_velocity,
                    max_angular_velocity=self.lift_angular_velocity,
                ),
            ]
        )


# %% screw box


@dataclass
class PickUpBoxAction(PickUpScrewAction):
    """
    Grasps the screw box by its carry bar and lifts it upright, so its loose contents
    stay in.
    """

    lift_angular_velocity: float = field(default=0.3, kw_only=True)
    """
    The hand's largest angular speed while lifting, in radians per second.
    """

    @property
    def _action_plan(self) -> PlanNode:
        _, _, lift = self.grasp_description.grasp_pose_sequence(self.object_designator)
        return sequential(
            [
                self._grasp_attempt_plan(),
                MoveToolCenterPointMotion(
                    lift,
                    self.arm,
                    max_linear_velocity=self.lift_linear_velocity,
                    max_angular_velocity=self.lift_angular_velocity,
                ),
            ]
        )
