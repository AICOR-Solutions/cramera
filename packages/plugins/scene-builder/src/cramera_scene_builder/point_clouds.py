"""
Reading point cloud files, PLY vertex clouds and PCD clouds, within bounds: every record
is checked before a file is kept, and the browser receives a display sample in the
file's own coordinates.
"""

from __future__ import annotations

import io
import math
import re
import struct
import sys
from abc import ABC, abstractmethod
from array import array
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from types import MappingProxyType

from typing_extensions import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from cramera_protocol.scene_builder import (
    PointCloudEncoding,
    PointCloudFormat,
    PointCloudMetadata,
    SceneBuilderLimits,
)
from cramera_scene_builder.exceptions import (
    MalformedPointCloud,
    PointCloudProblem,
    TooManyPoints,
)

MAXIMUM_HEADER_BYTES = 64 * 1024
"""
How long a header is at most, in bytes.
"""

MAXIMUM_HEADER_LINE_BYTES = 8192
"""
How long one header line is at most, in bytes.
"""

MAXIMUM_RECORD_BYTES = 64 * 1024
"""
How long one ASCII record line is at most, in bytes.
"""

MAXIMUM_FIELDS = 64
"""
How many named fields a point has at most.
"""

MAXIMUM_COMPONENTS = 1024
"""
How many scalars a point has at most, counting every component of every field.
"""

MAXIMUM_NUMBER_LENGTH = 128
"""
How many characters one number of an ASCII record has at most.
"""

MAXIMUM_SCALAR_SIZE = 8
"""
The largest scalar of a PCD field, in bytes.
"""

FLOAT32_MAXIMUM = float.fromhex("0x1.fffffep+127")
"""
The largest finite 32-bit float; the browser keeps positions in 32-bit buffers.
"""

COLOR_CHANNEL_MAXIMUM = 255
"""
The value of a full integer colour channel.
"""

BITS_PER_BYTE = 8
"""
The number of bits in a byte.
"""

UNSIGNED_32_BIT_MASK = 0xFFFFFFFF
"""
Keeps the lowest 32 bits of an integer.
"""

PACKED_CHANNEL_SHIFTS = (16, 8, 0)
"""
How far the red, green and blue bytes of a packed colour are shifted.
"""

PACKED_COLOR_SIZE = 4
"""
The size of a packed colour in bytes.
"""

FIELD_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
"""
The names a field may have.
"""

COUNT = re.compile(r"\d{1,10}")
"""
How a count is written in a header.
"""

FLOATING_NUMBER = re.compile(
    rb"[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|nan|inf|infinity)",
    re.IGNORECASE,
)
"""
How a floating-point value is written in an ASCII record.
"""

INTEGER_NUMBER = re.compile(rb"[+-]?\d+")
"""
How an integer value is written in an ASCII record.
"""

# %% scalars


class ScalarType(Enum):
    """
    The binary scalars point fields are stored as, by their ``struct`` code.
    """

    SIGNED_BYTE = "b"
    """
    An 8-bit signed integer.
    """

    UNSIGNED_BYTE = "B"
    """
    An 8-bit unsigned integer.
    """

    SIGNED_SHORT = "h"
    """
    A 16-bit signed integer.
    """

    UNSIGNED_SHORT = "H"
    """
    A 16-bit unsigned integer.
    """

    SIGNED_INTEGER = "i"
    """
    A 32-bit signed integer.
    """

    UNSIGNED_INTEGER = "I"
    """
    A 32-bit unsigned integer.
    """

    FLOAT = "f"
    """
    A 32-bit float.
    """

    DOUBLE = "d"
    """
    A 64-bit float.
    """

    def size(self) -> int:
        """
        :return: The scalar's size in bytes, without alignment.
        """
        return struct.calcsize(f"<{self.value}")

    def is_floating(self) -> bool:
        """
        :return: Whether the scalar is a floating-point number.
        """
        return self in (ScalarType.FLOAT, ScalarType.DOUBLE)

    def is_signed(self) -> bool:
        """
        :return: Whether an integer scalar holds negative values.
        """
        return self.value.islower()

    def bits_of(self, value: float) -> int:
        """
        :param value: A 32-bit value of this scalar.
        :return: Its bits as an unsigned 32-bit integer.
        """
        if self is ScalarType.FLOAT:
            return struct.unpack("<I", struct.pack("<f", value))[0]
        return int(value) & UNSIGNED_32_BIT_MASK

    def read(self, token: bytes) -> float:
        """
        :param token: One number of an ASCII record.
        :return: Its value.
        :raises MalformedPointCloud: When the token is no number of this type.
        """
        if len(token) > MAXIMUM_NUMBER_LENGTH:
            raise MalformedPointCloud(PointCloudProblem.INVALID_NUMBER)
        if self.is_floating():
            return self.read_floating(token)
        if INTEGER_NUMBER.fullmatch(token) is None:
            raise MalformedPointCloud(PointCloudProblem.INVALID_NUMBER)
        value = int(token)
        bits = self.size() * BITS_PER_BYTE
        minimum = -(1 << (bits - 1)) if self.is_signed() else 0
        maximum = (1 << (bits - 1 if self.is_signed() else bits)) - 1
        if not minimum <= value <= maximum:
            raise MalformedPointCloud(PointCloudProblem.INVALID_NUMBER)
        return value

    def read_floating(self, token: bytes) -> float:
        """
        :param token: One floating-point number of an ASCII record.
        :return: Its value; NaN marks a missing measurement.
        :raises MalformedPointCloud: When the token is no number or exceeds a 32-bit
            float of a 32-bit field.
        """
        if FLOATING_NUMBER.fullmatch(token) is None:
            raise MalformedPointCloud(PointCloudProblem.INVALID_NUMBER)
        value = float(token)
        if self is ScalarType.FLOAT and math.isfinite(value):
            if abs(value) > FLOAT32_MAXIMUM:
                raise MalformedPointCloud(PointCloudProblem.INVALID_NUMBER)
        return value


