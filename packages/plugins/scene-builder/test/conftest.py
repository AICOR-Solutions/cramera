"""
Shared fixtures of the scene builder's tests: a copy of the test library and scenes, and
the viewer serving them with the scene builder plugged in.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typing_extensions import Any, Callable

from cramera.application import ViewerApplication
from cramera.http.messages import Header, HttpMethod, Request, Response
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.locations import DataLocations
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_protocol.scene_builder import (
    ReservedResourceRoot,
    SceneBuilderLimits,
    SceneBuilderName,
    SceneBuilderVariable,
)
from cramera_protocol.viewer import ViewerRoute
from cramera_scene_builder.plugin import (
    LibraryRoots,
    SceneBuilderPlugin,
    SceneBuilderStorage,
)
from cramera_scene_builder.resources import ResourceLibrary

DATASET = Path(__file__).parent / "dataset"
"""
The directory holding the test library, scenes, drafts and point clouds.
"""

LIBRARY_ROOT = "library"
"""
The name of the test library's root, after its directory.
"""

HEADERS = {Header.HOST: "localhost"}
"""
The headers of a request addressed to this machine.
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """
    :return: A copy of the test library and scenes that tests may change.
    """
    for name in (LIBRARY_ROOT, "scenes"):
        shutil.copytree(DATASET / name, tmp_path / name)
    return tmp_path


@pytest.fixture
def catalog(workspace: Path) -> SceneCatalog:
    """
    :return: The test scenes as the viewer's demo scenes.
    """
    return SceneCatalog([SceneDirectory(workspace / "scenes", SceneSource.DEMO)])


@pytest.fixture
def locations(workspace: Path) -> DataLocations:
    """
    :return: Locations whose data directory lies in the workspace.
    """
    return DataLocations(data=workspace / "data", shared_scenes=None)


@pytest.fixture
def environment(workspace: Path) -> dict:
    """
    :return: An environment adding the test library.
    """
    return {SceneBuilderVariable.LIBRARY: str(workspace / LIBRARY_ROOT)}


@pytest.fixture
def storage(locations: DataLocations) -> SceneBuilderStorage:
    """
    :return: The scene builder's storage in the workspace.
    """
    return SceneBuilderStorage.of(locations)


@pytest.fixture
def library(catalog, storage, environment) -> ResourceLibrary:
    """
    :return: The library of the uploaded point clouds, the test scenes and the test
        library.
    """
    return LibraryRoots.of(catalog, storage, environment).library()


@pytest.fixture
def limits() -> SceneBuilderLimits:
    """
    :return: The default limits.
    """
    return SceneBuilderLimits()


@pytest.fixture
def plugin(environment, limits) -> SceneBuilderPlugin:
    """
    :return: The scene builder, reading the test environment.
    """
    return SceneBuilderPlugin(environment=environment, limits=limits)


@pytest.fixture
def serve(catalog, locations) -> Callable[[SceneBuilderPlugin], RequestAnswerer]:
    """
    :return: Builds the viewer's request answerer with a scene builder plugged in.
    """

    def build(plugin: SceneBuilderPlugin) -> RequestAnswerer:
        application = ViewerApplication(
            catalog=catalog, locations=locations, plugins=[plugin]
        )
        return RequestAnswerer(router=application.router(), policy=OriginPolicy())

    return build


@pytest.fixture
def answerer(serve, plugin) -> RequestAnswerer:
    """
    :return: The viewer's request answerer with the scene builder plugged in.
    """
    return serve(plugin)


def send(
    answerer: RequestAnswerer,
    method: HttpMethod,
    route: str,
    query: str = "",
    body: bytes = b"",
) -> Response:
    """
    :param answerer: The viewer's request answerer.
    :param method: The request's method.
    :param route: A route below the scene builder's prefix.
    :param query: The request's query.
    :param body: The request's body.
    :return: The answer.
    """
    return answerer.answer(
        Request(
            method=method,
            path=f"{ViewerRoute.PLUGIN_API}{SceneBuilderName.PLUGIN}/{route}",
            query=query,
            headers=HEADERS,
            body=body,
        )
    )


@pytest.fixture
def get(answerer) -> Callable[..., Response]:
    """
    :return: Sends a GET request for a route below the scene builder's prefix.
    """
    return lambda route, query="": send(answerer, HttpMethod.GET, route, query)


@pytest.fixture
def post(answerer) -> Callable[[str, bytes], Response]:
    """
    :return: Sends a POST request to a route below the scene builder's prefix.
    """
    return lambda route, body: send(answerer, HttpMethod.POST, route, body=body)


@pytest.fixture
def read_json() -> Callable[[str], Any]:
    """
    :return: Reads a JSON file of the test dataset.
    """

    def read(relative: str) -> Any:
        return json.loads((DATASET / relative).read_text(encoding="utf-8"))

    return read


def point_cloud_identifier(name: str) -> str:
    """
    :param name: The file name of an uploaded point cloud.
    :return: Its resource identifier.
    """
    return f"{ReservedResourceRoot.POINT_CLOUDS}/{name}"
