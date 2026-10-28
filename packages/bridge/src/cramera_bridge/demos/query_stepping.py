"""
The PR2's vessel transfer at the laboratory bench, held at every query it asks.

The transfer finds its robot, the bench's handles and the vessel it carries with entity
queries; run with ``--step-queries``, as this command does, each of them is published as
a query step and holds the run until the viewer's **Next** moves it on.

``python -m cramera_bridge.demos.query_stepping --bundle DIR``, where ``DIR`` is a scene
bundle such as ``~/.cramera/scenes/aicor_medical_lab``; the options of
:class:`~cramera_bridge.robot_task.TaskCommand`, such as ``--port``, ``--name`` and
``--no-hold``, follow.
"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

from typing_extensions import Optional, Sequence

from cramera_bridge.laboratory.transfer import VesselTransferDemo
from cramera_bridge.robot_task import TaskCommand
from cramera_protocol.laboratory.runs import TransferOption

NAME = "aicor_medical_lab_pr2_query_steps"
"""
The name the recording is saved under unless ``--name`` gives another.
"""

TASK = "PR2: vessel transfer A1 → A3, stepping through its queries"
"""
What the recording shows, as the scene picker labels it.
"""


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    ``python -m cramera_bridge.demos.query_stepping --bundle DIR [--port PORT] [--name
    NAME] [--no-hold]``

    :param arguments: The command's arguments, or this process's by default.
    """
    parser = ArgumentParser(description=TASK)
    parser.add_argument(
        TransferOption.BUNDLE, type=Path, required=True, help="the laboratory bundle"
    )
    options, remaining = parser.parse_known_args(arguments)
    demo = VesselTransferDemo.at_the_bench(
        options.bundle.expanduser(), name=NAME, task=TASK, step_queries=True
    )
    saved = TaskCommand(demo).main(remaining)
    asked = "" if demo.stepper is None else f"asked {len(demo.stepper.steps)} queries; "
    print(f"{asked}saved {saved.scene}")


if __name__ == "__main__":
    main()
