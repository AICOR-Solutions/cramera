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
from functools import cached_property
from enum import StrEnum

import numpy as np
import trimesh
from typing_extensions import List, Optional

from coraplex.robot_plans.actions.base import GoalAction, ParallelAction
from coraplex.robot_plans.actions.core.pick_up import PickUpAction, ReachAction
from coraplex.robot_plans.actions.core.placing import PlaceAction
from coraplex.robot_plans.mixins import OperatesGripper
from cramph.composites import Parallel
from cramph.node import (
    CompositeNode,
    NodeArtifacts,
    StatechartNode,
    SucceedsOnObservingTrue,
    expanded_child_field,
)
from giskardpy.motion_statechart.graph_node import MotionStatechartNode
from giskardpy.motion_statechart.tasks.cartesian_tasks import (
    CartesianPose,
    CartesianPosition,
    HoldPose,
)
from giskardpy.motion_statechart.tasks.joint_tasks import JointPositionList
from krrood.symbolic_math.symbolic_math import Scalar, trinary_if_cases
from krrood_spatial_math.spatial_types import HomogeneousTransformationMatrix, Pose
from semantic_digital_twin.collision_checking.collision_matrix import CollisionRule
from semantic_digital_twin.collision_checking.collision_rules import (
    AllowCollisionForEndEffector,
)
from semantic_digital_twin.datastructures.definitions import GripperState
from semantic_digital_twin.datastructures.joint_state import JointState
from semantic_digital_twin.grasping.grasp_candidates import GraspCandidate
from semantic_digital_twin.robots.robot_parts import EndEffector
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import ActiveConnection1DOF
from semantic_digital_twin.world_description.world_entity import Body

from cramera.exceptions import ViewerError

ACTION_FIELD_TYPES = (Optional,)
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
class GraspGeometryError(ViewerError):
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
    The signed clearances between the glass and each finger pad.
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


@dataclass(frozen=True)
class GlassExtent:
    """
    Where a vessel's glass lies around its axis, in the vessel's frame.
    """

    radius: float
    """
    The glass's outer radius, in metres.
    """

    bottom: float
    """
    The height of the glass's lowest point, in metres.
    """

    top: float
    """
    The height of the glass's highest point, in metres.
    """


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

    axis_step: float = 0.0005
    """
    How finely the glass's axis is sampled when the pads are measured against it, in
    metres.
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
        :return: Both pads' clearances from the glass, measured by the collision
            detector, collision margins included.
        """
        detector = self.world.collision_manager.collision_detector
        values = []
        for pad in self.pads:
            contact = detector.check_collision_between_bodies(
                pad, self.body, distance=self.query_distance
            )
            values.append(math.inf if contact is None else contact.distance)
        return PadClearances(*values)

    @cached_property
    def glass(self) -> GlassExtent:
        """
        Where the glass lies around its axis, from its collision shapes.
        """
        points = np.concatenate(
            [shape.mesh_in_frame(self.body).vertices for shape in self.body.collision]
        )
        return GlassExtent(
            radius=float(np.max(np.hypot(points[:, 0], points[:, 1]))),
            bottom=float(points[:, 2].min()),
            top=float(points[:, 2].max()),
        )

    def glass_clearances(self) -> PadClearances:
        """
        :return: Both pads' clearances from the glass's outer surface, measured against
            the glass's axis: the same wherever the gripper and the glass stand
            together, which the collision detector's distances between the flat pads
            and the glass's thin wall are not.
        """
        return PadClearances(
            *(self.axis_distance(pad) - self.glass.radius for pad in self.pads)
        )

    def axis_distance(self, pad: Body) -> float:
        """
        :param pad: One of the pads.
        :return: How close the pad comes to the glass's axis beside the glass, in
            metres; infinite when the pad is above or below the glass.
        """
        mesh = trimesh.util.concatenate(
            [shape.mesh_in_frame(self.body) for shape in pad.collision]
        )
        low = max(self.glass.bottom, float(mesh.vertices[:, 2].min()))
        high = min(self.glass.top, float(mesh.vertices[:, 2].max()))
        if low > high:
            return math.inf
        heights = np.append(np.arange(low, high, self.axis_step), high)
        axis = np.column_stack(
            [np.zeros_like(heights), np.zeros_like(heights), heights]
        )
        _, distances, _ = trimesh.proximity.closest_point(mesh, axis)
        return float(distances.min())

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


# %% plan steps


def tool_goal_of(step: StatechartNode) -> CartesianPose:
    """
    :param step: A step moving the tool center point, as CRAM's
        :meth:`~coraplex.robot_plans.mixins.MovesToolCenterPoint.tool_center_point_goal`
        creates it.
    :return: The goal reaching the step's target pose.
    """
    if isinstance(step, CartesianPose):
        return step
    return next(node for node in step.nodes if isinstance(node, CartesianPose))


