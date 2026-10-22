"""
Presentation directories: the bundles a storyboard shows, copied out of the scenes
directories they were recorded into, with the storyboard and a scenes index next to
them.

A presentation directory is a scenes directory the viewer can serve.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from typing_extensions import List, Sequence

from cramera.scenes import BundleEntryReader, SceneCatalog, SceneDirectory, SceneSource
from cramera.static_site import StaticSite
from cramera_offline.bundle_check import BundleCheck
from cramera_offline.exceptions import IncompleteBundles, PresentationExists
from cramera_offline.json_file import JsonFile
from cramera_offline.plugin import OfflinePlugin
from cramera_protocol.bundle.files import ScenesDirectoryFile
from cramera_protocol.bundle.index import SceneIndex, SceneIndexEntry
from cramera_protocol.offline import BundleCheckReport, PresentationFile, Storyboard
from cramera_protocol.version import CURRENT_VERSION
from cramera_protocol.viewer import ViewerInfo, ViewerRoute

# %% presentation


@dataclass(frozen=True)
class PresentationDirectory:
    """
    A prepared presentation: bundles, ``index.json`` and ``storyboard.json``.
    """

    path: Path
    """
    The directory.
    """

    def storyboard(self) -> Storyboard:
        """
        :return: The presentation's storyboard.
        :raises UnreadableFile: When the storyboard is not JSON.
        :raises ProtocolError: When it is not a valid storyboard.
        """
        return Storyboard.from_json(
            JsonFile(self.path / PresentationFile.STORYBOARD).read()
        )

    def check(self) -> List[BundleCheckReport]:
        """
        :return: The completeness report of every bundle the storyboard shows.
        """
        return [
            BundleCheck(self.path / name).report()
            for name in self.storyboard().scene_names()
        ]

    def scene_directory(self) -> SceneDirectory:
        """
        :return: The presentation as the viewer's scenes directory.
        """
        return SceneDirectory(self.path, SceneSource.SHARED)


@dataclass(frozen=True)
class PresentationPreparation:
    """
    Writes a new presentation directory from a storyboard and the scenes directories
    holding its bundles.
    """

    storyboard_file: Path
    """
    The storyboard to present.
    """

    sources: Sequence[Path]
    """
    The scenes directories the bundles are taken from; a bundle in an earlier directory
    hides one of the same name in a later one.
    """

    destination: Path
    """
    The presentation directory to write; it must be absent or empty.
    """

    def prepare(self) -> PresentationDirectory:
        """
        Every bundle is checked before anything is written, so a refused preparation
        leaves no partial presentation behind.

        :return: The written presentation.
        :raises PresentationExists: When the destination holds files.
        :raises UnknownScene: When no source holds a bundle the storyboard shows.
        :raises IncompleteBundles: When a bundle does not hold every file it references.
        """
        if self.destination.exists() and any(self.destination.iterdir()):
            raise PresentationExists(self.destination)
        storyboard = Storyboard.from_json(JsonFile(self.storyboard_file).read())
        catalog = SceneCatalog(
            [SceneDirectory(source, SceneSource.SHARED) for source in self.sources]
        )
        bundles = [
            catalog.directory_of(name).path / name for name in storyboard.scene_names()
        ]
        incomplete = [
            report
            for report in (BundleCheck(bundle).report() for bundle in bundles)
            if not report.is_complete()
        ]
        if incomplete:
            raise IncompleteBundles(incomplete)
        self.destination.mkdir(parents=True, exist_ok=True)
        for bundle in bundles:
            shutil.copytree(bundle, self.destination / bundle.name)
        storyboard.format_version = CURRENT_VERSION
        JsonFile(self.destination / PresentationFile.STORYBOARD).write(
            storyboard.to_json()
        )
        JsonFile(self.destination / ScenesDirectoryFile.INDEX).write(
            self.index(storyboard, bundles).to_json()
        )
        return PresentationDirectory(self.destination)

    @staticmethod
    def index(storyboard: Storyboard, bundles: List[Path]) -> SceneIndex:
        """
        :param storyboard: The presented storyboard.
        :param bundles: The bundle directories it shows.
        :return: The scenes index of the presentation, opening the first chapter's
            bundle.
        """
        entries = [BundleEntryReader(bundle).read() for bundle in bundles]
        return SceneIndex(
            format_version=CURRENT_VERSION,
            default=storyboard.chapters[0].scene,
            scenes=[entry for entry in entries if isinstance(entry, SceneIndexEntry)],
        )


# %% static site


@dataclass(frozen=True)
class PresentationSite:
    """
    Writes a presentation as a static site: the viewer's static export of its bundles,
    the offline plugin's browser files, and the storyboard at the plugin's route, so any
    local web server can present it without Python.
    """

    presentation: PresentationDirectory
    """
    The presentation to export.
    """

    output: Path
    """
    The directory to write the site to; it must be absent or empty.
    """

    def write(self) -> SceneIndex:
        """
        :return: The index of the exported bundles.
        :raises SiteDirectoryNotEmpty: When the output directory holds files.
        """
        storyboard = self.presentation.storyboard()
        site = StaticSite(
            output=self.output,
            scenes=self.presentation.path,
            default_scene=storyboard.chapters[0].scene,
        )
        index = site.write()
        plugin = OfflinePlugin()
        shutil.copytree(
            plugin.web_directory(),
            site.route_file(ViewerRoute.PLUGIN_FILES) / plugin.name(),
        )
        site.write_route(plugin.storyboard_route(), storyboard)
        site.write_route(
            ViewerRoute.INFO,
            ViewerInfo(version=version("cramera"), plugins=[plugin.info()]),
        )
        return index
