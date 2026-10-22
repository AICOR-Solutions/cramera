"""
Requests and configurations the scene builder refuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path

from typing_extensions import List

from cramera.exceptions import ViewerError

# %% base


@dataclass
class SceneBuilderError(ViewerError):
    """
    A request or configuration the scene builder cannot serve.
    """


# %% resources


@dataclass
class InvalidResourceIdentifier(SceneBuilderError):
    """
    A resource identifier that is not a path ``<root>/<path>`` of plain segments.
    """

    identifier: str
    """
    The identifier that was given.
    """

    def message(self) -> str:
        return (
            f"{self.identifier!r} is not a resource identifier: use '<root>/<path>' "
            f"without empty, hidden, '.' or '..' segments."
        )


@dataclass
class UnknownResourceRoot(SceneBuilderError):
    """
    A resource identifier whose root the library does not have.
    """

    root: str
    """
    The root that was named.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"The resource library has no root named {self.root!r}."


@dataclass
class InvalidRootName(SceneBuilderError):
    """
    A configured library directory whose name cannot be a resource root.
    """

    directory: Path
    """
    The configured directory.
    """

    def message(self) -> str:
        return (
            f"{str(self.directory)!r} cannot be a resource root: its name must be 1 to "
            f"64 letters, digits, '_' or '-', and differ from every other root."
        )


@dataclass
class UnservedResourceFile(SceneBuilderError):
    """
    A file of the library that is neither a model, a model's dependency nor a notice.
    """

    identifier: str
    """
    The identifier of the file.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.FORBIDDEN

    def message(self) -> str:
        return f"{self.identifier!r} is not a model, a model's file or a notice."


@dataclass
class NotAModel(SceneBuilderError):
    """
    A draft instance whose resource is not a model or a point cloud.
    """

    identifier: str
    """
    The identifier of the resource.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.identifier!r} is not a model or a point cloud that can be placed."
        )


@dataclass
class NotAPointCloud(SceneBuilderError):
    """
    A request for the display sample of a resource that is not a point cloud.
    """

    identifier: str
    """
    The identifier of the resource.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"{self.identifier!r} is not a point cloud."


@dataclass
class OutsideLibrary(SceneBuilderError):
    """
    A file a model refers to that lies in none of the library's roots.
    """

    path: Path
    """
    The file.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return "A model refers to a file outside the resource library."


@dataclass
class ExternalDependency(SceneBuilderError):
    """
    A model that refers to a file by an absolute path or a web address.
    """

    identifier: str
    """
    The identifier of the model.
    """

    reference: str
    """
    The reference the model holds.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.identifier!r} refers to {self.reference!r}, which is not a file "
            f"of the resource library."
        )


@dataclass
class MissingDependency(SceneBuilderError):
    """
    A model that refers to a file the library does not hold.
    """

    identifier: str
    """
    The identifier of the model.
    """

    reference: str
    """
    The reference the model holds.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"{self.identifier!r} refers to {self.reference!r}, which is missing."


@dataclass
class DocumentTypeDeclaration(SceneBuilderError):
    """
    A URDF with a document type or entity declaration, which the builder does not
    expand.
    """

    identifier: str
    """
    The identifier of the URDF.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"{self.identifier!r} declares a document type or entities."


@dataclass
class MalformedResourceDocument(SceneBuilderError):
    """
    A URDF or glTF file that cannot be parsed.
    """

    identifier: str
    """
    The identifier of the file.
    """

    reason: str
    """
    What the parser reported.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"{self.identifier!r} cannot be read: {self.reason}"


@dataclass
class UnusableOrientation(SceneBuilderError):
    """
    A recorded pose whose quaternion has no length.
    """

    quaternion: List[float]
    """
    The quaternion that was recorded, ``[x, y, z, w]``.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"The recorded orientation {self.quaternion} is no rotation."


# %% requests


@dataclass
class MalformedRequestBody(SceneBuilderError):
    """
    A request body that is not JSON text.
    """

    reason: str
    """
    What the decoder reported.
    """

    def message(self) -> str:
        return f"The request body is not JSON: {self.reason}"


@dataclass
class ContentTooLarge(SceneBuilderError):
    """
    A request body or a point cloud file larger than the builder reads.
    """

    size: int
    """
    The content's size in bytes.
    """

    limit: int
    """
    The largest size read, in bytes.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    def message(self) -> str:
        return f"The content has {self.size} bytes; at most {self.limit} are read."


@dataclass
class InvalidTemplateRequest(SceneBuilderError):
    """
    A template request that does not name exactly one scene.
    """

    query: str
    """
    The request's query.
    """

    def message(self) -> str:
        return f"Name exactly one scene to start a draft from, not {self.query!r}."


# %% drafts


@dataclass
class InvalidDraftIdentifier(SceneBuilderError):
    """
    A draft or instance identity that is not 1 to 96 letters, digits, ``_`` or ``-``.
    """

    identifier: str
    """
    The identity that was given.
    """

    def message(self) -> str:
        return (
            f"{self.identifier!r} is not an identity: use letters, digits, '_' and "
            f"'-' only."
        )


