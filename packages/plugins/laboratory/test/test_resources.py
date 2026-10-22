"""
The shipped laboratories, their asset terms, and installing them for the viewer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cramera.scenes import SceneDirectory, SceneSource
from cramera_laboratory.exceptions import (
    MissingLaboratoryBundle,
    NotALaboratory,
    UnknownLaboratory,
)
from cramera_laboratory.resources import (
    RESOURCES_DIRECTORY,
    AuthoringFile,
    LaboratoryBundle,
    LaboratoryInstallation,
    LaboratoryResource,
    RightsFile,
)
from cramera_laboratory.scene_files import JsonFile
from cramera_protocol.bundle.files import BundleFile, ScenesDirectoryFile
from cramera_protocol.bundle.index import SceneIndex, SceneIndexEntry
from cramera_protocol.laboratory.layout import LaboratorySceneKey
from cramera_protocol.rights import AssetRights

from .conftest import DATASET

LABORATORY_LICENSE = "LicenseRef-AICOR-Laboratory-Assets"
"""
The identifier of the laboratory assets' terms, which the owner set.
"""

LICENSE_FILE = "LICENSE.txt"
"""
The licence text every asset folder carries.
"""

NOTICE_FILE = "NOTICE.md"
"""
The credits every asset folder carries.
"""

OTHER_BUNDLE = "a_recording"
"""
A bundle another tool listed in the local index.
"""

# %% shelf


def test_the_shelf_offers_the_bench_and_the_expanded_room(shelf):
    names = [laboratory.name for laboratory in shelf.laboratories()]
    assert names == [LaboratoryResource.BENCH, LaboratoryResource.EXPANDED]


def test_only_the_expanded_room_has_instruments(shelf):
    bench = shelf.laboratory(LaboratoryResource.BENCH)
    expanded = shelf.laboratory(LaboratoryResource.EXPANDED)
    assert bench.instruments() is None
    assert expanded.instruments().instruments
    assert expanded.bench().centrifuge == bench.bench().centrifuge


def test_a_laboratory_takes_its_title_from_its_environment(bench_laboratory):
    assert bench_laboratory.title() == bench_laboratory.description.environment_name


def test_an_unknown_laboratory_is_refused(shelf):
    with pytest.raises(UnknownLaboratory):
        shelf.laboratory("kitchen")


def test_a_directory_without_a_bundle_is_refused(tmp_path):
    with pytest.raises(MissingLaboratoryBundle):
        LaboratoryBundle(tmp_path)


def test_a_bundle_without_a_bench_is_refused():
    with pytest.raises(NotALaboratory):
        LaboratoryBundle(DATASET / "plain_bundle")


# %% asset terms


def rights_records() -> list:
    """
    :return: Every rights record the plugin ships.
    """
    return sorted(RESOURCES_DIRECTORY.rglob(RightsFile.RECORD))


@pytest.mark.parametrize(
    "record",
    rights_records(),
    ids=lambda path: str(path.relative_to(RESOURCES_DIRECTORY)),
)
def test_every_asset_folder_keeps_the_owner_terms(record: Path):
    rights = AssetRights.from_json(json.loads(record.read_text(encoding="utf-8")))
    assert rights.license_identifier == LABORATORY_LICENSE
    assert (record.parent / rights.license_file).is_file()
    assert (record.parent / rights.notice_file).is_file()


def test_the_bundle_states_the_same_terms_as_its_record(bench_laboratory):
    stated = AssetRights.from_json(
        bench_laboratory.description.extensions[LaboratorySceneKey.ASSET_RIGHTS]
    )
    assert stated == bench_laboratory.asset_rights()


# %% installation


def test_installing_copies_the_laboratory_with_its_terms_but_without_sources(
    locations, shelf
):
    expanded = shelf.laboratory(LaboratoryResource.EXPANDED)
    name = LaboratoryInstallation(locations).install(expanded, expanded.name)
    copy = locations.local_scenes / name
    assert (copy / BundleFile.SCENE).is_file()
    assert (copy / LICENSE_FILE).is_file() and (copy / NOTICE_FILE).is_file()
    assert not list(copy.rglob(AuthoringFile.BLENDER))
    assert list(expanded.directory.rglob(AuthoringFile.BLENDER))


def test_an_installed_laboratory_is_shown_without_an_index(locations, bench_laboratory):
    LaboratoryInstallation(locations).install(bench_laboratory, bench_laboratory.name)
    index = SceneDirectory(locations.local_scenes, SceneSource.LOCAL).index()
    assert [entry.name for entry in index.scenes] == [bench_laboratory.name]


def test_an_installed_laboratory_joins_an_existing_index(locations, bench_laboratory):
    index_file = JsonFile(locations.local_scenes / ScenesDirectoryFile.INDEX)
    index_file.write(SceneIndex(scenes=[SceneIndexEntry(name=OTHER_BUNDLE, robot="")]))
    LaboratoryInstallation(locations).install(bench_laboratory, bench_laboratory.name)
    names = [entry.name for entry in index_file.read(SceneIndex).scenes]
    assert names == [OTHER_BUNDLE, bench_laboratory.name]


def test_installing_twice_keeps_the_first_copy(locations, bench_laboratory):
    installation = LaboratoryInstallation(locations)
    installation.install(bench_laboratory, bench_laboratory.name)
    marker = locations.local_scenes / bench_laboratory.name / "kept.txt"
    marker.write_text("kept", encoding="utf-8")
    installation.install(bench_laboratory, bench_laboratory.name)
    assert marker.is_file()
    assert installation.installed(bench_laboratory.name)
