"""
The URDF of a model of a converted stage: one link per converted link with its GLB as
visual, and one joint per non-root link.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from enum import StrEnum

import numpy
from typing_extensions import Dict, List, Sequence, Union

from cramera_usd.geometry.transforms import NEGATIVE_ZERO_REMOVAL, RigidTransform
from cramera_usd.scene.kinematics import Joint, JointKind, Link

# %% URDF vocabulary


class UrdfTag(StrEnum):
    """
    The URDF elements the writer emits.
    """

    ROBOT = "robot"
    """
    The document root.
    """

    LINK = "link"
    """
    A rigid body.
    """

    VISUAL = "visual"
    """
    A link's visual geometry.
    """

    GEOMETRY = "geometry"
    """
    The shape of a visual.
    """

    MESH = "mesh"
    """
    A mesh file shape.
    """

    JOINT = "joint"
    """
    A joint between two links.
    """

    PARENT = "parent"
    """
    A joint's parent link.
    """

    CHILD = "child"
    """
    A joint's child link.
    """

    ORIGIN = "origin"
    """
    A joint's frame in its parent link.
    """

    AXIS = "axis"
    """
    A joint's motion axis.
    """

    LIMIT = "limit"
    """
    A joint's limits.
    """


class UrdfAttribute(StrEnum):
    """
    The URDF attributes the writer emits.
    """

    NAME = "name"
    """
    The name of a link, joint or robot.
    """

    TYPE = "type"
    """
    A joint's kind.
    """

    FILENAME = "filename"
    """
    A mesh file, relative to the URDF.
    """

    LINK = "link"
    """
    The link a parent or child element names.
    """

    TRANSLATION = "xyz"
    """
    A translation or axis.
    """

    ROTATION = "rpy"
    """
    Fixed-axis roll, pitch and yaw.
    """

    LOWER = "lower"
    """
    The lowest joint value.
    """

    UPPER = "upper"
    """
    The highest joint value.
    """

    EFFORT = "effort"
    """
    The largest joint force or torque.
    """

    VELOCITY = "velocity"
    """
    The largest joint speed.
    """


class XmlEncoding(StrEnum):
    """
    The encoding the URDF file is written in.
    """

    UTF_8 = "utf-8"
    """
    UTF-8, declared in the XML declaration.
    """


NUMBER_FORMAT = ".9g"
"""
How a number is written: nine significant digits, without needless ones.
"""

NUMBER_SEPARATOR = " "
"""
Between the numbers of one attribute.
"""

# %% writer


@dataclass
class UrdfDocument:
    """
    A URDF document for links and joints of a converted stage.
    """

    name: str
    """
    The robot name in the URDF.
    """

    links: List[Link]
    """
    The links, parents before children.
    """

    joints: List[Joint]
    """
    One joint per non-root link.
    """

    mesh_files: Dict[str, str]
    """
    The GLB file of every link with geometry, relative to the URDF, by link name.
    """

    effort_limit: float = 1000.0
    """
    The effort written for every movable joint; USD stages author none.
    """

    velocity_limit: float = 1.0
    """
    The velocity written for every movable joint; USD stages author none.
    """

    unbounded_travel: float = 1000.0
    """
    The travel in metres written for a sliding joint without authored limits, which URDF
    cannot express.
    """

    def to_element(self) -> ElementTree.Element:
        """
        :return: The URDF document as an XML element.
        """
        robot = ElementTree.Element(UrdfTag.ROBOT, {UrdfAttribute.NAME: self.name})
        for link in self.links:
            self.add_link(robot, link)
        for joint in self.joints:
            self.add_joint(robot, joint)
        ElementTree.indent(robot)
        return robot

    def add_link(self, robot: ElementTree.Element, link: Link) -> None:
        """
        Add one link element, with its GLB as visual when it has geometry.

        :param robot: The document root.
        :param link: The link.
        """
        element = ElementTree.SubElement(
            robot, UrdfTag.LINK, {UrdfAttribute.NAME: link.name}
        )
        if not link.meshes:
            return
        geometry = ElementTree.SubElement(
            ElementTree.SubElement(element, UrdfTag.VISUAL), UrdfTag.GEOMETRY
        )
        ElementTree.SubElement(
            geometry, UrdfTag.MESH, {UrdfAttribute.FILENAME: self.mesh_files[link.name]}
        )

    def add_joint(self, robot: ElementTree.Element, joint: Joint) -> None:
        """
        Add one joint element.

        :param robot: The document root.
        :param joint: The joint.
        """
        motion = joint.motion
        element = ElementTree.SubElement(
            robot,
            UrdfTag.JOINT,
            {UrdfAttribute.NAME: joint.name, UrdfAttribute.TYPE: motion.kind.value},
        )
        ElementTree.SubElement(
            element, UrdfTag.PARENT, {UrdfAttribute.LINK: joint.parent}
        )
        ElementTree.SubElement(
            element, UrdfTag.CHILD, {UrdfAttribute.LINK: joint.child}
        )
        ElementTree.SubElement(
            element, UrdfTag.ORIGIN, self.origin_attributes(joint.origin)
        )
        if not motion.kind.movable:
            return
        ElementTree.SubElement(
            element,
            UrdfTag.AXIS,
            {UrdfAttribute.TRANSLATION: self.numbers(motion.axis)},
        )
        limit = {
            UrdfAttribute.EFFORT: self.numbers([self.effort_limit]),
            UrdfAttribute.VELOCITY: self.numbers([self.velocity_limit]),
        }
        if motion.kind is not JointKind.CONTINUOUS:
            limit[UrdfAttribute.LOWER] = self.numbers(
                [-self.unbounded_travel if motion.lower is None else motion.lower]
            )
            limit[UrdfAttribute.UPPER] = self.numbers(
                [self.unbounded_travel if motion.upper is None else motion.upper]
            )
        ElementTree.SubElement(element, UrdfTag.LIMIT, limit)

    def origin_attributes(self, pose: RigidTransform) -> Dict[str, str]:
        """
        :param pose: A pose.
        :return: Its ``xyz`` and ``rpy`` attributes.
        """
        return {
            UrdfAttribute.TRANSLATION: self.numbers(pose.translation),
            UrdfAttribute.ROTATION: self.numbers(pose.roll_pitch_yaw),
        }

    @staticmethod
    def numbers(values: Union[numpy.ndarray, Sequence[float]]) -> str:
        """
        :param values: Numbers.
        :return: The numbers separated by spaces, without needless digits and without
            negative zeros.
        """
        return NUMBER_SEPARATOR.join(
            format(float(value) + NEGATIVE_ZERO_REMOVAL, NUMBER_FORMAT)
            for value in values
        )

    def to_bytes(self) -> bytes:
        """
        :return: The URDF file's content, with its XML declaration.
        """
        stream = io.BytesIO()
        ElementTree.ElementTree(self.to_element()).write(
            stream, encoding=XmlEncoding.UTF_8, xml_declaration=True
        )
        return stream.getvalue()
