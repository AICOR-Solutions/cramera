"""
A plan's steps as the native coraplex actions they name: each value converted by the
kind of its field, the grasp derived from the arm and the object, the constraints'
switches turned on, and the action constructed with keyword arguments.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import Any, Callable, Dict, Iterable, Optional

from coraplex.datastructures.dataclasses import Context
from coraplex.datastructures.grasp import GraspDescription
from coraplex.robot_plans.actions.base import ActionDescription
from coraplex.view_manager import ViewManager
from cramera_plan_builder.cram.actions import DiscoveredAction, DiscoveredActions
from cramera_plan_builder.cram.surfaces import SurfaceTargets
from cramera_plan_builder.exceptions import AnnotationNotInWorld
from cramera_protocol.geometry import Pose as PlannedPose
from cramera_protocol.plan_builder import (
    ActionField,
    ActionFieldKind,
    Destination,
    PlacementMode,
    PlanStep,
)
from semantic_digital_twin.spatial_types import Pose
from semantic_digital_twin.world_description.world_entity import (
    Body,
    SemanticAnnotation,
)

# %% one step


@dataclass(frozen=True)
class StepArguments:
    """
    The keyword arguments of one step's action, converted from the step's values.
    """

    context: Context
    """
    The world and the robot that performs the step.
    """

    bodies: Dict[str, Body]
    """
    The plan's objects by their identity.
    """

    action: DiscoveredAction
    """
    The step's action with its schema and field types.
    """

    step: PlanStep
    """
    The step.
    """

    def arguments(self) -> Dict[str, Any]:
        """
        :return: A value for every field the step gives, a derived grasp for every
            required grasp, and True for every switch its constraints turn on; fields
            the step leaves out keep the action's defaults.
        """
        converters: Dict[ActionFieldKind, Callable[[ActionField, Any], Any]] = {
            ActionFieldKind.BODY: self.body,
            ActionFieldKind.ANNOTATION: self.annotation,
            ActionFieldKind.ENUM: self.member,
            ActionFieldKind.POSE: self.pose,
            ActionFieldKind.POSE_OR_SURFACE: self.poses,
            ActionFieldKind.NUMBER: self.plain,
            ActionFieldKind.INTEGER: self.plain,
            ActionFieldKind.BOOLEAN: self.plain,
            ActionFieldKind.TEXT: self.plain,
        }
        schema = self.action.schema
        arguments = {
            offered.name: converters[offered.kind](
                offered, self.step.values[offered.name]
            )
            for offered in schema.fields
            if offered.name in self.step.values
        }
        for offered in schema.fields:
            if offered.kind is ActionFieldKind.GRASP and offered.required:
                arm, body = offered.derived_from
                arguments[offered.name] = self.grasp(arguments[arm], arguments[body])
        for constraint in self.step.constraints:
            if constraint.switch is not None and self.is_switch(constraint.switch):
                arguments[constraint.switch] = True
        return arguments

    def is_switch(self, name: str) -> bool:
        """
        :param name: A field name a constraint turns on.
        :return: Whether the action has a boolean field of that name.
        """
        offered = self.action.schema.field_named(name)
        return offered is not None and offered.kind is ActionFieldKind.BOOLEAN

    def body(self, offered: ActionField, value: str) -> Body:
        """
        :param offered: A body field.
        :param value: An object's identity.
        :return: The object's body.
        """
        return self.bodies[value]

    def annotation(self, offered: ActionField, value: str) -> SemanticAnnotation:
        """
        :param offered: An annotation field.
        :param value: The name of an annotation of the field's class.
        :return: The world's annotation of that class and name.
        :raises AnnotationNotInWorld: When the world has none.
        """
        annotation_class = self.action.field_types[offered.name]
        for candidate in self.context.world.get_semantic_annotations_by_type(
            annotation_class
        ):
            if str(candidate.name) == value:
                return candidate
        raise AnnotationNotInWorld(offered.annotation, value)

    def member(self, offered: ActionField, value: str) -> Any:
        """
        :param offered: An enumeration field.
        :param value: A member's name.
        :return: The member.
        """
        return self.action.field_types[offered.name][value]

    def pose(self, offered: ActionField, value: Any) -> Pose:
        """
        :param offered: A pose field.
        :param value: A pose, or a destination when the field accepts a surface.
        :return: The pose, or the best rated spot of the surface now.
        """
        if not offered.accepts_surface:
            return self.native(PlannedPose.from_json(value))
        destination = Destination.from_json(value)
        if destination.placement is PlacementMode.POSE:
            return self.native(destination.pose)
        return self.surface(destination).first()

    def poses(self, offered: ActionField, value: Any) -> Pose | Iterable[Pose]:
        """
        :param offered: A field taking a pose or poses to try.
        :param value: A destination.
        :return: The pose, or the spots of the surface, sampled when the step runs.
        """
        destination = Destination.from_json(value)
        if destination.placement is PlacementMode.POSE:
            return self.native(destination.pose)
        return self.surface(destination)

    @staticmethod
    def plain(offered: ActionField, value: Any) -> Any:
        """
        :param offered: A number, integer, boolean or text field.
        :param value: Its value.
        :return: The value, which JSON already holds as the native type.
        """
        return value

    def surface(self, destination: Destination) -> SurfaceTargets:
        """
        :param destination: A destination on a surface.
        :return: The spots of the surface for the step's object.
        """
        return SurfaceTargets(
            world=self.context.world,
            body=self.bodies[self.object_identifier()],
            surface_type=destination.surface_type,
            surface_name=destination.surface_name,
        )

    def object_identifier(self) -> Optional[str]:
        """
        :return: The identity of the object the step acts on: the value of its action's
            first body field.
        """
        for offered in self.action.schema.fields:
            if offered.kind is ActionFieldKind.BODY:
                return self.step.values.get(offered.name)
        return None

    def grasp(self, arm: Any, body: Body) -> GraspDescription:
        """
        :param arm: The arm the step uses.
        :param body: The object it acts on.
        :return: The default grasp for the object as it lies, the approach side
            following the robot's reach.
        """
        return GraspDescription.robot_relative_default(
            ViewManager.get_end_effector_view(arm, self.context.robot),
            body.global_pose,
            body,
        )

    def native(self, planned: PlannedPose) -> Pose:
        """
        :param planned: A pose of the plan, in world coordinates.
        :return: The native pose in the world's root frame.
        """
        return Pose.from_xyz_quaternion(
            *planned.to_json(), reference_frame=self.context.world.root
        )


# %% actions


@dataclass(frozen=True)
class StepActions:
    """
    Builds the native action of each step against the world and robot of a context.
    """

    context: Context
    """
    The world and the robot that performs the steps.
    """

    bodies: Dict[str, Body]
    """
    The plan's objects by their identity.
    """

    actions: DiscoveredActions
    """
    The workspace's actions, which steps name by class name.
    """

    def action(self, step: PlanStep) -> ActionDescription:
        """
        :param step: A step the plan builder checked against its action's schema.
        :return: The native action the step stands for.
        :raises UnknownAction: When the workspace has no action of the step's name.
        """
        discovered = self.actions.named(step.action)
        arguments = StepArguments(
            context=self.context, bodies=self.bodies, action=discovered, step=step
        ).arguments()
        return discovered.action_class(**arguments)
