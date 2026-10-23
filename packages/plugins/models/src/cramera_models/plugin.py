"""
The models plugin of the viewer: the Models side panel and the workbench routes it
calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path

from typing_extensions import Any, List, Optional

from cramera.http.messages import HttpMethod, Request, Response
from cramera.plugins import (
    NavigationEntry,
    PanelEntry,
    PluginContext,
    PluginRoute,
    ViewerPlugin,
)
from cramera_models.json_text import JsonText
from cramera_models.workbench import Workbench, WorkbenchChoice
from cramera_protocol.models import (
    ModelsRoute,
    ModelUpload,
    ModeRequest,
    PosteriorRequest,
    ProbabilityRequest,
)
from cramera_protocol.plugins import PluginName
from cramera_protocol.viewer import NavigationGroup

WEB_DIRECTORY = Path(__file__).parent / "web"
"""
The plugin's browser files.
"""


class WebFile(StrEnum):
    """
    The plugin's browser files the viewer is told about.
    """

    MODULE = "index.js"
    """
    The module the viewer imports and registers.
    """


REQUEST_BODY = "The request body"
"""
How errors name the body of a request.
"""

NAVIGATION_TITLE = "Models"
"""
The text of the plugin's entry in the viewer's navigation.
"""

# %% routes


@dataclass(frozen=True)
class ModelsRoutes:
    """
    Answers the workbench routes from one workbench.
    """

    workbench: Workbench
    """
    The workbench the questions are asked of.
    """

    def answer_state(self, request: Request) -> Response:
        """
        :param request: A request for the workbench's state.
        :return: Whether a model is loaded, and its variables.
        """
        return Response.of_json(self.workbench.state())

    def answer_load(self, request: Request) -> Response:
        """
        :param request: A request carrying a :class:`ModelUpload`.
        :return: The state with the loaded model.
        """
        return Response.of_json(
            self.workbench.load(ModelUpload.from_json(self.body(request)))
        )

    def answer_probability(self, request: Request) -> Response:
        """
        :param request: A request carrying a :class:`ProbabilityRequest`.
        :return: The probability of the query given the evidence.
        """
        return Response.of_json(
            self.workbench.probability(ProbabilityRequest.from_json(self.body(request)))
        )

    def answer_posterior(self, request: Request) -> Response:
        """
        :param request: A request carrying a :class:`PosteriorRequest`.
        :return: The posterior marginals as Plotly figures.
        """
        return Response.of_json(
            self.workbench.posterior(PosteriorRequest.from_json(self.body(request)))
        )

    def answer_mode(self, request: Request) -> Response:
        """
        :param request: A request carrying a :class:`ModeRequest`.
        :return: The most likely assignments given the evidence.
        """
        return Response.of_json(
            self.workbench.mode(ModeRequest.from_json(self.body(request)))
        )

    @staticmethod
    def body(request: Request) -> Any:
        """
        :param request: A request with a JSON body.
        :return: The decoded body.
        :raises InvalidJson: When the body is not JSON.
        """
        return JsonText(
            request.body.decode("utf-8", errors="replace"), REQUEST_BODY
        ).decode()

    def routes(self) -> List[PluginRoute]:
        """
        :return: The workbench routes.
        """
        return [
            PluginRoute(HttpMethod.GET, ModelsRoute.STATE, self.answer_state),
            PluginRoute(HttpMethod.POST, ModelsRoute.LOAD, self.answer_load),
            PluginRoute(
                HttpMethod.POST, ModelsRoute.PROBABILITY, self.answer_probability
            ),
            PluginRoute(HttpMethod.POST, ModelsRoute.POSTERIOR, self.answer_posterior),
            PluginRoute(HttpMethod.POST, ModelsRoute.MODE, self.answer_mode),
        ]


# %% plugin


@dataclass
class ModelsPlugin(ViewerPlugin):
    """
    Asks a probabilistic circuit probability, posterior and mode questions from a side
    panel; without the circuit libraries every route answers which are missing.
    """

    choice: WorkbenchChoice = field(default_factory=WorkbenchChoice)
    """
    Creates the workbench the installed libraries allow.
    """

    def name(self) -> str:
        return PluginName.MODELS.value

    def version(self) -> str:
        return version("cramera-models")

    def routes(self, context: PluginContext) -> List[PluginRoute]:
        return ModelsRoutes(self.choice.workbench()).routes()

    def web_directory(self) -> Optional[Path]:
        return WEB_DIRECTORY

    def module(self) -> Optional[str]:
        return WebFile.MODULE.value

    def navigation(self) -> Optional[NavigationEntry]:
        return PanelEntry(NAVIGATION_TITLE, NavigationGroup.ANALYSIS)
