"""
The resource library: its roots, the files it lists and serves, and their notices.
"""

from __future__ import annotations

import pytest

from cramera.exceptions import FileNotInDirectory, PathOutsideDirectory
from cramera.scenes import SceneSource
from cramera_protocol.scene_builder import (
    ReservedResourceRoot,
    ResourceCategory,
    ResourceKind,
    SceneBuilderVariable,
)
from cramera_scene_builder.exceptions import (
    InvalidResourceIdentifier,
    InvalidRootName,
    NotAModel,
    NotAPointCloud,
    OutsideLibrary,
    UnknownResourceRoot,
    UnservedResourceFile,
)
from cramera_scene_builder.plugin import LibraryRoots
from cramera_scene_builder.resources import (
    NoticeFile,
    POINT_CLOUD_FORMATS,
    ResourceIdentifier,
)

from .conftest import LIBRARY_ROOT

# %% identifiers


def test_an_identifier_names_its_root_and_path():
    identifier = ResourceIdentifier.parse(f"{LIBRARY_ROOT}/kitchen/cabinet.urdf")
    assert (identifier.root, identifier.path) == (LIBRARY_ROOT, "kitchen/cabinet.urdf")
    assert identifier.text() == f"{LIBRARY_ROOT}/kitchen/cabinet.urdf"


@pytest.mark.parametrize(
    "text",
    [
        "cabinet.urdf",
        "library//cabinet.urdf",
        "library/../cabinet.urdf",
        "library/./cabinet.urdf",
        "library/.hidden/secret.urdf",
        "library\\kitchen\\cabinet.urdf",
        "library/kitchen/cabinet%2Eurdf",
        "library/kitchen/cabinet.urdf\x00",
    ],
)
def test_identifiers_with_unsafe_segments_are_refused(text):
    with pytest.raises(InvalidResourceIdentifier):
        ResourceIdentifier.parse(text)


# %% roots


def test_the_roots_are_the_uploads_the_scenes_and_the_configured_directories(
    library, workspace, storage
):
    assert library.roots == {
        ReservedResourceRoot.POINT_CLOUDS: storage.point_clouds,
        SceneSource.DEMO: workspace / "scenes",
        LIBRARY_ROOT: workspace / LIBRARY_ROOT,
    }


def test_a_configured_directory_named_like_another_root_is_refused(
    catalog, storage, workspace
):
    directory = workspace / SceneSource.DEMO.value
    directory.mkdir()
    with pytest.raises(InvalidRootName) as refused:
        LibraryRoots.of(
            catalog, storage, {SceneBuilderVariable.LIBRARY: str(directory)}
        )
    assert refused.value.directory == directory


def test_a_configured_directory_without_a_plain_name_is_refused(
    catalog, storage, workspace
):
    directory = workspace / "my library"
    with pytest.raises(InvalidRootName):
        LibraryRoots.of(
            catalog, storage, {SceneBuilderVariable.LIBRARY: str(directory)}
        )


def test_an_unknown_root_is_refused(library):
    with pytest.raises(UnknownResourceRoot) as refused:
        library.file(ResourceIdentifier("elsewhere", "cabinet.urdf"))
    assert refused.value.root == "elsewhere"


# %% listing


def describe(library):
    return {resource.identifier: resource for resource in library.resources()}


def test_the_library_lists_models_meshes_and_point_clouds_only(library):
    listed = describe(library)
    assert f"{LIBRARY_ROOT}/kitchen/cabinet.urdf" in listed
    assert f"{LIBRARY_ROOT}/kitchen/meshes/door.stl" in listed
    assert f"{LIBRARY_ROOT}/props/cup.gltf" in listed
    assert f"{LIBRARY_ROOT}/kitchen/meshes/handle.mtl" not in listed
    assert f"{LIBRARY_ROOT}/notes.txt" not in listed
    assert f"{LIBRARY_ROOT}/props/cup.bin" not in listed
    assert not any(".hidden" in identifier for identifier in listed)


