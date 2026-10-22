"""
Running a plugin's browser tests in Node.js against the viewer's modules, resolved the
way the viewer serves them.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from cramera.application import WEB_DIRECTORY
from cramera_protocol.browser import BrowserModule

TESTING_DIRECTORY = Path(__file__).parent
"""
The directory of the Node helpers: the resolve hook and the fake document.
"""


class BrowserTestVariable(StrEnum):
    """
    The environment variables the resolve hook reads.
    """

    VIEWER_WEB = "CRAMERA_VIEWER_WEB"
    """
    The viewer's web directory.
    """

    PLUGIN_WEB = "CRAMERA_PLUGIN_WEB"
    """
    The plugin's web directory.
    """


@dataclass(frozen=True)
class PluginBrowserTests:
    """
    The Node tests of one plugin's browser modules.
    """

    plugin_web: Path
    """
    The plugin's web directory, served at ``/plugins/<name>/``.
    """

    tests: Path
    """
    The directory holding the plugin's ``test_*.mjs`` files.
    """

    viewer_web: Path = WEB_DIRECTORY
    """
    The viewer's web directory.
    """

    def run(self) -> subprocess.CompletedProcess:
        """
        Write ``protocol.js`` next to the viewer's modules, as the server serves it, and
        run every test file.

        :return: The finished Node process with its output.
        """
        (self.viewer_web / "protocol.js").write_text(
            BrowserModule().source(), encoding="utf-8"
        )
        environment = {
            **os.environ,
            BrowserTestVariable.VIEWER_WEB: str(self.viewer_web),
            BrowserTestVariable.PLUGIN_WEB: str(self.plugin_web),
        }
        return subprocess.run(
            [
                "node",
                "--import",
                str(TESTING_DIRECTORY / "plugin-import-map.mjs"),
                "--test",
                *sorted(str(path) for path in self.tests.glob("test_*.mjs")),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
