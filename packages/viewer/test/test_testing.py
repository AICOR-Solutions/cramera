"""
Running a plugin's browser tests through cramera.testing.
"""

from __future__ import annotations

import shutil

import pytest

from cramera.testing.browser_tests import PluginBrowserTests

from .conftest import DATASET


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_a_plugin_s_browser_tests_run_against_the_viewer_modules():
    result = PluginBrowserTests(
        plugin_web=DATASET / "plugin_web", tests=DATASET / "plugin_browser_tests"
    ).run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# pass 1" in result.stdout