def test_resources_have_their_kind_and_category(library):
    listed = describe(library)
    cabinet = listed[f"{LIBRARY_ROOT}/kitchen/cabinet.urdf"]
    arm = listed[f"{LIBRARY_ROOT}/robots/arm/model.urdf"]
    door = listed[f"{LIBRARY_ROOT}/kitchen/meshes/door.stl"]
    assert (cabinet.kind, cabinet.category) == (
        ResourceKind.URDF,
        ResourceCategory.OBJECT,
    )
    assert (arm.kind, arm.category) == (ResourceKind.URDF, ResourceCategory.ROBOT)
    assert (door.kind, door.category) == (ResourceKind.MESH, ResourceCategory.OBJECT)


def test_bundle_models_take_their_category_from_the_scene(library):
    listed = describe(library)
    assert (
        listed[f"{SceneSource.DEMO}/cell/arm.urdf"].category is ResourceCategory.ROBOT
    )
    assert (
        listed[f"{SceneSource.DEMO}/cell/table.urdf"].category
        is ResourceCategory.ENVIRONMENT
    )


def test_a_generically_named_model_is_named_after_its_directory(library):
    assert describe(library)[f"{LIBRARY_ROOT}/robots/arm/model.urdf"].name == "arm"
    assert describe(library)[f"{LIBRARY_ROOT}/kitchen/cabinet.urdf"].name == "cabinet"


def test_notices_are_found_next_to_a_resource_and_above_it(library):
    cabinet = describe(library)[f"{LIBRARY_ROOT}/kitchen/cabinet.urdf"]
    assert [(notice.name, notice.asset) for notice in cabinet.notices] == [
        (NoticeFile.LICENSE_TEXT, f"{LIBRARY_ROOT}/kitchen/{NoticeFile.LICENSE_TEXT}"),
        (NoticeFile.NOTICE, f"{LIBRARY_ROOT}/{NoticeFile.NOTICE}"),
    ]


def test_a_link_leading_out_of_its_root_is_not_listed(library, workspace):
    outside = workspace / "outside.urdf"
    outside.write_text("<robot name='outside'/>", encoding="utf-8")
    (workspace / LIBRARY_ROOT / "linked.urdf").symlink_to(outside)
    assert f"{LIBRARY_ROOT}/linked.urdf" not in describe(library)


# %% files


def test_a_file_outside_its_root_is_refused(library, workspace):
    (workspace / LIBRARY_ROOT / "linked.urdf").symlink_to(workspace / "outside.urdf")
    with pytest.raises(PathOutsideDirectory):
        library.file(ResourceIdentifier(LIBRARY_ROOT, "linked.urdf"))


def test_a_missing_file_is_refused(library):
    with pytest.raises(FileNotInDirectory):
        library.file(ResourceIdentifier(LIBRARY_ROOT, "kitchen/gone.urdf"))


def test_a_file_that_is_no_model_dependency_or_notice_is_not_served(library):
    with pytest.raises(UnservedResourceFile):
        library.file(ResourceIdentifier(LIBRARY_ROOT, "notes.txt"))


def test_notices_and_dependencies_are_served_but_not_placed(library):
    notice = ResourceIdentifier(LIBRARY_ROOT, NoticeFile.NOTICE)
    material = ResourceIdentifier(LIBRARY_ROOT, "kitchen/meshes/handle.mtl")
    assert library.file(notice).name == NoticeFile.NOTICE
    with pytest.raises(NotAModel):
        library.placeable_file(material)


def test_the_identifier_of_a_file_outside_every_root_is_refused(library, workspace):
    outside = workspace / "outside.urdf"
    outside.write_text("<robot name='outside'/>", encoding="utf-8")
    with pytest.raises(OutsideLibrary):
        library.identifier_of(outside)


def test_point_cloud_formats_follow_the_suffix(library):
    for suffix, point_cloud_format in POINT_CLOUD_FORMATS.items():
        identifier = ResourceIdentifier(LIBRARY_ROOT, f"scan{suffix}")
        assert library.point_cloud_format(identifier) is point_cloud_format
    with pytest.raises(NotAPointCloud):
        library.point_cloud_format(
            ResourceIdentifier(LIBRARY_ROOT, "kitchen/cabinet.urdf")
        )