PLY_SCALAR_TYPES: Mapping[str, ScalarType] = MappingProxyType(
    {
        "char": ScalarType.SIGNED_BYTE,
        "int8": ScalarType.SIGNED_BYTE,
        "uchar": ScalarType.UNSIGNED_BYTE,
        "uint8": ScalarType.UNSIGNED_BYTE,
        "short": ScalarType.SIGNED_SHORT,
        "int16": ScalarType.SIGNED_SHORT,
        "ushort": ScalarType.UNSIGNED_SHORT,
        "uint16": ScalarType.UNSIGNED_SHORT,
        "int": ScalarType.SIGNED_INTEGER,
        "int32": ScalarType.SIGNED_INTEGER,
        "uint": ScalarType.UNSIGNED_INTEGER,
        "uint32": ScalarType.UNSIGNED_INTEGER,
        "float": ScalarType.FLOAT,
        "float32": ScalarType.FLOAT,
        "double": ScalarType.DOUBLE,
        "float64": ScalarType.DOUBLE,
    }
)
"""
The scalar of each PLY type name, with the sized aliases the PLY format allows.
"""


class PcdScalarCategory(StrEnum):
    """
    The kinds of scalars a PCD ``TYPE`` line names.
    """

    SIGNED = "I"
    """
    Signed integers.
    """

    UNSIGNED = "U"
    """
    Unsigned integers.
    """

    FLOATING = "F"
    """
    Floating-point numbers.
    """


PCD_SCALAR_TYPES: Mapping[Tuple[PcdScalarCategory, int], ScalarType] = MappingProxyType(
    {
        (PcdScalarCategory.SIGNED, 1): ScalarType.SIGNED_BYTE,
        (PcdScalarCategory.SIGNED, 2): ScalarType.SIGNED_SHORT,
        (PcdScalarCategory.SIGNED, 4): ScalarType.SIGNED_INTEGER,
        (PcdScalarCategory.UNSIGNED, 1): ScalarType.UNSIGNED_BYTE,
        (PcdScalarCategory.UNSIGNED, 2): ScalarType.UNSIGNED_SHORT,
        (PcdScalarCategory.UNSIGNED, 4): ScalarType.UNSIGNED_INTEGER,
        (PcdScalarCategory.FLOATING, 4): ScalarType.FLOAT,
        (PcdScalarCategory.FLOATING, 8): ScalarType.DOUBLE,
    }
)
"""
The scalar of each PCD type and size in bytes.
"""

# %% fields


class PointFieldName(StrEnum):
    """
    The field names the builder reads.
    """

    X = "x"
    """
    The x coordinate.
    """

    Y = "y"
    """
    The y coordinate.
    """

    Z = "z"
    """
    The z coordinate.
    """

    RGB = "rgb"
    """
    A colour packed into one 32-bit scalar.
    """

    RGBA = "rgba"
    """
    A colour with alpha packed into one 32-bit scalar.
    """

    RED = "red"
    """
    The red channel, as PLY names it.
    """

    GREEN = "green"
    """
    The green channel, as PLY names it.
    """

    BLUE = "blue"
    """
    The blue channel, as PLY names it.
    """

    R = "r"
    """
    The red channel, as short names spell it.
    """

    G = "g"
    """
    The green channel, as short names spell it.
    """

    B = "b"
    """
    The blue channel, as short names spell it.
    """


COORDINATE_FIELDS = (PointFieldName.X, PointFieldName.Y, PointFieldName.Z)
"""
The fields of a point's position, in order.
"""

