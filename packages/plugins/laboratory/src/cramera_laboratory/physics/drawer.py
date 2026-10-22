"""
The bench drawer: a rail with its authored friction and stops, and a drive holding it at
an end with no more force than a person pulls a drawer with.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from enum import StrEnum

import mujoco
import numpy as np
from typing_extensions import Dict

from cramera_laboratory.physics.model import (
    MjcfAttribute,
    MjcfTag,
    MjcfValue,
    ModelPart,
    UrdfInertial,
    numbers,
)
from cramera_laboratory.urdf import UrdfAttribute, UrdfTag
from cramera_protocol.laboratory.layout import DrawerLayout
from cramera_protocol.laboratory.physics import DrawerState, OpeningAction


class DrawerName(StrEnum):
    """
    The names the drawer's drive takes in the model.
    """

    DRIVE = "laboratory_drawer_motor"
    """
    The drawer's position drive.
    """


# %% parameters


@dataclass(frozen=True)
class DrawerParameters:
    """
    The drawer drive's limits.
    """

    maximum_force: float = 40.0
    """
    The drive's largest force, in newtons, about what a person pulls a drawer with.
    """

    stiffness: float = 400.0
    """
    The drive's stiffness, in newtons per metre.
    """

    damping: float = 50.0
    """
    The drive's damping, in newton seconds per metre.
    """

    speed: float = 0.10
    """
    How fast the commanded position may change, in metres per second.
    """

    position_tolerance: float = 0.005
    """
    How close to a stop the drawer counts as open or closed, in metres.
    """


# %% model


@dataclass
class DrawerModelPart(ModelPart):
    """
    Imports the drawer's rail and adds its force-limited drive.
    """

    layout: DrawerLayout
    """
    The authored drawer.
    """

    parameters: DrawerParameters = field(default_factory=DrawerParameters)
    """
    The drive's limits.
    """

    def import_joint(
        self,
        body: ElementTree.Element,
        link: ElementTree.Element,
        joint: ElementTree.Element,
    ) -> bool:
        if joint.get(UrdfAttribute.NAME) != self.layout.joint:
            return False
        UrdfInertial.of_link(link).add_to(body)
        dynamics = joint.find(UrdfTag.DYNAMICS)
        ElementTree.SubElement(
            body,
            MjcfTag.JOINT,
            {
                MjcfAttribute.NAME: self.layout.joint,
                MjcfAttribute.TYPE: MjcfValue.SLIDE,
                MjcfAttribute.AXIS: self.axis(joint),
                MjcfAttribute.LIMITED: MjcfValue.TRUE,
                MjcfAttribute.RANGE: self.limits(joint),
                MjcfAttribute.DAMPING: dynamics.get(UrdfAttribute.DAMPING),
                MjcfAttribute.FRICTION_LOSS: dynamics.get(UrdfAttribute.FRICTION),
            },
        )
        return True

    def complete(self, root: ElementTree.Element) -> None:
        force = self.parameters.maximum_force
        ElementTree.SubElement(
            self.section(root, MjcfTag.ACTUATOR),
            MjcfTag.POSITION_ACTUATOR,
            {
                MjcfAttribute.NAME: DrawerName.DRIVE,
                MjcfAttribute.JOINT: self.layout.joint,
                MjcfAttribute.POSITION_GAIN: str(self.parameters.stiffness),
                MjcfAttribute.VELOCITY_GAIN: str(self.parameters.damping),
                MjcfAttribute.FORCE_LIMITED: MjcfValue.TRUE,
                MjcfAttribute.FORCE_RANGE: numbers([-force, force]),
            },
        )


# %% drawer


@dataclass
class LaboratoryDrawer:
    """
    Moves the drawer to an end through its drive.
    """

    model: mujoco.MjModel
    """
    The compiled model.
    """

    data: mujoco.MjData
    """
    The simulation state.
    """

    layout: DrawerLayout
    """
    The authored drawer.
    """

    parameters: DrawerParameters = field(default_factory=DrawerParameters)
    """
    The drive's limits.
    """

    joint: int = field(init=False)
    """
    The drawer's rail.
    """

    drive: int = field(init=False)
    """
    The drawer's drive.
    """

    target: float = field(init=False, default=0.0)
    """
    Where the drive is asked to hold the drawer, in metres.
    """

    commanded: float = field(init=False, default=0.0)
    """
    Where the drive is commanded, ramped towards the target.
    """

    def __post_init__(self) -> None:
        self.joint = self.model.joint(self.layout.joint).id
        self.drive = self.model.actuator(DrawerName.DRIVE).id

    @property
    def position(self) -> float:
        """
        How far the drawer is out, measured, in metres.
        """
        return float(self.data.qpos[self.model.jnt_qposadr[self.joint]])

    @property
    def open_position(self) -> float:
        """
        The rail's outer stop, in metres.
        """
        return float(self.model.jnt_range[self.joint, 1])

    def reset(self) -> None:
        """
        Hold the drawer closed.
        """
        self.target = self.commanded = 0.0
        self.data.ctrl[self.drive] = 0.0

    def operate(self, action: OpeningAction) -> None:
        """
        :param action: Whether to open or close the drawer.
        """
        self.target = self.open_position if action is OpeningAction.OPEN else 0.0

    def advance(self, elapsed: float) -> None:
        """
        :param elapsed: The simulated time since the previous call, in seconds.
        """
        step = self.parameters.speed * elapsed
        self.commanded += float(np.clip(self.target - self.commanded, -step, step))
        self.data.ctrl[self.drive] = self.commanded

    def joints(self) -> Dict[str, float]:
        """
        :return: The drawer's measured position, by joint name.
        """
        return {self.layout.joint: self.position}

    def state(self) -> DrawerState:
        """
        :return: What the drawer measures, as the browser reads it.
        """
        tolerance = self.parameters.position_tolerance
        return DrawerState(
            position=self.position,
            target=self.target,
            fully_open=abs(self.position - self.open_position) <= tolerance,
            closed=abs(self.position) <= tolerance,
        )
