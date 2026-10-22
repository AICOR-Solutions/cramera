"""
The cable lab's simulation: a friction pinch that lifts a loose cable, slip without
friction, the background thread, and what is measured.
"""

from __future__ import annotations

import time
from pathlib import Path

import mujoco
import numpy as np
import pytest
from typing_extensions import Iterator

from cramera_cable_lab import physics as physics_module
from cramera_cable_lab.exceptions import (
    CableNotBuilt,
    GripperTargetOutsideWorkspace,
    SteppingWhileRunning,
    StoppedSimulation,
)
from cramera_cable_lab.physics import CablePhysics
from cramera_cable_lab.plugin import CablePhysicsFactory, SimulationLibraries
from cramera_cable_lab.session import CableLabSession
from cramera_protocol.cable_lab import (
    CableConfiguration,
    ContactFriction,
    GraspState,
    GripperAction,
    GripperCommand,
    SimulationLifecycle,
)
from cramera_protocol.geometry import Vector3

CLOSING_STEPS = 800
"""
How many steps the pads take to close on the cable.
"""

LIFTING_STEPS = 1800
"""
How many steps one lift takes.
"""

FALLING_STEPS = 1200
"""
How many steps a released cable falls.
"""

NEGLIGIBLE_FRICTION = ContactFriction(0.00001, 0.0, 0.0)
"""
Friction too small to hold the cable.
"""

STARTS = 5
"""
How often a test starts a cable, since a start races with the simulation thread.
"""

WAIT_SECONDS = 2.0
"""
How long a test waits for the background simulation.
"""


def command(physics: CablePhysics, action: GripperAction) -> None:
    physics.command(GripperCommand(action=action))


def mean_height(physics: CablePhysics) -> float:
    """
    :return: The capsules' mean height.
    """
    segments = physics.measure().segments
    return float(
        np.mean([(segment.start.z + segment.end.z) / 2 for segment in segments])
    )


@pytest.fixture
def loose_cable() -> Iterator[CablePhysics]:
    """
    :return: A loose cable's simulation; stopped afterwards.
    """
    physics = CablePhysics(configuration=CableConfiguration(anchored=False))
    yield physics
    physics.stop()


# %% friction grasp


def test_pinching_and_lifting_carries_the_cable_by_friction(loose_cable):
    command(loose_cable, GripperAction.PINCH)
    loose_cable.step(CLOSING_STEPS)
    initial = mean_height(loose_cable)
    assert loose_cable.measure().grasp.state is GraspState.HOLDING
    command(loose_cable, GripperAction.LIFT)
    loose_cable.step(LIFTING_STEPS)
    assert mean_height(loose_cable) > initial + 0.03
    assert loose_cable.model.neq == 0


def test_without_friction_the_cable_stays_down():
    physics = CablePhysics(
        configuration=CableConfiguration(anchored=False, friction=NEGLIGIBLE_FRICTION)
    )
    command(physics, GripperAction.PINCH)
    physics.step(CLOSING_STEPS)
    initial = mean_height(physics)
    command(physics, GripperAction.LIFT)
    physics.step(LIFTING_STEPS)
    assert mean_height(physics) < initial + 0.01
    physics.stop()


def test_opening_lets_a_lifted_cable_fall(loose_cable):
    command(loose_cable, GripperAction.PINCH)
    loose_cable.step(CLOSING_STEPS)
    command(loose_cable, GripperAction.LIFT)
    loose_cable.step(LIFTING_STEPS)
    held = mean_height(loose_cable)
    command(loose_cable, GripperAction.RELEASE)
    loose_cable.step(FALLING_STEPS)
    assert mean_height(loose_cable) < held - 0.03
    assert loose_cable.measure().grasp.state is GraspState.OPEN


def test_lowering_moves_the_gripper_down(loose_cable):
    start = loose_cable.target[2]
    command(loose_cable, GripperAction.LOWER)
    assert loose_cable.target[2] == pytest.approx(
        start - loose_cable.parameters.lift_distance
    )


