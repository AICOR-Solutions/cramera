"""
Reading recorded, converted and plugin-written scene descriptions.
"""

from __future__ import annotations

import pytest

from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import (
    PartRole,
    PartSide,
    SceneDescription,
    SceneKey,
)
from cramera_protocol.exceptions import (
    InvalidDocumentValue,
    MalformedProtocolVersion,
    MissingDocumentField,
    UnexpectedDocumentField,
    UnsupportedProtocolVersion,
)
from cramera_protocol.geometry import Bounds, Pose, Vector3
from cramera_protocol.version import CURRENT_VERSION, UNVERSIONED, ProtocolVersion

# %% recordings


def test_an_early_recording_reads_its_legacy_frame_rate(read_json):
    data = read_json("recorded_cell/scene.json")
    scene = SceneDescription.from_json(data)
    assert scene.format_version == UNVERSIONED
    assert scene.frames_per_second == data[SceneKey.LEGACY_FRAMES_PER_SECOND]
    assert scene.trajectory == BundleFile.TRAJECTORY
    assert [model.robot for model in scene.models] == [True, False]


def test_a_robot_recording_carries_parts_objects_steps_and_plans(read_json):
    data = read_json("recorded_warehouse_scene.json")
    scene = SceneDescription.from_json(data)
    assert scene.robot.name == data[SceneKey.ROBOT]["name"]
    assert {part.role for part in scene.robot.part_annotations} <= set(PartRole)
    assert {part.side for part in scene.robot.part_annotations} <= set(PartSide) | {
        None
    }
    assert scene.objects[0].spawn == Pose.from_json(data[SceneKey.OBJECTS][0]["spawn"])
    assert len(scene.segments) == len(data[SceneKey.SEGMENTS])
    assert scene.statecharts == BundleFile.STATECHARTS
    assert len(scene.plan_trees) == len(data.get(SceneKey.PLAN_TREES, []))


def test_a_recording_round_trips(read_json):
    scene = SceneDescription.from_json(read_json("recorded_warehouse_scene.json"))
    assert SceneDescription.from_json(scene.to_json()) == scene


def test_writing_an_early_recording_uses_current_keys(read_json):
    written = SceneDescription.from_json(
        read_json("recorded_cell/scene.json")
    ).to_json()
    assert SceneKey.FRAMES_PER_SECOND in written
    assert SceneKey.LEGACY_FRAMES_PER_SECOND not in written


# %% conversions


def test_a_converted_stage_reads_its_camera_rendering_and_source(read_json):
    data = read_json("converted_bundle/scene.json")
    scene = SceneDescription.from_json(data)
    assert scene.camera.position == Vector3.from_json(data[SceneKey.CAMERA]["position"])
    assert scene.camera.field_of_view == data[SceneKey.CAMERA]["fov"]
    assert scene.rendering.shadow_bounds == Bounds.from_json(
        data[SceneKey.RENDERING]["shadowBounds"]
    )
    assert scene.rendering.environment == BundleFile.LIGHTING
    assert scene.source.usd == data[SceneKey.SOURCE]["usd"]


# %% plugins and versions


def test_plugin_content_is_passed_on_unchanged(read_json):
    data = read_json("scene_with_plugin_content.json")
    scene = SceneDescription.from_json(data)
    assert scene.extensions == {"laboratory": {"rack": "A"}}
    assert scene.camera.extensions == {"follow": True}
    written = scene.to_json()
    assert written["laboratory"] == data["laboratory"]
    assert written[SceneKey.CAMERA]["follow"] is True
    assert SceneDescription.from_json(written) == scene


def test_a_later_minor_version_is_read(read_json):
    scene = SceneDescription.from_json(
        read_json("invalid/scene_from_later_minor_version.json")
    )
    assert scene.format_version == ProtocolVersion(major=1, minor=7)


def test_a_new_scene_declares_the_current_version():
    scene = SceneDescription(name="new", format_version=CURRENT_VERSION)
    assert scene.to_json()[SceneKey.FORMAT_VERSION] == CURRENT_VERSION.to_json()


# %% refusals


@pytest.mark.parametrize(
    "file_name, error",
    [
        ("scene_without_name.json", MissingDocumentField),
        ("scene_from_next_major_version.json", UnsupportedProtocolVersion),
        ("scene_with_malformed_version.json", MalformedProtocolVersion),
        ("scene_with_text_frame_rate.json", InvalidDocumentValue),
        ("scene_with_unknown_model_key.json", UnexpectedDocumentField),
        ("scene_with_short_pose.json", InvalidDocumentValue),
        ("scene_with_unknown_part_role.json", InvalidDocumentValue),
        ("scene_with_one_shadow_corner.json", InvalidDocumentValue),
        ("scene_with_models_text.json", InvalidDocumentValue),
        ("scene_with_number_as_flag.json", InvalidDocumentValue),
    ],
)
def test_an_invalid_scene_is_refused(read_json, file_name, error):
    with pytest.raises(error):
        SceneDescription.from_json(read_json(f"invalid/{file_name}"))
