"""
The questions plugin's routes over recorded scenes; they evaluate queries with krrood,
so this module is only imported where krrood is installed.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from typing_extensions import Dict, List, Optional, Tuple

from cramera.http.messages import HttpMethod, Request, Response
from cramera.plugins import PluginRoute
from cramera.scenes import SceneCatalog
from cramera_protocol.questions import (
    QueryRequest,
    QueryScope,
    QuestionRequest,
    QuestionsParameter,
    QuestionsRoute,
)
from cramera_questions.desk import QuestionDesk
from cramera_questions.exceptions import MissingParameter, UnknownScope
from cramera_questions.graph.views import GraphViews
from cramera_questions.recorded.bundle import BundleReader, RecordedBundle
from cramera_questions.recorded.knowledge_base import RecordedKnowledge
from cramera_questions.workspace_classes import WorkspaceClassIndex

# %% scenes


@dataclass(frozen=True)
class SceneQuestions:
    """
    What one recorded scene answers with, built from the scene's files as they were.
    """

    stamp: int
    """
    When the scene description last changed when this was built.
    """

    knowledge: RecordedKnowledge
    """
    The scene's entities.
    """

    desk: QuestionDesk
    """
    The desk answering questions about the scene.
    """


@dataclass
class SceneQuestionCache:
    """
    The questions of each scene, rebuilt when its scene description changes.
    """

    catalog: SceneCatalog
    """
    The scenes the viewer shows.
    """

    class_index: WorkspaceClassIndex
    """
    The workspace classes a query may name.
    """

    built: Dict[str, SceneQuestions] = field(default_factory=dict)
    """
    The questions of each scene asked about so far.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    """
    Makes checking, building and storing one step for concurrent requests.
    """

    def of_scene(self, name: str) -> SceneQuestions:
        """
        :param name: A bundle name.
        :return: The scene's questions, rebuilt when its description changed.
        """
        stamp = BundleReader(self.catalog, name).stamp()
        with self.lock:
            cached = self.built.get(name)
            if cached is not None and cached.stamp == stamp:
                return cached
            knowledge = RecordedKnowledge.of_bundle(
                RecordedBundle.of_catalog(self.catalog, name)
            )
            built = SceneQuestions(
                stamp=stamp, knowledge=knowledge, desk=knowledge.desk(self.class_index)
            )
            self.built[name] = built
            return built


# %% routes


@dataclass(frozen=True)
class QuestionRoutes:
    """
    The plugin's routes over one catalog's scenes.
    """

    @classmethod
    def of_catalog(
        cls, catalog: SceneCatalog, class_index: WorkspaceClassIndex
    ) -> QuestionRoutes:
        """
        :param catalog: The scenes the viewer shows.
        :param class_index: The workspace classes a query may name.
        :return: The routes over the catalog's scenes.
        """
        return cls(SceneQuestionCache(catalog, class_index), GraphViews())

    cache: SceneQuestionCache
    """
    The questions of each scene.
    """

    graph_views: GraphViews
    """
    Builds the graph views.
    """

    def routes(self) -> List[PluginRoute]:
        """
        :return: One route per :class:`QuestionsRoute`.
        """
        return [
            PluginRoute(HttpMethod.GET, QuestionsRoute.PRESETS, self.answer_presets),
            PluginRoute(
                HttpMethod.GET, QuestionsRoute.VOCABULARY, self.answer_vocabulary
            ),
            PluginRoute(HttpMethod.GET, QuestionsRoute.MEMBERS, self.answer_members),
            PluginRoute(HttpMethod.GET, QuestionsRoute.GRAPH, self.answer_graph),
            PluginRoute(HttpMethod.POST, QuestionsRoute.QUERY, self.answer_query),
            PluginRoute(HttpMethod.POST, QuestionsRoute.QUESTION, self.answer_question),
        ]

    # %% answers

    def answer_presets(self, request: Request) -> Response:
        """
        :param request: Names the scene.
        :return: Its ready-made questions.
        """
        return Response.of_json(self.scene_of(request).desk.preset_catalog())

    def answer_vocabulary(self, request: Request) -> Response:
        """
        :param request: Names the scene and, optionally, the scope.
        :return: The names a query may use.
        """
        desk = self.scene_of(request).desk
        return Response.of_json(desk.vocabulary(self.scope_of(request)))

    def answer_members(self, request: Request) -> Response:
        """
        :param request: Names the scene, the name and, optionally, the scope.
        :return: The members that may follow the name's dot.
        """
        desk = self.scene_of(request).desk
        name = self.required(request, QuestionsParameter.NAME)
        return Response.of_json(desk.members(self.scope_of(request), name))

    def answer_graph(self, request: Request) -> Response:
        """
        :param request: Names the scene and the view.
        :return: The graph view.
        """
        knowledge = self.scene_of(request).knowledge
        view = self.required(request, QuestionsParameter.VIEW)
        return Response.of_json(self.graph_views.build(view, knowledge))

    def answer_query(self, request: Request) -> Response:
        """
        :param request: A :class:`QueryRequest` naming its scene.
        :return: The answer.
        """
        query = QueryRequest.from_json(request.json())
        desk = self.cache.of_scene(self.scene_name(query.scene)).desk
        return Response.of_json(desk.answer_query(query))

    def answer_question(self, request: Request) -> Response:
        """
        :param request: A :class:`QuestionRequest` naming its scene.
        :return: The ready-made question it asks, or the reply that none does.
        """
        question = QuestionRequest.from_json(request.json())
        desk = self.cache.of_scene(self.scene_name(question.scene)).desk
        return Response.of_json(desk.answer_question(question))

    # %% parameters

    def scene_of(self, request: Request) -> SceneQuestions:
        """
        :param request: A request naming its scene in the query.
        :return: The scene's questions.
        """
        return self.cache.of_scene(self.required(request, QuestionsParameter.SCENE))

    @staticmethod
    def scene_name(scene: Optional[str]) -> str:
        """
        :param scene: The scene a request body names.
        :return: The scene.
        :raises MissingParameter: When the body names none.
        """
        if scene is None:
            raise MissingParameter(QuestionsParameter.SCENE.value)
        return scene

    @staticmethod
    def required(request: Request, parameter: QuestionsParameter) -> str:
        """
        :param request: A request.
        :param parameter: A query parameter it must carry.
        :return: The parameter's first value.
        :raises MissingParameter: When the request does not carry it.
        """
        values = request.parameters().get(parameter.value)
        if not values:
            raise MissingParameter(parameter.value)
        return values[0]

    @staticmethod
    def scope_of(request: Request) -> QueryScope:
        """
        :param request: A request that may name a scope.
        :return: The scope it names, the current state by default.
        :raises UnknownScope: When it names a scope that does not exist.
        """
        values: Tuple[str, ...] = tuple(
            request.parameters().get(QuestionsParameter.SCOPE.value, ())
        )
        if not values:
            return QueryScope.CURRENT_STATE
        if values[0] not in {scope.value for scope in QueryScope}:
            raise UnknownScope(values[0], [scope.value for scope in QueryScope])
        return QueryScope(values[0])
