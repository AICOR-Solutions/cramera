"""
The browser modules' tests, run in Node.js against the viewer's modules and the
generated protocol module, as the viewer serves them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cramera.testing.browser_tests import PluginBrowserTests
from cramera_plan_builder.plugin import WEB_DIRECTORY
from cramera_protocol.plan_builder import PlanBuilderName


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_the_browser_modules_pass_their_tests():
    result = PluginBrowserTests(
        plugin_web=WEB_DIRECTORY,
        tests=Path(__file__).parent / "js",
        plugin_name=PlanBuilderName.PLUGIN,
    ).run()
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-3000:]
