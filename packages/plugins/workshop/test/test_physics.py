"""
The workshop's contact world: loose bodies under gravity and contacts, the holding
spring, the drawer motors, the ideal thread and the solver's failures, measured in
MuJoCo.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import replace

import mujoco
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from typing_extensions import Iterator, List

from cramera_protocol.geometry import Pose
from cramera_protocol.workshop import (
    DriveDirection,
    ThreadState,
    WorkshopAction,
    WorkshopCommand,
)
from cramera_workshop.collision_model import FREE_JOINT_SUFFIX
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
from cramera_workshop.physics import WorkshopPhysics
from cramera_workshop.session import WorkshopSession

SCREW = "screw_1"
"""
The screw the thread tests drive.
"""

SCREW_BOX = "screw_box"
"""
The box of screws.
"""

NAIL_BOX = "nail_box"
"""
The box of nails.
"""

DRIVER = "driver"
"""
The screwdriver.
"""

ASSEMBLY = "workshop_assembly"
"""
The workpiece with the pilot hole.
"""

UPPER_DRAWER = "workshop_drawer_3_joint"
"""
The upper drawer's joint.
"""

# %% fixtures


@pytest.fixture
def physics(bundle) -> WorkshopPhysics:
    """
    :return: The workshop's contact world, at rest where its bodies spawn.
    """
    return WorkshopPhysics(bundle)


@pytest.fixture
def session(physics) -> Iterator[WorkshopSession]:
    """
    :return: A running session over the contact world, whose time the test lets pass
        by itself while it holds the session's lock.
    """
    session = WorkshopSession(factory=lambda: physics)
    with session.lock:
        session.command(WorkshopCommand(action=WorkshopAction.START))
        yield session
    session.close()


def pose_list(physics: WorkshopPhysics, key: str) -> List[float]:
    return physics.state().objects[key].to_json()


def relative_position(physics: WorkshopPhysics, part: str, box: str) -> np.ndarray:
    """
    :return: A loose part's measured position in its box's frame.
    """
    box_pose = physics.pose(box)
    return (
        Rotation.from_quat(box_pose[3:])
        .inv()
        .apply(physics.pose(part)[:3] - box_pose[:3])
    )


def touching(physics: WorkshopPhysics, first: str, second: str) -> bool:
    return any(
        {contact.body_a, contact.body_b} == {first, second}
        for contact in physics.state().contacts
    )


def place(physics: WorkshopPhysics, key: str, pose: List[float]) -> None:
    """
    Put a body somewhere before time passes, as a test's initial condition.
    """
    joint = physics.world.model.joint(f"{key}{FREE_JOINT_SUFFIX}")
    address = joint.qposadr[0]
    physics.world.data.qpos[address : address + 7] = [*pose[:3], pose[6], *pose[3:6]]
    mujoco.mj_forward(physics.world.model, physics.world.data)


# %% loose bodies and the holding spring


def test_gravity_settles_the_screws_inside_their_box(physics, bundle):
    physics.step(1.0)
    for key in bundle.workshop.screws():
        position = relative_position(physics, key, SCREW_BOX)
        assert -0.14 < position[0] < 0.14
        assert -0.16 < position[1] < 0.16
        assert 0.005 < position[2] < 0.075
    assert any(touching(physics, SCREW_BOX, key) for key in bundle.workshop.screws())
    assert physics.world.is_finite()


def test_the_spring_lifts_a_body_without_teleporting_it(physics):
    physics.step(0.5)
    original = pose_list(physics, SCREW_BOX)
    target = list(original)
    target[2] += 0.20
    physics.grab(SCREW_BOX)
    physics.move(SCREW_BOX, Pose(*target))
    assert pose_list(physics, SCREW_BOX) == original
    physics.step(0.6)
    assert pose_list(physics, SCREW_BOX)[2] > original[2] + 0.14
    assert physics.state().target.to_json() == pytest.approx(target)
    physics.release()
    physics.step(1.0)
    assert pose_list(physics, SCREW_BOX)[2] == pytest.approx(original[2], abs=0.002)


def test_holding_a_body_where_it_is_only_carries_its_weight(physics):
    physics.grasp.hold(DRIVER)
    physics.world.data.xfrc_applied[:] = 0
    physics.grasp.apply()
    body = physics.world.body(DRIVER)
    np.testing.assert_allclose(physics.world.data.xfrc_applied[body, 3:], 0, atol=1e-12)
    np.testing.assert_allclose(
        physics.world.data.xfrc_applied[body, :3],
        -physics.world.mass(DRIVER) * physics.world.model.opt.gravity,
    )


def test_the_screwdriver_rests_on_its_cradle_above_the_bench(physics, bundle):
    initial = np.array(pose_list(physics, DRIVER))
    physics.step(1.5)
    settled = np.array(pose_list(physics, DRIVER))
    assert settled[:3] == pytest.approx(initial[:3], abs=0.003)
    assert abs(np.dot(settled[3:], initial[3:])) > 0.9999
    environment = bundle.file(bundle.scene.models[0].urdf)
    worktop = ElementTree.parse(environment).find("link/collision[@name='worktop']")
    centre = np.fromstring(worktop.find("origin").attrib["xyz"], sep=" ")
    size = np.fromstring(worktop.find("geometry/box").attrib["size"], sep=" ")
    assert settled[2] - (centre[2] + size[2] / 2) > 0.10
    assert any(
        DRIVER in (contact.body_a, contact.body_b)
        for contact in physics.state().contacts
    )


def test_the_workpiece_stays_in_its_jig(physics):
    initial = np.array(pose_list(physics, ASSEMBLY))
    physics.step(1.5)
    settled = np.array(pose_list(physics, ASSEMBLY))
    assert settled[:3] == pytest.approx(initial[:3], abs=0.003)
    assert abs(np.dot(settled[3:], initial[3:])) > 0.9999


def test_the_jig_holds_the_workpiece_against_an_insertion_load(physics):
    physics.step(0.25)
    initial = physics.pose(ASSEMBLY)
    target = initial.copy()
    target[1] += 0.03
    physics.grab(ASSEMBLY)
    physics.move(ASSEMBLY, Pose(*target.tolist()))
    physics.step(0.5)
    assert abs(physics.pose(ASSEMBLY)[1] - initial[1]) < (
        physics.parameters.pilot_capture_height
    )


def test_tilting_a_box_lets_its_contents_slide(physics):
    physics.step(0.6)
    physics.grab(SCREW_BOX)
    target = pose_list(physics, SCREW_BOX)
    target[2] += 0.23
    physics.move(SCREW_BOX, Pose(*target))
    physics.step(1.0)
    before = relative_position(physics, SCREW, SCREW_BOX)
    target[3:] = Rotation.from_euler("x", 30, degrees=True).as_quat().tolist()
    physics.move(SCREW_BOX, Pose(*target))
    physics.step(1.0)
    after = relative_position(physics, SCREW, SCREW_BOX)
    assert abs(after[1] - before[1]) > 0.025
    assert -0.17 < after[1] < 0.17


def test_a_moved_box_does_not_carry_its_contents_rigidly(physics):
    physics.step(0.5)
    physics.grab(NAIL_BOX)
    target = pose_list(physics, NAIL_BOX)
    target[2] += 0.25
    physics.move(NAIL_BOX, Pose(*target))
    physics.step(0.8)
    before = relative_position(physics, "nail_1", NAIL_BOX)
    target[1] -= 0.20
    physics.move(NAIL_BOX, Pose(*target))
    physics.step(0.15)
    after = relative_position(physics, "nail_1", NAIL_BOX)
    assert np.linalg.norm(after - before) > 0.015


def test_the_worktop_resists_the_spring(physics):
    physics.step(0.5)
    physics.grab(NAIL_BOX)
    target = pose_list(physics, NAIL_BOX)
    original_height = target[2]
    target[2] -= 0.20
    physics.move(NAIL_BOX, Pose(*target))
    physics.step(0.6)
    assert pose_list(physics, NAIL_BOX)[2] > original_height - 0.005
    applied = physics.world.data.xfrc_applied[physics.world.body(NAIL_BOX), :3]
    assert np.linalg.norm(applied) <= physics.parameters.maximum_force + 1e-8


def test_commands_that_do_not_fit_the_world_are_refused(physics):
    with pytest.raises(NothingHeld):
        physics.move(SCREW_BOX, Pose(0, 0, 1, 0, 0, 0, 1))
    physics.grab(SCREW_BOX)
    with pytest.raises(NothingHeld):
        physics.move(NAIL_BOX, Pose(0, 0, 1, 0, 0, 0, 1))
    with pytest.raises(TargetOutsideWorkspace):
        physics.move(SCREW_BOX, Pose(0, 0, 9, 0, 0, 0, 1))
    with pytest.raises(UnknownWorkshopBody):
        physics.grab("workshop_environment")
    with pytest.raises(UnknownDrawer):
        physics.set_drawer("workshop_floor_joint", 0.1)
    with pytest.raises(InvalidStepDuration):
        physics.step(-1.0)


def test_a_moved_target_is_normalized(physics):
    physics.grab(SCREW_BOX)
    physics.move(SCREW_BOX, Pose(1.48, 0.1, 1.2, 0, 0, 0, 2))
    assert physics.state().target.qw == 1.0


def test_reset_puts_every_body_back(physics):
    original = physics.state()
    physics.step(0.2)
    physics.grab(SCREW_BOX)
    physics.reset()
    reset = physics.state()
    assert reset.objects == original.objects
    assert reset.time == 0 and reset.held is None


# %% drawers


def test_a_drawer_motor_drives_its_joint_to_the_target(physics):
    physics.set_drawer(UPPER_DRAWER, 0.30)
    assert physics.state().joints[UPPER_DRAWER] == 0
    physics.step(1.0)
    assert 0.28 < physics.state().joints[UPPER_DRAWER] <= 0.301
    with pytest.raises(DrawerTargetOutOfRange):
        physics.set_drawer(UPPER_DRAWER, 0.5)


def test_a_held_box_stalls_a_drawer_motor(physics):
    place(physics, NAIL_BOX, [-0.78, -0.51, 0.68, 0, 0, 0, 1])
    physics.grab(NAIL_BOX)
    physics.set_drawer(UPPER_DRAWER, 0.4)
    physics.step(1.0)
    assert physics.state().joints[UPPER_DRAWER] < 0.37
    assert touching(physics, "workshop_drawer_3", NAIL_BOX)


# %% ideal thread


def seat_screw_and_driver(physics: WorkshopPhysics) -> None:
    """
    Put the screw in the pilot hole and hold the driver with its blade in the slot.
    """
    physics.step(0.3)
    place(physics, SCREW, physics.state().thread.screw_target_pose.to_json())
    physics.step(0.15)
    goal = physics.state().thread.driver_target_pose
    place(physics, DRIVER, goal.to_json())
    physics.grab(DRIVER)
    physics.move(DRIVER, goal)
    physics.step(0.20)


def test_the_pilot_straightens_a_captured_tilt(physics):
    physics.step(0.3)
    target = physics.state().thread.screw_target_pose.to_json()
    tilted = Rotation.from_quat(target[3:]) * Rotation.from_euler("x", 0.06)
    target[3:] = tilted.as_quat().tolist()
    place(physics, SCREW, target)
    before = physics.pose(SCREW).copy()
    physics.thread.update()
    np.testing.assert_array_equal(physics.pose(SCREW), before)
    physics.step(0.8)
    axis = Rotation.from_quat(physics.pose(SCREW)[3:]).apply([0, 0, 1])
    relative = physics.thread.socket()[1].inv().apply(axis)
    assert np.linalg.norm(relative[:2]) < physics.parameters.pilot_angle / 4


def test_the_driver_turns_only_when_engaged_in_a_seated_screw(physics):
    physics.drive(DriveDirection.STOP)
    physics.grab(DRIVER)
    with pytest.raises(DriverNotEngaged):
        physics.drive(DriveDirection.FORWARD)
    seat_screw_and_driver(physics)
    thread = physics.state().thread
    assert thread.engaged and thread.screw == SCREW
    assert thread.state is ThreadState.SEATED


def test_measured_driver_rotation_advances_and_withdraws_the_screw(physics):
    seat_screw_and_driver(physics)
    initial_depth = physics.state().thread.depth
    physics.drive(DriveDirection.FORWARD)
    physics.step(1.0)
    forward = physics.state().thread
    assert forward.state is ThreadState.DRIVING
    assert forward.turns > 0.25
    assert forward.depth > initial_depth + 0.0015
    assert abs(forward.depth - forward.pitch * forward.turns) < 0.001
    physics.drive(DriveDirection.STOP)
    physics.step(0.25)
    stopped = physics.state().thread
    assert stopped.turns == forward.turns
    assert stopped.state is ThreadState.STOPPED
    physics.drive(DriveDirection.REVERSE)
    physics.step(0.50)
    reverse = physics.state().thread
    assert reverse.turns < forward.turns - 0.15
    assert reverse.depth < forward.depth - 0.0009


def test_without_torque_the_thread_does_not_advance(physics):
    seat_screw_and_driver(physics)
    physics.parameters = replace(physics.parameters, maximum_torque=0.0)
    physics.thread.parameters = physics.parameters
    initial_depth = physics.state().thread.depth
    physics.drive(DriveDirection.FORWARD)
    physics.step(0.5)
    thread = physics.state().thread
    assert abs(thread.turns) < 0.005
    assert thread.state is ThreadState.STOPPED
    assert physics.thread.direction == 0
    assert thread.depth <= initial_depth + physics.parameters.pilot_capture_height


def test_the_thread_reactions_cancel_out(physics):
    seat_screw_and_driver(physics)
    data = physics.world.data
    data.xfrc_applied[:] = 0
    target = physics.pose(SCREW)
    target[0] += 0.003
    physics.thread.apply_constraint(target)
    forces = data.xfrc_applied[:, :3]
    torques = data.xfrc_applied[:, 3:]
    np.testing.assert_allclose(forces.sum(axis=0), 0, atol=1e-12)
    np.testing.assert_allclose(
        (torques + np.cross(data.xipos, forces)).sum(axis=0), 0, atol=1e-12
    )
    assert np.linalg.norm(forces[physics.world.body(ASSEMBLY)]) > 1


def test_the_thread_stops_before_the_head_meets_the_wood(physics, bundle):
    seat_screw_and_driver(physics)
    maximum_depth = bundle.workshop.assembly.maximum_depth
    physics.drive(DriveDirection.FORWARD)
    physics.step(maximum_depth / bundle.workshop.screw.thread_pitch + 3.0)
    thread = physics.state().thread
    assert thread.state is ThreadState.LIMIT
    assert thread.depth <= maximum_depth + 0.001
    assert physics.thread.direction == 0


def test_pulling_a_seated_screw_out_frees_the_thread(physics):
    seat_screw_and_driver(physics)
    physics.release()
    physics.grab(SCREW)
    assert physics.state().thread.state is ThreadState.FREE


# %% solver failures


def test_an_invalid_state_is_reported_without_a_silent_reset(physics):
    physics.world.data.qpos[-1] = float("nan")
    with pytest.raises(WorkshopSimulationFailure):
        physics.step(0.01)
    with pytest.raises(WorkshopSimulationFailure):
        physics.state()


def test_a_reset_by_the_solver_is_reported_on_the_first_step(physics):
    physics.world.data.qvel[-1] = 1e20
    with pytest.raises(WorkshopSimulationFailure):
        physics.step(0.01)


# %% through the session


def test_a_screw_is_seated_and_driven_through_session_commands(physics, session):
    def act(action, **arguments):
        session.command(WorkshopCommand(action=action, **arguments))

    def approach(key: str, goal: Pose) -> None:
        """
        Lift a held body clear, come down along the goal's axis and settle on it.
        """
        lifted = pose_list(physics, key)
        lifted[2] = 1.40
        act(WorkshopAction.MOVE, object_key=key, pose=Pose(*lifted))
        physics.step(0.7)
        above = np.array(goal.to_json())
        above[:3] += Rotation.from_quat(above[3:]).apply([0, 0, 0.15])
        act(WorkshopAction.MOVE, object_key=key, pose=Pose(*above.tolist()))
        physics.step(0.8)
        act(WorkshopAction.MOVE, object_key=key, pose=goal)
        physics.step(0.8)

    physics.step(0.4)
    act(WorkshopAction.GRAB, object_key=SCREW)
    approach(SCREW, physics.state().thread.screw_target_pose)
    act(WorkshopAction.RELEASE)
    physics.step(0.2)
    assert physics.state().thread.state is ThreadState.SEATED
    act(WorkshopAction.GRAB, object_key=DRIVER)
    physics.step(0.01)
    approach(DRIVER, physics.state().thread.driver_target_pose)
    assert physics.state().thread.engaged
    act(WorkshopAction.DRIVE, direction=DriveDirection.FORWARD)
    physics.step(0.5)
    assert physics.state().thread.turns > 0.15
