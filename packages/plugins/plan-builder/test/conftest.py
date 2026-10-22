"""
Shared fixtures of the plan builder's tests: the test scenes and plans, a workspace that
stands in for CRAM, and the viewer serving them with the plan builder plugged in.
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
from cramera_plan_builder.plugin import PlanBuilderPlugin
from cramera_plan_builder.workspace import CramModules, CramWorkspace, WorkspaceLoader
from cramera_protocol.plan_builder import (
    PlanBuilderLimits,
    PlanBuilderName,
    PlanBuilderVariable,
    PlanDocument,
)
from cramera_protocol.viewer import ViewerRoute

from .dataset.given_workspace import DATASET, GivenWorkspace

HEADERS = {Header.HOST: "localhost"}
"""
The headers of a request addressed to this machine.
"""

DEMO_PORT = "18765"
"""
The port the test environment lets demos publish on.
"""


@pytest.fixture
def read_json() -> Callable[[str], Any]:
    """
    :return: Reads a JSON file of the test dataset.
    """
    return lambda relative: json.loads((DATASET / relative).read_text("utf-8"))


@pytest.fixture
def read_plan(read_json) -> Callable[[str], PlanDocument]:
    """
    :return: Reads a plan of the test dataset by its file name.
    """
    return lambda name: PlanDocument.from_json(read_json(f"plans/{name}"))


@pytest.fixture
def plan(read_plan) -> PlanDocument:
    """
    :return: The complete test plan.
    """
    return read_plan("milk_to_table.json")


@pytest.fixture
def scenes(tmp_path: Path) -> SceneCatalog:
    """
    :return: A copy of the test scenes as the viewer's demo scenes.
    """
    shutil.copytree(DATASET / "scenes", tmp_path / "scenes")
    return SceneCatalog([SceneDirectory(tmp_path / "scenes", SceneSource.DEMO)])


@pytest.fixture
def locations(tmp_path: Path) -> DataLocations:
    """
    :return: Locations whose data directory lies in the test's directory.
    """
    return DataLocations(data=tmp_path / "data", shared_scenes=None)


@pytest.fixture
def output(tmp_path: Path) -> Path:
    """
    :return: The directory the environment names for generated demos.
    """
    return tmp_path / "demos"


@pytest.fixture
def given_workspace() -> CramWorkspace:
    """
    :return: The workspace the test catalog file describes.
    """
    return GivenWorkspace()


@pytest.fixture
def workspace_loader(given_workspace) -> WorkspaceLoader:
    """
    :return: A loader that has read the test workspace already.
    """
    loader = WorkspaceLoader()
    loader.loaded = given_workspace
    return loader


@pytest.fixture
def plugin(output, workspace_loader) -> PlanBuilderPlugin:
    """
    :return: The plan builder with the test workspace, writing demos into the test's
        directory.
    """
    return PlanBuilderPlugin(
        environment={
            PlanBuilderVariable.OUTPUT: str(output),
            PlanBuilderVariable.PORT: DEMO_PORT,
        },
        limits=PlanBuilderLimits(),
        workspace=workspace_loader,
    )


@pytest.fixture
def serve(scenes, locations) -> Callable[[PlanBuilderPlugin], RequestAnswerer]:
    """
    :return: Builds the viewer's request answerer with a plan builder plugged in.
    """

    def build(plugin: PlanBuilderPlugin) -> RequestAnswerer:
        application = ViewerApplication(
            catalog=scenes, locations=locations, plugins=[plugin]
        )
        return RequestAnswerer(router=application.router(), policy=OriginPolicy())

    return build


@pytest.fixture
def answerer(serve, plugin) -> RequestAnswerer:
    """
    :return: The viewer's request answerer with the plan builder plugged in.
    """
    return serve(plugin)


def send(
    answerer: RequestAnswerer, method: HttpMethod, route: str, body: bytes = b""
) -> Response:
    """
    :param answerer: The viewer's request answerer.
    :param method: The request's method.
    :param route: A route below the plan builder's prefix.
    :param body: The request's body.
    :return: The answer.
    """
    return answerer.answer(
        Request(
            method=method,
            path=f"{ViewerRoute.PLUGIN_API}{PlanBuilderName.PLUGIN}/{route}",
            headers=HEADERS,
            body=body,
        )
    )


@pytest.fixture
def get(answerer) -> Callable[[str], Response]:
    """
    :return: Sends a GET request for a route below the plan builder's prefix.
    """
    return lambda route: send(answerer, HttpMethod.GET, route)


@pytest.fixture
def post(answerer) -> Callable[[str, Any], Response]:
    """
    :return: Sends a JSON body to a route below the plan builder's prefix.
    """
    return lambda route, body: send(
        answerer, HttpMethod.POST, route, json.dumps(body).encode("utf-8")
    )


# %% CRAM

if CramModules().missing():
    collect_ignore = ["cram"]
