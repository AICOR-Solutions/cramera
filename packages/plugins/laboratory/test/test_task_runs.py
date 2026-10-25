"""
Running robot task demos in a process of their own.
"""

from __future__ import annotations

import sys
import time
import os
import subprocess
from pathlib import Path

import cramera_laboratory.task_runs as task_runs
from cramera_laboratory.resources import RESOURCES_DIRECTORY, LaboratoryResource
from cramera_laboratory.task_runs import (
    LaboratoryTask,
    TaskProcess,
    TaskRecording,
)
from cramera_protocol.laboratory.runs import TaskRunState, TransferOption

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
    assert process.command == [
        sys.executable,
        "-m",
        LaboratoryTask.TRANSFER,
        TransferOption.BUNDLE,
        str(RESOURCES_DIRECTORY / LaboratoryResource.BENCH),
    ]
    assert process.scene == TaskRecording.TRANSFER
    assert process.log.parent.parent == locations.data


def test_missing_bridge_leaves_the_transfer_unavailable(locations, monkeypatch):
    monkeypatch.setattr(task_runs.importlib.util, "find_spec", lambda package: None)
    process = TaskProcess.of_task(
        LaboratoryTask.TRANSFER, TaskRecording.TRANSFER, locations
    )
    assert process.start().state is TaskRunState.UNAVAILABLE
    assert process.process is None


def test_an_older_bridge_without_the_laboratory_is_unavailable(tmp_path):
    bridge = tmp_path / "cramera_bridge"
    bridge.mkdir()
    (bridge / "__init__.py").write_text("")
    packages = Path(__file__).resolve().parents[3]
    paths = [
        tmp_path,
        packages / "plugins/laboratory/src",
        packages / "protocol/src",
        packages / "viewer/src",
    ]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "from cramera.locations import DataLocations; "
            "from cramera_laboratory.task_runs import "
            "LaboratoryTask, TaskProcess, TaskRecording; "
            "print(TaskProcess.of_task(LaboratoryTask.TRANSFER, "
            "TaskRecording.TRANSFER, DataLocations(Path('data'), None)).state().state)",
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(map(str, paths))},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == TaskRunState.UNAVAILABLE


def test_shutdown_kills_a_child_that_ignores_termination(locations, monkeypatch):
    monkeypatch.setattr(task_runs, "STOP_TIMEOUT", 0.02)
    process = stand_in(locations, "stubborn_task.py")
    process.start()
    deadline = time.monotonic() + WAIT
    try:
        while "ready" not in process.log.read_text():
            assert time.monotonic() < deadline
            time.sleep(POLL)
        assert process.stop().state is TaskRunState.FAILED
        assert process.process.poll() is not None
    finally:
        process.stop()
