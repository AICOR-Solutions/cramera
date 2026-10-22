"""
The sample refrigerator: a glass door on a force-limited hinge drive, storage positions
whose occupants are read from contact support, and a reduced model of the cabinet's
temperature.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from enum import StrEnum

import mujoco
import numpy as np
from typing_extensions import Dict, Optional, Sequence

from cramera_laboratory.exceptions import OperationRefused, Refusal
from cramera_laboratory.physics.contacts import ContactReader
from cramera_laboratory.physics.model import (
    MjcfAttribute,
    MjcfTag,
    MjcfValue,
    ModelPart,
    UrdfInertial,
    numbers,
)
from cramera_laboratory.urdf import UrdfAttribute
from cramera_protocol.laboratory.layout import RefrigeratorLayout
from cramera_protocol.laboratory.physics import (
    OpeningAction,
    RefrigeratorState,
    StoragePosition,
    TemperatureSource,
)

TEMPERATURE_DIGITS = 2
"""
The decimal places of a reported temperature.
"""


class RefrigeratorName(StrEnum):
    """
    The names the refrigerator's drive takes in the model.
    """

    DOOR_DRIVE = "laboratory_refrigerator_door_motor"
    """
    The door's position drive.
    """


# %% parameters


@dataclass(frozen=True)
class RefrigeratorParameters:
    """
    The door's drive, the storage tolerances and the temperature model.
    """

    maximum_torque: float = 2.0
    """
    The door drive's largest torque, in newton metres.
    """

    stiffness: float = 15.0
    """
    The door drive's stiffness, in newton metres per radian.
    """

    damping: float = 4.0
    """
    The door drive's damping, in newton metre seconds per radian.
    """

    hinge_damping: float = 0.1
    """
    The hinge's own friction, in newton metre seconds per radian.
    """

    angular_speed: float = 0.65
    """
    How fast the door's commanded angle may change, in radians per second.
    """

    angle_tolerance: float = 0.05
    """
    How close to a stop the door counts as open or closed, in radians.
    """

    position_tolerance: float = 0.008
    """
    How far a stored vessel may stand from its position, in metres.
    """

    upright_tolerance: float = 0.15
    """
    How far a stored vessel may lean, in radians.
    """

    support_share: float = 0.2
    """
    The share of a vessel's weight the cabinet must carry for it to count as stored.
    """

    ambient_temperature: float = 22.0
    """
    The laboratory's air temperature, in degrees Celsius.
    """

    cooling_time: float = 45.0
    """
    The closed cabinet's cooling time constant, in simulated seconds.
    """

    warming_time: float = 20.0
    """
    The open cabinet's warming time constant, in simulated seconds.
    """


# %% model


@dataclass
class RefrigeratorModelPart(ModelPart):
    """
    Imports the door's hinge and adds its force-limited drive.
    """

    layout: RefrigeratorLayout
    """
    The authored refrigerator.
    """

    parameters: RefrigeratorParameters = field(default_factory=RefrigeratorParameters)
    """
    The drive's limits.
    """

    def import_joint(
        self,
        body: ElementTree.Element,
        link: ElementTree.Element,
        joint: ElementTree.Element,
    ) -> bool:
        if joint.get(UrdfAttribute.NAME) != self.layout.door_joint:
            return False
        UrdfInertial.of_link(link).add_to(body)
        ElementTree.SubElement(
            body,
            MjcfTag.JOINT,
            {
                MjcfAttribute.NAME: self.layout.door_joint,
                MjcfAttribute.TYPE: MjcfValue.HINGE,
                MjcfAttribute.AXIS: self.axis(joint),
                MjcfAttribute.LIMITED: MjcfValue.TRUE,
                MjcfAttribute.RANGE: self.limits(joint),
                MjcfAttribute.DAMPING: str(self.parameters.hinge_damping),
            },
        )
        return True

    def complete(self, root: ElementTree.Element) -> None:
        torque = self.parameters.maximum_torque
        ElementTree.SubElement(
            self.section(root, MjcfTag.ACTUATOR),
            MjcfTag.POSITION_ACTUATOR,
            {
                MjcfAttribute.NAME: RefrigeratorName.DOOR_DRIVE,
                MjcfAttribute.JOINT: self.layout.door_joint,
                MjcfAttribute.POSITION_GAIN: str(self.parameters.stiffness),
                MjcfAttribute.VELOCITY_GAIN: str(self.parameters.damping),
                MjcfAttribute.FORCE_LIMITED: MjcfValue.TRUE,
                MjcfAttribute.FORCE_RANGE: numbers([-torque, torque]),
            },
        )


# %% refrigerator


@dataclass
class LaboratoryRefrigerator:
    """
    Opens and closes the door through its drive and reads which vessels it stores.
    """

    model: mujoco.MjModel
    """
    The compiled model.
    """

    data: mujoco.MjData
    """
    The simulation state.
    """

    layout: RefrigeratorLayout
    """
    The authored refrigerator.
    """

    vessels: Sequence[str]
    """
    The vessels it may store.
    """

    parameters: RefrigeratorParameters = field(default_factory=RefrigeratorParameters)
    """
    The drive, tolerances and temperature model.
    """

    cabinet: int = field(init=False)
    """
    The cabinet's body.
    """

    door_joint: int = field(init=False)
    """
    The door's hinge.
    """

    door_drive: int = field(init=False)
    """
    The door's drive.
    """

    target_angle: float = field(init=False, default=0.0)
    """
    The door angle asked for, in radians.
    """

    commanded_angle: float = field(init=False, default=0.0)
    """
    The angle the drive is commanded, ramped towards the target.
    """

    temperature: float = field(init=False, default=0.0)
    """
    The cabinet's temperature, in degrees Celsius.
    """

    def __post_init__(self) -> None:
        self.cabinet = self.model.body(self.layout.body).id
        self.door_joint = self.model.joint(self.layout.door_joint).id
        self.door_drive = self.model.actuator(RefrigeratorName.DOOR_DRIVE).id
        self.temperature = self.layout.target_temperature

    @property
    def door_angle(self) -> float:
        """
        The door's measured angle from closed, in radians.
        """
        return float(self.data.qpos[self.model.jnt_qposadr[self.door_joint]])

    @property
    def door_open(self) -> bool:
        """
        Whether the door reached its open stop.
        """
        return (
            self.door_angle >= self.layout.door_open - self.parameters.angle_tolerance
        )

    @property
    def door_closed(self) -> bool:
        """
        Whether the door is at its closed stop.
        """
        return abs(self.door_angle) <= self.parameters.angle_tolerance

    def reset(self) -> None:
        """
        Restore the closed, cooled cabinet; the stored vessels stay where they are.
        """
        self.target_angle = self.commanded_angle = 0.0
        self.temperature = self.layout.target_temperature
        self.data.ctrl[self.door_drive] = 0.0
        self.data.qpos[self.model.jnt_qposadr[self.door_joint]] = 0.0
        self.data.qvel[self.model.jnt_dofadr[self.door_joint]] = 0.0

    def operate(self, action: OpeningAction) -> None:
        """
        :param action: Whether to open or close the door.
        """
        self.target_angle = (
            self.layout.door_open if action is OpeningAction.OPEN else 0.0
        )

    def advance(self, elapsed: float) -> None:
        """
        Ramp the door's drive and let the cabinet warm or cool.

        :param elapsed: The simulated time since the previous call, in seconds.
        """
        step = self.parameters.angular_speed * elapsed
        self.commanded_angle += float(
            np.clip(self.target_angle - self.commanded_angle, -step, step)
        )
        self.data.ctrl[self.door_drive] = self.commanded_angle
        opening = float(np.clip(self.door_angle / self.layout.door_open, 0.0, 1.0))
        target = self.layout.target_temperature
        equilibrium = target + opening * (self.parameters.ambient_temperature - target)
        time_constant = (
            self.parameters.warming_time
            if equilibrium > self.temperature
            else self.parameters.cooling_time
        )
        self.temperature += (equilibrium - self.temperature) * (
            -math.expm1(-elapsed / time_constant)
        )

    def occupants(self) -> Dict[str, Optional[str]]:
        """
        :return: The upright vessel the cabinet carries at each storage position, None
            for an empty one.
        """
        occupants: Dict[str, Optional[str]] = {
            slot.identifier: None for slot in self.layout.slots
        }
        reader = ContactReader(self.model, self.data)
        for key in self.vessels:
            body = self.model.body(key).id
            upright = self.data.xmat[body].reshape(3, 3)[2, 2] >= math.cos(
                self.parameters.upright_tolerance
            )
            carried = reader.supports_of(body).get(self.cabinet, 0.0) > (
                self.parameters.support_share * reader.weight(body)
            )
            if not upright or not carried:
                continue
            for slot in self.layout.slots:
                distance = np.linalg.norm(
                    self.data.xpos[body] - np.array(slot.position.to_json())
                )
                if distance <= self.parameters.position_tolerance:
                    occupants[slot.identifier] = key
                    break
        return occupants

    def guard_manipulation(self, key: str) -> None:
        """
        :param key: A vessel a person wants to move or fill.
        :raises OperationRefused: When it is stored and the door is not fully open.
        """
        if not self.door_open and key in self.occupants().values():
            raise OperationRefused(Refusal.REFRIGERATOR_CLOSED)

    def joints(self) -> Dict[str, float]:
        """
        :return: The door's measured angle, by joint name.
        """
        return {self.layout.door_joint: self.door_angle}

    def state(self) -> RefrigeratorState:
        """
        :return: What the refrigerator measures, as the browser reads it.
        """
        return RefrigeratorState(
            door_open=self.door_open,
            door_closed=self.door_closed,
            temperature=round(self.temperature, TEMPERATURE_DIGITS),
            temperature_source=TemperatureSource.SIMULATED,
            positions=[
                StoragePosition(identifier=identifier, key=key)
                for identifier, key in self.occupants().items()
            ],
        )
