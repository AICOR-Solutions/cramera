"""
The workshop plugin: its routes over a stand-in world, its answers without the physics
libraries, and what it tells the viewer.
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
from cramera_protocol.plugins import PluginName
from cramera_protocol.viewer import ViewerRoute
from cramera_protocol.workshop import WorkshopRoute, WorkshopState
from cramera_workshop.exceptions import WorkshopPhysicsMissing
from cramera_workshop.plugin import (
    PhysicsLibraries,
    PhysicsLibrary,
    ShownWorkshopPhysics,
    WebFile,
    WorkshopPlugin,
    WorkshopRoutes,
)
from cramera_workshop.session import WorkshopSession

from .dataset.dynamics import RecordingDynamics
from cramera_workshop.plugin import NAVIGATION_TITLE
from cramera_protocol.viewer import NavigationGroup, ViewerRoute

HEADERS = {Header.HOST: "localhost"}
"""
The headers of a request addressed to this machine.
"""

PREFIX = f"{ViewerRoute.PLUGIN_API}{PluginName.WORKSHOP}/"
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


def found_everywhere(name: str) -> ModuleSpec:
    """
    :param name: A module name.
    :return: A specification with an origin, as for an installed module.
    """
    return ModuleSpec(name, None, origin=name)


@pytest.fixture
def dynamics() -> RecordingDynamics:
    """
    :return: A stand-in contact world.
    """
    return RecordingDynamics()


@pytest.fixture
def session(dynamics) -> Iterator[WorkshopSession]:
    """
    :return: A session over the stand-in world; closed afterwards.
    """
    session = WorkshopSession(factory=lambda: dynamics)
    yield session
    session.close()


@pytest.fixture
def answerer(session) -> RequestAnswerer:
    """
    :return: The workshop routes over the session, as the viewer serves them.
    """
    router = Router()
    routes = WorkshopRoutes(session, PhysicsLibraries(finder=found_everywhere))
    for declaration in routes.routes():
        router.add(declaration.route(PREFIX))
    return RequestAnswerer(router=router, policy=OriginPolicy())


def get_state(answerer: RequestAnswerer):
    return answerer.answer(
        Request(
            method=HttpMethod.GET,
            path=f"{PREFIX}{WorkshopRoute.STATE}",
            headers=HEADERS,
        )
    )


def post_command(answerer: RequestAnswerer, dataset, file_name: str):
    return answerer.answer(
        Request(
            method=HttpMethod.POST,
            path=f"{PREFIX}{WorkshopRoute.COMMAND}",
            headers=HEADERS,
            body=(dataset / "commands" / file_name).read_bytes(),
        )
    )


def state_of(response) -> WorkshopState:
    return WorkshopState.from_json(json.loads(response.body))


# %% routes


def test_the_state_route_answers_the_measured_state(answerer):
    response = get_state(answerer)
    assert response.status is HTTPStatus.OK
    assert state_of(response) == WorkshopState()


def test_commands_answer_the_state_after_them(answerer, dataset, dynamics):
    assert state_of(post_command(answerer, dataset, "start.json")).running
    held = state_of(post_command(answerer, dataset, "grab.json")).held
    assert held == dynamics.held_body


def test_a_command_the_world_refuses_is_a_bad_request(answerer, dataset):
    post_command(answerer, dataset, "start.json")
    response = post_command(answerer, dataset, "grab_environment.json")
    assert response.status is HTTPStatus.BAD_REQUEST


def test_a_command_before_the_start_is_a_conflict(answerer, dataset):
    assert post_command(answerer, dataset, "grab.json").status is HTTPStatus.CONFLICT


def test_a_body_that_is_no_json_is_a_bad_request(answerer, dataset):
    response = post_command(answerer, dataset, "truncated.json")
    assert response.status is HTTPStatus.BAD_REQUEST


# %% without the physics libraries


@pytest.fixture
def unequipped_answerer(tmp_path) -> Iterator[RequestAnswerer]:
    """
    :return: The viewer with the workshop plugin in an environment without MuJoCo.
    """
    plugin = WorkshopPlugin(libraries=PhysicsLibraries(finder=nothing_found))
    application = ViewerApplication(
        catalog=SceneCatalog([]),
        locations=DataLocations(data=tmp_path, shared_scenes=None),
        plugins=[plugin],
    )
    yield RequestAnswerer(router=application.router(), policy=OriginPolicy())
    application.close()


def test_without_mujoco_the_state_names_the_missing_libraries(unequipped_answerer):
    state = state_of(get_state(unequipped_answerer))
    missing = [library.value for library in PhysicsLibrary]
    assert not state.available
    assert state.error == WorkshopPhysicsMissing(missing).message()


def test_without_mujoco_starting_is_unavailable(unequipped_answerer, dataset):
    response = post_command(unequipped_answerer, dataset, "start.json")
    assert response.status is HTTPStatus.SERVICE_UNAVAILABLE


def test_building_the_world_without_mujoco_names_the_missing_libraries():
    builder = ShownWorkshopPhysics(
        SceneCatalog([]), PhysicsLibraries(finder=nothing_found)
    )
    with pytest.raises(WorkshopPhysicsMissing) as refused:
        builder.build()
    assert refused.value.modules == [library.value for library in PhysicsLibrary]


# %% plugin


def test_the_plugin_names_its_module_and_browser_files():
    plugin = WorkshopPlugin()
    assert plugin.name() == PluginName.WORKSHOP
    assert (plugin.web_directory() / plugin.module()).is_file()
    assert plugin.module() == WebFile.MODULE
    assert plugin.version()


def test_closing_the_plugin_closes_its_sessions(tmp_path, dataset):
    plugin = WorkshopPlugin(libraries=PhysicsLibraries(finder=nothing_found))
    application = ViewerApplication(
        catalog=SceneCatalog([]),
        locations=DataLocations(data=tmp_path, shared_scenes=None),
        plugins=[plugin],
    )
    application.router()
    application.close()
    assert [session.closed for session in plugin.sessions] == [True]


def test_the_plugin_has_an_entry_in_the_viewers_navigation():
    navigation = WorkshopPlugin().info().navigation
    assert navigation.title == NAVIGATION_TITLE
    assert navigation.group == NavigationGroup.LABORATORY
    assert navigation.page is None
