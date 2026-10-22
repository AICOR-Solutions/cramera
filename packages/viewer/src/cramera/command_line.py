"""
``cramera``: serve the viewer.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import webbrowser
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import List, Optional, Sequence

from cramera.application import ViewerApplication
from cramera.http.origin import OriginPolicy
from cramera.http.server import HttpServer, RequestAnswerer
from cramera.locations import DataLocations
from cramera.plugins import PluginLoader
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource

logger = logging.getLogger(__name__)
"""
The logger of the command.
"""


class Option(StrEnum):
    """
    The command's options.
    """

    HOST = "--host"
    """
    The address to listen on.
    """

    PORT = "--port"
    """
    The port to listen on.
    """

    SCENES = "--scenes"
    """
    A further shared scenes directory.
    """

    DEMO_SCENES = "--demo-scenes"
    """
    A directory of demo scenes.
    """

    NO_BROWSER = "--no-browser"
    """
    Do not open the viewer in a browser.
    """


DEFAULT_PORT = 8711
"""
The port the viewer listens on unless told otherwise.
"""

# %% configuration


@dataclass(frozen=True)
class ViewerConfiguration:
    """
    What the ``cramera`` command was asked to serve.
    """

    locations: DataLocations
    """
    Where cramera keeps its data.
    """

    host: str = "127.0.0.1"
    """
    The address to listen on.
    """

    port: int = DEFAULT_PORT
    """
    The port to listen on.
    """

    extra_scenes: List[Path] = field(default_factory=list)
    """
    Further shared scenes directories.
    """

    demo_scenes: Optional[Path] = None
    """
    A directory of demo scenes.
    """

    open_browser: bool = True
    """
    Whether to open the viewer in a browser.
    """

    @classmethod
    def from_arguments(
        cls, arguments: Sequence[str], locations: DataLocations
    ) -> ViewerConfiguration:
        """
        :param arguments: The command-line arguments without the program name.
        :param locations: The locations the environment configures.
        :return: The configuration they describe.
        """
        parser = argparse.ArgumentParser(
            prog="cramera", description="Serve the cramera viewer."
        )
        parser.add_argument(Option.HOST, default="127.0.0.1")
        parser.add_argument(Option.PORT, type=int, default=DEFAULT_PORT)
        parser.add_argument(Option.SCENES, type=Path, action="append", default=[])
        parser.add_argument(Option.DEMO_SCENES, type=Path, default=None)
        parser.add_argument(Option.NO_BROWSER, action="store_true")
        parsed = parser.parse_args(list(arguments))
        return cls(
            locations=locations,
            host=parsed.host,
            port=parsed.port,
            extra_scenes=parsed.scenes,
            demo_scenes=parsed.demo_scenes,
            open_browser=not parsed.no_browser,
        )

    def scene_directories(self) -> List[SceneDirectory]:
        """
        :return: The local, shared and demo scenes directories.
        """
        directories = [SceneDirectory(self.locations.local_scenes, SceneSource.LOCAL)]
        shared = [self.locations.shared_scenes, *self.extra_scenes]
        directories += [
            SceneDirectory(path, SceneSource.SHARED)
            for path in shared
            if path is not None
        ]
        if self.demo_scenes is not None:
            directories.append(SceneDirectory(self.demo_scenes, SceneSource.DEMO))
        return directories

    def server(self) -> HttpServer:
        """
        :return: The viewer's server, not yet started.
        """
        application = ViewerApplication(
            catalog=SceneCatalog(self.scene_directories()),
            locations=self.locations,
            plugins=PluginLoader().load(),
        )
        answerer = RequestAnswerer(router=application.router(), policy=OriginPolicy())
        return HttpServer(
            answerer=answerer,
            host=self.host,
            port=self.port,
            on_stop=[application.close],
        )


# %% command


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    Serve the viewer until the process is interrupted or terminated.

    :param arguments: The command-line arguments; the process arguments when None.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    locations = DataLocations.from_environment(os.environ, Path.home())
    configuration = ViewerConfiguration.from_arguments(
        arguments if arguments is not None else sys.argv[1:], locations
    )
    stop_signals = {signal.SIGINT, signal.SIGTERM}
    signal.pthread_sigmask(signal.SIG_BLOCK, stop_signals)
    with configuration.server() as server:
        logger.info("cramera serves %s", server.url())
        if configuration.open_browser:
            webbrowser.open(server.url())
        signal.sigwait(stop_signals)


if __name__ == "__main__":
    main()
