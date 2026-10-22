"""
A cable simulation that stands in for MuJoCo and CRAM, so the session and the routes can
be tested without either.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from typing_extensions import List

from cramera_cable_lab.exceptions import (
    CableNotBuilt,
    GripperTargetOutsideWorkspace,
    StoppedSimulation,
)
from cramera_cable_lab.session import GRIPPER_WORKSPACE, CableSimulation
from cramera_protocol.cable_lab import (
    CableConfiguration,
    CableLabState,
    GripperAction,
    GripperCommand,
    SimulationLifecycle,
)

REFUSED_SEGMENT_COUNT = 50
"""
The element count the stand-in factory refuses to build, as MuJoCo would a cable it
cannot compile.
"""


@dataclass
class RecordingSimulation(CableSimulation):
    """
    Records the commands it receives and whether it runs.
    """

    configuration: CableConfiguration
    """
    The cable it stands for.
    """

    commands: List[GripperCommand] = field(default_factory=list)
    """
    The commands it received, in order.
    """

    is_running: bool = False
    """
    Whether it runs.
    """

    stopped: bool = False
    """
    Whether it was stopped for good.
    """

    def running(self) -> bool:
        return self.is_running

    def start(self) -> None:
        if self.stopped:
            raise StoppedSimulation()
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False
        self.stopped = True

    def command(self, command: GripperCommand) -> None:
        if command.action is GripperAction.MOVE and not GRIPPER_WORKSPACE.contains(
            command.position
        ):
            raise GripperTargetOutsideWorkspace()
        self.commands.append(command)

    def measure(self) -> CableLabState:
        return CableLabState(
            lifecycle=SimulationLifecycle.IDLE,
            simulation_time=float(len(self.commands)),
            configuration=self.configuration,
        )


@dataclass
class RecordingFactory:
    """
    Builds stand-in simulations and keeps them.
    """

    built: List[RecordingSimulation] = field(default_factory=list)
    """
    Every simulation built, in order.
    """

    def build(self, configuration: CableConfiguration) -> RecordingSimulation:
        """
        :param configuration: The cable.
        :return: Its stand-in simulation.
        :raises CableNotBuilt: For a cable of :data:`REFUSED_SEGMENT_COUNT` elements.
        """
        if configuration.segment_count == REFUSED_SEGMENT_COUNT:
            raise CableNotBuilt("the stand-in refuses this cable")
        simulation = RecordingSimulation(configuration)
        self.built.append(simulation)
        return simulation