class CalibratedVesselApproach:
    """
    Preserves the laboratory's approach and lift distances at the tool frame.
    """

    def _approach_distance(self, grasp: Optional[GraspCandidate] = None) -> float:
        return self.approach_clearance

    def _retreat_pose(self, reference_T_grasp: Pose, tool_goal: Pose) -> Pose:
        target = tool_goal.reference_frame
        world = target._world
        world_T_tool = world.transform(tool_goal.homogeneous_matrix, world.root)
        world_T_lift = HomogeneousTransformationMatrix.from_xyz_rpy(
            z=self.retreat_distance, reference_frame=world.root
        )
        return world.transform(world_T_lift @ world_T_tool, target).pose


class ToolHolding:
    """
    An action that holds the tool and the base where they are while the fingers move, so
    collision avoidance cannot move the arm, and with it the glass the fingers take or
    let go of.
    """

    def tool_held(self, gripper: EndEffector) -> List[MotionStatechartNode]:
        """
        :param gripper: The gripper whose fingers move.
        :return: The tasks holding the base and the gripper's tool frame where they are.
        """
        return [
            *self.keep_base_still(),
            HoldPose(
                name="hold tool",
                root_link=self.world.root,
                tip_link=gripper.tool_frame,
            ),
        ]


@dataclass(eq=False, repr=False, kw_only=True)
class VesselReachAction(CalibratedVesselApproach, ReachAction):
    """
    Reaches the vessel using the calibrated tool-frame distances.
    """

    grasp_position_threshold: Optional[float] = None
    """
    The tool's position tolerance at the grasp itself, in metres; the reach's
    :attr:`position_threshold` when None.
    """

    def create_steps(self) -> List[StatechartNode]:
        steps = super().create_steps()
        if self.grasp_position_threshold is not None:
            tool_goal_of(steps[-1]).translation_threshold = (
                self.grasp_position_threshold
            )
        return steps


@dataclass(eq=False, repr=False, kw_only=True)
class PadContactGoal(SucceedsOnObservingTrue, CompositeNode):
    """
    Closes the fingers to their stop at the glass, which it finds when it starts: after
    the approach has finished, at the grasp pose the tool reached.

    It succeeds once the fingers reached the stop, and fails once they no longer can.
    """

    accepts_children_after_compile: bool = field(init=False, default=True)

    gripper: EndEffector
    """
    The gripper at the vessel.
    """

    object_designator: Body
    """
    The glass between the pads.
    """

    contact_clearance: float = 0.00025
    """
    The clearance each pad keeps from the glass, in metres.
    """

    joint_position_threshold: float = 0.0001
    """
    How close the fingers come to their stop, in radians.
    """

    finger_velocity: float = 0.1
    """
    The maximum finger velocity, in radians per second.
    """

    goal: Optional[JointPositionList] = expanded_child_field(default=None)
    """
    The child moving the fingers to their stop, None until this node started.
    """

    def goal_state(self) -> JointState:
        """
        :return: The finger stop at the reached pose.
        """
        return PadContact(
            self.context.world,
            self.gripper,
            self.object_designator,
            clearance=self.contact_clearance,
        ).goal_state()

    def on_start(self) -> None:
        """
        Find the finger stop and put the goal reaching it below this node, once.
        """
        super().on_start()
        if self.goal is not None:
            return
        with self.statechart.modify():
            self.goal = JointPositionList(
                goal_state=self.goal_state(),
                threshold=self.joint_position_threshold,
                max_velocity=self.finger_velocity,
            )
            self._add_child_to_statechart(self.goal)
            self._succeed_at_its_goal(self.goal)
            self.statechart.request_rebuild(self)

    def build_artifacts(self) -> NodeArtifacts:
        """
        Report how the goal ended, or nothing while it has not, or before it exists.
        """
        if self.goal is None:
            return NodeArtifacts(observation=Scalar.const_trinary_unknown())
        return NodeArtifacts(
            observation=trinary_if_cases(
                cases=[
                    (self.goal.is_succeeded, Scalar.const_true()),
                    (self.goal.is_failed_or_interrupted, Scalar.const_false()),
                ],
                else_result=Scalar.const_trinary_unknown(),
            )
        )


@dataclass(eq=False, repr=False, kw_only=True)
class PadContactAction(ToolHolding, ParallelAction):
    """
    Closes the fingers until both pads reach the glass, the tool held where the approach
    ended.
    """

    gripper: EndEffector
    """
    The gripper at the vessel.
    """

    object_designator: Body
    """
    The glass between the pads.
    """

    contact_clearance: float = 0.00025
    """
    The clearance each pad keeps from the glass, in metres.
    """

    joint_position_threshold: float = 0.0001
    """
    How close the fingers come to their stop, in radians.
    """

    finger_velocity: float = 0.1
    """
    The maximum finger velocity, in radians per second.
    """

    def create_steps(self) -> List[StatechartNode]:
        return [
            PadContactGoal(
                gripper=self.gripper,
                object_designator=self.object_designator,
                contact_clearance=self.contact_clearance,
                joint_position_threshold=self.joint_position_threshold,
                finger_velocity=self.finger_velocity,
            ),
            *self.tool_held(self.gripper),
        ]


