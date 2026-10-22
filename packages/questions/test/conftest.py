"""
Shared fixtures of the cramera-questions tests.

The tests need krrood from the CRAM workspace; without it they are not collected, so the
suite skips cleanly where CRAM is not installed.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

if importlib.util.find_spec("krrood") is None:
    collect_ignore_glob = ["*"]
else:
    from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource

    from .dataset.files import SCENES

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
