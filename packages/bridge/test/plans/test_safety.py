"""
A plan held to the safety limits of Tracy's profile in MuJoCo: a workspace box the left
arm's tool may not leave below a height its pick reaches down past, which stops the run
at the box's boundary, without another attempt at the pick.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass

import numpy as np
import pytest

from cramera_bridge.execution import PhysicalExecution
from cramera_bridge.plans.demo import PlannedTaskDemo
from cramera_bridge.plans.objects import LIBRARY_VARIABLE
from cramera_bridge.plans.command import PlanDemoCommand
from cramera_bridge.plans.run_log import (
    AttemptOutcome,
    RunLog,
    SafetyStopped,
    StepAttempt,
)
from cramera_protocol.geometry import AxisAlignedBox
from cramera_protocol.plan_builder import (
    DemoDocument,
    MonitorObservation,
    PlanDocument,
    RunEvent,
    RunEventKind,
    RunMonitor,
    SafetyStop,
    StepState,
)
from cramera_protocol.robot_profile import ArmWorkspace, SafetyLimits
from cramera_protocol.viewer import EnvironmentVariable
from giskardpy.motion_statechart.exceptions import SafetyConstraintViolated
from semantic_digital_twin.robots.tracy import Tracy

from ..dataset.bundles import DATASET

CUBE_LIBRARY = DATASET / "cube_library"
"""
A red, a yellow and a blue cube, each named by its color.
"""

PICK = DATASET / "plans" / "tracy_pick.json"
"""
Tracy parks its arms, then picks up the red cube with its left arm.
"""

LOW_WORKSPACE = ArmWorkspace(
    arm="left",
    label="Left arm workspace",
    box=AxisAlignedBox(
        min_x=0.3, max_x=1.2, min_y=-0.3, max_y=0.7, min_z=1.1, max_z=1.6
    ),
)
"""
A workspace holding the parked left tool, 1.37 m high, but none of the table below
1.1 m, which the pick reaches down past to the cube.
"""

BOUNDARY_TOLERANCE = 0.02
"""
How far, in metres, the tool may end beyond the box's boundary once stopped.
"""


@dataclass
class StoppedRun:
    """
    How a run held to the low workspace ended.
    """

    demo: PlannedTaskDemo
    """
    The demo, its world as the run left it.
    """

    violation: SafetyConstraintViolated
    """
    What stopped the run.
    """

    def tool_height(self) -> float:
        """
        :return: How high the left tool stands where the run stopped, in the plan's
            frame.
        """
        world = self.demo.bodies["red_cube"]._world
        [tracy] = world.get_semantic_annotations_by_type(Tracy)
        tool = tracy.left_arm.end_effector.tool_frame
        return float(world.compute_forward_kinematics_np(world.root, tool)[2, 3])


@pytest.fixture(scope="module")
def stopped_run(tmp_path_factory) -> StoppedRun:
    """
    :return: The pick run in MuJoCo, held to the low workspace and the profile's
        velocity limits.
    """
    if not Tracy.is_description_installed():
        pytest.skip("iai_tracy_description is not installed")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(LIBRARY_VARIABLE, str(CUBE_LIBRARY))
        patch.setenv(EnvironmentVariable.DATA, str(tmp_path_factory.mktemp("data")))
        plan = PlanDocument.from_json(json.loads(PICK.read_text("utf-8")))
        safety = SafetyLimits(
            workspaces=[LOW_WORKSPACE],
            maximum_joint_velocity=0.5,
            maximum_tool_velocity=0.5,
        )
        demo = PlannedTaskDemo.of_document(
            DemoDocument(plan=plan, safety=safety), port=0
        )
        demo.execution = PhysicalExecution()
        with pytest.raises(SafetyConstraintViolated) as violated:
            demo.run()
    return StoppedRun(demo=demo, violation=violated.value)


def test_leaving_the_workspace_stops_the_run_naming_the_box(stopped_run):
    assert stopped_run.violation.constraint == LOW_WORKSPACE.label


def test_the_tool_stops_at_the_boundary_of_the_box(stopped_run):
    overshoot = LOW_WORKSPACE.box.min_z - stopped_run.tool_height()
    print(f"the tool stopped {overshoot * 1000:.1f} mm beyond the box")
    assert 0.0 <= overshoot < BOUNDARY_TOLERANCE


def test_a_safety_stop_is_never_attempted_again(stopped_run):
    outcomes = [
        entry.outcome
        for entry in stopped_run.demo.run_log.entries
        if isinstance(entry, StepAttempt)
    ]
    assert outcomes == [AttemptOutcome.SUCCEEDED, AttemptOutcome.STOPPED]


def test_the_run_events_tell_which_step_the_safety_stop_ended(stopped_run):
    events = stopped_run.demo.run_log.events()
    [watched, *_] = [event for event in events if event.monitor is RunMonitor.SAFETY]
    [stop] = [event for event in events if event.kind is RunEventKind.SAFETY_STOP]
    pick = [
        event.state
        for event in events
        if event.kind is RunEventKind.STEP and event.step == "step_2"
    ]
    assert watched.observation is MonitorObservation.HOLDS
    assert pick == [StepState.PENDING, StepState.RUNNING, StepState.FAILED]
    assert stop == RunEvent(
        kind=RunEventKind.SAFETY_STOP, step="step_2", constraint=LOW_WORKSPACE.label
    )


def test_a_demos_safety_stop_is_reported_as_the_line_the_plan_builder_reads(capsys):
    log = RunLog(stream=io.StringIO(), listeners=[PlanDemoCommand.report_safety_stop])
    log.write(SafetyStopped(constraint=LOW_WORKSPACE.label, step="step_2"))
    assert SafetyStop.from_output(capsys.readouterr().out) == SafetyStop(
        constraint=LOW_WORKSPACE.label
    )
