"""
The check a recorded assembly passes before it is published: complete, consistent
evidence that the native plan ran every stage and achieved the assembly, read from the
bundle's files alone, without CRAM.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import Any, Dict, Iterable, List

from cramera.exceptions import ViewerError
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.geometry import Pose
from cramera_protocol.workshop import AssetRights
from cramera_workshop.acceptance import (
    ACTION_SUCCEEDED,
    ASSEMBLY_TOLERANCES,
    AssemblyStage,
    AssemblyTolerances,
    ContentsMeasurement,
    ContentsModel,
    DemoMeasurement,
)
from cramera_workshop.bundle import WorkshopFile

UNIT_QUATERNION_TOLERANCE = 0.01
"""
How far a recorded quaternion's squared length may be from one.
"""

# %% problems


class ReleaseProblem(StrEnum):
    """
    Why a recording cannot be published.
    """

    MISSING_DOCUMENT = "A document of the recording is missing"
    """
    The scene, the trajectory or the acceptance metrics are missing.
    """

    NOT_THE_BUNDLE = "The scene description names another bundle or no trajectory"
    """
    The scene's name differs from its directory, or it names no trajectory.
    """

    MISSING_ASSETS = "The recording could not include every file it references"
    """
    The writer listed missing assets.
    """

    MISSING_RIGHTS = "The recording does not name the workshop assets' rights"
    """
    The scene carries no asset rights.
    """

    MISSING_NOTICES = (
        "The licence, the notice or the rights document is missing or differs"
    )
    """
    A rights file is missing or does not match the scene's rights.
    """

    INCOMPLETE_METRICS = "The acceptance metrics lack a measurement"
    """
    A required measurement is absent or not finite.
    """

    FAILED_ACTION = "Not every stage of the assembly ran and succeeded"
    """
    The plan did not have every stage, or one did not succeed.
    """

    BOX_MISPLACED = "The screw box is not on its bench pose"
    """
    The box ended too far from its bench pose.
    """

    SCREW_NOT_DRIVEN = "The screw is not driven to its depth"
    """
    The screw's depth differs from the required depth.
    """

    HANDS_NOT_RELEASED = "The screwdriver or the supporting hand was not released"
    """
    A hand still holds the screwdriver, or the supporting hand did not withdraw.
    """

    PENETRATION = "Bodies penetrated each other"
    """
    The smallest collision distance is below the tolerance.
    """

    CONTENTS_LOST = "The screws were not kept in the box"
    """
    The contents' measurements are incomplete or a screw escaped.
    """

    NO_FRAMES = "The trajectory has no frames"
    """
    The recording is empty.
    """

    INVALID_POSE = "A recorded number is not finite or a quaternion is not a unit"
    """
    A frame holds an invalid value.
    """

    INVALID_SEGMENTS = "The recorded steps are out of order or outside the frames"
    """
    The timeline's segments overlap, run backwards or leave the recording.
    """


@dataclass
class InvalidWorkshopRelease(ViewerError):
    """
    A recording that cannot be published.
    """

    problem: ReleaseProblem
    """
    Why.
    """

    def message(self) -> str:
        return f"{self.problem.value}."


# %% numbers


def is_number(value: Any) -> bool:
    """
    :param value: A JSON value.
    :return: Whether it is a finite number other than a truth value.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def require(condition: bool, problem: ReleaseProblem) -> None:
    """
    :param condition: Whether a requirement holds.
    :param problem: What is wrong when it does not.
    :raises InvalidWorkshopRelease: When the condition does not hold.
    """
    if not condition:
        raise InvalidWorkshopRelease(problem)


# %% release


