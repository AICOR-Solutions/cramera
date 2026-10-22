"""
The contact simulation's session: one simulation at a time, stepped in real time by a
worker thread, every command serialized with the stepping under one lock, and the bundle
the viewer shows it in.

The viewer gives plugins no shutdown hook, so the worker is a daemon thread; the stop
route ends and joins it, and a new start replaces it.
"""

from __future__ import annotations

import importlib
import importlib.util
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import Callable, Optional

from cramera.locations import DataLocations
from cramera_laboratory.exceptions import (
    PhysicsUnavailable,
    SimulationNotRunning,
)
from cramera_laboratory.resources import LaboratoryBundle, LaboratoryInstallation
from cramera_laboratory.scene_files import JsonFile
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.laboratory.layout import LaboratorySceneKey
from cramera_protocol.laboratory.physics import (
    CentrifugeRequest,
    ContactPhysicsControls,
    DispenserRequest,
    InstrumentRequest,
    LiquidRequest,
    ManualRequest,
    OpeningRequest,
    SimulationAnswer,
    SimulationSnapshot,
    SimulationState,
    TargetRequest,
)

CONTACT_SUFFIX = "_contact_physics"
"""
What a laboratory's name gains for the bundle that shows its simulation.
"""

CONTACT_TASK = "Contact physics"
"""
The task the scene picker shows for a simulation's bundle.
"""

SHOWN_FRAME_RATE = 1.0
"""
The frame rate of the simulation's bundle, which holds a single frame.
"""

WORKER_INTERVAL = 0.005
"""
How long the worker waits between batches of steps, in seconds.
"""

LONGEST_CATCH_UP = 0.1
"""
The most wall-clock time one batch makes up for, in seconds, so a stalled worker does
not race.
"""


class PhysicsModule(StrEnum):
    """
    The optional modules the contact simulation needs.
    """

    MUJOCO = "mujoco"
    """
    The physics engine.
    """

    SIMULATION = "cramera_laboratory.physics.simulation"
    """
    The laboratory's simulation, which imports the engine.
    """


# %% engine


class ContactSimulation(ABC):
    """
    What the session asks of a contact simulation; it serializes every call.
    """

    @property
    @abstractmethod
    def timestep(self) -> float:
        """
        The integration step, in seconds.
        """

    @abstractmethod
    def step(self, count: int) -> None:
        """
        :param count: How many steps to integrate.
        """

    @abstractmethod
    def reset(self) -> None:
        """
        Restore the authored laboratory.
        """

    @abstractmethod
    def set_target(self, request: TargetRequest) -> None:
        """
        :param request: An object to pull and its target.
        """

    @abstractmethod
    def release(self) -> None:
        """
        Let go of the pulled object.
        """

    @abstractmethod
    def fill(self, request: LiquidRequest) -> None:
        """
        :param request: A vessel and its new amount of liquid.
        """

    @abstractmethod
    def tare(self) -> None:
        """
        Take the scale's settled load as zero.
        """

    @abstractmethod
    def operate_centrifuge(self, request: CentrifugeRequest) -> None:
        """
        :param request: A centrifuge operation.
        """

    @abstractmethod
    def read_manual(self, request: ManualRequest) -> None:
        """
        :param request: A manual for the centrifuge.
        """

    @abstractmethod
    def operate_refrigerator(self, request: OpeningRequest) -> None:
        """
        :param request: A door operation.
        """

    @abstractmethod
    def operate_drawer(self, request: OpeningRequest) -> None:
        """
        :param request: A drawer operation.
        """

    @abstractmethod
    def operate_dispenser(self, request: DispenserRequest) -> None:
        """
        :param request: A dispensing station operation.
        """

    @abstractmethod
    def move_instrument(self, request: InstrumentRequest) -> None:
        """
        :param request: An instrument and its pose.
        """

    @abstractmethod
    def snapshot(self) -> SimulationSnapshot:
        """
        :return: What the simulation measures.
        """

    @abstractmethod
    def controls(self) -> ContactPhysicsControls:
        """
        :return: What the browser needs to operate the simulation.
        """


