"""
The grasp a pick takes of a cube taken from above: Tracy's grippers close along the
cube's own x-axis, as they always have; a robot profile may have the hand close along
the cube's y-axis instead, as the Walker S2's hands need.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from coraplex.perception import WorldPerception
from cramera_bridge.plans.demo import PlannedTaskDemo
from cramera_bridge.plans.grounding import PlanGrounding
from cramera_bridge.plans.objects import LIBRARY_VARIABLE
from cramera_bridge.plans.site import RobotSite
from cramera_protocol.plan_builder import DemoDocument, PlanDocument
from cramera_protocol.robot_profile import GraspClosingAxis
from semantic_digital_twin.robots.tracy import Tracy

from ..dataset.bundles import DATASET

pytestmark = pytest.mark.skipif(
    not Tracy.is_description_installed(),
    reason="iai_tracy_description is not installed",
)

TRACY_TOWER = DATASET / "plans" / "tracy_tower.json"
"""
Tracy puts the red cube into the centre zone and stacks the yellow and the blue cube on
top of it.
"""

PICK_STEP = "step_2"
"""
The tower's pick of the red cube.
"""


@pytest.fixture(autouse=True)
def cube_library(monkeypatch) -> None:
    """
    Offer the cube library the plans' cubes come from.
    """
    monkeypatch.setenv(LIBRARY_VARIABLE, str(DATASET / "cube_library"))


def object_closing_axis(document: DemoDocument) -> np.ndarray:
    """
    :param document: A plan whose step :data:`PICK_STEP` picks a cube.
    :return: The axis the grasp of that pick closes along, in the cube's own frame.
    """
    demo = PlannedTaskDemo.of_document(document, port=0)
    grounding = PlanGrounding(
        context=demo.build_context(demo.build_world()),
        bodies=dict(demo.bodies),
        actions=demo.discovered_actions,
        perception=WorldPerception(),
        site=RobotSite.of_demo(document),
    )
    [pick] = [
        step
        for step in document.plan.performing_robot().steps
        if step.identifier == PICK_STEP
    ]
    arguments = grounding.arguments(pick)
    [grasp_field] = [
        field
        for field in arguments.action.schema.fields
        if field.name == "grasp"
    ]
    grasp = arguments.body(grasp_field, pick.values["grasp"])
    cube = grasp.graspable.root
    world = cube._world
    cube_R_grasp = world.transform(grasp.grasp_pose, cube).to_np()[:3, :3]
    # a grasp pose's x-axis is its approach, its y-axis the direction it closes along
    return cube_R_grasp[:, 1]


@pytest.fixture
def tower() -> PlanDocument:
    """
    :return: Tracy's tower plan.
    """
    return PlanDocument.from_json(json.loads(TRACY_TOWER.read_text("utf-8")))


def test_tracys_gripper_closes_along_the_cubes_x_axis(tower):
    closing = object_closing_axis(DemoDocument(plan=tower))

    assert np.abs(closing) == pytest.approx([1.0, 0.0, 0.0], abs=1e-6)


def test_a_profile_closing_its_hand_along_y_grasps_the_cube_along_its_y_axis(tower):
    closing = object_closing_axis(
        DemoDocument(plan=tower, grasp_closing_axis=GraspClosingAxis.Y)
    )

    assert np.abs(closing) == pytest.approx([0.0, 1.0, 0.0], abs=1e-6)
