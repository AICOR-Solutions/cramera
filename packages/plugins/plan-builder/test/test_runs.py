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

from cramera_plan_builder.demos import DemoDirectory, DemoTemplate
from cramera_plan_builder.exceptions import (
    DemoNotStarted,
    PlanRunning,
    RunRecordSaving,
    SafetyStopNotAcknowledged,
)
from cramera_plan_builder.runs import DemoRunner, OutputLog, RunEventLines
from cramera.process_sessions import ProcessSession
from cramera_protocol.plan_builder import (
    ArmHaltLine,
    DemoDocument,
    DemoOption,
    RunEvent,
    RunEventKind,
    RunMode,
    RunState,
    RunStatus,
    SafetyStop,
    StepState,
)
from cramera_protocol.robot_profile import ExecutorKind

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

ARM_HALT_STAND_IN = DATASET / "arm_halt_stand_in.py"
"""
A stand-in for the plan builder's halt of the real robot's arms.
"""

STUBBORN_TIMEOUT = 0.5
"""
How long a demo that ignores termination is given before it is killed, in seconds.
"""


def arm_halt_stand_in(tmp_path: Path, answer: str = "acknowledged") -> list[str]:
    """
    :param tmp_path: The test's directory, where the stand-in reports.
    :param answer: ``acknowledged``, or anything else for a halt nobody acknowledged.
    :return: The command of a stand-in of the plan builder's halt of the arms.
    """
    return [sys.executable, str(ARM_HALT_STAND_IN), str(tmp_path / "halt"), answer]


