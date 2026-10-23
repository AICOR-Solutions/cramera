"""
The questions plugin in a viewer installation without krrood.
"""

from __future__ import annotations

import subprocess
import sys

from cramera_protocol.plugins import PluginName

from .dataset.files import IMPORT_PLUGIN_WITHOUT_KRROOD


def test_the_plugin_imports_without_krrood():
    result = subprocess.run(
        [sys.executable, str(IMPORT_PLUGIN_WITHOUT_KRROOD)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == PluginName.QUESTIONS.value
