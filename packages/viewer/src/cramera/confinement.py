"""
Resolving requested paths without leaving a directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from cramera.exceptions import FileNotInDirectory, PathOutsideDirectory

# %% confinement


@dataclass(frozen=True)
class ConfinedDirectory:
    """
    A directory whose files can be requested by relative path, and nothing outside
    it: no ``..``, no absolute paths, no symbolic links that lead out.
    """

    root: Path
    """
    The directory; requested files must resolve to a path inside it.
    """

    def file(self, requested: str) -> Path:
        """
        :param requested: A path relative to :attr:`root`, with ``/`` separators.
        :return: The resolved file.
        :raises PathOutsideDirectory: When the path leaves :attr:`root`.
        :raises FileNotInDirectory: When the path names no file.
        """
        resolved = self.resolve(requested)
        if not resolved.is_file():
            raise FileNotInDirectory(self.root, requested)
        return resolved

    def resolve(self, requested: str) -> Path:
        """
        :param requested: A path relative to :attr:`root`, with ``/`` separators.
        :return: The resolved path, which may not exist.
        :raises PathOutsideDirectory: When the path leaves :attr:`root`.
        """
        relative = PurePosixPath(requested)
        if (
            not requested
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in requested
            or "\x00" in requested
        ):
            raise PathOutsideDirectory(self.root, requested)
        root = self.root.resolve()
        resolved = root.joinpath(*relative.parts).resolve()
        if not resolved.is_relative_to(root):
            raise PathOutsideDirectory(self.root, requested)
        return resolved
