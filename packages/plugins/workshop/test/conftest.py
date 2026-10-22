"""
Shared fixtures of the workshop plugin's tests.

The contact world needs MuJoCo, and the robot demos need the CRAM workspace. Where they
are missing, the test modules that need them are not collected, so the suite skips them
cleanly and the rest still runs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from cramera_workshop.bundle import WorkshopBundle
from cramera_workshop.plugin import PhysicsLibraries

TESTS_NEEDING_PHYSICS = ("test_collision_model.py", "test_physics.py")
"""
The test modules that simulate the contact world.
"""

TESTS_NEEDING_CRAM = ("cram",)
"""
The test modules and directories that build CRAM worlds and plans.
"""

CRAM_PACKAGES = ("semantic_digital_twin", "coraplex", "giskardpy", "cramera_cram")
"""
The packages the CRAM tests import.
"""

DATASET = Path(__file__).parent / "dataset"
"""
The directory holding the test documents.
"""

collect_ignore = []
if PhysicsLibraries().missing():
    collect_ignore.extend(TESTS_NEEDING_PHYSICS)
if any(importlib.util.find_spec(package) is None for package in CRAM_PACKAGES):
    collect_ignore.extend(TESTS_NEEDING_CRAM)


@pytest.fixture
def dataset() -> Path:
    """
    :return: The directory holding the test documents.
    """
    return DATASET


@pytest.fixture(scope="session")
def bundle() -> WorkshopBundle:
    """
    :return: The AICOR workshop this package ships.
    """
    return WorkshopBundle.packaged()
