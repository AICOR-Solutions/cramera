"""
Short, readable names for a robot's links and joints.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import cached_property
from itertools import takewhile

from typing_extensions import Dict, List

from cramera_usd.animation.link_tree import LinkTree
from cramera_usd.animation.models import RobotModel
from cramera_usd.names import GeneratedName, NameSeparator, PrimPath, UniqueNames
from cramera_usd.scene.kinematics import Joint

# %% naming


@dataclass(eq=False)
class RobotNaming:
    """
    Short, readable names for a robot's links and joints: the names of their prims,
    numbered where they repeat.
    """

    tree: LinkTree
    """
    The links of the converted stage.
    """

    links: List[str]
    """
    The converted names of the robot's links, the root first.
    """

    @cached_property
    def link_names(self) -> Dict[str, str]:
        """
        The robot's name of each link, by converted name.
        """
        return UniqueNames().claim_each(
            {name: PrimPath(self.tree.links[name].path).name for name in self.links}
        )

    @cached_property
    def joints(self) -> List[Joint]:
        """
        The joints inside the robot, in tree order.
        """
        return [self.tree.parent_joints[name] for name in self.links[1:]]

    @cached_property
    def joint_names(self) -> Dict[str, str]:
        """
        The robot's name of each joint, by converted name; a joint the converter
        generated is named after its child link.
        """
        return UniqueNames().claim_each(
            {joint.name: self.joint_name(joint) for joint in self.joints}
        )

    def joint_name(self, joint: Joint) -> str:
        """
        :param joint: A joint inside the robot.
        :return: The name the joint asks for: its prim's name, or its child link's name
            with the attachment suffix for a generated joint.
        """
        if not joint.generated:
            return PrimPath(joint.path).name
        return (
            f"{self.link_names[joint.child]}{NameSeparator.GENERATED_PART}"
            f"{GeneratedName.ATTACHMENT}"
        )

    def model(self) -> RobotModel:
        """
        :return: The robot's model under its own names, named after its root prim.
        """
        name = self.link_names[self.links[0]].lower()
        links = [
            replace(self.tree.links[link], name=self.link_names[link])
            for link in self.links
        ]
        joints = [
            replace(
                joint,
                name=self.joint_names[joint.name],
                parent=self.link_names[joint.parent],
                child=self.link_names[joint.child],
            )
            for joint in self.joints
        ]
        return RobotModel(name, links, joints, prefix=name, parts=self.parts(name))

    def parts(self, robot_name: str) -> Dict[str, List[str]]:
        """
        :param robot_name: The robot model's name.
        :return: The robot's links grouped by the prim right below the prim all of them
            share; links standing for that shared prim itself form a part named after
            the robot.
        """
        paths = {
            name: PrimPath(self.tree.links[name].path).elements for name in self.links
        }
        shared = len(
            list(
                takewhile(
                    lambda elements: len(set(elements)) == 1, zip(*paths.values())
                )
            )
        )
        parts: Dict[str, List[str]] = {}
        for name, elements in paths.items():
            part = elements[shared] if len(elements) > shared else robot_name
            parts.setdefault(part, []).append(self.link_names[name])
        return parts
