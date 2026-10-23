"""
The cable lab plugin of the viewer: a side panel that opens the cable lab page, and the
routes that build, command, read and stop the cable simulation.
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
from cramera.plugins import (
    NavigationEntry,
    PageEntry,
    PluginContext,
    PluginRoute,
    ViewerPlugin,
)
from cramera_cable_lab.exceptions import CableLabLibrariesMissing
from cramera_cable_lab.session import CableLabSession, CableSimulation
from cramera_protocol.cable_lab import (
    CableLabFile,
    CableConfiguration,
    CableLabRoute,
    GripperCommand,
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


class Distribution(StrEnum):
    """
    The package the plugin is installed from.
    """

    NAME = "cramera-cable-lab"
    """
    The distribution's name, under which its version is recorded.
    """


NAVIGATION_TITLE = "Cable Lab"
"""
The text of the plugin's entry in the viewer's navigation.
"""

# %% libraries


class SimulationLibrary(StrEnum):
    """
    The top-level modules the cable simulation imports.
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

    SEMANTIC_DIGITAL_TWIN = "semantic_digital_twin"
    """
    CRAM's world model and its MuJoCo adapter.
    """

    PHYSICS_SIMULATORS = "physics_simulators"
    """
    CRAM's simulators.
    """


class SimulationModule(StrEnum):
    """
    The plugin's module that imports the simulation libraries; it is only imported once
    they are found.
    """

    PHYSICS = "cramera_cable_lab.physics"
    """
    :class:`cramera_cable_lab.physics.CablePhysics`.
    """


ModuleFinder = Callable[[str], Optional[ModuleSpec]]
"""
Finds a top-level module without importing it; :func:`importlib.util.find_spec` outside
of tests.
"""


@dataclass(frozen=True)
class SimulationLibraries:
    """
    Finds out which of the simulation libraries are installed, before anything imports
    them.
    """

    modules: Tuple[SimulationLibrary, ...] = tuple(SimulationLibrary)
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


@dataclass(frozen=True)
class CablePhysicsFactory:
    """
    Builds cable simulations where the libraries are installed.
    """

    libraries: SimulationLibraries
    """
    Whether the simulation libraries are installed.
    """

    def build(self, configuration: CableConfiguration) -> CableSimulation:
        """
        :param configuration: The cable.
        :return: Its simulation, not yet started.
        :raises CableLabLibrariesMissing: When the libraries are missing.
        :raises CableNotBuilt: When MuJoCo cannot build the cable.
        """
        missing = self.libraries.missing()
        if missing:
            raise CableLabLibrariesMissing(missing)
        physics = importlib.import_module(SimulationModule.PHYSICS)
        return physics.CablePhysics(configuration=configuration)


# %% routes


@dataclass(frozen=True)
class CableLabRoutes:
    """
    Answers the cable lab routes from one session.
    """

    session: CableLabSession
    """
    The session that owns the simulation.
    """

    def answer_state(self, request: Request) -> Response:
        """
        :param request: A request for the lab's state.
        :return: The lifecycle and the measured cable.
        """
        return Response.of_json(self.session.state())

    def answer_start(self, request: Request) -> Response:
        """
        :param request: A request carrying a :class:`CableConfiguration`.
        :return: The state of the new simulation.
        """
        return Response.of_json(
            self.session.start(request.document(CableConfiguration))
        )

    def answer_command(self, request: Request) -> Response:
        """
        :param request: A request carrying a :class:`GripperCommand`.
        :return: The state after the command.
        """
        return Response.of_json(self.session.command(request.document(GripperCommand)))

    def answer_reset(self, request: Request) -> Response:
        """
        :param request: A request to build the last cable again.
        :return: The state of the new simulation.
        """
        return Response.of_json(self.session.reset())

    def answer_stop(self, request: Request) -> Response:
        """
        :param request: A request to stop the simulation.
        :return: Its last state.
        """
        return Response.of_json(self.session.stop())

    def routes(self) -> List[PluginRoute]:
        """
        :return: The cable lab routes.
        """
        return [
            PluginRoute(HttpMethod.GET, CableLabRoute.STATE, self.answer_state),
            PluginRoute(HttpMethod.POST, CableLabRoute.START, self.answer_start),
            PluginRoute(HttpMethod.POST, CableLabRoute.COMMAND, self.answer_command),
            PluginRoute(HttpMethod.POST, CableLabRoute.RESET, self.answer_reset),
            PluginRoute(HttpMethod.POST, CableLabRoute.STOP, self.answer_stop),
        ]


# %% plugin


@dataclass
class CableLabPlugin(ViewerPlugin):
    """
    The Cable lab panel and page, and the simulation they run.
    """

    libraries: SimulationLibraries = field(default_factory=SimulationLibraries)
    """
    Whether the simulation libraries are installed.
    """

    sessions: List[CableLabSession] = field(default_factory=list, init=False)
    """
    The sessions the plugin's routes were built with; closed with the plugin.
    """

    def name(self) -> str:
        return PluginName.CABLE_LAB.value

    def version(self) -> str:
        return version(Distribution.NAME)

    def routes(self, context: PluginContext) -> List[PluginRoute]:
        session = CableLabSession(factory=CablePhysicsFactory(self.libraries).build)
        self.sessions.append(session)
        return CableLabRoutes(session).routes()

    def web_directory(self) -> Optional[Path]:
        return WEB_DIRECTORY

    def module(self) -> Optional[str]:
        return WebFile.MODULE.value

    def navigation(self) -> Optional[NavigationEntry]:
        return PageEntry(
            NAVIGATION_TITLE, NavigationGroup.LABORATORY, CableLabFile.PAGE.value
        )

    def close(self) -> None:
        for session in self.sessions:
            session.close()
