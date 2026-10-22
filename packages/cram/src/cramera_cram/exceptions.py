"""
Errors cramera-cram raises.

Errors a request can cause derive from :class:`~cramera.exceptions.ViewerError`, so the
HTTP boundary answers them with their own status.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from typing_extensions import List

from cramera.exceptions import ViewerError

# %% base


@dataclass
class CramPublisherError(ViewerError):
    """
    A request or a world the live publisher cannot serve.
    """


@dataclass
class Conflict(CramPublisherError):
    """
    A request that is valid but cannot be carried out in the publisher's current state.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT


# %% world


@dataclass
class NoWorldAttached(Conflict):
    """
    A request that needs a world before one was attached.
    """

    def message(self) -> str:
        return "No world is attached to the live publisher yet."


@dataclass
class UnknownRobot(CramPublisherError):
    """
    A robot identity no robot of the world carries.
    """

    identifier: str
    """
    The identity that was asked for.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"The world has no robot with the identity {self.identifier!r}."


@dataclass
class UnknownArm(CramPublisherError):
    """
    An arm name no arm of the selected robot carries.
    """

    name: str
    """
    The name that was asked for.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"The selected robot has no arm named {self.name!r}."


@dataclass
class RobotSelectionBusy(Conflict):
    """
    A robot selection while a plan is executing with the selected robot.
    """

    def message(self) -> str:
        return "Wait for the running plan to finish before selecting another robot."


@dataclass
class UnknownObject(CramPublisherError):
    """
    An object key no published object carries.
    """

    key: str
    """
    The key that was asked for.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No published object has the key {self.key!r}."


@dataclass
class ObjectNotMovable(Conflict):
    """
    A move of an object that is not held by a free connection.
    """

    key: str
    """
    The key of the object.
    """

    connection_type: str
    """
    The class name of the connection holding it.
    """

    def message(self) -> str:
        return (
            f"The object {self.key!r} is held by a {self.connection_type}; only "
            f"objects with six degrees of freedom can be moved."
        )


@dataclass
class UnknownJoint(CramPublisherError):
    """
    A joint name no movable connection of the world carries.
    """

    joint: str
    """
    The name that was asked for.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"The world has no movable joint named {self.joint!r}."


@dataclass
class UnknownBody(CramPublisherError):
    """
    A body name a constraint or a placement names but the world does not hold.
    """

    name: str
    """
    The name that was asked for.
    """

    def message(self) -> str:
        return f"The world has no body named {self.name!r}."


@dataclass
class AmbiguousBody(CramPublisherError):
    """
    A body name that several bodies of the world carry.
    """

    name: str
    """
    The name that was asked for.
    """

    candidates: List[str]
    """
    The full names of the bodies carrying it.
    """

    def message(self) -> str:
        return f"Several bodies are named {self.name!r}: {self.candidates}."


@dataclass
class UnknownMesh(CramPublisherError):
    """
    A mesh key the publisher does not serve.
    """

    key: str
    """
    The key that was asked for.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No mesh is served under the key {self.key!r}."


@dataclass
class MissingMeshFile(CramPublisherError):
    """
    A mesh shape whose file does not exist.
    """

    path: Path
    """
    The file the shape names.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return f"The mesh file {str(self.path)!r} does not exist."


@dataclass
class UnsupportedShape(CramPublisherError):
    """
    A shape whose geometry has no published form.
    """

    shape_type: str
    """
    The class name of the shape.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return f"Shapes of type {self.shape_type} cannot be published."


# %% export


@dataclass
class ExportError(ViewerError):
    """
    A world or a file that cannot be written into a scene bundle.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR


@dataclass
class UnrepresentableJointLimits(ExportError):
    """
    A bounded joint whose native degree of freedom lacks two finite position limits.
    """

    joint: str
    """
    The name of the connection.
    """

    def message(self) -> str:
        return f"The joint {self.joint!r} needs two finite position limits for a URDF."


@dataclass
class PathOutsideBundle(ExportError):
    """
    A file reference or destination that would leave the bundle directory.
    """

    path: str
    """
    The reference or destination.
    """

    def message(self) -> str:
        return f"{self.path!r} leads out of the bundle directory."


@dataclass
class UrdfSourceNotFound(ExportError):
    """
    A URDF or xacro source that resolves to no file.
    """

    source: str
    """
    The source as it was given.
    """

    def message(self) -> str:
        return f"The URDF source {self.source!r} does not exist."


