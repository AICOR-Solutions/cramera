"""
Grounding and validating a plan of Tracy's: its steps are tried in a copy of the twin
without moving anything, a pick leaving its arm open is given the arm that reaches, the
nearer one first, a cube out of reach fails the pick as unreachable, and the plan then
runs with the arm its grounding chose.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from importlib.util import find_spec

import numpy as np
import pytest

from coraplex.perception import WorldPerception
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from cramera_bridge.exceptions import StepNotGrounded
from cramera_bridge.execution import PERCEPTION_ENGINE_VARIABLE
from cramera_bridge.geometry import NumericPose
from cramera_bridge.plans.arms import Arms
from cramera_bridge.plans.demo import PlannedTaskDemo
from cramera_bridge.plans.grounding import PlanGrounding
from cramera_bridge.plans.objects import LIBRARY_VARIABLE
from cramera_bridge.plans.steps import StepActions
from cramera_bridge.plans.validating import PlanValidator
from cramera_protocol.geometry import Pose
from cramera_protocol.plan_builder import DemoDocument, PlanDocument
from cramera_protocol.validation import (
    StepFailureReason,
    StepVerdict,
    ValidationOrder,
    ValidationReport,
)
from cramph.composites import StatementNode
from semantic_digital_twin.robots.tracy import Tracy

from ..dataset.bundles import DATASET

pytestmark = pytest.mark.skipif(
    not Tracy.is_description_installed(),
    reason="iai_tracy_description is not installed",
)

CUBE_LIBRARY = DATASET / "cube_library"
"""
A red, a yellow and a blue cube, each named by its color.
"""

TRACY_PICK_AND_PLACE = DATASET / "plans" / "tracy_pick_and_place.json"
"""
Tracy picks the red cube with the arm that reaches it and places it.
"""

TRACY_CUBES = DATASET / "plans" / "tracy_cubes.json"
"""
Tracy detects the red cube on its table and picks it up.
"""

OUT_OF_REACH = (1.5, 0.1)
"""
Where on the floor beyond Tracy's table no arm reaches a cube.
"""

RIGHT_ARM_ONLY = (0.55, -1.2)
"""
Where beside Tracy's table only its right arm reaches a cube.
"""

RIGHT_OF_CENTRE = (0.55, -0.15)
"""
Where on Tracy's table both arms reach a cube, the right one from nearer.
"""

# %% fixtures


@pytest.fixture(autouse=True)
def cube_library(monkeypatch) -> None:
    """
    Offer the cube library the plans' cubes come from.
    """
    monkeypatch.setenv(LIBRARY_VARIABLE, str(CUBE_LIBRARY))


@pytest.fixture
def pick_and_place() -> PlanDocument:
    """
    :return: The plan of Tracy picking the red cube with the arm that reaches it.
    """
    return PlanDocument.from_json(json.loads(TRACY_PICK_AND_PLACE.read_text("utf-8")))


def with_red_cube_at(plan: PlanDocument, x: float, y: float) -> PlanDocument:
    """
    :return: The plan with its red cube standing at the position on the table's height.
    """
    [red, *others] = plan.objects
    pose = red.pose.to_json()
    return replace(plan, objects=[replace(red, pose=Pose(x, y, *pose[2:])), *others])


def validated(plan: PlanDocument) -> ValidationReport:
    """
    :return: The report of the plan's validation.
    """
    return PlanValidator(ValidationOrder(demo=DemoDocument(plan=plan))).validate()


# %% validating


def test_a_plan_in_reach_passes_with_the_nearer_arm_that_reaches(pick_and_place):
    report = validated(pick_and_place)

    assert report.passed
    assert [step.verdict for step in report.steps] == [StepVerdict.VALID] * 4
    assert report.steps[1].arm == Arms.LEFT.name.lower()


def test_a_cube_out_of_reach_fails_the_pick_as_unreachable(pick_and_place):
    report = validated(with_red_cube_at(pick_and_place, *OUT_OF_REACH))

    assert not report.passed
    pick, *later = report.steps[1:]
    assert pick.verdict is StepVerdict.FAILED
    assert pick.reason is StepFailureReason.UNREACHABLE
    assert [step.verdict for step in later] == [StepVerdict.UNCHECKED] * 2


def test_a_cube_only_the_right_arm_reaches_is_picked_with_it(pick_and_place):
    report = validated(with_red_cube_at(pick_and_place, *RIGHT_ARM_ONLY))

    assert report.passed
    assert report.steps[1].arm == Arms.RIGHT.name.lower()


def test_a_cube_both_arms_reach_is_picked_with_the_nearer_one(pick_and_place):
    report = validated(with_red_cube_at(pick_and_place, *RIGHT_OF_CENTRE))

    assert report.passed
    assert report.steps[1].arm == Arms.RIGHT.name.lower()


def test_validating_moves_nothing_of_the_twin(pick_and_place):
    demo = PlannedTaskDemo.of_document(DemoDocument(plan=pick_and_place), port=0)
    world = demo.build_world()
    context = demo.build_context(world)
    before = world.state.positions.copy()

    PlanGrounding(
        context=context,
        bodies=dict(demo.bodies),
        actions=demo.discovered_actions,
        perception=WorldPerception(),
    ).ground(demo.steps())

    np.testing.assert_array_equal(world.state.positions, before)


# %% running with the arm chosen


def test_a_step_leaving_its_arm_open_is_a_statement(pick_and_place):
    demo = PlannedTaskDemo.of_document(DemoDocument(plan=pick_and_place), port=0)
    world = demo.build_world()
    context = demo.build_context(world)
    pick = demo.steps()[1]

    node = StepActions(context, demo.bodies, demo.discovered_actions).action(pick)

    assert isinstance(node, StatementNode)


def test_a_plan_runs_with_the_arm_its_grounding_chose(pick_and_place):
    demo = PlannedTaskDemo.of_document(
        DemoDocument(plan=with_red_cube_at(pick_and_place, *RIGHT_ARM_ONLY)), port=0
    )
    world = demo.build_world()
    context = demo.build_context(world)

    plan = demo.build_plan(context)

    step = plan.nodes[1]
    [pick] = [
        node for node in [step, *step.descendants] if isinstance(node, PickUpAction)
    ]
    assert pick.arm is context.robot.get_right_arm_if_specified()


def test_a_plan_no_arm_reaches_is_refused_before_it_runs(pick_and_place):
    demo = PlannedTaskDemo.of_document(
        DemoDocument(plan=with_red_cube_at(pick_and_place, *OUT_OF_REACH)), port=0
    )
    world = demo.build_world()

    with pytest.raises(StepNotGrounded):
        demo.build_plan(demo.build_context(world))


# %% detecting through the simulated camera


@pytest.mark.skipif(
    find_spec("robokudo_msgs") is None, reason="RoboKudo's messages are not installed"
)
def test_a_detection_the_simulated_camera_sees_is_valid_and_its_pick_holds(tmp_path):
    cubes = PlanDocument.from_json(json.loads(TRACY_CUBES.read_text("utf-8")))
    order_file = tmp_path / "order.json"
    report_file = tmp_path / "report.json"
    order = ValidationOrder(
        demo=DemoDocument(plan=cubes), simulated_objects=cubes.objects
    )
    order_file.write_text(json.dumps(order.to_json()), encoding="utf-8")

    finished = subprocess.run(
        [
            sys.executable,
            "-m",
            "cramera_bridge.plans.validating",
            str(order_file),
            str(report_file),
        ],
        env={
            **os.environ,
            LIBRARY_VARIABLE: str(CUBE_LIBRARY),
            PERCEPTION_ENGINE_VARIABLE: "tracy_cubes",
        },
        capture_output=True,
        timeout=600,
    )

    assert finished.returncode == 0, finished.stderr.decode()[-4000:]
    report = ValidationReport.from_json(json.loads(report_file.read_text("utf-8")))
    assert [step.verdict for step in report.steps] == [StepVerdict.VALID] * 2
