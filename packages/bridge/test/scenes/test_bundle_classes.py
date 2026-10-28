"""
The classes of the entities of bundles recorded before scenes named them.
"""

from __future__ import annotations

import shutil

import pytest

from cramera_bridge.documents import DocumentFile
from cramera_bridge.export.world_models import WorldModels
from cramera_bridge.names import class_path
from cramera_bridge.scenes.bundle_classes import BundleClasses, main
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import (
    ObjectDescription,
    SceneDescription,
)
from cramera_protocol.geometry import Pose
from cramera_protocol.version import CURRENT_VERSION
from semantic_digital_twin.world_description.world_entity import Body

BUNDLE_NAME = "pr2_alone"
"""
The name of the bundle written from the PR2's world.
"""

# %% bundles


@pytest.fixture(scope="module")
def recording(robot_world, tmp_path_factory):
    """
    :return: The scenes directory holding a bundle written from the PR2's world, with
        one free object and without classes, and what writing the bundle named.
    """
    scenes = tmp_path_factory.mktemp("scenes")
    models = WorldModels(robot_world.world, scenes / BUNDLE_NAME, "test").write(
        [], robot_world.robot
    )
    scene = SceneDescription(
        name=BUNDLE_NAME,
        format_version=CURRENT_VERSION,
        models=models.models,
        robot=models.robot,
        objects=[
            ObjectDescription(
                identifier="milk", key="k-milk", spawn=Pose(0, 0, 0, 0, 0, 0, 1)
            )
        ],
    )
    DocumentFile(scenes / BUNDLE_NAME / BundleFile.SCENE).write(scene)
    return scenes, models


@pytest.fixture
def scenes(recording, tmp_path):
    """
    :return: A copy of the scenes directory that tests may change.
    """
    return shutil.copytree(recording[0], tmp_path / "scenes")


def test_a_bundle_names_the_classes_its_recording_named(recording):
    scenes, models = recording
    bundle = BundleClasses(scenes / BUNDLE_NAME)
    named = bundle.classes(bundle.scene_file().read(SceneDescription))
    recorded = models.classes
    assert named.world == recorded.world
    assert named.models == recorded.models
    assert named.annotations == recorded.annotations
    assert recorded.bodies.items() <= named.bodies.items()
    assert recorded.connections.items() <= named.connections.items()
    assert named.bodies["milk"] == class_path(Body)


def test_writing_names_the_classes_in_the_scene(scenes):
    path = BundleClasses(scenes / BUNDLE_NAME).write()
    scene = DocumentFile(path).read(SceneDescription)
    assert scene.classes.annotations
    assert scene.robot.name in scene.classes.models


def test_the_command_names_the_classes_of_every_bundle(scenes, capsys, monkeypatch):
    monkeypatch.chdir(scenes.parent)
    assert main([scenes.name]) == 0
    assert BUNDLE_NAME in capsys.readouterr().out
    scene = DocumentFile(scenes / BUNDLE_NAME / BundleFile.SCENE).read(SceneDescription)
    assert scene.classes is not None
