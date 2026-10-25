"""
The expanded laboratory's instruments: every joint they declare becomes a simulated
joint with a force-limited position drive, which a person moves between its rest and
inspection positions.

The drive's demand moves at the joint's authored speed; where the joint ends up is what
the contacts let it reach.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from enum import StrEnum

import mujoco
import numpy as np
from typing_extensions import Dict, List, Set, Tuple

from cramera_laboratory.exceptions import InvalidLaboratoryModel, UnknownInstrument
from cramera_laboratory.physics.model import (
    MjcfAttribute,
    MjcfTag,
    MjcfValue,
    ModelPart,
    UrdfInertial,
    numbers,
)
from cramera_laboratory.urdf import UrdfAttribute, UrdfTag
from cramera_protocol.laboratory.layout import (
    Instrument,
    InstrumentCollection,
    InstrumentJoint,
    InstrumentJointKind,
)
from cramera_protocol.laboratory.physics import InstrumentPose

DRIVE_SUFFIX = "__drive"
"""
What a joint's drive adds to the joint's name.
"""

INSTRUMENT_SEPARATOR = "__"
"""
What separates an instrument's identifier from its own link names.
"""

ARMATURE = "0.0001"
"""
The rotor inertia added to each instrument joint, which keeps light parts stable.
"""


class InstrumentProblem(StrEnum):
    """
    Why authored instrument joints cannot be simulated.
    """

    LIMITS = "the stops of {joint} differ from its URDF"
    """
    The collection and the URDF disagree on a joint's stops.
    """

    EFFORT = "the effort of {joint} differs from its URDF"
    """
    The collection and the URDF disagree on a joint's effort.
    """

    MISSING = "the environment lacks the instrument joints {joints}"
    """
    Joints the collection declares are not in the environment.
    """

    TRAVEL = "the rest or inspection position of {joint} lies outside its stops"
    """
    A declared position lies beyond the joint's stops.
    """

    EXCLUSION = "the mating parts {first} and {second} belong to different instruments"
    """
    A contact exclusion joins parts of two instruments.
    """


# %% parameters


@dataclass(frozen=True)
class InstrumentDriveParameters:
    """
    The instruments' position drives and when a joint counts as arrived.
    """

    angular_stiffness: float = 40.0
    """
    A hinge drive's stiffness, in newton metres per radian.
    """

    angular_damping: float = 4.0
    """
    A hinge drive's damping, in newton metre seconds per radian.
    """

    linear_stiffness: float = 400.0
    """
    A slide drive's stiffness, in newtons per metre.
    """

    linear_damping: float = 20.0
    """
    A slide drive's damping, in newton seconds per metre.
    """

    angular_tolerance: float = 0.008
    """
    How close a hinge must come to count as arrived, in radians.
    """

    linear_tolerance: float = 0.0005
    """
    How close a slide must come to count as arrived, in metres.
    """

    settling_speed: float = 0.02
    """
    How fast an arrived joint may still move, per second.
    """


def drive_name(joint: str) -> str:
    """
    :param joint: An instrument joint.
    :return: The name of its drive.
    """
    return f"{joint}{DRIVE_SUFFIX}"


# %% model


@dataclass
class InstrumentModelPart(ModelPart):
    """
    Imports the instruments' declared joints, adds their drives, and leaves out the
    contacts between parts that touch by design.
    """

    collection: InstrumentCollection
    """
    The authored instruments.
    """

    parameters: InstrumentDriveParameters = field(
        default_factory=InstrumentDriveParameters
    )
    """
    The drives' gains.
    """

    joints: Dict[str, InstrumentJoint] = field(init=False)
    """
    The declared joints by name.
    """

    imported: Set[str] = field(init=False, default_factory=set)
    """
    The joints imported so far.
    """

    mounts: Dict[str, str] = field(init=False, default_factory=dict)
    """
    Each moving link's parent link.
    """

    def __post_init__(self) -> None:
        self.joints = {
            joint.name: joint
            for instrument in self.collection.instruments
            for joint in instrument.joints
        }
        for joint in self.joints.values():
            if joint.kind is InstrumentJointKind.CONTINUOUS:
                continue
            if not all(
                joint.lower <= value <= joint.upper
                for value in (joint.rest, joint.inspection)
            ):
                raise InvalidLaboratoryModel(
                    InstrumentProblem.TRAVEL.value.format(joint=joint.name)
                )

    def import_joint(
        self,
        body: ElementTree.Element,
        link: ElementTree.Element,
        joint: ElementTree.Element,
    ) -> bool:
        name = joint.get(UrdfAttribute.NAME)
        if name not in self.joints:
            return False
        declared = self.joints[name]
        UrdfInertial.of_link(link).add_to(body)
        attributes = {
            MjcfAttribute.NAME: name,
            MjcfAttribute.TYPE: (
                MjcfValue.SLIDE
                if declared.kind is InstrumentJointKind.PRISMATIC
                else MjcfValue.HINGE
            ),
            MjcfAttribute.AXIS: self.axis(joint),
            MjcfAttribute.ARMATURE: ARMATURE,
        }
        limit = joint.find(UrdfTag.LIMIT)
        if declared.kind is not InstrumentJointKind.CONTINUOUS:
            attributes[MjcfAttribute.LIMITED] = MjcfValue.TRUE
            attributes[MjcfAttribute.RANGE] = self.limits(joint)
            stops = (
                float(limit.get(UrdfAttribute.LOWER)),
                float(limit.get(UrdfAttribute.UPPER)),
            )
            if stops != (declared.lower, declared.upper):
                raise InvalidLaboratoryModel(
                    InstrumentProblem.LIMITS.value.format(joint=name)
                )
        if float(limit.get(UrdfAttribute.EFFORT)) != declared.effort:
            raise InvalidLaboratoryModel(
                InstrumentProblem.EFFORT.value.format(joint=name)
            )
        body.set(MjcfAttribute.GRAVITY_COMPENSATION, MjcfValue.ON)
        ElementTree.SubElement(body, MjcfTag.JOINT, attributes)
        self.imported.add(name)
        self.mounts[joint.find(UrdfTag.CHILD).get(UrdfAttribute.LINK)] = joint.find(
            UrdfTag.PARENT
        ).get(UrdfAttribute.LINK)
        return True

    def complete(self, root: ElementTree.Element) -> None:
        missing = self.joints.keys() - self.imported
        if missing:
            raise InvalidLaboratoryModel(
                InstrumentProblem.MISSING.value.format(joints=sorted(missing))
            )
        bodies = {
            body.get(MjcfAttribute.NAME): body for body in root.iter(MjcfTag.BODY)
        }
        pairs: Set[frozenset] = set()
        for child, parent in self.mounts.items():
            for moving in self.rigid_group(bodies[child]):
                for mounting in self.rigid_group(bodies[parent]):
                    pairs.add(frozenset((moving, mounting)))
        for exclusion in self.collection.contact_exclusions:
            if self.instrument_of(exclusion.first) != self.instrument_of(
                exclusion.second
            ):
                raise InvalidLaboratoryModel(
                    InstrumentProblem.EXCLUSION.value.format(
                        first=exclusion.first, second=exclusion.second
                    )
                )
            pairs.add(frozenset((exclusion.first, exclusion.second)))
        contacts = self.section(root, MjcfTag.CONTACT)
        for pair in sorted(pairs, key=sorted):
            if len(pair) != 2:
                continue
            first, second = sorted(pair)
            ElementTree.SubElement(
                contacts,
                MjcfTag.EXCLUDE,
                {MjcfAttribute.BODY_FIRST: first, MjcfAttribute.BODY_SECOND: second},
            )
        actuators = self.section(root, MjcfTag.ACTUATOR)
        for joint in self.joints.values():
            linear = joint.kind is InstrumentJointKind.PRISMATIC
            ElementTree.SubElement(
                actuators,
                MjcfTag.POSITION_ACTUATOR,
                {
                    MjcfAttribute.NAME: drive_name(joint.name),
                    MjcfAttribute.JOINT: joint.name,
                    MjcfAttribute.POSITION_GAIN: str(
                        self.parameters.linear_stiffness
                        if linear
                        else self.parameters.angular_stiffness
                    ),
                    MjcfAttribute.VELOCITY_GAIN: str(
                        self.parameters.linear_damping
                        if linear
                        else self.parameters.angular_damping
                    ),
                    MjcfAttribute.FORCE_LIMITED: MjcfValue.TRUE,
                    MjcfAttribute.FORCE_RANGE: numbers([-joint.effort, joint.effort]),
                },
            )

    @staticmethod
    def instrument_of(link: str) -> str:
        """
        :param link: A link of an instrument.
        :return: The instrument's identifier, the link name's prefix.
        """
        return link.split(INSTRUMENT_SEPARATOR)[0]

    @classmethod
    def rigid_group(cls, body: ElementTree.Element) -> Tuple[str, ...]:
        """
        :param body: An MJCF body.
        :return: The body and every body fixed to it below.
        """
        names = [body.get(MjcfAttribute.NAME)]
        for child in body.findall(MjcfTag.BODY):
            if (
                child.find(MjcfTag.JOINT) is None
                and child.find(MjcfTag.FREE_JOINT) is None
            ):
                names.extend(cls.rigid_group(child))
        return tuple(names)


# %% drives


@dataclass(frozen=True)
class JointIndices:
    """
    Where one instrument joint lives in MuJoCo's arrays.
    """

    position: int
    """
    The joint's position index.
    """

    velocity: int
    """
    The joint's velocity index.
    """

    drive: int
    """
    The joint drive's index.
    """


@dataclass
class InstrumentDrives:
    """
    Moves the instruments' joints through their drives.
    """

    model: mujoco.MjModel
    """
    The compiled model.
    """

    data: mujoco.MjData
    """
    The simulation state.
    """

    collection: InstrumentCollection
    """
    The authored instruments.
    """

    parameters: InstrumentDriveParameters = field(
        default_factory=InstrumentDriveParameters
    )
    """
    When a joint counts as arrived.
    """

    joints: Dict[str, InstrumentJoint] = field(init=False)
    """
    The declared joints by name.
    """

    indices: Dict[str, JointIndices] = field(init=False)
    """
    Where each joint lives in MuJoCo's arrays.
    """

    targets: Dict[str, float] = field(init=False, default_factory=dict)
    """
    Where each joint is asked to go.
    """

    demands: Dict[str, float] = field(init=False, default_factory=dict)
    """
    Where each drive is commanded, moving towards the target at the joint's speed.
    """

    def __post_init__(self) -> None:
        self.joints = {
            joint.name: joint
            for instrument in self.collection.instruments
            for joint in instrument.joints
        }
        self.indices = {
            name: JointIndices(
                position=int(self.model.jnt_qposadr[self.model.joint(name).id]),
                velocity=int(self.model.jnt_dofadr[self.model.joint(name).id]),
                drive=self.model.actuator(drive_name(name)).id,
            )
            for name in self.joints
        }

    def instrument(self, identifier: str) -> Instrument:
        """
        :param identifier: An instrument's identifier.
        :return: The instrument.
        :raises UnknownInstrument: When the collection has no such instrument.
        """
        for instrument in self.collection.instruments:
            if instrument.identifier == identifier:
                return instrument
        raise UnknownInstrument(identifier)

    def reset(self) -> None:
        """
        Put every joint at rest.
        """
        for name, joint in self.joints.items():
            indices = self.indices[name]
            self.data.qpos[indices.position] = joint.rest
            self.data.qvel[indices.velocity] = 0.0
            self.data.ctrl[indices.drive] = joint.rest
            self.targets[name] = self.demands[name] = joint.rest

    def move(self, identifier: str, pose: InstrumentPose) -> None:
        """
        :param identifier: An instrument.
        :param pose: Where to move every joint of it.
        :raises UnknownInstrument: When the collection has no such instrument.
        """
        for joint in self.instrument(identifier).joints:
            self.targets[joint.name] = (
                joint.inspection if pose is InstrumentPose.INSPECTION else joint.rest
            )

    def advance(self, elapsed: float) -> None:
        """
        :param elapsed: The simulated time since the previous call, in seconds.
        """
        for name, joint in self.joints.items():
            step = joint.velocity * elapsed
            self.demands[name] += float(
                np.clip(self.targets[name] - self.demands[name], -step, step)
            )
            self.data.ctrl[self.indices[name].drive] = self.demands[name]

    def arrived(self, identifier: str) -> bool:
        """
        :param identifier: An instrument.
        :return: Whether every joint of it settled at its target.
        """
        for joint in self.instrument(identifier).joints:
            indices = self.indices[joint.name]
            tolerance = (
                self.parameters.linear_tolerance
                if joint.kind is InstrumentJointKind.PRISMATIC
                else self.parameters.angular_tolerance
            )
            position = float(self.data.qpos[indices.position])
            speed = abs(float(self.data.qvel[indices.velocity]))
            if (
                abs(position - self.targets[joint.name]) > tolerance
                or speed > self.parameters.settling_speed
            ):
                return False
        return True

    def joint_positions(self) -> Dict[str, float]:
        """
        :return: Every instrument joint's measured position, by name.
        """
        return {
            name: float(self.data.qpos[indices.position])
            for name, indices in self.indices.items()
        }

    def poses(self) -> List[str]:
        """
        :return: The identifiers of the instruments with joints.
        """
        return [
            instrument.identifier
            for instrument in self.collection.instruments
            if instrument.joints
        ]
