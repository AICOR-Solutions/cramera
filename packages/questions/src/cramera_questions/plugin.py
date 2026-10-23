"""
The viewer plugin answering questions about recorded scenes.

The plugin itself imports nothing of krrood, so a viewer without the CRAM workspace
still loads it and serves its browser module; its routes are built from
:mod:`cramera_questions.routes` only where krrood is installed, and otherwise answer
that it is missing.
"""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.machinery import ModuleSpec
from importlib.metadata import distributions
from pathlib import Path

from typing_extensions import TYPE_CHECKING, Callable, Dict, List, Optional

from cramera.http.messages import HttpMethod, Request, Response
from cramera.plugins import PluginContext, PluginRoute, ViewerPlugin
from cramera_protocol.live import Capability
from cramera_protocol.plugins import PluginName
from cramera_protocol.questions import QuestionsRoute
from cramera_questions.exceptions import QueryLanguageMissing
from cramera_questions.workspace_classes import WorkspaceClassIndex, WorkspacePackage

if TYPE_CHECKING:
    from cramera_questions.routes import SceneQuestionCache

WEB_DIRECTORY = Path(__file__).parent / "web"
"""
The plugin's browser files.
"""

BROWSER_MODULE = "index.js"
"""
The plugin's browser module, relative to :data:`WEB_DIRECTORY`.
"""

DISTRIBUTION_NAME = "cramera-questions"
"""
The distribution the plugin is installed from.
"""

SOURCE_VERSION = "1.0.0"
"""
The version of this source tree, as its ``pyproject.toml`` declares it; reported when
the plugin runs from the sources without being installed.
"""

ModuleFinder = Callable[[str], Optional[ModuleSpec]]
"""
Finds a top-level module without importing it; :func:`importlib.util.find_spec` outside
of tests.
"""


class QuestionsModule(StrEnum):
    """
    The plugin's modules that import krrood, imported only where it is installed.
    """

    ROUTES = "cramera_questions.routes"
    """
    :class:`cramera_questions.routes.QuestionRoutes`.
    """


# %% installation


@dataclass(frozen=True)
class QueryLanguageInstallation:
    """
    Whether krrood, which evaluates the entity query language, is installed.
    """

    finder: ModuleFinder = field(default=importlib.util.find_spec)
    """
    Finds a module without importing it.
    """

    def is_installed(self) -> bool:
        """
        :return: Whether a module with code of its own is found under krrood's name;
            a directory that only shares the name does not count.
        """
        specification = self.finder(WorkspacePackage.KRROOD.value)
        return specification is not None and specification.origin is not None


@dataclass(frozen=True)
class UnavailableQuestionRoutes:
    """
    The plugin's routes in an environment without krrood: each answers that it is
    missing.
    """

    def routes(self) -> List[PluginRoute]:
        """
        :return: One route per :class:`QuestionsRoute` and method.
        """
        return [
            PluginRoute(method, route, self.refuse)
            for route in QuestionsRoute
            for method in (HttpMethod.GET, HttpMethod.POST)
        ]

    @staticmethod
    def refuse(request: Request) -> Response:
        """
        :param request: Any request of the plugin.
        :raises QueryLanguageMissing: Always.
        """
        raise QueryLanguageMissing(WorkspacePackage.KRROOD.value)


# %% plugin


@dataclass
class QuestionsPlugin(ViewerPlugin):
    """
    Answers queries, plain-language questions and graph views about recorded scenes.
    """

    class_index: WorkspaceClassIndex = field(
        default_factory=WorkspaceClassIndex.of_installed_packages
    )
    """
    The workspace classes a query may name.
    """

    installation: QueryLanguageInstallation = field(
        default_factory=QueryLanguageInstallation
    )
    """
    Finds out whether krrood is installed.
    """

    caches: Dict[int, SceneQuestionCache] = field(default_factory=dict)
    """
    The scene questions of each catalog the plugin was given, by the catalog's identity.
    """

    def name(self) -> str:
        return PluginName.QUESTIONS.value

    def version(self) -> str:
        """
        :return: The installed distribution's version, or the version of this source
            tree when it runs without being installed.
        """
        return next(
            (
                distribution.version
                for distribution in distributions(name=DISTRIBUTION_NAME)
            ),
            SOURCE_VERSION,
        )

    def capabilities(self) -> List[Capability]:
        return [Capability.QUESTIONS]

    def web_directory(self) -> Optional[Path]:
        return WEB_DIRECTORY

    def module(self) -> Optional[str]:
        return BROWSER_MODULE

    def routes(self, context: PluginContext) -> List[PluginRoute]:
        if not self.installation.is_installed():
            return UnavailableQuestionRoutes().routes()
        routes = importlib.import_module(QuestionsModule.ROUTES).QuestionRoutes
        answering = routes.of_catalog(context.catalog, self.class_index)
        self.caches[id(context.catalog)] = answering.cache
        return answering.routes()
