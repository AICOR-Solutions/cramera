"""
``cramera-check-bundle``: check that scene bundles hold every file they reference, so
they can be shown from their directories alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path

from typing_extensions import List, Optional, Sequence, TextIO

from cramera_offline.bundle_check import BundleCheck
from cramera_protocol.offline import BundleCheckReport

# %% vocabulary


class CheckOption(StrEnum):
    """
    The command's options.
    """

    BUNDLES = "bundles"
    """
    The bundle directories to check.
    """

    JSON = "--json"
    """
    Print the reports as a JSON list instead of text.
    """


class CheckExit(IntEnum):
    """
    The command's exit codes.
    """

    COMPLETE = 0
    """
    Every bundle holds every file it references.
    """

    INCOMPLETE = 1
    """
    A bundle cannot follow a reference.
    """


# %% output


@dataclass(frozen=True)
class ReportText:
    """
    A bundle check report as lines for people.
    """

    report: BundleCheckReport
    """
    The report.
    """

    def lines(self) -> List[str]:
        """
        :return: A summary line, and one line per problem.
        """
        if self.report.is_complete():
            return [
                f"{self.report.bundle}: complete, "
                f"{len(self.report.checked_files)} files"
            ]
        lines = [f"{self.report.bundle}: {len(self.report.problems)} problems"]
        for problem in self.report.problems:
            detail = f" ({problem.detail})" if problem.detail else ""
            lines.append(
                f"  {problem.kind.value}: {problem.source} -> "
                f"{problem.reference}{detail}"
            )
        return lines


def main(arguments: Optional[Sequence[str]] = None, output: TextIO = sys.stdout) -> int:
    """
    Check the bundles and print their reports.

    :param arguments: The command-line arguments; the process arguments when None.
    :param output: Where the reports are printed.
    :return: :attr:`CheckExit.COMPLETE` when every bundle is complete, else
        :attr:`CheckExit.INCOMPLETE`.
    """
    parser = argparse.ArgumentParser(
        prog="cramera-check-bundle", description=__doc__.strip().splitlines()[0]
    )
    parser.add_argument(CheckOption.BUNDLES, type=Path, nargs="+")
    parser.add_argument(CheckOption.JSON, action="store_true")
    parsed = parser.parse_args(arguments)
    reports = [BundleCheck(bundle).report() for bundle in parsed.bundles]
    if parsed.json:
        print(
            json.dumps([report.to_json() for report in reports], indent=2), file=output
        )
    else:
        for report in reports:
            print("\n".join(ReportText(report).lines()), file=output)
    if all(report.is_complete() for report in reports):
        return CheckExit.COMPLETE
    return CheckExit.INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
