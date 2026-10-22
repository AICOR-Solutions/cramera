"""
The laboratory's collision model in MuJoCo's MJCF, built from the authored URDFs.

Only collision geometry and inertia are imported; the browser draws the authored meshes.
The fixed environment becomes static bodies, every free object a body with its own free
joint, and the joints the instruments declare become simulated joints with force-limited
drives.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from typing_extensions import Dict, List, Optional, Sequence

from cramera_laboratory.cabinet import CabinetStructure
from cramera_laboratory.exceptions import InvalidLaboratoryModel
from cramera_laboratory.urdf import UrdfAttribute, UrdfJointType, UrdfTag
from cramera_protocol.bundle.scene import ObjectDescription

# %% names


class MjcfTag(StrEnum):
    """
    The MJCF elements the model writes.
    """

    MUJOCO = "mujoco"
    """
    The ``mujoco`` element.
    """

    COMPILER = "compiler"
    """
    The ``compiler`` element.
    """

    OPTION = "option"
    """
    The ``option`` element.
    """

    FLAG = "flag"
    """
    The ``flag`` element.
    """

    DEFAULT = "default"
    """
    The ``default`` element.
    """

    ASSET = "asset"
    """
    The ``asset`` element.
    """

    MESH = "mesh"
    """
    The ``mesh`` element.
    """

    WORLD = "worldbody"
    """
    The ``worldbody`` element.
    """

    BODY = "body"
    """
    The ``body`` element.
    """

    GEOMETRY = "geom"
    """
    The ``geom`` element.
    """

    SITE = "site"
    """
    The ``site`` element.
    """

    JOINT = "joint"
    """
    The ``joint`` element.
    """

    FREE_JOINT = "freejoint"
    """
    The ``freejoint`` element.
    """

    INERTIAL = "inertial"
    """
    The ``inertial`` element.
    """

    ACTUATOR = "actuator"
    """
    The ``actuator`` element.
    """

    POSITION_ACTUATOR = "position"
    """
    The ``position`` element.
    """

    VELOCITY_ACTUATOR = "velocity"
    """
    The ``velocity`` element.
    """

    EQUALITY = "equality"
    """
    The ``equality`` element.
    """

    WELD = "weld"
    """
    The ``weld`` element.
    """

    CONTACT = "contact"
    """
    The ``contact`` element.
    """

    EXCLUDE = "exclude"
    """
    The ``exclude`` element.
    """


class MjcfAttribute(StrEnum):
    """
    The MJCF attributes the model writes.
    """

    NAME = "name"
    """
    The ``name`` attribute.
    """

    MODEL = "model"
    """
    The ``model`` attribute.
    """

    MESH = "mesh"
    """
    The ``mesh`` attribute.
    """

    ANGLE = "angle"
    """
    The ``angle`` attribute.
    """

    INERTIA_FROM_GEOMETRY = "inertiafromgeom"
    """
    The ``inertiafromgeom`` attribute.
    """

    TIMESTEP = "timestep"
    """
    The ``timestep`` attribute.
    """

    INTEGRATOR = "integrator"
    """
    The ``integrator`` attribute.
    """

    CONE = "cone"
    """
    The ``cone`` attribute.
    """

    ITERATIONS = "iterations"
    """
    The ``iterations`` attribute.
    """

    ENERGY = "energy"
    """
    The ``energy`` attribute.
    """

    FRICTION = "friction"
    """
    The ``friction`` attribute.
    """

    CONTACT_DIMENSION = "condim"
    """
    The ``condim`` attribute.
    """

    SOLVER_REFERENCE = "solref"
    """
    The ``solref`` attribute.
    """

    SOLVER_IMPEDANCE = "solimp"
    """
    The ``solimp`` attribute.
    """

    PRIORITY = "priority"
    """
    The ``priority`` attribute.
    """

    POSITION = "pos"
    """
    The ``pos`` attribute.
    """

    QUATERNION = "quat"
    """
    The ``quat`` attribute.
    """

    TYPE = "type"
    """
    The ``type`` attribute.
    """

    SIZE = "size"
    """
    The ``size`` attribute.
    """

    FILE = "file"
    """
    The ``file`` attribute.
    """

    SCALE = "scale"
    """
    The ``scale`` attribute.
    """

    MASS = "mass"
    """
    The ``mass`` attribute.
    """

    FULL_INERTIA = "fullinertia"
    """
    The ``fullinertia`` attribute.
    """

    AXIS = "axis"
    """
    The ``axis`` attribute.
    """

    RANGE = "range"
    """
    The ``range`` attribute.
    """

    LIMITED = "limited"
    """
    The ``limited`` attribute.
    """

    DAMPING = "damping"
    """
    The ``damping`` attribute.
    """

    FRICTION_LOSS = "frictionloss"
    """
    The ``frictionloss`` attribute.
    """

    ARMATURE = "armature"
    """
    The ``armature`` attribute.
    """

    GRAVITY_COMPENSATION = "gravcomp"
    """
    The ``gravcomp`` attribute.
    """

    RGBA = "rgba"
    """
    The ``rgba`` attribute.
    """

    JOINT = "joint"
    """
    The ``joint`` attribute.
    """

    POSITION_GAIN = "kp"
    """
    The ``kp`` attribute.
    """

    VELOCITY_GAIN = "kv"
    """
    The ``kv`` attribute.
    """

    FORCE_LIMITED = "forcelimited"
    """
    The ``forcelimited`` attribute.
    """

    FORCE_RANGE = "forcerange"
    """
    The ``forcerange`` attribute.
    """

    SITE_FIRST = "site1"
    """
    The ``site1`` attribute.
    """

    SITE_SECOND = "site2"
    """
    The ``site2`` attribute.
    """

    ACTIVE = "active"
    """
    The ``active`` attribute.
    """

    TORQUE_SCALE = "torquescale"
    """
    The ``torquescale`` attribute.
    """

    BODY_FIRST = "body1"
    """
    The ``body1`` attribute.
    """

    BODY_SECOND = "body2"
    """
    The ``body2`` attribute.
    """


class MjcfValue(StrEnum):
    """
    The fixed MJCF attribute values the model writes.
    """

    RADIAN = "radian"
    """
    The value ``radian``.
    """

    FALSE = "false"
    """
    The value ``false``.
    """

    TRUE = "true"
    """
    The value ``true``.
    """

    ENABLE = "enable"
    """
    The value ``enable``.
    """

    IMPLICIT_FAST = "implicitfast"
    """
    The value ``implicitfast``.
    """

    ELLIPTIC = "elliptic"
    """
    The value ``elliptic``.
    """

    BOX = "box"
    """
    The value ``box``.
    """

    CYLINDER = "cylinder"
    """
    The value ``cylinder``.
    """

    SPHERE = "sphere"
    """
    The value ``sphere``.
    """

    MESH = "mesh"
    """
    The value ``mesh``.
    """

    HINGE = "hinge"
    """
    The value ``hinge``.
    """

    SLIDE = "slide"
    """
    The value ``slide``.
    """

    PLANE = "plane"
    """
    The value ``plane``.
    """

    ON = "1"
    """
    The value ``1``.
    """


INERTIA_COMPONENTS = ("ixx", "iyy", "izz", "ixy", "ixz", "iyz")
"""
The URDF inertia attributes in the order MJCF's ``fullinertia`` takes them.
"""

ZERO_TRIPLE = "0 0 0"
"""
A zero position or rotation as URDF writes it.
"""

UNIT_SCALE = "1 1 1"
"""
A mesh scale that keeps the mesh's size.
"""

CRITICAL_DAMPING = 1
"""
The damping ratio of every contact's spring: critically damped.
"""

FRAME_SITE_SIZE = 0.001
"""
The radius of the invisible sites that mark frames, in metres.
"""

INVISIBLE = "0 0 0 0"
"""
The colour of a site nobody sees.
"""

FLOOR_HALF_SIZE = "3 3 0.1"
"""
The half extent of the floor plane of a laboratory without a room, in metres.
"""

MODEL_NAME = "laboratory"
"""
The name of the compiled model.
"""

FLOOR = "floor"
"""
The name of that floor plane.
"""

NAME_SEPARATOR = "_"
"""
What joins a link's name and its collision's name into a geometry's name.
"""

# %% numbers as MJCF text


def numbers(values: Sequence[float]) -> str:
    """
    :param values: Numbers.
    :return: The numbers as MJCF writes them, separated by spaces.
    """
    return " ".join(str(float(value)) for value in values)


def number_list(text: Optional[str], default: str = ZERO_TRIPLE) -> np.ndarray:
    """
    :param text: Numbers separated by spaces, as URDF writes them, or None.
    :return: The numbers; the default's numbers when the text is None.
    """
    return np.array([float(value) for value in (text or default).split()])


# %% parameters


@dataclass(frozen=True)
class ContactParameters:
    """
    How MuJoCo integrates the laboratory and resolves its contacts.
    """

    timestep: float = 0.001
    """
    The integration step, in seconds.
    """

    iterations: int = 80
    """
    The constraint solver's iteration limit.
    """

    friction: str = "0.4 0.005 0.0001"
    """
    Sliding, torsional and rolling friction of every surface.
    """

    contact_dimension: int = 4
    """
    The friction dimensions of a contact: sliding and torsional friction.
    """

    contact_time_constant: float = 0.004
    """
    How fast contacts push bodies apart, in seconds.
    """

    contact_impedance: str = "0.95 0.99 0.0001"
    """
    How stiff contacts are at small and large penetration.
    """

    scale_time_constant: float = 0.008
    """
    The softer contact time constant of the scale's pan and holder, in seconds.
    """

    scale_priority: int = 1
    """
    The priority that lets the scale's contact settings win over a vessel's.
    """


# %% URDF reading


@dataclass(frozen=True)
class UrdfOrigin:
    """
    A URDF ``origin`` element as an MJCF position and quaternion.
    """

    element: Optional[ElementTree.Element]
    """
    The origin element, or None for the identity.
    """

    def attributes(self) -> Dict[str, str]:
        """
        :return: MJCF ``pos`` and ``quat`` attributes; none for the identity.
        """
        if self.element is None:
            return {}
        angles = number_list(self.element.get(UrdfAttribute.RPY))
        quaternion = Rotation.from_euler("xyz", angles).as_quat(scalar_first=True)
        return {
            MjcfAttribute.POSITION: numbers(
                number_list(self.element.get(UrdfAttribute.XYZ))
            ),
            MjcfAttribute.QUATERNION: numbers(quaternion),
        }

    def transform(self) -> np.ndarray:
        """
        :return: The origin as a 4×4 homogeneous transform.
        """
        transform = np.eye(4)
        if self.element is None:
            return transform
        transform[:3, 3] = number_list(self.element.get(UrdfAttribute.XYZ))
        transform[:3, :3] = Rotation.from_euler(
            "xyz", number_list(self.element.get(UrdfAttribute.RPY))
        ).as_matrix()
        return transform


@dataclass(frozen=True)
class UrdfInertial:
    """
    A link's URDF inertial element.
    """

    element: ElementTree.Element
    """
    The inertial element.
    """

    def add_to(self, body: ElementTree.Element) -> None:
        """
        Give an MJCF body the link's mass and inertia, rotated into the link's axes.

        :param body: The body.
        """
        values = self.element.find(UrdfTag.INERTIA).attrib
        xx, yy, zz, xy, xz, yz = (float(values[name]) for name in INERTIA_COMPONENTS)
        tensor = np.array([[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]])
        origin = self.element.find(UrdfTag.ORIGIN)
        rotation = Rotation.from_euler(
            "xyz",
            number_list(None if origin is None else origin.get(UrdfAttribute.RPY)),
        ).as_matrix()
        tensor = rotation @ tensor @ rotation.T
        ElementTree.SubElement(
            body,
            MjcfTag.INERTIAL,
            {
                MjcfAttribute.MASS: self.element.find(UrdfTag.MASS).get(
                    UrdfAttribute.VALUE
                ),
                MjcfAttribute.POSITION: numbers(
                    number_list(
                        None if origin is None else origin.get(UrdfAttribute.XYZ)
                    )
                ),
                MjcfAttribute.FULL_INERTIA: numbers(
                    [
                        tensor[0, 0],
                        tensor[1, 1],
                        tensor[2, 2],
                        tensor[0, 1],
                        tensor[0, 2],
                        tensor[1, 2],
                    ]
                ),
            },
        )

    @classmethod
    def of_link(cls, link: ElementTree.Element) -> UrdfInertial:
        """
        :param link: A moving link.
        :return: Its inertial element.
        :raises InvalidLaboratoryModel: When the link has none.
        """
        element = link.find(UrdfTag.INERTIAL)
        if element is None:
            raise InvalidLaboratoryModel(
                f"the moving link {link.get(UrdfAttribute.NAME)} has no inertia"
            )
        return cls(element)


# %% joints the instruments import


class ModelPart(ABC):
    """
    One part of the laboratory with joints or constraints of its own: it turns its URDF
    joints into simulated ones and adds its drives once the model is complete.
    """

    @abstractmethod
    def import_joint(
        self,
        body: ElementTree.Element,
        link: ElementTree.Element,
        joint: ElementTree.Element,
    ) -> bool:
        """
        :param body: The MJCF body of the joint's child link.
        :param link: The child link's URDF element.
        :param joint: The URDF joint.
        :return: Whether the part owns the joint and imported it.
        """

    @abstractmethod
    def complete(self, root: ElementTree.Element) -> None:
        """
        Add the part's drives and constraints.

        :param root: The model's root element.
        """

    @staticmethod
    def section(root: ElementTree.Element, tag: MjcfTag) -> ElementTree.Element:
        """
        :param root: The model's root element.
        :param tag: A top-level section, such as the actuators.
        :return: The section, created when the model has none yet.
        """
        existing = root.find(tag)
        return existing if existing is not None else ElementTree.SubElement(root, tag)

    @staticmethod
    def limits(joint: ElementTree.Element) -> str:
        """
        :param joint: A URDF joint with stops.
        :return: Its range as MJCF writes it.
        """
        limit = joint.find(UrdfTag.LIMIT)
        return numbers(
            [
                float(limit.get(UrdfAttribute.LOWER)),
                float(limit.get(UrdfAttribute.UPPER)),
            ]
        )

    @staticmethod
    def axis(joint: ElementTree.Element) -> str:
        """
        :param joint: A URDF joint.
        :return: Its axis as MJCF writes it.
        """
        return joint.find(UrdfTag.AXIS).get(UrdfAttribute.XYZ)


# %% builder


@dataclass
class CollisionModel:
    """
    Builds the laboratory's MJCF from its environment URDF, its free objects and the
    model parts of its instruments.
    """

    directory: Path
    """
    The laboratory bundle.
    """

    environment: List[Path]
    """
    The environment URDFs, relative to the bundle.
    """

    objects: List[ObjectDescription]
    """
    The free objects, each with its own URDF.
    """

    parts: List[ModelPart]
    """
    The parts with joints of their own.
    """

    parameters: ContactParameters = field(default_factory=ContactParameters)
    """
    How MuJoCo integrates the model.
    """

    scale_geometries: Sequence[str] = ()
    """
    The prefixes of the geometries of the scale's pan and holder, which get the softer
    scale contacts.
    """

    floating_links: Sequence[str] = ()
    """
    The links that move freely, such as the rack; they are lifted to the world with
    their own free joint.
    """

    has_room: bool = True
    """
    Whether the environment has a floor of its own; without one a plane is added.
    """

    root: ElementTree.Element = field(init=False)
    """
    The MJCF document.
    """

    assets: ElementTree.Element = field(init=False)
    """
    The mesh declarations.
    """

    world: ElementTree.Element = field(init=False)
    """
    The world body.
    """

    def build(self) -> mujoco.MjModel:
        """
        :return: The compiled model.
        """
        self.root = ElementTree.Element(
            MjcfTag.MUJOCO, {MjcfAttribute.MODEL: MODEL_NAME}
        )
        ElementTree.SubElement(
            self.root,
            MjcfTag.COMPILER,
            {
                MjcfAttribute.ANGLE: MjcfValue.RADIAN,
                MjcfAttribute.INERTIA_FROM_GEOMETRY: MjcfValue.FALSE,
            },
        )
        option = ElementTree.SubElement(
            self.root,
            MjcfTag.OPTION,
            {
                MjcfAttribute.TIMESTEP: str(self.parameters.timestep),
                MjcfAttribute.INTEGRATOR: MjcfValue.IMPLICIT_FAST,
                MjcfAttribute.CONE: MjcfValue.ELLIPTIC,
                MjcfAttribute.ITERATIONS: str(self.parameters.iterations),
            },
        )
        ElementTree.SubElement(
            option, MjcfTag.FLAG, {MjcfAttribute.ENERGY: MjcfValue.ENABLE}
        )
        defaults = ElementTree.SubElement(self.root, MjcfTag.DEFAULT)
        ElementTree.SubElement(
            defaults,
            MjcfTag.GEOMETRY,
            {
                MjcfAttribute.FRICTION: self.parameters.friction,
                MjcfAttribute.CONTACT_DIMENSION: str(self.parameters.contact_dimension),
                MjcfAttribute.SOLVER_REFERENCE: f"{self.parameters.contact_time_constant} {CRITICAL_DAMPING}",
                MjcfAttribute.SOLVER_IMPEDANCE: self.parameters.contact_impedance,
            },
        )
        self.assets = ElementTree.SubElement(self.root, MjcfTag.ASSET)
        self.world = ElementTree.SubElement(self.root, MjcfTag.WORLD)
        if not self.has_room:
            ElementTree.SubElement(
                self.world,
                MjcfTag.GEOMETRY,
                {
                    MjcfAttribute.NAME: FLOOR,
                    MjcfAttribute.TYPE: MjcfValue.PLANE,
                    MjcfAttribute.SIZE: FLOOR_HALF_SIZE,
                },
            )
        for description in self.environment:
            self.add_environment(self.directory / description)
        self.add_cabinet()
        for description in self.objects:
            self.add_object(description)
        for part in self.parts:
            part.complete(self.root)
        return mujoco.MjModel.from_xml_string(
            ElementTree.tostring(self.root, encoding="unicode")
        )

    def add_cabinet(self) -> None:
        """
        Add the closed cabinet panels the environment's URDF leaves without collision.
        """
        cabinet = CabinetStructure()
        body = ElementTree.SubElement(
            self.world, MjcfTag.BODY, {MjcfAttribute.NAME: cabinet.name}
        )
        for index, panel in enumerate(cabinet.panels()):
            ElementTree.SubElement(
                body,
                MjcfTag.GEOMETRY,
                {
                    MjcfAttribute.NAME: f"{cabinet.name}{NAME_SEPARATOR}{index}",
                    MjcfAttribute.TYPE: MjcfValue.BOX,
                    MjcfAttribute.POSITION: numbers(panel.center),
                    MjcfAttribute.SIZE: numbers(np.array(panel.size) / 2),
                },
            )

    def add_environment(self, description: Path) -> None:
        """
        :param description: An environment URDF.
        """
        robot = ElementTree.parse(description).getroot()
        links = {
            link.get(UrdfAttribute.NAME): link for link in robot.findall(UrdfTag.LINK)
        }
        joints = {
            joint.find(UrdfTag.CHILD).get(UrdfAttribute.LINK): joint
            for joint in robot.findall(UrdfTag.JOINT)
        }
        children: Dict[str, List[str]] = {name: [] for name in links}
        for child, joint in joints.items():
            children[joint.find(UrdfTag.PARENT).get(UrdfAttribute.LINK)].append(child)
        for name in links.keys() - joints.keys():
            EnvironmentTree(self, description, links, joints, children).add(
                name, self.world
            )

    def add_object(self, description: ObjectDescription) -> None:
        """
        Add a free object from its URDF, at its spawn pose, with a free joint.

        :param description: The object's description.
        """
        urdf = self.directory / description.urdf
        [link] = ElementTree.parse(urdf).getroot().findall(UrdfTag.LINK)
        spawn = description.spawn
        body = ElementTree.SubElement(
            self.world,
            MjcfTag.BODY,
            {
                MjcfAttribute.NAME: description.key,
                MjcfAttribute.POSITION: numbers([spawn.x, spawn.y, spawn.z]),
                MjcfAttribute.QUATERNION: numbers(
                    [spawn.qw, spawn.qx, spawn.qy, spawn.qz]
                ),
            },
        )
        ElementTree.SubElement(
            body, MjcfTag.FREE_JOINT, {MjcfAttribute.NAME: description.key}
        )
        UrdfInertial.of_link(link).add_to(body)
        self.add_collisions(body, link, urdf)

    def add_collisions(
        self, body: ElementTree.Element, link: ElementTree.Element, description: Path
    ) -> None:
        """
        Give a body the link's collision shapes.

        :param body: The MJCF body.
        :param link: The URDF link.
        :param description: The URDF, against which mesh files resolve.
        :raises InvalidLaboratoryModel: For a collision shape MJCF cannot take.
        """
        for collision in link.findall(UrdfTag.COLLISION):
            [shape] = list(collision.find(UrdfTag.GEOMETRY))
            name = NAME_SEPARATOR.join(
                (link.get(UrdfAttribute.NAME), collision.get(UrdfAttribute.NAME))
            )
            attributes = UrdfOrigin(collision.find(UrdfTag.ORIGIN)).attributes()
            if any(name.startswith(prefix) for prefix in self.scale_geometries):
                attributes[MjcfAttribute.PRIORITY] = str(self.parameters.scale_priority)
                attributes[MjcfAttribute.SOLVER_REFERENCE] = (
                    f"{self.parameters.scale_time_constant} {CRITICAL_DAMPING}"
                )
            attributes.update(self.shape(name, shape, description))
            attributes[MjcfAttribute.NAME] = name
            ElementTree.SubElement(body, MjcfTag.GEOMETRY, attributes)

    def shape(
        self, name: str, shape: ElementTree.Element, description: Path
    ) -> Dict[str, str]:
        """
        :param name: The geometry's name.
        :param shape: A URDF shape element.
        :param description: The URDF, against which mesh files resolve.
        :return: The MJCF attributes of the shape.
        :raises InvalidLaboratoryModel: For a shape MJCF cannot take.
        """
        if shape.tag == UrdfTag.BOX:
            return {
                MjcfAttribute.TYPE: MjcfValue.BOX,
                MjcfAttribute.SIZE: numbers(
                    number_list(shape.get(UrdfAttribute.SIZE)) / 2
                ),
            }
        if shape.tag == UrdfTag.CYLINDER:
            return {
                MjcfAttribute.TYPE: MjcfValue.CYLINDER,
                MjcfAttribute.SIZE: numbers(
                    [
                        float(shape.get(UrdfAttribute.RADIUS)),
                        float(shape.get(UrdfAttribute.LENGTH)) / 2,
                    ]
                ),
            }
        if shape.tag == UrdfTag.SPHERE:
            return {
                MjcfAttribute.TYPE: MjcfValue.SPHERE,
                MjcfAttribute.SIZE: shape.get(UrdfAttribute.RADIUS),
            }
        if shape.tag == UrdfTag.MESH:
            ElementTree.SubElement(
                self.assets,
                MjcfTag.MESH,
                {
                    MjcfAttribute.NAME: name,
                    MjcfAttribute.FILE: str(
                        (
                            description.parent / shape.get(UrdfAttribute.FILENAME)
                        ).resolve()
                    ),
                    MjcfAttribute.SCALE: shape.get(UrdfAttribute.SCALE, UNIT_SCALE),
                },
            )
            return {MjcfAttribute.TYPE: MjcfValue.MESH, MjcfAttribute.MESH: name}
        raise InvalidLaboratoryModel(f"the collision shape {shape.tag} of {name}")


@dataclass
class EnvironmentTree:
    """
    Adds one environment URDF's link tree to the model, link by link.
    """

    model: CollisionModel
    """
    The model being built.
    """

    description: Path
    """
    The URDF.
    """

    links: Dict[str, ElementTree.Element]
    """
    The URDF's links by name.
    """

    joints: Dict[str, ElementTree.Element]
    """
    The URDF's joints by their child link.
    """

    children: Dict[str, List[str]]
    """
    Each link's child links.
    """

    def add(self, name: str, parent: ElementTree.Element) -> None:
        """
        Add a link and everything below it.

        :param name: The link.
        :param parent: The MJCF body it hangs from.
        """
        joint = self.joints.get(name)
        attributes = UrdfOrigin(
            None if joint is None else joint.find(UrdfTag.ORIGIN)
        ).attributes()
        if name in self.model.floating_links:
            parent = self.model.world
            attributes = self.world_attributes(name)
        if self.is_frame(name, joint):
            ElementTree.SubElement(
                parent,
                MjcfTag.SITE,
                {
                    MjcfAttribute.NAME: name,
                    MjcfAttribute.SIZE: str(FRAME_SITE_SIZE),
                    MjcfAttribute.RGBA: INVISIBLE,
                    **attributes,
                },
            )
            return
        body = ElementTree.SubElement(
            parent, MjcfTag.BODY, {MjcfAttribute.NAME: name, **attributes}
        )
        link = self.links[name]
        self.model.add_collisions(body, link, self.description)
        if joint is not None and joint.get(UrdfAttribute.TYPE) != UrdfJointType.FIXED:
            if not any(
                part.import_joint(body, link, joint) for part in self.model.parts
            ):
                raise InvalidLaboratoryModel(
                    f"no part of the laboratory simulates the joint "
                    f"{joint.get(UrdfAttribute.NAME)}"
                )
        for child in self.children[name]:
            self.add(child, body)

    def is_frame(self, name: str, joint: Optional[ElementTree.Element]) -> bool:
        """
        :param name: A link.
        :param joint: Its joint, or None for a root.
        :return: Whether the link only marks a frame: fixed, without shapes or children.
        """
        return (
            joint is not None
            and joint.get(UrdfAttribute.TYPE) == UrdfJointType.FIXED
            and len(self.links[name]) == 0
            and not self.children[name]
        )

    def world_attributes(self, name: str) -> Dict[str, str]:
        """
        :param name: A link.
        :return: Its pose in the world, composed through its fixed ancestors.
        """
        transform = np.eye(4)
        while name in self.joints:
            joint = self.joints[name]
            transform = UrdfOrigin(joint.find(UrdfTag.ORIGIN)).transform() @ transform
            name = joint.find(UrdfTag.PARENT).get(UrdfAttribute.LINK)
        return {
            MjcfAttribute.POSITION: numbers(transform[:3, 3]),
            MjcfAttribute.QUATERNION: numbers(
                Rotation.from_matrix(transform[:3, :3]).as_quat(scalar_first=True)
            ),
        }
