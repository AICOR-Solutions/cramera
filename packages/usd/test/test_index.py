"""
The scenes index, rebuilt from the bundles a scenes directory holds.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cramera_protocol.bundle.files import BundleFile, ScenesDirectoryFile
from cramera_protocol.bundle.index import SceneIndex
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.version import CURRENT_VERSION
from cramera_usd.bundle.index import MODEL_NAME_SEPARATOR, NO_ROBOT, ScenesIndex
from cramera_usd.bundle.json_file import JsonFile

# %% scenes directories

SCENES = "scenes"
"""
A scenes directory with an index, readable bundles, a broken one and a directory that is
no bundle.
"""

BROKEN_INDEX = "scenes_with_broken_index"
"""
A scenes directory whose index is no scenes index.
"""

# %% helpers


@pytest.fixture
def scenes(dataset, tmp_path) -> Path:
    """
    :return: A copy of the scenes directory to rebuild the index of.
    """
    return Path(shutil.copytree(dataset / SCENES, tmp_path / SCENES))


def scene_of(scenes: Path, name: str) -> SceneDescription:
    """
    :param scenes: A scenes directory.
    :param name: A bundle in it.
    :return: The bundle's scene description.
    """
    return SceneDescription.from_json(JsonFile(scenes / name / BundleFile.SCENE).read())


# %% entries


def test_the_index_lists_every_readable_bundle_in_name_order(scenes):
    index = ScenesIndex(scenes).rebuild("bench")
    assert [entry.name for entry in index.scenes] == ["bench", "demo_run"]
    assert index.format_version == CURRENT_VERSION
    written = SceneIndex.from_json(JsonFile(scenes / ScenesDirectoryFile.INDEX).read())
    assert written == index


def test_a_broken_bundle_is_left_out_and_reported(scenes):
    index = ScenesIndex(scenes)
    index.rebuild("bench")
    assert [problem.bundle.name for problem in index.unreadable] == ["broken"]


# %% default scene


def test_the_default_of_the_index_is_kept(scenes):
    existing = SceneIndex.from_json(JsonFile(scenes / ScenesDirectoryFile.INDEX).read())
    assert ScenesIndex(scenes).rebuild("demo_run").default == existing.default


def test_a_new_index_opens_the_bundle_just_written(scenes):
    (scenes / ScenesDirectoryFile.INDEX).unlink()
    assert ScenesIndex(scenes).rebuild("demo_run").default == "demo_run"


# %% labels


def test_labels_a_person_gave_win_over_the_model_names(scenes):
    entry = ScenesIndex(scenes).rebuild("bench").entry("demo_run")
    scene = scene_of(scenes, "demo_run")
    assert (entry.robot, entry.environment, entry.task) == (
        scene.robot_name,
        scene.environment_name,
        scene.task,
    )


def test_a_bundle_without_labels_is_named_by_its_models(scenes):
    entry = ScenesIndex(scenes).rebuild("bench").entry("bench")
    scene = scene_of(scenes, "bench")
    assert entry.robot == NO_ROBOT
    assert entry.environment == MODEL_NAME_SEPARATOR.join(
        model.name for model in scene.models
    )


# %% refusals


def test_an_index_that_is_no_scenes_index_is_refused_and_kept(dataset, tmp_path):
    scenes = Path(shutil.copytree(dataset / BROKEN_INDEX, tmp_path / BROKEN_INDEX))
    before = (scenes / ScenesDirectoryFile.INDEX).read_bytes()
    with pytest.raises(ProtocolError):
        ScenesIndex(scenes).rebuild("bench")
    assert (scenes / ScenesDirectoryFile.INDEX).read_bytes() == before
