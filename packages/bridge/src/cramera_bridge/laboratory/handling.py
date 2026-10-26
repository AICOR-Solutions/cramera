"""
How the PR2 handles laboratory glass, shared by the laboratory's robot demos: its
posture at the bench, the clearances it keeps, and how it takes, carries and sets down
vessels with its left gripper.
"""

from __future__ import annotations

import math
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import List, Optional

from coraplex.datastructures.dataclasses import Context, MotionToleranceConfig
from coraplex.datastructures.enums import MovementType
from coraplex.plans.plan import Plan
from semantic_digital_twin.collision_checking.collision_rules import (
    AllowCollisionBetweenGroups,
    AvoidCollisionBetweenGroups,
)
from semantic_digital_twin.datastructures.definitions import (
    StaticJointState,
    TorsoState,
)
from semantic_digital_twin.grasping.grasp_candidates import GraspCandidate
from semantic_digital_twin.semantic_annotations.mixins import HasGraspCandidates
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.semantic_annotations.semantic_annotations import Container
from semantic_digital_twin.spatial_types import Pose, Quaternion
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

from cramera_bridge.laboratory.grasping import RackPlaceAction, VesselPickUpAction
from cramera_bridge.laboratory.world import LaboratoryEnvironment
from cramera_bridge.robot_task import RobotTaskDemo
from cramera_bridge.visualization import LiveVisualization
from cramera_protocol.live_messages import SavedScene

# %% speeds


@dataclass(frozen=True)
class TransferSpeeds:
    """
    How fast the tool moves in each stage of moving a vessel, in metres per second: slow
    near the glass and the openings it is taken from or set into.
    """

    approach: float = 0.12
    """
    Towards the vessel.
    """

    final_approach: float = 0.025
    """
    The last part of the way to the grasp.
    """

    lift: float = 0.04
    """
    Lifting the vessel out of its slot.
    """

    transport: float = 0.08
    """
    Carrying the vessel above the target.
    """

    placing: float = 0.02
    """
    Lowering the vessel into its slot.
    """

    retract: float = 0.08
    """
    Moving away after letting go.
    """


# %% grips


@dataclass(frozen=True)
class VesselGrip:
    """
    How the left gripper takes a vessel, lifts it out of where it stands and sets it
    down: suited to the opening the vessel is set into.
    """

    orientation: Quaternion
    """
    The tool's orientation relative to the upright vessel.
    """

    height: float
    """
    How high above the vessel's bottom the tool takes it, in metres.
    """

    approach_clearance: float
    """
    How far from the vessel's axis the approach to it starts, in metres.
    """

    grasp_tolerance: float
    """
    How far the tool may stop from the grasp before the fingers close, in metres: the
    coupled fingers close about the tool, so this offset takes from one pad's clearance.
    """

    lift: float
    """
    How far the vessel is lifted out of where it stood, in metres.
    """

    lowering: float
    """
    How far above its target the vessel is lowered from, in metres.
    """

    upright: bool = False
    """
    Whether the lift keeps the vessel upright; CRAM's pickup lifts by the tool's
    position only and lets the vessel tilt.
    """


# %% demo


