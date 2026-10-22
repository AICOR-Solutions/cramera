"""
The contact forces MuJoCo's solver computed, read once per question: which bodies touch,
how hard, and which bodies carry another's weight.
"""

from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np
from typing_extensions import Dict, Iterator, List

from cramera_laboratory.geometry import vector_of
from cramera_protocol.laboratory.physics import MeasuredContact

WRENCH_SIZE = 6
"""
The components of a contact wrench: three force and three torque components.
"""

# %% contacts


@dataclass(frozen=True)
class SolvedContact:
    """
    One contact the solver pushes apart.
    """

    index: int
    """
    The contact's index in the solver's contact list.
    """

    first_geometry: int
    """
    The first geometry.
    """

    second_geometry: int
    """
    The second geometry.
    """

    first_body: int
    """
    The first geometry's body.
    """

    second_body: int
    """
    The second geometry's body.
    """

    normal_force: float
    """
    The normal force, in newtons; positive.
    """

    frame: np.ndarray
    """
    The contact frame, its first row the normal from the first geometry towards the
    second.
    """

    position: np.ndarray
    """
    Where the geometries touch.
    """

    wrench: np.ndarray
    """
    The force and torque in the contact frame.
    """

    def world_force(self) -> np.ndarray:
        """
        :return: The force the first geometry exerts on the second, in the laboratory's
            frame.
        """
        return self.frame.T @ self.wrench[:3]

    def upward_force_on(self, body: int) -> float:
        """
        :param body: One of the two bodies.
        :return: How hard the other body pushes it upwards, in newtons; zero for a
            downward push.
        """
        direction = 1.0 if self.second_body == body else -1.0
        return max(0.0, direction * float(self.frame[0, 2]) * self.normal_force)

    def other(self, body: int) -> int:
        """
        :param body: One of the two bodies.
        :return: The other body.
        """
        return self.first_body if self.second_body == body else self.second_body

    def involves(self, body: int) -> bool:
        """
        :param body: A body.
        :return: Whether it is one of the two bodies.
        """
        return body in (self.first_body, self.second_body)


@dataclass(frozen=True)
class ContactReader:
    """
    Reads the solver's contacts of one model state.
    """

    model: mujoco.MjModel
    """
    The compiled model.
    """

    data: mujoco.MjData
    """
    The state whose contacts are read.
    """

    def contacts(self) -> Iterator[SolvedContact]:
        """
        :return: Every contact the solver pushes apart with a positive force.
        """
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            if contact.efc_address < 0:
                continue
            wrench = np.zeros(WRENCH_SIZE)
            mujoco.mj_contactForce(self.model, self.data, index, wrench)
            if wrench[0] <= 0:
                continue
            yield SolvedContact(
                index=index,
                first_geometry=int(contact.geom1),
                second_geometry=int(contact.geom2),
                first_body=int(self.model.geom_bodyid[contact.geom1]),
                second_body=int(self.model.geom_bodyid[contact.geom2]),
                normal_force=float(wrench[0]),
                frame=contact.frame.reshape(3, 3).copy(),
                position=contact.pos.copy(),
                wrench=wrench,
            )

    def supports_of(self, body: int) -> Dict[int, float]:
        """
        :param body: A body.
        :return: The upward force each touching body exerts on it, in newtons.
        """
        forces: Dict[int, float] = {}
        for contact in self.contacts():
            if not contact.involves(body):
                continue
            other = contact.other(body)
            forces[other] = forces.get(other, 0.0) + contact.upward_force_on(body)
        return forces

    def weight(self, body: int) -> float:
        """
        :param body: A body.
        :return: Its weight with what it holds, in newtons.
        """
        return float(self.model.body_mass[body]) * float(
            np.linalg.norm(self.model.opt.gravity)
        )

    def name(self, body: int) -> str:
        """
        :param body: A body.
        :return: Its name.
        """
        return self.model.body(body).name

    def measured(self) -> List[MeasuredContact]:
        """
        :return: Every contact as the browser reads it.
        """
        return [
            MeasuredContact(
                position=vector_of(contact.position),
                normal=vector_of(contact.frame[0]),
                force=contact.normal_force,
                first_body=self.name(contact.first_body),
                second_body=self.name(contact.second_body),
            )
            for contact in self.contacts()
        ]
