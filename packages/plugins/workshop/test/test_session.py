"""
The workshop session: building the world once, letting its time pass, the commands, the
pause after inactivity, solver failures and closing.
"""

from __future__ import annotations

import threading

import pytest
from typing_extensions import Iterator, List

from cramera_protocol.geometry import Pose
from cramera_protocol.workshop import DriveDirection, WorkshopAction, WorkshopCommand
from cramera_workshop.exceptions import (
    InactiveReason,
    WorkshopInactive,
    WorkshopSimulationFailure,
)
from cramera_workshop.session import WorkshopSession

from .dataset.dynamics import MOVABLE_BODIES, ManualClock, RecordingDynamics

WAIT_SECONDS = 5.0
"""
How long a test waits for the worker at most.
"""

# %% fixtures


@pytest.fixture
def dynamics() -> RecordingDynamics:
    """
    :return: A stand-in contact world.
    """
    return RecordingDynamics()


@pytest.fixture
def builds() -> List[RecordingDynamics]:
    """
    :return: The worlds the session's factory built.
    """
    return []


@pytest.fixture
def clock() -> ManualClock:
    """
    :return: A clock that only moves when told to.
    """
    return ManualClock()


@pytest.fixture
def session(dynamics, builds, clock) -> Iterator[WorkshopSession]:
    """
    :return: A session over the stand-in world; closed afterwards.
    """

    def build() -> RecordingDynamics:
        builds.append(dynamics)
        return dynamics

    session = WorkshopSession(factory=build, clock=clock)
    yield session
    session.close()


def act(session: WorkshopSession, action: WorkshopAction, **arguments):
    return session.command(WorkshopCommand(action=action, **arguments))


# %% lifecycle


def test_a_session_before_its_first_start_is_empty_and_available(session, builds):
    state = session.state()
    assert state.objects == {} and state.thread is None
    assert state.available and not state.running
    assert builds == []


def test_the_first_start_builds_the_world_once_and_lets_time_pass(
    session, dynamics, builds
):
    act(session, WorkshopAction.START)
    state = act(session, WorkshopAction.START)
    assert builds == [dynamics]
    assert state.running
    assert dynamics.stepped.wait(WAIT_SECONDS)
    assert session.state().time > 0


def test_reset_builds_the_world_and_puts_it_back(session, dynamics, builds):
    act(session, WorkshopAction.RESET)
    assert builds == [dynamics]
    assert dynamics.calls == [("reset",)]


def test_manipulating_needs_time_to_pass(session):
    with pytest.raises(WorkshopInactive) as refused:
        act(session, WorkshopAction.GRAB, object_key=MOVABLE_BODIES[0])
    assert refused.value.reason is InactiveReason.NOT_STARTED


def test_every_command_reaches_the_world(session, dynamics):
    key = MOVABLE_BODIES[0]
    act(session, WorkshopAction.START)
    act(session, WorkshopAction.GRAB, object_key=key)
    act(
        session,
        WorkshopAction.MOVE,
        object_key=key,
        pose=Pose(0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    )
    act(session, WorkshopAction.DRAWER, joint="drawer", position=0.1)
    act(session, WorkshopAction.DRIVE, direction=DriveDirection.FORWARD)
    state = act(session, WorkshopAction.RELEASE)
    assert dynamics.calls == [
        ("grab", key),
        ("move", key),
        ("drawer", "drawer"),
        ("drive", DriveDirection.FORWARD.value),
        ("release",),
    ]
    assert state.held is None


def test_pausing_stops_the_driver_and_lets_go(session, dynamics):
    act(session, WorkshopAction.START)
    act(session, WorkshopAction.GRAB, object_key=MOVABLE_BODIES[0])
    state = act(session, WorkshopAction.PAUSE)
    assert dynamics.calls[-2:] == [("drive", DriveDirection.STOP.value), ("release",)]
    assert not state.running and state.held is None


# %% stepping


def test_a_world_nobody_watches_pauses(session, dynamics, clock):
    act(session, WorkshopAction.START)
    act(session, WorkshopAction.GRAB, object_key=MOVABLE_BODIES[0])
    with session.lock:
        clock.now += session.inactivity_timeout
        session.advance()
        assert not session.running
    assert dynamics.held_body is None


def test_a_watched_world_keeps_running(session, clock):
    act(session, WorkshopAction.START)
    clock.now += session.inactivity_timeout
    session.state()
    with session.lock:
        session.advance()
        assert session.running


def test_a_solver_failure_stops_time_until_the_world_is_reset(session, dynamics):
    act(session, WorkshopAction.START)
    with session.lock:
        dynamics.failing = True
        session.advance()
    state = session.state()
    assert not state.running and not state.available
    assert state.error == WorkshopSimulationFailure().message()
    with pytest.raises(WorkshopInactive) as refused:
        act(session, WorkshopAction.START)
    assert refused.value.reason is InactiveReason.FAILED
    dynamics.failing = False
    act(session, WorkshopAction.RESET)
    assert act(session, WorkshopAction.START).running


def test_a_worker_that_ended_by_itself_is_reported(session, dynamics, monkeypatch):
    monkeypatch.setattr(threading, "excepthook", lambda arguments: None)
    dynamics.crashing = True
    act(session, WorkshopAction.START)
    session.worker.join(WAIT_SECONDS)
    state = session.state()
    assert not state.running
    assert state.error == WorkshopSimulationFailure().message()


# %% closing


def test_a_closed_session_ends_its_worker_and_refuses_commands(session):
    act(session, WorkshopAction.START)
    worker = session.worker
    session.close()
    session.close()
    assert not worker.is_alive()
    assert not session.state().available
    with pytest.raises(WorkshopInactive) as refused:
        act(session, WorkshopAction.START)
    assert refused.value.reason is InactiveReason.CLOSED
