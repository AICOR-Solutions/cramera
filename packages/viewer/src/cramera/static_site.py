"""
``cramera-export-site``: the viewer and a directory of scenes as a static site, which
any web server can serve without Python, such as GitHub Pages.

The viewer's two JSON routes become files at the same paths, and ``protocol.js`` is
generated next to the page.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path

from typing_extensions import Optional, Sequence

from cramera.application import WEB_DIRECTORY
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_protocol.browser import BrowserModule
from cramera_protocol.bundle.index import SceneIndex
from cramera_protocol.document import JsonDocument
from cramera_protocol.viewer import BuildStamp, ViewerInfo, ViewerRoute

# %% vocabulary


class SiteFile(StrEnum):
    """
    The files the export writes besides the viewer's own.
    """

    PROTOCOL_MODULE = "protocol.js"
    """
    The protocol's names as an ES module.
    """

    NO_JEKYLL = ".nojekyll"
    """
    Tells GitHub Pages to serve files and directories starting with ``_`` as they are.
    """


class ExportOption(StrEnum):
    """
    The command's options.
    """

    SCENES = "--scenes"
    """
    The directory of the bundles to publish.
    """

    DEFAULT_SCENE = "--default-scene"
    """
    The bundle the page opens first.
    """

    COMMIT = "--commit"
    """
    The commit the site is built from.
    """

    SOURCE = "--source"
    """
    The web address of the repository.
    """


# %% export


class SiteDirectoryNotEmpty(FileExistsError):
    """
    An export target that already holds files.
    """


@dataclass(frozen=True)
class StaticSite:
    """
    Writes the viewer and the bundles of one scenes directory as a static site.
    """

    output: Path
    """
    The directory to write the site to; it must be absent or empty.
    """

    scenes: Path
    """
    The directory of the bundles to publish.
    """

    default_scene: Optional[str] = None
    """
    The bundle the page opens first, or None for the first bundle.
    """

    build: Optional[BuildStamp] = None
    """
    The build stamp the page shows, or None for none.
    """

    web_directory: Path = WEB_DIRECTORY
    """
    The browser application's files.
    """

    def write(self) -> SceneIndex:
        """
        :return: The index of the published bundles.
        :raises SiteDirectoryNotEmpty: When the output directory holds files.
        """
        if self.output.exists() and any(self.output.iterdir()):
            raise SiteDirectoryNotEmpty(str(self.output))
        shutil.copytree(
            self.web_directory,
            self.output,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(SiteFile.PROTOCOL_MODULE, "__pycache__"),
        )
        (self.output / SiteFile.PROTOCOL_MODULE).write_text(
            BrowserModule().source(), encoding="utf-8"
        )
        (self.output / SiteFile.NO_JEKYLL).write_text("", encoding="utf-8")
        index = SceneCatalog([SceneDirectory(self.scenes, SceneSource.DEMO)]).index()
        index.default = self.default_scene or index.default
        for entry in index.scenes:
            shutil.copytree(
                self.scenes / entry.name,
                self.route_file(ViewerRoute.SCENE_FILES) / entry.name,
            )
        self.write_route(ViewerRoute.SCENES, index)
        self.write_route(
            ViewerRoute.INFO, ViewerInfo(version=version("cramera"), build=self.build)
        )
        return index

    def route_file(self, route: str) -> Path:
        """
        :param route: A viewer route.
        :return: The file or directory of the site that answers it.
        """
        return self.output / route.strip("/")

    def write_route(self, route: str, document: JsonDocument) -> None:
        """
        :param route: A JSON route of the viewer.
        :param document: Its answer.
        """
        path = self.route_file(route)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document.to_json()), encoding="utf-8")


def main(arguments: Optional[Sequence[str]] = None) -> int:
    """
    Export the site.

    :param arguments: The command-line arguments; the process arguments when None.
    :return: The process exit code.
    """
    parser = argparse.ArgumentParser(
        prog="cramera-export-site", description=__doc__.strip().splitlines()[0]
    )
    parser.add_argument("output", type=Path)
    parser.add_argument(ExportOption.SCENES, type=Path, required=True)
    parser.add_argument(ExportOption.DEFAULT_SCENE, default=None)
    parser.add_argument(ExportOption.COMMIT, default=None)
    parser.add_argument(ExportOption.SOURCE, default=None)
    parsed = parser.parse_args(arguments)
    build = None
    if parsed.commit:
        built_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        build = BuildStamp(
            commit=parsed.commit, built_at=built_at, source=parsed.source
        )
    index = StaticSite(
        parsed.output, parsed.scenes, parsed.default_scene, build
    ).write()
    print(f"exported {len(index.scenes)} scenes to {parsed.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
