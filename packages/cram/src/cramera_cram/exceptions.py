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


# %% live


@dataclass
class TeleoperationUnavailable(Conflict):
    """
    Hand control requested while no robot is selected or a plan moves the robot.
    """

    reason: str
    """
    Why hand control is unavailable.
    """

    def message(self) -> str:
        return f"Hand control is unavailable: {self.reason}"


@dataclass
class TeleoperationStillRunning(Conflict):
    """
    A hand-control driver that did not stop within its time budget.
    """

    def message(self) -> str:
        return "The previous hand control has not stopped yet."


@dataclass
class InvalidConstraint(CramPublisherError):
    """
    A constraint whose monitor parameters cannot be read.
    """

    parameter: str
    """
    The parameter that cannot be read.
    """

    expected: str
    """
    What the parameter must be.
    """

    def message(self) -> str:
        return f"The constraint parameter {self.parameter!r} must be {self.expected}."


@dataclass
class UnknownPlanNode(CramPublisherError):
    """
    A plan node identity the executing plan does not hold.
    """

    identifier: str
    """
    The identity that was given.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"The plan has no node {self.identifier!r}."


@dataclass
class MarkersUnavailable(Conflict):
    """
    A marker topic change in a process that reads no markers from ROS.
    """

    def message(self) -> str:
        return "This process reads no markers from ROS."


@dataclass
class NoRecording(Conflict):
    """
    A recording action while no recording is in the state the action needs.
    """

    needed: str
    """
    The recording state the action needs.
    """

    def message(self) -> str:
        return f"There is no {self.needed} recording."


@dataclass
class EmptyRecording(Conflict):
    """
    A recording without frames that was to be written as a bundle.
    """

    def message(self) -> str:
        return "The recording has no frames."


@dataclass
class InvalidFrameRange(CramPublisherError):
    """
    A frame range that runs backwards or past the recorded frames.
    """

    first: int
    """
    The first frame asked for.
    """

    last: int
    """
    The last frame asked for.
    """

    frame_count: int
    """
    How many frames the recording holds.
    """

    def message(self) -> str:
        return (
            f"The frames {self.first} to {self.last} are not within the "
            f"{self.frame_count} recorded frames."
        )


@dataclass
class SceneNameTaken(Conflict):
    """
    A save under a name a scenes directory already holds.
    """

    name: str
    """
    The name asked for.
    """

    def message(self) -> str:
        return f"A scene named {self.name!r} already exists."


@dataclass
class SharedScenesUnavailable(Conflict):
    """
    A save to the shared scenes directory while none is configured.
    """

    def message(self) -> str:
        return "No shared scenes directory is configured."


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


# %% scenes


@dataclass
class SceneWorldError(ViewerError):
    """
    A scene bundle or a robot configuration a world cannot be built from.
    """


@dataclass
class BundleNotFound(SceneWorldError):
    """
    A directory that holds no scene bundle.
    """

    directory: Path
    """
    The directory that was given.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"{str(self.directory)!r} holds no scene.json."


@dataclass
class UnknownPrimLink(SceneWorldError):
    """
    An annotated prim whose link the bundle's environment does not hold.
    """

    prim: str
    """
    The USD path of the prim.
    """

    link: str
    """
    The link the prim names.
    """

    def message(self) -> str:
        return f"The prim {self.prim!r} names the missing link {self.link!r}."


@dataclass
class InvalidRobotPlacement(SceneWorldError):
    """
    A robot configuration that cannot name its robot unambiguously.
    """

    reason: str
    """
    What is wrong with the configuration.
    """

    def message(self) -> str:
        return self.reason


@dataclass
class RobotPlacementUnavailable(SceneWorldError):
    """
    A configured robot that does not resolve to exactly one robot of a world.
    """

    namespace: str
    """
    The namespace of the configured robot.
    """

    matches: int
    """
    How many robots of the world carry it.
    """

    def message(self) -> str:
        return (
            f"The robot namespace {self.namespace!r} matches {self.matches} robots; "
            f"expected one."
        )


@dataclass
class MissingParameter(CramPublisherError):
    """
    A request without a query parameter its route needs.
    """

    name: str
    """
    The missing parameter.
    """

    def message(self) -> str:
        return f"The request needs the query parameter {self.name!r}."


@dataclass
class InvalidParameter(CramPublisherError):
    """
    A query parameter whose value its route does not accept.
    """

    name: str
    """
    The parameter.
    """

    value: str
    """
    The value given.
    """

    def message(self) -> str:
        return f"{self.value!r} is no valid value of the parameter {self.name!r}."


@dataclass
class MalformedBody(CramPublisherError):
    """
    A request body that is not JSON.
    """

    reason: str
    """
    Why it cannot be read.
    """

    def message(self) -> str:
        return f"The request body is no JSON document: {self.reason}"