def runner_of(tmp_path: Path, template: str, **fields) -> DemoRunner:
    """
    :param tmp_path: The test's directory.
    :param template: The file name of a stand-in template.
    :param fields: Further fields of the runner; the arms are halted by a stand-in
        whose halt is acknowledged unless they say otherwise.
    :return: A runner rendering the stand-in, writing into the test's directory.
    """
    return DemoRunner(
        directory=DemoDirectory(tmp_path / "demos", interpreter=sys.executable),
        port=PORT,
        log_limit=LOG_LIMIT,
        template=DemoTemplate(TEMPLATES / template),
        **{"arm_halt": arm_halt_stand_in(tmp_path), **fields},
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


@pytest.mark.parametrize(
    "mode, executor, expected",
    [
        (RunMode.PERFORM, None, ExecutorKind.KINEMATIC),
        (RunMode.SIMULATE, None, ExecutorKind.PHYSICS),
        (RunMode.PERFORM, ExecutorKind.PHYSICS, ExecutorKind.PHYSICS),
    ],
)
def test_a_performing_demo_is_told_how_to_execute_the_plan(
    runner, demo, mode, executor, expected
):
    runner.start(demo, mode, executor)
    ended = wait_for(runner, lambda status: status.state is not RunState.RUNNING)
    assert ended.mode is mode
    assert f"{DemoOption.EXECUTOR} {expected}" in ended.log


def test_a_staged_demo_executes_nothing(runner, demo):
    runner.start(demo, RunMode.STAGE, ExecutorKind.PHYSICS)
    shown = wait_for(runner, lambda status: DemoOption.STAGE in status.log)
    assert DemoOption.EXECUTOR not in shown.log


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


def stand_in_giskard(status: RunStatus) -> Path:
    """
    :return: Where the stand-in Giskard the stuck stand-in run printed lives.
    """
    [line] = [line for line in status.log.splitlines() if line.startswith("giskard ")]
    return Path("/proc") / line.split()[1]


def test_a_real_run_ignoring_termination_is_killed_its_giskard_ended_and_the_arms_halted(
    tmp_path, demo
):
    runner = runner_of(
        tmp_path, "stuck_real_run_demo.py", stop_timeout=STUBBORN_TIMEOUT
    )
    runner.start(demo, RunMode.ROBOT, ExecutorKind.REAL)
    giskard = stand_in_giskard(wait_for(runner, lambda status: "giskard" in status.log))
    started = time.monotonic()
    stopped = runner.stop()

    assert time.monotonic() - started < 10
    assert stopped.state is RunState.STOPPED
    assert stopped.return_code == -signal.SIGKILL
    assert not giskard.exists()
    assert (tmp_path / "halt").read_text() == "giskard ended"
    assert ArmHaltLine.HALTED in stopped.log


def test_a_stopped_real_run_whose_halt_nobody_acknowledged_is_not_reported_stopped(
    tmp_path, demo
):
    runner = runner_of(
        tmp_path,
        "stuck_real_run_demo.py",
        stop_timeout=STUBBORN_TIMEOUT,
        arm_halt=arm_halt_stand_in(tmp_path, answer="silence"),
    )
    runner.start(demo, RunMode.ROBOT, ExecutorKind.REAL)
    wait_for(runner, lambda status: "giskard" in status.log)
    stopped = runner.stop()

    assert stopped.state is RunState.HALT_UNCONFIRMED
    assert ArmHaltLine.NOT_HALTED in stopped.log


def test_a_simulated_run_is_stopped_without_halting_the_real_arms(tmp_path, demo):
    runner = runner_of(
        tmp_path, "stuck_real_run_demo.py", stop_timeout=STUBBORN_TIMEOUT
    )
    runner.start(demo, RunMode.ROBOT, ExecutorKind.PHYSICS)
    giskard = stand_in_giskard(wait_for(runner, lambda status: "giskard" in status.log))
    stopped = runner.stop()
    giskard_lived = giskard.exists()
    ProcessSession(int(giskard.name)).end()

    assert stopped.state is RunState.STOPPED
    assert not (tmp_path / "halt").exists()
    assert giskard_lived


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


# %% safety stops


@pytest.fixture
def safety_stopped(tmp_path, demo) -> DemoRunner:
    """
    :return: A runner whose demo was cancelled by a safety stop.
    """
    runner = runner_of(tmp_path, "safety_stopped_demo.py")
    runner.start(demo, RunMode.SIMULATE)
    wait_for(runner, lambda status: status.state is not RunState.RUNNING)
    yield runner
    runner.stop()


def test_a_demo_cancelled_by_a_safety_stop_names_the_broken_limit(safety_stopped):
    status = safety_stopped.status()
    assert status.state is RunState.SAFETY_STOPPED
    assert status.safety_stop == SafetyStop.from_output(status.log)
    assert not status.safety_stop.acknowledged


@pytest.mark.parametrize("mode", list(RunMode))
def test_no_demo_starts_before_the_safety_stop_is_acknowledged(
    safety_stopped, demo, mode
):
    with pytest.raises(SafetyStopNotAcknowledged):
        safety_stopped.start(demo, mode)
    assert safety_stopped.status().state is RunState.SAFETY_STOPPED


def test_a_new_run_starts_from_the_beginning_once_the_stop_is_acknowledged(
    safety_stopped, demo
):
    acknowledged = safety_stopped.acknowledge()
    started = safety_stopped.start(demo, RunMode.SIMULATE)

    assert acknowledged.safety_stop.acknowledged
    assert started.state is RunState.RUNNING and started.safety_stop is None


def test_acknowledging_without_a_demo_leaves_the_runner_idle(runner):
    assert runner.acknowledge() == RunStatus()


# %% saving the record


@pytest.fixture
def saving(tmp_path, demo) -> DemoRunner:
    """
    :return: A runner whose demo's run is over and which saves the run's record until
        it is stopped.
    """
    runner = runner_of(tmp_path, "saving_demo.py")
    runner.start(demo, RunMode.ROBOT, ExecutorKind.REAL)
    wait_for(runner, lambda status: status.state is not RunState.RUNNING)
    yield runner
    runner.stop()


def test_a_demo_saving_its_record_no_longer_runs(saving):
    assert saving.status().state is RunState.SAVING


@pytest.mark.parametrize("mode", list(RunMode))
def test_no_demo_starts_while_the_record_is_saved(saving, demo, mode):
    with pytest.raises(RunRecordSaving):
        saving.start(demo, mode)
    assert saving.status().state is RunState.SAVING


def test_no_validation_starts_while_the_record_is_saved(saving):
    with pytest.raises(RunRecordSaving):
        saving.refuse_to_start()


@pytest.fixture
def running(tmp_path) -> DemoRunner:
    """
    :return: A runner of the stand-in that runs in every mode until it is stopped; its
        demo is stopped after the test.
    """
    runner = runner_of(tmp_path, "running_demo.py")
    yield runner
    runner.stop()


@pytest.mark.parametrize(
    "mode, executor",
    [
        (RunMode.PERFORM, None),
        (RunMode.SIMULATE, None),
        (RunMode.ROBOT, ExecutorKind.PHYSICS),
        (RunMode.ROBOT, ExecutorKind.REAL),
    ],
)
def test_no_validation_starts_while_a_plan_runs(running, demo, mode, executor):
    running.start(demo, mode, executor)
    with pytest.raises(PlanRunning):
        running.refuse_to_validate()
    assert running.status().state is RunState.RUNNING


def test_a_validation_starts_beside_a_staged_scene_and_after_a_run(running, demo):
    running.start(demo, RunMode.STAGE)
    assert running.refuse_to_validate() is running.current
    running.start(demo, RunMode.ROBOT, ExecutorKind.REAL)
    running.stop()
    assert running.refuse_to_validate() is running.current


def test_refusing_a_validation_refuses_it_while_the_record_is_saved(saving):
    with pytest.raises(RunRecordSaving):
        saving.refuse_to_validate()


def test_a_demo_saving_its_record_can_be_stopped(saving):
    assert saving.stop().state is RunState.STOPPED


def test_a_demo_that_saved_its_record_finished(tmp_path, demo):
    runner = runner_of(tmp_path, "saved_demo.py")
    runner.start(demo, RunMode.ROBOT, ExecutorKind.REAL)
    ended = wait_for(runner, lambda status: status.return_code is not None)
    runner.stop()

    assert ended.state is RunState.FINISHED, ended.log


def test_a_record_that_could_not_be_saved_is_reported(tmp_path, demo):
    runner = runner_of(tmp_path, "save_failing_demo.py")
    runner.start(demo, RunMode.ROBOT, ExecutorKind.REAL)
    ended = wait_for(runner, lambda status: status.return_code is not None)
    runner.stop()

    assert ended.state is RunState.SAVE_FAILED
    assert "No space left on device" in ended.log


# %% output


def test_the_log_drops_its_oldest_bytes_beyond_the_limit():
    log = OutputLog(limit=4)
    log.append(b"abc")
    log.append(b"def")
    assert log.text() == "cdef"


# %% run events


def test_a_demo_reports_its_events_apart_from_its_log(tmp_path, demo):
    runner = runner_of(tmp_path, "reporting_demo.py")
    runner.start(demo, RunMode.SIMULATE)
    ended = wait_for(runner, lambda status: status.state is not RunState.RUNNING)
    runner.stop()

    assert ended.state is RunState.FINISHED, ended.log
    assert ended.events == [
        RunEvent(kind=RunEventKind.STEP, step="step_1", state=StepState.PENDING),
        RunEvent(
            kind=RunEventKind.STEP,
            step="step_1",
            state=StepState.DONE,
            attempt=1,
            attempts=3,
        ),
    ]
    assert ended.log == (
        "building the world\n[run log] step_1: attempt 1/3 succeeded\n"
    )


def test_events_are_kept_however_little_of_the_log_is():
    log = OutputLog(limit=4)
    event = RunEvent(kind=RunEventKind.STEP, step="step_1", state=StepState.RUNNING)
    log.append(f"{event.to_output_line()}\nabcdef\n".encode())
    assert log.events() == [event]
    assert log.text() == "def\n"


def test_an_unfinished_line_passes_unless_it_may_report_an_event():
    lines = RunEventLines()
    assert lines.split(b"progress 10%") == b"progress 10%"
    assert lines.split(b"[run event] within a line\n") == b"[run event] within a line\n"
    assert lines.split(b"[run ev") == b""
    assert lines.split(b"ent] garbled\n") == b"[run event] garbled\n"
    assert lines.events == []
