"""
A PR2 moves a vessel from one rack slot to another with CRAM's pickup and placing, in
the laboratory as a CRAM world, while the run is published, recorded and measured.

The measured outcome: both actions succeed, the vessel was carried and lifted clear of
the rack, it was released into the target slot within a millimetre, the other vessels
and the stopper did not move, and the gripper's pads never cut into the glass.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from typing_extensions import Dict, List, Optional, Sequence

from coraplex.datastructures.dataclasses import Context, MotionToleranceConfig
from coraplex.datastructures.enums import (
    ApproachDirection,
    Arms,
    TaskStatus,
    VerticalAlignment,
)
from coraplex.plans.factories import sequential
from coraplex.plans.plan import Plan
from coraplex.plans.plan_callbacks import PlanCallback
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from coraplex.robot_plans.actions.core.placing import PlaceAction
from giskardpy.motion_statechart.motion_statechart import MotionStatechart
from semantic_digital_twin.api import RobotSpecification
from semantic_digital_twin.collision_checking.collision_rules import (
    AllowCollisionBetweenGroups,
    AvoidCollisionBetweenGroups,
)
from semantic_digital_twin.datastructures.definitions import (
    StaticJointState,
    TorsoState,
)
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.spatial_types import (
    HomogeneousTransformationMatrix,
    Quaternion,
)
from semantic_digital_twin.world_description.world_entity import Body

from cramera_cram.exceptions import TaskFailed
from cramera_cram.robot_task import RobotTaskDemo, TaskCommand
from cramera_cram.scenes.presentation import ScenePresentation
from cramera_laboratory.grasping import (
    PadContact,
    RackPlaceAction,
    VesselGrasp,
    VesselPickUpAction,
)
from cramera_laboratory.resources import LaboratoryResource
from cramera_laboratory.world import LaboratoryEnvironment
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.scene import Camera
from cramera_protocol.geometry import Vector3

ROBOT_NAME = "pr2"
"""
The robot's part of the recording's name.
"""

TASK_IDENTIFIER = "transfer"
"""
The task's part of the recording's name.
"""

TASK = "PR2: vessel transfer A1 → A3"
"""
What the task does, as the scene picker labels it.
"""

ROBOT_START = (0.40, -0.72, math.pi / 2)
"""
Where the PR2 starts: x and y in metres and its heading, facing the bench.
"""

TRANSFER_CAMERA = Camera(
    position=Vector3(0.9, -0.9, 1.45), target=Vector3(0.22, -0.04, 0.95)
)
"""
The recording's first view: the rack from the robot's right, past its arm.
"""

POSE_TOLERANCE = 1e-10
"""
How far an untouched object may have moved, in metres.
"""

PENETRATION_TOLERANCE = 0.000001
"""
How far a pad may numerically reach into the glass, in metres.
"""

SINGLE_ACTION = 1
"""
How many nodes of each action the plan holds.
"""

# %% names


class TransferMeasurement(StrEnum):
    """
    What the transfer demo measures.
    """

    POSITION_ERROR = "positionError"
    """
    The distance between the vessel's bottom and the target slot, in metres.
    """

    ORIENTATION_ERROR = "orientationError"
    """
    The angle between the vessel and the target slot's orientation, in radians.
    """

    MAXIMUM_LIFT = "maximumLift"
    """
    How high the vessel was lifted above its slot, in metres.
    """

    CARRIED_TICKS = "carriedTicks"
    """
    How many controller ticks the gripper carried the vessel.
    """

    SMALLEST_PAD_CLEARANCE = "smallestPadClearance"
    """
    The smallest clearance between a pad and the glass while carried, in metres.
    """

    SMALLEST_COLLISION_DISTANCE = "smallestCollisionDistance"
    """
    The smallest distance between bodies whose collisions are avoided, in metres.
    """


class TransferFailure(StrEnum):
    """
    Why a transfer failed.
    """

    ACTIONS = "the pickup or the placing did not succeed: {statuses}"
    """
    An action ended in another state.
    """

    NOT_CARRIED = "the gripper never carried the vessel"
    """
    The vessel was never attached to the gripper.
    """

    NOT_LIFTED = "the vessel rose only {lift:.4f} m above its slot"
    """
    The vessel was not lifted clear of the rack.
    """

    NOT_RELEASED = "the vessel is still held"
    """
    The vessel is not attached to the world after placing.
    """

    MISPLACED = "the vessel ended {error:.4f} m from its target slot"
    """
    The vessel ended too far from the target.
    """

    TURNED = "the vessel ended turned by {error:.4f} rad"
    """
    The vessel ended turned.
    """

    DISTURBED = "another vessel or the stopper moved"
    """
    An object that was not picked moved.
    """

    PADS = "a gripper pad cut into the glass by {depth:.6f} m"
    """
    A pad intersected the glass while carrying it.
    """

    COLLISION = "bodies came {distance:.5f} m into each other"
    """
    A checked collision pair penetrated.
    """


# %% observation


@dataclass
class TransferObservation(PlanCallback):
    """
    Measures the vessel and its neighbours on every controller tick of the run.
    """

    context: Context = field(kw_only=True)
    """
    The world and the robot.
    """

    body: Body = field(kw_only=True)
    """
    The vessel moved.
    """

    pads: PadContact = field(kw_only=True)
    """
    Measures the pads' clearance from the glass.
    """

    others: List[Body] = field(kw_only=True)
    """
    The objects that must stay where they are.
    """

    start: np.ndarray = field(init=False)
    """
    The vessel's transform before the run.
    """

    other_starts: Dict[int, np.ndarray] = field(init=False)
    """
    The other objects' transforms before the run, by their position in :attr:`others`.
    """

    carried_ticks: int = field(init=False, default=0)
    """
    How many ticks the gripper carried the vessel.
    """

    maximum_lift: float = field(init=False, default=0.0)
    """
    How high the vessel rose above its start, in metres.
    """

    smallest_pad_clearance: Optional[float] = field(init=False, default=None)
    """
    The smallest pad clearance while carried, in metres.
    """

    smallest_collision_distance: Optional[float] = field(init=False, default=None)
    """
    The smallest distance of a checked collision pair, in metres.
    """

    others_still: bool = field(init=False, default=True)
    """
    Whether the other objects stayed where they were on every tick.
    """

    def __post_init__(self) -> None:
        self.start = self.body.global_pose.to_np().copy()
        self.other_starts = {
            index: other.global_pose.to_np().copy()
            for index, other in enumerate(self.others)
        }

    def carried(self) -> bool:
        """
        :return: Whether the vessel hangs from the left gripper's tool frame.
        """
        return (
            self.body.parent_connection.parent
            is self.context.robot.left_arm.end_effector.tool_frame
        )

    def on_motion_tick(self, statechart: MotionStatechart) -> None:
        """
        :param statechart: The statechart that ticked.
        """
        if self.carried():
            self.carried_ticks += 1
            lift = float(self.body.global_pose.to_np()[2, 3]) - self.start[2, 3]
            self.maximum_lift = max(self.maximum_lift, lift)
            clearance = self.pads.clearances().smallest
            self.smallest_pad_clearance = (
                clearance
                if self.smallest_pad_clearance is None
                else min(self.smallest_pad_clearance, clearance)
            )
        self.others_still = self.others_still and self.untouched()
        contacts = self.context.world.collision_manager.compute_collisions().contacts
        if contacts:
            distance = min(float(contact.distance) for contact in contacts)
            self.smallest_collision_distance = (
                distance
                if self.smallest_collision_distance is None
                else min(self.smallest_collision_distance, distance)
            )

    def untouched(self) -> bool:
        """
        :return: Whether every other object is where it started.
        """
        return all(
            np.allclose(
                other.global_pose.to_np(),
                self.other_starts[index],
                atol=POSE_TOLERANCE,
                rtol=0,
            )
            for index, other in enumerate(self.others)
        )


# %% demo


@dataclass(frozen=True)
class TransferSpeeds:
    """
    How fast the tool moves in each stage of the transfer, in metres per second: slow
    near the glass and the rack's openings.
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


