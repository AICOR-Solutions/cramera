"""
The scene builder as a viewer plugin: where it keeps its files, which directories its
resource library holds, and the routes and browser files it adds.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path

from typing_extensions import Dict, List, Mapping, Optional

from cramera.locations import DataLocations
from cramera.plugins import (
    NavigationEntry,
    PageEntry,
    PluginContext,
    RouteDeclaration,
    ViewerPlugin,
)
from cramera.scenes import SceneCatalog
from cramera_protocol.bundle.index import SceneName
from cramera_protocol.scene_builder import (
    ReservedResourceRoot,
    SceneBuilderFile,
    SceneBuilderLimits,
    SceneBuilderName,
    SceneBuilderVariable,
)
from cramera_protocol.viewer import NavigationGroup
from cramera_scene_builder.drafts import DraftCheck, DraftStore
from cramera_scene_builder.exceptions import InvalidRootName
from cramera_scene_builder.resources import ResourceLibrary
from cramera_scene_builder.routes import SceneBuilderRoutes
from cramera_scene_builder.uploads import PointCloudStore

WEB_DIRECTORY = Path(__file__).parent / "web"
"""
The scene builder's browser files.
"""

NAVIGATION_TITLE = "Scene Builder"
"""
The text of the plugin's entry in the viewer's navigation.
"""

# %% storage


class StorageDirectory(StrEnum):
    """
    The directories the scene builder writes, below cramera's data directory.
    """

    BUILDER = "scene-builder"
    """
    The scene builder's own directory.
    """

    DRAFTS = "drafts"
    """
    The saved drafts, below :attr:`BUILDER`.
    """

    POINT_CLOUDS = "point-clouds"
    """
    The uploaded point clouds, below :attr:`BUILDER`.
    """


class Distribution(StrEnum):
    """
    The package the scene builder is installed from.
    """

    NAME = "cramera-scene-builder"
    """
    The distribution's name, under which its version is recorded.
    """


@dataclass(frozen=True)
class SceneBuilderStorage:
    """
    Where the scene builder keeps drafts and uploaded point clouds, apart from every
    source file.
    """

    directory: Path
    """
    The scene builder's directory.
    """

    @classmethod
    def of(cls, locations: DataLocations) -> SceneBuilderStorage:
        """
        :param locations: Where cramera keeps its data.
        :return: The storage below cramera's data directory.
        """
        return cls(directory=locations.data / StorageDirectory.BUILDER)

    @property
    def drafts(self) -> Path:
        """
        The directory of the saved drafts.
        """
        return self.directory / StorageDirectory.DRAFTS

    @property
    def point_clouds(self) -> Path:
        """
        The directory of the uploaded point clouds.
        """
        return self.directory / StorageDirectory.POINT_CLOUDS


# %% library


@dataclass
class LibraryRoots:
    """
    The named directories of the resource library: the uploaded point clouds, the
    viewer's scenes directories named after their source, and the directories the
    environment adds, named after themselves.
    """

    roots: Dict[str, Path] = field(default_factory=dict)
    """
    The directory of each root, by root name.
    """

    @classmethod
    def of(
        cls,
        catalog: SceneCatalog,
        storage: SceneBuilderStorage,
        environment: Mapping[str, str],
    ) -> LibraryRoots:
        """
        :param catalog: The scenes the viewer shows.
        :param storage: Where the scene builder keeps its files.
        :param environment: The process environment.
        :return: The roots.
        :raises InvalidRootName: When a directory's name is no root name or names
            another root already.
        """
        roots = cls()
        roots.add(ReservedResourceRoot.POINT_CLOUDS, storage.point_clouds)
        for directory in catalog.ordered_directories():
            roots.add(directory.source, directory.path)
        configured = environment.get(SceneBuilderVariable.LIBRARY, "")
        for text in configured.split(os.pathsep):
            if text:
                directory = Path(text).expanduser()
                roots.add(directory.name, directory)
        return roots

    def add(self, name: str, directory: Path) -> None:
        """
        :param name: The root's name.
        :param directory: The root's directory.
        :raises InvalidRootName: When the name is no root name or names another root.
        """
        if not SceneName.is_valid(name) or name in self.roots:
            raise InvalidRootName(directory)
        self.roots[name] = directory

    def library(self) -> ResourceLibrary:
        """
        :return: The library of these roots.
        """
        return ResourceLibrary.of(self.roots)


# %% plugin


@dataclass
class SceneBuilderPlugin(ViewerPlugin):
    """
    Arranges copies of existing models, robots and scanned rooms into scene drafts.
    """

    environment: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    """
    The process environment, which may add library directories.
    """

    limits: SceneBuilderLimits = field(default_factory=SceneBuilderLimits)
    """
    The bounds drafts and uploads stay within.
    """

    def name(self) -> str:
        return SceneBuilderName.PLUGIN

    def version(self) -> str:
        return version(Distribution.NAME)

    def routes(self, context: PluginContext) -> List[RouteDeclaration]:
        """
        :param context: What the viewer offers the plugin.
        :return: The scene builder's routes.
        :raises InvalidRootName: When a library directory cannot be a root.
        """
        storage = SceneBuilderStorage.of(context.locations)
        library = LibraryRoots.of(context.catalog, storage, self.environment).library()
        return SceneBuilderRoutes(
            catalog=context.catalog,
            library=library,
            drafts=DraftStore(storage.drafts, DraftCheck(self.limits)),
            point_clouds=PointCloudStore(storage.point_clouds, self.limits),
            limits=self.limits,
        ).declarations()

    def web_directory(self) -> Optional[Path]:
        return WEB_DIRECTORY

    def module(self) -> Optional[str]:
        return SceneBuilderFile.MODULE

    def navigation(self) -> Optional[NavigationEntry]:
        return PageEntry(
            NAVIGATION_TITLE, NavigationGroup.BUILDER, SceneBuilderFile.PAGE.value
        )