PACKED_COLOR_FIELDS = (PointFieldName.RGB, PointFieldName.RGBA)
"""
The fields that hold a packed colour, the first present one wins.
"""

CHANNEL_FIELDS = (
    (PointFieldName.RED, PointFieldName.GREEN, PointFieldName.BLUE),
    (PointFieldName.R, PointFieldName.G, PointFieldName.B),
)
"""
The fields that hold separate colour channels, the first complete set wins.
"""


@dataclass(frozen=True)
class PointField:
    """
    One named field of every point record.
    """

    name: str
    """
    The field's name, such as ``x`` or ``rgb``.
    """

    scalar: ScalarType
    """
    How each of its components is stored.
    """

    count: int = 1
    """
    How many components follow each other.
    """


@dataclass(frozen=True)
class PointLayout:
    """
    The record layout a header declares, and where the records start.
    """

    encoding: PointCloudEncoding
    """
    How the records are stored.
    """

    point_count: int
    """
    How many records follow the header.
    """

    fields: Tuple[PointField, ...]
    """
    The fields of each record, in order.
    """

    offset: int
    """
    The byte offset of the first record.
    """

    def __post_init__(self) -> None:
        names = [point_field.name for point_field in self.fields]
        if (
            not self.fields
            or len(self.fields) > MAXIMUM_FIELDS
            or len(set(names)) != len(names)
            or any(FIELD_NAME.fullmatch(name) is None for name in names)
            or sum(point_field.count for point_field in self.fields)
            > MAXIMUM_COMPONENTS
        ):
            raise MalformedPointCloud(PointCloudProblem.INVALID_FIELDS)
        by_name = self.fields_by_name()
        if any(
            axis not in by_name or by_name[axis].count != 1
            for axis in COORDINATE_FIELDS
        ):
            raise MalformedPointCloud(PointCloudProblem.MISSING_COORDINATES)
        packed = self.packed_color()
        if packed is not None and (
            packed.count != 1 or packed.scalar.size() != PACKED_COLOR_SIZE
        ):
            raise MalformedPointCloud(PointCloudProblem.INVALID_COLOR)

    def fields_by_name(self) -> Dict[str, PointField]:
        """
        :return: The fields by name.
        """
        return {point_field.name: point_field for point_field in self.fields}

    def component_index(self, name: str) -> int:
        """
        :param name: A field's name.
        :return: The position of the field's first component in a record.
        """
        index = 0
        for point_field in self.fields:
            if point_field.name == name:
                return index
            index += point_field.count
        raise KeyError(name)

    def packed_color(self) -> Optional[PointField]:
        """
        :return: The field holding a packed colour, or None.
        """
        by_name = self.fields_by_name()
        return next(
            (by_name[name] for name in PACKED_COLOR_FIELDS if name in by_name), None
        )

    def channels(self) -> Optional[Tuple[PointField, ...]]:
        """
        :return: The fields holding the red, green and blue channels, or None.
        """
        by_name = self.fields_by_name()
        for names in CHANNEL_FIELDS:
            if all(name in by_name and by_name[name].count == 1 for name in names):
                return tuple(by_name[name] for name in names)
        return None

    def scalars(self, packed_as_bits: bool) -> List[ScalarType]:
        """
        :param packed_as_bits: Whether a packed colour is read as its unsigned bits
            rather than as its declared type.
        :return: The scalar of every component of a record, in order.
        """
        packed = self.packed_color()
        scalars: List[ScalarType] = []
        for point_field in self.fields:
            scalar = point_field.scalar
            if packed_as_bits and point_field is packed:
                scalar = ScalarType.UNSIGNED_INTEGER
            scalars.extend([scalar] * point_field.count)
        return scalars


# %% headers


@dataclass
class HeaderLines:
    """
    Reads the ASCII header line by line, keeping the offset of the next line.
    """

    body: bytes
    """
    The whole file.
    """

    offset: int = 0
    """
    The byte offset of the next line.
    """

    def read(self) -> str:
        """
        :return: The next line, without surrounding whitespace.
        :raises MalformedPointCloud: When the header ends early, is too long or holds
            other than short ASCII lines.
        """
        end = self.body.find(b"\n", self.offset, MAXIMUM_HEADER_BYTES)
        if end < 0:
            raise MalformedPointCloud(PointCloudProblem.HEADER_INCOMPLETE)
        line = self.body[self.offset : end]
        self.offset = end + 1
        if (
            len(line) > MAXIMUM_HEADER_LINE_BYTES
            or not line.isascii()
            or b"\x00" in line
        ):
            raise MalformedPointCloud(PointCloudProblem.HEADER_NOT_TEXT)
        return line.decode("ascii").strip()


