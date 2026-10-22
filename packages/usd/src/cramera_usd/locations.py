"""
Where the commands put scene bundles unless told otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import Mapping

from cramera_protocol.viewer import EnvironmentVariable

# %% directories


class DefaultDirectory(StrEnum):
    """
    The directories below the home directory the commands fall back to.
    """

    DATA = ".cramera"
    """
    Cramera's own data, whose ``scenes`` directory holds local bundles.
    """

    SHARED_SCENES = "cramera_scenes"
    """
    The shared scenes directory twins are exported into.
    """

    SCENES = "scenes"
    """
    The scenes directory inside cramera's data.
    """


@dataclass(frozen=True)
class ScenesLocations:
    """
    The scenes directories the environment configures.
    """

    environment: Mapping[str, str]
    """
    The process environment.
    """

    home: Path
    """
    The user's home directory.
    """

    def import_directory(self) -> Path:
        """
        :return: The scenes directory the viewer reads: the shared one when
            configured, else the local one in cramera's data.
        """
        shared = self.environment.get(EnvironmentVariable.SCENES)
        if shared:
            return Path(shared).expanduser()
        data = self.environment.get(EnvironmentVariable.DATA)
        data_directory = (
            Path(data).expanduser() if data else self.home / DefaultDirectory.DATA
        )
        return data_directory / DefaultDirectory.SCENES

    def export_directory(self) -> Path:
        """
        :return: The shared scenes directory: the configured one, else
            ``~/cramera_scenes``.
        """
        shared = self.environment.get(EnvironmentVariable.SCENES)
        if shared:
            return Path(shared).expanduser()
        return self.home / DefaultDirectory.SHARED_SCENES