@dataclass(eq=False, repr=False, kw_only=True)
class VesselPickUpAction(CalibratedVesselApproach, PickUpAction):
    """
    CRAM's pickup, closing the fingers only until both pads reach the glass.
    """

    grasp_joint_position_threshold: float = 0.0001
    """
    How close the fingers must come to their stop, in radians.
    """

    contact_clearance: float = 0.00025
    """
    The clearance each pad keeps from the glass, in metres.
    """

    grasp_position_threshold: Optional[float] = None
    """
    The tool's position tolerance at the grasp itself, before the fingers close, in
    metres; :attr:`position_threshold` when None.
    """

    lifts_upright: bool = False
    """
    Whether the lift keeps the tool's orientation, which keeps the vessel upright, or
    moves the tool by its position only, which lets the vessel tilt.
    """

    def _grasp_steps(self) -> List[StatechartNode]:
        """
        :return: Reach the grasp, close to contact, then attach the carried vessel.
        """
        return [
            VesselReachAction(
                grasp=self.grasp,
                arm=self.arm,
                approach_clearance=self.approach_clearance,
                retreat_distance=self.retreat_distance,
                pre_approach_linear_velocity=self.pre_approach_linear_velocity,
                final_approach_linear_velocity=self.final_approach_linear_velocity,
                open_gripper_at_pre_pose=True,
                position_threshold=self.position_threshold,
                orientation_threshold=self.orientation_threshold,
                grasp_position_threshold=self.grasp_position_threshold,
            ),
            PadContactAction(
                gripper=self.arm.end_effector,
                object_designator=self.grasp.graspable.root,
                contact_clearance=self.contact_clearance,
                finger_velocity=self.grasp_closing_velocity,
                joint_position_threshold=self.grasp_joint_position_threshold,
            ),
            *self.reattach(self.grasp.graspable.root, self.arm.end_effector.tool_frame),
        ]

    def create_steps(self) -> List[StatechartNode]:
        lift_to_pose = self.grasp_pose_sequence(
            self.grasp.grasp_pose, self.arm.end_effector, self.grasp
        ).retreat
        return [*self._grasp_steps(), self.lift_goal(lift_to_pose)]

    def lift_goal(self, target: Pose) -> MotionStatechartNode:
        """
        :param target: Where the tool is lifted to.
        :return: The goal lifting the tool there, by its pose if :attr:`lifts_upright`,
            otherwise by its position only, with the lift's speed cap and the base held.
        """
        if self.lifts_upright:
            return self.tool_center_point_goal(
                target, self.arm, max_linear_velocity=self.lift_linear_velocity
            )
        root = self.controlled_root
        tip = self.arm.end_effector.tool_frame
        return Parallel(
            nodes=[
                CartesianPosition(
                    root_link=root,
                    tip_link=tip,
                    goal_point=target.position,
                    threshold=self.position_threshold,
                ),
                *self._velocity_limits(root, tip, self.lift_linear_velocity, None),
                *self.keep_base_still(),
            ],
            name=CartesianPosition.__name__,
        )


@dataclass(eq=False, repr=False, kw_only=True)
class RackPlaceAction(CalibratedVesselApproach, PlaceAction):
    """
    CRAM's placing, with looser tolerance above the rack and tight insertion tolerance;
    as CRAM's placing does, the tool stays where it set the vessel down while the
    fingers let go.
    """

    approach_position_threshold: float = 0.003
    """
    The tool's position tolerance above the rack, in metres.
    """

    def create_steps(self) -> List[StatechartNode]:
        steps = super().create_steps()
        tool_goal_of(steps[0]).translation_threshold = self.approach_position_threshold
        return steps


@dataclass(eq=False, repr=False, kw_only=True)
class MoveGripperAction(OperatesGripper, GoalAction):
    """
    Opens or closes a gripper, which may touch its surroundings meanwhile.
    """

    gripper: EndEffector
    """
    The gripper moved.
    """

    state: GripperState
    """
    Whether the gripper ends open or closed.
    """

    def create_temporary_collision_rules(self) -> List[CollisionRule]:
        """
        :return: An allowance for the gripper to touch its surroundings.
        """
        return [AllowCollisionForEndEffector(end_effector=self.gripper)]

    def create_goal(self) -> StatechartNode:
        return self.gripper_goal_type.moving_gripper_to(
            self.gripper.default_configuration(self.state)
        )
