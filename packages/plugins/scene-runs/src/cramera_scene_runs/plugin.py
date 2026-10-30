"""
The scene runs plugin: a Runs panel that starts one of the runs the server offers, one
at a time, follows it live and replays its recording.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

from typing_extensions import List, Mapping, Optional

from cramera.http.messages import HttpMethod, Request, Response
from cramera.plugins import (
    PluginContext,
    PluginPrefixRoute,
    PluginRoute,
    RouteDeclaration,
    ViewerPlugin,
)
from cramera.scenes import SceneCatalog
from cramera_protocol.scene_runs import (
    SceneRunCatalog,
    SceneRunsName,
    SceneRunsRoute,
    SceneRunsVariable,
)
from cramera_scene_runs.runs import SceneRunCatalogFile, SceneRunner

WEB_DIRECTORY = Path(__file__).parent / "web"
"""
The plugin's browser files.
"""

MODULE = "index.js"
"""
The plugin's browser module, in :data:`WEB_DIRECTORY`.
"""

LOGS = "scene-runs"
"""
The directory of the runs' output files, in cramera's data directory.
"""

# %% plugin


@dataclass
class SceneRunsPlugin(ViewerPlugin):
    """
    Offers the runs the server's catalog file names; pages behind a password-checking
    proxy may start and stop them.
    """

    environment: Mapping[str, str] = field(default_factory=lambda: os.environ)
    """
    The environment naming the catalog file.
    """

    runner: Optional[SceneRunner] = field(default=None, init=False)
    """
    Starts and stops the runs, once the viewer asked for the routes.
    """

    def name(self) -> str:
        return SceneRunsName.PLUGIN

    def version(self) -> str:
        return version("cramera-scene-runs")

    def web_directory(self) -> Optional[Path]:
        return WEB_DIRECTORY

    def module(self) -> Optional[str]:
        """
        :return: The Runs panel's module where the server offers runs, else None, so a
            viewer that offers none shows no panel.
        """
        if SceneRunsVariable.CATALOG not in self.environment:
            return None
        return MODULE

    def routes(self, context: PluginContext) -> List[RouteDeclaration]:
        """
        :param context: What the viewer offers the plugin.
        :return: The state, and the start and stop other devices may ask for.
        :raises InvalidSceneRunCatalog: When the catalog file cannot be offered.
        """
        catalog = context.catalog
        self.runner = SceneRunner(
            catalog=self.catalog(),
            logs=context.locations.data / LOGS,
            recorded=lambda name: self.holds(catalog, name),
        )
        return [
            PluginRoute(HttpMethod.GET, SceneRunsRoute.STATE, self.answer_state),
            PluginPrefixRoute(
                HttpMethod.POST,
                SceneRunsRoute.START,
                self.answer_start,
                remote_changes=True,
            ),
            PluginRoute(
                HttpMethod.POST,
                SceneRunsRoute.STOP,
                self.answer_stop,
                remote_changes=True,
            ),
        ]

    def catalog(self) -> SceneRunCatalog:
        """
        :return: The runs the catalog file names, none without one.
        :raises InvalidSceneRunCatalog: When the file cannot be offered.
        """
        path = self.environment.get(SceneRunsVariable.CATALOG)
        if path is None:
            return SceneRunCatalog()
        return SceneRunCatalogFile(Path(path)).read()

    @staticmethod
    def holds(catalog: SceneCatalog, name: str) -> bool:
        """
        :param catalog: The viewer's scenes.
        :param name: A recording's name.
        :return: Whether a scenes directory of the viewer holds it.
        """
        return any(directory.holds(name) for directory in catalog.ordered_directories())

    def answer_state(self, request: Request) -> Response:
        """
        :param request: A request for the runs.
        :return: The runs offered and the one started last.
        """
        return Response.of_json(self.runner.state())

    def answer_start(self, request: Request, identifier: str) -> Response:
        """
        :param request: A request to start a run.
        :param identifier: The run.
        :return: The state with the run started.
        """
        return Response.of_json(self.runner.start(identifier))

    def answer_stop(self, request: Request) -> Response:
        """
        :param request: A request to stop the run that runs.
        :return: The state with the run stopped.
        """
        return Response.of_json(self.runner.stop())

    def close(self) -> None:
        """
        Stop the run that runs.
        """
        if self.runner is not None:
            self.runner.close()
