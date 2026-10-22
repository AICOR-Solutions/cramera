"""
The bench centrifuge: a hinged lid and a rotor of four holders, each moved by a force-
limited drive. Every operation checks what the simulation measures: the lid's angle, the
rotor's speed, whether a vessel rests seated on a holder's floor, and whether opposite
holders carry equal masses.

A secured vessel is held by a clamp anchored where the vessel was measured to rest, so
clamping never moves it.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from enum import StrEnum

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from typing_extensions import Dict, List, Optional, Sequence

from cramera_laboratory.exceptions import (
    OperationRefused,
    Refusal,
    TooFewSamples,
    ValueOutOfRange,
)
from cramera_laboratory.geometry import vector_of
from cramera_laboratory.knowledge import (
    CentrifugeManual,
    CentrifugeObservation,
    ManualKnowledge,
)
from cramera_laboratory.physics.contacts import ContactReader
from cramera_laboratory.physics.model import (
    MjcfAttribute,
    MjcfTag,
    MjcfValue,
    ModelPart,
    UrdfInertial,
    numbers,
)
from cramera_laboratory.urdf import UrdfAttribute, UrdfJointType
from cramera_protocol.laboratory.layout import CentrifugeLayout
from cramera_protocol.laboratory.physics import (
    CentrifugeAction,
    CentrifugeRequest,
    CentrifugeState,
    CycleLimits,
    RotorHolder,
)

SECONDS_PER_MINUTE = 60.0
"""
How many seconds a minute has.
"""

GRAMS_PER_KILOGRAM = 1000.0
"""
How many grams a kilogram has.
"""

SPEED_DIGITS = 2
"""
The decimal places of a reported speed or remaining time.
"""

FORCE_DIGITS = 3
"""
The decimal places of a reported relative centrifugal force or holder mass.
"""

ANCHOR_SIZE = 0.001
"""
The radius of a clamp's anchor sites, in metres.
"""

CLAMP_STIFFNESS = "0.008 1"
"""
How fast a clamp pulls its vessel back, as a solver time constant and damping ratio.
"""

CLAMP_TORQUE_SCALE = "0.02"
"""
How strongly a clamp holds the vessel's orientation compared with its position.
"""

COMMAND_EPSILON = 1e-9
"""
How small a commanded speed counts as zero, in revolutions per minute.
"""


class Quantity(StrEnum):
    """
    The quantities a centrifuge request gives.
    """

    SPEED = "rotor speed"
    """
    A speed in revolutions per minute.
    """

    DURATION = "cycle duration"
    """
    A cycle length in seconds.
    """


class CentrifugeName(StrEnum):
    """
    The names the centrifuge's drives and clamps take in the model.
    """

    LID_DRIVE = "laboratory_centrifuge_lid_motor"
    """
    The lid's position drive.
    """

    ROTOR_DRIVE = "laboratory_centrifuge_rotor_motor"
    """
    The rotor's velocity drive.
    """

    CLAMP = "laboratory_centrifuge_clamp_"
    """
    The prefix of a vessel's clamp.
    """

    ROTOR_ANCHOR = "laboratory_centrifuge_rotor_anchor_"
    """
    The prefix of a clamp's anchor on the rotor.
    """

    VESSEL_ANCHOR = "laboratory_centrifuge_tube_anchor_"
    """
    The prefix of a clamp's anchor on the vessel.
    """

    HOLDER_FLOOR = "{rotor}_slot_{number}_floor"
    """
    A holder's floor geometry, formatted with the rotor's link and the holder's number
    counted from one.
    """


# %% parameters


@dataclass(frozen=True)
class CentrifugeParameters:
    """
    The centrifuge's drives and the tolerances of its measured interlocks.
    """

    motor_torque: float = 0.12
    """
    The rotor drive's largest torque, in newton metres.
    """

    motor_gain: float = 0.05
    """
    The rotor drive's velocity gain, in newton metre seconds per radian.
    """

    rotor_damping: float = 0.0001
    """
    The bearing's damping, in newton metre seconds per radian.
    """

    acceleration: float = 60.0
    """
    How fast the commanded speed may change, in revolutions per minute per second.
    """

    lid_speed: float = 0.6
    """
    How fast the lid's commanded angle may change, in radians per second.
    """

    lid_stiffness: float = 20.0
    """
    The lid drive's stiffness, in newton metres per radian.
    """

    lid_damping: float = 1.0
    """
    The lid drive's damping, in newton metre seconds per radian.
    """

    lid_torque: float = 2.0
    """
    The lid drive's largest torque, in newton metres.
    """

    stopped_speed: float = 0.5
    """
    The largest measured speed that counts as standing still, in revolutions per minute.
    """

    lid_tolerance: float = 0.02
    """
    How close to a stop the lid counts as open or closed, in radians.
    """

    seating_distance: float = 0.003
    """
    How far a seated vessel's bottom may lie from the holder's position, in metres.
    """

    seating_angle: float = 0.04
    """
    How far a seated vessel may lean, in radians.
    """

    seating_speed: float = 0.02
    """
    How fast a seated vessel may still move, in metres per second.
    """

    balance: float = 0.25
    """
    The largest mass difference between opposite samples, in grams.
    """

    support_share: float = 0.5
    """
    The share of a vessel's weight the holder's floor must carry to clamp it.
    """

    default_speed: float = 120.0
    """
    The speed of a cycle when a request gives none, in revolutions per minute.
    """

    minimum_speed: float = 1.0
    """
    The lowest speed a cycle may ask for, in revolutions per minute.
    """

    default_duration: float = 20.0
    """
    The length of a cycle when a request gives none, in simulated seconds.
    """

    minimum_duration: float = 1.0
    """
    The shortest cycle, in simulated seconds.
    """

    maximum_duration: float = 300.0
    """
    The longest cycle, in simulated seconds.
    """

    speed_tolerance: float = 0.05
    """
    The share of the target speed within which a cycle's timer runs.
    """

    chamber_lower_margin: float = 0.04
    """
    How far below the holders' floors the chamber reaches, in metres.
    """


# %% model


@dataclass
class CentrifugeModelPart(ModelPart):
    """
    Imports the lid's hinge and the rotor's joint, and adds their drives and one idle
    clamp per vessel.
    """

    layout: CentrifugeLayout
    """
    The authored centrifuge.
    """

    vessels: Sequence[str]
    """
    The vessels a holder may clamp.
    """

    parameters: CentrifugeParameters = field(default_factory=CentrifugeParameters)
    """
    The drives' limits.
    """

    def import_joint(
        self,
        body: ElementTree.Element,
        link: ElementTree.Element,
        joint: ElementTree.Element,
    ) -> bool:
        name = joint.get(UrdfAttribute.NAME)
        if name not in (self.layout.lid_joint, self.layout.rotor_joint):
            return False
        UrdfInertial.of_link(link).add_to(body)
        attributes = {
            MjcfAttribute.NAME: name,
            MjcfAttribute.TYPE: MjcfValue.HINGE,
            MjcfAttribute.AXIS: self.axis(joint),
            MjcfAttribute.DAMPING: str(self.parameters.rotor_damping),
        }
        if joint.get(UrdfAttribute.TYPE) == UrdfJointType.REVOLUTE:
            attributes[MjcfAttribute.LIMITED] = MjcfValue.TRUE
            attributes[MjcfAttribute.RANGE] = self.limits(joint)
            body.set(MjcfAttribute.GRAVITY_COMPENSATION, MjcfValue.ON)
        ElementTree.SubElement(body, MjcfTag.JOINT, attributes)
        return True

    def complete(self, root: ElementTree.Element) -> None:
        rotor = root.find(
            f".//{MjcfTag.BODY}[@{MjcfAttribute.NAME}='{self.layout.rotor_body}']"
        )
        actuators = self.section(root, MjcfTag.ACTUATOR)
        torque = self.parameters.motor_torque
        ElementTree.SubElement(
            actuators,
            MjcfTag.VELOCITY_ACTUATOR,
            {
                MjcfAttribute.NAME: CentrifugeName.ROTOR_DRIVE,
                MjcfAttribute.JOINT: self.layout.rotor_joint,
                MjcfAttribute.VELOCITY_GAIN: str(self.parameters.motor_gain),
                MjcfAttribute.FORCE_LIMITED: MjcfValue.TRUE,
                MjcfAttribute.FORCE_RANGE: numbers([-torque, torque]),
            },
        )
        lid_torque = self.parameters.lid_torque
        ElementTree.SubElement(
            actuators,
            MjcfTag.POSITION_ACTUATOR,
            {
                MjcfAttribute.NAME: CentrifugeName.LID_DRIVE,
                MjcfAttribute.JOINT: self.layout.lid_joint,
                MjcfAttribute.POSITION_GAIN: str(self.parameters.lid_stiffness),
                MjcfAttribute.VELOCITY_GAIN: str(self.parameters.lid_damping),
                MjcfAttribute.FORCE_LIMITED: MjcfValue.TRUE,
                MjcfAttribute.FORCE_RANGE: numbers([-lid_torque, lid_torque]),
            },
        )
        equalities = self.section(root, MjcfTag.EQUALITY)
        for key in self.vessels:
            vessel = root.find(f".//{MjcfTag.BODY}[@{MjcfAttribute.NAME}='{key}']")
            rotor_anchor = f"{CentrifugeName.ROTOR_ANCHOR}{key}"
            vessel_anchor = f"{CentrifugeName.VESSEL_ANCHOR}{key}"
            for body, anchor in ((rotor, rotor_anchor), (vessel, vessel_anchor)):
                ElementTree.SubElement(
                    body,
                    MjcfTag.SITE,
                    {MjcfAttribute.NAME: anchor, MjcfAttribute.SIZE: str(ANCHOR_SIZE)},
                )
            ElementTree.SubElement(
                equalities,
                MjcfTag.WELD,
                {
                    MjcfAttribute.NAME: f"{CentrifugeName.CLAMP}{key}",
                    MjcfAttribute.SITE_FIRST: rotor_anchor,
                    MjcfAttribute.SITE_SECOND: vessel_anchor,
                    MjcfAttribute.ACTIVE: MjcfValue.FALSE,
                    MjcfAttribute.SOLVER_REFERENCE: CLAMP_STIFFNESS,
                    MjcfAttribute.TORQUE_SCALE: CLAMP_TORQUE_SCALE,
                },
            )


# %% holders


@dataclass
class Holder:
    """
    One holder of the rotor and the vessel it clamps.
    """

    identifier: str
    """
    The holder's name.
    """

    opposite: str
    """
    The holder on the rotor's opposite side.
    """

    position: np.ndarray
    """
    Where a seated vessel's bottom rests, in the rotor's frame.
    """

    floor: int
    """
    The holder floor's geometry.
    """

    key: Optional[str] = None
    """
    The clamped vessel, None while the holder is free.
    """


# %% centrifuge


@dataclass
class LaboratoryCentrifuge:
    """
    Operates the centrifuge through its drives and clamps, refusing what its measured
    state does not allow.
    """

    model: mujoco.MjModel
    """
    The compiled model.
    """

    data: mujoco.MjData
    """
    The simulation state.
    """

    layout: CentrifugeLayout
    """
    The authored centrifuge.
    """

    vessels: Sequence[str]
    """
    The vessels a holder may clamp.
    """

    parameters: CentrifugeParameters = field(default_factory=CentrifugeParameters)
    """
    The drives and interlock tolerances.
    """

    knowledge: ManualKnowledge = field(default_factory=ManualKnowledge)
    """
    The manual the centrifuge is operated by; it stays when the laboratory is reset.
    """

    holders: Dict[str, Holder] = field(init=False)
    """
    The rotor's holders by name.
    """

    rotor: int = field(init=False)
    """
    The rotor's body.
    """

    rotor_joint: int = field(init=False)
    """
    The rotor's joint.
    """

    lid_joint: int = field(init=False)
    """
    The lid's hinge.
    """

    rotor_drive: int = field(init=False)
    """
    The rotor's velocity drive.
    """

    lid_drive: int = field(init=False)
    """
    The lid's position drive.
    """

    target_speed: float = field(init=False, default=0.0)
    """
    The speed asked for, in revolutions per minute.
    """

    commanded_speed: float = field(init=False, default=0.0)
    """
    The speed the drive is commanded, ramped towards the target.
    """

    lid_target: float = field(init=False, default=0.0)
    """
    The lid angle asked for, in radians.
    """

    remaining: float = field(init=False, default=0.0)
    """
    The time left of the cycle at speed, in simulated seconds.
    """

    at_speed: bool = field(init=False, default=False)
    """
    Whether the current cycle reached its speed, which starts its timer.
    """

    def __post_init__(self) -> None:
        self.rotor = self.model.body(self.layout.rotor_body).id
        self.rotor_joint = self.model.joint(self.layout.rotor_joint).id
        self.lid_joint = self.model.joint(self.layout.lid_joint).id
        self.rotor_drive = self.model.actuator(CentrifugeName.ROTOR_DRIVE).id
        self.lid_drive = self.model.actuator(CentrifugeName.LID_DRIVE).id
        self.holders = {
            slot.identifier: Holder(
                identifier=slot.identifier,
                opposite=slot.opposite,
                position=np.array(slot.position.to_json()),
                floor=self.model.geom(
                    CentrifugeName.HOLDER_FLOOR.format(
                        rotor=self.layout.rotor_body, number=number
                    )
                ).id,
            )
            for number, slot in enumerate(self.layout.slots, start=1)
        }

    # %% measurements

    @property
    def speed(self) -> float:
        """
        The rotor's measured speed, in revolutions per minute.
        """
        velocity = float(self.data.qvel[self.model.jnt_dofadr[self.rotor_joint]])
        return velocity * SECONDS_PER_MINUTE / math.tau

    @property
    def lid_angle(self) -> float:
        """
        The lid's measured angle from closed, in radians.
        """
        return float(self.data.qpos[self.model.jnt_qposadr[self.lid_joint]])

    @property
    def stopped(self) -> bool:
        """
        Whether the rotor stands still and is not driven.
        """
        return (
            self.target_speed == 0
            and self.commanded_speed == 0
            and abs(self.speed) < self.parameters.stopped_speed
        )

    @property
    def lid_open(self) -> bool:
        """
        Whether the lid reached its open stop.
        """
        return self.lid_angle >= self.layout.open_angle - self.parameters.lid_tolerance

    @property
    def lid_closed(self) -> bool:
        """
        Whether the lid is closed and kept closed.
        """
        return (
            abs(self.lid_angle) <= self.parameters.lid_tolerance
            and self.lid_target == 0
        )

    def holder_mass(self, holder: Holder) -> float:
        """
        :param holder: A holder.
        :return: The clamped vessel's mass with its liquid, in grams; zero when free.
        """
        if holder.key is None:
            return 0.0
        return (
            float(self.model.body_mass[self.model.body(holder.key).id])
            * GRAMS_PER_KILOGRAM
        )

    def loose_load(self) -> bool:
        """
        :return: Whether an unclamped vessel lies in the chamber or touches the rotor.
        """
        clamped = {holder.key for holder in self.holders.values()}
        rotation = self.data.xmat[self.rotor].reshape(3, 3)
        floor = (
            min(holder.position[2] for holder in self.holders.values())
            - self.parameters.chamber_lower_margin
        )
        loose = set()
        for key in self.vessels:
            if key in clamped:
                continue
            body = self.model.body(key).id
            loose.add(body)
            local = rotation.T @ (self.data.xpos[body] - self.data.xpos[self.rotor])
            if (
                np.linalg.norm(local[:2]) <= self.layout.chamber_radius
                and floor <= local[2] <= self.layout.chamber_height
            ):
                return True
        return any(
            contact.involves(self.rotor) and contact.other(self.rotor) in loose
            for contact in ContactReader(self.model, self.data).contacts()
        )

    @property
    def balanced(self) -> bool:
        """
        Whether some holder clamps a vessel, every clamped vessel has an opposite one of
        equal mass, and nothing loose lies in the chamber.
        """
        occupied = [
            holder for holder in self.holders.values() if holder.key is not None
        ]
        if not occupied or self.loose_load():
            return False
        return all(
            self.holders[holder.opposite].key is not None
            and abs(
                self.holder_mass(holder)
                - self.holder_mass(self.holders[holder.opposite])
            )
            <= self.parameters.balance
            for holder in occupied
        )

    def holder_position(self, holder: Holder) -> np.ndarray:
        """
        :param holder: A holder.
        :return: Where a seated vessel's bottom rests at the rotor's measured angle.
        """
        return (
            self.data.xpos[self.rotor]
            + self.data.xmat[self.rotor].reshape(3, 3) @ holder.position
        )

    def clamps(self, key: str) -> bool:
        """
        :param key: A vessel.
        :return: Whether a holder clamps it.
        """
        return any(holder.key == key for holder in self.holders.values())

    def observation(self) -> CentrifugeObservation:
        """
        :return: What starting depends on, as measured now.
        """
        return CentrifugeObservation(
            secured_samples=sum(
                holder.key is not None for holder in self.holders.values()
            ),
            balanced=self.balanced,
            lid_closed=self.lid_closed,
            stopped=self.stopped,
        )

    # %% operations

    def reset(self) -> None:
        """
        Restore the stopped rotor with its lid open and every clamp loose; the manual
        stays.
        """
        self.target_speed = self.commanded_speed = self.remaining = 0.0
        self.at_speed = False
        self.lid_target = self.layout.open_angle
        self.data.qpos[self.model.jnt_qposadr[self.lid_joint]] = self.layout.open_angle
        self.data.ctrl[self.lid_drive] = self.layout.open_angle
        self.data.ctrl[self.rotor_drive] = 0.0
        for key in self.vessels:
            self.clamp(key).loosen()
        for holder in self.holders.values():
            holder.key = None

    def clamp(self, key: str) -> ClampSwitch:
        """
        :param key: A vessel.
        :return: The switch of the vessel's clamp.
        """
        return ClampSwitch(
            self.data,
            self.model.equality(f"{CentrifugeName.CLAMP}{key}").id,
        )

    def guard_manipulation(self, key: str) -> None:
        """
        :param key: A vessel a person wants to move or fill.
        :raises OperationRefused: When a holder clamps it.
        """
        if self.clamps(key):
            raise OperationRefused(Refusal.CLAMPED_VESSEL)

    def read(self, manual: CentrifugeManual) -> None:
        """
        :param manual: Another manual to follow.
        :raises OperationRefused: While the rotor turns.
        """
        if not self.stopped:
            raise OperationRefused(Refusal.STOP_FOR_MANUAL)
        self.knowledge.read(manual, float(self.data.time))

    def operate(self, request: CentrifugeRequest) -> None:
        """
        :param request: An operation, its fields checked for its action.
        :raises OperationRefused: When the measured state does not allow it.
        """
        if request.action is CentrifugeAction.SECURE:
            self.secure(request.slot, request.key)
        elif request.action is CentrifugeAction.RELEASE:
            self.release(request.slot)
        elif request.action in (CentrifugeAction.OPEN, CentrifugeAction.CLOSE):
            if not self.stopped:
                raise OperationRefused(Refusal.ROTOR_TURNING)
            self.lid_target = (
                self.layout.open_angle
                if request.action is CentrifugeAction.OPEN
                else 0.0
            )
        elif request.action is CentrifugeAction.START:
            self.start(request.speed, request.duration)
        else:
            self.target_speed = self.remaining = 0.0
            self.at_speed = False

    def require_loading(self) -> None:
        """
        :raises OperationRefused: Unless the rotor stands still with its lid fully open.
        """
        if not self.stopped or not self.lid_open:
            raise OperationRefused(Refusal.NOT_LOADABLE)

    def secure(self, identifier: str, key: str) -> None:
        """
        Clamp a vessel seated in a holder where it rests.

        :param identifier: The holder.
        :param key: The vessel.
        :raises OperationRefused: Unless the vessel rests upright and still on the free
            holder's floor of the stopped, open centrifuge.
        """
        self.require_loading()
        if identifier not in self.holders or key not in self.vessels:
            raise OperationRefused(Refusal.UNKNOWN_HOLDER)
        holder = self.holders[identifier]
        if holder.key is not None or self.clamps(key):
            raise OperationRefused(Refusal.HOLDER_TAKEN)
        body = self.model.body(key).id
        if not self.seated(holder, body):
            raise OperationRefused(Refusal.NOT_SEATED)
        rotation = self.data.xmat[self.rotor].reshape(3, 3)
        anchor = self.model.site(f"{CentrifugeName.ROTOR_ANCHOR}{key}").id
        self.model.site_pos[anchor] = rotation.T @ (
            self.data.xpos[body] - self.data.xpos[self.rotor]
        )
        self.model.site_quat[anchor] = Rotation.from_matrix(
            rotation.T @ self.data.xmat[body].reshape(3, 3)
        ).as_quat(scalar_first=True)
        self.model.site_sameframe[anchor] = mujoco.mjtSameFrame.mjSAMEFRAME_NONE
        self.clamp(key).engage()
        holder.key = key
        mujoco.mj_forward(self.model, self.data)

    def seated(self, holder: Holder, body: int) -> bool:
        """
        :param holder: A holder.
        :param body: A vessel's body.
        :return: Whether the vessel rests upright and still on the holder's floor,
            carried by it.
        """
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(
            self.model, self.data, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0
        )
        placed = (
            np.linalg.norm(self.data.xpos[body] - self.holder_position(holder))
            <= self.parameters.seating_distance
            and self.data.xmat[body].reshape(3, 3)[2, 2]
            >= math.cos(self.parameters.seating_angle)
            and np.linalg.norm(velocity[3:]) <= self.parameters.seating_speed
        )
        reader = ContactReader(self.model, self.data)
        support = sum(
            contact.normal_force
            for contact in reader.contacts()
            if holder.floor in (contact.first_geometry, contact.second_geometry)
            and contact.involves(body)
        )
        return placed and support >= self.parameters.support_share * reader.weight(body)

    def release(self, identifier: str) -> None:
        """
        :param identifier: A holder whose clamp to loosen.
        :raises OperationRefused: Unless the rotor stands still with its lid open and
            the holder clamps a vessel.
        """
        self.require_loading()
        if identifier not in self.holders or self.holders[identifier].key is None:
            raise OperationRefused(Refusal.EMPTY_HOLDER)
        holder = self.holders[identifier]
        self.clamp(holder.key).loosen()
        holder.key = None

    def start(self, speed: Optional[float], duration: Optional[float]) -> None:
        """
        :param speed: The cycle's speed, None for the default.
        :param duration: The cycle's length at speed, None for the default.
        :raises ValueOutOfRange: For a speed or length outside the limits.
        :raises TooFewSamples: When fewer samples are secured than the manual asks for.
        :raises OperationRefused: Unless the lid is closed, the load balanced and the
            rotor still.
        """
        speed = self.parameters.default_speed if speed is None else speed
        duration = self.parameters.default_duration if duration is None else duration
        if not self.parameters.minimum_speed <= speed <= self.layout.maximum_speed:
            raise ValueOutOfRange(
                Quantity.SPEED,
                speed,
                self.parameters.minimum_speed,
                self.layout.maximum_speed,
            )
        limits = self.cycle_limits()
        if not limits.minimum_duration <= duration <= limits.maximum_duration:
            raise ValueOutOfRange(
                Quantity.DURATION,
                duration,
                limits.minimum_duration,
                limits.maximum_duration,
            )
        observation = self.observation()
        required = self.knowledge.active.minimum_samples
        if observation.secured_samples < required:
            raise TooFewSamples(
                self.knowledge.active.version, required, observation.secured_samples
            )
        if not (
            observation.lid_closed and observation.balanced and observation.stopped
        ):
            raise OperationRefused(Refusal.NOT_READY_TO_START)
        self.target_speed = float(speed)
        self.remaining = float(duration)
        self.at_speed = False

    def advance(self, elapsed: float) -> None:
        """
        Ramp the drives and run the cycle's timer from the measured speed.

        :param elapsed: The simulated time since the previous call, in seconds.
        """
        if self.target_speed > 0:
            if not self.lid_closed or not self.balanced:
                self.target_speed = self.remaining = 0.0
            elif (
                abs(self.speed - self.target_speed)
                <= self.parameters.speed_tolerance * self.target_speed
            ):
                self.at_speed = True
            if self.at_speed:
                self.remaining = max(0.0, self.remaining - elapsed)
                if self.remaining == 0:
                    self.target_speed = 0.0
        ramp = self.parameters.acceleration * elapsed
        self.commanded_speed += float(
            np.clip(self.target_speed - self.commanded_speed, -ramp, ramp)
        )
        if abs(self.commanded_speed) < COMMAND_EPSILON:
            self.commanded_speed = 0.0
        self.data.ctrl[self.rotor_drive] = (
            self.commanded_speed * math.tau / SECONDS_PER_MINUTE
        )
        lid_step = self.parameters.lid_speed * elapsed
        self.data.ctrl[self.lid_drive] += float(
            np.clip(
                self.lid_target - self.data.ctrl[self.lid_drive], -lid_step, lid_step
            )
        )

    # %% reports

    def joints(self) -> Dict[str, float]:
        """
        :return: The lid's and the rotor's measured positions, by joint name.
        """
        return {
            self.layout.lid_joint: self.lid_angle,
            self.layout.rotor_joint: float(
                self.data.qpos[self.model.jnt_qposadr[self.rotor_joint]]
            ),
        }

    def cycle_limits(self) -> CycleLimits:
        """
        :return: The limits of a cycle.
        """
        return CycleLimits(
            default_speed=self.parameters.default_speed,
            maximum_speed=self.layout.maximum_speed,
            default_duration=self.parameters.default_duration,
            minimum_duration=self.parameters.minimum_duration,
            maximum_duration=self.parameters.maximum_duration,
        )

    def state(self) -> CentrifugeState:
        """
        :return: What the centrifuge measures, as the browser reads it.
        """
        radius = max(
            np.linalg.norm(holder.position[:2]) for holder in self.holders.values()
        )
        gravity = float(np.linalg.norm(self.model.opt.gravity))
        angular = self.speed * math.tau / SECONDS_PER_MINUTE
        holders: List[RotorHolder] = [
            RotorHolder(
                identifier=holder.identifier,
                position=vector_of(self.holder_position(holder)),
                key=holder.key,
                grams=round(self.holder_mass(holder), FORCE_DIGITS),
            )
            for holder in self.holders.values()
        ]
        return CentrifugeState(
            speed=round(self.speed, SPEED_DIGITS),
            target_speed=self.target_speed,
            relative_force=round(angular**2 * radius / gravity, FORCE_DIGITS),
            lid_open=self.lid_open,
            lid_closed=self.lid_closed,
            running=not self.stopped,
            balanced=self.balanced,
            remaining=round(self.remaining, SPEED_DIGITS),
            holders=holders,
            knowledge=self.knowledge.document(self.observation()),
        )


@dataclass(frozen=True)
class ClampSwitch:
    """
    Engages or loosens one vessel's clamp.
    """

    data: mujoco.MjData
    """
    The simulation state holding the clamps' switches.
    """

    equality: int
    """
    The clamp's equality constraint.
    """

    def engaged(self) -> bool:
        """
        :return: Whether the clamp holds its vessel.
        """
        return bool(self.data.eq_active[self.equality])

    def engage(self) -> None:
        """
        Let the clamp hold its vessel.
        """
        self.data.eq_active[self.equality] = True

    def loosen(self) -> None:
        """
        Let the clamp free its vessel.
        """
        self.data.eq_active[self.equality] = False
