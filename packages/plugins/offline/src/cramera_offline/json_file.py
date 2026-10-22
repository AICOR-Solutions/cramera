"""
Reading JSON files whose damage must become an error the viewer can answer with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Any

from cramera_offline.exceptions import UnreadableFile

# %% files


@dataclass(frozen=True)
class JsonFile:
    """
    A JSON file on disk.
    """

    path: Path
    """
    The file.
    """

    def read(self) -> Any:
        """
        :return: The decoded JSON value.
        :raises UnreadableFile: When the file is not JSON.
        """
        text = self.path.read_text(encoding="utf-8", errors="replace")
        return self.decode(self.path, text)

    @staticmethod
    def decode(path: Path, text: str) -> Any:
        """
        The JSON reader raises its own error for damaged text; this is the one place
        where it becomes :class:`UnreadableFile`.

        :param path: The file the text was read from, for the error.
        :param text: JSON text.
        :return: The decoded JSON value.
        :raises UnreadableFile: When the text is not JSON.
        """
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise UnreadableFile(path, str(error)) from error

    def write(self, value: Any) -> None:
        """
        :param value: A JSON-serializable value, written with an indentation that
            keeps the file readable for people.
        """
        self.path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