def test_a_move_outside_the_workspace_is_refused(loose_cable):
    with pytest.raises(GripperTargetOutsideWorkspace):
        loose_cable.command(
            GripperCommand(action=GripperAction.MOVE, position=Vector3(0.0, 0.0, 9.0))
        )
    target = Vector3(0.1, 0.0, 0.4)
    loose_cable.command(GripperCommand(action=GripperAction.MOVE, position=target))
    assert loose_cable.target.tolist() == target.to_json()


# %% measurement


def test_the_state_reports_every_capsule_and_its_point(loose_cable):
    loose_cable.step(20)
    state = loose_cable.measure()
    count = loose_cable.configuration.segment_count
    assert len(state.segments) == len(state.points) == count
    for point, name in zip(state.points, loose_cable.cable.body_names()):
        np.testing.assert_allclose(
            point.position.to_json(), loose_cable.data.body(name).xpos
        )
    assert state.anchor.enabled is False
    assert state.warnings == []


def test_a_reset_simulation_reports_where_the_cable_is(loose_cable):
    mujoco.mj_resetDataKeyframe(loose_cable.model, loose_cable.data, 0)
    heights = [segment.start.z for segment in loose_cable.measure().segments]
    assert heights == pytest.approx(
        [loose_cable.parameters.mount_height] * len(heights), abs=0.001
    )


@pytest.mark.parametrize("attempt", range(STARTS))
def test_a_cable_measured_right_after_its_start_is_where_it_was_built(attempt):
    physics = CablePhysics(configuration=CableConfiguration(anchored=False))
    physics.start()
    heights = [segment.start.z for segment in physics.measure().segments]
    physics.stop()
    assert heights == pytest.approx(
        [physics.parameters.mount_height] * len(heights), abs=0.001
    )


def test_numerical_warnings_are_reported(loose_cable):
    loose_cable.data.warning[0].number = 1
    assert len(loose_cable.measure().warnings) == 1


# %% background simulation


def test_the_background_thread_starts_and_stops(loose_cable):
    initial = mean_height(loose_cable)
    loose_cable.start()
    assert loose_cable.running()
    with pytest.raises(SteppingWhileRunning):
        loose_cable.step(1)
    deadline = time.monotonic() + WAIT_SECONDS
    while loose_cable.measure().simulation_time < 0.03 and time.monotonic() < deadline:
        time.sleep(0.01)
    loose_cable.stop()
    assert not loose_cable.running()
    assert loose_cable.measure().simulation_time >= 0.03
    assert mean_height(loose_cable) == pytest.approx(initial, abs=0.001)
    with pytest.raises(StoppedSimulation):
        loose_cable.start()


def test_a_session_runs_the_real_simulation():
    session = CableLabSession(factory=CablePhysicsFactory(SimulationLibraries()).build)
    state = session.start(CableConfiguration(segment_count=4))
    assert state.lifecycle is SimulationLifecycle.RUNNING
    session.command(GripperCommand(action=GripperAction.PINCH))
    assert session.stop().lifecycle is SimulationLifecycle.IDLE
    session.close()


# %% failed construction


def test_a_cable_that_cannot_be_built_releases_what_it_took(monkeypatch):
    directories = []

    class RecordedDirectory(physics_module.TemporaryDirectory):
        def __init__(self, *arguments, **keywords):
            super().__init__(*arguments, **keywords)
            directories.append(Path(self.name))

    def refuse(builder, specification):
        raise CableNotBuilt("the rig is refused")

    monkeypatch.setattr(physics_module, "TemporaryDirectory", RecordedDirectory)
    monkeypatch.setattr(physics_module.RigBuilder, "build", refuse)
    with pytest.raises(CableNotBuilt):
        CablePhysics()
    assert [directory.exists() for directory in directories] == [False]
