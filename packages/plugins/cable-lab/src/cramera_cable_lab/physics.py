"""
The cable lab's simulation: a composite cable on a narrow support rail below a Cartesian
parallel gripper whose force-limited pads hold the cable only by friction, simulated
headless by CRAM's MuJoCo adapter in the background.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import current_thread

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from typing_extensions import ClassVar, List, Mapping, Sequence, Tuple

from cramera_cable_lab.cable import (
    Cable,
    CableMujocoBuilder,
    CableMujocoSynchronizer,
)
from cramera_cable_lab.exceptions import (
    GripperTargetOutsideWorkspace,
    SteppingWhileRunning,
    StoppedSimulation,
)
from cramera_cable_lab.session import GRIPPER_WORKSPACE, CableSimulation
from cramera_protocol.cable_lab import (
    AnchorObservation,
    CableConfiguration,
    CableContact,
    CableLabState,
    CablePoint,
    CableSegment,
    GraspObservation,
    GraspState,
    GripperAction,
    GripperCommand,
    GripperObservation,
    OrientedBox,
    SimulationLifecycle,
)
from cramera_protocol.geometry import Pose, Vector3
from physics_simulators.base_simulator import SimulatorState
from physics_simulators.mujoco_simulator import MujocoSimulator
from semantic_digital_twin.adapters.multi_sim import MujocoSim
from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import FixedConnection
from semantic_digital_twin.world_description.world_entity import Body

# %% names


class RigName(StrEnum):
    """
    The names of the lab's parts.
    """

    CARRIAGE = "cable_gripper"
    """
    The Cartesian carriage carrying the pads.
    """

    LEFT_PAD = "cable_gripper_left_pad"
    """
    The pad on the carriage's positive y side.
    """

    RIGHT_PAD = "cable_gripper_right_pad"
    """
    The pad on the carriage's negative y side.
    """

    SUPPORT = "cable_support"
    """
    The narrow rail the cable starts on.
    """

    FLOOR = "cable_floor"
    """
    The ground.
    """

    SCENE = "cable-laboratory.xml"
    """
    The model file CRAM's adapter writes.
    """

    WORLD = "world"
    """
    The world's root.
    """

    MOUNT = "cable_mount"
    """
    The raised body the cable's anchor frame is fixed to.
    """


TEMPORARY_PREFIX = "cramera-cable-"
"""
The prefix of the directory the model file is written to.
"""

LIFT_DIRECTIONS: Mapping[GripperAction, float] = {
    GripperAction.LIFT: 1.0,
    GripperAction.LOWER: -1.0,
}
"""
The direction a lift or a lower moves the gripper's target along z.
"""

# %% parameters


@dataclass(frozen=True)
class RigParameters:
    """
    The rig's dimensions, actuator gains and limits, and motion rates.
    """

    timestep: float = 0.001
    """
    The integration interval, in seconds.
    """

    lift_distance: float = 0.05
    """
    How far one lift or lower moves the target, in metres.
    """

    carriage_speed: float = 0.05
    """
    The carriage target's largest speed, in metres per second.
    """

    pad_speed: float = 0.06
    """
    The pads' targets' largest speed, in metres per second.
    """

    open_clearance: float = 0.02
    """
    The gap between an open pad and the cable's surface, in metres.
    """

    pad_half_size: Sequence[float] = (0.06, 0.004, 0.02)
    """
    Each pad's half extents, in metres.
    """

    pad_mass: float = 0.03
    """
    Each pad's mass, in kilograms.
    """

    pad_force: float = 2.0
    """
    Each pad actuator's largest force, in newtons.
    """

    pad_stiffness: float = 500.0
    """
    The pads' position gain, in newtons per metre.
    """

    pad_damping: float = 2.0
    """
    The pads' velocity gain, in newton seconds per metre.
    """

    carriage_stiffness: float = 2000.0
    """
    The carriage's position gain, in newtons per metre.
    """

    carriage_damping: float = 60.0
    """
    The carriage's velocity gain, in newton seconds per metre.
    """

    carriage_force: float = 100.0
    """
    The carriage actuators' largest force, in newtons.
    """

    carriage_mass: float = 0.2
    """
    The carriage's mass, in kilograms.
    """

    carriage_radius: float = 0.01
    """
    The radius of the carriage's massive, collision-free sphere, in metres.
    """

    support_depth: float = 0.02
    """
    The rail's thickness, in metres.
    """

    support_margin: float = 0.05
    """
    How far the rail reaches beyond each end of the cable, in metres.
    """

    floor_depth: float = 0.35
    """
    How far below the mount the ground is, in metres.
    """

    floor_half_size: Sequence[float] = (1.0, 1.0, 0.01)
    """
    The ground plane's half extents and grid spacing, in metres.
    """

    holding_speed: float = 0.01
    """
    The largest speed of the cable against a pad that still counts as held, in metres
    per second.
    """

    mount_height: float = 0.35
    """
    The mount's height above the world's origin, in metres.
    """

    impedance_ratio: float = 10.0
    """
    MuJoCo's ratio of frictional to normal constraint impedance.
    """

    support_color: Sequence[float] = (0.28, 0.36, 0.43, 1.0)
    """
    The rail's colour.
    """

    floor_color: Sequence[float] = (0.1, 0.12, 0.15, 1.0)
    """
    The ground's colour.
    """

    pad_color: Sequence[float] = (0.24, 0.67, 0.91, 1.0)
    """
    The pads' colour.
    """


INVISIBLE = (0.0, 0.0, 0.0, 0.0)
"""
The colour of the carriage's sphere.
"""

GRAVITY_COMPENSATED = 1.0
"""
The share of gravity MuJoCo compensates for the carriage and the pads.
"""

NO_CONTACT = 0
"""
The contact type and affinity of a body that touches nothing.
"""

# %% simulator


@dataclass(eq=False)
class PacedMujocoSimulator(MujocoSimulator):
    """
    CRAM's MuJoCo simulator with every step under the model lock, so commands and
    measurements see whole steps, and the background thread paced to the wall clock.
    """

    def step(self) -> None:
        started = time.monotonic()
        with self._model_lock:
            super().step()
        if self.simulation_thread is current_thread():
            time.sleep(max(0.0, self.step_size - (time.monotonic() - started)))


@dataclass(init=False)
class CableLabSimulation(MujocoSim):
    """
    CRAM's headless MuJoCo adapter for a world holding a cable: the semantic points stay
    out of the model and follow the capsules.
    """

    builder_class: ClassVar[type[CableMujocoBuilder]] = CableMujocoBuilder
    """
    Leaves the semantic points out of the model.
    """

    synchronizer_class: ClassVar[type[CableMujocoSynchronizer]] = (
        CableMujocoSynchronizer
    )
    """
    Puts the capsules' poses on the semantic points.
    """

    simulator_class: ClassVar[type[PacedMujocoSimulator]] = PacedMujocoSimulator
    """
    Steps under the model lock, paced to the wall clock.
    """

    def __init__(
        self, world: World, scene_path: Path, parameters: RigParameters
    ) -> None:
        self.default_file_path = str(scene_path)
        super().__init__(
            world,
            headless=True,
            step_size=parameters.timestep,
            integrator=mujoco.mjtIntegrator.mjINT_RK4,
            cone=mujoco.mjtCone.mjCONE_ELLIPTIC,
            impratio=parameters.impedance_ratio,
        )


# %% rig


@dataclass(frozen=True)
class RigFrame:
    """
    Where the rig stands: centred on the cable, along the cable's direction.
    """

    origin: np.ndarray
    """
    The carriage's initial position, over the cable's middle.
    """

    rotation: np.ndarray
    """
    The rig's orientation; its x axis runs along the cable.
    """

    support_position: np.ndarray
    """
    The rail's centre.
    """

    support_size: np.ndarray
    """
    The rail's full size.
    """

    @classmethod
    def of_cable(cls, cable: Cable, parameters: RigParameters) -> RigFrame:
        """
        :param cable: The cable.
        :param parameters: The rig's dimensions.
        :return: The rig's frame under and over the cable.
        """
        configuration = cable.configuration
        rotation = cable.root_T_anchor[:3, :3]
        origin = (
            cable.root_T_anchor[:3, 3] + rotation[:, 0] * configuration.length() / 2
        )
        size = np.array(
            [
                configuration.length() + 2 * parameters.support_margin,
                configuration.radius,
                parameters.support_depth,
            ]
        )
        support = origin - rotation[:, 2] * (
            configuration.radius + parameters.support_depth / 2
        )
        return cls(origin, rotation, support, size)

    def quaternion(self) -> np.ndarray:
        """
        :return: The rig's orientation, scalar first.
        """
        return Rotation.from_matrix(self.rotation).as_quat(scalar_first=True)


@dataclass(frozen=True)
class RigBuilder:
    """
    Adds the rail, the ground, the carriage and the pads with their actuators to a
    specification.
    """

    frame: RigFrame
    """
    Where the rig stands.
    """

    configuration: CableConfiguration
    """
    The cable's radius and contact settings, which the pads share.
    """

    parameters: RigParameters
    """
    The rig's dimensions and gains.
    """

    def build(self, specification: mujoco.MjSpec) -> None:
        """
        :param specification: The scene's specification.
        """
        quaternion = self.frame.quaternion()
        support = specification.worldbody.add_body(
            name=RigName.SUPPORT, pos=self.frame.support_position, quat=quaternion
        )
        support.add_geom(
            name=RigName.SUPPORT,
            type=mujoco.mjtGeom.mjGEOM_BOX,
            size=self.frame.support_size / 2.0,
            friction=self.configuration.friction.to_json(),
            rgba=self.parameters.support_color,
        )
        specification.worldbody.add_geom(
            name=RigName.FLOOR,
            type=mujoco.mjtGeom.mjGEOM_PLANE,
            pos=(0.0, 0.0, self.parameters.mount_height - self.parameters.floor_depth),
            size=self.parameters.floor_half_size,
            rgba=self.parameters.floor_color,
        )
        carriage = specification.worldbody.add_body(
            name=RigName.CARRIAGE, pos=self.frame.origin, quat=quaternion
        )
        carriage.add_geom(
            type=mujoco.mjtGeom.mjGEOM_SPHERE,
            size=(self.parameters.carriage_radius, 0.0, 0.0),
            mass=self.parameters.carriage_mass,
            contype=NO_CONTACT,
            conaffinity=NO_CONTACT,
            rgba=INVISIBLE,
        )
        carriage.gravcomp = GRAVITY_COMPENSATED
        for axis, name in enumerate(CARRIAGE_ACTUATORS):
            carriage.add_joint(
                name=name, type=mujoco.mjtJoint.mjJNT_SLIDE, axis=np.eye(3)[axis]
            )
            self.add_servo(
                specification,
                name,
                self.parameters.carriage_stiffness,
                self.parameters.carriage_damping,
                self.parameters.carriage_force,
            )
        for sign, name in PADS:
            self.add_pad(specification, carriage, sign, name)

    def add_pad(
        self,
        specification: mujoco.MjSpec,
        carriage: mujoco.MjsBody,
        sign: float,
        name: str,
    ) -> None:
        """
        :param specification: The scene's specification.
        :param carriage: The carriage body.
        :param sign: Which side of the carriage the pad is on.
        :param name: The pad's name.
        """
        configuration = self.configuration
        distance = (
            configuration.radius
            + self.parameters.open_clearance
            + self.parameters.pad_half_size[1]
        )
        pad = carriage.add_body(name=name, pos=(0.0, sign * distance, 0.0))
        pad.gravcomp = GRAVITY_COMPENSATED
        pad.add_joint(
            name=name, type=mujoco.mjtJoint.mjJNT_SLIDE, axis=(0.0, -sign, 0.0)
        )
        pad.add_geom(
            name=name,
            type=mujoco.mjtGeom.mjGEOM_BOX,
            size=self.parameters.pad_half_size,
            mass=self.parameters.pad_mass,
            friction=configuration.friction.to_json(),
            condim=configuration.contact_dimension,
            solref=configuration.solver_reference.to_json(),
            solimp=configuration.solver_impedance.to_json(),
            rgba=self.parameters.pad_color,
        )
        self.add_servo(
            specification,
            name,
            self.parameters.pad_stiffness,
            self.parameters.pad_damping,
            self.parameters.pad_force,
        )

    @staticmethod
    def add_servo(
        specification: mujoco.MjSpec,
        name: str,
        stiffness: float,
        damping: float,
        maximum_force: float,
    ) -> None:
        """
        Add a force-limited position actuator on a joint of the same name.

        :param specification: The scene's specification.
        :param name: The joint's and the actuator's name.
        :param stiffness: The position gain.
        :param damping: The velocity gain.
        :param maximum_force: The largest force.
        """
        unused = [0.0] * (mujoco.mjNGAIN - 1)
        specification.add_actuator(
            name=name,
            target=name,
            trntype=mujoco.mjtTrn.mjTRN_JOINT,
            gaintype=mujoco.mjtGain.mjGAIN_FIXED,
            gainprm=(stiffness, *unused),
            biastype=mujoco.mjtBias.mjBIAS_AFFINE,
            biasprm=(0.0, -stiffness, -damping, *([0.0] * (mujoco.mjNBIAS - 3))),
            forcelimited=True,
            forcerange=(-maximum_force, maximum_force),
        )


CARRIAGE_ACTUATORS = tuple(f"{RigName.CARRIAGE}_{axis}" for axis in range(3))
"""
The carriage's joints and actuators along its x, y and z axes.
"""

PADS: Tuple[Tuple[float, RigName], ...] = (
    (1.0, RigName.LEFT_PAD),
    (-1.0, RigName.RIGHT_PAD),
)
"""
Each pad with the side of the carriage it is on.
"""


# %% simulation


@dataclass
class CablePhysics(CableSimulation):
    """
    A cable in its own CRAM world, with the rig, simulated in the background by CRAM's
    MuJoCo adapter.
    """

    configuration: CableConfiguration = field(default_factory=CableConfiguration)
    """
    The cable.
    """

    parameters: RigParameters = field(default_factory=RigParameters)
    """
    The rig.
    """

    world: World = field(init=False)
    """
    The world with the mount and the cable's semantic points.
    """

    cable: Cable = field(init=False)
    """
    The cable.
    """

    simulation: CableLabSimulation = field(init=False)
    """
    CRAM's adapter with its simulator and synchronizer.
    """

    frame: RigFrame = field(init=False)
    """
    Where the rig stands.
    """

    directory: TemporaryDirectory = field(init=False, repr=False)
    """
    The directory of the model file, removed when the simulation stops.
    """

    target: np.ndarray = field(init=False)
    """
    The gripper's target in the world.
    """

    pinching: bool = field(default=False, init=False)
    """
    Whether the pads are commanded closed.
    """

    stopped: bool = field(default=False, init=False)
    """
    Whether the simulation was stopped for good.
    """

    def __post_init__(self) -> None:
        self.world = World()
        root = Body(name=PrefixedName(RigName.WORLD))
        mount = Body(name=PrefixedName(RigName.MOUNT))
        with self.world.modify_world():
            self.world.add_kinematic_structure_entity(root)
        with self.world.modify_world():
            self.world.add_kinematic_structure_entity(mount)
            self.world.add_connection(
                FixedConnection(
                    parent=root,
                    child=mount,
                    parent_T_connection_expression=HomogeneousTransformationMatrix.from_xyz_rpy(
                        z=self.parameters.mount_height
                    ),
                )
            )
        self.cable = Cable(self.world, self.configuration, mount)
        self.frame = RigFrame.of_cable(self.cable, self.parameters)
        self.target = self.frame.origin.copy()
        self.directory = TemporaryDirectory(prefix=TEMPORARY_PREFIX)
        self.simulation = CableLabSimulation(
            self.world, Path(self.directory.name) / RigName.SCENE, self.parameters
        )
        simulator = self.simulation.simulator
        RigBuilder(self.frame, self.configuration, self.parameters).build(
            simulator._mj_spec
        )
        simulator._mj_model, simulator._mj_data = simulator._mj_spec.recompile(
            simulator._mj_model, simulator._mj_data
        )
        compiled = self.cable.install(
            simulator._mj_spec, simulator._mj_model, simulator._mj_data
        )
        simulator._mj_spec = compiled.specification
        simulator._mj_model = compiled.model
        simulator._mj_data = compiled.data
        simulator.pre_step_callback = self.prepare_step

    # %% access

    @property
    def model(self) -> mujoco.MjModel:
        """
        :return: The compiled scene.
        """
        return self.simulation.simulator._mj_model

    @property
    def data(self) -> mujoco.MjData:
        """
        :return: The scene's state.
        """
        return self.simulation.simulator._mj_data

    def body(self, name: str) -> int:
        """
        :param name: A body name.
        :return: The body's index.
        """
        return self.model.body(name).id

    # %% lifecycle

    def running(self) -> bool:
        simulator = self.simulation.simulator
        return (
            simulator.state == SimulatorState.RUNNING
            and simulator.simulation_thread is not None
            and simulator.simulation_thread.is_alive()
        )

    def start(self) -> None:
        if self.stopped:
            raise StoppedSimulation()
        if not self.running():
            self.simulation.start_simulation()

    def stop(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        self.simulation.simulator.stop()
        self.simulation.synchronizer.stop()
        self.directory.cleanup()

    def step(self, count: int) -> None:
        """
        Advance a simulation that does not run in the background, step by step.

        :param count: How many steps.
        :raises SteppingWhileRunning: When the background simulation runs.
        """
        if self.running():
            raise SteppingWhileRunning()
        with self.simulation.simulator._model_lock:
            for _ in range(count):
                self.prepare_step()
                mujoco.mj_step(self.model, self.data)
            mujoco.mj_forward(self.model, self.data)
            self.cable.follow(self.model, self.data)

    # %% commands

    def command(self, command: GripperCommand) -> None:
        with self.simulation.simulator._model_lock:
            action = command.action
            if action in (GripperAction.PINCH, GripperAction.RELEASE):
                self.pinching = action is GripperAction.PINCH
                return
            if action in LIFT_DIRECTIONS:
                self.target[2] = GRIPPER_WORKSPACE.clamped_height(
                    self.target[2]
                    + LIFT_DIRECTIONS[action] * self.parameters.lift_distance
                )
                return
            if not GRIPPER_WORKSPACE.contains(command.position):
                raise GripperTargetOutsideWorkspace()
            self.target = np.array(command.position.to_json())

    def prepare_step(self) -> None:
        """
        Move the actuators' targets towards the commanded ones, no faster than the
        carriage and pad speeds allow.
        """
        control = self.data.ctrl
        local = self.frame.rotation.T @ (self.target - self.frame.origin)
        carriage_step = self.parameters.carriage_speed * self.parameters.timestep
        for axis, name in enumerate(CARRIAGE_ACTUATORS):
            actuator = self.model.actuator(name).id
            control[actuator] += np.clip(
                local[axis] - control[actuator], -carriage_step, carriage_step
            )
        closed = self.parameters.open_clearance + self.configuration.radius
        pad_target = closed if self.pinching else 0.0
        pad_step = self.parameters.pad_speed * self.parameters.timestep
        for _, name in PADS:
            actuator = self.model.actuator(name).id
            control[actuator] += np.clip(
                pad_target - control[actuator], -pad_step, pad_step
            )

    # %% measurement

    def measure(self) -> CableLabState:
        with self.simulation.simulator._model_lock:
            # a reset keeps the joints but clears the bodies' poses until the next step
            mujoco.mj_kinematics(self.model, self.data)
            contacts = self.contacts()
            return CableLabState(
                lifecycle=SimulationLifecycle.IDLE,
                simulation_time=float(self.data.time),
                configuration=self.configuration,
                segments=self.segments(),
                points=[
                    CablePoint(
                        name=point.name.name,
                        position=Vector3(*self.point_position(point).tolist()),
                    )
                    for point in self.cable.points
                ],
                gripper=self.gripper(),
                contacts=contacts,
                anchor=AnchorObservation(
                    position=Vector3(
                        *self.point_position(self.cable.points[0]).tolist()
                    ),
                    enabled=self.configuration.anchored,
                ),
                grasp=self.grasp(contacts),
                warnings=self.warnings(),
                support=OrientedBox(
                    pose=Pose(
                        *self.frame.support_position.tolist(),
                        *Rotation.from_matrix(self.frame.rotation).as_quat().tolist(),
                    ),
                    size=Vector3(*self.frame.support_size.tolist()),
                ),
            )

    def point_position(self, point: Body) -> np.ndarray:
        """
        :param point: A semantic point.
        :return: Its position in the world.
        """
        return self.world.compute_forward_kinematics_np(self.world.root, point)[:3, 3]

    def segments(self) -> List[CableSegment]:
        """
        :return: Each capsule by the measured ends of its centre line.
        """
        segments = []
        for name in self.cable.body_names():
            geom = int(self.model.body_geomadr[self.body(name)])
            centre = self.data.geom_xpos[geom]
            direction = self.data.geom_xmat[geom].reshape(3, 3)[:, 2]
            half_length = self.model.geom_size[geom, 1]
            segments.append(
                CableSegment(
                    name=name,
                    start=Vector3(*(centre - half_length * direction).tolist()),
                    end=Vector3(*(centre + half_length * direction).tolist()),
                )
            )
        return segments

    def gripper(self) -> GripperObservation:
        """
        :return: The measured carriage and pads.
        """
        left, right = (self.body(name) for _, name in PADS)
        pad_width = 2.0 * self.parameters.pad_half_size[1]
        return GripperObservation(
            position=Vector3(*self.data.xpos[self.body(RigName.CARRIAGE)].tolist()),
            opening=float(
                np.linalg.norm(self.data.xpos[left] - self.data.xpos[right]) - pad_width
            ),
            pads=[
                OrientedBox(
                    pose=Pose(
                        *self.data.xpos[pad].tolist(),
                        *np.roll(self.data.xquat[pad], -1).tolist(),
                    ),
                    size=Vector3(
                        *(2.0 * np.array(self.parameters.pad_half_size)).tolist()
                    ),
                )
                for pad in (left, right)
            ],
        )

    def contacts(self) -> List[CableContact]:
        """
        :return: Every contact of a capsule with its measured forces.
        """
        capsules = {self.body(name) for name in self.cable.body_names()}
        contacts = []
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            first = int(self.model.geom_bodyid[contact.geom1])
            second = int(self.model.geom_bodyid[contact.geom2])
            if first not in capsules and second not in capsules:
                continue
            force = np.zeros(6)
            mujoco.mj_contactForce(self.model, self.data, index, force)
            contacts.append(
                CableContact(
                    position=Vector3(*contact.pos.tolist()),
                    normal_force=float(max(0.0, force[0])),
                    friction_force=float(np.linalg.norm(force[1:3])),
                    body_a=self.model.body(first).name,
                    body_b=self.model.body(second).name,
                )
            )
        return contacts

    def grasp(self, contacts: List[CableContact]) -> GraspObservation:
        """
        :param contacts: The cable's contacts.
        :return: What the pads' force-bearing contacts tell about the pinch.
        """
        pad_names = {name.value for _, name in PADS}
        pad_contacts = [
            contact
            for contact in contacts
            if {contact.body_a, contact.body_b} & pad_names and contact.normal_force > 0
        ]
        touching = {
            name
            for contact in pad_contacts
            for name in (contact.body_a, contact.body_b)
            if name in pad_names
        }
        return GraspObservation(
            state=self.grasp_state(pad_contacts, touching == pad_names),
            normal_force=sum(contact.normal_force for contact in pad_contacts),
            friction_force=sum(contact.friction_force for contact in pad_contacts),
            contact_count=len(pad_contacts),
        )

    def grasp_state(self, pad_contacts: List[CableContact], both: bool) -> GraspState:
        """
        :param pad_contacts: The pads' force-bearing contacts with the cable.
        :param both: Whether both pads touch the cable.
        :return: What the contacts tell about the pinch.
        """
        if not self.pinching:
            return GraspState.OPEN
        if not pad_contacts:
            return GraspState.SLIPPING
        if not both:
            return GraspState.CONTACT
        names = self.cable.body_names()
        middle = self.body(names[len(names) // 2])
        pad = self.body(PADS[0][1])
        relative_speed = np.linalg.norm(
            self.data.cvel[middle, 3:] - self.data.cvel[pad, 3:]
        )
        if relative_speed < self.parameters.holding_speed:
            return GraspState.HOLDING
        return GraspState.SLIPPING

    def warnings(self) -> List[str]:
        """
        :return: MuJoCo's numerical warnings since the start.
        """
        return [
            f"MuJoCo {mujoco.mjtWarning(index).name}: {int(count)} warning(s); the "
            f"solver may have reset the simulation."
            for index, count in enumerate(self.data.warning.number)
            if count
        ]
