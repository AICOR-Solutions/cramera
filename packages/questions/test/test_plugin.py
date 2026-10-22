"""
The questions plugin, through the viewer's routes.
"""

from __future__ import annotations

import json
import os
from http import HTTPStatus

import pytest

from cramera.application import ViewerApplication
from cramera.http.messages import Header, HttpMethod, Request
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.locations import DataLocations
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.live import Capability
from cramera_protocol.questions import (
    GraphView,
    GraphViewName,
    Members,
    PresetCatalog,
    QueryAnswer,
    QueryRequest,
    QueryScope,
    QuestionMatch,
    QuestionRequest,
    QuestionsParameter,
    QuestionsRoute,
    Vocabulary,
)
from cramera_protocol.viewer import ViewerRoute
from cramera_questions.plugin import SOURCE_VERSION, QuestionsPlugin
from cramera_protocol.plugins import PluginName
from cramera_questions.presets import QueryVariable, RobotQuestion
from cramera_questions.workspace_classes import WorkspaceClassIndex
from .dataset.files import SceneName

LOCAL_HOST = {Header.HOST: "127.0.0.1:8711"}
"""
The headers of a request addressed to this machine.
"""


@pytest.fixture
def plugin() -> QuestionsPlugin:
    """
    :return: The plugin without the workspace's classes.
    """
    return QuestionsPlugin(class_index=WorkspaceClassIndex())


@pytest.fixture
def answerer(catalog, tmp_path, plugin) -> RequestAnswerer:
    """
    :return: The viewer's request answerer with the plugin.
    """
    application = ViewerApplication(
        catalog=catalog,
        locations=DataLocations(data=tmp_path / "data", shared_scenes=None),
        plugins=[plugin],
    )
    return RequestAnswerer(router=application.router(), policy=OriginPolicy())


def route(plugin_route: QuestionsRoute) -> str:
    """
    :param plugin_route: One of the plugin's routes.
    :return: Its path on the viewer.
    """
    return f"{ViewerRoute.PLUGIN_API}{PluginName.QUESTIONS}/{plugin_route}"


def get(answerer, plugin_route: QuestionsRoute, **parameters):
    """
    :param answerer: The viewer's request answerer.
    :param plugin_route: One of the plugin's routes.
    :param parameters: The query parameters.
    :return: The response to a GET request.
    """
    query = "&".join(f"{key}={value}" for key, value in parameters.items())
    return answerer.answer(
        Request(
            method=HttpMethod.GET,
            path=route(plugin_route),
            query=query,
            headers=LOCAL_HOST,
        )
    )


def post(answerer, plugin_route: QuestionsRoute, document):
    """
    :param answerer: The viewer's request answerer.
    :param plugin_route: One of the plugin's routes.
    :param document: The request body.
    :return: The response to a POST request.
    """
    body = json.dumps(document.to_json()).encode("utf-8")
    return answerer.answer(
        Request(
            method=HttpMethod.POST,
            path=route(plugin_route),
            headers=LOCAL_HOST,
            body=body,
        )
    )


def read(response, document_class):
    """
    :param response: A successful response.
    :param document_class: The class of its body.
    :return: The body as a document.
    """
    assert response.status is HTTPStatus.OK
    return document_class.from_json(json.loads(response.body))


# %% plugin


def test_the_plugin_adds_questions(plugin):
    assert plugin.name() == PluginName.QUESTIONS
    assert plugin.capabilities() == [Capability.QUESTIONS]
    assert plugin.version() == SOURCE_VERSION


# %% routes


def test_presets_are_listed_per_scene(answerer):
    catalog = read(
        get(
            answerer,
            QuestionsRoute.PRESETS,
            **{QuestionsParameter.SCENE: SceneName.ANNOTATED},
        ),
        PresetCatalog,
    )
    assert catalog.title == SceneName.ANNOTATED
    assert catalog.presets[0].text == RobotQuestion.WHICH_ROBOT
    assert catalog.presets[0].verbalization is not None


def test_a_query_and_a_question_are_answered(answerer):
    answer = read(
        post(
            answerer,
            QuestionsRoute.QUERY,
            QueryRequest(
                code=f"an(entity({QueryVariable.ARM}))", scene=SceneName.ANNOTATED
            ),
        ),
        QueryAnswer,
    )
    assert answer.ok and answer.count == 1
    match = read(
        post(
            answerer,
            QuestionsRoute.QUESTION,
            QuestionRequest(text=RobotQuestion.WHICH_ROBOT, scene=SceneName.LEGACY),
        ),
        QuestionMatch,
    )
    assert match.matched


def test_vocabulary_and_members_are_offered(answerer):
    scene = {QuestionsParameter.SCENE: SceneName.ANNOTATED}
    vocabulary = read(get(answerer, QuestionsRoute.VOCABULARY, **scene), Vocabulary)
    assert vocabulary.entries[0].name == QueryVariable.ROBOT
    members = read(
        get(
            answerer,
            QuestionsRoute.MEMBERS,
            **scene,
            **{
                QuestionsParameter.NAME: QueryVariable.EVENT,
                QuestionsParameter.SCOPE: QueryScope.DETECTED_EVENTS,
            },
        ),
        Members,
    )
    assert "event_type" in [member.name for member in members.members]


def test_a_graph_view_is_built(answerer):
    view = read(
        get(
            answerer,
            QuestionsRoute.GRAPH,
            **{
                QuestionsParameter.SCENE: SceneName.ANNOTATED,
                QuestionsParameter.VIEW: GraphViewName.PLAN,
            },
        ),
        GraphView,
    )
    assert view.view is GraphViewName.PLAN


@pytest.mark.parametrize(
    "plugin_route, parameters, status",
    [
        (QuestionsRoute.PRESETS, {}, HTTPStatus.BAD_REQUEST),
        (
            QuestionsRoute.PRESETS,
            {QuestionsParameter.SCENE: "missing_scene"},
            HTTPStatus.NOT_FOUND,
        ),
        (
            QuestionsRoute.VOCABULARY,
            {
                QuestionsParameter.SCENE: SceneName.ANNOTATED,
                QuestionsParameter.SCOPE: "dreams",
            },
            HTTPStatus.NOT_FOUND,
        ),
        (
            QuestionsRoute.GRAPH,
            {
                QuestionsParameter.SCENE: SceneName.ANNOTATED,
                QuestionsParameter.VIEW: "weather",
            },
            HTTPStatus.NOT_FOUND,
        ),
    ],
)
def test_bad_requests_are_refused_with_their_status(
    answerer, plugin_route, parameters, status
):
    assert get(answerer, plugin_route, **parameters).status is status


def test_a_query_without_a_scene_is_refused(answerer):
    response = post(answerer, QuestionsRoute.QUERY, QueryRequest(code="1"))
    assert response.status is HTTPStatus.BAD_REQUEST


# %% cache


def test_a_scene_is_rebuilt_only_when_its_description_changes(plugin, answerer, scenes):
    [cache] = plugin.caches.values()
    first = cache.of_scene(SceneName.ANNOTATED)
    assert cache.of_scene(SceneName.ANNOTATED) is first
    path = scenes / SceneName.ANNOTATED / BundleFile.SCENE
    stamp = path.stat().st_mtime_ns
    os.utime(path, ns=(stamp + 1, stamp + 1))
    assert cache.of_scene(SceneName.ANNOTATED) is not first
