"""
A screenshot of a published bundle in the viewer, taken when the viewer is installed.
"""

from __future__ import annotations

import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import TYPE_CHECKING, Callable, Optional

from cramera_protocol.page import PageParameter
from cramera_usd.distribution import Distribution
from cramera_usd.exceptions import ViewerNotInstalled

if TYPE_CHECKING:
    from cramera.screenshot import PageReport, WebDriver

# %% constants

SCREENSHOT_MODULE = "cramera.screenshot"
"""
The viewer's module that takes screenshots.
"""

PAGE_PATH = "/"
"""
The path of the viewer's page.
"""

ANY_FREE_PORT = 0
"""
The port that lets the viewer pick a free one.
"""

# %% screenshot


@dataclass(frozen=True)
class ViewerScreenshot:
    """
    Serves a scenes directory with the viewer and screenshots one of its bundles in a
    headless Firefox.
    """

    scenes_directory: Path
    """
    The scenes directory the viewer serves.
    """

    name: str
    """
    The bundle to show.
    """

    output: Path
    """
    The PNG file to write.
    """

    def available(self) -> bool:
        """
        :return: Whether the viewer that takes the screenshot is installed.
        """
        return Distribution.VIEWER.importable(SCREENSHOT_MODULE)

    def page(self, server_url: str) -> str:
        """
        :param server_url: The base address of a viewer serving the scenes directory.
        :return: The address of the page showing the bundle.
        """
        query = urllib.parse.urlencode({PageParameter.SCENE.value: self.name})
        address = urllib.parse.urlsplit(server_url)
        return address._replace(path=PAGE_PATH, query=query).geturl()

    def take(
        self, driver_factory: Optional[Callable[[], WebDriver]] = None
    ) -> PageReport:
        """
        Serve the scenes directory, with empty local recordings so the viewer offers
        these bundles only, and screenshot the bundle's page.

        :param driver_factory: Makes the WebDriver to use; a Firefox driver when None.
        :return: What the page reported when the screenshot was taken.
        :raises ViewerNotInstalled: When the viewer is not installed.
        """
        if not self.available():
            raise ViewerNotInstalled(Distribution.VIEWER.value)
        # The viewer is an optional extra, imported only once it is known to be there.
        from cramera.command_line import ViewerConfiguration
        from cramera.locations import DataLocations
        from cramera.screenshot import BrowserKind, Screenshot, WebDriver

        with tempfile.TemporaryDirectory() as data:
            configuration = ViewerConfiguration(
                locations=DataLocations(
                    data=Path(data), shared_scenes=self.scenes_directory
                ),
                port=ANY_FREE_PORT,
                open_browser=False,
            )
            driver = (
                WebDriver(BrowserKind.FIREFOX)
                if driver_factory is None
                else driver_factory()
            )
            with configuration.server() as server, driver:
                return Screenshot(url=self.page(server.url()), output=self.output).take(
                    driver
                )
