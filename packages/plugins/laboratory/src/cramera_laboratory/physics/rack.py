"""
The sample rack: a free body that carries the vessels standing in its slots.

Which vessel stands in which slot is read from where the vessels are and whether the
rack carries them.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from enum import StrEnum

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from typing_extensions import Dict, List, Optional

from cramera_laboratory.geometry import RigidPose
from cramera_laboratory.physics.contacts import ContactReader
from cramera_laboratory.physics.model import (
    MjcfAttribute,
    MjcfTag,
    ModelPart,
    UrdfInertial,
)
from cramera_laboratory.urdf import UrdfAttribute, UrdfJointType
from cramera_protocol.geometry import Pose
from cramera_protocol.laboratory.layout import BenchLayout
from cramera_protocol.laboratory.physics import RackPosition, RackState


class RackName(StrEnum):
    """
    The rack's names in the environment.
    """

    BODY = "laboratory_rack"
    """
    The rack's link.
    """

    JOINT = "laboratory_rack_joint"
    """
    The rack's floating joint.
    """


# %% parameters


@dataclass(frozen=True)
class RackParameters:
    """
    When a vessel counts as standing in a slot.
    """

    position_tolerance: float = 0.008
    """
    How far a vessel's bottom may lie from the slot's position, in metres.
    """

    upright_tolerance: float = 0.15
    """
    How far a vessel may lean against the rack, in radians.
    """

    support_share: float = 0.2
    """
    The share of a body's weight a support must carry to count as one.
    """


# %% model


@dataclass
class RackModelPart(ModelPart):
    """
    Gives the rack, which the environment declares floating, a free joint of its own.
    """

    def import_joint(
        self,
        body: ElementTree.Element,
        link: ElementTree.Element,
        joint: ElementTree.Element,
    ) -> bool:
        if (
            joint.get(UrdfAttribute.NAME) != RackName.JOINT
            or joint.get(UrdfAttribute.TYPE) != UrdfJointType.FLOATING
        ):
            return False
        UrdfInertial.of_link(link).add_to(body)
        ElementTree.SubElement(
            body, MjcfTag.FREE_JOINT, {MjcfAttribute.NAME: RackName.JOINT}
        )
        return True

    def complete(self, root: ElementTree.Element) -> None:
        """
        The rack needs no drives.
        """


# %% rack


@dataclass
class LaboratoryRack:
    """
    Reads where the rack stands, where its slots are and what they hold.
    """

    model: mujoco.MjModel
    """
    The compiled model.
    """

    data: mujoco.MjData
    """
    The simulation state.
    """

    bench: BenchLayout
    """
    The authored bench, whose slot poses describe the rack where it starts.
    """

    parameters: RackParameters = field(default_factory=RackParameters)
    """
    The occupancy tolerances.
    """

    body: int = field(init=False)
    """
    The rack's body.
    """

    local_positions: Dict[str, np.ndarray] = field(init=False)
    """
    Each slot's position in the rack's frame.
    """

    @classmethod
    def of_model(
        cls, model: mujoco.MjModel, data: mujoco.MjData, bench: BenchLayout
    ) -> Optional[LaboratoryRack]:
        """
        :param model: The compiled model.
        :param data: The simulation state.
        :param bench: The authored bench.
        :return: The rack, or None when it does not move freely.
        """
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, RackName.JOINT)
        if joint < 0 or model.jnt_type[joint] != mujoco.mjtJoint.mjJNT_FREE:
            return None
        return cls(model, data, bench)

    def __post_init__(self) -> None:
        self.body = self.model.body(RackName.BODY).id
        start = RigidPose(
            position=self.model.body_pos[self.body].copy(),
            rotation=Rotation.from_quat(
                self.model.body_quat[self.body], scalar_first=True
            ).as_matrix(),
        )
        self.local_positions = {
            slot.identifier: start.point_in_body(RigidPose.of_pose(slot.pose).position)
            for slot in self.bench.rack_slots
        }

    def pose(self) -> RigidPose:
        """
        :return: Where the rack stands, measured.
        """
        return RigidPose.of_scalar_first(
            self.data.xpos[self.body], self.data.xquat[self.body]
        )

    def slot_position(self, identifier: str) -> np.ndarray:
        """
        :param identifier: A slot.
        :return: Where a vessel's bottom stands in it now.
        """
        return self.pose().point_in_world(self.local_positions[identifier])

    def occupants(self) -> Dict[str, Optional[str]]:
        """
        :return: The upright vessel the rack carries in each slot, None for an empty
            slot.
        """
        occupants: Dict[str, Optional[str]] = dict.fromkeys(self.local_positions)
        rack = self.pose()
        reader = ContactReader(self.model, self.data)
        for placement in self.bench.tubes:
            body = self.model.body(placement.key).id
            vessel = self.data.xmat[body].reshape(3, 3)
            if (rack.rotation.T @ vessel)[2, 2] < math.cos(
                self.parameters.upright_tolerance
            ):
                continue
            if reader.supports_of(body).get(self.body, 0.0) <= (
                self.parameters.support_share * reader.weight(body)
            ):
                continue
            for identifier in occupants:
                if (
                    np.linalg.norm(
                        self.data.xpos[body] - self.slot_position(identifier)
                    )
                    <= self.parameters.position_tolerance
                ):
                    occupants[identifier] = placement.key
                    break
        return occupants

    def supports(self) -> List[str]:
        """
        :return: The bodies carrying a share of the rack's weight.
        """
        reader = ContactReader(self.model, self.data)
        weight = reader.weight(self.body)
        return [
            reader.name(body)
            for body, force in reader.supports_of(self.body).items()
            if force > self.parameters.support_share * weight
        ]

    def body_poses(self) -> Dict[str, Pose]:
        """
        :return: The rack's pose, by its link's name.
        """
        return {RackName.BODY.value: self.pose().pose()}

    def state(self) -> RackState:
        """
        :return: What the rack measures, as the browser reads it.
        """
        rack = self.pose()
        occupants = self.occupants()
        return RackState(
            pose=rack.pose(),
            supports=self.supports(),
            slots=[
                RackPosition(
                    identifier=identifier,
                    pose=rack.moved_to(self.slot_position(identifier)).pose(),
                    key=occupants[identifier],
                )
                for identifier in self.local_positions
            ],
        )
