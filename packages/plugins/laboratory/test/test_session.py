"""
The simulation session: one simulation at a time, its bundle, its worker and its
commands, with stand-ins for the simulation.
"""

from __future__ import annotations

import time

import pytest

from cramera.scenes import SceneDirectory, SceneSource
from cramera_laboratory.exceptions import PhysicsUnavailable, SimulationNotRunning
from cramera_laboratory.resources import LaboratoryResource
from cramera_laboratory.scene_files import JsonFile
from cramera_laboratory.session import (
    CONTACT_SUFFIX,
    MujocoSimulations,
    SimulationSession,
)
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.geometry import Vector3
from cramera_protocol.laboratory.layout import LaboratorySceneKey
from cramera_protocol.laboratory.physics import (
    ContactPhysicsControls,
    SimulationState,
    TargetRequest,
)

from .dataset.simulations import RecordingFactory

WAIT = 5.0
"""
How long a test waits for the worker at most, in seconds.
"""

POLL = 0.01
"""
How often a waiting test looks, in seconds.
"""

FAILURE = "the solver diverged"
"""
What the failing stand-in reports.
"""


@pytest.fixture
def session(locations, factory) -> SimulationSession:
    """
    :return: A session over stand-ins; stopped after the test.
    """
    session = SimulationSession(locations, factory)
    yield session
    session.stop()


def wait_until(condition) -> None:
    """
    :param condition: What must become true.
    """
    deadline = time.monotonic() + WAIT
    while not condition():
        assert time.monotonic() < deadline
        time.sleep(POLL)


def test_starting_writes_the_bundle_and_runs_the_worker(
    session, factory, bench_laboratory, locations
):
    answer = session.start(bench_laboratory)
    assert answer.state is SimulationState.RUNNING
    assert answer.scene == f"{bench_laboratory.name}{CONTACT_SUFFIX}"
    bundle = locations.local_scenes / answer.scene
    description = JsonFile(bundle / BundleFile.SCENE).read(SceneDescription)
    controls = ContactPhysicsControls.from_json(
        description.extensions[LaboratorySceneKey.CONTACT_PHYSICS]
    )
    trajectory = JsonFile(bundle / BundleFile.TRAJECTORY).read(Trajectory)
    snapshot = factory.created[0].snapshot()
    assert description.name == answer.scene
    assert controls.laboratory == bench_laboratory.name
    assert trajectory.objects == [snapshot.objects]
    assert trajectory.frames == [snapshot.joints]
    assert trajectory.body_poses == [snapshot.body_poses]
    assert answer.scene in [
        entry.name
        for entry in SceneDirectory(locations.local_scenes, SceneSource.LOCAL)
        .index()
        .scenes
    ]
    wait_until(lambda: factory.created[0].steps > 0)


def test_a_command_reaches_the_running_simulation(session, factory, bench_laboratory):
    session.start(bench_laboratory)
    request = TargetRequest(key="tube_clear", position=Vector3(0.16, -0.065, 1.0))
    answer = session.command(lambda simulation: simulation.set_target(request))
    assert factory.created[0].commands == [request]
    assert answer.snapshot == factory.created[0].snapshot()


def test_commands_need_a_running_simulation(session):
    with pytest.raises(SimulationNotRunning):
        session.command(lambda simulation: simulation.release())


def test_stopping_ends_the_worker_and_keeps_the_last_state(session, bench_laboratory):
    session.start(bench_laboratory)
    answer = session.stop()
    assert answer.state is SimulationState.IDLE
    assert answer.snapshot is not None and answer.laboratory == bench_laboratory.name
    assert session.worker is None


def test_starting_the_same_laboratory_again_keeps_its_simulation(
    session, factory, bench_laboratory
):
    session.start(bench_laboratory)
    session.start(bench_laboratory)
    assert len(factory.created) == 1


def test_starting_another_laboratory_replaces_the_simulation(session, factory, shelf):
    session.start(shelf.laboratory(LaboratoryResource.BENCH))
    answer = session.start(shelf.laboratory(LaboratoryResource.EXPANDED))
    assert len(factory.created) == 2
    assert answer.laboratory == LaboratoryResource.EXPANDED


def test_a_failing_step_ends_the_worker_and_is_reported(
    session, factory, bench_laboratory
):
    session.start(bench_laboratory)
    factory.created[0].failure = RuntimeError(FAILURE)
    wait_until(lambda: session.answer().state is SimulationState.FAILED)
    assert FAILURE in session.answer().error


def test_an_idle_session_reports_nothing_simulated(session):
    answer = session.answer()
    assert answer.state is SimulationState.IDLE and answer.snapshot is None


def test_without_the_engine_a_start_is_refused(locations, bench_laboratory):
    session = SimulationSession(locations, RecordingFactory(installed=False))
    with pytest.raises(PhysicsUnavailable):
        session.start(bench_laboratory)


def test_mujoco_simulations_know_whether_mujoco_is_installed(
    monkeypatch, bench_laboratory
):
    simulations = MujocoSimulations()
    monkeypatch.setattr(MujocoSimulations, "available", lambda self: False)
    with pytest.raises(PhysicsUnavailable):
        simulations.create(bench_laboratory)
