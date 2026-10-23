"""
Preparing, checking and exporting presentation directories.
"""

from __future__ import annotations

import json

import pytest

from cramera.exceptions import UnknownScene
from cramera.static_site import SiteDirectoryNotEmpty
from cramera_offline.exceptions import IncompleteBundles, PresentationExists
from cramera_offline.plugin import OfflinePlugin
from cramera_offline.presentation import (
    PresentationDirectory,
    PresentationPreparation,
    PresentationSite,
)
from cramera_protocol.bundle.files import ScenesDirectoryFile
from cramera_protocol.bundle.index import SceneIndex
from cramera_protocol.offline import PresentationFile, Storyboard
from cramera_protocol.version import CURRENT_VERSION
from cramera_protocol.viewer import ViewerInfo, ViewerRoute

# %% preparation


@pytest.fixture
def presentation(tmp_path, recorded_scenes, storyboard_file) -> PresentationDirectory:
    """
    :return: A presentation prepared from the storyboard of the complete bundle.
    """
    return PresentationPreparation(
        storyboard_file, [recorded_scenes], tmp_path / "presentation"
    ).prepare()


def test_preparation_copies_the_shown_bundles_only(presentation, storyboard_file):
    shown = Storyboard.from_json(json.loads(storyboard_file.read_text())).scene_names()
    bundles = sorted(path.name for path in presentation.path.iterdir() if path.is_dir())
    assert bundles == sorted(shown)


def test_preparation_writes_the_storyboard_with_the_current_version(
    presentation, storyboard_file
):
    written = presentation.storyboard()
    expected = Storyboard.from_json(json.loads(storyboard_file.read_text()))
    assert written.format_version == CURRENT_VERSION
    assert written.chapters == expected.chapters


def test_preparation_writes_an_index_opening_the_first_chapter(presentation):
    index = SceneIndex.from_json(
        json.loads((presentation.path / ScenesDirectoryFile.INDEX).read_text())
    )
    first = presentation.storyboard().chapters[0].scene
    assert index.default == first
    assert [entry.name for entry in index.scenes] == [first]


def test_a_prepared_presentation_is_complete(presentation):
    assert all(report.is_complete() for report in presentation.check())


def test_preparation_refuses_a_directory_with_files(
    tmp_path, recorded_scenes, storyboard_file
):
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "notes.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(PresentationExists):
        PresentationPreparation(
            storyboard_file, [recorded_scenes], tmp_path / "taken"
        ).prepare()


def test_preparation_refuses_incomplete_bundles_before_writing(
    tmp_path, recorded_scenes, dataset
):
    destination = tmp_path / "presentation"
    with pytest.raises(IncompleteBundles) as refused:
        PresentationPreparation(
            dataset / "storyboard_with_broken_bundle.json",
            [recorded_scenes],
            destination,
        ).prepare()
    assert [report.bundle for report in refused.value.reports] == ["broken_cell"]
    assert not destination.exists()


def test_preparation_refuses_a_storyboard_showing_an_unknown_bundle(
    tmp_path, recorded_scenes, dataset
):
    with pytest.raises(UnknownScene):
        PresentationPreparation(
            dataset / "storyboard_with_unknown_scene.json",
            [recorded_scenes],
            tmp_path / "presentation",
        ).prepare()


# %% static site


def test_the_static_site_carries_the_plugin_and_its_storyboard(tmp_path, presentation):
    output = tmp_path / "site"
    index = PresentationSite(presentation, output).write()
    plugin = OfflinePlugin()
    assert index.default == presentation.storyboard().chapters[0].scene
    storyboard = json.loads((output / plugin.storyboard_route().strip("/")).read_text())
    assert Storyboard.from_json(storyboard) == presentation.storyboard()
    info = ViewerInfo.from_json(
        json.loads((output / ViewerRoute.INFO.strip("/")).read_text())
    )
    assert info.plugins == [plugin.info()]


def test_the_static_site_refuses_a_directory_with_files(tmp_path, presentation):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("", encoding="utf-8")
    with pytest.raises(SiteDirectoryNotEmpty):
        PresentationSite(presentation, tmp_path / "site").write()


def test_a_presentation_without_a_storyboard_file_cannot_be_read(tmp_path):
    with pytest.raises(FileNotFoundError):
        PresentationDirectory(tmp_path).storyboard()


def test_the_presentation_is_a_shared_scenes_directory(presentation):
    assert presentation.scene_directory().path == presentation.path
    assert presentation.scene_directory().holds(
        presentation.storyboard().chapters[0].scene
    )
    assert (presentation.path / PresentationFile.STORYBOARD).is_file()
