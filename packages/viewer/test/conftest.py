"""
Shared fixtures of the viewer tests.
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

DATASET = Path(__file__).parent / "dataset"
"""
The directory holding the test scenes and plugin files.
"""


@pytest.fixture
def scenes(tmp_path: Path) -> Path:
    """
    :return: A copy of the test scene directories that tests may change.
    """
    for name in ("local_scenes", "shared_scenes", "demo_scenes"):
        shutil.copytree(DATASET / name, tmp_path / name)
    return tmp_path


@pytest.fixture
def catalog(scenes: Path) -> SceneCatalog:
    """
    :return: A catalog of the local, shared and demo test scenes, given out of order.
    """
    return SceneCatalog(
        [
            SceneDirectory(scenes / "demo_scenes", SceneSource.DEMO),
            SceneDirectory(scenes / "shared_scenes", SceneSource.SHARED),
            SceneDirectory(scenes / "local_scenes", SceneSource.LOCAL),
        ]
    )


@pytest.fixture
def locations(scenes: Path) -> DataLocations:
    """
    :return: Locations whose data directory holds the local test scenes.
    """
    return DataLocations(data=scenes / "data", shared_scenes=scenes / "shared_scenes")


@pytest.fixture
def answerer(catalog: SceneCatalog, locations: DataLocations) -> RequestAnswerer:
    """
    :return: The viewer's request answerer without plugins.
    """
    application = ViewerApplication(catalog=catalog, locations=locations)
    return RequestAnswerer(router=application.router(), policy=OriginPolicy())
