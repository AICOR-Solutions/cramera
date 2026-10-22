"""
Where cramera keeps and finds its data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Mapping, Optional, Self

from cramera_protocol.viewer import EnvironmentVariable

# %% locations


@dataclass(frozen=True)
class DataLocations:
    """
    The directories cramera reads scenes from and writes recordings to.
    """

    data: Path
    """
    The directory of cramera's own data.
    """

    shared_scenes: Optional[Path]
    """
    The shared scenes directory, when one is configured.
    """

    @classmethod
    def from_environment(cls, environment: Mapping[str, str], home: Path) -> Self:
        """
        :param environment: The process environment.
        :param home: The user's home directory.
        :return: The locations the environment configures, with ``~/.cramera`` as the
            data directory by default.
        """
        data = environment.get(EnvironmentVariable.DATA)
        shared = environment.get(EnvironmentVariable.SCENES)
        return cls(
            data=Path(data).expanduser() if data else home / ".cramera",
            shared_scenes=Path(shared).expanduser() if shared else None,
        )

    @property
    def local_scenes(self) -> Path:
        """
        The directory local recordings are written to.
        """
        return self.data / "scenes"
