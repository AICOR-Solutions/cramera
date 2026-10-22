"""
Running ``cramera-export`` on the test stages.
"""

from __future__ import annotations

import os
from pathlib import Path

from typing_extensions import Dict

from cramera_usd.commands.export_scene import ExportCommand, ExportExit, ExportParser
from cramera_usd.commands.import_scene import ImportOption
from cramera_usd.export.import_process import ImportEnvironment, NO_MEMORY_LIMIT

from .stages import Stage

# %% labels

ENVIRONMENT_NAME = "Test cell"
"""
The environment name the test exports give.
"""

# %% export


def environment() -> Dict[str, str]:
    """
    :return: The process environment without a memory cap, so the conversion runs in
        any test environment.
    """
    return {**os.environ, ImportEnvironment.MEMORY_LIMIT: NO_MEMORY_LIMIT}


def export(stage: Stage, scenes: Path, name: str, *options: str) -> ExportExit:
    """
    Run ``cramera-export`` on a test stage.

    :param stage: The test stage.
    :param scenes: The scenes directory to publish into.
    :param name: The bundle name.
    :param options: Further command line options.
    :return: The export's exit code.
    """
    request = ExportParser(scenes).parse(
        [
            str(stage.path),
            ImportOption.NAME,
            name,
            ImportOption.ENVIRONMENT_NAME,
            ENVIRONMENT_NAME,
            *options,
        ]
    )
    return ExportCommand(request, environment()).run()
