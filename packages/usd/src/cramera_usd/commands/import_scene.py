"""
``cramera-import``: convert a USD stage, such as an Isaac Sim twin, into a scene bundle.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import numpy
from typing_extensions import List, Optional, Self, Sequence

from cramera_protocol.bundle.conversion_report import ReportCount
from cramera_protocol.bundle.files import BundleFile
from cramera_usd.animation.animation import SceneAnimation
from cramera_usd.animation.animator import SceneAnimator
from cramera_usd.animation.residuals import MILLIMETRES_PER_METRE
from cramera_usd.animation.run_record import RecordedRun
from cramera_usd.animation.trace import BodyTrace
from cramera_usd.bundle.camera import SceneCamera
from cramera_usd.bundle.scene import DEFAULT_EXPOSURE, ScenePresentation
from cramera_usd.bundle.writer import SceneBundle
from cramera_usd.locations import ScenesLocations
from cramera_usd.scene.kinematics import JointKind
from cramera_usd.scene.log import ConversionLog
from cramera_usd.scene.stage import ConvertedStage
from cramera_usd.stage.reader import StageReader
from cramera_usd.stage.robots import (
    ENTITY_TYPE_ATTRIBUTE,
    PrimExclusion,
    RobotMarker,
)
from cramera_usd.stage.variants import VariantSelection

# %% options


class ImportOption(StrEnum):
    """
    The command line options of ``cramera-import``.
    """

    NAME = "--name"
    """
    The bundle name.
    """

    OUT = "--out"
    """
    The scenes directory receiving the bundle.
    """

    PRIM = "--prim"
    """
    A prim whose subtree is converted; repeatable.
    """

    EXCLUDE = "--exclude"
    """
    A prim whose subtree is left out; repeatable.
    """

    ENVIRONMENT_NAME = "--environment-name"
    """
    The environment's name in the viewer's picker.
    """

    TASK = "--task"
    """
    The scene's description in the viewer's picker.
    """

    EXPOSURE = "--exposure"
    """
    The viewer's tone mapping exposure.
    """

    CAMERA_POSITION = "--camera-position"
    """
    The initial camera position.
    """

    CAMERA_TARGET = "--camera-target"
    """
    The point the initial camera looks at.
    """

    CAMERA_FIELD_OF_VIEW = "--camera-fov"
    """
    The vertical field of view of the initial camera in degrees.
    """

    TRACE = "--trace"
    """
    A recorded body trace to play back instead of the stage's time samples.
    """

    FRAMES_PER_SECOND = "--fps"
    """
    The playback rate.
    """

    ROBOT = "--robot"
    """
    The prim of the robot's root link, converted as a model of its own.
    """

    KEEP_ROBOTS = "--keep-robots"
    """
    Keep the robots the stage marks in the environment instead of leaving them out.
    """

    VARIANT = "--variant"
    """
    A variant selected in the stage's session layer; repeatable.
    """

    RECORD = "--record"
    """
    A run record whose steps become the playback's segments.
    """


class ImportDestination(StrEnum):
    """
    The names the parsed options are kept under where their option abbreviates.
    """

    CAMERA_FIELD_OF_VIEW = "camera_field_of_view"
    """
    The vertical field of view of the initial camera.
    """

    FRAMES_PER_SECOND = "frames_per_second"
    """
    The playback rate.
    """


DEFAULT_FRAMES_PER_SECOND = 30.0
"""
The playback rate unless one is given.
"""

PROGRAM = "cramera-import"
"""
The command's name.
"""

COORDINATES = ("X", "Y", "Z")
"""
The names of a point's coordinates in the help.
"""

VARIANT_PARTS = ("PRIM", "SET", "VARIANT")
"""
The names of a variant selection's parts in the help.
"""

# %% parser


@dataclass(frozen=True)
class ImportParser:
    """
    The argument parser of ``cramera-import``, which ``cramera-export`` extends.
    """

    def parser(self, program: str, add_help: bool = True) -> argparse.ArgumentParser:
        """
        :param program: The program name the help shows.
        :param add_help: Whether the parser answers ``--help`` itself.
        :return: A parser of every import option.
        """
        parser = argparse.ArgumentParser(
            prog=program,
            add_help=add_help,
            description="Convert a USD stage (.usd, .usda, .usdc) into a cramera scene "
            "bundle of its environment: robots the stage marks are left out unless "
            f"{ImportOption.ROBOT} or {ImportOption.KEEP_ROBOTS} keeps them.",
        )
        parser.add_argument("stage", type=Path, help="the stage file to convert")
        parser.add_argument(
            ImportOption.NAME,
            required=True,
            help="bundle name (letters, digits, _ and -)",
        )
        parser.add_argument(
            ImportOption.OUT,
            type=Path,
            default=None,
            help="scenes directory (default: CRAMERA_SCENES, else the local scenes "
            "directory)",
        )
        parser.add_argument(
            ImportOption.PRIM,
            action="append",
            default=[],
            help="convert only this prim's subtree; repeatable (default: the whole "
            "stage)",
        )
        parser.add_argument(
            ImportOption.EXCLUDE,
            action="append",
            default=[],
            metavar="PRIM",
            help="leave out this prim's subtree; repeatable",
        )
        parser.add_argument(
            ImportOption.ENVIRONMENT_NAME,
            default="",
            help="environment name in the picker",
        )
        parser.add_argument(
            ImportOption.TASK, default="", help="scene description in the picker"
        )
        parser.add_argument(
            ImportOption.EXPOSURE,
            type=float,
            help=f"tone mapping exposure (default: {DEFAULT_EXPOSURE})",
        )
        parser.add_argument(
            ImportOption.CAMERA_POSITION,
            type=float,
            nargs=len(COORDINATES),
            metavar=COORDINATES,
        )
        parser.add_argument(
            ImportOption.CAMERA_TARGET,
            type=float,
            nargs=len(COORDINATES),
            metavar=COORDINATES,
        )
        parser.add_argument(
            ImportOption.CAMERA_FIELD_OF_VIEW,
            type=float,
            dest=ImportDestination.CAMERA_FIELD_OF_VIEW,
            metavar="DEGREES",
            help="vertical field of view of the camera given by position and target",
        )
        parser.add_argument(
            ImportOption.TRACE,
            type=Path,
            help="recorded body trace (.npz: bodies, pos, quat w-first, sample_hz) to "
            "play back",
        )
        parser.add_argument(
            ImportOption.FRAMES_PER_SECOND,
            type=float,
            dest=ImportDestination.FRAMES_PER_SECOND,
            default=DEFAULT_FRAMES_PER_SECOND,
            help="playback rate (default: %(default)s)",
        )
        parser.add_argument(
            ImportOption.ROBOT,
            metavar="PRIM",
            help="prim of the robot's root link, written as a robot model of its own "
            "and kept although the stage marks it as a robot",
        )
        parser.add_argument(
            ImportOption.KEEP_ROBOTS,
            action="store_true",
            help=f"keep the robots the stage marks (applied "
            f"{RobotMarker.ISAAC_ROBOT_SCHEMA}, or {ENTITY_TYPE_ATTRIBUTE} "
            f"{RobotMarker.ROBOT_ENTITY_TYPE}) in the environment; by default they are "
            "left out",
        )
        parser.add_argument(
            ImportOption.VARIANT,
            nargs=len(VARIANT_PARTS),
            action="append",
            default=[],
            metavar=VARIANT_PARTS,
            help="select a variant in the in-memory session layer; repeatable",
        )
        parser.add_argument(
            ImportOption.RECORD,
            type=Path,
            help="run record (JSON with steps) whose steps become the segments",
        )
        return parser


# %% command


@dataclass
class ImportCommand:
    """
    One run of ``cramera-import``.
    """

    stage: Path
    """
    The stage file to convert.
    """

    name: str
    """
    The bundle name.
    """

    scenes_directory: Path
    """
    The directory holding the bundles and ``index.json``.
    """

    prim_paths: List[str] = field(default_factory=list)
    """
    The prims whose subtrees are converted; empty for the whole stage.
    """

    exclusion: PrimExclusion = field(default_factory=PrimExclusion)
    """
    The prims left out with their subtrees.
    """

    presentation: ScenePresentation = field(default_factory=ScenePresentation)
    """
    How the scene is labelled and first shown.
    """

    trace: Optional[Path] = None
    """
    The recorded body trace to play back, or None to sample the stage's time samples.
    """

    frames_per_second: float = DEFAULT_FRAMES_PER_SECOND
    """
    The playback rate.
    """

    variant_selections: List[VariantSelection] = field(default_factory=list)
    """
    The variants selected in the stage's session layer.
    """

    record: Optional[Path] = None
    """
    The run record whose steps label the playback, or None.
    """

    @classmethod
    def from_options(
        cls,
        options: argparse.Namespace,
        parser: argparse.ArgumentParser,
        default_directory: Path,
    ) -> Self:
        """
        :param options: The parsed import options.
        :param parser: The parser, to refuse options that do not fit together.
        :param default_directory: The scenes directory when none is given.
        :return: The command the options ask for.
        """
        return cls(
            stage=options.stage,
            name=options.name,
            scenes_directory=options.out or default_directory,
            prim_paths=options.prim,
            exclusion=PrimExclusion(
                options.exclude, options.keep_robots, options.robot
            ),
            presentation=ScenePresentation(
                environment_name=options.environment_name,
                task=options.task,
                camera=cls.camera_of(options, parser),
                exposure=(
                    DEFAULT_EXPOSURE if options.exposure is None else options.exposure
                ),
            ),
            trace=options.trace,
            frames_per_second=options.frames_per_second,
            variant_selections=[
                VariantSelection(*selection) for selection in options.variant
            ],
            record=options.record,
        )

    @staticmethod
    def camera_of(
        options: argparse.Namespace, parser: argparse.ArgumentParser
    ) -> Optional[SceneCamera]:
        """
        :param options: The parsed import options.
        :param parser: The parser, to refuse a camera given in part.
        :return: The camera the options give, or None when they give none.
        """
        position_given = options.camera_position is not None
        target_given = options.camera_target is not None
        field_of_view_given = options.camera_field_of_view is not None
        if not (position_given or target_given or field_of_view_given):
            return None
        if not (position_given and target_given):
            parser.error(
                f"{ImportOption.CAMERA_POSITION} and {ImportOption.CAMERA_TARGET} give "
                f"the camera together, and {ImportOption.CAMERA_FIELD_OF_VIEW} only "
                "goes with both"
            )
        camera = SceneCamera(
            numpy.array(options.camera_position), numpy.array(options.camera_target)
        )
        if field_of_view_given:
            camera.field_of_view = options.camera_field_of_view
        return camera

    @property
    def robot_path(self) -> Optional[str]:
        """
        The prim of the robot's root link, or None for a scene without a robot.
        """
        return self.exclusion.robot_path

    def run(self) -> SceneBundle:
        """
        Read the stage and write the bundle.

        :return: The written bundle.
        """
        started = time.perf_counter()
        reader = StageReader(
            self.stage, self.prim_paths, self.variant_selections, self.exclusion
        )
        stage = reader.read()
        bundle = SceneBundle(
            stage,
            self.name,
            self.scenes_directory,
            presentation=self.presentation,
            animation=self.animation(reader, stage),
            read_seconds=time.perf_counter() - started,
        )
        bundle.write()
        return bundle

    def animation(
        self, reader: StageReader, stage: ConvertedStage
    ) -> Optional[SceneAnimation]:
        """
        :param reader: The reader of the stage.
        :param stage: The converted stage.
        :return: The playback of the trace, else of the stage's time samples; None for
            a stage without moving links, recorded trace or robot.
        """
        if self.trace is not None:
            trace = BodyTrace.from_file(self.trace).resampled(self.frames_per_second)
        else:
            trace = reader.motion(
                [link.path for link in stage.links], self.frames_per_second
            )
        if self.trace is None and not trace.poses and self.robot_path is None:
            return None
        return SceneAnimator(
            stage,
            trace,
            robot_path=self.robot_path,
            run=None if self.record is None else RecordedRun.from_file(self.record),
        ).animate()


# %% summary

EMPTY_LIST = "-"
"""
What the summary shows for an empty list.
"""

BYTES_PER_MEGABYTE = 1e6
"""
The number of bytes in a megabyte.
"""


@dataclass(frozen=True)
class ImportSummary:
    """
    What a conversion wrote, for the terminal.
    """

    bundle: SceneBundle
    """
    The written bundle.
    """

    def lines(self) -> List[str]:
        """
        :return: The summary, one line per entry.
        """
        stage = self.bundle.stage
        counts = stage.log.counts
        joints = {kind: 0 for kind in JointKind}
        for joint in stage.joints:
            joints[joint.motion.kind] += 1
        megabytes = self.bundle.layout.size() / BYTES_PER_MEGABYTE
        return [
            f"wrote {self.bundle.layout.file(BundleFile.SCENE)}",
            f"  {len(stage.links)} links, "
            + ", ".join(f"{count} {kind.value}" for kind, count in joints.items())
            + " joints",
            f"  {counts[ReportCount.MESHES]} meshes, {counts[ReportCount.TRIANGLES]} "
            f"triangles, {len(stage.materials)} materials, {megabytes:.1f} MB",
            f"  skipped: {dict(stage.log.skipped)}",
            "  left out: "
            + (
                ", ".join(
                    f"{excluded.path} ({excluded.reason})"
                    for excluded in stage.log.excluded
                )
                or EMPTY_LIST
            ),
            *self.separation_lines(stage.log),
            *self.animation_lines(self.bundle.animation),
            f"  view it with `cramera` and open the scene {self.bundle.name}",
        ]

    @classmethod
    def separation_lines(cls, log: ConversionLog) -> List[str]:
        """
        :param log: The conversion's log.
        :return: What of the log asks for a look: the bodies detached from left-out
            prims, the articulations kept in the environment and the warnings.
        """
        return [
            *cls.listed(
                "detached from left-out prims",
                [
                    f"{detached.body} from {detached.parent_body} "
                    f"(joint {detached.joint})"
                    + (
                        f", movable joints below it: {len(detached.movable_joints)}, "
                        f"a robot part? {ImportOption.EXCLUDE} it"
                        if detached.movable_joints
                        else ""
                    )
                    for detached in log.detached
                ],
            ),
            *cls.listed(
                "articulations kept in the environment "
                f"({ImportOption.EXCLUDE} a robot the stage does not mark)",
                [
                    f"{articulation.path}, movable joints: "
                    f"{len(articulation.movable_joints)}"
                    for articulation in log.articulations
                ],
            ),
            *cls.listed("warnings", log.warnings),
        ]

    @staticmethod
    def listed(title: str, items: List[str]) -> List[str]:
        """
        :param title: What the items are.
        :param items: The items.
        :return: A titled list, one item per line, or a dash when it is empty.
        """
        if not items:
            return [f"  {title}: {EMPTY_LIST}"]
        return [f"  {title}:", *(f"    {item}" for item in items)]

    @staticmethod
    def animation_lines(animation: Optional[SceneAnimation]) -> List[str]:
        """
        :param animation: The playback, or None.
        :return: What the playback holds and how well it reproduces the recording.
        """
        if animation is None:
            return []
        worst = max(
            animation.body_residuals,
            key=lambda residual: residual.largest_distance,
            default=None,
        )
        robot = EMPTY_LIST if animation.robot is None else animation.robot.name
        return [
            f"  playback: {animation.frame_count} frames at "
            f"{animation.frames_per_second:g} fps from {animation.source}, "
            f"{len(animation.joint_values)} joints, robot {robot}, "
            f"objects {[moving.key for moving in animation.objects]}",
            f"  replay: {len(animation.body_residuals)} bodies, worst "
            + (
                EMPTY_LIST
                if worst is None
                else f"{worst.largest_distance * MILLIMETRES_PER_METRE:.3f} mm "
                f"({worst.path})"
            )
            + f", {len(animation.beyond_tolerance())} residuals beyond tolerance",
        ]


# %% entry point


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    Convert a USD stage into a scene bundle and print what was written.

    :param arguments: The command line arguments; the process arguments when None.
    """
    parser = ImportParser().parser(PROGRAM)
    options = parser.parse_args(arguments if arguments is not None else sys.argv[1:])
    default_directory = ScenesLocations(os.environ, Path.home()).import_directory()
    command = ImportCommand.from_options(options, parser, default_directory)
    print("\n".join(ImportSummary(command.run()).lines()))


if __name__ == "__main__":
    main()