@dataclass(frozen=True)
class HeaderCount:
    """
    Reads a count of a header within its bounds.
    """

    minimum: int
    """
    The smallest count allowed.
    """

    maximum: int
    """
    The largest count allowed.
    """

    def read(self, text: str) -> int:
        """
        :param text: The count as written in the header.
        :return: The count.
        :raises MalformedPointCloud: When the text is no count within the bounds.
        """
        if COUNT.fullmatch(text) is None:
            raise MalformedPointCloud(PointCloudProblem.INVALID_COUNT)
        count = int(text)
        if not self.minimum <= count <= self.maximum:
            raise MalformedPointCloud(PointCloudProblem.INVALID_COUNT)
        return count


@dataclass(frozen=True)
class PointCountCheck:
    """
    Refuses clouds that declare more points than the builder reads.
    """

    limit: int
    """
    How many points the builder reads at most.
    """

    def read(self, text: str, minimum: int) -> int:
        """
        :param text: A point count as written in the header.
        :param minimum: The smallest count allowed.
        :return: The count.
        :raises TooManyPoints: When the count exceeds :attr:`limit`.
        :raises MalformedPointCloud: When the text is no count or below the minimum.
        """
        count = HeaderCount(minimum, sys.maxsize).read(text)
        if count > self.limit:
            raise TooManyPoints(count, self.limit)
        return count


class HeaderReader(ABC):
    """
    Reads the header of one point cloud format into a record layout.
    """

    @abstractmethod
    def read(self, lines: HeaderLines, points: PointCountCheck) -> PointLayout:
        """
        :param lines: The header's lines, from the file's first byte.
        :param points: Bounds the number of points.
        :return: The record layout.
        :raises MalformedPointCloud: When the header is malformed or unsupported.
        """


class PlyKeyword(StrEnum):
    """
    The words of a PLY header.
    """

    MAGIC = "ply"
    """
    The first line of every PLY file.
    """

    FORMAT = "format"
    """
    Declares how the records are stored.
    """

    VERSION = "1.0"
    """
    The PLY version the builder reads.
    """

    ELEMENT = "element"
    """
    Declares an element and how many of it follow.
    """

    VERTEX = "vertex"
    """
    The element holding the points.
    """

    PROPERTY = "property"
    """
    Declares a field of the last element.
    """

    LIST = "list"
    """
    Marks a property holding a list, such as a face's vertices.
    """

    COMMENT = "comment"
    """
    A comment line.
    """

    OBJECT_INFORMATION = "obj_info"
    """
    A line of information about the object.
    """

    END_HEADER = "end_header"
    """
    The last line of the header.
    """


PLY_ENCODINGS = (
    PointCloudEncoding.ASCII,
    PointCloudEncoding.BINARY_LITTLE_ENDIAN,
    PointCloudEncoding.BINARY_BIG_ENDIAN,
)
"""
The encodings a PLY file may declare.
"""


