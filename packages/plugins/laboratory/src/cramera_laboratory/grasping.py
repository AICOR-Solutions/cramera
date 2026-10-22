"""
Grasping laboratory glass with a parallel gripper: the fingers close only until both
pads reach the glass's collision surface, found on a copy of the world at the reached
grasp pose, so the gripper never squeezes the glass in the planning world.

This is geometry and a stop position; it models no grip force, friction, compliance or
breaking glass.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from typing_extensions import ClassVar, List, Optional

from coraplex.datastructures.enums import Arms
from coraplex.datastructures.grasp import GraspDescription
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from coraplex.robot_plans.actions.core.placing import PlaceAction
from coraplex.robot_plans.motions.gripper import MoveGripperMotion
from coraplex.robot_plans.motions.placement import MovePlacementMotion, PlacementStage
from coraplex.plans.plan_node import MotionNode, PlanNode
from coraplex.utils import translate_pose_along_local_axis
from coraplex.view_manager import ViewManager
from giskardpy.motion_statechart.context import MotionStatechartContext
from giskardpy.motion_statechart.goals.templates import Sequence
from giskardpy.motion_statechart.graph_node import MotionStatechartNode
from semantic_digital_twin.datastructures.definitions import GripperState
from semantic_digital_twin.datastructures.joint_state import JointState
from semantic_digital_twin.robots.robot_parts import EndEffector
from semantic_digital_twin.spatial_types import (
    HomogeneousTransformationMatrix,
    Pose,
    Quaternion,
)
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import ActiveConnection1DOF
from semantic_digital_twin.world_description.world_entity import Body

from cramera_laboratory.exceptions import LaboratoryError

ACTION_FIELD_TYPES = (Arms, Optional)
"""
The types CRAM's actions annotate their fields with; CRAM resolves an action's
annotations in the module of its class, so the subclasses here need them in scope.
"""

TOOL_LATERAL_AXIS = 1
"""
The tool frame's axis the fingers close along.
"""

# %% errors


class GraspProblem(StrEnum):
    """
    Why a glass cannot be held between the fingers.
    """

    TOLERANCES = "The contact search's tolerances are invalid."
    """
    A clearance, distance or tolerance is negative or not finite.
    """

    NO_INTERVAL = "The gripper's open and closed states define no closing interval."
    """
    The closed state is not below the open state.
    """

    NO_CONTACT = (
        "The glass has no safe contact between the closed and the open gripper."
    )
    """
    The glass is not between the pads.
    """

    OFF_CENTRE = "The glass is not centred between both pads."
    """
    One pad touches long before the other.
    """

    INTERSECTS = "The glass intersects the gripper outside its pads."
    """
    Another part of the gripper cuts into the glass.
    """

    UNCOMMANDED = "The gripper state does not command the fingers."
    """
    The open or closed state names no finger joint.
    """


@dataclass
class GraspGeometryError(LaboratoryError):
    """
    A glass the gripper cannot hold between its pads.
    """

    problem: GraspProblem
    """
    What is wrong.
    """

    def message(self) -> str:
        return self.problem.value


# %% pad contact


@dataclass(frozen=True)
class PadClearances:
    """
    The signed clearances between the glass and each finger pad, collision margins
    included.
    """

    first: float
    """
    The first pad's clearance, in metres.
    """

    second: float
    """
    The second pad's clearance, in metres.
    """

    @property
    def smallest(self) -> float:
        """
        The closer pad's clearance.
        """
        return min(self.first, self.second)

    @property
    def largest(self) -> float:
        """
        The farther pad's clearance.
        """
        return max(self.first, self.second)


@dataclass
class PadContact:
    """
    Finds where a parallel gripper's fingers stop at a glass, from the gripper's own
    finger annotations.
    """

    world: World
    """
    The world holding the robot and the glass.
    """

    end_effector: EndEffector
    """
    The gripper; its fingers' tips are the pads.
    """

    body: Body
    """
    The glass.
    """

    clearance: float = 0.00025
    """
    The clearance each pad keeps from the glass, in metres.
    """

    largest_difference: float = 0.001
    """
    How much farther one pad may stop than the other, in metres.
    """

    query_distance: float = 0.2
    """
    How far the collision detector looks, in metres.
    """

    joint_tolerance: float = 1e-9
    """
    How narrow the searched finger interval becomes, in radians.
    """

    def __post_init__(self) -> None:
        values = (
            self.clearance,
            self.largest_difference,
            self.query_distance,
            self.joint_tolerance,
        )
        if (
            not all(math.isfinite(value) for value in values)
            or self.clearance < 0
            or self.largest_difference < 0
            or self.query_distance <= self.clearance
            or self.joint_tolerance <= 0
        ):
            raise GraspGeometryError(GraspProblem.TOLERANCES)

    @property
    def connection(self) -> ActiveConnection1DOF:
        """
        The joint the fingers share.
        """
        finger = self.end_effector.fingers[0].root.parent_connection
        return self.world.get_connection_by_name(finger.raw_dof.name)

    @property
    def pads(self) -> List[Body]:
        """
        The fingertips the gripper's annotation names.
        """
        return [finger.tip for finger in self.end_effector.fingers]

    def clearances(self) -> PadClearances:
        """
        :return: Both pads' clearances from the glass, measured directly.
        """
        detector = self.world.collision_manager.collision_detector
        values = []
        for pad in self.pads:
            contact = detector.check_collision_between_bodies(
                pad, self.body, distance=self.query_distance
            )
            values.append(math.inf if contact is None else contact.distance)
        return PadClearances(*values)

    def aperture(self) -> float:
        """
        :return: The gap between the pads' meshes across the tool, in metres.
        """
        intervals = []
        for pad in self.pads:
            points = np.concatenate(
                [
                    shape.mesh_in_frame(self.end_effector.tool_frame).vertices
                    for shape in pad.collision
                ]
            )
            lateral = points[:, TOOL_LATERAL_AXIS]
            intervals.append((float(lateral.min()), float(lateral.max())))
        intervals.sort()
        return intervals[1][0] - intervals[0][1]

    def goal_state(self) -> JointState:
        """
        :return: The finger position where both pads reach the glass, searched on a copy
            of the world.
        """
        copied = deepcopy(self.world)
        search = PadContact(
            world=copied,
            end_effector=copied.get_semantic_annotation_by_id(self.end_effector.id),
            body=copied.get_kinematic_structure_entity_by_id(self.body.id),
            clearance=self.clearance,
            largest_difference=self.largest_difference,
            query_distance=self.query_distance,
            joint_tolerance=self.joint_tolerance,
        )
        return JointState.from_mapping({self.connection: search.stop_position()})

    def state_position(self, state: GripperState) -> float:
        """
        :param state: Open or closed.
        :return: The shared finger joint's position in that state.
        :raises GraspGeometryError: When the state commands no finger.
        """
        for connection, value in self.end_effector.get_joint_state_by_type(
            state
        ).items():
            if connection.raw_dof is self.connection.raw_dof:
                raw = (value - connection.offset) / connection.multiplier
                return raw * self.connection.multiplier + self.connection.offset
        raise GraspGeometryError(GraspProblem.UNCOMMANDED)

    def stop_position(self) -> float:
        """
        Search, on this world, the most closed finger position that keeps both pads
        clear of the glass.

        :return: The position.
        :raises GraspGeometryError: When the glass cannot be held between the pads.
        """
        closed = self.state_position(GripperState.CLOSE)
        opened = self.state_position(GripperState.OPEN)
        if closed >= opened:
            raise GraspGeometryError(GraspProblem.NO_INTERVAL)
        self.connection.position = closed
        closed_clearance = self.clearances().smallest
        self.connection.position = opened
        if (
            closed_clearance >= self.clearance
            or self.clearances().smallest < self.clearance
        ):
            raise GraspGeometryError(GraspProblem.NO_CONTACT)
        while opened - closed > self.joint_tolerance:
            middle = (closed + opened) / 2
            self.connection.position = middle
            if self.clearances().smallest >= self.clearance:
                opened = middle
            else:
                closed = middle
        self.connection.position = opened
        clearances = self.clearances()
        if clearances.largest - clearances.smallest > self.largest_difference:
            raise GraspGeometryError(GraspProblem.OFF_CENTRE)
        detector = self.world.collision_manager.collision_detector
        for body in self.end_effector.bodies_with_collision:
            if body in self.pads:
                continue
            contact = detector.check_collision_between_bodies(body, self.body)
            if contact is not None and contact.distance < 0:
                raise GraspGeometryError(GraspProblem.INTERSECTS)
        return opened


# %% grasp and motions


@dataclass
class VesselGrasp(GraspDescription):
    """
    Grasps a vessel at a height above its bottom, with an optional tool orientation and
    approach distance.
    """

    grasp_height: float = 0.14
    """
    The tool's height above the vessel's bottom, in metres.
    """

    tool_orientation: Quaternion | None = None
    """
    The tool's orientation relative to the upright vessel; None for the grasp
    description's own.
    """

    approach_distance: float | None = None
    """
    How far from the vessel the approach starts, in metres; None for the grasp
    description's own.
    """

    def grasp_orientation(self) -> Quaternion:
        """
        :return: The tool's orientation at the vessel.
        """
        if self.tool_orientation is not None:
            return self.tool_orientation
        return super().grasp_orientation()

    def pose_sequence(
        self, target_T_grasp_pose: Pose, body: Body | None = None, reverse: bool = False
    ) -> List[Pose]:
        """
        :param target_T_grasp_pose: The vessel's bottom.
        :param body: The vessel.
        :param reverse: Whether to return the poses last first.
        :return: The approach, the grasp at :attr:`grasp_height` and the lift.
        """
        at_height = (
            target_T_grasp_pose.to_homogeneous_matrix()
            @ HomogeneousTransformationMatrix.from_xyz_rpy(z=self.grasp_height)
        )
        sequence = super().pose_sequence(at_height.to_pose(), body, False)
        if self.approach_distance is not None:
            sequence[0] = translate_pose_along_local_axis(
                sequence[1], self.manipulation_axis(), -self.approach_distance
            )
        return list(reversed(sequence)) if reverse else sequence


@dataclass(eq=False, repr=False)
class PadContactGoal(Sequence):
    """
    Closes the fingers to the stop found at the grasp pose the previous motion reached.
    """

    motion: PadContactMotion = field(kw_only=True)
    """
    The closing motion.
    """

    def expand(self, context: MotionStatechartContext) -> None:
        """
        :param context: The statechart's context.
        """
        self.nodes = [self.motion.resolved_motion().motion_chart]
        super().expand(context)


@dataclass
class PadContactMotion(MoveGripperMotion):
    """
    Closes the fingers until both pads reach the glass.
    """

    requires_individual_execution: ClassVar[bool] = True
    """
    The stop is searched only once the gripper reached the glass.
    """

    object_designator: Body = field(kw_only=True)
    """
    The glass between the pads.
    """

    contact_clearance: float = field(default=0.00025, kw_only=True)
    """
    The clearance each pad keeps from the glass, in metres.
    """

    @property
    def motion_chart(self) -> MotionStatechartNode:
        """
        The goal that searches the stop when it runs.
        """
        return PadContactGoal(motion=self)

    def resolved_goal_state(self) -> JointState:
        """
        :return: The finger stop at the reached pose.
        """
        end_effector = ViewManager.get_end_effector_view(self.gripper, self.robot)
        self.goal_state = PadContact(
            self.world,
            end_effector,
            self.object_designator,
            clearance=self.contact_clearance,
        ).goal_state()
        return super().resolved_goal_state()

    def resolved_motion(self) -> MoveGripperMotion:
        """
        :return: The plain finger motion to the stop.
        """
        motion = MoveGripperMotion(
            motion=self.motion,
            gripper=self.gripper,
            goal_state=self.resolved_goal_state(),
            joint_position_threshold=self.joint_position_threshold,
            finger_velocity=self.finger_velocity,
            allow_gripper_collision=self.allow_gripper_collision,
        )
        motion.plan_node = self.plan_node
        return motion


@dataclass
class VesselPickUpAction(PickUpAction):
    """
    CRAM's pickup, closing the fingers only until both pads reach the glass.
    """

    grasp_joint_position_threshold: float = field(
        default=MoveGripperMotion.joint_position_threshold, kw_only=True
    )
    """
    How close the fingers must come to their stop, in radians.
    """

    contact_clearance: float = field(default=0.00025, kw_only=True)
    """
    The clearance each pad keeps from the glass, in metres.
    """

    def create_grasp_motion(self) -> PadContactMotion:
        """
        :return: The closing motion that stops at the glass.
        """
        return PadContactMotion(
            motion=GripperState.CLOSE,
            gripper=self.arm,
            object_designator=self.object_designator,
            contact_clearance=self.contact_clearance,
            finger_velocity=self.grasp_closing_velocity,
            joint_position_threshold=self.grasp_joint_position_threshold,
        )


@dataclass
class RackPlaceAction(PlaceAction):
    """
    CRAM's placing, with a looser tolerance for the approach in free space above the
    rack while the insertion keeps the context's tight tolerance.
    """

    approach_position_threshold: float = field(default=0.003, kw_only=True)
    """
    The tool's position tolerance above the rack, in metres.
    """

    @property
    def _action_plan(self) -> PlanNode:
        """
        The placing plan with the looser approach tolerance.
        """
        plan = super()._action_plan
        for node in plan.descendants:
            if (
                isinstance(node, MotionNode)
                and isinstance(node.designator, MovePlacementMotion)
                and node.designator.stage is PlacementStage.APPROACH
            ):
                node.designator.position_threshold = self.approach_position_threshold
        return plan
