"""
Scene directories and the catalog that merges them.
"""

from __future__ import annotations

import pytest

from cramera.exceptions import FileNotInDirectory, UnknownScene
from cramera.locations import DataLocations
from cramera.scenes import SceneDirectory, SceneSource
from cramera_protocol.bundle.files import BundleFile, ScenesDirectoryFile
from cramera_protocol.viewer import EnvironmentVariable


def test_a_directory_without_an_index_derives_one_from_its_bundles(scenes):
    derived = SceneDirectory(
        scenes / "shared_scenes", SceneSource.SHARED
    ).derived_index()
    assert [entry.name for entry in derived.index.scenes] == ["cell", "warehouse"]
    assert {problem.bundle.name for problem in derived.problems} == {
        "bad name",
        "broken",
    }


def test_a_derived_entry_prefers_the_labels_a_person_gave(scenes):
    index = SceneDirectory(scenes / "shared_scenes", SceneSource.SHARED).index()
    warehouse = index.entry("warehouse")
    assert (warehouse.robot, warehouse.environment, warehouse.task) == (
        "pr2",
        "Warehouse Hall",
        "transport",
    )


def test_a_derived_entry_names_the_environment_after_its_models(scenes):
    cell = (
        SceneDirectory(scenes / "shared_scenes", SceneSource.SHARED)
        .index()
        .entry("cell")
    )
    assert cell.environment == "aicor_cell_environment"
    assert cell.robot == "aicor_cell_arm"


def test_a_directory_with_an_index_uses_it(scenes):
    index = SceneDirectory(scenes / "demo_scenes", SceneSource.DEMO).index()
    assert index.default == "converted"


def test_a_missing_directory_holds_no_bundles(tmp_path):
    assert SceneDirectory(tmp_path / "absent", SceneSource.LOCAL).index().scenes == []


def test_the_catalog_prefers_local_then_shared_then_demo_bundles(catalog):
    index = catalog.index()
    assert [entry.name for entry in index.scenes] == ["cell", "warehouse", "converted"]
    assert index.entry("cell").robot == "local arm"
    assert catalog.directory_of("cell").source is SceneSource.LOCAL


def test_the_catalog_leaves_out_indexed_bundles_that_do_not_exist(catalog):
    assert catalog.index().entry("listed_but_missing") is None


def test_the_catalog_default_is_the_first_visible_default(catalog):
    assert catalog.index().default == "converted"


def test_a_bundle_file_is_served_from_the_preferred_directory(catalog, scenes):
    path = catalog.bundle_file("cell", BundleFile.SCENE)
    assert path == (scenes / "local_scenes" / "cell" / BundleFile.SCENE).resolve()


@pytest.mark.parametrize(
    "name", ["missing", "../shared_scenes", "bad name", "__live__"]
)
def test_an_unknown_or_invalid_bundle_name_is_refused(catalog, name):
    with pytest.raises(UnknownScene):
        catalog.directory_of(name)


def test_a_missing_bundle_file_is_refused(catalog):
    with pytest.raises(FileNotInDirectory):
        catalog.bundle_file("cell", ScenesDirectoryFile.INDEX)


def test_locations_follow_the_environment(tmp_path):
    environment = {
        EnvironmentVariable.DATA: str(tmp_path / "data"),
        EnvironmentVariable.SCENES: str(tmp_path / "shared"),
    }
    locations = DataLocations.from_environment(environment, tmp_path / "home")
    assert locations.local_scenes == tmp_path / "data" / "scenes"
    assert locations.shared_scenes == tmp_path / "shared"


def test_locations_default_to_the_home_directory(tmp_path):
    locations = DataLocations.from_environment({}, tmp_path)
    assert locations.data == tmp_path / ".cramera"
    assert locations.shared_scenes is None
