"""
Whether a run's grasps turn the camera to their object and detect it before the final
approach: a robot whose camera turns does, as the robot profile's camera mount says or,
without one, as a robot with a torso does.
"""

from __future__ import annotations

import json

import pytest

from coraplex.robot_plans.plan_transformations import DetectBeforeGrasp
from cramera_bridge.plans.demo import PlannedTaskDemo
from cramera_protocol.plan_builder import DemoDocument, PlanDocument
from cramera_protocol.robot_profile import CameraMount, PerceptionSettings, RuntimeCheck

from ..dataset.bundles import DATASET

PR2_PLAN = DATASET / "plans" / "pick_and_place.json"
"""
A PR2, which has a torso, picking and placing an object.
"""


@pytest.fixture(scope="module")
def pr2_plan() -> PlanDocument:
    """
    :return: The PR2's plan.
    """
    return PlanDocument.from_json(json.loads(PR2_PLAN.read_text("utf-8")))


def detects_before_grasp(document: DemoDocument) -> bool:
    """
    :param document: A plan and the robot profile's settings.
    :return: Whether a run of it detects each grasp's object before the final approach.
    """
    demo = PlannedTaskDemo.of_document(document, port=0)
    performance = demo.performance(demo.build_context(demo.build_world()))
    return any(
        isinstance(transformation, DetectBeforeGrasp)
        for transformation in performance.plan_transformations
    )


LENIENT = PerceptionSettings(runtime_check=RuntimeCheck.LENIENT)
"""
A perception that lets a run act where it last knew an object.
"""


def test_a_robot_with_a_torso_turns_its_camera_when_its_profile_names_no_mount(
    pr2_plan,
):
    assert detects_before_grasp(DemoDocument(plan=pr2_plan, perception=LENIENT))


def test_a_robot_whose_profile_says_its_camera_is_fixed_does_not_turn_it(pr2_plan):
    assert not detects_before_grasp(
        DemoDocument(
            plan=pr2_plan, perception=LENIENT, camera_mount=CameraMount.FIXED
        )
    )


def test_a_strict_runtime_check_detects_before_every_grasp(pr2_plan):
    assert detects_before_grasp(
        DemoDocument(plan=pr2_plan, camera_mount=CameraMount.FIXED)
    )
