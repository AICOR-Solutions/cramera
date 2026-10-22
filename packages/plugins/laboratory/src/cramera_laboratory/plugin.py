"""
The laboratory plugin of the viewer: the Laboratory side panel and the routes it calls
to install the shipped laboratories, list the devices and operate the contact
simulation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

from typing_extensions import Any, Callable, List, Optional, Type, TypeVar

from cramera.confinement import ConfinedDirectory
from cramera.http.messages import HttpMethod, Request, Response
from cramera.locations import DataLocations
from cramera.plugins import (
    PluginContext,
    PluginPrefixRoute,
    PluginRoute,
    RouteDeclaration,
    ViewerPlugin,
)
from cramera_laboratory.devices import DeviceShelf
from cramera_laboratory.exceptions import InvalidRequestBody
from cramera_laboratory.resources import LaboratoryInstallation, LaboratoryShelf
from cramera_laboratory.task_runs import LaboratoryTask, TaskProcess, TaskRecording
from cramera_laboratory.session import (
    ContactSimulation,
    MujocoSimulations,
    SimulationFactory,
    SimulationSession,
)
from cramera_protocol.document import JsonDocument
from cramera_protocol.laboratory.physics import (
    CentrifugeRequest,
    DispenserRequest,
    EmptyRequest,
    InstalledLaboratory,
    InstrumentRequest,
    LaboratoryCatalog,
    LaboratoryChoice,
    LaboratoryEntry,
    LaboratoryFile,
    LaboratoryName,
    LaboratoryRoute,
    LiquidRequest,
    ManualRequest,
    OpeningRequest,
    TargetRequest,
)

WEB_DIRECTORY = Path(__file__).parent / "web"
"""
The plugin's browser files.
"""

EMPTY_OBJECT = "{}"
"""
The body of a request that gives nothing.
"""

DocumentType = TypeVar("DocumentType", bound=JsonDocument)
"""
A request document class.
"""

# %% routes


@dataclass(frozen=True)
class CommandRoute:
    """
    A route that applies one command to the running simulation.
    """

    route: LaboratoryRoute
    """
    The route.
    """

    document_class: Type[JsonDocument]
    """
    The document its requests carry.
    """

    action: Callable[[ContactSimulation, Any], None]
    """
    What the command does with the simulation and the request's document.
    """


COMMAND_ROUTES = (
    CommandRoute(
        LaboratoryRoute.RESET, EmptyRequest, lambda simulation, _: simulation.reset()
    ),
    CommandRoute(
        LaboratoryRoute.RELEASE,
        EmptyRequest,
        lambda simulation, _: simulation.release(),
    ),
    CommandRoute(
        LaboratoryRoute.TARE, EmptyRequest, lambda simulation, _: simulation.tare()
    ),
    CommandRoute(
        LaboratoryRoute.TARGET,
        TargetRequest,
        lambda simulation, request: simulation.set_target(request),
    ),
    CommandRoute(
        LaboratoryRoute.LIQUID,
        LiquidRequest,
        lambda simulation, request: simulation.fill(request),
    ),
    CommandRoute(
        LaboratoryRoute.CENTRIFUGE,
        CentrifugeRequest,
        lambda simulation, request: simulation.operate_centrifuge(request),
    ),
    CommandRoute(
        LaboratoryRoute.MANUAL,
        ManualRequest,
        lambda simulation, request: simulation.read_manual(request),
    ),
    CommandRoute(
        LaboratoryRoute.REFRIGERATOR,
        OpeningRequest,
        lambda simulation, request: simulation.operate_refrigerator(request),
    ),
    CommandRoute(
        LaboratoryRoute.DRAWER,
        OpeningRequest,
        lambda simulation, request: simulation.operate_drawer(request),
    ),
    CommandRoute(
        LaboratoryRoute.DISPENSER,
        DispenserRequest,
        lambda simulation, request: simulation.operate_dispenser(request),
    ),
    CommandRoute(
        LaboratoryRoute.INSTRUMENT,
        InstrumentRequest,
        lambda simulation, request: simulation.move_instrument(request),
    ),
)
"""
The routes that command the running simulation.
"""


@dataclass
class LaboratoryRoutes:
    """
    Answers the laboratory's routes.
    """

    locations: DataLocations
    """
    Where the viewer keeps its scenes.
    """

    factory: SimulationFactory = field(default_factory=MujocoSimulations)
    """
    Creates contact simulations.
    """

    shelf: LaboratoryShelf = field(default_factory=LaboratoryShelf)
    """
    The shipped laboratories.
    """

    devices: DeviceShelf = field(default_factory=DeviceShelf)
    """
    The device catalog.
    """

    session: SimulationSession = field(init=False)
    """
    The contact simulation's session.
    """

    transfer: TaskProcess = field(init=False)
    """
    Runs the PR2 vessel transfer demo.
    """

    def __post_init__(self) -> None:
        self.session = SimulationSession(self.locations, self.factory)
        self.transfer = TaskProcess.of_task(
            LaboratoryTask.TRANSFER, TaskRecording.TRANSFER, self.locations
        )

    @property
    def installation(self) -> LaboratoryInstallation:
        """
        Installs laboratories into the viewer's local scenes.
        """
        return LaboratoryInstallation(self.locations)

    # %% bodies

    @staticmethod
    def body(request: Request, document_class: Type[DocumentType]) -> DocumentType:
        """
        The HTTP boundary is where an unreadable body becomes an error answer, so this
        is where JSON decoding errors are caught.

        :param request: A request with a JSON body, or none for an empty object.
        :param document_class: The document the body holds.
        :return: The document.
        :raises InvalidRequestBody: When the body is not JSON.
        """
        text = request.body.decode("utf-8", errors="replace") or EMPTY_OBJECT
        try:
            data = json.loads(text)
        except ValueError as error:
            raise InvalidRequestBody(str(error)) from error
        return document_class.from_json(data)

    # %% catalog

    def answer_laboratories(self, request: Request) -> Response:
        """
        :param request: A request for the shipped laboratories.
        :return: The laboratories and whether they are installed.
        """
        installation = self.installation
        return Response.of_json(
            LaboratoryCatalog(
                laboratories=[
                    LaboratoryEntry(
                        name=laboratory.name,
                        title=laboratory.title(),
                        installed=installation.installed(laboratory.name),
                        instruments=(
                            0
                            if laboratory.instruments() is None
                            else len(laboratory.instruments().instruments)
                        ),
                    )
                    for laboratory in self.shelf.laboratories()
                ],
                physics_available=self.factory.available(),
            )
        )

    def answer_install(self, request: Request) -> Response:
        """
        :param request: A request carrying a :class:`LaboratoryChoice`.
        :return: The bundle the laboratory is shown as.
        """
        choice = self.body(request, LaboratoryChoice)
        laboratory = self.shelf.laboratory(choice.laboratory)
        scene = self.installation.install(laboratory, laboratory.name)
        return Response.of_json(InstalledLaboratory(scene=scene))

    def answer_devices(self, request: Request) -> Response:
        """
        :param request: A request for the device catalog.
        :return: The devices.
        """
        return Response.of_json(self.devices.entries())

    def answer_device_file(self, request: Request, path: str) -> Response:
        """
        :param request: A request for a file of a device folder.
        :param path: ``<device>/<file>``.
        :return: The file.
        """
        name, _, relative = path.partition("/")
        folder = self.devices.folder(name)
        return Response.of_file(ConfinedDirectory(folder.directory).file(relative))

    # %% simulation

    def answer_transfer_state(self, request: Request) -> Response:
        """
        :param request: A request for the transfer demo's state.
        :return: How far the demo is.
        """
        return Response.of_json(self.transfer.state())

    def answer_transfer_start(self, request: Request) -> Response:
        """
        :param request: A request carrying an :class:`EmptyRequest`.
        :return: How far the demo is after starting it.
        """
        self.body(request, EmptyRequest)
        return Response.of_json(self.transfer.start())

    def answer_transfer_stop(self, request: Request) -> Response:
        """
        :param request: A request carrying an :class:`EmptyRequest`.
        :return: How far the demo is after ending it.
        """
        self.body(request, EmptyRequest)
        return Response.of_json(self.transfer.stop())

    def answer_state(self, request: Request) -> Response:
        """
        :param request: A request for the simulation's state.
        :return: The state.
        """
        return Response.of_json(self.session.answer())

    def answer_start(self, request: Request) -> Response:
        """
        :param request: A request carrying a :class:`LaboratoryChoice`.
        :return: The state of the started simulation.
        """
        choice = self.body(request, LaboratoryChoice)
        return Response.of_json(
            self.session.start(self.shelf.laboratory(choice.laboratory))
        )

    def answer_stop(self, request: Request) -> Response:
        """
        :param request: A request carrying an :class:`EmptyRequest`.
        :return: The state of the stopped simulation.
        """
        self.body(request, EmptyRequest)
        return Response.of_json(self.session.stop())

    def command(self, command: CommandRoute) -> Callable[[Request], Response]:
        """
        :param command: A command's route.
        :return: The handler of the route.
        """

        def handle(request: Request) -> Response:
            document = self.body(request, command.document_class)
            return Response.of_json(
                self.session.command(
                    lambda simulation: command.action(simulation, document)
                )
            )

        return handle

    def routes(self) -> List[RouteDeclaration]:
        """
        :return: Every route of the laboratory.
        """
        return [
            PluginRoute(
                HttpMethod.GET, LaboratoryRoute.LABORATORIES, self.answer_laboratories
            ),
            PluginRoute(HttpMethod.POST, LaboratoryRoute.INSTALL, self.answer_install),
            PluginRoute(HttpMethod.GET, LaboratoryRoute.DEVICES, self.answer_devices),
            PluginPrefixRoute(
                HttpMethod.GET, LaboratoryRoute.DEVICE_FILES, self.answer_device_file
            ),
            PluginRoute(
                HttpMethod.GET,
                LaboratoryRoute.TRANSFER_STATE,
                self.answer_transfer_state,
            ),
            PluginRoute(
                HttpMethod.POST,
                LaboratoryRoute.TRANSFER_START,
                self.answer_transfer_start,
            ),
            PluginRoute(
                HttpMethod.POST,
                LaboratoryRoute.TRANSFER_STOP,
                self.answer_transfer_stop,
            ),
            PluginRoute(HttpMethod.GET, LaboratoryRoute.STATE, self.answer_state),
            PluginRoute(HttpMethod.POST, LaboratoryRoute.START, self.answer_start),
            PluginRoute(HttpMethod.POST, LaboratoryRoute.STOP, self.answer_stop),
            *(
                PluginRoute(HttpMethod.POST, command.route, self.command(command))
                for command in COMMAND_ROUTES
            ),
        ]


# %% plugin


@dataclass
class LaboratoryPlugin(ViewerPlugin):
    """
    Shows the shipped laboratories, their devices and their contact simulation in a side
    panel.
    """

    factory: SimulationFactory = field(default_factory=MujocoSimulations)
    """
    Creates contact simulations.
    """

    def name(self) -> str:
        return LaboratoryName.PLUGIN.value

    def version(self) -> str:
        return version("cramera-laboratory")

    def routes(self, context: PluginContext) -> List[RouteDeclaration]:
        return LaboratoryRoutes(context.locations, self.factory).routes()

    def web_directory(self) -> Optional[Path]:
        return WEB_DIRECTORY

    def module(self) -> Optional[str]:
        return LaboratoryFile.MODULE.value
