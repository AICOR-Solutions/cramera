"""
Shared fixtures of the laboratory's tests.

The tests of the simulation need MuJoCo and those of the CRAM world the CRAM workspace;
where either is missing they are left out, and everything else still runs.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from typing_extensions import Any, Callable

from cramera.application import ViewerApplication
from cramera.http.messages import Header, HttpMethod, Request, Response
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.locations import DataLocations
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_laboratory.plugin import LaboratoryPlugin
from cramera_laboratory.resources import (
    LaboratoryBundle,
    LaboratoryResource,
    LaboratoryShelf,
)
from cramera_protocol.laboratory.physics import LaboratoryName
from cramera_protocol.viewer import ViewerRoute

from .dataset.simulations import RecordingFactory

DATASET = Path(__file__).parent / "dataset"
"""
The directory holding the test documents.
"""

HEADERS = {Header.HOST: "localhost"}
"""
The headers of a request addressed to this machine.
"""

CRAM_PACKAGES = ("semantic_digital_twin", "coraplex", "giskardpy", "cramera_cram")
"""
The packages the CRAM world and the task demo need.
"""

TESTS_NEEDING_MUJOCO = ["test_physics*.py"]
"""
The test modules that simulate, which import MuJoCo.
"""

TESTS_NEEDING_CRAM = ["cram/*"]
"""
The tests that build CRAM worlds, which import the CRAM workspace.
"""

collect_ignore_glob = (
    TESTS_NEEDING_MUJOCO if importlib.util.find_spec("mujoco") is None else []
) + (
    TESTS_NEEDING_CRAM
    if any(importlib.util.find_spec(package) is None for package in CRAM_PACKAGES)
    else []
)
"""
The tests left out where MuJoCo or the CRAM workspace is missing; the rest still run.
"""

# %% laboratories


@pytest.fixture(scope="session")
def shelf() -> LaboratoryShelf:
    """
    :return: The shipped laboratories.
    """
    return LaboratoryShelf()


@pytest.fixture(scope="session")
def bench_laboratory(shelf) -> LaboratoryBundle:
    """
    :return: The shipped bench laboratory.
    """
    return shelf.laboratory(LaboratoryResource.BENCH)


@pytest.fixture
def locations(tmp_path: Path) -> DataLocations:
    """
    :return: Data locations below the test's directory.
    """
    return DataLocations(data=tmp_path / "data", shared_scenes=None)


@pytest.fixture
def read_json() -> Callable[[str], Any]:
    """
    :return: Reads a JSON file of the test dataset.
    """

    def read(relative: str) -> Any:
        return json.loads((DATASET / relative).read_text(encoding="utf-8"))

    return read


# %% viewer


@pytest.fixture
def factory() -> RecordingFactory:
    """
    :return: A factory of simulation stand-ins.
    """
    return RecordingFactory()


@pytest.fixture
def answerer(locations, factory) -> RequestAnswerer:
    """
    :return: The viewer's request answerer with the laboratory plugged in.
    """
    application = ViewerApplication(
        catalog=SceneCatalog(
            [SceneDirectory(locations.local_scenes, SceneSource.LOCAL)]
        ),
        locations=locations,
        plugins=[LaboratoryPlugin(factory=factory)],
    )
    return RequestAnswerer(router=application.router(), policy=OriginPolicy())


def send(
    answerer: RequestAnswerer, method: HttpMethod, route: str, body: bytes = b""
) -> Response:
    """
    :param answerer: The viewer's request answerer.
    :param method: The request's method.
    :param route: A route below the laboratory's prefix.
    :param body: The request's body.
    :return: The answer.
    """
    return answerer.answer(
        Request(
            method=method,
            path=f"{ViewerRoute.PLUGIN_API}{LaboratoryName.PLUGIN}/{route}",
            headers=HEADERS,
            body=body,
        )
    )


@pytest.fixture
def get(answerer) -> Callable[[str], Response]:
    """
    :return: Sends a GET request to a route below the laboratory's prefix.
    """
    return lambda route: send(answerer, HttpMethod.GET, route)


@pytest.fixture
def post(answerer) -> Callable[[str, Any], Response]:
    """
    :return: Sends a POST request with a JSON body to a route below the laboratory's
        prefix.
    """
    return lambda route, body: send(
        answerer, HttpMethod.POST, route, json.dumps(body).encode("utf-8")
    )
