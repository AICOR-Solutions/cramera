"""
The plugin's browser modules, tested in Node.js inside a copy of the viewer's browser
files, where they sit as the viewer serves them.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cramera.application import WEB_DIRECTORY
from cramera.static_site import SiteFile
from cramera_offline.plugin import OfflinePlugin
from cramera_protocol.browser import BrowserModule
from cramera_protocol.viewer import ViewerRoute

TESTS = Path(__file__).parent / "js"
"""
The directory of the browser tests.
"""

VIEWER_TEST_SUPPORT = WEB_DIRECTORY.parents[2] / "test" / "js" / "support"
"""
The viewer's browser test support in the repository, with its stand-in document.
"""

SUPPORT_DIRECTORY = "support"
"""
Where the tests find the viewer's test support, next to themselves.
"""

TEST_DIRECTORY = "test"
"""
Where the tests sit inside the plugin's copied browser files.
"""


@pytest.fixture
def test_directory(tmp_path: Path) -> Path:
    """
    :return: The tests inside a copy of the viewer's browser files, with the generated
        protocol module and the plugin's files at the plugin's path.
    """
    web = tmp_path / "web"
    shutil.copytree(
        WEB_DIRECTORY,
        web,
        ignore=shutil.ignore_patterns(
            "vendor", SiteFile.PROTOCOL_MODULE, "__pycache__"
        ),
    )
    (web / SiteFile.PROTOCOL_MODULE).write_text(
        BrowserModule().source(), encoding="utf-8"
    )
    plugin = OfflinePlugin()
    plugin_directory = web / ViewerRoute.PLUGIN_FILES.strip("/") / plugin.name()
    shutil.copytree(plugin.web_directory(), plugin_directory)
    tests = plugin_directory / TEST_DIRECTORY
    shutil.copytree(TESTS, tests)
    shutil.copytree(VIEWER_TEST_SUPPORT, tests / SUPPORT_DIRECTORY)
    return tests


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_the_browser_modules_pass_their_tests(test_directory):
    tests = sorted(str(path) for path in test_directory.glob("test_*.mjs"))
    result = subprocess.run(
        ["node", "--test", *tests], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-3000:]
