"""
Errors raised while reading or writing protocol documents.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import Any, Tuple

# %% base


@dataclass
class ProtocolError(Exception):
    """
    A protocol document or message that cannot be read or written.
    """

    def __post_init__(self) -> None:
        super().__init__(self.message())

    def message(self) -> str:
        """
        :return: The sentence a person reads when this error is raised.
        """
        return type(self).__name__


# %% versions


@dataclass
class UnsupportedProtocolVersion(ProtocolError):
    """
    A document or answer written by a protocol version this package cannot read.
    """

    found: str
    """
    The version the document declares.
    """

    supported: str
    """
    The version this package reads and writes.
    """

    def message(self) -> str:
        return (
            f"Protocol version {self.found} is not supported; "
            f"this cramera reads version {self.supported}."
        )


@dataclass
class MalformedProtocolVersion(ProtocolError):
    """
    A version text that is not two non-negative integers separated by a dot.
    """

    text: str
    """
    The text that was read as a version.
    """

    def message(self) -> str:
        return f"{self.text!r} is not a protocol version such as '1.0'."


# %% documents


@dataclass
class MissingDocumentField(ProtocolError):
    """
    A document that lacks a field without a default.
    """

    document: str
    """
    The name of the document class being read.
    """

    key: str
    """
    The JSON key that is missing.
    """

    def message(self) -> str:
        return f"{self.document} needs the key {self.key!r}."


@dataclass
class UnexpectedDocumentField(ProtocolError):
    """
    A document that holds keys its class does not declare.
    """

    document: str
    """
    The name of the document class being read.
    """

    keys: Tuple[str, ...]
    """
    The undeclared keys, sorted.
    """

    def message(self) -> str:
        return f"{self.document} does not know the keys {list(self.keys)}."


@dataclass
class InvalidDocumentValue(ProtocolError):
    """
    A value whose JSON type does not match the field it is read into.
    """

    document: str
    """
    The name of the document or value class being read.
    """

    location: str
    """
    The key or position of the value inside the document.
    """

    value: Any
    """
    The value that was read.
    """

    expected: str
    """
    A description of the value the field accepts.
    """

    def message(self) -> str:
        return (
            f"{self.document}.{self.location} expects {self.expected}, "
            f"got {self.value!r}."
        )


@dataclass
class UnsupportedFieldType(ProtocolError):
    """
    A document class that declares a field type the document reader cannot convert.
    """

    document: str
    """
    The name of the document class.
    """

    field_name: str
    """
    The Python name of the field.
    """

    annotation: str
    """
    The field's type annotation.
    """

    def message(self) -> str:
        return (
            f"{self.document}.{self.field_name} has the type {self.annotation}, "
            f"which protocol documents cannot hold."
        )
