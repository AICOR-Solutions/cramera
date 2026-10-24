"""
The questions plugin's routes over recorded scenes.

They hand each request to cramera-bridge's question engine, which evaluates queries with
krrood, so this module is only imported where both are installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import List, Optional, Tuple

from cramera.http.messages import HttpMethod, Request, Response
from cramera.plugins import PluginRoute
from cramera.scenes import SceneCatalog
from cramera_bridge.questions.exceptions import UnknownScope
from cramera_bridge.questions.scenes import RecordedSceneQuestions
from cramera_bridge.questions.workspace_classes import WorkspaceClassIndex
from cramera_protocol.questions import (
    QueryRequest,
    QueryScope,
    QuestionRequest,
    QuestionsParameter,
    QuestionsRoute,
)
from cramera_questions.exceptions import MissingParameter

# %% routes


@dataclass(frozen=True)
class QuestionRoutes:
    """
    The plugin's routes over one catalog's scenes.
    """

    @classmethod
    def of_catalog(
        cls, catalog: SceneCatalog, class_index: Optional[WorkspaceClassIndex] = None
    ) -> QuestionRoutes:
        """
        :param catalog: The scenes the viewer shows.
        :param class_index: The workspace classes a query may name; None reads those of
            the installed workspace packages.
        :return: The routes over the catalog's scenes.
        """
        return cls(RecordedSceneQuestions.of_catalog(catalog, class_index))

    questions: RecordedSceneQuestions
    """
    The question engine's answers about the catalog's scenes.
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
        return Response.of_json(self.questions.preset_catalog(self.scene_of(request)))

    def answer_vocabulary(self, request: Request) -> Response:
        """
        :param request: Names the scene and, optionally, the scope.
        :return: The names a query may use.
        """
        return Response.of_json(
            self.questions.vocabulary(self.scene_of(request), self.scope_of(request))
        )

    def answer_members(self, request: Request) -> Response:
        """
        :param request: Names the scene, the name and, optionally, the scope.
        :return: The members that may follow the name's dot.
        """
        scene = self.scene_of(request)
        name = self.required(request, QuestionsParameter.NAME)
        return Response.of_json(
            self.questions.members(scene, self.scope_of(request), name)
        )

    def answer_graph(self, request: Request) -> Response:
        """
        :param request: Names the scene and the view.
        :return: The graph view.
        """
        scene = self.scene_of(request)
        view = self.required(request, QuestionsParameter.VIEW)
        return Response.of_json(self.questions.graph_view(scene, view))

    def answer_query(self, request: Request) -> Response:
        """
        :param request: A :class:`QueryRequest` naming its scene.
        :return: The answer.
        """
        query = QueryRequest.from_json(request.json())
        scene = self.scene_name(query.scene)
        return Response.of_json(self.questions.answer_query(scene, query))

    def answer_question(self, request: Request) -> Response:
        """
        :param request: A :class:`QuestionRequest` naming its scene.
        :return: The ready-made question it asks, or the reply that none does.
        """
        question = QuestionRequest.from_json(request.json())
        scene = self.scene_name(question.scene)
        return Response.of_json(self.questions.answer_question(scene, question))

    # %% parameters

    def scene_of(self, request: Request) -> str:
        """
        :param request: A request naming its scene in the query.
        :return: The scene.
        :raises MissingParameter: When the request names none.
        """
        return self.required(request, QuestionsParameter.SCENE)

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
