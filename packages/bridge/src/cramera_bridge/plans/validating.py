"""
Validating a plan before it runs on the robot: the performing robot's steps are grounded
one after another in a copy of the plan's twin, so nothing moves, and the report says
how each fared. A detection perceives where the robot's camera sees its region now,
through the robot's perception or that of its simulated scene, else it is assumed from
the twin.

Run as ``python -m cramera_bridge.plans.validating <order.json> <report.json>``, it reads
a :class:`~cramera_protocol.validation.ValidationOrder` and writes the
:class:`~cramera_protocol.validation.ValidationReport`, so each validation has a process
of its own.
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Iterator, List, Sequence

from coraplex.perception import PerceptionInterface, WorldPerception
from cramera_bridge.plans.demo import PlannedTaskDemo
from cramera_bridge.plans.grounding import PlanGrounding
from cramera_bridge.plans.robot_perception import RobotPerception
from cramera_protocol.plan_builder import PlanStep
from cramera_protocol.validation import ValidationOrder, ValidationReport

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

    def validate(self) -> ValidationReport:
        """
        :return: How each step of the performing robot fared, starting from the posture
            the plan gives the robot.
        """
        demo = PlannedTaskDemo.of_document(self.order.demo, port=0)
        world = demo.build_world()
        context = demo.build_context(world)
        steps = demo.steps()
        with self.perception(demo, steps) as live:
            grounded = PlanGrounding(
                context=context,
                bodies=dict(demo.bodies),
                actions=demo.discovered_actions,
                perception=live,
            ).ground(steps)
        return ValidationReport(steps=[step.to_step_validation() for step in grounded])

    @contextmanager
    def perception(
        self, demo: PlannedTaskDemo, steps: List[PlanStep]
    ) -> Iterator[PerceptionInterface]:
        """
        Reach the robot's perception while the block runs, if a step looks for objects;
        a plan that looks for none is given the twin, which it never asks.

        :param demo: The plan's demo.
        :param steps: The performing robot's steps.
        """
        if not any(
            demo.discovered_actions.named(step.action).looks_for_objects()
            for step in steps
        ):
            yield WorldPerception()
            return
        with RobotPerception(
            demo=self.order.demo, simulated_objects=self.order.simulated_objects
        ).perceiving() as live:
            yield live


# %% command


@dataclass(frozen=True)
class ValidateCommand:
    """
    Validates the plan an order file names and writes the report into a file.
    """

    def main(self, arguments: Sequence[str]) -> None:
        """
        :param arguments: The order's file and the file the report is written to.
        """
        order_file, report_file = arguments
        order = ValidationOrder.from_json(
            json.loads(Path(order_file).read_text(encoding="utf-8"))
        )
        report = PlanValidator(order).validate()
        Path(report_file).write_text(json.dumps(report.to_json()), encoding="utf-8")


if __name__ == "__main__":
    ValidateCommand().main(sys.argv[1:])
