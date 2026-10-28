"""
The standalone rigid bodies of a static scene as free objects, each carrying the bodies
nested in it, and the environment model that remains.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from typing_extensions import Dict, List

from cramera_usd.animation.animator import ENVIRONMENT_MODEL
from cramera_usd.animation.models import (
    AnimatedObject,
    KinematicModel,
    LinkPlacement,
    LinkPlacements,
)
from cramera_usd.geometry.transforms import TransformTrack
from cramera_usd.names import ObjectNames
from cramera_usd.scene.kinematics import Link
from cramera_usd.scene.stage import ConvertedStage

# %% constants

STATIC_FRAME_COUNT = 1
"""
The frames of a static scene, which hold every free object at its spawn pose.
"""

# %% free objects


@dataclass
class FreeObjects(LinkPlacements):
    """
    The standalone rigid bodies of a static scene as free objects a CRAM world can pick
    up, and the environment that remains.
    """

    stage: ConvertedStage
    """
    The converted stage.
    """

    environment_name: str = ENVIRONMENT_MODEL
    """
    The name of the remaining environment model.
    """

    objects: List[AnimatedObject] = field(init=False)
    """
    One object per standalone body, its geometry and collision boxes and those of the
    bodies nested in it in the body's frame, keyed by the body's name among the objects
    (:class:`~cramera_usd.names.ObjectNames`).
    """

    placements: Dict[str, LinkPlacement] = field(init=False)
    """
    Where each converted link ended up, by converted link name.
    """

    def __post_init__(self) -> None:
        links = {link.name: link for link in self.stage.links}
        standalone = [link for link in self.stage.links if link.standalone]
        keys = ObjectNames([link.path for link in standalone]).by_path
        self.objects = []
        self.placements = {
            link.name: LinkPlacement(self.environment_name, link.name)
            for link in self.stage.links
        }
        for link in standalone:
            carried = [links[name] for name in self.subtree(link.name)]
            key = keys[link.path]
            self.objects.append(
                AnimatedObject(
                    key,
                    self.merged(link, carried),
                    TransformTrack.constant(link.pose, STATIC_FRAME_COUNT),
                )
            )
            self.placements.update(
                {item.name: LinkPlacement(key, key) for item in carried}
            )

    def subtree(self, name: str) -> List[str]:
        """
        :param name: A link name.
        :return: The link and every link below it.
        """
        children: Dict[str, List[str]] = {}
        for joint in self.stage.joints:
            children.setdefault(joint.parent, []).append(joint.child)
        names = [name]
        for current in names:
            names += children.get(current, [])
        return names

    @staticmethod
    def merged(link: Link, carried: List[Link]) -> Link:
        """
        :param link: A standalone link.
        :param carried: The link and the links below it.
        :return: The link holding the geometry and collision boxes of every carried
            link, in its own frame.
        """
        to_object = {item.name: link.pose.inverse() @ item.pose for item in carried}
        return replace(
            link,
            meshes=[
                mesh.moved(to_object[item.name])
                for item in carried
                for mesh in item.meshes
            ],
            collisions=[
                box.moved(to_object[item.name])
                for item in carried
                for box in item.collisions
            ],
        )

    @property
    def environment(self) -> KinematicModel:
        """
        The links and joints no object carries.
        """
        kept = {
            name
            for name, placement in self.placements.items()
            if placement.model == self.environment_name
        }
        return KinematicModel(
            self.environment_name,
            [link for link in self.stage.links if link.name in kept],
            [joint for joint in self.stage.joints if joint.child in kept],
        )

    def placement_of(self, link: str) -> LinkPlacement:
        return self.placements[link]
