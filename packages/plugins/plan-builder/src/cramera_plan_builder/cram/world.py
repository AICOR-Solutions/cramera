"""
The world a plan runs in: its environment, an empty floor when it names none, and the
free objects it places.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Dict, List

from cramera_cram.scenes.bundle_world import ColorText, PoseText
from cramera_cram.scenes.environment import SceneEnvironment
from cramera_plan_builder.cram.workspace import OBJECT_DIRECTORY
from cramera_protocol.plan_builder import PlannedObject
from semantic_digital_twin.semantic_annotations.mixins import HasGraspCandidates
from semantic_digital_twin.specifications.connections import (
    Connection6DoFSpecification,
)
from semantic_digital_twin.specifications.kinematic_structure_entities import (
    BodySpecification,
)
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

# %% environment


@dataclass
class EmptyFloor(SceneEnvironment):
    """
    The environment of a plan that names none: nothing but the world's root.
    """

    def populate(self, world: World) -> None:
        """
        Add nothing.

        :param world: The world.
        """


# %% objects


@dataclass(eq=False)
class PlannedGraspable(HasGraspCandidates):
    """
    A free object of a plan, which coraplex's actions take hold of and put down: grasped
    around its own origin, as nothing more is known of its shape.
    """

    @classmethod
    def of(cls, body: Body) -> PlannedGraspable:
        """
        :param body: The body of an object the plan placed.
        :return: The object's annotation.
        """
        (annotation,) = [
            annotation
            for annotation in body._world.get_semantic_annotations_by_type(cls)
            if annotation.root is body
        ]
        return annotation


@dataclass(frozen=True)
class PlannedObjects:
    """
    The free objects of a plan, each a copy of an object mesh that moves on its own.
    """

    objects: List[PlannedObject]
    """
    The objects.
    """

    directory: Path = field(default=OBJECT_DIRECTORY)
    """
    The directory of the object meshes.
    """

    def spawn(self, world: World) -> Dict[str, Body]:
        """
        :param world: The world receiving the objects at their start poses, below its
            root, each annotated as graspable.
        :return: Each object's body by its identity.
        """
        bodies = {
            planned.identifier: BodySpecification.mesh(
                planned.identifier,
                str(self.directory / planned.model),
                color=(
                    ColorText(planned.color).native()
                    if planned.color is not None
                    else None
                ),
                connection_specification=Connection6DoFSpecification(),
            ).spawn(world, parent_T_self=PoseText(planned.pose).native(world.root))
            for planned in self.objects
        }
        with world.modify_world():
            for body in bodies.values():
                world.add_semantic_annotation(PlannedGraspable(root=body))
        return bodies
