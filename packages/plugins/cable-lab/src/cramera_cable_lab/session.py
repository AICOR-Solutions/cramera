"""
The cable lab session: at most one cable simulation, replaced when a new cable is built,
with every lifecycle change under one lock.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace

from typing_extensions import Callable, Optional, Sequence

from cramera_protocol.cable_lab import (
    CableConfiguration,
    CableLabState,
    GripperCommand,
    SimulationLifecycle,
)
from cramera_protocol.geometry import Vector3
from cramera_cable_lab.exceptions import CableLabInactive

UNEXPECTED_STOP = "The cable simulation stopped by itself."
"""
The error a session reports when its simulation ended without being stopped.
"""

# %% workspace


@dataclass(frozen=True)
class GripperWorkspace:
    """
    The box the gripper's target stays in, in world coordinates.
    """

    minimum: Sequence[float] = (-1.0, -1.0, 0.02)
    """
    The smallest x, y and z, in metres.
    """

    maximum: Sequence[float] = (1.0, 1.0, 1.5)
    """
    The largest x, y and z, in metres.
    """

    def contains(self, position: Vector3) -> bool:
        """
        :param position: A target.
        :return: Whether it lies in the workspace.
        """
        return all(
            low <= value <= high
            for value, low, high in zip(position.to_json(), self.minimum, self.maximum)
        )

    def clamped_height(self, height: float) -> float:
        """
        :param height: A target height.
        :return: The height moved into the workspace.
        """
        return min(max(height, self.minimum[2]), self.maximum[2])


GRIPPER_WORKSPACE = GripperWorkspace()
"""
The workspace of the cable lab's gripper.
"""


# %% simulation


class CableSimulation(ABC):
    """
    One built cable with its gripper, simulated in the background between :meth:`start`
    and :meth:`stop`; safe to call from several threads.
    """

    @abstractmethod
    def running(self) -> bool:
        """
        :return: Whether the background simulation advances.
        """

    @abstractmethod
    def start(self) -> None:
        """
        Start the background simulation.

        :raises StoppedSimulation: When the simulation was stopped before.
        """

    @abstractmethod
    def stop(self) -> None:
        """
        Stop the background simulation for good and release what it holds.
        """

    @abstractmethod
    def command(self, command: GripperCommand) -> None:
        """
        Change the gripper's actuator targets; the cable moves only by contact.

        :param command: The command.
        :raises GripperTargetOutsideWorkspace: For a move outside the workspace.
        """

    @abstractmethod
    def measure(self) -> CableLabState:
        """
        :return: The measured cable, gripper and contacts; the session sets the
            lifecycle.
        """


SimulationFactory = Callable[[CableConfiguration], CableSimulation]
"""
Builds a cable simulation from a configuration.

:raises CableNotBuilt: When MuJoCo cannot build the cable.
"""


# %% session


@dataclass
class CableLabSession:
    """
    Owns the current cable simulation; building, resetting, commanding, stopping and
    reading hold :attr:`lock`.
    """

    factory: SimulationFactory
    """
    Builds a cable simulation.
    """

    simulation: Optional[CableSimulation] = field(default=None, init=False)
    """
    The current simulation, kept after it stopped so its last state stays readable.
    """

    configuration: Optional[CableConfiguration] = field(default=None, init=False)
    """
    The configuration the current simulation was built from.
    """

    expected_running: bool = field(default=False, init=False)
    """
    Whether the simulation should be running.
    """

    error: Optional[str] = field(default=None, init=False)
    """
    Why the simulation failed.
    """

    lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    """
    Serializes the lifecycle and the state reads.
    """

    def start(self, configuration: CableConfiguration) -> CableLabState:
        """
        Build a new cable and start it; the previous simulation is stopped once the new
        one is built.

        :param configuration: The cable to build.
        :return: The state of the new simulation.
        :raises CableNotBuilt: When MuJoCo cannot build the cable; the previous
            simulation keeps running then.
        """
        with self.lock:
            candidate = self.factory(configuration)
            self.halt()
            self.simulation = candidate
            self.configuration = configuration
            self.error = None
            candidate.start()
            self.expected_running = True
            return self.current_state()

    def reset(self) -> CableLabState:
        """
        Build the last cable again and start it from its initial pose.

        :return: The state of the new simulation.
        :raises CableLabInactive: When no cable was built yet.
        """
        with self.lock:
            if self.configuration is None:
                raise CableLabInactive()
            return self.start(self.configuration)

    def stop(self) -> CableLabState:
        """
        :return: The last state of the stopped simulation.
        """
        with self.lock:
            self.halt()
            self.error = None
            return self.current_state()

    def command(self, command: GripperCommand) -> CableLabState:
        """
        :param command: A gripper command.
        :return: The state after it.
        :raises CableLabInactive: When no simulation runs.
        """
        with self.lock:
            if self.simulation is None or not self.simulation.running():
                raise CableLabInactive()
            self.simulation.command(command)
            return self.current_state()

    def state(self) -> CableLabState:
        """
        :return: The lifecycle and the measured cable.
        """
        with self.lock:
            return self.current_state()

    def current_state(self) -> CableLabState:
        """
        :return: The lifecycle and the measured cable; call with the lock.
        """
        running = self.simulation is not None and self.simulation.running()
        if self.expected_running and not running:
            self.expected_running = False
            self.error = UNEXPECTED_STOP
        measured = (
            CableLabState(lifecycle=SimulationLifecycle.IDLE)
            if self.simulation is None
            else self.simulation.measure()
        )
        lifecycle = (
            SimulationLifecycle.FAILED
            if self.error is not None
            else SimulationLifecycle.RUNNING if running else SimulationLifecycle.IDLE
        )
        return replace(measured, lifecycle=lifecycle, error=self.error)

    def halt(self) -> None:
        """
        Stop the current simulation; call with the lock.
        """
        self.expected_running = False
        if self.simulation is not None:
            self.simulation.stop()

    def close(self) -> None:
        """
        Stop the simulation, as the viewer stops serving.
        """
        with self.lock:
            self.halt()
