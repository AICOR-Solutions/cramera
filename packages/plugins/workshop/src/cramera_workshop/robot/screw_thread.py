"""
Two-handed screw driving as native CRAM actions: the supporting hand holds the screw at
the pilot hole, the screwdriver's blade is seated in its slot, and an ideal helical
connection between screw and workpiece is installed only after the blade and the pilot
are measured aligned.

The helical connection is a kinematic idealization: it relates tool rotation to screw
travel and simulates no tightening torque, friction, wood cutting or damage.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from typing_extensions import ClassVar, List, Optional

from coraplex.datastructures.enums import Arms, ExecutionType, TaskStatus
from coraplex.plans.executables import Executable, GiskardExecutable
from coraplex.plans.factories import sequential
from coraplex.plans.failures import PlanFailure
from coraplex.plans.plan_node import ExecutionBoundaryNode, PlanNode
from coraplex.robot_plans.actions.base import ActionDescription
from coraplex.robot_plans.motions.base import BaseMotion
from coraplex.robot_plans.motions.gripper import (
    MoveGripperMotion,
    MoveToolCenterPointMotion,
)
from coraplex.view_manager import ViewManager
from cramera_protocol.workshop import WorkshopDescription
from cramera_workshop.robot.gaze import ManipulationWithGaze, follow_tool, hold_base
from giskardpy.motion_statechart.context import MotionStatechartContext
from giskardpy.motion_statechart.goals.open_close import Close
from giskardpy.motion_statechart.goals.templates import Sequence
from giskardpy.motion_statechart.graph_node import MotionStatechartNode
from giskardpy.motion_statechart.tasks.cartesian_tasks import CartesianPose
from semantic_digital_twin.datastructures.definitions import GripperState
from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.spatial_types import (
    HomogeneousTransformationMatrix,
    Pose,
    Vector3,
)
from semantic_digital_twin.spatial_types.derivatives import DerivativeMap
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import ScrewConnection
from semantic_digital_twin.world_description.degree_of_freedom import (
    DegreeOfFreedomLimits,
)
from semantic_digital_twin.world_description.world_entity import Body

# %% names


class ThreadTask(StrEnum):
    """
    The names of the thread's connection and tasks in recordings.
    """

    THREAD = "ideal_pilot_thread"
    """
    The helical connection between screw and workpiece.
    """

    DRIVE = "Drive threaded screw"
    """
    Turning the screw with the driver seated in its slot.
    """

    HOLD_SUPPORT = "Hold supporting gripper"
    """
    The supporting hand staying where it is.
    """


class EngagementProblem(StrEnum):
    """
    Why the thread cannot be engaged or turned.
    """

    INVALID_GEOMETRY = (
        "The thread's dimensions and tolerances must be finite and positive."
    )
    """
    A dimension or tolerance is not finite and positive.
    """

    ALREADY_THREADED = "The screw already has a threaded connection."
    """
    The screw is engaged already.
    """

    BLADE_OFF_SLOT = "The blade tip is not seated in the screw's slot."
    """
    The blade is too far from the slot floor.
    """

    BLADE_TURNED = "The blade's orientation does not match the screw's slot."
    """
    The blade is turned against the slot.
    """

    OFF_PILOT_AXIS = "The screw is not aligned with the pilot axis."
    """
    The screw's tip or shaft is off the pilot axis.
    """

    NOT_AT_MOUTH = "The screw's tip must be at the pilot hole's entrance."
    """
    The screw's tip is not at the entrance.
    """

    NOT_THREADED = "The screw must engage the pilot thread before it is turned."
    """
    Turning a screw without a threaded connection.
    """

    INVALID_TURNS = "The engagement turns must be finite and positive."
    """
    The requested turns are not finite and positive.
    """

    NOT_SIMULATED = "The ideal thread needs simulated robot execution."
    """
    The plan runs on a real robot.
    """


@dataclass
class ScrewEngagementFailed(PlanFailure):
    """
    The measured blade, screw or pilot alignment does not allow the thread.
    """

    problem: EngagementProblem
    """
    What is wrong.
    """

    def error_message(self) -> str:
        return self.problem.value


# %% dimensions


@dataclass(frozen=True)
class ThreadDimensions:
    """
    The dimensions of screw driving, from the workshop description.
    """

    pitch: float
    """
    The thread's advance per turn, in metres.
    """

    depth: float
    """
    How far below the pilot's entrance the screw's tip ends, in metres.
    """

    mouth_height: float
    """
    The pilot's entrance on the workpiece's local z axis, in metres.
    """

    slot_floor: float
    """
    The slot floor's height above the screw's tip, where the blade seats, in metres.
    """

    @classmethod
    def of_workshop(cls, workshop: WorkshopDescription) -> ThreadDimensions:
        """
        :param workshop: A workshop description.
        :return: Its screw driving dimensions.
        """
        screw = workshop.screw
        return cls(
            pitch=screw.thread_pitch,
            depth=workshop.assembly.maximum_depth,
            mouth_height=workshop.assembly.local_mouth.z,
            slot_floor=screw.head_top - screw.slot_size.z,
        )

    def is_valid(self) -> bool:
        """
        :return: Whether every dimension is finite and positive.
        """
        return all(
            math.isfinite(value) and value > 0
            for value in (self.pitch, self.depth, self.mouth_height, self.slot_floor)
        )


@dataclass(frozen=True)
class ThreadLimits:
    """
    The tolerances and speeds of screw driving.
    """

    position_tolerance: float = 0.002
    """
    How far blade and screw may be off their targets at engagement, in metres.
    """

    angle_tolerance: float = 0.025
    """
    How far blade and screw may be turned off their targets at engagement, in radians.
    """

    maximum_angular_velocity: float = 1.5
    """
    The helical connection's largest speed, in radians per second.
    """

    maximum_turns_per_stage: float = 2.0
    """
    The most turns one controller stage drives, so long threads get enough control
    periods.
    """

    tool_linear_velocity: float = 0.08
    """
    The held tool's largest speed while aligning, in metres per second.
    """

    tool_angular_velocity: float = 0.35
    """
    The held tool's largest angular speed while aligning, in radians per second.
    """

    tool_position_threshold: float = 0.0005
    """
    How close the held tool must come to its target, in metres.
    """

    tool_orientation_threshold: float = 0.008
    """
    How close the held tool's orientation must come to its target, in radians.
    """

    support_position_threshold: float = 0.002
    """
    How far the supporting hand may drift while it holds, in metres.
    """

    support_orientation_threshold: float = 0.01
    """
    How far the supporting hand may turn while it holds, in radians.
    """

    pause_interval: float = 0.01
    """
    How often a paused engagement looks whether it may go on, in seconds.
    """


THREAD_LIMITS = ThreadLimits()
"""
The limits screw driving uses.
"""

# %% engagement


@dataclass
class ScrewAssembly:
    """
    Installs the helical connection of a screw in the pilot hole, once the blade is
    seated in the screw's slot and the screw's tip is at the entrance on the pilot axis.
    """

    screw: Body
    """
    The screw, its origin at the tip and its z axis towards the head.
    """

    driver: Body
    """
    The held screwdriver, its origin at the blade's tip and its z axis towards the
    handle.
    """

    workpiece: Body
    """
    The workpiece, its pilot hole on its local z axis.
    """

    dimensions: ThreadDimensions
    """
    The thread's dimensions.
    """

    limits: ThreadLimits = THREAD_LIMITS
    """
    The engagement's tolerances.
    """

    def install(self, world: World) -> ScrewConnection:
        """
        Replace the screw's connection by the helical one, keeping its measured pose.

        :param world: The world holding the bodies.
        :return: The helical connection.
        :raises ScrewEngagementFailed: When the measured alignment does not allow it.
        """
        workpiece_T_screw = world.compute_forward_kinematics_np(
            self.workpiece, self.screw
        )
        screw_T_driver = world.compute_forward_kinematics_np(self.screw, self.driver)
        self.validate(workpiece_T_screw, screw_T_driver)
        inserted = self.dimensions.mouth_height - workpiece_T_screw[2, 3]
        remaining = float(self.dimensions.depth - inserted)
        limits = DegreeOfFreedomLimits(
            lower=DerivativeMap(
                position=-remaining * math.tau / self.dimensions.pitch,
                velocity=-self.limits.maximum_angular_velocity,
            ),
            upper=DerivativeMap(
                position=0.0, velocity=self.limits.maximum_angular_velocity
            ),
        )
        previous = self.screw.parent_connection
        with world.modify_world():
            connection = ScrewConnection.create_with_dofs(
                world=world,
                parent=self.workpiece,
                child=self.screw,
                name=PrefixedName(ThreadTask.THREAD, str(self.screw.name)),
                parent_T_connection_expression=HomogeneousTransformationMatrix(
                    workpiece_T_screw,
                    reference_frame=self.workpiece,
                    child_frame=self.screw,
                ),
                axis=Vector3.Z(),
                screw_pitch=self.dimensions.pitch,
                dof_limits=limits,
            )
            world.add_connection(connection)
            world.remove_connection(previous)
            world.delete_orphaned_dofs()
        return connection

    def validate(
        self, workpiece_T_screw: np.ndarray, screw_T_driver: np.ndarray
    ) -> None:
        """
        :param workpiece_T_screw: The screw's measured pose in the workpiece.
        :param screw_T_driver: The driver's measured pose in the screw.
        :raises ScrewEngagementFailed: When the blade is not seated, or the screw is not
            at the entrance on the pilot axis.
        """
        tolerance = self.limits.position_tolerance
        if not self.dimensions.is_valid():
            raise ScrewEngagementFailed(EngagementProblem.INVALID_GEOMETRY)
        if isinstance(self.screw.parent_connection, ScrewConnection):
            raise ScrewEngagementFailed(EngagementProblem.ALREADY_THREADED)
        slot = np.array([0.0, 0.0, self.dimensions.slot_floor])
        if np.linalg.norm(screw_T_driver[:3, 3] - slot) > tolerance:
            raise ScrewEngagementFailed(EngagementProblem.BLADE_OFF_SLOT)
        turned = math.acos(
            float(np.clip((np.trace(screw_T_driver[:3, :3]) - 1) / 2, -1, 1))
        )
        if turned > self.limits.angle_tolerance:
            raise ScrewEngagementFailed(EngagementProblem.BLADE_TURNED)
        tilted = math.acos(float(np.clip(workpiece_T_screw[2, 2], -1, 1)))
        if (
            np.linalg.norm(workpiece_T_screw[:2, 3]) > tolerance
            or tilted > self.limits.angle_tolerance
        ):
            raise ScrewEngagementFailed(EngagementProblem.OFF_PILOT_AXIS)
        inserted = self.dimensions.mouth_height - workpiece_T_screw[2, 3]
        if not -tolerance <= inserted < self.dimensions.depth:
            raise ScrewEngagementFailed(EngagementProblem.NOT_AT_MOUTH)


@dataclass(eq=False, repr=False)
class EngageThreadNode(ExecutionBoundaryNode):
    """
    Installs the helical connection when the plan reaches it, after the motions before
    it have run, and not while the plan is only being expanded.
    """

    assembly: ScrewAssembly = field(kw_only=True)
    """
    The bodies and dimensions checked right before the connection changes.
    """

    def notify(self) -> None:
        """
        Expanding the plan changes nothing in the world.
        """

    def parse(self) -> EngageThreadExecutable:
        return EngageThreadExecutable(node=self, context=self.plan.context)


@dataclass
class EngageThreadExecutable(Executable):
    """
    Installs the helical connection within the plan's pause and interrupt controls.
    """

    node: EngageThreadNode = field(kw_only=True)
    """
    The node with the bodies and dimensions.
    """

    def execute(self) -> None:
        """
        :raises ScrewEngagementFailed: On a real robot, or when the measured alignment
            does not allow the thread.
        """
        with self.node.execution_scope():
            while self.node.is_paused and not self.node.is_interrupted:
                time.sleep(self.node.assembly.limits.pause_interval)
            if self.node.is_interrupted:
                self.node.status = TaskStatus.INTERRUPTED
                return
            if GiskardExecutable.execution_type is ExecutionType.NO_EXECUTION:
                return
            if GiskardExecutable.execution_type is not ExecutionType.SIMULATED:
                raise ScrewEngagementFailed(EngagementProblem.NOT_SIMULATED)
            self.node.assembly.install(self.context.world)


# %% held tool motion


def tool_frame(motion: BaseMotion, arm: Arms) -> Body:
    """
    :param motion: A motion of the robot.
    :param arm: One of its arms.
    :return: The arm's tool frame.
    """
    return ViewManager().get_end_effector_view(arm, motion.robot).tool_frame


def hold_support(motion: BaseMotion, world: World, arm: Arms) -> CartesianPose:
    """
    :param motion: A motion of the robot.
    :param world: The world the robot is in.
    :param arm: The supporting arm.
    :return: A task keeping the supporting hand where it is.
    """
    support = tool_frame(motion, arm)
    return CartesianPose(
        name=ThreadTask.HOLD_SUPPORT,
        root_link=world.root,
        tip_link=support,
        goal_pose=Pose(reference_frame=support),
        translation_threshold=THREAD_LIMITS.support_position_threshold,
        orientation_threshold=THREAD_LIMITS.support_orientation_threshold,
    )


@dataclass(eq=False, repr=False)
class HeldBodyGoal(Sequence):
    """
    Resolves a held body's target from its measured attachment once the grasps before it
    have run.
    """

    motion: MoveHeldBodyMotion = field(kw_only=True)
    """
    The motion whose target is resolved.
    """

    def expand(self, context: MotionStatechartContext) -> None:
        chart = self.motion.resolved_motion().motion_chart
        self.nodes = [chart]
        if self.motion.support_arm is not None:
            self.nodes = [
                ManipulationWithGaze(
                    nodes=[
                        chart,
                        hold_support(
                            self.motion, context.world, self.motion.support_arm
                        ),
                    ]
                )
            ]
        super().expand(context)


@dataclass
class MoveHeldBodyMotion(BaseMotion):
    """
    Moves a held body to a pose relative to a reference body, or withdraws a bare tool
    along its own axis.
    """

    arm: Arms
    """
    The arm holding the body.
    """

    reference: Optional[Body] = None
    """
    The body the target is relative to; the tool frame when None.
    """

    body: Optional[Body] = None
    """
    The held body whose origin reaches the target; the tool frame when None.
    """

    height: float = 0.0
    """
    The target's height along the reference's z axis, in metres.
    """

    retreat: float = 0.0
    """
    How far back along the tool's x axis the tool withdraws, in metres.
    """

    support_arm: Optional[Arms] = None
    """
    The other hand, kept where it is during the motion, or None.
    """

    requires_individual_execution: ClassVar[bool] = True
    """
    The target is resolved only after the motions before it ran.
    """

    @property
    def _motion_chart(self) -> MotionStatechartNode:
        return HeldBodyGoal(motion=self)

    def resolved_motion(self) -> MoveToolCenterPointMotion:
        """
        :return: The tool motion that puts the held body at its target, computed from
            the measured attachment.
        """
        tool = tool_frame(self, self.arm)
        reference = self.reference if self.reference is not None else tool
        reference_T_target = HomogeneousTransformationMatrix.from_xyz_rpy(
            x=-self.retreat, z=self.height
        ).to_np()
        world_T_target = (
            self.world.compute_forward_kinematics_np(self.world.root, reference)
            @ reference_T_target
        )
        if self.body is not None:
            world_T_target = world_T_target @ self.world.compute_forward_kinematics_np(
                self.body, tool
            )
        motion = MoveToolCenterPointMotion(
            target=HomogeneousTransformationMatrix(
                world_T_target, reference_frame=self.world.root
            ).to_pose(),
            arm=self.arm,
            max_linear_velocity=THREAD_LIMITS.tool_linear_velocity,
            max_angular_velocity=THREAD_LIMITS.tool_angular_velocity,
            position_threshold=THREAD_LIMITS.tool_position_threshold,
            orientation_threshold=THREAD_LIMITS.tool_orientation_threshold,
        )
        motion.plan_node = self.plan_node
        return motion


# %% turning


@dataclass(eq=False, repr=False)
class TurnScrewGoal(Sequence):
    """
    Resolves the installed helical connection once the engagement before it has run.
    """

    motion: TurnScrewMotion = field(kw_only=True)
    """
    The turning motion.
    """

    def expand(self, context: MotionStatechartContext) -> None:
        self.nodes = [
            self.motion.resolved_chart(target) for target in self.motion.joint_targets()
        ]
        super().expand(context)


@dataclass
class TurnScrewMotion(BaseMotion):
    """
    Turns a threaded screw through its helical connection with the driver kept in the
    slot, the supporting hand held, the base held and the head following the driver.
    """

    screw: Body
    """
    The threaded screw.
    """

    driver: Body
    """
    The held screwdriver.
    """

    driver_arm: Arms = Arms.RIGHT
    """
    The hand turning the driver.
    """

    support_arm: Arms = Arms.LEFT
    """
    The other hand, kept where it is.
    """

    turns: Optional[float] = None
    """
    The clockwise turns from the engagement; the whole thread when None.
    """

    requires_individual_execution: ClassVar[bool] = True
    """
    The connection is resolved only after the engagement ran.
    """

    @property
    def _motion_chart(self) -> MotionStatechartNode:
        return TurnScrewGoal(motion=self)

    def joint_targets(self) -> List[float]:
        """
        :return: The helical connection's targets, the remaining travel divided into
            stages of at most :attr:`ThreadLimits.maximum_turns_per_stage` turns.
        :raises ScrewEngagementFailed: When the screw is not threaded, or the turns are
            not finite and positive.
        """
        connection = self.screw.parent_connection
        if not isinstance(connection, ScrewConnection):
            raise ScrewEngagementFailed(EngagementProblem.NOT_THREADED)
        if self.turns is not None and (
            not math.isfinite(self.turns) or self.turns <= 0
        ):
            raise ScrewEngagementFailed(EngagementProblem.INVALID_TURNS)
        final = float(connection.dof.limits.lower.position)
        if self.turns is not None:
            return [max(final, -self.turns * math.tau)]
        current = float(connection.position)
        stage = THREAD_LIMITS.maximum_turns_per_stage * math.tau
        count = max(1, int((current - final) / stage) + 1)
        return [
            current + (final - current) * index / count for index in range(1, count)
        ] + [final]

    def resolved_chart(self, target: float) -> MotionStatechartNode:
        """
        :param target: The helical connection's target.
        :return: The stage turning the screw to it.
        """
        return ManipulationWithGaze(
            nodes=[
                Close(
                    tip_link=self.driver,
                    environment_link=self.screw,
                    goal_joint_state=target,
                ),
                hold_support(self, self.world, self.support_arm),
                follow_tool(self.robot, tool_frame(self, self.driver_arm)),
                hold_base(self.world, self.robot),
            ],
            name=ThreadTask.DRIVE,
        )


# %% actions


@dataclass
class AlignScrewdriverAction(ActionDescription):
    """
    Brings the held screwdriver down the screw's axis and seats its blade in the slot,
    with the supporting hand holding the screw still.
    """

    screw: Body
    """
    The screw held at the pilot hole.
    """

    driver: Body
    """
    The held screwdriver.
    """

    dimensions: ThreadDimensions
    """
    The thread's dimensions.
    """

    driver_arm: Arms = Arms.RIGHT
    """
    The hand holding the driver.
    """

    support_arm: Arms = Arms.LEFT
    """
    The hand holding the screw.
    """

    clearance: float = 0.005
    """
    How far above the slot the blade stops before seating, in metres.
    """

    @property
    def _action_plan(self) -> PlanNode:
        return sequential(
            [
                MoveHeldBodyMotion(
                    arm=self.driver_arm,
                    reference=self.screw,
                    body=self.driver,
                    height=self.dimensions.slot_floor + self.clearance,
                    support_arm=self.support_arm,
                ),
                MoveHeldBodyMotion(
                    arm=self.driver_arm,
                    reference=self.screw,
                    body=self.driver,
                    height=self.dimensions.slot_floor,
                    support_arm=self.support_arm,
                ),
            ],
            context=self.context,
        )


@dataclass
class EngageScrewAction(ActionDescription):
    """
    Checks the blade and the pilot, installs the thread and turns the screw in a little
    while the supporting hand still holds it.
    """

    screw: Body
    """
    The screw held at the pilot hole.
    """

    driver: Body
    """
    The screwdriver seated in the slot.
    """

    workpiece: Body
    """
    The workpiece with the pilot hole.
    """

    dimensions: ThreadDimensions
    """
    The thread's dimensions.
    """

    engagement_turns: float = 0.25
    """
    The turns before the supporting hand lets go.
    """

    driver_arm: Arms = Arms.RIGHT
    """
    The hand holding the driver.
    """

    support_arm: Arms = Arms.LEFT
    """
    The hand holding the screw.
    """

    @property
    def _action_plan(self) -> PlanNode:
        return sequential(
            [
                EngageThreadNode(
                    assembly=ScrewAssembly(
                        screw=self.screw,
                        driver=self.driver,
                        workpiece=self.workpiece,
                        dimensions=self.dimensions,
                    )
                ),
                TurnScrewMotion(
                    screw=self.screw,
                    driver=self.driver,
                    driver_arm=self.driver_arm,
                    support_arm=self.support_arm,
                    turns=self.engagement_turns,
                ),
            ],
            context=self.context,
        )


@dataclass
class ReleaseScrewSupportAction(ActionDescription):
    """
    Opens the supporting hand and withdraws it, with the driver held still so the thread
    stays engaged.
    """

    screw: Body
    """
    The threaded screw.
    """

    support_arm: Arms = Arms.LEFT
    """
    The supporting hand.
    """

    retreat: float = 0.15
    """
    How far the supporting hand withdraws, in metres.
    """

    driver_arm: Arms = Arms.RIGHT
    """
    The hand holding the driver.
    """

    @property
    def _action_plan(self) -> PlanNode:
        return sequential(
            [
                MoveGripperMotion(motion=GripperState.OPEN, gripper=self.support_arm),
                MoveHeldBodyMotion(
                    arm=self.support_arm,
                    retreat=self.retreat,
                    support_arm=self.driver_arm,
                ),
            ],
            context=self.context,
        )


@dataclass
class DriveScrewAction(ActionDescription):
    """
    Drives the threaded screw to the end of its thread.
    """

    screw: Body
    """
    The threaded screw.
    """

    driver: Body
    """
    The held screwdriver.
    """

    driver_arm: Arms = Arms.RIGHT
    """
    The hand holding the driver.
    """

    support_arm: Arms = Arms.LEFT
    """
    The withdrawn hand, kept where it is.
    """

    @property
    def _action_plan(self) -> PlanNode:
        return sequential(
            [
                TurnScrewMotion(
                    screw=self.screw,
                    driver=self.driver,
                    driver_arm=self.driver_arm,
                    support_arm=self.support_arm,
                )
            ],
            context=self.context,
        )
