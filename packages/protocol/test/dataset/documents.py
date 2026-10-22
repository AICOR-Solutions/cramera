"""
Documents that exercise every kind of field the document reader supports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import Any, Dict, List, Optional

from cramera_protocol.document import JsonDocument, document_field, extension_field
from cramera_protocol.geometry import Pose

# %% keys


class ColorName(StrEnum):
    """
    Colours a sample document can name.
    """

    RED = "red"
    """
    Red.
    """

    BLUE = "blue"
    """
    Blue.
    """


class SampleKey(StrEnum):
    """
    The keys of the sample documents.
    """

    TITLE = "title"
    """
    A required text.
    """

    OLD_TITLE = "heading"
    """
    The key an earlier format used for the title.
    """

    COUNT = "count"
    """
    An optional integer.
    """

    RATIO = "ratio"
    """
    A float with a default.
    """

    ENABLED = "enabled"
    """
    A flag with a default.
    """

    COLOR = "color"
    """
    An optional enumeration member.
    """

    POSES = "poses"
    """
    A list of poses.
    """

    TABLE = "table"
    """
    A dictionary of number lists.
    """

    CHILDREN = "children"
    """
    Nested documents of the same class.
    """

    ANYTHING = "anything"
    """
    A value of any JSON type.
    """


# %% documents


@dataclass(kw_only=True)
class SampleDocument(JsonDocument):
    """
    A document with one field of every supported kind.
    """

    title: str = document_field(SampleKey.TITLE, legacy_keys=(SampleKey.OLD_TITLE,))
    """
    A required text with a legacy key.
    """

    count: Optional[int] = document_field(SampleKey.COUNT, default=None)
    """
    An optional integer.
    """

    ratio: float = document_field(SampleKey.RATIO, default=1.0)
    """
    A float with a default.
    """

    enabled: bool = document_field(SampleKey.ENABLED, default=False)
    """
    A flag with a default.
    """

    color: Optional[ColorName] = document_field(SampleKey.COLOR, default=None)
    """
    An optional enumeration member.
    """

    poses: List[Pose] = document_field(SampleKey.POSES, default_factory=list)
    """
    A list of poses.
    """

    table: Dict[str, List[float]] = document_field(
        SampleKey.TABLE, default_factory=dict
    )
    """
    A dictionary of number lists.
    """

    children: List[SampleDocument] = document_field(
        SampleKey.CHILDREN, default_factory=list
    )
    """
    Nested documents of the same class.
    """

    anything: Any = document_field(SampleKey.ANYTHING, default=None)
    """
    A value of any JSON type.
    """


@dataclass(kw_only=True)
class OpenDocument(JsonDocument):
    """
    A document that keeps keys it does not declare.
    """

    title: str = document_field(SampleKey.TITLE)
    """
    A required text.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    The undeclared keys.
    """


@dataclass(kw_only=True)
class DocumentWithPlainField(JsonDocument):
    """
    A document that declares a field without a JSON key.
    """

    title: str = field(default="")
    """
    A field the reader cannot place.
    """


@dataclass(kw_only=True)
class DocumentWithUnion(JsonDocument):
    """
    A document with a union of two types, which documents cannot hold.
    """

    value: int | str = document_field(SampleKey.ANYTHING)
    """
    A field of two types.
    """


@dataclass(kw_only=True)
class DocumentWithSet(JsonDocument):
    """
    A document with a set, which JSON cannot hold.
    """

    values: set[int] = document_field(SampleKey.ANYTHING)
    """
    A set of integers.
    """
