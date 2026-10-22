"""
Running a generated demo as a child process the plan builder owns.
"""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

import pytest
from typing_extensions import Callable

from cramera_plan_builder.demos import DemoDirectory, DemoOption, DemoTemplate
from cramera_plan_builder.exceptions import DemoNotStarted
from cramera_plan_builder.runs import DemoRunner, OutputLog
from cramera_protocol.plan_builder import (
    DemoDocument,
    RunMode,
    RunState,
    RunStatus,
)

from .dataset.given_workspace import DATASET

TEMPLATES = DATASET / "templates"
"""
The stand-ins of the demo template.
"""

PORT = 18766
"""
The port the test demos are told to publish on.
"""

LOG_LIMIT = 256
"""
How many bytes of a test demo's output are kept.
"""

WAIT = 20.0
"""
How long a test waits for a demo to reach a state, in seconds.
"""

WAIT_INTERVAL = 0.05
"""
How often a test looks at a demo's state, in seconds.
"""

STUBBORN_TIMEOUT = 0.5
"""
How long a demo that ignores termination is given before it is killed, in seconds.
"""


def runner_of(tmp_path: Path, template: str, **fields) -> DemoRunner:
    """
    :param tmp_path: The test's directory.
    :param template: The file name of a stand-in template.
    :param fields: Further fields of the runner.
    :return: A runner rendering the stand-in, writing into the test's directory.
    """
    return DemoRunner(
        directory=DemoDirectory(tmp_path / "demos", interpreter=sys.executable),
        port=PORT,
        log_limit=LOG_LIMIT,
        template=DemoTemplate(TEMPLATES / template),
        **fields,
    )


def wait_for(runner: DemoRunner, accepts: Callable[[RunStatus], bool]) -> RunStatus:
    """
    :param runner: A runner with a started demo.
    :param accepts: Whether a status is the awaited one.
    :return: The first accepted status.
    """
    deadline = time.monotonic() + WAIT
    status = runner.status()
    while not accepts(status) and time.monotonic() < deadline:
        time.sleep(WAIT_INTERVAL)
        status = runner.status()
    return status


@pytest.fixture
def demo(plan) -> DemoDocument:
    """
    :return: The test plan's demo document.
    """
    return DemoDocument(plan=plan)


@pytest.fixture
def runner(tmp_path) -> DemoRunner:
    """
    :return: A runner of the waiting stand-in; its demo is stopped after the test.
    """
    runner = runner_of(tmp_path, "waiting_demo.py")
    yield runner
    runner.stop()


# %% states


def test_nothing_runs_before_a_demo_is_started(runner):
    assert runner.status() == RunStatus()
    assert runner.stop() == RunStatus()


def test_a_staged_demo_runs_until_it_is_stopped(runner, demo):
    started = runner.start(demo, RunMode.STAGE)
    assert started.state is RunState.RUNNING and started.mode is RunMode.STAGE
    shown = wait_for(runner, lambda status: DemoOption.STAGE in status.log)
    assert f"{DemoOption.PORT} {PORT} {DemoOption.LIFELINE}" in shown.log
    stopped = runner.stop()
    assert stopped.state is RunState.STOPPED
    assert stopped.return_code is not None


def test_a_performing_demo_ends_on_its_own(runner, demo):
    runner.start(demo, RunMode.PERFORM)
    ended = wait_for(runner, lambda status: status.state is not RunState.RUNNING)
    assert ended.state is RunState.FINISHED and ended.return_code == 0
    assert DemoOption.STAGE not in ended.log
    assert ended.path == str(
        (runner.directory.directory / "milk_to_table.py").resolve()
    )


def test_a_demo_watching_its_owner_ends_cleanly_on_its_own(tmp_path, demo):
    runner = runner_of(tmp_path, "finishing_demo.py")
    runner.start(demo, RunMode.PERFORM)
    ended = wait_for(runner, lambda status: status.state is not RunState.RUNNING)
    runner.stop()
    assert ended.state is RunState.FINISHED, ended.log
    assert ended.return_code == 0


def test_a_failing_demo_shows_its_output(tmp_path, demo):
    runner = runner_of(tmp_path, "failing_demo.py")
    runner.start(demo, RunMode.PERFORM)
    ended = wait_for(runner, lambda status: status.state is not RunState.RUNNING)
    runner.stop()
    assert ended.state is RunState.FAILED and ended.return_code == 1
    assert ended.log.startswith("Traceback")


def test_a_demo_ignoring_termination_is_killed(tmp_path, demo):
    runner = runner_of(tmp_path, "stubborn_demo.py", stop_timeout=STUBBORN_TIMEOUT)
    runner.start(demo, RunMode.STAGE)
    wait_for(runner, lambda status: bool(status.log))
    stopped = runner.stop()
    assert stopped.state is RunState.STOPPED
    assert stopped.return_code == -signal.SIGKILL


def test_a_new_demo_replaces_the_running_one(runner, demo):
    runner.start(demo, RunMode.STAGE)
    first = runner.current
    runner.start(demo, RunMode.STAGE)
    assert first.status().state is RunState.STOPPED
    assert runner.status().state is RunState.RUNNING


def test_a_staged_demo_ends_when_its_owner_goes_away(runner, demo):
    runner.start(demo, RunMode.STAGE)
    wait_for(runner, lambda status: DemoOption.STAGE in status.log)
    runner.current.process.stdin.close()
    ended = wait_for(runner, lambda status: status.state is not RunState.RUNNING)
    assert ended.state is RunState.FINISHED
    assert ended.log.rstrip().endswith("stage ended")


def test_only_the_newest_output_is_kept(tmp_path, demo):
    runner = runner_of(tmp_path, "chatty_demo.py")
    runner.start(demo, RunMode.PERFORM)
    ended = wait_for(runner, lambda status: status.state is not RunState.RUNNING)
    runner.stop()
    assert len(ended.log.encode("utf-8")) == LOG_LIMIT
    assert ended.log.endswith("line 01999\n")


def test_a_demo_whose_interpreter_is_missing_is_not_started(tmp_path, demo):
    runner = DemoRunner(
        directory=DemoDirectory(tmp_path, interpreter=str(tmp_path / "no-python")),
        port=PORT,
        log_limit=LOG_LIMIT,
    )
    with pytest.raises(DemoNotStarted):
        runner.start(demo, RunMode.STAGE)


# %% output


def test_the_log_drops_its_oldest_bytes_beyond_the_limit():
    log = OutputLog(limit=4)
    log.append(b"abc")
    log.append(b"def")
    assert log.text() == "cdef"
