"""
The laboratory's contact simulation: the compiled model, its state, and every part of
the laboratory stepped together.

Only a reset writes object poses. A person moves an object by pulling it towards a
target with a spring whose force stays below what a careful hand applies; gravity,
friction and contacts decide where the object goes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from typing_extensions import Dict, FrozenSet, List, Optional

from cramera_laboratory.commands import CommandCheck
from cramera_laboratory.dispenser import LaboratoryDispenser
from cramera_laboratory.exceptions import (
    OperationRefused,
    Refusal,
    UnknownObject,
    ValueOutOfRange,
)
from cramera_laboratory.geometry import RigidPose, vector_of
from cramera_laboratory.liquid import LaboratoryLiquid, VesselShape, laboratory_fills
from cramera_laboratory.physics.centrifuge import (
    CentrifugeModelPart,
    LaboratoryCentrifuge,
)
from cramera_laboratory.physics.contacts import SPATIAL_VELOCITY_SIZE, ContactReader
from cramera_laboratory.physics.drawer import DrawerModelPart, LaboratoryDrawer
from cramera_laboratory.physics.instruments import (
    InstrumentDrives,
    InstrumentModelPart,
)
from cramera_laboratory.physics.mass import LiquidMass
from cramera_laboratory.physics.model import (
    CollisionModel,
    ContactParameters,
    ModelPart,
)
from cramera_laboratory.physics.rack import LaboratoryRack, RackModelPart, RackName
from cramera_laboratory.physics.refrigerator import (
    LaboratoryRefrigerator,
    RefrigeratorModelPart,
)
from cramera_laboratory.physics.scale import LaboratoryScale, ScaleGeometry
from cramera_laboratory.resources import LaboratoryBundle
from cramera_laboratory.session import ContactSimulation
from cramera_protocol.geometry import Pose, Vector3
from cramera_protocol.laboratory.layout import CornerBox, Quaternion
from cramera_protocol.laboratory.physics import (
    CentrifugeRequest,
    ContactPhysicsControls,
    DispenserRequest,
    InstrumentRequest,
    LiquidRequest,
    ManualRequest,
    OpeningRequest,
    PullTarget,
    SimulationSnapshot,
    TargetRequest,
)

UPRIGHT = Quaternion(0.0, 0.0, 0.0, 1.0)
"""
The orientation a pulled object is turned towards when the request names none.
"""

DEFAULT_BOUNDS = CornerBox(
    minimum=Vector3(-1.55, -0.85, 0.15), maximum=Vector3(0.8, 0.45, 1.6)
)
"""
Where pull targets may lie in the bench laboratory, in metres.
"""

LIQUID_TIME_TOLERANCE = 1e-12
"""
How much earlier than due a liquid update still runs, in seconds.
"""


class ObjectRole(StrEnum):
    """
    What an object was asked to be.
    """

    FREE_OBJECT = "free object"
    """
    An object a person may pull.
    """


class Quantity(StrEnum):
    """
    The quantities a simulation command gives.
    """

    TARGET_X = "target's x coordinate"
    """
    A target's x coordinate.
    """

    TARGET_Y = "target's y coordinate"
    """
    A target's y coordinate.
    """

    TARGET_Z = "target's z coordinate"
    """
    A target's z coordinate.
    """


# %% parameters


@dataclass(frozen=True)
class PullParameters:
    """
    The spring a person pulls an object with.
    """

    stiffness: float = 12.0
    """
    The spring's stiffness, in newtons per metre.
    """

    damping: float = 0.8
    """
    The spring's damping, in newton seconds per metre.
    """

    maximum_force: float = 0.6
    """
    The strongest pull, gravity compensation included, in newtons.
    """

    angular_stiffness: float = 0.04
    """
    The stiffness that turns the object, in newton metres per radian.
    """

    angular_damping: float = 0.0016
    """
    The turning damping, in newton metre seconds per radian.
    """

    maximum_torque: float = 0.02
    """
    The strongest turning torque, in newton metres.
    """


@dataclass(frozen=True)
class SimulationParameters:
    """
    The simulation's settings.
    """

    contacts: ContactParameters = field(default_factory=ContactParameters)
    """
    How MuJoCo integrates and resolves contacts.
    """

    pull: PullParameters = field(default_factory=PullParameters)
    """
    The spring a person pulls with.
    """

    liquid_period: float = 0.02
    """
    The simulated time between liquid updates, in seconds.
    """


# %% pull


@dataclass(frozen=True)
class Pull:
    """
    An object a person pulls, and where to.
    """

    key: str
    """
    The object.
    """

    body: int
    """
    The object's body.
    """

    position: np.ndarray
    """
    Where its origin is pulled.
    """

    orientation: Quaternion
    """
    How it is turned.
    """

    def document(self) -> PullTarget:
        """
        :return: The target as the browser reads it.
        """
        return PullTarget(
            key=self.key,
            position=vector_of(self.position),
            orientation=self.orientation,
        )


# %% simulation


@dataclass
class LaboratoryPhysics(ContactSimulation):
    """
    The contact simulation of one laboratory.

    Its owner serializes every call.
    """

    laboratory: LaboratoryBundle
    """
    The laboratory simulated.
    """

    parameters: SimulationParameters = field(default_factory=SimulationParameters)
    """
    The simulation's settings.
    """

    model: mujoco.MjModel = field(init=False, repr=False)
    """
    The compiled model.
    """

    data: mujoco.MjData = field(init=False, repr=False)
    """
    The simulation state.
    """

    objects: Dict[str, int] = field(init=False)
    """
    Each free object's body, by key.
    """

    liquid: LaboratoryLiquid = field(init=False)
    """
    The vessels' liquid.
    """

    mass: LiquidMass = field(init=False)
    """
    The liquid's weight on the vessels.
    """

    scale: Optional[LaboratoryScale] = field(init=False, default=None)
    """
    The scale.
    """

    centrifuge: Optional[LaboratoryCentrifuge] = field(init=False, default=None)
    """
    The centrifuge.
    """

    refrigerator: Optional[LaboratoryRefrigerator] = field(init=False, default=None)
    """
    The refrigerator.
    """

    drawer: Optional[LaboratoryDrawer] = field(init=False, default=None)
    """
    The drawer.
    """

    rack: Optional[LaboratoryRack] = field(init=False, default=None)
    """
    The rack.
    """

    dispenser: Optional[LaboratoryDispenser] = field(init=False, default=None)
    """
    The dispensing station.
    """

    instruments: Optional[InstrumentDrives] = field(init=False, default=None)
    """
    The expanded laboratory's instruments.
    """

    pull: Optional[Pull] = field(init=False, default=None)
    """
    The object pulled, None while nothing is.
    """

    applied_force: float = field(init=False, default=0.0)
    """
    The pulling force now, in newtons.
    """

    maximum_applied_force: float = field(init=False, default=0.0)
    """
    The largest pulling force since the last reset, in newtons.
    """

    maximum_contact_force: float = field(init=False, default=0.0)
    """
    The largest single contact force since the last reset, in newtons.
    """

    liquid_elapsed: float = field(init=False, default=0.0)
    """
    The simulated time since the last liquid update, in seconds.
    """

    def __post_init__(self) -> None:
        bench = self.laboratory.bench()
        collection = self.laboratory.instruments()
        vessels = [placement.key for placement in bench.tubes]
        parts: List[ModelPart] = [RackModelPart()]
        if bench.centrifuge is not None:
            parts.append(CentrifugeModelPart(bench.centrifuge, vessels))
        if bench.refrigerator is not None:
            parts.append(RefrigeratorModelPart(bench.refrigerator))
        if bench.drawer is not None:
            parts.append(DrawerModelPart(bench.drawer))
        if collection is not None:
            parts.append(InstrumentModelPart(collection))
        description = self.laboratory.description
        self.model = CollisionModel(
            directory=self.laboratory.directory,
            environment=[
                Path(model.urdf) for model in description.models if not model.robot
            ],
            objects=list(description.objects),
            parts=parts,
            parameters=self.parameters.contacts,
            scale_geometries=list(ScaleGeometry),
            floating_links=[RackName.BODY],
            has_room=collection is not None,
        ).build()
        self.data = mujoco.MjData(self.model)
        self.objects = {
            item.key: self.model.body(item.key).id for item in description.objects
        }
        shape = VesselShape()
        fills = {
            key: fill for key, fill in laboratory_fills(shape).items() if key in vessels
        }
        self.liquid = LaboratoryLiquid(fills=fills, shape=shape)
        self.mass = LiquidMass(self.model, {key: self.objects[key] for key in fills})
        self.scale = LaboratoryScale.of_model(self.model, self.data)
        self.rack = LaboratoryRack.of_model(self.model, self.data, bench)
        if bench.centrifuge is not None:
            self.centrifuge = LaboratoryCentrifuge(
                self.model, self.data, bench.centrifuge, vessels
            )
        if bench.refrigerator is not None:
            self.refrigerator = LaboratoryRefrigerator(
                self.model, self.data, bench.refrigerator, vessels
            )
        if bench.drawer is not None:
            self.drawer = LaboratoryDrawer(self.model, self.data, bench.drawer)
        if bench.dispenser is not None:
            self.dispenser = LaboratoryDispenser(
                bench.dispenser, self.liquid, bench.stopper
            )
        if collection is not None:
            self.instruments = InstrumentDrives(self.model, self.data, collection)
        self.reset()

    # %% lifecycle

    @property
    def timestep(self) -> float:
        """
        The integration step, in seconds.
        """
        return float(self.model.opt.timestep)

    def reset(self) -> None:
        """
        Restore the authored laboratory: objects at their spawn poses, at rest, initial
        fills, instruments at rest; the centrifuge keeps the manual it follows.
        """
        mujoco.mj_resetData(self.model, self.data)
        self.pull = None
        self.applied_force = self.maximum_applied_force = self.maximum_contact_force = (
            0.0
        )
        self.liquid_elapsed = 0.0
        for part in (self.centrifuge, self.refrigerator, self.drawer, self.instruments):
            if part is not None:
                part.reset()
        mujoco.mj_forward(self.model, self.data)
        self.liquid.reset(self.vessel_poses())
        if self.dispenser is not None:
            self.dispenser.reset()
        self.mass.synchronize(self.liquid)
        mujoco.mj_forward(self.model, self.data)
        if self.scale is not None:
            self.scale.reset()

    def step(self, count: int) -> None:
        """
        Integrate a number of steps.

        :param count: How many steps.
        """
        for _ in range(count):
            self.apply_pull()
            for part in (
                self.centrifuge,
                self.refrigerator,
                self.drawer,
                self.instruments,
            ):
                if part is not None:
                    part.advance(self.timestep)
            mujoco.mj_step(self.model, self.data)
            self.observe_contacts()
            self.liquid_elapsed += self.timestep
            if (
                self.liquid_elapsed + LIQUID_TIME_TOLERANCE
                >= self.parameters.liquid_period
            ):
                self.update_liquid()
            if self.scale is not None:
                self.scale.observe()
        mujoco.mj_forward(self.model, self.data)

    def update_liquid(self) -> None:
        """
        Advance the liquid and the dispensing station by the time since their last
        update.
        """
        poses = self.object_poses()
        self.liquid.step(self.liquid_elapsed, poses)
        if self.dispenser is not None:
            self.dispenser.advance(self.liquid_elapsed, poses, self.clamped())
        if self.mass.synchronize(self.liquid):
            mujoco.mj_forward(self.model, self.data)
        self.liquid_elapsed = 0.0

    def observe_contacts(self) -> None:
        """
        Remember the largest contact force.
        """
        for contact in ContactReader(self.model, self.data).contacts():
            self.maximum_contact_force = max(
                self.maximum_contact_force, contact.normal_force
            )

    # %% measurements

    def object_poses(self) -> Dict[str, RigidPose]:
        """
        :return: Every free object's measured pose.
        """
        return {
            key: RigidPose.of_scalar_first(self.data.xpos[body], self.data.xquat[body])
            for key, body in self.objects.items()
        }

    def vessel_poses(self) -> Dict[str, RigidPose]:
        """
        :return: The measured poses of the vessels holding liquid.
        """
        poses = self.object_poses()
        return {key: poses[key] for key in self.liquid.fills}

    def clamped(self) -> FrozenSet[str]:
        """
        :return: The vessels a centrifuge holder clamps.
        """
        if self.centrifuge is None:
            return frozenset()
        return frozenset(
            holder.key
            for holder in self.centrifuge.holders.values()
            if holder.key is not None
        )

    def bounds(self) -> CornerBox:
        """
        :return: Where pull targets may lie.
        """
        collection = self.laboratory.instruments()
        if collection is not None and collection.bounds is not None:
            return collection.bounds
        return DEFAULT_BOUNDS

    # %% commands

    def guard_manipulation(self, key: str) -> None:
        """
        :param key: A free object a person wants to move or fill.
        :raises OperationRefused: When an instrument holds it.
        """
        if self.centrifuge is not None:
            self.centrifuge.guard_manipulation(key)
        if self.refrigerator is not None:
            self.refrigerator.guard_manipulation(key)

    def set_target(self, request: TargetRequest) -> None:
        """
        Pull an object towards a target.

        :param request: The object and the target.
        :raises UnknownObject: When no free object has the key.
        :raises ValueOutOfRange: When the target lies outside the bounds.
        :raises OperationRefused: When an instrument holds the object.
        """
        CommandCheck().target(request)
        if request.key not in self.objects:
            raise UnknownObject(request.key, ObjectRole.FREE_OBJECT)
        bounds = self.bounds()
        for quantity, value, lowest, highest in zip(
            (Quantity.TARGET_X, Quantity.TARGET_Y, Quantity.TARGET_Z),
            request.position.to_json(),
            bounds.minimum.to_json(),
            bounds.maximum.to_json(),
        ):
            if not lowest <= value <= highest:
                raise ValueOutOfRange(quantity, value, lowest, highest)
        self.guard_manipulation(request.key)
        orientation = request.orientation or UPRIGHT
        unit = np.array(orientation.to_json()) / np.linalg.norm(orientation.to_json())
        self.pull = Pull(
            key=request.key,
            body=self.objects[request.key],
            position=np.array(request.position.to_json()),
            orientation=Quaternion(*(float(value) for value in unit)),
        )

    def release(self) -> None:
        """
        Let go of the pulled object.
        """
        self.pull = None
        self.data.xfrc_applied[:] = 0
        self.applied_force = 0.0

    def apply_pull(self) -> None:
        """
        Apply the bounded spring force and torque of the current pull.
        """
        self.data.xfrc_applied[:] = 0
        self.applied_force = 0.0
        if self.pull is None:
            return
        parameters = self.parameters.pull
        body = self.pull.body
        velocity = np.zeros(SPATIAL_VELOCITY_SIZE)
        mujoco.mj_objectVelocity(
            self.model, self.data, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0
        )
        force = (
            parameters.stiffness * (self.pull.position - self.data.xpos[body])
            - parameters.damping * velocity[3:]
            - self.model.body_mass[body] * self.model.opt.gravity
        )
        force = self.limited(force, parameters.maximum_force)
        rotation = (
            Rotation.from_quat(self.pull.orientation.to_json())
            * Rotation.from_quat(self.data.xquat[body], scalar_first=True).inv()
        ).as_rotvec()
        torque = (
            parameters.angular_stiffness * rotation
            - parameters.angular_damping * velocity[:3]
        )
        principal = self.data.ximat[body].reshape(3, 3)
        inertia = self.model.body_inertia[body]
        response = inertia / (
            inertia
            + self.timestep * parameters.angular_damping
            + self.timestep**2 * parameters.angular_stiffness
        )
        torque = principal @ (response * (principal.T @ torque))
        self.data.xfrc_applied[body, :3] = force
        self.data.xfrc_applied[body, 3:] = self.limited(
            torque, parameters.maximum_torque
        )
        self.applied_force = float(np.linalg.norm(force))
        self.maximum_applied_force = max(self.maximum_applied_force, self.applied_force)

    @staticmethod
    def limited(vector: np.ndarray, maximum: float) -> np.ndarray:
        """
        :param vector: A force or torque.
        :param maximum: The largest magnitude allowed.
        :return: The vector, shortened to the maximum if longer.
        """
        magnitude = float(np.linalg.norm(vector))
        return vector * min(1.0, maximum / magnitude) if magnitude else vector

    def fill(self, request: LiquidRequest) -> None:
        """
        :param request: A vessel and the amount it holds afterwards.
        :raises OperationRefused: When an instrument holds the vessel or a dose flows
            into it.
        """
        CommandCheck().liquid(request)
        self.guard_manipulation(request.key)
        if self.dispenser is not None and self.dispenser.receiving(request.key):
            raise OperationRefused(Refusal.DOSE_DELIVERING)
        self.liquid.fill(request.key, request.volume)
        self.mass.synchronize(self.liquid)
        mujoco.mj_forward(self.model, self.data)
        if self.scale is not None:
            self.scale.observe(force=True)

    def tare(self) -> None:
        """
        :raises OperationRefused: Without a scale or before its reading settled.
        """
        if self.scale is None:
            raise OperationRefused(Refusal.NO_SCALE)
        self.scale.take_tare()

    def operate_centrifuge(self, request: CentrifugeRequest) -> None:
        """
        :param request: A centrifuge operation.
        :raises OperationRefused: Without a centrifuge or when its state refuses it.
        """
        CommandCheck().centrifuge(request)
        if self.centrifuge is None:
            raise OperationRefused(Refusal.NO_CENTRIFUGE)
        self.centrifuge.operate(request)
        if (
            self.pull is not None
            and request.key == self.pull.key
            and request.key in self.clamped()
        ):
            self.release()

    def read_manual(self, request: ManualRequest) -> None:
        """
        :param request: A manual for the centrifuge.
        :raises OperationRefused: Without a centrifuge or while its rotor turns.
        """
        manual = CommandCheck.manual(request)
        if self.centrifuge is None:
            raise OperationRefused(Refusal.NO_CENTRIFUGE)
        self.centrifuge.read(manual)

    def operate_refrigerator(self, request: OpeningRequest) -> None:
        """
        :param request: Whether to open or close the door.
        :raises OperationRefused: Without a refrigerator.
        """
        if self.refrigerator is None:
            raise OperationRefused(Refusal.NO_REFRIGERATOR)
        self.refrigerator.operate(request.action)

    def operate_drawer(self, request: OpeningRequest) -> None:
        """
        :param request: Whether to open or close the drawer.
        :raises OperationRefused: Without a drawer.
        """
        if self.drawer is None:
            raise OperationRefused(Refusal.NO_DRAWER)
        self.drawer.operate(request.action)

    def operate_dispenser(self, request: DispenserRequest) -> None:
        """
        :param request: A dispensing station operation.
        :raises OperationRefused: Without a station or when the receiver refuses it.
        """
        CommandCheck().dispenser(request)
        if self.dispenser is None:
            raise OperationRefused(Refusal.NO_DISPENSER)
        self.dispenser.operate(request, self.object_poses(), self.clamped())

    def move_instrument(self, request: InstrumentRequest) -> None:
        """
        :param request: An instrument and the pose to move it to.
        :raises OperationRefused: Without the instrument collection.
        """
        if self.instruments is None:
            raise OperationRefused(Refusal.NO_INSTRUMENTS)
        self.instruments.move(request.instrument, request.pose)

    # %% reports

    def joints(self) -> Dict[str, float]:
        """
        :return: The measured positions of the environment's moving joints, by name.
        """
        joints: Dict[str, float] = {}
        for part in (self.centrifuge, self.refrigerator, self.drawer):
            if part is not None:
                joints.update(part.joints())
        if self.instruments is not None:
            joints.update(self.instruments.joint_positions())
        return joints

    def snapshot(self) -> SimulationSnapshot:
        """
        :return: What the simulation measures, as the browser reads it.
        """
        objects: Dict[str, Pose] = {}
        for key, body in self.objects.items():
            w, x, y, z = (float(value) for value in self.data.xquat[body])
            px, py, pz = (float(value) for value in self.data.xpos[body])
            objects[key] = Pose(px, py, pz, x, y, z, w)
        return SimulationSnapshot(
            time=float(self.data.time),
            energy=float(np.sum(self.data.energy)),
            applied_force=self.applied_force,
            maximum_applied_force=self.maximum_applied_force,
            maximum_contact_force=self.maximum_contact_force,
            objects=objects,
            body_poses={} if self.rack is None else self.rack.body_poses(),
            joints=self.joints(),
            target=None if self.pull is None else self.pull.document(),
            contacts=ContactReader(self.model, self.data).measured(),
            liquid=self.liquid.state(),
            scale=None if self.scale is None else self.scale.reading(),
            centrifuge=None if self.centrifuge is None else self.centrifuge.state(),
            refrigerator=(
                None if self.refrigerator is None else self.refrigerator.state()
            ),
            drawer=None if self.drawer is None else self.drawer.state(),
            rack=None if self.rack is None else self.rack.state(),
            dispenser=None if self.dispenser is None else self.dispenser.status(),
        )

    def controls(self) -> ContactPhysicsControls:
        """
        :return: What the browser needs to operate this simulation.
        """
        return ContactPhysicsControls(
            laboratory=self.laboratory.name,
            objects=list(self.objects),
            vessels=list(self.liquid.fills),
            bounds=self.bounds(),
            maximum_force=self.parameters.pull.maximum_force,
            interior=self.liquid.shape.document(),
            doses=None if self.dispenser is None else self.dispenser.limits(),
            cycles=None if self.centrifuge is None else self.centrifuge.cycle_limits(),
        )
