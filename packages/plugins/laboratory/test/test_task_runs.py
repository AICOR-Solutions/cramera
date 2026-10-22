"""
Running robot task demos in a process of their own.
"""

from __future__ import annotations

import sys
import time


from cramera_laboratory.task_runs import (
    LaboratoryTask,
    TaskProcess,
    TaskRecording,
)
from cramera_protocol.laboratory.runs import TaskRunState

from .conftest import DATASET

SCENE = TaskRecording.TRANSFER.value
"""
The recording the stand-in demos save.
"""

FAILURE = "the vessel is still held"
"""
What the failing stand-in prints.
"""

WAIT = 20.0
"""
How long a test waits for a stand-in at most, in seconds.
"""

POLL = 0.05
"""
How often a waiting test looks, in seconds.
"""


def stand_in(locations, script: str, packages=()) -> TaskProcess:
    """
    :param locations: Where the viewer keeps its scenes.
    :param script: A stand-in demo of the dataset.
    :param packages: The packages the demo needs.
    :return: A process running the stand-in.
    """
    return TaskProcess(
        command=[sys.executable, str(DATASET / "tasks" / script), SCENE],
        scene=SCENE,
        locations=locations,
        packages=packages,
    )


def settled(process: TaskProcess):
    """
    :param process: A started process.
    :return: Its state once it no longer runs.
    """
    deadline = time.monotonic() + WAIT
    while process.state().state is TaskRunState.RUNNING:
        assert time.monotonic() < deadline
        time.sleep(POLL)
    return process.state()


def test_a_demo_that_saves_its_recording_ends_recorded(locations):
    process = stand_in(locations, "recording_task.py")
    assert process.state().state is TaskRunState.IDLE
    process.start()
    assert settled(process).state is TaskRunState.RECORDED
    assert process.start().state is TaskRunState.RECORDED


def test_a_failing_demo_reports_its_last_output(locations):
    process = stand_in(locations, "failing_task.py")
    process.start()
    state = settled(process)
    assert state.state is TaskRunState.FAILED and FAILURE in state.error


def test_a_running_demo_is_not_started_twice_and_ends_on_request(locations):
    process = stand_in(locations, "waiting_task.py")
    first = process.start().state
    running = process.process
    assert first is TaskRunState.RUNNING
    assert process.start().state is TaskRunState.RUNNING and process.process is running
    assert process.stop().state is TaskRunState.FAILED


def test_a_demo_without_its_packages_is_unavailable(locations):
    process = stand_in(locations, "recording_task.py", packages=("no_such_package",))
    assert process.state().state is TaskRunState.UNAVAILABLE
    assert process.start().state is TaskRunState.UNAVAILABLE


def test_the_laboratory_runs_its_transfer_as_a_module(locations):
    process = TaskProcess.of_task(
        LaboratoryTask.TRANSFER, TaskRecording.TRANSFER, locations
    )
    assert process.command[-1] == LaboratoryTask.TRANSFER
    assert process.scene == TaskRecording.TRANSFER
    assert process.log.parent.parent == locations.data
