"""
The browser modules' tests, run in Node.js against the viewer's modules and the
generated protocol module, as the viewer serves them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cramera.testing.browser_tests import PluginBrowserTests

WEB_DIRECTORY = Path(__file__).parent.parent / "src" / "cramera_laboratory" / "web"
"""
The plugin's browser files.
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_the_browser_modules_pass_their_tests():
    result = PluginBrowserTests(
        plugin_web=WEB_DIRECTORY, tests=Path(__file__).parent / "js"
    ).run()
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-3000:]
