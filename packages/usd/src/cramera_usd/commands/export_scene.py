"""
``cramera-export``: hand the environment of a twin to cramera.

The stage is converted into a staging directory inside the scenes directory and gated
there; only a bundle that passes replaces the published one and enters the scenes index.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path

from typing_extensions import List, Mapping, Optional, Sequence

from cramera_protocol.bundle.conversion_report import ReportCount
from cramera_usd.commands.import_scene import (
    BYTES_PER_MEGABYTE,
    ImportDestination,
    ImportOption,
    ImportParser,
)
from cramera_usd.exceptions import ViewerNotInstalled
from cramera_usd.distribution import Distribution
from cramera_usd.export.gate import ExportGate, StagedBundle
from cramera_usd.export.import_process import ImportArguments, ImportProcess
from cramera_usd.export.lens import (
    DEFAULT_RENDER_HEIGHT,
    DEFAULT_RENDER_WIDTH,
    RenderLens,
)
from cramera_usd.export.screenshot import ViewerScreenshot
from cramera_usd.export.staging import StagingDirectory
from cramera_usd.locations import ScenesLocations

# %% options


class ExportOption(StrEnum):
    """
    The options ``cramera-export`` adds to those of ``cramera-import``.
    """

    REPLAY = "--replay"
    """
    The bundle replays a recorded run with its robot instead of showing the environment
    alone.
    """

    NO_ROBOTS = "--no-robots"
    """
    The twin has no robots, so nothing is left out.
    """

    FOCAL = "--focal"
    """
    The focal length of the twin's render view, passed on as the camera's field of view.
    """

    RENDER_SIZE = "--render-size"
    """
    The size the render view is rendered at.
    """

    SHOT = "--shot"
    """
    A screenshot of the published bundle in the viewer.
    """


class ExportExit(IntEnum):
    """
    The exit codes of the command.
    """

    PUBLISHED = 0
    """
    The bundle passed its gate and was published.
    """

    REJECTED = 1
    """
    The import failed, or the bundle did not pass its gate; nothing was published.
    """


PROGRAM = "cramera-export"
"""
The command's name.
"""

MESSAGE_PREFIX = f"[{PROGRAM}]"
"""
What starts the command's own lines, to tell them from the conversion's output.
"""

RENDER_SIZE_PARTS = ("WIDTH", "HEIGHT")
"""
The names of the render size's parts in the help.
"""

# %% request


@dataclass(frozen=True)
class ExportRequest:
    """
    What an export was asked to do.
    """

    options: argparse.Namespace
    """
    The parsed import options, the camera's field of view already derived from a focal
    length.
    """

    scenes_directory: Path
    """
    The scenes directory the bundle is published into.
    """

    replay: bool
    """
    Whether the bundle replays a recorded run with its robot.
    """

    without_robots: bool
    """
    Whether the twin is declared to have no robots.
    """

    shot: Optional[Path]
    """
    The PNG file of a screenshot of the published bundle, or None for none.
    """

    @property
    def name(self) -> str:
        """
        The bundle's name.
        """
        return self.options.name

    @property
    def gate(self) -> ExportGate:
        """
        The gate the staged bundle passes.
        """
        return ExportGate.of_export(
            self.options.environment_name,
            self.replay,
            self.without_robots,
            self.options.exclude,
        )


@dataclass(frozen=True)
class ExportParser:
    """
    The argument parser of ``cramera-export``: every import option, and the options of
    the export.
    """

    default_directory: Path
    """
    The scenes directory when none is given.
    """

    def parser(self) -> argparse.ArgumentParser:
        """
        :return: The parser.
        """
        parser = argparse.ArgumentParser(
            prog=PROGRAM,
            description=__doc__.strip().splitlines()[0],
            parents=[ImportParser().parser(PROGRAM, add_help=False)],
            allow_abbrev=False,
        )
        parser.add_argument(
            ExportOption.REPLAY,
            action="store_true",
            help="a replay of a recorded run: allows the trace, robot, record, rate "
            "and kept robots, and skips the environment-only checks",
        )
        parser.add_argument(
            ExportOption.NO_ROBOTS,
            action="store_true",
            help="the twin has no robots (otherwise an export that left nothing out "
            "fails the gate)",
        )
        parser.add_argument(
            ExportOption.FOCAL,
            type=float,
            metavar="MILLIMETRES",
            help="focal length of the twin's render view, passed on as the vertical "
            "field of view",
        )
        parser.add_argument(
            ExportOption.RENDER_SIZE,
            type=int,
            nargs=2,
            metavar=RENDER_SIZE_PARTS,
            default=(DEFAULT_RENDER_WIDTH, DEFAULT_RENDER_HEIGHT),
            help="the size the render view is rendered at (default: %(default)s)",
        )
        parser.add_argument(
            ExportOption.SHOT,
            type=Path,
            metavar="PNG",
            help="screenshot the published bundle in the viewer (needs cramera)",
        )
        parser.set_defaults(**{ImportDestination.FRAMES_PER_SECOND: None})
        return parser

    def parse(self, arguments: Sequence[str]) -> ExportRequest:
        """
        :param arguments: The command line arguments without the program name.
        :return: The export they ask for; the parser exits on options that do not fit
            together.
        """
        parser = self.parser()
        options = parser.parse_args(list(arguments))
        if not options.replay:
            for option in self.replay_options_given(options):
                parser.error(
                    f"{option} makes a replay of a recorded run, not an environment "
                    f"export: add {ExportOption.REPLAY}"
                )
        if not options.environment_name:
            parser.error(
                f"{ImportOption.ENVIRONMENT_NAME} is required: a robot demo pairs with "
                "this bundle through it"
            )
        if options.focal is not None and options.camera_field_of_view is not None:
            parser.error(
                f"give {ExportOption.FOCAL} (from the render view) or "
                f"{ImportOption.CAMERA_FIELD_OF_VIEW}, not both"
            )
        if options.focal is not None:
            width, height = options.render_size
            options.camera_field_of_view = RenderLens(
                options.focal, width, height
            ).vertical_field_of_view()
        return ExportRequest(
            options=options,
            scenes_directory=(options.out or self.default_directory).resolve(),
            replay=options.replay,
            without_robots=options.no_robots,
            shot=None if options.shot is None else options.shot.resolve(),
        )

    @staticmethod
    def replay_options_given(options: argparse.Namespace) -> List[ImportOption]:
        """
        :param options: The parsed options.
        :return: The options given that make a replay of a recorded run.
        """
        given = {
            ImportOption.TRACE: options.trace is not None,
            ImportOption.ROBOT: options.robot is not None,
            ImportOption.RECORD: options.record is not None,
            ImportOption.FRAMES_PER_SECOND: options.frames_per_second is not None,
            ImportOption.KEEP_ROBOTS: options.keep_robots,
        }
        return [option for option, present in given.items() if present]


# %% command


@dataclass(frozen=True)
class ExportCommand:
    """
    One run of ``cramera-export``.
    """

    request: ExportRequest
    """
    What the export was asked to do.
    """

    environment: Mapping[str, str]
    """
    The environment the conversion runs in.
    """

    def run(self) -> ExportExit:
        """
        Convert into a staging directory, gate the bundle there, and publish it when it
        passes.

        :return: Whether the bundle was published.
        :raises ViewerNotInstalled: When a screenshot is asked for without the viewer.
        """
        request = self.request
        if request.shot is not None and not self.screenshot().available():
            raise ViewerNotInstalled(Distribution.VIEWER.value)
        staging = StagingDirectory.create(request.scenes_directory, request.name)
        self.say(
            f"{request.options.stage} -> {staging.published} (staged in {staging.path})"
        )
        converted = ImportProcess(self.environment).run(
            ImportArguments(request.options).to_list(staging.path)
        )
        if not converted:
            staging.remove()
            self.say("the import failed; nothing was published")
            return ExportExit.REJECTED
        bundle = StagedBundle.read(staging.path, request.name)
        for line in self.summary(bundle):
            self.say(line)
        outcomes = request.gate.evaluate(bundle)
        for outcome in outcomes:
            print(outcome.line(), flush=True)
        failed = [outcome for outcome in outcomes if not outcome.passed]
        if failed:
            self.say(
                f"gate failed: {'; '.join(outcome.description for outcome in failed)}"
            )
            self.say(f"not published: {staging.published} and the index are unchanged")
            self.say(
                f"the rejected bundle is {staging.bundle} (delete {staging.path} when done)"
            )
            return ExportExit.REJECTED
        for line in self.hints(bundle):
            self.say(line)
        entry = staging.publish(request.replay)
        self.say(
            f"published {staging.published}; index.json lists "
            f"{json.dumps(entry.to_json())}"
        )
        if request.shot is not None:
            report = self.screenshot().take()
            self.say(f"screenshot {request.shot}: {report.state} ({report.status})")
        return ExportExit.PUBLISHED

    def screenshot(self) -> ViewerScreenshot:
        """
        :return: The screenshot of the published bundle the export was asked for.
        """
        return ViewerScreenshot(
            self.request.scenes_directory, self.request.name, self.request.shot
        )

    @staticmethod
    def say(line: str) -> None:
        """
        Print one of the command's own lines.

        :param line: The line.
        """
        print(f"{MESSAGE_PREFIX} {line}", flush=True)

    @staticmethod
    def summary(bundle: StagedBundle) -> List[str]:
        """
        :param bundle: The staged bundle.
        :return: What the conversion wrote and left out.
        """
        report = bundle.report
        counts = report.counts
        lines = [
            f"{counts.get(ReportCount.LINKS)} links, {counts.get(ReportCount.MESHES)} "
            f"meshes, {counts.get(ReportCount.TRIANGLES)} triangles, "
            f"{counts.get(ReportCount.MATERIALS)} materials, "
            f"{counts.get(ReportCount.SEMANTIC_PRIMS)} semantic prims, "
            f"{report.bundle_bytes / BYTES_PER_MEGABYTE:.1f} MB"
        ]
        lines += [f"left out {item.path} ({item.reason})" for item in report.excluded]
        lines += [
            f"detached {item.body} from {item.parent_body} (joint {item.joint}"
            + (
                f", moves {len(item.movable_joints)} joints"
                if item.movable_joints
                else ""
            )
            + ")"
            for item in report.detached
        ]
        lines += [
            f"articulation kept: {item.path} ({len(item.movable_joints)} movable joints)"
            for item in report.articulations
        ]
        return lines

    def hints(self, bundle: StagedBundle) -> List[str]:
        """
        :param bundle: The staged bundle, which passed its gate.
        :return: What to confirm by eye before handing an environment over.
        """
        if self.request.replay:
            return []
        hints = []
        if bundle.report.detached:
            hints.append(
                "check in the screenshot that each detached body is an object a robot "
                "held"
            )
        if bundle.report.articulations:
            hints.append(
                "confirm each kept articulation is equipment (door, station), not a "
                f"robot the stage does not mark; {ImportOption.EXCLUDE} such a robot"
            )
        return hints


# %% entry point


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    Export a twin's environment into a scenes directory, gated.

    :param arguments: The command line arguments; the process arguments when None.
    """
    default_directory = ScenesLocations(os.environ, Path.home()).export_directory()
    request = ExportParser(default_directory).parse(
        arguments if arguments is not None else sys.argv[1:]
    )
    sys.exit(ExportCommand(request, os.environ).run())


if __name__ == "__main__":
    main()
