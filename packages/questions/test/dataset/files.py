"""
Where the test files are.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

DATASET = Path(__file__).parent
"""
The directory of the test files.
"""

# %% files


class SceneName(StrEnum):
    """
    The bundles of the dataset.
    """

    ANNOTATED = "annotated_run"
    """
    A recording with annotated parts, statecharts, plans and detections.
    """

    LEGACY = "legacy_run"
    """
    One of the earliest recordings, naming its parts without annotations.
    """


SCENES = DATASET / "scenes"
"""
The scenes directory of the dataset.
"""

IMPORT_PLUGIN_WITHOUT_KRROOD = DATASET / "scripts" / "import_plugin_without_krrood.py"
"""
A script importing the questions plugin while krrood and cramera-bridge cannot be
imported.
"""
