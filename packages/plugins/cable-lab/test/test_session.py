"""
The cable lab session: building, replacing, resetting, commanding and stopping a cable
simulation, and noticing one that stopped by itself.
"""

from __future__ import annotations

import pytest

from cramera_cable_lab.exceptions import (
    CableLabInactive,
    CableNotBuilt,
    GripperTargetOutsideWorkspace,
    StoppedSimulation,
)
from cramera_cable_lab.session import (
    GRIPPER_WORKSPACE,
    UNEXPECTED_STOP,
    CableLabSession,
)
from cramera_protocol.cable_lab import (
    CableConfiguration,
    GripperAction,
    GripperCommand,
    SimulationLifecycle,
)
from cramera_protocol.geometry import Vector3

from .dataset.simulations import REFUSED_SEGMENT_COUNT, RecordingFactory


@pytest.fixture
def factory() -> RecordingFactory:
    """
    :return: A factory of stand-in simulations.
    """
    return RecordingFactory()


@pytest.fixture
def session(factory) -> CableLabSession:
    """
    :return: A session over stand-in simulations.
    """
    return CableLabSession(factory=factory.build)


PINCH = GripperCommand(action=GripperAction.PINCH)
"""
Closing the pads.
"""


# %% lifecycle


def test_a_new_session_is_idle_without_a_cable(session):
    state = session.state()
    assert state.lifecycle is SimulationLifecycle.IDLE
    assert state.configuration is None


def test_starting_builds_and_runs_the_cable(session, factory):
    configuration = CableConfiguration(segment_count=4)
    state = session.start(configuration)
    assert state.lifecycle is SimulationLifecycle.RUNNING
    assert state.configuration == configuration
    assert factory.built[0].running()


def test_a_new_cable_stops_the_previous_one(session, factory):
    session.start(CableConfiguration())
    session.start(CableConfiguration(segment_count=4))
    first, second = factory.built
    assert first.stopped and second.running()


def test_a_cable_that_cannot_be_built_keeps_the_running_one(session, factory):
    session.start(CableConfiguration())
    with pytest.raises(CableNotBuilt):
        session.start(CableConfiguration(segment_count=REFUSED_SEGMENT_COUNT))
    assert factory.built[0].running()
    assert session.state().lifecycle is SimulationLifecycle.RUNNING


def test_resetting_builds_the_last_cable_again(session, factory):
    configuration = CableConfiguration(segment_count=4)
    session.start(configuration)
    session.reset()
    first, second = factory.built
    assert first.stopped and second.running()
    assert second.configuration == configuration


def test_resetting_without_a_cable_is_refused(session):
    with pytest.raises(CableLabInactive):
        session.reset()


def test_stopping_keeps_the_last_state_readable(session):
    session.start(CableConfiguration())
    session.command(PINCH)
    state = session.stop()
    assert state.lifecycle is SimulationLifecycle.IDLE
    assert state.simulation_time == 1.0


def test_a_simulation_that_stopped_by_itself_is_reported(session, factory):
    session.start(CableConfiguration())
    factory.built[0].is_running = False
    state = session.state()
    assert state.lifecycle is SimulationLifecycle.FAILED
    assert state.error == UNEXPECTED_STOP


def test_closing_stops_the_simulation(session, factory):
    session.start(CableConfiguration())
    session.close()
    assert factory.built[0].stopped


def test_a_stopped_simulation_does_not_start_again(factory):
    simulation = factory.build(CableConfiguration())
    simulation.stop()
    with pytest.raises(StoppedSimulation):
        simulation.start()


# %% commands


def test_commands_reach_the_running_simulation(session, factory):
    session.start(CableConfiguration())
    session.command(PINCH)
    assert factory.built[0].commands == [PINCH]


def test_commands_without_a_running_simulation_are_refused(session):
    with pytest.raises(CableLabInactive):
        session.command(PINCH)
    session.start(CableConfiguration())
    session.stop()
    with pytest.raises(CableLabInactive):
        session.command(PINCH)


def test_a_target_outside_the_workspace_is_refused(session):
    session.start(CableConfiguration())
    above = Vector3(0.0, 0.0, GRIPPER_WORKSPACE.maximum[2] + 1.0)
    with pytest.raises(GripperTargetOutsideWorkspace):
        session.command(GripperCommand(action=GripperAction.MOVE, position=above))


def test_the_workspace_clamps_a_height():
    assert GRIPPER_WORKSPACE.clamped_height(-1.0) == GRIPPER_WORKSPACE.minimum[2]
    assert GRIPPER_WORKSPACE.clamped_height(99.0) == GRIPPER_WORKSPACE.maximum[2]