@dataclass
class UnknownDraft(SceneBuilderError):
    """
    A draft identity no saved draft has.
    """

    identifier: str
    """
    The identity that was requested.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No saved draft is named {self.identifier!r}."


@dataclass
class InvalidDraftText(SceneBuilderError):
    """
    A name or reference of a draft that is empty, too long or holds control characters.
    """

    location: str
    """
    Where the text sits in the draft.
    """

    text: str
    """
    The text that was given.
    """

    def message(self) -> str:
        return (
            f"{self.location} must be non-empty text without control characters "
            f"within the length limit, not {self.text!r}."
        )


@dataclass
class ValueOutOfRange(SceneBuilderError):
    """
    A number of a draft outside the range the builder allows.
    """

    location: str
    """
    Where the number sits in the draft.
    """

    value: float
    """
    The number that was given.
    """

    minimum: float
    """
    The smallest allowed value.
    """

    maximum: float
    """
    The largest allowed value.
    """

    def message(self) -> str:
        return (
            f"{self.location} is {self.value}; it must be finite and between "
            f"{self.minimum} and {self.maximum}."
        )


@dataclass
class NonPositiveScale(SceneBuilderError):
    """
    A scale factor of a draft that is zero or negative.
    """

    location: str
    """
    Where the factor sits in the draft.
    """

    value: float
    """
    The factor that was given.
    """

    def message(self) -> str:
        return f"{self.location} is {self.value}; scale factors must be positive."


@dataclass
class TooManyEntries(SceneBuilderError):
    """
    A list or mapping of a draft with more entries than the builder allows.
    """

    location: str
    """
    Where the entries sit in the draft.
    """

    count: int
    """
    How many entries were given.
    """

    limit: int
    """
    How many entries are allowed.
    """

    def message(self) -> str:
        return f"{self.location} has {self.count} entries; at most {self.limit} fit."


@dataclass
class DuplicateInstance(SceneBuilderError):
    """
    Two instances of a draft with the same identity.
    """

    identifier: str
    """
    The identity both instances have.
    """

    def message(self) -> str:
        return f"Two instances are named {self.identifier!r}."


@dataclass
class DraftTooLarge(SceneBuilderError):
    """
    A draft whose JSON is larger than the builder keeps.
    """

    size: int
    """
    The size of the draft's JSON in bytes.
    """

    limit: int
    """
    The largest size kept, in bytes.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    def message(self) -> str:
        return (
            f"The draft has {self.size} bytes of JSON; at most {self.limit} are kept."
        )


# %% point clouds


@dataclass
class UnsupportedPointCloudFormat(SceneBuilderError):
    """
    An upload to a format the builder does not read.
    """

    given: str
    """
    The format the upload named.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"{self.given!r} is not a point cloud format: upload PLY or PCD."


class PointCloudProblem(StrEnum):
    """
    Why a point cloud file is refused.
    """

    EMPTY = "The file is empty."
    HEADER_INCOMPLETE = "The header is missing, truncated or too large."
    HEADER_NOT_TEXT = "Header lines must be short ASCII text."
    NOT_PLY = "A PLY file starts with the line 'ply'."
    UNSUPPORTED_ENCODING = "The records are stored in an encoding the builder does not read; PCD binary_compressed is one."
    INVALID_DECLARATION = "A header line is malformed or repeated."
    UNKNOWN_DECLARATION = "A header line declares something the builder does not know."
    NOT_VERTICES = (
        "Only vertex clouds are read; mesh faces and other elements must be empty."
    )
    LIST_PROPERTY = "Vertex properties must be scalars, not lists."
    UNKNOWN_SCALAR_TYPE = "A field has a scalar type the builder does not know."
    UNSUPPORTED_VERSION = "Only PCD version 0.7 is read."
    INVALID_COUNT = "A count in the header is not a number within the limits."
    DIMENSION_MISMATCH = "The cloud's width and height do not give its point count."
    INVALID_FIELDS = "The fields must be distinct, named plainly, bounded in number and described consistently."
    MISSING_COORDINATES = "A cloud needs scalar x, y and z fields."
    INVALID_VIEWPOINT = "A PCD viewpoint needs seven finite numbers."
    INVALID_COLOR = "A packed colour needs one 32-bit scalar."
    INVALID_NUMBER = "A record holds a value that is not a number of its field's type."
    RECORD_TOO_LONG = "A record line is too long."
    RECORD_SHAPE = "A record does not have the fields the header declares."
    TRUNCATED = "The records are fewer or more than the header declares."
    COORDINATE_OUT_OF_RANGE = (
        "A coordinate is infinite or beyond the range of 32-bit floats."
    )
    NO_FINITE_POINTS = "No point has three finite coordinates."


@dataclass
class MalformedPointCloud(SceneBuilderError):
    """
    A point cloud file the builder does not read.
    """

    problem: PointCloudProblem
    """
    Why the file is refused.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"The point cloud cannot be read: {self.problem.value}"


@dataclass
class TooManyPoints(SceneBuilderError):
    """
    A point cloud that declares more points than the builder reads.
    """

    count: int
    """
    How many points the file declares.
    """

    limit: int
    """
    How many points the builder reads at most.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    def message(self) -> str:
        return f"The point cloud declares {self.count} points; at most {self.limit} are read."


@dataclass
class UnsafeStoragePath(SceneBuilderError):
    """
    A storage location that is a symbolic link, which could redirect a write.
    """

    path: Path
    """
    The location.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return "A storage location of the scene builder is a symbolic link."


@dataclass
class StoredContentMismatch(SceneBuilderError):
    """
    A stored point cloud whose content differs from the content its name was made from.
    """

    path: Path
    """
    The stored file.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return "A stored point cloud does not match its content's name."


@dataclass
class UnreadableDraft(SceneBuilderError):
    """
    A saved draft whose file is not a readable draft.
    """

    identifier: str
    """
    The draft's identity.
    """

    reason: str
    """
    What reading reported.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return f"The saved draft {self.identifier!r} cannot be read: {self.reason}"
