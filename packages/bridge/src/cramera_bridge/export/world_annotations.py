"""
The semantic annotations of a world other than its robots and their parts, as a scene
bundle names them: each by its name and class, with the bodies it gives a meaning to.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from typing_extensions import Dict, List

from cramera_bridge.names import class_path
from cramera_bridge.scenes.semantics import UsdPrimAnnotation
from cramera_protocol.bundle.scene import SceneAnnotation
from semantic_digital_twin.robots.robot_parts import AbstractRobot, AbstractRobotPart
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import SemanticAnnotation

UNNAMED_ANNOTATIONS = (AbstractRobot, AbstractRobotPart, UsdPrimAnnotation)
"""
The annotations a scene does not list among its annotations: the robots and their parts,
which the scene's robot describes, and the prim annotations carrying a converted stage's
attributes, whose class is no class of the ontology.
"""


@dataclass(frozen=True)
class WorldAnnotations:
    """
    Describes the semantic annotations of a world for ``scene.json``.
    """

    world: World
    """
    The world holding the annotations.
    """

    def annotations(self) -> List[SemanticAnnotation]:
        """
        :return: The world's annotations other than :data:`UNNAMED_ANNOTATIONS`.
        """
        return [
            annotation
            for annotation in self.world.semantic_annotations
            if not isinstance(annotation, UNNAMED_ANNOTATIONS)
        ]

    def descriptions(self, body_names: Dict[UUID, str]) -> List[SceneAnnotation]:
        """
        :param body_names: The name a bundle gives each of its bodies, a link name or a
            free object identifier, by the body's identity.
        :return: The annotations naming any of those bodies, sorted by name and class,
            each naming its bodies once, in the order the annotation holds them.
        """
        descriptions = []
        for annotation in self.annotations():
            bodies = [
                body_names[body.id]
                for body in annotation.bodies
                if body.id in body_names
            ]
            if not bodies:
                continue
            descriptions.append(
                SceneAnnotation(
                    name=str(annotation.name),
                    class_path=class_path(type(annotation)),
                    bodies=list(dict.fromkeys(bodies)),
                )
            )
        return sorted(
            descriptions,
            key=lambda description: (description.name, description.class_path),
        )
