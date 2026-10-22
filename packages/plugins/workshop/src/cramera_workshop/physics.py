"""
The workshop's contact world: loose bodies under gravity, friction and contacts, a
force-limited spring that holds one body, force-limited drawer motors, and an ideal
thread that turns measured screwdriver rotation into screw travel.

The thread is an idealization: it relates tool rotation to insertion and puts the
reaction on the workpiece, but simulates no wood cutting, damage, tightening torque or
thread-flank contact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from typing_extensions import Dict, List, Mapping, Optional, Tuple

from cramera_protocol.geometry import Pose, Vector3
from cramera_protocol.workshop import (
    DriveDirection,
    MeasuredContact,
    ThreadObservation,
    ThreadState,
    WorkshopState,
)
from cramera_workshop.bundle import WorkshopBundle
from cramera_workshop.collision_model import CollisionModel, ContactSettings
from cramera_workshop.exceptions import (
    DrawerTargetOutOfRange,
    DriverNotEngaged,
    InvalidStepDuration,
    NothingHeld,
    TargetOutsideWorkspace,
    UnknownDrawer,
    UnknownWorkshopBody,
    WorkshopSimulationFailure,
)
from cramera_workshop.session import WorkshopDynamics

DRIVE_SIGNS: Mapping[DriveDirection, int] = {
    DriveDirection.FORWARD: 1,
    DriveDirection.REVERSE: -1,
    DriveDirection.STOP: 0,
}
"""
The sign of the driver's rotation about its driving axis for each direction.
"""

SHAFT_AXIS = np.array([0.0, 0.0, 1.0])
"""
The local axis along which screws, the pilot hole and the driver's shaft point.
"""

SMALLEST_NORM = 1e-12
"""
The length below which a force or torque counts as zero when it is limited.
"""

TIME_ROUNDING = 1e-12
"""
How much of a timestep a requested duration may fall short and still take the step.
"""

INVALID_STATE_WARNINGS = (
    mujoco.mjtWarning.mjWARN_BADQPOS,
    mujoco.mjtWarning.mjWARN_BADQVEL,
    mujoco.mjtWarning.mjWARN_BADQACC,
)
"""
The MuJoCo warnings that mean the solver reset an invalid state.
"""

# %% parameters


@dataclass(frozen=True)
class PhysicsParameters:
    """
    The force limits, gains and tolerances of the contact world.
    """

    contact: ContactSettings = field(default_factory=ContactSettings)
    """
    The solver and contact settings, timestep included.
    """

    spring: float = 350.0
    """
    The holding spring's translational stiffness, in newtons per metre.
    """

    maximum_force: float = 35.0
    """
    The holding spring's largest force, in newtons.
    """

    angular_spring: float = 2.5
    """
    The holding spring's rotational stiffness, in newton metres per radian.
    """

    maximum_torque: float = 1.2
    """
    The holding spring's largest torque, in newton metres.
    """

    drawer_spring: float = 800.0
    """
    The drawer motors' stiffness, in newtons per metre.
    """

    drawer_damping: float = 60.0
    """
    The drawer motors' damping, in newton seconds per metre.
    """

    drawer_force: float = 15.0
    """
    The drawer motors' largest force, in newtons; an obstruction can stop a drawer.
    """

    thread_spring: float = 2000.0
    """
    The thread's translational stiffness, in newtons per metre.
    """

    thread_force: float = 20.0
    """
    The thread's largest reaction force, in newtons.
    """

    thread_angular_spring: float = 20.0
    """
    The thread's rotational stiffness about the pilot axis, in newton metres per radian.
    """

    thread_torque: float = 1.2
    """
    The thread's largest reaction torque, in newton metres.
    """

    driver_speed: float = 2.0 * math.pi
    """
    The driver's commanded angular speed, in radians per second.
    """

    maximum_contacts: int = 64
    """
    The most contacts a state reports, the strongest first.
    """

    smallest_contact_force: float = 1e-8
    """
    The normal force below which a contact is not reported, in newtons.
    """

    blade_preload: float = 0.001
    """
    How far below the slot floor the driver's target puts the blade, in metres; the
    contact resolves it into a preload.
    """

    contact_gap: float = 0.08
    """
    How long an engaged blade may lose contact while turning, in seconds.
    """

    driver_distance: float = 0.006
    """
    How far the blade may be from its slot target while engaged, in metres.
    """

    driver_angle: float = 0.15
    """
    How far the driver's shaft may tilt from the screw's while engaged, in radians.
    """

    pilot_distance: float = 0.002
    """
    How far a screw's tip may be off the pilot axis when the thread captures it, in
    metres.
    """

    pilot_angle: float = 0.08
    """
    How far a screw's shaft may tilt from the pilot axis when the thread captures it, in
    radians.
    """

    pilot_clearance: float = 0.0002
    """
    How far above the pilot entrance a screw is put to be captured, in metres.
    """

    contact_margin: float = 0.0005
    """
    The largest separation of blade and screw that counts as touching, in metres.
    """

    pilot_capture_depth: float = 0.004
    """
    The deepest a screw tip may be when the thread first captures it, in metres.
    """

    pilot_capture_height: float = 0.0005
    """
    The highest above the entrance a screw tip may be when captured, in metres.
    """

    pilot_release_distance: float = 0.003
    """
    How far off the pilot axis a held screw is pulled to leave the thread, in metres.
    """

    pilot_release_height: float = 0.006
    """
    How far along the pilot axis a held screw is pulled to leave the thread, in metres.
    """

    longest_step: float = 30.0
    """
    The longest duration one call advances, in seconds.
    """

    workspace_half_width: float = 2.1
    """
    How far from the origin a spring target may be along x and y, in metres.
    """

    lowest_target: float = 0.05
    """
    The lowest height of a spring target, in metres.
    """

    highest_target: float = 2.5
    """
    The highest height of a spring target, in metres.
    """


# %% measured bodies


@dataclass(frozen=True)
class Wrench:
    """
    A force and a torque about a body's centre of mass, in the world frame.
    """

    force: np.ndarray
    """
    The force, in newtons.
    """

    torque: np.ndarray
    """
    The torque, in newton metres.
    """


@dataclass(frozen=True)
class LimitedVector:
    """
    A force or torque scaled down to a largest magnitude.
    """

    vector: np.ndarray
    """
    The requested vector.
    """

    maximum: float
    """
    The largest magnitude.
    """

    def value(self) -> np.ndarray:
        """
        :return: The vector, scaled down if longer than :attr:`maximum`.
        """
        length = max(float(np.linalg.norm(self.vector)), SMALLEST_NORM)
        return self.vector * min(1.0, self.maximum / length)


@dataclass
class ContactWorld:
    """
    The compiled MuJoCo model and its state, read and pushed by object key.
    """

    model: mujoco.MjModel
    """
    The compiled model.
    """

    data: mujoco.MjData
    """
    Its state.
    """

    def body(self, key: str) -> int:
        """
        :param key: A body name.
        :return: The body's index.
        """
        return self.model.body(key).id

    def pose(self, key: str) -> np.ndarray:
        """
        :param key: A body name.
        :return: The body's measured pose, position then quaternion with the scalar
            last.
        """
        body = self.body(key)
        return np.concatenate(
            (self.data.xpos[body], np.roll(self.data.xquat[body], -1))
        )

    def rotation(self, key: str) -> Rotation:
        """
        :param key: A body name.
        :return: The body's measured orientation.
        """
        return Rotation.from_quat(self.pose(key)[3:])

    def velocity(self, key: str) -> np.ndarray:
        """
        :param key: A body name.
        :return: The body's angular then linear velocity at its centre of mass, in the
            world frame.
        """
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(
            self.model,
            self.data,
            mujoco.mjtObj.mjOBJ_BODY,
            self.body(key),
            velocity,
            0,
        )
        return velocity

    def mass(self, key: str) -> float:
        """
        :param key: A body name.
        :return: The body's mass, in kilograms.
        """
        return float(self.model.body_mass[self.body(key)])

    def largest_inertia(self, key: str) -> float:
        """
        :param key: A body name.
        :return: The body's largest principal moment of inertia.
        """
        return float(max(self.model.body_inertia[self.body(key)]))

    def centre_of_mass(self, key: str) -> np.ndarray:
        """
        :param key: A body name.
        :return: The body's centre of mass in the world.
        """
        return self.data.xipos[self.body(key)].copy()

    def push(self, key: str, wrench: Wrench) -> None:
        """
        Add a wrench to what acts on a body during the next step.

        :param key: A body name.
        :param wrench: The force and the torque about the body's centre of mass.
        """
        body = self.body(key)
        self.data.xfrc_applied[body, :3] += wrench.force
        self.data.xfrc_applied[body, 3:] += wrench.torque

    def touching(self, first: str, second: str, margin: float) -> bool:
        """
        :param first: A body name.
        :param second: Another body name.
        :param margin: The largest separation that counts as touching, in metres.
        :return: Whether a contact of the two bodies is within the margin.
        """
        pair = {self.body(first), self.body(second)}
        return any(
            {
                int(self.model.geom_bodyid[contact.geom1]),
                int(self.model.geom_bodyid[contact.geom2]),
            }
            == pair
            and contact.dist < margin
            for contact in self.data.contact[: self.data.ncon]
        )

    def contacts(self, smallest_force: float, maximum: int) -> List[MeasuredContact]:
        """
        :param smallest_force: The normal force below which a contact is left out.
        :param maximum: The most contacts to report.
        :return: The contacts with their measured normal forces, the strongest first;
            each body named by the body it is welded to.
        """
        measured = []
        for index, contact in enumerate(self.data.contact[: self.data.ncon]):
            force = np.zeros(6)
            mujoco.mj_contactForce(self.model, self.data, index, force)
            if force[0] <= smallest_force:
                continue
            measured.append(
                MeasuredContact(
                    body_a=self.welded_body(contact.geom1),
                    body_b=self.welded_body(contact.geom2),
                    position=Vector3(*contact.pos.tolist()),
                    normal=Vector3(*contact.frame[:3].tolist()),
                    force=float(force[0]),
                    distance=float(contact.dist),
                )
            )
        measured.sort(key=lambda contact: contact.force, reverse=True)
        return measured[:maximum]

    def welded_body(self, geom: int) -> str:
        """
        :param geom: A geom's index.
        :return: The name of the body its body is rigidly attached to.
        """
        return self.model.body(
            int(self.model.body_weldid[self.model.geom_bodyid[geom]])
        ).name

    def is_finite(self) -> bool:
        """
        :return: Whether positions, velocities and time are finite.
        """
        return bool(
            np.isfinite(self.data.qpos).all()
            and np.isfinite(self.data.qvel).all()
            and math.isfinite(self.data.time)
        )

    def solver_reset_state(self) -> bool:
        """
        :return: Whether MuJoCo reported resetting an invalid state.
        """
        return any(
            self.data.warning[warning].number for warning in INVALID_STATE_WARNINGS
        )


# %% holding spring


@dataclass
class SpringGrasp:
    """
    A damped, force-limited spring between one body and a target pose, with gravity
    compensation; the body still meets every contact on its way.
    """

    world: ContactWorld
    """
    The contact world.
    """

    parameters: PhysicsParameters
    """
    The spring's gains and limits.
    """

    held: Optional[str] = None
    """
    The held body's name, or None.
    """

    target: Optional[np.ndarray] = None
    """
    The held body's target pose, position then quaternion with the scalar last.
    """

    def hold(self, key: str) -> None:
        """
        :param key: The body to hold, at its measured pose.
        """
        self.held = key
        self.target = self.world.pose(key)

    def release(self) -> None:
        """
        Let go of the held body.
        """
        self.held = None
        self.target = None

    def apply(self) -> None:
        """
        Push the held body towards its target for the next step.
        """
        if self.held is None:
            return
        key = self.held
        measured = self.world.pose(key)
        velocity = self.world.velocity(key)
        mass = self.world.mass(key)
        damping = 2.0 * math.sqrt(mass * self.parameters.spring)
        origin_offset = measured[:3] - self.world.centre_of_mass(key)
        origin_velocity = velocity[3:] + np.cross(velocity[:3], origin_offset)
        origin_force = (
            self.parameters.spring * (self.target[:3] - measured[:3])
            - damping * origin_velocity
        )
        requested = origin_force - mass * self.world.model.opt.gravity
        force = LimitedVector(requested, self.parameters.maximum_force).value()
        requested_norm = float(np.linalg.norm(requested))
        scale = float(np.linalg.norm(force)) / requested_norm if requested_norm else 1.0
        error = (
            Rotation.from_quat(self.target[3:]) * self.world.rotation(key).inv()
        ).as_rotvec()
        angular_damping = 2.0 * math.sqrt(
            self.world.largest_inertia(key) * self.parameters.angular_spring
        )
        torque = LimitedVector(
            self.parameters.angular_spring * error - angular_damping * velocity[:3],
            self.parameters.maximum_torque,
        ).value()
        self.world.push(
            key,
            Wrench(
                force=force,
                torque=torque + np.cross(origin_offset, scale * origin_force),
            ),
        )


# %% ideal thread


@dataclass(frozen=True)
class ThreadGeometry:
    """
    The dimensions and frames of the screw driving, from the workshop description.
    """

    assembly: str
    """
    The workpiece's object key.
    """

    driver: str
    """
    The screwdriver's object key.
    """

    mouth: np.ndarray
    """
    The pilot hole's entrance in the workpiece's frame.
    """

    maximum_depth: float
    """
    How deep a screw tip goes before the head seats, in metres.
    """

    slot_floor: float
    """
    The slot floor's height above a screw's tip, in metres.
    """

    bit_tip: np.ndarray
    """
    The blade's tip in the driver's frame.
    """

    drive_axis: np.ndarray
    """
    The direction that drives a screw in, in the aligned driver's frame.
    """

    pitch: float
    """
    The thread's advance per turn, in metres.
    """

    screws: Tuple[str, ...]
    """
    The object keys of the screws.
    """

    @classmethod
    def of_bundle(cls, bundle: WorkshopBundle) -> ThreadGeometry:
        """
        :param bundle: A workshop bundle.
        :return: The geometry its workshop description gives.
        """
        workshop = bundle.workshop
        screw = workshop.screw
        return cls(
            assembly=workshop.assembly.key,
            driver=workshop.driver.key,
            mouth=np.array(workshop.assembly.local_mouth.to_json()),
            maximum_depth=workshop.assembly.maximum_depth,
            slot_floor=screw.head_top - screw.slot_size.z,
            bit_tip=np.array(workshop.driver.bit_tip.to_json()),
            drive_axis=np.array(workshop.driver.axis.to_json()),
            pitch=screw.thread_pitch,
            screws=tuple(workshop.screws()),
        )

    def turn_limit(self) -> float:
        """
        :return: The turns from capture to the seated head.
        """
        return self.maximum_depth / self.pitch


@dataclass
class IdealThread:
    """
    The pilot hole's thread: it captures a screw put at its entrance, holds it on the
    pilot axis with equal and opposite reactions on screw and workpiece, and advances it
    by the pitch per measured turn of an engaged driver.
    """

    world: ContactWorld
    """
    The contact world.
    """

    grasp: SpringGrasp
    """
    The spring holding the driver, whose target the thread guides.
    """

    geometry: ThreadGeometry
    """
    The thread's dimensions.
    """

    parameters: PhysicsParameters
    """
    The thread's gains and tolerances.
    """

    seated_screw: Optional[str] = None
    """
    The captured screw, or None.
    """

    turns: float = 0.0
    """
    The measured driver turns since the capture.
    """

    direction: int = 0
    """
    The commanded rotation's sign about the driving axis; 0 holds the driver still.
    """

    phase: ThreadState = ThreadState.FREE
    """
    The thread's phase.
    """

    previous_driver_rotation: Optional[Rotation] = None
    """
    The driver's orientation relative to the workpiece at the previous step.
    """

    initial_screw_rotation: Optional[Rotation] = None
    """
    The captured screw's roll about the pilot axis relative to the workpiece.
    """

    contact_gap_time: float = 0.0
    """
    How long the engaged blade has been out of contact, in seconds.
    """

    guided_driver: bool = False
    """
    Whether the driver's target is kept on the slot so the blade stays engaged.
    """

    def release_driver(self) -> None:
        """
        Stop turning and stop guiding the driver, as when its spring target changes.
        """
        self.direction = 0
        self.guided_driver = False

    def free(self) -> None:
        """
        Let the captured screw go.
        """
        self.seated_screw = None
        self.turns = 0.0
        self.phase = ThreadState.FREE

    # %% measured frames

    def socket(self) -> Tuple[np.ndarray, Rotation]:
        """
        :return: The measured pilot entrance and the workpiece's orientation, whose z
            axis points out of the hole.
        """
        pose = self.world.pose(self.geometry.assembly)
        rotation = Rotation.from_quat(pose[3:])
        return pose[:3] + rotation.apply(self.geometry.mouth), rotation

    def driver_goal(self, screw: str) -> np.ndarray:
        """
        :param screw: A screw's object key.
        :return: The driver pose that puts the blade in the screw's slot, preloaded.
        """
        pose = self.world.pose(screw)
        rotation = Rotation.from_quat(pose[3:])
        depth = self.geometry.slot_floor - self.parameters.blade_preload
        return np.concatenate(
            (
                pose[:3] + rotation.apply(depth * SHAFT_AXIS - self.geometry.bit_tip),
                pose[3:],
            )
        )

    def driver_within_slot(self) -> bool:
        """
        :return: Whether the measured blade is near its slot target and the shafts are
            aligned.
        """
        if self.seated_screw is None:
            return False
        goal = self.driver_goal(self.seated_screw)
        driver = self.world.pose(self.geometry.driver)
        tilt = (
            Rotation.from_quat(goal[3:]).inv() * Rotation.from_quat(driver[3:])
        ).as_rotvec()
        return bool(
            np.linalg.norm(driver[:3] - goal[:3]) < self.parameters.driver_distance
            and np.linalg.norm(tilt[:2]) < self.parameters.driver_angle
        )

    def driver_aligned(self) -> bool:
        """
        :return: Whether the blade is within the slot and touches the screw.
        """
        return self.driver_within_slot() and self.world.touching(
            self.geometry.driver, self.seated_screw, self.parameters.contact_margin
        )

    def driver_engaged(self) -> bool:
        """
        :return: Whether the blade is aligned, or was guided and lost contact only
            briefly while staying within the slot.
        """
        return self.driver_aligned() or (
            self.guided_driver
            and self.contact_gap_time <= self.parameters.contact_gap
            and self.driver_within_slot()
        )

    # %% commands

    def drive(self, direction: DriveDirection) -> None:
        """
        Turn the held driver, or hold it still on its slot.

        :param direction: Which way to turn.
        :raises DriverNotEngaged: When turning while the held driver's blade is not
            engaged in a seated screw.
        """
        sign = DRIVE_SIGNS[direction]
        if sign == 0:
            self.stop_driver()
            return
        if self.grasp.held != self.geometry.driver or not self.driver_engaged():
            raise DriverNotEngaged()
        if self.parameters.maximum_torque <= 0:
            self.stop_driver()
            self.phase = ThreadState.STOPPED
            return
        self.direction = sign
        self.guided_driver = True
        self.contact_gap_time = 0.0
        self.previous_driver_rotation = self.socket()[1].inv() * self.world.rotation(
            self.geometry.driver
        )

    def stop_driver(self) -> None:
        """
        Stop turning and hold the driver where it is, on the slot when it is near.
        """
        self.direction = 0
        if self.grasp.held != self.geometry.driver:
            return
        self.grasp.target = self.world.pose(self.geometry.driver)
        if self.seated_screw is None:
            return
        goal = self.driver_goal(self.seated_screw)
        if (
            np.linalg.norm(self.grasp.target[:3] - goal[:3])
            < self.parameters.driver_distance
        ):
            self.grasp.target[:3] = goal[:3]

    # %% stepping

    def update(self) -> None:
        """
        Capture a screw at the entrance, follow the driver's measured rotation and apply
        the thread's reactions for the next step.
        """
        mouth, world_R_assembly = self.socket()
        axis = world_R_assembly.apply(SHAFT_AXIS)
        if self.seated_screw is None:
            self.capture(mouth, world_R_assembly, axis)
        if self.seated_screw is None:
            return
        if self.grasp.held == self.seated_screw:
            self.release_when_pulled(mouth, world_R_assembly)
            return
        self.follow_driver(world_R_assembly)
        depth = self.turns * self.geometry.pitch
        target = np.concatenate(
            (
                mouth - depth * axis,
                (
                    world_R_assembly
                    * Rotation.from_rotvec(-2 * math.pi * self.turns * SHAFT_AXIS)
                    * self.initial_screw_rotation
                ).as_quat(),
            )
        )
        self.apply_constraint(target)

    def capture(
        self, mouth: np.ndarray, world_R_assembly: Rotation, axis: np.ndarray
    ) -> None:
        """
        Capture the first screw whose tip is at the entrance and whose shaft is aligned.

        :param mouth: The measured pilot entrance.
        :param world_R_assembly: The workpiece's orientation.
        :param axis: The pilot axis, out of the hole.
        """
        for key in self.geometry.screws:
            screw = self.world.pose(key)
            relative = world_R_assembly.inv().apply(screw[:3] - mouth)
            shaft = Rotation.from_quat(screw[3:]).apply(SHAFT_AXIS)
            if (
                np.linalg.norm(relative[:2]) < self.parameters.pilot_distance
                and -self.parameters.pilot_capture_depth
                < relative[2]
                <= self.parameters.pilot_capture_height
                and np.dot(shaft, axis) > math.cos(self.parameters.pilot_angle)
            ):
                self.seated_screw = key
                self.turns = 0.0
                relative_rotation = (
                    world_R_assembly.inv() * Rotation.from_quat(screw[3:])
                ).as_quat()
                self.initial_screw_rotation = Rotation.from_quat(
                    [0, 0, relative_rotation[2], relative_rotation[3]]
                )
                self.phase = ThreadState.SEATED
                return

    def release_when_pulled(
        self, mouth: np.ndarray, world_R_assembly: Rotation
    ) -> None:
        """
        Let a held screw go once it is pulled away from the entrance.

        :param mouth: The measured pilot entrance.
        :param world_R_assembly: The workpiece's orientation.
        """
        relative = world_R_assembly.inv().apply(
            self.world.pose(self.seated_screw)[:3] - mouth
        )
        if (
            np.linalg.norm(relative[:2]) > self.parameters.pilot_release_distance
            or abs(relative[2]) > self.parameters.pilot_release_height
        ):
            self.seated_screw = None
            self.phase = ThreadState.FREE

    def follow_driver(self, world_R_assembly: Rotation) -> None:
        """
        Keep the guided driver on its slot and add its measured rotation to the turns.

        :param world_R_assembly: The workpiece's orientation.
        """
        engaged = self.driver_aligned()
        self.contact_gap_time = (
            0.0 if engaged else self.contact_gap_time + self.parameters.contact.timestep
        )
        goal = self.driver_goal(self.seated_screw)
        if (
            engaged
            and self.grasp.held == self.geometry.driver
            and np.linalg.norm(self.grasp.target[:3] - goal[:3])
            < self.parameters.driver_distance
        ):
            self.guided_driver = True
        if self.guided_driver and (
            not self.driver_within_slot()
            or self.contact_gap_time > self.parameters.contact_gap
        ):
            self.release_driver()
        actual_rotation = world_R_assembly.inv() * self.world.rotation(
            self.geometry.driver
        )
        if self.guided_driver and self.grasp.held == self.geometry.driver:
            self.grasp.target[:3] = goal[:3]
        if self.direction and self.previous_driver_rotation is not None:
            self.turn(world_R_assembly, actual_rotation, goal)
        elif self.turns and self.phase is not ThreadState.LIMIT:
            self.phase = ThreadState.STOPPED
        self.previous_driver_rotation = actual_rotation

    def turn(
        self, world_R_assembly: Rotation, actual_rotation: Rotation, goal: np.ndarray
    ) -> None:
        """
        Count the driver's measured rotation since the previous step and turn its target
        on; stop at either end of the thread.

        :param world_R_assembly: The workpiece's orientation.
        :param actual_rotation: The driver's orientation relative to the workpiece.
        :param goal: The driver's slot target.
        """
        delta = (actual_rotation * self.previous_driver_rotation.inv()).as_rotvec()
        self.turns = float(
            np.clip(
                self.turns + np.dot(delta, self.geometry.drive_axis) / (2 * math.pi),
                0.0,
                self.geometry.turn_limit(),
            )
        )
        increment = Rotation.from_rotvec(
            world_R_assembly.apply(self.geometry.drive_axis)
            * self.direction
            * self.parameters.driver_speed
            * self.parameters.contact.timestep
        )
        self.grasp.target[3:] = (
            increment * Rotation.from_quat(self.grasp.target[3:])
        ).as_quat()
        self.grasp.target[:3] = goal[:3]
        self.phase = ThreadState.DRIVING
        reached_bottom = self.direction > 0 and self.turns >= self.geometry.turn_limit()
        reached_top = self.direction < 0 and self.turns <= 0
        if reached_bottom or reached_top:
            self.direction = 0
            self.grasp.target[3:] = self.world.pose(self.geometry.driver)[3:]
            self.phase = ThreadState.LIMIT

    def apply_constraint(self, target: np.ndarray) -> None:
        """
        Push the screw towards its thread pose and the workpiece by the opposite
        reaction, so the pair's total force and moment stay zero.

        :param target: The screw's thread pose, position then quaternion, scalar last.
        """
        screw_key = self.seated_screw
        assembly_key = self.geometry.assembly
        screw = self.world.pose(screw_key)
        screw_velocity = self.world.velocity(screw_key)
        assembly_velocity = self.world.velocity(assembly_key)
        assembly_point_velocity = assembly_velocity[3:] + np.cross(
            assembly_velocity[:3],
            screw[:3] - self.world.centre_of_mass(assembly_key),
        )
        damping = 2.0 * math.sqrt(
            self.world.mass(screw_key) * self.parameters.thread_spring
        )
        force = self.parameters.thread_spring * (target[:3] - screw[:3]) - damping * (
            screw_velocity[3:] - assembly_point_velocity
        )
        error = (
            Rotation.from_quat(target[3:]) * Rotation.from_quat(screw[3:]).inv()
        ).as_rotvec()
        angular_damping = 2.0 * math.sqrt(
            self.world.largest_inertia(screw_key)
            * self.parameters.thread_angular_spring
        )
        torque = self.parameters.thread_angular_spring * error - angular_damping * (
            screw_velocity[:3] - assembly_velocity[:3]
        )
        force = LimitedVector(force, self.parameters.thread_force).value()
        torque = LimitedVector(torque, self.parameters.thread_torque).value()
        for key, sign in ((screw_key, 1.0), (assembly_key, -1.0)):
            lever = screw[:3] - self.world.centre_of_mass(key)
            self.world.push(
                key,
                Wrench(
                    force=sign * force,
                    torque=sign * (torque + np.cross(lever, force)),
                ),
            )

    # %% observation

    def observation(self) -> ThreadObservation:
        """
        :return: The thread's measured state.
        """
        mouth, rotation = self.socket()
        held_screw = (
            self.grasp.held if self.grasp.held in self.geometry.screws else None
        )
        screw = self.seated_screw or held_screw or self.geometry.screws[0]
        depth = (
            0.0
            if self.seated_screw is None
            else float(
                np.dot(
                    mouth - self.world.pose(self.seated_screw)[:3],
                    rotation.apply(SHAFT_AXIS),
                )
            )
        )
        quaternion = rotation.as_quat().tolist()
        return ThreadObservation(
            engaged=self.driver_engaged(),
            screw=screw,
            driver=self.geometry.driver,
            depth=depth,
            turns=self.turns,
            pitch=self.geometry.pitch,
            state=self.phase,
            driver_target_pose=Pose(*self.driver_goal(screw).tolist()),
            socket_pose=Pose(*mouth.tolist(), *quaternion),
            screw_target_pose=Pose(
                *(
                    mouth + rotation.apply(self.parameters.pilot_clearance * SHAFT_AXIS)
                ).tolist(),
                *quaternion,
            ),
        )


# %% workshop physics


@dataclass
class WorkshopPhysics(WorkshopDynamics):
    """
    The workshop's contact world with its holding spring, drawer motors and thread.
    """

    bundle: WorkshopBundle
    """
    The workshop bundle the world is built from.
    """

    parameters: PhysicsParameters = field(default_factory=PhysicsParameters)
    """
    The force limits, gains and tolerances.
    """

    world: ContactWorld = field(init=False)
    """
    The compiled model and its state.
    """

    objects: Tuple[str, ...] = field(init=False)
    """
    The object keys of the loose bodies.
    """

    drawers: Dict[str, float] = field(init=False)
    """
    Each drawer joint's motor target, in metres.
    """

    grasp: SpringGrasp = field(init=False)
    """
    The holding spring.
    """

    thread: IdealThread = field(init=False)
    """
    The pilot hole's thread.
    """

    elapsed_remainder: float = field(default=0.0, init=False)
    """
    Requested time shorter than a timestep, carried into the next call.
    """

    def __post_init__(self) -> None:
        model = CollisionModel(self.bundle, self.parameters.contact).compile()
        self.world = ContactWorld(model=model, data=mujoco.MjData(model))
        self.objects = tuple(item.key for item in self.bundle.movable_objects())
        self.drawers = {drawer.joint: 0.0 for drawer in self.bundle.workshop.drawers}
        self.grasp = SpringGrasp(self.world, self.parameters)
        self.thread = IdealThread(
            self.world,
            self.grasp,
            ThreadGeometry.of_bundle(self.bundle),
            self.parameters,
        )
        self.reset()

    def reset(self) -> None:
        mujoco.mj_resetData(self.world.model, self.world.data)
        self.grasp.release()
        self.thread = IdealThread(
            self.world, self.grasp, self.thread.geometry, self.parameters
        )
        self.elapsed_remainder = 0.0
        self.drawers = dict.fromkeys(self.drawers, 0.0)
        mujoco.mj_forward(self.world.model, self.world.data)

    def pose(self, key: str) -> np.ndarray:
        """
        :param key: A body name.
        :return: The body's measured pose, position then quaternion with the scalar
            last.
        """
        return self.world.pose(key)

    # %% commands

    def held(self) -> Optional[str]:
        return self.grasp.held

    def grab(self, key: str) -> None:
        if key not in self.objects:
            raise UnknownWorkshopBody(key)
        self.thread.release_driver()
        self.grasp.hold(key)
        if key == self.thread.seated_screw:
            self.thread.free()

    def move(self, key: str, pose: Pose) -> None:
        if self.grasp.held is None or self.grasp.held != key:
            raise NothingHeld(key)
        value = np.array(pose.to_json())
        if (
            np.any(np.abs(value[:2]) > self.parameters.workspace_half_width)
            or not self.parameters.lowest_target
            <= value[2]
            <= self.parameters.highest_target
        ):
            raise TargetOutsideWorkspace()
        value[3:] /= np.linalg.norm(value[3:])
        self.grasp.target = value
        self.thread.release_driver()

    def release(self) -> None:
        self.grasp.release()
        self.thread.release_driver()

    def set_drawer(self, joint: str, position: float) -> None:
        if joint not in self.drawers:
            raise UnknownDrawer(joint)
        lower, upper = self.world.model.jnt_range[self.world.model.joint(joint).id]
        if not lower <= position <= upper:
            raise DrawerTargetOutOfRange(joint, position, float(lower), float(upper))
        self.drawers[joint] = position

    def drive(self, direction: DriveDirection) -> None:
        self.thread.drive(direction)

    # %% stepping

    def step(self, duration: float) -> None:
        if (
            not math.isfinite(duration)
            or not 0 <= duration <= self.parameters.longest_step
        ):
            raise InvalidStepDuration(duration)
        timestep = self.parameters.contact.timestep
        self.elapsed_remainder += duration
        steps = int((self.elapsed_remainder + TIME_ROUNDING) / timestep)
        self.elapsed_remainder -= steps * timestep
        for _ in range(steps):
            self.advance_once()
        mujoco.mj_forward(self.world.model, self.world.data)

    def advance_once(self) -> None:
        """
        Apply the spring, the motors and the thread, and take one solver step.

        :raises WorkshopSimulationFailure: When the state is or becomes invalid.
        """
        data = self.world.data
        if not self.world.is_finite():
            raise WorkshopSimulationFailure()
        data.xfrc_applied[:] = 0
        data.qfrc_applied[:] = 0
        self.thread.update()
        self.grasp.apply()
        for joint, target in self.drawers.items():
            self.apply_drawer_motor(joint, target)
        previous_time = float(data.time)
        mujoco.mj_step(self.world.model, data)
        if (
            self.world.solver_reset_state()
            or data.time <= previous_time
            or not self.world.is_finite()
        ):
            raise WorkshopSimulationFailure()

    def apply_drawer_motor(self, joint: str, target: float) -> None:
        """
        :param joint: A drawer joint.
        :param target: Its motor's target, in metres.
        """
        description = self.world.model.joint(joint)
        position = self.world.data.qpos[description.qposadr[0]]
        velocity = self.world.data.qvel[description.dofadr[0]]
        force = (
            self.parameters.drawer_spring * (target - position)
            - self.parameters.drawer_damping * velocity
        )
        self.world.data.qfrc_applied[description.dofadr[0]] = np.clip(
            force, -self.parameters.drawer_force, self.parameters.drawer_force
        )

    # %% observation

    def state(self) -> WorkshopState:
        if not self.world.is_finite():
            raise WorkshopSimulationFailure()
        return WorkshopState(
            objects={key: Pose(*self.world.pose(key).tolist()) for key in self.objects},
            joints={
                joint: float(
                    self.world.data.qpos[self.world.model.joint(joint).qposadr[0]]
                )
                for joint in self.drawers
            },
            held=self.grasp.held,
            target=(
                None if self.grasp.target is None else Pose(*self.grasp.target.tolist())
            ),
            contacts=self.world.contacts(
                self.parameters.smallest_contact_force,
                self.parameters.maximum_contacts,
            ),
            time=float(self.world.data.time),
            thread=self.thread.observation(),
        )
