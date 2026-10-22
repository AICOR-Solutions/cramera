"""
Which of the viewer's bundles a plan can run in.
"""

from __future__ import annotations

from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_plan_builder.environments import EnvironmentBundles

from .dataset.given_workspace import DATASET


def test_only_bundles_without_a_robot_model_are_environments(scenes):
    assert [entry.name for entry in EnvironmentBundles(scenes).entries()] == ["lab"]


def test_a_damaged_bundle_the_index_lists_is_no_environment():
    scenes = SceneCatalog(
        [SceneDirectory(DATASET / "damaged_scenes", SceneSource.SHARED)]
    )
    assert [entry.name for entry in scenes.index().scenes] == ["damaged"]
    assert EnvironmentBundles(scenes).entries() == []
