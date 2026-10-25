"""
Reading recorded, converted and plugin-written scene descriptions.
"""

from __future__ import annotations

import pytest

from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import (
    LegacyPlanNodeKind,
    PartRole,
    PartSide,
    PlanNode,
    PlanNodeKey,
    PlanNodeKind,
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


def plan_node(kind: str) -> dict:
    """
    :return: A recorded plan node of a kind.
    """
    return {
        PlanNodeKey.KIND: kind,
        PlanNodeKey.LABEL: "ParkArmsAction",
        PlanNodeKey.STATUS: "SUCCEEDED",
    }


@pytest.mark.parametrize("legacy", list(LegacyPlanNodeKind))
def test_an_earlier_recordings_class_name_is_read_as_its_kind(legacy):
    node = PlanNode.from_json(plan_node(legacy.value))
    assert node.kind is PlanNodeKind[legacy.name]
    assert node.to_json()[PlanNodeKey.KIND] == PlanNodeKind[legacy.name].value


def test_a_class_name_no_kind_stands_for_is_read_as_other():
    assert PlanNode.from_json(plan_node("TryAllNode")).kind is PlanNodeKind.OTHER


def test_a_kind_is_read_as_itself():
    assert PlanNode.from_json(plan_node("motion")).kind is PlanNodeKind.MOTION


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


def test_a_plan_node_names_the_frames_it_ran_in(read_json):
    data = read_json("recorded_plan_steps_scene.json")
    root = SceneDescription.from_json(data).plan_trees[0]
    written_steps = data[SceneKey.PLAN_TREES][0][PlanNodeKey.CHILDREN]
    navigate = root.children[1]
    assert (navigate.start, navigate.end) == (
        written_steps[1][PlanNodeKey.START],
        written_steps[1][PlanNodeKey.END],
    )
    assert navigate.extensions == {}


def test_a_plan_node_that_never_ran_has_no_frames(read_json):
    place = (
        SceneDescription.from_json(read_json("recorded_plan_steps_scene.json"))
        .plan_trees[0]
        .children[2]
    )
    assert (place.start, place.end) == (None, None)
    assert PlanNodeKey.START not in place.to_json()


def test_each_plan_root_names_the_robot_that_performed_it(read_json):
    data = read_json("recorded_robot_plans_scene.json")
    roots = SceneDescription.from_json(data).plan_trees
    assert [root.robot for root in roots] == [
        written[PlanNodeKey.ROBOT] for written in data[SceneKey.PLAN_TREES]
    ]
    assert roots[0].extensions == {}


def test_a_plan_node_without_a_robot_writes_none(read_json):
    step = (
        SceneDescription.from_json(read_json("recorded_robot_plans_scene.json"))
        .plan_trees[0]
        .children[0]
    )
    assert step.robot is None
    assert PlanNodeKey.ROBOT not in step.to_json()


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
