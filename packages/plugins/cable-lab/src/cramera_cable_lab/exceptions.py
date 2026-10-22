"""
Errors of the cable lab plugin; each becomes the error answer of the request that raised
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

from typing_extensions import List

from cramera.exceptions import ViewerError

# %% availability


@dataclass
class CableLabLibrariesMissing(ViewerError):
    """
    The libraries the cable simulation needs are not installed.
    """

    modules: List[str]
    """
    The modules that cannot be found.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.SERVICE_UNAVAILABLE

    def message(self) -> str:
        return (
            f"The cable lab needs {', '.join(self.modules)}, which this Python "
            f"environment does not have. Run the viewer from a CRAM workspace with "
            f"MuJoCo."
        )


# %% building


@dataclass
class CableNotBuilt(ViewerError):
    """
    MuJoCo could not build the cable into the lab's scene.
    """

    reason: str
    """
    What MuJoCo reported.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"MuJoCo could not build the cable: {self.reason}"


@dataclass
class CablePrefixTaken(ViewerError):
    """
    A cable whose point names are taken in its world already.
    """

    prefix: str
    """
    The prefix of the cable's point names.
    """

    def message(self) -> str:
        return f"The world already holds cable points named {self.prefix!r}."


# %% session


@dataclass
class CableLabInactive(ViewerError):
    """
    A command or reset before a cable was built and started.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return "Build and start a cable first."


@dataclass
class GripperTargetOutsideWorkspace(ViewerError):
    """
    A gripper target outside the lab's workspace.
    """

    def message(self) -> str:
        return "The gripper target is outside the cable lab's workspace."


@dataclass
class SteppingWhileRunning(ViewerError):
    """
    A deterministic step while the background simulation runs.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return "Stop the background simulation before stepping it by hand."


@dataclass
class StoppedSimulation(ViewerError):
    """
    A start of a simulation that was stopped for good.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return "A stopped cable simulation cannot start again; build a new cable."


@dataclass
class SimulationNotAdvancing(ViewerError):
    """
    A started simulation whose thread took no step in time.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return "The cable simulation started but did not advance."
