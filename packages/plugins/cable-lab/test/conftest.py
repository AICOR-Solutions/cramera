"""
Shared fixtures of the cable lab's tests.

The simulation needs MuJoCo and the CRAM workspace. Where they are missing, the test
modules that simulate are not collected, so the suite skips them cleanly and the rest
still runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cramera_cable_lab.plugin import SimulationLibraries

TESTS_NEEDING_SIMULATION = ("test_cable.py", "test_physics.py")
"""
The test modules that simulate a cable.
"""

DATASET = Path(__file__).parent / "dataset"
"""
The directory holding the test documents.
"""

collect_ignore = (
    list(TESTS_NEEDING_SIMULATION) if SimulationLibraries().missing() else []
)


@pytest.fixture
def dataset() -> Path:
    """
    :return: The directory holding the test documents.
    """
    return DATASET
