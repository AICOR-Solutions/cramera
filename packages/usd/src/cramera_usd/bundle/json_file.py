"""
Writing protocol documents to JSON files, replacing a file only once its new content is
complete.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from typing_extensions import Any, Dict, Optional, Tuple

from cramera_protocol.document import JsonDocument
from cramera_usd.encoding import TEXT_ENCODING
from cramera_usd.gltf.format import COMPACT_SEPARATORS

# %% layouts

PARTIAL_SUFFIX = ".part"
"""
Appended to a file's name while its new content is written.
"""

FINAL_NEWLINE = "\n"
"""
The line end every JSON file ends with.
"""


class JsonLayout(Enum):
    """
    How a JSON file is laid out.
    """

    INDENTED = 1
    """
    One item per line, indented by one space per level, for files people read.
    """

    COMPACT = None
    """
    Without optional whitespace, for large files.
    """

    @property
    def separators(self) -> Optional[Tuple[str, str]]:
        """
        The item and key separators, or None for the default ones.
        """
        if self is JsonLayout.COMPACT:
            return COMPACT_SEPARATORS
        return None


# %% files


@dataclass(frozen=True)
class JsonFile:
    """
    One JSON file.
    """

    path: Path
    """
    The file.
    """

    def write(self, document: JsonDocument, layout: JsonLayout) -> None:
        """
        Write a document, replacing the file only once the new content is complete.

        :param document: The document.
        :param layout: How the file is laid out.
        """
        self.write_text(self.text(document.to_json(), layout))

    @staticmethod
    def text(payload: Dict[str, Any], layout: JsonLayout) -> str:
        """
        :param payload: The JSON object.
        :param layout: How the file is laid out.
        :return: The file's text, ending in a newline.
        """
        return (
            json.dumps(
                payload,
                indent=layout.value,
                separators=layout.separators,
                ensure_ascii=False,
            )
            + FINAL_NEWLINE
        )

    def write_text(self, text: str) -> None:
        """
        Write text, replacing the file only once the new content is complete.

        :param text: The content.
        """
        partial = self.path.with_name(f"{self.path.name}{PARTIAL_SUFFIX}")
        partial.write_text(text, encoding=TEXT_ENCODING)
        partial.replace(self.path)

    def read(self) -> Any:
        """
        :return: The decoded content of the file.
        """
        return json.loads(self.path.read_text(encoding=TEXT_ENCODING))
