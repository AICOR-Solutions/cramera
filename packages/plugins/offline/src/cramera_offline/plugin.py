"""
The offline plugin of the viewer: the tour panel and the routes it reads, the storyboard
and the completeness check of a bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path

from typing_extensions import List, Optional

from cramera.http.messages import HttpMethod, Request, Response
from cramera.plugins import PluginContext, PluginRoute, ViewerPlugin
from cramera.scenes import SceneCatalog
from cramera_offline.bundle_check import BundleCheck
from cramera_offline.exceptions import MissingQueryParameter, StoryboardNotFound
from cramera_offline.json_file import JsonFile
from cramera_protocol.offline import (
    OfflineParameter,
    OfflineRoute,
    PresentationFile,
    Storyboard,
)
from cramera_protocol.plugins import PluginName
from cramera_protocol.viewer import ViewerRoute

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


# %% routes


@dataclass(frozen=True)
class OfflineRoutes:
    """
    Answers the offline plugin's routes from the viewer's scenes.
    """

    catalog: SceneCatalog
    """
    The scenes the viewer shows.
    """

    def answer_storyboard(self, request: Request) -> Response:
        """
        :param request: A request for the storyboard.
        :return: The storyboard of the first scenes directory, in the order bundles
            are preferred, that holds one.
        :raises StoryboardNotFound: When no scenes directory holds a storyboard.
        """
        directories = self.catalog.ordered_directories()
        for directory in directories:
            path = directory.path / PresentationFile.STORYBOARD
            if path.is_file():
                return Response.of_json(Storyboard.from_json(JsonFile(path).read()))
        raise StoryboardNotFound([directory.path for directory in directories])

    def answer_bundle_check(self, request: Request) -> Response:
        """
        :param request: A request naming a bundle in :attr:`OfflineParameter.SCENE`.
        :return: The bundle's completeness report.
        :raises MissingQueryParameter: When the request names no bundle.
        :raises UnknownScene: When no scenes directory holds the bundle.
        """
        names = request.parameters().get(OfflineParameter.SCENE, [])
        if not names:
            raise MissingQueryParameter(OfflineParameter.SCENE)
        directory = self.catalog.directory_of(names[0])
        return Response.of_json(BundleCheck(directory.path / names[0]).report())


# %% plugin


@dataclass
class OfflinePlugin(ViewerPlugin):
    """
    Presents recorded scenes as a storyboard of chapters and reports whether bundles
    hold every file they reference.
    """

    def name(self) -> str:
        return PluginName.OFFLINE.value

    def version(self) -> str:
        return version("cramera-offline")

    def routes(self, context: PluginContext) -> List[PluginRoute]:
        routes = OfflineRoutes(context.catalog)
        return [
            PluginRoute(
                HttpMethod.GET, OfflineRoute.STORYBOARD, routes.answer_storyboard
            ),
            PluginRoute(
                HttpMethod.GET, OfflineRoute.BUNDLE_CHECK, routes.answer_bundle_check
            ),
        ]

    def web_directory(self) -> Optional[Path]:
        return WEB_DIRECTORY

    def module(self) -> Optional[str]:
        return WebFile.MODULE.value

    def storyboard_route(self) -> str:
        """
        :return: The path the viewer serves the storyboard at.
        """
        return f"{ViewerRoute.PLUGIN_API}{self.name()}/{OfflineRoute.STORYBOARD}"
