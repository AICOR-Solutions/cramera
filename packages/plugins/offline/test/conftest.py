"""
Shared fixtures of the offline plugin's tests.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cramera.application import ViewerApplication
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.locations import DataLocations
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_offline.plugin import OfflinePlugin

DATASET = Path(__file__).parent / "dataset"
"""
The directory holding the test bundles and storyboards.
"""


@pytest.fixture
def dataset() -> Path:
    """
    :return: The directory holding the test bundles and storyboards.
    """
    return DATASET


@pytest.fixture
def recorded_scenes(tmp_path: Path) -> Path:
    """
    :return: A copy of the recorded test bundles that tests may change.
    """
    return Path(shutil.copytree(DATASET / "recorded_scenes", tmp_path / "recorded"))


@pytest.fixture
def complete_bundle(recorded_scenes: Path) -> Path:
    """
    :return: The bundle that holds every file it references.
    """
    return recorded_scenes / "complete_cell"


@pytest.fixture
def broken_bundle(recorded_scenes: Path) -> Path:
    """
    :return: The bundle with one reference of every kind that cannot be followed.
    """
    return recorded_scenes / "broken_cell"


@pytest.fixture
def storyboard_file() -> Path:
    """
    :return: The storyboard showing the complete bundle.
    """
    return DATASET / "storyboard.json"


@pytest.fixture
def answerer(recorded_scenes: Path) -> RequestAnswerer:
    """
    :return: The viewer's request answerer over the recorded test bundles, with the
        offline plugin.
    """
    application = ViewerApplication(
        catalog=SceneCatalog([SceneDirectory(recorded_scenes, SceneSource.SHARED)]),
        locations=DataLocations(data=recorded_scenes, shared_scenes=recorded_scenes),
        plugins=[OfflinePlugin()],
    )
    return RequestAnswerer(router=application.router(), policy=OriginPolicy())
