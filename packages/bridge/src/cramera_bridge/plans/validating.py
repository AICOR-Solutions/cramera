"""
Validating a plan before it runs on the robot: the performing robot's steps are grounded
one after another in a copy of the plan's twin, so nothing moves, and the report says
how each fared. A detection perceives where the robot's camera sees its region now,
through the robot's perception or that of its simulated scene, else it is assumed from
the twin. For the real robot, the twin's robot stands as the real one reports.

Run as ``python -m cramera_bridge.plans.validating <order.json> <report.json>
[<expected order.json>]``, it reads a :class:`~cramera_protocol.validation.ValidationOrder`
and writes the :class:`~cramera_protocol.validation.ValidationReport` once its standard
input closes, so each validation has a process of its own. While it waits, it imports the
robot models and builds the robots' world of the order it is told to expect, which the
order copies when its robots are the same.
"""

from __future__ import annotations

import sys
from contextlib import nullcontext
from dataclasses import dataclass, field, replace

from typing_extensions import Any, List, Optional

from coraplex.perception import WorldPerception
from cramera_bridge.plans.demo import PlannedTaskDemo, SceneWorlds
from cramera_bridge.plans.grounding import GroundedStep, PlanGrounding
from cramera_bridge.plans.order_command import OrderCommand
from cramera_bridge.plans.robot_perception import RobotPerception
from cramera_bridge.plans.workspace import RobotAnnotations
from cramera_bridge.real_robot import ReportedPosture
from cramera_protocol.validation import (
    GroundedStepDocument,
    ValidatedGrounding,
    ValidationOrder,
    ValidationReport,
)
from semantic_digital_twin.world import World

# %% validating


@dataclass(frozen=True)
class PlanValidator:
    """
    Validates the plan of an order.
    """

    order: ValidationOrder
    """
    The plan, its environment and the scene the robot's camera sees.
    """

    scene_worlds: Optional[SceneWorlds] = None
    """
    The robots' worlds built before, which the twin and the world of a simulated scene
    copy, so a validation builds its robots once; None builds the robots for each.
    """

    def demo(self) -> PlannedTaskDemo:
        """
        :return: The plan's demo, building its robots' world through
            :attr:`scene_worlds`.
        """
        return PlannedTaskDemo.of_document(
            self.order.demo, port=0, scene_worlds=self.scene_worlds
        )

    def prepare(self) -> None:
        """
        Build the robots' world of the order into :attr:`scene_worlds`, so a validation
        of the same robots copies it.
        """
        self.demo().build_robots_world()

    def validate(self) -> ValidationReport:
        """
        :return: How each step of the performing robot fared, starting where
            :meth:`build_world` stands the robot. A plan that looks for no objects is
            given the twin, which it never asks, and no camera.
        """
        demo = self.demo()
        steps = demo.steps()
        robot = RobotPerception(
            demo=self.order.demo,
            simulated_objects=self.order.simulated_objects,
            scene_worlds=self.scene_worlds,
        )
        looks = any(
            demo.discovered_actions.named(step.action).looks_for_objects()
            for step in steps
        )
        # listening from the start, so it knows RoboKudo's image topics by the first query
        with robot.watching() if looks else nullcontext() as camera:
            world = self.build_world(demo)
            with (
                robot.perceiving() if looks else nullcontext(WorldPerception())
            ) as live:
                grounded = PlanGrounding(
                    context=demo.build_context(world),
                    bodies=dict(demo.bodies),
                    actions=demo.discovered_actions,
                    perception=live,
                    site=demo.site,
                    safety=demo.document.safety,
                    camera=camera,
                ).ground(steps)
        report = ValidationReport(
            steps=[step.to_step_validation() for step in grounded]
        )
        if not report.passed or looks or self.order.reads_robot_posture:
            return report
        return replace(report, grounding=self.passed_on(grounded))

    def passed_on(self, grounded: List[GroundedStep]) -> ValidatedGrounding:
        """
        :param grounded: The steps of a passed validation that perceived nothing and
            started from the posture the plan gives the robot, as a simulated run of the
            plan starts.
        :return: Their grounding, which such a run of the same plan performs.
        """
        return ValidatedGrounding(
            demo=ValidatedGrounding.fingerprint(self.order.demo),
            steps=[
                GroundedStepDocument(
                    resolved=step.resolved_step(),
                    expected_positions=dict(step.expected_positions),
                )
                for step in grounded
            ],
        )

    def build_world(self, demo: PlannedTaskDemo) -> World:
        """
        :param demo: The plan's demo.
        :return: The plan's twin, the robot standing as the real one reports when the
            order says so, else in the posture the plan gives it.
        :raises JointStatesNotReceived: When the real robot reports no joint positions.
        """
        world = demo.build_world()
        if self.order.reads_robot_posture:
            ReportedPosture().apply(world)
        return world


# %% command


@dataclass(frozen=True)
class ValidateCommand(OrderCommand):
    """
    Validates the plan an order file names and writes the report into a file.
    """

    scene_worlds: SceneWorlds = field(default_factory=SceneWorlds)
    """
    The robots' worlds built while the process waits for its order.
    """

    def prepare(self, expected: Optional[Any]) -> None:
        """
        Import every robot model, and build the robots' world of the expected order.
        """
        RobotAnnotations().annotations()
        if expected is not None:
            PlanValidator(
                ValidationOrder.from_json(expected), scene_worlds=self.scene_worlds
            ).prepare()

    def answer(self, order: Any) -> ValidationReport:
        return PlanValidator(
            ValidationOrder.from_json(order), scene_worlds=self.scene_worlds
        ).validate()


if __name__ == "__main__":
    ValidateCommand().main(sys.argv[1:])
