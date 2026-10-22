"""
The workshop's contact world as MuJoCo XML: every URDF of the bundle with its collision
primitives, joints and inertia, each loose object on a free joint.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from typing_extensions import Dict, List, Optional, Sequence

from cramera_protocol.geometry import Pose
from cramera_workshop.bundle import WorkshopBundle
from cramera_workshop.exceptions import UnsupportedCollisionShape

ZERO_VECTOR = "0 0 0"
"""
A URDF origin's translation and rotation when it gives none.
"""

DEFAULT_AXIS = "0 0 1"
"""
A URDF joint's axis when it gives none.
"""

INERTIA_ORDER = ("ixx", "iyy", "izz", "ixy", "ixz", "iyz")
"""
The URDF inertia attributes in the order MuJoCo's ``fullinertia`` takes them.
"""

FREE_JOINT_SUFFIX = "_free"
"""
What a loose object's free joint is named after the object.
"""

COLLISION_INFIX = "_collision_"
"""
What separates a link's name from the index of its collision geometry.
"""

# %% vocabulary


class UrdfTag(StrEnum):
    """
    The URDF elements and attributes the contact world reads.
    """

    LINK = "link"
    """
    A link.
    """

    JOINT = "joint"
    """
    A joint.
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
    A pose relative to the parent.
    """

    AXIS = "axis"
    """
    A joint's axis.
    """

    LIMIT = "limit"
    """
    A joint's limits.
    """

    INERTIAL = "inertial"
    """
    A link's mass properties.
    """

    INERTIA = "inertia"
    """
    A link's inertia tensor.
    """

    MASS = "mass"
    """
    A link's mass.
    """

    COLLISION = "collision"
    """
    A link's collision geometry.
    """

    GEOMETRY = "geometry"
    """
    The shape of a collision.
    """

    NAME = "name"
    """
    The name attribute.
    """

    TYPE = "type"
    """
    A joint's type attribute.
    """

    XYZ = "xyz"
    """
    A translation attribute.
    """

    RPY = "rpy"
    """
    A roll, pitch and yaw attribute.
    """

    LOWER = "lower"
    """
    A limit's lower end.
    """

    UPPER = "upper"
    """
    A limit's upper end.
    """

    VALUE = "value"
    """
    A mass's value.
    """

    SIZE = "size"
    """
    A box's full size.
    """

    RADIUS = "radius"
    """
    A cylinder's or sphere's radius.
    """

    LENGTH = "length"
    """
    A cylinder's length.
    """


class UrdfJointType(StrEnum):
    """
    The URDF joint types the contact world distinguishes.
    """

    FIXED = "fixed"
    """
    A rigid connection.
    """

    PRISMATIC = "prismatic"
    """
    A sliding joint.
    """


class UrdfShape(StrEnum):
    """
    The URDF collision shapes the contact world builds.
    """

    BOX = "box"
    """
    A box, by its full size.
    """

    CYLINDER = "cylinder"
    """
    A cylinder along local z, by radius and length.
    """

    SPHERE = "sphere"
    """
    A sphere, by radius.
    """


class MujocoTag(StrEnum):
    """
    The MuJoCo XML elements and attribute values the contact world writes.
    """

    ROOT = "mujoco"
    """
    The document's root.
    """

    COMPILER = "compiler"
    """
    The compiler settings.
    """

    OPTION = "option"
    """
    The simulation settings.
    """

    DEFAULT = "default"
    """
    The default attributes.
    """

    WORLD_BODY = "worldbody"
    """
    The world's bodies.
    """

    BODY = "body"
    """
    A body.
    """

    GEOM = "geom"
    """
    A collision geometry.
    """

    JOINT = "joint"
    """
    A joint.
    """

    FREE_JOINT = "freejoint"
    """
    A six degree of freedom joint.
    """

    INERTIAL = "inertial"
    """
    A body's mass properties.
    """

    SLIDE = "slide"
    """
    A sliding joint type.
    """

    HINGE = "hinge"
    """
    A rotating joint type.
    """

    RADIAN = "radian"
    """
    Angles in radians.
    """

    FALSE = "false"
    """
    A false attribute value.
    """

    IMPLICIT_FAST = "implicitfast"
    """
    MuJoCo's implicit integrator with fast derivatives.
    """

    ELLIPTIC = "elliptic"
    """
    Elliptic friction cones.
    """


class MujocoAttribute(StrEnum):
    """
    The MuJoCo XML attributes the contact world writes from computed dictionaries.
    """

    POSITION = "pos"
    """
    A body's or geom's position.
    """

    QUATERNION = "quat"
    """
    A body's or geom's orientation, scalar first.
    """

    TYPE = "type"
    """
    A geom's shape.
    """

    SIZE = "size"
    """
    A geom's half extents or radii.
    """


# %% settings


@dataclass(frozen=True)
class ContactSettings:
    """
    The solver and contact settings of the contact world.
    """

    timestep: float = 0.001
    """
    The integration interval, in seconds.
    """

    friction: Sequence[float] = (0.35, 0.005, 0.0001)
    """
    The sliding, torsional and rolling friction of every contact.
    """

    contact_time: float = 0.004
    """
    The contacts' response time, longer than two integration steps, in seconds.
    """

    contact_damping_ratio: float = 1.0
    """
    The contacts' damping ratio.
    """

    impedance: Sequence[float] = (0.95, 0.99, 0.0001)
    """
    MuJoCo's contact impedance: at no penetration, at full penetration, and the
    penetration in metres over which it changes.
    """

    contact_dimension: int = 4
    """
    MuJoCo's contact dimensionality: normal, sliding and torsional friction.
    """

    solver_iterations: int = 80
    """
    The constraint solver's iterations per step.
    """

    joint_damping: float = 2.0
    """
    The damping of the drawers' joints, in newton seconds per metre.
    """

    model_name: str = "aicor_workshop_contact"
    """
    The compiled model's name.
    """


# %% formatting


@dataclass(frozen=True)
class XmlNumbers:
    """
    Numbers as one XML attribute value.
    """

    values: Sequence[float]
    """
    The numbers.
    """

    def text(self) -> str:
        """
        :return: The numbers separated by spaces.
        """
        return " ".join(str(float(value)) for value in self.values)


@dataclass(frozen=True)
class UrdfOrigin:
    """
    A URDF origin as a MuJoCo position and quaternion.
    """

    element: Optional[ElementTree.Element]
    """
    The URDF ``origin`` element, or None for the identity.
    """

    def attributes(self) -> Dict[str, str]:
        """
        :return: The ``pos`` and ``quat`` attributes; none for the identity.
        """
        if self.element is None:
            return {}
        angles = np.fromstring(self.element.get(UrdfTag.RPY, ZERO_VECTOR), sep=" ")
        return {
            MujocoAttribute.POSITION: self.element.get(UrdfTag.XYZ, ZERO_VECTOR),
            MujocoAttribute.QUATERNION: XmlNumbers(
                Rotation.from_euler("xyz", angles).as_quat(scalar_first=True)
            ).text(),
        }


@dataclass(frozen=True)
class PlacedPose:
    """
    A protocol pose as a MuJoCo position and quaternion.
    """

    pose: Pose
    """
    The pose, its quaternion last.
    """

    def attributes(self) -> Dict[str, str]:
        """
        :return: The ``pos`` and ``quat`` attributes.
        """
        pose = self.pose
        return {
            MujocoAttribute.POSITION: XmlNumbers((pose.x, pose.y, pose.z)).text(),
            MujocoAttribute.QUATERNION: XmlNumbers(
                (pose.qw, pose.qx, pose.qy, pose.qz)
            ).text(),
        }


# %% URDF description


@dataclass(frozen=True)
class UrdfDescription:
    """
    One URDF file, read for its links, joints and collision primitives.
    """

    path: Path
    """
    The URDF file.
    """

    settings: ContactSettings
    """
    The joint damping.
    """

    def add_to(self, parent: ElementTree.Element, pose: Optional[Pose]) -> None:
        """
        Add every root link of the URDF with its subtree below a MuJoCo element.

        :param parent: The MuJoCo element receiving the root links.
        :param pose: Where a loose object starts, put on a free joint; None for a model
            fixed to the world.
        :raises UnsupportedCollisionShape: For a collision that is no box, cylinder or
            sphere.
        """
        root = ElementTree.parse(self.path).getroot()
        links = {link.attrib[UrdfTag.NAME]: link for link in root.findall(UrdfTag.LINK)}
        joints = root.findall(UrdfTag.JOINT)
        children = {joint.find(UrdfTag.CHILD).attrib[UrdfTag.LINK] for joint in joints}
        for name in links.keys() - children:
            body = ElementTree.SubElement(
                parent,
                MujocoTag.BODY,
                name=name,
                **({} if pose is None else PlacedPose(pose).attributes()),
            )
            if pose is not None:
                ElementTree.SubElement(
                    body, MujocoTag.FREE_JOINT, name=f"{name}{FREE_JOINT_SUFFIX}"
                )
            self.fill(body, links, joints, name)

    def fill(
        self,
        body: ElementTree.Element,
        links: Dict[str, ElementTree.Element],
        joints: List[ElementTree.Element],
        name: str,
    ) -> None:
        """
        Give a MuJoCo body its link's inertia and collisions, and add its child links.

        :param body: The MuJoCo body of the link.
        :param links: Every link of the URDF by name.
        :param joints: Every joint of the URDF.
        :param name: The link's name.
        """
        link = links[name]
        self.add_inertia(body, link.find(UrdfTag.INERTIAL))
        for index, collision in enumerate(link.findall(UrdfTag.COLLISION)):
            ElementTree.SubElement(
                body,
                MujocoTag.GEOM,
                name=f"{name}{COLLISION_INFIX}{index}",
                **UrdfOrigin(collision.find(UrdfTag.ORIGIN)).attributes(),
                **self.shape(collision.find(UrdfTag.GEOMETRY)[0]),
            )
        for joint in joints:
            if joint.find(UrdfTag.PARENT).attrib[UrdfTag.LINK] != name:
                continue
            child_name = joint.find(UrdfTag.CHILD).attrib[UrdfTag.LINK]
            child = ElementTree.SubElement(
                body,
                MujocoTag.BODY,
                name=child_name,
                **UrdfOrigin(joint.find(UrdfTag.ORIGIN)).attributes(),
            )
            self.add_joint(child, joint)
            self.fill(child, links, joints, child_name)

    def add_joint(self, body: ElementTree.Element, joint: ElementTree.Element) -> None:
        """
        :param body: The MuJoCo body of the joint's child link.
        :param joint: A URDF joint; a fixed one adds nothing.
        """
        kind = joint.attrib[UrdfTag.TYPE]
        if kind == UrdfJointType.FIXED:
            return
        limit = joint.find(UrdfTag.LIMIT)
        ElementTree.SubElement(
            body,
            MujocoTag.JOINT,
            name=joint.attrib[UrdfTag.NAME],
            type=(
                MujocoTag.SLIDE if kind == UrdfJointType.PRISMATIC else MujocoTag.HINGE
            ),
            axis=joint.find(UrdfTag.AXIS).get(UrdfTag.XYZ, DEFAULT_AXIS),
            range=f"{limit.attrib[UrdfTag.LOWER]} {limit.attrib[UrdfTag.UPPER]}",
            damping=str(self.settings.joint_damping),
        )

    @staticmethod
    def add_inertia(
        body: ElementTree.Element, inertial: Optional[ElementTree.Element]
    ) -> None:
        """
        :param body: A MuJoCo body.
        :param inertial: The link's URDF ``inertial`` element; None adds nothing.
        """
        if inertial is None:
            return
        inertia = inertial.find(UrdfTag.INERTIA).attrib
        ElementTree.SubElement(
            body,
            MujocoTag.INERTIAL,
            pos=inertial.find(UrdfTag.ORIGIN).get(UrdfTag.XYZ, ZERO_VECTOR),
            mass=inertial.find(UrdfTag.MASS).attrib[UrdfTag.VALUE],
            fullinertia=" ".join(inertia[key] for key in INERTIA_ORDER),
        )

    def shape(self, primitive: ElementTree.Element) -> Dict[str, str]:
        """
        :param primitive: A URDF collision shape.
        :return: The MuJoCo geom's ``type`` and ``size``, sizes halved where MuJoCo
            takes half extents.
        :raises UnsupportedCollisionShape: For a shape that is no box, cylinder or
            sphere.
        """
        if primitive.tag == UrdfShape.BOX:
            size = np.fromstring(primitive.attrib[UrdfTag.SIZE], sep=" ") / 2
            return {
                MujocoAttribute.TYPE: UrdfShape.BOX,
                MujocoAttribute.SIZE: XmlNumbers(size).text(),
            }
        if primitive.tag == UrdfShape.CYLINDER:
            radius = float(primitive.attrib[UrdfTag.RADIUS])
            half_length = float(primitive.attrib[UrdfTag.LENGTH]) / 2
            return {
                MujocoAttribute.TYPE: UrdfShape.CYLINDER,
                MujocoAttribute.SIZE: XmlNumbers((radius, half_length)).text(),
            }
        if primitive.tag == UrdfShape.SPHERE:
            return {
                MujocoAttribute.TYPE: UrdfShape.SPHERE,
                MujocoAttribute.SIZE: primitive.attrib[UrdfTag.RADIUS],
            }
        raise UnsupportedCollisionShape(self.path, primitive.tag)


# %% contact world


@dataclass(frozen=True)
class CollisionModel:
    """
    Builds the MuJoCo model of a workshop bundle: its environment models fixed to the
    world, its loose objects on free joints at their spawn poses.
    """

    bundle: WorkshopBundle
    """
    The workshop bundle.
    """

    settings: ContactSettings = ContactSettings()
    """
    The solver and contact settings.
    """

    def xml(self) -> str:
        """
        :return: The model's MuJoCo XML.
        """
        root = ElementTree.Element(MujocoTag.ROOT, model=self.settings.model_name)
        ElementTree.SubElement(
            root,
            MujocoTag.COMPILER,
            angle=MujocoTag.RADIAN,
            inertiafromgeom=MujocoTag.FALSE,
        )
        ElementTree.SubElement(
            root,
            MujocoTag.OPTION,
            timestep=str(self.settings.timestep),
            integrator=MujocoTag.IMPLICIT_FAST,
            cone=MujocoTag.ELLIPTIC,
            iterations=str(self.settings.solver_iterations),
        )
        defaults = ElementTree.SubElement(root, MujocoTag.DEFAULT)
        ElementTree.SubElement(
            defaults,
            MujocoTag.GEOM,
            friction=XmlNumbers(self.settings.friction).text(),
            condim=str(self.settings.contact_dimension),
            solref=XmlNumbers(
                (self.settings.contact_time, self.settings.contact_damping_ratio)
            ).text(),
            solimp=XmlNumbers(self.settings.impedance).text(),
        )
        world = ElementTree.SubElement(root, MujocoTag.WORLD_BODY)
        for model in self.bundle.scene.models:
            UrdfDescription(self.bundle.file(model.urdf), self.settings).add_to(
                world, None
            )
        for item in self.bundle.movable_objects():
            UrdfDescription(self.bundle.file(item.urdf), self.settings).add_to(
                world, item.spawn
            )
        return ElementTree.tostring(root, encoding="unicode")

    def compile(self) -> mujoco.MjModel:
        """
        :return: The compiled model.
        """
        return mujoco.MjModel.from_xml_string(self.xml())
