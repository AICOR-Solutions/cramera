"""
``cramera-audit-robots``: audit how a composed twin stage separates its robots from its
environment, statically and without Isaac Sim.

  R0 the stage has at least one robot root (with ``--no-robots``: none at all; R1, R5
     and R6 are then skipped)
  R1 the root layer sublayers ``<twin>_robots.usda`` and ``<twin>_environment.usda``
     next to it, and both resolve
  R2 every robot root is a direct child of the robots scope
  R3 every child of the robots scope is a robot root
  R4 every robot root carries ``sdt:entityType`` ``Robot``
  R5 the environment layer, opened on its own, has no prim in the robots scope and no
     robot mark
  R6 the robots layer authors prims only in the robots scope and on the prims above it
  R7 no joint outside the robots scope and the robot roots connects to a robot body
  R8 every robot root has geometry

The command exits with 1 when a check fails. A single-layer twin fails R1, R5 and R6.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path

from pxr import Sdf, Usd
from typing_extensions import Optional, Sequence

from cramera_protocol.bundle.conversion_report import ExclusionReason
from cramera_usd.audit.report import AuditLine, AuditReport
from cramera_usd.audit.separation import (
    DEFAULT_ROBOTS_SCOPE,
    AuditedTwin,
    SeparationAudit,
)
from cramera_usd.bundle.json_file import JsonFile, JsonLayout
from cramera_usd.exceptions import StageNotFound, StageUnreadable
from cramera_usd.export.gate import CheckVerdict
from cramera_usd.stage.robots import ENTITY_TYPE_ATTRIBUTE, RobotMarker, RobotMarks

# %% options


class AuditOption(StrEnum):
    """
    The options of ``cramera-audit-robots``.
    """

    ROBOTS = "--robots"
    """
    The scope holding the robots.
    """

    NO_ROBOTS = "--no-robots"
    """
    The twin has no robots.
    """

    JSON = "--json"
    """
    The file the report is written to.
    """


class AuditExit(IntEnum):
    """
    The exit codes of the command.
    """

    PASSED = 0
    """
    Every check passed.
    """

    FAILED = 1
    """
    A check failed.
    """


PROGRAM = "cramera-audit-robots"
"""
The command's name.
"""

SHOWN_ITEMS = 10
"""
How many items of a list the printed outcome shows.
"""


TIME_PRECISION = "seconds"
"""
The precision of the report's time.
"""

# %% command


@dataclass(frozen=True)
class AuditCommand:
    """
    One run of ``cramera-audit-robots``.
    """

    stage: Path
    """
    The twin's root layer, absolute.
    """

    scope: str = DEFAULT_ROBOTS_SCOPE
    """
    The scope holding the robots.
    """

    without_robots: bool = False
    """
    Whether the twin is declared to have no robots.
    """

    report_file: Optional[Path] = None
    """
    The file the report is written to, or None for none.
    """

    @classmethod
    def from_arguments(cls, arguments: Sequence[str]) -> AuditCommand:
        """
        :param arguments: The command line arguments without the program name.
        :return: The audit they ask for.
        """
        parser = argparse.ArgumentParser(
            prog=PROGRAM, description=__doc__.strip().splitlines()[0]
        )
        parser.add_argument("stage", type=Path)
        parser.add_argument(
            AuditOption.ROBOTS, default=DEFAULT_ROBOTS_SCOPE, help="the robots scope"
        )
        parser.add_argument(
            AuditOption.NO_ROBOTS,
            action="store_true",
            help="the twin has no robots: R0 requires none, R1, R5 and R6 are skipped",
        )
        parser.add_argument(
            AuditOption.JSON, type=Path, help="write the outcome of every check here"
        )
        options = parser.parse_args(list(arguments))
        return cls(
            stage=Path(os.path.abspath(options.stage)),
            scope=options.robots,
            without_robots=options.no_robots,
            report_file=options.json,
        )

    def twin(self) -> AuditedTwin:
        """
        :return: The twin's composed stage.
        :raises StageNotFound: When the stage file does not exist.
        :raises StageUnreadable: When the file is of a type USD does not read.
        """
        if not self.stage.is_file():
            raise StageNotFound(self.stage)
        if not Usd.Stage.IsSupportedFile(str(self.stage)):
            raise StageUnreadable(self.stage)
        stage = Usd.Stage.Open(str(self.stage))
        return AuditedTwin(self.stage, stage, Sdf.Path(self.scope), self.without_robots)

    def run(self) -> AuditExit:
        """
        Audit the twin, print every outcome and write the report when asked to.

        :return: Whether every check passed.
        """
        twin = self.twin()
        marks = RobotMarks()
        roots = ", ".join(
            f"{root.GetPath()} ({self.mark_label(marks.mark_of(root))})"
            for root in twin.roots
        )
        print(f"[separation] {self.stage}: robot roots {roots or 'none'}")
        lines = SeparationAudit.of_twin(self.without_robots).run(twin)
        for line in lines:
            print(self.shown(line))
        passed = sum(line.passed for line in lines)
        print(
            f"[separation] {passed}/{len(lines)} checks pass, {len(twin.roots)} robot roots"
        )
        if self.report_file is not None:
            JsonFile(self.report_file).write(
                AuditReport(
                    generated=datetime.datetime.now().isoformat(
                        timespec=TIME_PRECISION
                    ),
                    stage=str(self.stage),
                    robots=[str(path) for path in twin.root_paths],
                    passed=passed,
                    total=len(lines),
                    lines=lines,
                ),
                JsonLayout.INDENTED,
            )
        return AuditExit.PASSED if passed == len(lines) else AuditExit.FAILED

    @staticmethod
    def mark_label(reason: ExclusionReason) -> str:
        """
        :param reason: The reason a robot root's mark gives.
        :return: The mark as the stage spells it.
        """
        if reason is ExclusionReason.ISAAC_ROBOT_SCHEMA:
            return RobotMarker.ISAAC_ROBOT_SCHEMA.value
        return ENTITY_TYPE_ATTRIBUTE

    @staticmethod
    def shown(line: AuditLine) -> str:
        """
        :param line: A check's outcome.
        :return: The outcome as one printed line, long lists cut short.
        """
        verdict = CheckVerdict.PASS if line.passed else CheckVerdict.FAIL
        shown = {
            str(key): value[:SHOWN_ITEMS] if isinstance(value, list) else value
            for key, value in line.details.items()
        }
        return f"{verdict} {line.check} {line.what} {shown if shown else ''}".rstrip()


# %% entry point


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    Audit a twin's robot separation.

    :param arguments: The command line arguments; the process arguments when None.
    """
    command = AuditCommand.from_arguments(
        arguments if arguments is not None else sys.argv[1:]
    )
    sys.exit(command.run())


if __name__ == "__main__":
    main()
