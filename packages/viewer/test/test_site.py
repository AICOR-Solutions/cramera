"""
Upgrading bundles and exporting the viewer as a static site.
"""

from __future__ import annotations

import json
import shutil

import pytest

from cramera import bundle_upgrade, static_site
from cramera.bundle_upgrade import BundleLabels, BundleUpgrade, UpgradeOption
from cramera.static_site import (
    ExportOption,
    SiteDirectoryNotEmpty,
    SiteFile,
    StaticSite,
)
from cramera_protocol.browser import BrowserModule
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import InvalidSceneName, SceneIndex
from cramera_protocol.bundle.scene import SceneDescription, SceneKey
from cramera_protocol.bundle.trajectory import Trajectory, TrajectoryKey
from cramera_protocol.version import CURRENT_VERSION
from cramera_protocol.viewer import BuildStamp, ViewerInfo, ViewerRoute

from .conftest import DATASET

PROTOCOL_DATASET = DATASET.parent.parent.parent / "protocol" / "test" / "dataset"
"""
The protocol package's test documents, which hold an early recording.
"""


@pytest.fixture
def early_recording(tmp_path):
    bundle = tmp_path / "early"
    shutil.copytree(PROTOCOL_DATASET / "recorded_cell", bundle)
    return bundle


# %% upgrading


def test_an_upgraded_bundle_declares_the_current_version_and_current_keys(
    early_recording, tmp_path
):
    destination = tmp_path / "upgraded"
    scene = BundleUpgrade(early_recording, destination).run()
    written = json.loads((destination / BundleFile.SCENE).read_text())
    assert written[SceneKey.FORMAT_VERSION] == CURRENT_VERSION.to_json()
    assert SceneKey.LEGACY_FRAMES_PER_SECOND not in written
    assert scene.name == destination.name
    trajectory = json.loads((destination / BundleFile.TRAJECTORY).read_text())
    assert TrajectoryKey.LEGACY_FRAMES_PER_SECOND not in trajectory
    original = Trajectory.from_json(
        json.loads((early_recording / BundleFile.TRAJECTORY).read_text())
    )
    assert Trajectory.from_json(trajectory) == original


def test_labels_are_written_and_absent_labels_kept(early_recording, tmp_path):
    scene = BundleUpgrade(
        early_recording, tmp_path / "labelled", BundleLabels(task="plan")
    ).run()
    assert scene.task == "plan"
    assert scene.robot_name is None


def test_an_upgrade_needs_a_valid_new_bundle_name(early_recording, tmp_path):
    with pytest.raises(InvalidSceneName):
        BundleUpgrade(early_recording, tmp_path / "bad name").run()
    (tmp_path / "taken").mkdir()
    with pytest.raises(FileExistsError):
        BundleUpgrade(early_recording, tmp_path / "taken").run()


def test_the_upgrade_command_takes_labels(early_recording, tmp_path):
    destination = tmp_path / "commanded"
    assert (
        bundle_upgrade.main(
            [
                str(early_recording),
                str(destination),
                UpgradeOption.ENVIRONMENT_NAME,
                "Cell",
            ]
        )
        == 0
    )
    scene = SceneDescription.from_json(
        json.loads((destination / BundleFile.SCENE).read_text())
    )
    assert scene.environment_name == "Cell"


# %% exporting


@pytest.fixture
def demo_scenes(tmp_path, early_recording):
    scenes = tmp_path / "demo"
    BundleUpgrade(early_recording, scenes / "cell", BundleLabels(task="plan")).run()
    shutil.copytree(DATASET / "shared_scenes" / "warehouse", scenes / "warehouse")
    shutil.copytree(DATASET / "shared_scenes" / "broken", scenes / "broken")
    return scenes


def test_the_site_holds_the_page_the_protocol_the_routes_and_the_readable_bundles(
    demo_scenes, tmp_path
):
    output = tmp_path / "site"
    build = BuildStamp(
        commit="a" * 40,
        built_at="2026-10-22T13:00:00Z",
        source="https://github.com/sunava/cramera",
    )
    index = StaticSite(
        output, demo_scenes, default_scene="warehouse", build=build
    ).write()
    assert (output / "index.html").is_file()
    assert (output / SiteFile.PROTOCOL_MODULE).read_text() == BrowserModule().source()
    assert (output / SiteFile.NO_JEKYLL).is_file()
    assert (
        SceneIndex.from_json(
            json.loads((output / ViewerRoute.SCENES.strip("/")).read_text())
        )
        == index
    )
    assert index.default == "warehouse"
    assert [entry.name for entry in index.scenes] == ["cell", "warehouse"]
    assert (
        output / ViewerRoute.SCENE_FILES.strip("/") / "cell" / BundleFile.TRAJECTORY
    ).is_file()
    assert not (output / ViewerRoute.SCENE_FILES.strip("/") / "broken").exists()
    info = ViewerInfo.from_json(
        json.loads((output / ViewerRoute.INFO.strip("/")).read_text())
    )
    assert info.build == build


def test_a_site_is_not_written_over_existing_files(demo_scenes, tmp_path):
    output = tmp_path / "site"
    output.mkdir()
    (output / "kept.txt").write_text("kept")
    with pytest.raises(SiteDirectoryNotEmpty):
        StaticSite(output, demo_scenes).write()


def test_the_export_command_stamps_the_build(demo_scenes, tmp_path):
    output = tmp_path / "site"
    code = static_site.main(
        [
            str(output),
            ExportOption.SCENES,
            str(demo_scenes),
            ExportOption.COMMIT,
            "b" * 40,
            ExportOption.SOURCE,
            "https://example.org/repo",
        ]
    )
    assert code == 0
    info = ViewerInfo.from_json(
        json.loads((output / ViewerRoute.INFO.strip("/")).read_text())
    )
    assert info.build.commit == "b" * 40
    assert info.build.built_at.endswith("Z")


def test_an_export_without_a_commit_has_no_build_stamp(demo_scenes, tmp_path):
    output = tmp_path / "unstamped"
    static_site.main([str(output), ExportOption.SCENES, str(demo_scenes)])
    info = ViewerInfo.from_json(
        json.loads((output / ViewerRoute.INFO.strip("/")).read_text())
    )
    assert info.build is None
