"""
Which of the viewer's bundles a plan can run in, and the annotations each offers.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlencode

from typing_extensions import List

from cramera.http.messages import HttpMethod, Request
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_plan_builder.environments import (
    EnvironmentAnnotationCache,
    EnvironmentBundles,
)
from cramera_plan_builder.plugin import PlanBuilderPlugin
from cramera_plan_builder.workspace import CramModules, WorkspaceLoader
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.live_messages import SurfaceDescription
from cramera_protocol.plan_builder import (
    EnvironmentAnnotations,
    EnvironmentAnnotationsParameter,
    PlanBuilderName,
    PlanBuilderRoute,
)
from cramera_protocol.viewer import ViewerRoute

from .conftest import HEADERS
from .dataset.given_workspace import DATASET, GivenWorkspace


def test_only_bundles_without_a_robot_model_are_environments(scenes):
    assert [entry.name for entry in EnvironmentBundles(scenes).entries()] == ["lab"]


def test_a_damaged_bundle_the_index_lists_is_no_environment():
    scenes = SceneCatalog(
        [SceneDirectory(DATASET / "damaged_scenes", SceneSource.SHARED)]
    )
    assert [entry.name for entry in scenes.index().scenes] == ["damaged"]
    assert EnvironmentBundles(scenes).entries() == []


# %% annotations


@dataclass(frozen=True)
class CountingWorkspace(GivenWorkspace):
    """
    The test workspace, giving every environment one handle and counting the worlds it
    builds.
    """

    built: List[Path] = field(default_factory=list)
    """
    The environments whose world was built, in order.
    """

    def environment_annotations(self, directory: Path) -> EnvironmentAnnotations:
        self.built.append(directory)
        return EnvironmentAnnotations(
            annotations=[SurfaceDescription(type_name="handle", name="handle_1")]
        )


def test_an_environments_annotations_are_served(serve, scenes):
    workspace = CountingWorkspace()
    loader = WorkspaceLoader()
    loader.loaded = workspace
    answerer = serve(PlanBuilderPlugin(environment={}, workspace=loader))
    answer = annotations_request(answerer, "lab")
    listed = EnvironmentAnnotations.from_json(json.loads(answer.body))
    assert answer.status == HTTPStatus.OK
    assert listed.annotations == [
        SurfaceDescription(type_name="handle", name="handle_1")
    ]
    assert annotations_request(answerer, "nowhere").status == HTTPStatus.NOT_FOUND


def test_an_environments_world_is_built_once_per_version(scenes):
    workspace = CountingWorkspace()
    loader = WorkspaceLoader()
    loader.loaded = workspace
    cache = EnvironmentAnnotationCache(loader)
    lab = scenes.directory_of("lab").path / "lab"
    cache.of(lab)
    cache.of(lab)
    assert workspace.built == [lab]
    scene = lab / BundleFile.SCENE
    stat = scene.stat()
    os.utime(scene, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    cache.of(lab)
    assert workspace.built == [lab, lab]


def test_without_cram_an_environment_offers_no_annotations(scenes):
    cache = EnvironmentAnnotationCache(
        WorkspaceLoader(modules=CramModules(finder=lambda name: None))
    )
    assert cache.of(scenes.directory_of("lab").path / "lab").annotations == []


def annotations_request(answerer, environment: str):
    """
    :return: The answer to asking for an environment's annotations.
    """
    return answerer.answer(
        Request(
            method=HttpMethod.GET,
            path=f"{ViewerRoute.PLUGIN_API}{PlanBuilderName.PLUGIN}/{PlanBuilderRoute.ENVIRONMENT_ANNOTATIONS}",
            query=urlencode({EnvironmentAnnotationsParameter.ENVIRONMENT: environment}),
            headers=HEADERS,
        )
    )
