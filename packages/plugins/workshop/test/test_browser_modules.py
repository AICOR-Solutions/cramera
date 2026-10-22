"""
The plugin's browser modules, tested in Node.js against the viewer's modules as the
viewer serves them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cramera.testing.browser_tests import PluginBrowserTests
from cramera_workshop.plugin import WorkshopPlugin


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_the_browser_modules_pass_their_tests():
    result = PluginBrowserTests(
        plugin_web=WorkshopPlugin().web_directory(), tests=Path(__file__).parent / "js"
    ).run()
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-3000:]