@dataclass(frozen=True)
class WorkshopRelease:
    """
    Checks a recorded assembly bundle before it is published.
    """

    directory: Path
    """
    The bundle directory.
    """

    tolerances: AssemblyTolerances = field(default=ASSEMBLY_TOLERANCES)
    """
    How closely the assembly must have been achieved.
    """

    required_contents: int = 5
    """
    How many screws the box carried.
    """

    def read(self, file_name: str) -> Any:
        """
        :param file_name: A file of the bundle.
        :return: Its decoded JSON.
        :raises InvalidWorkshopRelease: When the file is missing.
        """
        path = self.directory / file_name
        require(path.is_file(), ReleaseProblem.MISSING_DOCUMENT)
        return json.loads(path.read_text(encoding="utf-8"))

    def validate(self) -> None:
        """
        :raises InvalidWorkshopRelease: Naming the first requirement the recording
            misses.
        """
        scene = SceneDescription.from_json(self.read(BundleFile.SCENE))
        require(
            scene.name == self.directory.name and scene.trajectory is not None,
            ReleaseProblem.NOT_THE_BUNDLE,
        )
        require(not scene.missing_assets, ReleaseProblem.MISSING_ASSETS)
        self.validate_rights(scene)
        metrics = AcceptanceMetrics.from_json(self.read(BundleFile.ACCEPTANCE_METRICS))
        self.validate_metrics(metrics.measurements)
        self.validate_contents(metrics.measurements.get(DemoMeasurement.CONTENTS))
        trajectory = Trajectory.from_json(self.read(scene.trajectory))
        frame_count = len(trajectory.frames)
        require(frame_count > 0, ReleaseProblem.NO_FRAMES)
        self.validate_frames(trajectory)
        self.validate_segments(scene, frame_count)

    def validate_rights(self, scene: SceneDescription) -> None:
        """
        :param scene: The scene description.
        :raises InvalidWorkshopRelease: When the rights or their files are missing.
        """
        rights = AssetRights.of_scene(scene.extensions)
        require(rights is not None, ReleaseProblem.MISSING_RIGHTS)
        files = (rights.license_file, rights.notice_file, WorkshopFile.RIGHTS)
        require(
            all((self.directory / name).is_file() for name in files),
            ReleaseProblem.MISSING_NOTICES,
        )
        require(
            self.read(WorkshopFile.RIGHTS) == rights.to_json(),
            ReleaseProblem.MISSING_NOTICES,
        )

    def validate_metrics(self, measurements: Dict[str, Any]) -> None:
        """
        :param measurements: The acceptance metrics.
        :raises InvalidWorkshopRelease: When a measurement is missing or a requirement
            is not met.
        """
        numbers = (
            DemoMeasurement.BOX_POSITION_ERROR,
            DemoMeasurement.SCREW_DEPTH,
            DemoMeasurement.REQUIRED_DEPTH,
        )
        require(
            all(is_number(measurements.get(name)) for name in numbers)
            and isinstance(measurements.get(DemoMeasurement.ACTION_STATUSES), list),
            ReleaseProblem.INCOMPLETE_METRICS,
        )
        statuses = measurements[DemoMeasurement.ACTION_STATUSES]
        require(
            len(statuses) == len(AssemblyStage)
            and all(status == ACTION_SUCCEEDED for status in statuses),
            ReleaseProblem.FAILED_ACTION,
        )
        require(
            0
            <= measurements[DemoMeasurement.BOX_POSITION_ERROR]
            < self.tolerances.box_position,
            ReleaseProblem.BOX_MISPLACED,
        )
        require(
            measurements[DemoMeasurement.REQUIRED_DEPTH] > 0
            and abs(
                measurements[DemoMeasurement.SCREW_DEPTH]
                - measurements[DemoMeasurement.REQUIRED_DEPTH]
            )
            < self.tolerances.depth,
            ReleaseProblem.SCREW_NOT_DRIVEN,
        )
        require(
            measurements.get(DemoMeasurement.DRIVER_RELEASED) is True
            and measurements.get(DemoMeasurement.SUPPORT_RELEASED) is True,
            ReleaseProblem.HANDS_NOT_RELEASED,
        )
        distance = measurements.get(DemoMeasurement.MINIMUM_COLLISION_DISTANCE)
        require(
            distance is None
            or (is_number(distance) and distance >= -self.tolerances.penetration),
            ReleaseProblem.PENETRATION,
        )

    def validate_contents(self, contents: Any) -> None:
        """
        :param contents: The contents' measurements.
        :raises InvalidWorkshopRelease: When they are incomplete or a screw escaped.
        """
        require(isinstance(contents, dict), ReleaseProblem.CONTENTS_LOST)
        lengths = (
            ContentsMeasurement.SIMULATED_SECONDS,
            ContentsMeasurement.MAXIMUM_BOX_POSITION_LAG,
            ContentsMeasurement.MAXIMUM_BOX_ANGULAR_LAG,
            ContentsMeasurement.MAXIMUM_RELATIVE_DISPLACEMENT,
            ContentsMeasurement.MAXIMUM_PROJECTION_CORRECTION,
        )
        ticks = contents.get(ContentsMeasurement.TICKS)
        require(
            all(
                is_number(contents.get(name)) and contents[name] >= 0
                for name in lengths
            )
            and contents[ContentsMeasurement.SIMULATED_SECONDS] > 0
            and contents.get(ContentsMeasurement.MODEL)
            == ContentsModel.RELATIVE_CONTACT
            and contents.get(ContentsMeasurement.RETAINED_CONTENTS) is True
            and contents.get(ContentsMeasurement.ESCAPED_CONTENTS) == []
            and contents.get(ContentsMeasurement.CONTENTS_COUNT)
            == self.required_contents
            and type(ticks) is int
            and ticks > 0,
            ReleaseProblem.CONTENTS_LOST,
        )

    def validate_frames(self, trajectory: Trajectory) -> None:
        """
        :param trajectory: The recorded trajectory.
        :raises InvalidWorkshopRelease: When a value is not finite or a quaternion is
            not a unit.
        """
        require(
            all(
                is_number(value)
                for frame in trajectory.frames
                for value in frame.values()
            ),
            ReleaseProblem.INVALID_POSE,
        )
        poses: List[Pose] = list(trajectory.base)
        for frames in (
            trajectory.objects,
            trajectory.body_poses,
            trajectory.model_bases,
        ):
            poses.extend(PoseFrames(frames).poses())
        require(
            all(UnitPose(pose).is_valid() for pose in poses),
            ReleaseProblem.INVALID_POSE,
        )

    def validate_segments(self, scene: SceneDescription, frame_count: int) -> None:
        """
        :param scene: The scene description with the recorded steps.
        :param frame_count: How many frames the trajectory has.
        :raises InvalidWorkshopRelease: When the steps overlap, run backwards or leave
            the recording.
        """
        end = -1
        for segment in scene.segments:
            require(
                end < segment.start <= segment.end < frame_count,
                ReleaseProblem.INVALID_SEGMENTS,
            )
            end = segment.end


@dataclass(frozen=True)
class PoseFrames:
    """
    Recorded frames of poses by key.
    """

    frames: List[Dict[str, Pose]]
    """
    The frames.
    """

    def poses(self) -> Iterable[Pose]:
        """
        :return: Every pose of every frame.
        """
        return (pose for frame in self.frames for pose in frame.values())


@dataclass(frozen=True)
class UnitPose:
    """
    A recorded pose, checked for finite numbers and a unit quaternion.
    """

    pose: Pose
    """
    The pose.
    """

    def is_valid(self) -> bool:
        """
        :return: Whether its numbers are finite and its quaternion is a unit.
        """
        values = self.pose.to_json()
        return all(math.isfinite(value) for value in values) and (
            abs(sum(value * value for value in values[3:]) - 1.0)
            < UNIT_QUATERNION_TOLERANCE
        )
