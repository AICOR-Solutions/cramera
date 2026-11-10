"""
Running a plan's steps with retries: the run log every attempt is written to, a step
keeping its object in view of Tracy's fixed camera, a cube nudged while the plan runs in
MuJoCo, which the step acting on it grounds anew, and a cube taken away, whose step is
given up once it used up its attempts.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field

import pytest

from cramera_bridge.exceptions import StepAbandoned
from cramera_bridge.execution import PhysicalExecution
from cramera_bridge.plans.demo import PlannedTaskDemo
from cramera_bridge.plans.objects import LIBRARY_VARIABLE
from cramera_bridge.plans.run_log import (
    AttemptOutcome,
    LookAt,
    ObjectPerceived,
    RunLog,
    RunLogEntry,
    SafetyStopped,
    StepAttempt,
    StepScheduled,
    StepStarted,
    View,
)
from cramera_bridge.plans.step_run import Alternative
from cramera_protocol.geometry import FloorRectangle
from cramera_protocol.plan_builder import (
    DemoDocument,
    MonitorObservation,
    PlanDocument,
    RunEvent,
    RunEventKind,
    RunMonitor,
    StepState,
)
from cramera_protocol.robot_profile import Zone
from cramera_protocol.viewer import EnvironmentVariable
from krrood_spatial_math.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.robots.tracy import Tracy
from semantic_digital_twin.world_description.world_entity import Body

from ..dataset.bundles import DATASET

CUBE_LIBRARY = DATASET / "cube_library"
"""
A red, a yellow and a blue cube, each named by its color.
"""

NUDGED_CUBES = DATASET / "plans" / "tracy_nudged_cubes.json"
"""
Tracy detects the red cube and puts it into the centre zone, then the blue cube into the
right tray, keeping each in view while it is picked up.
"""

ZONES = [
    Zone(
        identifier="center",
        label="Center",
        area=FloorRectangle(min_x=0.6, max_x=0.8, min_y=-0.1, max_y=0.1),
    ),
    Zone(
        identifier="right_tray",
        label="Right tray",
        area=FloorRectangle(min_x=0.6, max_x=0.8, min_y=-0.5, max_y=-0.3),
    ),
]
"""
The zones of Tracy's profile the plan puts the cubes into.
"""

NUDGE = 0.05
"""
How far, in metres, the red cube is pushed along the table once it was detected.
"""

FAR_AWAY = (3.0, 3.0, 0.03)
"""
Where the blue cube is taken to once the red one was put down: on the floor, beyond what
Tracy's camera sees and its arms reach.
"""

# %% the run log


def test_every_entry_is_a_line_of_the_runs_output():
    stream = io.StringIO()
    run_log = RunLog(stream=stream)
    entry = StepAttempt(
        step="step_3", number=1, attempts=3, outcome=AttemptOutcome.SUCCEEDED
    )

    run_log.write(entry)

    assert stream.getvalue() == (
        f"{RunLog.line_prefix} {entry.line()}\n{entry.event().to_output_line()}\n"
    )
    assert run_log.entries == [entry]
    assert run_log.events() == [entry.event()]


@pytest.mark.parametrize(
    "outcome, state",
    [
        (AttemptOutcome.SUCCEEDED, StepState.DONE),
        (AttemptOutcome.RETRYING, StepState.RETRYING),
        (AttemptOutcome.ABORTED, StepState.FAILED),
        (AttemptOutcome.STOPPED, StepState.FAILED),
    ],
)
def test_an_attempt_ends_its_step_in_the_state_of_its_outcome(outcome, state):
    entry = StepAttempt(
        step="step_3", number=2, attempts=3, outcome=outcome, arm="right"
    )
    assert entry.event() == RunEvent(
        kind=RunEventKind.STEP,
        step="step_3",
        state=state,
        attempt=2,
        attempts=3,
        arm="right",
    )


def test_a_step_is_pending_then_running_with_the_arm_its_grounding_chose():
    scheduled = StepScheduled(step="step_3", arm="left")
    started = StepStarted(step="step_3", number=1, attempts=3, arm="left")
    assert scheduled.event().state is StepState.PENDING
    assert started.event().state is StepState.RUNNING
    assert "left arm" in scheduled.line() and "left arm" in started.line()


def test_a_perceived_object_and_a_safety_stop_are_events_of_their_own():
    perceived = ObjectPerceived(step="step_2", target="red_cube", color="red")
    stopped = SafetyStopped(constraint="Left arm workspace", step="step_3")
    assert perceived.event().kind is RunEventKind.PERCEIVED
    assert perceived.line() == "step_2: perceived red_cube (red)"
    assert stopped.event() == RunEvent(
        kind=RunEventKind.SAFETY_STOP, step="step_3", constraint="Left arm workspace"
    )


def test_a_look_at_says_whether_its_target_is_in_view():
    entry = LookAt(step="step_3", target="red_cube", view=View.IN_VIEW)
    assert f"look-at: {View.IN_VIEW}" in entry.line()
    assert entry.event().monitor is RunMonitor.LOOK_AT
    assert entry.event().observation is MonitorObservation.HOLDS


def test_a_failed_attempt_names_why_and_what_the_next_one_does():
    entry = StepAttempt(
        step="step_3",
        number=1,
        attempts=3,
        outcome=AttemptOutcome.RETRYING,
        reason="the cube moved.",
        next_attempt=Alternative.OTHER_ARM.value,
    )
    assert entry.line() == (
        f"step_3: attempt 1/3 {AttemptOutcome.RETRYING}: the cube moved. "
        f"Next attempt {Alternative.OTHER_ARM.value}."
    )


# %% nudging and taking away cubes while the plan runs in physics


@dataclass
class Disturbance:
    """
    Moves cubes of the running plan once the run log says a step succeeded.
    """

    demo: PlannedTaskDemo
    """
    The running demo.
    """

    moves: dict[str, tuple[str, tuple[float, float, float]]]
    """
    By the identity of the step after whose success it moves: the identity of the cube
    and the offset it is moved by.
    """

    done: list[str] = field(default_factory=list)
    """
    The steps after which a cube was moved.
    """

    def __call__(self, entry: RunLogEntry) -> None:
        if not isinstance(entry, StepAttempt) or entry.step not in self.moves:
            return
        if entry.outcome is not AttemptOutcome.SUCCEEDED or entry.step in self.done:
            return
        identifier, offset = self.moves[entry.step]
        self.move(self.demo.bodies[identifier], offset)
        self.done.append(entry.step)

    @staticmethod
    def move(cube: Body, offset: tuple[float, float, float]) -> None:
        """
        Move a free cube by an offset in the world's coordinates.
        """
        world = cube._world
        position = cube.global_pose.position
        cube.parent_connection.origin = HomogeneousTransformationMatrix.from_xyz_rpy(
            float(position.x) + offset[0],
            float(position.y) + offset[1],
            float(position.z) + offset[2],
            reference_frame=world.root,
        )
        world.notify_state_change()


@dataclass
class DisturbedRun:
    """
    What a run of the plan wrote to its log, and how it ended.
    """

    entries: list[RunLogEntry]
    """
    The run log.
    """

    failure: StepAbandoned
    """
    The step the run gave up.
    """

    def attempts_at(self, step: str) -> list[StepAttempt]:
        """
        :return: The attempts at a step, in order.
        """
        return [
            entry
            for entry in self.entries
            if isinstance(entry, StepAttempt) and entry.step == step
        ]


@pytest.fixture(scope="module")
def disturbed_run(tmp_path_factory) -> DisturbedRun:
    """
    :return: The plan run in MuJoCo, the red cube nudged once it was detected and the
        blue one taken away once the red one was put down.
    """
    if not Tracy.is_description_installed():
        pytest.skip("iai_tracy_description is not installed")
    data = tmp_path_factory.mktemp("data")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(LIBRARY_VARIABLE, str(CUBE_LIBRARY))
        patch.setenv(EnvironmentVariable.DATA, str(data))
        plan = PlanDocument.from_json(json.loads(NUDGED_CUBES.read_text("utf-8")))
        demo = PlannedTaskDemo.of_document(DemoDocument(plan=plan, zones=ZONES), port=0)
        demo.execution = PhysicalExecution()
        far_away = (FAR_AWAY[0] - 0.55, FAR_AWAY[1] - 0.30, FAR_AWAY[2] - 0.906)
        demo.run_log.listeners.append(
            Disturbance(
                demo,
                {
                    "step_2": ("red_cube", (0.0, -NUDGE, 0.0)),
                    "step_4": ("blue_cube", far_away),
                },
            )
        )
        with pytest.raises(StepAbandoned) as abandoned:
            demo.run()
    return DisturbedRun(entries=demo.run_log.entries, failure=abandoned.value)


def test_a_step_keeping_its_cube_in_view_reports_it_in_view(disturbed_run):
    looks = [entry for entry in disturbed_run.entries if isinstance(entry, LookAt)]
    assert LookAt(step="step_3", target="detected:step_2", view=View.IN_VIEW) in looks


def test_a_cube_nudged_once_detected_is_grounded_anew_and_picked_up(disturbed_run):
    first, second = disturbed_run.attempts_at("step_3")
    assert first.outcome is AttemptOutcome.RETRYING
    assert first.next_attempt == Alternative.REDETECTION.value
    assert second.number == 2
    assert second.outcome is AttemptOutcome.SUCCEEDED
    [placed] = disturbed_run.attempts_at("step_4")
    assert placed.outcome is AttemptOutcome.SUCCEEDED


def test_a_cube_taken_away_aborts_the_plan_once_its_step_used_up_its_attempts(
    disturbed_run,
):
    attempts = disturbed_run.attempts_at("step_5")
    assert [attempt.number for attempt in attempts] == [1, 2, 3]
    assert attempts[-1].outcome is AttemptOutcome.ABORTED
    assert disturbed_run.failure == StepAbandoned(
        "step_5", attempts[-1].attempts, attempts[-1].reason
    )


def test_the_run_events_follow_every_step_through_its_retries(disturbed_run):
    events = [entry.event() for entry in disturbed_run.entries]
    states = {
        step: [
            event.state
            for event in events
            if event.kind is RunEventKind.STEP and event.step == step
        ]
        for step in ("step_2", "step_3", "step_5")
    }
    assert states["step_2"] == [StepState.PENDING, StepState.RUNNING, StepState.DONE]
    assert StepState.RETRYING in states["step_3"]
    assert states["step_3"][-1] is StepState.DONE
    assert states["step_5"].count(StepState.RETRYING) == 2
    assert states["step_5"][-1] is StepState.FAILED
    [perceived, *_] = [e for e in events if e.kind is RunEventKind.PERCEIVED]
    assert (perceived.target, perceived.color) == ("red_cube", "red")
    [picked] = [
        event
        for event in events
        if event.step == "step_3" and event.state is StepState.DONE
    ]
    assert picked.arm in ("left", "right")