@dataclass
class PlyHeaderReader(HeaderReader):
    """
    Reads PLY headers of vertex clouds; other elements must be empty.
    """

    encoding: Optional[PointCloudEncoding] = None
    """
    The declared encoding, once read.
    """

    point_count: Optional[int] = None
    """
    The number of vertices, once read.
    """

    element: Optional[str] = None
    """
    The element whose properties follow.
    """

    fields: List[PointField] = field(default_factory=list)
    """
    The vertex fields read so far.
    """

    def read(self, lines: HeaderLines, points: PointCountCheck) -> PointLayout:
        if lines.read() != PlyKeyword.MAGIC:
            raise MalformedPointCloud(PointCloudProblem.NOT_PLY)
        while True:
            words = lines.read().split()
            if not words:
                raise MalformedPointCloud(PointCloudProblem.INVALID_DECLARATION)
            if words[0] == PlyKeyword.END_HEADER:
                return self.layout(words, lines.offset)
            self.declare(words, points)

    def declare(self, words: List[str], points: PointCountCheck) -> None:
        """
        :param words: The words of one header line other than its last.
        :param points: Bounds the number of points.
        :raises MalformedPointCloud: When the line is malformed or unsupported.
        """
        keyword = words[0]
        if keyword in (PlyKeyword.COMMENT, PlyKeyword.OBJECT_INFORMATION):
            return
        if keyword == PlyKeyword.FORMAT:
            self.declare_format(words)
        elif keyword == PlyKeyword.ELEMENT:
            self.declare_element(words, points)
        elif keyword == PlyKeyword.PROPERTY:
            self.declare_property(words)
        else:
            raise MalformedPointCloud(PointCloudProblem.UNKNOWN_DECLARATION)

    def declare_format(self, words: List[str]) -> None:
        """
        :param words: The words of the ``format`` line.
        """
        if (
            self.encoding is not None
            or len(words) != 3
            or words[2] != PlyKeyword.VERSION
        ):
            raise MalformedPointCloud(PointCloudProblem.INVALID_DECLARATION)
        if words[1] not in PLY_ENCODINGS:
            raise MalformedPointCloud(PointCloudProblem.UNSUPPORTED_ENCODING)
        self.encoding = PointCloudEncoding(words[1])

    def declare_element(self, words: List[str], points: PointCountCheck) -> None:
        """
        :param words: The words of an ``element`` line.
        :param points: Bounds the number of points.
        """
        if len(words) != 3 or self.encoding is None:
            raise MalformedPointCloud(PointCloudProblem.INVALID_DECLARATION)
        self.element = words[1]
        if self.element != PlyKeyword.VERTEX:
            if HeaderCount(0, sys.maxsize).read(words[2]) != 0:
                raise MalformedPointCloud(PointCloudProblem.NOT_VERTICES)
            return
        if self.point_count is not None:
            raise MalformedPointCloud(PointCloudProblem.INVALID_DECLARATION)
        self.point_count = points.read(words[2], minimum=1)

    def declare_property(self, words: List[str]) -> None:
        """
        :param words: The words of a ``property`` line.
        """
        if self.element is None:
            raise MalformedPointCloud(PointCloudProblem.INVALID_DECLARATION)
        if self.element != PlyKeyword.VERTEX:
            return
        if len(words) != 3 or words[1] == PlyKeyword.LIST:
            raise MalformedPointCloud(PointCloudProblem.LIST_PROPERTY)
        if words[1] not in PLY_SCALAR_TYPES:
            raise MalformedPointCloud(PointCloudProblem.UNKNOWN_SCALAR_TYPE)
        if len(self.fields) >= MAXIMUM_FIELDS:
            raise MalformedPointCloud(PointCloudProblem.INVALID_FIELDS)
        self.fields.append(PointField(name=words[2], scalar=PLY_SCALAR_TYPES[words[1]]))

    def layout(self, words: List[str], offset: int) -> PointLayout:
        """
        :param words: The words of the ``end_header`` line.
        :param offset: The byte offset after the header.
        :return: The record layout the header declared.
        """
        if len(words) != 1 or self.encoding is None or self.point_count is None:
            raise MalformedPointCloud(PointCloudProblem.HEADER_INCOMPLETE)
        return PointLayout(
            encoding=self.encoding,
            point_count=self.point_count,
            fields=tuple(self.fields),
            offset=offset,
        )


class PcdKeyword(StrEnum):
    """
    The declarations of a PCD header.
    """

    VERSION = "VERSION"
    """
    The format version.
    """

    FIELDS = "FIELDS"
    """
    The field names.
    """

    SIZE = "SIZE"
    """
    The size of each field's scalars in bytes.
    """

    TYPE = "TYPE"
    """
    The kind of each field's scalars.
    """

    COUNT = "COUNT"
    """
    How many components each field has.
    """

    WIDTH = "WIDTH"
    """
    The cloud's width.
    """

    HEIGHT = "HEIGHT"
    """
    The cloud's height; 1 for an unorganized cloud.
    """

    VIEWPOINT = "VIEWPOINT"
    """
    The pose the cloud was taken from.
    """

    POINTS = "POINTS"
    """
    How many points follow.
    """

    DATA = "DATA"
    """
    How the records are stored; the last declaration.
    """


PCD_REQUIRED = frozenset(PcdKeyword) - {PcdKeyword.COUNT, PcdKeyword.VIEWPOINT}
"""
The declarations every PCD header has.
"""

PCD_SINGLE_VALUED = (
    PcdKeyword.VERSION,
    PcdKeyword.WIDTH,
    PcdKeyword.HEIGHT,
    PcdKeyword.POINTS,
    PcdKeyword.DATA,
)
"""
The declarations holding exactly one value.
"""

PCD_VERSIONS = (".7", "0.7")
"""
The ways a PCD header writes the version the builder reads.
"""

PCD_ENCODINGS = (PointCloudEncoding.ASCII, PointCloudEncoding.BINARY)
"""
The encodings a PCD file may declare.
"""

VIEWPOINT_VALUES = 7
"""
How many numbers a PCD viewpoint holds: a position and a quaternion.
"""

PCD_COMMENT = "#"
"""
Starts a comment in a PCD header line.
"""

PCD_KEYWORDS = frozenset(keyword.value for keyword in PcdKeyword)
"""
The declarations a PCD header may hold.
"""

PCD_SCALAR_CATEGORIES = frozenset(category.value for category in PcdScalarCategory)
"""
The scalar kinds a PCD ``TYPE`` line may name.
"""