class SimulationFactory(ABC):
    """
    Creates contact simulations.
    """

    @abstractmethod
    def available(self) -> bool:
        """
        :return: Whether simulations can be created here.
        """

    @abstractmethod
    def create(self, laboratory: LaboratoryBundle) -> ContactSimulation:
        """
        :param laboratory: A laboratory.
        :return: Its contact simulation.
        """


@dataclass(frozen=True)
class MujocoSimulations(SimulationFactory):
    """
    Creates MuJoCo simulations; the engine is an optional dependency, so its module is
    imported only when a simulation starts.
    """

    def available(self) -> bool:
        return importlib.util.find_spec(PhysicsModule.MUJOCO) is not None

    def create(self, laboratory: LaboratoryBundle) -> ContactSimulation:
        """
        :param laboratory: A laboratory.
        :return: Its contact simulation.
        :raises PhysicsUnavailable: When MuJoCo is not installed.
        """
        if not self.available():
            raise PhysicsUnavailable()
        module = importlib.import_module(PhysicsModule.SIMULATION)
        return module.LaboratoryPhysics(laboratory)


# %% bundle


@dataclass(frozen=True)
class ContactBundle:
    """
    The bundle the viewer shows a simulation in: the laboratory's assets with the
    simulation's controls and its state at the start.
    """

    installation: LaboratoryInstallation
    """
    Where the viewer keeps its scenes.
    """

    laboratory: LaboratoryBundle
    """
    The laboratory simulated.
    """

    @property
    def name(self) -> str:
        """
        The bundle's name.
        """
        return f"{self.laboratory.name}{CONTACT_SUFFIX}"

    def write(self, simulation: ContactSimulation) -> str:
        """
        Install the bundle, then write its description and its single frame.

        :param simulation: The simulation, freshly reset.
        :return: The bundle's name.
        """
        self.installation.install(self.laboratory, self.name)
        directory = self.installation.locations.local_scenes / self.name
        description = SceneDescription.from_json(self.laboratory.description.to_json())
        description.name = self.name
        description.task = CONTACT_TASK
        description.frames_per_second = SHOWN_FRAME_RATE
        description.trajectory = BundleFile.TRAJECTORY.value
        description.extensions[LaboratorySceneKey.CONTACT_PHYSICS.value] = (
            simulation.controls().to_json()
        )
        snapshot = simulation.snapshot()
        JsonFile(directory / BundleFile.SCENE).write(description)
        JsonFile(directory / BundleFile.TRAJECTORY).write(
            Trajectory(
                frames=[dict(snapshot.joints)],
                frames_per_second=SHOWN_FRAME_RATE,
                objects=[dict(snapshot.objects)],
                body_poses=[dict(snapshot.body_poses)],
            )
        )
        self.installation.register(description, self.name)
        return self.name


# %% session


