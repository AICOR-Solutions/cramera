"""
A PR2 works through the small laboratory: it re-sorts the rack, opens and closes the
sample refrigerator's door, and opens and closes the centrifuge's lid, driving between
its stands at the bench; the run is published, recorded and measured.

The measured outcome: every motion succeeds, every moved vessel was carried and set down
within a millimetre of its new slot, the refrigerator's door and the centrifuge's lid
were opened and are closed again, the vessel and the stopper the workflow does not move
stayed where they were, and the gripper's pads never cut into glass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import numpy as np
from typing_extensions import Dict, List, Optional, Tuple

from coraplex.datastructures.dataclasses import Context
from coraplex.plans.factories import sequential
from coraplex.plans.plan import Plan
from coraplex.plans.plan_node import MotionNode, PlanNode
from coraplex.robot_plans.actions.core.pick_up import GraspingAction
from coraplex.robot_plans.motions.gripper import (
    MoveGripperMotion,
    MoveToolCenterPointMotion,
)
from giskardpy.motion_statechart.data_types import LifeCycleValues
from semantic_digital_twin.callbacks.callback import StateChangeCallback
from semantic_digital_twin.collision_checking.collision_rules import (
    AvoidCollisionBetweenGroups,
)
from semantic_digital_twin.datastructures.definitions import GripperState
from semantic_digital_twin.grasping.grasp_candidates import GraspCandidate
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.semantic_annotations.semantic_annotations import Handle
from semantic_digital_twin.specifications.robots import RobotSpecification
from semantic_digital_twin.spatial_types import (
    HomogeneousTransformationMatrix,
    Pose,
    Quaternion,
)
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import ActiveConnection1DOF
from semantic_digital_twin.world_description.world_entity import Body

from cramera_bridge.exceptions import TaskFailed
from cramera_bridge.laboratory.grasping import PadContact
from cramera_bridge.laboratory.handling import VesselTaskDemo
from cramera_bridge.laboratory.mobility import (
    DriveAction,
    MechanismMotion,
    TuckArmsAction,
)
from cramera_bridge.laboratory.transfer import POSE_TOLERANCE, PENETRATION_TOLERANCE
from cramera_bridge.laboratory.world import LaboratoryEnvironment, LaboratoryHandle
from cramera_bridge.scenes.presentation import ScenePresentation
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.scene import Camera
from cramera_protocol.geometry import Vector3
from cramera_protocol.laboratory.runs import TaskRecording
from cramera_protocol.live_messages import SavedScene

TASK = "PR2: rack, refrigerator door and centrifuge lid"
"""
What the task does, as the scene picker labels it.
"""

WORKFLOW_CAMERA = Camera(
    position=Vector3(1.9, -3.3, 2.4), target=Vector3(-0.35, -0.25, 0.8)
)
"""
The recording's first view: the PR2, the bench, the centrifuge and the refrigerator.
"""

CLOSED_TOLERANCE = 0.01
"""
How far from its stop a closed door or lid may stand, in radians.
"""

OPENED_TOLERANCE = 0.02
"""
How far short of its goal an opened door or lid may have stopped, in radians.
"""

# %% layout


@dataclass(frozen=True)
class Stand:
    """
    Where the PR2's base stands to work at one station.
    """

    x: float
    """
    The base's x coordinate in the laboratory, in metres.
    """

    y: float
    """
    The base's y coordinate in the laboratory, in metres.
    """

    heading: float = math.pi / 2
    """
    Which way the base faces, in radians about the vertical.
    """

    def pose(self, world: World) -> Pose:
        """
        :param world: A world holding the laboratory.
        :return: The base's pose at the stand.
        """
        return Pose.from_xyz_rpy(
            self.x, self.y, yaw=self.heading, reference_frame=world.root
        )


RACK_STAND = Stand(0.40, -0.72)
"""
In front of the rack, where the PR2 starts.
"""

CENTRIFUGE_STAND = Stand(-0.22, -0.72)
"""
In front of the centrifuge, its left shoulder beside the lid's handle.
"""

CENTRIFUGE_STEP_BACK = Stand(-0.22, -0.88)
"""
A step back from :data:`CENTRIFUGE_STAND`, where the tucked arm is clear of the
centrifuge's housing while the torso rises.
"""

DOOR_STAND = Stand(-0.95, -0.95)
"""
In front of the refrigerator's door, clear of its swing, its left arm able to follow the
handle until the door stands beside the refrigerator.
"""


@dataclass(frozen=True)
class RackMove:
    """
    One vessel moved between two rack slots.
    """

    source: str
    """
    The slot the vessel is taken from.
    """

    target: str
    """
    The slot it is set into.
    """


# %% names


class WorkflowMeasurement(StrEnum):
    """
    What the workflow measures.
    """

    RACK_POSITION_ERROR = "rackPositionError"
    """
    The largest distance between a re-sorted vessel and its target slot, in metres.
    """

    WIDEST_DOOR = "widestDoorAngle"
    """
    How far the refrigerator's door was opened, in radians.
    """

    WIDEST_LID = "widestLidAngle"
    """
    How far the centrifuge's lid was opened, in radians.
    """

    DOOR = "doorAngle"
    """
    The refrigerator door's angle at the end, in radians.
    """

    LID = "lidAngle"
    """
    The centrifuge lid's angle at the end, in radians.
    """

    SMALLEST_PAD_CLEARANCE = "smallestPadClearance"
    """
    The smallest clearance between a pad and a carried vessel, in metres.
    """

    SMALLEST_COLLISION_DISTANCE = "smallestCollisionDistance"
    """
    The smallest distance between bodies whose collisions are avoided, in metres.
    """


class WorkflowFailure(StrEnum):
    """
    Why the workflow failed.
    """

    MOTIONS = "not every motion succeeded: {statuses}"
    """
    A motion ended in another state, or the plan holds none.
    """

    NOT_CARRIED = "the gripper never carried {vessel}"
    """
    A handled vessel was never attached to the gripper.
    """

    NOT_RELEASED = "{vessel} is still held"
    """
    A handled vessel is not attached to the world at the end.
    """

    NOT_SET_DOWN = "the vessels were not set down in the workflow's order: {released}"
    """
    The gripper let go of other vessels, or in another order, than the workflow sets
    down.
    """

    MISPLACED = "{vessel} ended {error:.4f} m from where it belongs"
    """
    A handled vessel ended too far from its target.
    """

    NOT_OPENED = "{part} opened only to {angle:.3f} rad"
    """
    The door or the lid was not opened far enough.
    """

    LEFT_OPEN = "{part} was left open at {angle:.3f} rad"
    """
    The door or the lid is not closed at the end.
    """

    DISTURBED = "a vessel or the stopper the workflow does not handle moved"
    """
    An object that was not handled moved.
    """

    PADS = "a gripper pad cut into the glass by {depth:.6f} m"
    """
    A pad intersected a carried vessel.
    """

    COLLISION = "bodies came {distance:.5f} m into each other"
    """
    A checked collision pair penetrated.
    """


@dataclass(frozen=True)
class VesselPlacing:
    """
    One vessel set down where the workflow takes it.
    """

    vessel: Body
    """
    The vessel.
    """

    target: Pose
    """
    Where the vessel's bottom ends.
    """

    def error(self, world: World) -> float:
        """
        :param world: The world holding the vessel.
        :return: The distance between the vessel's bottom and its target, in metres.
        """
        desired = world.transform(self.target.homogeneous_matrix, world.root).to_np()
        return float(
            np.linalg.norm(self.vessel.global_pose.to_np()[:3, 3] - desired[:3, 3])
        )


# %% observation


@dataclass(eq=False)
class WorkflowObservation(StateChangeCallback):
    """
    Measures the handled vessels, the untouched objects, the door and the lid after each
    state update of the run.
    """

    context: Context = field(kw_only=True)
    """
    The world and the robot.
    """

    pads: Dict[Body, PadContact] = field(kw_only=True)
    """
    Measures the pads' clearance from each handled vessel.
    """

    placings: List[VesselPlacing] = field(kw_only=True)
    """
    Where the vessels are set down, in order.
    """

    untouched: List[Body] = field(kw_only=True)
    """
    The objects that must stay where they are.
    """

    door: ActiveConnection1DOF = field(kw_only=True)
    """
    The refrigerator door's hinge.
    """

    lid: ActiveConnection1DOF = field(kw_only=True)
    """
    The centrifuge lid's hinge.
    """

    starts: List[np.ndarray] = field(init=False)
    """
    The untouched objects' transforms before the run, in the order of :attr:`untouched`.
    """

    carried_ticks: Dict[Body, int] = field(init=False)
    """
    How many observed state updates the gripper carried each handled vessel.
    """

    smallest_pad_clearance: Optional[float] = field(init=False, default=None)
    """
    The smallest pad clearance from a carried vessel, in metres.
    """

    smallest_collision_distance: Optional[float] = field(init=False, default=None)
    """
    The smallest distance of a checked collision pair, in metres.
    """

    widest_door: float = field(init=False, default=0.0)
    """
    The door's largest angle so far, in radians.
    """

    widest_lid: float = field(init=False, default=0.0)
    """
    The lid's largest angle so far, in radians.
    """

    untouched_still: bool = field(init=False, default=True)
    """
    Whether the untouched objects stayed where they were on every state update.
    """

    holding: Optional[Body] = field(init=False, default=None)
    """
    The vessel the gripper carried on the previous state update, if any.
    """

    let_go: Optional[Body] = field(init=False, default=None)
    """
    The vessel the gripper let go of on the previous state update, measured on this
    one: the update that moves it to the world comes before its pose is final.
    """

    released: List[Tuple[Body, float]] = field(init=False, default_factory=list)
    """
    Every vessel the gripper let go of, in order, with its distance from the target of
    the placing it belongs to when it was let go, in metres.
    """

    def __post_init__(self) -> None:
        self.starts = [body.global_pose.to_np().copy() for body in self.untouched]
        self.carried_ticks = {vessel: 0 for vessel in self.pads}
        super().__post_init__()

    def carried(self, vessel: Body) -> bool:
        """
        :param vessel: A handled vessel.
        :return: Whether it hangs from the left gripper's tool frame.
        """
        return (
            vessel.parent_connection.parent
            is self.context.robot.left_arm.end_effector.tool_frame
        )

    def on_state_change(self, **kwargs) -> None:
        """
        Measure the world after the controller updates its state.
        """
        if self.let_go is not None:
            self.record_release(self.let_go)
            self.let_go = None
        carried = next((vessel for vessel in self.pads if self.carried(vessel)), None)
        if self.holding is not None and carried is not self.holding:
            self.let_go = self.holding
        self.holding = carried
        for vessel, pads in self.pads.items():
            if not self.carried(vessel):
                continue
            self.carried_ticks[vessel] += 1
            clearance = pads.clearances().smallest
            self.smallest_pad_clearance = (
                clearance
                if self.smallest_pad_clearance is None
                else min(self.smallest_pad_clearance, clearance)
            )
        self.widest_door = max(self.widest_door, float(self.door.position))
        self.widest_lid = max(self.widest_lid, float(self.lid.position))
        self.untouched_still = self.untouched_still and self.still()
        contacts = self.context.world.collision_manager.compute_collisions().contacts
        if contacts:
            distance = min(float(contact.distance) for contact in contacts)
            self.smallest_collision_distance = (
                distance
                if self.smallest_collision_distance is None
                else min(self.smallest_collision_distance, distance)
            )

    def record_release(self, vessel: Body) -> None:
        """
        :param vessel: The vessel the gripper just let go of.
        """
        placing = self.placings[min(len(self.released), len(self.placings) - 1)]
        self.released.append((vessel, placing.error(self.context.world)))

    def still(self) -> bool:
        """
        :return: Whether every untouched object is where it started.
        """
        return all(
            np.allclose(body.global_pose.to_np(), start, atol=POSE_TOLERANCE, rtol=0)
            for body, start in zip(self.untouched, self.starts)
        )


# %% demo


@dataclass
class LaboratoryWorkflowDemo(VesselTaskDemo):
    """
    A PR2 re-sorts the rack, opens and closes the refrigerator's door, and opens and
    closes the centrifuge's lid, with its left arm.
    """

    rack_moves: Tuple[RackMove, ...] = (
        RackMove("A1", "A3"),
        RackMove("A2", "B2"),
        RackMove("B1", "A1"),
    )
    """
    The vessels moved within the rack, in order.
    """

    door_handle_orientation: Quaternion = field(
        default_factory=lambda: Quaternion.from_rpy(0, 0, math.pi / 2)
    )
    """
    The tool's orientation at the refrigerator door's upright handle bar: level,
    pointing towards the door, the fingers closing across the bar.
    """

    lid_handle_orientation: Quaternion = field(
        default_factory=lambda: Quaternion.from_rpy(math.pi / 2, 0, math.pi / 2)
    )
    """
    The tool's orientation at the lid's handle bar: level, towards the lid's hinge, the
    fingers closing above and below the bar.
    """

    lid_approach_orientation: Quaternion = field(
        default_factory=lambda: Quaternion.from_rpy(math.pi, -math.pi / 2, 0)
    )
    """
    The closed gripper's orientation on its way under the lid, relative to the lid,
    pointing straight into the lid's underside with the fingers across its width.
    """

    lid_push_orientation: Quaternion = field(
        default_factory=lambda: Quaternion.from_rpy(
            math.pi / 2, -math.radians(75), math.pi / 2
        )
    )
    """
    The closed gripper's orientation while it moves the lid, relative to the lid: tilted
    15 degrees from :attr:`lid_approach_orientation` towards the lid's hinge, so the arm
    stays clear of the housing in front of the lid.
    """

    lid_contact: Vector3 = field(default_factory=lambda: Vector3(0.0, -0.29, -0.012))
    """
    Where the closed gripper touches the lid from below, in the lid's frame.
    """

    lid_contact_approach: Vector3 = field(
        default_factory=lambda: Vector3(0.0, -0.36, -0.07)
    )
    """
    Where the gripper comes from to touch the lid, in front of and below its edge, in
    the lid's frame.
    """

    door_open: float = 1.45
    """
    How far the refrigerator's door is opened, in radians: beside the refrigerator, as
    far as the left arm follows the handle from :data:`DOOR_STAND`.
    """

    lid_pulled: float = 0.6
    """
    How far the lid is pulled open by its handle, and lowered back to before it is
    closed by its handle, in radians.
    """

    lid_pushed: float = 1.3
    """
    How far the lid is pushed open from below, clearing the rotor's holders, in radians.
    """

    handle_clearance: float = 0.06
    """
    How far in front of a handle the approach to it starts, in metres.
    """

    back_off: float = 0.07
    """
    How far the gripper backs away from a handle or the lid it let go of, in metres.
    """

    arm_clearance: float = 0.02
    """
    How far the left arm, apart from its gripper, keeps from the centrifuge and the
    refrigerator it works at, in metres.
    """

    observation: Optional[WorkflowObservation] = field(init=False, default=None)
    """
    The measurements of the current run, once its plan is built.
    """

    # %% vessels

    def handled(self) -> List[str]:
        """
        :return: The vessels the workflow picks up at least once.
        """
        keys = [self.vessel_in(move.source) for move in self.rack_moves]
        return list(dict.fromkeys(keys))

    def stands(self) -> List[Stand]:
        """
        :return: Where the PR2 stands at its stations.
        """
        return [RACK_STAND, CENTRIFUGE_STAND, CENTRIFUGE_STEP_BACK, DOOR_STAND]

    # %% context

    def build_context(self, world: World) -> Context:
        """
        Park the arms, raise the torso, and keep the gripper and the handled vessels
        clear of the laboratory, except for the intended contacts of the grasps.

        :param world: The world built for the task.
        :return: The context with tight tolerances at the slots.
        """
        robot = self.posture(world)
        self.keep_clear(
            world, robot, [world.get_body_by_name(key) for key in self.handled()]
        )
        self.reach_into_instruments(world, robot)
        return self.tight_context(world, robot)

    def reach_into_instruments(self, world: World, robot: PR2) -> None:
        """
        Let the left arm come within :attr:`arm_clearance` of the centrifuge and the
        refrigerator, so it reaches under the centrifuge's lid.

        :param world: The world built for the task.
        :param robot: The robot.
        """
        arm = robot.left_arm
        bench = self.laboratory.bench
        instruments = [
            world.get_body_by_name(name)
            for name in (
                bench.centrifuge.body,
                bench.centrifuge.lid_body,
                bench.centrifuge.rotor_body,
                bench.refrigerator.body,
                bench.refrigerator.door_body,
            )
        ]
        with world.modify_world():
            world.collision_manager.add_default_rule(
                AvoidCollisionBetweenGroups(
                    body_group_a=[
                        body
                        for body in arm.bodies_with_collision
                        if body not in arm.end_effector.bodies_with_collision
                    ],
                    body_group_b=instruments,
                    buffer_zone_distance=self.arm_clearance,
                    violated_distance=0.0,
                )
            )

    # %% plan

    def build_plan(self, context: Context) -> Plan:
        """
        :param context: The world and the robot.
        :return: The rack moves, the refrigerator's door and the centrifuge's lid, in
            order.
        """
        world = context.world
        bench = self.laboratory.bench
        handled = [world.get_body_by_name(key) for key in self.handled()]
        untouched = [
            world.get_body_by_name(placement.key)
            for placement in bench.tubes
            if placement.key not in self.handled()
        ]
        if bench.stopper is not None:
            untouched.append(world.get_body_by_name(bench.stopper.key))
        plan = sequential(
            [
                *self.rack_stage(context),
                *self.refrigerator_stage(context),
                *self.centrifuge_stage(context),
                self.drive(context, RACK_STAND),
            ],
            context=context,
        ).plan
        if self.observation is not None:
            self.observation.stop()
        self.observation = WorkflowObservation(
            _world=world,
            context=context,
            pads={
                vessel: PadContact(
                    world,
                    context.robot.left_arm.end_effector,
                    vessel,
                    clearance=self.pad_clearance,
                )
                for vessel in handled
            },
            placings=self.placings(world),
            untouched=untouched,
            door=world.get_connection_by_name(bench.refrigerator.door_joint),
            lid=world.get_connection_by_name(bench.centrifuge.lid_joint),
        )
        self.plan = plan
        return plan

    def rack_stage(self, context: Context) -> List[PlanNode]:
        """
        :param context: The world and the robot.
        :return: Every rack move, picked from and set into the rack.
        """
        steps = []
        for move in self.rack_moves:
            grasp = self.grasp(
                context, context.world.get_body_by_name(self.vessel_in(move.source))
            )
            steps += [
                self.pick_up(context, grasp),
                self.place(
                    grasp, self.laboratory.slot_pose(move.target, context.world)
                ),
            ]
        return steps

    def refrigerator_stage(self, context: Context) -> List[PlanNode]:
        """
        :param context: The world and the robot.
        :return: Open the refrigerator's door by its handle and close it again, then
            tuck the arm in and raise the torso, so the centrifuge starts from the same
            posture as the PR2 did.
        """
        handle = self.handle(context.world, LaboratoryHandle.REFRIGERATOR_DOOR)
        door_grasp = self.grasp_at(
            context,
            handle,
            Pose.from_xyz_quaternion(
                0,
                0,
                0,
                *self.door_handle_orientation.to_np(),
                reference_frame=handle.root,
            ),
        )
        arm = context.robot.left_arm
        return [
            self.park(context),
            self.drive(context, DOOR_STAND),
            GraspingAction(door_grasp, arm, approach_clearance=self.handle_clearance),
            MechanismMotion(handle.root, arm, self.door_open),
            MechanismMotion(handle.root, arm, 0.0),
            *self.let_go(context),
            self.park(context, raise_torso=True),
        ]

    def centrifuge_stage(self, context: Context) -> List[PlanNode]:
        """
        :param context: The world and the robot.
        :return: Open the lid, by its handle and then from below, and close it again
            the same way; before it takes the handle again, the PR2 steps back to raise
            its torso, so it closes the lid from the posture it opened it from.
        """
        world = context.world
        handle = self.handle(world, LaboratoryHandle.CENTRIFUGE_LID)
        lid_grasp = self.grasp_at(
            context,
            handle,
            Pose.from_xyz_quaternion(
                0,
                0,
                0,
                *self.lid_handle_orientation.to_np(),
                reference_frame=handle.root,
            ),
        )
        lid = world.get_body_by_name(self.laboratory.bench.centrifuge.lid_body)
        return [
            self.drive(context, CENTRIFUGE_STAND),
            *self.operate(context, lid_grasp, self.lid_pulled),
            *self.support_lid(context, lid, self.lid_pushed),
            *self.support_lid(context, lid, self.lid_pulled),
            self.drive(context, CENTRIFUGE_STEP_BACK),
            self.park(context, raise_torso=True),
            self.drive(context, CENTRIFUGE_STAND),
            *self.operate(context, lid_grasp, 0.0),
            self.park(context),
        ]

    # %% steps

    @staticmethod
    def handle(world: World, name: LaboratoryHandle) -> Handle:
        """
        :param world: A world holding the laboratory.
        :param name: One of the laboratory's handles.
        :return: The handle's annotation.
        """
        return next(
            handle
            for handle in world.get_semantic_annotations_by_type(Handle)
            if handle.root.name.name == name.value
        )

    def drive(self, context: Context, stand: Stand) -> DriveAction:
        """
        :param context: The world and the robot.
        :param stand: Where the PR2 drives to.
        :return: The drive.
        """
        return DriveAction(stand.pose(context.world))

    @staticmethod
    def park(context: Context, raise_torso: bool = False) -> TuckArmsAction:
        """
        :param context: The world and the robot.
        :param raise_torso: Whether the torso is raised to the top of its travel as well.
        :return: Tucking the left arm in, for driving or out of the way.
        """
        return TuckArmsAction([context.robot.left_arm], raise_torso=raise_torso)

    def operate(
        self, context: Context, grasp: GraspCandidate, position: float
    ) -> List[PlanNode]:
        """
        :param context: The world and the robot.
        :param grasp: The left gripper's grasp on a handle.
        :param position: Where the handle's joint ends.
        :return: Take the handle, move its joint, let go and back away.
        """
        arm = context.robot.left_arm
        return [
            GraspingAction(grasp, arm, approach_clearance=self.handle_clearance),
            MechanismMotion(grasp.graspable.root, arm, position),
            *self.let_go(context),
        ]

    def support_lid(
        self, context: Context, lid: Body, position: float
    ) -> List[PlanNode]:
        """
        :param context: The world and the robot.
        :param lid: The centrifuge's lid.
        :param position: Where the lid's hinge ends.
        :return: Tuck the arm in, put the closed gripper under the lid's front edge from
            below, move the lid on it, back away and tuck the arm in again.
        """
        arm = context.robot.left_arm
        gripper = arm.end_effector

        def under_the_lid(point: Vector3, orientation: Quaternion) -> Pose:
            return Pose.from_xyz_quaternion(
                point.x, point.y, point.z, *orientation.to_np(), reference_frame=lid
            )

        return [
            self.park(context),
            MoveGripperMotion(
                GripperState.CLOSE, gripper, allow_gripper_collision=True
            ),
            MoveToolCenterPointMotion(
                under_the_lid(self.lid_contact_approach, self.lid_approach_orientation),
                arm,
            ),
            MoveToolCenterPointMotion(
                under_the_lid(self.lid_contact, self.lid_push_orientation),
                arm,
                allow_gripper_collision=True,
            ),
            MechanismMotion(lid, arm, position),
            MoveToolCenterPointMotion(
                Pose.from_xyz_rpy(-self.back_off, reference_frame=gripper.tool_frame),
                arm,
                allow_gripper_collision=True,
            ),
            self.park(context),
        ]

    def let_go(self, context: Context) -> List[PlanNode]:
        """
        :param context: The world and the robot.
        :return: Open the gripper and back away from what it held.
        """
        arm = context.robot.left_arm
        gripper = arm.end_effector
        return [
            MoveGripperMotion(GripperState.OPEN, gripper, allow_gripper_collision=True),
            MoveToolCenterPointMotion(
                Pose.from_xyz_rpy(-self.back_off, reference_frame=gripper.tool_frame),
                arm,
                allow_gripper_collision=True,
            ),
        ]

    # %% running

    def run(self) -> SavedScene:
        """
        :return: The measured recording; release observation on failure as well as
            success.
        """
        try:
            return super().run()
        finally:
            if self.observation is not None:
                self.observation.stop()

    def placings(self, world: World) -> List[VesselPlacing]:
        """
        :param world: A world holding the laboratory.
        :return: Where the workflow sets every vessel down, in order.
        """
        return [
            VesselPlacing(
                world.get_body_by_name(self.vessel_in(move.source)),
                self.laboratory.slot_pose(move.target, world),
            )
            for move in self.rack_moves
        ]

    def measure(self, context: Context) -> AcceptanceMetrics:
        """
        :param context: The world and the robot after the run.
        :return: The measurements.
        :raises TaskFailed: When a vessel was not carried, released and set down where
            it belongs, the door or the lid was not opened and closed again, or anything
            else moved.
        """
        world = context.world
        observation = self.observation
        self.require_success(context)
        for vessel, ticks in observation.carried_ticks.items():
            if ticks == 0:
                raise TaskFailed(
                    WorkflowFailure.NOT_CARRIED.value.format(vessel=vessel.name.name)
                )
            if vessel.parent_connection.parent is not world.root:
                raise TaskFailed(
                    WorkflowFailure.NOT_RELEASED.value.format(vessel=vessel.name.name)
                )
        placings = self.placings(world)
        if [vessel for vessel, _ in observation.released] != [
            placing.vessel for placing in placings
        ]:
            raise TaskFailed(
                WorkflowFailure.NOT_SET_DOWN.value.format(
                    released=[vessel.name.name for vessel, _ in observation.released]
                )
            )
        largest_error = 0.0
        for placing, (vessel, released) in zip(placings, observation.released):
            for error in (released, placing.error(world)):
                if error > 2 * self.position_tolerance:
                    raise TaskFailed(
                        WorkflowFailure.MISPLACED.value.format(
                            vessel=vessel.name.name, error=error
                        )
                    )
            largest_error = max(largest_error, released)
        bench = self.laboratory.bench
        for part, widest, goal, joint in (
            (
                bench.refrigerator.door_body,
                observation.widest_door,
                self.door_open,
                observation.door,
            ),
            (
                bench.centrifuge.lid_body,
                observation.widest_lid,
                self.lid_pushed,
                observation.lid,
            ),
        ):
            if widest < goal - OPENED_TOLERANCE:
                raise TaskFailed(
                    WorkflowFailure.NOT_OPENED.value.format(part=part, angle=widest)
                )
            if abs(float(joint.position)) > CLOSED_TOLERANCE:
                raise TaskFailed(
                    WorkflowFailure.LEFT_OPEN.value.format(
                        part=part, angle=float(joint.position)
                    )
                )
        if not (observation.untouched_still and observation.still()):
            raise TaskFailed(WorkflowFailure.DISTURBED.value)
        if (observation.smallest_pad_clearance or 0.0) < -PENETRATION_TOLERANCE:
            raise TaskFailed(
                WorkflowFailure.PADS.value.format(
                    depth=-observation.smallest_pad_clearance
                )
            )
        if (observation.smallest_collision_distance or 0.0) < -self.pad_clearance:
            raise TaskFailed(
                WorkflowFailure.COLLISION.value.format(
                    distance=-observation.smallest_collision_distance
                )
            )
        return AcceptanceMetrics(
            measurements={
                WorkflowMeasurement.RACK_POSITION_ERROR.value: largest_error,
                WorkflowMeasurement.WIDEST_DOOR.value: observation.widest_door,
                WorkflowMeasurement.WIDEST_LID.value: observation.widest_lid,
                WorkflowMeasurement.DOOR.value: float(observation.door.position),
                WorkflowMeasurement.LID.value: float(observation.lid.position),
                WorkflowMeasurement.SMALLEST_PAD_CLEARANCE.value: observation.smallest_pad_clearance,
                WorkflowMeasurement.SMALLEST_COLLISION_DISTANCE.value: observation.smallest_collision_distance,
            }
        )

    def require_success(self, context: Context) -> None:
        """
        Check every motion of the plan.

        :param context: The world and the robot after the run.
        :raises TaskFailed: When the plan holds no motion or a motion did not succeed.
        """
        motions = [node for node in self.plan.nodes if isinstance(node, MotionNode)]
        statuses = [motion.status for motion in motions]
        if not motions or any(
            status is not LifeCycleValues.SUCCEEDED for status in statuses
        ):
            raise TaskFailed(
                WorkflowFailure.MOTIONS.value.format(
                    statuses=sorted({status.name for status in statuses})
                )
            )

    @classmethod
    def at_the_bench(cls, directory: Path, **fields) -> LaboratoryWorkflowDemo:
        """
        :param directory: The laboratory bundle supplied by the caller.
        :param fields: Fields that differ from the shipped bench's workflow.
        :return: The workflow in the shipped bench laboratory.
        """
        environment = LaboratoryEnvironment(directory, allow_support_contacts=True)
        defaults = dict(
            environment=environment,
            robot=RobotSpecification(
                semantic_annotation_type=PR2,
                odom_T_robot_start=HomogeneousTransformationMatrix.from_xyz_rpy(
                    x=RACK_STAND.x, y=RACK_STAND.y, yaw=RACK_STAND.heading
                ),
            ),
            name=TaskRecording.WORKFLOW.value,
            task=TASK,
            environment_name=environment.contents.scene.environment_name,
            presentation=ScenePresentation.of_bundle(environment.directory),
            camera=WORKFLOW_CAMERA,
            collision_avoidance=True,
        )
        defaults.update(fields)
        return cls(**defaults)
