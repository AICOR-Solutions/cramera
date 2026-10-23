"""
The fields of a plan's actions as the short texts a replayed step shows.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from enum import Enum

from typing_extensions import Any, Dict, List, Optional, Tuple

from cramera_protocol.bundle.scene import BooleanText, DeclaredField, FieldValueKind
from semantic_digital_twin.spatial_types import Point3, Pose
from semantic_digital_twin.world_description.world_entity import (
    KinematicStructureEntity,
    SemanticAnnotation,
)

PARAMETER_PRECISION = 3
"""
Decimal places of a number a parameter shows.
"""

MAXIMUM_TEXT_LENGTH = 120
"""
The most characters a parameter's text has; a longer one is cut and ends in
:data:`ELLIPSIS`.
"""

ELLIPSIS = "…"
"""
Ends a parameter's text that was cut.
"""

LIST_SEPARATOR = ", "
"""
Separates the items of a list, and the fields of a dataclass value.
"""

NAME_SEPARATOR = "_"
"""
Separates the words of a field's name.
"""

DEGREE_SIGN = "°"
"""
Follows an angle in degrees.
"""

MAXIMUM_NESTING = 1
"""
How many dataclass values deep a parameter's text shows fields; a deeper dataclass value
is named by its class.
"""

PLAIN_DEFAULTS = (bool, int, float, str, Enum)
"""
The default values a field's value is compared with; a default of another type never
counts as left unchanged.
"""

# %% kinds


@dataclass(frozen=True)
class FieldValue:
    """
    A value an action's field holds, named by its kind.
    """

    value: Any
    """
    The value; never None.
    """

    def kind(self) -> FieldValueKind:
        """
        :return: What the value is; an enumeration member is named an enumeration before
            a number, since some enumerations are numbers too.
        """
        value = self.value
        if isinstance(value, bool):
            return FieldValueKind.BOOLEAN
        if isinstance(value, Enum):
            return FieldValueKind.ENUMERATION
        if isinstance(value, (int, float)):
            return FieldValueKind.NUMBER
        if isinstance(value, str):
            return FieldValueKind.TEXT
        if isinstance(value, Pose):
            return FieldValueKind.POSE
        if isinstance(value, Point3):
            return FieldValueKind.POINT
        if isinstance(value, (KinematicStructureEntity, SemanticAnnotation)):
            return FieldValueKind.ENTITY
        if isinstance(value, type):
            return FieldValueKind.CLASS
        if isinstance(value, (list, tuple)):
            return FieldValueKind.LIST
        if dataclasses.is_dataclass(value):
            return FieldValueKind.STRUCTURE
        return FieldValueKind.OTHER


# %% values


@dataclass(frozen=True)
class NumberText:
    """
    A number rounded to :data:`PARAMETER_PRECISION` decimal places.
    """

    value: float
    """
    The number.
    """

    def text(self) -> str:
        """
        :return: The rounded number without trailing zeros.
        """
        return f"{round(float(self.value), PARAMETER_PRECISION) + 0.0:g}"


@dataclass(frozen=True)
class PositionText:
    """
    A point or a pose of the world: its position, a pose's heading, and the frame it is
    given in.
    """

    coordinates: Tuple[float, ...]
    """
    The position in metres.
    """

    yaw: Optional[float]
    """
    A pose's heading about the vertical axis in radians, or None for a point.
    """

    frame: Optional[KinematicStructureEntity]
    """
    The frame the position is given in, or None when it names none.
    """

    @classmethod
    def of_pose(cls, pose: Pose) -> PositionText:
        """
        :param pose: A pose.
        :return: Its position, heading and frame.
        """
        matrix = pose.to_np()
        return cls(
            coordinates=tuple(matrix[:3, 3]),
            yaw=math.atan2(matrix[1, 0], matrix[0, 0]),
            frame=pose.reference_frame,
        )

    @classmethod
    def of_point(cls, point: Point3) -> PositionText:
        """
        :param point: A point.
        :return: Its position and frame.
        """
        return cls(
            coordinates=tuple(point.to_np()[:3]), yaw=None, frame=point.reference_frame
        )

    def text(self) -> str:
        """
        :return: The coordinates, then a pose's heading in whole degrees, then the
            frame.
        """
        numbers = LIST_SEPARATOR.join(
            NumberText(value).text() for value in self.coordinates
        )
        text = f"({numbers})"
        if self.yaw is not None:
            text = f"{text} yaw {round(math.degrees(self.yaw))}{DEGREE_SIGN}"
        if self.frame is None:
            return text
        return f"{text} in {self.frame.name.name}"


@dataclass(frozen=True)
class ParameterText:
    """
    Turns the value of an action's field into a short text.
    """

    nesting: int = 0
    """
    How many dataclass values the value is a field of, below the action.
    """

    def text(self, value: Any) -> Optional[str]:
        """
        :param value: The value of a field.
        :return: The value's text, at most :data:`MAXIMUM_TEXT_LENGTH` characters long,
            or None for a field that is not set.
        """
        if value is None:
            return None
        text = self.full_text(value)
        if len(text) <= MAXIMUM_TEXT_LENGTH:
            return text
        return text[: MAXIMUM_TEXT_LENGTH - len(ELLIPSIS)] + ELLIPSIS

    def full_text(self, value: Any) -> str:
        """
        :param value: A value that is set.
        :return: A switch as yes or no, an enumeration member by its name, a number
            rounded, a pose or point by its position, an entity of the world or a class
            by its name, a list by its items, a dataclass value by the fields it was
            given, and any other value by its class.
        """
        kind = FieldValue(value).kind()
        if kind is FieldValueKind.BOOLEAN:
            return BooleanText.YES if value else BooleanText.NO
        if kind is FieldValueKind.ENUMERATION:
            return value.name
        if kind is FieldValueKind.NUMBER:
            return NumberText(value).text() if isinstance(value, float) else str(value)
        if kind is FieldValueKind.TEXT:
            return value
        if kind is FieldValueKind.POSE:
            return PositionText.of_pose(value).text()
        if kind is FieldValueKind.POINT:
            return PositionText.of_point(value).text()
        if kind is FieldValueKind.ENTITY:
            return value.name.name
        if kind is FieldValueKind.CLASS:
            return value.__name__
        if kind is FieldValueKind.LIST:
            texts = (self.text(item) for item in value)
            return LIST_SEPARATOR.join(text for text in texts if text is not None)
        if kind is FieldValueKind.STRUCTURE and self.nesting < MAXIMUM_NESTING:
            texts = FieldTexts(value, self.nesting + 1).texts()
            return LIST_SEPARATOR.join(
                f"{name.replace(NAME_SEPARATOR, ' ')} {text}"
                for name, text in texts.items()
            )
        return type(value).__name__


# %% fields


@dataclass(frozen=True)
class FieldTexts:
    """
    The fields a dataclass value was given, as texts by field name.
    """

    value: Any
    """
    A dataclass value, such as an action.
    """

    nesting: int = 0
    """
    How many dataclass values the value is a field of, below the action.
    """

    def texts(self) -> Dict[str, str]:
        """
        :return: The text of every init field that is set and differs from its default,
            in the order the dataclass declares them.
        """
        values = vars(self.value)
        texts: Dict[str, str] = {}
        for declared in dataclasses.fields(self.value):
            if not declared.init or self.is_default(declared, values[declared.name]):
                continue
            text = ParameterText(self.nesting).text(values[declared.name])
            if text is not None:
                texts[declared.name] = text
        return texts

    @staticmethod
    def is_default(declared: dataclasses.Field, value: Any) -> bool:
        """
        :param declared: A field of the dataclass.
        :param value: Its value.
        :return: Whether the value is the field's plain default.
        """
        default = declared.default
        return (
            isinstance(default, PLAIN_DEFAULTS)
            and type(value) is type(default)
            and value == default
        )


@dataclass(frozen=True)
class FieldDeclarations:
    """
    Every field a dataclass value declares, such as an action, with whether it must be
    given and its default.
    """

    value: Any
    """
    A dataclass value, such as an action.
    """

    def declarations(self) -> List[DeclaredField]:
        """
        :return: Every init field in the order the dataclass declares them, with what
            its value is; a field without a default or default factory must be given,
            and only a plain default is named.
        """
        values = vars(self.value)
        return [
            DeclaredField(
                name=declared.name,
                required=declared.default is dataclasses.MISSING
                and declared.default_factory is dataclasses.MISSING,
                default=(
                    ParameterText().text(declared.default)
                    if isinstance(declared.default, PLAIN_DEFAULTS)
                    else None
                ),
                kind=self.kind(declared, values[declared.name]),
            )
            for declared in dataclasses.fields(self.value)
            if declared.init
        ]

    @staticmethod
    def kind(declared: dataclasses.Field, value: Any) -> Optional[FieldValueKind]:
        """
        :param declared: A field of the dataclass.
        :param value: Its value.
        :return: What the value is, else what the field's plain default is; None when
            the field is not set and has no plain default.
        """
        if value is not None:
            return FieldValue(value).kind()
        if isinstance(declared.default, PLAIN_DEFAULTS):
            return FieldValue(declared.default).kind()
        return None
