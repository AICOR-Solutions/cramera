"""
The scenes index, ``index.json``, rebuilt from the bundles a scenes directory holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import List, Optional, Union

from cramera_protocol.bundle.files import BundleFile, ScenesDirectoryFile
from cramera_protocol.bundle.index import SceneIndex, SceneIndexEntry, SceneName
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.version import CURRENT_VERSION
from cramera_usd.bundle.json_file import JsonFile, JsonLayout

# %% constants

MODEL_NAME_SEPARATOR = "+"
"""
Between the names of a scene's environment models when no environment name is given.
"""

NO_ROBOT = ""
"""
The robot of a bundle without one, which the viewer's picker shows as the bench alone.
"""

# %% bundles


@dataclass(frozen=True)
class UnreadableBundle:
    """
    A bundle in a scenes directory whose ``scene.json`` cannot be read.
    """

    bundle: Path
    """
    The bundle directory.
    """

    reason: str
    """
    Why it cannot be read.
    """


@dataclass(frozen=True)
class BundleEntryReader:
    """
    Reads the index entry of one bundle from its ``scene.json``.
    """

    bundle: Path
    """
    The bundle directory.
    """

    def read(self) -> Union[SceneIndexEntry, UnreadableBundle]:
        """
        A bundle with a broken ``scene.json`` must not keep its readable neighbours out
        of the index, so this is the one place where reading errors become data.

        :return: The bundle's entry, or the reason it cannot be read.
        """
        try:
            description = SceneDescription.from_json(
                JsonFile(self.bundle / BundleFile.SCENE).read()
            )
        except (ValueError, ProtocolError) as error:
            return UnreadableBundle(self.bundle, str(error))
        return self.entry_of(description)

    def entry_of(self, description: SceneDescription) -> SceneIndexEntry:
        """
        :param description: The bundle's scene description.
        :return: How the pickers offer the bundle: the labels a person gave win over
            the names the models carry.
        """
        robot = description.robot_name or (
            description.robot.name if description.robot is not None else NO_ROBOT
        )
        environment = description.environment_name or (
            MODEL_NAME_SEPARATOR.join(
                model.name for model in description.models if not model.robot
            )
            or None
        )
        return SceneIndexEntry(
            name=self.bundle.name,
            robot=robot,
            environment=environment,
            task=description.task,
        )


# %% index


@dataclass
class ScenesIndex:
    """
    The ``index.json`` of a scenes directory, rebuilt from the bundles on disk so that a
    bundle removed or renamed since cannot leave an entry behind.
    """

    directory: Path
    """
    The scenes directory.
    """

    unreadable: List[UnreadableBundle] = field(default_factory=list)
    """
    The bundles the last rebuild could not read and left out.
    """

    @property
    def path(self) -> Path:
        """
        The index file.
        """
        return self.directory / ScenesDirectoryFile.INDEX

    def read(self) -> Optional[SceneIndex]:
        """
        :return: The index on disk, or None when there is none.
        :raises ProtocolError: When the index is not a scenes index; it is left as it
            is.
        """
        if not self.path.is_file():
            return None
        return SceneIndex.from_json(JsonFile(self.path).read())

    def rebuild(self, name: str) -> SceneIndex:
        """
        Rewrite the index from the bundles on disk, registering a bundle just written.

        :param name: The bundle just written; it becomes the default when the index had
            none.
        :return: The written index.
        :raises ProtocolError: When the existing index is not a scenes index; it is not
            overwritten.
        """
        existing = self.read()
        default = existing.default if existing is not None else None
        self.unreadable = []
        index = SceneIndex(
            format_version=CURRENT_VERSION,
            default=default or name,
            scenes=self.entries(),
        )
        JsonFile(self.path).write(index, JsonLayout.INDENTED)
        return index

    def entries(self) -> List[SceneIndexEntry]:
        """
        :return: The entry of every readable bundle, in name order; the unreadable
            ones are kept in :attr:`unreadable`.
        """
        entries = []
        for bundle in sorted(self.directory.iterdir()):
            if not SceneName.is_valid(bundle.name):
                continue
            if not (bundle / BundleFile.SCENE).is_file():
                continue
            read = BundleEntryReader(bundle).read()
            if isinstance(read, UnreadableBundle):
                self.unreadable.append(read)
                continue
            entries.append(read)
        return entries
