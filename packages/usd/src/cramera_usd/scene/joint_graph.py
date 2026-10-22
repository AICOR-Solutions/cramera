"""
The joints read from a stage as edges between their bodies.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import List, Set

from cramera_usd.names import PrimPath
from cramera_usd.scene.kinematics import Joint

# %% graph


@dataclass
class JointGraph:
    """
    The joints read from a stage, as edges from their parent body to their child body.
    """

    joints: List[Joint]
    """
    The joints, in stage order.
    """

    def movable_joints_below(self, bodies: Set[str]) -> List[str]:
        """
        :param bodies: The USD paths of some bodies.
        :return: The USD paths of the movable joints that move one of the bodies or a
            body hanging from them, in stage order.
        """
        reached = set(bodies)
        grown = True
        while grown:
            below = {
                joint.child_body
                for joint in self.joints
                if joint.parent_body in reached and joint.child_body not in reached
            }
            reached |= below
            grown = bool(below)
        return [
            joint.path
            for joint in self.joints
            if joint.movable and joint.child_body in reached
        ]

    def bodies_in(self, path: str) -> Set[str]:
        """
        :param path: The USD path of a prim.
        :return: The USD paths of the joint bodies that are the prim or lie below it.
        """
        ends = {
            body
            for joint in self.joints
            for body in (joint.parent_body, joint.child_body)
            if body is not None
        }
        return {body for body in ends if PrimPath(path).holds(body)}
