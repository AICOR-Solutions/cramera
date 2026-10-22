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
from semantic_digital_twin.api import BodySpecification, Connection6DoFSpecification
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
            root.
        :return: Each object's body by its identity.
        """
        return {
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