@dataclass(frozen=True)
class PcdHeaderReader(HeaderReader):
    """
    Reads PCD headers of version 0.7, ASCII or uncompressed binary.
    """

    def read(self, lines: HeaderLines, points: PointCountCheck) -> PointLayout:
        declarations = self.declarations(lines)
        if not PCD_REQUIRED <= declarations.keys() or any(
            len(declarations[keyword]) != 1 for keyword in PCD_SINGLE_VALUED
        ):
            raise MalformedPointCloud(PointCloudProblem.INVALID_DECLARATION)
        if declarations[PcdKeyword.VERSION][0] not in PCD_VERSIONS:
            raise MalformedPointCloud(PointCloudProblem.UNSUPPORTED_VERSION)
        if declarations[PcdKeyword.DATA][0] not in PCD_ENCODINGS:
            raise MalformedPointCloud(PointCloudProblem.UNSUPPORTED_ENCODING)
        point_count = points.read(declarations[PcdKeyword.POINTS][0], minimum=1)
        size = HeaderCount(1, points.limit)
        width = size.read(declarations[PcdKeyword.WIDTH][0])
        height = size.read(declarations[PcdKeyword.HEIGHT][0])
        if width * height != point_count:
            raise MalformedPointCloud(PointCloudProblem.DIMENSION_MISMATCH)
        if PcdKeyword.VIEWPOINT in declarations:
            self.check_viewpoint(declarations[PcdKeyword.VIEWPOINT])
        return PointLayout(
            encoding=PointCloudEncoding(declarations[PcdKeyword.DATA][0]),
            point_count=point_count,
            fields=self.fields(declarations),
            offset=lines.offset,
        )

    @staticmethod
    def declarations(lines: HeaderLines) -> Dict[str, List[str]]:
        """
        :param lines: The header's lines.
        :return: The values of each declaration, up to and including ``DATA``.
        :raises MalformedPointCloud: For unknown or repeated declarations.
        """
        declarations: Dict[str, List[str]] = {}
        while PcdKeyword.DATA not in declarations:
            words = lines.read().split(PCD_COMMENT, 1)[0].split()
            if not words:
                continue
            if words[0] not in PCD_KEYWORDS:
                raise MalformedPointCloud(PointCloudProblem.UNKNOWN_DECLARATION)
            if words[0] in declarations:
                raise MalformedPointCloud(PointCloudProblem.INVALID_DECLARATION)
            declarations[words[0]] = words[1:]
        return declarations

    @staticmethod
    def check_viewpoint(values: List[str]) -> None:
        """
        :param values: The values of the ``VIEWPOINT`` declaration.
        :raises MalformedPointCloud: Unless they are seven finite numbers.
        """
        if len(values) != VIEWPOINT_VALUES or any(
            FLOATING_NUMBER.fullmatch(value.encode()) is None
            or not math.isfinite(float(value))
            for value in values
        ):
            raise MalformedPointCloud(PointCloudProblem.INVALID_VIEWPOINT)

    @staticmethod
    def fields(declarations: Dict[str, List[str]]) -> Tuple[PointField, ...]:
        """
        :param declarations: The header's declarations.
        :return: The fields the header declares.
        :raises MalformedPointCloud: When the field declarations disagree.
        """
        names = declarations[PcdKeyword.FIELDS]
        sizes = declarations[PcdKeyword.SIZE]
        kinds = declarations[PcdKeyword.TYPE]
        counts = declarations.get(PcdKeyword.COUNT, ["1"] * len(names))
        if not len(names) == len(sizes) == len(kinds) == len(counts):
            raise MalformedPointCloud(PointCloudProblem.INVALID_FIELDS)
        if len(names) > MAXIMUM_FIELDS:
            raise MalformedPointCloud(PointCloudProblem.INVALID_FIELDS)
        size = HeaderCount(1, MAXIMUM_SCALAR_SIZE)
        count = HeaderCount(1, MAXIMUM_COMPONENTS)
        fields = []
        for name, size_text, kind, count_text in zip(names, sizes, kinds, counts):
            key = (kind, size.read(size_text))
            if kind not in PCD_SCALAR_CATEGORIES or key not in PCD_SCALAR_TYPES:
                raise MalformedPointCloud(PointCloudProblem.UNKNOWN_SCALAR_TYPE)
            fields.append(
                PointField(
                    name=name,
                    scalar=PCD_SCALAR_TYPES[key],
                    count=count.read(count_text),
                )
            )
        return tuple(fields)


# %% records


