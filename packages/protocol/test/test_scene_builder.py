"""
The scene builder's drafts, catalog and limits.
"""

from __future__ import annotations

import pytest

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.exceptions import (
    InvalidDocumentValue,
    UnexpectedDocumentField,
    UnsupportedProtocolVersion,
)
from cramera_protocol.geometry import Vector3
from cramera_protocol.scene_builder import (
    AppearanceKey,
    BuilderPageParameter,
    CatalogKey,
    DraftKey,
    DraftRecord,
    DraftRecordKey,
    InstanceKey,
    LimitsKey,
    PointCloudAppearance,
    PointCloudEncoding,
    PointCloudFormat,
    ResourceCategory,
    ResourceKind,
    SceneBuilderCatalog,
    SceneBuilderLimits,
    SceneDraft,
    UNIT_SCALE,
)
from cramera_protocol.version import CURRENT_VERSION

# %% drafts


def test_a_draft_reads_its_instances_offsets_and_reference(read_json):
    data = read_json("scene_builder/draft.json")
    draft = SceneDraft.from_json(data)
    model, scan = draft.instances
    written_model = data[DraftKey.INSTANCES][0]
    assert model.position == Vector3.from_json(written_model[InstanceKey.POSITION])
    assert model.link_offsets["drawer"].rotation == Vector3.from_json(
        written_model[InstanceKey.LINK_OFFSETS]["drawer"]["rotation"]
    )
    assert model.joint_positions == written_model[InstanceKey.JOINT_POSITIONS]
    assert model.point_cloud is None
    assert (
        scan.point_cloud.locked
        is data[DraftKey.INSTANCES][1][InstanceKey.POINT_CLOUD][AppearanceKey.LOCKED]
    )
    assert draft.source_scene == data[DraftKey.SOURCE_SCENE]


def test_a_draft_round_trips(read_json):
    draft = SceneDraft.from_json(read_json("scene_builder/draft.json"))
    assert SceneDraft.from_json(draft.to_json()) == draft


def test_left_out_fields_take_their_defaults(read_json):
    draft = SceneDraft.from_json(read_json("scene_builder/draft_with_defaults.json"))
    cup, scan = draft.instances
    assert draft.format_version == CURRENT_VERSION
    assert cup.scale == UNIT_SCALE
    assert cup.link_offsets == {} and cup.joint_positions == {}
    assert scan.point_cloud == PointCloudAppearance()


def test_a_written_draft_names_the_current_version():
    written = SceneDraft(name="Empty").to_json()
    assert written[DraftKey.FORMAT_VERSION] == CURRENT_VERSION.to_json()
    assert DraftKey.SOURCE_SCENE not in written


def test_a_draft_of_another_major_version_is_refused(read_json):
    with pytest.raises(UnsupportedProtocolVersion):
        SceneDraft.from_json(
            read_json("scene_builder/invalid/draft_from_next_major_version.json")
        )


def test_an_instance_with_an_unknown_key_is_refused(read_json):
    with pytest.raises(UnexpectedDocumentField):
        SceneDraft.from_json(
            read_json("scene_builder/invalid/draft_with_unknown_instance_key.json")
        )


@pytest.mark.parametrize(
    "file_name",
    ["draft_with_short_position.json", "draft_with_text_joint_value.json"],
)
def test_an_instance_with_a_malformed_value_is_refused(read_json, file_name):
    with pytest.raises(InvalidDocumentValue):
        SceneDraft.from_json(read_json(f"scene_builder/invalid/{file_name}"))


def test_a_record_without_identity_asks_for_a_new_draft():
    record = DraftRecord(document=SceneDraft(name="New"))
    written = record.to_json()
    assert DraftRecordKey.IDENTIFIER not in written
    assert DraftRecord.from_json(written) == record


# %% catalog


def test_the_catalog_reads_resources_scenes_drafts_and_limits(read_json):
    data = read_json("scene_builder/catalog.json")
    catalog = SceneBuilderCatalog.from_json(data)
    robot, scan = catalog.resources
    assert (robot.kind, robot.category) == (ResourceKind.URDF, ResourceCategory.ROBOT)
    assert scan.point_cloud.file_format is PointCloudFormat.PLY
    assert scan.point_cloud.encoding is PointCloudEncoding.BINARY_LITTLE_ENDIAN
    assert [scene.name for scene in catalog.scenes] == [
        scene["name"] for scene in data[CatalogKey.SCENES]
    ]
    assert (
        catalog.limits.maximum_instances
        == data[CatalogKey.LIMITS][LimitsKey.MAXIMUM_INSTANCES]
    )
    assert catalog.limits.maximum_scale == SceneBuilderLimits().maximum_scale
    assert SceneBuilderCatalog.from_json(catalog.to_json()) == catalog


def test_a_resource_of_an_unknown_category_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        SceneBuilderCatalog.from_json(
            read_json("scene_builder/invalid/catalog_with_unknown_category.json")
        )


def test_an_empty_catalog_carries_the_default_limits_and_appearance():
    written = SceneBuilderCatalog().to_json()
    assert written[CatalogKey.LIMITS] == SceneBuilderLimits().to_json()
    assert written[CatalogKey.DEFAULT_APPEARANCE] == PointCloudAppearance().to_json()


# %% browser


def test_the_builder_page_parameters_reach_the_browser():
    assert BuilderPageParameter in BROWSER_ENUMERATIONS
