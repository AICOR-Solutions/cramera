"""
Shared fixtures of the cramera-cram tests.

The tests need the CRAM workspace; without it they are not collected, so the suite skips
cleanly where CRAM is not installed.
"""

from __future__ import annotations

import importlib.util

import pytest

CRAM_PACKAGES = ("semantic_digital_twin", "coraplex", "giskardpy", "krrood")
"""
The CRAM packages every test of this package imports.
"""

if any(importlib.util.find_spec(package) is None for package in CRAM_PACKAGES):
    collect_ignore_glob = ["*"]
else:
    from .dataset.worlds import KitchenWorld, RobotWorld

    @pytest.fixture
    def kitchen() -> KitchenWorld:
        """
        :return: A new kitchen world.
        """
        return KitchenWorld.build()

    @pytest.fixture(scope="session")
    def robot_world() -> RobotWorld:
        """
        :return: A world holding a PR2, shared by the tests that only read it.
        """
        return RobotWorld.build()