@dataclass(frozen=True)
class PointRecord:
    """
    The values of one point, in the order of the layout's components.
    """

    values: Sequence[float]
    """
    The values of every component.
    """

    def with_bits_at(self, index: int, scalar: ScalarType) -> PointRecord:
        """
        :param index: Where a packed colour sits.
        :param scalar: The colour's declared scalar.
        :return: The record with the colour's value replaced by its unsigned bits.
        """
        values = list(self.values)
        values[index] = scalar.bits_of(values[index])
        return PointRecord(values)

    def position(self, indices: Tuple[int, int, int]) -> Optional[Tuple[float, ...]]:
        """
        :param indices: Where the x, y and z coordinates sit.
        :return: The position, or None for a missing measurement (a NaN coordinate).
        :raises MalformedPointCloud: For an infinite or overly large coordinate.
        """
        coordinates = tuple(self.values[index] for index in indices)
        for value in coordinates:
            if not math.isnan(value) and (
                math.isinf(value) or abs(value) > FLOAT32_MAXIMUM
            ):
                raise MalformedPointCloud(PointCloudProblem.COORDINATE_OUT_OF_RANGE)
        if any(math.isnan(value) for value in coordinates):
            return None
        return coordinates


@dataclass(frozen=True)
class ColorReading:
    """
    How the colour of a record is read from its values.
    """

    packed_index: Optional[int]
    """
    Where a packed colour's bits sit, or None.
    """

    channel_indices: Optional[Tuple[int, int, int]]
    """
    Where the red, green and blue channels sit, or None.
    """

    channel_scales: Tuple[float, float, float]
    """
    The value of a full channel: 255 for integers, 1 for floats.
    """

    @classmethod
    def of(cls, layout: PointLayout) -> Optional[ColorReading]:
        """
        :param layout: A record layout.
        :return: How to read the colour of its records, or None for a colourless cloud.
        """
        packed = layout.packed_color()
        if packed is not None:
            return cls(
                packed_index=layout.component_index(packed.name),
                channel_indices=None,
                channel_scales=(1.0, 1.0, 1.0),
            )
        channels = layout.channels()
        if channels is None:
            return None
        return cls(
            packed_index=None,
            channel_indices=tuple(
                layout.component_index(channel.name) for channel in channels
            ),
            channel_scales=tuple(
                1.0 if channel.scalar.is_floating() else float(COLOR_CHANNEL_MAXIMUM)
                for channel in channels
            ),
        )

    def color(self, record: PointRecord) -> Tuple[float, float, float]:
        """
        :param record: A record whose packed colour, if any, holds its bits.
        :return: The red, green and blue channels between 0 and 1, as stored (sRGB).
        """
        if self.packed_index is not None:
            bits = int(record.values[self.packed_index])
            return tuple(
                ((bits >> shift) & COLOR_CHANNEL_MAXIMUM) / COLOR_CHANNEL_MAXIMUM
                for shift in PACKED_CHANNEL_SHIFTS
            )
        return tuple(
            self.channel(record.values[index], scale)
            for index, scale in zip(self.channel_indices, self.channel_scales)
        )

    @staticmethod
    def channel(value: float, scale: float) -> float:
        """
        :param value: A channel's stored value.
        :param scale: The value of a full channel.
        :return: The channel between 0 and 1; a missing channel is full.
        """
        if not math.isfinite(value):
            return 1.0
        return min(1.0, max(0.0, value / scale))


# %% files


SAMPLE_HEADER = struct.Struct("<II")
"""
The start of a display sample: the number of points and whether colours follow.
"""

SAMPLE_VALUE = "f"
"""
The ``array`` code of the sample's values: 32-bit floats.
"""


@dataclass(frozen=True)
class PointCloudSample:
    """
    The points the browser shows of a cloud: positions in the file's coordinates and,
    for a coloured cloud, sRGB colours between 0 and 1.

    Its bytes are two little-endian unsigned 32-bit integers, the number of points and 1
    when colours follow, then the x, y and z of every point and, if coloured, the red,
    green and blue of every point, as little-endian 32-bit floats.
    """

    positions: array
    """
    The x, y and z of every point.
    """

    colors: Optional[array]
    """
    The red, green and blue of every point, or None for a colourless cloud.
    """

    def point_count(self) -> int:
        """
        :return: How many points the sample holds.
        """
        return len(self.positions) // len(COORDINATE_FIELDS)

    def to_bytes(self) -> bytes:
        """
        :return: The sample's bytes.
        """
        values = array(SAMPLE_VALUE, self.positions)
        if self.colors is not None:
            values.extend(self.colors)
        if sys.byteorder != "little":
            values.byteswap()
        header = SAMPLE_HEADER.pack(self.point_count(), int(self.colors is not None))
        return header + values.tobytes()


