"""
The staging directory an export converts into, and the publication of a bundle that
passed its gate.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import Self

from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_usd.bundle.index import NO_ROBOT, ScenesIndex
from cramera_usd.exceptions import PublicationNotListed

# %% names


class StagingName(StrEnum):
    """
    The names inside and of a staging directory.
    """

    PREFIX = ".export_"
    """
    Starts the name of a staging directory; the viewer lists no directory whose name is
    not a scene name, so it never shows a staged bundle.
    """

    SUFFIX_SEPARATOR = "."
    """
    Between the bundle name and the random part of a staging directory's name.
    """

    REPLACED = "replaced"
    """
    The published bundle a newer one replaces, moved aside before it is deleted.
    """


# %% staging


@dataclass(frozen=True)
class StagingDirectory:
    """
    A directory inside the scenes directory, on the same file system, so a passed bundle
    moves into place by rename.
    """

    path: Path
    """
    The staging directory.
    """

    scenes_directory: Path
    """
    The scenes directory the bundle is published into.
    """

    name: str
    """
    The bundle's name.
    """

    @classmethod
    def create(cls, scenes_directory: Path, name: str) -> Self:
        """
        :param scenes_directory: The scenes directory.
        :param name: The bundle's name.
        :return: A new, empty staging directory for the bundle.
        """
        scenes_directory.mkdir(parents=True, exist_ok=True)
        path = tempfile.mkdtemp(
            prefix=f"{StagingName.PREFIX}{name}{StagingName.SUFFIX_SEPARATOR}",
            dir=scenes_directory,
        )
        return cls(Path(path), scenes_directory, name)

    @property
    def bundle(self) -> Path:
        """
        The staged bundle.
        """
        return self.path / self.name

    @property
    def published(self) -> Path:
        """
        Where the bundle is published.
        """
        return self.scenes_directory / self.name

    def remove(self) -> None:
        """
        Delete the staging directory and everything in it.
        """
        shutil.rmtree(self.path)

    def publish(self, replay: bool) -> SceneIndexEntry:
        """
        Move the staged bundle into place, replacing a published one of the same name,
        delete the staging directory and rebuild the scenes index.

        :param replay: Whether the bundle replays a run with its robot, rather than
            showing the environment alone.
        :return: The bundle's entry in the rebuilt index.
        :raises PublicationNotListed: When the index does not list the bundle, or lists
            it with a robot that does not fit the kind of bundle.
        """
        if self.published.exists():
            self.published.rename(self.path / StagingName.REPLACED)
        self.bundle.rename(self.published)
        self.remove()
        index = ScenesIndex(self.scenes_directory)
        entry = index.rebuild(self.name).entry(self.name)
        if entry is None or (entry.robot == NO_ROBOT) == replay:
            raise PublicationNotListed(index.path, self.name)
        return entry
