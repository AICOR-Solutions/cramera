"""
Shared fixtures of the cramera-questions tests.

Most tests need krrood from the CRAM workspace. Where it is missing, only the tests
listed in :data:`TESTS_WITHOUT_KRROOD` are collected, so the suite skips the rest
cleanly and the pure logic still runs.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource

from .dataset.files import SCENES

TESTS_WITHOUT_KRROOD = (
    "test_browser_modules.py",
    "test_presets_and_matching.py",
    "test_recorded_bundle.py",
    "test_urdf_structure.py",
)
"""
The test modules that import nothing of krrood.
"""

TEST_DIRECTORY = Path(__file__).parent
"""
The directory of this package's tests.
"""

if importlib.util.find_spec("krrood") is None:
    collect_ignore = [
        path.name
        for path in TEST_DIRECTORY.glob("test_*.py")
        if path.name not in TESTS_WITHOUT_KRROOD
    ]


@pytest.fixture
def scenes(tmp_path: Path) -> Path:
    """
    :return: A copy of the dataset's scenes that tests may change.
    """
    copy = tmp_path / "scenes"
    shutil.copytree(SCENES, copy)
    return copy


@pytest.fixture
def catalog(scenes: Path) -> SceneCatalog:
    """
    :return: A catalog of the dataset's scenes.
    """
    return SceneCatalog([SceneDirectory(scenes, SceneSource.LOCAL)])