@dataclass(frozen=True)
class PointCloudFile:
    """
    The bytes of a point cloud file of a known format, read within the builder's limits.
    """

    file_format: PointCloudFormat
    """
    The file's format.
    """

    body: bytes
    """
    The whole file.
    """

    limits: SceneBuilderLimits
    """
    The builder's limits.
    """

    def layout(self) -> PointLayout:
        """
        :return: The record layout the file's header declares.
        :raises MalformedPointCloud: When the header is malformed or unsupported.
        :raises TooManyPoints: When the file declares too many points.
        """
        if not self.body:
            raise MalformedPointCloud(PointCloudProblem.EMPTY)
        reader = (
            PlyHeaderReader()
            if self.file_format is PointCloudFormat.PLY
            else PcdHeaderReader()
        )
        return reader.read(
            HeaderLines(self.body), PointCountCheck(self.limits.maximum_points)
        )

    def records(
        self, layout: PointLayout, packed_as_bits: bool
    ) -> Iterator[PointRecord]:
        """
        :param layout: The file's record layout.
        :param packed_as_bits: Whether a packed colour is read as its unsigned bits.
        :return: Every record, checked against the layout.
        :raises MalformedPointCloud: When the records do not match the layout.
        """
        if layout.encoding is not PointCloudEncoding.ASCII:
            return self.binary_records(layout, layout.scalars(packed_as_bits))
        records = self.ascii_records(layout, layout.scalars(packed_as_bits=False))
        packed = layout.packed_color()
        if not packed_as_bits or packed is None:
            return records
        index = layout.component_index(packed.name)
        return (record.with_bits_at(index, packed.scalar) for record in records)

    def ascii_records(
        self, layout: PointLayout, scalars: List[ScalarType]
    ) -> Iterator[PointRecord]:
        """
        :param layout: The file's record layout.
        :param scalars: The scalar of every component.
        :return: The records of an ASCII file, one per non-empty line.
        """
        source = io.BytesIO(self.body)
        source.seek(layout.offset)
        count = 0
        for line in iter(lambda: source.readline(MAXIMUM_RECORD_BYTES + 1), b""):
            if len(line) > MAXIMUM_RECORD_BYTES:
                raise MalformedPointCloud(PointCloudProblem.RECORD_TOO_LONG)
            tokens = line.split()
            if not tokens:
                continue
            count += 1
            if count > layout.point_count or len(tokens) != len(scalars):
                raise MalformedPointCloud(PointCloudProblem.RECORD_SHAPE)
            yield PointRecord(
                [scalar.read(token) for scalar, token in zip(scalars, tokens)]
            )
        if count != layout.point_count:
            raise MalformedPointCloud(PointCloudProblem.TRUNCATED)

    def binary_records(
        self, layout: PointLayout, scalars: List[ScalarType]
    ) -> Iterator[PointRecord]:
        """
        :param layout: The file's record layout.
        :param scalars: The scalar of every component.
        :return: The records of a binary file.
        """
        order = ">" if layout.encoding is PointCloudEncoding.BINARY_BIG_ENDIAN else "<"
        record = struct.Struct(order + "".join(scalar.value for scalar in scalars))
        if len(self.body) - layout.offset != layout.point_count * record.size:
            raise MalformedPointCloud(PointCloudProblem.TRUNCATED)
        for values in record.iter_unpack(memoryview(self.body)[layout.offset :]):
            yield PointRecord(values)

    def check(self) -> PointCloudMetadata:
        """
        Read every record.

        :return: What the file holds.
        :raises MalformedPointCloud: When the file is malformed or holds no finite
            point.
        :raises TooManyPoints: When the file declares too many points.
        """
        layout = self.layout()
        indices = self.coordinate_indices(layout)
        finite = sum(
            record.position(indices) is not None
            for record in self.records(layout, packed_as_bits=False)
        )
        if finite == 0:
            raise MalformedPointCloud(PointCloudProblem.NO_FINITE_POINTS)
        return PointCloudMetadata(
            file_format=self.file_format,
            encoding=layout.encoding,
            point_count=layout.point_count,
            finite_point_count=finite,
        )

    def sample(self) -> PointCloudSample:
        """
        :return: Every n-th point with finite coordinates, n chosen so that at most
            :attr:`SceneBuilderLimits.maximum_sample_points` remain; the same file
            always gives the same sample.
        :raises MalformedPointCloud: When the file is malformed or holds no finite point.
        """
        metadata = self.check()
        layout = self.layout()
        indices = self.coordinate_indices(layout)
        color = ColorReading.of(layout)
        stride = math.ceil(
            metadata.finite_point_count / self.limits.maximum_sample_points
        )
        positions = array(SAMPLE_VALUE)
        colors = None if color is None else array(SAMPLE_VALUE)
        finite = 0
        for record in self.records(layout, packed_as_bits=True):
            position = record.position(indices)
            if position is None:
                continue
            if finite % stride == 0:
                positions.extend(position)
                if colors is not None:
                    colors.extend(color.color(record))
            finite += 1
        return PointCloudSample(positions=positions, colors=colors)

    @staticmethod
    def coordinate_indices(layout: PointLayout) -> Tuple[int, int, int]:
        """
        :param layout: A record layout.
        :return: Where the x, y and z coordinates sit in its records.
        """
        return tuple(layout.component_index(axis) for axis in COORDINATE_FIELDS)
