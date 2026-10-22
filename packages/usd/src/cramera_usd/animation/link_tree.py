"""
The links of a converted stage as the tree their joints form, the world poses of their
prims under a trace, and the joint values those poses imply.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy
from typing_extensions import Dict, List, Optional, Self

from cramera_usd.animation.deviation import PoseDeviation
from cramera_usd.animation.trace import BodyTrace
from cramera_usd.geometry.transforms import (
    NEGATIVE_ZERO_REMOVAL,
    RigidTransform,
    TransformTrack,
)
from cramera_usd.names import PrimPath
from cramera_usd.scene.kinematics import Joint, Link
from cramera_usd.scene.stage import ConvertedStage

# %% tree


@dataclass
class LinkTree:
    """
    The links of a converted stage as the tree their joints form.
    """

    stage: ConvertedStage
    """
    The converted stage.
    """

    @cached_property
    def links(self) -> Dict[str, Link]:
        """
        Every link by name.
        """
        return {link.name: link for link in self.stage.links}

    @cached_property
    def links_by_path(self) -> Dict[str, Link]:
        """
        Every link by the path of the prim it stands for.
        """
        return {link.path: link for link in self.stage.links}

    @cached_property
    def parent_joints(self) -> Dict[str, Joint]:
        """
        The joint holding each link except the root, by child link name.
        """
        return {joint.child: joint for joint in self.stage.joints}

    @cached_property
    def children(self) -> Dict[str, List[str]]:
        """
        The names of each link's child links, in tree order.
        """
        children: Dict[str, List[str]] = {link: [] for link in self.links}
        for link in self.stage.links:
            joint = self.parent_joints.get(link.name)
            if joint is not None:
                children[joint.parent].append(link.name)
        return children

    def subtree(self, name: str) -> List[str]:
        """
        :param name: A link's name.
        :return: The link and every link below it, parents before children.
        """
        names = [name]
        for current in names:
            names += self.children[current]
        return names


# %% body poses


@dataclass
class BodyPoses:
    """
    The world pose track of any prim a link stands for: recorded, carried along by a
    recorded ancestor prim, or at rest at its initial pose.
    """

    trace: BodyTrace
    """
    The recorded body poses.
    """

    initial: Dict[str, RigidTransform]
    """
    The initial rigid world pose of every link's prim, by path.
    """

    @classmethod
    def of_stage(cls, trace: BodyTrace, stage: ConvertedStage) -> Self:
        """
        :param trace: The recorded body poses.
        :param stage: The converted stage.
        :return: The body poses of the stage's links under the trace.
        """
        return cls(trace, {link.path: link.prim_pose for link in stage.links})

    def of(self, path: Optional[str]) -> TransformTrack:
        """
        :param path: A prim's path, or None for the world.
        :return: The prim's world pose track.
        """
        frame_count = self.trace.frame_count
        if path is None:
            return TransformTrack.constant(RigidTransform(), frame_count)
        if path in self.trace.poses:
            return self.trace.poses[path]
        carrier = self.carrier_of(path)
        if carrier is None:
            return TransformTrack.constant(self.initial[path], frame_count)
        return self.trace.poses[carrier] @ (
            self.initial[carrier].inverse() @ self.initial[path]
        )

    def carrier_of(self, path: str) -> Optional[str]:
        """
        :param path: A prim's path.
        :return: The nearest recorded ancestor of the prim, or None.
        """
        ancestors = [
            recorded
            for recorded in self.trace.poses
            if PrimPath(recorded).strictly_holds(path) and recorded in self.initial
        ]
        return max(ancestors, key=len, default=None)


# %% joint motion


@dataclass(eq=False)
class JointMotion:
    """
    The values a movable joint takes over a trace, recovered from the world poses of its
    two bodies.
    """

    joint: Joint
    """
    The joint.
    """

    values: numpy.ndarray
    """
    The joint value per frame, in radians or metres; revolute values are kept within the
    joint's limits and continuous values free of jumps.
    """

    off_axis: PoseDeviation
    """
    The part of the bodies' relative motion the joint cannot make, per frame.
    """

    @classmethod
    def recover(
        cls,
        joint: Joint,
        parent_body: TransformTrack,
        child_body: TransformTrack,
        decimals: int,
    ) -> Self:
        """
        :param joint: A movable joint.
        :param parent_body: The world poses of the joint's parent body.
        :param child_body: The world poses of the joint's child body.
        :param decimals: The decimals kept of the values.
        :return: The motion of the joint between the two body pose tracks.
        """
        relative = joint.relative_motion(parent_body, child_body)
        values = joint.motion.values_of(relative)
        return cls(
            joint,
            numpy.round(values, decimals) + NEGATIVE_ZERO_REMOVAL,
            PoseDeviation.between(joint.motion.transforms(values), relative),
        )
