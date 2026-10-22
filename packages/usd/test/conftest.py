"""
Shared fixtures of the converter's tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# %% fixtures

DATASET = Path(__file__).parent / "dataset"
"""
The directory holding the test stages, traces and images.
"""


@pytest.fixture
def dataset() -> Path:
    """
    :return: The directory holding the test stages, traces and images.
    """
    return DATASET
