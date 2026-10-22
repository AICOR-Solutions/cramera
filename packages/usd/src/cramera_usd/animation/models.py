"""
The URDF models and free objects a playback puts into a bundle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy
from typing_extensions import Dict, List

from cramera_usd.geometry.transforms import SPACE_DIMENSIONS, TransformTrack
from cramera_usd.names import NameSeparator
from cramera_usd.scene.kinematics import Joint, Link

# %% constants

HEIGHT_COLUMN = SPACE_DIMENSIONS - 1
"""
The column of a point holding its height.
"""

# %% models


@dataclass
class KinematicModel:
    """
    One URDF model of a bundle: links and the joints between them.
    """

    name: str
    """
    The model's name in ``scene.json``.
    """

    links: List[Link]
    """
    The links, the root first and parents before children.
    """

    joints: List[Joint]
    """
    One joint per link except the root.
    """

    prefix: str = ""
    """
    What the trajectory puts before the model's joint names.
    """

    @property
    def robot(self) -> bool:
        """
        Whether the model is the robot.
        """
        return False

    @property
    def movable_joints(self) -> List[Joint]:
        """
        The joints whose value can change, in tree order.
        """
        return [joint for joint in self.joints if joint.movable]

    def key_of(self, joint: Joint) -> str:
        """
        :param joint: One of the model's joints.
        :return: The joint's key in the trajectory.
        """
        if not self.prefix:
            return joint.name
        return f"{self.prefix}{NameSeparator.MODEL_PREFIX}{joint.name}"


@dataclass
class RobotModel(KinematicModel):
    """
    The robot's model, placed in the world by the trajectory's base pose.
    """

    parts: Dict[str, List[str]] = field(default_factory=dict)
    """
    The names of the robot's links, grouped by the prim they were assembled under.
    """

    @property
    def robot(self) -> bool:
        return True

    @property
    def base_link(self) -> str:
        """
        The name of the root link, whose world pose the base track holds.
        """
        return self.links[0].name


# %% placements and objects

NO_MODEL = ""
"""
The model of a link that no model or object holds.
"""


@dataclass(frozen=True)
class LinkPlacement:
    """
    Where a converted link ended up in the bundle.
    """

    model: str
    """
    The name of the model, or the key of the object, holding the link; empty when none
    does.
    """

    link: str
    """
    The link's name in that model.
    """


@dataclass(eq=False)
class AnimatedObject:
    """
    A link that moves on its own, played back by its world pose per frame.
    """

    key: str
    """
    The object's key in ``scene.json`` and the trajectory.
    """

    link: Link
    """
    The link, its geometry in the object frame.
    """

    poses: TransformTrack
    """
    The world pose of the object frame per frame.
    """

    @property
    def height(self) -> float:
        """
        The extent of the geometry along the object frame's Z axis.
        """
        heights = [
            numpy.ptp(mesh.geometry.points[:, HEIGHT_COLUMN])
            for mesh in self.link.meshes
        ]
        return float(max(heights, default=0.0))
