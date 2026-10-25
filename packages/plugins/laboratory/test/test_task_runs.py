"""
Running robot task demos in a process of their own.
"""

from __future__ import annotations

import sys
import time
import os
import subprocess
from pathlib import Path

import pytest

import cramera_laboratory.task_runs as task_runs
from cramera_laboratory.resources import RESOURCES_DIRECTORY, LaboratoryResource
from cramera_laboratory.task_runs import (
    LaboratoryTask,
    TaskProcess,
    TaskRecording,
)
from cramera_protocol.laboratory.runs import TaskRunState, TransferOption
from cramera_protocol.bundle.files import BundleFile

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


def test_the_previous_bridge_cannot_start_a_run_with_unsupported_options(
    locations, monkeypatch
):
    from cramera_bridge.laboratory import command

    monkeypatch.setattr(task_runs.importlib.util, "find_spec", lambda package: object())
    monkeypatch.setattr(command, "missing_libraries", lambda: [])
    monkeypatch.delattr(command, "prepare_preview")
    process = TaskProcess.of_task(
        LaboratoryTask.TRANSFER, TaskRecording.TRANSFER, locations
    )
    state = process.start()
    assert state.state is TaskRunState.UNAVAILABLE
    assert state.can_run is False
    assert process.process is None


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


# %% native reruns and live address


def native_stand_in(locations, *arguments) -> TaskProcess:
    """
    :return: A command that accepts the native recording and live announcement options.
    """
    return TaskProcess(
        command=[
            sys.executable,
            str(DATASET / "tasks" / "native_recording_task.py"),
            *arguments,
        ],
        scene=SCENE,
        locations=locations,
        packages=(),
        fresh_recording=True,
    )


def test_native_reruns_save_new_recordings_and_preserve_the_previous_one(locations):
    process = native_stand_in(locations)
    process.start()
    first = settled(process)
    original = locations.local_scenes / first.scene / BundleFile.SCENE
    original_bytes = original.read_bytes()
    assert process.start().state is TaskRunState.RUNNING
    second = settled(process)
    assert second.state is TaskRunState.RECORDED
    assert second.scene != first.scene
    assert (locations.local_scenes / second.scene / BundleFile.SCENE).is_file()
    assert original.read_bytes() == original_bytes


def test_failed_native_rerun_is_not_hidden_by_an_older_recording(locations):
    process = native_stand_in(locations)
    process.start()
    previous = settled(process)
    process.command.append("--failure")
    process.start()
    failed = settled(process)
    assert failed.state is TaskRunState.FAILED
    assert failed.scene != previous.scene
    assert FAILURE in failed.error
    assert (locations.local_scenes / previous.scene / BundleFile.SCENE).is_file()


def test_existing_recording_remains_viewable_without_the_native_runtime(locations):
    process = native_stand_in(locations)
    process.start()
    recorded = settled(process)
    process.packages = ("no_such_package",)
    unavailable = process.start()
    assert unavailable.state is TaskRunState.RECORDED
    assert unavailable.scene == recorded.scene
    assert unavailable.can_run is False


def test_live_address_belongs_to_the_current_child_and_is_cleared_on_stop(locations):
    process = native_stand_in(locations, "--waiting")
    process.live_url_file.parent.mkdir(parents=True)
    process.live_url_file.write_text("http://127.0.0.1:1234/")
    assert process.live_address() is None
    process.start()
    deadline = time.monotonic() + WAIT
    try:
        while process.live_address() is None:
            assert time.monotonic() < deadline
            time.sleep(POLL)
        assert process.live_address() == "http://127.0.0.1:8765/"
        assert process.state().live_url == "/api/plugins/laboratory/transfer/live/"
    finally:
        process.stop()
    assert process.live_address() is None
    assert not process.live_url_file.exists()


@pytest.mark.parametrize(
    "address",
    [
        "https://127.0.0.1:8765/",
        "http://example.com:8765/",
        "http://127.0.0.1:8765/private/",
        "http://127.0.0.1:8765/?destination=elsewhere",
        "http://user:secret@127.0.0.1:8765/",
        "http://127.0.0.1:99999/",
    ],
)
def test_live_address_refuses_anything_beyond_the_child_loopback_root(
    locations, address
):
    process = native_stand_in(locations, "--waiting")
    process.start()
    deadline = time.monotonic() + WAIT
    try:
        while process.live_address() is None:
            assert time.monotonic() < deadline
            time.sleep(POLL)
        process.live_url_file.write_text(address)
        assert process.live_address() is None
    finally:
        process.stop()
