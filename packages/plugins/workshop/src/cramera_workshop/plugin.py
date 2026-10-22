"""
The workshop plugin of the viewer: the Workshop side panel, and the routes that start,
command and read the workshop's contact world.
"""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.machinery import ModuleSpec
from importlib.metadata import version
from pathlib import Path

from typing_extensions import Callable, List, Optional, Tuple

from cramera.http.messages import HttpMethod, Request, Response
from cramera.plugins import PluginContext, PluginRoute, ViewerPlugin
from cramera.scenes import SceneCatalog
from cramera_protocol.plugins import PluginName
from cramera_protocol.workshop import WorkshopCommand, WorkshopRoute, WorkshopState
from cramera_workshop.bundle import WorkshopBundle
from cramera_workshop.exceptions import WorkshopPhysicsMissing
from cramera_workshop.session import WorkshopDynamics, WorkshopSession

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


class Distribution(StrEnum):
    """
    The package the plugin is installed from.
    """

    NAME = "cramera-workshop"
    """
    The distribution's name, under which its version is recorded.
    """


# %% physics libraries


class PhysicsLibrary(StrEnum):
    """
    The top-level modules the contact world imports.
    """

    MUJOCO = "mujoco"
    """
    The physics engine.
    """

    NUMPY = "numpy"
    """
    Arrays.
    """

    SCIPY = "scipy"
    """
    Rotations.
    """


class PhysicsModule(StrEnum):
    """
    The plugin's module that imports the physics libraries; it is only imported once
    they are found.
    """

    PHYSICS = "cramera_workshop.physics"
    """
    :class:`cramera_workshop.physics.WorkshopPhysics`.
    """


ModuleFinder = Callable[[str], Optional[ModuleSpec]]
"""
Finds a top-level module without importing it; :func:`importlib.util.find_spec` outside
of tests.
"""


@dataclass(frozen=True)
class PhysicsLibraries:
    """
    Finds out which of the physics libraries are installed, before anything imports
    them, so a missing library is a value rather than an import error.
    """

    modules: Tuple[PhysicsLibrary, ...] = tuple(PhysicsLibrary)
    """
    The modules that must be installed.
    """

    finder: ModuleFinder = field(default=importlib.util.find_spec)
    """
    Finds a module without importing it.
    """

    def missing(self) -> List[str]:
        """
        :return: The modules that cannot be found, in the order of :attr:`modules`.
        """
        return [
            module.value
            for module in self.modules
            if (specification := self.finder(module)) is None
            or specification.origin is None
        ]


# %% contact world


@dataclass(frozen=True)
class ShownWorkshopPhysics:
    """
    Builds the contact world of the workshop the viewer shows.
    """

    catalog: SceneCatalog
    """
    The scenes the viewer shows.
    """

    libraries: PhysicsLibraries
    """
    Whether the physics libraries are installed.
    """

    def build(self) -> WorkshopDynamics:
        """
        :return: The contact world.
        :raises WorkshopPhysicsMissing: When the physics libraries are missing.
        """
        missing = self.libraries.missing()
        if missing:
            raise WorkshopPhysicsMissing(missing)
        physics = importlib.import_module(PhysicsModule.PHYSICS)
        return physics.WorkshopPhysics(WorkshopBundle.shown_or_packaged(self.catalog))


# %% routes


@dataclass(frozen=True)
class WorkshopRoutes:
    """
    Answers the workshop routes from one session.
    """

    session: WorkshopSession
    """
    The session that owns the contact world.
    """

    libraries: PhysicsLibraries
    """
    Whether the physics libraries are installed.
    """

    def answer_state(self, request: Request) -> Response:
        """
        :param request: A request for the measured state.
        :return: The state; without the physics libraries an unavailable state naming
            them.
        """
        missing = self.libraries.missing()
        if missing:
            return Response.of_json(
                WorkshopState(
                    available=False, error=WorkshopPhysicsMissing(missing).message()
                )
            )
        return Response.of_json(self.session.state())

    def answer_command(self, request: Request) -> Response:
        """
        :param request: A request carrying a :class:`WorkshopCommand`.
        :return: The state after the command.
        """
        return Response.of_json(self.session.command(request.document(WorkshopCommand)))

    def routes(self) -> List[PluginRoute]:
        """
        :return: The workshop routes.
        """
        return [
            PluginRoute(HttpMethod.GET, WorkshopRoute.STATE, self.answer_state),
            PluginRoute(HttpMethod.POST, WorkshopRoute.COMMAND, self.answer_command),
        ]


# %% plugin


@dataclass
class WorkshopPlugin(ViewerPlugin):
    """
    The Workshop panel and its contact world; the world is built on the first start,
    from the workshop bundle the viewer shows.
    """

    libraries: PhysicsLibraries = field(default_factory=PhysicsLibraries)
    """
    Whether the physics libraries are installed.
    """

    sessions: List[WorkshopSession] = field(default_factory=list, init=False)
    """
    The sessions the plugin's routes were built with; closed with the plugin.
    """

    def name(self) -> str:
        return PluginName.WORKSHOP.value

    def version(self) -> str:
        return version(Distribution.NAME)

    def routes(self, context: PluginContext) -> List[PluginRoute]:
        session = WorkshopSession(
            factory=ShownWorkshopPhysics(context.catalog, self.libraries).build
        )
        self.sessions.append(session)
        return WorkshopRoutes(session, self.libraries).routes()

    def web_directory(self) -> Optional[Path]:
        return WEB_DIRECTORY

    def module(self) -> Optional[str]:
        return WebFile.MODULE.value

    def close(self) -> None:
        for session in self.sessions:
            session.close()
