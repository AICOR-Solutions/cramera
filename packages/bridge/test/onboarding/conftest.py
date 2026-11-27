"""
Fixtures of the onboarding tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cramera.locations import DataLocations

from ..dataset.onboarding.sliding_box_demo import SlidingBoxWorld

ONBOARDING_DATASET = Path(__file__).parent.parent / "dataset" / "onboarding"
"""
The demo files the onboarding tests run.
"""

SLIDING_BOX_DEMO = ONBOARDING_DATASET / "sliding_box_demo.py"
"""
A demo performing a plan through a coraplex plan executor.
"""


@pytest.fixture
def locations(tmp_path: Path) -> DataLocations:
    """
    :return: Data locations in a temporary directory, with a shared scenes directory.
    """
    return DataLocations(data=tmp_path / "data", shared_scenes=tmp_path / "shared")


@pytest.fixture
def sliding_box() -> SlidingBoxWorld:
    """
    :return: A new world of a box above a table.
    """
    return SlidingBoxWorld.build()