@dataclass
class VesselTransferDemo(RobotTaskDemo):
    """
    A PR2 at the bench moves a vessel between two rack slots with its left arm.
    """

    source_slot: str = "A1"
    """
    The slot the vessel starts in.
    """

    target_slot: str = "A3"
    """
    The slot the vessel is placed in.
    """

    lift: float = 0.16
    """
    How high the vessel is lifted out of the rack, clear of its neighbours, in metres.
    """

    position_tolerance: float = 0.0005
    """
    The tool's position tolerance at the rack, in metres.
    """

    orientation_tolerance: float = 0.003
    """
    The tool's orientation tolerance at the rack, in radians.
    """

    obstacle_clearance: float = 0.003
    """
    How far the gripper and the carried vessel keep from the laboratory, in metres.
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
    How far beyond the vessel's radius the approach starts, in metres.
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

    observation: Optional[TransferObservation] = field(init=False, default=None)
    """
    The measurements of the current run, once its plan is built.
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

    def vessel_key(self) -> str:
        """
        :return: The vessel starting in the source slot.
        """
        return {
            placement.slot: placement.key for placement in self.laboratory.bench.tubes
        }[self.source_slot]

    def build_context(self, world) -> Context:
        """
        Park the arms, raise the torso, and keep the gripper and the vessel clear of the
        laboratory, except for the intended contacts of the grasp.

        :param world: The world built for the task.
        :return: The context with tight tolerances at the rack.
        """
        robot = world.get_semantic_annotations_by_type(PR2)[0]
        robot.mobile_base.full_body_controlled = False
        for arm in (robot.left_arm, robot.right_arm):
            arm.get_joint_state_by_type(StaticJointState.PARK).apply_to(world)
        robot.get_torso().get_joint_state_by_type(TorsoState.HIGH).apply_to(world)
        for connection in robot.get_torso().active_connections:
            connection.position = connection.dof.limits.upper.position
        body = world.get_body_by_name(self.vessel_key())
        gripper = robot.left_arm.end_effector.bodies_with_collision
        obstacles = [
            item
            for item in world.bodies
            if item not in robot.bodies and item is not body and item.collision
        ]
        with world.modify_world():
            world.collision_manager.add_ignore_collision_rule(
                AllowCollisionBetweenGroups(body_group_a=gripper, body_group_b=[body])
            )
            for group in (gripper, [body]):
                world.collision_manager.add_default_rule(
                    AvoidCollisionBetweenGroups(
                        body_group_a=group,
                        body_group_b=obstacles,
                        buffer_zone_distance=self.obstacle_clearance,
                        violated_distance=0.0,
                    )
                )
        return Context(
            world=world,
            robot=robot,
            motion_tolerances=MotionToleranceConfig(
                default_tcp_position_threshold=self.position_tolerance,
                tool_orientation_threshold=self.orientation_tolerance,
            ),
        )

    def build_plan(self, context: Context) -> Plan:
        """
        :param context: The world and the robot.
        :return: Pickup from the source slot and placing into the target slot.
        """
        key = self.vessel_key()
        body = context.world.get_body_by_name(key)
        bench = self.laboratory.bench
        grasp = VesselGrasp(
            ApproachDirection.RIGHT,
            VerticalAlignment.NoAlignment,
            context.robot.left_arm.end_effector,
            manipulation_offset=self.lift,
            grasp_height=self.laboratory.vessels.grasp_height,
            approach_distance=self.laboratory.vessels.outer_radius
            + self.approach_margin,
            tool_orientation=self.tool_orientation,
        )
        others = [
            context.world.get_body_by_name(placement.key)
            for placement in bench.tubes
            if placement.key != key
        ]
        if bench.stopper is not None:
            others.append(context.world.get_body_by_name(bench.stopper.key))
        plan = sequential(
            [
                VesselPickUpAction(
                    body,
                    Arms.LEFT,
                    grasp,
                    pre_approach_linear_velocity=self.speeds.approach,
                    final_approach_linear_velocity=self.speeds.final_approach,
                    lift_linear_velocity=self.speeds.lift,
                    grasp_closing_velocity=self.closing_velocity,
                    grasp_joint_position_threshold=self.finger_tolerance,
                    contact_clearance=self.pad_clearance,
                ),
                RackPlaceAction(
                    body,
                    self.laboratory.slot_pose(self.target_slot, context.world),
                    Arms.LEFT,
                    transport_linear_velocity=self.speeds.transport,
                    placing_linear_velocity=self.speeds.placing,
                    retract_linear_velocity=self.speeds.retract,
                ),
            ],
            context=context,
        ).plan
        self.observation = TransferObservation(
            context=context,
            body=body,
            pads=PadContact(
                context.world,
                context.robot.left_arm.end_effector,
                body,
                clearance=self.pad_clearance,
            ),
            others=others,
        )
        plan.node_callbacks.append(self.observation)
        self.plan = plan
        return plan

    def measure(self, context: Context) -> AcceptanceMetrics:
        """
        :param context: The world and the robot after the run.
        :return: The measurements.
        :raises TaskFailed: When the vessel was not carried, lifted, released and placed
            as required, or anything else moved.
        """
        observation = self.observation
        body = observation.body
        actual = body.global_pose.to_np()
        desired = self.laboratory.slot_pose(self.target_slot, context.world).to_np()
        position_error = float(np.linalg.norm(actual[:3, 3] - desired[:3, 3]))
        orientation_error = float(
            np.arccos(
                np.clip((np.trace(desired[:3, :3].T @ actual[:3, :3]) - 1) / 2, -1, 1)
            )
        )
        self.require_success(context)
        if observation.carried_ticks == 0:
            raise TaskFailed(TransferFailure.NOT_CARRIED.value)
        if observation.maximum_lift < self.lift - self.position_tolerance:
            raise TaskFailed(
                TransferFailure.NOT_LIFTED.value.format(lift=observation.maximum_lift)
            )
        if body.parent_connection.parent is not context.world.root:
            raise TaskFailed(TransferFailure.NOT_RELEASED.value)
        if position_error > 2 * self.position_tolerance:
            raise TaskFailed(
                TransferFailure.MISPLACED.value.format(error=position_error)
            )
        if orientation_error > 2 * self.orientation_tolerance:
            raise TaskFailed(
                TransferFailure.TURNED.value.format(error=orientation_error)
            )
        if not (observation.others_still and observation.untouched()):
            raise TaskFailed(TransferFailure.DISTURBED.value)
        if (observation.smallest_pad_clearance or 0.0) < -PENETRATION_TOLERANCE:
            raise TaskFailed(
                TransferFailure.PADS.value.format(
                    depth=-observation.smallest_pad_clearance
                )
            )
        if (observation.smallest_collision_distance or 0.0) < -self.pad_clearance:
            raise TaskFailed(
                TransferFailure.COLLISION.value.format(
                    distance=-observation.smallest_collision_distance
                )
            )
        return AcceptanceMetrics(
            measurements={
                TransferMeasurement.POSITION_ERROR.value: position_error,
                TransferMeasurement.ORIENTATION_ERROR.value: orientation_error,
                TransferMeasurement.MAXIMUM_LIFT.value: float(observation.maximum_lift),
                TransferMeasurement.CARRIED_TICKS.value: observation.carried_ticks,
                TransferMeasurement.SMALLEST_PAD_CLEARANCE.value: observation.smallest_pad_clearance,
                TransferMeasurement.SMALLEST_COLLISION_DISTANCE.value: observation.smallest_collision_distance,
            }
        )

    def require_success(self, context: Context) -> None:
        """
        :param context: The world and the robot after the run.
        :raises TaskFailed: When the pickup or the placing did not succeed.
        """
        plan = self.plan
        nodes = plan.get_nodes_by_designator_type(
            PickUpAction
        ) + plan.get_nodes_by_designator_type(PlaceAction)
        statuses = [node.status for node in nodes]
        if len(nodes) != 2 * SINGLE_ACTION or any(
            status is not TaskStatus.SUCCEEDED for status in statuses
        ):
            raise TaskFailed(
                TransferFailure.ACTIONS.value.format(
                    statuses=[status.name for status in statuses]
                )
            )

    @classmethod
    def at_the_bench(cls, **fields) -> VesselTransferDemo:
        """
        :param fields: Fields that differ from the shipped bench's transfer.
        :return: The transfer in the shipped bench laboratory.
        """
        environment = LaboratoryEnvironment(allow_support_contacts=True)
        x, y, heading = ROBOT_START
        defaults = dict(
            environment=environment,
            robot=RobotSpecification(
                semantic_annotation_type=PR2,
                odom_T_robot_start=HomogeneousTransformationMatrix.from_xyz_rpy(
                    x=x, y=y, yaw=heading
                ),
            ),
            name="_".join((LaboratoryResource.BENCH, ROBOT_NAME, TASK_IDENTIFIER)),
            task=TASK,
            environment_name=environment.contents.scene.environment_name,
            presentation=ScenePresentation.of_bundle(environment.directory),
            camera=TRANSFER_CAMERA,
            collision_avoidance=True,
        )
        defaults.update(fields)
        return cls(**defaults)


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    Run the transfer and save its recording, or publish a saved recording.

    :param arguments: The command's arguments; the process's arguments by default.
    """
    TaskCommand(VesselTransferDemo.at_the_bench()).main(
        sys.argv[1:] if arguments is None else arguments
    )
