"""
The models plugin's routes, what it tells the viewer, and a viewer without the circuit
libraries.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from importlib.metadata import entry_points

import pytest

from cramera.application import ViewerApplication
from cramera.http.messages import HttpMethod, Request
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.locations import DataLocations
from cramera.plugins import PluginLoader
from cramera.scenes import SceneCatalog
from cramera_models.exceptions import CircuitLibrariesMissing
from cramera_models.libraries import CircuitLibraries, CircuitLibrary
from cramera_models.plugin import ModelsPlugin, WebFile
from cramera_models.workbench import UnavailableWorkbench, WorkbenchChoice
from cramera_protocol.models import (
    ModelsRoute,
    ModeRequest,
    PosteriorRequest,
    ProbabilityRequest,
    WorkbenchState,
)
from cramera_protocol.plugins import PluginName
from cramera_protocol.viewer import ErrorKey, PluginGroup, ViewerInfo, ViewerRoute

from .dataset.recording_workbench import RecordingWorkbench
from .dataset.requests import LOCAL_HOST, answer_json, local_get, local_post
from cramera_models.plugin import NAVIGATION_TITLE
from cramera_protocol.viewer import NavigationGroup, ViewerRoute

# %% plugin


def test_the_plugin_is_installed_under_its_protocol_name():
    installed = [
        entry_point
        for entry_point in entry_points(group=PluginGroup.VIEWER)
        if entry_point.name == PluginName.MODELS
    ]
    plugins = PluginLoader(entry_points=installed).load()
    assert [plugin.name() for plugin in plugins] == [PluginName.MODELS]


def test_the_plugin_names_its_browser_module():
    info = ModelsPlugin().info()
    assert (
        info.module == f"{ViewerRoute.PLUGIN_FILES}{PluginName.MODELS}/{WebFile.MODULE}"
    )
    assert (ModelsPlugin().web_directory() / WebFile.MODULE).is_file()


# %% routes


def test_the_state_is_answered(answerer_of):
    workbench = RecordingWorkbench()
    response = answerer_of(workbench).answer(local_get(ModelsRoute.STATE))
    assert response.status == HTTPStatus.OK
    assert WorkbenchState.from_json(answer_json(response)) == workbench.loaded_state


def test_a_model_file_is_handed_to_the_workbench(answerer_of, upload_of):
    workbench = RecordingWorkbench()
    upload = upload_of("mimic_circuit.json")
    body = json.dumps(upload.to_json()).encode()
    response = answerer_of(workbench).answer(local_post(ModelsRoute.LOAD, body))
    assert WorkbenchState.from_json(answer_json(response)) == workbench.loaded_state
    assert workbench.received == [upload]


@pytest.mark.parametrize(
    "route, question_file, request_class, answer_of_workbench",
    [
        (
            ModelsRoute.PROBABILITY,
            "probability_of_low_x_given_red.json",
            ProbabilityRequest,
            lambda workbench: workbench.probability_answer,
        ),
        (
            ModelsRoute.POSTERIOR,
            "posterior_of_x_and_color.json",
            PosteriorRequest,
            lambda workbench: workbench.posterior_answer,
        ),
        (
            ModelsRoute.MODE,
            "mode_given_blue.json",
            ModeRequest,
            lambda workbench: workbench.mode_answer,
        ),
    ],
)
def test_a_question_is_read_into_its_document_and_answered(
    answerer_of, question, route, question_file, request_class, answer_of_workbench
):
    workbench = RecordingWorkbench()
    body = question(question_file)
    response = answerer_of(workbench).answer(local_post(route, body))
    assert response.status == HTTPStatus.OK
    assert answer_json(response) == answer_of_workbench(workbench).to_json()
    assert workbench.received == [request_class.from_json(json.loads(body))]


def test_a_body_that_is_not_json_is_a_bad_request(answerer_of, question):
    workbench = RecordingWorkbench()
    response = answerer_of(workbench).answer(
        local_post(ModelsRoute.PROBABILITY, question("not_json.txt"))
    )
    assert response.status == HTTPStatus.BAD_REQUEST
    assert workbench.received == []


def test_a_question_of_the_wrong_shape_is_a_bad_request(answerer_of, question):
    workbench = RecordingWorkbench()
    response = answerer_of(workbench).answer(
        local_post(ModelsRoute.POSTERIOR, question("mode_without_evidence.json"))
    )
    assert response.status == HTTPStatus.BAD_REQUEST
    assert workbench.received == []


# %% without the libraries


@pytest.fixture
def unavailable() -> UnavailableWorkbench:
    """
    :return: The workbench of an environment without plotly.
    """
    return UnavailableWorkbench([CircuitLibrary.PLOTLY])


@pytest.mark.parametrize(
    "request_of",
    [
        lambda question: local_get(ModelsRoute.STATE),
        lambda question: local_post(
            ModelsRoute.PROBABILITY, question("probability_of_any_x.json")
        ),
    ],
)
def test_without_the_libraries_the_routes_answer_which_are_missing(
    answerer_of, unavailable, question, request_of
):
    response = answerer_of(unavailable).answer(request_of(question))
    assert response.status == CircuitLibrariesMissing(unavailable.missing).status()
    assert (
        answer_json(response)[ErrorKey.ERROR]
        == CircuitLibrariesMissing(unavailable.missing).message()
    )


def test_without_the_libraries_the_viewer_keeps_serving(answerer_of, unavailable):
    response = answerer_of(unavailable).answer(
        Request(method=HttpMethod.GET, path=ViewerRoute.INFO, headers=LOCAL_HOST)
    )
    assert response.status == HTTPStatus.OK
    info = ViewerInfo.from_json(answer_json(response))
    assert [plugin.name for plugin in info.plugins] == [PluginName.MODELS]


def test_the_plugin_chooses_its_workbench_from_the_installed_libraries(tmp_path):
    nothing_installed = CircuitLibraries(finder=lambda name: None)
    application = ViewerApplication(
        catalog=SceneCatalog([]),
        locations=DataLocations(data=tmp_path, shared_scenes=None),
        plugins=[ModelsPlugin(choice=WorkbenchChoice(nothing_installed))],
    )
    answerer = RequestAnswerer(router=application.router(), policy=OriginPolicy())
    response = answerer.answer(local_get(ModelsRoute.STATE))
    expected = CircuitLibrariesMissing(nothing_installed.missing())
    assert response.status == expected.status()
    assert answer_json(response)[ErrorKey.ERROR] == expected.message()


def test_the_plugin_has_an_entry_in_the_viewers_navigation():
    navigation = ModelsPlugin().info().navigation
    assert navigation.title == NAVIGATION_TITLE
    assert navigation.group == NavigationGroup.ANALYSIS
    assert navigation.page is None
