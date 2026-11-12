"""
A run reporting what RoboKudo answered every detection of its steps: the pick of the
red cube run kinematically, its detections answered by the world model, while RoboKudo's
answers are those of the real table on 2026-11-12, where the red cube validated at one
spot was reported 19 cm away; here 24 cm from where the plan holds it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

pytest.importorskip("robokudo_msgs")

from geometry_msgs.msg import PoseStamped
from robokudo_msgs.msg import ObjectDesignator, ShapeSize
from typing_extensions import List, Optional

from cramera.locations import EnvironmentVariable
from cramera_bridge.execution import KinematicExecution
from cramera_bridge.plans.demo import PlannedTaskDemo
from cramera_bridge.plans.objects import LIBRARY_VARIABLE
from cramera_bridge.plans.perception_reporting import PerceptionReported
from cramera_bridge.plans.robokudo_answers import QueryAnswer
from cramera_protocol.plan_builder import (
    DemoDocument,
    PlanDocument,
    ReportedObjectVerdict,
    RunEventKind,
)
from semantic_digital_twin.robots.tracy import Tracy

from ..dataset.bundles import DATASET

CUBE_LIBRARY = DATASET / "cube_library"
"""
A red, a yellow and a blue cube, each named by its color.
"""

TRACY_PICK = DATASET / "plans" / "tracy_pick.json"
"""
Tracy parks its arms, then picks up the red cube, at x 0.55, y 0.1.
"""


@dataclass
class TableAnswers:
    """
    Answers every query as RoboKudo answered on the real table: the red cube 24 cm from
    where the plan holds it, and the table top as two grey objects.
    """

    demo: PlannedTaskDemo
    """
    The demo whose world names the frame of the answers.
    """

    asked: List[int] = field(default_factory=list)
    """
    How many queries each plan asked.
    """

    def since(self, start: float, count: int, timeout: float) -> List[QueryAnswer]:
        self.asked.append(count)
        return [
            QueryAnswer(accepted=start, ended=True, objects=self.objects())
            for _ in range(count)
        ]

    def objects(self) -> List[ObjectDesignator]:
        """
        :return: The objects RoboKudo reported.
        """
        return [
            self.designator(0.79, 0.145, 0.906, (0.066, 0.061, 0.022), ["red"]),
            self.designator(0.82, 0.3, 0.9, (0.8, 0.5, 0.06), ["grey"]),
            self.designator(0.85, -0.3, 0.9, (0.8, 0.5, 0.08), ["grey"]),
        ]

    def designator(
        self, x: float, y: float, z: float, size: tuple, colors: List[str]
    ) -> ObjectDesignator:
        """
        :return: An object as RoboKudo reports it, in the world's root.
        """
        pose = PoseStamped()
        pose.header.frame_id = str(self.demo.step_run.context.world.root.name)
        pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = x, y, z
        pose.pose.orientation.w = 1.0
        shape = ShapeSize()
        shape.dimensions.x, shape.dimensions.y, shape.dimensions.z = size
        return ObjectDesignator(color=colors, pose=[pose], shape_size=[shape])


@dataclass
class AnsweredKinematicExecution(KinematicExecution):
    """
    Moves kinematically, with RoboKudo's answers of the real table.
    """

    answers: Optional[TableAnswers] = None
    """
    The answers.
    """

    def perception_answers(self) -> Optional[TableAnswers]:
        return self.answers


@pytest.fixture(scope="module")
def reports(tmp_path_factory) -> List[PerceptionReported]:
    """
    :return: What the run of the pick, its arm left open, reported of its detections.
    """
    if not Tracy.is_description_installed():
        pytest.skip("iai_tracy_description is not installed")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(LIBRARY_VARIABLE, str(CUBE_LIBRARY))
        patch.setenv(EnvironmentVariable.DATA, str(tmp_path_factory.mktemp("data")))
        document = json.loads(TRACY_PICK.read_text("utf-8"))
        document["robots"][0]["steps"][1]["values"]["arm"] = "automatic"
        plan = PlanDocument.from_json(document)
        demo = PlannedTaskDemo.of_document(DemoDocument(plan=plan), port=0)
        demo.execution = AnsweredKinematicExecution(answers=TableAnswers(demo))
        demo.run()
    return [
        entry for entry in demo.run_log.entries if isinstance(entry, PerceptionReported)
    ]


def test_the_check_of_the_picked_cube_reports_it_24_cm_away(reports):
    first = reports[0]
    report = first.report
    assert first.step == "step_2"
    assert (report.target, report.color, report.tolerance) == ("red_cube", "red", 0.02)
    assert (report.grounded.x, report.grounded.y) == pytest.approx((0.55, 0.1))
    assert [seen.verdict for seen in report.objects] == [
        ReportedObjectVerdict.OUTSIDE_BOX,
        ReportedObjectVerdict.WRONG_COLOR,
        ReportedObjectVerdict.WRONG_COLOR,
    ]
    assert report.summary.startswith("red_cube was seen 24 cm from where the plan")


def test_every_detection_the_run_ran_is_reported_as_an_event(reports):
    assert len(reports) >= 2
    assert all(entry.step == "step_2" for entry in reports)
    assert all(entry.event().kind is RunEventKind.PERCEPTION for entry in reports)
