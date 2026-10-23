"""
The cable lab plugin: its routes over stand-in simulations, its answers without the
simulation libraries, and what it tells the viewer.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from importlib.machinery import ModuleSpec

import pytest
from typing_extensions import Iterator

from cramera.application import ViewerApplication
from cramera.http.messages import Header, HttpMethod, Request
from cramera.http.origin import OriginPolicy
from cramera.http.routing import Router
from cramera.http.server import RequestAnswerer
from cramera.locations import DataLocations
from cramera.scenes import SceneCatalog
from cramera_cable_lab.exceptions import CableLabLibrariesMissing
from cramera_cable_lab.plugin import (
    CableLabPlugin,
    CableLabRoutes,
    CablePhysicsFactory,
    SimulationLibraries,
    SimulationLibrary,
    WebFile,
)
from cramera_cable_lab.session import CableLabSession
from cramera_protocol.cable_lab import (
    CableConfiguration,
    CableLabRoute,
    CableLabState,
    SimulationLifecycle,
)
from cramera_protocol.plugins import PluginName
from cramera_protocol.viewer import ErrorKey, ViewerRoute

from .dataset.simulations import RecordingFactory
from cramera_cable_lab.plugin import NAVIGATION_TITLE
from cramera_protocol.viewer import NavigationGroup, ViewerRoute
from cramera_protocol.cable_lab import CableLabFile

HEADERS = {Header.HOST: "localhost"}
"""
The headers of a request addressed to this machine.
"""

PREFIX = f"{ViewerRoute.PLUGIN_API}{PluginName.CABLE_LAB}/"
"""
Where the plugin's routes are served.
"""

# %% fixtures


def nothing_found(name: str) -> None:
    """
    :param name: A module name.
    :return: Nothing, as for a module that is not installed.
    """
    return None


def found_without_origin(name: str) -> ModuleSpec:
    """
    :param name: A module name.
    :return: A specification without code, as for a directory that only shares the
        module's name.
    """
    return ModuleSpec(name, None)


@pytest.fixture
def factory() -> RecordingFactory:
    """
    :return: A factory of stand-in simulations.
    """
    return RecordingFactory()


@pytest.fixture
def answerer(factory) -> Iterator[RequestAnswerer]:
    """
    :return: The cable lab routes over stand-in simulations, as the viewer serves them.
    """
    session = CableLabSession(factory=factory.build)
    router = Router()
    for declaration in CableLabRoutes(session).routes():
        router.add(declaration.route(PREFIX))
    yield RequestAnswerer(router=router, policy=OriginPolicy())
    session.close()


def send(answerer: RequestAnswerer, method: HttpMethod, route: str, body: bytes = b""):
    return answerer.answer(
        Request(method=method, path=f"{PREFIX}{route}", headers=HEADERS, body=body)
    )


def post(answerer: RequestAnswerer, dataset, route: str, file_name: str):
    body = (dataset / "commands" / file_name).read_bytes()
    return send(answerer, HttpMethod.POST, route, body)


def state_of(response) -> CableLabState:
    return CableLabState.from_json(json.loads(response.body))


# %% routes


def test_the_state_of_a_new_lab_is_idle(answerer):
    response = send(answerer, HttpMethod.GET, CableLabRoute.STATE)
    assert response.status is HTTPStatus.OK
    assert state_of(response).lifecycle is SimulationLifecycle.IDLE


def test_start_command_reset_and_stop(answerer, dataset, factory):
    started = state_of(post(answerer, dataset, CableLabRoute.START, "loose_cable.json"))
    expected = json.loads((dataset / "commands" / "loose_cable.json").read_text())
    assert started.configuration == CableConfiguration.from_json(expected)
    assert started.lifecycle is SimulationLifecycle.RUNNING
    post(answerer, dataset, CableLabRoute.COMMAND, "pinch.json")
    post(answerer, dataset, CableLabRoute.COMMAND, "move.json")
    assert len(factory.built[0].commands) == 2
    reset = state_of(post(answerer, dataset, CableLabRoute.RESET, "empty.json"))
    assert reset.lifecycle is SimulationLifecycle.RUNNING
    stopped = state_of(post(answerer, dataset, CableLabRoute.STOP, "empty.json"))
    assert stopped.lifecycle is SimulationLifecycle.IDLE
    assert [simulation.stopped for simulation in factory.built] == [True, True]


def test_a_command_before_a_cable_is_a_conflict(answerer, dataset):
    response = post(answerer, dataset, CableLabRoute.COMMAND, "pinch.json")
    assert response.status is HTTPStatus.CONFLICT


def test_a_target_outside_the_workspace_is_a_bad_request(answerer, dataset):
    post(answerer, dataset, CableLabRoute.START, "empty.json")
    response = post(answerer, dataset, CableLabRoute.COMMAND, "move_too_high.json")
    assert response.status is HTTPStatus.BAD_REQUEST


@pytest.mark.parametrize("file_name", ["one_element.json", "truncated.json"])
def test_a_cable_the_lab_cannot_build_is_a_bad_request(answerer, dataset, file_name):
    response = post(answerer, dataset, CableLabRoute.START, file_name)
    assert response.status is HTTPStatus.BAD_REQUEST


# %% without the simulation libraries


def test_without_the_libraries_starting_names_them(tmp_path, dataset):
    plugin = CableLabPlugin(libraries=SimulationLibraries(finder=nothing_found))
    application = ViewerApplication(
        catalog=SceneCatalog([]),
        locations=DataLocations(data=tmp_path, shared_scenes=None),
        plugins=[plugin],
    )
    answerer = RequestAnswerer(router=application.router(), policy=OriginPolicy())
    response = post(answerer, dataset, CableLabRoute.START, "empty.json")
    missing = [library.value for library in SimulationLibrary]
    assert response.status is HTTPStatus.SERVICE_UNAVAILABLE
    assert (
        json.loads(response.body)[ErrorKey.ERROR]
        == CableLabLibrariesMissing(missing).message()
    )
    application.close()
    assert [session.simulation for session in plugin.sessions] == [None]


def test_a_name_without_code_does_not_count_as_installed():
    libraries = SimulationLibraries(finder=found_without_origin)
    assert libraries.missing() == [library.value for library in SimulationLibrary]
    with pytest.raises(CableLabLibrariesMissing):
        CablePhysicsFactory(libraries).build(CableConfiguration())


# %% plugin


def test_the_plugin_names_its_module():
    plugin = CableLabPlugin()
    assert plugin.name() == PluginName.CABLE_LAB
    assert plugin.module() == WebFile.MODULE
    assert plugin.version()


def test_the_plugin_has_an_entry_in_the_viewers_navigation():
    navigation = CableLabPlugin().info().navigation
    assert navigation.title == NAVIGATION_TITLE
    assert navigation.group == NavigationGroup.LABORATORY
    assert (
        navigation.page
        == f"{ViewerRoute.PLUGIN_FILES}{CableLabPlugin().name()}/{CableLabFile.PAGE}"
    )
