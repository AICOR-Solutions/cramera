"""
Errors of the workshop plugin; each becomes the error answer of the request that raised
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path

from typing_extensions import List

from cramera.exceptions import ViewerError

# %% bundle


@dataclass
class NotAWorkshopBundle(ViewerError):
    """
    A bundle whose scene description names no workshop or no asset rights.
    """

    directory: Path
    """
    The bundle directory.
    """

    def message(self) -> str:
        return f"The bundle {self.directory} describes no workshop and its rights."


@dataclass
class UnsupportedCollisionShape(ViewerError):
    """
    A URDF collision whose shape the contact world cannot build.
    """

    description: Path
    """
    The URDF file.
    """

    shape: str
    """
    The shape's element name.
    """

    def message(self) -> str:
        return (
            f"{self.description.name} has a {self.shape} collision; the workshop "
            f"simulates boxes, cylinders and spheres."
        )


# %% physics availability


@dataclass
class WorkshopPhysicsMissing(ViewerError):
    """
    The libraries the contact world needs are not installed.
    """

    modules: List[str]
    """
    The modules that cannot be found.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.SERVICE_UNAVAILABLE

    def message(self) -> str:
        return (
            f"The workshop's contact world needs {', '.join(self.modules)}, which this "
            f"Python environment does not have. Install cramera-workshop[physics]."
        )


# %% session


class InactiveReason(StrEnum):
    """
    Why the workshop does not take a command.
    """

    NOT_STARTED = "Start the workshop physics first."
    """
    The command needs time to pass, and it does not.
    """

    CLOSED = "The workshop has been shut down."
    """
    The viewer stopped serving.
    """

    FAILED = "Reset the workshop after its simulation failed."
    """
    The solver lost a valid state.
    """


@dataclass
class WorkshopInactive(ViewerError):
    """
    A command the workshop cannot take in its current state.
    """

    reason: InactiveReason
    """
    Why.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return self.reason.value


# %% commands


@dataclass
class UnknownWorkshopBody(ViewerError):
    """
    A command naming a body that does not move freely in the workshop.
    """

    key: str
    """
    The object key that was given.
    """

    def message(self) -> str:
        return f"{self.key!r} is no movable body of the workshop."


@dataclass
class UnknownDrawer(ViewerError):
    """
    A drawer command naming a joint the workshop has no drawer for.
    """

    joint: str
    """
    The joint that was given.
    """

    def message(self) -> str:
        return f"{self.joint!r} is no drawer joint of the workshop."


@dataclass
class DrawerTargetOutOfRange(ViewerError):
    """
    A drawer target beyond the drawer's travel.
    """

    joint: str
    """
    The drawer joint.
    """

    target: float
    """
    The requested position, in metres.
    """

    lower: float
    """
    The closed position, in metres.
    """

    upper: float
    """
    The fully open position, in metres.
    """

    def message(self) -> str:
        return (
            f"{self.joint} travels from {self.lower} m to {self.upper} m; "
            f"{self.target} m is outside."
        )


@dataclass
class TargetOutsideWorkspace(ViewerError):
    """
    A spring target outside the volume bodies may be moved in.
    """

    def message(self) -> str:
        return "The grasp target is outside the workshop."


@dataclass
class NothingHeld(ViewerError):
    """
    A move while the spring holds no body, or holds another body than the one named.
    """

    key: str
    """
    The object key the move named.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return f"{self.key!r} is not held; grab it first."


@dataclass
class DriverNotEngaged(ViewerError):
    """
    A drive while the held screwdriver's blade is not engaged in a seated screw.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return "Hold the driver with its blade in a seated screw's slot first."


@dataclass
class InvalidStepDuration(ViewerError):
    """
    A simulation step that is negative, not finite or too long to take at once.
    """

    duration: float
    """
    The requested duration, in seconds.
    """

    def message(self) -> str:
        return f"Cannot advance the workshop by {self.duration} s at once."


# %% solver


@dataclass
class WorkshopSimulationFailure(ViewerError):
    """
    The contact solver lost a finite, advancing state.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return "The workshop's contact solver stopped with an invalid state."
