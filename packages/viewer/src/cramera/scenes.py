"""
The scene bundles the viewer can show, from several scenes directories.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import Dict, List, Optional, Sequence, Union

from cramera.confinement import ConfinedDirectory
from cramera.exceptions import UnknownScene
from cramera_protocol.bundle.files import BundleFile, ScenesDirectoryFile
from cramera_protocol.bundle.index import (
    InvalidSceneName,
    ReservedSceneName,
    SceneIndex,
    SceneIndexEntry,
    SceneName,
)
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.version import CURRENT_VERSION

# %% directories


class SceneSource(StrEnum):
    """
    Where a scenes directory's bundles come from, in the order a bundle of the same name
    is preferred.
    """

    LOCAL = "local"
    """
    Recordings made on this machine.
    """

    SHARED = "shared"
    """
    The configured shared scenes directory.
    """

    DEMO = "demo"
    """
    The demo scenes shipped with the viewer.
    """


@dataclass(frozen=True)
class BundleProblem:
    """
    A bundle that a scenes directory holds but the viewer cannot read.
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
class SceneDirectory:
    """
    One directory of scene bundles.
    """

    path: Path
    """
    The directory holding the bundles and, optionally, their ``index.json``.
    """

    source: SceneSource
    """
    Where the bundles come from.
    """

    def index(self) -> SceneIndex:
        """
        :return: The directory's ``index.json``, or an index derived from its bundles
            when it has none.
        """
        index_file = self.path / ScenesDirectoryFile.INDEX
        if index_file.is_file():
            return SceneIndex.from_json(
                json.loads(index_file.read_text(encoding="utf-8"))
            )
        return self.derived_index().index

    def derived_index(self) -> DerivedIndex:
        """
        :return: An index of every readable bundle, with the bundles that could not
            be read.
        """
        derived = DerivedIndex(index=SceneIndex(format_version=CURRENT_VERSION))
        if not self.path.is_dir():
            return derived
        for bundle in sorted(self.path.iterdir()):
            if not (bundle / BundleFile.SCENE).is_file():
                continue
            derived.add(BundleEntryReader(bundle).read())
        return derived

    def holds(self, name: str) -> bool:
        """
        :param name: A bundle name.
        :return: Whether this directory holds a bundle of that name.
        """
        return (self.path / name / BundleFile.SCENE).is_file()

    def bundle(self, name: str) -> ConfinedDirectory:
        """
        :param name: A bundle name this directory holds.
        :return: The bundle directory, confined to the bundle.
        """
        return ConfinedDirectory(self.path / name)


@dataclass
class DerivedIndex:
    """
    An index built by reading every bundle of a directory.
    """

    index: SceneIndex
    """
    The readable bundles.
    """

    problems: List[BundleProblem] = field(default_factory=list)
    """
    The bundles that could not be read.
    """

    def add(self, read: Union[SceneIndexEntry, BundleProblem]) -> None:
        """
        :param read: What reading one bundle gave.
        """
        if isinstance(read, BundleProblem):
            self.problems.append(read)
            return
        self.index.scenes.append(read)


@dataclass(frozen=True)
class BundleEntryReader:
    """
    Reads the index entry of one bundle from its ``scene.json``.
    """

    bundle: Path
    """
    The bundle directory.
    """

    def read(self) -> Union[SceneIndexEntry, BundleProblem]:
        """
        A bundle with a broken ``scene.json`` must not hide its readable neighbours, so
        this is the one place where reading errors become data.

        :return: The bundle's entry, or the reason it cannot be read.
        """
        if not SceneName.is_valid(self.bundle.name):
            return BundleProblem(
                bundle=self.bundle, reason=str(InvalidSceneName(self.bundle.name))
            )
        try:
            data = json.loads(
                (self.bundle / BundleFile.SCENE).read_text(encoding="utf-8")
            )
            description = SceneDescription.from_json(data)
        except (ValueError, ProtocolError) as error:
            return BundleProblem(bundle=self.bundle, reason=str(error))
        return self.entry_of(description)

    def entry_of(self, description: SceneDescription) -> SceneIndexEntry:
        """
        :param description: The bundle's scene description.
        :return: How the pickers offer the bundle: the labels a person gave win over
            the names the models carry.
        """
        robot = description.robot_name or (
            description.robot.name if description.robot is not None else ""
        )
        environment = description.environment_name or (
            "+".join(model.name for model in description.models if not model.robot)
            or None
        )
        return SceneIndexEntry(
            name=self.bundle.name,
            robot=robot,
            environment=environment,
            task=description.task,
        )


# %% catalog


@dataclass(frozen=True)
class SceneCatalog:
    """
    Every bundle of several scenes directories; a bundle in a directory of an earlier
    :class:`SceneSource` hides one of the same name in a later directory.
    """

    directories: Sequence[SceneDirectory]
    """
    The scenes directories.
    """

    def ordered_directories(self) -> List[SceneDirectory]:
        """
        :return: The directories in the order their bundles are preferred.
        """
        order = list(SceneSource)
        return sorted(
            self.directories, key=lambda directory: order.index(directory.source)
        )

    def index(self) -> SceneIndex:
        """
        :return: One index of every visible bundle; the default is the first
            directory's default that is visible.
        """
        merged = SceneIndex(format_version=CURRENT_VERSION)
        seen: Dict[str, SceneIndexEntry] = {}
        defaults: List[Optional[str]] = []
        for directory in self.ordered_directories():
            index = directory.index()
            defaults.append(index.default)
            for entry in index.scenes:
                if entry.name not in seen and directory.holds(entry.name):
                    seen[entry.name] = entry
                    merged.scenes.append(entry)
        merged.default = next((name for name in defaults if name in seen), None)
        return merged

    def directory_of(self, name: str) -> SceneDirectory:
        """
        A reserved bundle, the live world or a recording before it is saved, is served
        only from a local directory, where this machine's publisher writes it.

        :param name: A bundle name.
        :return: The directory whose bundle of that name is shown.
        :raises UnknownScene: When no directory holds a valid bundle of that name.
        """
        reserved = name in {member.value for member in ReservedSceneName}
        if not reserved and not SceneName.is_valid(name):
            raise UnknownScene(name)
        sources = [SceneSource.LOCAL] if reserved else list(SceneSource)
        for directory in self.ordered_directories():
            if directory.source in sources and directory.holds(name):
                return directory
        raise UnknownScene(name)

    def bundle_file(self, name: str, requested: str) -> Path:
        """
        :param name: A bundle name.
        :param requested: A file of the bundle, relative to the bundle directory.
        :return: The file.
        :raises UnknownScene: When no directory holds the bundle.
        :raises PathOutsideDirectory: When the path leaves the bundle.
        :raises FileNotInDirectory: When the bundle has no such file.
        """
        return self.directory_of(name).bundle(name).file(requested)