@dataclass
class VesselTaskDemo(RobotTaskDemo, ABC):
    """
    A PR2 task at the laboratory bench that takes, carries and sets down vessels with
    its left gripper.
    """

    live_url_file: Optional[Path] = None
    """
    Where the owning viewer reads this run's live address, or None for standalone use.
    """

    lift: float = 0.16
    """
    How high a vessel is lifted out of its slot, clear of its neighbours, in metres.
    """

    position_tolerance: float = 0.0005
    """
    The tool's position tolerance at a slot, in metres.
    """

    orientation_tolerance: float = 0.003
    """
    The tool's orientation tolerance at a slot, in radians.
    """

    obstacle_clearance: float = 0.003
    """
    How far the gripper and the vessels keep from the laboratory, in metres.
    """

    closing_velocity: float = 0.1
    """
    How fast the fingers close, in radians per second.
    """

    finger_tolerance: float = 0.0001
    """
    How close the fingers come to their stop, in radians.
    """

    pad_clearance: float = 0.00025
    """
    The clearance each pad keeps from the glass, in metres.
    """

    approach_margin: float = 0.1
    """
    How far beyond a vessel's radius the approach starts, in metres.
    """

    tool_orientation: Quaternion = field(
        default_factory=lambda: Quaternion.from_rpy(0, math.pi / 2, -math.pi / 4)
    )
    """
    The tool's orientation relative to the upright vessel: from above, diagonal to the
    rack's rows.
    """

    speeds: TransferSpeeds = field(default_factory=lambda: TransferSpeeds())
    """
    How fast the tool moves in each stage.
    """

    plan: Optional[Plan] = field(init=False, default=None)
    """
    The current run's plan, once it is built.
    """

    @property
    def laboratory(self) -> LaboratoryEnvironment:
        """
        The laboratory environment.
        """
        return self.environment

    def vessel_in(self, slot: str) -> str:
        """
        :param slot: A rack slot a vessel starts in.
        :return: The vessel's key.
        """
        return {
            placement.slot: placement.key for placement in self.laboratory.bench.tubes
        }[slot]

    # %% context

    def posture(self, world: World) -> PR2:
        """
        Park the arms, raise the torso and take the drive out of the controller; the arm
        motions hold the base where it stands.

        :param world: The world built for the task.
        :return: The robot.
        """
        robot = world.get_semantic_annotations_by_type(PR2)[0]
        robot.mobile_base.full_body_controlled = False
        with world.modify_world():
            world.set_dofs_has_hardware_interface(robot.drive.active_dofs, False)
        for arm in (robot.left_arm, robot.right_arm):
            arm.get_joint_state_by_type(StaticJointState.PARK).apply_to(world)
        robot.torso.get_joint_state_by_type(TorsoState.HIGH).apply_to(world)
        for connection in robot.torso.active_connections:
            connection.position = connection.dof.limits.upper.position
        return robot

    def keep_clear(self, world: World, robot: PR2, vessels: List[Body]) -> None:
        """
        Keep the gripper and the handled vessels clear of the laboratory and of each
        other, except for the intended contacts of a grasp between the gripper and a
        handled vessel.

        :param world: The world built for the task.
        :param robot: The robot.
        :param vessels: The vessels the task handles.
        """
        gripper = robot.left_arm.end_effector.bodies_with_collision
        laboratory = [
            body
            for body in world.bodies
            if body not in robot.bodies and body.has_collision()
        ]
        with world.modify_world():
            world.collision_manager.add_ignore_collision_rule(
                AllowCollisionBetweenGroups(body_group_a=gripper, body_group_b=vessels)
            )
            world.collision_manager.add_default_rule(
                AvoidCollisionBetweenGroups(
                    body_group_a=gripper,
                    body_group_b=[body for body in laboratory if body not in vessels],
                    buffer_zone_distance=self.obstacle_clearance,
                    violated_distance=0.0,
                )
            )
            for vessel in vessels:
                world.collision_manager.add_default_rule(
                    AvoidCollisionBetweenGroups(
                        body_group_a=[vessel],
                        body_group_b=[
                            body for body in laboratory if body is not vessel
                        ],
                        buffer_zone_distance=self.obstacle_clearance,
                        violated_distance=0.0,
                    )
                )

    def tight_context(self, world: World, robot: PR2) -> Context:
        """
        :param world: The world built for the task.
        :param robot: The robot.
        :return: The context with tight tolerances at the slots.
        """
        return Context(
            world=world,
            robot=robot,
            motion_tolerances=MotionToleranceConfig(
                default_tcp_position_threshold=self.position_tolerance,
                tool_orientation_threshold=self.orientation_tolerance,
            ),
        )

    # %% handling

    @property
    def top_grip(self) -> VesselGrip:
        """
        Taking a vessel from above at its grasp height, the tool at
        :attr:`tool_orientation`, lifting and lowering it by :attr:`lift`.
        """
        return VesselGrip(
            orientation=self.tool_orientation,
            height=self.laboratory.vessels.grasp_height,
            approach_clearance=self.approach_clearance,
            grasp_tolerance=self.position_tolerance,
            lift=self.lift,
            lowering=self.lift,
        )

    def grasp(
        self, context: Context, body: Body, grip: Optional[VesselGrip] = None
    ) -> GraspCandidate:
        """
        :param context: The world and the robot.
        :param body: The upright vessel.
        :param grip: How the vessel is taken; :attr:`top_grip` by default.
        :return: The left gripper's grasp on the vessel.
        """
        grip = self.top_grip if grip is None else grip
        return self.grasp_at(
            context,
            Container(root=body),
            Pose.from_xyz_quaternion(
                0, 0, grip.height, *grip.orientation.to_np(), reference_frame=body
            ),
        )

    @staticmethod
    def grasp_at(
        context: Context, graspable: HasGraspCandidates, tool_pose: Pose
    ) -> GraspCandidate:
        """
        :param context: The world and the robot.
        :param graspable: What the gripper takes.
        :param tool_pose: Where the left gripper's tool frame is while it holds it.
        :return: The left gripper's grasp with its tool frame at that pose.
        """
        gripper = context.robot.left_arm.end_effector
        return GraspCandidate(
            graspable,
            Pose(
                position=tool_pose.homogeneous_matrix
                @ gripper.tool_P_grasp_when_closed,
                orientation=(
                    tool_pose.rotation_matrix @ gripper.tool_R_grasp
                ).quaternion,
                reference_frame=tool_pose.reference_frame,
            ),
        )

    @property
    def approach_clearance(self) -> float:
        """
        How far from a vessel's axis the approach to it starts, in metres.
        """
        return self.laboratory.vessels.outer_radius + self.approach_margin

    def pick_up(
        self,
        context: Context,
        grasp: GraspCandidate,
        grip: Optional[VesselGrip] = None,
    ) -> VesselPickUpAction:
        """
        :param context: The world and the robot.
        :param grasp: The left gripper's grasp on a vessel.
        :param grip: How the vessel is taken; :attr:`top_grip` by default.
        :return: Taking the vessel and lifting it out of where it stands.
        """
        grip = self.top_grip if grip is None else grip
        return VesselPickUpAction(
            grasp=grasp,
            arm=context.robot.left_arm,
            approach_clearance=grip.approach_clearance,
            retreat_distance=grip.lift,
            pre_approach_linear_velocity=self.speeds.approach,
            final_approach_linear_velocity=self.speeds.final_approach,
            lift_linear_velocity=self.speeds.lift,
            grasp_closing_velocity=self.closing_velocity,
            grasp_joint_position_threshold=self.finger_tolerance,
            contact_clearance=self.pad_clearance,
            grasp_position_threshold=grip.grasp_tolerance,
            lift_movement=(
                MovementType.CARTESIAN if grip.upright else MovementType.TRANSLATION
            ),
        )

    def place(
        self,
        grasp: GraspCandidate,
        target: Pose,
        grip: Optional[VesselGrip] = None,
    ) -> RackPlaceAction:
        """
        :param grasp: The grasp the vessel is held by.
        :param target: Where the vessel's bottom ends.
        :param grip: How the vessel was taken; :attr:`top_grip` by default.
        :return: Lowering the vessel into its target and letting go.
        """
        grip = self.top_grip if grip is None else grip
        return RackPlaceAction(
            grasp.graspable,
            target,
            approach_clearance=grip.approach_clearance,
            retreat_distance=grip.lowering,
            transport_linear_velocity=self.speeds.transport,
            placing_linear_velocity=self.speeds.placing,
            retract_linear_velocity=self.speeds.retract,
        )

    # %% running

    def on_live_started(self, visualization: LiveVisualization) -> None:
        """
        :param visualization: The started server whose real port the viewer needs.
        """
        if self.live_url_file is not None:
            self.live_url_file.parent.mkdir(parents=True, exist_ok=True)
            self.live_url_file.write_text(visualization.url(), encoding="utf-8")

    def run(self) -> SavedScene:
        """
        :return: The measured recording; the live announcement is withdrawn on failure
            as well as success.
        """
        if self.live_url_file is not None:
            self.live_url_file.unlink(missing_ok=True)
        try:
            return super().run()
        finally:
            if self.live_url_file is not None:
                self.live_url_file.unlink(missing_ok=True)
