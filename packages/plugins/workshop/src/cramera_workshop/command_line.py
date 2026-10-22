"""
``cramera-workshop``: name the scenes directory of the packaged workshop, run or publish
the PR2 demos, and check a recorded assembly before it is published.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from enum import StrEnum
from pathlib import Path

from typing_extensions import List, Optional, Sequence, TextIO

from cramera_workshop.bundle import RESOURCES
from cramera_workshop.release import WorkshopRelease

# %% vocabulary


class WorkshopCommand(StrEnum):
    """
    The subcommands.
    """

    SCENES_DIRECTORY = "scenes-directory"
    """
    Print the scenes directory holding the packaged workshop, for ``cramera --scenes``.
    """

    INSERTION = "insertion"
    """
    Run the screw insertion demo, or publish its recording.
    """

    ASSEMBLY = "assembly"
    """
    Run the two-handed assembly demo, or publish its recording.
    """

    CHECK_RELEASE = "check-release"
    """
    Check a recorded assembly before it is published.
    """


class CommandOption(StrEnum):
    """
    The options of the subcommands.
    """

    COMMAND = "command"
    """
    The subcommand.
    """

    BUNDLE = "bundle"
    """
    The recording to check.
    """

    DEMO_ARGUMENTS = "arguments"
    """
    The arguments passed on to a demo's command.
    """


class DemoModule(StrEnum):
    """
    The module holding the demos; it imports CRAM, so it is imported only for them.
    """

    DEMOS = "cramera_workshop.robot.demos"
    """
    :mod:`cramera_workshop.robot.demos`.
    """


RELEASE_PASSED = "passes the release check"
"""
What the release check prints after a bundle's name when it passes.
"""

# %% command


def run_demo(command: WorkshopCommand, arguments: Sequence[str]) -> None:
    """
    :param command: :attr:`WorkshopCommand.INSERTION` or
        :attr:`WorkshopCommand.ASSEMBLY`.
    :param arguments: The demo command's arguments.
    """
    demos = importlib.import_module(DemoModule.DEMOS)
    demos.WorkshopDemoCommand(demos.WorkshopDemoName[command.name]).main(arguments)


def main(
    arguments: Optional[Sequence[str]] = None, output: TextIO = sys.stdout
) -> None:
    """
    :param arguments: The command-line arguments; the process arguments when None.
    :param output: Where the command prints.
    :raises InvalidWorkshopRelease: When a checked recording cannot be published.
    """
    parser = argparse.ArgumentParser(prog="cramera-workshop", description=__doc__)
    parser.add_argument(
        CommandOption.COMMAND, choices=[command.value for command in WorkshopCommand]
    )
    parser.add_argument(CommandOption.DEMO_ARGUMENTS, nargs=argparse.REMAINDER)
    parsed = parser.parse_args(arguments)
    command = WorkshopCommand(parsed.command)
    remaining: List[str] = parsed.arguments
    if command is WorkshopCommand.SCENES_DIRECTORY:
        print(RESOURCES, file=output)
    elif command is WorkshopCommand.CHECK_RELEASE:
        directory = Path(remaining[0])
        WorkshopRelease(directory).validate()
        print(f"{directory.name} {RELEASE_PASSED}", file=output)
    else:
        run_demo(command, remaining)
