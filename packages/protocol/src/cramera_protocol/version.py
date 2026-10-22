"""
The protocol version documents and answers declare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from typing_extensions import Any, Self

from cramera_protocol.document import JsonValue, ValueLocation
from cramera_protocol.exceptions import (
    MalformedProtocolVersion,
    UnsupportedProtocolVersion,
)

# %% version


@dataclass(frozen=True, order=True)
class ProtocolVersion(JsonValue):
    """
    A major and a minor version number.

    Readers accept every minor version of their own major version: a minor version
    only adds optional fields.
    """

    major: int
    """
    Changes when a reader of the previous major version would misread a document.
    """

    minor: int
    """
    Changes when a document gains optional content.
    """

    @classmethod
    def from_json(cls, data: Any) -> Self:
        if not isinstance(data, str):
            raise MalformedProtocolVersion(repr(data))
        match = re.fullmatch(r"(\d+)\.(\d+)", data)
        if match is None:
            raise MalformedProtocolVersion(data)
        return cls(major=int(match.group(1)), minor=int(match.group(2)))

    def to_json(self) -> str:
        return f"{self.major}.{self.minor}"

    def require_readable_by(self, reader: ProtocolVersion) -> None:
        """
        A reader reads its own major version and documents without a version.

        :param reader: The version of the code reading a document of this version.
        :raises UnsupportedProtocolVersion: When the document has another major version.
        """
        if self != UNVERSIONED and self.major != reader.major:
            raise UnsupportedProtocolVersion(self.to_json(), reader.to_json())


CURRENT_VERSION = ProtocolVersion(major=1, minor=0)
"""
The version this package reads and writes.
"""

UNVERSIONED = ProtocolVersion(major=0, minor=0)
"""
The version of a document written before documents declared one.
"""
