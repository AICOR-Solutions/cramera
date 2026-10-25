"""
The folders of the viewer's machine as the URDF picker browses them: their folders and
their URDF and xacro files, so an environment is picked rather than its path typed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Optional

from cramera_plan_builder.exceptions import FolderNotReadable, NotAFolder
from cramera_protocol.plan_builder import UrdfFolder

URDF_SOURCE_SUFFIXES = frozenset({".urdf", ".xacro"})
"""
The suffixes of the files an environment is loaded from.
"""

HIDDEN_PREFIX = "."
"""
How the names of hidden files and folders start.
"""


@dataclass(frozen=True)
class UrdfFolders:
    """
    Lists the folders of this machine for the URDF picker.
    """

    home: Path = field(default_factory=Path.home)
    """
    The folder listed when none is named.
    """

    def listing(self, given: Optional[str]) -> UrdfFolder:
        """
        :param given: A folder, absolute or starting with ``~``, or None for the home
            folder.
        :return: The folder's folders and URDF and xacro files, hidden ones left out.
        :raises NotAFolder: When the path names no folder.
        :raises FolderNotReadable: When the folder may not be listed.
        """
        folder = (Path(given.strip()).expanduser() if given else self.home).resolve()
        if not folder.is_dir():
            raise NotAFolder(str(given))
        if not os.access(folder, os.R_OK | os.X_OK):
            raise FolderNotReadable(str(folder))
        entries = sorted(
            entry
            for entry in folder.iterdir()
            if not entry.name.startswith(HIDDEN_PREFIX)
        )
        return UrdfFolder(
            path=str(folder),
            parent=str(folder.parent) if folder.parent != folder else None,
            folders=[entry.name for entry in entries if entry.is_dir()],
            files=[
                entry.name
                for entry in entries
                if entry.is_file() and entry.suffix in URDF_SOURCE_SUFFIXES
            ],
        )
