"""
The PR2's laboratory workflow at the bench, with every query it asks recorded as a step.

The workflow finds its robot, the vessels it moves and the handles of the refrigerator's
door and the centrifuge's lid with entity queries; run with ``--step-queries``, as this
command does, each of them is published as a query step, stamped with the frame it was
asked at and the action under way. With ``--no-hold`` the run does not wait at them.

``python -m cramera_bridge.demos.workflow_queries --bundle DIR``, where ``DIR`` is a
laboratory bundle such as the laboratory plugin's ``aicor_medical_lab``; the options of
:class:`~cramera_bridge.robot_task.TaskCommand`, such as ``--port``, ``--name`` and
``--no-hold``, follow.
"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

from typing_extensions import Optional, Sequence

from cramera_bridge.laboratory.workflow import LaboratoryWorkflowDemo
from cramera_bridge.robot_task import TaskCommand
from cramera_protocol.laboratory.runs import TransferOption

NAME = "aicor_medical_lab_pr2_workflow_queries"
"""
The name the recording is saved under unless ``--name`` gives another.
"""

TASK = "PR2: rack, refrigerator and centrifuge loading, with its queries"
"""
What the recording shows, as the scene picker labels it.
"""


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    ``python -m cramera_bridge.demos.workflow_queries --bundle DIR [--port PORT]
    [--name NAME] [--no-hold]``

    :param arguments: The command's arguments, or this process's by default.
    """
    parser = ArgumentParser(description=TASK)
    parser.add_argument(
        TransferOption.BUNDLE, type=Path, required=True, help="the laboratory bundle"
    )
    options, remaining = parser.parse_known_args(arguments)
    demo = LaboratoryWorkflowDemo.at_the_bench(
        options.bundle.expanduser(), name=NAME, task=TASK, step_queries=True
    )
    saved = TaskCommand(demo).main(remaining)
    asked = "" if demo.stepper is None else f"asked {len(demo.stepper.steps)} queries; "
    print(f"{asked}saved {saved.scene}")


if __name__ == "__main__":
    main()