@dataclass
class SimulationSession:
    """
    Runs at most one contact simulation and serializes everything done to it.
    """

    locations: DataLocations
    """
    Where the viewer keeps its scenes.
    """

    factory: SimulationFactory = field(default_factory=MujocoSimulations)
    """
    Creates a laboratory's simulation.
    """

    simulation: Optional[ContactSimulation] = field(default=None, init=False)
    """
    The simulation, None before the first start.
    """

    laboratory: Optional[LaboratoryBundle] = field(default=None, init=False)
    """
    The laboratory simulated.
    """

    scene: Optional[str] = field(default=None, init=False)
    """
    The bundle the simulation is shown in.
    """

    error: Optional[str] = field(default=None, init=False)
    """
    Why the simulation failed, None while it did not.
    """

    worker: Optional[threading.Thread] = field(default=None, init=False)
    """
    The thread stepping the simulation, None while it is stopped.
    """

    stopping: threading.Event = field(default_factory=threading.Event, init=False)
    """
    Tells the worker to end.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    """
    Serializes stepping, commands and reading the state.
    """

    lifecycle: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    """
    Serializes starting and stopping, so no start races a stop's join.
    """

    # %% lifecycle

    def start(self, laboratory: LaboratoryBundle) -> SimulationAnswer:
        """
        Start a laboratory's simulation and write the bundle that shows it; a running
        simulation of another laboratory is stopped first, one of the same laboratory
        keeps running.

        :param laboratory: The laboratory.
        :return: The session's state.
        :raises PhysicsUnavailable: When MuJoCo is not installed.
        """
        with self.lifecycle:
            if self.running() and self.laboratory.directory == laboratory.directory:
                return self.answer()
            self.halt()
            simulation = self.factory.create(laboratory)
            scene = ContactBundle(
                LaboratoryInstallation(self.locations), laboratory
            ).write(simulation)
            with self.lock:
                self.simulation = simulation
                self.laboratory = laboratory
                self.scene = scene
                self.error = None
                self.stopping.clear()
                self.worker = threading.Thread(target=self.run, name=scene, daemon=True)
                self.worker.start()
                return self.answer_locked()

    def stop(self) -> SimulationAnswer:
        """
        End the worker and wait for it; the simulation keeps its last state.

        :return: The session's state.
        """
        with self.lifecycle:
            self.halt()
            with self.lock:
                if self.simulation is not None:
                    self.simulation.release()
                return self.answer_locked()

    def halt(self) -> None:
        """
        End and join the worker, if one runs; the caller holds :attr:`lifecycle`.
        """
        self.stopping.set()
        worker = self.worker
        if worker is not None:
            worker.join()
        self.worker = None

    def running(self) -> bool:
        """
        :return: Whether a worker steps a simulation.
        """
        return (
            self.worker is not None
            and self.worker.is_alive()
            and not self.stopping.is_set()
        )

    def run(self) -> None:
        """
        Step the simulation as fast as wall-clock time passes, until told to stop.

        An error a step raises ends the worker and is reported as the session's failure;
        this thread is the boundary where it becomes the session's state.
        """
        previous = time.monotonic()
        owed = 0.0
        while not self.stopping.wait(WORKER_INTERVAL):
            now = time.monotonic()
            owed += min(now - previous, LONGEST_CATCH_UP)
            previous = now
            with self.lock:
                count = int(owed / self.simulation.timestep)
                if count == 0:
                    continue
                try:
                    self.simulation.step(count)
                except Exception as error:
                    self.error = f"{type(error).__name__}: {error}"
                    self.stopping.set()
                    return
                owed -= count * self.simulation.timestep

    # %% commands

    def command(self, action: Callable[[ContactSimulation], None]) -> SimulationAnswer:
        """
        Apply a command to the running simulation between two steps.

        :param action: What to do with the simulation.
        :return: The session's state afterwards.
        :raises SimulationNotRunning: When no simulation runs.
        """
        with self.lock:
            if not self.running():
                raise SimulationNotRunning()
            action(self.simulation)
            return self.answer_locked()

    def answer(self) -> SimulationAnswer:
        """
        :return: The session's state.
        """
        with self.lock:
            return self.answer_locked()

    def answer_locked(self) -> SimulationAnswer:
        """
        :return: The session's state; the caller holds :attr:`lock`.
        """
        if self.error is not None:
            state = SimulationState.FAILED
        elif self.running():
            state = SimulationState.RUNNING
        else:
            state = SimulationState.IDLE
        return SimulationAnswer(
            state=state,
            error=self.error,
            laboratory=None if self.laboratory is None else self.laboratory.name,
            scene=self.scene,
            snapshot=None if self.simulation is None else self.simulation.snapshot(),
        )
