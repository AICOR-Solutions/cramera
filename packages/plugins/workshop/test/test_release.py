"""
The release check of a recorded assembly: a complete recording passes, and each kind of
missing or failed evidence is named.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typing_extensions import Any, Callable

from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneKey, SegmentKey
from cramera_protocol.bundle.trajectory import TrajectoryKey
from cramera_protocol.workshop import WorkshopSceneKey
from cramera_workshop.acceptance import (
    ContentsMeasurement,
    DemoMeasurement,
)
from cramera_workshop.bundle import WorkshopFile
from cramera_workshop.release import (
    InvalidWorkshopRelease,
    ReleaseProblem,
    WorkshopRelease,
)

RECORDING = "aicor_workshop_pr2_screw_assembly"
"""
The recorded assembly of the dataset.
"""

# %% fixtures


@pytest.fixture
def recording(dataset, tmp_path) -> Path:
    """
    :return: A copy of the dataset's complete recording.
    """
    copy = tmp_path / RECORDING
    shutil.copytree(dataset / "recordings" / RECORDING, copy)
    return copy


def edit(directory: Path, file_name: str, change: Callable[[Any], None]) -> None:
    """
    Change one JSON document of a recording.

    :param directory: The recording.
    :param file_name: The document.
    :param change: Changes its decoded content in place.
    """
    path = directory / file_name
    document = json.loads(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(json.dumps(document), encoding="utf-8")


def problem_of(directory: Path) -> ReleaseProblem:
    with pytest.raises(InvalidWorkshopRelease) as refused:
        WorkshopRelease(directory).validate()
    return refused.value.problem


# %% complete recording


def test_a_complete_recording_passes(recording):
    WorkshopRelease(recording).validate()


def test_a_recording_without_collision_contacts_passes(recording):
    edit(
        recording,
        BundleFile.ACCEPTANCE_METRICS,
        lambda metrics: metrics.pop(DemoMeasurement.MINIMUM_COLLISION_DISTANCE),
    )
    WorkshopRelease(recording).validate()


# %% refused recordings


def test_a_missing_document_is_named(recording):
    (recording / BundleFile.ACCEPTANCE_METRICS).unlink()
    assert problem_of(recording) is ReleaseProblem.MISSING_DOCUMENT


def test_a_recording_saved_under_another_name_is_refused(recording):
    renamed = recording.parent / "other_name"
    recording.rename(renamed)
    assert problem_of(renamed) is ReleaseProblem.NOT_THE_BUNDLE


def test_missing_assets_are_refused(recording):
    edit(
        recording,
        BundleFile.SCENE,
        lambda scene: scene.update({SceneKey.MISSING_ASSETS: ["meshes/screw.glb"]}),
    )
    assert problem_of(recording) is ReleaseProblem.MISSING_ASSETS


def test_a_recording_without_the_assets_rights_is_refused(recording):
    edit(
        recording,
        BundleFile.SCENE,
        lambda scene: scene.pop(WorkshopSceneKey.ASSET_RIGHTS),
    )
    assert problem_of(recording) is ReleaseProblem.MISSING_RIGHTS


def test_a_recording_without_its_notice_is_refused(recording):
    (recording / WorkshopFile.RIGHTS).unlink()
    assert problem_of(recording) is ReleaseProblem.MISSING_NOTICES


def test_a_failed_stage_is_refused(recording):
    def fail_last(metrics):
        metrics[DemoMeasurement.ACTION_STATUSES][-1] = "FAILED"

    edit(recording, BundleFile.ACCEPTANCE_METRICS, fail_last)
    assert problem_of(recording) is ReleaseProblem.FAILED_ACTION


@pytest.mark.parametrize(
    "measurement, value, problem",
    [
        (DemoMeasurement.BOX_POSITION_ERROR, 0.05, ReleaseProblem.BOX_MISPLACED),
        (DemoMeasurement.SCREW_DEPTH, 0.05, ReleaseProblem.SCREW_NOT_DRIVEN),
        (DemoMeasurement.DRIVER_RELEASED, False, ReleaseProblem.HANDS_NOT_RELEASED),
        (DemoMeasurement.MINIMUM_COLLISION_DISTANCE, -0.01, ReleaseProblem.PENETRATION),
        (DemoMeasurement.REQUIRED_DEPTH, "deep", ReleaseProblem.INCOMPLETE_METRICS),
    ],
)
def test_an_unmet_requirement_is_named(recording, measurement, value, problem):
    edit(
        recording,
        BundleFile.ACCEPTANCE_METRICS,
        lambda metrics: metrics.update({measurement: value}),
    )
    assert problem_of(recording) is problem


def test_an_escaped_screw_is_refused(recording):
    def escape(metrics):
        contents = metrics[DemoMeasurement.CONTENTS]
        contents[ContentsMeasurement.RETAINED_CONTENTS] = False
        contents[ContentsMeasurement.ESCAPED_CONTENTS] = ["screw_3"]

    edit(recording, BundleFile.ACCEPTANCE_METRICS, escape)
    assert problem_of(recording) is ReleaseProblem.CONTENTS_LOST


def test_an_empty_trajectory_is_refused(recording):
    def empty(trajectory):
        for key in (TrajectoryKey.FRAMES, TrajectoryKey.BASE, TrajectoryKey.OBJECTS):
            trajectory[key] = []

    edit(recording, BundleFile.TRAJECTORY, empty)
    edit(
        recording, BundleFile.SCENE, lambda scene: scene.update({SceneKey.SEGMENTS: []})
    )
    assert problem_of(recording) is ReleaseProblem.NO_FRAMES


def test_a_quaternion_that_is_no_unit_is_refused(recording):
    def stretch(trajectory):
        trajectory[TrajectoryKey.BASE][0][-1] = 2.0

    edit(recording, BundleFile.TRAJECTORY, stretch)
    assert problem_of(recording) is ReleaseProblem.INVALID_POSE


def test_overlapping_steps_are_refused(recording):
    def overlap(scene):
        scene[SceneKey.SEGMENTS][1][SegmentKey.START] = 0

    edit(recording, BundleFile.SCENE, overlap)
    assert problem_of(recording) is ReleaseProblem.INVALID_SEGMENTS


def test_the_refusal_explains_itself(recording):
    (recording / BundleFile.SCENE).unlink()
    with pytest.raises(InvalidWorkshopRelease) as refused:
        WorkshopRelease(recording).validate()
    assert refused.value.message().startswith(ReleaseProblem.MISSING_DOCUMENT.value)
