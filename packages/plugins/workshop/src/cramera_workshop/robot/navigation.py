"""
Short straight base translations in the workshop with the carried posture kept: the
corridor is checked against the native collision shapes in a separate copy of the
collision geometry before the controller moves the base.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

import giskardpy_bullet_bindings as bullet
import numpy as np
from typing_extensions import ClassVar, Dict, List, Optional, Set, Tuple

from coraplex.plans.factories import execute_single
from coraplex.plans.failures import PlanFailure
from coraplex.plans.plan_node import PlanNode
from coraplex.robot_plans.actions.base import ActionDescription
from coraplex.robot_plans.motions.base import BaseMotion
from giskardpy.motion_statechart.context import MotionStatechartContext
from giskardpy.motion_statechart.goals.collision_avoidance import (
    ExternalCollisionAvoidance,
)
from giskardpy.motion_statechart.goals.templates import Sequence
from giskardpy.motion_statechart.graph_node import MotionStatechartNode, NodeArtifacts
from giskardpy.motion_statechart.tasks.cartesian_tasks import (
    CartesianPose,
    CartesianVelocityLimit,
)
from giskardpy.motion_statechart.tasks.joint_tasks import JointPositionList
from krrood.symbolic_math.symbolic_math import trinary_logic_and
from semantic_digital_twin.collision_checking.collision_matrix import (
    CollisionCheck,
    CollisionMatrix,
)
from semantic_digital_twin.collision_checking.pybullet_collision_detector import (
    BulletCollisionDetector,
    create_object,
)
from semantic_digital_twin.datastructures.joint_state import JointState
from semantic_digital_twin.robots.robot_parts import AbstractRobot
from semantic_digital_twin.spatial_types import Point3, Pose
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import (
    ActiveConnection1DOF,
    OmniDrive,
)
from semantic_digital_twin.world_description.world_entity import Body

# %% failures


class TranslationProblem(StrEnum):
    """
    Why a translation cannot be certified.
    """

    DRIVE = "A planar omnidirectional base is required."
    """
    The robot's base does not move sideways.
    """

    ORIENTATION = "The straight corridor requires unchanged height and orientation."
    """
    The target turns or raises the base.
    """

    LIMITS = "The translation or collision sampling limits are invalid."
    """
    The translation is too long, or the sampling limits are invalid.
    """

    POLICY = "No external collision checks cover the moving robot."
    """
    The collision rules check nothing against the moving robot.
    """

    GEOMETRY = "Native Bullet collision geometry is required."
    """
    The world checks collisions without Bullet.
    """

    OBSTRUCTION = "The corridor intersects native collision geometry."
    """
    Something stands in the corridor.
    """


@dataclass
class TranslationBlocked(PlanFailure):
    """
    A short translation that cannot be certified with the current posture and collision
    rules.
    """

    problem: TranslationProblem
    """
    Why.
    """

    pair: Optional[Tuple[str, str]] = None
    """
    The names of the colliding bodies, for an obstruction.
    """

    def error_message(self) -> str:
        if self.pair is None:
            return self.problem.value
        return f"{self.problem.value} {self.pair}"


# %% corridor check


@dataclass(frozen=True)
class TranslationClearance:
    """
    The certificate of a sampled straight translation.
    """

    samples: int
    """
    How many base positions were checked, both ends included.
    """

    sample_spacing: float
    """
    The distance between neighbouring checked positions, in metres.
    """

    minimum_clearance: float
    """
    The smallest measured clearance, at most the query distance, in metres.
    """


@dataclass(frozen=True)
class TranslationLimits:
    """
    The sampling and speed limits of workshop translations.
    """

    maximum_sample_spacing: float = 0.005
    """
    The largest distance between neighbouring checked positions, in metres.
    """

    clearance: float = 0.0005
    """
    The clearance kept beyond half a sample spacing, in metres.
    """

    maximum_distance: float = 2.5
    """
    The longest translation, in metres.
    """

    straightness_tolerance: float = 1e-8
    """
    How far the target may differ from the start in height and orientation.
    """

    linear_velocity: float = 0.08
    """
    The base's largest speed, in metres per second.
    """

    angular_velocity: float = 0.1
    """
    The base's largest angular speed, in radians per second.
    """

    translation_threshold: float = 0.001
    """
    How close the base must come to its target, in metres.
    """

    orientation_threshold: float = 0.002
    """
    How close the base's heading must stay, in radians.
    """


TRANSLATION_LIMITS = TranslationLimits()
"""
The limits every workshop translation uses.
"""


@dataclass
class WorkshopTranslation:
    """
    Checks a short base translation against a separate copy of the collision geometry;
    the world's state, model and callbacks stay untouched.

    A margin of half a sample spacing covers obstructions between the sampled positions.
    """

    world: World
    """
    The world supplying the shapes, attachments and collision rules.
    """

    robot: AbstractRobot
    """
    The robot translated with its posture and what it holds.
    """

    target: Pose
    """
    The destination, with the start's height and heading.
    """

    limits: TranslationLimits = TRANSLATION_LIMITS
    """
    The sampling limits.
    """

    def collision_matrix(self) -> CollisionMatrix:
        """
        :return: The world's collision rules applied to a separate matrix.
        """
        manager = self.world.collision_manager
        matrix = CollisionMatrix()
        for rule in manager.rules:
            rule.update(self.world)
        for rule in (
            manager.default_rules
            + manager.temporary_rules
            + manager.ignore_collision_rules
        ):
            rule.apply_to_collision_matrix(matrix)
        return matrix

    def world_target(self) -> Pose:
        """
        :return: The destination in the world's root frame.
        :raises TranslationBlocked: For a base that does not move sideways, a too long
            translation, or a target that turns or raises the base.
        """
        if not isinstance(self.robot.drive, OmniDrive):
            raise TranslationBlocked(TranslationProblem.DRIVE)
        start = self.robot.root.global_pose.to_np()
        target = self.world.transform(self.target, self.world.root)
        value = target.to_np()
        distance = float(np.linalg.norm(value[:3, 3] - start[:3, 3]))
        if not (np.isfinite(value).all() and distance <= self.limits.maximum_distance):
            raise TranslationBlocked(TranslationProblem.LIMITS)
        tolerance = self.limits.straightness_tolerance
        if abs(value[2, 3] - start[2, 3]) > tolerance or not np.allclose(
            value[:3, :3], start[:3, :3], atol=tolerance, rtol=0
        ):
            raise TranslationBlocked(TranslationProblem.ORIENTATION)
        return target

    def validate(self) -> TranslationClearance:
        """
        :return: The certificate of the corridor.
        :raises TranslationBlocked: When the corridor cannot be checked or something
            stands in it.
        """
        with self.world.state.world_lock:
            target = self.world_target()
            displacement = (
                target.to_np()[:3, 3] - self.robot.root.global_pose.to_np()[:3, 3]
            )
            distance = float(np.linalg.norm(displacement))
            intervals = max(1, math.ceil(distance / self.limits.maximum_sample_spacing))
            spacing = distance / intervals
            guard = spacing / 2 + self.limits.clearance
            query_distance = guard + self.limits.maximum_sample_spacing
            moving = set(self.robot.bodies_with_collision)
            checks = [
                check
                for check in self.collision_matrix().collision_checks
                if (check.body_a in moving) != (check.body_b in moving)
            ]
            if not checks:
                raise TranslationBlocked(TranslationProblem.POLICY)
            detector = self.world.collision_manager.collision_detector
            if not isinstance(detector, BulletCollisionDetector):
                raise TranslationBlocked(TranslationProblem.GEOMETRY)
            return CorridorSampling(
                world=self.world,
                detector=detector,
                checks=checks,
                moving=moving,
                displacement=displacement,
                intervals=intervals,
                guard=guard,
                query_distance=query_distance,
            ).run(spacing)


@dataclass
class CorridorSampling:
    """
    Moves copies of the bodies' collision shapes along the corridor in a private Bullet
    world and measures their clearances.
    """

    world: World
    """
    The world whose bodies are copied.
    """

    detector: BulletCollisionDetector
    """
    The world's collision detector, owner of the shapes.
    """

    checks: List[CollisionCheck]
    """
    The collision checks between moving and still bodies.
    """

    moving: Set[Body]
    """
    The robot's bodies with collision shapes.
    """

    displacement: np.ndarray
    """
    The translation, in metres.
    """

    intervals: int
    """
    How many steps the corridor is sampled in.
    """

    guard: float
    """
    The smallest clearance accepted, in metres.
    """

    query_distance: float
    """
    How far the clearance query looks, in metres.
    """

    geometry: bullet.KineverseWorld = field(default_factory=bullet.KineverseWorld)
    """
    The private Bullet world, emptied after the sampling.
    """

    def run(self, spacing: float) -> TranslationClearance:
        """
        :param spacing: The distance between neighbouring samples, in metres.
        :return: The certificate.
        :raises TranslationBlocked: When something stands in the corridor.
        """
        bodies = {body for check in self.checks for body in check.bodies()}
        objects: Dict[Body, bullet.CollisionObject] = {}
        poses = {body: body.global_pose.to_np().copy() for body in bodies}
        for body in bodies:
            copy = create_object(
                body.id, self.detector.body_to_bullet_object[body].collision_shape
            )
            self.geometry.add_collision_object(copy)
            objects[body] = copy
        minimum = self.query_distance
        blocked: Optional[TranslationBlocked] = None
        ordered = list(bodies)
        query = {
            (objects[check.body_a], objects[check.body_b]): self.query_distance
            for check in self.checks
        }
        for index in range(self.intervals + 1):
            fraction = index / self.intervals
            transforms = []
            for body in ordered:
                pose = poses[body].copy()
                if body in self.moving:
                    pose[:3, 3] += self.displacement * fraction
                transforms.append(pose)
            bullet.batch_set_transforms(
                [objects[body] for body in ordered], np.vstack(transforms)
            )
            for contact in self.geometry.get_closest_filtered_map_batch(query):
                separation = float(contact.contact_distance)
                if math.isfinite(separation) and separation >= self.guard:
                    minimum = min(minimum, separation)
                    continue
                blocked = TranslationBlocked(
                    TranslationProblem.OBSTRUCTION,
                    (self.name_of(contact.obj_a), self.name_of(contact.obj_b)),
                )
                break
            if blocked is not None:
                break
        for copy in list(self.geometry.collision_objects):
            self.geometry.remove_collision_object(copy)
        if blocked is not None:
            raise blocked
        return TranslationClearance(self.intervals + 1, spacing, minimum)

    def name_of(self, copy: bullet.CollisionObject) -> str:
        """
        :param copy: A copied collision object.
        :return: The name of the body it was copied from.
        """
        return str(self.world.get_kinematic_structure_entity_by_id(copy.name).name)


# %% motion


@dataclass(eq=False, repr=False)
class WorkshopTranslationGoal(Sequence):
    """
    Moves the base along a checked corridor with collision avoidance, keeping the arm
    and gripper joints where they are.
    """

    translation: WorkshopTranslation = field(kw_only=True)
    """
    The translation, checked again from the posture at expansion.
    """

    base_goal: Optional[CartesianPose] = field(default=None, init=False)
    """
    The base's task, whose observation completes the translation.
    """

    joint_hold: Optional[JointPositionList] = field(default=None, init=False)
    """
    The task keeping the arm and gripper joints, if the robot has any.
    """

    def expand(self, context: MotionStatechartContext) -> None:
        translation = self.translation
        limits = translation.limits
        start = translation.robot.root.global_pose
        destination = translation.world.transform(
            translation.target, translation.world.root
        )
        translation.target = Pose(
            Point3(destination.x, destination.y, start.z),
            start.to_quaternion(),
            reference_frame=translation.world.root,
        )
        translation.validate()
        self.base_goal = CartesianPose(
            root_link=translation.world.root,
            tip_link=translation.robot.root,
            goal_pose=translation.world_target(),
            translation_threshold=limits.translation_threshold,
            orientation_threshold=limits.orientation_threshold,
            reference_linear_velocity=limits.linear_velocity,
            reference_angular_velocity=limits.angular_velocity,
        )
        self.nodes = [self.base_goal]
        super().expand(context)
        self.add_node(
            CartesianVelocityLimit(
                root_link=translation.world.root,
                tip_link=translation.robot.root,
                max_linear_velocity=limits.linear_velocity,
                max_angular_velocity=limits.angular_velocity,
            )
        )
        joints = JointState.from_mapping(
            {
                connection: float(connection.position)
                for connection in translation.robot.controlled_connections
                if isinstance(connection, ActiveConnection1DOF)
            }
        )
        if len(joints):
            self.joint_hold = JointPositionList(goal_state=joints)
            self.add_node(self.joint_hold)
        if not any(
            node.parent_node is None
            for node in self.motion_statechart.get_nodes_by_type(
                ExternalCollisionAvoidance
            )
        ):
            self.add_node(ExternalCollisionAvoidance(robot=translation.robot))

    def build_artifacts(self, context: MotionStatechartContext) -> NodeArtifacts:
        observed = self.base_goal.observation_variable
        if self.joint_hold is not None:
            observed = trinary_logic_and(observed, self.joint_hold.observation_variable)
        return NodeArtifacts(observation=observed)


@dataclass
class WorkshopTranslateMotion(BaseMotion):
    """
    Moves the base to an x and y with its height and heading kept.
    """

    target: Pose
    """
    The destination's x and y.
    """

    requires_individual_execution: ClassVar[bool] = True
    """
    The corridor is checked only after the motions before it ran.
    """

    @property
    def _motion_chart(self) -> MotionStatechartNode:
        return WorkshopTranslationGoal(
            translation=WorkshopTranslation(self.world, self.robot, self.target)
        )


@dataclass
class WorkshopTranslateAction(ActionDescription):
    """
    Moves the robot along a straight corridor without turning its loaded posture.
    """

    target: Pose
    """
    The destination's x and y.
    """

    @property
    def _action_plan(self) -> PlanNode:
        return execute_single(
            WorkshopTranslateMotion(self.target), context=self.context
        )
