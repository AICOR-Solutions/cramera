"""
The browser application's tests, run in Node.js against the generated protocol module.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cramera.application import WEB_DIRECTORY
from cramera_protocol.browser import BrowserModule

TESTS = Path(__file__).parent / "js"
"""
The directory of the browser tests.
"""


@pytest.fixture
def protocol_module() -> Path:
    """
    :return: ``protocol.js`` written next to the browser modules, as the server
        serves it.
    """
    module = WEB_DIRECTORY / "protocol.js"
    module.write_text(BrowserModule().source(), encoding="utf-8")
    return module


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_the_browser_modules_pass_their_tests(protocol_module):
    tests = sorted(str(path) for path in TESTS.glob("test_*.mjs"))
    result = subprocess.run(
        [
            "node",
            "--import",
            str(TESTS / "support" / "import-map.mjs"),
            "--test",
            *tests,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-3000:]
